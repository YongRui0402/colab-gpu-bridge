"""跨端點驗收:在 UI 裡跟模型對話(004 testplan.md § 3.2)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨、plan.md Q99)。
對話轉送經真的 HTTP 打 `fakes.server`(`FakeOllamaServer`):`FakeTunnel` 開的通道就是它的位址(`ColabWorld._open_tunnel`)。
回覆的每一行以 `NdjsonReply` 排;要在「收到第 N 行之後、下一行之前」看畫面的地方用 `Gate` 停住,不靠行間延遲。
執行環境上的模型以 `ColabWorld.models` 鋪(等同 `set_tags`、`set_loaded`)。
"""

import re
import time
from dataclasses import replace
from typing import Any

import pytest
from playwright.sync_api import BrowserContext, Locator, Page, expect

from cgb.app import Timeouts
from conftest import TEST_TIMEOUTS
from e2e.test_us1_session import ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture
from fakes import DisconnectReply, Gate, HangReply, JsonReply, NdjsonReply

QWEN = "qwen2.5:latest"
LLAMA = "llama3.2:3b"
SIZES = {QWEN: 4_683_087_332, LLAMA: 2_019_393_189}


@pytest.fixture
def chat_read() -> float | None:
    """注入的段間逾時(`Timeouts.chat_read`,plan.md Q44);要測逾時的案例以 `parametrize("chat_read", [0.3])` 覆寫。"""
    return None


@pytest.fixture
def test_timeouts(chat_read: float | None) -> Timeouts:
    return TEST_TIMEOUTS if chat_read is None else replace(TEST_TIMEOUTS, chat_read=chat_read)


def chunk(text: str) -> dict[str, Any]:
    return {"model": QWEN, "created_at": "2026-11-09T09:00:00Z", "message": {"role": "assistant", "content": text}, "done": False}


DONE = {"model": QWEN, "message": {"role": "assistant", "content": ""}, "done": True, "eval_count": 30, "eval_duration": 762323000}
SIX = [chunk(c) for c in "一二三四五六"]


def with_models(world: ColabWorld, *names: str, loaded: tuple[str, ...] | None = None) -> None:
    """執行環境上的模型;`loaded` 沒給時全部已載入。"""
    for name in names:
        world.models[name] = (SIZES[name], name in (names if loaded is None else loaded))


def open_chat(page: Page, world: ColabWorld, *names: str, loaded: tuple[str, ...] | None = None) -> None:
    open_to_ready(page)
    with_models(world, *names, loaded=loaded)
    page.goto("/chat.html")
    expect(page.locator('[data-state="chat-ready"]')).to_be_visible()


def send(page: Page, text: str) -> None:
    page.fill("#input", text)
    page.click("#send")


def replies(page: Page) -> Locator:
    return page.locator("#log .msg-bot")


def chat_requests(fakes: Any) -> list[Any]:
    return fakes.server.requests_to("POST", "/api/chat")


# ---- 004 US2-AJ-01


def test_送出後回覆逐段出現_完成後不再顯示正在回覆(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:第 3 行之後停在閘門前,DONE 還沒送
    held = Gate()
    fakes.server.add("POST", "/api/chat", NdjsonReply([*SIX[:3], held, *SIX[3:], DONE]))
    open_chat(page, world, QWEN)
    page.select_option("#model", QWEN)

    # Act
    send(page, "你好")

    # Assert
    held.wait_entered()
    expect(replies(page).last.locator(".content")).to_contain_text("一二三")
    held.release()
    expect(replies(page).last.locator(".content")).to_have_text("一二三四五六")
    expect(page.locator('[data-state="turn-streaming"]')).to_be_hidden()


def complete_turn(page: Page, fakes: Any, text: str = "你好") -> None:
    """送出一則,替身回完整的 6 行與 `DONE`,等到這則回覆完成。"""
    fakes.server.add("POST", "/api/chat", NdjsonReply([*SIX, DONE]), times=1)
    send(page, text)
    expect(replies(page).last.locator(".content")).to_have_text("一二三四五六")
    expect(page.locator('[data-state="turn-streaming"]')).to_be_hidden()


# ---- 004 US2-AJ-02


def test_第二則送出時帶上前面的對話與模型的回覆(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:第一則已完成
    open_chat(page, world, QWEN)
    complete_turn(page, fakes)
    fakes.server.add("POST", "/api/chat", NdjsonReply([*SIX, DONE]), times=1)

    # Act
    send(page, "再說一次")

    # Assert
    expect(replies(page)).to_have_count(2)
    expect(replies(page).last.locator(".content")).to_have_text("一二三四五六")
    sent = [(m["role"], m["content"]) for m in chat_requests(fakes)[1].json()["messages"]]
    assert sent == [("user", "你好"), ("assistant", "一二三四五六"), ("user", "再說一次")]


# ---- 004 US2-AJ-03


def test_回覆完成後下方顯示耗時與每秒token數(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_chat(page, world, QWEN)

    # Act
    complete_turn(page, fakes)

    # Assert
    foot = replies(page).last.locator(".msg-foot")
    expect(foot).to_contain_text(re.compile(r"耗時 \S+ 秒"))
    expect(foot).to_contain_text("39.4 tokens/s")


# ---- 004 US2-AJ-04


def test_結束行沒有token統計時只顯示耗時_不標成中斷(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:最後一行沒有 eval_count、eval_duration
    open_chat(page, world, QWEN)
    bare_done = {"message": {"role": "assistant", "content": ""}, "done": True}
    fakes.server.add("POST", "/api/chat", NdjsonReply([*SIX, bare_done]))

    # Act
    send(page, "你好")

    # Assert
    expect(replies(page).last.locator(".content")).to_have_text("一二三四五六")
    expect(replies(page).last.locator(".msg-foot")).to_contain_text("沒有 token 統計,不顯示速度")
    expect(page.locator('[data-state="turn-error"]')).to_be_hidden()


def start_hanging_turn(page: Page, fakes: Any, text: str = "你好") -> None:
    """送出一則,替身送出 `一`、`二` 之後停住不再送(`then="hang"`),等畫面出現「一二」。"""
    fakes.server.add("POST", "/api/chat", NdjsonReply(SIX[:2], then="hang"), times=1)
    send(page, text)
    expect(replies(page).last.locator(".content")).to_have_text("一二")


# ---- 004 US2-AJ-05


def test_按停止後斷開連線並保留已收到的內容_之後可以再送(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_chat(page, world, QWEN)
    start_hanging_turn(page, fakes)
    expect(page.locator("#stop")).to_be_visible()

    # Act
    page.click("#stop")

    # Assert
    expect(page.locator('[data-state="turn-stopped"]')).to_be_visible(timeout=1_000)
    expect(replies(page).last.locator(".content")).to_have_text("一二")
    deadline = time.monotonic() + 2.0
    while not fakes.server.closed_requests("POST", "/api/chat") and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(fakes.server.closed_requests("POST", "/api/chat")) == 1, "按下停止後,替身沒有發現第 1 個對話請求的連線被關掉"
    complete_turn(page, fakes, "下一則")
    expect(replies(page).first.locator(".content")).to_have_text("一二")


# ---- 004 US2-AJ-06


def test_清空與換模型都清掉畫面與要帶上的對話(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_chat(page, world, QWEN, LLAMA)
    page.select_option("#model", QWEN)
    complete_turn(page, fakes)

    # Act(情況 A)
    page.click("#clear")

    # Assert(則1)
    expect(page.locator("#log .msg")).to_have_count(0)

    # Arrange、Act(情況 B)
    complete_turn(page, fakes)
    page.select_option("#model", LLAMA)

    # Assert(則2)
    expect(page.locator("#log .msg")).to_have_count(0)

    # Act、Assert(則3)
    complete_turn(page, fakes, "嗨")
    sent = [(m["role"], m["content"]) for m in chat_requests(fakes)[-1].json()["messages"]]
    assert sent == [("user", "嗨")]


# ---- 004 US2-AJ-07


def test_選的模型還沒載入時第一段之前顯示正在載入(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:沒有已載入的模型;替身在第一行之前停在閘門(等同先載入)
    first = Gate()
    fakes.server.add("POST", "/api/chat", NdjsonReply([first, *SIX, DONE]))
    open_chat(page, world, QWEN, loaded=())
    page.select_option("#model", QWEN)

    # Act
    send(page, "你好")

    # Assert
    first.wait_entered()
    loading = page.locator('[data-state="turn-loading"]')
    expect(loading).to_be_visible()
    expect(loading).to_contain_text("qwen2.5")
    first.release()
    expect(replies(page).last.locator(".content")).to_contain_text("一")
    expect(loading).to_be_hidden()


# ---- 004 US2-AJ-08


def test_沒有工作階段或沒有模型時說明原因且不能送出(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # 情況 A:沒有工作階段
    page.goto("/chat.html")
    no_session = page.locator('[data-state="chat-no-session"]')
    expect(no_session).to_be_visible()
    expect(no_session).to_contain_text("沒有就緒的工作階段")
    expect(page.locator("#send")).to_be_disabled()

    # 情況 B:工作階段就緒,執行環境上沒有模型
    open_to_ready(page)
    page.goto("/chat.html")
    no_models = page.locator('[data-state="chat-no-models"]')
    expect(no_models).to_be_visible()
    expect(no_models).to_contain_text("還沒有下載完成的模型")
    expect(page.locator("#send")).to_be_disabled()


def end_session_in_other_tab(context: BrowserContext) -> None:
    """由另一個分頁按「結束」並確認。"""
    home = context.new_page()
    home.goto("/")
    home.locator('[data-state="ready"]').get_by_role("button", name="結束", exact=True).click()
    home.click("#stop")


# ---- 004 US2-AJ-09


def test_回覆途中工作階段被結束_保留已收到的內容並標示中斷(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    open_chat(page, world, QWEN)
    start_hanging_turn(page, fakes)

    # Act
    end_session_in_other_tab(context)

    # Assert
    expect(page.locator('[data-state="turn-lost"]')).to_be_visible()
    expect(replies(page).last.locator(".content")).to_have_text("一二")
    expect(page.locator("#model option", has_text=QWEN)).to_have_count(0)


# ---- 004 US2-AJ-10


@pytest.mark.parametrize("chat_read", [0.3])
def test_回覆途中推論失敗或逾時_保留已收到的內容並以中文說明(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_chat(page, world, QWEN)
    fakes.server.add("POST", "/api/chat", NdjsonReply([chunk("一"), {"error": "llama runner process has terminated"}]), times=1)
    fakes.server.add("POST", "/api/chat", NdjsonReply([chunk("一")], then="hang"), times=1)
    error = page.locator('[data-state="turn-error"]')
    timeout = page.locator('[data-state="turn-timeout"]')

    # Act、Assert(情況 A:遠端送了帶 error 的一行)
    send(page, "你好")
    expect(error).to_be_visible()
    expect(replies(page).last.locator(".content")).to_have_text("一")
    expect(error).to_contain_text("處理時發生錯誤")
    assert "llama runner" not in page.locator("main").inner_text()

    # Act、Assert(情況 B:送 `一` 後停住超過段間逾時)
    send(page, "再一次")
    expect(timeout).to_be_visible()
    expect(replies(page).last.locator(".content")).to_have_text("一")
    expect(timeout).to_contain_text("在時限內沒有回應")
    assert "llama runner" not in page.locator("main").inner_text()


def thought(text: str) -> dict[str, Any]:
    return {"model": QWEN, "message": {"role": "assistant", "content": "", "thinking": text}, "done": False}


# ---- 004 US2-AJ-11


def test_思考型模型的思考過程放在收合區塊_不混進回覆(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:先 3 行只有 message.thinking,停在閘門,再送 2 行內容與 DONE
    held = Gate()
    fakes.server.add("POST", "/api/chat", NdjsonReply([thought("想"), thought("一"), thought("下"), held, chunk("好"), chunk("的"), DONE]))
    open_chat(page, world, QWEN)

    # Act
    send(page, "你好")

    # Assert
    held.wait_entered()
    thinking = replies(page).last.locator("details.thinking")
    expect(thinking.locator("summary")).to_contain_text("思考過程")
    expect(thinking.locator(".thought")).to_have_text("想一下")
    held.release()
    expect(replies(page).last.locator(".content")).to_have_text("好的")
    expect(replies(page).last.locator(".content")).not_to_contain_text("想一下")


# ---- 004 US2-AJ-13


def test_回覆到一半斷線或收到無法解讀的行_各自標示原因(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_chat(page, world, QWEN)
    fakes.server.add("POST", "/api/chat", NdjsonReply([chunk("一")], then="disconnect"), times=1)
    fakes.server.add("POST", "/api/chat", NdjsonReply([chunk("一"), b"not json\n"]), times=1)
    interrupted = page.locator('[data-state="turn-interrupted"]')
    bad = page.locator('[data-state="turn-bad-response"]')

    # Act、Assert(情況 A:送 `一` 後斷線)
    send(page, "你好")
    expect(interrupted).to_be_visible()
    expect(replies(page).last.locator(".content")).to_have_text("一")
    expect(interrupted).to_contain_text("回應到一半就斷了")

    # Act、Assert(情況 B:送 `一` 後送一行不是 JSON 的)
    send(page, "再一次")
    expect(bad).to_be_visible()
    expect(replies(page).last.locator(".content")).to_have_text("一")
    expect(bad).to_contain_text("回應無法解讀")


# ---- 004 US2-AJ-14


@pytest.mark.parametrize("chat_read", [0.3])
def test_串流開始前失敗時說明沒有送出的原因_訊息留在對話裡(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:A 404、B 讀完請求就斷線、C 不回應直到段間逾時、D 遠端 500(記憶體不足)
    open_chat(page, world, QWEN)
    for reply in (
        JsonReply({"error": "model 'qwen2.5' not found"}, status=404),
        DisconnectReply(),
        HangReply(),
        JsonReply({"error": "model requires more system memory"}, status=500),
    ):
        fakes.server.add("POST", "/api/chat", reply, times=1)
    users = page.locator("#log .msg-user", has_text="你好")
    cases = [
        ("turn-not-found", "執行環境上沒有這個模型"),
        ("turn-unavailable", "連不到執行環境上的 Ollama"),
        ("turn-start-timeout", "在時限內沒有回應"),
        ("turn-unavailable", "處理時發生錯誤"),
    ]

    for count, (state, text) in enumerate(cases, start=1):
        # Act
        send(page, "你好")

        # Assert(則1~則3、則5;則4:「你好」都留在 #log)
        line = page.locator(f'[data-state="{state}"]')
        expect(line).to_be_visible()
        expect(line).to_contain_text(text)
        expect(users).to_have_count(count)
        expect(page.locator("#send")).to_be_visible()
    main = page.locator("main").inner_text()
    assert "連不到" not in page.locator('[data-state="turn-unavailable"]').inner_text()
    assert "memory" not in main


# ---- 004 US2-AJ-15


def test_回覆途中在另一個分頁變更類型_保留已收到的內容並說明正在變更類型(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    open_chat(page, world, QWEN)
    start_hanging_turn(page, fakes)
    home = context.new_page()
    home.goto("/")

    # Act
    home.locator('[data-state="ready"]').get_by_role("button", name="變更類型").click()
    home.locator('[data-state="confirm-switch"] input[type="radio"][value="L4"]').check()
    home.click("#switch")
    page.bring_to_front()

    # Assert
    lost = page.locator('[data-state="turn-lost"]')
    expect(lost).to_be_visible()
    expect(replies(page).last.locator(".content")).to_have_text("一二")
    expect(lost).to_contain_text("正在變更類型")


# ---- 004 US2-AJ-12

ALLOWED_WORDS = ("Hugging Face", "Colab", "token", "Ollama", "GGUF")


def assert_traditional_chinese(page: Page, state: str) -> None:
    """對話頁 `main` 的文字去掉模型名稱與 `tokens/s` 之後,沒有連續 4 個以上的英文字母(容許清單除外),且至少有一個中文字。"""
    text = page.locator("main").inner_text()
    for removed in (QWEN, LLAMA, "qwen2.5", "tokens/s", *ALLOWED_WORDS):
        text = text.replace(removed, "")
    words = re.findall(r"[A-Za-z]{4,}", text)
    assert words == [], f"{state}:對話頁出現英文 {words}"
    assert re.search(r"[一-鿿]", text), f"{state}:對話頁沒有中文字"


def test_對話頁各種狀態的文字都是繁體中文(page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    def shown(state: str) -> None:
        expect(page.locator(f'[data-state="{state}"]')).to_be_visible()
        assert_traditional_chinese(page, state)

    # 沒有工作階段、沒有模型
    page.goto("/chat.html")
    shown("chat-no-session")
    open_to_ready(page)
    page.goto("/chat.html")
    shown("chat-no-models")

    # 可以送出、完成與停止的回覆
    with_models(world, QWEN)
    page.goto("/chat.html")
    shown("chat-ready")
    complete_turn(page, fakes)
    assert_traditional_chinese(page, "完成的回覆")
    start_hanging_turn(page, fakes)
    page.click("#stop")
    shown("turn-stopped")

    # 回覆途中中斷、串流開始前就失敗
    for reply, state in (
        (NdjsonReply([chunk("一"), {"error": "llama runner process has terminated"}]), "turn-error"),
        (NdjsonReply([chunk("一")], then="disconnect"), "turn-interrupted"),
        (NdjsonReply([chunk("一"), b"not json\n"]), "turn-bad-response"),
        (JsonReply({"error": "model 'qwen2.5' not found"}, status=404), "turn-not-found"),
        (DisconnectReply(), "turn-unavailable"),
    ):
        fakes.server.add("POST", "/api/chat", reply, times=1)
        send(page, "你好")
        shown(state)

    # 回覆途中工作階段被結束
    start_hanging_turn(page, fakes)
    end_session_in_other_tab(context)
    page.bring_to_front()
    shown("turn-lost")


@pytest.mark.parametrize("chat_read", [0.3])
def test_對話頁逾時的兩種說明也是繁體中文(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    open_chat(page, world, QWEN)
    for reply, state in ((NdjsonReply([chunk("一")], then="hang"), "turn-timeout"), (HangReply(), "turn-start-timeout")):
        fakes.server.add("POST", "/api/chat", reply, times=1)
        send(page, "你好")
        expect(page.locator(f'[data-state="{state}"]')).to_be_visible()
        assert_traditional_chinese(page, state)


# ---- 004 US2-AJ-網路例外:瀏覽器與後端之間斷線


def test_送出前連線被拒_標示中斷並釋放送出鈕_恢復後可以再送(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:第一次送出的 `/api/chat` 在瀏覽器端被拒絕(模擬斷線),之後放行
    open_chat(page, world, QWEN)
    fakes.server.add("POST", "/api/chat", NdjsonReply([chunk("好"), DONE]), times=1)
    page.route("**/api/chat", lambda route: route.abort(), times=1)

    # Act
    send(page, "你好")

    # Assert:這一則標示中斷,送出鈕與模型選單回復
    expect(page.locator('[data-state="turn-interrupted"]')).to_be_visible()
    expect(page.locator("#send")).to_be_visible()
    expect(page.locator("#model")).to_be_enabled()

    # Act、Assert:恢復後再送一則,回覆完成
    send(page, "再試一次")
    expect(replies(page).last.locator(".content")).to_have_text("好")
    expect(page.locator("#send")).to_be_visible()


def test_收到部分內容後串流讀取失敗_保留已收到的內容並標示中斷_恢復後可以再送(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:第一次的回應送出一行就讓串流讀取丟例外,之後的請求走真的後端
    open_chat(page, world, QWEN)
    fakes.server.add("POST", "/api/chat", NdjsonReply([chunk("好"), DONE]), times=1)
    page.evaluate(
        """() => {
            const real = window.fetch.bind(window);
            let broken = false;
            window.fetch = async (input, init) => {
                if (!broken && String(input).includes("/api/chat")) {
                    broken = true;
                    const line = JSON.stringify({ model: "m", message: { role: "assistant", content: "一二" }, done: false }) + "\\n";
                    const body = new ReadableStream({
                        start(controller) { controller.enqueue(new TextEncoder().encode(line)); },
                        pull() { return new Promise((_, reject) => setTimeout(() => reject(new TypeError("network disconnected")), 50)); },
                    });
                    return new Response(body, { status: 200, headers: { "Content-Type": "application/x-ndjson" } });
                }
                return real(input, init);
            };
        }"""
    )

    # Act
    send(page, "你好")

    # Assert
    expect(page.locator('[data-state="turn-interrupted"]')).to_be_visible()
    expect(replies(page).last.locator(".content")).to_have_text("一二")
    expect(page.locator("#send")).to_be_visible()
    expect(page.locator("#model")).to_be_enabled()

    # Act、Assert:恢復後再送一則,回覆完成
    send(page, "再試一次")
    expect(replies(page).last.locator(".content")).to_have_text("好")
