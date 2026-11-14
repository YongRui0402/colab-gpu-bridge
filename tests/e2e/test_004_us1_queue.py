"""跨端點驗收:工作階段結束後,下載佇列不留舊紀錄(004 testplan.md § 2.3)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨、plan.md Q99)。
佇列裡的項目以加入下載(`POST /api/downloads`)與 `fakes.remote_ollama.pull_model` 的閘門鋪出。
"""

import re
import time
from dataclasses import replace
from typing import Any

import httpx
import pytest
from playwright.sync_api import BrowserContext, Locator, Page, expect

from cgb.adapters.errors import AdapterError
from cgb.app import Timeouts
from conftest import TEST_TIMEOUTS
from e2e.test_us1_session import ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture
from fakes import Gate

QWEN = "qwen2.5:latest"
LLAMA = "llama3.2:3b"
HF_SMOL = "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"
# 模型在磁碟上的大小(位元組)
SIZES = {QWEN: 4_683_087_332, LLAMA: 2_019_393_189, HF_SMOL: 105_469_472}


@pytest.fixture
def test_timeouts() -> Timeouts:
    """重連時限縮到 0.3 秒(plan.md Q38):失聯的案例不必等 2 秒;其他案例的健康檢查都通過,不會進入重連。"""
    return replace(TEST_TIMEOUTS, reconnect_limit=0.3)


def set_manifests(fakes: Any) -> None:
    """`get_manifest` 依 `<名稱>:<版本>` 回 `SIZES` 的大小。"""
    fakes.model_library.get_manifest.side_effect(
        lambda *a, **k: {"name": k["name"], "tag": k["tag"], "sizeBytes": SIZES[f"{k['name']}:{k['tag']}"]}
    )


def pulls(world: ColabWorld, fakes: Any, *, fail: tuple[str, ...] = (), hold: tuple[str, ...] = ()) -> Gate:
    """`pull_model` 依模型分流:`fail` 裡的串流中途失敗,`hold` 裡的停在回傳的閘門前(下載中),其他的直接完成並出現在執行環境上。"""
    gate = Gate()

    def pull(*args: Any, **kwargs: Any) -> list[Any]:
        model = kwargs["model"]
        if model in fail:
            return [{"status": "pulling manifest"}, AdapterError("OLLAMA_PULL_FAILED", "pull failed")]
        if model in hold:
            return [{"status": "pulling manifest"}, gate, {"status": "success"}]
        world.models[model] = (SIZES[model], False)
        return [{"status": "pulling manifest"}, {"status": "success"}]

    fakes.remote_ollama.pull_model.side_effect(pull)
    return gate


def enqueue(e2e_servers: Any, *models: str) -> None:
    reply = httpx.post(f"{e2e_servers.ui_url}/api/downloads", json={"models": list(models)}, timeout=5.0)
    assert reply.status_code == 201, reply.text


def queue_rows(page: Page) -> Locator:
    """`#queue` 裡的下載項目(每一列有模型名稱)。"""
    return page.locator("#queue li").filter(has=page.locator(".item-name"))


def queue_row(page: Page, model: str) -> Locator:
    return page.locator("#queue li").filter(has=page.locator(".item-name", has_text=re.compile(rf"^{re.escape(model)}$")))


def jobs(e2e_servers: Any) -> list[dict[str, Any]]:
    return httpx.get(f"{e2e_servers.ui_url}/api/downloads", timeout=5.0).json()["jobs"]


# ---- 004 US1-AJ-01


def test_在另一個分頁結束工作階段_模型頁不重新整理就在5秒內清空佇列(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:完成的 qwen2.5、失敗的 hf.co 模型、停在閘門的 llama3.2:3b
    open_to_ready(page)
    set_manifests(fakes)
    held = pulls(world, fakes, fail=(HF_SMOL,), hold=(LLAMA,))
    enqueue(e2e_servers, QWEN, HF_SMOL, LLAMA)
    page.goto("/models.html")
    expect(queue_row(page, QWEN).locator(".pill")).to_have_text("完成")
    expect(queue_row(page, HF_SMOL).locator(".pill")).to_have_text("失敗")
    expect(queue_row(page, LLAMA).locator(".pill")).to_have_text("下載中")
    expect(queue_rows(page)).to_have_count(3)
    page.evaluate("window.__cgbNotReloaded = true")
    home = context.new_page()
    home.goto("/")

    # Act
    home.locator('[data-state="ready"]').get_by_role("button", name="結束", exact=True).click()
    with home.expect_response(lambda r: r.request.method == "DELETE" and r.url.endswith("/api/session")):
        home.click("#stop")
    answered = time.monotonic()

    # Assert
    expect(queue_rows(page)).to_have_count(0, timeout=5_000)
    assert time.monotonic() - answered <= 5.0
    assert page.evaluate("window.__cgbNotReloaded === true")
    assert jobs(e2e_servers) == []
    held.release()


def lose_connection_until_timeout(fakes: Any) -> None:
    """健康檢查一直失敗、重連每一輪都建不起通道:重連時限到了就變成失聯(`RECONNECT_TIMEOUT`)。"""
    fakes.tunnel.open_tunnel.raises("TUNNEL_FAILED", "ssh exited")
    fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "remote ollama unreachable")


def catalog_row(page: Page, name: str) -> Locator:
    return page.locator("#catalog li").filter(has=page.locator(".item-name", has_text=re.compile(rf"^{re.escape(name)}$")))


# ---- 004 US1-AJ-02


def test_重連逾時而失聯時_模型頁不重新整理就清空佇列_目錄也沒有下載中的那個模型(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any, fake_clock: Any
) -> None:
    # Arrange:qwen2.5 下載中(已推過一則 10% 的進度後停在閘門),llama3.2:3b 排隊中
    open_to_ready(page)
    set_manifests(fakes)
    before_progress, after_progress = Gate(), Gate()
    total = SIZES[QWEN]
    fakes.remote_ollama.pull_model.side_effect(
        lambda *a, **k: [
            {"status": "pulling manifest"},
            before_progress,
            {"status": "pulling cgb-test", "digest": "sha256:cgb-test", "total": total, "completed": (total + 9) // 10},
            after_progress,
            {"status": "success"},
        ]
    )
    enqueue(e2e_servers, QWEN, LLAMA)
    before_progress.wait_entered()
    fake_clock.advance(1.0)  # 進度最多每秒推一則
    before_progress.release()
    after_progress.wait_entered()
    page.goto("/models.html")
    expect(queue_row(page, QWEN).locator("[data-progress-text]")).to_contain_text("下載中 10%")
    expect(queue_row(page, LLAMA).locator(".pill")).to_have_text("排隊中")
    expect(queue_rows(page)).to_have_count(2)

    # Act
    lose_connection_until_timeout(fakes)
    expect(page.locator("#session-pill")).to_contain_text("失聯", timeout=10_000)
    lost_at = time.monotonic()

    # Assert
    expect(queue_rows(page)).to_have_count(0, timeout=5_000)
    assert time.monotonic() - lost_at <= 5.0
    expect(catalog_row(page, QWEN)).to_have_count(0)
    after_progress.release()


# ---- 004 US1-AJ-03


def test_變更類型後模型頁不重新整理_佇列只剩要重新載入的那一個模型(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:已載入 qwen2.5;佇列另有完成的 llama3.2:3b
    open_to_ready(page)
    world.models = {QWEN: (SIZES[QWEN], True)}
    set_manifests(fakes)
    pulls(world, fakes)
    enqueue(e2e_servers, LLAMA)
    page.goto("/models.html")
    expect(queue_row(page, LLAMA).locator(".pill")).to_have_text("完成")
    home = context.new_page()
    home.goto("/")

    # Act
    home.locator('[data-state="ready"]').get_by_role("button", name="變更類型").click()
    home.locator('[data-state="confirm-switch"] input[type="radio"][value="L4"]').check()
    home.click("#switch")
    expect(home.locator('[data-state="ready"]')).to_be_visible(timeout=10_000)
    expect(home.locator("#r-type")).to_contain_text("L4")
    page.bring_to_front()

    # Assert
    expect(queue_rows(page)).to_have_count(1)
    expect(queue_rows(page).locator(".item-name")).to_have_text(QWEN)


def end_and_wait_ended(e2e_servers: Any) -> str:
    """送 `DELETE /api/session`,等到工作階段變成 `ended`;回傳那個工作階段的名稱。"""
    reply = httpx.delete(f"{e2e_servers.ui_url}/api/session", timeout=5.0)
    assert reply.status_code == 202, reply.text
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        session = httpx.get(f"{e2e_servers.ui_url}/api/session", timeout=5.0).json()
        if session["state"] == "ended":
            return str(session["name"])
        time.sleep(0.05)
    raise AssertionError(f"5 秒內沒有變成 ended:{session['state']}")


def downloading_and_queued(e2e_servers: Any, world: ColabWorld, fakes: Any) -> Gate:
    """qwen2.5 停在閘門(下載中),llama3.2:3b 排在它後面(排隊中)。"""
    set_manifests(fakes)
    held = pulls(world, fakes, hold=(QWEN,))
    enqueue(e2e_servers, QWEN, LLAMA)
    held.wait_entered()
    return held


# ---- 004 US1-AJ-04


def test_結束工作階段後模型頁說明佇列已一起清空_不再說重新開啟後會繼續下載(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:佇列裡有排隊中的 llama3.2:3b,模型頁已打開
    open_to_ready(page)
    held = downloading_and_queued(e2e_servers, world, fakes)
    page.goto("/models.html")
    expect(queue_row(page, LLAMA).locator(".pill")).to_have_text("排隊中")

    # Act
    end_and_wait_ended(e2e_servers)
    expect(page.locator("#session-pill")).to_contain_text("已結束")

    # Assert
    expect(page.locator('[data-state="queue-cleared"] #qc-text')).to_contain_text("已一起清空")
    assert "重新開啟後會繼續下載" not in page.locator("body").inner_text()
    held.release()


# ---- 004 US1-AJ-05


def test_重連逾時而失聯時_首頁顯示重連逾時的畫面並說明下載佇列也一起清空了(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:佇列裡有排隊中的 llama3.2:3b,首頁已打開
    open_to_ready(page)
    held = downloading_and_queued(e2e_servers, world, fakes)

    # Act
    lose_connection_until_timeout(fakes)
    expect(page.locator("#session-pill")).to_contain_text("失聯", timeout=10_000)
    assert httpx.get(f"{e2e_servers.ui_url}/api/session", timeout=5.0).json()["endReason"] == "RECONNECT_TIMEOUT"

    # Assert
    timeout_view = page.locator('[data-state="lost-timeout"]')
    expect(timeout_view).to_be_visible()
    expect(timeout_view).to_contain_text("下載佇列也一起清空了")
    expect(page.locator('[data-state="lost"]')).to_be_hidden()
    held.release()


# ---- 004 US1-AJ-06


def test_變更類型後新的工作階段開不起來時_首頁說明重新載入的項目也一起清空了(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:已載入 qwen2.5;就緒之後才讓新的通道建不起來(只影響新的工作階段)
    open_to_ready(page)
    world.models = {QWEN: (SIZES[QWEN], True)}
    fakes.tunnel.open_tunnel.raises("TUNNEL_UNREACHABLE", "連不到")

    # Act
    page.locator('[data-state="ready"]').get_by_role("button", name="變更類型").click()
    page.locator('[data-state="confirm-switch"] input[type="radio"][value="L4"]').check()
    page.click("#switch")
    failed = page.locator('[data-state="failed"]')

    # Assert
    expect(failed).to_be_visible(timeout=10_000)
    expect(failed).to_contain_text("一起清空了")
    assert jobs(e2e_servers) == []


# ---- 004 US1-AJ-07


def test_佇列是空的時依工作階段狀態顯示_從沒開過是空佇列_結束之後才打開是已一起清空(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # 情況 A:從沒開過工作階段
    page.goto("/models.html")
    expect(page.locator('[data-state="queue-empty"]')).to_be_visible()  # 則1

    # 情況 B:佇列有排隊中的 llama3.2:3b,結束並等到 ended 之後才打開模型頁
    open_to_ready(page)
    held = downloading_and_queued(e2e_servers, world, fakes)
    name = end_and_wait_ended(e2e_servers)
    held.release()
    page.goto("/models.html")

    # Assert
    cleared = page.locator('[data-state="queue-cleared"]')
    expect(cleared).to_be_visible()  # 則2
    expect(cleared.locator("#qc-text")).to_contain_text(name)  # 則3
    expect(cleared.locator("#qc-text")).not_to_contain_text("筆")  # 則4
