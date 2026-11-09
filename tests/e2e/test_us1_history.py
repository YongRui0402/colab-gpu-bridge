"""跨端點驗收:紀錄頁(testplan.md § 2.11)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨、plan.md Q99)。
三次工作階段經 HTTP `/api/*` 開關(同一張表的接縫),再以瀏覽器看紀錄頁。
"""

import time
from typing import Any

import httpx
from playwright.sync_api import Page, expect

from cgb.adapters.errors import AdapterError
from e2e.test_us1_session import ColabWorld, world  # noqa: F401 - `world` 是 fixture

T4 = {"runtimeType": {"gpu": "T4", "highMem": False}}


def wait_for_state(client: httpx.Client, state: str, timeout: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        session = client.get("/api/session").json()
        if session["state"] == state:
            return session
        if time.monotonic() > deadline:
            raise AssertionError(f"等了 {timeout} 秒,工作階段仍是 {session['state']}(預期 {state})")
        time.sleep(0.02)


# ---------------------------------------------------------------- US1-AJ-13


def test_紀錄頁由新到舊列出三次工作階段與運行時長(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any, fake_clock: Any
) -> None:
    # Arrange:使用者結束(運行 2 分鐘)、開啟失敗、目前就緒
    with httpx.Client(base_url=e2e_servers.ui_url) as client:
        client.post("/api/session", json=T4)
        oldest = wait_for_state(client, "ready")["name"]
        fake_clock.advance(120)
        client.delete("/api/session")
        wait_for_state(client, "ended")
        fakes.colab.create_session.then(AdapterError("COLAB_ALLOCATION_REFUSED", "Colab refused to allocate"))
        client.post("/api/session", json=T4)
        wait_for_state(client, "open_failed")
        client.post("/api/session", json=T4)
        newest = wait_for_state(client, "ready")["name"]
    rows = page.locator("#rows > tr")

    # Act
    page.goto("/history.html")

    # Assert
    expect(rows).to_have_count(3)
    expect(rows.nth(0)).to_contain_text(newest)
    expect(rows.nth(0).locator("td").nth(1)).to_have_text("—")
    expect(rows.nth(2)).to_contain_text(oldest)
    oldest_cells = rows.nth(2).locator("td")
    expect(oldest_cells.nth(0)).not_to_be_empty()
    expect(oldest_cells.nth(1)).not_to_be_empty()
    expect(oldest_cells.nth(2)).to_have_text("T4")
    expect(oldest_cells.nth(3)).to_contain_text("使用者結束")
    expect(oldest_cells.nth(4)).to_contain_text("2 分")
