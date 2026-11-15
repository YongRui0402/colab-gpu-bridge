"""跨端點驗收:工作階段結束後可以直接開新的(docs/觀察紀錄.md 2026-11-14)。

001~003 的 testplan 都沒有「結束後再開」:`ended`、`lost-timeout` 停在結果訊息,沒有任何地方能開新的。
接縫同 `test_us1_session.py`:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身,不開真的 Colab。
"""

from typing import Any

import httpx
from playwright.sync_api import Page, expect

from cgb.adapters.errors import AdapterError
from e2e.test_us1_session import ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture
from e2e.test_us4_usage import advance_clocks, reading, serve, sync_browser_clock  # noqa: F401 - `serve` 是 fixture


def open_from(page: Page, state: str) -> None:
    """在結束類狀態的區塊裡改選 L4 再按「開啟」:送出 `POST /api/session`,之後開到就緒。"""
    panel = page.locator(f'[data-state="{state}"]')
    expect(panel).to_be_visible()
    expect(panel.locator('input[type="radio"]')).to_have_count(4)
    panel.locator('input[type="radio"][value="L4"]').check()

    with page.expect_request(lambda r: r.method == "POST" and r.url.endswith("/api/session")) as sent:
        panel.get_by_role("button", name="開啟", exact=True).click()

    # 005:開啟畫面一律帶「Ollama 設定」三個欄位;都沒填就是三個 null(全部自動,FR-009)
    assert sent.value.post_data_json == {
        "runtimeType": {"gpu": "L4", "highMem": False},
        "tuning": {"numParallel": None, "contextLength": None, "maxLoadedModels": None},
    }
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    expect(page.locator("#r-type")).to_contain_text("L4")


def test_使用者結束後_在已結束畫面選類型就能開新的(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange
    open_to_ready(page)

    # Act
    page.locator('[data-state="ready"]').get_by_role("button", name="結束", exact=True).click()
    page.click("#stop")

    # Assert
    open_from(page, "ended")


def test_閒置自動結束後_在已結束畫面選類型就能開新的(page: Page, e2e_servers: Any, world: ColabWorld, fake_clock: Any) -> None:
    # Arrange:閒置時限 1 分鐘
    reply = httpx.put(f"{e2e_servers.ui_url}/api/settings", json={"idleTimeoutMinutes": 1, "lowBalanceThreshold": 10})
    assert reply.status_code == 200
    sync_browser_clock(page, fake_clock)
    open_to_ready(page)

    # Act
    advance_clocks(page, fake_clock, 61)

    # Assert
    open_from(page, "ended-idle")


def test_開啟失敗後_在開啟失敗畫面選類型就能開新的(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    fakes.colab.create_session.then(AdapterError("COLAB_ALLOCATION_REFUSED", "Colab refused to allocate"))
    page.goto("/")

    # Act
    page.click("#open")

    # Assert
    open_from(page, "failed")


def test_被Colab收回後_在失聯畫面選類型就能開新的(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)

    # Act
    world.alive.clear()
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))

    # Assert
    open_from(page, "lost")


def test_重連逾時並已釋放後_在失聯畫面選類型就能開新的(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    fakes.tunnel.open_tunnel.raises("TUNNEL_FAILED", "ssh exited")

    # Act
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))
    expect(page.locator('[data-state="lost-timeout"]')).to_be_visible(timeout=10_000)
    fakes.tunnel.open_tunnel.side_effect(world._open_tunnel)

    # Assert
    open_from(page, "lost-timeout")


def test_餘額可能歸零而失聯後_在失聯畫面選類型就能開新的(page: Page, world: ColabWorld, fakes: Any, serve: Any) -> None:
    # Arrange:最後一次讀到的餘額 0.00,首頁是低餘額警告的「開啟」
    fakes.colab.get_usage.returns(reading(0.00, 1.76))
    serve()
    page.goto("/")
    page.locator('[data-state="low-balance"]').get_by_role("button", name="開啟", exact=True).click()
    expect(page.locator('[data-state="ready"]')).to_be_visible()

    # Act
    world.alive.clear()
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))

    # Assert
    open_from(page, "lost-zero")


def test_釋放不了時畫面上沒有開啟按鈕_要先處理釋放(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:對照組。FR-007:舊執行環境可能還在扣 compute units
    open_to_ready(page)
    fakes.tunnel.open_tunnel.raises("TUNNEL_FAILED", "ssh exited")
    fakes.colab.stop_session.raises("COLAB_STOP_UNCONFIRMED", "colab sessions still lists it")

    # Act
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))

    # Assert
    expect(page.locator('[data-state="release-failed"]')).to_be_visible(timeout=10_000)
    expect(page.locator('[data-state="lost-timeout"]')).to_be_visible()
    expect(page.get_by_role("button", name="開啟", exact=True)).to_have_count(0)
    expect(page.locator('[data-state="lost-timeout"] [data-picker]')).to_be_hidden()
