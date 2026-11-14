"""E2 後端 UI API:精選清單(testplan.md § 4.1,`/api/curated` › 新增、修改、移除)。

接縫:HTTP `/api/*`,五個轉接層用替身;精選清單存在 SQLite(contracts/store.dbml § Table curated_models)。
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any

import httpx

from cgb.adapters.errors import AdapterError
from integration.test_api_downloads import downloadable, set_library
from integration.test_api_models import set_tags, tag
from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    ColabWorld,
    error_code,
    open_ready,
    ui_client,
)

# 故事 3 的測試資料(testplan.md § 4.1)
HF_SMOL = "hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"
HF_SMOL_BYTES = 105_471_520


def set_hf(fakes: Any, sizes: dict[str, int], raises: dict[str, str] | None = None) -> None:
    """`FakeHuggingFaceHub.get_manifest` 依 `hf.co/<作者>/<模型>:<tag>` 回 `sizes` 裡的大小,其他回 `HF_AUTH_REQUIRED`(plan.md Q36、Q65)。

    `raises` 對某個完整名稱指定要丟的代碼(例:`{"hf.co/x/y:Q4_0": "HF_QUANT_UNAVAILABLE"}`),優先於 `sizes`(testplan.md § 5.3)。
    """
    failing = raises or {}

    def manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        full = f"hf.co/{kwargs['author']}/{kwargs['model']}:{kwargs['tag']}"
        if full in failing:
            raise AdapterError(failing[full], "manifest failure")
        if full not in sizes:
            raise AdapterError("HF_AUTH_REQUIRED", "manifest unknown")
        return {"sizeBytes": sizes[full]}

    fakes.huggingface.get_manifest.side_effect(manifest)


def error_model(response: httpx.Response) -> str | None:
    """錯誤回應的 `Error.model`;本文不是 JSON 時是 None(和 `error_code` 一致)。"""
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json().get("model")
    return None


async def curate(client: httpx.AsyncClient, name: str, auto: bool = True) -> dict[str, Any]:
    """`POST /api/curated` 並斷言 201,回傳那一筆。"""
    response = await client.post("/api/curated", json={"name": name, "autoDownload": auto})
    assert response.status_code == 201, response.text
    return response.json()


async def wait_auto(client: httpx.AsyncClient, predicate: Callable[[Any], bool], timeout: float = 1.0) -> Any:
    """一直查 `GET /api/downloads/auto-result`,直到 `predicate(result)` 成立或逾時;回傳最後一次的 `result`。"""
    deadline = time.monotonic() + timeout
    result = (await client.get("/api/downloads/auto-result")).json().get("result")
    while not predicate(result) and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
        result = (await client.get("/api/downloads/auto-result")).json().get("result")
    return result


# ---- 004 US3-API-01


async def test_新增的精選項目補_latest_大小寫照原樣_沒給自動下載就是關_也不向模型來源查證(
    ui_client: httpx.AsyncClient, fakes: Any
) -> None:
    # Arrange:沒有工作階段,精選清單是空的
    ColabWorld(fakes)
    set_library(fakes)
    set_hf(fakes, {HF_SMOL: HF_SMOL_BYTES})

    # Act
    first = await ui_client.post(
        "/api/curated",
        json={"name": "qwen2.5", "description": "日常用", "recommendedRuntimeType": {"gpu": "T4", "highMem": False}},
    )
    second = await ui_client.post(
        "/api/curated", json={"name": "hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF", "autoDownload": True}
    )
    listed = (await ui_client.get("/api/curated")).json()

    # Assert
    assert (first.status_code, second.status_code) == (201, 201)  # 則1
    assert (first.json().get("name"), first.json().get("autoDownload")) == ("qwen2.5:latest", False)  # 則2、則3
    assert (second.json().get("name"), second.json().get("autoDownload")) == (
        "hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:latest",
        True,
    )  # 則4、則5
    items = listed.get("items", [])
    assert [item.get("name") for item in items] == ["qwen2.5:latest", "hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:latest"]  # 則6
    assert (items[0].get("recommendedRuntimeType"), items[0].get("description")) == ({"gpu": "T4", "highMem": False}, "日常用")  # 則6
    assert listed.get("runtimeChecked") is False  # 則7
    assert (fakes.model_library.get_manifest.call_count, fakes.huggingface.get_manifest.call_count) == (0, 0)  # 則8


# ---- 004 US3-API-02


async def test_修改整筆取代_id_與順序不變(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:依序新增三筆(id 為 a、b、c)
    ColabWorld(fakes)
    ids = [(await curate(ui_client, name, auto=False))["id"] for name in ("qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:7b")]
    sent = {
        "name": HF_SMOL,
        "description": "小模型",
        "recommendedRuntimeType": {"gpu": "L4", "highMem": True},
        "autoDownload": True,
    }

    # Act
    updated = await ui_client.put(f"/api/curated/{ids[1]}", json=sent)
    listed = (await ui_client.get("/api/curated")).json()

    # Assert
    assert (updated.status_code, updated.json().get("id")) == (200, ids[1])  # 則1
    assert {key: updated.json().get(key) for key in sent} == sent  # 則2
    assert [item.get("id") for item in listed.get("items", [])] == ids  # 則3
    assert listed["items"][1].get("name") == HF_SMOL  # 則4


# ---- 004 US3-API-03


async def test_修改只帶名稱時說明與建議類型清空_自動下載關閉(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    created = await ui_client.post(
        "/api/curated",
        json={
            "name": "qwen2.5:7b",
            "description": "日常用",
            "recommendedRuntimeType": {"gpu": "T4", "highMem": False},
            "autoDownload": True,
        },
    )
    curated_id = created.json()["id"]

    # Act
    updated = await ui_client.put(f"/api/curated/{curated_id}", json={"name": "qwen2.5:7b"})
    listed = (await ui_client.get("/api/curated")).json()

    # Assert
    assert updated.status_code == 200  # 則1
    item = listed["items"][0]
    assert (item.get("description"), item.get("recommendedRuntimeType"), item.get("autoDownload")) == (None, None, False)  # 則2~4


# ---- 004 US3-API-04


async def test_刪除與修改不存在的項目回_404_CURATED_NOT_FOUND(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:依序新增三筆(id 為 a、b、c)
    ColabWorld(fakes)
    ids = [(await curate(ui_client, name, auto=False))["id"] for name in ("qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:7b")]

    # Act
    first = await ui_client.delete(f"/api/curated/{ids[1]}")
    second = await ui_client.delete(f"/api/curated/{ids[1]}")
    updated = await ui_client.put(f"/api/curated/{ids[1]}", json={"name": "qwen2.5:1.5b"})
    missing = await ui_client.delete("/api/curated/999")
    listed = (await ui_client.get("/api/curated")).json()

    # Assert
    assert first.status_code == 204  # 則1
    assert (second.status_code, error_code(second)) == (404, "CURATED_NOT_FOUND")  # 則2
    assert (updated.status_code, error_code(updated)) == (404, "CURATED_NOT_FOUND")  # 則3
    assert (missing.status_code, error_code(missing)) == (404, "CURATED_NOT_FOUND")  # 則4
    assert [item.get("id") for item in listed.get("items", [])] == [ids[0], ids[2]]  # 則5


# ---- 004 US3-API-05


async def test_新增時補過版本後不分大小寫相同就算重複_回清單裡已有的名稱(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    for name in ("qwen2.5", HF_SMOL, "hf.co/unsloth/Qwen3-0.6B-GGUF"):
        await curate(ui_client, name, auto=False)

    # Act
    case_a = await ui_client.post("/api/curated", json={"name": "qwen2.5:LATEST"})
    case_b = await ui_client.post("/api/curated", json={"name": "hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m"})
    case_c = await ui_client.post("/api/curated", json={"name": "hf.co/UNSLOTH/qwen3-0.6b-gguf:latest"})
    control_d = await ui_client.post("/api/curated", json={"name": "hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:Q8_0"})
    control_e = await ui_client.post("/api/curated", json={"name": "qwen2.5:7b"})
    listed = (await ui_client.get("/api/curated")).json()

    # Assert
    duplicates = [(r.status_code, error_code(r), error_model(r)) for r in (case_a, case_b, case_c)]
    assert duplicates == [
        (409, "CURATED_DUPLICATE", "qwen2.5:latest"),
        (409, "CURATED_DUPLICATE", HF_SMOL),
        (409, "CURATED_DUPLICATE", "hf.co/unsloth/Qwen3-0.6B-GGUF:latest"),
    ]  # 則1~3
    assert (control_d.status_code, control_e.status_code) == (201, 201)  # 則4、則5
    assert len(listed.get("items", [])) == 5  # 則6


# ---- 004 US3-API-06


async def test_修改撞到別筆回_409_只改自己的大小寫不算重複(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    a = (await curate(ui_client, HF_SMOL, auto=False))["id"]
    b = (await curate(ui_client, "qwen2.5:7b", auto=False))["id"]

    # Act
    into_a = await ui_client.put(f"/api/curated/{b}", json={"name": "hf.co/bartowski/SMOLLM2-135M-Instruct-GGUF:q4_k_m"})
    own_case = await ui_client.put(f"/api/curated/{a}", json={"name": "hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m"})
    listed = {item["id"]: item["name"] for item in (await ui_client.get("/api/curated")).json().get("items", [])}

    # Assert
    assert (into_a.status_code, error_code(into_a), error_model(into_a)) == (409, "CURATED_DUPLICATE", HF_SMOL)  # 則1
    assert own_case.status_code == 200  # 則2
    assert listed[a] == "hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m"  # 則3
    assert listed[b] == "qwen2.5:7b"  # 則4


# ---- 004 US3-API-07


async def test_名稱不合法回_400_INVALID_MODEL_NAME_新增與修改都不查證名稱(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:清單裡已有 `qwen2.5:7b`(id a)
    ColabWorld(fakes)
    set_library(fakes)
    set_hf(fakes, {HF_SMOL: HF_SMOL_BYTES})
    a = (await curate(ui_client, "qwen2.5:7b", auto=False))["id"]
    invalid_bodies: list[dict[str, Any]] = [
        {"name": "Qwen2.5"},
        {"name": "huggingface.co/bartowski/x-GGUF"},
        {"name": "HF.co/bartowski/x-GGUF"},
        {"name": "bartowski/x"},
        {"name": "hf.co/bartowski"},
        {"name": ""},
        {"name": 123},
        {"description": "x"},
    ]

    # Act
    added = [await ui_client.post("/api/curated", json=body) for body in invalid_bodies]
    updated = await ui_client.put(f"/api/curated/{a}", json={"name": "Qwen2.5"})
    listed = (await ui_client.get("/api/curated")).json()

    # Assert
    assert [(r.status_code, error_code(r)) for r in added] == [(400, "INVALID_MODEL_NAME")] * 8  # 則1
    assert error_model(added[0]) == "Qwen2.5"  # 則2
    assert (updated.status_code, error_code(updated)) == (400, "INVALID_MODEL_NAME")  # 則3
    assert [item.get("name") for item in listed.get("items", [])] == ["qwen2.5:7b"]  # 則4
    assert (fakes.model_library.get_manifest.call_count, fakes.huggingface.get_manifest.call_count) == (0, 0)  # 則5


# ---- 004 US3-API-08


def invalid_body_cases(names: list[str]) -> dict[str, dict[str, Any]]:
    """US3-API-08 情況 A~H 的請求參數(`httpx` 的 `content` 或 `json`);`names` 依序給情況 C 對照、C、D~H 各自的合法名稱。"""
    control, long_text, gpu, high_mem, no_gpu, auto_text, auto_int = names
    return {
        "A": {"content": b'{"name":', "headers": {"Content-Type": "application/json"}},
        "B": {"content": b"[]", "headers": {"Content-Type": "application/json"}},
        "C": {"json": {"name": long_text, "description": "字" * 201}},
        "C對照": {"json": {"name": control, "description": "字" * 200}},
        "D": {"json": {"name": gpu, "recommendedRuntimeType": {"gpu": "V100", "highMem": False}}},
        "E": {"json": {"name": high_mem, "recommendedRuntimeType": {"gpu": "T4", "highMem": "no"}}},
        "F": {"json": {"name": no_gpu, "recommendedRuntimeType": {"highMem": False}}},
        "G": {"json": {"name": auto_text, "autoDownload": "true"}},
        "H": {"json": {"name": auto_int, "autoDownload": 1}},
    }


async def test_新增時本文格式_說明長度_建議類型與自動下載不合法都回_400(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    cases = invalid_body_cases(["qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b", "qwen2.5:72b"])

    # Act
    responses = {label: await ui_client.post("/api/curated", **kwargs) for label, kwargs in cases.items()}
    listed = (await ui_client.get("/api/curated")).json()

    # Assert
    outcome = {label: (r.status_code, error_code(r)) for label, r in responses.items()}
    assert (outcome["A"], outcome["B"]) == ((400, "INVALID_REQUEST_BODY"), (400, "INVALID_REQUEST_BODY"))  # 則1
    assert outcome["C"] == (400, "INVALID_CURATED_DESCRIPTION")  # 則2
    assert responses["C對照"].status_code == 201  # 則3
    assert [outcome[label] for label in "DEF"] == [(400, "INVALID_RUNTIME_TYPE")] * 3  # 則4
    assert [outcome[label] for label in "GH"] == [(400, "INVALID_AUTO_DOWNLOAD")] * 2  # 則5
    assert [item.get("name") for item in listed.get("items", [])] == ["qwen2.5:0.5b"]  # 則6


# ---- 004 US3-API-09


async def test_修改時本文不合法也都回_400_失敗的請求不改資料(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    created = await ui_client.post("/api/curated", json={"name": "qwen2.5:7b", "description": "日常用", "autoDownload": True})
    path = f"/api/curated/{created.json()['id']}"
    cases = invalid_body_cases(["qwen2.5:7b"] * 7)

    # Act
    responses = {label: await ui_client.put(path, **kwargs) for label, kwargs in cases.items() if label != "C對照"}
    before_control = (await ui_client.get("/api/curated")).json()["items"][0]
    control = await ui_client.put(path, **cases["C對照"])
    after_control = (await ui_client.get("/api/curated")).json()["items"][0]

    # Assert
    outcome = {label: (r.status_code, error_code(r)) for label, r in responses.items()}
    assert (outcome["A"], outcome["B"]) == ((400, "INVALID_REQUEST_BODY"), (400, "INVALID_REQUEST_BODY"))  # 則1
    assert outcome["C"] == (400, "INVALID_CURATED_DESCRIPTION")  # 則2
    assert [outcome[label] for label in "DEF"] == [(400, "INVALID_RUNTIME_TYPE")] * 3  # 則3
    assert [outcome[label] for label in "GH"] == [(400, "INVALID_AUTO_DOWNLOAD")] * 2  # 則4
    assert control.status_code == 200  # 則5
    assert (before_control["description"], before_control["recommendedRuntimeType"], before_control["autoDownload"]) == (
        "日常用",
        None,
        True,
    )  # 則6:A~H 沒有改動任何欄位
    assert after_control["description"] == "字" * 200  # 則6


# ---- 004 US3-API-10


async def test_建議類型是_H100_後端照常接受與列出(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    first = await ui_client.post(
        "/api/curated", json={"name": "qwen2.5:32b", "recommendedRuntimeType": {"gpu": "H100", "highMem": False}}
    )
    second = await ui_client.post("/api/curated", json={"name": "qwen2.5:7b"})

    # Act
    updated = await ui_client.put(
        f"/api/curated/{second.json().get('id')}",
        json={"name": "qwen2.5:7b", "recommendedRuntimeType": {"gpu": "H100", "highMem": True}},
    )
    listed = (await ui_client.get("/api/curated")).json()

    # Assert
    assert first.status_code == 201  # 則1
    assert updated.status_code == 200  # 則2
    types = [item.get("recommendedRuntimeType") for item in listed.get("items", [])]
    assert types == [{"gpu": "H100", "highMem": False}, {"gpu": "H100", "highMem": True}]  # 則3、則4


# ---- 004 US3-API-11


async def test_就緒時列出標出執行環境上已有的模型_不分大小寫_讀不到就不標(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:三項都不設自動下載
    downloadable(fakes)
    for name in (HF_SMOL, "qwen2.5:Latest", "qwen2.5:7b"):
        await curate(ui_client, name, auto=False)

    # Act
    no_session = (await ui_client.get("/api/curated")).json()
    await open_ready(ui_client)
    set_tags(
        fakes,
        tag("hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m", 105_471_520),
        tag("qwen2.5:latest", 4_683_087_332),
    )
    checked = (await ui_client.get("/api/curated")).json()
    fakes.remote_ollama.list_local_models.raises("OLLAMA_UNREACHABLE")
    unreachable = await ui_client.get("/api/curated")

    # Assert
    def downloaded(listed: dict[str, Any]) -> list[Any]:
        return [item.get("downloaded") for item in listed.get("items", [])]

    assert no_session.get("runtimeChecked") is False  # 則1
    assert downloaded(no_session) == [False, False, False]  # 則2
    assert checked.get("runtimeChecked") is True  # 則3
    assert downloaded(checked) == [True, True, False]  # 則4
    assert (unreachable.status_code, unreachable.json().get("runtimeChecked")) == (200, False)  # 則5
    assert downloaded(unreachable.json()) == [False, False, False]  # 則6


# ---------------------------------------------------------------- US3-API-24


# ---------------------------------------------------------------- US3-API-24


async def test_沒寫版本視為_latest_同一個模型不存兩筆(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:精選清單是空的
    ColabWorld(fakes)

    # Act
    first = await ui_client.post("/api/curated", json={"name": "qwen2.5:7b", "description": "日常用"})
    second = await ui_client.post("/api/curated", json={"name": "qwen2.5"})
    third = await ui_client.post("/api/curated", json={"name": "qwen2.5:latest"})
    first_id = first.json().get("id") if first.status_code == 201 else 0
    second_id = second.json().get("id") if second.status_code == 201 else 0
    updated = await ui_client.put(f"/api/curated/{first_id}", json={"name": "qwen2.5:7b", "description": "長" * 201})
    removed = await ui_client.delete(f"/api/curated/{second_id}")
    listed = (await ui_client.get("/api/curated")).json()

    # Assert
    assert (first.status_code, second.status_code) == (201, 201)
    assert (third.status_code, error_code(third)) == (409, "CURATED_DUPLICATE")
    assert (updated.status_code, error_code(updated)) == (400, "INVALID_CURATED_DESCRIPTION")
    assert removed.status_code == 204
    assert [item.get("name") for item in listed.get("items", [])] == ["qwen2.5:7b"]


# ---- 004 US3-API-38


async def test_修改的檢查順序是本文_id_重複_id_不存在時仍先驗本文(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有工作階段;清單裡有 `qwen2.5:7b`(id a)、`llama3.2:3b`(id b);id 999 不存在
    ColabWorld(fakes)
    a = (await curate(ui_client, "qwen2.5:7b", auto=False))["id"]
    await curate(ui_client, "llama3.2:3b", auto=False)

    # Act
    invalid_json = await ui_client.put("/api/curated/999", content=b'{"name":', headers={"Content-Type": "application/json"})
    invalid_name = await ui_client.put("/api/curated/999", json={"name": "Qwen2.5"})
    missing_id = await ui_client.put("/api/curated/999", json={"name": "llama3.2:3b"})
    duplicate = await ui_client.put(f"/api/curated/{a}", json={"name": "llama3.2:3B"})
    listed = (await ui_client.get("/api/curated")).json()["items"]

    # Assert
    assert (invalid_json.status_code, error_code(invalid_json)) == (400, "INVALID_REQUEST_BODY")  # 則1
    assert (invalid_name.status_code, error_code(invalid_name)) == (400, "INVALID_MODEL_NAME")  # 則2
    assert (missing_id.status_code, error_code(missing_id)) == (404, "CURATED_NOT_FOUND")  # 則3
    assert (duplicate.status_code, error_code(duplicate)) == (409, "CURATED_DUPLICATE")  # 則4
    assert [item["name"] for item in listed] == ["qwen2.5:7b", "llama3.2:3b"]  # 則5
