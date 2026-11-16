"""`/api/connect`(contracts/ui.openapi.yaml § paths./connect)。"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cgb.domain import connect as snippets

router = APIRouter()


def _snippets_of(port: int, models: list[str], context_length: int | None) -> dict[str, str | None]:
    """`ConnectSnippets`:每一段交給 `domain/connect.py` 產生。"""
    return {
        "opencode": snippets.opencode_snippet(port, models, context_length),
        "piModels": snippets.pi_models_snippet(port, models, context_length),
        "piSettings": snippets.pi_settings_snippet(context_length),
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
        "recommendedMinContextLength": snippets.RECOMMENDED_MIN_CONTEXT,
        # 讀不到顯示記憶體或沒有就緒的工作階段時是下限(Q11);就緒且讀得到目錄時在下面依顯示記憶體改寫
        "recommendedContextLength": snippets.recommended_context_length(None),
        "shouldWarn": False,
        "models": [],
        "reserveTokens": None,
        "snippets": None,
    }
    # info.x-reason-rule (1):不是就緒的任何狀態都回 200 與原因,不回錯誤
    if session["state"] != "ready":
        return JSONResponse({**info, "reason": "no_ready_session"})
    # 005 讀不到目前設定(ollama.status 為 pending / unknown)時 tuning 是 null:contextLength 為 null(Q9)
    tuning = session["ollama"]["tuning"]
    context_length = tuning["contextLength"]["value"] if tuning is not None else None
    # info.x-recommendation-rule:讀得到 context 且小於建議下限時提醒
    should_warn = snippets.should_warn(context_length)
    # 讀不到不當成目錄是空的:`Catalog.list()` 轉成 502 或 504 的 `ApiError`,由全域處理器回應(plan.md Q11)
    catalog = await services.catalog.list()
    models = [item["name"] for item in catalog["items"]]
    # info.x-recommendation-rule:建議值依顯示記憶體估算,讀不到時用下限(FR-007、Q11)
    info["recommendedContextLength"] = snippets.recommended_context_length(catalog["vramBytes"])
    # info.x-reason-rule (2):模型目錄是空的,`contextLength` 照實回
    if not models:
        return JSONResponse({**info, "reason": "no_models", "contextLength": context_length, "shouldWarn": should_warn})
    return JSONResponse(
        {
            **info,
            "contextLength": context_length,
            "shouldWarn": should_warn,
            "models": models,
            "reserveTokens": snippets.reserve_tokens(context_length),
            "snippets": _snippets_of(state.public_ollama_port, models, context_length),
        }
    )
