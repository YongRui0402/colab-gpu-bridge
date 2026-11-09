"""Ollama 官方模型庫轉接層(`contracts/model-library.openapi.yaml`;research.md R6)。

搜尋頁與版本頁取自 ollama.com 的 HTML(解析在 `cgb.domain.library_html`),manifest 取自 registry.ollama.ai。
"""

import json
from typing import Any

import httpx

from cgb.adapters.errors import AdapterError
from cgb.domain.library_html import has_next_page, parse_model_tags, parse_search_models

OLLAMA_BASE_URL = "https://ollama.com"
REGISTRY_BASE_URL = "https://registry.ollama.ai"
MANIFEST_MEDIA_TYPE = "application/vnd.docker.distribution.manifest.v2+json"


class ModelLibrary:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        ollama_base_url: str = OLLAMA_BASE_URL,
        registry_base_url: str = REGISTRY_BASE_URL,
    ) -> None:
        self._transport = transport
        self._ollama_base_url = ollama_base_url
        self._registry_base_url = registry_base_url

    async def _get(self, base_url: str, path: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(base_url=base_url, transport=self._transport) as client:
            return await client.get(path, **kwargs)

    async def search_library(self, q: str, page: int = 1) -> dict[str, Any]:
        """`GET /search`;每一頁都帶 `c=local`(Q10),第 2 頁起帶 `page` 與 `HX-Request: true` 取片段。"""
        params: dict[str, str | int] = {"q": q, "c": "local"}
        headers: dict[str, str] = {}
        if page > 1:
            params["page"] = page
            headers["HX-Request"] = "true"
        response = await self._get(self._ollama_base_url, "/search", params=params, headers=headers)
        names = parse_search_models(response.text)
        return {"items": [{"name": name} for name in names], "hasMore": has_next_page(response.text)}

    async def list_model_tags(self, name: str) -> list[dict[str, Any]]:
        """`GET /library/{name}/tags`;一次列出全部版本(不分頁)。"""
        response = await self._get(self._ollama_base_url, f"/library/{name}/tags")
        return parse_model_tags(response.text, name)

    async def get_manifest(self, name: str, tag: str) -> dict[str, Any]:
        """`GET /v2/library/{name}/manifests/{tag}`;回 `{"sizeBytes": 各層 size 合計}`(不含 config,research.md R6)。"""
        response = await self._get(
            self._registry_base_url, f"/v2/library/{name}/manifests/{tag}", headers={"Accept": MANIFEST_MEDIA_TYPE}
        )
        if response.status_code == 404:
            # 沒有這個模型或這個版本(registry 回的內容相同,分不出來)
            raise AdapterError("LIBRARY_NOT_FOUND", f"官方模型庫沒有 {name}:{tag}")
        if response.status_code >= 500:
            raise AdapterError("LIBRARY_SERVER_ERROR", f"官方模型庫暫時無法處理(HTTP {response.status_code})")
        if response.status_code != 200:
            raise AdapterError("LIBRARY_BAD_RESPONSE", f"官方模型庫回了非預期的狀態碼 {response.status_code}")
        # 雲端版本的 Content-Type 是 text/plain,內容仍是同一種 JSON,所以不看 Content-Type
        try:
            manifest = json.loads(response.text)
        except ValueError as error:
            raise AdapterError("LIBRARY_BAD_RESPONSE", "官方模型庫的 manifest 不是 JSON") from error
        layers = manifest.get("layers") if isinstance(manifest, dict) else None
        if not isinstance(layers, list) or not all(
            isinstance(layer, dict) and isinstance(layer.get("size"), int) for layer in layers
        ):
            raise AdapterError("LIBRARY_BAD_RESPONSE", "官方模型庫的 manifest 格式不符")
        if not layers:
            raise AdapterError("LIBRARY_CLOUD_ONLY", f"{name}:{tag} 只能在 Ollama 雲端執行,不能下載")
        return {"sizeBytes": sum(layer["size"] for layer in layers)}
