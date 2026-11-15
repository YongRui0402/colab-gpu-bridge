"""`/api/downloads`(contracts/ui.openapi.yaml § paths./downloads)。"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from cgb.api._body import read_json
from cgb.domain.errors import ApiError
from cgb.domain.model_name import is_valid

router = APIRouter()


def _selected_models(body: Any) -> list[str]:
    """`DownloadSelection.models`:名稱格式最先檢查,不需要工作階段(`info.x-download-check-order` (1))。"""
    models = body["models"]
    if not models:
        raise ApiError(400, "EMPTY_MODEL_LIST")
    for model in models:
        if not is_valid(model):
            raise ApiError(400, "INVALID_MODEL_NAME", model=model)
    return models


@router.get("/downloads")
async def list_downloads(request: Request) -> JSONResponse:
    services = request.app.state.services
    # 沒有就緒的工作階段時暫停(排隊中的保留)
    paused = services.lifecycle.current()["state"] != "ready"
    return JSONResponse(services.downloads.queue(paused=paused))


@router.get("/downloads/auto-result")
async def get_auto_download_result(request: Request) -> JSONResponse:
    return JSONResponse({"result": request.app.state.services.auto_download.result()})


@router.post("/downloads/auto-result/dismiss")
async def dismiss_auto_download_result(request: Request) -> JSONResponse:
    result = request.app.state.services.auto_download.dismiss()
    if result is None:
        raise ApiError(404, "AUTO_DOWNLOAD_RESULT_NOT_FOUND")
    return JSONResponse(result)


@router.post("/downloads/estimate")
async def estimate_downloads(request: Request) -> JSONResponse:
    body = await read_json(request)
    return JSONResponse(await request.app.state.services.downloads.estimate(_selected_models(body)))


@router.post("/downloads")
async def enqueue_downloads(request: Request) -> JSONResponse:
    body = await read_json(request)
    jobs = await request.app.state.services.downloads.enqueue(_selected_models(body))
    return JSONResponse(jobs, status_code=201)


@router.post("/downloads/clear-completed")
async def clear_completed_downloads(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.services.downloads.clear_completed())


@router.post("/downloads/{job_id}/retry")
async def retry_download(request: Request, job_id: int) -> JSONResponse:
    return JSONResponse(await request.app.state.services.downloads.retry(job_id))


@router.delete("/downloads/{job_id}")
async def remove_download(request: Request, job_id: int) -> Response:
    request.app.state.services.downloads.remove(job_id)
    return Response(status_code=204)
