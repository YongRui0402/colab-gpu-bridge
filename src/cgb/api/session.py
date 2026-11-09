"""`/api/session`(contracts/ui.openapi.yaml § paths./session)。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cgb.api._body import read_json
from cgb.domain.session_state import parse_runtime_type

router = APIRouter()


@router.get("/session")
async def get_session(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.services.lifecycle.current())


@router.post("/session")
async def open_session(request: Request) -> JSONResponse:
    runtime_type = parse_runtime_type(await read_json(request))
    session = await request.app.state.services.lifecycle.open(runtime_type)
    return JSONResponse(session, status_code=202)


@router.delete("/session")
async def end_session(request: Request) -> JSONResponse:
    session = await request.app.state.services.lifecycle.end()
    return JSONResponse(session, status_code=202)


@router.post("/session/restart")
async def restart_session(request: Request) -> JSONResponse:
    runtime_type = parse_runtime_type(await read_json(request))
    session = await request.app.state.services.switch.restart(runtime_type)
    return JSONResponse(session, status_code=202)
