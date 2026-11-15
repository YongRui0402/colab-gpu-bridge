"""E2 後端 UI API:連線設定資訊(testplan.md § 2.2,`GET /api/connect`)。

接縫:HTTP `GET /api/connect`(ASGI transport),五個轉接層用替身(testplan.md § 接縫的取捨)。
預設資料:工作階段就緒(T4、套用 context 4096)、模型目錄有 `qwen2.5-coder:7b` 與 `qwen2.5:3b`、`CGB_PUBLIC_OLLAMA_PORT` 為 11436。
"""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx

from cgb.app import AppPair
from conftest import FakeClock
from integration.test_api_models import QWEN_7B_BYTES, QWEN_SMALL_BYTES, set_tags, tag
from integration.test_api_session import ColabWorld, error_code, get_session, open_ready, ui_client  # noqa: F401(ui_client 是 fixture)

CODER_7B = "qwen2.5-coder:7b"
QWEN_3B = "qwen2.5:3b"


@asynccontextmanager
async def ui_of(pair: AppPair) -> AsyncIterator[httpx.AsyncClient]:
    """自己組的 app(帶不同的設定)用的 UI 用戶端。"""
    async with pair.ui.router.lifespan_context(pair.ui):
        transport = httpx.ASGITransport(app=pair.ui, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://cgb-ui.test") as client:
            yield client


def set_default_catalog(fakes: Any) -> None:
    set_tags(fakes, tag(CODER_7B, QWEN_7B_BYTES), tag(QWEN_3B, QWEN_SMALL_BYTES))


# ---------------------------------------------------------------- US1-API-03


async def test_就緒時回目前套用的_context_與模型清單並附_opencode_片段(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    set_default_catalog(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.get("/api/connect")

    # Assert
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["ollamaPort"], body["basePath"], body["reason"]) == (11436, "/v1", None)
    assert (body["models"], body["contextLength"]) == ([CODER_7B, QWEN_3B], 4096)
    opencode = json.loads(body["snippets"]["opencode"])
    assert opencode["provider"]["cgb"]["models"][CODER_7B]["limit"]["context"] == 4096


# ---------------------------------------------------------------- US1-API-04


async def test_沒設對外_port_時用容器內的_port(make_app: Callable[..., AppPair], fakes: Any) -> None:
    # Arrange:等於沒設 CGB_PUBLIC_OLLAMA_PORT、容器內 CGB_OLLAMA_PORT 是 11434
    ColabWorld(fakes)
    set_default_catalog(fakes)
    async with ui_of(make_app(public_ollama_port=None, ollama_port=11434)) as ui:
        await open_ready(ui)

        # Act
        response = await ui.get("/api/connect")

    # Assert
    assert response.status_code == 200, response.text
    assert response.json()["ollamaPort"] == 11434


# ---------------------------------------------------------------- US1-API-05


async def test_沒有開工作階段時回_200_並說明沒有就緒的工作階段(ui_client: httpx.AsyncClient) -> None:
    # Act
    response = await ui_client.get("/api/connect")

    # Assert
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["reason"], body["snippets"]) == ("no_ready_session", None)


# ---------------------------------------------------------------- US1-API-06


async def test_模型目錄是空的時回_200_並說明沒有模型(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    set_tags(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.get("/api/connect")

    # Assert
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["reason"], body["models"], body["snippets"]) == ("no_models", [], None)


# ---------------------------------------------------------------- US1-API-07


async def test_讀不到模型目錄時回_502_不當成目錄是空的(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    fakes.remote_ollama.list_local_models.raises("OLLAMA_UNREACHABLE", "連不到")

    # Act
    response = await ui_client.get("/api/connect")

    # Assert
    assert (response.status_code, error_code(response)) == (502, "OLLAMA_UNREACHABLE")


# ---------------------------------------------------------------- US1-API-08


async def test_讀連線資訊不重設閒置計時(ui_client: httpx.AsyncClient, fakes: Any, fake_clock: FakeClock) -> None:
    # Arrange:工作階段就緒,閒置計時的最後請求時間是 T
    ColabWorld(fakes)
    set_default_catalog(fakes)
    await open_ready(ui_client)
    last_request_at = (await get_session(ui_client))["idle"]["lastRequestAt"]

    # Act:T+30 秒讀連線資訊
    fake_clock.advance(30)
    response = await ui_client.get("/api/connect")

    # Assert
    assert response.status_code == 200, response.text
    assert (await get_session(ui_client))["idle"]["lastRequestAt"] == last_request_at


# ---------------------------------------------------------------- US1-API-09


async def test_回應與片段不含轉發位址與機密_片段的主機都是佔位(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:通道的 baseUrl 是 http://127.0.0.1:49123
    world = ColabWorld(fakes)
    set_default_catalog(fakes)
    opened = world._open_tunnel
    fakes.tunnel.open_tunnel.side_effect(lambda *a, **k: {**opened(*a, **k), "baseUrl": "http://127.0.0.1:49123"})
    await open_ready(ui_client)

    # Act
    response = await ui_client.get("/api/connect")

    # Assert
    assert response.status_code == 200, response.text
    body = response.json()
    snippets = body["snippets"]
    pi_models = json.loads(snippets["piModels"])
    hosts = {
        "opencode": json.loads(snippets["opencode"])["provider"]["cgb"]["options"]["baseURL"],
        "piModels": pi_models.get("providers", {}).get("cgb", {}).get("baseUrl"),
    }
    assert hosts == {"opencode": "http://{{host}}:11436/v1", "piModels": "http://{{host}}:11436/v1"}
    forbidden = ["49123", "127.0.0.1", "access_token", "refresh_token", "authorization"]
    assert [word for word in forbidden if word in response.text.lower()] == []


# ---------------------------------------------------------------- US2-API-03


async def test_就緒時附_pi_的_models_與_settings_片段並依套用的_context_算預留(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    set_default_catalog(fakes)
    await open_ready(ui_client)

    # Act
    response = await ui_client.get("/api/connect")

    # Assert
    assert response.status_code == 200, response.text
    body = response.json()
    pi_models = json.loads(body["snippets"]["piModels"])
    assert pi_models["providers"]["cgb"]["models"][0]["contextWindow"] == 4096
    assert json.loads(body["snippets"]["piSettings"]) == {"compaction": {"reserveTokens": 1024}}
    assert body["reserveTokens"] == 1024
