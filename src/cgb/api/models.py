"""`/api/models`(contracts/ui.openapi.yaml § paths./models、paths./models/preload)。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cgb.api._body import read_json

router = APIRouter()


@router.get("/models")
async def list_catalog(request: Request) -> JSONResponse:
    return JSONResponse(await request.app.state.services.catalog.list())


@router.post("/models/preload")
async def preload_model(request: Request) -> JSONResponse:
    body = await read_json(request)
    model = await request.app.state.services.catalog.preload(body["name"])
    return JSONResponse(model, status_code=202)
