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
PRELOAD_TIMEOUT = 300.0  # 預先載入的 x-timeout(plan.md Q5)
LIST_TIMEOUT = 10.0  # listLocalModels、listLoadedModels 的 x-timeout(plan.md Q5)
PULL_PROGRESS_TIMEOUT = 60.0  # pull 兩行進度之間的逾時,不設總時長(plan.md Q5)

# pull 串流裡 error 行含這段文字 → 官方模型庫沒有這個模型或版本(plan.md Q3)
NOT_FOUND_MARKER = "file does not exist"
# 串流開始前 Ollama 回的錯誤狀態碼 → 原因代碼(contracts § paths./api/generate.post 的 x-error-codes)
_STATUS_CODES = {400: "OLLAMA_BAD_REQUEST", 404: "OLLAMA_NOT_FOUND", 500: "OLLAMA_SERVER_ERROR"}
# pull 串流開始前的錯誤狀態碼 → 原因代碼(contracts info.x-failure-rules 第 3 條;pullModel 沒有 404 回應)
_PULL_STATUS_CODES = {400: "OLLAMA_BAD_REQUEST", 500: "OLLAMA_SERVER_ERROR"}


class RemoteOllama:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        version_timeout: float = VERSION_TIMEOUT,
        connect_timeout: float = CONNECT_TIMEOUT,
        stream_timeout: float = STREAM_TIMEOUT,
        pull_progress_timeout: float = PULL_PROGRESS_TIMEOUT,
    ) -> None:
        self._transport = transport
        self._version_timeout = version_timeout
        self._connect_timeout = connect_timeout
        self._stream_timeout = stream_timeout
        self._pull_progress_timeout = pull_progress_timeout

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

    async def list_local_models(self, *, base_url: str) -> dict[str, Any]:
        """`GET /api/tags`;回 `TagsResponse`(已下載完成的模型,每個有 `name`、`size`…)。"""
        body = await self._get_list(base_url, "/api/tags")
        if not all(_is_size(model.get("size")) for model in body["models"]):
            raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的清單有一筆沒有非負整數 size")
        return body

    async def list_loaded_models(self, *, base_url: str) -> dict[str, Any]:
        """`GET /api/ps`;回 `PsResponse`(已載入記憶體的模型)。"""
        return await self._get_list(base_url, "/api/ps")

    async def _get_list(self, base_url: str, path: str) -> dict[str, Any]:
        """`GET` 一份模型清單,對方的失敗依合約 `info.x-failure-rules` 歸成 `OLLAMA_` 代碼,不重試。"""
        try:
            async with self._client(base_url, httpx.Timeout(LIST_TIMEOUT)) as client:
                response = await client.get(path)
        except httpx.TimeoutException as error:
            raise AdapterError("OLLAMA_TIMEOUT", f"{LIST_TIMEOUT:g} 秒內沒有收到遠端 Ollama 的回應") from error
        except httpx.TransportError as error:
            raise AdapterError("OLLAMA_UNREACHABLE", f"連不到遠端 Ollama:{type(error).__name__}") from error
        except httpx.DecodingError as error:
            raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的回應本文無法解壓") from error
        return _parse_model_list(response)

    async def preload(self, *, base_url: str, model: str) -> dict[str, Any]:
        """預先載入(FR-015):`POST /api/generate` 只帶 `model` 與 `keep_alive: -1`(plan.md Q4),不帶 `prompt`。"""
        try:
            async with self._client(base_url, httpx.Timeout(PRELOAD_TIMEOUT)) as client:
                response = await client.post("/api/generate", json={"model": model, "keep_alive": -1})
        except httpx.TimeoutException as error:
            raise AdapterError("OLLAMA_TIMEOUT", f"{PRELOAD_TIMEOUT:g} 秒內沒有收到遠端 Ollama 的回應") from error
        except httpx.TransportError as error:
            raise AdapterError("OLLAMA_UNREACHABLE", f"連不到遠端 Ollama:{type(error).__name__}") from error
        except httpx.DecodingError as error:
            raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的回應本文無法解壓") from error
        if response.status_code != 200:
            code = _STATUS_CODES.get(response.status_code, "OLLAMA_BAD_RESPONSE")
            raise AdapterError(code, f"遠端 Ollama 回了 {response.status_code}")
        try:
            body = response.json()
        except ValueError as error:
            raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的預先載入回應不是 JSON") from error
        if not isinstance(body, dict):
            raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的預先載入回應不是 JSON 物件")
        return body

    async def pull_model(self, *, base_url: str, model: str) -> AsyncIterator[dict[str, Any]]:
        """`POST /api/pull`(串流);逐行產出帶 `total` 的進度行,最後產出 `{"status":"success"}`。

        沒有 `total` 的狀態行(`pulling manifest`、`verifying sha256 digest`…)不是進度,不產出。
        失敗一律歸成 `OLLAMA_` 代碼(contracts `info.x-failure-rules`),底層例外不往外拋;
        串流開始前的失敗在 `await` 時就丟出,開始後的在迭代時丟出。
        """
        client = self._client(base_url, httpx.Timeout(self._pull_progress_timeout, connect=self._connect_timeout))
        request = client.build_request("POST", "/api/pull", json={"model": model, "stream": True})
        try:
            response = await client.send(request, stream=True)
        except httpx.TransportError as error:
            await client.aclose()
            raise _pull_send_failure(error) from error
        rejection = _pull_start_failure(response)
        if rejection is not None:
            await response.aclose()
            await client.aclose()
            raise rejection
        return _pull_progress(client, response)


def _pull_send_failure(error: httpx.TransportError) -> AdapterError:
    """串流開始前的傳輸層失敗(`info.x-failure-rules` 第 1、2 條):逾時先於其他傳輸層失敗判定。"""
    if isinstance(error, httpx.TimeoutException):
        return AdapterError("OLLAMA_TIMEOUT", "遠端 Ollama 沒有在時限內回應下載請求")
    return AdapterError("OLLAMA_UNREACHABLE", f"連不到遠端 Ollama:{type(error).__name__}")


def _pull_start_failure(response: httpx.Response) -> AdapterError | None:
    """收到回應標頭後、讀本文之前的判定(`info.x-failure-rules` 第 3、4 條);可以開始讀串流時交回 `None`。

    只看狀態碼與 `Content-Type` 的 media type(`;` 之前、去掉空白、不分大小寫,plan.md Q45),不讀本文。
    """
    if response.status_code != 200:
        code = _PULL_STATUS_CODES.get(response.status_code, "OLLAMA_BAD_RESPONSE")
        return AdapterError(code, f"遠端 Ollama 回了 {response.status_code}")
    if response.headers.get("content-type", "").split(";")[0].strip().lower() != "application/x-ndjson":
        return AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的下載回應不是 NDJSON")
    return None


def _is_size(value: object) -> bool:
    """非負整數;`bool` 是 `int` 的子類,要排除。"""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_model_list(response: httpx.Response) -> dict[str, Any]:
    """200 的 JSON 物件、`models` 是陣列、每筆是物件且有字串 `name`;任何一處不符整份算 `OLLAMA_BAD_RESPONSE`(plan.md Q2)。"""
    if response.status_code != 200:
        raise AdapterError("OLLAMA_BAD_RESPONSE", f"遠端 Ollama 回了非預期的狀態碼 {response.status_code}")
    try:
        body = response.json()
    except ValueError as error:
        raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的清單回應不是 JSON") from error
    if not isinstance(body, dict) or not isinstance(body.get("models"), list):
        raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的清單回應缺少 models 陣列")
    for model in body["models"]:
        if not isinstance(model, dict) or not isinstance(model.get("name"), str):
            raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的清單有一筆沒有字串 name")
    return body


async def _ndjson_until_done(client: httpx.AsyncClient, response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """逐行解析 NDJSON,直到 `done` 為 true 的那一行;之前就斷線算中斷。"""
    try:
        async for item in _json_lines(response):
            yield item
            if item.get("done") is True:
                return
    except httpx.TransportError as error:
        raise AdapterError("OLLAMA_STREAM_INTERRUPTED", "遠端 Ollama 的串流在完成前中斷") from error
    finally:
        await response.aclose()
        await client.aclose()


async def _pull_progress(client: httpx.AsyncClient, response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """pull 的 NDJSON:只產出帶 `total` 的進度行,直到 `status` 為 `success` 的那一行。

    HTTP 200 之後的失敗以 `error` 行回報(contracts § paths./api/pull.post 的 200 回應):
    含 `file does not exist` 是找不到模型或版本,其他是下載失敗;某一行不是合法的 JSON 物件或欄位型別不符算壞回應;
    `success` 之前結束或斷線算中斷;兩行之間超過進度間隔逾時算逾時(不設總時長,大模型下載不會被砍)。
    """
    try:
        async for raw in response.aiter_lines():
            if not raw.strip():
                continue
            item = _parse_pull_line(raw)
            if "error" in item:
                code = "OLLAMA_NOT_FOUND" if NOT_FOUND_MARKER in item["error"] else "OLLAMA_PULL_FAILED"
                raise AdapterError(code, item["error"])
            if item.get("status") == "success":
                yield item
                return
            if "total" in item:
                yield item
    except httpx.TimeoutException as error:
        raise AdapterError("OLLAMA_TIMEOUT", "遠端 Ollama 的下載進度停住,超過進度間隔逾時") from error
    except httpx.TransportError as error:
        raise AdapterError("OLLAMA_STREAM_INTERRUPTED", "遠端 Ollama 的下載串流在完成前中斷") from error
    finally:
        await response.aclose()
        await client.aclose()
    raise AdapterError("OLLAMA_STREAM_INTERRUPTED", "遠端 Ollama 的下載串流在 success 之前就結束")


def _parse_pull_line(raw: str) -> dict[str, Any]:
    """pull 串流的一行:要是 JSON 物件,`status`、`error` 是字串,`total`、`completed` 是非負整數;不符算 `OLLAMA_BAD_RESPONSE`。"""
    try:
        item = json.loads(raw)
    except ValueError as error:
        raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的下載進度有一行不是 JSON") from error
    if not isinstance(item, dict):
        raise AdapterError("OLLAMA_BAD_RESPONSE", "遠端 Ollama 的下載進度有一行不是 JSON 物件")
    for key in ("status", "error"):
        if key in item and not isinstance(item[key], str):
            raise AdapterError("OLLAMA_BAD_RESPONSE", f"遠端 Ollama 的下載進度有一行 {key} 不是字串")
    for key in ("total", "completed"):
        if key in item and not _is_size(item[key]):
            raise AdapterError("OLLAMA_BAD_RESPONSE", f"遠端 Ollama 的下載進度有一行 {key} 不是非負整數")
    return item


async def _json_lines(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """NDJSON 的每一行解析成 JSON,略過空行。"""
    async for line in response.aiter_lines():
        if line.strip():
            yield json.loads(line)
