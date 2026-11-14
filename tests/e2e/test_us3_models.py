"""跨端點驗收:模型頁(目錄、預先載入與下載佇列)(testplan.md § 4.8)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨、plan.md Q99)。
"""

import re
import threading
import time
from typing import Any

import httpx
from playwright.sync_api import Locator, Page, expect

from e2e.test_us1_session import ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture
from fakes import Gate

# 模型在磁碟上的大小(位元組;照 ollama.com 版本頁的 0.5b 398MB、7b 4.7GB)
SIZE_0_5B = 397_821_319
SIZE_1_5B = 986_061_892
SIZE_7B = 4_683_087_332


def catalog_row(page: Page, name: str) -> Locator:
    """`#catalog` 裡名稱剛好是 `name` 的那一列(`qwen2.5:7b` 不會對到 `qwen2.5:7b-instruct`)。"""
    return page.locator("#catalog li").filter(has=page.locator(".item-name", has_text=re.compile(rf"^{re.escape(name)}$")))


def paced_pull(world: ColabWorld, clock: Any, model: str, size: int, lines: int = 20, every: float = 0.1) -> list[Any]:
    """`pull` 的進度串流:每 `every` 秒一行、共 `lines` 行,最後一行之前模型才出現在執行環境上。

    進度事件最多每秒推一次(asyncapi § sendDownloadUpdated);每一行另把假時鐘往前推 `every` 秒,
    讓 2 秒的串流穩定推出幾次進度,不必等到真的 4 秒。
    """
    gates = [Gate() for _ in range(lines)]

    def release() -> None:
        for gate in gates:
            time.sleep(every)
            clock.advance(every)
            if gate is gates[-1]:
                world.models[model] = (size, False)
            gate.release()

    threading.Thread(target=release, name="cgb-test-paced-pull", daemon=True).start()
    stream: list[Any] = [{"status": "pulling manifest"}]
    for i, gate in enumerate(gates, start=1):
        stream += [gate, {"status": "pulling cgb-test", "digest": "sha256:cgb-test", "total": size, "completed": size * i // lines}]
    return stream + [{"status": "success"}]


def ready_with_models(page: Page, world: ColabWorld, models: dict[str, tuple[int, bool]]) -> None:
    """開到就緒,再讓執行環境上有 `models`(名稱 → (大小, 是否已載入))。"""
    open_to_ready(page)
    world.models = dict(models)


# ---------------------------------------------------------------- US3-AJ-01


def test_打開模型頁_目錄列出名稱與大小_已載入的標示已載入_未載入的有預先載入按鈕(
    page: Page, e2e_servers: Any, world: ColabWorld
) -> None:
    # Arrange
    ready_with_models(page, world, {"qwen2.5:0.5b": (SIZE_0_5B, True), "qwen2.5:7b": (SIZE_7B, False)})

    # Act
    page.goto("/models.html")

    # Assert
    expect(page.locator("#catalog li")).to_have_count(2)
    small, big = catalog_row(page, "qwen2.5:0.5b"), catalog_row(page, "qwen2.5:7b")
    expect(small).to_contain_text("398 MB")
    expect(big).to_contain_text("4.7 GB")
    expect(small).to_contain_text("已載入")
    expect(small.get_by_role("button", name="預先載入")).to_have_count(0)
    expect(big.get_by_role("button", name="預先載入")).to_be_visible()


# ---------------------------------------------------------------- US3-AJ-02


def test_按預先載入後那一列顯示載入中_放行後不必重新整理就標示已載入(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    ready_with_models(page, world, {"qwen2.5:0.5b": (SIZE_0_5B, True), "qwen2.5:7b": (SIZE_7B, False)})
    preload_gate = fakes.remote_ollama.preload.gate()
    page.goto("/models.html")
    row = catalog_row(page, "qwen2.5:7b")
    button = row.get_by_role("button", name="預先載入")

    # Act
    expect(button).to_be_visible()
    button.click()
    expect(row).to_contain_text("載入中")
    preload_gate.wait_entered()
    preload_gate.release()

    # Assert
    expect(row).to_contain_text("已載入")
    expect(row).not_to_contain_text("載入中")
    assert fakes.remote_ollama.preload.last_call.kwargs["model"] == "qwen2.5:7b"


def queue_row(page: Page, model: str) -> Locator:
    """`#queue` 裡模型名稱剛好是 `model` 的那一列。"""
    return page.locator("#queue li").filter(has=page.locator(".item-name", has_text=re.compile(rf"^{re.escape(model)}$")))


def progress_percent(row: Locator) -> int:
    match = re.search(r"(\d+)%", row.locator("[data-progress-text]").inner_text())
    assert match, "下載中的那一列沒有百分比"
    return int(match.group(1))


# ---------------------------------------------------------------- US3-AJ-07


def test_取消排隊中的第2筆_它從佇列消失而下載中的第1筆繼續且沒有取消按鈕(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any, fake_clock: Any
) -> None:
    # Arrange
    open_to_ready(page)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="7b").returns({"sizeBytes": SIZE_7B})
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="1.5b").returns({"sizeBytes": SIZE_1_5B})
    fakes.remote_ollama.pull_model.side_effect(lambda *a, **k: paced_pull(world, fake_clock, k["model"], SIZE_7B, lines=60))
    enqueued = httpx.post(f"{e2e_servers.ui_url}/api/downloads", json={"models": ["qwen2.5:7b", "qwen2.5:1.5b"]}, timeout=5.0)
    assert enqueued.status_code == 201
    page.goto("/models.html")
    first, second = queue_row(page, "qwen2.5:7b"), queue_row(page, "qwen2.5:1.5b")
    expect(first.locator(".pill")).to_have_text("下載中")
    expect(second.locator(".pill")).to_have_text("排隊中")
    cancel = second.get_by_role("button", name="取消")

    # Act
    expect(cancel).to_be_visible()
    cancel.click()
    expect(second).to_have_count(0)
    percent_after_cancel = progress_percent(first)

    # Assert
    expect(first.locator(".pill")).to_have_text("下載中")
    expect(first.get_by_role("button", name="取消")).to_have_count(0)
    expect(first.locator("[data-progress-text]")).not_to_contain_text(f"下載中 {percent_after_cancel}%")
    assert progress_percent(first) > percent_after_cancel
    jobs = httpx.get(f"{e2e_servers.ui_url}/api/downloads", timeout=5.0).json()["jobs"]
    assert [job["model"] for job in jobs] == ["qwen2.5:7b"]


# ---------------------------------------------------------------- US3-AJ-11

SIZE_BIG_70B = 42_520_413_916  # 超過 T4 的顯示記憶體總量(ColabWorld 的 vramTotalBytes 約 16.1 GB)


def test_可能放不下的模型先標示_預先載入前提示且取消不送_放得下的直接載入(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    ready_with_models(page, world, {"cgb-test-big:70b": (SIZE_BIG_70B, False), "qwen2.5:7b": (SIZE_7B, False)})
    preload_gate = fakes.remote_ollama.preload.gate()
    page.goto("/models.html")
    big, fits = catalog_row(page, "cgb-test-big:70b"), catalog_row(page, "qwen2.5:7b")
    warn = page.locator('[data-state="preload-warn"]')

    # Act
    expect(big).to_contain_text("可能無法載入")
    big.get_by_role("button", name="預先載入").click()
    expect(warn).to_be_visible()
    page.click("#pw-cancel")
    preloads_after_cancel = fakes.remote_ollama.preload.call_count
    fits.get_by_role("button", name="預先載入").click()

    # Assert
    assert preloads_after_cancel == 0
    expect(fits).to_contain_text("載入中")
    expect(warn).to_be_hidden()
    expect(fits).not_to_contain_text("可能無法載入")
    preload_gate.wait_entered()
    assert fakes.remote_ollama.preload.last_call.kwargs["model"] == "qwen2.5:7b"
    preload_gate.release()
