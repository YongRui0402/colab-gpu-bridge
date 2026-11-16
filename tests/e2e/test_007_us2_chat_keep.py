"""跨端點驗收:對話保留在瀏覽器裡,工作階段結束就清除(007 testplan.md § 3.2)。

接縫:瀏覽器畫面與 `localStorage` 的 `cgb.chat.v1` 接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身
(testplan.md § 接縫的取捨)。同一個 browser context 以 `context.new_page()` 開多個分頁。
「兩問兩答」指送出「你好」收到 `一二三` + `DONE`、再送出「再說一次」收到 `四五六` + `DONE`;
「結束後 5 秒」從 `GET /api/session` 輪詢到結束狀態(或 `name` 變了)的那一刻起算(plan.md Q24)。
"""

import json
import time
from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import BrowserContext, Page, expect

from e2e.test_004_us2_chat import (  # noqa: F401 - 後面的案例沿用
    DONE,
    LLAMA,
    QWEN,
    assert_traditional_chinese,
    chat_requests,
    chunk,
    complete_turn,
    end_session_in_other_tab,
    open_chat,
    replies,
    send,
    start_hanging_turn,
    with_models,
)
from cgb.adapters.errors import AdapterError
from e2e.test_004_us4_hf import api
from e2e.test_us1_session import ColabWorld, open_to_ready, restart_backend, wait_until, world  # noqa: F401 - `world` 是 fixture
from e2e.test_us4_usage import advance_clocks, sync_browser_clock  # noqa: F401 - 後面的案例沿用
from fakes import NdjsonReply

TWO_ROUNDS = ["你好", "一二三", "再說一次", "四五六"]


def saved(page: Page) -> dict[str, Any] | None:
    """`localStorage.getItem("cgb.chat.v1")` 解析成 dict;沒有保存時是 None。"""
    raw = page.evaluate("() => localStorage.getItem('cgb.chat.v1')")
    return None if raw is None else json.loads(raw)


def reply_with(fakes: Any, text: str) -> None:
    """替身下一次 `POST /api/chat` 逐字回 `text`,再送 `DONE`。"""
    fakes.server.add("POST", "/api/chat", NdjsonReply([*(chunk(c) for c in text), DONE]), times=1)


def finish_round(page: Page, fakes: Any, text: str, answer: str) -> None:
    """送出 `text`,替身回 `answer` + `DONE`,等到這則回覆完成。"""
    reply_with(fakes, answer)
    send(page, text)
    expect(replies(page).last.locator(".content")).to_have_text(answer)
    expect(page.locator('[data-state="turn-streaming"]')).to_be_hidden()


def two_rounds(page: Page, fakes: Any) -> None:
    """節首的「兩問兩答」。"""
    finish_round(page, fakes, "你好", "一二三")
    finish_round(page, fakes, "再說一次", "四五六")


def expect_two_rounds(page: Page) -> None:
    """`#log .msg` 依序是兩問兩答的 4 則。"""
    expect(page.locator("#log .msg")).to_have_count(4)
    expect(page.locator("#log .msg")).to_contain_text(TWO_ROUNDS)


def wait_session(e2e_servers: Any, pred: Callable[[dict[str, Any]], bool], timeout: float = 10.0) -> float:
    """以 `GET /api/session` 輪詢到 `pred` 成立,回傳那一刻(`time.monotonic()`),當「結束後 5 秒」的起點。"""
    deadline = time.monotonic() + timeout
    while True:
        session = api(e2e_servers, "GET", "/session").json()
        if pred(session):
            return time.monotonic()
        if time.monotonic() > deadline:
            raise AssertionError(f"等了 {timeout} 秒,工作階段仍是 {session}")
        time.sleep(0.05)


# ---------------------------------------------------------------- US2-AJ-01


def test_重新整理後對話依原順序還原_選的模型與回覆的速度都還在(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:改選預設以外的那一個模型 M,兩問兩答
    open_chat(page, world, QWEN, LLAMA)
    chosen = LLAMA if page.locator("#model").input_value() == QWEN else QWEN
    page.select_option("#model", chosen)
    two_rounds(page, fakes)

    # Act
    page.reload()

    # Assert
    expect_two_rounds(page)
    expect(page.locator("#model")).to_have_value(chosen)
    expect(replies(page).nth(1).locator(".msg-foot")).to_contain_text("tokens/s")


# ---------------------------------------------------------------- US2-AJ-02


def via_models_page(page: Page) -> None:
    """點頁首「模型」,等模型頁的目錄出現,再點頁首「對話」回來。"""
    page.locator("header nav").get_by_role("link", name="模型", exact=True).click()
    expect(page.locator("#catalog li").first).to_be_visible()
    page.locator("header nav").get_by_role("link", name="對話", exact=True).click()
    expect(page.locator('[data-state="chat-ready"]')).to_be_visible()


def test_切到模型頁再回來_對話依原順序還原(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)

    # Act
    via_models_page(page)

    # Assert
    expect_two_rounds(page)


# ---------------------------------------------------------------- US2-AJ-03


def test_另開分頁打開對話頁_對話依原順序還原(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:分頁 A 兩問兩答
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)

    # Act
    other = context.new_page()
    other.goto("/chat.html")

    # Assert
    expect_two_rounds(other)


# ---------------------------------------------------------------- US2-AJ-04


def come_back(page: Page, context: BrowserContext, way: str) -> Page:
    """照 `way` 離開再回到對話頁,回傳回來之後的那個分頁。"""
    if way == "重新整理":
        page.reload()
        return page
    if way == "切到模型頁再回來":
        via_models_page(page)
        return page
    other = context.new_page()
    other.goto("/chat.html")
    return other


def is_chat_post(request: Any) -> bool:
    return request.method == "POST" and request.url.endswith("/api/chat")


@pytest.mark.parametrize("way", ["重新整理", "切到模型頁再回來", "另開分頁"])
def test_回到對話頁後送出_帶上前面每一輪(
    way: str, page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)
    back = come_back(page, context, way)
    expect_two_rounds(back)
    reply_with(fakes, "七八九")

    # Act
    with back.expect_request(is_chat_post) as caught:
        send(back, "第三則")

    # Assert
    sent = [(m["role"], m["content"]) for m in caught.value.post_data_json["messages"]]
    assert sent == [("user", "你好"), ("assistant", "一二三"), ("user", "再說一次"), ("assistant", "四五六"), ("user", "第三則")]
    expect(replies(back).last.locator(".content")).to_have_text("七八九")


# ---------------------------------------------------------------- US2-AJ-05

LEFT = "中斷:離開頁面時這則回覆還沒有完成"


def reload_mid_reply(page: Page, fakes: Any) -> None:
    """送出「你好」,替身回「一」「二」後停住;畫面顯示「一二」、正在回覆時重新整理。"""
    start_hanging_turn(page, fakes)
    expect(page.locator('[data-state="turn-streaming"]')).to_be_visible()
    page.reload()


def test_回覆途中重新整理_保留已收到的內容並標示離開頁面時還沒有完成(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    open_chat(page, world, QWEN, LLAMA)

    # Act
    reload_mid_reply(page, fakes)

    # Assert
    last = replies(page).last
    expect(last.locator(".content")).to_have_text("一二")
    expect(last.locator(".msg-foot")).to_contain_text(LEFT)
    expect(last).not_to_contain_text("tokens/s")
    assert saved(page)["messages"][-1]["status"] == "left"


# ---------------------------------------------------------------- US2-AJ-06


def test_一段都還沒收到就切到別頁_回來時標示離開頁面時還沒有完成而不說成沒有回覆(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:替身一段都還沒送就停住
    open_chat(page, world, QWEN, LLAMA)
    fakes.server.add("POST", "/api/chat", NdjsonReply([], then="hang"), times=1)
    send(page, "你好")
    expect(page.locator('[data-state="turn-streaming"]')).to_be_visible()

    # Act
    via_models_page(page)

    # Assert
    expect(replies(page).last.locator(".msg-foot")).to_contain_text(LEFT)
    expect(page.locator("main")).not_to_contain_text("沒有回覆:Ollama 暫時無法使用")
    expect(page.locator("#log .msg")).to_have_count(2)


# ---------------------------------------------------------------- US2-AJ-07


def test_中斷的回覆之後接著送出_帶上已收到的部分且原本的中斷標示還在(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:照 US2-AJ-05 重新整理,最後一則是「一二」且標示中斷
    open_chat(page, world, QWEN, LLAMA)
    reload_mid_reply(page, fakes)
    expect(replies(page).last.locator(".msg-foot")).to_contain_text(LEFT)
    reply_with(fakes, "四五六")

    # Act
    with page.expect_request(is_chat_post) as caught:
        send(page, "繼續")

    # Assert
    sent = [(m["role"], m["content"]) for m in caught.value.post_data_json["messages"]]
    assert sent == [("user", "你好"), ("assistant", "一二"), ("user", "繼續")]
    expect(replies(page).first.locator(".msg-foot")).to_contain_text(LEFT)


# ---------------------------------------------------------------- US2-AJ-08


def test_按過停止的回覆重新整理後仍標示已停止而不是中斷(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:收到「一二」後按停止
    open_chat(page, world, QWEN, LLAMA)
    start_hanging_turn(page, fakes)
    page.click("#stop")
    expect(page.locator('[data-state="turn-stopped"]')).to_contain_text("已停止這則回覆")

    # Act
    page.reload()

    # Assert
    foot = replies(page).last.locator(".msg-foot")
    expect(foot).to_contain_text("已停止")
    expect(foot).not_to_contain_text("中斷")


# ---------------------------------------------------------------- US2-AJ-09

CLEARED = "工作階段已結束,對話已清除"


def left_ms(since: float, seconds: float = 5.0) -> float:
    """從 `since` 起算 `seconds` 秒,還剩幾毫秒(給 `expect` 的 timeout;至少 1 毫秒)。"""
    return max(1.0, (since + seconds - time.monotonic()) * 1000)


def expect_cleared_within_5s(page: Page, since: float) -> None:
    """結束後 5 秒內顯示「工作階段已結束,對話已清除」、`#log .msg` 0 則,保存是 null。"""
    cleared = page.locator('[data-state="keep-cleared"]')
    expect(cleared).to_be_visible(timeout=left_ms(since))
    expect(cleared).to_contain_text(CLEARED, timeout=left_ms(since))
    expect(page.locator("#log .msg")).to_have_count(0, timeout=left_ms(since))
    assert saved(page) is None


def test_另一個分頁結束工作階段_開著的對話頁不重新載入就清除對話(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:分頁 A 兩問兩答,記一個重新載入就會消失的標記
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)
    page.evaluate("window.__cgbMark = 1")

    # Act
    end_session_in_other_tab(context)
    ended = wait_session(e2e_servers, lambda s: s["state"] == "ended")

    # Assert
    expect_cleared_within_5s(page, ended)
    assert page.evaluate("window.__cgbMark") == 1


# ---------------------------------------------------------------- US2-AJ-10


def test_閒置自動結束後_開著的對話頁清除對話(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any, fake_clock: Any) -> None:
    # Arrange:閒置時限 1 分鐘,瀏覽器的時鐘跟著假時鐘
    assert api(e2e_servers, "PUT", "/settings", json={"idleTimeoutMinutes": 1, "lowBalanceThreshold": 10}).status_code == 200
    sync_browser_clock(page, fake_clock)
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)

    # Act
    advance_clocks(page, fake_clock, 61)
    ended = wait_session(e2e_servers, lambda s: s["state"] == "ended" and s.get("endReason") == "IDLE_TIMEOUT")

    # Assert
    expect_cleared_within_5s(page, ended)


# ---------------------------------------------------------------- US2-AJ-11


def test_工作階段被Colab收回而失聯後_開著的對話頁清除對話(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)

    # Act:Colab 已經沒有這台,通道也斷了
    world.alive.clear()
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))
    lost = wait_session(e2e_servers, lambda s: s["state"] == "lost")

    # Assert
    expect_cleared_within_5s(page, lost)


# ---------------------------------------------------------------- US2-AJ-12


def test_重連逾時而失聯後_開著的對話頁清除對話(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:之後重連一律開不起通道
    open_chat(page, world, QWEN, LLAMA)
    fakes.tunnel.open_tunnel.raises("TUNNEL_FAILED", "ssh exited")
    two_rounds(page, fakes)

    # Act:通道斷了,經過重連中之後重連逾時
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))
    lost = wait_session(e2e_servers, lambda s: s["state"] == "lost")

    # Assert
    expect_cleared_within_5s(page, lost)


# ---------------------------------------------------------------- US2-AJ-13


def switch_to_l4_in_other_tab(context: BrowserContext) -> Page:
    """由另一個分頁在就緒畫面按「變更類型」、選 L4、按「確認,結束並重開」,等重開到就緒。"""
    home = context.new_page()
    home.goto("/")
    home.locator('[data-state="ready"]').get_by_role("button", name="變更類型").click()
    home.locator('[data-state="confirm-switch"] input[type="radio"][value="L4"]').check()
    home.click("#switch")
    return home


def test_另一個分頁變更類型後_開著的對話頁清除舊工作階段的對話(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:分頁 A 兩問兩答,記下工作階段名稱 N
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)
    before = api(e2e_servers, "GET", "/session").json()["name"]

    # Act
    home = switch_to_l4_in_other_tab(context)
    renamed = wait_session(e2e_servers, lambda s: s.get("name") not in (None, before))

    # Assert
    cleared = page.locator('[data-state="keep-cleared"]')
    expect(cleared).to_be_visible(timeout=left_ms(renamed))
    expect(cleared).to_contain_text(CLEARED, timeout=left_ms(renamed))
    expect(page.locator("#log .msg")).to_have_count(0, timeout=left_ms(renamed))
    expect(home.locator('[data-state="ready"]')).to_be_visible()
    kept = saved(page)
    assert kept is None or kept["session"] != before


# ---------------------------------------------------------------- US2-AJ-14


def test_回覆途中工作階段被結束_清除對話且重新整理後不復活(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:一問一答之後,第二則回覆收到「四」後停住
    open_chat(page, world, QWEN, LLAMA)
    finish_round(page, fakes, "你好", "一二三")
    fakes.server.add("POST", "/api/chat", NdjsonReply([chunk("四")], then="hang"), times=1)
    send(page, "再說一次")
    expect(replies(page).last.locator(".content")).to_have_text("四")

    # Act
    end_session_in_other_tab(context)
    ended = wait_session(e2e_servers, lambda s: s["state"] == "ended")
    cleared = page.locator('[data-state="keep-cleared"]')
    expect(cleared).to_be_visible(timeout=left_ms(ended))
    expect(page.locator("#log .msg")).to_have_count(0, timeout=left_ms(ended))
    time.sleep(1)
    kept_after_clear = saved(page)
    page.reload()

    # Assert
    assert kept_after_clear is None
    expect(page.locator('[data-state="chat-no-session"]')).to_be_visible()
    expect(page.locator("#log .msg")).to_have_count(0)


# ---------------------------------------------------------------- US2-AJ-15

# 新分頁一載入就開始看 `#log`:記下「再說一次」出現過幾次(畫上去又清掉也算)
WATCH_LOG = """
window.__seenOld = 0;
new MutationObserver(() => {
  if (document.getElementById("log")?.textContent.includes("再說一次")) window.__seenOld += 1;
}).observe(document, { childList: true, subtree: true, characterData: true });
"""


def test_結束後開了新的工作階段才打開對話頁_上一段對話不閃現也不還原(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:兩問兩答後關掉對話頁;在工作階段頁結束,再開到新的就緒
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)
    page.close()
    home = context.new_page()
    home.goto("/")
    home.locator('[data-state="ready"]').get_by_role("button", name="結束", exact=True).click()
    home.click("#stop")
    ended = home.locator('[data-state="ended"]')
    expect(ended).to_be_visible()
    ended.get_by_role("button", name="開啟", exact=True).click()
    expect(home.locator('[data-state="ready"]')).to_be_visible()
    with_models(world, QWEN, LLAMA)  # 新開的執行環境是空的,再鋪一次目錄
    context.add_init_script(WATCH_LOG)

    # Act
    chat = context.new_page()
    chat.goto("/chat.html")
    expect(chat.locator('[data-state="chat-ready"]')).to_be_visible()
    chat.wait_for_timeout(1_000)

    # Assert
    expect(chat.locator("#log .msg")).to_have_count(0)
    assert chat.evaluate("window.__seenOld") == 0
    assert saved(chat) is None
