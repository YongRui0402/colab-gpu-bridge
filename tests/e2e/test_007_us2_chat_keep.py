"""跨端點驗收:對話保留在瀏覽器裡,工作階段結束就清除(007 testplan.md § 3.2)。

接縫:瀏覽器畫面與 `localStorage` 的 `cgb.chat.v1` 接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身
(testplan.md § 接縫的取捨)。同一個 browser context 以 `context.new_page()` 開多個分頁。
「兩問兩答」指送出「你好」收到 `一二三` + `DONE`、再送出「再說一次」收到 `四五六` + `DONE`;
「結束後 5 秒」從 `GET /api/session` 輪詢到結束狀態(或 `name` 變了)的那一刻起算(plan.md Q24)。
"""

import json
import logging
import shutil
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
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
from fakes import Gate, NdjsonReply

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


# ---------------------------------------------------------------- US2-AJ-16


def test_關掉對話頁後變更類型_新開的對話頁不還原舊工作階段的對話(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:兩問兩答後關掉對話頁;在工作階段頁變更類型成 L4,等新的工作階段就緒
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)
    before = api(e2e_servers, "GET", "/session").json()["name"]
    page.close()
    switch_to_l4_in_other_tab(context)
    wait_session(e2e_servers, lambda s: s["state"] == "ready" and s.get("name") not in (None, before), timeout=15.0)
    with_models(world, QWEN, LLAMA)  # 新開的執行環境是空的,再鋪一次目錄

    # Act
    chat = context.new_page()
    chat.goto("/chat.html")
    expect(chat.locator('[data-state="chat-ready"]')).to_be_visible()

    # Assert
    expect(chat.locator("#log .msg")).to_have_count(0)
    assert saved(chat) is None


# ---------------------------------------------------------------- US2-AJ-17


def test_關掉對話頁後結束工作階段_新開的對話頁說明沒有工作階段且不還原對話(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:兩問兩答後關掉對話頁;在工作階段頁按「結束」並確認,不開新的
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)
    page.close()
    home = context.new_page()
    home.goto("/")
    home.locator('[data-state="ready"]').get_by_role("button", name="結束", exact=True).click()
    home.click("#stop")
    expect(home.locator('[data-state="ended"]')).to_be_visible()

    # Act
    chat = context.new_page()
    chat.goto("/chat.html")

    # Assert
    expect(chat.locator('[data-state="chat-no-session"]')).to_be_visible()
    expect(chat.locator("#log .msg")).to_have_count(0)
    assert saved(chat) is None


# ---------------------------------------------------------------- US2-AJ-18


def test_按清除後對話與保存一起清掉_重新整理也不還原(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)

    # Act
    page.click("#clear")
    count_after_clear = page.locator("#log .msg").count()
    kept_after_clear = saved(page)
    page.reload()
    expect(page.locator('[data-state="chat-ready"]')).to_be_visible()

    # Assert
    assert count_after_clear == 0
    assert kept_after_clear is None
    expect(page.locator("#log .msg")).to_have_count(0)
    expect(page.locator("#clear")).to_have_text("清除")



# ---------------------------------------------------------------- US2-AJ-19


def test_換模型後對話與保存一起清掉_重新整理也不還原(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    open_chat(page, world, QWEN, LLAMA)
    page.select_option("#model", QWEN)
    two_rounds(page, fakes)

    # Act
    page.select_option("#model", LLAMA)
    count_after_switch = page.locator("#log .msg").count()
    kept_after_switch = saved(page)
    page.reload()
    expect(page.locator('[data-state="chat-ready"]')).to_be_visible()

    # Assert
    assert count_after_switch == 0
    assert kept_after_switch is None
    expect(page.locator("#log .msg")).to_have_count(0)

# ---------------------------------------------------------------- US2-AJ-20


def test_兩個分頁都開著_一個分頁對話後另一個重新整理_看到剛保存的對話(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:分頁 A、B 都打開對話頁且都是空的
    open_chat(page, world, QWEN, LLAMA)
    other = context.new_page()
    other.goto("/chat.html")
    expect(other.locator('[data-state="chat-ready"]')).to_be_visible()
    finish_round(page, fakes, "你好", "一二三")

    # Act
    other.reload()

    # Assert
    expect(other.locator("#log .msg")).to_have_count(2)
    expect(other.locator("#log .msg")).to_contain_text(["你好", "一二三"])


# ---------------------------------------------------------------- US2-AJ-21


def test_兩個分頁各自接著對話_之後打開的分頁看到最後保存的那一份(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:A 一問一答後開 B 還原同一輪;替身前兩次各在第一段後停在閘門前
    open_chat(page, world, QWEN, LLAMA)
    finish_round(page, fakes, "你好", "一二三")
    other = context.new_page()
    other.goto("/chat.html")
    expect(other.locator("#log .msg")).to_have_count(2)
    gate_a, gate_b = Gate(), Gate()
    fakes.server.add("POST", "/api/chat", NdjsonReply([chunk("子"), gate_a, chunk("丑"), DONE]), times=1)
    fakes.server.add("POST", "/api/chat", NdjsonReply([chunk("寅"), gate_b, chunk("卯"), DONE]), times=1)

    # Act
    send(page, "甲")
    gate_a.wait_entered()
    send(other, "乙")
    gate_b.wait_entered()
    gate_a.release()
    expect(replies(page).last.locator(".content")).to_have_text("子丑")
    expect(page.locator('[data-state="turn-streaming"]')).to_be_hidden()
    gate_b.release()
    expect(replies(other).last.locator(".content")).to_have_text("寅卯")
    expect(other.locator('[data-state="turn-streaming"]')).to_be_hidden()
    third = context.new_page()
    third.goto("/chat.html")

    # Assert
    expect(third.locator("#log .msg")).to_have_count(4)
    expect(third.locator("#log .msg")).to_contain_text(["你好", "一二三", "乙", "寅卯"])


# ---------------------------------------------------------------- US2-AJ-22

NO_STORE = "這個瀏覽器無法保存對話,離開或重新整理後會消失"
QUOTA_FULL = """
Storage.prototype.setItem = function () { throw new DOMException("quota exceeded", "QuotaExceededError"); };
"""


def test_瀏覽器空間不足無法保存時_提示離開會消失且對話照常可用(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:之後打開的頁面寫入 localStorage 一律丟 QuotaExceededError
    errors: list[str] = []
    context.add_init_script(QUOTA_FULL)
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_chat(page, world, QWEN, LLAMA)
    reply_with(fakes, "一二三")

    # Act
    send(page, "你好")

    # Assert
    expect(page.locator("main")).to_contain_text(NO_STORE)
    expect(replies(page).last.locator(".content")).to_have_text("一二三")
    expect(replies(page).last.locator(".msg-foot")).to_contain_text("tokens/s")
    assert errors == []


# ---------------------------------------------------------------- US2-AJ-23

STORAGE_DENIED = """
Object.defineProperty(window, "localStorage", {
  configurable: true,
  get() { throw new DOMException("access denied", "SecurityError"); },
});
"""


def test_瀏覽器不讓讀取保存時_提示離開會消失且對話照常可用(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:之後打開的頁面一碰 window.localStorage 就丟 SecurityError
    open_to_ready(page)
    with_models(world, QWEN, LLAMA)
    errors: list[str] = []
    context.add_init_script(STORAGE_DENIED)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("/chat.html")
    expect(page.locator('[data-state="chat-ready"]')).to_be_visible()
    reply_with(fakes, "一二三")

    # Act
    send(page, "你好")

    # Assert
    expect(page.locator("main")).to_contain_text(NO_STORE)
    expect(replies(page).last.locator(".content")).to_have_text("一二三")
    assert errors == []


# ---------------------------------------------------------------- US2-AJ-24

# 頁面一載入就開始看:記下「工作階段已結束,對話已清除」顯示出來過幾次(顯示又藏起來也算)
WATCH_CLEARED = """
window.__seenCleared = 0;
new MutationObserver(() => {
  const el = document.querySelector('[data-state="keep-cleared"]');
  if (el && !el.hidden && el.textContent.includes("工作階段已結束,對話已清除")) window.__seenCleared += 1;
}).observe(document, { childList: true, subtree: true, characterData: true, attributes: true });
"""


def test_後端重新啟動後接回同一個工作階段_對話不被清除_重新整理後也還在(
    page: Page,
    context: BrowserContext,
    e2e_servers: Any,
    start_live_servers: Callable[..., Any],
    make_app: Callable[..., Any],
    world: ColabWorld,
    fakes: Any,
) -> None:
    # Arrange:兩問兩答,記下工作階段名稱 N
    context.add_init_script(WATCH_CLEARED)
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)
    before = api(e2e_servers, "GET", "/session").json()["name"]

    # Act
    servers = restart_backend(e2e_servers, start_live_servers, make_app)
    wait_session(servers, lambda s: s["state"] == "ready" and s.get("name") == before, timeout=15.0)
    page.wait_for_timeout(3_000)
    count_before_reload = page.locator("#log .msg").count()
    seen_cleared = page.evaluate("window.__seenCleared")
    page.reload()

    # Assert
    assert count_before_reload == 4
    assert seen_cleared == 0
    expect_two_rounds(page)


# ---------------------------------------------------------------- US2-AJ-25


def test_通道斷線後重連接回同一個工作階段_對話不被清除(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:兩問兩答,記下工作階段名稱 N
    context.add_init_script(WATCH_CLEARED)
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)
    before = api(e2e_servers, "GET", "/session").json()["name"]

    # Act:通道斷一次,重連第 1 輪就接回(閘門讓重連中停到看得到為止)
    reconnect_gate = fakes.tunnel.open_tunnel.gate()
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))
    wait_session(e2e_servers, lambda s: s["state"] == "reconnecting")
    reconnect_gate.release()
    wait_session(e2e_servers, lambda s: s["state"] == "ready" and s.get("name") == before, timeout=15.0)
    page.wait_for_timeout(3_000)

    # Assert
    expect(page.locator("#log .msg")).to_have_count(4)
    assert page.evaluate("window.__seenCleared") == 0
    assert saved(page)["session"] == before


# ---------------------------------------------------------------- US2-AJ-26

GONE = "已不在執行環境上"


def qwen_gone_after_reload(page: Page, world: ColabWorld, fakes: Any) -> None:
    """選 `qwen2.5:latest` 兩問兩答後,從目錄拿掉它(只剩 `llama3.2:3b`),再重新整理。"""
    open_chat(page, world, QWEN, LLAMA)
    page.select_option("#model", QWEN)
    two_rounds(page, fakes)
    del world.models[QWEN]
    page.reload()


def test_保存的對話選的模型已不在目錄裡_一打開就說明且不能送出_對話照常顯示(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange、Act
    qwen_gone_after_reload(page, world, fakes)

    # Assert
    gone = page.locator('[data-state="chat-model-gone"]')
    expect(gone).to_be_visible()
    expect(gone).to_contain_text(QWEN)
    expect(page.locator("#log .msg")).to_have_count(4)
    option = page.locator("#model option[disabled]")
    expect(option).to_contain_text(QWEN)
    expect(option).to_contain_text(GONE)
    expect(page.locator("#send")).to_be_disabled()


# ---------------------------------------------------------------- US2-AJ-27


def test_模型已不在時改選另一個模型_清掉舊對話就能送出_重新整理也不還原(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:照 US2-AJ-26 已顯示模型已不在
    qwen_gone_after_reload(page, world, fakes)
    expect(page.locator('[data-state="chat-model-gone"]')).to_be_visible()

    # Act
    page.select_option("#model", LLAMA)
    count_after_switch = page.locator("#log .msg").count()
    send_enabled_after_switch = page.locator("#send").is_enabled()
    page.reload()
    expect(page.locator('[data-state="chat-ready"]')).to_be_visible()

    # Assert
    assert count_after_switch == 0
    assert send_enabled_after_switch
    expect(page.locator("#log .msg")).to_have_count(0)



# ---------------------------------------------------------------- US2-AJ-31


def test_模型已不在時改選另一個模型送出一則_收到推送後仍可接著送(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:照 US2-AJ-26 已顯示模型已不在,改選另一個模型
    qwen_gone_after_reload(page, world, fakes)
    expect(page.locator('[data-state="chat-model-gone"]')).to_be_visible()
    page.select_option("#model", LLAMA)
    reply_with(fakes, "一二三")

    # Act:送出一則,等回覆完成,再等對話後的推送讓頁面重讀目錄
    send(page, "你好")
    expect(replies(page).last.locator(".content")).to_have_text("一二三")
    page.wait_for_timeout(2_000)

    # Assert
    expect(page.locator('[data-state="chat-model-gone"]')).to_be_hidden()
    expect(page.locator('[data-state="chat-ready"]')).to_be_visible()
    expect(page.locator("#send")).to_be_enabled()

# ---------------------------------------------------------------- US2-AJ-28

USER_MARK = "cgb-test-007-使用者-不該留下"
REPLY_MARK = "cgb-test-007-回覆-不該留下"


def mark_count(text_or_bytes: str | bytes, mark: str) -> int:
    """`mark` 出現幾次:一律換成 UTF-8 位元組比,也比 JSON 把中文轉成 `\\uXXXX` 的寫法。"""
    data = text_or_bytes.encode("utf-8") if isinstance(text_or_bytes, str) else text_or_bytes
    return data.count(mark.encode("utf-8")) + data.count(json.dumps(mark)[1:-1].encode("utf-8"))


def file_bytes(path: Path) -> bytes:
    """SQLite 檔與同名 `-wal`、`-journal` 的位元組(沒有的算空)。"""
    return b"".join(Path(f"{path}{suffix}").read_bytes() for suffix in ("", "-wal", "-journal") if Path(f"{path}{suffix}").exists())


def rows_with_marks(path: Path, *marks: str) -> int:
    """列出 `sqlite_master` 的每張表、全表掃描,任何欄位含任一標記的列數。"""
    with sqlite3.connect(path) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        rows = [row for table in tables for row in conn.execute(f'SELECT * FROM "{table}"').fetchall()]
    return sum(1 for row in rows if any(isinstance(v, (str, bytes)) and mark_count(v, m) for v in row for m in marks))


def reply_mark(fakes: Any, *, hang: bool = False) -> None:
    """替身下一次 `POST /api/chat` 回 `REPLY_MARK`;`hang` 時送完這一段就停住,否則接著送 `DONE`。"""
    reply = NdjsonReply([chunk(REPLY_MARK)], then="hang") if hang else NdjsonReply([chunk(REPLY_MARK), DONE])
    fakes.server.add("POST", "/api/chat", reply, times=1)


def test_對話內容只留在瀏覽器_不寫進日誌與資料庫(
    page: Page,
    context: BrowserContext,
    e2e_servers: Any,
    world: ColabWorld,
    fakes: Any,
    caplog: pytest.LogCaptureFixture,
    db_path: Path,
    tmp_path: Path,
) -> None:
    # Arrange
    caplog.set_level(logging.DEBUG)
    open_chat(page, world, QWEN, LLAMA)

    # Act:故事 2 的獨立測試走一遍
    for text in (f"第一則 {USER_MARK}", f"第二則 {USER_MARK}"):
        reply_mark(fakes)
        send(page, text)
        expect(replies(page).last.locator(".content")).to_have_text(REPLY_MARK)
        expect(page.locator('[data-state="turn-streaming"]')).to_be_hidden()
    page.reload()
    expect(page.locator("#log .msg")).to_have_count(4)
    via_models_page(page)
    expect(page.locator("#log .msg")).to_have_count(4)
    other = context.new_page()
    other.goto("/chat.html")
    expect(other.locator("#log .msg")).to_have_count(4)
    reply_mark(fakes)
    send(other, f"第三則 {USER_MARK}")
    expect(other.locator("#log .msg")).to_have_count(6)
    expect(other.locator('[data-state="turn-streaming"]')).to_be_hidden()
    reply_mark(fakes, hang=True)
    send(other, f"第四則 {USER_MARK}")
    expect(replies(other).last.locator(".content")).to_have_text(REPLY_MARK)
    other.reload()
    expect(other.locator("#log .msg")).to_have_count(8)
    kept_before_end = json.dumps(saved(other), ensure_ascii=False)
    end_session_in_other_tab(context)
    wait_session(e2e_servers, lambda s: s["state"] == "ended")
    time.sleep(1)
    sent_to_ollama = b"".join(r.body for r in chat_requests(fakes))
    log_text = caplog.text
    user_in_log, reply_in_log = mark_count(log_text, USER_MARK), mark_count(log_text, REPLY_MARK)
    rows = rows_with_marks(db_path, USER_MARK, REPLY_MARK)
    in_files = mark_count(file_bytes(db_path), USER_MARK) + mark_count(file_bytes(db_path), REPLY_MARK)
    # 對照組:同一個搜尋與掃描函式找得到刻意寫進去的標記
    logging.getLogger("cgb").warning(USER_MARK)
    control_db = tmp_path / "control.sqlite3"
    shutil.copy(db_path, control_db)
    with sqlite3.connect(control_db) as conn:
        conn.execute("CREATE TABLE control (note TEXT)")
        conn.execute("INSERT INTO control VALUES (?)", (USER_MARK,))

    # Assert
    assert mark_count(kept_before_end, USER_MARK) >= 1  # 則1
    assert mark_count(sent_to_ollama, USER_MARK) >= 1  # 則2
    assert user_in_log == 0  # 則3
    assert reply_in_log == 0  # 則4
    assert rows == 0  # 則5
    assert in_files == 0  # 則6
    assert mark_count(caplog.text, USER_MARK) == 1  # 則7
    assert rows_with_marks(control_db, USER_MARK, REPLY_MARK) == 1  # 則8


# ---------------------------------------------------------------- US2-AJ-29


def test_保存相關的提示都是繁體中文(page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # 則1:清空後(US2-AJ-09)
    open_chat(page, world, QWEN, LLAMA)
    two_rounds(page, fakes)
    name = api(e2e_servers, "GET", "/session").json()["name"]
    home = context.new_page()
    home.goto("/")
    home.locator('[data-state="ready"]').get_by_role("button", name="結束", exact=True).click()
    home.click("#stop")
    expect(page.locator('[data-state="keep-cleared"]')).to_be_visible()
    assert_traditional_chinese(page, "keep-cleared", names=(name,))
    expect(page.locator("main")).to_contain_text(CLEARED)

    # 則2:不能保存(US2-AJ-22),另開一個寫入一律丟 QuotaExceededError 的分頁
    ended = home.locator('[data-state="ended"]')
    ended.get_by_role("button", name="開啟", exact=True).click()
    expect(home.locator('[data-state="ready"]')).to_be_visible()
    with_models(world, QWEN, LLAMA)
    no_store = context.new_page()
    no_store.add_init_script(QUOTA_FULL)
    no_store.goto("/chat.html")
    expect(no_store.locator('[data-state="chat-ready"]')).to_be_visible()
    reply_with(fakes, "一二三")
    send(no_store, "你好")
    expect(replies(no_store).last.locator(".content")).to_have_text("一二三")
    expect(no_store.locator('[data-state="keep-no-store"]')).to_be_visible()
    assert_traditional_chinese(no_store, "keep-no-store")
    expect(no_store.locator("main")).to_contain_text(NO_STORE)
    no_store.close()

    # 則3:離開頁面中斷(US2-AJ-05)
    page.reload()
    expect(page.locator('[data-state="chat-ready"]')).to_be_visible()
    page.select_option("#model", QWEN)
    reload_mid_reply(page, fakes)
    expect(replies(page).last.locator(".msg-foot")).to_contain_text(LEFT)
    assert_traditional_chinese(page, "turn-interrupted")
    expect(page.locator("main")).to_contain_text(LEFT)

    # 則4:模型已不在(US2-AJ-26)
    del world.models[QWEN]
    page.reload()
    expect(page.locator('[data-state="chat-model-gone"]')).to_be_visible()
    assert_traditional_chinese(page, "chat-model-gone")
    expect(page.locator("main")).to_contain_text(GONE)


# ---------------------------------------------------------------- US2-AJ-30

IDLE_HINT = "在這裡送出訊息,也會讓工作階段的閒置倒數重新計時。"


def test_還原後回到可以送出的提示_接著送出先顯示載入模型再回到可以送出(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:模型還沒載入;兩問兩答後重新整理,等對話還原;下一次回覆在第一段之前停在閘門前
    open_chat(page, world, QWEN, LLAMA, loaded=())
    page.select_option("#model", QWEN)
    two_rounds(page, fakes)
    page.reload()
    expect_two_rounds(page)
    turn = page.locator('[data-group="turn"]:not([hidden])')
    restored_text = turn.inner_text()
    first_chunk = Gate()
    fakes.server.add("POST", "/api/chat", NdjsonReply([first_chunk, chunk("七"), DONE]), times=1)

    # Act
    send(page, "第三則")
    first_chunk.wait_entered()
    loading_text = turn.inner_text() if page.locator('[data-state="turn-loading"]').is_visible() else None
    first_chunk.release()

    # Assert
    assert restored_text == IDLE_HINT
    assert loading_text is not None and QWEN in loading_text
    expect(replies(page).last.locator(".content")).to_have_text("七")
    expect(turn).to_have_text(IDLE_HINT, timeout=2_000)
