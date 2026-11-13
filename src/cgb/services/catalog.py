"""模型目錄:執行環境上已下載的模型、是否已載入與預先載入(FR-014、FR-015;contracts/ui.openapi.yaml § listCatalog、preloadModel)。"""

from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.errors import ApiError
from cgb.services.event_bus import EventBus
from cgb.services.session_lifecycle import SessionLifecycle

_IDLE = {"state": "idle", "reasonCode": None, "message": None}
# 預先載入失敗給使用者看的說明;不把遠端的英文原文交給 UI(NFR-010)
PRELOAD_FAILED_MESSAGE = "預先載入失敗,可能是顯示記憶體不足;請改用較小的模型,或換有更多顯示記憶體的執行階段類型。"


class Catalog:
    def __init__(self, state: Any, lifecycle: SessionLifecycle, events: EventBus) -> None:
        self._state = state
        self._lifecycle = lifecycle
        self._events = events
        # 每個模型的預先載入狀態(PreloadState);只活在這次執行之中
        self._preloads: dict[str, dict[str, Any]] = {}
        # (工作階段名稱, 顯示記憶體總量);同名的工作階段讀到之後沿用,不再 `colab exec`(FR-003、FR-005、research.md R3)
        self._vram: tuple[str, int] | None = None

    async def list(self) -> dict[str, Any]:
        base_url = self._lifecycle.require_ready_base_url()
        remote = self._state.remote_ollama
        local = (await remote.list_local_models(base_url=base_url))["models"]
        loaded = {m["name"] for m in (await remote.list_loaded_models(base_url=base_url))["models"]}
        vram = await self._vram_total()
        items = [
            {
                "name": m["name"],
                "sizeBytes": m["size"],
                "modifiedAt": m["modified_at"],
                "loaded": m["name"] in loaded,
                # NFR-006:和顯示記憶體總量比(不扣已載入的,Q62);讀不到時是 null
                "mayNotFit": m["size"] > vram if vram is not None else None,
                "preload": dict(self._preloads.get(m["name"], _IDLE)),
            }
            for m in local
        ]
        return {"vramBytes": vram, "items": items}

    async def _vram_total(self) -> int | None:
        """顯示記憶體總量由 S8 probe_resources 提供(Q7、Q62);讀不到時是 None。"""
        name = self._lifecycle.current()["name"]
        if self._vram is None or self._vram[0] != name:
            try:
                resources = await self._state.colab.probe_resources(name=name)
            except AdapterError:
                # 讀不到不擋目錄(FR-004);不寫入快取,下一次再讀
                return None
            total = resources["vramTotalBytes"]
            if total is None:
                # `colab exec` 成功但讀到 null 也視同讀不到;不寫入快取,下一次再讀(FR-004、邊界情況)
                return None
            self._vram = (name, total)
        return self._vram[1]

    async def preload(self, name: str) -> dict[str, Any]:
        """受理預先載入:標成載入中,在背景送只有 `model` 的載入(S1 preload,keep_alive: -1,Q4)。"""
        base_url = self._lifecycle.require_ready_base_url()
        # 先確認在目錄裡;不在就回 404,不會自動下載(FR-016)
        item = next((m for m in (await self.list())["items"] if m["name"] == name), None)
        if item is None:
            raise ApiError(404, "OLLAMA_NOT_FOUND")
        # 正在載入時不另送一次,照樣回 202
        if self._preloads.get(name, _IDLE)["state"] != "loading":
            self._preloads[name] = {"state": "loading", "reasonCode": None, "message": None}
            self._lifecycle.spawn(self._run_preload(base_url, name))
        return {**item, "preload": dict(self._preloads[name])}

    async def _run_preload(self, base_url: str, name: str) -> None:
        try:
            await self._state.remote_ollama.preload(base_url=base_url, model=name)
        except AdapterError as error:
            # 只標這個模型失敗,其他模型的載入狀態照 ps(邊界情況)
            self._preloads[name] = {"state": "failed", "reasonCode": error.code, "message": PRELOAD_FAILED_MESSAGE}
        else:
            self._preloads.pop(name, None)
        await self.publish()

    async def publish(self) -> None:
        """推送 `models.updated`(目錄的完整現況)。"""
        self._events.models_updated(await self.list())
