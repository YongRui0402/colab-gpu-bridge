"""官方模型庫的搜尋與版本(FR-020;contracts/ui.openapi.yaml § searchLibrary、listLibraryTags)。"""

from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.errors import ApiError
from cgb.services.session_lifecycle import SessionLifecycle


class Library:
    def __init__(self, state: Any, lifecycle: SessionLifecycle) -> None:
        self._state = state
        self._lifecycle = lifecycle

    async def _local_models(self) -> list[str] | None:
        """執行環境上已有的模型名稱(含版本);沒有就緒的工作階段時是 None(`runtimeChecked` 為 false)。"""
        base_url = self._lifecycle.ready_base_url()
        if base_url is None:
            return None
        return [m["name"] for m in (await self._state.remote_ollama.list_local_models(base_url=base_url))["models"]]

    async def search(self, q: str, page: int) -> dict[str, Any]:
        try:
            found = await self._state.model_library.search_library(q=q, page=page)
        except AdapterError as error:
            # 連不到、5xx、解析不出來(contracts § searchLibrary 的 502);UI 退回精選清單與輸入名稱
            raise ApiError(502, error.code) from None
        local = await self._local_models()

        def downloaded_tags(name: str) -> list[str]:
            return [full.split(":", 1)[1] for full in local or [] if full.split(":", 1)[0] == name]

        return {
            "query": q,
            "page": page,
            "hasMore": found["hasMore"],
            "runtimeChecked": local is not None,
            "items": [{**item, "downloadedTags": downloaded_tags(item["name"])} for item in found["items"]],
        }

    async def tags(self, name: str) -> dict[str, Any]:
        """一個官方模型的所有版本;`fullName` 對照執行環境標出已下載的(雲端專用版本由 S2 標出 `cloudOnly`,Q8)。"""
        tags = await self._state.model_library.list_model_tags(name=name)
        local = await self._local_models()
        return {
            "name": name,
            "runtimeChecked": local is not None,
            "tags": [
                {**t, "fullName": f"{name}:{t['tag']}", "downloaded": f"{name}:{t['tag']}" in (local or [])} for t in tags
            ],
        }
