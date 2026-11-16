"""跨端點驗收:模型目錄讀不到時,看得到真正的原因(007 testplan.md § 2.2)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨)。
執行環境上的模型以 `ColabWorld.models` 鋪;遠端 Ollama 的 tags 以 `fakes.remote_ollama.list_local_models.raises(code)` 失敗、
以 `.side_effect(world._local_models)` 恢復,ps 是 `list_loaded_models`。
"""

import re
from typing import Any

from playwright.sync_api import BrowserContext, Locator, Page, expect

from e2e.test_004_us2_chat import complete_turn, end_session_in_other_tab
from e2e.test_us1_session import ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture

# contracts/ui.openapi.yaml § info.x-ollama-error-message:三個代碼固定的說明(照規格原句寫,不從程式碼取)
U = "連不到執行環境上的 Ollama,請確認工作階段仍在運作後再試。"
B = "執行環境上的 Ollama 回應無法解讀,請稍後再試。"
T = "執行環境上的 Ollama 在時限內沒有回應,請稍後再試。"

# testplan.md § 2.2 節首說明:執行環境上的三個模型(名稱 → (大小, 是否已載入))
MODELS = {
    "qwen2.5:0.5b": (397_821_319, True),
    "llama3.2:3b": (2_019_393_189, False),
    "qwen2.5:7b": (4_683_087_332, False),
}
WITHIN = 5_000  # 「5 秒內」(毫秒)


def ready_with_models(page: Page, world: ColabWorld) -> None:
    """工作階段由工作階段頁開到就緒,執行環境上有節首說明的三個模型。"""
    open_to_ready(page)
    world.models.update(MODELS)


def row(page: Page, name: str) -> Locator:
    """目錄裡名稱恰好是 `name` 的那一列。"""
    return page.locator("#catalog li").filter(has=page.locator(".item-name", has_text=re.compile(f"^{re.escape(name)}$")))


def open_catalog(page: Page, world: ColabWorld) -> None:
    """工作階段就緒、打開模型頁,等到目錄列出 3 列。"""
    ready_with_models(page, world)
    page.goto("/models.html")
    expect(page.locator("#catalog li")).to_have_count(3)


# ---------------------------------------------------------------- US1-AJ-01


def test_讀不到已下載清單時_模型頁說明連不到的原因而不顯示成空目錄(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    ready_with_models(page, world)
    fakes.remote_ollama.list_local_models.raises("OLLAMA_UNREACHABLE")

    # Act
    page.goto("/models.html")

    # Assert
    expect(page.locator('[data-state="unavailable"]')).to_be_visible(timeout=WITHIN)
    expect(page.locator("#un-message")).to_have_text(U)
    expect(page.locator("#un-code")).to_have_text("OLLAMA_UNREACHABLE")
    expect(page.locator('[data-state="empty"]')).to_be_hidden()
    expect(page.locator('[data-state="loading"]')).to_be_hidden()
    assert "還沒有模型" not in page.locator("main").inner_text()
    expect(page.locator("#catalog li")).to_have_count(0)


# ---------------------------------------------------------------- US1-AJ-02


def test_讀不到已載入清單時_模型頁說明無法解讀的原因而不列出半套目錄(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:tags 照常回 3 個模型,只有 ps 失敗
    ready_with_models(page, world)
    fakes.remote_ollama.list_loaded_models.raises("OLLAMA_BAD_RESPONSE")

    # Act
    page.goto("/models.html")

    # Assert
    expect(page.locator('[data-state="unavailable"]')).to_be_visible(timeout=WITHIN)
    expect(page.locator("#un-message")).to_have_text(B)
    expect(page.locator("#un-code")).to_have_text("OLLAMA_BAD_RESPONSE")
    expect(page.locator("#catalog li")).to_have_count(0)
    shown = page.locator("main").inner_text()
    assert [name for name in MODELS if name in shown] == []
    expect(page.locator('[data-state="empty"]')).to_be_hidden()


# ---------------------------------------------------------------- US1-AJ-03


def test_讀已下載清單逾時時_模型頁說明沒有回應的原因而不顯示成空目錄(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    ready_with_models(page, world)
    fakes.remote_ollama.list_local_models.raises("OLLAMA_TIMEOUT")

    # Act
    page.goto("/models.html")

    # Assert
    expect(page.locator('[data-state="unavailable"]')).to_be_visible(timeout=WITHIN)
    expect(page.locator("#un-message")).to_have_text(T)
    expect(page.locator("#un-code")).to_have_text("OLLAMA_TIMEOUT")
    expect(page.locator('[data-state="empty"]')).to_be_hidden()


# ---------------------------------------------------------------- US1-AJ-04


def test_遠端恢復後按重新讀取_模型頁列出目錄而不必重開工作階段(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    ready_with_models(page, world)
    fakes.remote_ollama.list_local_models.raises("OLLAMA_UNREACHABLE")
    page.goto("/models.html")
    expect(page.locator('[data-state="unavailable"]')).to_be_visible(timeout=WITHIN)
    fakes.remote_ollama.list_local_models.side_effect(world._local_models)

    # Act
    page.click("#reload")

    # Assert
    expect(page.locator('[data-state="normal"]')).to_be_visible(timeout=WITHIN)
    expect(page.locator("#catalog li")).to_have_count(3)
    expect(page.locator('[data-state="unavailable"]')).to_be_hidden()
    assert fakes.colab.create_session.call_count == 1


# ---------------------------------------------------------------- US1-AJ-05


def test_遠端恢復後讀到零個模型_重新讀取顯示空目錄而不是讀不到(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    ready_with_models(page, world)
    fakes.remote_ollama.list_local_models.raises("OLLAMA_TIMEOUT")
    page.goto("/models.html")
    expect(page.locator('[data-state="unavailable"]')).to_be_visible(timeout=WITHIN)
    world.models.clear()
    fakes.remote_ollama.list_local_models.side_effect(world._local_models)

    # Act
    page.click("#reload")

    # Assert
    expect(page.locator('[data-state="empty"]')).to_be_visible(timeout=WITHIN)
    expect(page.locator('[data-state="unavailable"]')).to_be_hidden()


# ---------------------------------------------------------------- US1-AJ-06


def test_預先載入前讀不到目錄_說明沒有預先載入的原因而其他模型照原狀顯示(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_catalog(page, world)
    fakes.remote_ollama.list_local_models.raises("OLLAMA_UNREACHABLE")

    # Act
    row(page, "llama3.2:3b").get_by_role("button", name="預先載入").click()

    # Assert
    expect(page.locator('[data-state="preload-unavailable"]')).to_be_visible(timeout=WITHIN)
    expect(page.locator("#pu-name")).to_have_text("llama3.2:3b")
    expect(page.locator("#pu-message")).to_have_text(U)
    expect(page.locator("#pu-code")).to_have_text("OLLAMA_UNREACHABLE")
    expect(page.locator("#catalog li")).to_have_count(3)
    expect(row(page, "llama3.2:3b").get_by_role("button", name="預先載入")).to_be_visible()
    expect(row(page, "llama3.2:3b")).not_to_contain_text("載入中")
    expect(row(page, "qwen2.5:0.5b")).to_contain_text("已載入")
    expect(row(page, "qwen2.5:7b").get_by_role("button", name="預先載入")).to_be_visible()
    expect(page.locator('[data-state="unavailable"]')).to_be_hidden()
    assert fakes.remote_ollama.preload.call_count == 0


# ---------------------------------------------------------------- US1-AJ-07


def test_預先載入逾時的說明關掉後_遠端恢復再按一次就受理(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:第二次受理後的載入停在閘門前,畫面才看得到「載入中」
    open_catalog(page, world)
    loading = fakes.remote_ollama.preload.gate()
    fakes.remote_ollama.list_local_models.raises("OLLAMA_TIMEOUT")
    note = page.locator('[data-state="preload-unavailable"]')

    # Act 1:讀不到目錄時按「預先載入」
    row(page, "qwen2.5:7b").get_by_role("button", name="預先載入").click()

    # Assert 1
    expect(note).to_be_visible(timeout=WITHIN)
    expect(page.locator("#pu-code")).to_have_text("OLLAMA_TIMEOUT")
    expect(page.locator("#pu-message")).to_have_text(T)

    # Act 2:關閉
    page.click("#pu-close")

    # Assert 2
    expect(note).to_be_hidden()
    expect(page.locator("#catalog li")).to_have_count(3)

    # Act 3:遠端恢復後再按一次
    fakes.remote_ollama.list_local_models.side_effect(world._local_models)
    row(page, "qwen2.5:7b").get_by_role("button", name="預先載入").click()

    # Assert 3
    expect(row(page, "qwen2.5:7b")).to_contain_text("載入中", timeout=WITHIN)
    expect(note).to_be_hidden()
    loading.wait_entered()
    assert [c.kwargs["model"] for c in fakes.remote_ollama.preload.calls] == ["qwen2.5:7b"]
    loading.release()


# ---------------------------------------------------------------- US1-AJ-08


def test_對話頁讀不到目錄時_說明讀不到的原因而不說成沒有工作階段且不能送出(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    ready_with_models(page, world)
    fakes.remote_ollama.list_local_models.raises("OLLAMA_BAD_RESPONSE")

    # Act
    page.goto("/chat.html")

    # Assert
    unavailable = page.locator('[data-state="chat-unavailable"]')
    expect(unavailable).to_be_visible(timeout=WITHIN)
    expect(unavailable.locator("#un-message")).to_have_text(B)
    expect(unavailable.locator("#un-code")).to_have_text("OLLAMA_BAD_RESPONSE")
    expect(page.locator('[data-state="chat-no-session"]')).to_be_hidden()
    expect(page.locator('[data-state="chat-no-models"]')).to_be_hidden()
    expect(page.locator("#send")).to_be_disabled()
    expect(page.locator("#input")).to_be_disabled()


# ---------------------------------------------------------------- US1-AJ-09


def test_重新整理後讀不到目錄_保存的對話照常顯示而不被清除(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:一則完成的對話,之後 tags 逾時
    ready_with_models(page, world)
    page.goto("/chat.html")
    expect(page.locator('[data-state="chat-ready"]')).to_be_visible()
    page.select_option("#model", "qwen2.5:0.5b")
    complete_turn(page, fakes, "你好")
    fakes.remote_ollama.list_local_models.raises("OLLAMA_TIMEOUT")

    # Act
    page.reload()

    # Assert
    unavailable = page.locator('[data-state="chat-unavailable"]')
    expect(unavailable).to_be_visible(timeout=WITHIN)
    expect(unavailable.locator("#un-code")).to_have_text("OLLAMA_TIMEOUT")
    expect(page.locator("#log .msg-user")).to_have_count(1)
    expect(page.locator("#log .msg-user")).to_have_text("你好")
    expect(page.locator("#log .msg-bot")).to_have_count(1)
    expect(page.locator("#log .msg-bot")).to_contain_text("一二三四五六")
    expect(page.locator('[data-state="keep-on"]')).to_be_visible()
    expect(page.locator('[data-state="keep-cleared"]')).to_be_hidden()
    kept = page.evaluate("() => JSON.parse(localStorage.getItem('cgb.chat.v1'))")
    assert len(kept["messages"]) == 2


# ---------------------------------------------------------------- US1-AJ-10


def test_讀不到目錄時工作階段被結束_兩頁不重新整理就改說沒有就緒的工作階段(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:分頁 A 是模型頁、分頁 B 是對話頁,兩頁都已顯示讀不到目錄
    ready_with_models(page, world)
    fakes.remote_ollama.list_local_models.raises("OLLAMA_UNREACHABLE")
    models_tab = page
    models_tab.goto("/models.html")
    chat_tab = context.new_page()
    chat_tab.goto("/chat.html")
    expect(models_tab.locator('[data-state="unavailable"]')).to_be_visible(timeout=WITHIN)
    expect(chat_tab.locator('[data-state="chat-unavailable"]')).to_be_visible(timeout=WITHIN)

    # Act:分頁 C 在工作階段頁按「結束」並確認
    end_session_in_other_tab(context)

    # Assert
    expect(models_tab.locator('[data-state="no-session"]')).to_be_visible(timeout=WITHIN)
    expect(models_tab.locator('[data-state="unavailable"]')).to_be_hidden()
    expect(chat_tab.locator('[data-state="chat-no-session"]')).to_be_visible(timeout=WITHIN)
    expect(chat_tab.locator('[data-state="chat-unavailable"]')).to_be_hidden()
