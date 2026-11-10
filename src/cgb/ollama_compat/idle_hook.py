"""經 Ollama 相容端點的請求重設閒置計時的掛點(FR-026、Q24、Q52)。

以 ASGI middleware 包住整個 Ollama 相容端點:被擋下的管理操作(403)與白名單外的路徑(404)也算請求。
UI app 的 `/api/*` 不經過這裡,所以 UI 的輪詢與 SSE 不會重設(Q24)。
"""

from collections.abc import Callable
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send


class IdleHook:
    def __init__(self, app: ASGIApp, services_of: Callable[[], Any]) -> None:
        self._app = app
        # 用例在 UI app 的 lifespan 裡建立,每個請求才去取(cgb.ollama_compat.install 的說明)
        self._services_of = services_of

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        idle = self._services_of().idle
        idle.request_started()
        try:
            # 串流回應送完(或中斷)之後才回來,所以串流進行中都算進行中的請求
            await self._app(scope, receive, send)
        finally:
            idle.request_finished()
