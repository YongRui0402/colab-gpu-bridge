"""`/api/library`(contracts/ui.openapi.yaml § paths./library/search、paths./library/models/{name}/tags)。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/library/search")
async def search_library(request: Request, q: str, page: int = 1) -> JSONResponse:
    return JSONResponse(await request.app.state.services.library.search(q, page))


@router.get("/library/models/{name}/tags")
async def list_library_tags(request: Request, name: str) -> JSONResponse:
    return JSONResponse(await request.app.state.services.library.tags(name))
