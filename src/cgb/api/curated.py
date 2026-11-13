"""`/api/curated`(contracts/ui.openapi.yaml § paths./curated、paths./curated/{id})。"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from cgb.api._body import read_json
from cgb.domain.errors import ApiError
from cgb.domain.model_name import with_version
from cgb.repos.curated import CuratedDuplicate, CuratedRepo

router = APIRouter()

# CuratedModelInput.description 的 maxLength
DESCRIPTION_MAX_LENGTH = 200


def normalized(name: str) -> str:
    """沒寫版本視為 `latest`(contracts § ModelName);規則與下載共用 `with_version()`。"""
    return with_version(name)


def curated_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "recommendedRuntimeType": None,
        "downloaded": False,
    }


async def _input(request: Request) -> tuple[str, str | None]:
    body = await read_json(request)
    description = body.get("description")
    if description is not None and len(description) > DESCRIPTION_MAX_LENGTH:
        raise ApiError(400, "INVALID_CURATED_DESCRIPTION")
    return normalized(body["name"]), description


def _repo(request: Request) -> CuratedRepo:
    return request.app.state.services.curated


@router.get("/curated")
async def list_curated(request: Request) -> JSONResponse:
    # 精選清單是本系統自己的資料,不依賴 ollama.com
    return JSONResponse({"runtimeChecked": False, "items": [curated_payload(row) for row in _repo(request).all()]})


@router.post("/curated")
async def add_curated(request: Request) -> JSONResponse:
    name, description = await _input(request)
    try:
        curated_id = _repo(request).insert(name=name, description=description)
    except CuratedDuplicate:
        raise ApiError(409, "CURATED_DUPLICATE") from None
    return JSONResponse(curated_payload(_repo(request).get(curated_id)), status_code=201)


@router.put("/curated/{curated_id}")
async def update_curated(request: Request, curated_id: int) -> JSONResponse:
    name, description = await _input(request)
    _repo(request).update(curated_id, name=name, description=description)
    return JSONResponse(curated_payload(_repo(request).get(curated_id)))


@router.delete("/curated/{curated_id}")
async def remove_curated(request: Request, curated_id: int) -> Response:
    _repo(request).delete(curated_id)
    return Response(status_code=204)
