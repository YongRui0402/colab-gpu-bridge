"""遠端 Ollama 轉接層(`contracts/remote-ollama.openapi.yaml`;research.md R3)。

執行環境上的 Ollama 只聽 127.0.0.1:11434,本系統經 SSH 本機轉發呼叫它;`base_url` 是轉發的位址
(`Tunnel.open_tunnel` 回報的 `baseUrl`)。對方的失敗一律歸成 `components.schemas.Error` 的 `OLLAMA_` 代碼。
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from cgb.adapters.errors import AdapterError

VERSION_TIMEOUT = 5.0  # getVersion 的 x-timeout(plan.md Q5)
CONNECT_TIMEOUT = 10.0  # 推論類的連線逾時(plan.md Q22)
STREAM_TIMEOUT = 300.0  # 推論類第一段與兩段之間的逾時,不設總時長(plan.md Q22)

# 串流開始前 Ollama 回的錯誤狀態碼 → 原因代碼(contracts § paths./api/generate.post 的 x-error-codes)
_STATUS_CODES = {400: "OLLAMA_BAD_REQUEST", 404: "OLLAMA_NOT_FOUND", 500: "OLLAMA_SERVER_ERROR"}


class RemoteOllama:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        version_timeout: float = VERSION_TIMEOUT,
        connect_timeout: float = CONNECT_TIMEOUT,
        stream_timeout: float = STREAM_TIMEOUT,
    ) -> None:
        self._transport = transport
        self._version_timeout = version_timeout
        self._connect_timeout = connect_timeout
        self._stream_timeout = stream_timeout

    def _client(self, base_url: str, timeout: httpx.Timeout) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=base_url, transport=self._transport, timeout=timeout)

    async def get_version(self, base_url: str) -> dict[str, Any]:
        """`GET /api/version`;回 `VersionResponse`(含字串 `version`)。"""
        try:
            async with self._client(base_url, httpx.Timeout(self._version_timeout)) as client:
                response = await client.get("/api/version")
        except httpx.TimeoutException as error:
            raise AdapterError("OLLAMA_TIMEOUT", f"{self._version_timeout:g} 秒內沒有收到遠端 Ollama 的回應") from error
        except httpx.TransportError as error:
            raise AdapterError("OLLAMA_UNREACHABLE", f"連不到遠端 Ollama:{type(error).__name__}") from error
        if response.status_code != 200:
            raise AdapterError("OLLAMA_BAD_RESPONSE", f"遠端 Ollama 回了非預期的狀態碼 {response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的版本回應不是 JSON") from error
        if not isinstance(body, dict) or not isinstance(body.get("version"), str):
            raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的版本回應缺少 version")
        return body

    async def generate(self, base_url: str, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """`POST /api/generate`;回逐行產出 `GenerateResponse` 的非同步迭代器。

        串流開始前的 400/404/500 在這裡就丟出,`message` 保留遠端的英文 `error` 原文;
        串流在 `done: true` 之前斷線,在迭代時丟 `OLLAMA_STREAM_INTERRUPTED`。
        """
        client = self._client(base_url, httpx.Timeout(self._stream_timeout, connect=self._connect_timeout))
        response = await client.send(client.build_request("POST", "/api/generate", json=body), stream=True)
        if response.status_code != 200:
            try:
                await response.aread()
            finally:
                await client.aclose()
            raise AdapterError(_STATUS_CODES[response.status_code], response.json()["error"])
        return _ndjson_until_done(client, response)


async def _ndjson_until_done(client: httpx.AsyncClient, response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """逐行解析 NDJSON,直到 `done` 為 true 的那一行;之前就斷線算中斷。"""
    try:
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            item = json.loads(line)
            yield item
            if item.get("done") is True:
                return
    except httpx.TransportError as error:
        raise AdapterError("OLLAMA_STREAM_INTERRUPTED", "遠端 Ollama 的串流在完成前中斷") from error
    finally:
        await response.aclose()
        await client.aclose()
