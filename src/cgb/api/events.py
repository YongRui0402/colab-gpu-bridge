"""`/api/events`(contracts/ui.openapi.yaml § paths./events;contracts/ui-events.asyncapi.yaml)。"""

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette import EventSourceResponse

router = APIRouter()

# 每 15 秒一行 `: ping` 保持連線(asyncapi 的 description)
PING_SECONDS = 15


@router.get("/events")
async def subscribe_events(request: Request) -> EventSourceResponse:
    services = request.app.state.services
    queue = services.events.subscribe()

    async def stream() -> AsyncIterator[dict[str, Any]]:
        try:
            # 連上時先送快照:工作階段的完整現況、下載佇列、自動下載結果(沒有時 result 為 null)
            session = services.lifecycle.current()
            yield {"event": "session.updated", "data": json.dumps({"type": "session.updated", "session": session}, ensure_ascii=False)}
            downloads = {"type": "downloads.snapshot", "queue": services.downloads.queue(paused=session["state"] != "ready")}
            yield {"event": "downloads.snapshot", "data": json.dumps(downloads, ensure_ascii=False)}
            auto = {"type": "autoDownload.updated", "result": services.auto_download.result()}
            yield {"event": "autoDownload.updated", "data": json.dumps(auto, ensure_ascii=False)}
            while True:
                name, payload = await queue.get()
                yield {"event": name, "data": json.dumps(payload, ensure_ascii=False)}
        finally:
            services.events.unsubscribe(queue)

    return EventSourceResponse(stream(), ping=PING_SECONDS)
