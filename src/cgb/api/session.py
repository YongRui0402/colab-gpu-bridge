"""`/api/session`(contracts/ui.openapi.yaml § paths./session)。"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cgb.api._body import read_json
from cgb.domain.errors import ApiError
from cgb.domain.session_state import parse_runtime_type
from cgb.domain.tuning import parse_overrides

router = APIRouter()


def _tuning_of(body: dict[str, Any]) -> dict[str, int | None] | None:
    """本文帶的覆蓋值(`OpenSessionInput.tuning`);沒有帶時是 None。不符時丟 400,在開啟或結束舊的之前擋下(FR-017)。"""
    return parse_overrides(body["tuning"]) if body.get("tuning") is not None else None


@router.get("/session")
async def get_session(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.services.lifecycle.current())


@router.post("/session")
async def open_session(request: Request) -> JSONResponse:
    body = await read_json(request)
    runtime_type = parse_runtime_type(body)
    tuning = _tuning_of(body)
    session = await request.app.state.services.lifecycle.open(runtime_type, tuning)
    return JSONResponse(session, status_code=202)


@router.delete("/session")
async def end_session(request: Request) -> JSONResponse:
    session = await request.app.state.services.lifecycle.end()
    return JSONResponse(session, status_code=202)


@router.post("/session/restart")
async def restart_session(request: Request) -> JSONResponse:
    body = await read_json(request)
    runtime_type = parse_runtime_type(body)
    tuning = _tuning_of(body)
    services = request.app.state.services
    # 照 001 restartSession 的 409:沒有有效的 Colab 帳號授權時不結束舊的(FR-008)
    if (await services.auth.check())["state"] == "logged_out":
        raise ApiError(409, "AUTH_REQUIRED")
    session = await services.switch.restart(runtime_type, tuning)
    return JSONResponse(session, status_code=202)
