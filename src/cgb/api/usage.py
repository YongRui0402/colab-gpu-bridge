"""`/api/usage`(contracts/ui.openapi.yaml § paths./usage)。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/usage")
async def get_usage(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.services.usage.current())
