"""`/api/curated`(contracts/ui.openapi.yaml § paths./curated、paths./curated/{id})。"""

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from cgb.api._body import read_json
from cgb.domain.errors import ApiError
from cgb.domain.model_name import is_valid, match_key, with_version
from cgb.domain.session_state import GPU_TYPES
from cgb.repos.curated import CuratedDuplicate, CuratedRepo

router = APIRouter()

# CuratedModelInput.description 的 maxLength
DESCRIPTION_MAX_LENGTH = 200


def normalized(name: str) -> str:
    """沒寫版本視為 `latest`(contracts § ModelName);規則與下載共用 `with_version()`。"""
    return with_version(name)


def _runtime_type_of(row: dict[str, Any]) -> dict[str, Any] | None:
    if row["recommended_runtime_type_gpu"] is None:
        return None
    return {"gpu": row["recommended_runtime_type_gpu"], "highMem": bool(row["recommended_runtime_type_high_mem"])}


def curated_payload(row: dict[str, Any], local_keys: set[str] | None = None) -> dict[str, Any]:
    """`local_keys` 是執行環境上已有模型的 `match_key`;None 表示沒有就緒或讀不到(`downloaded` 一律 false)。"""
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "recommendedRuntimeType": _runtime_type_of(row),
        "autoDownload": bool(row["auto_download"]),
        "downloaded": local_keys is not None and match_key(row["name"]) in local_keys,
    }


def _runtime_type(value: Any) -> dict[str, Any] | None:
    """`recommendedRuntimeType`:沒有(null)或 `RuntimeType`;H100 照常接受(FR-017 只隱藏 UI 選單)。"""
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("gpu") not in GPU_TYPES or not isinstance(value.get("highMem"), bool):
        raise ApiError(400, "INVALID_RUNTIME_TYPE")
    return {"gpu": value["gpu"], "highMem": value["highMem"]}


@dataclass(frozen=True)
class CuratedInput:
    """驗證過的 `CuratedModelInput`;`name` 已補版本。"""

    name: str
    description: str | None
    runtime_type: dict[str, Any] | None
    auto_download: bool


async def _input(request: Request) -> CuratedInput:
    """新增與修改共用的本文驗證(`CuratedModelInput`):任何一項不合法都在寫入之前回 400。"""
    body = await read_json(request)
    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_REQUEST_BODY")
    name = body.get("name")
    if not is_valid(name):
        # 不向任何模型來源查證名稱存不存在(FR-018、邊界情況)
        raise ApiError(400, "INVALID_MODEL_NAME", model=name if isinstance(name, str) else None)
    description = body.get("description")
    if description is not None and (not isinstance(description, str) or len(description) > DESCRIPTION_MAX_LENGTH):
        raise ApiError(400, "INVALID_CURATED_DESCRIPTION")
    runtime_type = _runtime_type(body.get("recommendedRuntimeType"))
    auto_download = body.get("autoDownload", False)
    if not isinstance(auto_download, bool):
        raise ApiError(400, "INVALID_AUTO_DOWNLOAD")
    return CuratedInput(normalized(name), description, runtime_type, auto_download)


def _repo(request: Request) -> CuratedRepo:
    return request.app.state.services.curated


@router.get("/curated")
async def list_curated(request: Request) -> JSONResponse:
    # 精選清單是本系統自己的資料,不依賴 ollama.com;就緒時才對照執行環境上的模型,讀不到照常回 200
    local_keys = await request.app.state.services.downloads.local_keys()
    items = [curated_payload(row, local_keys) for row in _repo(request).all()]
    return JSONResponse({"runtimeChecked": local_keys is not None, "items": items})


@router.post("/curated")
async def add_curated(request: Request) -> JSONResponse:
    body = await _input(request)
    try:
        curated_id = _repo(request).insert(
            name=body.name, description=body.description, runtime_type=body.runtime_type, auto_download=body.auto_download
        )
    except CuratedDuplicate as duplicate:
        raise ApiError(409, "CURATED_DUPLICATE", model=duplicate.existing) from None
    return JSONResponse(curated_payload(_repo(request).get(curated_id)), status_code=201)


@router.put("/curated/{curated_id}")
async def update_curated(request: Request, curated_id: int) -> JSONResponse:
    body = await _input(request)
    try:
        found = _repo(request).update(
            curated_id,
            name=body.name,
            description=body.description,
            runtime_type=body.runtime_type,
            auto_download=body.auto_download,
        )
    except CuratedDuplicate as duplicate:
        raise ApiError(409, "CURATED_DUPLICATE", model=duplicate.existing) from None
    if not found:
        raise ApiError(404, "CURATED_NOT_FOUND")
    return JSONResponse(curated_payload(_repo(request).get(curated_id)))


@router.delete("/curated/{curated_id}")
async def remove_curated(request: Request, curated_id: int) -> Response:
    if not _repo(request).delete(curated_id):
        raise ApiError(404, "CURATED_NOT_FOUND")
    return Response(status_code=204)
