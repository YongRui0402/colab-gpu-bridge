"""模型目錄:執行環境上已下載的模型與是否已載入(FR-014;contracts/ui.openapi.yaml § listCatalog)。"""

from typing import Any

from cgb.services.session_lifecycle import SessionLifecycle


class Catalog:
    def __init__(self, state: Any, lifecycle: SessionLifecycle) -> None:
        self._state = state
        self._lifecycle = lifecycle

    async def list(self) -> dict[str, Any]:
        remote, base_url = self._state.remote_ollama, self._lifecycle.base_url
        local = (await remote.list_local_models(base_url=base_url))["models"]
        loaded = {m["name"] for m in (await remote.list_loaded_models(base_url=base_url))["models"]}
        items = [
            {
                "name": m["name"],
                "sizeBytes": m["size"],
                "modifiedAt": m["modified_at"],
                "loaded": m["name"] in loaded,
                "mayNotFit": None,
                "preload": {"state": "idle", "reasonCode": None, "message": None},
            }
            for m in local
        ]
        # 顯示記憶體總量由 S8 probe_resources 提供(Q7、Q62),屬故事 3;還沒有時照合約回 null
        return {"vramBytes": None, "items": items}
