"""005 跨端點驗收:開啟畫面的「Ollama 設定」手動覆蓋與依 GPU 類型記住(testplan.md § US2-AJ)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨)。
替身的 `start_ollama` 照遠端腳本的「覆蓋值 > 級距 > 不帶」組出回報,所以畫面上的來源就是後端帶給遠端的覆蓋值。
"""

from typing import Any

import httpx
from playwright.sync_api import Page, expect

from e2e.test_us1_history import wait_for_state
from e2e.test_us1_session import ColabWorld, world  # noqa: F401 - `world` 是 fixture
from integration.test_api_tuning import GIB, started

KEYS = ("numParallel", "contextLength", "maxLoadedModels")
A100_TIER = (8, 8192, 2)


def a100_start(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """40 GiB 的 A100:填了的項目標手動,沒填的照級距標自動。"""
    overrides = kwargs["overrides"]
    tuning: dict[str, Any] = {
        key: {"value": overrides[key], "source": "manual"} if overrides[key] is not None else {"value": auto, "source": "auto"}
        for key, auto in zip(KEYS, A100_TIER, strict=True)
    }
    tuning["flashAttention"] = {"value": True, "source": "auto"}
    tuning["kvCacheType"] = {"value": "q8_0", "source": "auto"}
    return started(40 * GIB, tuning, gpu_name="NVIDIA A100-SXM4-40GB", system_bytes=83 * GIB)


def open_screen(page: Page) -> Any:
    """使用者看到的開啟畫面:沒有工作階段時是 `normal`,結束之後是 `ended`,都有類型選單與開啟按鈕。"""
    page.goto("/")
    screen = page.locator("main section:not([hidden])").filter(has=page.locator("[data-picker]"))
    expect(screen).to_have_count(1)
    return screen


def press_open(screen: Any) -> None:
    screen.get_by_role("button", name="開啟", exact=True).click()


def pick(screen: Any, gpu: str) -> None:
    screen.locator(f'input[value="{gpu}"]').check()


def field(screen: Any, key: str) -> Any:
    return screen.locator(f'input[data-field="{key}"]')


def expect_sources(page: Page, sources: list[str]) -> None:
    rows = page.locator("#t-rows > tr")
    for i, source in enumerate(sources):
        expect(rows.nth(i).locator("td").nth(2)).to_have_text(source)


def end_session(e2e_servers: Any) -> None:
    with httpx.Client(base_url=e2e_servers.ui_url) as client:
        client.delete("/api/session")
        wait_for_state(client, "ended")


def open_with_parallel_4(page: Page) -> None:
    screen = open_screen(page)
    pick(screen, "A100")
    screen.locator(".tuning-block > summary").click()
    field(screen, "numParallel").fill("4")
    press_open(screen)
    expect(page.locator('[data-state="ready"]')).to_be_visible(timeout=10_000)


# ---- 005 US2-AJ-01


def test_只填平行數開啟時它標手動_沒填的兩項照自動(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    fakes.colab.start_ollama.side_effect(a100_start)
    screen = open_screen(page)
    pick(screen, "A100")
    screen.locator(".tuning-block > summary").click()

    # Assert 則1:欄位旁顯示「留空 = 自動」
    expect(screen.locator(".tuning-fields .hint").first).to_contain_text("留空 = 自動")

    # Act
    field(screen, "numParallel").fill("4")
    page.locator("#open").click()

    # Assert 則2
    expect(page.locator('[data-state="ready"]')).to_be_visible(timeout=10_000)
    rows = page.locator("#t-rows > tr")
    expect(rows.nth(0).locator("td").nth(1)).to_have_text("4")
    expect(rows.nth(1).locator("td").nth(1)).to_have_text("8,192 tokens")
    expect(rows.nth(2).locator("td").nth(1)).to_have_text("2 個")
    expect_sources(page, ["手動", "自動", "自動"])


# ---- 005 US2-AJ-02


def test_選類型時預先填入那一種記住的值_換類型不殘留(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:US2-AJ-01 之後結束工作階段
    fakes.colab.start_ollama.side_effect(a100_start)
    open_with_parallel_4(page)
    end_session(e2e_servers)

    # Act
    screen = open_screen(page)
    pick(screen, "A100")

    # Assert
    expect(field(screen, "numParallel")).to_have_value("4")
    pick(screen, "T4")
    for key in KEYS:
        expect(field(screen, key)).to_have_value("")


# ---- 005 US2-AJ-03


def test_全部改回自動後開啟_三項都標自動_記住的值也清掉(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:A100 記住平行數 4
    fakes.colab.start_ollama.side_effect(a100_start)
    open_with_parallel_4(page)
    end_session(e2e_servers)
    screen = open_screen(page)
    pick(screen, "A100")
    expect(field(screen, "numParallel")).to_have_value("4")

    # Act
    screen.locator(".tuning-block > summary").click()
    screen.locator("[data-clear]").click()
    press_open(screen)

    # Assert 則1
    expect(page.locator('[data-state="ready"]')).to_be_visible(timeout=10_000)
    expect_sources(page, ["自動", "自動", "自動"])

    # Assert 則2:就緒後結束,再選 A100 時三個欄位都是空的
    end_session(e2e_servers)
    screen = open_screen(page)
    pick(screen, "A100")
    for key in KEYS:
        expect(field(screen, key)).to_have_value("")


# ---- 005 US2-AJ-04


def test_平行數超出範圍時說明範圍_不開啟也不記住(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    fakes.colab.start_ollama.side_effect(a100_start)
    screen = open_screen(page)
    pick(screen, "A100")
    screen.locator(".tuning-block > summary").click()
    field(screen, "numParallel").fill("64")

    # Act
    page.locator("#open").click()

    # Assert 則1
    expect(page.locator("#invalid-note")).to_be_visible()
    expect(page.locator("#invalid-note")).to_contain_text("1~32")
    # 則2:沒有開出工作階段
    expect(screen).to_be_visible()
    expect(page.locator("#session-pill")).to_have_text("未開啟")
    assert fakes.colab.create_session.call_count == 0
    # 則3:再選 A100 時平行數不是 64
    page.goto("/")
    screen = open_screen(page)
    pick(screen, "A100")
    expect(field(screen, "numParallel")).not_to_have_value("64")


# ---- 005 US2-AJ-02(變更類型)


def open_t4_ready(page: Page) -> None:
    screen = open_screen(page)
    screen.locator(".tuning-block > summary").click()
    field(screen, "numParallel").fill("4")
    press_open(screen)
    expect(page.locator('[data-state="ready"]')).to_be_visible(timeout=10_000)


def test_變更類型的確認頁預先填入目標類型記住的值_不沿用目前類型的欄位(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:L4 記住平行數 8,再以平行數 4 開 T4
    fakes.colab.start_ollama.side_effect(a100_start)
    screen = open_screen(page)
    pick(screen, "L4")
    screen.locator(".tuning-block > summary").click()
    field(screen, "numParallel").fill("8")
    press_open(screen)
    expect(page.locator('[data-state="ready"]')).to_be_visible(timeout=10_000)
    end_session(e2e_servers)
    page.goto("/")
    open_t4_ready(page)

    # Act:按「變更類型」,不另點類型選項
    page.locator('[data-state="ready"]').get_by_role("button", name="變更類型").click()

    # Assert:預選的 L4 欄位是它記住的 8,不是 T4 的 4
    confirm = page.locator('[data-state="confirm-switch"]')
    expect(confirm.locator('input[type="radio"][value="L4"]')).to_be_checked()
    expect(field(confirm, "numParallel")).to_have_value("8")


# ---- 005 FR-017(變更類型)


def test_變更類型的平行數超出範圍時留在確認頁說明範圍_原工作階段不受影響(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    fakes.colab.start_ollama.side_effect(a100_start)
    open_t4_ready(page)
    page.locator('[data-state="ready"]').get_by_role("button", name="變更類型").click()
    confirm = page.locator('[data-state="confirm-switch"]')
    # 設定區塊的展開狀態會沿用(開 T4 時已展開),沒展開才點,免得點了反而收起來
    if not confirm.locator(".tuning-block").evaluate("d => d.open"):
        confirm.locator(".tuning-block > summary").click()
    field(confirm, "numParallel").fill("64")

    # Act
    page.click("#switch")

    # Assert:留在確認頁、保留輸入、說明 1~32
    expect(confirm).to_be_visible()
    expect(field(confirm, "numParallel")).to_have_value("64")
    expect(page.locator("#switch-invalid-note")).to_be_visible()
    expect(page.locator("#switch-invalid-note")).to_contain_text("1~32")
    # 沒有重開:原本的工作階段還在
    page.goto("/")
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    assert fakes.colab.create_session.call_count == 1
