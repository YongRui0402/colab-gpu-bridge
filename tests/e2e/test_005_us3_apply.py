"""005 跨端點驗收:工作階段開著時改設定,套用並重啟遠端 Ollama(testplan.md § US3-AJ)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨)。
替身的 `restart_ollama` 回報的 `OllamaRestarted` 就是遠端重啟後套用的設定;重啟後遠端 `/api/ps` 是空的,
預先載入才把模型載回去(`ColabWorld.models` 的「已載入」)。
"""

from typing import Any

from playwright.sync_api import Page, expect

from cgb.adapters.errors import AdapterError

from e2e.test_004_us1_queue import LLAMA, QWEN, SIZES, catalog_row, enqueue, queue_row, queue_rows, set_manifests
from e2e.test_us1_session import ColabWorld, world  # noqa: F401 - `world` 是 fixture
from fakes import Gate
from integration.test_api_tuning import GIB, applied, restarted

MODEL_A = "qwen2.5:7b"
SIZE_A = 4_683_087_332
_T4_MACHINE = {"gpu_name": "Tesla T4", "system_bytes": 13_605_855_232}
# T4 的自動值是 2/4096/1(e2e `ColabWorld` 預設的 `T4_STARTED`);手動平行數 4 的重啟結果
T4_RESTARTED_4 = restarted(15 * GIB, applied(4, 4096, 1, sources=("manual", "auto", "auto")), **_T4_MACHINE)
# 改回自動值(三個覆蓋值都是 null)之後的重啟結果
T4_RESTARTED_AUTO = restarted(15 * GIB, applied(2, 4096, 1), **_T4_MACHINE)
AUTO = {"numParallel": None, "contextLength": None, "maxLoadedModels": None}


def restart_with(world: ColabWorld, result: dict[str, Any]) -> None:
    """`restart_ollama` 成功回 `result`;重啟後遠端 Ollama 沒有載入任何模型。"""

    def restart(*args: Any, **kwargs: Any) -> dict[str, Any]:
        world.models = {name: (size, False) for name, (size, _) in world.models.items()}
        return result

    world.fakes.colab.restart_ollama.side_effect(restart)


def open_ready_with(page: Page, world: ColabWorld, models: dict[str, tuple[int, bool]]) -> None:
    """以預設類型開到就緒,執行環境上有 `models`(名稱 → (大小, 是否已載入))。"""
    page.goto("/")
    page.locator("#open").click()
    expect(page.locator('[data-state="ready"]')).to_be_visible(timeout=10_000)
    world.models = dict(models)


def edit_parallel(page: Page, value: str) -> None:
    """在設定卡按「修改設定」,把平行數改成 `value`,按「套用並重啟 Ollama」。"""
    edit = page.locator("#t-card").get_by_role("button", name="修改設定")
    expect(edit).to_be_visible()
    edit.click()
    parallel = page.locator('#et-fields input[data-field="numParallel"]')
    expect(parallel).to_be_visible()
    parallel.fill(value)
    page.get_by_role("button", name="套用並重啟 Ollama").click()


# ---- 005 US3-AJ-01


def test_套用前確認視窗說明重啟與重新載入_套用中依序顯示兩步_回到就緒後設定卡是新的值(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    restart_with(world, T4_RESTARTED_4)
    open_ready_with(page, world, {MODEL_A: (SIZE_A, True)})
    restart_gate = fakes.colab.restart_ollama.gate()
    preload_gate = fakes.remote_ollama.preload.gate()

    # Act
    edit_parallel(page, "4")

    # Assert 則1:確認視窗寫出會重啟、要重新載入、這段時間無法對話與送請求
    confirm = page.locator('[data-state="confirm-apply"]')
    expect(confirm).to_be_visible()
    expect(confirm).to_contain_text("會重啟遠端 Ollama")
    expect(confirm).to_contain_text("已載入的模型要重新載入")
    expect(confirm).to_contain_text("無法對話與送請求")

    # Act
    page.locator("#confirm-apply").click()

    # Assert 則2:套用中依序顯示「重啟 Ollama」「重新載入模型」
    restarting = page.locator('[data-state="restarting"]')
    expect(restarting).to_be_visible()
    expect(restarting.locator("[data-apply-steps] li.current")).to_contain_text("重啟 Ollama")
    expect(page.locator("#session-pill")).to_contain_text("套用設定中")
    restart_gate.wait_entered()
    restart_gate.release()
    reloading = page.locator('[data-state="reloading"]')
    expect(reloading).to_be_visible()
    expect(reloading.locator("[data-apply-steps] li.current")).to_contain_text("重新載入模型")
    preload_gate.wait_entered()
    preload_gate.release()

    # Assert 則3:回到就緒後設定卡顯示平行 4 標「手動」
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    first = page.locator("#t-rows > tr").first
    expect(first.locator("td").nth(1)).to_have_text("4")
    expect(first.locator("td").nth(2)).to_have_text("手動")


# ---- 005 US3-AJ-02


def pull_in_steps(fakes: Any, model: str, *gates: Gate) -> None:
    """`model` 的下載每過一道閘門多回報一段進度:10%、50%……,全部放行後完成。"""
    total = SIZES[model]
    lines: list[Any] = [{"status": "pulling manifest"}]
    for percent, gate in zip((10, 50, 90), gates, strict=False):
        lines += [{"status": "pulling cgb-test", "digest": "sha256:cgb-test", "total": total, "completed": total * percent // 100}, gate]
    lines.append({"status": "success"})
    fakes.remote_ollama.pull_model.side_effect(lambda *a, **k: list(lines))


def test_有模型正在下載時按套用_說明下載完才能套用_下載照常進行_工作階段仍就緒(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    set_manifests(fakes)
    first, second = Gate(), Gate()
    pull_in_steps(fakes, QWEN, first, second)
    open_ready_with(page, world, {})
    enqueue(e2e_servers, QWEN)
    first.wait_entered()

    # Act
    edit_parallel(page, "4")
    page.locator("#confirm-apply").click()

    # Assert 則1:畫面說明有模型正在下載、下載完才能套用
    blocked = page.locator('[data-state="apply-blocked-download"]')
    expect(blocked).to_be_visible()
    expect(blocked).to_contain_text("有模型正在下載")
    expect(blocked).to_contain_text("下載完才能套用")

    # Assert 則2:下載進度繼續推進,工作階段仍是就緒
    first.release()
    second.wait_entered()
    expect(page.locator("#session-pill")).to_contain_text("就緒")
    page.goto("/models.html")
    expect(queue_row(page, QWEN)).to_contain_text("下載中 50%")
    second.release()


# ---- 005 US3-AJ-03


def test_要求的設定起不來時改回自動值_設定卡說明沒有套用成功並列出要求的值_三項都標自動(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:要求的設定那一次在 `verify` 失敗,改回自動值的那一次成功
    def restart(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs["overrides"] != AUTO:
            raise AdapterError("COLAB_REMOTE_ERROR", "遠端腳本失敗:verify", remote_stage="verify")
        return T4_RESTARTED_AUTO

    fakes.colab.restart_ollama.side_effect(restart)
    open_ready_with(page, world, {})

    # Act
    edit_parallel(page, "16")
    page.locator("#confirm-apply").click()

    # Assert 則1:回到就緒後說明改回自動值,列出這次要求的平行數 16
    fallback = page.locator("#t-fallback")
    expect(fallback).to_be_visible()
    expect(fallback).to_contain_text("手動設定沒有套用成功,已改回自動值")
    expect(fallback).to_contain_text("16")
    # 則2:三項都標「自動」
    rows = page.locator("#t-rows > tr")
    for i in range(3):
        expect(rows.nth(i).locator("td").nth(2)).to_have_text("自動")


# ---- 005 US3-AJ-04


def test_同時載入模型數改小時依順序只重新載入前面的_畫面列出沒有重新載入的模型(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:遠端 `/api/ps` 依序列出 A(qwen2.5)、B(llama3.2)
    restart_with(world, restarted(15 * GIB, applied(2, 4096, 1, sources=("auto", "auto", "manual")), **_T4_MACHINE))
    open_ready_with(page, world, {QWEN: (SIZES[QWEN], True), LLAMA: (SIZES[LLAMA], True)})

    # Act
    page.locator("#t-card").get_by_role("button", name="修改設定").click()
    page.locator('#et-fields input[data-field="maxLoadedModels"]').fill("1")
    page.get_by_role("button", name="套用並重啟 Ollama").click()
    page.locator("#confirm-apply").click()

    # Assert 則1:回到就緒後列出 B 沒有重新載入
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    expect(page.locator("#t-not-reloaded")).to_be_visible()
    expect(page.locator("#t-not-reloaded")).to_contain_text(f"{LLAMA} 沒有重新載入")
    # 則2:模型頁只有 A 顯示已載入
    page.goto("/models.html")
    expect(catalog_row(page, QWEN)).to_contain_text("已載入")
    expect(catalog_row(page, LLAMA)).not_to_contain_text("已載入")


# ---- 005 US3-AJ-05


def test_要求的設定與改回自動值都起不來時工作階段結束_結束原因是重啟_Ollama_失敗_佇列清空(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:兩次重啟都在 `start` 失敗;佇列裡已經有一筆下載完成的項目
    def restart(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise AdapterError("COLAB_REMOTE_ERROR", "遠端腳本失敗:start", remote_stage="start")

    fakes.colab.restart_ollama.side_effect(restart)
    set_manifests(fakes)
    open_ready_with(page, world, {})
    enqueue(e2e_servers, QWEN)
    page.goto("/models.html")
    expect(queue_row(page, QWEN)).to_be_visible()
    page.goto("/")

    # Act
    edit_parallel(page, "4")
    page.locator("#confirm-apply").click()

    # Assert 則1:工作階段結束,結束原因顯示「重啟 Ollama 失敗」
    expect(page.locator("#session-pill")).to_contain_text("失聯")
    screen = page.locator("main > section:not([hidden])")
    expect(screen).to_have_count(1)
    expect(screen).to_contain_text("重啟 Ollama 失敗")
    # 則2:模型頁的下載佇列是空的
    page.goto("/models.html")
    expect(queue_rows(page)).to_have_count(0)


# ---- 005 US3-AJ-06


def apply_parallel(page: Page, value: str) -> None:
    """在工作階段頁把平行數改成 `value`,套用確認,等到回到就緒、設定卡顯示新的值。"""
    edit_parallel(page, value)
    page.locator("#confirm-apply").click()
    expect(page.locator('[data-state="ready"]')).to_be_visible()
    expect(page.locator("#t-rows > tr").first.locator("td").nth(1)).to_have_text(value)


def test_紀錄頁明細依時間列出開啟與每一次套用_套用的那幾筆寫出要求的值與結果(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:同一個工作階段先後套用平行數 4 與 8,都成功
    def restart(*args: Any, **kwargs: Any) -> dict[str, Any]:
        np = kwargs["overrides"]["numParallel"]
        return restarted(15 * GIB, applied(np, 4096, 1, sources=("manual", "auto", "auto")), **_T4_MACHINE)

    fakes.colab.restart_ollama.side_effect(restart)
    open_ready_with(page, world, {})
    apply_parallel(page, "4")
    apply_parallel(page, "8")
    page.goto("/history.html")

    # Act
    page.locator("#rows > tr").first.click()

    # Assert 則1:開啟、套用 4、套用 8 三筆,各自的結果都是「成功」
    logs = page.locator('[data-state="tuning-log"] tbody > tr')
    expect(logs).to_have_count(3)
    for i, (trigger, requested) in enumerate([("開啟", None), ("套用", "平行 4"), ("套用", "平行 8")]):
        cells = logs.nth(i).locator("td")
        expect(cells.nth(1)).to_have_text(trigger)
        if requested is not None:
            expect(cells.nth(2)).to_contain_text(requested)
        expect(cells.nth(9)).to_contain_text("成功")
