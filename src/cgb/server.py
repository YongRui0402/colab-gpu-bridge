"""在同一個行程起 UI 與 Ollama 相容端點兩個 uvicorn(plan.md Q93、Q113;compose.yaml 的 x-ports)。

兩個 app 來自同一個 `create_app` 結果,共用同一份 `AppState`(工作階段、閒置計時與下載佇列在同一份記憶體裡)。
正式進入點 `python -m cgb` 與測試行程內的 uvicorn 都走這裡。
"""

import asyncio
import socket
from collections.abc import Sequence

import uvicorn

from cgb.app import AppPair


class Servers:
    """跑在同一個事件迴圈裡的兩個 uvicorn。"""

    def __init__(
        self,
        pair: AppPair,
        *,
        host: str,
        ui_port: int,
        ollama_port: int,
        log_level: str = "info",
        access_log: bool = True,
        timeout_graceful_shutdown: float | None = None,
    ) -> None:
        """`timeout_graceful_shutdown`:要求結束後最多等連線自己結束幾秒(None 是一直等)。

        收到結束訊號時 sse-starlette 會自己收掉 SSE 連線;不經訊號、由 `stop()` 結束時(測試行程內),
        開著的 SSE 連線不會自己結束,要靠這個時限。
        """
        self.pair = pair
        self._servers = tuple(
            uvicorn.Server(
                uvicorn.Config(
                    app,
                    host=host,
                    port=port,
                    log_level=log_level,
                    access_log=access_log,
                    lifespan="on",
                    timeout_graceful_shutdown=timeout_graceful_shutdown,
                )
            )
            for app, port in ((pair.ui, ui_port), (pair.ollama, ollama_port))
        )

    @property
    def started(self) -> bool:
        return all(server.started for server in self._servers)

    def stop(self) -> None:
        """要求兩個伺服器結束(可以從別的執行緒呼叫)。"""
        for server in self._servers:
            server.should_exit = True

    async def serve(self, sockets: Sequence[socket.socket] | None = None) -> None:
        """跑到兩個伺服器都結束;`sockets` 是事先綁好的 UI、Ollama 相容端點兩個 socket(測試用)。"""
        bound = [[sock] for sock in sockets] if sockets is not None else [None] * len(self._servers)
        await asyncio.gather(*(server.serve(sockets=socks) for server, socks in zip(self._servers, bound, strict=True)))


def serve(pair: AppPair, *, host: str, ui_port: int, ollama_port: int) -> None:
    """正式進入點:UI 與 Ollama 相容端點跑到收到結束訊號為止。"""
    asyncio.run(Servers(pair, host=host, ui_port=ui_port, ollama_port=ollama_port).serve())
