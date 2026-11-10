"""US1-AJ-22(tasks.md T154):在終端機 `colab stop` 模擬被 Colab 收回,2 分鐘內顯示失聯(SC-002、Q103)。

前置:沒有工作階段。開 1 台 T4(經 UI API)到就緒;主機上以 `HOME=<暫存目錄>/home colab stop -s <這個名稱>`
(`realrun.colab()`,只帶這次的 cgb-test- 名稱;和容器共用 `<暫存目錄>/data/colab-cli`),每 5 秒讀一次 `GET /api/session`。
畫面用 Playwright 看「失聯」與「重新開啟」(不按)。約 5 分鐘、約 0.1 compute units。
"""

import time

from playwright.sync_api import Page, expect

from realrun.helpers_container import UI, browser_page, get_stack, verdict

LOST_DEADLINE = 150


def test_us1_aj_22(realrun):
    with browser_page() as page:
        _measure(realrun, page)


def _measure(realrun, page: Page) -> None:
    stack = get_stack(realrun)
    stack.require("US1-AJ-22", "T154")
    leftover = stack.ensure_no_active()
    extra = [f"開之前先結束了前一個案例留下的 {leftover}"] if leftover else []
    last, open_s = stack.open("T4", False)
    name = (last or {}).get("name")
    if (last or {}).get("state") != "ready":
        verdict("US1-AJ-22", "T154", {"前置": False}, f"開啟 {open_s:.1f} 秒", "就緒",
                [f"沒有就緒:{(last or {}).get('state')}、{(last or {}).get('reasonCode')}"])  # fmt: skip

    stop = realrun.colab("stop", "-s", name, timeout=120)
    realrun.record_raw("us1_aj_22", f"$ colab stop -s {name} (exit {stop.returncode})\n{stop.stdout}{stop.stderr}\n")
    returned = time.monotonic()
    lost, _, samples = stack.poll_session(lambda s: s.get("state") in ("lost", "ended", "open_failed"), LOST_DEADLINE)
    to_lost = time.monotonic() - returned

    page.goto(f"{UI}/")
    panel = page.locator('section[data-state="lost"]:not([hidden])')
    shown = True
    try:
        expect(panel).to_be_visible(timeout=30_000)
        expect(panel.locator(".pill")).to_have_text("失聯")
        expect(panel.locator('[data-action="reopen"]')).to_have_text("重新開啟")
    except AssertionError:
        shown = False

    checks = {
        "則1": (lost or {}).get("state") == "lost" and to_lost <= 120,
        "則2": (lost or {}).get("endReason") == "RECLAIMED_BY_COLAB",
        "則3": shown,
    }
    extra.append(f"狀態取樣 {samples}")
    numbers = (
        f"開啟 {open_s:.1f} 秒;colab stop exit {stop.returncode};stop 回來到 {(lost or {}).get('state')} {to_lost:.1f} 秒;"
        f"endReason {(lost or {}).get('endReason')}"
    )
    verdict("US1-AJ-22", "T154", checks, numbers, "則1 2 分鐘內 lost;則2 RECLAIMED_BY_COLAB;則3 首頁顯示失聯與重新開啟", extra)
