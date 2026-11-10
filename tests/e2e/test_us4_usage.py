"""跨端點驗收:用量與設定頁(testplan.md § 5.6)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身、時鐘由測試注入(testplan.md § 接縫的取捨、plan.md Q99)。
後端啟動時就會讀一次用量,所以每個測試先設好 `get_usage` 的結果,再以 `serve()` 啟動後端。
"""

import re
import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from playwright.sync_api import Page, expect

from e2e.conftest import E2E_OLLAMA_PORT
from e2e.test_us1_session import CJK, ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture
from fakes import JsonReply


def reading(balance: float, rate: float) -> dict[str, Any]:
    """`colab usage` 讀到的一次用量(contracts/colab-cli.openapi.yaml § getUsage;讀取時間是假時鐘的起點)。"""
    return {"balance": balance, "ratePerHour": rate, "activeAssignments": 0, "readAt": "2026-11-09T09:00:00Z"}


def sync_browser_clock(page: Page, clock: Any) -> None:
    """瀏覽器的時鐘換成和後端注入的假時鐘同一個時間,之後兩邊一起照真實時間走(閒置倒數以 `deadline` 減瀏覽器的現在)。

    要在第一次打開頁面之前呼叫。
    """
    page.clock.install(time=clock.now())


def advance_clocks(page: Page, clock: Any, seconds: float) -> None:
    """後端的假時鐘和瀏覽器的時鐘一起往前推。"""
    clock.advance(seconds)
    page.clock.fast_forward(int(seconds * 1000))


def countdown_seconds(page: Page) -> int:
    """`#r-countdown` 顯示的剩餘時間(「分:秒」)換成秒。"""
    text = page.locator("#r-countdown").inner_text()
    match = re.fullmatch(r"(\d+):(\d{2})", text.strip())
    assert match, f"倒數的格式不是「分:秒」:{text!r}"
    return int(match[1]) * 60 + int(match[2])


def wait_countdown_between(page: Page, low: int, high: int, timeout: float = 3.0) -> int:
    """等 `#r-countdown` 顯示的剩餘秒數落在 `low`~`high` 之間,回傳那個秒數;逾時就以最後看到的值斷言失敗。

    倒數每秒重畫一次:時鐘剛推進時,畫面上可能還是推進前最後一次重畫的值,所以給它一兩次重畫的時間。
    """
    deadline = time.monotonic() + timeout
    while True:
        seconds = countdown_seconds(page)
        if low <= seconds <= high or time.monotonic() > deadline:
            break
        page.wait_for_timeout(100)
    assert low <= seconds <= high, f"倒數剩 {seconds} 秒,不在 {low}~{high} 秒之間"
    return seconds


@pytest.fixture
def serve(request: pytest.FixtureRequest) -> Callable[[], Any]:
    """測試設好替身之後才啟動後端(UI 127.0.0.1:8781、Ollama 相容端點 127.0.0.1:11437)。"""
    return lambda: request.getfixturevalue("e2e_servers")


# ---------------------------------------------------------------- US4-AJ-01


def test_打開用量頁_顯示餘額每小時耗用可用時數與讀取時間(page: Page, world: ColabWorld, fakes: Any, serve: Any) -> None:
    # Arrange
    fakes.colab.get_usage.returns(reading(381.66, 1.15))
    serve()

    # Act
    page.goto("/usage.html")

    # Assert
    expect(page.locator('[data-state="normal"]')).to_be_visible()
    expect(page.locator("#n-balance")).to_contain_text("381.66")
    expect(page.locator("#n-rate")).to_contain_text("1.15")
    expect(page.locator("#n-hours")).to_contain_text("331")
    expect(page.locator("#n-read")).to_have_text(re.compile(r"\d{2}:\d{2} 讀取"))


# ---------------------------------------------------------------- US4-AJ-02


def test_第一次讀到用量之前顯示讀取中_讀到後不必重新整理就顯示數字(page: Page, world: ColabWorld, fakes: Any, serve: Any) -> None:
    # Arrange:後端啟動時的第一次讀取停在閘門前
    fakes.colab.get_usage.returns(reading(381.66, 1.15))
    gate = fakes.colab.get_usage.gate()
    serve()
    gate.wait_entered()
    loading = page.locator('[data-state="loading"]')
    normal = page.locator('[data-state="normal"]')

    # Act
    page.goto("/usage.html")
    expect(loading).to_be_visible()
    page.wait_for_timeout(1000)
    loading_after_a_second = loading.is_visible()
    normal_before_release = normal.is_visible()
    gate.release()

    # Assert
    assert loading_after_a_second
    assert not normal_before_release
    expect(normal).to_be_visible()
    expect(page.locator("#n-balance")).to_contain_text("381.66")


# ---------------------------------------------------------------- US4-AJ-03


def test_讀不到用量時顯示未知與中文原因_首頁照樣可以開到就緒(page: Page, world: ColabWorld, fakes: Any, serve: Any) -> None:
    # Arrange
    fakes.colab.get_usage.raises("COLAB_UNREACHABLE", "colab usage: connection refused")
    serve()
    unknown = page.locator('[data-state="unknown"]')

    # Act
    page.goto("/usage.html")
    expect(unknown).to_be_visible()
    balance_text = page.locator("#u-balance").inner_text()
    reason_text = page.locator("#u-reason").inner_text()
    page.goto("/")
    expect(page.locator("#open")).to_be_enabled()
    page.click("#open")

    # Assert
    assert balance_text == "未知"
    assert CJK.search(reason_text)
    assert "COLAB_" not in reason_text
    expect(page.locator('[data-state="ready"]')).to_be_visible()


# ---------------------------------------------------------------- US4-AJ-04


def test_餘額低於門檻時用量頁與首頁都警告_首頁照樣可以開到就緒(page: Page, world: ColabWorld, fakes: Any, serve: Any) -> None:
    # Arrange:警告門檻是預設的 10
    fakes.colab.get_usage.returns(reading(9.50, 1.15))
    serve()
    low_balance = page.locator('[data-state="low-balance"]')

    # Act
    page.goto("/usage.html")
    expect(page.locator('[data-state="low"]')).to_be_visible()
    warn_text = page.locator("#l-warn").inner_text()
    page.goto("/")
    expect(low_balance).to_be_visible()
    low_balance_text = low_balance.inner_text()
    open_button = low_balance.get_by_role("button", name="開啟", exact=True)
    expect(open_button).to_be_enabled()
    open_button.click()

    # Assert
    assert warn_text.strip()
    assert "compute units 快用完了" in low_balance_text
    expect(page.locator('[data-state="ready"]')).to_be_visible()


# ---------------------------------------------------------------- US4-AJ-05


def test_儲存設定後不必重新整理_用量頁依新門檻警告_首頁倒數依新閒置時限(
    page: Page, world: ColabWorld, fakes: Any, serve: Any, fake_clock: Any
) -> None:
    # Arrange:就緒,閒置時限是預設的 30 分鐘,剛收到一個請求
    fakes.colab.get_usage.returns(reading(381.66, 1.15))
    fakes.server.add("GET", "/api/tags", JsonReply({"models": []}))
    serve()
    sync_browser_clock(page, fake_clock)
    open_to_ready(page)
    assert httpx.get(f"http://127.0.0.1:{E2E_OLLAMA_PORT}/api/tags").status_code == 200
    page.goto("/usage.html")
    expect(page.locator('[data-state="normal"]')).to_be_visible()
    form = page.locator("#settings-form")
    expect(form.locator("#idle")).to_have_value("30")

    # Act
    form.locator("#idle").fill("10")
    form.locator("#warn").fill("400")
    form.get_by_role("button", name="儲存").click()
    expect(page.locator("#saved")).to_be_visible()
    low_without_reload = page.locator('[data-state="low"]')
    expect(low_without_reload).to_be_visible()
    page.goto("/")
    expect(page.locator('[data-state="ready"]')).to_be_visible()

    # Assert
    wait_countdown_between(page, 9 * 60, 10 * 60)


# ---------------------------------------------------------------- US4-AJ-08


def test_讀不到新的用量超過15分鐘_標示過期並保留原本的數字與讀取時間(
    page: Page, world: ColabWorld, fakes: Any, serve: Any, fake_clock: Any
) -> None:
    # Arrange:第一次讀取成功,之後一直讀不到
    fakes.colab.get_usage.then(reading(381.66, 1.15))
    fakes.colab.get_usage.raises("COLAB_TIMEOUT", "colab usage timed out")
    serve()
    page.goto("/usage.html")
    expect(page.locator('[data-state="normal"]')).to_be_visible()
    read_at = re.match(r"\d{2}:\d{2}", page.locator("#n-read").inner_text())
    assert read_at
    stale = page.locator('[data-state="stale"]')

    # Act
    fake_clock.advance(16 * 60)

    # Assert
    expect(stale).to_be_visible()
    expect(stale).to_contain_text("已過期")
    expect(stale).to_contain_text(f"最後一次讀取是 {read_at[0]}")
    expect(stale).to_contain_text("381.66")
