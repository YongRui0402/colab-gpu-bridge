"""後端 UI API(E2):把 `/api` 的路由與用例掛進 `create_app` 建好的 UI app。"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from cgb.api import auth, downloads, events, history, models, session
from cgb.db.connection import connect
from cgb.db.schema import create_schema
from cgb.domain.errors import ApiError
from cgb.domain.session_state import iso
from cgb.repos.downloads import DownloadsRepo
from cgb.repos.sessions import SessionsRepo
from cgb.services.auth import AuthService
from cgb.services.downloads import DownloadsService
from cgb.services.event_bus import EventBus
from cgb.services.health_monitor import HealthMonitor
from cgb.services.recovery import Recovery
from cgb.services.runtime_switch import RuntimeSwitch
from cgb.services.session_lifecycle import SessionLifecycle

# Q87:SSH 私鑰路徑由 CGB_SSH_IDENTITY_PATH 指定(deploy/compose.yaml)
DEFAULT_SSH_IDENTITY_PATH = "/data/ssh/id_ed25519"


@dataclass
class Services:
    auth: AuthService
    lifecycle: SessionLifecycle
    downloads: DownloadsService
    switch: RuntimeSwitch
    sessions_repo: SessionsRepo
    events: EventBus


def install(app: FastAPI) -> None:
    state = app.state.cgb

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        conn = connect(state.db_path)
        create_schema(conn)
        key_path = os.environ.get("CGB_SSH_IDENTITY_PATH", DEFAULT_SSH_IDENTITY_PATH)
        repo = SessionsRepo(conn, now=lambda: iso(state.clock.now()))
        auth_service = AuthService(state)
        lifecycle = SessionLifecycle(state, repo, auth_service, key_path)
        downloads_service = DownloadsService(state, DownloadsRepo(conn))
        app.state.services = Services(
            auth=auth_service,
            lifecycle=lifecycle,
            downloads=downloads_service,
            switch=RuntimeSwitch(state, repo, lifecycle, downloads_service),
            sessions_repo=repo,
            events=EventBus(),
        )
        repo.listeners.append(lambda: app.state.services.events.session_updated(lifecycle.current()))
        auth_service.listeners.append(lambda status: app.state.services.events.auth_updated(status))
        recovery = Recovery(state, repo, key_path)
        recovery.start()
        monitor = HealthMonitor(state, repo)
        monitor.start()
        try:
            yield
        finally:
            await monitor.stop()
            await recovery.stop()
            await app.state.services.lifecycle.shutdown()
            conn.close()

    app.router.lifespan_context = lifespan

    @app.exception_handler(ApiError)
    async def api_error(_: Request, error: ApiError) -> JSONResponse:
        # 錯誤本文一律是 `Error`(contracts/ui.openapi.yaml)
        return JSONResponse(error.body(), status_code=error.status)

    app.include_router(auth.router, prefix="/api")
    app.include_router(session.router, prefix="/api")
    app.include_router(history.router, prefix="/api")
    app.include_router(downloads.router, prefix="/api")
    app.include_router(models.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
