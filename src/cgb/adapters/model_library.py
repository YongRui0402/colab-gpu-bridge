"""Ollama 官方模型庫轉接層(`contracts/model-library.openapi.yaml`;research.md R6)。

搜尋頁與版本頁取自 ollama.com 的 HTML(解析在 `cgb.domain.library_html`),manifest 取自 registry.ollama.ai。
"""

import asyncio
import json
from typing import Any

import httpx

from cgb.adapters.errors import AdapterError
from cgb.domain.library_html import has_next_page, is_search_page, parse_model_tags, parse_search_models

OLLAMA_BASE_URL = "https://ollama.com"
REGISTRY_BASE_URL = "https://registry.ollama.ai"
MANIFEST_MEDIA_TYPE = "application/vnd.docker.distribution.manifest.v2+json"
REQUEST_TIMEOUT_SECONDS = 10.0  # 每個請求的逾時與整體期限(spec NFR-001;research.md R2)


def _check_status(response: httpx.Response, *, not_found: str | None = None) -> None:
    """三個操作共用的狀態碼判定(research.md R3):404 → `LIBRARY_NOT_FOUND`(只有給了 `not_found` 說明的操作;
    搜尋頁沒有 404 的合約回應,404 歸非預期)、5xx → `LIBRARY_SERVER_ERROR`、其他非 200(含 3xx,不跟著導向)→ `LIBRARY_BAD_RESPONSE`。"""
    status = response.status_code
    if status == 404 and not_found is not None:
        raise AdapterError("LIBRARY_NOT_FOUND", not_found)
    if status >= 500:
        raise AdapterError("LIBRARY_SERVER_ERROR", f"官方模型庫暫時無法處理(HTTP {status})")
    if status != 200:
        raise AdapterError("LIBRARY_BAD_RESPONSE", f"官方模型庫回了非預期的狀態碼 {status}")


class ModelLibrary:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        ollama_base_url: str = OLLAMA_BASE_URL,
        registry_base_url: str = REGISTRY_BASE_URL,
        request_timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._transport = transport
        self._ollama_base_url = ollama_base_url
        self._registry_base_url = registry_base_url
        self._request_timeout = request_timeout

    async def _get(self, base_url: str, path: str, **kwargs: Any) -> httpx.Response:
        seconds = self._request_timeout
        try:
            # httpx 的逾時是每次讀寫各自計算,整個請求(含讀完本文)另以 asyncio.timeout 設期限(research.md R2)
            async with (
                asyncio.timeout(seconds),
                # 不跟著 3xx 導向:導向去的是別的頁(例如第 1 頁),由 _check_status 歸成非預期(research.md R3)
                httpx.AsyncClient(
                    base_url=base_url, transport=self._transport, timeout=httpx.Timeout(seconds), follow_redirects=False
                ) as client,
            ):
                return await client.get(path, **kwargs)
        # TimeoutException 是 TransportError 的子類別,要先判斷(research.md R1)
        except (httpx.TimeoutException, TimeoutError):
            raise AdapterError("LIBRARY_TIMEOUT", "官方模型庫沒有在時限內回應") from None
        except httpx.TransportError:
            # 不帶原例外的文字或網址(spec NFR-002),也不留例外鏈(research.md R1)
            raise AdapterError("LIBRARY_UNREACHABLE", "連不到官方模型庫") from None

    async def search_library(self, q: str, page: int = 1) -> dict[str, Any]:
        """`GET /search`;每一頁都帶 `c=local`(Q10),第 2 頁起帶 `page` 與 `HX-Request: true` 取片段。"""
        params: dict[str, str | int] = {"q": q, "c": "local"}
        headers: dict[str, str] = {}
        if page > 1:
            params["page"] = page
            headers["HX-Request"] = "true"
        response = await self._get(self._ollama_base_url, "/search", params=params, headers=headers)
        _check_status(response)
        if not is_search_page(response.text, first_page=page == 1):
            raise AdapterError("LIBRARY_BAD_RESPONSE", "官方模型庫的搜尋頁格式不符")
        names = parse_search_models(response.text)
        return {"items": [{"name": name} for name in names], "hasMore": has_next_page(response.text)}

    async def list_model_tags(self, name: str) -> list[dict[str, Any]]:
        """`GET /library/{name}/tags`;一次列出全部版本(不分頁)。"""
        response = await self._get(self._ollama_base_url, f"/library/{name}/tags")
        _check_status(response, not_found=f"官方模型庫沒有 {name}")
        tags = parse_model_tags(response.text, name)
        if not tags:
            # 一個 `/library/<名稱>:<版本>` 連結都沒有就是改版或不是版本頁(research.md R3)
            raise AdapterError("LIBRARY_BAD_RESPONSE", "官方模型庫的版本頁格式不符")
        return tags

    async def get_manifest(self, name: str, tag: str) -> dict[str, Any]:
        """`GET /v2/library/{name}/manifests/{tag}`;回 `{"sizeBytes": 各層 size 合計}`(不含 config,research.md R6)。"""
        response = await self._get(
            self._registry_base_url, f"/v2/library/{name}/manifests/{tag}", headers={"Accept": MANIFEST_MEDIA_TYPE}
        )
        # 404 是沒有這個模型或這個版本(registry 回的內容相同,分不出來)
        _check_status(response, not_found=f"官方模型庫沒有 {name}:{tag}")
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
