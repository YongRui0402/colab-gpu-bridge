"""E2 後端 UI API:遠端 Ollama 依機器配置調好的設定(testplan.md § 2.2)。

接縫:HTTP `/api/*` 與 SSE `/api/events`,轉接層用替身(testplan.md § 接縫的取捨)。
E2 不重算設定(contracts/ui.openapi.yaml § `info.x-tuning-rule` (2)):替身回報的 `tuning` 就是期望值,
這裡驗的是「原樣轉交、什麼時候寫、寫到哪裡」。
"""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest

from cgb.app import AppPair
from cgb.db.connection import connect
from cgb.domain.session_state import parse_iso
from integration.test_api_recovery import reset_calls, running
from integration.test_api_events import next_session_update, sse_events
from integration.test_api_session import T4, error_code, T4_STARTED, ColabWorld, open_ready, ui_client, wait_for_state, wait_until  # noqa: F401

GIB = 1073741824
A100 = {"gpu": "A100", "highMem": False}
L4 = {"gpu": "L4", "highMem": False}

# 沒有任何類型覆蓋值時交給 `start_ollama` 的覆蓋值(三個都是自動)
NO_OVERRIDES = {"numParallel": None, "contextLength": None, "maxLoadedModels": None}


def applied(
    np: int | None,
    ctx: int | None,
    mlm: int | None,
    sources: tuple[str, str, str] = ("auto", "auto", "auto"),
    fa: str = "auto",
) -> dict[str, Any]:
    """組出 `AppliedTuning`:來源是 `ollama_default` 的項目 `value` 為 None。"""

    def item(value: Any, source: str) -> dict[str, Any]:
        return {"value": None if source == "ollama_default" else value, "source": source}

    return {
        "numParallel": item(np, sources[0]),
        "contextLength": item(ctx, sources[1]),
        "maxLoadedModels": item(mlm, sources[2]),
        "flashAttention": item(True, fa),
        "kvCacheType": item("q8_0", fa),
    }


def _machine(vram_bytes: int | None, gpu_name: str | None, system_bytes: int | None) -> dict[str, Any]:
    return {
        "gpuName": gpu_name,
        "vramTotalBytes": vram_bytes,
        "systemMemoryTotalBytes": system_bytes,
        "probedAt": "2026-11-15T09:00:00Z",
    }


def started(
    vram_bytes: int | None,
    tuning: dict[str, Any] | None,
    *,
    gpu_name: str | None,
    system_bytes: int | None,
    already_running: bool = False,
) -> dict[str, Any]:
    """組出 `OllamaStarted`(contracts/colab-cli.openapi.yaml § components.schemas.OllamaStarted)。"""
    return {
        "ollamaVersion": "0.40.15",
        "alreadyRunning": already_running,
        "machine": _machine(vram_bytes, gpu_name, system_bytes),
        "tuning": tuning,
    }


def restarted(
    vram_bytes: int | None,
    tuning: dict[str, Any],
    *,
    gpu_name: str | None,
    system_bytes: int | None,
    stopped_by: str = "pid_file",
) -> dict[str, Any]:
    """組出 `OllamaRestarted`(contracts/colab-cli.openapi.yaml § components.schemas.OllamaRestarted)。"""
    return {
        "ollamaVersion": "0.40.15",
        "stoppedBy": stopped_by,
        "machine": _machine(vram_bytes, gpu_name, system_bytes),
        "tuning": tuning,
    }


A100_STARTED = started(40 * GIB, applied(8, 8192, 2), gpu_name="NVIDIA A100-SXM4-40GB", system_bytes=89_632_571_392)


async def record_of(client: httpx.AsyncClient, name: str) -> dict[str, Any]:
    """`GET /api/sessions/{name}` 的本文。"""
    return (await client.get(f"/api/sessions/{name}")).json()


def sent_overrides(fakes: Any) -> Any:
    """最近一次 `start_ollama` 收到的覆蓋值。"""
    return fakes.colab.start_ollama.last_call.kwargs["overrides"]


# ---- 005 US1-API-01

MACHINES = [
    pytest.param(started(6 * GIB, applied(1, 4096, 1), gpu_name="NVIDIA RTX A2000", system_bytes=13_605_855_232), id="6GiB"),
    pytest.param(T4_STARTED, id="T4-15GiB"),
    pytest.param(
        started(int(22.5 * GIB), applied(4, 8192, 1), gpu_name="NVIDIA L4", system_bytes=56_000_000_000), id="L4-22.5GiB"
    ),
    pytest.param(A100_STARTED, id="A100-40GiB"),
    pytest.param(
        started(96 * GIB, applied(16, 8192, 3), gpu_name="NVIDIA H100 NVL", system_bytes=180_000_000_000), id="96GiB"
    ),
]


@pytest.mark.parametrize("reported", MACHINES)
async def test_開到就緒後_工作階段照遠端回報顯示量到的硬體與套用的設定(
    ui_client: httpx.AsyncClient, fakes: Any, reported: dict[str, Any]
) -> None:
    # Arrange
    world = ColabWorld(fakes)
    world.start_result = reported

    # Act
    await open_ready(ui_client, A100)
    session = (await ui_client.get("/api/session")).json()

    # Assert
    ollama = session.get("ollama") or {}
    assert ollama.get("status") == "applied"
    assert (ollama.get("machine") or {}).get("vramTotalBytes") == reported["machine"]["vramTotalBytes"]
    assert (ollama.get("machine") or {}).get("systemMemoryTotalBytes") == reported["machine"]["systemMemoryTotalBytes"]
    assert ollama.get("tuning") == reported["tuning"]
    assert sent_overrides(fakes) == NO_OVERRIDES


# ---- 005 US1-API-02


async def test_選的類型和配到的機器不同時_設定照量到的顯示記憶體_類型照原樣(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:選的是 A100,Colab 卻配到顯示記憶體 22.5 GiB 的機器
    world = ColabWorld(fakes)
    world.start_result = started(int(22.5 * GIB), applied(4, 8192, 1), gpu_name="NVIDIA L4", system_bytes=56_000_000_000)

    # Act
    await open_ready(ui_client, A100)
    session = (await ui_client.get("/api/session")).json()

    # Assert
    ollama = session.get("ollama") or {}
    tuning = ollama.get("tuning") or {}
    assert tuning.get("numParallel") == {"value": 4, "source": "auto"}
    assert tuning.get("maxLoadedModels") == {"value": 1, "source": "auto"}
    assert (ollama.get("machine") or {}).get("gpuName") == "NVIDIA L4"
    assert session.get("runtimeType") == A100


# ---- 005 US1-API-03


async def updates_until_ready(events: Any, timeout: float = 1.0) -> list[dict[str, Any]]:
    """讀 `session.updated` 直到收到 `state` 為 `ready` 的那一則(最多 `timeout` 秒);回傳讀到的每一則。"""
    seen: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not seen or seen[-1].get("state") != "ready":
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        update = await next_session_update(events, timeout=remaining)
        if update is None:
            break
        seen.append(update)
    return seen


async def test_遠端_Ollama_一啟動完就顯示設定_不等到就緒(live_servers: Any, fakes: Any) -> None:
    # Arrange
    world = ColabWorld(fakes)
    world.start_result = A100_STARTED
    start_gate = fakes.colab.start_ollama.gate()
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)
            await next_session_update(events)

            # Act
            accepted = await client.post("/api/session", json={"runtimeType": A100})
            await start_gate.wait_entered_async()
            before_start = (await client.get("/api/session")).json()
            start_gate.release()
            updates = await updates_until_ready(events)

    # Assert
    accepted_ollama = accepted.json().get("ollama") or {}
    connecting = [u for u in updates if u.get("step") == "connecting"]
    first_connecting = (connecting[0].get("ollama") or {}) if connecting else {}
    assert accepted.status_code == 202 and accepted_ollama.get("status") == "pending"
    assert "machine" in accepted_ollama and accepted_ollama["machine"] is None
    assert (before_start.get("step"), (before_start.get("ollama") or {}).get("status")) == ("starting_ollama", "pending")
    assert first_connecting.get("status") == "applied"
    assert first_connecting.get("tuning") == A100_STARTED["tuning"]
    assert not [u for u in connecting if (u.get("ollama") or {}).get("status") == "pending"]


# ---- 005 US1-API-04


async def test_讀不到顯示記憶體時照常就緒_設定標成使用_Ollama_預設值(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:`nvidia-smi` 失敗
    world = ColabWorld(fakes)
    world.start_result = started(
        None,
        applied(None, None, None, sources=("ollama_default",) * 3, fa="ollama_default"),
        gpu_name=None,
        system_bytes=13_605_855_232,
    )

    # Act
    await ui_client.post("/api/session", json={"runtimeType": T4})
    await wait_for_state(ui_client, "ready")
    session = (await ui_client.get("/api/session")).json()
    record = await record_of(ui_client, session["name"])

    # Assert
    ollama = session.get("ollama") or {}
    tuning = ollama.get("tuning") or {}
    tunings = record.get("tunings") or [{}]
    assert session.get("state") == "ready"
    assert ollama.get("status") == "applied"
    assert "machine" in ollama and (ollama["machine"] or {}).get("vramTotalBytes", "沒有") is None
    assert tuning.get("numParallel") == {"value": None, "source": "ollama_default"}
    assert tuning.get("flashAttention") == {"value": None, "source": "ollama_default"}
    assert tunings[0].get("result") == "applied"


# ---- 005 US1-API-05


async def test_遠端_Ollama_已在執行而讀不到設定時照常就緒_設定標成不知道(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:`Connection was lost` 重跑時 Ollama 已在回應、讀不到設定檔
    world = ColabWorld(fakes)
    world.start_result = started(15 * GIB, None, gpu_name="Tesla T4", system_bytes=13_605_855_232, already_running=True)

    # Act
    await ui_client.post("/api/session", json={"runtimeType": T4})
    await wait_for_state(ui_client, "ready")
    response = await ui_client.get("/api/session")
    session = response.json() if response.status_code == 200 else {}
    record = await record_of(ui_client, session["name"]) if "name" in session else {}

    # Assert
    ollama = session.get("ollama") or {}
    tunings = record.get("tunings") or []
    assert session.get("state") == "ready"
    assert ollama.get("status") == "unknown"
    assert "tuning" in ollama and ollama["tuning"] is None
    assert (ollama.get("machine") or {}).get("vramTotalBytes") == 15 * GIB
    assert len(tunings) == 1 and "tuning" in tunings[0] and tunings[0]["tuning"] is None


# ---- 005 US1-API-06


async def test_開啟時那一筆設定在遠端啟動完才記下_含量到的硬體與來源(
    ui_client: httpx.AsyncClient, fakes: Any, fake_clock: Any
) -> None:
    # Arrange
    world = ColabWorld(fakes)
    world.start_result = A100_STARTED
    start_gate = fakes.colab.start_ollama.gate()
    accepted_at = fake_clock.now()

    # Act
    await ui_client.post("/api/session", json={"runtimeType": A100})
    await start_gate.wait_entered_async()
    fake_clock.advance(30)
    start_gate.release()
    session = await wait_for_state(ui_client, "ready", timeout=1.0)
    record = await record_of(ui_client, session["name"])

    # Assert
    tunings = record.get("tunings") or []
    only = tunings[0] if len(tunings) == 1 else {}
    at = parse_iso(only["at"]) if only.get("at") else None
    assert len(tunings) == 1
    assert (only.get("trigger"), only.get("result")) == ("open", "applied")
    assert at is not None and accepted_at + timedelta(seconds=30) <= at <= accepted_at + timedelta(seconds=31)
    assert only.get("finishedAt") == only.get("at")
    assert only.get("requested") == NO_OVERRIDES
    assert (only.get("machine") or {}).get("vramTotalBytes") == 40 * GIB
    assert only.get("tuning") == A100_STARTED["tuning"]
    assert "attempt" not in only


# ---- 005 US1-API-07


@pytest.mark.parametrize(
    ("method", "code"),
    [
        pytest.param("start_ollama", "COLAB_REMOTE_ERROR", id="安裝失敗"),
        pytest.param("create_session", "COLAB_ACCELERATOR_REJECTED", id="配置被拒"),
    ],
)
async def test_開啟失敗的工作階段沒有開啟時那一筆設定(
    ui_client: httpx.AsyncClient, fakes: Any, method: str, code: str
) -> None:
    # Arrange
    ColabWorld(fakes)
    getattr(fakes.colab, method).raises(code)

    # Act
    await ui_client.post("/api/session", json={"runtimeType": T4})
    session = await wait_for_state(ui_client, "open_failed")
    record = await record_of(ui_client, session["name"])

    # Assert
    ollama = session.get("ollama") or {}
    assert record.get("tunings") == []
    assert ollama.get("status") == "pending"
    assert "tuning" in ollama and ollama["tuning"] is None


# ---- 005 US1-API-08


async def test_後端重新啟動接回時照紀錄顯示設定_不重新量測也不重啟遠端_Ollama(
    make_app: Callable[..., AppPair], fakes: Any
) -> None:
    # Arrange
    world = ColabWorld(fakes)
    world.start_result = A100_STARTED
    async with running(make_app()) as client:
        name = (await open_ready(client, A100))["name"]
        before = (await client.get("/api/session")).json()["ollama"]
    reset_calls(fakes)
    world.log.clear()

    # Act
    async with running(make_app()) as client:
        session = await wait_until(
            client, lambda s: s.get("state") == "ready" and bool(world.calls("open_tunnel")), timeout=1.0
        )
        record = await record_of(client, name)

    # Assert
    ollama = session.get("ollama") or {}
    assert ollama.get("machine") == before["machine"]
    assert ollama.get("tuning") == before["tuning"]
    assert ollama.get("status") == "applied"
    assert fakes.colab.start_ollama.call_count == 0
    # `restart_ollama` 到故事 3(US3-CLI-01)才有;在那之前看替身背後的呼叫紀錄
    assert world.calls("restart_ollama") == []
    assert len(record.get("tunings") or []) == 1


# ---- 005 US1-API-09


async def test_查不存在的工作階段紀錄回找不到(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.get("/api/sessions/cgb-test-not-there")

    # Assert
    assert (response.status_code, error_code(response)) == (404, "SESSION_NOT_FOUND")


# ---- 005 US1-API-10


async def test_005_之前開的工作階段接回後_設定標成不知道_紀錄沒有設定(
    make_app: Callable[..., AppPair], fakes: Any, db_path: Any
) -> None:
    # Arrange:遷移不補舊工作階段的紀錄(store.dbml 遷移 3.)
    world = ColabWorld(fakes)
    async with running(make_app()) as client:
        name = (await open_ready(client))["name"]
    conn = connect(db_path)
    conn.execute("DELETE FROM session_tunings")
    conn.close()
    reset_calls(fakes)
    world.log.clear()

    # Act
    async with running(make_app()) as client:
        await wait_until(client, lambda s: s.get("state") == "ready" and bool(world.calls("open_tunnel")), timeout=1.0)
        response = await client.get("/api/session")
        record = await record_of(client, name)

    # Assert
    ollama = (response.json() if response.status_code == 200 else {}).get("ollama") or {}
    assert ollama.get("status") == "unknown"
    assert "machine" in ollama and ollama["machine"] is None
    assert "tuning" in ollama and ollama["tuning"] is None
    assert record.get("tunings") == []
    assert response.status_code == 200
