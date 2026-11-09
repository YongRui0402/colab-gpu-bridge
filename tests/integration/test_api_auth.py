"""E2 後端 UI API:Colab 帳號登入(testplan.md § 2.1,`/api/auth` › 取得授權連結、送出授權碼;FR-008)。

接縫:HTTP `/api/*` 與 SSE `/api/events`;Google OAuth 轉接層用 `FakeGoogleOAuth`。
"""

import asyncio
import itertools
import stat
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.app import AppPair
from integration.test_api_recovery import running

from integration.test_api_session import ColabWorld, error_code, ui_client  # noqa: F401(ui_client 是 fixture)

AUTH_URL_PREFIX = "https://accounts.google.com/o/oauth2/auth?"


def google_flows(fakes: Any) -> None:
    """每次取得授權網址都是新的一組 state 與 code_verifier(照 E9 `AuthorizationRequest` 的形狀)。"""
    counter = itertools.count(1)

    def build(*args: Any, **kwargs: Any) -> SimpleNamespace:
        n = next(counter)
        return SimpleNamespace(
            url=f"{AUTH_URL_PREFIX}response_type=code&state=cgb-test-state-{n}",
            state=f"cgb-test-state-{n}",
            code_verifier=f"cgb-test-verifier-{n:040d}",
        )

    fakes.google_oauth.build_authorization_url.side_effect(build)


# ---------------------------------------------------------------- US1-API-30


async def test_每次取得授權連結都是新的流程_舊的流程代號失效(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    google_flows(fakes)
    fakes.google_oauth.request_token.returns("/tmp/cgb-test-not-written/token.json")

    # Act
    first = await ui_client.post("/api/auth/authorizations")
    second = await ui_client.post("/api/auth/authorizations")
    first_flow = first.json().get("flowId") if first.status_code == 201 else None
    stale = await ui_client.post(f"/api/auth/authorizations/{first_flow}/code", json={"code": "4/cgb-test-code"})

    # Assert
    assert (first.status_code, second.status_code) == (201, 201)
    assert all(r.json().get("authorizationUrl", "").startswith(AUTH_URL_PREFIX) for r in (first, second))
    assert first.json().get("flowId") != second.json().get("flowId")
    assert (stale.status_code, error_code(stale)) == (404, "AUTH_LINK_EXPIRED")


# ---------------------------------------------------------------- US1-API-32


async def test_授權碼錯誤時回原因_同一個流程可以再送一次(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    google_flows(fakes)
    fakes.google_oauth.request_token.then(AdapterError("OAUTH_INVALID_GRANT", "invalid_grant"))
    fakes.google_oauth.request_token.returns("/tmp/cgb-test-not-written/token.json")
    flow_id = (await ui_client.post("/api/auth/authorizations")).json().get("flowId")

    # Act
    wrong = await ui_client.post(f"/api/auth/authorizations/{flow_id}/code", json={"code": "4/cgb-test-wrong"})
    right = await ui_client.post(f"/api/auth/authorizations/{flow_id}/code", json={"code": "4/cgb-test-code"})

    # Assert
    assert (wrong.status_code, error_code(wrong)) == (400, "OAUTH_INVALID_GRANT")
    assert wrong.json().get("message") if wrong.status_code == 400 else False
    assert (right.status_code, right.json().get("state") if right.status_code == 200 else None) == (200, "logged_in")


# ---------------------------------------------------------------- US1-API-33


async def test_後端重啟後舊的授權連結失效(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    google_flows(fakes)
    fakes.google_oauth.request_token.returns("/tmp/cgb-test-not-written/token.json")
    async with running(make_app()) as client:
        flow_id = (await client.post("/api/auth/authorizations")).json().get("flowId")

    # Act
    async with running(make_app()) as client:
        response = await client.post(f"/api/auth/authorizations/{flow_id}/code", json={"code": "4/cgb-test-code"})

    # Assert
    assert (response.status_code, error_code(response)) == (404, "AUTH_LINK_EXPIRED")
    assert fakes.google_oauth.request_token.call_count == 0


# ---------------------------------------------------------------- US1-API-31


async def test_送出授權碼時去掉前後空白_登入後推送登入狀態(
    live_servers: Any, fakes: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange:替身照 E9 轉接層的行為,在 $CGB_COLAB_CONFIG_DIR 寫出 0600 的 token.json 並回傳路徑
    from integration.test_api_events import sse_events

    config_dir = tmp_path / "colab-cli"
    monkeypatch.setenv("CGB_COLAB_CONFIG_DIR", str(config_dir))
    ColabWorld(fakes)
    google_flows(fakes)

    def write_token(*args: Any, **kwargs: Any) -> Path:
        config_dir.mkdir(mode=0o700, exist_ok=True)
        token = config_dir / "token.json"
        token.touch(mode=0o600)
        token.write_text('{"refresh_token": "cgb-test-refresh"}', encoding="utf-8")
        return token

    fakes.google_oauth.request_token.side_effect(write_token)
    auth_events: list[dict[str, Any]] = []

    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        flow_id = (await client.post("/api/auth/authorizations")).json().get("flowId")
        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)

            # Act
            response = await client.post(f"/api/auth/authorizations/{flow_id}/code", json={"code": "  4/cgb-test-code  "})

            async def collect() -> None:
                async for event, payload in events:
                    if event == "auth.updated":
                        auth_events.append(payload.get("auth", {}))
                        if auth_events[-1].get("state") == "logged_in":
                            return

            try:
                await asyncio.wait_for(collect(), 2.0)
            except TimeoutError:
                pass

    # Assert
    token = config_dir / "token.json"
    assert (response.status_code, response.json().get("state")) == (200, "logged_in")
    assert fakes.google_oauth.request_token.last_call.kwargs.get("code") == "4/cgb-test-code"
    assert token.exists() and stat.S_IMODE(token.stat().st_mode) == 0o600
    assert [e.get("state") for e in auth_events][-1:] == ["logged_in"]
