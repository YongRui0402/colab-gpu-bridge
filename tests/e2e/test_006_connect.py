"""006 跨端點驗收:連線設定頁(testplan.md § 2.4 US1-AJ)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨)。
預設資料:替身回報 T4、套用 context 4096(`ColabWorld` 預設的 `T4_STARTED`);執行環境上的模型是
`qwen2.5-coder:7b` 與 `qwen2.5:3b`;相容端點對外的 port 是 11436(測試的 `make_app` 預設)。
瀏覽器連的是 `http://127.0.0.1:8781`,所以片段的 `{{host}}` 要換成 `127.0.0.1`。
"""

import json
import re
from typing import Any

from playwright.sync_api import BrowserContext, Page, expect

from e2e.test_005_us2_overrides import open_screen, press_open
from e2e.test_locale import SIMPLIFIED_OR_MAINLAND
from e2e.test_us1_session import CJK, ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture
from integration.test_api_models import QWEN_7B_BYTES, QWEN_SMALL_BYTES
from integration.test_api_tuning import GIB, applied, started

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


# ---- 006 US2-AJ-01


def test_pi_分頁有_models_json_與_settings_json_兩段各能複製_位址換好主機名稱並寫明放哪裡(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange
    ready_with_default_models(page, world)
    page.goto("/connect.html")
    shown = snippets(page)
    expect(shown.locator('[data-code="opencode"]')).to_contain_text("http://127.0.0.1:11436/v1")

    # Act
    shown.locator('.tab[data-tab="pi"]').click()

    # Assert
    pi = shown.locator('[data-panel="pi"]')
    expect(pi).to_be_visible()
    # 則1:models.json 與 settings.json 兩段都看得到,各有自己的「複製」
    heads = pi.locator(".snippet:visible .snippet-head")
    expect(heads.locator("h3")).to_have_text(["models.json", "settings.json"])
    for head in heads.all():
        expect(head.locator("button")).to_have_text("複製")
    expect(pi.locator('.code[data-code="pi-settings"]')).to_be_visible()
    # 則2:models.json 的 baseUrl 換成目前網址的主機名稱
    pi_models = json.loads(pi.locator('[data-code="pi-models"]').inner_text())
    assert pi_models["providers"]["cgb"]["baseUrl"] == "http://127.0.0.1:11436/v1"
    # 則3:使用方式寫著兩個檔放哪裡,以及怎麼選用模型
    howto = pi.locator(".howto")
    expect(howto).to_contain_text("~/.pi/agent/models.json")
    expect(howto).to_contain_text("~/.pi/agent/settings.json")
    expect(howto).to_contain_text(f"pi --model cgb/{CODER_7B}")


# ---- 006 US2-AJ-02


def test_按_settings_json_那段的複製後剪貼簿的內容和畫面上的_settings_json_片段完全相同(page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    ready_with_default_models(page, world)
    page.goto("/connect.html")
    shown = snippets(page)
    expect(shown.locator('[data-code="opencode"]')).to_contain_text("http://127.0.0.1:11436/v1")
    shown.locator('.tab[data-tab="pi"]').click()
    settings = shown.locator('[data-code="pi-settings"]')
    expect(settings).to_contain_text("reserveTokens")
    button = shown.locator('[data-copy="pi-settings"]')

    # Act
    button.click()

    # Assert
    expect(button).to_have_text("已複製")
    copied = page.evaluate("navigator.clipboard.readText()")
    assert copied == settings.text_content()


# ---- 006 US3-AJ-01


def test_context_太小時提醒目前值_建議值與兩種改法並連回首頁的_Ollama_設定_片段照樣可以複製(page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange:預設資料,15 GiB 的 T4 套用 context 4096
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    ready_with_default_models(page, world)

    # Act
    page.goto("/connect.html")

    # Assert
    shown = snippets(page)
    notice = shown.locator('[data-part="low-notice"]')
    # 則1:提醒寫著目前 4096、建議 32768(依顯示記憶體估),以及開啟前與開著時的兩種改法,都連回首頁的 Ollama 設定
    expect(notice).to_be_visible()
    expect(notice).to_contain_text("目前套用的 context 是 4,096")
    expect(notice).to_contain_text("建議值:32,768")
    expect(notice).to_contain_text("顯示記憶體 15 GB")
    ways = notice.locator(".note-list li")
    expect(ways).to_have_count(2)
    expect(ways.nth(0)).to_contain_text(re.compile(r"開啟前在\s*Ollama 設定\s*填 context 長度"))
    expect(ways.nth(1)).to_contain_text("套用並重啟 Ollama")
    links = notice.locator('a[href="index.html#t-card"]')
    expect(links).to_have_count(2)
    # 則2:片段照樣顯示,按複製後剪貼簿的內容和畫面上的片段完全相同
    code = shown.locator('[data-code="opencode"]')
    expect(code).to_contain_text("http://127.0.0.1:11436/v1")
    button = shown.locator('[data-copy="opencode"]')
    button.click()
    expect(button).to_have_text("已複製")
    assert page.evaluate("navigator.clipboard.readText()") == code.text_content()
    # 回首頁的連結連得到工作階段頁的 Ollama 設定(005 已做好的畫面,plan.md Q26)
    links.first.click()
    expect(page).to_have_url("http://127.0.0.1:8781/index.html#t-card")
    expect(page.locator("#t-card h2")).to_have_text("Ollama 設定")
    expect(page.locator("#t-card")).to_be_visible()


# ---- 006 US3-AJ-02


def t4_start(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """15 GiB 的 T4:填了 context 長度時照覆蓋值套用、標手動,其他照級距(平行 2、同時載入 1)。"""
    context_length = kwargs["overrides"]["contextLength"]
    tuning = applied(2, context_length, 1, ("auto", "manual", "auto"))
    return started(15 * GIB, tuning, gpu_name="Tesla T4", system_bytes=13_605_855_232)


def test_以覆蓋值_context_32768_開到就緒時沒有提醒區塊(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:開啟前在 Ollama 設定填 context 32768
    fakes.colab.start_ollama.side_effect(t4_start)
    screen = open_screen(page)
    screen.locator(".tuning-block > summary").click()
    screen.locator('input[data-field="contextLength"]').fill("32768")
    press_open(screen)
    expect(page.locator('[data-state="ready"]')).to_be_visible(timeout=10_000)
    world.models[CODER_7B] = (QWEN_7B_BYTES, False)
    world.models[QWEN_3B] = (QWEN_SMALL_BYTES, False)

    # Act
    page.goto("/connect.html")

    # Assert
    shown = snippets(page)
    expect(shown.locator('[data-field="context"]')).to_have_text("32,768")
    # 則1:沒有提醒區塊
    expect(shown.locator(".notice:visible")).to_have_count(0)


# ---- 006 US3-AJ-03


def test_讀不到目前的_Ollama_設定時說明片段不帶_context_長度_pi_分頁沒有_settings_json(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:005 的 ollama.status 是 unknown(遠端 Ollama 已在執行、讀不到設定)
    fakes.colab.start_ollama.side_effect(
        lambda *a, **k: started(15 * GIB, None, gpu_name="Tesla T4", system_bytes=13_605_855_232, already_running=True)
    )
    ready_with_default_models(page, world)

    # Act
    page.goto("/connect.html")

    # Assert
    shown = snippets(page)
    # 則1:看到讀不到設定的說明,目前 context 寫「讀不到」而不是 null
    unknown = shown.locator('[data-part="unknown-notice"]')
    expect(unknown).to_be_visible()
    expect(unknown).to_contain_text("讀不到目前的 Ollama 設定,片段不帶 context 長度")
    expect(shown.locator('[data-field="context"]')).to_have_text("讀不到")
    expect(shown.locator('[data-part="low-notice"]')).to_be_hidden()
    # 則2:pi 分頁只有 models.json 一段,使用方式不提 settings.json
    shown.locator('.tab[data-tab="pi"]').click()
    pi = shown.locator('[data-panel="pi"]')
    expect(pi).to_be_visible()
    expect(pi.locator(".snippet:visible .snippet-head h3")).to_have_text(["models.json"])
    expect(pi.locator('.code[data-code="pi-settings"]')).to_be_hidden()
    expect(pi.locator(".howto")).not_to_contain_text("settings.json", use_inner_text=True)
