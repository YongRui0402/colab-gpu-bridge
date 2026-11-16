"""跨端點驗收:開工作階段時不列出開不到的 H100(004 testplan.md § 6.1)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨、plan.md Q99)。
後端的 `GpuType` 仍收 H100(spec.md 假設第五點):紀錄與精選清單裡的 H100 項目直接經 `/api/*` 寫進真的 SQLite。
"""

import time
from typing import Any

import httpx
from playwright.sync_api import Locator, Page, expect

from e2e.test_004_us3_curated import LLAMA, api, curate, curated_row
from e2e.test_us1_session import ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture

QWEN = "qwen2.5"
# 送出時補上 `:latest`(FR-018),清單與 `GET /api/curated` 上的名稱
QWEN_SHOWN = "qwen2.5:latest"
PICKABLE = ["T4", "L4", "G4", "A100"]


def radio_values(panel: Locator) -> list[str]:
    """類型選單裡每個選項的值,依畫面上的順序(含藏起來的 `<input>`)。"""
    return panel.locator('input[type="radio"][name^="type-"]').evaluate_all("els => els.map(e => e.value)")


def option_values(page: Page, selector: str) -> list[str]:
    return page.locator(f"{selector} option").evaluate_all("els => els.map(e => e.value)")


def wait_for_state(client: httpx.Client, state: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while client.get("/api/session").json()["state"] != state:
        assert time.monotonic() < deadline, f"等了 {timeout} 秒,工作階段仍不是 {state}"
        time.sleep(0.02)


# ---- 004 US5-AJ-01


def test_開啟面板的類型選單依序只有T4_L4_G4_A100_預設選中T4(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange:沒有工作階段
    open_panel = page.locator('[data-state="normal"]')

    # Act
    page.goto("/")
    expect(open_panel).to_be_visible()

    # Assert
    assert radio_values(open_panel) == PICKABLE
    expect(open_panel.locator('input[type="radio"][value="T4"]')).to_be_checked()


# ---- 004 US5-AJ-02


def test_變更類型的選單也沒有H100(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange:工作階段就緒(T4)
    open_to_ready(page)
    confirm = page.locator('[data-state="confirm-switch"]')

    # Act
    page.locator('[data-state="ready"]').get_by_role("button", name="變更類型").click()
    expect(confirm).to_be_visible()

    # Assert
    assert radio_values(confirm) == PICKABLE


# ---- 004 US5-AJ-03


def test_紀錄裡以前用H100開過的工作階段類型照常顯示H100(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange:以 H100 開一次、結束(後端仍收 H100)
    with httpx.Client(base_url=e2e_servers.ui_url) as client:
        assert client.post("/api/session", json={"runtimeType": {"gpu": "H100", "highMem": False}}).status_code == 202
        wait_for_state(client, "ready")
        client.delete("/api/session")
        wait_for_state(client, "ended")
    rows = page.locator("#rows > tr")

    # Act
    page.goto("/history.html")

    # Assert
    expect(rows).to_have_count(1)
    expect(rows.nth(0).locator("td").nth(2)).to_have_text("H100")


# ---- 004 US5-AJ-04


def recommended_of(e2e_servers: Any, name: str) -> Any:
    items = api(e2e_servers, "GET", "/curated").json()["items"]
    return next(c["recommendedRuntimeType"] for c in items if c["name"] == name)


def test_精選清單的H100照常顯示_修改表單不列H100_既有H100維持目前設定送出後不變(
    page: Page, e2e_servers: Any, world: ColabWorld
) -> None:
    # Arrange:qwen2.5 建議 H100、llama3.2:3b 建議 T4
    curate(e2e_servers, QWEN, recommendedRuntimeType={"gpu": "H100", "highMem": False})
    curate(e2e_servers, LLAMA, recommendedRuntimeType={"gpu": "T4", "highMem": False})

    # Act A:看清單
    page.goto("/library.html")

    # Assert A
    expect(curated_row(page, QWEN_SHOWN).locator(".item-meta")).to_contain_text("H100")

    # Act B:打開 llama3.2:3b 的修改表單
    curated_row(page, LLAMA).get_by_role("button", name="修改").click()

    # Assert B
    expect(page.locator("#c-type")).to_be_visible()
    assert "H100" not in option_values(page, "#c-type")
    page.click("#c-cancel")

    # Act C:打開 qwen2.5 的修改表單,不改類型就送出
    curated_row(page, QWEN_SHOWN).get_by_role("button", name="修改").click()
    keep = page.locator("#c-type option", has_text="維持目前設定")

    # Assert C
    expect(keep).to_have_count(1)
    assert page.locator("#c-type").evaluate("el => el.selectedOptions[0].textContent") == "維持目前設定"
    assert "H100" not in option_values(page, "#c-type")
    with page.expect_response(lambda r: "/api/curated/" in r.url and r.request.method != "GET") as reply:
        page.click("#c-submit")
    assert reply.value.status == 200
    assert recommended_of(e2e_servers, QWEN_SHOWN) == {"gpu": "H100", "highMem": False}


# ---- 004 US5-AJ-05


def test_新增表單的建議類型沒有H100_也沒有維持目前設定(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange:沒有工作階段;qwen2.5 建議 H100
    curate(e2e_servers, QWEN, recommendedRuntimeType={"gpu": "H100", "highMem": False})
    page.goto("/library.html")
    expect(curated_row(page, QWEN_SHOWN)).to_be_visible()

    # Act
    page.click("#cur-add")
    expect(page.locator("#c-type")).to_be_visible()

    # Assert
    assert "H100" not in option_values(page, "#c-type")
    expect(page.locator("#c-type option", has_text="維持目前設定")).to_have_count(0)
