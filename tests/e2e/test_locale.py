"""全域:畫面與錯誤訊息一律繁體中文、台灣用語(testplan.md § G-06;spec.md NFR-011;plan.md Q105、Q111、Q117)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781、Ollama 相容端點 127.0.0.1:11437),轉接層用替身
(testplan.md § 接縫的取捨、plan.md Q99)。每個畫面狀態都照使用者真的會走到的路走過去(Q117:有些狀態只有這裡走得到),
再取整頁的可見文字;錯誤訊息則對 UI API 的每個錯誤代碼、Ollama 相容端點本系統自己產生的每一種錯誤各觸發一次。
"""

import json
import re
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from playwright.sync_api import BrowserContext, Page, expect

from cgb.adapters.errors import AdapterError
from cgb.domain.errors import MESSAGES
from e2e.conftest import E2E_OLLAMA_PORT
from e2e.test_us1_login import google_flows
from e2e.test_us1_session import CJK, T4, ColabWorld, open_to_ready, restart_backend, wait_until, world  # noqa: F401 - `world` 是 fixture
from e2e.test_us3_library import search_page
from e2e.test_us4_usage import advance_clocks, reading, sync_browser_clock
from fakes import Gate, NdjsonReply

# Q105(a):`constitution/_shared/語言.md` Rule 1 的對照詞。testplan § G-06 列的簡體寫法,加上 Rule 1 點名的大陸用語(繁體寫法)
SIMPLIFIED_OR_MAINLAND = (
    "会话", "服务器", "默认", "用户", "数据", "设置", "登录", "网络", "内存", "信息", "程序", "文件", "接口", "支持",
    "數據", "服務器", "默認", "用戶", "設置", "登錄", "網絡", "內存",
)  # fmt: skip
HTML_LANGS = {"zh-Hant-TW", "zh-TW"}

MODEL = "qwen2.5:0.5b"
SIZE_0_5B = 397_821_319
# 比替身的顯示記憶體總量(15 GiB 左右)大:預先載入前要先提示(NFR-006)
SIZE_32B = 19_851_336_078
# 比替身的剩餘磁碟(225 GB 左右)大:加入下載前要提示空間不足(FR-022)
SIZE_405B = 243_250_000_000


def unreachable_base_url() -> str:
    """一個沒有人在聽的本機位址:轉送時連不上(OLLAMA_UNREACHABLE)。"""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}"


@dataclass
class World:
    """一個測試要用到的全部東西:瀏覽器、替身、時鐘與「設好替身之後才啟動」的後端。"""

    page: Page
    context: BrowserContext
    colab: ColabWorld
    fakes: Any
    clock: Any
    serve: Callable[[], Any]
    start_live_servers: Callable[..., Any]
    make_app: Callable[..., Any]
    servers: Any = None
    gates: list[Gate] = field(default_factory=list)

    def start(self) -> Any:
        self.servers = self.serve()
        return self.servers

    def gate(self, method: Any) -> Gate:
        gate = method.gate()
        self.gates.append(gate)
        return gate

    def release_all(self) -> None:
        for gate in self.gates:
            gate.release()

    def api(self) -> httpx.Client:
        return httpx.Client(base_url=self.servers.ui_url)

    def ready(self) -> None:
        """啟動後端,打開首頁以預設類型開到就緒。"""
        self.start()
        open_to_ready(self.page)

    def ready_with_models(self, models: dict[str, tuple[int, bool]]) -> None:
        """開到就緒,再讓執行環境上有 `models`(名稱 → (大小, 是否已載入));新開的執行環境是空的。"""
        self.ready()
        self.colab.models = dict(models)

    def restart(self) -> None:
        self.servers = restart_backend(self.servers, self.start_live_servers, self.make_app)

    def health_fails_once(self) -> None:
        self.fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))

    def open_via_api(self) -> str:
        with self.api() as client:
            client.post("/api/session", json=T4)
            wait_until(lambda: client.get("/api/session").json()["state"] == "ready", "工作階段沒有就緒")
            return client.get("/api/session").json()["name"]


@pytest.fixture
def w(
    request: pytest.FixtureRequest,
    page: Page,
    context: BrowserContext,
    world: ColabWorld,
    fakes: Any,
    fake_clock: Any,
    start_live_servers: Callable[..., Any],
    make_app: Callable[..., Any],
) -> Any:
    state = World(
        page=page,
        context=context,
        colab=world,
        fakes=fakes,
        clock=fake_clock,
        serve=lambda: request.getfixturevalue("e2e_servers"),
        start_live_servers=start_live_servers,
        make_app=make_app,
    )
    try:
        yield state
    finally:
        state.release_all()


# ================================================================ 則1、則4:每一頁每個畫面狀態

# ---------------------------------------------------------------- 首頁(工作階段面板)


def home_normal(w: World) -> None:
    w.start()
    w.page.goto("/")


def home_low_balance(w: World) -> None:
    w.fakes.colab.get_usage.returns(reading(9.50, 1.15))
    w.start()
    w.page.goto("/")


def home_foreign(w: World) -> None:
    # 後端啟動時 `colab sessions` 列出一台名稱是 `[?]` 的 T4
    w.colab.unnamed = [{"hardware": "T4", "shape": "Standard", "variant": "GPU"}]
    w.start()
    w.page.goto("/")


def home_needs_login(w: World) -> None:
    w.fakes.colab.get_usage.raises("AUTH_REQUIRED", "colab needs login")
    w.start()
    w.page.goto("/")
    w.page.click("#open")


def home_starting(w: World) -> None:
    w.start()
    w.gate(w.fakes.colab.create_session)
    w.page.goto("/")
    w.page.click("#open")


def home_ready(w: World) -> None:
    w.ready()


def home_confirm_stop(w: World) -> None:
    w.ready()
    w.page.locator('[data-state="ready"]').get_by_role("button", name="結束", exact=True).click()


def home_confirm_switch(w: World) -> None:
    w.ready()
    w.page.locator('[data-state="ready"]').get_by_role("button", name="變更類型").click()


def home_stopping(w: World) -> None:
    w.ready()
    w.gate(w.fakes.colab.stop_session)
    w.page.locator('[data-state="ready"]').get_by_role("button", name="結束", exact=True).click()
    w.page.click("#stop")


def home_switching(w: World) -> None:
    w.ready()
    w.gate(w.fakes.colab.stop_session)
    w.page.locator('[data-state="ready"]').get_by_role("button", name="變更類型").click()
    w.page.locator('[data-state="confirm-switch"] input[type="radio"][value="L4"]').check()
    w.page.click("#switch")


def home_ended(w: World) -> None:
    w.ready()
    w.page.locator('[data-state="ready"]').get_by_role("button", name="結束", exact=True).click()
    w.page.click("#stop")


def home_ended_idle(w: World) -> None:
    w.start()
    reply = httpx.put(f"{w.servers.ui_url}/api/settings", json={"idleTimeoutMinutes": 1, "lowBalanceThreshold": 10})
    assert reply.status_code == 200, reply.text
    sync_browser_clock(w.page, w.clock)
    open_to_ready(w.page)
    advance_clocks(w.page, w.clock, 61)


def home_failed(w: World) -> None:
    w.fakes.colab.create_session.then(AdapterError("COLAB_ALLOCATION_REFUSED", "Colab refused to allocate"))
    w.start()
    w.page.goto("/")
    w.page.click("#open")


def home_already_open(w: World) -> None:
    # 第二個分頁收不到推送,畫面停在打開時的「未開啟」,只能靠後端擋
    w.start()
    second = w.context.new_page()
    second.route("**/api/events", lambda route: route.abort())
    second.goto("/")
    create = w.gate(w.fakes.colab.create_session)
    w.page.goto("/")
    w.page.click("#open")
    create.wait_entered()
    w.page = second
    expect(second.locator("#open")).to_be_visible()
    second.click("#open")


def home_reconnecting(w: World) -> None:
    w.ready()
    w.gate(w.fakes.tunnel.open_tunnel)
    w.health_fails_once()


def home_lost(w: World) -> None:
    w.ready()
    w.colab.alive.clear()
    w.health_fails_once()


def home_lost_timeout(w: World) -> None:
    w.ready()
    w.fakes.tunnel.open_tunnel.raises("TUNNEL_FAILED", "ssh exited")
    w.health_fails_once()
    expect(w.page.locator('[data-state="lost-timeout"]')).to_be_visible(timeout=10_000)


def home_lost_zero(w: World) -> None:
    w.fakes.colab.get_usage.returns(reading(0.00, 1.76))
    w.start()
    w.page.goto("/")
    w.page.locator('[data-state="low-balance"]').get_by_role("button", name="開啟", exact=True).click()
    expect(w.page.locator('[data-state="ready"]')).to_be_visible()
    w.colab.alive.clear()
    w.health_fails_once()


def home_release_failed(w: World) -> None:
    w.ready()
    w.fakes.tunnel.open_tunnel.raises("TUNNEL_FAILED", "ssh exited")
    w.fakes.colab.stop_session.raises("COLAB_STOP_UNCONFIRMED", "colab sessions still lists it")
    w.health_fails_once()
    expect(w.page.locator('[data-state="release-failed"]')).to_be_visible(timeout=10_000)


def home_resuming(w: World) -> None:
    # 後端重新啟動後接回:清掉上一個行程留下的 ssh 那一步停住,等測試放行
    w.ready()
    w.gate(w.fakes.tunnel.cleanup_residual)
    w.restart()
    w.page.goto("/")


# ---------------------------------------------------------------- 登入頁


def logged_out(w: World) -> None:
    w.fakes.colab.get_usage.raises("AUTH_REQUIRED", "colab needs login")
    google_flows(w.fakes)


def login_normal(w: World) -> None:
    logged_out(w)
    w.start()
    w.page.goto("/login.html")


def login_signed_in(w: World) -> None:
    w.start()
    w.page.goto("/login.html")


def login_loading(w: World) -> None:
    logged_out(w)
    w.gate(w.fakes.google_oauth.build_authorization_url)
    w.start()
    w.page.goto("/login.html")
    w.page.locator('[data-state="normal"] [data-action="get-link"]').click()


def to_link(w: World) -> None:
    w.start()
    w.page.goto("/login.html")
    w.page.locator('[data-state="normal"] [data-action="get-link"]').click()
    expect(w.page.locator("#code")).to_be_visible()


def submit_code(w: World) -> None:
    w.page.fill("#code", "4/cgb-test-code")
    w.page.locator("#code-form").get_by_role("button", name="送出授權碼").click()


def login_link(w: World) -> None:
    logged_out(w)
    to_link(w)


def login_verifying(w: World) -> None:
    logged_out(w)
    w.fakes.google_oauth.request_token.returns("/tmp/cgb-test-not-written/token.json")
    w.gate(w.fakes.google_oauth.request_token)
    to_link(w)
    submit_code(w)


def login_rejected(code: str) -> Callable[[World], None]:
    def drive(w: World) -> None:
        logged_out(w)
        w.fakes.google_oauth.request_token.raises(code, code.lower())
        to_link(w)
        submit_code(w)

    return drive


def login_link_expired(w: World) -> None:
    # 取得連結之後後端重新啟動過,這組連結的流程已經不在
    logged_out(w)
    w.fakes.google_oauth.request_token.returns("/tmp/cgb-test-not-written/token.json")
    to_link(w)
    w.restart()
    submit_code(w)


# ---------------------------------------------------------------- 紀錄頁


def history_normal(w: World) -> None:
    w.start()
    w.open_via_api()
    with w.api() as client:
        client.delete("/api/session")
        wait_until(lambda: client.get("/api/session").json()["state"] == "ended", "工作階段沒有結束")
    w.page.goto("/history.html")


def history_empty(w: World) -> None:
    w.start()
    w.page.goto("/history.html")


# ---------------------------------------------------------------- 模型頁


def models_normal(w: World) -> None:
    w.ready_with_models({MODEL: (SIZE_0_5B, True)})
    w.page.goto("/models.html")


def models_empty(w: World) -> None:
    w.ready()
    w.page.goto("/models.html")


def models_loading(w: World) -> None:
    w.ready_with_models({MODEL: (SIZE_0_5B, True)})
    w.gate(w.fakes.remote_ollama.list_local_models)
    w.page.goto("/models.html")


def models_no_session(w: World) -> None:
    w.start()
    w.page.goto("/models.html")


def click_preload(w: World, name: str) -> None:
    row = w.page.locator("#catalog li", has_text=name)
    button = row.get_by_role("button", name="預先載入")
    expect(button).to_be_visible()
    button.click()


def models_preload_warn(w: World) -> None:
    w.ready_with_models({"qwen2.5-coder:32b": (SIZE_32B, False)})
    w.page.goto("/models.html")
    click_preload(w, "qwen2.5-coder:32b")


def models_preloading(w: World) -> None:
    w.ready_with_models({MODEL: (SIZE_0_5B, False)})
    w.gate(w.fakes.remote_ollama.preload)
    w.page.goto("/models.html")
    click_preload(w, MODEL)


def models_preload_failed(w: World) -> None:
    w.ready_with_models({MODEL: (SIZE_0_5B, False)})
    w.fakes.remote_ollama.preload.raises("OLLAMA_SERVER_ERROR", "model requires more system memory")
    w.page.goto("/models.html")
    click_preload(w, MODEL)


# ---------------------------------------------------------------- 下載模型頁


def search_for(w: World, keyword: str) -> None:
    w.page.goto("/library.html")
    expect(w.page.locator("#search-form")).to_be_visible()
    w.page.fill("#q", keyword)
    w.page.locator("#search-form").get_by_role("button", name="搜尋").click()


def type_name(w: World, name: str) -> None:
    w.page.goto("/library.html")
    expect(w.page.locator("#name-form")).to_be_visible()
    w.page.fill("#direct", name)
    w.page.locator("#name-form").get_by_role("button").click()


def add_typed(w: World, name: str) -> None:
    """輸入名稱加入勾選,再按「加入下載」。"""
    type_name(w, name)
    expect(w.page.locator("#tray")).to_be_visible()
    w.page.click("#add")


def library_normal(w: World) -> None:
    w.start()
    w.page.goto("/library.html")


def library_searching(w: World) -> None:
    w.fakes.model_library.search_library.returns(search_page("qwen2.5", has_more=False))
    w.gate(w.fakes.model_library.search_library)
    w.start()
    search_for(w, "qwen2.5")


def library_results(w: World) -> None:
    w.fakes.model_library.search_library.returns(search_page("qwen2.5", "qwen2.5-coder", has_more=True))
    w.start()
    search_for(w, "qwen2.5")


def library_no_results(w: World) -> None:
    w.fakes.model_library.search_library.returns(search_page(has_more=False))
    w.start()
    search_for(w, "qwne")


def library_down(w: World) -> None:
    w.fakes.model_library.search_library.raises("LIBRARY_BAD_RESPONSE", "search page changed")
    w.start()
    search_for(w, "qwen2.5")


def library_checking(w: World) -> None:
    w.ready()
    w.fakes.model_library.get_manifest.returns({"sizeBytes": SIZE_0_5B})
    w.gate(w.fakes.model_library.get_manifest)
    type_name(w, MODEL)


def library_confirm(w: World) -> None:
    w.ready()
    w.fakes.model_library.get_manifest.returns({"sizeBytes": SIZE_0_5B})
    add_typed(w, MODEL)


def library_no_space(w: World) -> None:
    w.ready()
    w.fakes.model_library.get_manifest.returns({"sizeBytes": SIZE_405B})
    add_typed(w, "llama3.1:405b")


def library_not_found(w: World) -> None:
    w.ready()
    w.fakes.model_library.get_manifest.raises("LIBRARY_NOT_FOUND", "manifest unknown")
    type_name(w, "qwen2.5:cgb-test-nonexistent")


def library_cloud_only(w: World) -> None:
    w.ready()
    w.fakes.model_library.get_manifest.raises("LIBRARY_CLOUD_ONLY", "cloud only")
    type_name(w, "qwen3-coder:480b-cloud")


def library_no_session(w: World) -> None:
    # 沒有就緒的工作階段:從精選清單勾一個,按「加入下載」
    w.start()
    with w.api() as client:
        assert client.post("/api/curated", json={"name": MODEL}).status_code == 201
    w.page.goto("/library.html")
    w.page.locator(f'#curated [data-pick="{MODEL}"]').check()
    w.page.click("#add")


# ---------------------------------------------------------------- 用量頁


def usage_normal(w: World) -> None:
    w.fakes.colab.get_usage.returns(reading(381.66, 1.15))
    w.start()
    w.page.goto("/usage.html")


def usage_low(w: World) -> None:
    w.fakes.colab.get_usage.returns(reading(9.50, 1.15))
    w.start()
    w.page.goto("/usage.html")


def usage_unknown(w: World) -> None:
    w.fakes.colab.get_usage.raises("COLAB_UNREACHABLE", "colab usage: connection refused")
    w.start()
    w.page.goto("/usage.html")


def usage_stale(w: World) -> None:
    w.fakes.colab.get_usage.then(reading(381.66, 1.15))
    w.fakes.colab.get_usage.raises("COLAB_TIMEOUT", "colab usage timed out")
    w.start()
    w.page.goto("/usage.html")
    expect(w.page.locator('[data-state="normal"]')).to_be_visible()
    w.clock.advance(16 * 60)


def usage_loading(w: World) -> None:
    w.fakes.colab.get_usage.returns(reading(381.66, 1.15))
    first_read = w.gate(w.fakes.colab.get_usage)
    w.start()
    first_read.wait_entered()
    w.page.goto("/usage.html")


SCREENS: list[tuple[str, str, Callable[[World], None]]] = [
    ("index", "normal", home_normal),
    ("index", "low-balance", home_low_balance),
    ("index", "needs-login", home_needs_login),
    ("index", "starting", home_starting),
    ("index", "ready", home_ready),
    ("index", "confirm-stop", home_confirm_stop),
    ("index", "confirm-switch", home_confirm_switch),
    ("index", "stopping", home_stopping),
    ("index", "switching", home_switching),
    ("index", "ended", home_ended),
    ("index", "ended-idle", home_ended_idle),
    ("index", "failed", home_failed),
    ("index", "already-open", home_already_open),
    ("index", "reconnecting", home_reconnecting),
    ("index", "lost", home_lost),
    ("index", "lost-timeout", home_lost_timeout),
    ("index", "lost-zero", home_lost_zero),
    ("index", "release-failed", home_release_failed),
    ("index", "resuming", home_resuming),
    ("index", "foreign", home_foreign),
    ("login", "normal", login_normal),
    ("login", "signed-in", login_signed_in),
    ("login", "loading", login_loading),
    ("login", "link", login_link),
    ("login", "verifying", login_verifying),
    ("login", "failed", login_rejected("OAUTH_INVALID_GRANT")),
    ("login", "link-expired", login_link_expired),
    ("login", "scope-missing", login_rejected("OAUTH_SCOPE_NOT_GRANTED")),
    ("login", "unreachable", login_rejected("OAUTH_UNREACHABLE")),
    ("history", "normal", history_normal),
    ("history", "empty", history_empty),
    ("models", "normal", models_normal),
    ("models", "empty", models_empty),
    ("models", "loading", models_loading),
    ("models", "no-session", models_no_session),
    ("models", "preload-warn", models_preload_warn),
    ("models", "preloading", models_preloading),
    ("models", "preload-failed", models_preload_failed),
    ("library", "normal", library_normal),
    ("library", "searching", library_searching),
    ("library", "results", library_results),
    ("library", "no-results", library_no_results),
    ("library", "library-down", library_down),
    ("library", "checking", library_checking),
    ("library", "confirm", library_confirm),
    ("library", "no-space", library_no_space),
    ("library", "not-found", library_not_found),
    ("library", "cloud-only", library_cloud_only),
    ("library", "no-session", library_no_session),
    ("usage", "normal", usage_normal),
    ("usage", "low", usage_low),
    ("usage", "unknown", usage_unknown),
    ("usage", "stale", usage_stale),
    ("usage", "loading", usage_loading),
]

# 「預先載入中」照 T235b 畫在目錄那一列(載入中的標示),不是另一個區塊
STATE_LOCATORS = {("models", "preloading"): '[data-state="normal"] #catalog .pill-busy'}


def test_畫面狀態清單涵蓋原型的每一個狀態() -> None:
    """Q111、Q117:原型的六頁每個 `data-state` 都要走到(清單漏了就不算看過那一頁)。"""
    from pathlib import Path

    prototype = Path(__file__).resolve().parents[2] / "specs" / "001-session-model-catalog" / "prototype"
    expected = {
        (name, state)
        for name in ("index", "login", "history", "models", "library", "usage")
        for state in re.findall(r'data-state="([a-z-]+)"', (prototype / f"{name}.html").read_text(encoding="utf-8"))
    }
    assert expected == {(name, state) for name, state, _ in SCREENS}


@pytest.mark.parametrize(("screen", "state", "drive"), [pytest.param(*s, id=f"{s[0]}-{s[1]}") for s in SCREENS])
def test_每一頁每個畫面狀態的可見文字是繁體中文與台灣用語(w: World, screen: str, state: str, drive: Callable[[World], None]) -> None:
    # Arrange、Act:照使用者會走的路走到這個狀態
    drive(w)
    shown = w.page.locator(STATE_LOCATORS.get((screen, state), f'[data-state="{state}"]'))
    expect(shown.first).to_be_visible()
    text = w.page.locator("body").inner_text()
    lang = w.page.locator("html").get_attribute("lang")

    # Assert
    assert [word for word in SIMPLIFIED_OR_MAINLAND if word in text] == [], text
    assert CJK.search(text)
    assert lang in HTML_LANGS, f"{screen}.html 的 <html lang> 是 {lang!r}"


# ================================================================ 則2:UI API 的每一個錯誤代碼


def trigger_ok(w: World, method: str, path: str, **kwargs: Any) -> httpx.Response:
    with w.api() as client:
        return client.request(method, f"/api{path}", **kwargs)


def err_invalid_request_body(w: World) -> httpx.Response:
    w.start()
    return trigger_ok(w, "PUT", "/settings", content=b"{not json", headers={"Content-Type": "application/json"})


def err_session_already_active(w: World) -> httpx.Response:
    w.start()
    w.gate(w.fakes.colab.create_session)
    trigger_ok(w, "POST", "/session", json=T4)
    return trigger_ok(w, "POST", "/session", json=T4)


def err_session_ending(w: World) -> httpx.Response:
    w.start()
    w.open_via_api()
    stop = w.gate(w.fakes.colab.stop_session)
    trigger_ok(w, "DELETE", "/session")
    stop.wait_entered()
    return trigger_ok(w, "POST", "/session", json=T4)


def err_auth_required(w: World) -> httpx.Response:
    w.fakes.colab.get_usage.raises("AUTH_REQUIRED", "colab needs login")
    w.start()
    return trigger_ok(w, "POST", "/session", json=T4)


def err_no_active_session(w: World) -> httpx.Response:
    w.start()
    return trigger_ok(w, "DELETE", "/session")


def err_auth_link_expired(w: World) -> httpx.Response:
    w.start()
    return trigger_ok(w, "POST", "/auth/authorizations/cgb-test-gone/code", json={"code": "4/cgb-test-code"})


def err_oauth(code: str) -> Callable[[World], httpx.Response]:
    def trigger(w: World) -> httpx.Response:
        google_flows(w.fakes)
        w.fakes.google_oauth.request_token.raises(code, code.lower())
        w.start()
        flow = trigger_ok(w, "POST", "/auth/authorizations").json()
        return trigger_ok(w, "POST", f"/auth/authorizations/{flow['flowId']}/code", json={"code": "4/cgb-test-code"})

    return trigger


def err_session_not_found(w: World) -> httpx.Response:
    w.start()
    return trigger_ok(w, "GET", "/sessions/cgb-test-nonexistent")


def err_invalid_runtime_type(w: World) -> httpx.Response:
    w.start()
    return trigger_ok(w, "POST", "/session", json={"runtimeType": {"gpu": "V100", "highMem": False}})


def err_no_ready_session(w: World) -> httpx.Response:
    w.start()
    return trigger_ok(w, "GET", "/models")


def err_invalid_curated_description(w: World) -> httpx.Response:
    w.start()
    return trigger_ok(w, "POST", "/curated", json={"name": MODEL, "description": "長" * 201})


def err_curated_duplicate(w: World) -> httpx.Response:
    w.start()
    trigger_ok(w, "POST", "/curated", json={"name": MODEL})
    return trigger_ok(w, "POST", "/curated", json={"name": MODEL})


def ready_api(w: World, models: dict[str, tuple[int, bool]] | None = None) -> None:
    w.start()
    w.open_via_api()
    w.colab.models = dict(models or {})
    w.fakes.model_library.get_manifest.returns({"sizeBytes": SIZE_0_5B})


def err_ollama_not_found(w: World) -> httpx.Response:
    ready_api(w)
    return trigger_ok(w, "POST", "/models/preload", json={"name": "qwen2.5:cgb-test-nonexistent"})


def err_model_already_downloaded(w: World) -> httpx.Response:
    ready_api(w, {MODEL: (SIZE_0_5B, False)})
    return trigger_ok(w, "POST", "/downloads", json={"models": [MODEL]})


def gated_pull(w: World) -> None:
    gate = Gate()
    w.gates.append(gate)
    w.fakes.remote_ollama.pull_model.returns([{"status": "pulling manifest"}, gate, {"status": "success"}])


def err_download_already_queued(w: World) -> httpx.Response:
    ready_api(w)
    gated_pull(w)
    trigger_ok(w, "POST", "/downloads", json={"models": [MODEL]})
    return trigger_ok(w, "POST", "/downloads", json={"models": [MODEL]})


def err_download_in_progress(w: World) -> httpx.Response:
    ready_api(w)
    gated_pull(w)
    job = trigger_ok(w, "POST", "/downloads", json={"models": [MODEL]}).json()["jobs"][0]
    with w.api() as client:
        wait_until(lambda: client.get("/api/downloads").json()["jobs"][0]["state"] == "downloading", "沒有開始下載")
    return trigger_ok(w, "DELETE", f"/downloads/{job['id']}")


def err_disk_space_insufficient(w: World) -> httpx.Response:
    ready_api(w)
    w.fakes.model_library.get_manifest.returns({"sizeBytes": SIZE_405B})
    return trigger_ok(w, "POST", "/downloads", json={"models": ["llama3.1:405b"]})


def err_disk_space_unknown(w: World) -> httpx.Response:
    ready_api(w)
    w.fakes.colab.probe_resources.raises("COLAB_EXEC_FAILED", "df: not found")
    return trigger_ok(w, "POST", "/downloads/estimate", json={"models": [MODEL]})


def err_manifest(code: str) -> Callable[[World], httpx.Response]:
    def trigger(w: World) -> httpx.Response:
        ready_api(w)
        w.fakes.model_library.get_manifest.raises(code, code.lower())
        return trigger_ok(w, "POST", "/downloads/estimate", json={"models": [MODEL]})

    return trigger


def err_search(code: str) -> Callable[[World], httpx.Response]:
    def trigger(w: World) -> httpx.Response:
        w.fakes.model_library.search_library.raises(code, code.lower())
        w.start()
        return trigger_ok(w, "GET", "/library/search", params={"q": "qwen2.5", "page": 1})

    return trigger


def err_settings(body: dict[str, Any]) -> Callable[[World], httpx.Response]:
    def trigger(w: World) -> httpx.Response:
        w.start()
        return trigger_ok(w, "PUT", "/settings", json=body)

    return trigger


# 本系統做得出來的每一個錯誤代碼(= `MESSAGES` 的每一個 key);合約列了、後端還沒有產生的代碼見回報(plan.md Q178)
API_ERRORS: list[tuple[str, Callable[[World], httpx.Response]]] = [
    ("INVALID_REQUEST_BODY", err_invalid_request_body),
    ("SESSION_ALREADY_ACTIVE", err_session_already_active),
    ("SESSION_ENDING", err_session_ending),
    ("AUTH_REQUIRED", err_auth_required),
    ("NO_ACTIVE_SESSION", err_no_active_session),
    ("AUTH_LINK_EXPIRED", err_auth_link_expired),
    *[
        (code, err_oauth(code))
        for code in (
            "OAUTH_INVALID_GRANT",
            "OAUTH_SCOPE_NOT_GRANTED",
            "OAUTH_TIMEOUT",
            "OAUTH_UNREACHABLE",
            "OAUTH_SERVER_ERROR",
            "OAUTH_BAD_RESPONSE",
            "OAUTH_INVALID_REQUEST",
            "OAUTH_INVALID_CLIENT",
            "OAUTH_UNAUTHORIZED_CLIENT",
            "OAUTH_UNSUPPORTED_GRANT_TYPE",
            "OAUTH_INVALID_SCOPE",
        )
    ],
    ("SESSION_NOT_FOUND", err_session_not_found),
    ("INVALID_RUNTIME_TYPE", err_invalid_runtime_type),
    ("NO_READY_SESSION", err_no_ready_session),
    ("INVALID_CURATED_DESCRIPTION", err_invalid_curated_description),
    ("CURATED_DUPLICATE", err_curated_duplicate),
    ("OLLAMA_NOT_FOUND", err_ollama_not_found),
    ("MODEL_ALREADY_DOWNLOADED", err_model_already_downloaded),
    ("DOWNLOAD_ALREADY_QUEUED", err_download_already_queued),
    ("DISK_SPACE_INSUFFICIENT", err_disk_space_insufficient),
    ("DISK_SPACE_UNKNOWN", err_disk_space_unknown),
    ("DOWNLOAD_IN_PROGRESS", err_download_in_progress),
    ("LIBRARY_NOT_FOUND", err_manifest("LIBRARY_NOT_FOUND")),
    ("LIBRARY_UNREACHABLE", err_search("LIBRARY_UNREACHABLE")),
    ("LIBRARY_SERVER_ERROR", err_search("LIBRARY_SERVER_ERROR")),
    ("LIBRARY_BAD_RESPONSE", err_search("LIBRARY_BAD_RESPONSE")),
    ("LIBRARY_TIMEOUT", err_search("LIBRARY_TIMEOUT")),
    ("LIBRARY_CLOUD_ONLY", err_manifest("LIBRARY_CLOUD_ONLY")),
    ("INVALID_IDLE_TIMEOUT", err_settings({"idleTimeoutMinutes": 0, "lowBalanceThreshold": 10})),
    ("INVALID_BALANCE_THRESHOLD", err_settings({"idleTimeoutMinutes": 30, "lowBalanceThreshold": -1})),
]


def test_錯誤代碼清單涵蓋本系統的每一個錯誤代碼() -> None:
    assert sorted(code for code, _ in API_ERRORS) == sorted(MESSAGES)


@pytest.mark.parametrize(("code", "trigger"), [pytest.param(*e, id=e[0]) for e in API_ERRORS])
def test_UI_API每一個錯誤代碼的說明至少含一個中文字(w: World, code: str, trigger: Callable[[World], httpx.Response]) -> None:
    # Act
    response = trigger(w)

    # Assert
    assert response.status_code >= 400, response.text
    body = response.json()
    assert body.get("code") == code, response.text
    assert CJK.search(body.get("message") or ""), response.text


# ================================================================ 則3:Ollama 相容端點本系統自己產生的錯誤

OLLAMA_URL = f"http://127.0.0.1:{E2E_OLLAMA_PORT}"
GENERATE = {"model": MODEL, "prompt": "你好"}
FIRST_LINE = {"model": MODEL, "created_at": "2026-11-09T09:00:00Z", "response": "你", "done": False}


def last_error(response: httpx.Response) -> str:
    """NDJSON 的最後一行(或整個 JSON 本文)的 `error`。"""
    lines = [line for line in response.text.splitlines() if line.strip()]
    return json.loads(lines[-1]).get("error") or ""


def oc_managed(w: World) -> str:
    w.start()
    return httpx.post(f"{OLLAMA_URL}/api/pull", json={"model": MODEL}).json()["error"]


def oc_unlisted(w: World) -> str:
    w.start()
    return httpx.get(f"{OLLAMA_URL}/v1/models").json()["error"]


def oc_no_ready_session(w: World) -> str:
    w.start()
    return httpx.post(f"{OLLAMA_URL}/api/generate", json=GENERATE).json()["error"]


def oc_unreachable(w: World) -> str:
    # 通道回報的轉發位址沒有人在聽
    nobody = unreachable_base_url()
    w.fakes.tunnel.open_tunnel.side_effect(
        lambda *a, **k: {
            "sessionName": k["session_name"],
            "baseUrl": nobody,
            "remoteOllamaVersion": "0.40.15",
            "connectedAt": "2026-11-09T09:00:00Z",
            "elapsedMs": 0,
        }
    )
    w.start()
    w.open_via_api()
    return httpx.post(f"{OLLAMA_URL}/api/generate", json=GENERATE).json()["error"]


def oc_stream_interrupted(w: World) -> str:
    w.start()
    w.open_via_api()
    w.fakes.server.add("POST", "/api/generate", NdjsonReply([FIRST_LINE], then="disconnect"))
    return last_error(httpx.post(f"{OLLAMA_URL}/api/generate", json=GENERATE, timeout=10))


def oc_session_ended(w: World) -> str:
    # 串流進行中使用者按「結束」
    w.start()
    w.open_via_api()
    hang = Gate()
    w.gates.append(hang)
    w.fakes.server.add("POST", "/api/generate", NdjsonReply([FIRST_LINE], then="hang", release=hang))
    result: dict[str, httpx.Response] = {}
    request = threading.Thread(
        target=lambda: result.setdefault("r", httpx.post(f"{OLLAMA_URL}/api/generate", json=GENERATE, timeout=10))
    )
    request.start()
    wait_until(lambda: len(w.fakes.server.requests_to("POST", "/api/generate")) == 1, "請求沒有轉送到遠端")
    trigger_ok(w, "DELETE", "/session")
    request.join(timeout=10)
    return last_error(result["r"])


OLLAMA_ERRORS: list[tuple[str, Callable[[World], str]]] = [
    ("管理模型的操作", oc_managed),
    ("白名單外的路徑", oc_unlisted),
    ("沒有就緒的工作階段", oc_no_ready_session),
    ("連不到執行環境上的模型服務", oc_unreachable),
    ("串流中途斷線", oc_stream_interrupted),
    ("串流中途工作階段結束", oc_session_ended),
]


@pytest.mark.parametrize(("kind", "trigger"), [pytest.param(*e, id=e[0]) for e in OLLAMA_ERRORS])
def test_Ollama相容端點本系統產生的錯誤至少含一個中文字(w: World, kind: str, trigger: Callable[[World], str]) -> None:
    # Act
    error = trigger(w)

    # Assert
    assert CJK.search(error), f"{kind}:{error!r}"
