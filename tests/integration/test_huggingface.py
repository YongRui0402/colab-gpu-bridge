"""E12 Hugging Face Hub 轉接層(testplan.md § 5.1;接縫:`HuggingFaceHub` 的方法,對方是 `httpx.MockTransport`)。

huggingface.co 一律由 handler 代替,不連外網;每個 `HuggingFaceHub` 都注入 `transport`。
"""

import inspect
from collections.abc import Awaitable, Callable

import httpx
import pytest

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
