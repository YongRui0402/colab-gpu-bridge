"""跨端點驗收:從 Hugging Face 找模型下載(004 testplan.md § 5.4)。

接縫:瀏覽器畫面接測試行程內真的後端(UI 127.0.0.1:8781),轉接層用替身(testplan.md § 接縫的取捨、plan.md Q99)。
Hugging Face 用 `FakeHuggingFaceHub`(`search_models`、`list_quants`、`get_manifest`),官方模型庫用 `FakeModelLibrary`,
下載用 `FakeRemoteOllama.pull_model`(`ColabWorld`)。
"""

import re
import time
from typing import Any

import httpx
from playwright.sync_api import Locator, Page, expect

from e2e.test_us1_session import ColabWorld, open_to_ready, world  # noqa: F401 - `world` 是 fixture
from e2e.test_us3_models import catalog_row

SMOL_ID = "bartowski/SmolLM2-135M-Instruct-GGUF"
HF_Q4 = f"hf.co/{SMOL_ID}:Q4_K_M"
HF_Q8 = f"hf.co/{SMOL_ID}:Q8_0"
SMOL_QUANTS = [{"quant": "Q4_K_M", "sizeBytes": 105_455_145}, {"quant": "Q8_0", "sizeBytes": 144_811_072}]


def hf_page(*ids: str, cursor: str | None) -> dict[str, Any]:
    """`search_models` 的一頁(plan.md Q49):`items` 依序是 `ids`,`nextCursor` 是下一頁的 cursor。"""
    return {"items": [{"id": i, "downloads": 1000 - n} for n, i in enumerate(ids)], "nextCursor": cursor}


def hf_search(page: Page, keyword: str) -> None:
    """打開下載模型頁(已開的就沿用),在 `#hf-q` 搜尋 `keyword`。"""
    if not page.url.endswith("/library.html"):
        page.goto("/library.html")
    expect(page.locator("#hf-form")).to_be_visible()
    page.fill("#hf-q", keyword)
    page.locator("#hf-form").get_by_role("button", name="搜尋").click()


def hf_result(page: Page, repo_id: str) -> Locator:
    return page.locator("#hf-results .result").filter(has=page.locator(".item-name", has_text=re.compile(rf"^hf\.co/{re.escape(repo_id)}$")))


def hf_names(page: Page) -> list[str]:
    return page.locator("#hf-results .result .item-name").all_inner_texts()


def api(e2e_servers: Any, method: str, path: str, **kwargs: Any) -> httpx.Response:
    return httpx.request(method, f"{e2e_servers.ui_url}/api{path}", timeout=5.0, **kwargs)


# ---- 004 US4-AJ-01


def test_搜尋Hugging_Face後載入更多_接在原本的結果後面_最後一頁不再顯示載入更多(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    fakes.huggingface.search_models.when(query="qwen", cursor=None).returns(
        hf_page("Qwen/Qwen2.5-0.5B-Instruct-GGUF", "unsloth/Qwen3-0.6B-GGUF", cursor="c2")
    )
    fakes.huggingface.search_models.when(query="qwen", cursor="c2").returns(hf_page("bartowski/Qwen2.5-7B-Instruct-GGUF", cursor=None))

    # Act
    hf_search(page, "qwen")
    expect(page.locator("#hf-results .result")).to_have_count(2)
    first = hf_names(page)
    page.click("#hf-more")

    # Assert
    assert first == ["hf.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF", "hf.co/unsloth/Qwen3-0.6B-GGUF"]
    expect(page.locator("#hf-results .result")).to_have_count(3)
    assert hf_names(page)[2] == "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF"
    expect(page.locator("#hf-more")).to_be_hidden()


def search_smol(page: Page, fakes: Any) -> Locator:
    """搜尋 `qwen` 只回 `bartowski/SmolLM2-135M-Instruct-GGUF`,回傳那一個結果。"""
    fakes.huggingface.search_models.returns(hf_page(SMOL_ID, cursor=None))
    hf_search(page, "qwen")
    result = hf_result(page, SMOL_ID)
    expect(result).to_be_visible()
    return result


def expand_quants(result: Locator) -> None:
    button = result.get_by_role("button", name="看量化版本")
    expect(button).to_be_visible()
    button.click()


def quant_row(result: Locator, quant: str) -> Locator:
    return result.locator(".version").filter(has=result.page.locator(".mono", has_text=re.compile(rf"^{re.escape(quant)}$")))


# ---- 004 US4-AJ-02


def test_展開Hugging_Face模型列出量化版本與大小_已下載不分大小寫比對且不能勾(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    world.models["hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:q4_k_m"] = (105_455_145, False)
    fakes.huggingface.list_quants.returns(SMOL_QUANTS)
    result = search_smol(page, fakes)

    # Act
    expand_quants(result)

    # Assert
    expect(result.locator(".version")).to_have_count(2)
    assert result.locator(".version .mono").all_inner_texts() == ["Q4_K_M", "Q8_0"]
    expect(quant_row(result, "Q8_0")).to_contain_text("0.14 GB")
    expect(quant_row(result, "Q4_K_M")).to_contain_text("已下載")
    expect(quant_row(result, "Q4_K_M").locator("input[type=checkbox]")).to_be_disabled()


QWEN_BYTES = 4_683_087_332


def official_qwen25(page: Page, fakes: Any) -> Locator:
    """在 `#lib-q` 搜尋 `qwen2.5`,展開它的版本(只有 `latest`),回傳那一個結果。"""
    fakes.model_library.search_library.returns(
        {"items": [{"name": "qwen2.5", "description": None, "parameterSizes": [], "capabilities": []}], "hasMore": False}
    )
    fakes.model_library.list_model_tags.returns([{"tag": "latest", "sizeLabel": "4.7GB", "contextLength": "32K", "cloudOnly": False}])
    page.fill("#lib-q", "qwen2.5")
    page.locator("#lib-form").get_by_role("button", name="搜尋").click()
    result = page.locator("#lib-results .result").filter(has=page.locator(".item-name", has_text=re.compile(r"^qwen2\.5$")))
    expect(result).to_be_visible()
    result.get_by_role("button", name="看版本").click()
    return result


# ---- 004 US4-AJ-03


def test_勾Hugging_Face與官方的版本一起試算_確認視窗列兩列與總大小_確定後依序排入佇列(
    page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any
) -> None:
    # Arrange
    open_to_ready(page)
    fakes.huggingface.list_quants.returns(SMOL_QUANTS)
    fakes.huggingface.get_manifest.when(tag="Q8_0").returns({"sizeBytes": 144_811_072})
    fakes.model_library.get_manifest.when(name="qwen2.5", tag="latest").returns({"sizeBytes": QWEN_BYTES})
    world.fakes.remote_ollama.pull_model.gate()  # 下載停在第一筆,佇列的順序看得到
    result = search_smol(page, fakes)
    expand_quants(result)

    # Act
    quant_row(result, "Q8_0").locator("input[type=checkbox]").check()
    official_qwen25(page, fakes).locator(".version input[type=checkbox]").check()
    page.click("#add")
    confirm = page.locator('[data-state="confirm"]')
    expect(confirm).to_be_visible()
    rows = page.locator("#confirm-table tr")
    total = page.locator("#confirm-table tr.total")
    disk = page.locator("#confirm-disk")
    expect(rows).to_have_count(3)
    expect(total).to_contain_text("4.83 GB")
    expect(disk).to_contain_text("剩餘磁碟")
    page.click("#confirm-go")
    page.wait_for_url("**/models.html")

    # Assert
    jobs = api(e2e_servers, "GET", "/downloads").json()["jobs"]
    assert [j["model"] for j in jobs] == [HF_Q8, "qwen2.5:latest"]


# ---- 004 US4-AJ-04


def test_Hugging_Face搜尋逾時只影響它自己的搜尋區_官方搜尋照常可用(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    fakes.huggingface.search_models.raises("HF_TIMEOUT", "timed out")
    statuses: list[int] = []
    page.on("response", lambda r: statuses.append(r.status) if "/search?" in r.url else None)

    # Act
    hf_search(page, "qwen")
    down = page.locator('[data-state="hf-down"]')
    expect(down).to_be_visible()
    official = official_qwen25(page, fakes)

    # Assert
    expect(down).to_contain_text("暫時無法搜尋 Hugging Face")
    expect(official).to_be_visible()
    assert len(statuses) == 2 and 500 not in statuses, statuses


# ---- 004 US4-AJ-05


def test_Hugging_Face搜尋0筆時說找不到_並提示可以直接輸入名稱(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    fakes.huggingface.search_models.when(query="qwne", cursor=None).returns(hf_page(cursor=None))

    # Act
    hf_search(page, "qwne")

    # Assert
    empty = page.locator('[data-state="hf-empty"]')
    expect(empty).to_be_visible()
    expect(empty).to_contain_text("找不到符合「qwne」的 GGUF 模型")
    expect(empty).to_contain_text("直接輸入")


def add_direct(page: Page, name: str) -> None:
    """在直接輸入名稱的欄位輸入 `name`,按「加入勾選」。"""
    if not page.url.endswith("/library.html"):
        page.goto("/library.html")
    expect(page.locator("#name-form")).to_be_visible()
    page.fill("#direct", name)
    page.locator("#name-form").get_by_role("button", name="加入勾選").click()


HF_GATED = "hf.co/google/gemma-3-1b-it-qat-q4_0-gguf:Q4_0"
HF_Q4_L = f"hf.co/{SMOL_ID}:Q4_K_L"


# ---- 004 US4-AJ-06


def test_要登入與沒有這個量化版本的Hugging_Face名稱_分開說明且都沒有加入佇列(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    fakes.huggingface.get_manifest.when(model="gemma-3-1b-it-qat-q4_0-gguf").raises("HF_AUTH_REQUIRED", "gated repo")
    fakes.huggingface.get_manifest.when(tag="Q4_K_L").raises("HF_QUANT_UNAVAILABLE", "not a valid quantization")

    # Act
    add_direct(page, HF_GATED)
    auth = page.locator('[data-state="hf-auth-required"]')
    expect(auth).to_be_visible()
    auth_text = auth.inner_text()
    jobs_a = api(e2e_servers, "GET", "/downloads").json()["jobs"]
    auth.get_by_role("button", name="知道了").click()
    add_direct(page, HF_Q4_L)
    quant = page.locator('[data-state="hf-quant-unavailable"]')
    expect(quant).to_be_visible()
    jobs_b = api(e2e_servers, "GET", "/downloads").json()["jobs"]

    # Assert
    assert "要登入才能下載" in auth_text
    expect(quant).to_contain_text("這個量化版本無法下載")
    assert jobs_a == [] and jobs_b == []


def wait_completed(e2e_servers: Any, model: str, timeout: float = 5.0) -> None:
    """一直查 `GET /api/downloads` 直到 `model` 那一筆是 `completed`。"""
    deadline = time.monotonic() + timeout
    while True:
        jobs = {j["model"]: j["state"] for j in api(e2e_servers, "GET", "/downloads").json()["jobs"]}
        if jobs.get(model) == "completed" or time.monotonic() > deadline:
            assert jobs.get(model) == "completed", jobs
            return
        time.sleep(0.05)


# ---- 004 US4-AJ-07


def test_下載好的Hugging_Face模型出現在模型目錄與對話頁的模型選單(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    fakes.huggingface.get_manifest.returns({"sizeBytes": 105_455_145})
    reply = api(e2e_servers, "POST", "/downloads", json={"models": [HF_Q4]})
    assert reply.status_code in (200, 201, 202), reply.text
    wait_completed(e2e_servers, HF_Q4)

    # Act
    page.goto("/models.html")
    in_catalog = catalog_row(page, HF_Q4)
    expect(in_catalog).to_be_visible()
    page.goto("/chat.html")
    options = page.locator("#model option")
    expect(options.filter(has_text=HF_Q4)).to_have_count(1)

    # Assert
    assert HF_Q4 in options.all_inner_texts()


# ---- 004 US4-AJ-08

# 容許的英文字同 US2-AJ-12(另加 latest);主機名稱和模型名稱一樣先去掉再看
ALLOWED_WORDS = ("Hugging Face", "Colab", "token", "Ollama", "GGUF", "latest")
HOSTS = ("huggingface.co", "registry.ollama.ai")
HF_SLOW = "hf.co/unsloth/Qwen3-0.6B-GGUF:Q8_0"
NAMES = (HF_GATED, HF_Q4_L, HF_SLOW, HF_Q4, HF_Q8, f"hf.co/{SMOL_ID}", "Q4_K_M", "Q8_0", "Q4_K_L", "Q4_0", "qwen", "qwne")  # 搜尋的關鍵字是使用者輸入的,和模型名稱一樣去掉


def block_text(block: Locator, state: str) -> str:
    """區塊的 `innerText` 去掉模型名稱、量化版本與主機名稱之後,沒有連續 4 個以上的英文字母(容許清單除外),且至少有一個中文字。"""
    expect(block.first).to_be_visible()
    text = "\n".join(block.all_inner_texts())
    raw = text
    for removed in (*NAMES, *HOSTS, *ALLOWED_WORDS):
        text = text.replace(removed, "")
    words = re.findall(r"[A-Za-z]{4,}", text)
    assert words == [], f"{state}:出現英文 {words}"
    assert re.search(r"[一-鿿]", text), f"{state}:沒有中文字"
    return raw


def test_Hugging_Face搜尋區與說明畫面都是繁體中文_不顯示Hugging_Face的英文原文(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    hub = fakes.huggingface
    hub.search_models.when(query="qwen").returns(hf_page(SMOL_ID, cursor=None))
    hub.search_models.when(query="qwne").returns(hf_page(cursor=None))
    hub.search_models.when(query="down").raises("HF_UNREACHABLE", "Invalid username or password.")
    hub.list_quants.raises("HF_TIMEOUT", "Read timed out")
    hub.get_manifest.when(model="gemma-3-1b-it-qat-q4_0-gguf").raises("HF_AUTH_REQUIRED", "Invalid username or password.")
    hub.get_manifest.when(tag="Q4_K_L").raises("HF_QUANT_UNAVAILABLE", "not a valid quantization")
    hub.get_manifest.when(model="Qwen3-0.6B-GGUF").raises("HF_TIMEOUT", "Read timed out")
    texts: dict[str, str] = {}

    # Act
    hf_search(page, "qwen")
    texts["hf-results"] = block_text(page.locator('[data-state="hf-results"], #hf-results-box'), "hf-results")
    expand_quants(hf_result(page, SMOL_ID))
    texts["hf-expand-down"] = block_text(page.locator('[data-state="hf-expand-down"]'), "hf-expand-down")
    hf_search(page, "qwne")
    texts["hf-empty"] = block_text(page.locator('[data-state="hf-empty"]'), "hf-empty")
    hf_search(page, "down")
    texts["hf-down"] = block_text(page.locator('[data-state="hf-down"]'), "hf-down")
    for name, state in ((HF_GATED, "hf-auth-required"), (HF_Q4_L, "hf-quant-unavailable"), (HF_SLOW, "hf-size-down")):
        add_direct(page, name)
        sheet = page.locator(f'[data-state="{state}"]')
        texts[state] = block_text(sheet, state)
        sheet.get_by_role("button", name="知道了").click()

    # Assert
    assert sorted(texts) == sorted(
        ["hf-results", "hf-empty", "hf-down", "hf-expand-down", "hf-auth-required", "hf-quant-unavailable", "hf-size-down"]
    )
    for state, text in texts.items():
        assert "Invalid username" not in text and "not a valid quantization" not in text and "timed out" not in text, (state, text)


# ---- 004 US4-AJ-09


def test_沒有GGUF模型檔的repo試算回量化版本無法下載時_說明含不是GGUF且沒有加入佇列(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    open_to_ready(page)
    fakes.huggingface.get_manifest.raises("HF_QUANT_UNAVAILABLE", "not a valid quantization")

    # Act
    add_direct(page, "hf.co/ggml-org/Qwen2.5-VL-7B-Instruct-mmproj-GGUF:Q4_K_M")
    sheet = page.locator('[data-state="hf-quant-unavailable"]')
    expect(sheet).to_be_visible()

    # Assert
    expect(sheet).to_contain_text("不是 GGUF")
    assert "沒有可下載的 GGUF 檔" not in page.locator("body").inner_text()
    assert api(e2e_servers, "GET", "/downloads").json()["jobs"] == []


# ---- 004 US4-AJ-10


def test_展開時Hugging_Face連不到_回應錯誤或看不懂_都說暫時無法使用且不顯示代碼(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange
    seen: dict[str, tuple[bool, str]] = {}

    # Act
    for code in ("HF_UNREACHABLE", "HF_SERVER_ERROR", "HF_BAD_RESPONSE"):
        fakes.huggingface.list_quants.raises(code, code.lower())
        page.goto("/library.html")
        expand_quants(search_smol(page, fakes))
        down = page.locator('[data-state="hf-expand-down"]')
        try:
            down.wait_for(state="visible", timeout=2_000)
        except Exception:
            pass
        seen[code] = (down.is_visible(), page.locator("main").inner_text())

    # Assert
    assert {code: visible for code, (visible, _) in seen.items()} == {"HF_UNREACHABLE": True, "HF_SERVER_ERROR": True, "HF_BAD_RESPONSE": True}
    for code, (_, text) in seen.items():
        assert "Hugging Face 暫時無法使用" in text, code
        assert re.search(r"HF_[A-Z]", text) is None, (code, text)


# ---- 004 US4-AJ-11


def test_沒有工作階段時直接輸入Hugging_Face名稱_只檢查格式就加入勾選且不取大小(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any) -> None:
    # Arrange:沒有工作階段
    fakes.huggingface.get_manifest.reset_calls()

    # Act
    add_direct(page, HF_SLOW)

    # Assert
    unchecked = page.locator('[data-state="direct-unchecked"]')
    expect(unchecked).to_be_visible()
    expect(unchecked).to_contain_text("只檢查名稱的格式")
    expect(page.locator("#tray")).to_contain_text(HF_SLOW)
    assert len(fakes.huggingface.get_manifest.calls) == 0
