"""實跑案例共用的小工具(不是護欄;護欄 P1–P9 在 `conftest.py`)。

- `RecordingTransport`:包住 httpx 的真傳輸,把每一次請求的方法、路徑、狀態碼與回應本文的位元組留下來,
  讓案例在轉接層照常解析的同時,也能逐行檢查原始回應(轉接層會濾掉的行也看得到)。
  可設定只允許 GET、請求次數上限與兩次請求的最小間隔(US3-LIB-05 的「只送 GET、不超過 10 個、間隔 1 秒」)。
- `run`:在同步的測試裡跑一個 coroutine;轉接層的物件(`Tunnel` 等)不綁事件迴圈,可以跨多次 `run` 沿用。
- `free_loopback_port`:127.0.0.1 上一個沒人用的 port,避開 11434~11436(P6)。
- `field_names`:把一組 dict 的鍵整理成排序過的清單,供「欄位名稱相同」的比對與記錄。
"""

import asyncio
import json
import socket
import time
from collections.abc import AsyncIterator, Coroutine, Iterable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import httpx

from realrun.conftest import FORBIDDEN_PORTS, OLLAMA_PORT, UI_PORT, GuardViolation, check_port

T = TypeVar("T")
RESERVED_PORTS = frozenset({*FORBIDDEN_PORTS, 11435, OLLAMA_PORT, UI_PORT})


def run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def free_loopback_port() -> int:
    """127.0.0.1 上目前沒人用的 port;不會是 11434~11436 或 8780。"""
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port not in RESERVED_PORTS:
            check_port(port)
            return port


def port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def field_names(items: Iterable[dict[str, Any]]) -> list[str]:
    names: set[str] = set()
    for item in items:
        names.update(item.keys())
    return sorted(names)


def ndjson(body: bytes) -> list[Any]:
    """NDJSON 本文逐行解析;不是 JSON 的行以 `{"<不是 JSON>": 原文前 80 字}` 留下,讓檢查看得到。"""
    lines = []
    for raw in body.decode(errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            lines.append(json.loads(raw))
        except ValueError:
            lines.append({"<不是 JSON>": raw[:80]})
    return lines


@dataclass
class Exchange:
    method: str
    path: str
    status: int
    headers: dict[str, str]
    body: bytearray = field(default_factory=bytearray)

    def json(self) -> Any:
        return json.loads(bytes(self.body))


class _TeeStream(httpx.AsyncByteStream):
    def __init__(self, inner: httpx.AsyncByteStream, sink: bytearray) -> None:
        self._inner = inner
        self._sink = sink

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._inner:
            self._sink.extend(chunk)
            yield chunk

    async def aclose(self) -> None:
        await self._inner.aclose()


class RecordingTransport(httpx.AsyncBaseTransport):
    """留下每一次往返;轉接層每次呼叫都會關掉自己的 client,所以這裡的 `aclose` 不關真傳輸,用完呼叫 `close_inner`。"""

    def __init__(self, *, get_only: bool = False, max_requests: int | None = None, min_interval: float = 0.0) -> None:
        self._inner = httpx.AsyncHTTPTransport()
        self._get_only = get_only
        self._max_requests = max_requests
        self._min_interval = min_interval
        self._last_sent: float | None = None
        self.exchanges: list[Exchange] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.port is not None:
            check_port(request.url.port)
        if self._get_only and request.method != "GET":
            raise GuardViolation(f"這個案例只送 GET,收到 {request.method}")
        if self._max_requests is not None and len(self.exchanges) >= self._max_requests:
            raise GuardViolation(f"這個案例最多送 {self._max_requests} 個請求")
        if self._last_sent is not None:
            wait = self._min_interval - (time.monotonic() - self._last_sent)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_sent = time.monotonic()
        response = await self._inner.handle_async_request(request)
        exchange = Exchange(request.method, request.url.path, response.status_code, dict(response.headers))
        self.exchanges.append(exchange)
        assert isinstance(response.stream, httpx.AsyncByteStream)
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            stream=_TeeStream(response.stream, exchange.body),
            extensions=response.extensions,
            request=request,
        )

    async def aclose(self) -> None:
        return None

    async def close_inner(self) -> None:
        await self._inner.aclose()

    def last(self, method: str, path: str) -> Exchange | None:
        for exchange in reversed(self.exchanges):
            if exchange.method == method and exchange.path == path:
                return exchange
        return None
