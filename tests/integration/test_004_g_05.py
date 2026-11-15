"""G-05(tasks.md T237):Hugging Face 不回應時,自動下載仍在就緒後 30 秒內有結果(004 testplan.md § 7.2;research.md R6)。

後端以 `make_app` 建、`start_live_servers` 起在 127.0.0.1 隨機 port;Hugging Face 注入真的 `HuggingFaceHub`,transport 的
handler 收到請求就 `await asyncio.sleep(60)`(不連網),逾時用原樣的 10 秒;精選清單有 8 個 hf.co 名稱都設了自動下載,
`probe_resources` 回剩餘磁碟 225,485,783,040、顯示記憶體 16,106,127,360。開啟工作階段到就緒,從就緒起每 0.5 秒讀一次
`GET /api/downloads/auto-result`,記下就緒到 `done` 的秒數、跳過的原因與 handler 同時在處理的請求數最大值。

標 `realrun`,預設排除;不放 `tests/realrun/`,不經會執行 `colab usage` 的 `realrun` fixture。
護欄:不連網(handler 只 sleep);資料庫是 pytest 暫存資料夾的 SQLite;Colab、通道、遠端 Ollama 用替身,
不執行任何 `colab` 指令、不花 compute units;約 25 秒。
判定者:腳本(和 30 秒、4 個比較);樣本:一次量測(未用於調整)。
執行:`uv run pytest -m realrun tests/integration/test_004_g_05.py`
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from cgb.adapters.huggingface import HuggingFaceHub
from cgb.app import AppPair
from integration.test_004_g_01 import ensure_measurements
from integration.test_api_curated import curate
from integration.test_api_downloads import downloadable
from integration.test_api_session import open_ready
from realrun.conftest import write_measurement

pytestmark = pytest.mark.realrun

CASE, TASK = "G-05", "T237"
LIMIT_SECONDS = 30.0
POLL_SECONDS = 0.5
HANG_SECONDS = 60.0
NAMES = [
    "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M",
    "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q8_0",
    "hf.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M",
    "hf.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M",
    "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M",
    "hf.co/unsloth/Qwen3-0.6B-GGUF:Q4_K_M",
    "hf.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M",
    "hf.co/lmstudio-community/gemma-3-1b-it-GGUF:Q4_K_M",
]
THRESHOLD = "則1:就緒後 30 秒內 result.state 變成 done;則2:跳過的 8 筆 reason 都是 SIZE_UNAVAILABLE、reasonCode 都是 HF_TIMEOUT;則3:handler 同時處理的請求最多 4 個"


class Hanging:
    """收到請求就睡 60 秒的 handler;記下同時在處理的請求數最大值與收到的請求數。"""

    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self.received = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.received += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(HANG_SECONDS)
            return httpx.Response(200, json={})
        finally:
            self.active -= 1


async def test_g_05(make_app: Callable[..., AppPair], start_live_servers: Callable[..., Any], fakes: Any) -> None:
    # Arrange
    downloadable(fakes)
    fakes.colab.probe_resources.returns(
        {
            "diskFreeBytes": 225_485_783_040,
            "diskTotalBytes": 253_338_115_072,
            "gpuName": "Tesla T4",
            "vramTotalBytes": 16_106_127_360,
            "vramFreeBytes": 15_727_591_424,
            "checkedAt": "2026-11-09T09:00:00Z",
        }
    )
    handler = Hanging()
    servers = start_live_servers(make_app(huggingface=HuggingFaceHub(transport=httpx.MockTransport(handler))))
    async with httpx.AsyncClient(base_url=servers.ui_url, timeout=10.0) as client:
        for name in NAMES:
            await curate(client, name, auto=True)

        # Act
        await open_ready(client)
        ready_at = time.monotonic()
        polls: list[tuple[float, str | None]] = []
        result: Any = None
        while time.monotonic() - ready_at < LIMIT_SECONDS + 5:
            result = (await client.get("/api/downloads/auto-result")).json().get("result")
            polls.append((time.monotonic() - ready_at, result["state"] if result else None))
            if result is not None and result["state"] == "done":
                break
            await asyncio.sleep(POLL_SECONDS)
        done_after = polls[-1][0] if polls and polls[-1][1] == "done" else None

    # 量到的數字
    skipped = result["skipped"] if result else []
    checks = {
        "則1": done_after is not None and done_after <= LIMIT_SECONDS,
        "則2": len(skipped) == 8 and all(s["reason"] == "SIZE_UNAVAILABLE" and s["reasonCode"] == "HF_TIMEOUT" for s in skipped),
        "則3": handler.peak <= 4,
    }
    numbers = [
        f"就緒到 done {done_after:.2f} 秒(讀了 {len(polls)} 次)" if done_after is not None else f"{LIMIT_SECONDS + 5:g} 秒內沒有 done(讀了 {len(polls)} 次)",
        f"跳過 {len(skipped)} 筆,reason {sorted({s['reason'] for s in skipped})}、reasonCode {sorted({s['reasonCode'] for s in skipped})};"
        f"排入 {len(result['enqueued']) if result else '—'} 筆",
        f"handler 收到 {handler.received} 個請求,同時處理最多 {handler.peak} 個",
    ]
    failed = [name for name, ok in checks.items() if not ok]
    note = ("沒過:" + "、".join(failed) + ";" if failed else "") + "不連網(handler 只 sleep 60 秒),逾時用原樣的 10 秒"
    write_measurement(CASE, TASK, ";".join(numbers), THRESHOLD, not failed, note, path=ensure_measurements())

    # Assert
    assert not failed, ";".join(numbers)
