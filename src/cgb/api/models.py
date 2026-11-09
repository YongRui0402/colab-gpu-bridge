"""`/api/models`(contracts/ui.openapi.yaml § paths./models)。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cgb.services.catalog import Catalog

router = APIRouter()


@router.get("/models")
async def list_catalog(request: Request) -> JSONResponse:
    catalog = Catalog(request.app.state.cgb, request.app.state.services.lifecycle)
    return JSONResponse(await catalog.list())
