"""006 跨端點驗收:連線設定頁(testplan.md § 2.4 US1-AJ)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨)。
預設資料:替身回報 T4、套用 context 4096(`ColabWorld` 預設的 `T4_STARTED`);執行環境上的模型是
`qwen2.5-coder:7b` 與 `qwen2.5:3b`;相容端點對外的 port 是 11436(測試的 `make_app` 預設)。
瀏覽器連的是 `http://127.0.0.1:8781`,所以片段的 `{{host}}` 要換成 `127.0.0.1`。
"""

import json
from typing import Any

from playwright.sync_api import BrowserContext, Page, expect

from e2e.test_locale import SIMPLIFIED_OR_MAINLAND
from e2e.test_us1_session import CJK, ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture
from integration.test_api_models import QWEN_7B_BYTES, QWEN_SMALL_BYTES

CODER_7B = "qwen2.5-coder:7b"
QWEN_3B = "qwen2.5:3b"


def snippets(page: Page) -> Any:
    """畫面上正在顯示的片段區塊(context 正常或偏小時都是同一份片段,只差提醒)。"""
    return page.locator('[data-render="snippets"]:visible')


def ready_with_default_models(page: Page, world: ColabWorld) -> None:
    """以預設類型開到就緒,執行環境上放好預設資料的兩個模型。"""
    open_to_ready(page)
    world.models[CODER_7B] = (QWEN_7B_BYTES, False)
    world.models[QWEN_3B] = (QWEN_SMALL_BYTES, False)


# ---- 006 US1-AJ-01


def test_從導覽列進連線設定_opencode_分頁的片段換好主機名稱並列出模型(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange
    ready_with_default_models(page, world)
    entry = page.locator(".topbar nav a", has_text="連線設定")
    expect(entry).to_be_visible()

    # Act
    entry.click()

    # Assert
    # 則1:進到連線設定頁,opencode 分頁被選取
    expect(page).to_have_url("http://127.0.0.1:8781/connect.html")
    shown = snippets(page)
    expect(shown).to_have_count(1)
    expect(shown.locator('.tab[data-tab="opencode"]')).to_have_attribute("aria-selected", "true")
    # 則2、則3:片段的位址換成目前網址的主機名稱,列出目錄裡的兩個模型
    code = shown.locator('[data-code="opencode"]')
    expect(code).to_contain_text("http://127.0.0.1:11436/v1")
    cgb = json.loads(code.inner_text())["provider"]["cgb"]
    assert cgb["options"]["baseURL"] == "http://127.0.0.1:11436/v1"
    assert list(cgb["models"]) == [CODER_7B, QWEN_3B]
    howto = shown.locator('[data-panel="opencode"] .howto')
    expect(howto).to_contain_text("opencode.json")
    expect(howto).to_contain_text(f"opencode -m cgb/{CODER_7B}")


# ---- 006 US1-AJ-02


def test_按複製後剪貼簿的內容和畫面上換好主機名稱的片段完全相同(page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    ready_with_default_models(page, world)
    page.goto("/connect.html")
    shown = snippets(page)
    expect(shown.locator('[data-code="opencode"]')).to_contain_text("http://127.0.0.1:11436/v1")
    button = shown.locator('[data-copy="opencode"]')

    # Act
    button.click()

    # Assert
    expect(button).to_have_text("已複製")
    copied = page.evaluate("navigator.clipboard.readText()")
    assert copied == shown.locator('[data-code="opencode"]').text_content()


# ---- 006 US1-AJ-03


def test_沒有開工作階段時說明原因並附回首頁的連結_不顯示片段(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange:沒有開工作階段

    # Act
    page.goto("/connect.html")

    # Assert
    no_session = page.locator('[data-state="no-session"]')
    expect(no_session).to_be_visible()
    expect(no_session).to_contain_text("目前沒有就緒的工作階段")
    expect(no_session.locator('a[href="index.html"]')).to_be_visible()
    expect(page.locator(".snippet:visible")).to_have_count(0)


# ---- 006 US1-AJ-04


def test_模型目錄是空的時說明先下載模型並附模型頁的連結_不顯示片段(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange:工作階段就緒,新開的執行環境上沒有模型
    open_to_ready(page)

    # Act
    page.goto("/connect.html")

    # Assert
    empty = page.locator('[data-state="empty-catalog"]')
    expect(empty).to_be_visible()
    expect(empty).to_contain_text("先到模型頁下載模型")
    expect(empty.locator('a[href="models.html"]')).to_be_visible()
    expect(page.locator(".snippet:visible")).to_have_count(0)


# ---- 006 US1-AJ-05

# 給人看的文字:標題、按鈕、事實的名稱、使用方式的每一步與提醒;分頁名稱與片段的標題(`models.json`)是工具與檔案本身的名字,不在這裡比對
PROSE = "[data-panel] > h3:visible, .btn:visible, .facts dt:visible, .howto li:visible, .notice strong:visible, .notice p:visible, .notice li:visible"


def prose_of(page: Page) -> tuple[str, list[str]]:
    """整頁看得到的文字去掉片段本身,以及每一段給人看的文字。"""
    text = page.locator("main").inner_text()
    for code in page.locator(".code:visible").all():
        text = text.replace(code.inner_text(), "")
    return text, page.locator(f"main :is({PROSE})").all_inner_texts()


def test_連線設定頁的說明都是繁體中文_片段的鍵名照原文(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange:預設資料,context 4096
    ready_with_default_models(page, world)
    page.goto("/connect.html")
    shown = snippets(page)
    expect(shown.locator('[data-code="opencode"]')).to_contain_text("http://127.0.0.1:11436/v1")
    pi_tab = shown.locator('.tab[data-tab="pi"]')

    # Act:依序看 opencode 分頁(含提醒)與 pi 分頁
    expect(shown.locator(".notice:visible")).to_contain_text("context 太小")
    opencode_view = prose_of(page)
    opencode = json.loads(shown.locator('[data-code="opencode"]').inner_text())
    expect(pi_tab).to_be_visible()
    pi_tab.click()
    expect(shown.locator('[data-panel="pi"]')).to_be_visible()
    pi_view = prose_of(page)
    pi_models = json.loads(shown.locator('[data-code="pi-models"]').inner_text())

    # Assert
    # 則1:分頁名稱照工具原名;其他給人看的每一段都有中文,整頁沒有簡體字與大陸用語
    assert shown.locator(".tab").all_inner_texts() == ["opencode", "pi"]
    for text, pieces in (opencode_view, pi_view):
        assert pieces, "畫面上找不到給人看的文字"
        assert [p for p in pieces if not CJK.search(p)] == []
        assert [word for word in SIMPLIFIED_OR_MAINLAND if word in text] == []
    assert "使用方式" in opencode_view[0] and "使用方式" in pi_view[0]
    # 則2:片段的鍵名照各工具的原文
    assert "limit" in opencode["provider"]["cgb"]["models"][CODER_7B]
    assert opencode["provider"]["cgb"]["options"]["baseURL"] == "http://127.0.0.1:11436/v1"
    assert pi_models["providers"]["cgb"]["baseUrl"] == "http://127.0.0.1:11436/v1"
