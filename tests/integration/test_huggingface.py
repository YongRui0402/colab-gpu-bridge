"""E12 Hugging Face Hub 轉接層(testplan.md § 5.1;接縫:`HuggingFaceHub` 的方法,對方是 `httpx.MockTransport`)。

huggingface.co 一律由 handler 代替,不連外網;每個 `HuggingFaceHub` 都注入 `transport`。
"""

import asyncio
import inspect
import json
import time
from collections.abc import Awaitable, Callable

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.adapters.huggingface import HuggingFaceHub


class Recorder:
    """MockTransport 的 handler(async):記下每個收到的請求,再交給 `reply` 決定回什麼(`reply` 可以是 async)。"""

    def __init__(self, reply: Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]) -> None:
        self.requests: list[httpx.Request] = []
        self._reply = reply

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self._reply(request)
        return await response if inspect.isawaitable(response) else response

    def hub(self, **kwargs: float) -> HuggingFaceHub:
        return HuggingFaceHub(transport=httpx.MockTransport(self), **kwargs)


def json_reply(body: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)


class HalfBody(httpx.AsyncByteStream):
    """先送出半截 JSON,再丟出指定的例外(模擬本文讀到一半才出事)。"""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def __aiter__(self):
        yield b'[{"_id":"1","id":"bartowski/SmolLM2-135M-Instruct-GGUF",'
        raise self._error


def half_body_reply(error: Exception) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, headers={"Content-Type": "application/json"}, stream=HalfBody(error))


# ---- 004 US4-HF-05


async def test_搜尋帶齊篩選與排序參數_不帶_token_與_Cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    """US4-HF-05:`HF_TOKEN` 設成假 token;handler 對 `GET /api/models` 回 200 `[]`。"""
    monkeypatch.setenv("HF_TOKEN", "cgb-test-假token")
    handler = Recorder(lambda request: json_reply([]))

    await handler.hub().search_models("qwen 2.5")

    # 則1:只有 1 個請求,GET https://huggingface.co/api/models
    assert len(handler.requests) == 1
    request = handler.requests[0]
    assert (request.method, request.url.scheme, request.url.host, request.url.path) == (
        "GET",
        "https",
        "huggingface.co",
        "/api/models",
    )
    # 則2:query 參數齊全(`expand[]` 兩次、`gated=false`、`limit=20`、`sort=downloads`、沒有 `cursor`)
    assert sorted(request.url.params.multi_items()) == [
        ("expand[]", "downloads"),
        ("expand[]", "gated"),
        ("filter", "gguf"),
        ("gated", "false"),
        ("limit", "20"),
        ("search", "qwen 2.5"),
        ("sort", "downloads"),
    ]
    # 則3、則4:不帶 Authorization 與 Cookie(本系統不帶 Hugging Face 的 token)
    assert "Authorization" not in request.headers
    assert "Cookie" not in request.headers


# ---- 004 US4-HF-06


async def test_搜尋結果依對方的順序回傳_並取出下一頁的_cursor() -> None:
    """US4-HF-06:handler 回 3 筆,`Link` 標頭帶 `rel="next"` 與已編碼的 cursor。"""
    link = '<https://huggingface.co/api/models?search=qwen&filter=gguf&cursor=eyJpZCI6IjMifQ%3D%3D>; rel="next"'
    body = [
        {"_id": "1", "id": "bartowski/SmolLM2-135M-Instruct-GGUF", "downloads": 5120, "gated": False},
        {"_id": "2", "id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF", "downloads": 3000, "gated": False},
        {"_id": "3", "id": "unsloth/Qwen3-0.6B-GGUF", "downloads": 10, "gated": False},
    ]
    handler = Recorder(lambda request: httpx.Response(200, json=body, headers={"Link": link}))

    result = await handler.hub().search_models("qwen")

    # 則1:`id` 依對方的順序
    assert [item["id"] for item in result["items"]] == [
        "bartowski/SmolLM2-135M-Instruct-GGUF",
        "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "unsloth/Qwen3-0.6B-GGUF",
    ]
    # 則2:`downloads` 依序為 5120、3000、10
    assert [item["downloads"] for item in result["items"]] == [5120, 3000, 10]
    # 則3:`nextCursor` 是解碼後的值
    assert result["nextCursor"] == "eyJpZCI6IjMifQ=="


# ---- 004 US4-HF-07


async def test_載入更多時帶回原樣的_cursor_其他參數照第一頁再帶一次() -> None:
    """US4-HF-07:`Link` 的網址帶了和本系統不同的 `limit`、`gated`;載入更多不能照抄它。"""
    link = '<https://huggingface.co/api/models?search=qwen&limit=2&gated=true&cursor=eyJpZCI6IjMifQ%3D%3D>; rel="next"'
    handler = Recorder(lambda request: httpx.Response(200, json=[], headers={"Link": link}))
    hub = handler.hub()

    await hub.search_models("qwen")
    await hub.search_models("qwen", cursor="eyJpZCI6IjMifQ==")

    # 則1:2 個請求
    assert len(handler.requests) == 2
    first, second = (request.url.params for request in handler.requests)
    # 則2:第 2 個請求的 cursor 是原樣的值(不重複編碼)
    assert second.get("cursor") == "eyJpZCI6IjMifQ=="
    # 則3:去掉 cursor 之後,其他參數和第 1 個請求相同
    assert sorted(item for item in second.multi_items() if item[0] != "cursor") == sorted(first.multi_items())


# ---- 004 US4-HF-08


async def test_沒有_rel_next_就是最後一頁_沒有符合的模型是正常結果() -> None:
    """US4-HF-08:A 沒有 `Link`;B 的 `Link` 是 `rel="prev"`;C 本文 `[]`、沒有 `Link`。"""
    one = [{"_id": "1", "id": "bartowski/SmolLM2-135M-Instruct-GGUF", "downloads": 5120, "gated": False}]
    prev = {"Link": '<https://huggingface.co/api/models?search=qwen&cursor=abc>; rel="prev"'}
    page_a = await Recorder(lambda request: httpx.Response(200, json=one)).hub().search_models("qwen")
    page_b = await Recorder(lambda request: httpx.Response(200, json=one, headers=prev)).hub().search_models("qwen")
    page_c = await Recorder(lambda request: httpx.Response(200, json=[])).hub().search_models("zzzqqqnonexist")

    # 則1、則2:A、B 都沒有下一頁
    assert page_a["nextCursor"] is None
    assert page_b["nextCursor"] is None
    # 則3、則4:C 沒有丟出例外,`items` 是空陣列、沒有下一頁
    assert page_c["items"] == []
    assert page_c["nextCursor"] is None


# ---- 004 US4-HF-09


async def test_搜尋結果略過組不出作者與模型的那一筆_downloads_型別不符不算格式不符() -> None:
    """US4-HF-09:6 筆裡 `onlyname`、`a/b/c`、`-bad/x` 組不出 `hf.co/<作者>/<模型>`;`downloads` 是字串的那一筆照列。"""
    body = [
        {"id": "bartowski/SmolLM2-135M-Instruct-GGUF", "downloads": 7},
        {"id": "onlyname"},
        {"id": "a/b/c"},
        {"id": "-bad/x"},
        {"id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF", "downloads": "很多"},
        {"id": "unsloth/Qwen3-0.6B-GGUF"},
    ]
    handler = Recorder(lambda request: json_reply(body))

    result = await handler.hub().search_models("qwen")

    # 則1:沒有丟出例外,只列組得出名稱的三筆
    assert [item["id"] for item in result["items"]] == [
        "bartowski/SmolLM2-135M-Instruct-GGUF",
        "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "unsloth/Qwen3-0.6B-GGUF",
    ]
    # 則2:`downloads` 不是整數或沒給就是 None
    assert [item["downloads"] for item in result["items"]] == [7, None, None]


# ---- 004 US4-HF-10


async def test_檔案清單只讀第一個回應_帶_recursive_不帶_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """US4-HF-10:第一個回應有 `Link` `rel="next"`,但只讀第一頁(Q3 決定 A)。"""
    monkeypatch.setenv("HF_TOKEN", "cgb-test-假token")
    base = "https://huggingface.co/api/models/bartowski/SmolLM2-135M-Instruct-GGUF/tree/main"

    def reply(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("cursor") == "p2":
            return json_reply([{"type": "file", "path": "SmolLM2-135M-Instruct-Q8_0.gguf", "size": 145}])
        link = f'<{base}?recursive=true&cursor=p2>; rel="next"'
        body = [{"type": "file", "path": "SmolLM2-135M-Instruct-Q4_K_M.gguf", "size": 105}]
        return httpx.Response(200, json=body, headers={"Link": link})

    handler = Recorder(reply)

    quants = await handler.hub().list_repo_files("bartowski", "SmolLM2-135M-Instruct-GGUF")

    # 則1:只有 1 個請求,URL 帶 `recursive=true`
    assert [str(request.url) for request in handler.requests] == [f"{base}?recursive=true"]
    # 則2:沒有 Authorization 與 Cookie
    assert "Authorization" not in handler.requests[0].headers
    assert "Cookie" not in handler.requests[0].headers
    # 則3:只有第一頁的 `Q4_K_M`
    assert quants == ["Q4_K_M"]


# ---- 004 US4-HF-11


async def test_檔案清單依_type_只取檔案_略過資料夾_mmproj_與分割檔重複() -> None:
    """US4-HF-11:TheBloke 式檔名、mmproj、分割檔、名稱結尾是 `.gguf` 的資料夾;`oid`、`lfs` 都沒給。"""
    body = [
        {"type": "directory", "path": "Q8_0"},
        {"type": "file", "path": "README.md", "size": 10},
        {"type": "file", "path": "llama-2-7b.Q4_K_M.gguf", "size": 100},
        {"type": "file", "path": "mmproj-model-f16.gguf", "size": 20},
        {"type": "file", "path": "Q8_0/llama-2-7b-Q8_0-00001-of-00002.gguf", "size": 50},
        {"type": "file", "path": "Q8_0/llama-2-7b-Q8_0-00002-of-00002.gguf", "size": 50},
        {"type": "directory", "path": "old.gguf"},
        {"type": "file", "path": "llama-2-7b.q4_k_m.gguf", "size": 100},
    ]
    handler = Recorder(lambda request: json_reply(body))

    quants = await handler.hub().list_repo_files("TheBloke", "Llama-2-7B-GGUF")

    # 則1:只有 `Q4_K_M` 與 `Q8_0`(不分大小寫去重、分割檔只算一個)
    assert quants == ["Q4_K_M", "Q8_0"]


# ---- 004 US4-HF-12


async def test_沒有可列的量化版本時檔案清單丟出_HF_NO_GGUF() -> None:
    """US4-HF-12:A 沒有 GGUF 檔;B 只有 mmproj;C 只有名稱是 `.gguf` 的資料夾;D 空陣列。"""
    bodies = {
        "A": [{"type": "file", "path": "README.md", "size": 10}, {"type": "file", "path": "model.safetensors", "size": 99}],
        "B": [
            {"type": "file", "path": "mmproj-model-f16.gguf", "size": 20},
            {"type": "file", "path": "mmproj-model-q8_0.gguf", "size": 10},
        ],
        "C": [{"type": "directory", "path": "weights.gguf"}],
        "D": [],
    }

    results: dict[str, str] = {}
    for case, body in bodies.items():
        hub = Recorder(lambda request, body=body: json_reply(body)).hub()
        try:
            await hub.list_repo_files("bartowski", "SmolLM2-135M-Instruct-GGUF")
            results[case] = "沒有丟出例外"
        except AdapterError as error:
            results[case] = error.code
        except Exception as error:
            results[case] = type(error).__name__

    # 則1~4:A~D 都是 `HF_NO_GGUF`
    assert results == {"A": "HF_NO_GGUF", "B": "HF_NO_GGUF", "C": "HF_NO_GGUF", "D": "HF_NO_GGUF"}


# ---- 004 US4-HF-13

# 取自合約實測的 `unsloth/Qwen3-0.6B-GGUF:Q4_K_M`;`config` 的 549 不計入大小
QWEN3_MANIFEST = {
    "schemaVersion": 2,
    "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
    "config": {"mediaType": "application/vnd.docker.container.image.v1+json", "digest": "sha256:" + "0" * 64, "size": 549},
    "layers": [
        {"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:" + "1" * 64, "size": 396705472},
        {"mediaType": "application/vnd.ollama.image.template", "digest": "sha256:" + "2" * 64, "size": 1482},
        {"mediaType": "application/vnd.ollama.image.params", "digest": "sha256:" + "3" * 64, "size": 178},
    ],
}


async def test_manifest_的大小是各層_size_總和_不含_config_也不看_Content_Type(monkeypatch: pytest.MonkeyPatch) -> None:
    """US4-HF-13:對方回的 Content-Type 是 `application/json; charset=utf-8`(不是 manifest 的媒體型別)。"""
    monkeypatch.setenv("HF_TOKEN", "cgb-test-假token")
    handler = Recorder(
        lambda request: httpx.Response(
            200, content=json.dumps(QWEN3_MANIFEST), headers={"Content-Type": "application/json; charset=utf-8"}
        )
    )
    hub = handler.hub()

    first = await hub.get_manifest("unsloth", "Qwen3-0.6B-GGUF", "Q4_K_M")
    await hub.get_manifest("unsloth", "Qwen3-0.6B-GGUF", "latest")

    # 則1:模型層加 template 加 params,不含 config
    assert first == {"sizeBytes": 396707132}
    # 則2:第 1 個請求的 URL
    assert str(handler.requests[0].url) == "https://huggingface.co/v2/unsloth/Qwen3-0.6B-GGUF/manifests/Q4_K_M"
    # 則3:Accept 標頭
    assert handler.requests[0].headers["Accept"] == "application/vnd.docker.distribution.manifest.v2+json"
    # 則4:沒有 Authorization 與 Cookie
    assert "Authorization" not in handler.requests[0].headers
    assert "Cookie" not in handler.requests[0].headers
    # 則5:`latest` 照送
    assert handler.requests[1].url.path.endswith("/manifests/latest")


# ---- 004 US4-HF-14


async def test_manifest_回_400_就是這個量化版本無法下載() -> None:
    """US4-HF-14:A 是不認的量化名稱;B 是分割檔(不讀英文本文,只看狀態碼)。"""
    bodies = {
        "A": {"error": 'The specified tag is not a valid quantization scheme. Please use another tag or "latest"'},
        "B": {"error": "This tag is a sharded GGUF"},
    }
    tags = {"A": "Q4_K_L", "B": "Q8_0"}

    results: dict[str, str] = {}
    for case, body in bodies.items():
        hub = Recorder(lambda request, body=body: json_reply(body, status=400)).hub()
        try:
            await hub.get_manifest("bartowski", "Meta-Llama-3.1-70B-Instruct-GGUF", tags[case])
            results[case] = "沒有丟出例外"
        except AdapterError as error:
            results[case] = error.code
        except Exception as error:
            results[case] = type(error).__name__

    # 則1、則2:A、B 都是 `HF_QUANT_UNAVAILABLE`
    assert results == {"A": "HF_QUANT_UNAVAILABLE", "B": "HF_QUANT_UNAVAILABLE"}


# ---- 004 US4-HF-15


async def test_檔案清單與_manifest_回_401_都是這個模型需要登入() -> None:
    """US4-HF-15:A 不存在的 repo 的 tree 回 401;B 需要同意條款的 manifest 回 401(帶 `WWW-Authenticate`)。"""
    unauthorized = {"error": "Invalid username or password."}

    def reply(request: httpx.Request) -> httpx.Response:
        headers = {"WWW-Authenticate": 'Bearer realm="https://huggingface.co"'} if "/manifests/" in request.url.path else {}
        return httpx.Response(401, json=unauthorized, headers=headers)

    handler = Recorder(reply)
    hub = handler.hub()
    results: dict[str, str] = {}
    for case, call in {
        "A": lambda: hub.list_repo_files("cgb-test", "no-such-repo"),
        "B": lambda: hub.get_manifest("google", "gemma-3-1b-it-qat-q4_0-gguf", "Q4_0"),
    }.items():
        try:
            await call()
            results[case] = "沒有丟出例外"
        except AdapterError as error:
            results[case] = error.code
        except Exception as error:
            results[case] = type(error).__name__

    # 則1、則2:兩個方法都是 `HF_AUTH_REQUIRED`
    assert results == {"A": "HF_AUTH_REQUIRED", "B": "HF_AUTH_REQUIRED"}
    # 則3:共 2 個請求(看到 `WWW-Authenticate` 也不去要 token 重送)
    assert len(handler.requests) == 2


# ---- 004 US4-HF-16


async def test_manifest_沒有模型層就不能當成可下載() -> None:
    """US4-HF-16:A 只有 template、params 兩層;B `layers` 是 `[]`;C 兩層都沒有 `mediaType`。"""
    template = {"mediaType": "application/vnd.ollama.image.template", "digest": "sha256:" + "2" * 64, "size": 1482}
    params = {"mediaType": "application/vnd.ollama.image.params", "digest": "sha256:" + "3" * 64, "size": 178}
    layers = {
        "A": [template, params],
        "B": [],
        "C": [{"digest": template["digest"], "size": 1482}, {"digest": params["digest"], "size": 178}],
    }

    results: dict[str, str] = {}
    for case, case_layers in layers.items():
        body = {**QWEN3_MANIFEST, "layers": case_layers}
        hub = Recorder(lambda request, body=body: json_reply(body)).hub()
        try:
            await hub.get_manifest("unsloth", "Qwen3-0.6B-GGUF", "Q4_K_M")
            results[case] = "沒有丟出例外"
        except AdapterError as error:
            results[case] = error.code
        except Exception as error:
            results[case] = type(error).__name__

    # 則1~3:A~C 都是 `HF_BAD_RESPONSE`
    assert results == {"A": "HF_BAD_RESPONSE", "B": "HF_BAD_RESPONSE", "C": "HF_BAD_RESPONSE"}


# ---- 004 US4-HF-17


def tree_reply(*names: str) -> httpx.Response:
    return json_reply([{"type": "file", "path": name, "size": 1} for name in names])


def manifest_body(model_bytes: int) -> dict[str, object]:
    """模型層加 template 1,482 位元組的 manifest(`config` 同 US4-HF-13)。"""
    model_layer = {"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:" + "1" * 64, "size": model_bytes}
    template = {"mediaType": "application/vnd.ollama.image.template", "digest": "sha256:" + "2" * 64, "size": 1482}
    return {**QWEN3_MANIFEST, "layers": [model_layer, template]}


async def test_展開的版本依檔案清單的順序_400_的候選不列出() -> None:
    """US4-HF-17:`Q4_K_M` 慢(0.15 秒)、`Q4_K_L` 立刻 400、`F16` 快(0.02 秒)。"""

    async def reply(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tree/main"):
            return tree_reply(
                "SmolLM2-135M-Instruct-Q4_K_M.gguf", "SmolLM2-135M-Instruct-Q4_K_L.gguf", "SmolLM2-135M-Instruct-F16.gguf"
            )
        if request.url.path.endswith("/Q4_K_L"):
            return json_reply({"error": "This tag is a sharded GGUF"}, status=400)
        if request.url.path.endswith("/Q4_K_M"):
            await asyncio.sleep(0.15)
            return json_reply(manifest_body(105_000_000))
        await asyncio.sleep(0.02)
        return json_reply(manifest_body(270_000_000 - 1482))

    handler = Recorder(reply)

    quants = await handler.hub().list_quants("bartowski", "SmolLM2-135M-Instruct-GGUF")

    # 則1:依檔案清單的順序,400 的 `Q4_K_L` 不列
    assert quants == [{"quant": "Q4_K_M", "sizeBytes": 105001482}, {"quant": "F16", "sizeBytes": 270000000}]
    # 則2:三個候選都送過 manifest 請求(不論順序)
    manifests = [request.url.path.rsplit("/", 1)[-1] for request in handler.requests if "/manifests/" in request.url.path]
    assert sorted(manifests) == ["F16", "Q4_K_L", "Q4_K_M"]


# ---- 004 US4-HF-18


async def test_展開版本時_manifest_請求同時最多_4_個() -> None:
    """US4-HF-18:6 個候選,每個 manifest 等 0.05 秒才回;記下同時進行中的請求數最大值。"""
    names = [f"SmolLM2-135M-Instruct-Q{n}_0.gguf" for n in range(1, 7)]
    running = 0
    peak = 0

    async def reply(request: httpx.Request) -> httpx.Response:
        nonlocal running, peak
        if request.url.path.endswith("/tree/main"):
            return tree_reply(*names)
        running += 1
        peak = max(peak, running)
        try:
            await asyncio.sleep(0.05)
        finally:
            running -= 1
        return json_reply(manifest_body(1000))

    quants = await Recorder(reply).hub().list_quants("bartowski", "SmolLM2-135M-Instruct-GGUF")

    # 則1:同時進行中的 manifest 請求最多 4 個
    assert peak == 4
    # 則2:回傳 6 筆
    assert len(quants) == 6


# ---- 004 US4-HF-19


async def test_展開後一個版本都列不出來時丟出_HF_NO_GGUF() -> None:
    """US4-HF-19:A 的候選 manifest 全部 400;B 的 tree 只有 mmproj 與 README(不該送任何 manifest 請求)。"""

    def reply_a(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tree/main"):
            return tree_reply("SmolLM2-135M-Instruct-Q4_K_L.gguf", "SmolLM2-135M-Instruct-Q5_K_L.gguf")
        return json_reply({"error": "This tag is a sharded GGUF"}, status=400)

    def reply_b(request: httpx.Request) -> httpx.Response:
        return tree_reply("mmproj-model-f16.gguf", "README.md")

    handler_b = Recorder(reply_b)
    results: dict[str, str] = {}
    for case, hub in {"A": Recorder(reply_a).hub(), "B": handler_b.hub()}.items():
        try:
            await hub.list_quants("bartowski", "SmolLM2-135M-Instruct-GGUF")
            results[case] = "沒有丟出例外"
        except AdapterError as error:
            results[case] = error.code
        except Exception as error:
            results[case] = type(error).__name__

    # 則1、則2:A、B 都是 `HF_NO_GGUF`
    assert results == {"A": "HF_NO_GGUF", "B": "HF_NO_GGUF"}
    # 則3:B 沒有送任何 manifest 請求
    assert [request for request in handler_b.requests if "/manifests/" in request.url.path] == []


# ---- 004 US4-HF-20


async def test_展開時_tree_或_manifest_回_401_整個模型需要登入() -> None:
    """US4-HF-20:A tree 回 401;B tree 三個檔,`Q8_0` 的 manifest 回 401、其他回 200。"""
    unauthorized = {"error": "Invalid username or password."}

    def reply_a(request: httpx.Request) -> httpx.Response:
        return json_reply(unauthorized, status=401)

    def reply_b(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tree/main"):
            return tree_reply("gemma-3-1b-it-Q4_K_M.gguf", "gemma-3-1b-it-Q8_0.gguf", "gemma-3-1b-it-F16.gguf")
        if request.url.path.endswith("/Q8_0"):
            return json_reply(unauthorized, status=401)
        return json_reply(manifest_body(1000))

    handler_a = Recorder(reply_a)
    results: dict[str, str] = {}
    for case, hub in {"A": handler_a.hub(), "B": Recorder(reply_b).hub()}.items():
        try:
            await hub.list_quants("google", "gemma-3-1b-it-qat-q4_0-gguf")
            results[case] = "沒有丟出例外"
        except AdapterError as error:
            results[case] = error.code
        except Exception as error:
            results[case] = type(error).__name__

    # 則1、則3:A、B 都是 `HF_AUTH_REQUIRED`
    assert results == {"A": "HF_AUTH_REQUIRED", "B": "HF_AUTH_REQUIRED"}
    # 則2:A 沒有送任何 manifest 請求
    assert [request for request in handler_a.requests if "/manifests/" in request.url.path] == []


# ---- 004 US4-HF-21


async def test_展開時有一個請求失敗就立刻丟出_並取消其他還沒完成的請求() -> None:
    """US4-HF-21:6 個候選,`Q2_K` 0.02 秒後回 503,其他每個等 0.25 秒才回 200;同時最多 4 個,所以有 2 個還沒送出。"""
    tags = ["Q2_K", "Q3_K_M", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
    sent: list[str] = []
    cancelled: list[str] = []
    completed: list[tuple[str, int]] = []

    async def reply(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tree/main"):
            return tree_reply(*(f"SmolLM2-135M-Instruct-{tag}.gguf" for tag in tags))
        tag = request.url.path.rsplit("/", 1)[-1]
        sent.append(tag)
        try:
            await asyncio.sleep(0.02 if tag == "Q2_K" else 0.25)
        except asyncio.CancelledError:
            cancelled.append(tag)
            raise
        status = 503 if tag == "Q2_K" else 200
        completed.append((tag, status))
        return json_reply({"error": "Internal Error"} if status == 503 else manifest_body(1000), status=status)

    hub = Recorder(reply).hub()
    started = time.monotonic()
    raised: Exception | None = None
    try:
        await hub.list_quants("bartowski", "SmolLM2-135M-Instruct-GGUF")
    except Exception as error:
        raised = error
    elapsed = time.monotonic() - started
    await asyncio.sleep(0.3)

    # 則1:`HF_SERVER_ERROR`
    assert getattr(raised, "code", type(raised).__name__) == "HF_SERVER_ERROR"
    # 則2:從呼叫到丟出不超過 0.1 秒
    assert elapsed < 0.1
    # 則3:`Q2_K` 以外所有已經送出的請求都被取消
    assert sorted(cancelled) == sorted(set(sent) - {"Q2_K"})
    # 則4:等完 0.3 秒後,沒有任何 200 的 manifest 完成
    assert [item for item in completed if item[1] == 200] == []


async def raised(call: Callable[[], Awaitable[object]]) -> Exception | None:
    """呼叫一次,回傳丟出的例外(沒有丟出就是 None)。"""
    try:
        await call()
    except Exception as error:
        return error
    return None


def code_of(error: Exception | None) -> str:
    """`AdapterError` 回它的 `code`;其他例外回型別名稱(讓越過轉接層的原生例外在斷言裡看得到)。"""
    if error is None:
        return "沒有丟出例外"
    return error.code if isinstance(error, AdapterError) else type(error).__name__


async def three_calls(hub: HuggingFaceHub) -> dict[str, Exception | None]:
    """依序呼叫三個方法(`search_models("qwen")`、`list_repo_files("a","b")`、`get_manifest("a","b","Q4_K_M")`)。"""
    return {
        "search_models": await raised(lambda: hub.search_models("qwen")),
        "list_repo_files": await raised(lambda: hub.list_repo_files("a", "b")),
        "get_manifest": await raised(lambda: hub.get_manifest("a", "b", "Q4_K_M")),
    }


def raising_reply(error: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def reply(request: httpx.Request) -> httpx.Response:
        raise error

    return reply


# ---- 004 US4-HF-22


async def test_傳輸層失敗都歸_HF_UNREACHABLE_不重試_說明不帶底層文字與網址() -> None:
    """US4-HF-22:A 連線失敗;B 連線被重設;C 伺服器沒回應就斷線;D 回 200 後讀本文到一半連線中斷。"""
    replies = {
        "A": raising_reply(httpx.ConnectError("cgb-test-底層細節 huggingface.co")),
        "B": raising_reply(httpx.ReadError("[Errno 104] Connection reset by peer")),
        "C": raising_reply(httpx.RemoteProtocolError("Server disconnected without sending a response.")),
        "D": half_body_reply(httpx.RemoteProtocolError("peer closed connection")),
    }
    handlers = {case: Recorder(reply) for case, reply in replies.items()}

    outcomes = {case: await three_calls(handler.hub()) for case, handler in handlers.items()}

    # 則1~3:A~D 的三個方法都是 `HF_UNREACHABLE`
    for method in ("search_models", "list_repo_files", "get_manifest"):
        assert {case: code_of(outcomes[case][method]) for case in replies} == dict.fromkeys(replies, "HF_UNREACHABLE")
    # 則4:每種情況都只收到 3 個請求(不重試)
    assert {case: len(handler.requests) for case, handler in handlers.items()} == dict.fromkeys(replies, 3)
    # 則5:A 的 `search_models` 不留例外鏈
    error_a = outcomes["A"]["search_models"]
    assert error_a is not None
    assert error_a.__cause__ is None
    assert error_a.__suppress_context__ is True
    # 則6、則7:A 的 `search_models`、`get_manifest` 說明不含底層文字與網址
    for method in ("search_models", "get_manifest"):
        error = outcomes["A"][method]
        assert isinstance(error, AdapterError)
        assert "cgb-test-底層細節" not in error.message
        assert "huggingface.co" not in error.message


def codes_of(outcomes: dict[str, dict[str, Exception | None]], method: str) -> dict[str, str]:
    """每種情況的某個方法丟出的代碼,收成 `{情況: code}`。"""
    return {case: code_of(outcome[method]) for case, outcome in outcomes.items()}


# ---- 004 US4-HF-23


async def test_逾時先於傳輸層失敗判定_都歸_HF_TIMEOUT_不重試() -> None:
    """US4-HF-23:A 連線逾時;B 讀取逾時;C 連線池逾時;D 回 200 後讀本文到一半讀取逾時。"""
    replies = {
        "A": raising_reply(httpx.ConnectTimeout("timed out")),
        "B": raising_reply(httpx.ReadTimeout("timed out")),
        "C": raising_reply(httpx.PoolTimeout("timed out")),
        "D": half_body_reply(httpx.ReadTimeout("timed out")),
    }
    handlers = {case: Recorder(reply) for case, reply in replies.items()}

    outcomes = {case: await three_calls(handler.hub()) for case, handler in handlers.items()}

    # 則1~3:A~D 的三個方法都是 `HF_TIMEOUT`
    for method in ("search_models", "list_repo_files", "get_manifest"):
        assert codes_of(outcomes, method) == dict.fromkeys(replies, "HF_TIMEOUT")
    # 則4:每種情況都只收到 3 個請求(不重試)
    assert {case: len(handler.requests) for case, handler in handlers.items()} == dict.fromkeys(replies, 3)


def valid_body_of(operation: str) -> object:
    """某個操作(`search`、`tree`、`manifest`)合法的 200 本文。"""
    if operation == "search":
        return [{"id": "a/b"}]
    if operation == "tree":
        return [{"type": "file", "path": "b-Q4_K_M.gguf", "size": 1}]
    return QWEN3_MANIFEST


def valid_body(request: httpx.Request) -> object:
    """依請求的路徑回該操作合法的 200 本文。"""
    if request.url.path == "/api/models":
        return valid_body_of("search")
    return valid_body_of("tree" if request.url.path.endswith("/tree/main") else "manifest")


# ---- 004 US4-HF-24


async def test_5xx_都歸_HF_SERVER_ERROR_即使本文看起來合法_不重試() -> None:
    """US4-HF-24:A 500 空本文;B 503 帶英文錯誤;C 599 空本文;D 502 但本文是合法的 200 本文。"""
    replies = {
        "A": lambda request: httpx.Response(500),
        "B": lambda request: json_reply({"error": "Internal Error - We're working hard to fix this as soon as we can!"}, 503),
        "C": lambda request: httpx.Response(599),
        "D": lambda request: json_reply(valid_body(request), 502),
    }
    handlers = {case: Recorder(reply) for case, reply in replies.items()}

    outcomes = {case: await three_calls(handler.hub()) for case, handler in handlers.items()}

    # 則1~3:A~D 的三個方法都是 `HF_SERVER_ERROR`
    for method in ("search_models", "list_repo_files", "get_manifest"):
        assert codes_of(outcomes, method) == dict.fromkeys(replies, "HF_SERVER_ERROR")
    # 則4:每種情況都只收到 3 個請求(不重試)
    assert {case: len(handler.requests) for case, handler in handlers.items()} == dict.fromkeys(replies, 3)


# ---- 004 US4-HF-25


async def test_搜尋的_401_與檔案清單的_400_不屬於它們的操作_都歸_HF_BAD_RESPONSE() -> None:
    """US4-HF-25:A 401 `Invalid username or password.`;B 400 `Bad request`。"""
    handler_a = Recorder(lambda request: json_reply({"error": "Invalid username or password."}, 401))
    handler_b = Recorder(lambda request: json_reply({"error": "Bad request"}, 400))

    search_a = await raised(lambda: handler_a.hub().search_models("qwen"))
    search_b = await raised(lambda: handler_b.hub().search_models("qwen"))
    files_b = await raised(lambda: handler_b.hub().list_repo_files("a", "b"))

    # 則1:A 的 `search_models`
    assert code_of(search_a) == "HF_BAD_RESPONSE"
    # 則2:B 的 `search_models`
    assert code_of(search_b) == "HF_BAD_RESPONSE"
    # 則3:B 的 `list_repo_files`
    assert code_of(files_b) == "HF_BAD_RESPONSE"


# ---- 004 US4-HF-26


async def test_轉址_404_與_429_都歸_HF_BAD_RESPONSE_不跟著轉址_不重試() -> None:
    """US4-HF-26:三個操作的路徑回 A 302(`Location` 指到 `/elsewhere`)、B 404、C 429;`/elsewhere` 回合法的 200 本文。"""

    def operation(request: httpx.Request) -> str:
        if request.url.path == "/api/models":
            return "search"
        return "tree" if request.url.path.endswith("/tree/main") else "manifest"

    def redirect(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/elsewhere":  # 跟著轉址才會到這裡,回該操作合法的 200 本文
            return json_reply(valid_body_of(request.url.params["op"]))
        return httpx.Response(302, headers={"Location": f"/elsewhere?op={operation(request)}"})

    def status_reply(status: int, error: str) -> Callable[[httpx.Request], httpx.Response]:
        return lambda request: json_reply({"error": error}, status)

    replies = {
        "A": redirect,
        "B": status_reply(404, "Not Found"),
        "C": status_reply(429, "Too many requests"),
    }
    handlers = {case: Recorder(reply) for case, reply in replies.items()}

    outcomes = {case: await three_calls(handler.hub()) for case, handler in handlers.items()}

    # 則1~3:A~C 的三個方法都是 `HF_BAD_RESPONSE`
    for method in ("search_models", "list_repo_files", "get_manifest"):
        assert codes_of(outcomes, method) == dict.fromkeys(replies, "HF_BAD_RESPONSE")
    # 則4:A 的 handler 沒有收到任何 `/elsewhere` 的請求
    assert [request for request in handlers["A"].requests if request.url.path == "/elsewhere"] == []


# ---- 004 US4-HF-27


async def test_200_但本文無法解讀_都歸_HF_BAD_RESPONSE() -> None:
    """US4-HF-27:A 本文是 HTML;B 本文空;C 本文是被截斷的 JSON;D 宣告 gzip 但本文不是 gzip(讀本文時丟 `DecodingError`)。"""

    def truncated(request: httpx.Request) -> httpx.Response:
        text = json.dumps(valid_body(request))
        return httpx.Response(200, headers={"Content-Type": "application/json"}, content=text[:10])

    replies = {
        "A": lambda request: httpx.Response(
            200, headers={"Content-Type": "text/html"}, content="<!DOCTYPE html><html><body>維護中</body></html>"
        ),
        "B": lambda request: httpx.Response(200, headers={"Content-Type": "application/json"}),
        "C": truncated,
        "D": lambda request: httpx.Response(
            200,
            headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
            stream=httpx.ByteStream(b"not gzip"),
        ),
    }

    outcomes = {case: await three_calls(Recorder(reply).hub()) for case, reply in replies.items()}

    # 則1~3:A~D 的三個方法都是 `HF_BAD_RESPONSE`
    for method in ("search_models", "list_repo_files", "get_manifest"):
        assert codes_of(outcomes, method) == dict.fromkeys(replies, "HF_BAD_RESPONSE")


# ---- 004 US4-HF-28


async def test_搜尋回應不是陣列或有一筆沒有字串_id_都歸_HF_BAD_RESPONSE() -> None:
    """US4-HF-28:A `{}`;B `null`;C 陣列裡是字串;D 沒有 `id`;E `id` 是數字;F 第一筆合法、第二筆 `id` 是 null。"""
    bodies = {
        "A": {},
        "B": None,
        "C": ["bartowski/SmolLM2-135M-Instruct-GGUF"],
        "D": [{"_id": "1"}],
        "E": [{"id": 123}],
        "F": [{"id": "a/b"}, {"id": None}],
    }

    codes = {}
    for case, body in bodies.items():
        hub = Recorder(lambda request, body=body: json_reply(body)).hub()
        codes[case] = code_of(await raised(lambda: hub.search_models("qwen")))

    # 則1:A~F 每一種都是 `HF_BAD_RESPONSE`
    assert codes == dict.fromkeys(bodies, "HF_BAD_RESPONSE")


# ---- 004 US4-HF-29


async def test_檔案清單的每一筆缺欄位或型別不符_都歸_HF_BAD_RESPONSE_不當成沒有_GGUF() -> None:
    """US4-HF-29:A `{}`;B 陣列裡是字串;C 沒有 `type`;D 沒有 `path`;E 檔案沒有 `size`;F `size` 是字串;G `size` 是 -1;H `size` 是 true。"""
    entry = {"type": "file", "path": "a-Q4_K_M.gguf", "size": 1}
    bodies = {
        "A": {},
        "B": ["a-Q4_K_M.gguf"],
        "C": [{"path": "a-Q4_K_M.gguf", "size": 1}],
        "D": [{"type": "file", "size": 1}],
        "E": [{"type": "file", "path": "a-Q4_K_M.gguf"}],
        "F": [{**entry, "size": "1"}],
        "G": [{**entry, "size": -1}],
        "H": [{**entry, "size": True}],
    }

    codes = {}
    for case, body in bodies.items():
        hub = Recorder(lambda request, body=body: json_reply(body)).hub()
        codes[case] = code_of(await raised(lambda: hub.list_repo_files("a", "b")))

    # 則1:A~H 每一種都是 `HF_BAD_RESPONSE`
    assert codes == dict.fromkeys(bodies, "HF_BAD_RESPONSE")


# ---- 004 US4-HF-30


async def test_manifest_的層缺欄位或型別不符_都歸_HF_BAD_RESPONSE() -> None:
    """US4-HF-30:A 不是物件;B 沒有 `layers`;C `layers` 是 null;D `layers` 是物件;E 有一層是字串;F~I 模型層的 `size` 缺少、是字串、-1、true。"""
    model_layer, *other_layers = QWEN3_MANIFEST["layers"]
    rest = {key: value for key, value in QWEN3_MANIFEST.items() if key != "layers"}

    def with_model_layer(layer: dict[str, object]) -> dict[str, object]:
        return {**rest, "layers": [layer, *other_layers]}

    bodies = {
        "A": [],
        "B": rest,
        "C": {**rest, "layers": None},
        "D": {**rest, "layers": {}},
        "E": {**rest, "layers": [model_layer, "layer"]},
        "F": with_model_layer({"mediaType": model_layer["mediaType"], "digest": model_layer["digest"]}),
        "G": with_model_layer({**model_layer, "size": "396705472"}),
        "H": with_model_layer({**model_layer, "size": -1}),
        "I": with_model_layer({**model_layer, "size": True}),
    }

    codes = {}
    for case, body in bodies.items():
        hub = Recorder(lambda request, body=body: json_reply(body)).hub()
        codes[case] = code_of(await raised(lambda: hub.get_manifest("unsloth", "Qwen3-0.6B-GGUF", "Q4_K_M")))

    # 則1:A~I 每一種都是 `HF_BAD_RESPONSE`
    assert codes == dict.fromkeys(bodies, "HF_BAD_RESPONSE")


# ---- 004 US4-HF-31


async def test_失敗說明是固定的繁體中文_不帶對方的英文原文與網址() -> None:
    """US4-HF-31:兩組 handler 狀態碼相同(tree 401、manifest 400、搜尋 503),只有本文的英文不同。"""
    english = {
        "first": {
            "tree": "Invalid username or password.",
            "manifest": 'The specified tag is not a valid quantization scheme. Please use another tag or "latest"',
            "search": "Internal Error - We're working hard to fix this as soon as we can!",
        },
        "second": dict.fromkeys(("tree", "manifest", "search"), "cgb-test english body"),
    }

    def reply_with(errors: dict[str, str]) -> Callable[[httpx.Request], httpx.Response]:
        def reply(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/models":
                return json_reply({"error": errors["search"]}, 503)
            if request.url.path.endswith("/tree/main"):
                return json_reply({"error": errors["tree"]}, 401)
            return json_reply({"error": errors["manifest"]}, 400)

        return reply

    outcomes = {group: await three_calls(Recorder(reply_with(errors)).hub()) for group, errors in english.items()}

    def message(group: str, method: str) -> str:
        error = outcomes[group][method]
        assert isinstance(error, AdapterError)
        return error.message

    # 則1~3:兩組的 `message` 相同
    assert message("first", "list_repo_files") == message("second", "list_repo_files")
    assert message("first", "get_manifest") == message("second", "get_manifest")
    assert message("first", "search_models") == message("second", "search_models")
    # 則4~6:第一組的 `message` 不含對方的英文與網址
    assert "Invalid username" not in message("first", "list_repo_files")
    assert "huggingface.co" not in message("first", "list_repo_files")
    assert "not a valid quantization" not in message("first", "get_manifest")
    assert "huggingface.co" not in message("first", "get_manifest")
    assert "Internal Error" not in message("first", "search_models")
    assert "huggingface.co" not in message("first", "search_models")


# ---- 004 US4-HF-32


async def test_沒指定逾時時每個請求的連線_讀取_寫入_連線池逾時都是_10_秒() -> None:
    """US4-HF-32:handler 記下每個請求的 `timeout`;`HuggingFaceHub(transport=...)` 不帶任何逾時參數。"""

    def reply(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/models":
            return json_reply([])
        return json_reply(valid_body(request))

    handler = Recorder(reply)
    hub = handler.hub()

    await hub.search_models("qwen")
    await hub.list_repo_files("a", "b")
    await hub.get_manifest("a", "b", "Q4_K_M")

    ten = {"connect": 10.0, "read": 10.0, "write": 10.0, "pool": 10.0}
    # 則1~3:三個方法的請求 `timeout` 都是 10 秒
    assert [request.extensions["timeout"] for request in handler.requests] == [ten, ten, ten]


# ---- 004 US4-HF-33


async def test_對方一直不回時每個請求在注入的期限到期就歸_HF_TIMEOUT() -> None:
    """US4-HF-33:`request_timeout=0.2`;handler 對任何請求等 0.5 秒才回 200(MockTransport 不會觸發 httpx 的逾時)。"""

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.5)
        return json_reply(valid_body(request))

    handler = Recorder(slow)
    hub = handler.hub(request_timeout=0.2)

    results: dict[str, tuple[str, float]] = {}
    calls = {
        "search_models": lambda: hub.search_models("qwen"),
        "list_repo_files": lambda: hub.list_repo_files("a", "b"),
        "get_manifest": lambda: hub.get_manifest("a", "b", "Q4_K_M"),
    }
    for method, call in calls.items():
        started = time.monotonic()
        error = await raised(call)
        results[method] = (code_of(error), time.monotonic() - started)

    # 則1~3:三個方法都丟出 `HF_TIMEOUT`,經過 0.2 到 0.3 秒
    assert {method: code for method, (code, _) in results.items()} == dict.fromkeys(calls, "HF_TIMEOUT")
    assert all(0.2 <= elapsed <= 0.3 for _, elapsed in results.values())
    # 則4:handler 總共收到 3 個請求(不重試)
    assert len(handler.requests) == 3


# ---- 004 US4-HF-34


class SlowBody(httpx.AsyncByteStream):
    """每 0.08 秒送 1 個位元組、共送 8 次(約 0.64 秒)的本文。"""

    async def __aiter__(self):
        for _ in range(8):
            await asyncio.sleep(0.08)
            yield b" "


async def test_讀本文太慢時也在每個請求的期限內歸_HF_TIMEOUT() -> None:
    """US4-HF-34:`request_timeout=0.2`;handler 立刻回 200 與標頭,本文約 0.64 秒才送完。"""
    handler = Recorder(
        lambda request: httpx.Response(200, headers={"Content-Type": "application/json"}, stream=SlowBody())
    )
    hub = handler.hub(request_timeout=0.2)

    results: dict[str, tuple[str, float]] = {}
    calls = {
        "search_models": lambda: hub.search_models("qwen"),
        "list_repo_files": lambda: hub.list_repo_files("a", "b"),
        "get_manifest": lambda: hub.get_manifest("a", "b", "Q4_K_M"),
    }
    for method, call in calls.items():
        started = time.monotonic()
        error = await raised(call)
        results[method] = (code_of(error), time.monotonic() - started)

    # 則1~3:三個方法都丟出 `HF_TIMEOUT`,經過 0.2 到 0.3 秒
    assert {method: code for method, (code, _) in results.items()} == dict.fromkeys(calls, "HF_TIMEOUT")
    assert all(0.2 <= elapsed <= 0.3 for _, elapsed in results.values())


# ---- 004 US4-HF-35


async def test_載入更多時每一頁各自計算期限() -> None:
    """US4-HF-35:同一個 `HuggingFaceHub(request_timeout=0.2)`;handler 每個請求等 0.15 秒才回 200,第一頁帶 `rel="next"`。"""
    link = '<https://huggingface.co/api/models?search=qwen&cursor=c2>; rel="next"'

    async def reply(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.15)
        return httpx.Response(200, json=[{"id": "a/b"}], headers={"Link": link})

    hub = Recorder(reply).hub(request_timeout=0.2)

    pages: list[str | int] = []
    for cursor in (None, "c2"):
        try:
            result = await hub.search_models("qwen", cursor=cursor)
            pages.append(len(result["items"]))
        except Exception as error:
            pages.append(code_of(error))

    # 則1、則2:兩頁都正常回傳 1 筆
    assert pages == [1, 1]


# ---- 004 US4-HF-36


async def test_展開版本整體超過期限就取消進行中的請求_歸_HF_TIMEOUT() -> None:
    """US4-HF-36:`request_timeout=0.2`、`expand_deadline=0.25`;tree 與每個 manifest 各等 0.15 秒才回 200(5 個版本,沒有整體期限時約 0.45 秒完成)。"""
    tags = ["Q2_K", "Q3_K_M", "Q4_K_M", "Q5_K_M", "Q6_K"]
    cancelled: list[str] = []
    completed: list[str] = []

    async def reply(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tree/main"):
            await asyncio.sleep(0.15)
            return tree_reply(*(f"SmolLM2-135M-Instruct-{tag}.gguf" for tag in tags))
        tag = request.url.path.rsplit("/", 1)[-1]
        try:
            await asyncio.sleep(0.15)
        except asyncio.CancelledError:
            cancelled.append(tag)
            raise
        completed.append(tag)
        return json_reply(manifest_body(1000))

    hub = Recorder(reply).hub(request_timeout=0.2, expand_deadline=0.25)
    started = time.monotonic()
    error = await raised(lambda: hub.list_quants("bartowski", "SmolLM2-135M-Instruct-GGUF"))
    elapsed = time.monotonic() - started
    await asyncio.sleep(0.3)

    # 則1:`HF_TIMEOUT`
    assert code_of(error) == "HF_TIMEOUT"
    # 則2:從呼叫到丟出經過 0.25 到 0.33 秒
    assert 0.25 <= elapsed <= 0.33
    # 則3:取消紀錄含到期時進行中的 4 個 manifest 請求
    assert sorted(cancelled) == ["Q2_K", "Q3_K_M", "Q4_K_M", "Q5_K_M"]
    # 則4:等完 0.3 秒後,沒有任何 manifest 完成
    assert completed == []


# ---- 004 US4-HF-37


async def test_展開時每個_manifest_請求仍受每請求期限限制_一個逾時就整個展開失敗() -> None:
    """US4-HF-37:`request_timeout=0.15`、`expand_deadline=0.6`;tree 立刻回三個檔,`Q8_0` 的 manifest 等 1 秒,其他立刻回 200。"""

    async def reply(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tree/main"):
            return tree_reply("SmolLM2-135M-Instruct-Q4_K_M.gguf", "SmolLM2-135M-Instruct-Q8_0.gguf", "SmolLM2-135M-Instruct-F16.gguf")
        if request.url.path.endswith("/Q8_0"):
            await asyncio.sleep(1)
        return json_reply(manifest_body(1000))

    hub = Recorder(reply).hub(request_timeout=0.15, expand_deadline=0.6)
    started = time.monotonic()
    error = await raised(lambda: hub.list_quants("bartowski", "SmolLM2-135M-Instruct-GGUF"))
    elapsed = time.monotonic() - started

    # 則1:`HF_TIMEOUT`
    assert code_of(error) == "HF_TIMEOUT"
    # 則2:從呼叫到丟出經過 0.15 到 0.25 秒
    assert 0.15 <= elapsed <= 0.25


# ---- 004 US4-HF-38


async def test_單獨取_manifest_大小不套展開的整體期限() -> None:
    """US4-HF-38:`request_timeout=0.3`、`expand_deadline=0.1`;manifest 等 0.15 秒才回 200。"""

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.15)
        return httpx.Response(200, content=json.dumps(QWEN3_MANIFEST), headers={"Content-Type": "application/json"})

    hub = Recorder(slow).hub(request_timeout=0.3, expand_deadline=0.1)

    try:
        outcome: object = await hub.get_manifest("unsloth", "Qwen3-0.6B-GGUF", "Q4_K_M")
    except Exception as error:
        outcome = code_of(error)

    # 則1:回傳大小
    assert outcome == {"sizeBytes": 396707132}
