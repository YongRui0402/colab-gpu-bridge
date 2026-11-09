"""Colab 帳號的登入狀態(FR-008;contracts/ui.openapi.yaml § AuthStatus)。

以 Colab CLI 能否讀到用量判斷(contracts/colab-cli.openapi.yaml § getUsage):成功即已登入,`AUTH_REQUIRED` 即未登入,
其他失敗為確認不了。最後一次判斷的結果留在記憶體;其他操作碰到 `AUTH_REQUIRED` 時也更新它。
"""

import secrets
from collections.abc import Callable
from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.errors import ApiError, oauth_error
from cgb.domain.session_state import iso


class AuthService:
    def __init__(self, state: Any) -> None:
        self._state = state
        self._status: dict[str, Any] | None = None
        # 登入狀態每次判斷之後呼叫(推送 auth.updated 用)
        self.listeners: list[Callable[[dict[str, Any]], None]] = []
        # 同一時間只有最新的一次授權流程有效;`code_verifier` 只放記憶體,後端重啟就失效(Q17)
        self._flow: dict[str, str] | None = None

    def _set(self, state: str, reason_code: str | None = None) -> dict[str, Any]:
        self._status = {
            "state": state,
            "checkedAt": iso(self._state.clock.now()),
            "reasonCode": reason_code,
            "message": None,
        }
        for listener in list(self.listeners):
            listener(self._status)
        return self._status

    def mark_logged_out(self) -> None:
        self._set("logged_out", "AUTH_REQUIRED")

    async def check(self) -> dict[str, Any]:
        try:
            await self._state.colab.get_usage()
        except AdapterError as error:
            if error.code == "AUTH_REQUIRED":
                return self._set("logged_out", "AUTH_REQUIRED")
            return self._set("unknown", error.code)
        return self._set("logged_in")

    async def status(self) -> dict[str, Any]:
        if self._status is None:
            return await self.check()
        return self._status

    async def start_authorization(self) -> dict[str, Any]:
        request = await self._state.google_oauth.build_authorization_url()
        flow_id = secrets.token_urlsafe(24)
        self._flow = {"flowId": flow_id, "codeVerifier": request.code_verifier}
        return {"flowId": flow_id, "authorizationUrl": request.url, "createdAt": iso(self._state.clock.now())}

    async def submit_code(self, flow_id: str, code: str) -> dict[str, Any]:
        flow = self._flow
        if flow is None or flow["flowId"] != flow_id:
            # Q46、Q50:已被較新的流程取代、已用過,或後端重啟後遺失
            raise ApiError(404, "AUTH_LINK_EXPIRED")
        try:
            # 貼上時多帶的空白會讓 Google 回 invalid_grant
            await self._state.google_oauth.request_token(code=code.strip(), code_verifier=flow["codeVerifier"])
        except AdapterError as error:
            # 換 token 失敗時流程代號仍然有效,使用者可以用同一個連結再送一次
            raise oauth_error(error.code) from None
        self._flow = None
        return self._set("logged_in")
