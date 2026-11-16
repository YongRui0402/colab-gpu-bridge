"""跨端點驗收:下載模型頁(搜尋、精選清單、試算與加入佇列)(testplan.md § 4.8)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨、plan.md Q99)。
"""

import re
from typing import Any

import httpx
from playwright.sync_api import Page, expect

from e2e.test_us1_session import ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture
from e2e.test_us3_models import SIZE_0_5B, SIZE_1_5B, SIZE_7B, catalog_row, paced_pull, queue_row
from fakes import Gate

# 瀏覽器端記下每一次 `[data-progress-text]` 的文字(換頁後照樣記;連續相同的只記一次)
RECORD_PROGRESS_TEXTS = """
window.__progressTexts = [];
new MutationObserver(() => {
  document.querySelectorAll("[data-progress-text]").forEach((el) => {
    const texts = window.__progressTexts;
    if (texts[texts.length - 1] !== el.textContent) texts.push(el.textContent);
  });
}).observe(document, { subtree: true, childList: true, characterData: true });
"""


# ---------------------------------------------------------------- US3-AJ-03


def test_輸入名稱下載後佇列的進度至少變化兩次_完成後目錄有這個模型(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any, fake_clock: Any
) -> None:
    # Arrange
    open_to_ready(page)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="7b").returns({"sizeBytes": SIZE_7B})
    fakes.remote_ollama.pull_model.side_effect(lambda *a, **k: paced_pull(world, fake_clock, k["model"], SIZE_7B))
    page.add_init_script(RECORD_PROGRESS_TEXTS)
    page.goto("/library.html")

    # Act
    expect(page.locator("#name-form")).to_be_visible()
    page.fill("#direct", "qwen2.5:7b")
    page.locator("#name-form").get_by_role("button").click()
    expect(page.locator("#add")).to_be_visible()
    page.click("#add")
    expect(page.locator('[data-state="confirm"]')).to_be_visible()
    page.click("#confirm-go")
    page.wait_for_url("**/models.html")
    row = page.locator("#queue li", has_text="qwen2.5:7b")
    expect(row).to_contain_text("完成", timeout=10_000)
    texts = page.evaluate("window.__progressTexts")
    page.goto("/models.html")

    # Assert
    assert len(texts) - 1 >= 2, f"下載中的進度文字只變化 {len(texts) - 1} 次:{texts}"
    expect(row.locator(".pill")).to_have_text("完成")
    expect(catalog_row(page, "qwen2.5:7b")).to_be_visible()


def queued_models(e2e_servers: Any) -> list[str]:
    """後端佇列裡的模型名稱(`GET /api/downloads`)。"""
    return [job["model"] for job in httpx.get(f"{e2e_servers.ui_url}/api/downloads", timeout=5.0).json()["jobs"]]


# ---------------------------------------------------------------- US3-AJ-04


def test_輸入不存在的名稱送出_顯示找不到這個模型且佇列沒有新增(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="cgb-test-nonexistent").raises("LIBRARY_NOT_FOUND", "manifest unknown")
    page.goto("/library.html")
    not_found = page.locator('[data-state="not-found"]')

    # Act
    expect(page.locator("#name-form")).to_be_visible()
    page.fill("#direct", "qwen2.5:cgb-test-nonexistent")
    page.locator("#name-form").get_by_role("button").click()

    # Assert
    expect(not_found).to_be_visible()
    expect(not_found).to_contain_text("找不到這個模型")
    expect(not_found).to_contain_text("qwen2.5:cgb-test-nonexistent")
    assert queued_models(e2e_servers) == []


def search_page(*names: str, has_more: bool) -> dict[str, Any]:
    """`ModelLibrary.search_library` 的回傳。"""
    return {
        "items": [{"name": n, "description": None, "parameterSizes": [], "capabilities": []} for n in names],
        "hasMore": has_more,
    }


QWEN25_TAGS = [
    {"tag": "0.5b", "sizeLabel": "398MB", "contextLength": "32K", "cloudOnly": False},
    {"tag": "1.5b", "sizeLabel": "986MB", "contextLength": "32K", "cloudOnly": False},
    {"tag": "7b", "sizeLabel": "4.7GB", "contextLength": "32K", "cloudOnly": False},
]


def search_qwen25(page: Page, fakes: Any) -> None:
    """打開下載模型頁搜尋 `qwen2.5`:第 1 頁 `qwen2.5`、`qwen2.5-coder`,有下一頁;第 2 頁 `qwen2.5vl`。"""
    fakes.model_library.search_library.when(q="qwen2.5", page=1).returns(search_page("qwen2.5", "qwen2.5-coder", has_more=True))
    fakes.model_library.search_library.when(q="qwen2.5", page=2).returns(search_page("qwen2.5vl", has_more=False))
    page.goto("/library.html")
    expect(page.locator("#lib-form")).to_be_visible()
    page.fill("#lib-q", "qwen2.5")
    page.locator("#lib-form").get_by_role("button", name="搜尋").click()


def expand_versions(page: Page, name: str) -> Any:
    """展開搜尋結果裡 `name` 的版本,回傳那一個結果。"""
    result = page.locator("#lib-results .result").filter(has=page.locator(".item-name", has_text=re.compile(rf"^{re.escape(name)}$")))
    button = result.get_by_role("button", name="看版本")
    expect(button).to_be_visible()
    button.click()
    return result


# ---------------------------------------------------------------- US3-AJ-05


def test_精選清單在搜尋結果之上_展開版本標出已下載_顯示更多會多列(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    open_to_ready(page)
    world.models = {"qwen2.5:0.5b": (SIZE_0_5B, False)}
    httpx.post(f"{e2e_servers.ui_url}/api/curated", json={"name": "qwen2.5:7b", "description": "中文對話的主力"}, timeout=5.0)
    fakes.model_library.list_model_tags.when(name="qwen2.5").returns(QWEN25_TAGS)

    # Act
    search_qwen25(page, fakes)
    results = page.locator("#lib-results .result")
    expect(results).to_have_count(2)
    expect(page.locator("#curated li", has_text="qwen2.5:7b")).to_be_visible()
    curated_box = page.locator("#curated").bounding_box()
    results_box = page.locator("#lib-results").bounding_box()
    qwen25 = expand_versions(page, "qwen2.5")
    version_05b = qwen25.locator(".version").filter(has=page.locator(".mono", has_text=re.compile(r"^0\.5b$")))
    expect(version_05b).to_be_visible()
    page.click("#more")

    # Assert
    assert curated_box is not None and results_box is not None
    assert curated_box["y"] < results_box["y"], f"精選清單在 y={curated_box['y']},搜尋結果在 y={results_box['y']}"
    expect(version_05b).to_contain_text("398MB")
    expect(version_05b).to_contain_text("已下載")
    expect(results).to_have_count(3)


MANIFEST_SIZES = {"0.5b": SIZE_0_5B, "1.5b": SIZE_1_5B, "7b": SIZE_7B}


def manifests(fakes: Any) -> None:
    """registry 對 `qwen2.5` 的 0.5b、1.5b、7b 回 manifest 的大小。"""
    for tag, size in MANIFEST_SIZES.items():
        fakes.model_library.get_manifest.when(name="qwen2.5", tag=tag).returns({"sizeBytes": size})


def gated_pulls(world: ColabWorld, fakes: Any) -> dict[str, Gate]:
    """每個模型的 `pull` 停在第一行之後,等測試放行才回 success;回傳 模型 → 閘門。"""
    gates: dict[str, Gate] = {}

    def pull(*args: Any, **kwargs: Any) -> list[Any]:
        model = kwargs["model"]
        gate = gates.setdefault(model, Gate())
        world.models[model] = (MANIFEST_SIZES[model.split(":", 1)[1]], False)
        return [{"status": "pulling manifest"}, gate, {"status": "success"}]

    fakes.remote_ollama.pull_model.side_effect(pull)
    for model in ("qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:7b"):
        gates[model] = Gate()
    return gates


# ---------------------------------------------------------------- US3-AJ-06


def test_勾三個版本加入下載先看確認畫面_確認後依序下載到全部完成(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    open_to_ready(page)
    manifests(fakes)
    gates = gated_pulls(world, fakes)
    fakes.model_library.list_model_tags.when(name="qwen2.5").returns(QWEN25_TAGS)
    search_qwen25(page, fakes)
    qwen25 = expand_versions(page, "qwen2.5")
    for tag in ("0.5b", "1.5b", "7b"):
        version = qwen25.locator(".version").filter(has=page.locator(".mono", has_text=re.compile(rf"^{re.escape(tag)}$")))
        version.locator('input[type="checkbox"]').check()
    confirm = page.locator('[data-state="confirm"]')

    # Act
    page.click("#add")
    expect(confirm).to_be_visible()
    queued_before_confirm = queued_models(e2e_servers)
    table_text = page.locator("#confirm-table").inner_text()
    disk_text = page.locator("#confirm-disk").inner_text()
    eta_text = confirm.locator("p", has=page.locator("#confirm-eta")).inner_text()
    page.click("#confirm-go")
    page.wait_for_url("**/models.html")
    rows = page.locator("#queue li")
    expect(rows.locator(".item-name")).to_have_text(["qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:7b"])
    expect(rows.locator(".pill")).to_have_text(["下載中", "排隊中", "排隊中"])
    for model in ("qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:7b"):
        gates[model].wait_entered()
        gates[model].release()

    # Assert
    assert queued_before_confirm == []
    for name in ("qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:7b", "總大小", "6.07 GB"):
        assert name in table_text, f"確認畫面的模型表沒有「{name}」:{table_text!r}"
    assert "剩餘磁碟" in disk_text and "225 GB" in disk_text, disk_text
    assert re.search(r"約 \d+ (分 \d+ )?秒", eta_text) and "估計" in eta_text, eta_text
    for model in ("qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:7b"):
        expect(queue_row(page, model).locator(".pill")).to_have_text("完成")


# ---------------------------------------------------------------- US3-AJ-08


def test_剩餘磁碟不夠時按加入下載_先提示空間不足而且不能加入(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    fakes.colab.probe_resources.side_effect(
        lambda *a, **k: {
            "diskFreeBytes": 1_000_000_000,
            "diskTotalBytes": 253_338_115_072,
            "gpuName": "Tesla T4",
            "vramTotalBytes": 16_106_127_360,
            "vramFreeBytes": 15_727_591_424,
            "checkedAt": "2026-11-09T09:00:00Z",
        }
    )
    manifests(fakes)
    httpx.post(f"{e2e_servers.ui_url}/api/curated", json={"name": "qwen2.5:7b", "description": "中文對話的主力"}, timeout=5.0)
    page.goto("/library.html")
    no_space = page.locator('[data-state="no-space"]')
    confirm_go = page.locator("#confirm-go")

    # Act
    page.locator("#curated li", has_text="qwen2.5:7b").locator('input[type="checkbox"]').check()
    page.click("#add")
    expect(no_space).to_be_visible()
    if confirm_go.is_visible() and confirm_go.is_enabled():
        confirm_go.click()

    # Assert
    expect(no_space).to_contain_text("不足")
    expect(no_space).to_contain_text("qwen2.5:7b")
    assert queued_models(e2e_servers) == []


# ---------------------------------------------------------------- US3-AJ-10


def test_展開版本時雲端專用版本說明只能在雲端執行而且不能勾選(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    tags = [*QWEN25_TAGS, {"tag": "7b-cloud", "sizeLabel": None, "contextLength": None, "cloudOnly": True}]
    fakes.model_library.list_model_tags.when(name="qwen2.5").returns(tags)
    search_qwen25(page, fakes)

    # Act
    qwen25 = expand_versions(page, "qwen2.5")
    cloud = qwen25.locator(".version").filter(has=page.locator(".mono", has_text=re.compile(r"^7b-cloud$")))

    # Assert
    expect(cloud).to_contain_text("只能在雲端執行")
    expect(cloud.locator("input:not([disabled])")).to_have_count(0)
