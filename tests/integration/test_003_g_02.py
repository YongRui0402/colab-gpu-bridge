"""G-02(tasks.md T069):讀一次顯示記憶體要 3 秒時,經真的 HTTP 連線量打開模型目錄的回應時間(testplan.md § 4.2)。

後端以測試行程內的 uvicorn 起在 127.0.0.1 隨機 port(`start_live_servers`,不經 `httpx.ASGITransport`);
工作階段就緒用替身,`probe_resources` 的 async 替身每次先 `await asyncio.sleep(3)` 再回顯示記憶體 16,106,127,360。
就緒後 `reset_calls()`,連續送 10 次 `GET /api/models` 並記每次耗時;再變更類型成 L4,等到新的工作階段就緒後送 1 次。

標 `realrun`,預設排除;不放 `tests/realrun/`,不經會執行 `colab usage` 的 `realrun` fixture(plan.md Q9)。
護欄:uvicorn 只綁 127.0.0.1 隨機 port;資料庫是 pytest 暫存資料夾的 SQLite;Colab、通道、遠端 Ollama、模型庫都用替身,
不執行任何 `colab` 指令、不花 compute units;約 7 秒。
判定者:腳本(耗時和 1 秒、3 秒比較);樣本:一次量測(未用於調整)。
執行:`uv run pytest -m realrun tests/integration/test_003_g_02.py`
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from cgb.app import AppPair
from integration.test_003_g_01 import ensure_measurements
from integration.test_api_models import L4, QWEN_7B, QWEN_7B_BYTES, VRAM_TOTAL, resources, set_loaded, set_tags, tag
from integration.test_api_session import ColabWorld, open_ready, wait_until
from realrun.conftest import write_measurement

pytestmark = pytest.mark.realrun

CASE, TASK = "G-02", "T069"
PROBE_SECONDS = 3.0
FAST_SECONDS = 1.0
THRESHOLD = (
    "則1:10 次之後 probe_resources call_count 1;則2:第 2~10 次每次 < 1 秒;"
    "則3:10 次的 vramBytes 都是 16,106,127,360;則4:第 1 次 ≥ 3 秒;則5:變更類型後那 1 次之後 call_count 2"
)


async def slow_probe(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """讀一次顯示記憶體要 3 秒的 `probe_resources`(SC-002 原樣)。"""
    await asyncio.sleep(PROBE_SECONDS)
    return resources(vram_total=VRAM_TOTAL)


async def test_g_02(make_app: Callable[..., AppPair], start_live_servers: Callable[..., Any], fakes: Any) -> None:
    # Arrange:真的 HTTP 連線;工作階段開到就緒(替身)
    ColabWorld(fakes)
    servers = start_live_servers(make_app())
    async with httpx.AsyncClient(base_url=servers.ui_url, timeout=30.0) as client:
        old = (await open_ready(client))["name"]
        set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
        set_loaded(fakes)
        fakes.colab.probe_resources.side_effect(slow_probe)
        fakes.colab.probe_resources.reset_calls()

        # Act:連續 10 次列出目錄
        elapsed: list[float] = []
        responses: list[httpx.Response] = []
        for _ in range(10):
            started = time.monotonic()
            responses.append(await client.get("/api/models"))
            elapsed.append(time.monotonic() - started)
        calls_after_ten = fakes.colab.probe_resources.call_count

        # 變更類型,等到新的工作階段就緒後再列一次
        restart = await client.post("/api/session/restart", json={"runtimeType": L4})
        new = await wait_until(client, lambda s: s.get("state") == "ready" and s.get("name") != old, timeout=10.0)
        started = time.monotonic()
        after_restart = await client.get("/api/models")
        after_restart_seconds = time.monotonic() - started
        calls_after_restart = fakes.colab.probe_resources.call_count

    statuses = [r.status_code for r in responses]
    vram = [r.json().get("vramBytes") if r.status_code == 200 else None for r in responses]
    checks = {
        "則1": calls_after_ten == 1,
        "則2": max(elapsed[1:]) < FAST_SECONDS,
        "則3": all(v == VRAM_TOTAL for v in vram),
        "則4": elapsed[0] >= PROBE_SECONDS,
        "則5": calls_after_restart == 2,
    }
    numbers = (
        f"10 次之後 call_count {calls_after_ten};第 1 次 {elapsed[0]:.3f} 秒;"
        f"第 2~10 次 {', '.join(f'{s:.3f}' for s in elapsed[1:])} 秒(最大 {max(elapsed[1:]):.3f});"
        f"10 次的狀態碼 {sorted(set(statuses))}、vramBytes {sorted({f'{v:,}' if v is not None else 'null' for v in vram})};"
        f"變更類型 {restart.status_code},新工作階段 {new.get('state')}(名稱{'不同' if new.get('name') != old else '相同'});"
        f"變更類型後那 1 次 {after_restart.status_code}、{after_restart_seconds:.3f} 秒,之後 call_count {calls_after_restart}"
    )
    failed = [name for name, ok in checks.items() if not ok]
    note = ("沒過:" + "、".join(failed) + ";" if failed else "") + "uvicorn 只綁 127.0.0.1 隨機 port,Colab 與遠端 Ollama 都用替身"
    write_measurement(CASE, TASK, numbers, THRESHOLD, not failed, note, path=ensure_measurements())

    # Assert
    assert not failed, numbers
