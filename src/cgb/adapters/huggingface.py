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

# `<作者>/<模型>`,兩段都符合 `[A-Za-z0-9][A-Za-z0-9._-]*`;組不出 `hf.co/` 名稱的那一筆略過(合約 searchHfModels default)
_REPO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*")


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
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport) as client:
            response = await client.get("/api/models", params=params)
        items = [
            {"id": item["id"], "downloads": item["downloads"] if isinstance(item.get("downloads"), int) else None}
            for item in response.json()
            if _REPO_ID.fullmatch(item["id"])
        ]
        # 有沒有下一頁以 `Link` 的 `rel="next"` 為準;cursor 是不透明字串,取網址 query 解碼後的值(合約 searchHfModels)
        next_link = response.links.get("next")
        next_cursor = httpx.URL(next_link["url"]).params.get("cursor") if next_link else None
        return {"items": items, "nextCursor": next_cursor}

    async def list_repo_files(self, author: str, model: str) -> list[str]:
        """`GET /api/models/{author}/{model}/tree/main?recursive=true`;只讀第一個回應,不跟 `Link` 翻頁(plan.md Q3 決定 A)。"""
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport) as client:
            response = await client.get(f"/api/models/{author}/{model}/tree/main", params={"recursive": "true"})
        if response.status_code == 401:
            # 私有或不存在的模型,分不出來,和 manifest 的 401 合成同一個原因(plan.md Q2 決定 A)
            raise AdapterError("HF_AUTH_REQUIRED", "這個模型需要登入或同意條款,目前不支援")
        quants = candidates([entry["path"] for entry in response.json() if entry["type"] == "file"])
        if not quants:
            raise AdapterError("HF_NO_GGUF", "這個模型沒有可下載的 GGUF 檔")
        return quants

    async def get_manifest(self, author: str, model: str, tag: str) -> dict[str, Any]:
        """`GET /v2/{author}/{model}/manifests/{tag}`;回 `{"sizeBytes": layers[].size 的總和}`(不含 config)。"""
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport) as client:
            response = await client.get(
                f"/v2/{author}/{model}/manifests/{tag}", headers={"Accept": MANIFEST_MEDIA_TYPE}
            )
        if 500 <= response.status_code <= 599:
            raise AdapterError("HF_SERVER_ERROR", "Hugging Face 暫時無法使用")
        if response.status_code == 401:
            raise AdapterError("HF_AUTH_REQUIRED", "這個模型需要登入或同意條款,目前不支援")
        if response.status_code == 400:
            raise AdapterError("HF_QUANT_UNAVAILABLE", "這個量化版本無法下載")
        # 對方回的 Content-Type 是 application/json,不是 manifest 的媒體型別,所以不看它,只看本文
        layers = response.json()["layers"]
        # 沒有模型層就是拉下來不是模型,不能當成可下載(plan.md Q5 決定 A)
        if not any(layer.get("mediaType") == MODEL_LAYER_MEDIA_TYPE for layer in layers):
            raise AdapterError("HF_BAD_RESPONSE", "Hugging Face 的 manifest 沒有模型層")
        return {"sizeBytes": sum(layer["size"] for layer in layers)}

    async def list_quants(self, author: str, model: str) -> list[dict[str, Any]]:
        """列出一個模型的量化版本與大小:tree 的每個候選經 `get_manifest` 驗證,依檔案清單的順序;400 的候選不列出(research.md R3 第 6 步)。"""
        gate = asyncio.Semaphore(MANIFEST_CONCURRENCY)

        async def size_of(quant: str) -> dict[str, Any] | None:
            async with gate:
                try:
                    manifest = await self.get_manifest(author, model, quant)
                except AdapterError as error:
                    if error.code != "HF_QUANT_UNAVAILABLE":
                        raise
                    return None
            return {"quant": quant, "sizeBytes": manifest["sizeBytes"]}

        tasks = [asyncio.ensure_future(size_of(quant)) for quant in await self.list_repo_files(author, model)]
        try:
            # gather 依傳入的順序回傳結果(不是完成的順序);第一個失敗就立刻丟出
            results = await asyncio.gather(*tasks)
        except BaseException:
            # 第一個失敗就取消其他還沒完成的請求,不留背景 task(合約 info.x-timeout、getHfManifest)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        sizes = [result for result in results if result is not None]
        if not sizes:
            # 候選都是 400 而一個都列不出來(research.md R3 第 7 步)
            raise AdapterError("HF_NO_GGUF", "這個模型沒有可下載的 GGUF 檔")
        return sizes
