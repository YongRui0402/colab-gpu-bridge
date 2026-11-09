"""`/api/downloads`(contracts/ui.openapi.yaml § paths./downloads)。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/downloads")
async def list_downloads(request: Request) -> JSONResponse:
    services = request.app.state.services
    # 沒有就緒的工作階段時暫停(排隊中的保留)
    paused = services.lifecycle.current()["state"] != "ready"
    return JSONResponse(services.downloads.queue(paused=paused))
