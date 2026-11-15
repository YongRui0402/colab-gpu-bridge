"""跨端點驗收:在 UI 編輯精選清單,開好工作階段就自動下載(004 testplan.md § 4.3)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨、plan.md Q99)。
精選清單存在真的 SQLite;工作階段、剩餘磁碟、顯示記憶體與取大小用替身(`fakes.model_library`、`fakes.huggingface`、
`ColabWorld` 的 `probe_resources`)。
"""

import re
import time
from typing import Any

import httpx
from playwright.sync_api import BrowserContext, Locator, Page, expect

from cgb.adapters.errors import AdapterError
from e2e.test_us1_session import ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture

HF_SMOL = "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"
HF_GATED = "hf.co/google/gemma-3-1b-it-qat-q4_0-gguf:Q4_0"
QWEN = "qwen2.5:latest"
LLAMA = "llama3.2:3b"
BIG = "cgb-test-big:70b"
# 模型在磁碟上的大小(位元組);BIG 超過 T4 的顯示記憶體 16,106,127,360
SIZES = {QWEN: 4_683_087_332, LLAMA: 2_019_393_189, BIG: 20_000_000_000, "llama3.2:latest": 2_019_393_189}


def curated_row(page: Page, name: str) -> Locator:
    return page.locator("#curated li").filter(has=page.locator(".item-name", has_text=re.compile(rf"^{re.escape(name)}$")))


def curated_names(page: Page) -> list[str]:
    return page.locator("#curated li .item-name").all_inner_texts()


def set_sizes(fakes: Any, sizes: dict[str, int]) -> None:
    """官方名稱的 `get_manifest` 依 `<名稱>:<版本>` 回大小;沒列的回 `LIBRARY_NOT_FOUND`。`hf.co/` 一律 `HF_AUTH_REQUIRED`(需要登入)。"""

    def manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        full = f"{kwargs['name']}:{kwargs['tag']}"
        if full not in sizes:
            raise AdapterError("LIBRARY_NOT_FOUND", "manifest unknown")
        return {"name": kwargs["name"], "tag": kwargs["tag"], "sizeBytes": sizes[full]}

    fakes.model_library.get_manifest.side_effect(manifest)
    fakes.huggingface.get_manifest.raises("HF_AUTH_REQUIRED", "gated repo")


def notice(page: Page) -> Locator:
    return page.locator("#auto-notice")


def skipped_line(page: Page, model: str) -> Locator:
    return notice(page).locator("li").filter(has_text=model)


def reload_reading_result(page: Page) -> None:
    """重新整理,等頁面讀完 `GET /api/downloads/auto-result` 再往下看畫面。"""
    with page.expect_response(lambda r: r.url.endswith("/api/downloads/auto-result")):
        page.reload()


def wait_done(e2e_servers: Any, timeout: float = 5.0) -> dict[str, Any]:
    """一直查 `GET /api/downloads/auto-result` 直到判定完成(`state` 為 `done`),回傳那份結果。"""
    deadline = time.monotonic() + timeout
    while True:
        result = api(e2e_servers, "GET", "/downloads/auto-result").json()["result"]
        if (result is not None and result["state"] == "done") or time.monotonic() > deadline:
            assert result is not None and result["state"] == "done", result
            return result
        time.sleep(0.05)


def api(e2e_servers: Any, method: str, path: str, **kwargs: Any) -> httpx.Response:
    return httpx.request(method, f"{e2e_servers.ui_url}/api{path}", timeout=5.0, **kwargs)


def curate(e2e_servers: Any, name: str, **fields: Any) -> dict[str, Any]:
    """`POST /api/curated` 鋪一筆精選項目,斷言 201。"""
    reply = api(e2e_servers, "POST", "/curated", json={"name": name, **fields})
    assert reply.status_code == 201, reply.text
    return reply.json()


# ---- 004 US3-AJ-01


def test_沒有工作階段也能新增精選項目_重新整理後仍在且自動下載是開的(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange:沒有工作階段,精選清單是空的
    page.goto("/library.html")

    expect(page.locator("#cur-add")).to_be_visible()

    # Act
    page.click("#cur-add")
    page.fill("#c-name", HF_SMOL)
    page.fill("#c-note", "小模型試對話")
    page.select_option("#c-type", "L4")
    page.locator("label.switch", has=page.locator("#c-auto")).click()  # 開關的 input 是隱藏的,點外觀那一顆
    page.click("#c-submit")

    # Assert
    row = curated_row(page, HF_SMOL)
    expect(row).to_be_visible()
    expect(row.locator(".item-meta")).to_contain_text("小模型試對話")
    page.reload()
    expect(curated_row(page, HF_SMOL)).to_be_visible()
    curated_row(page, HF_SMOL).get_by_role("button", name="修改").click()
    expect(page.locator("#c-auto")).to_be_checked()


# ---- 004 US3-AJ-02


def test_修改說明不改順序_刪除要先確認_取消不刪(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange:沒有工作階段;精選清單依序是 qwen2.5、llama3.2:3b、hf.co/…
    qwen = curate(e2e_servers, "qwen2.5")["name"]
    llama = curate(e2e_servers, "llama3.2:3b")["name"]
    curate(e2e_servers, HF_SMOL)
    page.goto("/library.html")
    expect(page.locator("#curated li")).to_have_count(3)

    # Act 1:把 qwen2.5 的說明改成「改過」
    curated_row(page, qwen).get_by_role("button", name="修改").click()
    page.fill("#c-note", "改過")
    page.click("#c-submit")

    # Assert 1:順序不變
    expect(curated_row(page, qwen).locator(".item-meta")).to_contain_text("改過")
    assert curated_names(page) == [qwen, llama, HF_SMOL]

    # Act 2:刪除 llama3.2:3b,確認視窗按取消
    curated_row(page, llama).get_by_role("button", name="刪除").click()
    dialog = page.locator('[data-state="cur-delete"]')
    expect(dialog).to_be_visible()
    dialog.get_by_role("button", name="取消").click()

    # Assert 2
    expect(dialog).to_be_hidden()
    expect(curated_row(page, llama)).to_be_visible()

    # Act 3:再刪一次,確認視窗按刪除
    curated_row(page, llama).get_by_role("button", name="刪除").click()
    page.click("#del-go")

    # Assert 3
    expect(page.locator("#curated li")).to_have_count(2)
    assert curated_names(page) == [qwen, HF_SMOL]


# ---- 004 US3-AJ-03


def test_只差版本大小寫的名稱提示已在清單_格式不對的名稱提示格式(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange
    curate(e2e_servers, "qwen2.5")
    page.goto("/library.html")
    expect(page.locator("#curated li")).to_have_count(1)

    # Act A:qwen2.5:Latest(合法的名稱,只有版本的大小寫不同)
    page.click("#cur-add")
    page.fill("#c-name", "qwen2.5:Latest")
    page.click("#c-submit")

    # Assert A
    expect(page.locator('[data-state="cur-duplicate"]')).to_be_visible()
    expect(page.locator('[data-state="cur-duplicate"]')).to_contain_text("已經在精選清單裡")
    page.click("#c-cancel")
    page.reload()
    expect(page.locator('[data-state="cur-list"]')).to_be_visible()
    expect(page.locator("#curated li")).to_have_count(1)

    # Act B:hf.co/只有作者
    page.click("#cur-add")
    page.fill("#c-name", "hf.co/只有作者")
    page.click("#c-submit")

    # Assert B
    expect(page.locator('[data-state="cur-invalid"]')).to_be_visible()
    expect(page.locator('[data-state="cur-invalid"]')).to_contain_text("名稱的格式不對")


# ---- 004 US3-AJ-04


def curate_aj04(e2e_servers: Any, fakes: Any) -> None:
    """US3-AJ-04 的精選清單:qwen2.5 放得下、hf.co 需要登入取不到大小、BIG 超過顯示記憶體(都設自動下載);llama3.2:3b 沒設。"""
    set_sizes(fakes, SIZES)
    curate(e2e_servers, "qwen2.5", autoDownload=True)
    curate(e2e_servers, HF_GATED, autoDownload=True)
    curate(e2e_servers, BIG, autoDownload=True)
    curate(e2e_servers, LLAMA)


def test_就緒後模型頁的提示區列出排入與跳過的原因_重新整理後仍在(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:qwen2.5 放得下、hf.co 需要登入取不到大小、BIG 超過顯示記憶體;llama3.2:3b 沒設自動下載
    curate_aj04(e2e_servers, fakes)

    # Act
    open_to_ready(page)
    page.goto("/models.html")

    # Assert
    expect(notice(page)).to_contain_text("排入 1 個,跳過 2 個")
    expect(skipped_line(page, HF_GATED)).to_contain_text("取不到大小")
    expect(skipped_line(page, BIG)).to_contain_text("這台可能無法載入")
    expect(page.locator("#queue li .item-name", has_text=QWEN)).to_have_count(1)
    expect(page.locator("#queue li .item-name", has_text=LLAMA)).to_have_count(0)
    page.reload()
    expect(notice(page)).to_contain_text("跳過 2 個")


# ---- 004 US3-AJ-05


def test_按關閉後提示區不再顯示_重新整理後也不顯示(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:同 US3-AJ-04 就緒後的狀態
    curate_aj04(e2e_servers, fakes)
    open_to_ready(page)
    page.goto("/models.html")
    expect(notice(page)).to_contain_text("跳過 2 個")

    # Act
    notice(page).get_by_role("button", name="關閉").click()

    # Assert
    expect(notice(page)).to_be_hidden()
    reload_reading_result(page)
    expect(notice(page)).to_be_hidden()


# ---- 004 US3-AJ-06


def running_notice(page: Page) -> Locator:
    return page.locator('[data-state="auto-running"]')


def ready_with_models_page_open(page: Page, context: BrowserContext) -> None:
    """先打開模型頁,在另一個分頁開啟工作階段到就緒(模型頁跟著推送更新,不重新整理)。"""
    page.goto("/models.html")
    open_to_ready(context.new_page())


def test_判定中顯示正在依精選清單排入_取完大小後不再顯示(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:qwen2.5 設自動下載;取大小停在閘門前(判定中)
    set_sizes(fakes, SIZES)
    curate(e2e_servers, "qwen2.5", autoDownload=True)
    gate = fakes.model_library.get_manifest.gate()

    # Act
    ready_with_models_page_open(page, context)

    # Assert
    expect(running_notice(page)).to_be_visible()
    expect(running_notice(page)).to_contain_text("正在依精選清單排入")
    gate.release()
    expect(running_notice(page)).to_be_hidden()
    expect(notice(page)).to_contain_text("排入 1 個")


# ---- 004 US3-AJ-07


def test_排入與跳過都是空的時不顯示提示(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:qwen2.5 設自動下載,執行環境上已經有 qwen2.5:latest
    set_sizes(fakes, SIZES)
    curate(e2e_servers, "qwen2.5", autoDownload=True)
    create = fakes.colab.create_session

    def create_with_qwen(*args: Any, **kwargs: Any) -> dict[str, Any]:
        # 新開的執行環境上就已經有 qwen2.5:latest(等同 set_tags)
        created = world._create(*args, **kwargs)
        world.models[QWEN] = (SIZES[QWEN], False)
        return created

    create.side_effect(create_with_qwen)

    # Act
    open_to_ready(page)
    assert wait_done(e2e_servers)["enqueued"] == []
    with page.expect_response(lambda r: r.url.endswith("/api/downloads/auto-result")):
        page.goto("/models.html")

    # Assert
    expect(notice(page)).to_be_hidden()
    expect(page.locator("#queue li .item-name")).to_have_count(0)


# ---- 004 US3-AJ-08

# 容許的英文字同 US2-AJ-12,另加 latest
ALLOWED_WORDS = ("Hugging Face", "Colab", "token", "Ollama", "GGUF", "latest")
MODEL_NAMES = (HF_GATED, BIG, QWEN, LLAMA, "llama3.2:latest", "qwen2.5:14b", "qwen2.5")


def assert_traditional_chinese(block: Locator, state: str) -> str:
    """區塊的 `innerText` 去掉模型名稱之後,沒有連續 4 個以上的英文字母(容許清單除外),且至少有一個中文字;回傳去掉之後的文字。"""
    expect(block).to_be_visible()
    text = block.inner_text()
    for removed in (*MODEL_NAMES, *ALLOWED_WORDS):
        text = text.replace(removed, "")
    words = re.findall(r"[A-Za-z]{4,}", text)
    assert words == [], f"{state}:出現英文 {words}"
    assert re.search(r"[一-鿿]", text), f"{state}:沒有中文字"
    return text


def skip_reasons(page: Page) -> list[str]:
    """提示區跳過清單每一列的原因名稱(訊息 `原因名稱:說明` 的冒號前面)。"""
    lines = notice(page).locator("li").all_inner_texts()
    return [re.split(r" · ", line, maxsplit=1)[1].split(":", 1)[0] for line in lines]


def small_disk(fakes: Any) -> None:
    """`probe_resources`:剩餘磁碟 5,200,000,000、顯示記憶體 16,106,127,360(T4)。"""
    fakes.colab.probe_resources.side_effect(
        lambda *a, **k: {
            "diskFreeBytes": 5_200_000_000,
            "diskTotalBytes": 253_338_115_072,
            "gpuName": "Tesla T4",
            "vramTotalBytes": 16_106_127_360,
            "vramFreeBytes": 15_727_591_424,
            "checkedAt": "2026-11-09T09:00:00Z",
        }
    )


def wait_session(e2e_servers: Any, state: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while api(e2e_servers, "GET", "/session").json()["state"] != state:
        assert time.monotonic() < deadline, f"工作階段沒有在 {timeout} 秒內變成 {state}"
        time.sleep(0.05)


def test_精選清單的表單與兩個工作階段的自動下載提示都是繁體中文(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:精選清單的各個畫面
    page.goto("/library.html")
    assert_traditional_chinese(page.locator('[data-state="cur-empty"]'), "cur-empty")
    page.click("#cur-add")
    assert_traditional_chinese(page.locator("#cur-form"), "cur-form")
    page.fill("#c-name", "hf.co/只有作者")
    page.click("#c-submit")
    assert_traditional_chinese(page.locator('[data-state="cur-invalid"]'), "cur-invalid")
    page.click("#c-cancel")
    set_sizes(fakes, SIZES)
    for name in (HF_GATED, BIG, "qwen2.5", LLAMA):
        curate(e2e_servers, name, autoDownload=True)
    page.reload()
    assert_traditional_chinese(page.locator('[data-state="cur-list"]'), "cur-list")
    curated_row(page, QWEN).get_by_role("button", name="修改").click()
    assert_traditional_chinese(page.locator("#cur-form"), "cur-form-edit")
    page.fill("#c-name", LLAMA)
    page.click("#c-submit")
    assert_traditional_chinese(page.locator('[data-state="cur-duplicate"]'), "cur-duplicate")
    page.click("#c-cancel")
    curated_row(page, LLAMA).get_by_role("button", name="刪除").click()
    assert_traditional_chinese(page.locator('[data-state="cur-delete"]'), "cur-delete")
    page.click("#del-cancel")

    # 第一個工作階段:剩餘磁碟 5,200,000,000、顯示記憶體 16,106,127,360
    small_disk(fakes)
    open_to_ready(page)
    wait_done(e2e_servers)
    page.goto("/models.html")
    first = assert_traditional_chinese(notice(page), "auto-notice 第一個工作階段")
    first_reasons = skip_reasons(page)

    # 第二個工作階段:開啟前讓 probe_resources 丟 COLAB_UNREACHABLE(剩餘磁碟與顯示記憶體都讀不到)
    assert api(e2e_servers, "DELETE", "/session").status_code < 300
    wait_session(e2e_servers, "ended")
    fakes.colab.probe_resources.raises("COLAB_UNREACHABLE", "colab unreachable")
    assert api(e2e_servers, "POST", "/session", json={"runtimeType": {"gpu": "T4", "highMem": False}}).status_code < 300
    wait_session(e2e_servers, "ready")
    wait_done(e2e_servers)
    page.goto("/models.html")
    second = assert_traditional_chinese(notice(page), "auto-notice 第二個工作階段")
    second_reasons = skip_reasons(page)

    # Assert
    assert first and second
    assert first_reasons == ["取不到大小", "這台可能無法載入", "空間不足"]
    assert second_reasons == ["取不到大小", "讀不到剩餘空間", "讀不到剩餘空間", "讀不到剩餘空間"]


# ---- 004 US3-AJ-09


def test_跳過的項目顯示大小_剩餘空間與顯示記憶體_沒有值的不顯示(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:同 US3-API-39 情況 A
    set_sizes(fakes, {"qwen2.5:32b": 19_851_336_256, "qwen2.5:7b": 4_683_087_332, "llama3.2:latest": 2_019_393_189})
    small_disk(fakes)
    for name in ("qwen2.5:999b", "qwen2.5:32b", "qwen2.5:7b", "llama3.2"):
        curate(e2e_servers, name, autoDownload=True)

    # Act
    open_to_ready(page)
    wait_done(e2e_servers)
    page.goto("/models.html")

    # Assert
    expect(notice(page)).to_contain_text("跳過 3 個")
    expect(skipped_line(page, "qwen2.5:32b")).to_contain_text("顯示記憶體約 15 GB")
    expect(skipped_line(page, "llama3.2:latest")).to_contain_text("大小 2.0 GB")
    expect(skipped_line(page, "llama3.2:latest")).to_contain_text("排入前面幾個之後只剩 517 MB")
    missing = skipped_line(page, "qwen2.5:999b").inner_text()
    assert "GB" not in missing and "MB" not in missing, missing


# ---- 004 US3-AJ-10


def test_判定中按關閉_完成後與重新整理後都不再顯示(
    page: Page, context: BrowserContext, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange:同 US3-AJ-06,取大小停在閘門前
    set_sizes(fakes, SIZES)
    curate(e2e_servers, "qwen2.5", autoDownload=True)
    gate = fakes.model_library.get_manifest.gate()
    ready_with_models_page_open(page, context)
    expect(running_notice(page)).to_be_visible()

    # Act
    running_notice(page).locator("[data-dismiss]").click()

    # Assert
    expect(running_notice(page)).to_be_hidden()
    gate.release()
    assert wait_done(e2e_servers)["dismissed"] is True
    expect(notice(page)).to_be_hidden()
    reload_reading_result(page)
    expect(notice(page)).to_be_hidden()
    expect(running_notice(page)).to_be_hidden()


# ---- 004 US3-AJ-11


def runtime_type_of(e2e_servers: Any, name: str) -> Any:
    items = api(e2e_servers, "GET", "/curated").json()["items"]
    return next(c["recommendedRuntimeType"] for c in items if c["name"] == name)


def test_高RAM跟著建議類型_送出時建議類型帶GPU與高RAM_只改說明時保留(page: Page, e2e_servers: Any, world: ColabWorld) -> None:
    # Arrange:沒有工作階段;qwen2.5:7b 建議 T4、高 RAM 開
    curate(e2e_servers, "qwen2.5:7b", recommendedRuntimeType={"gpu": "T4", "highMem": True})
    page.goto("/library.html")
    expect(curated_row(page, "qwen2.5:7b")).to_be_visible()

    # Act A:新增表單,建議類型選「不指定」
    page.click("#cur-add")
    page.select_option("#c-type", "")

    # Assert A
    expect(page.locator("#c-highmem")).to_be_disabled()

    # Act B:同一個表單改成 T4、勾高 RAM,名稱 llama3.2:3b 送出
    page.select_option("#c-type", "T4")
    page.check("#c-highmem")
    page.fill("#c-name", LLAMA)
    page.click("#c-submit")

    # Assert B
    expect(curated_row(page, LLAMA)).to_be_visible()
    assert runtime_type_of(e2e_servers, LLAMA) == {"gpu": "T4", "highMem": True}

    # Act C:打開 qwen2.5:7b 的修改表單,只改說明
    curated_row(page, "qwen2.5:7b").get_by_role("button", name="修改").click()

    # Assert C
    expect(page.locator("#c-highmem")).to_be_checked()
    page.fill("#c-note", "改過")
    page.click("#c-submit")
    expect(curated_row(page, "qwen2.5:7b").locator(".item-meta")).to_contain_text("改過")
    assert runtime_type_of(e2e_servers, "qwen2.5:7b") == {"gpu": "T4", "highMem": True}
