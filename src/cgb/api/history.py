"""`/api/sessions`(contracts/ui.openapi.yaml § paths./sessions、components.schemas.SessionRecord)。"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cgb.domain.errors import ApiError
from cgb.domain.session_state import parse_iso, runtime_type_of

router = APIRouter()


def record_payload(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    # 運行時長:從開啟到結束(還沒結束時到現在),不另存(store.dbml 的說明)
    until = parse_iso(row["ended_at"]) if row["ended_at"] is not None else now
    return {
        "name": row["name"],
        "runtimeType": runtime_type_of(row),
        "state": row["state"],
        "endReason": row["end_reason"],
        "reasonCode": row["reason_code"],
        "openedAt": row["opened_at"],
        "readyAt": row["ready_at"],
        "endedAt": row["ended_at"],
        "durationSeconds": max(int((until - parse_iso(row["opened_at"])).total_seconds()), 0),
    }


@router.get("/sessions")
async def list_session_history(request: Request) -> JSONResponse:
    now = request.app.state.cgb.clock.now()
    rows = request.app.state.services.sessions_repo.history()
    return JSONResponse({"items": [record_payload(row, now) for row in rows], "hasMore": False})


@router.get("/sessions/{name}")
async def get_session_record(name: str, request: Request) -> JSONResponse:
    repo = request.app.state.services.sessions_repo
    row = repo.get(name)
    if row is None:
        raise ApiError(404, "SESSION_NOT_FOUND")
    transitions = [
        {"at": t["at"], "state": t["state"], "step": t["step"], "endReason": t["end_reason"], "reasonCode": t["reason_code"]}
        for t in repo.transitions(name)
    ]
    return JSONResponse({**record_payload(row, request.app.state.cgb.clock.now()), "transitions": transitions})
