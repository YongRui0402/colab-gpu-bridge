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
