"""`/api/huggingface`(contracts/ui.openapi.yaml § paths./huggingface/search、paths./huggingface/models/{author}/{model}/quants)。"""

import asyncio
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cgb.adapters.errors import AdapterError
from cgb.domain.errors import ApiError, hf_error
from cgb.domain.model_name import HF_PREFIX, match_key

router = APIRouter()

# `searchHfModels` 的 `q` 去掉前後空白後的最大長度
QUERY_MAX_LENGTH = 100

# `HfModel.author`、`HfModel.model` 的 pattern;組得出 `hf.co/<作者>/<模型>` 名稱的才送到 Hugging Face
_HF_ID_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _model_payload(item: dict[str, Any]) -> dict[str, Any]:
    """`HfModel`:轉接層給的 `id`(`<作者>/<模型>`)拆出作者與模型,組成 Ollama 用的 `hf.co/` 名稱。"""
    author, model = item["id"].split("/", 1)
    return {
        "id": item["id"],
        "author": author,
        "model": model,
        "name": f"{HF_PREFIX}{item['id']}",
        "downloads": item.get("downloads"),
    }


@router.get("/huggingface/search")
async def search_hf_models(request: Request, q: str | None = None, cursor: str | None = None) -> JSONResponse:
    # 不以 FastAPI 的 `Query(...)` 驗:它的 422 與 `detail` 不是合約的 `Error`
    query = (q or "").strip()
    if not 1 <= len(query) <= QUERY_MAX_LENGTH:
        raise ApiError(400, "INVALID_QUERY")
    if cursor == "":
        raise ApiError(400, "INVALID_CURSOR")
    try:
        page = await request.app.state.cgb.huggingface.search_models(query=query, cursor=cursor)
    except AdapterError as error:
        # 連不到、5xx、格式不符回 502,逾時回 504;搜尋區以外的路徑不受影響(FR-016);關鍵字不放進 `model`
        raise hf_error(error.code) from None
    return JSONResponse(
        {
            "query": query,
            "items": [_model_payload(item) for item in page["items"]],
            "hasMore": page["nextCursor"] is not None,
            "nextCursor": page["nextCursor"],
        }
    )


@router.get("/huggingface/models/{author}/{model}/quants")
async def list_hf_quants(request: Request, author: str, model: str) -> JSONResponse:
    # 不以 FastAPI 的 `Path(pattern=...)` 驗:它的 422 與 `detail` 不是合約的 `Error`
    if not (_HF_ID_PART.fullmatch(author) and _HF_ID_PART.fullmatch(model)):
        raise ApiError(400, "INVALID_HF_MODEL_ID")
    deadline = request.app.state.cgb.timeouts.hf_expand_deadline
    loop = asyncio.get_running_loop()
    started = loop.time()
    # Hugging Face 這一段與讀模型清單同時開始,期限都從收到請求起算(Q67;兩段不串接)
    quants_task = asyncio.create_task(request.app.state.cgb.huggingface.list_quants(author=author, model=model))
    keys_task = asyncio.create_task(request.app.state.services.downloads.local_keys())
    try:
        try:
            quants = await asyncio.wait_for(quants_task, timeout=deadline)
        except AdapterError as error:
            raise hf_error(error.code) from None
        except TimeoutError:
            raise hf_error("HF_TIMEOUT") from None
        # 「已下載」不分大小寫比對(FR-018);沒有就緒的工作階段、讀不到或期限內沒讀完時 `runtimeChecked` 為 false
        try:
            local_keys = await asyncio.wait_for(keys_task, timeout=max(0.0, deadline - (loop.time() - started)))
        except TimeoutError:
            local_keys = None
    finally:
        quants_task.cancel()
        keys_task.cancel()

    def quant_payload(quant: dict[str, Any]) -> dict[str, Any]:
        name = f"{HF_PREFIX}{author}/{model}:{quant['quant']}"
        return {
            "quant": quant["quant"],
            "name": name,
            "sizeBytes": quant["sizeBytes"],
            "downloaded": local_keys is not None and match_key(name) in local_keys,
        }

    return JSONResponse(
        {
            "author": author,
            "model": model,
            "runtimeChecked": local_keys is not None,
            "quants": [quant_payload(quant) for quant in quants],
        }
    )
