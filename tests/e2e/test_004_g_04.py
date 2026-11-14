"""G-04(tasks.md T236):Hugging Face 不回應時,下載頁在 11 秒內說暫時無法使用,官方搜尋不受影響(004 testplan.md § 7.2)。

`e2e_servers` 起真的後端(UI 127.0.0.1:8781),Hugging Face 注入真的 `HuggingFaceHub`,transport 的 handler 收到請求就
`await asyncio.sleep(60)`(不連網),逾時用原樣的 10 秒;官方模型庫用 `FakeModelLibrary`,搜尋回 `qwen2.5`。
情況 A 在 `#hf-q` 搜尋 `qwen`,等的同時每 1 秒在官方搜尋送一次 `qwen2.5`;情況 B 打開
`bartowski/SmolLM2-135M-Instruct-GGUF` 的展開。畫面上要先有這一筆搜尋結果才有展開的按鈕,所以 B 的 handler 對
`/api/models`(搜尋)立刻回這一筆,tree 與 manifest 照樣睡 60 秒(分身決策紀錄 D121)。

標 `realrun`,預設排除。護欄:不連網(handler 只 sleep);UI 只綁 127.0.0.1:8781(e2e 的固定 port,同一時間只跑一份);
資料庫是 pytest 暫存資料夾的 SQLite;不執行任何 `colab` 指令;約 25 秒。
判定者:腳本(和 11 秒、1 秒比較);樣本:一次量測(未用於調整)。
執行:`uv run pytest -m realrun tests/e2e/test_004_g_04.py`
"""

import asyncio
import re
import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from playwright.sync_api import Page, expect

from cgb.adapters.huggingface import HuggingFaceHub
from cgb.app import AppPair
from e2e.test_004_us4_hf import SMOL_ID, expand_quants, hf_result, hf_search
from e2e.test_us1_session import ColabWorld, world  # noqa: F401 - `world` 是 fixture
from integration.test_004_g_01 import ensure_measurements
from realrun.conftest import write_measurement

pytestmark = pytest.mark.realrun

CASE, TASK = "G-04", "T236"
HF_LIMIT = 11.0
OFFICIAL_LIMIT = 1.0
HANG_SECONDS = 60.0
THRESHOLD = "則1:A 從送出到 hf-down 顯示 ≤ 11 秒;則2:A 等待期間官方搜尋每一次都在 1 秒內列出 qwen2.5;則3:B 從送出到 hf-expand-down 顯示 ≤ 11 秒;則4:A、B 的 UI API 回應都不是 500"


class Handler:
    """收到請求就睡 60 秒;`answer_search` 為 True 時,搜尋(`/api/models`)立刻回 SmolLM2 這一筆。"""

    def __init__(self) -> None:
        self.answer_search = False
        self.received: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.received.append(request.url.path)
        if self.answer_search and request.url.path == "/api/models":
            return httpx.Response(200, json=[{"id": SMOL_ID, "downloads": 1000, "gated": False}])
        await asyncio.sleep(HANG_SECONDS)
        return httpx.Response(200, json={})


@pytest.fixture
def handler() -> Handler:
    return Handler()


@pytest.fixture
def app_pair(make_app: Callable[..., AppPair], handler: Handler) -> AppPair:
    return make_app(huggingface=HuggingFaceHub(transport=httpx.MockTransport(handler)))


def official_search(page: Page) -> float:
    """在官方搜尋送一次 `qwen2.5`,回傳從按下到列出 `qwen2.5` 的秒數。"""
    result = page.locator("#lib-results .result").filter(has=page.locator(".item-name", has_text=re.compile(r"^qwen2\.5$")))
    page.fill("#lib-q", "qwen2.5")
    started = time.monotonic()
    with page.expect_response(lambda r: "/api/library/search?" in r.url, timeout=5_000):
        page.locator("#lib-form").get_by_role("button", name="搜尋").click()
    expect(result).to_be_visible(timeout=5_000)
    return time.monotonic() - started


def test_g_04(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any, handler: Handler) -> None:
    # Arrange
    fakes.model_library.search_library.returns(
        {"items": [{"name": "qwen2.5", "description": None, "parameterSizes": [], "capabilities": []}], "hasMore": False}
    )
    statuses: list[tuple[str, int]] = []
    page.on("response", lambda r: statuses.append((r.url, r.status)) if "/api/" in r.url else None)
    down = page.locator('[data-state="hf-down"]')
    expand_down = page.locator('[data-state="hf-expand-down"]')

    # Act A:HF 搜尋送出後,每 1 秒送一次官方搜尋,直到 hf-down 顯示
    page.goto("/library.html")
    expect(page.locator("#hf-form")).to_be_visible()
    hf_search(page, "qwen")
    a_started = time.monotonic()
    official: list[float] = []
    a_seconds: float | None = None
    while time.monotonic() - a_started < HF_LIMIT + 4:
        if down.is_visible():
            a_seconds = time.monotonic() - a_started
            break
        official.append(official_search(page))
        tick = time.monotonic()
        while time.monotonic() - tick < 1.0:
            if down.is_visible():
                break
            time.sleep(0.02)
    a_statuses = list(statuses)

    # Act B:搜尋立刻回這一筆,展開(tree、manifest)睡 60 秒
    handler.answer_search = True
    page.goto("/library.html")
    hf_search(page, "smol")
    result = hf_result(page, SMOL_ID)
    expect(result).to_be_visible()
    b_started = time.monotonic()
    expand_quants(result)
    b_seconds: float | None = None
    try:
        expand_down.wait_for(state="visible", timeout=(HF_LIMIT + 4) * 1000)
        b_seconds = time.monotonic() - b_started
    except Exception:
        pass
    b_text = expand_down.inner_text() if b_seconds is not None else ""

    # 量到的數字
    errors = [(url.split("/api", 1)[1], status) for url, status in statuses if status >= 500]
    checks = {
        "則1": a_seconds is not None and a_seconds <= HF_LIMIT,
        "則2": bool(official) and all(t <= OFFICIAL_LIMIT for t in official),
        "則3": b_seconds is not None and b_seconds <= HF_LIMIT and "Hugging Face 暫時無法使用" in b_text,
        "則4": not [e for e in errors if e[1] == 500],
    }
    numbers = [
        f"A:送出到 hf-down {a_seconds:.2f} 秒" if a_seconds is not None else f"A:{HF_LIMIT + 4:g} 秒內沒顯示 hf-down",
        f"A 等待期間官方搜尋 {len(official)} 次(秒)" + "、".join(f"{t:.3f}" for t in official) + (f",最大 {max(official):.3f}" if official else ""),
        (f"B:送出到 hf-expand-down {b_seconds:.2f} 秒,含「Hugging Face 暫時無法使用」{'是' if 'Hugging Face 暫時無法使用' in b_text else '否'}"
         if b_seconds is not None else f"B:{HF_LIMIT + 4:g} 秒內沒顯示 hf-expand-down"),
        f"UI API 回應 {len(statuses)} 個(A {len(a_statuses)} 個),5xx:{errors or '無'}",
        f"handler 收到 {len(handler.received)} 個請求:{sorted(set(handler.received))}",
    ]  # fmt: skip
    failed = [name for name, ok in checks.items() if not ok]
    note = ("沒過:" + "、".join(failed) + ";" if failed else "") + "不連網(handler 只 sleep 60 秒),逾時用原樣的 10 秒;B 的搜尋立刻回一筆(D121)"
    write_measurement(CASE, TASK, ";".join(numbers), THRESHOLD, not failed, note, path=ensure_measurements())

    # Assert
    assert not failed, ";".join(numbers)
