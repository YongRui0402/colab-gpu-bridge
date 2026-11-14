"""Hugging Face Hub 轉接層(`contracts/huggingface.openapi.yaml`;research.md R2~R4)。"""

from typing import Any

import httpx


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
        async with httpx.AsyncClient(base_url=self._base_url, transport=self._transport) as client:
            await client.get("/api/models", params=params)
        return {"items": [], "nextCursor": None}  # 回應的解讀由 US4-HF-06 之後的任務補

    async def list_repo_files(self, author: str, model: str) -> list[str]:
        raise NotImplementedError  # 後面的任務(US4-HF-10~)

    async def get_manifest(self, author: str, model: str, tag: str) -> dict[str, Any]:
        raise NotImplementedError  # 後面的任務(US4-HF-13~)

    async def list_quants(self, author: str, model: str) -> list[dict[str, Any]]:
        raise NotImplementedError  # 後面的任務(US4-HF-17~)
