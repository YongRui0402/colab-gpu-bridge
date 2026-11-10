"""US1-AJ-21(tasks.md T153):在首頁按「結束工作階段」並確認,1 分鐘內 Colab 上沒有這台,首頁顯示已結束與使用者結束(SC-003)。

前置:US1-AJ-20 的 T4 高 RAM 工作階段就緒。畫面用 Playwright:就緒區塊的「結束」→ 確認區塊的「結束工作階段」。
結束 1 台,約 2 分鐘、約 0.04 compute units。
"""

import time

from playwright.sync_api import Page, expect

from realrun.helpers_container import UI, browser_page, get_stack, verdict

GONE_DEADLINE = 60


def test_us1_aj_21(realrun):
    with browser_page() as page:
        _measure(realrun, page)


def _measure(realrun, page: Page) -> None:
    stack = get_stack(realrun)
    stack.require("US1-AJ-21", "T153", "highram_ready")
    name = stack.state["main"]

    page.goto(f"{UI}/")
    page.locator('section[data-state="ready"]:not([hidden])').wait_for(state="visible", timeout=30_000)
    page.locator('section[data-state="ready"] [data-go="confirm-stop"]').click()
    page.locator("#stop").click()
    clicked = time.monotonic()
    gone_s = stack.wait_gone(name, GONE_DEADLINE + 5)

    ended = page.locator('section[data-state="ended"]:not([hidden])')
    shown = True
    try:
        expect(ended).to_be_visible(timeout=90_000)
        expect(ended.locator(".pill")).to_have_text("已結束")
        expect(page.locator("#e-reason")).to_contain_text("使用者結束")
    except AssertionError:
        shown = False
    reason_text = page.locator("#e-reason").text_content() if ended.count() else None
    stack.state["main_ready"] = stack.state["highram_ready"] = False

    checks = {"則1": gone_s is not None and gone_s <= GONE_DEADLINE, "則2": shown}
    numbers = (
        f"按下到 colab sessions 沒有這台 {f'{gone_s:.1f} 秒' if gone_s is not None else '超過 1 分鐘'};"
        f"畫面結束原因 {reason_text!r};按下到量完 {time.monotonic() - clicked:.1f} 秒"
    )
    verdict("US1-AJ-21", "T153", checks, numbers, "則1 1 分鐘內沒有這個名稱;則2 首頁顯示已結束與使用者結束", [])
