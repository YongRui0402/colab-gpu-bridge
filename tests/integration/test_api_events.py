"""E2 後端 UI API:SSE 狀態推送(testplan.md § 2.1,`/api/events` › 訂閱;contracts/ui-events.asyncapi.yaml)。

SSE 用測試行程內的 uvicorn(127.0.0.1 隨機 port,Q97),經真的 HTTP 連線讀事件。
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from integration.test_api_session import ColabWorld, open_ready


async def sse_events(response: httpx.Response) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """一則一則讀出 (`event:`, `data:` 的 JSON)。"""
    event, data = None, []
    async for line in response.aiter_lines():
        if line.startswith("event:"):
            event = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            data.append(line.removeprefix("data:").strip())
        elif line == "" and data:
            yield event or "message", json.loads("\n".join(data))
            event, data = None, []


async def next_session_update(events: AsyncIterator[tuple[str, dict[str, Any]]], timeout: float = 2.0) -> dict[str, Any] | None:
    async def find() -> dict[str, Any] | None:
        async for name, payload in events:
            if name == "session.updated":
                return payload.get("session")
        return None

    try:
        return await asyncio.wait_for(find(), timeout)
    except TimeoutError:
        return None


# ---------------------------------------------------------------- US1-API-38


async def test_連上時先收到工作階段的完整現況_之後收到每次變化(live_servers: Any, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        name = (await open_ready(client))["name"]

        # Act
        async with client.stream("GET", "/api/events") as response:
            events = sse_events(response)
            snapshot = await next_session_update(events)
            await client.delete("/api/session")
            change = await next_session_update(events)

    # Assert
    assert response.status_code == 200
    assert snapshot is not None and (snapshot.get("state"), snapshot.get("name")) == ("ready", name)
    assert change is not None and change.get("state") == "ending"

