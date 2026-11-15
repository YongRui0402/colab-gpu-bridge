"""`/api/tuning`(contracts/ui.openapi.yaml § paths./tuning/overrides)。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/tuning/overrides")
async def get_tuning_overrides(request: Request) -> JSONResponse:
    return JSONResponse({"items": request.app.state.services.tunings_repo.type_overrides()})
