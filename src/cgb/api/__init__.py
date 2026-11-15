"""後端 UI API(E2):把 `/api` 的路由與用例掛進 `create_app` 建好的 UI app。"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from cgb.api import auth, chat, curated, downloads, events, history, huggingface, library, models, session, settings, tuning, usage
from cgb.db.connection import connect
from cgb.db.schema import create_schema
from cgb.domain.errors import ApiError
from cgb.domain.session_state import iso
from cgb.repos.auto_download import AutoDownloadRepo
from cgb.repos.curated import CuratedRepo
from cgb.repos.downloads import DownloadsRepo
from cgb.repos.sessions import SessionsRepo
from cgb.repos.settings import SettingsRepo
from cgb.repos.tunings import TuningsRepo
from cgb.repos.usage import UsageRepo
from cgb.services.auth import AuthService
from cgb.services.auto_download import AutoDownload
from cgb.services.catalog import Catalog
from cgb.services.downloads import DownloadsService
from cgb.services.event_bus import EventBus
from cgb.services.health_monitor import HealthMonitor
from cgb.services.idle_monitor import IdleMonitor
from cgb.services.library import Library
from cgb.services.recovery import Recovery
from cgb.services.runtime_switch import RuntimeSwitch
from cgb.services.session_lifecycle import SessionLifecycle
from cgb.services.settings import SettingsService
from cgb.services.usage import UsageService

# Q87:SSH 私鑰路徑由 CGB_SSH_IDENTITY_PATH 指定(deploy/compose.yaml)
DEFAULT_SSH_IDENTITY_PATH = "/data/ssh/id_ed25519"


@dataclass
class Services:
    auth: AuthService
    lifecycle: SessionLifecycle
    downloads: DownloadsService
    auto_download: AutoDownload
    switch: RuntimeSwitch
    sessions_repo: SessionsRepo
    tunings_repo: TuningsRepo
    events: EventBus
    monitor: HealthMonitor
    catalog: Catalog
    library: Library
    curated: CuratedRepo
    usage: UsageService
    settings: SettingsService
    idle: IdleMonitor


def install(app: FastAPI) -> None:
    state = app.state.cgb

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        conn = connect(state.db_path)
        create_schema(conn)
        key_path = os.environ.get("CGB_SSH_IDENTITY_PATH", DEFAULT_SSH_IDENTITY_PATH)
        repo = SessionsRepo(conn, now=lambda: iso(state.clock.now()))
        auth_service = AuthService(state)
        tunings_repo = TuningsRepo(conn)
        lifecycle = SessionLifecycle(state, repo, auth_service, key_path, tunings_repo)
        events = EventBus()
        downloads_service = DownloadsService(state, DownloadsRepo(conn), lifecycle, events)
        curated_repo = CuratedRepo(conn)
        auto_download = AutoDownload(state, AutoDownloadRepo(conn), curated_repo, downloads_service, lifecycle, events)
        monitor = HealthMonitor(state, repo, lifecycle)
        settings_service = SettingsService(SettingsRepo(conn), events)
        usage_service = UsageService(state, UsageRepo(conn), events, settings_service)
        idle = IdleMonitor(state, repo, lifecycle, settings_service)
        lifecycle.idle = idle
        lifecycle.usage = usage_service
        app.state.services = Services(
            auth=auth_service,
            lifecycle=lifecycle,
            downloads=downloads_service,
            auto_download=auto_download,
            switch=RuntimeSwitch(state, repo, lifecycle, downloads_service),
            sessions_repo=repo,
            tunings_repo=tunings_repo,
            events=events,
            monitor=monitor,
            catalog=Catalog(state, lifecycle, events),
            library=Library(state, lifecycle),
            curated=curated_repo,
            usage=usage_service,
            settings=settings_service,
            idle=idle,
        )
        # FR-001:工作階段結束類的狀態一寫入就清空下載佇列(research.md R1,清除只掛在這一處)
        repo.listeners.append(downloads_service.clear_if_session_over)
        repo.listeners.append(auto_download.clear_if_session_over)
        repo.listeners.append(lambda: events.session_updated(lifecycle.current()))
        # FR-027:新的閒置時限立即反映在倒數上,已經到了就立即結束;餘額警告依新的門檻判斷(FR-025)
        settings_service.listeners.append(lambda _: events.session_updated(lifecycle.current()))
        settings_service.listeners.append(lambda _: idle.check_now())
        settings_service.listeners.append(lambda _: usage_service.publish())
        auth_service.listeners.append(lambda status: events.auth_updated(status))
        recovery = Recovery(state, repo, key_path, lifecycle, downloads_service)
        recovery.start()
        monitor.start()
        usage_service.start()
        idle.start()
        # 對話轉送用的用戶端(plan.md Q35、Q44):連線 10 秒、收到回應標頭之前與兩段之間 300 秒
        chat_client = httpx.AsyncClient(timeout=httpx.Timeout(state.timeouts.chat_connect, read=state.timeouts.chat_read))
        app.state.chat_client = chat_client
        try:
            yield
        finally:
            await chat_client.aclose()
            await idle.stop()
            await usage_service.stop()
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
    app.include_router(library.router, prefix="/api")
    app.include_router(curated.router, prefix="/api")
    app.include_router(huggingface.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(usage.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(tuning.router, prefix="/api")
