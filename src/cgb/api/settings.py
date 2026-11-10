"""`/api/settings`(contracts/ui.openapi.yaml § paths./settings)。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cgb.api._body import read_json

router = APIRouter()


@router.get("/settings")
async def get_settings(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.services.settings.current())


@router.put("/settings")
async def update_settings(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.services.settings.update(await read_json(request)))
