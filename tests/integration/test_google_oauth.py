"""E9 Google OAuth 轉接層(testplan.md § 2.4;接縫:`GoogleOAuth` 的方法,token 端點是 `httpx.MockTransport`)。

測試不對 Google 發出任何請求;換 token 的案例一律注入假的 client 設定,CLI 隨附的 client secret 不進任何斷言或輸出。
"""

import asyncio
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from google.oauth2.credentials import Credentials

from cgb.adapters.errors import AdapterError
from cgb.adapters.google_oauth import GoogleOAuth

REDIRECT_URI = "https://sdk.cloud.google.com/applicationdefaultauthcode.html"
COLAB_SCOPE = "https://www.googleapis.com/auth/colaboratory"
TOKEN_URI = "https://oauth2.googleapis.com/token"
# 與 CLI 0.7.5 請求的 scope 相同(contracts/google-oauth.openapi.yaml § authorize 的 scope 說明)
ALL_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/cloud-platform",
    COLAB_SCOPE,
    "https://www.googleapis.com/auth/drive.file",
]
# 換 token 的案例用假的 installed 型 client 設定,不碰 CLI 隨附的 client secret
FAKE_CLIENT_CONFIG = {
    "installed": {
        "client_id": "cgb-test-client-id",
        "client_secret": "cgb-test-client-secret",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": TOKEN_URI,
        "redirect_uris": ["http://localhost"],
    }
}


@pytest.fixture
def dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """`CGB_COLAB_CONFIG_DIR`(Q87)與 `HOME` 都指到暫存資料夾;回傳 (授權檔資料夾, HOME)。"""
    config_dir = tmp_path / "data" / "colab-cli"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("CGB_COLAB_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("HOME", str(home))
    return config_dir, home


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


async def test_每次取得的授權網址都帶新的_PKCE_挑戰() -> None:
    """US1-OA-01:CLI 內建的 client 設定,呼叫兩次。"""
    oauth = GoogleOAuth()

    first = _query((await oauth.build_authorization_url()).url)
    second = _query((await oauth.build_authorization_url()).url)

    for query in (first, second):
        assert query.get("redirect_uri") == [REDIRECT_URI]
        assert query.get("code_challenge_method") == ["S256"]
        assert len(query.get("code_challenge", [""])[0]) == 43
        assert COLAB_SCOPE in query.get("scope", [""])[0].split(" ")
    assert first["state"] != second["state"]
    assert first["code_challenge"] != second["code_challenge"]


async def test_以授權碼換到的_token_存成_CLI_讀得到的授權檔(tmp_path: Path, dirs: tuple[Path, Path]) -> None:
    """US1-OA-02:假 token 端點回 200,以授權碼與同一次的 `code_verifier` 呼叫。"""
    config_dir, home = dirs
    received: list[dict[str, list[str]]] = []

    def token_endpoint(request: httpx.Request) -> httpx.Response:
        received.append(parse_qs(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "access_token": "cgb-test-access-token",
                "refresh_token": "cgb-test-refresh-token",
                "expires_in": 3599,
                "scope": " ".join(ALL_SCOPES),
                "token_type": "Bearer",
            },
        )

    oauth = GoogleOAuth(client_config=FAKE_CLIENT_CONFIG, transport=httpx.MockTransport(token_endpoint))
    flow = await oauth.build_authorization_url()

    await oauth.request_token(code="4/cgb-test-code", code_verifier=flow.code_verifier)

    # 則1:假端點收到 grant_type、code、code_verifier
    assert len(received) == 1
    assert received[0].get("grant_type") == ["authorization_code"]
    assert received[0].get("code") == ["4/cgb-test-code"]
    assert received[0].get("code_verifier") == [flow.code_verifier]
    # 則2:授權檔含 CLI 讀取所需的欄位,並以 CLI 讀取的同一個方法讀得到
    token_path = config_dir / "token.json"
    saved = json.loads(token_path.read_text(encoding="utf-8"))
    assert saved.get("refresh_token") == "cgb-test-refresh-token"
    assert saved.get("client_id") == "cgb-test-client-id"
    assert saved.get("client_secret") == "cgb-test-client-secret"
    assert saved.get("token_uri") == TOKEN_URI
    assert Credentials.from_authorized_user_file(str(token_path), ALL_SCOPES).refresh_token == "cgb-test-refresh-token"
    # 則3:授權檔只在 CGB_COLAB_CONFIG_DIR,不寫到 HOME 底下 CLI 的預設位置
    assert sorted(tmp_path.rglob("token.json")) == [token_path]
    assert not (home / ".config" / "colab-cli" / "token.json").exists()


async def _code_of_failed_request_token(oauth: GoogleOAuth) -> str | None:
    """送一次授權碼;丟出 `AdapterError` 就回它的代碼,沒有失敗回 None。"""
    flow = await oauth.build_authorization_url()
    try:
        await oauth.request_token(code="4/cgb-test-code", code_verifier=flow.code_verifier)
    except AdapterError as error:
        return error.code
    return None


async def test_token_端點拒絕時依_error_分出授權碼錯與設定錯(dirs: tuple[Path, Path]) -> None:
    """US1-OA-03:假端點依序回 400 invalid_grant、400 invalid_request、401 invalid_client,各呼叫一次。"""
    script = [
        (400, {"error": "invalid_grant", "error_description": "Bad Request"}),
        (400, {"error": "invalid_request", "error_description": "Missing required parameter"}),
        (401, {"error": "invalid_client", "error_description": "Unauthorized"}),
    ]

    def token_endpoint(request: httpx.Request) -> httpx.Response:
        status, body = script.pop(0)
        return httpx.Response(status, json=body)

    oauth = GoogleOAuth(client_config=FAKE_CLIENT_CONFIG, transport=httpx.MockTransport(token_endpoint))

    codes = [await _code_of_failed_request_token(oauth) for _ in range(3)]

    assert codes == ["OAUTH_INVALID_GRANT", "OAUTH_INVALID_REQUEST", "OAUTH_INVALID_CLIENT"]


async def test_沒拿到_refresh_token_或沒授予_colaboratory_時不存授權檔(tmp_path: Path, dirs: tuple[Path, Path]) -> None:
    """US1-OA-04:情況 A 回 200 但沒有 refresh_token;情況 B 回 200 但 scope 不含 colaboratory;各呼叫一次。"""
    without_colab = [scope for scope in ALL_SCOPES if scope != COLAB_SCOPE]
    script = [
        {"access_token": "cgb-test-access-token", "expires_in": 3599, "scope": " ".join(ALL_SCOPES), "token_type": "Bearer"},
        {
            "access_token": "cgb-test-access-token",
            "refresh_token": "cgb-test-refresh-token",
            "expires_in": 3599,
            "scope": " ".join(without_colab),
            "token_type": "Bearer",
        },
    ]

    def token_endpoint(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=script.pop(0))

    oauth = GoogleOAuth(client_config=FAKE_CLIENT_CONFIG, transport=httpx.MockTransport(token_endpoint))

    codes = [await _code_of_failed_request_token(oauth) for _ in range(2)]

    assert codes == ["OAUTH_BAD_RESPONSE", "OAUTH_SCOPE_NOT_GRANTED"]
    assert sorted(tmp_path.rglob("token.json")) == []


async def test_連不到_逾時或_Google_暫時故障時回對應的原因代碼(dirs: tuple[Path, Path]) -> None:
    """US1-OA-05:情況 A 連線被拒;情況 B 逾時(注入 0.3 秒);情況 C 回 503;各呼叫一次。"""

    async def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("[Errno 111] Connection refused", request=request)

    async def too_slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1.0)
        return httpx.Response(
            200,
            json={
                "access_token": "cgb-test-access-token",
                "refresh_token": "cgb-test-refresh-token",
                "expires_in": 3599,
                "scope": " ".join(ALL_SCOPES),
                "token_type": "Bearer",
            },
        )

    async def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    codes: list[str | None] = []
    for handler in (refused, too_slow, unavailable):
        oauth = GoogleOAuth(client_config=FAKE_CLIENT_CONFIG, transport=httpx.MockTransport(handler), timeout=0.3)
        flow = await oauth.build_authorization_url()
        try:
            await oauth.request_token(code="4/cgb-test-code", code_verifier=flow.code_verifier)
        except AdapterError as error:
            codes.append(error.code)
        except Exception as error:  # 要抓的錯:沒處理的例外讓 API 回 500 沒有原因
            codes.append(f"未處理的例外 {type(error).__name__}")
        else:
            codes.append(None)

    assert codes == ["OAUTH_UNREACHABLE", "OAUTH_TIMEOUT", "OAUTH_SERVER_ERROR"]
