"""跨端點驗收:真的 E2(api、services、domain、repos 與 SQLite)接真的 `ModelLibrary`(testplan.md § 2.3、§ 3.3)。

ollama.com 與 registry.ollama.ai 換成 `httpx.MockTransport`(plan.md Q4),其他轉接層用替身;逾時縮短成 0.5 秒。
接縫:HTTP `/api/*`;斷言 MockTransport 丟出的原生 httpx 例外與各狀態碼經兩層之後回的狀態碼與 `code`,沒有任何一次是 500。
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx

from cgb.adapters.model_library import ModelLibrary
from cgb.domain.errors import MESSAGES
from integration.test_api_session import error_code
from integration.test_model_library import html

Handler = Callable[[httpx.Request], httpx.Response]

SHORT_TIMEOUT = 0.5


@asynccontextmanager
async def ui_with_library(make_app: Callable[..., Any], handler: Handler) -> AsyncIterator[httpx.AsyncClient]:
    """真的 `ModelLibrary`(對方是 MockTransport)接上真的 app;未處理的例外照 HTTP 500 回給測試。"""
    library = ModelLibrary(transport=httpx.MockTransport(handler), request_timeout=SHORT_TIMEOUT)
    app_pair = make_app(model_library=library)
    async with app_pair.ui.router.lifespan_context(app_pair.ui):
        transport = httpx.ASGITransport(app=app_pair.ui, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://cgb-ui.test") as client:
            yield client


def raising(error: Exception) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        raise error

    return handle


def replying(response: httpx.Response) -> Handler:
    return lambda _: response


MAINTENANCE_PAGE = "<!DOCTYPE html><html><body><h1>維護中</h1></body></html>"


# ---------------------------------------------------------------- US1-AJ-01


async def test_搜尋時模型庫的各種失敗經_UI_API_回合約的狀態碼_沒有_500(make_app: Callable[..., Any]) -> None:
    # Arrange:沒有開工作階段;ollama.com 依情況失敗
    cases = {
        "A": raising(httpx.ConnectError("cgb-test 連不到")),
        "B": raising(httpx.ReadTimeout("cgb-test 逾時")),
        "C": raising(httpx.RemoteProtocolError("cgb-test 中斷")),
        "D": replying(html("Service Unavailable", status=503)),
        "E": replying(html(MAINTENANCE_PAGE)),
    }

    # Act
    results: dict[str, tuple[int, str | None, str]] = {}
    for case, handler in cases.items():
        async with ui_with_library(make_app, handler) as client:
            response = await client.get("/api/library/search", params={"q": "qwen2.5"})
        results[case] = (response.status_code, error_code(response), response.headers.get("content-type", ""))

    # Assert
    assert results["A"][:2] == (502, "LIBRARY_UNREACHABLE")
    assert results["B"][:2] == (504, "LIBRARY_TIMEOUT")
    assert results["C"][:2] == (502, "LIBRARY_UNREACHABLE")
    assert results["D"][:2] == (502, "LIBRARY_SERVER_ERROR")
    assert results["E"][:2] == (502, "LIBRARY_BAD_RESPONSE")
    assert all(content_type.startswith("application/json") for _, _, content_type in results.values())
    assert 500 not in [status for status, _, _ in results.values()]


# ---------------------------------------------------------------- US1-AJ-02


async def test_版本清單時模型庫的各種失敗經_UI_API_回合約的狀態碼_沒有_500(make_app: Callable[..., Any]) -> None:
    # Arrange:沒有開工作階段;ollama.com 的版本頁依情況失敗
    no_tag_links = '<!DOCTYPE html><html><body><a href="/library/qwen2.5">qwen2.5</a></body></html>'
    cases = {
        "A": raising(httpx.ConnectError("cgb-test 連不到")),
        "B": raising(httpx.ConnectTimeout("cgb-test 逾時")),
        "C": replying(html("Not Found", status=404)),
        "D": replying(html("Bad Gateway", status=502)),
        "E": replying(html(no_tag_links)),
        "F": replying(httpx.Response(301, headers={"Location": "https://ollama.com/library/qwen2.5"})),
    }

    # Act
    results: dict[str, tuple[int, str | None]] = {}
    for case, handler in cases.items():
        async with ui_with_library(make_app, handler) as client:
            response = await client.get("/api/library/models/qwen2.5/tags")
        results[case] = (response.status_code, error_code(response))

    # Assert
    assert results["A"] == (502, "LIBRARY_UNREACHABLE")
    assert results["B"] == (504, "LIBRARY_TIMEOUT")
    assert results["C"] == (404, "LIBRARY_NOT_FOUND")
    assert results["D"] == (502, "LIBRARY_SERVER_ERROR")
    assert results["E"] == (502, "LIBRARY_BAD_RESPONSE")
    assert results["F"] == (502, "LIBRARY_BAD_RESPONSE")
    assert 500 not in [status for status, _ in results.values()]


# ---------------------------------------------------------------- US1-AJ-03


async def test_搜尋連不到時回應不帶底層例外的文字或網址(make_app: Callable[..., Any]) -> None:
    # Arrange:沒有開工作階段;httpx 例外的文字帶 Errno 與網址
    handler = raising(httpx.ConnectError("[Errno -2] Name or service not known: https://ollama.com/search?q=qwen2.5"))

    # Act
    async with ui_with_library(make_app, handler) as client:
        response = await client.get("/api/library/search", params={"q": "qwen2.5"})

    # Assert
    assert (response.status_code, error_code(response)) == (502, "LIBRARY_UNREACHABLE")
    assert response.json().get("message") == MESSAGES["LIBRARY_UNREACHABLE"]
    assert "ollama.com" not in response.text
    assert "Errno" not in response.text
