"""E2 後端 UI API:工作階段的開啟、結束與查詢(testplan.md § 2.1)。

接縫:HTTP `/api/*` 與 SSE `/api/events`,五個轉接層用替身(testplan.md § 接縫的取捨)。
"""

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from cgb.app import AppPair

from cgb.adapters.errors import AdapterError
from fakes import Gate

T4 = {"gpu": "T4", "highMem": False}
# 替身預設的 `OllamaStarted`(Q59):15 GiB 的 T4,自動值 2/4096/1(test_api_tuning.py 從這裡匯入)
T4_STARTED = {
    "ollamaVersion": "0.40.15",
    "alreadyRunning": False,
    "machine": {
        "gpuName": "Tesla T4",
        "vramTotalBytes": 15 * 1073741824,
        "systemMemoryTotalBytes": 13_605_855_232,
        "probedAt": "2026-11-15T09:00:00Z",
    },
    "tuning": {
        "numParallel": {"value": 2, "source": "auto"},
        "contextLength": {"value": 4096, "source": "auto"},
        "maxLoadedModels": {"value": 1, "source": "auto"},
        "flashAttention": {"value": True, "source": "auto"},
        "kvCacheType": {"value": "q8_0", "source": "auto"},
    },
}
NAME_PATTERN = re.compile(r"^cgb-test-[a-z0-9-]+$")


@pytest.fixture
async def ui_client(app_pair: AppPair) -> AsyncIterator[httpx.AsyncClient]:
    """UI 的 ASGI 用戶端;app 內未處理的例外照 HTTP 500 回給測試(UI 看到的就是 500),不直接丟進測試。"""
    async with app_pair.ui.router.lifespan_context(app_pair.ui):
        transport = httpx.ASGITransport(app=app_pair.ui, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://cgb-ui.test") as client:
            yield client


class ColabWorld:
    """替身背後一個最小的 Colab 帳號:記得哪些執行環境還在,並依序記下每一次轉接層呼叫。

    `create_session` 成功就把名稱加進 `colab sessions`,`stop_session` 成功就拿掉;
    測試要改某一次的結果時,照替身的 `then()`、`raises()` 覆寫。
    """

    def __init__(self, fakes: Any) -> None:
        self.fakes = fakes
        self.alive: list[str] = []
        self.unnamed: list[dict[str, str]] = []
        self.hardware: dict[str, str] = {}  # 名稱 → `colab sessions` 列出的硬體,沒寫的是 T4
        self.log: list[tuple[str, Any]] = []
        self.start_result: dict[str, Any] = T4_STARTED  # `start_ollama` 回的結果;測試要別的機器時換掉
        colab, tunnel, remote = fakes.colab, fakes.tunnel, fakes.remote_ollama

        colab.get_usage.side_effect(self._usage)
        colab.list_sessions.side_effect(self._list)
        colab.create_session.side_effect(self._create)
        colab.start_ollama.side_effect(self._start_ollama)
        colab.stop_session.side_effect(self._stop)
        tunnel.open_tunnel.side_effect(self._open_tunnel)
        tunnel.close_tunnel.side_effect(self._close_tunnel)
        tunnel.check_health.side_effect(self._check_health)
        tunnel.cleanup_residual.side_effect(self._cleanup)
        remote.get_version.side_effect(lambda *a, **k: {"version": "0.40.15"})
        remote.list_loaded_models.side_effect(lambda *a, **k: {"models": []})
        # 剩餘磁碟夠大(下載佇列自動繼續前會重新讀,testplan.md § US3-API-19)
        colab.probe_resources.side_effect(self._probe)

    def _probe(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.log.append(("probe_resources", kwargs.get("name")))
        return {
            "diskFreeBytes": 225_485_783_040,
            "diskTotalBytes": 253_338_115_072,
            "gpuName": "Tesla T4",
            "vramTotalBytes": 16_106_127_360,
            "vramFreeBytes": 15_727_591_424,
            "checkedAt": "2026-11-09T09:00:00Z",
        }

    def _usage(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.log.append(("get_usage", None))
        return {"balance": 100.0, "ratePerHour": 1.76, "activeAssignments": len(self.alive), "readAt": "2026-11-09T09:00:00Z"}

    def _list(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.log.append(("list_sessions", None))
        return {
            "named": [
                {"name": n, "hardware": self.hardware.get(n, "T4"), "shape": "Standard", "variant": "GPU"} for n in self.alive
            ],
            "unnamed": [dict(u) for u in self.unnamed],
        }

    def _create(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        name = kwargs["name"]
        self.log.append(("create_session", name))
        self.alive.append(name)
        return {"name": name, "hardware": kwargs["gpu"], "shape": "Standard", "highMemIgnored": False}

    def _start_ollama(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.log.append(("start_ollama", kwargs.get("name")))
        return self.start_result

    def _stop(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        name = kwargs["name"]
        self.log.append(("stop_session", name))
        if name in self.alive:
            self.alive.remove(name)
        return {"name": name, "stopOutput": "terminated"}

    def _open_tunnel(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        name = kwargs["session_name"]
        self.log.append(("open_tunnel", name))
        return {
            "sessionName": name,
            "baseUrl": self.fakes.server.base_url,
            "remoteOllamaVersion": "0.40.15",
            "connectedAt": "2026-11-09T09:00:00Z",
            "elapsedMs": 0,
        }

    def _close_tunnel(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        name = kwargs.get("session_name")
        self.log.append(("close_tunnel", name))
        return {"sessionName": name, "wasRunning": True, "forced": False}

    def _check_health(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        name = kwargs.get("session_name")
        return {"sessionName": name, "healthy": True, "remoteOllamaVersion": "0.40.15", "checkedAt": "2026-11-09T09:00:00Z", "latencyMs": 1}

    def _cleanup(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.log.append(("cleanup_residual", None))
        return {"killed": 0}

    def calls(self, method: str) -> list[Any]:
        return [arg for name, arg in self.log if name == method]


def error_code(response: httpx.Response) -> str | None:
    """錯誤回應的 `Error.code`;本文不是 JSON 時(例如未處理的例外變成的 500)是 None。"""
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json().get("code")
    return None


async def get_session(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get("/api/session")
    return response.json()


async def wait_for_state(client: httpx.AsyncClient, state: str, timeout: float = 3.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    session = await get_session(client)
    while session.get("state") != state and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
        session = await get_session(client)
    return session


async def states_until_entered(client: httpx.AsyncClient, gate: Gate, timeout: float = 3.0) -> list[str]:
    """一直查 `GET /api/session`,直到下一個替身走到閘門前;回傳期間看到的每一個 `state`。"""
    seen: list[str] = []
    deadline = time.monotonic() + timeout
    while gate.entered == 0 and time.monotonic() < deadline:
        seen.append((await get_session(client)).get("state"))
        await asyncio.sleep(0.005)
    seen.append((await get_session(client)).get("state"))
    return seen


# ---------------------------------------------------------------- US1-API-01


async def test_開啟立即受理_通道與模型服務就緒後才是就緒(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    create_gate = fakes.colab.create_session.gate()
    start_gate = fakes.colab.start_ollama.gate()
    tunnel_gate = fakes.tunnel.open_tunnel.gate()

    # Act
    response = await ui_client.post("/api/session", json={"runtimeType": T4})
    accepted = (response.status_code, response.json().get("state"))
    states_before_tunnel = await states_until_entered(ui_client, create_gate)
    create_gate.release()
    states_before_tunnel += await states_until_entered(ui_client, start_gate)
    start_gate.release()
    states_before_tunnel += await states_until_entered(ui_client, tunnel_gate)
    tunnel_gate.release()
    final = await wait_for_state(ui_client, "ready")

    # Assert
    assert accepted == (202, "opening")
    assert "ready" not in states_before_tunnel
    assert (final.get("state"), final.get("runtimeType")) == ("ready", T4)
    assert fakes.colab.create_session.call_count == 1
    created = fakes.colab.create_session.last_call.kwargs
    assert (created["gpu"], created["high_mem"]) == ("T4", False)
    assert NAME_PATTERN.match(created["name"])
    assert world.calls("create_session") == [created["name"]]


async def test_建立通道前先準備通道金鑰_同一把金鑰給通道(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    """實跑發現:開啟流程從沒呼叫 ensureTunnelKey(tunnel 合約 openTunnel 的前置(1)),全新部署沒有金鑰,
    每次開啟都在建立通道時 TUNNEL_KEY_REJECTED;整批實跑會過只是因為主機階段先在共用資料夾產生了金鑰。"""
    # Arrange
    ColabWorld(fakes)
    key_gate = fakes.tunnel.ensure_key.gate()

    # Act
    await ui_client.post("/api/session", json={"runtimeType": T4})
    await key_gate.wait_entered_async()
    tunnel_calls_while_preparing_key = fakes.tunnel.open_tunnel.call_count
    key_gate.release()
    await wait_for_state(ui_client, "ready")

    # Assert
    key_path = fakes.tunnel.ensure_key.last_call.kwargs.get("key_path") or fakes.tunnel.ensure_key.last_call.args[0]
    assert tunnel_calls_while_preparing_key == 0
    assert fakes.tunnel.open_tunnel.last_call.kwargs["key_path"] == key_path


# ---------------------------------------------------------------- US1-API-02


async def test_開啟時照使用者選的類型_CLI_忽略高_RAM_時仍記下使用者的選擇(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)

    def create_l4(*args: Any, **kwargs: Any) -> dict[str, Any]:
        created = world._create(*args, **kwargs)
        return {**created, "hardware": "L4", "highMemIgnored": True}

    fakes.colab.create_session.side_effect(create_l4)

    # Act
    await ui_client.post("/api/session", json={"runtimeType": {"gpu": "L4", "highMem": True}})
    final = await wait_for_state(ui_client, "ready")

    # Assert
    created = fakes.colab.create_session.last_call.kwargs
    assert (created["gpu"], created["high_mem"]) == ("L4", True)
    assert final.get("runtimeType") == {"gpu": "L4", "highMem": True}


# ---------------------------------------------------------------- US1-API-03


async def test_開啟時不在可選清單的類型一律拒絕_不呼叫_CLI(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    bodies = [
        {"runtimeType": {"gpu": "t4", "highMem": False}},
        {"runtimeType": {"gpu": "TPU", "highMem": False}},
        {"runtimeType": {"gpu": "V100", "highMem": False}},
        {"runtimeType": {"gpu": "T4", "highMem": "yes"}},
    ]

    # Act
    responses = [await ui_client.post("/api/session", json=body) for body in bodies]
    await asyncio.sleep(0.1)

    # Assert
    results = [(r.status_code, r.json().get("code") if r.status_code == 400 else None) for r in responses]
    assert all(status == 400 and code in {"INVALID_RUNTIME_TYPE", "INVALID_REQUEST_BODY"} for status, code in results), results
    assert fakes.colab.create_session.call_count == 0


# ---------------------------------------------------------------- US1-API-04


async def test_同時送兩個開啟只開一台(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    create_gate = fakes.colab.create_session.gate()

    # Act
    first, second = await asyncio.gather(
        ui_client.post("/api/session", json={"runtimeType": T4}),
        ui_client.post("/api/session", json={"runtimeType": T4}),
    )
    await asyncio.sleep(0.1)
    create_gate.release()

    # Assert
    outcomes = sorted((r.status_code, error_code(r)) for r in (first, second))
    assert outcomes == [(202, None), (409, "SESSION_ALREADY_ACTIVE")]
    assert fakes.colab.create_session.call_count == 1


async def open_ready(client: httpx.AsyncClient, runtime_type: dict[str, Any] = T4) -> dict[str, Any]:
    """開一個工作階段並等到就緒。"""
    response = await client.post("/api/session", json={"runtimeType": runtime_type})
    assert response.status_code == 202, response.text
    return await wait_for_state(client, "ready")


# ---------------------------------------------------------------- US1-API-05


async def test_就緒或結束中時不能再開啟(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)

    # Act
    while_ready = await ui_client.post("/api/session", json={"runtimeType": T4})
    stop_gate = fakes.colab.stop_session.gate()
    await ui_client.delete("/api/session")
    while_ending = await ui_client.post("/api/session", json={"runtimeType": T4})
    stop_gate.release()

    # Assert
    assert (while_ready.status_code, error_code(while_ready)) == (409, "SESSION_ALREADY_ACTIVE")
    assert "已有工作階段" in while_ready.json()["message"]
    assert (while_ending.status_code, error_code(while_ending)) == (409, "SESSION_ENDING")
    assert fakes.colab.create_session.call_count == 1


# ---------------------------------------------------------------- US1-API-06


async def test_沒有授權時開啟要先登入_不呼叫_CLI_開機(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    fakes.colab.get_usage.raises("AUTH_REQUIRED")

    # Act
    response = await ui_client.post("/api/session", json={"runtimeType": T4})
    await asyncio.sleep(0.1)
    auth = await ui_client.get("/api/auth")

    # Assert
    assert (response.status_code, error_code(response)) == (409, "AUTH_REQUIRED")
    assert fakes.colab.create_session.call_count == 0
    assert auth.status_code == 200 and auth.json().get("state") == "logged_out"


# ---------------------------------------------------------------- US1-API-07


async def test_結束時先關通道再釋放執行環境_確認後為使用者結束(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    name = (await open_ready(ui_client))["name"]
    stop_gate = fakes.colab.stop_session.gate()

    # Act
    response = await ui_client.delete("/api/session")
    accepted = (response.status_code, response.json().get("state"))
    await stop_gate.wait_entered_async()
    stop_gate.release()
    final = await wait_for_state(ui_client, "ended")

    # Assert
    assert accepted == (202, "ending")
    order = [method for method, arg in world.log if method in ("close_tunnel", "stop_session") and arg == name]
    assert order == ["close_tunnel", "stop_session"]
    assert (final.get("state"), final.get("endReason")) == ("ended", "USER_ENDED")
    assert final.get("endedAt") is not None
    assert "releaseWarning" in final and final["releaseWarning"] is None


async def wait_until(client: httpx.AsyncClient, predicate: Any, timeout: float = 3.0) -> dict[str, Any]:
    """一直查 `GET /api/session`,直到 `predicate(session)` 成立或逾時;回傳最後一次看到的。"""
    deadline = time.monotonic() + timeout
    session = await get_session(client)
    while not predicate(session) and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
        session = await get_session(client)
    return session


# ---------------------------------------------------------------- US1-API-08


async def test_釋放失敗時留下警告_再按結束會再試一次(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await open_ready(ui_client)
    fakes.colab.stop_session.then(AdapterError("COLAB_STOP_UNCONFIRMED", "兩次結束後仍看得到這個執行環境"))

    # Act
    await ui_client.delete("/api/session")
    after_first = await wait_until(ui_client, lambda s: s.get("state") not in ("ready", "ending"))
    second = await ui_client.delete("/api/session")
    after_second = await wait_until(ui_client, lambda s: s.get("state") == "ended" and s.get("releaseWarning") is None)

    # Assert
    warning = after_first.get("releaseWarning") or {}
    assert warning.get("message") is not None
    assert warning.get("reasonCode") == "COLAB_STOP_UNCONFIRMED"
    assert second.status_code == 202
    assert fakes.colab.stop_session.call_count == 2
    assert after_second.get("releaseWarning") is None
    assert world.alive == []


# ---------------------------------------------------------------- US1-API-09


async def test_沒有可以結束的工作階段時結束回錯誤_不呼叫_colab_stop(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)

    # Act
    never_opened = await ui_client.delete("/api/session")
    stops_before = fakes.colab.stop_session.call_count
    await open_ready(ui_client)
    await ui_client.delete("/api/session")
    await wait_until(ui_client, lambda s: s.get("state") == "ended")
    stops_after_end = fakes.colab.stop_session.call_count
    already_ended = await ui_client.delete("/api/session")
    await asyncio.sleep(0.1)

    # Assert
    assert (never_opened.status_code, error_code(never_opened)) == (409, "NO_ACTIVE_SESSION")
    assert (already_ended.status_code, error_code(already_ended)) == (409, "NO_ACTIVE_SESSION")
    assert stops_before == 0
    assert fakes.colab.stop_session.call_count == stops_after_end


def calls_after(world: ColabWorld, first: str, then: str) -> list[Any]:
    """`world.log` 裡最後一次 `first` 之後的每一次 `then` 呼叫。"""
    methods = [method for method, _ in world.log]
    if first not in methods:
        return []
    start = len(methods) - 1 - methods[::-1].index(first)
    return [arg for method, arg in world.log[start + 1 :] if method == then]


# ---------------------------------------------------------------- US1-API-10


async def test_開啟失敗時附上原因_並確認沒有遺留(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)

    def refuse(*args: Any, **kwargs: Any) -> None:
        world.log.append(("create_session", kwargs["name"]))
        raise AdapterError("COLAB_ALLOCATION_REFUSED", "Colab 拒絕配置")

    fakes.colab.create_session.side_effect(refuse)

    # Act
    await ui_client.post("/api/session", json={"runtimeType": T4})
    final = await wait_until(ui_client, lambda s: s.get("state") not in ("opening",))

    # Assert
    assert (final.get("state"), final.get("endReason"), final.get("reasonCode")) == (
        "open_failed",
        "OPEN_FAILED",
        "COLAB_ALLOCATION_REFUSED",
    )
    assert final.get("message")
    assert len(calls_after(world, "create_session", "list_sessions")) >= 1


# ---------------------------------------------------------------- US1-API-11


async def test_啟動_Ollama_失敗時釋放已配置的執行環境(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    fakes.colab.start_ollama.raises("COLAB_REMOTE_ERROR", "遠端腳本失敗")

    # Act
    response = await ui_client.post("/api/session", json={"runtimeType": T4})
    name = response.json()["name"]
    final = await wait_until(ui_client, lambda s: s.get("state") == "open_failed" and fakes.colab.stop_session.call_count > 0)
    await asyncio.sleep(0.05)

    # Assert
    assert (final.get("state"), final.get("reasonCode")) == ("open_failed", "COLAB_REMOTE_ERROR")
    assert world.calls("stop_session") == [name]
    assert (await get_session(ui_client)).get("releaseWarning") is None


# ---------------------------------------------------------------- US1-API-12


async def test_開啟超過總時限即失敗並釋放(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:開啟總時限注入 3 秒(conftest 的 TEST_TIMEOUTS)
    world = ColabWorld(fakes)
    fakes.colab.start_ollama.gate()

    # Act
    started = time.monotonic()
    response = await ui_client.post("/api/session", json={"runtimeType": T4})
    name = response.json()["name"]
    final = await wait_until(ui_client, lambda s: s.get("state") != "opening", timeout=5.0)
    elapsed = time.monotonic() - started
    await wait_until(ui_client, lambda s: bool(world.calls("stop_session")), timeout=1.0)

    # Assert
    assert (final.get("state"), final.get("reasonCode")) == ("open_failed", "COLAB_TIMEOUT")
    assert 3.0 <= elapsed <= 3.5, elapsed
    assert world.calls("stop_session") == [name]


# ---------------------------------------------------------------- US1-API-13


async def test_配置中按結束_等_colab_new_結束後才釋放_不再往下開(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    create_gate = fakes.colab.create_session.gate()
    name = (await ui_client.post("/api/session", json={"runtimeType": T4})).json()["name"]
    await create_gate.wait_entered_async()

    # Act
    response = await ui_client.delete("/api/session")
    accepted = (response.status_code, response.json().get("state"))
    await asyncio.sleep(0.1)
    stops_before_release = list(world.calls("stop_session"))
    create_gate.release()
    final = await wait_until(ui_client, lambda s: s.get("state") == "ended" and bool(world.calls("stop_session")))
    await asyncio.sleep(0.1)

    # Assert
    assert accepted == (202, "ending")
    assert stops_before_release == []
    assert world.calls("create_session") == [name]  # colab new 跑完了(替身沒有被取消)
    assert calls_after(world, "create_session", "stop_session") == [name]
    assert (final.get("state"), final.get("endReason")) == ("ended", "USER_ENDED")
    assert fakes.colab.start_ollama.call_count == 0


# ---------------------------------------------------------------- US1-API-14


async def test_colab_new_逾時後多出沒有名稱的執行環境時警告_不去結束它(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)

    def time_out(*args: Any, **kwargs: Any) -> None:
        world.log.append(("create_session", kwargs["name"]))
        world.unnamed.append({"hardware": "T4", "shape": "Standard", "variant": "GPU"})
        raise AdapterError("COLAB_TIMEOUT", "colab new 逾時")

    fakes.colab.create_session.side_effect(time_out)

    # Act
    response = await ui_client.post("/api/session", json={"runtimeType": T4})
    name = response.json()["name"]
    final = await wait_until(ui_client, lambda s: s.get("state") == "open_failed" and s.get("releaseWarning") is not None)

    # Assert
    assert (final.get("state"), final.get("reasonCode")) == ("open_failed", "COLAB_TIMEOUT")
    assert (final.get("releaseWarning") or {}).get("message") is not None
    assert all(stopped == name for stopped in world.calls("stop_session"))


# ---------------------------------------------------------------- US1-API-15


async def test_名稱不在_colab_sessions_時不建立通道(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:`colab new` 成功,但之後 `colab sessions` 沒有列出這個名稱
    world = ColabWorld(fakes)

    def create_unlisted(*args: Any, **kwargs: Any) -> dict[str, Any]:
        created = world._create(*args, **kwargs)
        world.alive.remove(kwargs["name"])
        return created

    fakes.colab.create_session.side_effect(create_unlisted)

    # Act
    await ui_client.post("/api/session", json={"runtimeType": T4})
    final = await wait_until(ui_client, lambda s: s.get("state") not in ("opening",))
    await asyncio.sleep(0.05)

    # Assert
    assert fakes.tunnel.open_tunnel.call_count == 0
    assert final.get("state") == "open_failed"
    assert final.get("reasonCode") in {"COLAB_NOT_FOUND", "TUNNEL_NOT_FOUND"}


# ---------------------------------------------------------------- US1-API-16


async def test_通道回報找不到執行環境時結束意外開出的那台並確認(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:`colab ssh` 意外開出新的執行環境並已被關閉(contracts/tunnel.openapi.yaml § x-stderr-patterns)
    world = ColabWorld(fakes)
    fakes.tunnel.open_tunnel.raises("TUNNEL_NOT_FOUND", "要連的執行環境不在")

    # Act
    response = await ui_client.post("/api/session", json={"runtimeType": T4})
    name = response.json()["name"]
    final = await wait_until(
        ui_client, lambda s: s.get("state") == "open_failed" and bool(calls_after(world, "stop_session", "list_sessions"))
    )

    # Assert
    assert name in world.calls("stop_session")
    assert len(calls_after(world, "stop_session", "list_sessions")) >= 1
    assert (final.get("state"), final.get("reasonCode")) == ("open_failed", "TUNNEL_NOT_FOUND")


# ---------------------------------------------------------------- US1-API-34


async def test_開啟途中授權過期時判定開啟失敗並要求重新登入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:讀用量時仍是已登入,`colab new` 時授權過期
    world = ColabWorld(fakes)

    def auth_expired(*args: Any, **kwargs: Any) -> None:
        world.log.append(("create_session", kwargs["name"]))
        raise AdapterError("AUTH_REQUIRED", "需要重新授權")

    fakes.colab.create_session.side_effect(auth_expired)

    # Act
    await ui_client.post("/api/session", json={"runtimeType": T4})
    final = await wait_until(ui_client, lambda s: s.get("state") != "opening")
    auth = (await ui_client.get("/api/auth")).json()

    # Assert
    assert (final.get("state"), final.get("reasonCode")) == ("open_failed", "AUTH_REQUIRED")
    assert auth.get("state") == "logged_out"
    assert final.get("state") != "lost"


# ---------------------------------------------------------------- US1-API-39


async def test_開啟中每一步開始時_step_就更新(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:每一步的替身各自等測試放行(verifying 那一步是遠端 Ollama 的 get_version)
    ColabWorld(fakes)
    gates = [
        fakes.colab.create_session.gate(),
        fakes.colab.start_ollama.gate(),
        fakes.tunnel.open_tunnel.gate(),
        fakes.remote_ollama.get_version.gate(),
    ]

    # Act
    await ui_client.post("/api/session", json={"runtimeType": T4})
    steps = []
    for gate in gates:
        await gate.wait_entered_async()
        steps.append((await get_session(ui_client)).get("step"))
        gate.release()
    final = await wait_for_state(ui_client, "ready")

    # Assert
    assert steps == ["allocating", "starting_ollama", "connecting", "verifying"]
    assert final.get("step") is None


# ---------------------------------------------------------------- US1-API-40

FAKE_ENDPOINT = "https://cgb-test-fake-endpoint.example"


async def test_開啟失敗後回應與事件都不含執行環境的位址(live_servers: Any, fakes: Any) -> None:
    # Arrange:轉接層的錯誤帶著原始字樣與 endpoint
    from integration.test_api_events import sse_events

    world = ColabWorld(fakes)

    def fail_with_endpoint(*args: Any, **kwargs: Any) -> None:
        world.log.append(("create_session", kwargs["name"]))
        raise AdapterError(
            "COLAB_FAILED",
            f"colab new 失敗:Failed to issue request POST {FAKE_ENDPOINT}/tun/m/assign: 500",
            stderr_last_line="Failed to issue request POST <網址>: 500",
        )

    fakes.colab.create_session.side_effect(fail_with_endpoint)
    received: list[str] = []

    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)

            # Act
            await client.post("/api/session", json={"runtimeType": {"gpu": "T4", "highMem": False}})

            async def collect() -> None:
                async for _, payload in events:
                    received.append(json.dumps(payload, ensure_ascii=False))
                    if payload.get("session", {}).get("state") == "open_failed":
                        return

            await asyncio.wait_for(collect(), 3.0)
        session = (await client.get("/api/session")).text
        history = (await client.get("/api/sessions")).text

    # Assert
    everything = [session, history, *received]
    assert any("open_failed" in text for text in received)
    assert all("cgb-test-fake-endpoint" not in text for text in everything)
    assert all(not re.search(r"https://\S*(colab|googleusercontent)", text) for text in everything)
