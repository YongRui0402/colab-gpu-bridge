"""跨端點驗收:首頁的工作階段 → 區網程式經 Ollama 相容端點(testplan.md § 3.7)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781、Ollama 相容端點 127.0.0.1:11437),轉接層用替身;
區網程式以 httpx 對 Ollama 相容端點送請求,轉送真的經過 httpx 打到假 Ollama 伺服器(`FakeTunnel.open_tunnel` 回報的 `baseUrl`)。
"""

import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from playwright.sync_api import Page, expect

from cgb.adapters.errors import AdapterError
from e2e.test_us1_session import ColabWorld, open_to_ready, restart_backend, wait_until, world  # noqa: F401 - `world` 是 fixture
from fakes import JsonReply

GENERATE = {"model": "qwen2.5:0.5b", "prompt": "你好", "stream": False}


@pytest.fixture
def generate_ok(fakes: Any) -> None:
    """假 Ollama 對非串流的 `generate` 回 `cgb-test-ok`。"""
    fakes.server.add("POST", "/api/generate", JsonReply({"model": "qwen2.5:0.5b", "response": "cgb-test-ok", "done": True}))


# ---------------------------------------------------------------- US2-AJ-01


def test_首頁開啟就緒後區網程式經相容端點拿到回應_結束後立即回503(
    page: Page, e2e_servers: Any, world: ColabWorld, generate_ok: None
) -> None:
    # Arrange
    open_to_ready(page)

    # Act
    with httpx.Client(base_url=e2e_servers.ollama_url, timeout=5.0) as client:
        ready_reply = client.post("/api/generate", json=GENERATE)
        page.locator('[data-state="ready"]').get_by_role("button", name="結束", exact=True).click()
        page.click("#stop")
        expect(page.locator('[data-state="ended"]')).to_be_visible()
        started = time.monotonic()
        ended_reply = client.post("/api/generate", json=GENERATE)
        ended_elapsed = time.monotonic() - started

    # Assert
    assert ready_reply.status_code == 200
    assert ready_reply.json()["response"] == "cgb-test-ok"
    assert ended_reply.status_code == 503
    assert "沒有可用的工作階段" in ended_reply.json()["error"]
    assert ended_elapsed < 1.0


# ---------------------------------------------------------------- US2-AJ-05


def test_後端重啟接回與重連之後_相容端點都轉送到新的通道而不是一直回503(
    page: Page,
    e2e_servers: Any,
    start_live_servers: Callable[..., Any],
    make_app: Callable[..., Any],
    world: ColabWorld,
    fakes: Any,
    generate_ok: None,
) -> None:
    # Arrange
    open_to_ready(page)
    opens_before_restart = fakes.tunnel.open_tunnel.call_count

    # Act:重新起後端,等接回(重建通道)後送一次;再讓健康檢查失敗一次,等重連第 1 輪接回後再送一次
    servers = restart_backend(e2e_servers, start_live_servers, make_app)
    states: list[str] = []
    with (
        httpx.Client(base_url=servers.ui_url, timeout=5.0) as ui,
        httpx.Client(base_url=servers.ollama_url, timeout=5.0) as ollama,
    ):

        def session_state() -> str:
            states.append(ui.get("/api/session").json()["state"])
            return states[-1]

        wait_until(lambda: fakes.tunnel.open_tunnel.call_count > opens_before_restart, "重啟後沒有重建通道")
        wait_until(lambda: session_state() == "ready", "重啟接回後沒有就緒")
        after_restart = ollama.post("/api/generate", json=GENERATE)
        fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "remote ollama unreachable"))
        wait_until(lambda: fakes.tunnel.open_tunnel.call_count > opens_before_restart + 1, "健康檢查失敗後沒有重連")
        wait_until(lambda: session_state() == "ready", "重連後沒有回到就緒")
        after_reconnect = ollama.post("/api/generate", json=GENERATE)
        session_state()

    # Assert
    assert after_restart.status_code == 200
    assert after_restart.json()["response"] == "cgb-test-ok"
    assert after_reconnect.status_code == 200
    assert states[-1] == "ready"
