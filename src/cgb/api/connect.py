"""`/api/connect`(contracts/ui.openapi.yaml § paths./connect)。"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cgb.adapters.errors import AdapterError
from cgb.domain import connect as snippets
from cgb.domain.errors import ollama_error

router = APIRouter()


def _snippets_of(port: int, models: list[str], context_length: int) -> dict[str, str | None]:
    """`ConnectSnippets`:每一段交給 `domain/connect.py` 產生。"""
    return {
        "opencode": snippets.opencode_snippet(port, models, context_length),
        "piModels": snippets.pi_models_snippet(port, models, context_length),
        "piSettings": None,
    }


@router.get("/connect")
async def get_connect_info(request: Request) -> JSONResponse:
    state = request.app.state.cgb
    services = request.app.state.services
    session = services.lifecycle.current()
    info: dict[str, Any] = {
        "ollamaPort": state.public_ollama_port,
        "basePath": "/v1",
        "sessionState": session["state"],
        "reason": None,
        "contextLength": None,
        "recommendedMinContextLength": 16384,
        "recommendedContextLength": 16384,
        "shouldWarn": False,
        "models": [],
        "reserveTokens": None,
        "snippets": None,
    }
    # info.x-reason-rule (1):不是就緒的任何狀態都回 200 與原因,不回錯誤
    if session["state"] != "ready":
        return JSONResponse({**info, "reason": "no_ready_session"})
    context_length = session["ollama"]["tuning"]["contextLength"]["value"]
    try:
        catalog = await services.catalog.list()
    except AdapterError as error:
        # 讀不到不當成目錄是空的(plan.md Q7):和 001 listCatalog 一樣回 502 或 504 與 S1 的代碼
        raise ollama_error(error.code) from None
    models = [item["name"] for item in catalog["items"]]
    # info.x-reason-rule (2):模型目錄是空的,`contextLength` 照實回
    if not models:
        return JSONResponse({**info, "reason": "no_models", "contextLength": context_length})
    return JSONResponse(
        {
            **info,
            "contextLength": context_length,
            "models": models,
            "snippets": _snippets_of(state.public_ollama_port, models, context_length),
        }
    )
