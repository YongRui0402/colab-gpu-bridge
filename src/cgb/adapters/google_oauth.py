"""Google OAuth 轉接層(`contracts/google-oauth.openapi.yaml`;research.md R2)。

與 google-colab-cli 0.7.5 相同的「複製貼上」授權碼流程:組出授權網址交給 UI,
以使用者貼回的授權碼換 token,存成 CLI 讀得到的 `token.json`。
client 設定取自 CLI 隨附的 `colab_cli/oauth_config.json`,只在程式裡使用,不印出、不寫進紀錄。
"""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path
from typing import Any

import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from cgb.adapters.errors import AdapterError

COLAB_SCOPE = "https://www.googleapis.com/auth/colaboratory"
# 與 CLI 0.7.5 `colab_cli/auth.py` 的 PUBLIC_SCOPES、REMOTE_REDIRECT_URI 相同
SCOPES = (
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/cloud-platform",
    COLAB_SCOPE,
    "https://www.googleapis.com/auth/drive.file",
)
REDIRECT_URI = "https://sdk.cloud.google.com/applicationdefaultauthcode.html"

# token 端點 400/401 的 `OAuthError.error` → 本系統的原因代碼(contracts § paths./token.post 的 x-error-codes)
_OAUTH_ERROR_CODES = {
    "invalid_grant": "OAUTH_INVALID_GRANT",
    "invalid_request": "OAUTH_INVALID_REQUEST",
    "unsupported_grant_type": "OAUTH_UNSUPPORTED_GRANT_TYPE",
    "unauthorized_client": "OAUTH_UNAUTHORIZED_CLIENT",
    "invalid_scope": "OAUTH_INVALID_SCOPE",
    "invalid_client": "OAUTH_INVALID_CLIENT",
}


@dataclass(frozen=True)
class AuthorizationRequest:
    """一次授權流程:交給 UI 的網址,與換 token 時要送回的 `code_verifier`(Q17:只放記憶體)。"""

    url: str
    state: str
    code_verifier: str


def _cli_client_config() -> dict[str, Any]:
    return json.loads(resources.files("colab_cli").joinpath("oauth_config.json").read_text(encoding="utf-8"))


def _save_token_file(credentials: Credentials) -> Path:
    """寫到 `$CGB_COLAB_CONFIG_DIR/token.json`(Q87),只有擁有者讀寫。"""
    config_dir = Path(os.environ["CGB_COLAB_CONFIG_DIR"])
    config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    token_path = config_dir / "token.json"
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as token_file:
        token_file.write(credentials.to_json())
    return token_path


class GoogleOAuth:
    def __init__(
        self,
        *,
        client_config: dict[str, Any] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._timeout = timeout
        self._transport = transport
        self._client_config = client_config if client_config is not None else _cli_client_config()

    async def build_authorization_url(self) -> AuthorizationRequest:
        # 每次一個新的 flow:新的 state 與 code_verifier(PKCE S256 由 google-auth-oauthlib 產生)
        flow = InstalledAppFlow.from_client_config(self._client_config, list(SCOPES))
        flow.redirect_uri = REDIRECT_URI
        url, state = flow.authorization_url(prompt="consent", token_usage="remote")
        return AuthorizationRequest(url=url, state=state, code_verifier=flow.code_verifier)

    async def request_token(self, code: str, code_verifier: str) -> Path:
        """以授權碼與同一次流程的 `code_verifier` 換 token,存成 `$CGB_COLAB_CONFIG_DIR/token.json`(Q87)。"""
        client = self._client_config["installed"]
        response = await self._post_token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "redirect_uri": REDIRECT_URI,
                "code_verifier": code_verifier,
            }
        )
        body = response.json()
        if not body.get("refresh_token"):
            # 沒有 refresh token,access token 一小時後過期 CLI 就無法更新,不存
            raise AdapterError("OAUTH_BAD_RESPONSE", "Google 的回應沒有 refresh token")
        if COLAB_SCOPE not in body.get("scope", "").split():
            raise AdapterError("OAUTH_SCOPE_NOT_GRANTED", "沒有授予 Colab 權限(同意畫面取消勾選了 colaboratory)")
        # 與 CLI 自己登入時寫出的格式相同(`Credentials.to_json()`);expiry 是 naive UTC
        credentials = Credentials(
            token=body["access_token"],
            refresh_token=body["refresh_token"],
            token_uri=client["token_uri"],
            client_id=client["client_id"],
            client_secret=client["client_secret"],
            scopes=body.get("scope", "").split(),
            expiry=datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=int(body["expires_in"])),
        )
        return _save_token_file(credentials)

    async def _post_token_request(self, form: dict[str, str]) -> httpx.Response:
        """送到 token 端點;沒有 HTTP 回應(連不到、逾時)與非 200 的回應都歸成 `OAUTH_` 代碼。"""
        try:
            async with asyncio.timeout(self._timeout), httpx.AsyncClient(
                transport=self._transport, timeout=self._timeout
            ) as http:
                response = await http.post(self._client_config["installed"]["token_uri"], data=form)
        except (TimeoutError, httpx.TimeoutException) as error:
            raise AdapterError("OAUTH_TIMEOUT", f"{self._timeout:g} 秒內沒有收到 Google 的回應") from error
        except httpx.TransportError as error:
            raise AdapterError("OAUTH_UNREACHABLE", f"連不到 Google token 端點:{type(error).__name__}") from error
        if response.status_code >= 500:
            raise AdapterError("OAUTH_SERVER_ERROR", f"Google 暫時無法處理(HTTP {response.status_code})")
        if response.status_code >= 400:
            error = response.json().get("error") if response.status_code in (400, 401) else None
            if error in _OAUTH_ERROR_CODES:
                raise AdapterError(_OAUTH_ERROR_CODES[error], f"Google 拒絕換 token:{error}")
            raise AdapterError("OAUTH_BAD_RESPONSE", "換 token 失敗")
        return response
