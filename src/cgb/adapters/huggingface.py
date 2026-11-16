"""Hugging Face Hub 轉接層(`contracts/huggingface.openapi.yaml`;research.md R2~R4)。"""

from typing import Any

import asyncio
import re

import httpx

from cgb.adapters.errors import AdapterError
from cgb.domain.hf_quants import candidates

# manifest 的媒體型別,和 Ollama 拉取時送的 Accept 相同(合約 getHfManifest)
MANIFEST_MEDIA_TYPE = "application/vnd.docker.distribution.manifest.v2+json"

# 展開版本時同時進行的 manifest 請求上限(合約 getHfManifest)
MANIFEST_CONCURRENCY = 4

# 模型權重那一層的 mediaType
MODEL_LAYER_MEDIA_TYPE = "application/vnd.ollama.image.model"

# 固定繁體中文的失敗說明(合約:不帶底層例外文字、網址或對方的英文原文)
_AUTH_REQUIRED = ("HF_AUTH_REQUIRED", "這個模型需要登入或同意條款,目前不支援")
_NO_GGUF = ("HF_NO_GGUF", "這個模型沒有可下載的 GGUF 檔")
_QUANT_UNAVAILABLE = ("HF_QUANT_UNAVAILABLE", "這個量化版本無法下載")
_BAD_RESPONSE = ("HF_BAD_RESPONSE", "Hugging Face 的回應無法解讀")
_TIMEOUT = ("HF_TIMEOUT", "Hugging Face 沒有在時限內回應")

# `<作者>/<模型>`,兩段都符合 `[A-Za-z0-9][A-Za-z0-9._-]*`;組不出 `hf.co/` 名稱的那一筆略過(合約 searchHfModels default)
_REPO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*")


def _json(response: httpx.Response) -> Any:
    """本文解析成 JSON;不是 JSON 就是 `HF_BAD_RESPONSE`(合約第 6 條)。"""
    try:
        return response.json()
    except ValueError:
        raise AdapterError(*_BAD_RESPONSE) from None


def _is_size(value: object) -> bool:
    """非負整數(`bool` 是 `int` 的子類別,要排除)。"""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_search_item(item: object) -> bool:
    """搜尋結果的一筆:有字串 `id` 的物件(合約 searchHfModels default)。"""
    return isinstance(item, dict) and isinstance(item.get("id"), str)


def _search_summary(item: dict[str, Any]) -> dict[str, Any] | None:
    """搜尋結果的一筆 → `{"id", "downloads"}`;`id` 組不出 `hf.co/` 名稱的回 None(略過);`downloads` 不是整數就是 None。"""
    if not _REPO_ID.fullmatch(item["id"]):
        return None
    return {"id": item["id"], "downloads": item["downloads"] if isinstance(item.get("downloads"), int) else None}


def _is_layer(layer: object) -> bool:
    """manifest 的一層:有非負整數 `size` 的物件(合約 getHfManifest default)。"""
    return isinstance(layer, dict) and _is_size(layer.get("size"))


def _is_tree_entry(entry: object) -> bool:
    """tree 的一筆:物件、有字串的 `type` 與 `path`,`type` 是 `file` 時還要有非負整數的 `size`(合約 listRepoFiles default)。"""
    if not isinstance(entry, dict) or not isinstance(entry.get("type"), str) or not isinstance(entry.get("path"), str):
        return False
    return entry["type"] != "file" or _is_size(entry.get("size"))


async def _cancel_all(tasks: list[asyncio.Future[Any]]) -> None:
    """取消還沒完成的 task 並等它們收尾(例外都吞掉,由呼叫的一方丟出原本的失敗)。"""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


class HuggingFaceHub:
    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = "https://huggingface.co",
        request_timeout: float = 10,
        expand_deadline: float = 10,
    ) -> None:
        self._transport = transport
        self._base_url = base_url
        self._request_timeout = request_timeout
        self._expand_deadline = expand_deadline

    async def _get(
        self, path: str, named_statuses: dict[int, tuple[str, str]] | None = None, **kwargs: Any
    ) -> httpx.Response:
        """`named_statuses` 是該操作點名的狀態碼對應的錯誤(代碼, 說明);其餘非 200 一律是 `HF_BAD_RESPONSE`(合約第 4、5 條)。"""
        named_statuses = named_statuses or {}
        try:
            # httpx 的逾時是每次讀寫各自計算,整個請求(含讀完本文)另以 asyncio.timeout 設期限(合約 x-timeout)
            async with (
                asyncio.timeout(self._request_timeout),
                httpx.AsyncClient(
                    base_url=self._base_url, transport=self._transport, timeout=httpx.Timeout(self._request_timeout)
                ) as client,
            ):
                response = await client.get(path, **kwargs)
        # TimeoutException 是 TransportError 的子類別,要先判斷(合約 x-failure-rules 第 1 條)
        except (httpx.TimeoutException, TimeoutError):
            raise AdapterError(*_TIMEOUT) from None
        except httpx.TransportError:
            # 不帶原例外的文字或網址,也不留例外鏈(合約 x-failure-rules)
            raise AdapterError("HF_UNREACHABLE", "連不到 Hugging Face") from None
        except httpx.HTTPError:
            # 其餘的 httpx 例外(例如本文解壓失敗的 DecodingError)是回應內容壞掉,不讓它越過轉接層(合約第 6 條)
            raise AdapterError(*_BAD_RESPONSE) from None
        if 500 <= response.status_code <= 599:
            raise AdapterError("HF_SERVER_ERROR", "Hugging Face 暫時無法使用")
        if response.status_code in named_statuses:
            raise AdapterError(*named_statuses[response.status_code])
        if response.status_code != 200:
            raise AdapterError(*_BAD_RESPONSE)
        return response

    async def search_models(self, query: str, cursor: str | None = None) -> dict[str, Any]:
        """`GET /api/models`;每一頁固定帶 `filter=gguf`、`gated=false`、`sort=downloads`、`limit=20` 與兩個 `expand[]`;不帶 token 與 Cookie。"""
        params = [
            ("search", query),
            ("filter", "gguf"),
            ("gated", "false"),
            ("sort", "downloads"),
            ("limit", "20"),
            ("expand[]", "downloads"),
            ("expand[]", "gated"),
        ]
        if cursor is not None:
            params.append(("cursor", cursor))  # 對方給的不透明字串,原樣帶回(不編碼兩次,也不照抄 `Link` 的網址)
        response = await self._get("/api/models", params=params)
        body = _json(response)
        # 回應要是陣列、每一筆是有字串 `id` 的物件;`id` 的格式不對才略過(合約第 7 條、searchHfModels default)
        if not isinstance(body, list) or not all(_is_search_item(item) for item in body):
            raise AdapterError(*_BAD_RESPONSE)
        summaries = (_search_summary(item) for item in body)
        items = [summary for summary in summaries if summary is not None]
        # 有沒有下一頁以 `Link` 的 `rel="next"` 為準;cursor 是不透明字串,取網址 query 解碼後的值(合約 searchHfModels)
        next_link = response.links.get("next")
        next_cursor = httpx.URL(next_link["url"]).params.get("cursor") if next_link else None
        return {"items": items, "nextCursor": next_cursor}

    async def list_repo_files(self, author: str, model: str) -> list[str]:
        """`GET /api/models/{author}/{model}/tree/main?recursive=true`;只讀第一個回應,不跟 `Link` 翻頁(plan.md Q3 決定 A)。"""
        # 401:私有或不存在的模型,分不出來,和 manifest 的 401 合成同一個原因(plan.md Q2 決定 A)
        response = await self._get(
            f"/api/models/{author}/{model}/tree/main", named_statuses={401: _AUTH_REQUIRED}, params={"recursive": "true"}
        )
        entries = _json(response)
        if not isinstance(entries, list) or not all(_is_tree_entry(entry) for entry in entries):
            raise AdapterError(*_BAD_RESPONSE)
        quants = candidates([entry["path"] for entry in entries if entry["type"] == "file"])
        if not quants:
            raise AdapterError(*_NO_GGUF)
        return quants

    async def get_manifest(self, author: str, model: str, tag: str) -> dict[str, Any]:
        """`GET /v2/{author}/{model}/manifests/{tag}`;回 `{"sizeBytes": layers[].size 的總和}`(不含 config)。"""
        response = await self._get(
            f"/v2/{author}/{model}/manifests/{tag}",
            named_statuses={400: _QUANT_UNAVAILABLE, 401: _AUTH_REQUIRED},
            headers={"Accept": MANIFEST_MEDIA_TYPE},
        )
        # 對方回的 Content-Type 是 application/json,不是 manifest 的媒體型別,所以不看它,只看本文
        manifest = _json(response)
        layers = manifest.get("layers") if isinstance(manifest, dict) else None
        # `layers` 要是陣列、每一層是有非負整數 `size` 的物件(合約 getHfManifest default)
        if not isinstance(layers, list) or not all(_is_layer(layer) for layer in layers):
            raise AdapterError(*_BAD_RESPONSE)
        # 沒有模型層就是拉下來不是模型,不能當成可下載(plan.md Q5 決定 A)
        if not any(layer.get("mediaType") == MODEL_LAYER_MEDIA_TYPE for layer in layers):
            raise AdapterError("HF_BAD_RESPONSE", "Hugging Face 的 manifest 沒有模型層")
        return {"sizeBytes": sum(layer["size"] for layer in layers)}

    async def list_quants(self, author: str, model: str) -> list[dict[str, Any]]:
        """列出一個模型的量化版本與大小:tree 的每個候選經 `get_manifest` 驗證,依檔案清單的順序;400 的候選不列出(research.md R3 第 6 步)。"""
        try:
            # 整個展開(tree 加所有候選的 manifest)共用一個期限,每個請求自己的期限仍在(合約 x-timeout)
            async with asyncio.timeout(self._expand_deadline):
                return await self._expand(author, model)
        except TimeoutError:
            raise AdapterError(*_TIMEOUT) from None

    async def _expand(self, author: str, model: str) -> list[dict[str, Any]]:
        gate = asyncio.Semaphore(MANIFEST_CONCURRENCY)

        async def size_of(quant: str) -> dict[str, Any] | None:
            async with gate:
                try:
                    manifest = await self.get_manifest(author, model, quant)
                except AdapterError as error:
                    if error.code != _QUANT_UNAVAILABLE[0]:
                        raise
                    return None
            return {"quant": quant, "sizeBytes": manifest["sizeBytes"]}

        tasks = [asyncio.ensure_future(size_of(quant)) for quant in await self.list_repo_files(author, model)]
        try:
            # gather 依傳入的順序回傳結果(不是完成的順序);第一個失敗就立刻丟出
            results = await asyncio.gather(*tasks)
        except BaseException:
            # 第一個失敗(或整體期限到)就取消其他還沒完成的請求,不留背景 task(合約 info.x-timeout、getHfManifest)
            await _cancel_all(tasks)
            raise
        sizes = [result for result in results if result is not None]
        if not sizes:
            # 候選都是 400 而一個都列不出來(research.md R3 第 7 步)
            raise AdapterError(*_NO_GGUF)
        return sizes
