"""E2 後端 UI API:工作階段開著時套用新的 Ollama 設定並重啟(testplan.md § 4.2)。

接縫:HTTP `/api/*` 與 SSE `/api/events`,轉接層用替身(testplan.md § 接縫的取捨)。
套用的流程與時機照 contracts/ui.openapi.yaml 的 `info.x-apply-flow`、`info.x-applying-state` 與 contracts/store.dbml 的寫入時機。
"""

import asyncio
import json
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.app import AppPair
from cgb.domain.session_state import parse_iso
from conftest import FakeClock
from fakes import Gate, NdjsonReply
from integration.test_api_downloads import downloadable, enqueue_waiting, queue, states, wait_queue
from integration.test_api_events import sse_events
from integration.test_api_idle import set_idle_timeout, states_for
from integration.test_api_models import QWEN_7B, QWEN_SMALL
from integration.test_api_recovery import reset_calls
from integration.test_api_usage import running
from integration.test_ollama_compat import connect
from integration.test_api_tuning import (  # noqa: F401
    A100,
    GIB,
    L4,
    NONE3,
    A100_STARTED,
    applied,
    log_out,
    overrides,
    remember,
    record_of,
    restarted,
    sent_overrides,
    started,
    tuning_body,
)
from integration.test_api_session import T4, ColabWorld, error_code, open_ready, ui_client, wait_for_state, wait_until  # noqa: F401

LLAMA = "llama3.2:latest"
_A100_MACHINE = {"gpu_name": "NVIDIA A100-SXM4-40GB", "system_bytes": 89_632_571_392}
# 手動平行數 4 的重啟結果;同時載入模型數仍是自動值 2
A100_RESTARTED_4 = restarted(40 * GIB, applied(4, 8192, 2, sources=("manual", "auto", "auto")), **_A100_MACHINE)
# 改回自動值之後的重啟結果(三個覆蓋值都是 null,A100 的級距是 8/8192/2)
AUTO_RESTARTED = restarted(40 * GIB, applied(8, 8192, 2), **_A100_MACHINE)


async def apply_ready(client: httpx.AsyncClient, world: ColabWorld, fakes: Any, *loaded: str) -> dict[str, Any]:
    """A100 開到就緒,遠端 Ollama 已載入 `loaded`(依 `/api/ps` 的順序);套用時重啟成功回 `A100_RESTARTED_4`。

    `world.loaded` 是替身背後遠端 Ollama 現在載入的模型:`list_loaded_models` 讀它,重啟成功就清空(重啟後 `/api/ps` 是空的,research R1),
    預先載入把模型接到後面。
    """
    world.start_result = A100_STARTED
    world.restart_result = A100_RESTARTED_4
    world.loaded = list(loaded)

    def list_loaded(*args: Any, **kwargs: Any) -> dict[str, Any]:
        world.log.append(("list_loaded_models", None))
        return {"models": [{"name": model} for model in world.loaded]}

    def restart(*args: Any, **kwargs: Any) -> dict[str, Any]:
        world.log.append(("restart_ollama", kwargs.get("name")))
        world.loaded = []
        return world.restart_result

    def preload(*args: Any, **kwargs: Any) -> dict[str, Any]:
        model = kwargs["model"]
        world.log.append(("preload", model))
        world.loaded.append(model)
        return {"model": model, "done": True}

    fakes.remote_ollama.list_loaded_models.side_effect(list_loaded)
    fakes.colab.restart_ollama.side_effect(restart)
    fakes.remote_ollama.preload.side_effect(preload)
    return await open_ready(client, A100)


async def apply(client: httpx.AsyncClient, body: Any) -> httpx.Response:
    return await client.post("/api/session/tuning", json=body)


async def wait_applied(client: httpx.AsyncClient) -> dict[str, Any]:
    """等到 `state` 不是 `applying_tuning`(最多 1 秒);回傳最後一次看到的工作階段。"""
    return await wait_until(client, lambda s: s.get("state") != "applying_tuning", timeout=1.0)


def remote_error(stage: str | None) -> AdapterError:
    return AdapterError("COLAB_REMOTE_ERROR", f"遠端腳本失敗:{stage}", remote_stage=stage)


def restart_overrides(fakes: Any) -> list[dict[str, Any]]:
    """每一次 `restart_ollama` 收到的覆蓋值,依呼叫順序。"""
    return [call.kwargs["overrides"] for call in fakes.colab.restart_ollama.calls]


def preloaded(world: ColabWorld) -> list[str]:
    return world.calls("preload")


def fallback_split(fakes: Any, first_error: AdapterError, gate: Any = None) -> None:
    """`restart_ollama` 依 `overrides` 分流:不是 `NONE3` 的那一次丟 `first_error`;`NONE3` 的那一次(有 `gate` 時先等放行)回 `AUTO_RESTARTED`。"""

    async def split(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs["overrides"] != NONE3:
            raise first_error
        if gate is not None:
            await gate.pass_async()
        return AUTO_RESTARTED

    fakes.colab.restart_ollama.side_effect(split)


# ---- 005 US3-API-01


async def test_套用立即受理_重啟後依重啟前載入的模型重新載入才回到就緒(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)

    # Act
    accepted = await apply(ui_client, tuning_body(4, None, None))
    final = await wait_applied(ui_client)

    # Assert
    started = accepted.json()
    assert accepted.status_code == 202
    assert started["state"] == "applying_tuning"
    assert started["step"] == "restarting_ollama"
    assert started["ollama"]["lastApply"]["result"] == "in_progress"
    assert started["ollama"]["lastApply"]["attempt"] == "requested"
    assert started["ollama"]["tuning"]["numParallel"] == {"value": 8, "source": "auto"}
    assert restart_overrides(fakes) == [tuning_body(4, None, None)]
    assert preloaded(world) == [QWEN_7B]
    assert (final["state"], final["step"]) == ("ready", None)
    assert final["ollama"]["tuning"]["numParallel"] == {"value": 4, "source": "manual"}
    last = final["ollama"]["lastApply"]
    assert last["result"] == "applied"
    assert last["reloaded"] == [QWEN_7B]
    assert last["notReloaded"] == []
    assert last["finishedAt"] is not None


# ---- 005 US3-API-02


async def test_套用的每個步驟都推送_重啟後模型目錄先更新再開始重新載入(live_servers: Any, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    fakes.remote_ollama.list_local_models.side_effect(
        lambda *a, **k: {"models": [{"name": QWEN_7B, "size": 4_683_087_332, "modified_at": "2026-11-09T09:00:00Z"}]}
    )
    received: list[tuple[str, dict[str, Any]]] = []

    async def collect(response: httpx.Response) -> None:
        async for name, payload in sse_events(response):
            received.append((name, payload))

    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await apply_ready(client, world, fakes, QWEN_7B)
        restart_gate = fakes.colab.restart_ollama.gate()
        preload_gate = fakes.remote_ollama.preload.gate()
        async with client.stream("GET", "/api/events") as response:
            reader = asyncio.create_task(collect(response))
            while len(received) < 3:  # 連上時的快照:session.updated、downloads.snapshot、autoDownload.updated
                await asyncio.sleep(0.005)
            before = len(received)

            # Act
            await apply(client, tuning_body(4, None, None))
            await restart_gate.wait_entered_async()
            restarting = (await client.get("/api/session")).json()
            restart_gate.release()
            await preload_gate.wait_entered_async()
            reloading = (await client.get("/api/session")).json()
            preload_gate.release()
            for _ in range(200):  # 最多 1 秒
                if any(_is_ready_update(event) for event in received[before:]):
                    break
                await asyncio.sleep(0.005)
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)

    # Assert
    assert restarting["step"] == "restarting_ollama"
    assert restarting["idle"] is None
    assert reloading["state"] == "applying_tuning"
    assert reloading["step"] == "reloading_models"
    assert reloading["ollama"]["tuning"]["numParallel"] == {"value": 4, "source": "manual"}
    assert reloading["ollama"]["lastApply"]["result"] == "in_progress"
    assert reloading["ollama"]["lastApply"]["tuning"]["numParallel"] == {"value": 4, "source": "manual"}
    steps = [(e["session"]["state"], e["session"]["step"]) for name, e in received[before:] if name == "session.updated"]
    assert [step for i, step in enumerate(steps) if i == 0 or step != steps[i - 1]] == [
        ("applying_tuning", "restarting_ollama"),
        ("applying_tuning", "reloading_models"),
        ("ready", None),
    ]
    names = [(name, e["session"]["step"] if name == "session.updated" else None) for name, e in received[before:]]
    first_models = next(i for i, (name, _) in enumerate(names) if name == "models.updated")
    assert first_models < names.index(("session.updated", "reloading_models"))
    models = next(e for name, e in received[before:] if name == "models.updated")["catalog"]["items"]
    assert [m["loaded"] for m in models if m["name"] == QWEN_7B] == [False]


def _is_ready_update(event: tuple[str, dict[str, Any]]) -> bool:
    name, payload = event
    return name == "session.updated" and payload["session"]["state"] == "ready"


# ---- 005 US3-API-03


async def test_套用成功才記住這種類型的設定_下次開啟帶著它(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:A100 記住 2
    world = ColabWorld(fakes)
    await remember(ui_client, "A100", tuning_body(2, None, None))
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    restart_gate = fakes.colab.restart_ollama.gate()

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    await restart_gate.wait_entered_async()
    while_restarting = (await overrides(ui_client))["A100"]
    restart_gate.release()
    final = await wait_applied(ui_client)
    after = (await overrides(ui_client))["A100"]
    await ui_client.delete("/api/session")
    await wait_for_state(ui_client, "ended")
    await ui_client.post("/api/session", json={"runtimeType": A100})
    await wait_for_state(ui_client, "ready")

    # Assert
    assert while_restarting["numParallel"] == 2
    assert after["numParallel"] == 4
    assert after["updatedAt"] == final["ollama"]["lastApply"]["finishedAt"]
    assert sent_overrides(fakes) == tuning_body(4, None, None)


# ---- 005 US3-API-04


async def test_三個都改回自動時清除這種類型記住的設定(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:A100 記住 4/16384/2
    world = ColabWorld(fakes)
    await remember(ui_client, "A100", tuning_body(4, 16384, 2))
    await apply_ready(ui_client, world, fakes, QWEN_7B)

    # Act
    await apply(ui_client, NONE3)
    final = await wait_applied(ui_client)
    remembered = (await overrides(ui_client))["A100"]

    # Assert
    assert restart_overrides(fakes) == [NONE3]
    assert final["ollama"]["lastApply"]["result"] == "applied"
    assert (remembered["numParallel"], remembered["contextLength"], remembered["maxLoadedModels"]) == (None, None, None)
    assert remembered["updatedAt"] is None


# ---- 005 US3-API-05


async def test_和目前生效的設定相同也照常重啟(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:目前生效的是自動值 8/8192/2,A100 沒有記過任何覆蓋值
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)

    # Act
    accepted = await apply(ui_client, NONE3)
    final = await wait_applied(ui_client)

    # Assert
    assert accepted.status_code == 202
    assert fakes.colab.restart_ollama.call_count == 1
    assert final["ollama"]["lastApply"]["result"] == "applied"


# ---- 005 US3-API-06


async def test_手動設定重啟失敗時改回自動值再試_成功後不記住失敗的設定(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:A100 記住 2
    world = ColabWorld(fakes)
    await remember(ui_client, "A100", tuning_body(2, None, None))
    kept = (await overrides(ui_client))["A100"]
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    fallback_gate = Gate()
    fallback_split(fakes, remote_error("verify"), fallback_gate)

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    falling_back = await wait_until(ui_client, lambda s: fakes.colab.restart_ollama.call_count == 2, timeout=1.0)
    fallback_gate.release()
    final = await wait_applied(ui_client)
    remembered = (await overrides(ui_client))["A100"]

    # Assert
    assert (falling_back["state"], falling_back["step"]) == ("applying_tuning", "restarting_ollama")
    assert falling_back["ollama"]["lastApply"]["attempt"] == "auto_fallback"
    assert falling_back["ollama"]["lastApply"]["reasonCode"] == "COLAB_REMOTE_ERROR"
    assert restart_overrides(fakes) == [tuning_body(4, None, None), NONE3]
    assert final["state"] == "ready"
    last = final["ollama"]["lastApply"]
    assert last["result"] == "fell_back_to_auto"
    assert last["remoteStage"] == "verify"
    assert last["message"] == "手動設定沒有套用成功,已改回自動值"
    assert last["requested"] == tuning_body(4, None, None)
    assert final["ollama"]["tuning"]["numParallel"] == {"value": 8, "source": "auto"}
    assert preloaded(world) == [QWEN_7B]
    assert remembered == kept


# ---- 005 US3-API-07


@pytest.mark.parametrize(
    ("first_error", "stage"),
    [
        pytest.param(remote_error("stop"), "stop", id="停不掉舊的"),
        pytest.param(remote_error("start"), "start", id="啟動失敗"),
        pytest.param(AdapterError("COLAB_REMOTE_ERROR", "Traceback", remote_stage=None), None, id="遠端丟出例外"),
        pytest.param(AdapterError("COLAB_INVALID_TUNING", "stage input"), None, id="覆蓋值不符"),
    ],
)
async def test_遠端腳本失敗或覆蓋值不符都改回自動值再試(
    ui_client: httpx.AsyncClient, fakes: Any, first_error: AdapterError, stage: str | None
) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    fallback_split(fakes, first_error)

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    final = await wait_applied(ui_client)

    # Assert
    assert fakes.colab.restart_ollama.call_count == 2
    assert restart_overrides(fakes)[1:] == [NONE3]
    last = final["ollama"]["lastApply"]
    assert last["result"] == "fell_back_to_auto"
    assert last["reasonCode"] == first_error.code
    assert last["remoteStage"] == stage


# ---- 005 US3-API-08


@pytest.mark.parametrize(
    "code",
    [
        pytest.param("COLAB_UNREACHABLE", id="轉接層重跑後仍斷線"),
        pytest.param("COLAB_TIMEOUT", id="逾時"),
        pytest.param("COLAB_FAILED", id="指令失敗"),
        pytest.param("COLAB_BAD_RESPONSE", id="回應無法解讀"),
        pytest.param("COLAB_NOT_INSTALLED", id="找不到_colab"),
    ],
)
async def test_不是設定造成的失敗不改回自動值_直接失聯並釋放(ui_client: httpx.AsyncClient, fakes: Any, code: str) -> None:
    # Arrange
    world = ColabWorld(fakes)
    name = (await apply_ready(ui_client, world, fakes, QWEN_7B))["name"]
    fakes.colab.restart_ollama.raises(code)

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    final = await wait_applied(ui_client)

    # Assert
    assert fakes.colab.restart_ollama.call_count == 1
    assert final["state"] == "lost"
    assert final["endReason"] == "OLLAMA_RESTART_FAILED"
    assert final["reasonCode"] == code
    assert final["ollama"]["lastApply"]["result"] == "failed"
    assert "重新開啟" in final["message"]
    assert world.calls("stop_session") == [name]


# ---- 005 US3-API-09


async def test_改回自動值也失敗時失聯_紀錄最後一次的失敗_清空下載佇列(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:A100 記住 2;佇列裡有一筆已完成的下載
    world = downloadable(fakes)
    await remember(ui_client, "A100", tuning_body(2, None, None))
    kept = (await overrides(ui_client))["A100"]
    name = (await apply_ready(ui_client, world, fakes, QWEN_7B))["name"]
    world.log.clear()  # 記住 2 時結束的那個工作階段不算
    hold = await enqueue_waiting(ui_client, fakes, QWEN_SMALL)
    hold.release()
    await wait_queue(ui_client, lambda q: states(q) == [(QWEN_SMALL, "completed")])
    fakes.colab.restart_ollama.then(remote_error("verify"), remote_error("start"))

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    final = await wait_applied(ui_client)
    record = await record_of(ui_client, name)
    last = record["tunings"][-1]

    # Assert
    assert fakes.colab.restart_ollama.call_count == 2
    assert final["state"] == "lost"
    assert final["endReason"] == "OLLAMA_RESTART_FAILED"
    assert final["reasonCode"] == "COLAB_REMOTE_ERROR"
    assert last["result"] == "failed"
    assert last["remoteStage"] == "start"
    assert last["machine"] is None
    assert last["tuning"] is None
    assert world.calls("stop_session") == [name]
    assert (await queue(ui_client))["jobs"] == []
    assert (await overrides(ui_client))["A100"] == kept
    assert preloaded(world) == []


# ---- 005 US3-API-10


async def test_套用時執行環境已被收回_說明被收回而不是重啟失敗(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    fakes.colab.restart_ollama.raises("COLAB_NOT_FOUND")

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    final = await wait_applied(ui_client)

    # Assert
    assert final["endReason"] == "RECLAIMED_BY_COLAB"
    assert fakes.colab.restart_ollama.call_count == 1
    assert final["ollama"]["lastApply"]["result"] == "failed"


async def test_套用時授權過期_失聯並把登入狀態標成未登入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    fakes.colab.restart_ollama.raises("AUTH_REQUIRED")

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    final = await wait_applied(ui_client)
    auth = (await ui_client.get("/api/auth")).json()

    # Assert
    assert final["endReason"] == "OLLAMA_RESTART_FAILED"
    assert final["reasonCode"] == "AUTH_REQUIRED"
    assert auth["state"] == "logged_out"


# ---- 005 US3-API-11


async def test_失聯後釋放不了時留下釋放警告_套用的工作不中止(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    fakes.colab.restart_ollama.then(remote_error("verify"), remote_error("verify"))
    fakes.colab.stop_session.raises("COLAB_UNREACHABLE")

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    await wait_applied(ui_client)
    response = await ui_client.get("/api/session")

    # Assert
    session = response.json()
    assert session["state"] == "lost"
    assert session["releaseWarning"] is not None
    assert response.status_code == 200


# ---- 005 US3-API-12


async def test_有模型正在下載時不套用_也不中斷下載(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:`qwen2.5:7b` 下載中
    world = downloadable(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    gate = await enqueue_waiting(ui_client, fakes, QWEN_7B)

    # Act
    response = await apply(ui_client, tuning_body(4, None, None))
    during = (await ui_client.get("/api/session")).json()
    gate.release()
    finished = await wait_queue(ui_client, lambda q: states(q)[:1] != [(QWEN_7B, "downloading")], timeout=1.0)

    # Assert
    assert (response.status_code, error_code(response)) == (409, "DOWNLOAD_IN_PROGRESS")
    assert response.json()["model"] == QWEN_7B
    assert response.json()["message"] == "有模型正在下載,下載完才能套用"
    assert fakes.colab.restart_ollama.call_count == 0
    assert during["state"] == "ready"
    assert states(finished) == [(QWEN_7B, "completed")]


# ---- 005 US3-API-13


@pytest.mark.parametrize(
    ("which", "path", "first_line", "body"),
    [
        pytest.param(
            "ui",
            "/api/chat",
            {"message": {"role": "assistant", "content": "a"}, "done": False},
            {"model": QWEN_7B, "messages": [{"role": "user", "content": "hi"}]},
            id="UI對話",
        ),
        pytest.param("ollama", "/api/generate", {"response": "a"}, {"model": QWEN_7B, "prompt": "hi"}, id="相容端點"),
    ],
)
async def test_還有請求沒回完時不套用_進行中的串流照常結束(
    live_servers: Any, fakes: Any, which: str, path: str, first_line: dict[str, Any], body: dict[str, Any]
) -> None:
    # Arrange
    async with connect(live_servers, fakes) as bridge:
        await apply_ready(bridge.ui, bridge.world, fakes, QWEN_7B)
        gate = Gate()
        fakes.server.add("POST", path, NdjsonReply([first_line, gate, {"done": True}]))

        # Act
        async with getattr(bridge, which).stream("POST", path, json=body) as stream:
            lines = stream.aiter_lines()
            await anext(lines)
            response = await bridge.ui.post("/api/session/tuning", json=tuning_body(4, None, None))
            gate.release()
            rest = [line async for line in lines if line]
        final = (await bridge.ui.get("/api/session")).json()

    # Assert
    assert (response.status_code, error_code(response)) == (409, "REQUESTS_IN_PROGRESS")
    assert "請求" in response.json()["message"]
    assert fakes.colab.restart_ollama.call_count == 0
    assert json.loads(rest[-1])["done"] is True
    assert final["state"] == "ready"


# ---- 005 US3-API-14


async def _no_session(client: httpx.AsyncClient, world: ColabWorld, fakes: Any) -> None:
    return None


async def _opening(client: httpx.AsyncClient, world: ColabWorld, fakes: Any) -> None:
    gate = fakes.colab.create_session.gate()
    await client.post("/api/session", json={"runtimeType": A100})
    await gate.wait_entered_async()


async def _reconnecting(client: httpx.AsyncClient, world: ColabWorld, fakes: Any) -> None:
    await apply_ready(client, world, fakes, QWEN_7B)
    gate = fakes.tunnel.open_tunnel.gate()
    fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")
    await gate.wait_entered_async()


async def _ending(client: httpx.AsyncClient, world: ColabWorld, fakes: Any) -> None:
    await apply_ready(client, world, fakes, QWEN_7B)
    gate = fakes.colab.stop_session.gate()
    await client.delete("/api/session")
    await gate.wait_entered_async()


async def _ended(client: httpx.AsyncClient, world: ColabWorld, fakes: Any) -> None:
    await apply_ready(client, world, fakes, QWEN_7B)
    await client.delete("/api/session")
    await wait_for_state(client, "ended")


@pytest.mark.parametrize(
    "enter",
    [
        pytest.param(_no_session, id="沒有工作階段"),
        pytest.param(_opening, id="開啟中"),
        pytest.param(_reconnecting, id="重連中"),
        pytest.param(_ending, id="結束中"),
        pytest.param(_ended, id="已結束"),
    ],
)
async def test_工作階段不是就緒時不套用(ui_client: httpx.AsyncClient, fakes: Any, enter: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await enter(ui_client, world, fakes)

    # Act
    response = await apply(ui_client, tuning_body(4, None, None))

    # Assert
    assert (response.status_code, error_code(response)) == (503, "NO_READY_SESSION")
    assert "就緒" in response.json()["message"]
    assert fakes.colab.restart_ollama.call_count == 0


# ---- 005 US3-API-15


async def test_同時按套用只有一個受理_重啟中再按也回正在套用(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    restart_gate = fakes.colab.restart_ollama.gate()

    # Act
    first, second = await asyncio.gather(
        apply(ui_client, tuning_body(4, None, None)), apply(ui_client, tuning_body(16, None, None))
    )
    await restart_gate.wait_entered_async()
    third = await apply(ui_client, tuning_body(8, None, None))
    restart_gate.release()
    await wait_applied(ui_client)

    # Assert
    assert sorted((r.status_code, error_code(r)) for r in (first, second)) == [(202, None), (409, "TUNING_IN_PROGRESS")]
    rejected = first if first.status_code == 409 else second
    assert "正在套用設定" in rejected.json()["message"]
    assert (third.status_code, error_code(third)) == (409, "TUNING_IN_PROGRESS")
    assert fakes.colab.restart_ollama.call_count == 1


# ---- 005 US3-API-16


async def test_沒有登入時不套用_受理前就擋下(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    log_out(fakes)

    # Act
    response = await apply(ui_client, tuning_body(4, None, None))
    final = (await ui_client.get("/api/session")).json()

    # Assert
    assert (response.status_code, error_code(response)) == (409, "AUTH_REQUIRED")
    assert fakes.colab.restart_ollama.call_count == 0
    assert final["state"] == "ready"


# ---- 005 US3-API-17


@pytest.mark.parametrize(
    ("body", "code"),
    [
        pytest.param(tuning_body(33, None, None), "INVALID_NUM_PARALLEL", id="平行數超過範圍"),
        pytest.param(tuning_body(None, 131073, None), "INVALID_CONTEXT_LENGTH", id="context長度超過範圍"),
        pytest.param(tuning_body(None, None, 0), "INVALID_MAX_LOADED_MODELS", id="同時載入模型數低於範圍"),
        pytest.param({"numParallel": 4, "contextLength": None}, "INVALID_REQUEST_BODY", id="少了一個欄位"),
        pytest.param("4", "INVALID_REQUEST_BODY", id="本文是字串"),
        pytest.param(tuning_body(True, None, None), "INVALID_NUM_PARALLEL", id="布林值不算整數"),
    ],
)
async def test_範圍外或格式不對的設定不套用_說明哪一項不符(ui_client: httpx.AsyncClient, fakes: Any, body: Any, code: str) -> None:
    # Arrange:A100 記住 2
    world = ColabWorld(fakes)
    await remember(ui_client, "A100", tuning_body(2, None, None))
    kept = (await overrides(ui_client))["A100"]
    await apply_ready(ui_client, world, fakes, QWEN_7B)

    # Act
    response = await apply(ui_client, body)
    final = (await ui_client.get("/api/session")).json()

    # Assert
    assert (response.status_code, error_code(response)) == (400, code)
    assert fakes.colab.restart_ollama.call_count == 0
    assert final["state"] == "ready"
    assert (await overrides(ui_client))["A100"] == kept


# ---- 005 US3-API-18


async def test_檢查順序_先驗本文再看是否已在套用(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:(a)套用停在重啟中
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    restart_gate = fakes.colab.restart_ollama.gate()
    await apply(ui_client, tuning_body(4, None, None))
    await restart_gate.wait_entered_async()

    # Act
    response = await apply(ui_client, tuning_body(33, None, None))
    restart_gate.release()

    # Assert
    assert (response.status_code, error_code(response)) == (400, "INVALID_NUM_PARALLEL")


async def test_檢查順序_先看下載再看進行中的請求(live_servers: Any, fakes: Any) -> None:
    # Arrange:(b)`qwen2.5:7b` 下載中,UI 對話串流也進行中
    downloadable(fakes)
    async with connect(live_servers, fakes) as bridge:
        await apply_ready(bridge.ui, bridge.world, fakes, QWEN_7B)
        download_gate = await enqueue_waiting(bridge.ui, fakes, QWEN_7B)
        chat_gate = Gate()
        fakes.server.add("POST", "/api/chat", NdjsonReply([{"message": {"role": "assistant", "content": "a"}, "done": False}, chat_gate, {"done": True}]))
        chat = {"model": QWEN_7B, "messages": [{"role": "user", "content": "hi"}]}
        async with bridge.ui.stream("POST", "/api/chat", json=chat) as stream:
            lines = stream.aiter_lines()
            await anext(lines)

            # Act
            response = await apply(bridge.ui, tuning_body(4, None, None))
            chat_gate.release()
            [line async for line in lines]
        download_gate.release()

    # Assert
    assert (response.status_code, error_code(response)) == (409, "DOWNLOAD_IN_PROGRESS")


async def test_檢查順序_先看是否就緒再看授權(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:(c)開啟中,而且沒有登入
    ColabWorld(fakes)
    create_gate = fakes.colab.create_session.gate()
    await ui_client.post("/api/session", json={"runtimeType": A100})
    await create_gate.wait_entered_async()
    log_out(fakes)

    # Act
    response = await apply(ui_client, tuning_body(4, None, None))
    create_gate.release()

    # Assert
    assert (response.status_code, error_code(response)) == (503, "NO_READY_SESSION")


# ---- 005 US3-API-19


async def test_新的同時載入模型數較少時只重新載入前面幾個_其餘列為超出上限(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:重啟前載入 A、B;重啟後同時載入模型數是 1
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B, LLAMA)
    world.restart_result = restarted(40 * GIB, applied(8, 8192, 1, sources=("auto", "auto", "manual")), **_A100_MACHINE)

    # Act
    await apply(ui_client, tuning_body(None, None, 1))
    final = await wait_applied(ui_client)

    # Assert
    last = final["ollama"]["lastApply"]
    assert preloaded(world) == [QWEN_7B]
    assert last["reloaded"] == [QWEN_7B]
    assert last["notReloaded"] == [{"model": LLAMA, "reason": "OVER_LIMIT", "reasonCode": None}]
    assert last["result"] == "applied"


# ---- 005 US3-API-20


async def test_重新載入依重啟前的順序一次一個_不同時爭顯示記憶體(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:重啟前依序載入 C、A、B;重啟後同時載入模型數是 2;第一個預先載入閘住
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, LLAMA, QWEN_7B, QWEN_SMALL)
    world.restart_result = restarted(40 * GIB, applied(8, 8192, 2, sources=("auto", "auto", "manual")), **_A100_MACHINE)
    first_gate = Gate()

    async def preload(*args: Any, **kwargs: Any) -> dict[str, Any]:
        model = kwargs["model"]
        if fakes.remote_ollama.preload.call_count == 1:
            await first_gate.pass_async()
        world.log.append(("preload", model))
        world.loaded.append(model)
        return {"model": model, "done": True}

    fakes.remote_ollama.preload.side_effect(preload)

    # Act
    await apply(ui_client, tuning_body(None, None, 2))
    await first_gate.wait_entered_async()
    calls_while_first_loading = fakes.remote_ollama.preload.call_count
    first_gate.release()
    final = await wait_applied(ui_client)

    # Assert
    assert calls_while_first_loading == 1
    assert preloaded(world) == [LLAMA, QWEN_7B]
    assert final["ollama"]["lastApply"]["notReloaded"] == [{"model": QWEN_SMALL, "reason": "OVER_LIMIT", "reasonCode": None}]


# ---- 005 US3-API-21


async def test_同時載入模型數用_Ollama_預設值時全部重新載入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:重啟前載入 A、B、C;重啟後讀不到顯示記憶體,同時載入模型數用 Ollama 預設值
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B, LLAMA, QWEN_SMALL)
    world.restart_result = restarted(
        None,
        applied(4, None, None, sources=("manual", "ollama_default", "ollama_default")),
        gpu_name=None,
        system_bytes=_A100_MACHINE["system_bytes"],
    )

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    final = await wait_applied(ui_client)

    # Assert
    assert preloaded(world) == [QWEN_7B, LLAMA, QWEN_SMALL]
    assert final["ollama"]["lastApply"]["notReloaded"] == []


# ---- 005 US3-API-22


async def test_單一模型預先載入失敗時套用仍成功_列為沒有重新載入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:重啟前載入 A、B;預先載入 A 失敗、B 成功
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B, LLAMA)

    def preload(*args: Any, **kwargs: Any) -> dict[str, Any]:
        model = kwargs["model"]
        if model == QWEN_7B:
            raise AdapterError("OLLAMA_SERVER_ERROR", "load failed")
        world.log.append(("preload", model))
        world.loaded.append(model)
        return {"model": model, "done": True}

    fakes.remote_ollama.preload.side_effect(preload)

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    final = await wait_applied(ui_client)
    remembered = (await overrides(ui_client))["A100"]

    # Assert
    last = final["ollama"]["lastApply"]
    assert final["state"] == "ready"
    assert last["result"] == "applied"
    assert last["notReloaded"] == [{"model": QWEN_7B, "reason": "PRELOAD_FAILED", "reasonCode": "OLLAMA_SERVER_ERROR"}]
    assert last["reloaded"] == [LLAMA]
    assert remembered["numParallel"] == 4


# ---- 005 US3-API-23


async def test_讀不到已載入的模型時照常套用_當作沒有要重新載入的(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    fakes.remote_ollama.list_loaded_models.raises("OLLAMA_UNREACHABLE")

    # Act
    accepted = await apply(ui_client, tuning_body(4, None, None))
    final = await wait_applied(ui_client)

    # Assert
    assert accepted.status_code == 202
    assert fakes.colab.restart_ollama.call_count == 1
    assert final["ollama"]["lastApply"]["result"] == "applied"
    assert final["ollama"]["lastApply"]["reloaded"] == []
    assert preloaded(world) == []


# ---- 005 US3-API-24


async def test_重啟期間不計閒置_回到就緒時重新倒數(make_app: Callable[..., AppPair], fakes: Any, fake_clock: FakeClock) -> None:
    # Arrange:閒置時限 1 分鐘,就緒的時間為 T
    world = ColabWorld(fakes)
    async with running(make_app()) as client:
        await set_idle_timeout(client, 1)
        t = parse_iso((await apply_ready(client, world, fakes, QWEN_7B))["readyAt"])
        restart_gate = fakes.colab.restart_ollama.gate()

        # Act:T+50 秒開始套用,重啟中時間走到 T+120 秒(已超過原本的倒數)
        fake_clock.set(t + timedelta(seconds=50))
        await apply(client, tuning_body(4, None, None))
        await restart_gate.wait_entered_async()
        fake_clock.set(t + timedelta(seconds=120))
        while_restarting = await states_for(client, 0.3)
        restart_gate.release()
        await wait_applied(client)
        back_at = fake_clock.now()
        idle = (await client.get("/api/session")).json()["idle"]
        after = await states_for(client, 0.3)

    # Assert
    assert set(while_restarting) == {"applying_tuning"}
    assert back_at - timedelta(seconds=1) <= parse_iso(idle["lastRequestAt"]) <= back_at
    assert parse_iso(idle["deadline"]) - parse_iso(idle["lastRequestAt"]) == timedelta(minutes=1)
    assert set(after) == {"ready"}


# ---- 005 US3-API-25


async def test_套用中相容端點_對話與下載都回沒有就緒的工作階段_不轉送不排隊(live_servers: Any, fakes: Any) -> None:
    # Arrange
    async with connect(live_servers, fakes) as bridge:
        await apply_ready(bridge.ui, bridge.world, fakes, QWEN_7B)
        fakes.server.add("POST", "/api/generate", NdjsonReply([{"response": "a"}, {"done": True}]))
        restart_gate = fakes.colab.restart_ollama.gate()

        # Act
        await bridge.ui.post("/api/session/tuning", json=tuning_body(4, None, None))
        await restart_gate.wait_entered_async()
        sent_at = time.monotonic()
        compat = await bridge.ollama.post("/api/generate", json={"model": QWEN_7B, "prompt": "hi"})
        elapsed = time.monotonic() - sent_at
        chat = await bridge.ui.post("/api/chat", json={"model": QWEN_7B, "messages": [{"role": "user", "content": "hi"}]})
        downloads = await bridge.ui.post("/api/downloads", json={"models": [QWEN_SMALL]})
        restart_gate.release()

    # Assert
    assert compat.status_code == 503
    assert compat.json()["error"].startswith("目前沒有可用的工作階段")
    assert "工作階段正在套用 Ollama 設定" in compat.json()["error"]
    assert elapsed < 0.5
    assert fakes.server.requests_to("POST", "/api/generate") == []
    assert (chat.status_code, error_code(chat)) == (503, "NO_READY_SESSION")
    assert (downloads.status_code, error_code(downloads)) == (503, "NO_READY_SESSION")


# ---- 005 US3-API-26


async def test_套用中可以結束_等進行中的重啟結束後才釋放_這次套用記為中斷(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:A100 記住 2
    world = ColabWorld(fakes)
    await remember(ui_client, "A100", tuning_body(2, None, None))
    kept = (await overrides(ui_client))["A100"]
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    fakes.colab.stop_session.reset_calls()  # 記住 2 時結束的那個工作階段不算
    restart_gate = fakes.colab.restart_ollama.gate()

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    await restart_gate.wait_entered_async()
    ending = await ui_client.delete("/api/session")
    await asyncio.sleep(0.2)
    stops_while_restarting = fakes.colab.stop_session.call_count
    restart_gate.release()
    final = await wait_for_state(ui_client, "ended")
    remembered = (await overrides(ui_client))["A100"]

    # Assert
    assert ending.status_code == 202
    assert stops_while_restarting == 0
    assert final["endReason"] == "USER_ENDED"
    last = final["ollama"]["lastApply"]
    assert last["result"] == "interrupted"
    assert last["finishedAt"] is not None
    assert preloaded(world) == []
    assert remembered == kept


# ---- 005 US3-API-27


def _started_4(*, tuning: dict[str, Any] | None) -> dict[str, Any]:
    return started(40 * GIB, tuning, gpu_name=_A100_MACHINE["gpu_name"], system_bytes=_A100_MACHINE["system_bytes"], already_running=True)


@pytest.mark.parametrize(
    ("fall_back", "start_result", "expected_overrides", "status", "num_parallel"),
    [
        pytest.param(
            False,
            _started_4(tuning=applied(4, 8192, 2, sources=("manual", "auto", "auto"))),
            tuning_body(4, None, None),
            "applied",
            {"value": 4, "source": "manual"},
            id="重啟中_遠端已在執行並回報設定",
        ),
        pytest.param(False, _started_4(tuning=None), tuning_body(4, None, None), "unknown", None, id="重啟中_讀不到設定"),
        pytest.param(True, A100_STARTED, NONE3, "applied", {"value": 8, "source": "auto"}, id="停在改回自動值那一次"),
    ],
)
async def test_後端在套用中停機後接回_以要求的設定讀回遠端的狀態_不重啟不重新載入(
    make_app: Callable[..., AppPair],
    fakes: Any,
    fall_back: bool,
    start_result: dict[str, Any],
    expected_overrides: dict[str, Any],
    status: str,
    num_parallel: dict[str, Any] | None,
) -> None:
    # Arrange:第一個 app 的套用停在重啟中(或停在改回自動值那一次),A100 記住 2
    world = ColabWorld(fakes)
    async with running(make_app()) as client:
        await remember(client, "A100", tuning_body(2, None, None))
        kept = (await overrides(client))["A100"]
        await apply_ready(client, world, fakes, QWEN_7B)
        stuck = Gate()
        if fall_back:
            fallback_split(fakes, remote_error("verify"), stuck)
        else:
            stuck = fakes.colab.restart_ollama.gate()
        await apply(client, tuning_body(4, None, None))
        await stuck.wait_entered_async()
    reset_calls(fakes)
    world.start_result = start_result

    # Act
    async with running(make_app()) as client:
        session = await wait_until(client, lambda s: s.get("state") != "applying_tuning" and not s.get("resuming"), timeout=1.0)
        remembered = (await overrides(client))["A100"]

    # Assert
    assert session["state"] == "ready"
    assert fakes.colab.start_ollama.call_count == 1
    assert fakes.colab.start_ollama.last_call.kwargs["overrides"] == expected_overrides
    assert session["ollama"]["lastApply"]["result"] == "interrupted"
    assert session["ollama"]["status"] == status
    if num_parallel is not None:
        assert session["ollama"]["tuning"]["numParallel"] == num_parallel
    assert fakes.colab.restart_ollama.call_count == 0
    assert fakes.remote_ollama.preload.call_count == 0
    assert remembered == kept


# ---- 005 US3-API-28


@pytest.mark.parametrize(
    ("reclaimed", "end_reason"),
    [
        pytest.param(True, "RECLAIMED_BY_COLAB", id="停機期間被_Colab_收回"),
        pytest.param(False, "OLLAMA_RESTART_FAILED", id="恢復時啟動遠端_Ollama_失敗"),
    ],
)
async def test_後端在套用中停機後恢復時失聯_這一次套用記為中斷(
    make_app: Callable[..., AppPair], fakes: Any, reclaimed: bool, end_reason: str
) -> None:
    # Arrange:第一個 app 的套用停在重啟中
    world = ColabWorld(fakes)
    async with running(make_app()) as client:
        await asyncio.sleep(0.05)  # 啟動時的恢復先跑完,才不會把接著開啟的工作階段當成上一個行程留下的
        name = (await apply_ready(client, world, fakes, QWEN_7B))["name"]
        stuck = fakes.colab.restart_ollama.gate()
        await apply(client, tuning_body(4, None, None))
        await stuck.wait_entered_async()
    reset_calls(fakes)
    world.log.clear()
    if reclaimed:
        world.alive.remove(name)
    else:
        fakes.colab.start_ollama.raises("COLAB_REMOTE_ERROR")

    # Act
    async with running(make_app()) as client:
        session = await wait_until(client, lambda s: s.get("state") == "lost", timeout=1.0)
        record = await record_of(client, name)

    # Assert
    assert session["endReason"] == end_reason
    assert record["tunings"][-1]["result"] == "interrupted"
    if reclaimed:
        assert fakes.colab.start_ollama.call_count == 0
    else:
        assert world.calls("stop_session") == [name]


# ---- 005 US3-API-29


async def test_後端重新啟動接回後目前生效的設定是最新一筆讀到的_含改回自動值那次(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:套用過兩次:先成功套用 4,再套用 16 而改回自動值
    world = ColabWorld(fakes)
    async with running(make_app()) as client:
        await asyncio.sleep(0.05)  # 啟動時的恢復先跑完
        await apply_ready(client, world, fakes, QWEN_7B)
        await apply(client, tuning_body(4, None, None))
        await wait_applied(client)
        fallback_split(fakes, remote_error("verify"))
        await apply(client, tuning_body(16, None, None))
        after_second = await wait_applied(client)
    reset_calls(fakes)

    # Act
    async with running(make_app()) as client:
        session = await wait_until(client, lambda s: s.get("state") == "ready" and not s.get("resuming"), timeout=1.0)

    # Assert
    assert after_second["ollama"]["lastApply"]["result"] == "fell_back_to_auto"
    assert session["ollama"]["tuning"]["numParallel"] == {"value": 8, "source": "auto"}
    assert session["ollama"]["lastApply"]["result"] == "fell_back_to_auto"
    assert session["ollama"]["lastApply"]["requested"] == tuning_body(16, None, None)
    assert fakes.colab.start_ollama.call_count == 0


# ---- 005 US3-API-30


async def test_每次套用追加一筆紀錄_步驟也記進狀態變化(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    name = (await apply_ready(ui_client, world, fakes, QWEN_7B))["name"]
    fakes.colab.restart_ollama.then(
        A100_RESTARTED_4,
        restarted(40 * GIB, applied(8, 8192, 2, sources=("manual", "auto", "auto")), **_A100_MACHINE),
    )

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    await wait_applied(ui_client)
    await apply(ui_client, tuning_body(8, None, None))
    session = await wait_applied(ui_client)
    record = await record_of(ui_client, name)

    # Assert
    tunings = record["tunings"]
    assert len(tunings) == 3
    assert [t["trigger"] for t in tunings] == ["open", "apply", "apply"]
    assert [t["requested"]["numParallel"] for t in tunings] == [None, 4, 8]
    assert [t["result"] for t in tunings] == ["applied", "applied", "applied"]
    assert tunings[0]["tuning"] == A100_STARTED["tuning"]
    steps = [(t["state"], t["step"]) for t in record["transitions"]]
    assert steps.count(("applying_tuning", "restarting_ollama")) == 2
    assert steps.count(("applying_tuning", "reloading_models")) == 2
    assert session["ollama"]["lastApply"] == tunings[2]


# ---- 005 US3-API-33


async def test_套用中不能變更執行階段類型(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:套用停在重啟中
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    world.log.clear()
    restart_gate = fakes.colab.restart_ollama.gate()
    await apply(ui_client, tuning_body(4, None, None))
    await restart_gate.wait_entered_async()

    # Act
    response = await ui_client.post("/api/session/restart", json={"runtimeType": L4})
    restart_gate.release()
    final = await wait_applied(ui_client)

    # Assert
    assert (response.status_code, error_code(response)) == (409, "TUNING_IN_PROGRESS")
    assert world.calls("stop_session") == []
    assert fakes.colab.create_session.call_count == 1
    assert final["state"] == "ready"
    assert final["runtimeType"]["gpu"] == "A100"


# ---- 005 US3-API-34


async def test_套用中不能再開啟另一個工作階段(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:套用停在重啟中
    world = ColabWorld(fakes)
    await apply_ready(ui_client, world, fakes, QWEN_7B)
    restart_gate = fakes.colab.restart_ollama.gate()
    await apply(ui_client, tuning_body(4, None, None))
    await restart_gate.wait_entered_async()

    # Act
    response = await ui_client.post("/api/session", json={"runtimeType": T4})
    restart_gate.release()
    final = await wait_applied(ui_client)

    # Assert
    assert (response.status_code, error_code(response)) == (409, "SESSION_ALREADY_ACTIVE")
    assert fakes.colab.create_session.call_count == 1
    assert final["state"] == "ready"


# ---- 005 US3-API-31


@pytest.mark.parametrize(
    ("fall_back", "low", "high"),
    [
        pytest.param(False, 85, 90, id="要求的設定一次重啟成功"),
        pytest.param(True, 170, 180, id="改回自動值再重啟"),
    ],
)
async def test_重啟成功就直接切到重新載入_受理到重新載入的時間只含重啟本身(
    ui_client: httpx.AsyncClient, fakes: Any, fake_clock: FakeClock, fall_back: bool, low: int, high: int
) -> None:
    # Arrange:遠端每次重啟花 85 秒(假時鐘往前推,不真的等)
    started_at = time.monotonic()
    world = ColabWorld(fakes)
    name = (await apply_ready(ui_client, world, fakes, QWEN_7B))["name"]
    preload_gate = fakes.remote_ollama.preload.gate()

    async def slow_restart(*args: Any, **kwargs: Any) -> dict[str, Any]:
        fake_clock.advance(85)
        if fall_back and kwargs["overrides"] != NONE3:
            raise remote_error("verify")
        return AUTO_RESTARTED if fall_back else A100_RESTARTED_4

    fakes.colab.restart_ollama.side_effect(slow_restart)

    # Act
    await apply(ui_client, tuning_body(4, None, None))
    await preload_gate.wait_entered_async()
    record = await record_of(ui_client, name)
    preload_gate.release()
    await wait_applied(ui_client)

    # Assert
    reloading = next(t for t in record["transitions"] if t["step"] == "reloading_models")
    seconds = (parse_iso(reloading["at"]) - parse_iso(record["tunings"][-1]["at"])).total_seconds()
    assert low <= seconds <= high
    assert time.monotonic() - started_at < 1.0


# ---- 005 US3-API-32


async def test_忙碌時連按十次都被擋下_下載與對話都不受影響(live_servers: Any, fakes: Any) -> None:
    # Arrange:`qwen2.5:7b` 下載中,UI 對話串流也進行中
    downloadable(fakes)
    async with connect(live_servers, fakes) as bridge:
        await apply_ready(bridge.ui, bridge.world, fakes, QWEN_7B)
        download_gate = await enqueue_waiting(bridge.ui, fakes, QWEN_7B)
        chat_gate = Gate()
        fakes.server.add("POST", "/api/chat", NdjsonReply([{"message": {"role": "assistant", "content": "a"}, "done": False}, chat_gate, {"done": True}]))
        chat = {"model": QWEN_7B, "messages": [{"role": "user", "content": "hi"}]}
        async with bridge.ui.stream("POST", "/api/chat", json=chat) as stream:
            lines = stream.aiter_lines()
            await anext(lines)

            # Act
            responses = [await apply(bridge.ui, tuning_body(4, None, None)) for _ in range(10)]
            chat_gate.release()
            rest = [line async for line in lines if line]
        download_gate.release()
        finished = await wait_queue(bridge.ui, lambda q: states(q)[:1] != [(QWEN_7B, "downloading")], timeout=1.0)
        final = (await bridge.ui.get("/api/session")).json()

    # Assert
    assert [r.status_code for r in responses] == [409] * 10
    assert {error_code(r) for r in responses} == {"DOWNLOAD_IN_PROGRESS"}
    assert fakes.colab.restart_ollama.call_count == 0
    assert json.loads(rest[-1])["done"] is True
    assert states(finished) == [(QWEN_7B, "completed")]
    assert final["state"] == "ready"
