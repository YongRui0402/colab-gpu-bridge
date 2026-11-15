"""005 跨端點驗收:工作階段頁的 Ollama 設定卡與紀錄頁的設定明細(testplan.md § US1-AJ)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨)。
替身回報的 `OllamaStarted` 就是遠端量到的硬體與套用的設定;畫面只照它顯示,不查 GPU 類型的表。
"""

from typing import Any

from playwright.sync_api import Page, expect

from e2e.test_us1_session import ColabWorld, world  # noqa: F401 - `world` 是 fixture
from integration.test_api_tuning import GIB, applied, started

# 替身回報 A100:顯示記憶體 40960 MiB、系統記憶體 83 GiB(testplan.md § US1-AJ-01 的假如)
A100_40G = started(40 * GIB, applied(8, 8192, 2), gpu_name="NVIDIA A100-SXM4-40GB", system_bytes=83 * GIB)

# `nvidia-smi` 讀不到顯示記憶體:三項設定都不帶,用 Ollama 預設值(FR-003)
T4_NO_VRAM = started(
    None,
    applied(None, None, None, ("ollama_default",) * 3, fa="ollama_default"),
    gpu_name=None,
    system_bytes=13_605_855_232,
)


def open_from_page(page: Page, gpu: str) -> None:
    """使用者在開啟畫面選類型、按開啟,等到就緒。"""
    page.goto("/")
    page.locator(f'[data-state="normal"] input[value="{gpu}"]').check()
    page.locator("#open").click()
    expect(page.locator('[data-state="ready"]')).to_be_visible(timeout=10_000)


# ---- 005 US1-AJ-01


def test_設定卡顯示量到的顯示記憶體算出的三項設定_都標自動(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    fakes.colab.start_ollama.side_effect(lambda *a, **k: A100_40G)

    # Act
    open_from_page(page, "A100")

    # Assert
    expect(page.locator("#t-summary")).to_have_text("顯示記憶體 40 GB · 平行 8 · context 8192 · 同時載入 2 個模型(自動)")
    expect(page.locator("#t-hardware")).to_contain_text("顯示記憶體 40 GB")
    expect(page.locator("#t-hardware")).to_contain_text("系統記憶體 83 GB")
    rows = page.locator("#t-rows > tr")
    expect(rows).to_have_count(5)
    for i, value in enumerate(["8", "8,192 tokens", "2 個"]):
        expect(rows.nth(i).locator("td").nth(1)).to_have_text(value)
        expect(rows.nth(i).locator("td").nth(2)).to_have_text("自動")
    # 則2:flash attention 與 KV cache 固定開啟,卡上沒有可修改的欄位
    expect(rows.nth(3).locator("td").nth(1)).to_have_text("開啟")
    expect(rows.nth(3).locator("td").nth(2)).to_contain_text("固定")
    expect(rows.nth(4).locator("td").nth(1)).to_have_text("q8_0")
    expect(rows.nth(4).locator("td").nth(2)).to_contain_text("固定")
    expect(page.locator("#t-card input, #t-card select")).to_have_count(0)


# ---- 005 US1-AJ-02


def test_讀不到顯示記憶體時照常就緒_設定卡說明用_Ollama_預設值(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    fakes.colab.start_ollama.side_effect(lambda *a, **k: T4_NO_VRAM)

    # Act
    open_from_page(page, "T4")

    # Assert
    expect(page.locator('[data-state="ready-no-vram"]')).to_be_visible()
    expect(page.locator('[data-state="ready-no-vram"]')).to_contain_text("讀不到顯示記憶體,使用 Ollama 預設值")
    expect(page.locator("#session-pill")).to_contain_text("就緒")


# ---- 005 US1-AJ-03


def test_紀錄頁明細列出開啟那一筆_Ollama_設定(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:US1-AJ-01 的工作階段已就緒
    fakes.colab.start_ollama.side_effect(lambda *a, **k: A100_40G)
    open_from_page(page, "A100")
    page.goto("/history.html")

    # Act
    page.locator("#rows > tr").first.click()

    # Assert
    detail = page.locator('[data-state="tuning-log"]')
    expect(detail).to_be_visible()
    logs = detail.locator("tbody > tr")
    expect(logs).to_have_count(1)
    cells = logs.first.locator("td")
    expect(cells.nth(0)).not_to_be_empty()
    expect(cells.nth(1)).to_have_text("開啟")
    expect(cells.nth(3)).to_contain_text("顯示記憶體 40 GB")
    expect(cells.nth(4)).to_have_text("8 自動")
    expect(cells.nth(5)).to_have_text("8,192 自動")
    expect(cells.nth(6)).to_have_text("2 自動")
    expect(cells.nth(9)).to_contain_text("成功")
