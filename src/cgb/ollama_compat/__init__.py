"""E3 Ollama 相容端點:把轉送路由掛進 `create_app` 建好的 Ollama 相容端點 app(contracts/ollama-compat.openapi.yaml)。

工作階段等用例在 UI app 的 lifespan 裡建立(`cgb.api.install`);兩個 app 共用同一份記憶體,
所以這裡每個請求都向 UI app 取當下的用例,不在掛載時固定。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI

from cgb.ollama_compat import routes
from cgb.ollama_compat.forward import FORWARD_TIMEOUT


def install(app: FastAPI, ui: FastAPI) -> None:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(timeout=FORWARD_TIMEOUT) as client:
            app.state.forward_client = client
            yield

    def services() -> Any:
        return ui.state.services

    app.router.lifespan_context = lifespan
    app.state.services_of = services
    app.include_router(routes.router)
