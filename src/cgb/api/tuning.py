"""`/api/tuning`、`/api/session/tuning`(contracts/ui.openapi.yaml § paths./tuning/overrides、paths./session/tuning)。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cgb.api._body import read_json
from cgb.domain.tuning import parse_overrides

router = APIRouter()


@router.get("/tuning/overrides")
async def get_tuning_overrides(request: Request) -> JSONResponse:
    return JSONResponse({"items": request.app.state.services.tunings_repo.type_overrides()})


@router.post("/session/tuning")
async def apply_tuning(request: Request) -> JSONResponse:
    body = await read_json(request)
    session = await request.app.state.services.tuning.apply(parse_overrides(body))
    return JSONResponse(session, status_code=202)
