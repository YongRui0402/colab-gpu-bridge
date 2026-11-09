"""`/api/downloads`(contracts/ui.openapi.yaml § paths./downloads)。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from cgb.api._body import read_json

router = APIRouter()


@router.get("/downloads")
async def list_downloads(request: Request) -> JSONResponse:
    services = request.app.state.services
    # 沒有就緒的工作階段時暫停(排隊中的保留)
    paused = services.lifecycle.current()["state"] != "ready"
    return JSONResponse(services.downloads.queue(paused=paused))


@router.post("/downloads/estimate")
async def estimate_downloads(request: Request) -> JSONResponse:
    body = await read_json(request)
    return JSONResponse(await request.app.state.services.downloads.estimate(body["models"]))


@router.post("/downloads")
async def enqueue_downloads(request: Request) -> JSONResponse:
    body = await read_json(request)
    jobs = await request.app.state.services.downloads.enqueue(body["models"])
    return JSONResponse(jobs, status_code=201)


@router.post("/downloads/clear-completed")
async def clear_completed_downloads(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.services.downloads.clear_completed())


@router.post("/downloads/{job_id}/retry")
async def retry_download(request: Request, job_id: int) -> JSONResponse:
    return JSONResponse(request.app.state.services.downloads.retry(job_id))


@router.delete("/downloads/{job_id}")
async def remove_download(request: Request, job_id: int) -> Response:
    request.app.state.services.downloads.remove(job_id)
    return Response(status_code=204)
