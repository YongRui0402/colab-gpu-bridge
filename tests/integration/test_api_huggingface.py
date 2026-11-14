"""E2 後端 UI API:Hugging Face 搜尋與展開(testplan.md § 5.3,`/api/huggingface` › 搜尋、展開)。

接縫:HTTP `/api/*`,五個轉接層用替身;Hugging Face 用 `FakeHuggingFaceHub`(`fakes.huggingface`,plan.md Q36、Q49、Q65)。
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx

from cgb.app import AppPair
from cgb.domain.errors import MESSAGES
from conftest import TEST_TIMEOUTS
from integration.test_api_curated import curate
from integration.test_api_downloads import downloadable
from integration.test_api_library import search_page
from integration.test_api_models import set_tags, tag
from integration.test_api_recovery import running
from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    ColabWorld,
    error_code,
    open_ready,
    ui_client,
)

# 故事 4 的測試資料(testplan.md § 5.3)
HF_Q4 = "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"
QWEN_GGUF = {"id": "unsloth/Qwen3-0.6B-GGUF", "downloads": 1_200_000}
SMOLLM_GGUF = {"id": "bartowski/SmolLM2-135M-Instruct-GGUF", "downloads": 80_000}
LLAMA_GGUF = {"id": "bartowski/Llama-3.2-1B-Instruct-GGUF", "downloads": 50_000}


def hf_page(*models: dict[str, Any], next_cursor: str | None = None) -> dict[str, Any]:
    """`HuggingFaceHub.search_models` 的回傳(plan.md Q49)。"""
    return {"items": list(models), "nextCursor": next_cursor}


def hf_quants(*quants: tuple[str, int]) -> list[dict[str, Any]]:
    """`HuggingFaceHub.list_quants` 的回傳(plan.md Q49):每個 (量化名稱, 大小位元組)。"""
    return [{"quant": quant, "sizeBytes": size} for quant, size in quants]


# ---- 004 US4-API-01


async def test_搜尋去掉關鍵字前後空白_依下載次數列出並帶出下一頁的_cursor(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.huggingface.search_models.returns(hf_page(QWEN_GGUF, SMOLLM_GGUF, next_cursor="c1"))

    # Act
    response = await ui_client.get("/api/huggingface/search?q=%20qwen%20")
    page = response.json() if response.status_code == 200 else {}

    # Assert
    assert response.status_code == 200
    assert [item["name"] for item in page.get("items", [])] == [
        "hf.co/unsloth/Qwen3-0.6B-GGUF",
        "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF",
    ]
    assert page.get("query") == "qwen"
    assert (page.get("hasMore"), page.get("nextCursor")) == (True, "c1")
    assert [call.kwargs for call in fakes.huggingface.search_models.calls] == [{"query": "qwen", "cursor": None}]
    assert fakes.remote_ollama.list_local_models.call_count == 0


# ---- 004 US4-API-02


async def test_載入更多時把_cursor_原樣交給轉接層_最後一頁沒有下一頁(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段;沒帶 cursor 的是第一頁,帶 `c1` 的是最後一頁
    ColabWorld(fakes)
    fakes.huggingface.search_models.returns(hf_page(QWEN_GGUF, next_cursor="c1"))
    fakes.huggingface.search_models.when(cursor="c1").returns(hf_page(LLAMA_GGUF, next_cursor=None))

    # Act
    response = await ui_client.get("/api/huggingface/search", params={"q": "qwen", "cursor": "c1"})
    page = response.json() if response.status_code == 200 else {}

    # Assert
    assert response.status_code == 200
    assert [item["name"] for item in page.get("items", [])] == ["hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF"]
    assert (page.get("hasMore"), page.get("nextCursor")) == (False, None)
    assert [call.kwargs for call in fakes.huggingface.search_models.calls] == [{"query": "qwen", "cursor": "c1"}]


# ---- 004 US4-API-03


async def test_沒有符合的模型時照樣回_200_與空的清單(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段;轉接層回 0 筆
    ColabWorld(fakes)
    fakes.huggingface.search_models.returns(hf_page(next_cursor=None))

    # Act
    response = await ui_client.get("/api/huggingface/search", params={"q": "zzzqqqnonexist"})
    page = response.json() if response.status_code == 200 else {}

    # Assert
    assert response.status_code == 200
    assert (page.get("items"), page.get("hasMore")) == ([], False)


# ---- 004 US4-API-04


async def test_關鍵字或_cursor_不合格時回_400_而且沒有送到_Hugging_Face(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.huggingface.search_models.returns(hf_page(QWEN_GGUF, next_cursor=None))
    requests = {
        "A 只有空白": {"q": "   "},
        "B 101 個字元": {"q": "q" * 101},
        "C 沒帶 q": {},
        "D cursor 是空字串": {"q": "qwen", "cursor": ""},
    }

    # Act
    results = {}
    for case, params in requests.items():
        response = await ui_client.get("/api/huggingface/search", params=params)
        results[case] = (response.status_code, error_code(response))

    # Assert
    assert results == {
        "A 只有空白": (400, "INVALID_QUERY"),
        "B 101 個字元": (400, "INVALID_QUERY"),
        "C 沒帶 q": (400, "INVALID_QUERY"),
        "D cursor 是空字串": (400, "INVALID_CURSOR"),
    }
    assert fakes.huggingface.search_models.call_count == 0


# ---- 004 US4-API-05


async def test_搜尋時_Hugging_Face_失敗依代碼回_502_或_504_本文不帶_model(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    codes = ["HF_UNREACHABLE", "HF_SERVER_ERROR", "HF_BAD_RESPONSE", "HF_TIMEOUT"]

    # Act
    results = {}
    for code in codes:
        fakes.huggingface.search_models.raises(code)
        response = await ui_client.get("/api/huggingface/search", params={"q": "qwen"})
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        results[code] = (response.status_code, error_code(response), "model" in body)

    # Assert
    assert results == {
        "HF_UNREACHABLE": (502, "HF_UNREACHABLE", False),
        "HF_SERVER_ERROR": (502, "HF_SERVER_ERROR", False),
        "HF_BAD_RESPONSE": (502, "HF_BAD_RESPONSE", False),
        "HF_TIMEOUT": (504, "HF_TIMEOUT", False),
    }


# ---- 004 US4-API-06


async def test_Hugging_Face_全部失敗時官方搜尋_精選清單與官方名稱的試算照常(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:工作階段就緒;精選清單有 `qwen2.5:7b`;Hugging Face 的三個方法都失敗
    downloadable(fakes)
    await open_ready(ui_client)
    await curate(ui_client, "qwen2.5:7b", auto=False)
    fakes.model_library.search_library.returns(search_page("qwen2.5", has_more=False))
    fakes.huggingface.search_models.raises("HF_TIMEOUT")
    fakes.huggingface.list_quants.raises("HF_UNREACHABLE")
    fakes.huggingface.get_manifest.raises("HF_UNREACHABLE")

    # Act
    hf_search = await ui_client.get("/api/huggingface/search", params={"q": "qwen"})
    expanded = await ui_client.get("/api/huggingface/models/bartowski/SmolLM2-135M-Instruct-GGUF/quants")
    library = await ui_client.get("/api/library/search", params={"q": "qwen2.5"})
    curated = await ui_client.get("/api/curated")
    estimated = await ui_client.post("/api/downloads/estimate", json={"models": ["qwen2.5:7b"]})

    # Assert
    assert [
        (hf_search.status_code, error_code(hf_search)),
        (expanded.status_code, error_code(expanded)),
        library.status_code,
        curated.status_code,
        estimated.status_code,
    ] == [(504, "HF_TIMEOUT"), (502, "HF_UNREACHABLE"), 200, 200, 200]
    assert library.json()["items"][0]["name"] == "qwen2.5"
    assert curated.json()["items"][0]["name"] == "qwen2.5:7b"
    assert estimated.json()["totalBytes"] == 4_683_087_332
    assert fakes.huggingface.get_manifest.call_count == 0


# ---- 004 US4-API-07

SMOLLM_QUANTS = "bartowski/SmolLM2-135M-Instruct-GGUF"


async def test_展開時依檔案清單列出量化版本_並不分大小寫標出執行環境上已下載的(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:工作階段就緒;執行環境上有大小寫不同的 `hf.co/Bartowski/smollm2-135m-instruct-gguf:q4_k_m`
    downloadable(fakes)
    await open_ready(ui_client)
    fakes.huggingface.list_quants.returns(hf_quants(("Q4_K_M", 105_455_145), ("Q8_0", 144_806_689)))
    set_tags(fakes, tag("hf.co/Bartowski/smollm2-135m-instruct-gguf:q4_k_m", 105_455_694))
    fakes.remote_ollama.list_local_models.reset_calls()

    # Act
    response = await ui_client.get(f"/api/huggingface/models/{SMOLLM_QUANTS}/quants")
    listed = response.json() if response.status_code == 200 else {}

    # Assert
    assert response.status_code == 200
    assert listed.get("runtimeChecked") is True
    assert [(q["name"], q["sizeBytes"], q["downloaded"]) for q in listed.get("quants", [])] == [
        ("hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M", 105_455_145, True),
        ("hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q8_0", 144_806_689, False),
    ]
    assert [call.kwargs for call in fakes.huggingface.list_quants.calls] == [
        {"author": "bartowski", "model": "SmolLM2-135M-Instruct-GGUF"}
    ]
    assert fakes.remote_ollama.list_local_models.call_count == 1


# ---- 004 US4-API-08


async def test_展開時模型清單讀不到或讀太久只讓_runtimeChecked_為_false_期限從收到請求起算(
    make_app: Callable[..., AppPair], fakes: Any
) -> None:
    # Arrange:Hugging Face 這一段要 0.2 秒;展開的期限縮短成 0.3 秒(plan.md Q44)
    async def slow_quants(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        await asyncio.sleep(0.2)
        return hf_quants(("Q4_K_M", 105_455_145))

    downloadable(fakes)
    fakes.huggingface.list_quants.side_effect(slow_quants)
    path = f"/api/huggingface/models/{SMOLLM_QUANTS}/quants"
    async with running(make_app(timeouts=replace(TEST_TIMEOUTS, hf_expand_deadline=0.3))) as client:

        async def expand() -> tuple[Any, ...]:
            started = time.monotonic()
            try:
                response = await asyncio.wait_for(client.get(path), timeout=2.0)
            except TimeoutError:
                return ("2 秒內沒有回應",)
            listed = response.json() if response.status_code == 200 else {}
            elapsed = time.monotonic() - started
            return (response.status_code, listed.get("runtimeChecked"), [q["downloaded"] for q in listed.get("quants", [])], elapsed)

        # Act
        no_session = await expand()
        calls_without_session = fakes.remote_ollama.list_local_models.call_count
        await open_ready(client)
        fakes.remote_ollama.list_local_models.raises("OLLAMA_UNREACHABLE")
        unreadable = await expand()
        gate = fakes.remote_ollama.list_local_models.gate()
        never_read = await expand()
        gate.release()

    # Assert
    assert no_session[:3] == (200, False, [False])  # 則1:沒有工作階段
    assert calls_without_session == 0  # 則2
    assert unreadable[:3] == (200, False, [False])  # 則3:模型清單讀失敗
    assert never_read[:2] == (200, False)  # 則4:模型清單一直不放行
    assert 0.3 <= never_read[3] <= 0.45  # 則5:兩段平行、都從收到請求起算;串接時至少 0.5 秒


# ---- 004 US4-API-09


async def test_展開需要登入或沒有_GGUF_的模型回_422_並說明原因(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)

    # Act
    responses = {}
    for code in ["HF_AUTH_REQUIRED", "HF_NO_GGUF"]:
        fakes.huggingface.list_quants.raises(code)
        responses[code] = await ui_client.get("/api/huggingface/models/google/gemma-3-1b-it-qat-q4_0-gguf/quants")
    bodies = {
        code: response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        for code, response in responses.items()
    }

    # Assert
    assert {code: (response.status_code, error_code(response)) for code, response in responses.items()} == {
        "HF_AUTH_REQUIRED": (422, "HF_AUTH_REQUIRED"),
        "HF_NO_GGUF": (422, "HF_NO_GGUF"),
    }
    assert bodies["HF_AUTH_REQUIRED"]["message"] == MESSAGES["HF_AUTH_REQUIRED"]
    assert "這一輪不支援" in bodies["HF_AUTH_REQUIRED"]["message"]
    assert not any("model" in body for body in bodies.values())


# ---- 004 US4-API-10


async def test_展開時_Hugging_Face_連不到_出錯或逾時依代碼回_502_或_504(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:工作階段就緒,執行環境上沒有模型
    downloadable(fakes)
    await open_ready(ui_client)
    codes = ["HF_UNREACHABLE", "HF_SERVER_ERROR", "HF_BAD_RESPONSE", "HF_TIMEOUT"]

    # Act
    results = {}
    for code in codes:
        fakes.huggingface.list_quants.raises(code)
        response = await ui_client.get(f"/api/huggingface/models/{SMOLLM_QUANTS}/quants")
        body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        results[code] = (response.status_code, error_code(response), "model" in body)

    # Assert
    assert results == {
        "HF_UNREACHABLE": (502, "HF_UNREACHABLE", False),
        "HF_SERVER_ERROR": (502, "HF_SERVER_ERROR", False),
        "HF_BAD_RESPONSE": (502, "HF_BAD_RESPONSE", False),
        "HF_TIMEOUT": (504, "HF_TIMEOUT", False),
    }


# ---- 004 US4-API-11


async def test_展開的作者或模型名稱組不出_hf_co_名稱時回_400_而且沒有送到_Hugging_Face(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.huggingface.list_quants.returns(hf_quants(("Q4_K_M", 1)))
    paths = {
        "A 作者開頭是連字號": "-bartowski/SmolLM2-135M-Instruct-GGUF",
        "B 模型名稱含空白": "bartowski/Smol%20LM",
        "C 作者開頭是底線": "_x/SmolLM2-135M-Instruct-GGUF",
    }

    # Act
    results = {}
    for case, path in paths.items():
        response = await ui_client.get(f"/api/huggingface/models/{path}/quants")
        results[case] = (response.status_code, error_code(response))

    # Assert
    assert results == {case: (400, "INVALID_HF_MODEL_ID") for case in paths}
    assert fakes.huggingface.list_quants.call_count == 0
