"""跨端點驗收:首頁的閒置倒數與失聯提示(testplan.md § 5.6)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨、plan.md Q99);
時間一律用注入的假時鐘推進,瀏覽器的時鐘以 Playwright 的 `page.clock` 跟著推進,不真的等閒置時限。
"""

from typing import Any

import httpx
from playwright.sync_api import Page, expect

from cgb.adapters.errors import AdapterError
from e2e.test_us1_session import ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture
from e2e.test_us4_usage import (  # noqa: F401 - `serve` 是 fixture
    advance_clocks,
    reading,
    serve,
    sync_browser_clock,
    wait_countdown_between,
)


# ---------------------------------------------------------------- US4-AJ-06


def test_閒置倒數跟著時間走_到期後不必重新整理就顯示閒置自動結束(
    page: Page, e2e_servers: Any, world: ColabWorld, fake_clock: Any
) -> None:
    # Arrange:閒置時限 1 分鐘
    reply = httpx.put(f"{e2e_servers.ui_url}/api/settings", json={"idleTimeoutMinutes": 1, "lowBalanceThreshold": 10})
    assert reply.status_code == 200
    sync_browser_clock(page, fake_clock)
    open_to_ready(page)

    # Act
    advance_clocks(page, fake_clock, 30)
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    wait_countdown_between(page, 20, 30)
    advance_clocks(page, fake_clock, 31)

    # Assert
    ended = page.locator('[data-state="ended-idle"]')
    expect(ended).to_be_visible()
    expect(ended).to_contain_text("閒置自動結束")


# ---------------------------------------------------------------- US4-AJ-07


def test_最後讀到的餘額為0時失聯_提示餘額可能已經歸零(page: Page, world: ColabWorld, fakes: Any, serve: Any) -> None:
    # Arrange:最後一次讀到的餘額 0.00(低於預設門檻 10,首頁是低餘額警告的「開啟」)
    fakes.colab.get_usage.returns(reading(0.00, 1.76))
    serve()
    page.goto("/")
    page.locator('[data-state="low-balance"]').get_by_role("button", name="開啟", exact=True).click()
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    lost_zero = page.locator('[data-state="lost-zero"]')

    # Act:Colab 已經沒有這台,通道也斷了
    world.alive.clear()
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))

    # Assert
    expect(lost_zero).to_be_visible()
    expect(lost_zero).to_contain_text("餘額可能已經歸零")
