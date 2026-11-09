"""`/api/auth`(contracts/ui.openapi.yaml § paths./auth)。"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from cgb.api._body import read_json
from cgb.domain.errors import ApiError

router = APIRouter()


@router.get("/auth")
async def get_auth_status(request: Request) -> JSONResponse:
    return JSONResponse(await request.app.state.services.auth.status())


@router.post("/auth/authorizations")
async def start_authorization(request: Request) -> JSONResponse:
    return JSONResponse(await request.app.state.services.auth.start_authorization(), status_code=201)


@router.post("/auth/authorizations/{flow_id}/code")
async def submit_authorization_code(flow_id: str, request: Request) -> JSONResponse:
    body = await read_json(request)
    if not isinstance(body, dict) or not isinstance(body.get("code"), str):
        raise ApiError(400, "INVALID_REQUEST_BODY")
    return JSONResponse(await request.app.state.services.auth.submit_code(flow_id, body["code"]))
