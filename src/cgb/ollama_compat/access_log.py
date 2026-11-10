"""Ollama 相容端點的請求紀錄(spec.md § 假設:只記時間、模型、耗時與狀態碼;NFR-010)。

以 ASGI middleware 包住整個 Ollama 相容端點:先讀完本文讀出 `model`(`/api/show` 舊版用 `name`),再原樣交給下游重播;
不讀本文就回應的路徑(403、404、503)也記得到模型(Q199)。
不記 prompt、回應內容、路徑與用戶端位址。時間由 logging 的 formatter 加上。
"""

import json
import logging
import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

# 解析模型名稱的本文上限;超過就不解析(帶圖片的請求本文可能很大)
_MAX_PEEK_BYTES = 1 << 20


def _model_of(body: bytes) -> str:
    try:
        data: Any = json.loads(body) if body else None
    except ValueError:
        return "-"
    if isinstance(data, dict):
        model = data.get("model") or data.get("name")
        if isinstance(model, str) and model:
            return model
    return "-"


class AccessLog:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        started = time.monotonic()
        status = 500
        # 轉送本來就整份讀進本文(forward.py 的 `await request.body()`),這裡先讀完不改變記憶體用量
        pending: list[Message] = []
        while True:
            message = await receive()
            pending.append(message)
            if message["type"] != "http.request" or not message.get("more_body", False):
                break
        body = b"".join(m.get("body", b"") for m in pending if m["type"] == "http.request")

        async def receive_replaying() -> Message:
            if pending:
                return pending.pop(0)
            return await receive()

        async def send_watching(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            # 串流回應送完(或中斷)之後才回來,耗時含整段串流
            await self._app(scope, receive_replaying, send_watching)
        finally:
            model = _model_of(body) if len(body) <= _MAX_PEEK_BYTES else "-"
            elapsed_ms = (time.monotonic() - started) * 1000
            logger.info("model=%s 耗時=%.0fms 狀態碼=%d", model, elapsed_ms, status)
