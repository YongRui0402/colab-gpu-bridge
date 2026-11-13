"""E7 遠端 Ollama 轉接層(testplan.md § 3.2;接縫:`RemoteOllama` 的方法,另一端是 `tests/fakes/ollama_server.py` 的假 Ollama 伺服器)。

`base_url` 直接指到假伺服器,相當於 SSH 本機轉發已經建好(contracts/remote-ollama.openapi.yaml § servers)。
"""

import asyncio
import socket
import time
from collections.abc import Callable

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.adapters.remote_ollama import RemoteOllama
from fakes import FakeOllamaServer, HangReply, JsonReply, NdjsonReply


def closed_port_url() -> str:
    """一個沒有人在聽的 127.0.0.1 port(先綁再放掉)。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


# ---------------------------------------------------------------- US2-RO-01 get_version


async def test_get_version_回傳遠端的版本(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-01 情況 A:假伺服器回 200 `{"version":"0.40.15"}`。"""
    ollama_server.add("GET", "/api/version", JsonReply({"version": "0.40.15"}))

    result = await RemoteOllama().get_version(ollama_server.base_url)

    assert result["version"] == "0.40.15"
    ollama_server.assert_all_matched()


async def test_get_version_回應不是_JSON_時回_OLLAMA_BAD_RESPONSE(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-01 情況 B:假伺服器回 200 `<html>`。"""
    ollama_server.add(
        "GET", "/api/version", JsonReply(b"<html>", headers={"Content-Type": "text/html"})
    )

    with pytest.raises(AdapterError) as caught:
        await RemoteOllama().get_version(ollama_server.base_url)

    assert caught.value.code == "OLLAMA_BAD_RESPONSE"


async def test_get_version_port_關閉時回_OLLAMA_UNREACHABLE() -> None:
    """US2-RO-01 情況 C:本機轉發的 port 沒有在聽。"""
    with pytest.raises(AdapterError) as caught:
        await RemoteOllama().get_version(closed_port_url())

    assert caught.value.code == "OLLAMA_UNREACHABLE"


async def test_get_version_不回應時在逾時內回_OLLAMA_TIMEOUT(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-01 情況 D:假伺服器 6 秒不回(逾時注入 0.3 秒);逾時沒設的話健康檢查會卡住。"""
    ollama_server.add("GET", "/api/version", HangReply())
    remote = RemoteOllama(version_timeout=0.3)

    started = time.monotonic()
    with pytest.raises(AdapterError) as caught:
        await remote.get_version(ollama_server.base_url)
    elapsed = time.monotonic() - started

    assert caught.value.code == "OLLAMA_TIMEOUT"
    assert elapsed < 2.0, f"注入 0.3 秒逾時,卻等了 {elapsed:.2f} 秒"


# ---------------------------------------------------------------- US2-RO-02 generate

GENERATE_BODY = {"model": "x", "prompt": "hi"}


async def _generate_all(remote: RemoteOllama, base_url: str) -> list[dict]:
    return [line async for line in await remote.generate(base_url, GENERATE_BODY)]


async def test_generate_模型不在執行環境上時回_OLLAMA_NOT_FOUND_並保留英文原文(
    ollama_server: FakeOllamaServer,
) -> None:
    """US2-RO-02 情況 A:假伺服器回 404 `{"error":"model 'x' not found"}`。"""
    ollama_server.add("POST", "/api/generate", JsonReply({"error": "model 'x' not found"}, status=404))

    with pytest.raises(AdapterError) as caught:
        await _generate_all(RemoteOllama(), ollama_server.base_url)

    assert caught.value.code == "OLLAMA_NOT_FOUND"
    assert caught.value.message == "model 'x' not found"
    ollama_server.assert_all_matched()


async def test_generate_回_400_時回_OLLAMA_BAD_REQUEST(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-02 情況 B:假伺服器回 400。"""
    ollama_server.add(
        "POST", "/api/generate", JsonReply({"error": "invalid character 'x' looking for beginning of value"}, status=400)
    )

    with pytest.raises(AdapterError) as caught:
        await _generate_all(RemoteOllama(), ollama_server.base_url)

    assert caught.value.code == "OLLAMA_BAD_REQUEST"


async def test_generate_回_500_時回_OLLAMA_SERVER_ERROR(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-02 情況 C:假伺服器回 500;和 404 要分得開。"""
    ollama_server.add("POST", "/api/generate", JsonReply({"error": "model requires more system memory"}, status=500))

    with pytest.raises(AdapterError) as caught:
        await _generate_all(RemoteOllama(), ollama_server.base_url)

    assert caught.value.code == "OLLAMA_SERVER_ERROR"


async def test_generate_串流在_done_之前斷線時回_OLLAMA_STREAM_INTERRUPTED(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-02 情況 D:串流 2 行後關閉、沒有 `done:true`;不能當成正常結束。"""
    lines = [
        {"model": "x", "created_at": "2026-11-10T09:00:00Z", "response": "a", "done": False},
        {"model": "x", "created_at": "2026-11-10T09:00:01Z", "response": "b", "done": False},
    ]
    ollama_server.add("POST", "/api/generate", NdjsonReply(lines, then="disconnect"))
    received: list[dict] = []

    with pytest.raises(AdapterError) as caught:
        async for line in await RemoteOllama().generate(ollama_server.base_url, GENERATE_BODY):
            received.append(line)

    assert caught.value.code == "OLLAMA_STREAM_INTERRUPTED"
    assert [line["response"] for line in received] == ["a", "b"]


# ---------------------------------------------------------------- US3-RO-01 pull_model

PULL_LAYER_50 = {"status": "pulling a", "digest": "sha256:a", "total": 100, "completed": 50}
PULL_LAYER_100 = {"status": "pulling a", "digest": "sha256:a", "total": 100, "completed": 100}


async def _pull_all(remote: RemoteOllama, base_url: str, model: str = "qwen2.5:7b") -> list[dict]:
    return [line async for line in await remote.pull_model(base_url=base_url, model=model)]


async def test_pull_model_只把帶_total_的行當進度_最後回成功(ollama_server: FakeOllamaServer) -> None:
    """US3-RO-01:`pulling manifest` 沒有 `total`,不能變成 0% 進度;要等到 `success` 才算完成。"""
    lines = [{"status": "pulling manifest"}, PULL_LAYER_50, PULL_LAYER_100, {"status": "success"}]
    ollama_server.add("POST", "/api/pull", NdjsonReply(lines), json={"model": "qwen2.5:7b"})

    received = await _pull_all(RemoteOllama(), ollama_server.base_url)

    progress = [(line["completed"], line["total"]) for line in received if "total" in line]
    assert progress == [(50, 100), (100, 100)]
    assert all("total" in line for line in received[:-1]), f"沒有 total 的狀態行被當成進度:{received}"
    assert received[-1] == {"status": "success"}
    ollama_server.assert_all_matched()


# ---------------------------------------------------------------- US3-RO-02 pull_model 的失敗


async def _pull_outcome(remote: RemoteOllama, base_url: str, within: float = 3.0) -> str:
    """跑完一次 pull,交回錯誤代碼;正常結束是「回成功」,`within` 秒內沒結束是「沒有結束」。"""
    try:
        await asyncio.wait_for(_pull_all(remote, base_url), within)
    except AdapterError as error:
        return error.code
    except TimeoutError:
        return f"{within:g} 秒內沒有結束"
    except Exception as error:  # noqa: BLE001 - 丟了別的例外也要成為斷言失敗
        return repr(error)
    return "回成功"


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        pytest.param(
            NdjsonReply([{"status": "pulling manifest"}, {"error": "pull model manifest: file does not exist"}]),
            "OLLAMA_NOT_FOUND",
            id="A-file-does-not-exist",
        ),
        pytest.param(NdjsonReply([{"error": "max retries exceeded"}]), "OLLAMA_PULL_FAILED", id="B-other-error"),
        pytest.param(NdjsonReply([PULL_LAYER_50, PULL_LAYER_100], then="disconnect"), "OLLAMA_STREAM_INTERRUPTED", id="C-disconnect"),
        pytest.param(NdjsonReply([PULL_LAYER_50], then="hang"), "OLLAMA_TIMEOUT", id="D-silent"),
    ],
)
async def test_pull_model_的失敗依串流內容分類(
    ollama_server: FakeOllamaServer, reply: NdjsonReply, expected: str
) -> None:
    """US3-RO-02:HTTP 200 之後的 error 行、中途斷線、進度停住(進度間隔逾時注入 0.3 秒)都不能當成功。"""
    ollama_server.add("POST", "/api/pull", reply, json={"model": "qwen2.5:7b"})
    remote = RemoteOllama(pull_progress_timeout=0.3)

    outcome = await _pull_outcome(remote, ollama_server.base_url)

    assert outcome == expected
    ollama_server.assert_all_matched()


# ---------------------------------------------------------------- US3-RO-03 list_local_models、list_loaded_models

DIGEST_7B = "845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e"
DIGEST_05B = "a8b0c51577010a279d933d14c2f8ab4b268079d44c5c8830c0a93900f1827c67"
DETAILS = {"format": "gguf", "family": "qwen2", "families": ["qwen2"], "parameter_size": "7.6B", "quantization_level": "Q4_K_M"}
TAGS_TWO_MODELS = {
    "models": [
        {
            "name": "qwen2.5:7b",
            "model": "qwen2.5:7b",
            "modified_at": "2026-11-10T09:00:00.000000000Z",
            "size": 4683087332,
            "digest": DIGEST_7B,
            "details": DETAILS,
        },
        {
            "name": "qwen2.5:0.5b",
            "model": "qwen2.5:0.5b",
            "modified_at": "2026-11-10T08:00:00.000000000Z",
            "size": 397821319,
            "digest": DIGEST_05B,
            "details": {**DETAILS, "parameter_size": "494.03M"},
        },
    ]
}
PS_ONE_MODEL = {
    "models": [
        {
            "name": "qwen2.5:7b",
            "model": "qwen2.5:7b",
            "size": 6654289920,
            "digest": DIGEST_7B,
            "details": DETAILS,
            "expires_at": "2318-02-19T09:00:00.000000000Z",
            "size_vram": 6654289920,
            "context_length": 4096,
        }
    ]
}


async def test_list_local_models_與_list_loaded_models_回名稱與大小(ollama_server: FakeOllamaServer) -> None:
    """US3-RO-03:tags 回兩個模型、ps 回一個。"""
    ollama_server.add("GET", "/api/tags", JsonReply(TAGS_TWO_MODELS))
    ollama_server.add("GET", "/api/ps", JsonReply(PS_ONE_MODEL))
    remote = RemoteOllama()

    local = await remote.list_local_models(base_url=ollama_server.base_url)
    loaded = await remote.list_loaded_models(base_url=ollama_server.base_url)

    assert [(m["name"], m["size"]) for m in local["models"]] == [("qwen2.5:7b", 4683087332), ("qwen2.5:0.5b", 397821319)]
    assert [m["name"] for m in loaded["models"]] == ["qwen2.5:7b"]
    ollama_server.assert_all_matched()


# ---------------------------------------------------------------- US3-RO-04 preload


async def test_preload_只送_model_與_keep_alive_負一(ollama_server: FakeOllamaServer) -> None:
    """US3-RO-04:預先載入不帶 `prompt`,`keep_alive` 一律 -1(plan.md Q4)。"""
    loaded = {
        "model": "qwen2.5:7b",
        "created_at": "2026-11-10T09:00:00Z",
        "response": "",
        "done": True,
        "done_reason": "load",
    }
    ollama_server.add("POST", "/api/generate", JsonReply(loaded))

    await RemoteOllama().preload(base_url=ollama_server.base_url, model="qwen2.5:7b")

    [request] = ollama_server.requests_to("POST", "/api/generate")
    assert request.json() == {"model": "qwen2.5:7b", "keep_alive": -1}
    ollama_server.assert_all_matched()


# ---- 003 US1-RO-01 以 MockTransport 驗 list_local_models(base_url 一律是本機轉發的位址)

LOCAL_FORWARD_URL = "http://127.0.0.1:11435"


class Recorder:
    """MockTransport 的 handler:記下每個收到的請求,再交給 `reply` 決定回什麼。"""

    def __init__(self, reply: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._reply = reply

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._reply(request)

    def remote(self) -> RemoteOllama:
        return RemoteOllama(transport=httpx.MockTransport(self))


def json_reply(body: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)


def tags_only(body: object) -> Callable[[httpx.Request], httpx.Response]:
    """只有 `GET /api/tags` 回 `body`,其他路徑回 404。"""

    def reply(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/tags":
            return json_reply(body)
        return httpx.Response(404)

    return reply


async def test_list_local_models_回兩筆模型的名稱與大小並只打_api_tags() -> None:
    """US1-RO-01:handler 回兩筆模型;名稱與大小照實,只收到一個打在傳進來的 base_url 的 GET /api/tags。"""
    tags = {
        "models": [
            {
                "name": "qwen2.5:latest",
                "model": "qwen2.5:latest",
                "modified_at": "2026-11-10T09:00:00.000000000Z",
                "size": 4683087332,
                "digest": "845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e",
                "details": {"format": "gguf", "family": "qwen2"},
            },
            {
                "name": "llama3.2:3b",
                "model": "llama3.2:3b",
                "modified_at": "2026-11-10T08:00:00.000000000Z",
                "size": 2019393189,
                "digest": "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72",
                "details": {"format": "gguf", "family": "llama"},
            },
        ]
    }
    handler = Recorder(tags_only(tags))

    result = await handler.remote().list_local_models(base_url=LOCAL_FORWARD_URL)

    assert [m["name"] for m in result["models"]] == ["qwen2.5:latest", "llama3.2:3b"]
    assert [m.get("size") for m in result["models"]] == [4683087332, 2019393189]
    assert [(r.method, str(r.url)) for r in handler.requests] == [("GET", "http://127.0.0.1:11435/api/tags")]


# ---- 003 US1-RO-02 名稱原樣交回


async def test_list_local_models_名稱原樣交回不補版本不轉小寫不去前綴() -> None:
    """US1-RO-02:遠端回了沒帶版本的 `qwen2.5`;清單這一側不補版本,比對時才只補輸入那一側。"""
    names = ["qwen2.5", "llama3.2:latest", "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M"]
    tags = {"models": [{"name": name, "size": index} for index, name in enumerate(names, start=1)]}
    handler = Recorder(tags_only(tags))

    result = await handler.remote().list_local_models(base_url=LOCAL_FORWARD_URL)

    assert [m["name"] for m in result["models"]] == names


# ---- 003 US1-RO-03 空清單


async def list_outcome(remote: RemoteOllama) -> object:
    """呼叫一次 `list_local_models`;成功交回 `models`,丟出 `AdapterError` 交回 `AdapterError(<code>)`,
    其他例外交回 `repr`。讓「丟了不該丟的例外」成為斷言失敗,不是測試本身出錯。"""
    try:
        return (await remote.list_local_models(base_url=LOCAL_FORWARD_URL))["models"]
    except AdapterError as error:
        return f"AdapterError({error.code})"
    except Exception as error:  # noqa: BLE001 - 丟了別的例外也要成為斷言失敗
        return repr(error)


async def test_list_local_models_空陣列照常回傳不當成失敗() -> None:
    """US1-RO-03:執行環境剛開好、還沒下載任何模型時,`models` 是空陣列。"""
    handler = Recorder(tags_only({"models": []}))

    assert await list_outcome(handler.remote()) == []


# ---- 003 US1-RO-04 只要求 name 與 size,其他欄位缺了或型別不符不算失敗


async def test_list_local_models_其他欄位缺了或型別不符時照常回傳() -> None:
    """US1-RO-04:第一筆只有 `name`、`size`(0 位元組);第二筆其他欄位型別都不符。"""
    tags = {
        "models": [
            {"name": "qwen2.5:latest", "size": 0},
            {"name": "llama3.2:3b", "model": 123, "size": 2019393189, "digest": None, "modified_at": "昨天", "details": "x"},
        ]
    }
    handler = Recorder(tags_only(tags))

    models = await list_outcome(handler.remote())

    assert isinstance(models, list), models
    assert [m["name"] for m in models] == ["qwen2.5:latest", "llama3.2:3b"]
    assert models[0]["size"] == 0


# ---- 003 US1-RO-05 逾時一律歸成 OLLAMA_TIMEOUT


def raising(errors: list[Exception]) -> Callable[[httpx.Request], httpx.Response]:
    """第 N 個請求丟出第 N 個例外。"""
    queue = iter(errors)

    def reply(request: httpx.Request) -> httpx.Response:
        raise next(queue)

    return reply


async def test_list_local_models_四種逾時都歸成_OLLAMA_TIMEOUT_且不重試() -> None:
    """US1-RO-05:連線、讀、寫、連線池逾時各用一個新的 `RemoteOllama`;失敗不自動重試。"""
    handler = Recorder(
        raising(
            [
                httpx.ConnectTimeout("timed out"),
                httpx.ReadTimeout("timed out"),
                httpx.WriteTimeout("timed out"),
                httpx.PoolTimeout("timed out"),
            ]
        )
    )

    outcomes = [await list_outcome(handler.remote()) for _ in range(4)]

    assert outcomes == ["AdapterError(OLLAMA_TIMEOUT)"] * 4
    assert len(handler.requests) == 4


# ---- 003 US1-RO-06 讀到一半逾時


class HalfBody(httpx.AsyncByteStream):
    """先送出半截 JSON,再丟出指定的例外(模擬本文讀到一半才出事)。"""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def __aiter__(self):
        yield b'{"models":[{"name":"qwen2.5:latest",'
        raise self._error


def half_body_reply(error: Exception) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, headers={"Content-Type": "application/json"}, stream=HalfBody(error))


async def test_list_local_models_本文讀到一半逾時也歸成_OLLAMA_TIMEOUT() -> None:
    """US1-RO-06:回 200,本文先送半截再丟 `ReadTimeout`。"""
    handler = Recorder(half_body_reply(httpx.ReadTimeout("timed out")))

    assert await list_outcome(handler.remote()) == "AdapterError(OLLAMA_TIMEOUT)"


# ---- 003 US1-RO-07 其他傳輸層失敗歸成 OLLAMA_UNREACHABLE


async def test_list_local_models_連不到_連線被重設_協定錯誤都歸成_OLLAMA_UNREACHABLE_且不重試() -> None:
    """US1-RO-07:本機轉發沒有在聽、SSH 通道斷了、對方沒回完整回應就斷線。"""
    handler = Recorder(
        raising(
            [
                httpx.ConnectError("[Errno 111] Connection refused"),
                httpx.ReadError("[Errno 104] Connection reset by peer"),
                httpx.RemoteProtocolError("Server disconnected without sending a response."),
            ]
        )
    )

    outcomes = [await list_outcome(handler.remote()) for _ in range(3)]

    assert outcomes == ["AdapterError(OLLAMA_UNREACHABLE)"] * 3
    assert len(handler.requests) == 3


# ---- 003 US1-RO-08 讀到一半連線中斷


async def test_list_local_models_本文讀到一半連線中斷歸成_OLLAMA_UNREACHABLE() -> None:
    """US1-RO-08:回 200,本文先送半截再丟 `RemoteProtocolError`;沒有完整 HTTP 回應算連不到。"""
    error = httpx.RemoteProtocolError("peer closed connection without sending complete message body")
    handler = Recorder(half_body_reply(error))

    assert await list_outcome(handler.remote()) == "AdapterError(OLLAMA_UNREACHABLE)"


# ---- 003 US1-RO-09 狀態碼不是 200 一律歸成 OLLAMA_BAD_RESPONSE


def replying(responses: list[httpx.Response]) -> Callable[[httpx.Request], httpx.Response]:
    """第 N 個請求回第 N 個回應。"""
    queue = iter(responses)
    return lambda request: next(queue)


async def test_list_local_models_狀態碼不是_200_一律歸成_OLLAMA_BAD_RESPONSE_且不重試() -> None:
    """US1-RO-09:503 與 201 帶著合法清單、404、500;都不能當成成功,也不沿用 generate 的狀態碼對照。"""
    valid = {"models": [{"name": "qwen2.5:latest", "size": 1}]}
    handler = Recorder(
        replying(
            [
                json_reply(valid, 503),
                json_reply({"error": "404 page not found"}, 404),
                json_reply({"error": "llama runner process has terminated"}, 500),
                json_reply(valid, 201),
            ]
        )
    )

    outcomes = [await list_outcome(handler.remote()) for _ in range(4)]

    assert outcomes == ["AdapterError(OLLAMA_BAD_RESPONSE)"] * 4
    assert len(handler.requests) == 4


# ---- 003 US1-RO-10 不跟著 3xx 導向


async def test_list_local_models_不跟著導向_回_302_歸成_OLLAMA_BAD_RESPONSE() -> None:
    """US1-RO-10:`/api/tags` 導到 `/elsewhere`,後者是合法清單;跟過去會把別處的清單當成已下載的模型。"""

    def reply(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(302, headers={"Location": "http://127.0.0.1:11435/elsewhere"})
        return json_reply({"models": [{"name": "qwen2.5:latest", "size": 1}]})

    handler = Recorder(reply)

    assert await list_outcome(handler.remote()) == "AdapterError(OLLAMA_BAD_RESPONSE)"
    assert len(handler.requests) == 1


# ---- 003 US1-RO-11 200 但本文無法解讀


async def test_list_local_models_本文無法解讀時歸成_OLLAMA_BAD_RESPONSE() -> None:
    """US1-RO-11:A 回 HTML、B 宣稱 gzip 卻壞掉(讀本文時才丟 `DecodingError`)、C 空本文。"""
    handler = Recorder(
        replying(
            [
                httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    content=b"<!DOCTYPE html><html><body>502 Bad Gateway</body></html>",
                ),
                httpx.Response(
                    200,
                    headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
                    stream=httpx.ByteStream(b"not gzip"),
                ),
                httpx.Response(200, headers={"Content-Type": "application/json"}, content=b""),
            ]
        )
    )

    outcomes = [await list_outcome(handler.remote()) for _ in range(3)]

    assert outcomes == ["AdapterError(OLLAMA_BAD_RESPONSE)"] * 3


# ---- 003 US1-RO-12 最上層形狀不符


async def test_list_local_models_最上層不是物件或_models_不是陣列時歸成_OLLAMA_BAD_RESPONSE() -> None:
    """US1-RO-12:`[]`、`{}`、`{"models":null}`、`models` 是物件、整份是字串;缺少 `models` 不能當成沒有模型。"""
    bodies = [[], {}, {"models": None}, {"models": {"name": "qwen2.5:latest", "size": 1}}, "qwen2.5:latest"]
    handler = Recorder(replying([json_reply(body) for body in bodies]))

    outcomes = [await list_outcome(handler.remote()) for _ in bodies]

    assert outcomes == ["AdapterError(OLLAMA_BAD_RESPONSE)"] * 5


# ---- 003 US1-RO-13 某一筆沒有字串的 name


async def test_list_local_models_任何一筆不是物件或沒有字串_name_時整份歸成_OLLAMA_BAD_RESPONSE() -> None:
    """US1-RO-13:字串、沒有 `name`、`name` 是 123、`name` 是 null、第二筆沒有 `name`;不跳過、不轉字串。"""
    bodies = [
        {"models": ["qwen2.5:latest"]},
        {"models": [{"model": "qwen2.5:latest", "size": 1}]},
        {"models": [{"name": 123, "size": 1}]},
        {"models": [{"name": None, "size": 1}]},
        {"models": [{"name": "qwen2.5:latest", "size": 1}, {"size": 2}]},
    ]
    handler = Recorder(replying([json_reply(body) for body in bodies]))

    outcomes = [await list_outcome(handler.remote()) for _ in bodies]

    assert outcomes == ["AdapterError(OLLAMA_BAD_RESPONSE)"] * 5


# ---- 003 US1-RO-14 size 不是非負整數


async def test_list_local_models_size_不是非負整數時歸成_OLLAMA_BAD_RESPONSE() -> None:
    """US1-RO-14:沒有 `size`、字串、-1、`true`(bool 不算整數)、null。"""
    models = [{"name": "qwen2.5:latest"}] + [{"name": "qwen2.5:latest", "size": size} for size in ("4.7 GB", -1, True, None)]
    handler = Recorder(replying([json_reply({"models": [model]}) for model in models]))

    outcomes = [await list_outcome(handler.remote()) for _ in models]

    assert outcomes == ["AdapterError(OLLAMA_BAD_RESPONSE)"] * 5


# ---- 003 US1-RO-15 x-timeout 10 秒


async def test_list_local_models_逾時四項都是_10_秒() -> None:
    """US1-RO-15:不帶任何逾時參數時,請求的逾時是合約 `x-timeout` 的 10 秒,不是 `get_version` 的 5 秒。"""
    seen: list[dict] = []

    def reply(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return json_reply({"models": []})

    await RemoteOllama(transport=httpx.MockTransport(reply)).list_local_models(base_url=LOCAL_FORWARD_URL)

    assert seen == [{"connect": 10.0, "read": 10.0, "write": 10.0, "pool": 10.0}]
