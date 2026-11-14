"""E2 後端 UI API:自動下載(testplan.md § 4.1,`/api/session` 就緒時排入、`/api/downloads`、`/api/downloads/auto-result`)。

接縫:HTTP `/api/*`,五個轉接層與 Hugging Face 替身(`FakeHuggingFaceHub`);精選清單與自動下載結果存在 SQLite。
`set_hf`、`curate`、`wait_auto` 與 `HF_SMOL` 取自 `test_api_curated.py`(testplan.md § 4.1)。
"""

import asyncio
import time
from typing import Any

import httpx

from integration.test_api_curated import HF_SMOL, HF_SMOL_BYTES, curate, set_hf, wait_auto
from integration.test_api_downloads import downloadable, hold_pulls, queue, set_library
from integration.test_api_models import set_tags, tag
from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    open_ready,
    ui_client,
)


async def wait_calls(method: Any, count: int = 1, timeout: float = 1.0) -> None:
    """等替身方法被呼叫到 `count` 次(下載在背景開始)。"""
    deadline = time.monotonic() + timeout
    while method.call_count < count and time.monotonic() < deadline:
        await asyncio.sleep(0.01)


# ---- 004 US3-API-12


async def test_第一次就緒時依清單順序排入設了自動下載的項目_hf_名稱向_Hugging_Face_取大小(
    ui_client: httpx.AsyncClient, fakes: Any
) -> None:
    # Arrange:沒有工作階段時依序新增三項
    downloadable(fakes)
    set_library(fakes)
    set_hf(fakes, {HF_SMOL: HF_SMOL_BYTES})
    hold_pulls(fakes)
    await curate(ui_client, "qwen2.5:7b", auto=True)
    await curate(ui_client, "qwen2.5:1.5b", auto=False)
    await curate(ui_client, HF_SMOL, auto=True)

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")
    await wait_calls(fakes.remote_ollama.pull_model)
    jobs = (await queue(ui_client))["jobs"]

    # Assert
    assert [job["model"] for job in jobs] == ["qwen2.5:7b", HF_SMOL]  # 則1
    assert [job["origin"] for job in jobs] == ["auto", "auto"]  # 則2
    assert [job["preloadOnComplete"] for job in jobs] == [False, False]  # 則3
    assert [job.get("source") for job in jobs] == ["library", "huggingface"]  # 則4
    assert result is not None and result["enqueued"] == ["qwen2.5:7b", HF_SMOL]  # 則5
    assert result["skipped"] == []  # 則6
    library_calls = fakes.model_library.get_manifest.calls
    assert not [c for c in library_calls if c.kwargs.get("tag") == "1.5b"]  # 則7
    hf_calls = fakes.huggingface.get_manifest.calls
    assert [c.kwargs.get("tag") for c in hf_calls] == ["Q4_K_M"]  # 則8
    assert not [c for c in library_calls if str(c.kwargs.get("name")).startswith("hf.co/")]  # 則9
    assert fakes.remote_ollama.pull_model.calls[0].kwargs.get("model") == "qwen2.5:7b"  # 則10


# ---- 004 US3-API-13


async def test_執行環境上已有的項目不排_大小寫不同也算已有_也不取大小(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:執行環境上已有 `hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m`(和精選清單的寫法大小寫不同)
    downloadable(fakes)
    set_hf(fakes, {HF_SMOL: HF_SMOL_BYTES})
    set_tags(fakes, tag("hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m", HF_SMOL_BYTES))
    hold_pulls(fakes)
    await curate(ui_client, HF_SMOL, auto=True)
    await curate(ui_client, "qwen2.5:0.5b", auto=True)

    # Act
    await open_ready(ui_client)
    result = await wait_auto(ui_client, lambda r: r is not None and r["state"] == "done")
    jobs = (await queue(ui_client))["jobs"]

    # Assert
    assert result is not None and result["enqueued"] == ["qwen2.5:0.5b"]  # 則1
    assert result["skipped"] == []  # 則2
    assert [job["model"] for job in jobs] == ["qwen2.5:0.5b"]  # 則3
    assert fakes.huggingface.get_manifest.call_count == 0  # 則4
