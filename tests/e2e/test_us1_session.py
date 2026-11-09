"""跨端點驗收:首頁(工作階段面板)(testplan.md § 2.11)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨、plan.md Q99)。
"""

import re
import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from playwright.sync_api import BrowserContext, Page, expect

from cgb.adapters.errors import AdapterError
from fakes import Gate

# 至少一個中日韓統一表意文字:給使用者看的原因是繁體中文,不是代碼本身
CJK = re.compile(r"[\u4e00-\u9fff]")


class ColabWorld:
    """替身背後一個最小的 Colab 帳號:記得哪些執行環境還在。

    `create_session` 成功就把名稱加進 `colab sessions`,`stop_session` 成功就拿掉;
    測試要改某一次的結果時,照替身的 `then()`、`raises()`、`when()` 覆寫。
    """

    def __init__(self, fakes: Any) -> None:
        self.fakes = fakes
        self.alive: list[str] = []
        self.unnamed: list[dict[str, str]] = []
        # 目前這台執行環境上的模型:名稱 → (大小, 是否已載入);新開的執行環境是空的
        self.models: dict[str, tuple[int, bool]] = {}
        # `colab stop` 回報成功、`colab sessions` 卻仍列著的名稱(遺留)
        self.stuck: set[str] = set()
        colab, tunnel, remote = fakes.colab, fakes.tunnel, fakes.remote_ollama
        colab.get_usage.side_effect(self._usage)
        colab.list_sessions.side_effect(self._list)
        colab.create_session.side_effect(self._create)
        colab.start_ollama.side_effect(lambda *a, **k: {"ollamaVersion": "0.40.15", "alreadyRunning": False})
        colab.stop_session.side_effect(self._stop)
        tunnel.open_tunnel.side_effect(self._open_tunnel)
        tunnel.close_tunnel.side_effect(lambda *a, **k: {"sessionName": k.get("session_name"), "wasRunning": True, "forced": False})
        tunnel.check_health.side_effect(self._healthy)
        tunnel.cleanup_residual.side_effect(lambda *a, **k: {"killed": 0})
        remote.get_version.side_effect(lambda *a, **k: {"version": "0.40.15"})
        remote.list_local_models.side_effect(self._local_models)
        remote.list_loaded_models.side_effect(self._loaded_models)
        remote.pull_model.side_effect(self._pull)
        remote.preload.side_effect(self._preload)

    def _usage(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"balance": 100.0, "ratePerHour": 1.76, "activeAssignments": len(self.alive), "readAt": "2026-11-09T09:00:00Z"}

    def _list(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "named": [{"name": n, "hardware": "T4", "shape": "Standard", "variant": "GPU"} for n in self.alive],
            "unnamed": [dict(u) for u in self.unnamed],
        }

    def _create(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.alive.append(kwargs["name"])
        self.models = {}
        return {"name": kwargs["name"], "hardware": kwargs["gpu"], "shape": "Standard", "highMemIgnored": False}

    def _stop(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs["name"] in self.alive and kwargs["name"] not in self.stuck:
            self.alive.remove(kwargs["name"])
        return {"name": kwargs["name"], "stopOutput": "terminated"}

    def _open_tunnel(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "sessionName": kwargs["session_name"],
            "baseUrl": self.fakes.server.base_url,
            "remoteOllamaVersion": "0.40.15",
            "connectedAt": "2026-11-09T09:00:00Z",
            "elapsedMs": 0,
        }

    def _healthy(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "sessionName": kwargs.get("session_name"),
            "healthy": True,
            "remoteOllamaVersion": "0.40.15",
            "checkedAt": "2026-11-09T09:00:00Z",
            "latencyMs": 1,
        }

    def _local_models(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "models": [
                {"name": n, "model": n, "modified_at": "2026-11-09T09:00:00Z", "size": size, "digest": "cgb-test"}
                for n, (size, _) in self.models.items()
            ]
        }

    def _loaded_models(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "models": [
                {"name": n, "model": n, "size": size, "digest": "cgb-test", "expires_at": "2318-11-09T09:00:00Z", "size_vram": size}
                for n, (size, loaded) in self.models.items()
                if loaded
            ]
        }

    def _pull(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.models[kwargs["model"]] = (397821319, False)
        return [{"status": "pulling manifest"}, {"status": "success"}]

    def _preload(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        size, _ = self.models[kwargs["model"]]
        self.models[kwargs["model"]] = (size, True)
        return {"model": kwargs["model"], "done": True}

    def gate_open_steps(self) -> list[Gate]:
        """開啟的三個步驟(配置、啟動 Ollama、建立通道)各自等測試放行。"""
        return [
            self.fakes.colab.create_session.gate(),
            self.fakes.colab.start_ollama.gate(),
            self.fakes.tunnel.open_tunnel.gate(),
        ]


@pytest.fixture
def world(fakes: Any) -> ColabWorld:
    return ColabWorld(fakes)


def release_in_order(gates: list[Gate]) -> None:
    for gate in gates:
        gate.wait_entered()
        gate.release()


# ---------------------------------------------------------------- US1-AJ-01


def test_不改類型按開啟_看得到開啟中的步驟並以T4就緒(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    gates = world.gate_open_steps()
    page.goto("/")
    open_panel = page.locator('[data-state="normal"]')
    expect(open_panel.locator('input[type="radio"][value="T4"]')).to_be_checked()
    expect(open_panel.locator('input[type="checkbox"][name^="highmem"]')).not_to_be_checked()

    # Act
    page.click("#open")
    expect(page.locator('[data-state="starting"]')).to_be_visible()
    expect(page.locator("#s-steps li.current")).to_have_text("在 Colab 配置 T4 執行環境")
    release_in_order(gates)

    # Assert
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    expect(page.locator("#r-type")).to_contain_text("T4")
    assert fakes.colab.create_session.last_call.kwargs["gpu"] == "T4"


# ---------------------------------------------------------------- US1-AJ-10


def test_選G4並勾高RAM開啟_請求帶上選的類型且就緒畫面顯示G4高RAM(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    page.goto("/")
    open_panel = page.locator('[data-state="normal"]')
    open_panel.locator('input[type="radio"][value="G4"]').check()
    open_panel.locator('input[type="checkbox"][name^="highmem"]').check()

    # Act
    page.click("#open")

    # Assert
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    kwargs = fakes.colab.create_session.last_call.kwargs
    assert kwargs["gpu"] == "G4"
    assert kwargs["high_mem"] is True
    expect(page.locator("#r-type")).to_contain_text("G4")
    expect(page.locator("#r-type")).to_contain_text("高 RAM")


def open_to_ready(page: Page) -> None:
    """打開首頁,以預設類型開到就緒。"""
    page.goto("/")
    page.click("#open")
    expect(page.locator('[data-state="ready"]')).to_be_visible()


# ---------------------------------------------------------------- US1-AJ-02


def test_結束工作階段要先確認_取消不結束_確認後顯示使用者結束(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    ready = page.locator('[data-state="ready"]')
    end_button = ready.get_by_role("button", name="結束", exact=True)
    confirm = page.locator('[data-state="confirm-stop"]')

    # Act
    expect(end_button).to_be_visible()
    end_button.click()
    expect(confirm).to_be_visible()
    confirm.get_by_role("button", name="取消").click()
    expect(ready).to_be_visible()
    stops_after_cancel = fakes.colab.stop_session.call_count
    end_button.click()
    page.click("#stop")

    # Assert
    assert stops_after_cancel == 0
    expect(page.locator('[data-state="ended"]')).to_be_visible()
    expect(page.locator("#e-reason")).to_have_text("使用者結束")


# ---------------------------------------------------------------- US1-AJ-03


def test_配置被拒時顯示開啟失敗與中文原因_而且可以再開啟(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    fakes.colab.create_session.then(AdapterError("COLAB_ALLOCATION_REFUSED", "Colab refused to allocate"))
    page.goto("/")
    failed = page.locator('[data-state="failed"]')

    # Act
    page.click("#open")

    # Assert
    expect(failed).to_be_visible()
    expect(page.locator("#f-reason")).to_have_text(CJK)
    expect(page.locator("#f-reason")).not_to_contain_text("COLAB_")
    failed.get_by_role("button", name="改選類型重新開啟").click()
    page.click("#open")
    expect(page.locator('[data-state="ready"]')).to_be_visible()


# ---------------------------------------------------------------- US1-AJ-04


def test_被Colab收回時不必重新整理就顯示失聯_重新開啟後進入開啟中(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    lost = page.locator('[data-state="lost"]')

    # Act
    world.alive.clear()
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))
    expect(lost).to_be_visible()
    create_gate = fakes.colab.create_session.gate()
    lost.get_by_role("button", name="重新開啟").click()

    # Assert
    expect(lost).to_contain_text("被 Colab 收回")
    expect(page.locator('[data-state="starting"]')).to_be_visible()
    create_gate.release()


# ---------------------------------------------------------------- US1-AJ-05


def test_連線中斷時顯示重連中_接回後是同一個工作階段(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    name_before = page.locator("#r-name").inner_text()
    reconnect_gate = fakes.tunnel.open_tunnel.gate()
    fakes.tunnel.open_tunnel.then(AdapterError("TUNNEL_FAILED", "ssh exited"))

    # Act
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))
    expect(page.locator('[data-state="reconnecting"]')).to_be_visible()
    reconnect_gate.release()

    # Assert
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    expect(page.locator("#r-name")).to_have_text(name_before)


# ---------------------------------------------------------------- US1-AJ-06


def test_重連逾時且釋放不了時_畫面警告可能還在扣點並可再試一次釋放(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    fakes.tunnel.open_tunnel.raises("TUNNEL_FAILED", "ssh exited")
    fakes.colab.stop_session.raises("COLAB_STOP_UNCONFIRMED", "colab sessions still lists it")
    warning = page.locator('[data-state="release-failed"]')

    # Act
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))

    # Assert
    expect(page.locator('[data-state="lost-timeout"]')).to_contain_text("重連逾時", timeout=10_000)
    expect(warning).to_be_visible()
    expect(warning).to_contain_text("沒辦法確認執行環境已經釋放")
    expect(warning.get_by_role("button", name="再試一次釋放")).to_be_enabled()


# ---------------------------------------------------------------- US1-AJ-07


def test_另一個分頁按開啟時顯示目前已有工作階段_不會再開一台(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:第二個分頁收不到推送,畫面停在打開時的「未開啟」,只能靠後端擋
    second = context.new_page()
    second.route("**/api/events", lambda route: route.abort())
    second.goto("/")
    create_gate = fakes.colab.create_session.gate()
    page.goto("/")
    page.click("#open")
    create_gate.wait_entered()

    # Act
    expect(second.locator("#open")).to_be_visible()
    second.click("#open")

    # Assert
    expect(second.locator('[data-state="already-open"]')).to_contain_text("目前已有工作階段")
    assert fakes.colab.create_session.call_count == 1
    create_gate.release()


# ---------------------------------------------------------------- US1-AJ-11


def test_變更類型要先確認_重開成L4後原本載入的模型又在目錄上(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    world.models = {"qwen2.5:0.5b": (397821319, True)}
    create_gate = fakes.colab.create_session.gate()
    switch_button = page.locator('[data-state="ready"]').get_by_role("button", name="變更類型")
    confirm = page.locator('[data-state="confirm-switch"]')

    # Act
    expect(switch_button).to_be_visible()
    switch_button.click()
    expect(confirm).to_contain_text("會結束目前的工作階段並重開")
    confirm.locator('input[type="radio"][value="L4"]').check()
    page.click("#switch")
    expect(page.locator('[data-state="starting"]')).to_be_visible()
    expect(page.locator("#s-steps")).to_contain_text("結束原本的 T4 執行環境")
    create_gate.release()
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    expect(page.locator("#r-type")).to_contain_text("L4")
    page.goto("/models.html")

    # Assert
    loaded = page.locator("#catalog li", has_text="qwen2.5:0.5b")
    expect(loaded).to_contain_text("已載入")


# ---------------------------------------------------------------- US1-AJ-12


def test_變更類型開不起來時顯示開啟失敗並說明原本的T4已經結束(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    fakes.colab.create_session.when(gpu="L4").raises("COLAB_ACCELERATOR_REJECTED", "L4 is not available")
    failed = page.locator('[data-state="failed"]')

    # Act
    page.locator('[data-state="ready"]').get_by_role("button", name="變更類型").click()
    page.locator('[data-state="confirm-switch"] input[type="radio"][value="L4"]').check()
    page.click("#switch")

    # Assert
    expect(failed).to_be_visible()
    expect(page.locator("#f-reason")).to_have_text(CJK)
    expect(failed).to_contain_text("原本的 T4 執行環境在變更類型時已經結束")


def restart_backend(e2e_servers: Any, start_live_servers: Callable[..., Any], make_app: Callable[..., Any]) -> Any:
    """停掉測試行程內的 uvicorn,以同一個 SQLite 檔與同一份替身在同樣的 port 重新起。"""
    e2e_servers.stop()
    return start_live_servers(make_app(), ui_port=e2e_servers.ui_port, ollama_port=e2e_servers.ollama_port)


# ---------------------------------------------------------------- US1-AJ-14


def test_後端重新啟動後重新整理首頁仍是同一個就緒的工作階段(
    page: Page,
    e2e_servers: Any,
    start_live_servers: Callable[..., Any],
    make_app: Callable[..., Any],
    world: ColabWorld,
    fakes: Any,
) -> None:
    # Arrange
    open_to_ready(page)
    name_before = page.locator("#r-name").inner_text()

    # Act
    restart_backend(e2e_servers, start_live_servers, make_app)
    page.reload()

    # Assert
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    expect(page.locator("#r-name")).to_have_text(name_before)
    assert fakes.colab.create_session.call_count == 1



# ---------------------------------------------------------------- US1-AJ-15


def test_帳號下有不是本系統開的執行環境時只提示_不提供結束(
    page: Page,
    e2e_servers: Any,
    start_live_servers: Callable[..., Any],
    make_app: Callable[..., Any],
    world: ColabWorld,
) -> None:
    # Arrange:`colab sessions` 列出一台名稱是 `[?]` 的 T4;後端啟動時才會查,所以重新起一次
    world.unnamed = [{"hardware": "T4", "shape": "Standard", "variant": "GPU"}]
    restart_backend(e2e_servers, start_live_servers, make_app)
    foreign = page.locator('[data-state="foreign"]')

    # Act
    page.goto("/")

    # Assert
    expect(foreign).to_contain_text("不是本系統開的執行環境")
    expect(foreign).to_contain_text("T4")
    expect(foreign.get_by_role("button", name=re.compile("結束|中斷|關閉|停止"))).to_have_count(0)


# ---------------------------------------------------------------- US1-AJ-16


def test_開啟中可以停止開啟_配置完成後釋放這次的執行環境(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    create_gate = fakes.colab.create_session.gate()
    page.goto("/")
    page.click("#open")
    expect(page.locator("#s-name")).not_to_be_empty()
    name = page.locator("#s-name").inner_text()
    cancel = page.locator("#cancel-open")

    # Act
    expect(cancel).to_be_visible()
    cancel.click()
    page.click("#stop")
    expect(page.locator('[data-state="stopping"]')).to_be_visible()
    create_gate.release()

    # Assert
    expect(page.locator('[data-state="ended"]')).to_be_visible()
    assert [call.kwargs.get("name") for call in fakes.colab.stop_session.calls] == [name]


T4 = {"runtimeType": {"gpu": "T4", "highMem": False}}


def wait_until(condition: Callable[[], bool], what: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"等了 {timeout} 秒,{what}")
        time.sleep(0.02)


# ---------------------------------------------------------------- US1-AJ-23


def test_重啟接回時釋放遺留失敗會警告_接回與重連沿用同一把金鑰與port(
    page: Page,
    world: ColabWorld,
    fakes: Any,
    e2e_servers: Any,
    start_live_servers: Callable[..., Any],
    make_app: Callable[..., Any],
) -> None:
    # Arrange:先開過一台並結束(Colab 卻還列著它),再開一台到就緒(已結束的畫面沒有開新的入口,兩台都經 API 開)
    with httpx.Client(base_url=e2e_servers.ui_url) as client:
        client.post("/api/session", json=T4)
        wait_until(lambda: client.get("/api/session").json()["state"] == "ready", "第一台沒有就緒")
        leftover = client.get("/api/session").json()["name"]
        world.stuck.add(leftover)
        client.delete("/api/session")
        wait_until(lambda: client.get("/api/session").json()["state"] == "ended", "第一台沒有結束")
        client.post("/api/session", json=T4)
        wait_until(lambda: client.get("/api/session").json()["state"] == "ready", "第二台沒有就緒")
    page.goto("/")
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    current = page.locator("#r-name").inner_text()
    opens = fakes.tunnel.open_tunnel.calls
    first = next(call for call in opens if call.kwargs.get("session_name") == current)
    fakes.colab.stop_session.when(name=leftover).raises("COLAB_STOP_UNCONFIRMED", "colab sessions still lists it")
    opens_before_restart = len(opens)

    # Act:重新起後端;接回之後健康檢查失敗一次,重連第 1 輪就接回
    servers = restart_backend(e2e_servers, start_live_servers, make_app)
    wait_until(lambda: len(fakes.tunnel.open_tunnel.calls) > opens_before_restart, "重啟後沒有重建通道")
    fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))
    wait_until(lambda: len(fakes.tunnel.open_tunnel.calls) > opens_before_restart + 1, "健康檢查失敗後沒有重連")
    with httpx.Client(base_url=servers.ui_url) as client:
        wait_until(lambda: client.get("/api/session").json()["state"] == "ready", "重連後沒有回到就緒")
        session = client.get("/api/session").json()
    page.goto("/")
    reopened = fakes.tunnel.open_tunnel.calls[opens_before_restart:]

    # Assert
    assert session["releaseWarning"] is not None
    assert session["releaseWarning"]["message"] is not None
    assert session["releaseWarning"]["reasonCode"] == "COLAB_STOP_UNCONFIRMED"
    expect(page.locator('[data-state="release-failed"]')).to_be_visible()
    assert [call.kwargs.get("key_path") for call in reopened] == [first.kwargs["key_path"]] * len(reopened)
    assert [call.kwargs.get("local_port") for call in reopened] == [first.kwargs["local_port"]] * len(reopened)
    assert (session["state"], session["name"]) == ("ready", current)
