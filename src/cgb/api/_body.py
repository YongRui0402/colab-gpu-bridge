"""API 共用:讀請求本文。"""

import json
from typing import Any

from fastapi import Request

from cgb.domain.errors import ApiError


async def read_json(request: Request) -> Any:
    """本文不是合法 JSON 時回 400 `INVALID_REQUEST_BODY`。"""
    try:
        return json.loads(await request.body())
    except ValueError:
        raise ApiError(400, "INVALID_REQUEST_BODY") from None
