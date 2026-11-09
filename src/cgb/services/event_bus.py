"""狀態推送事件的分送(contracts/ui-events.asyncapi.yaml)。

每條 SSE 連線一個佇列;事件都是完整的現況,所有連線收到相同的內容。
"""

import asyncio
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[tuple[str, dict[str, Any]]]] = set()

    def subscribe(self) -> asyncio.Queue[tuple[str, dict[str, Any]]]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[tuple[str, dict[str, Any]]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, name: str, payload: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait((name, payload))

    def session_updated(self, session: dict[str, Any]) -> None:
        self.publish("session.updated", {"type": "session.updated", "session": session})

    def auth_updated(self, auth: dict[str, Any]) -> None:
        self.publish("auth.updated", {"type": "auth.updated", "auth": auth})
