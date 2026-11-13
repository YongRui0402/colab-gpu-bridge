"""跨端點驗收:真的 E2(api、services、domain、repos 與 SQLite)接真的 `RemoteOllama`(003 testplan.md § 2.3)。

遠端 Ollama 的 HTTP 換成 `httpx.MockTransport`(`/api/version` 一律回 200 讓工作階段開到就緒,`/api/tags` 照案例),
其他轉接層用替身(plan.md Q25)。
接縫:HTTP `/api/*`;斷言 MockTransport 丟出的原生 httpx 例外與各種回應經轉接層與服務兩層之後回的狀態碼與 `code`,
沒有任何一次是 500。
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx

from cgb.adapters.remote_ollama import RemoteOllama
from cgb.domain.errors import MESSAGES
from integration.test_api_downloads import downloadable
from integration.test_api_session import error_code, open_ready

Handler = Callable[[httpx.Request], httpx.Response]

QWEN_7B = "qwen2.5:7b"


class SwitchableOllama:
    """MockTransport 的 handler:`/api/version` 回 200,`/api/tags` 交給目前的 `tags`,其他路徑回 404。"""

    def __init__(self, tags: Handler) -> None:
        self.tags = tags

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.40.15"})
        if request.url.path == "/api/tags":
            return self.tags(request)
        return httpx.Response(404, json={"error": "404 page not found"})


@asynccontextmanager
async def ui_with_remote_ollama(make_app: Callable[..., Any], ollama: SwitchableOllama) -> AsyncIterator[httpx.AsyncClient]:
    """真的 `RemoteOllama`(對方是 MockTransport)接上真的 app;未處理的例外照 HTTP 500 回給測試。"""
    app_pair = make_app(remote_ollama=RemoteOllama(transport=httpx.MockTransport(ollama)))
    async with app_pair.ui.router.lifespan_context(app_pair.ui):
        transport = httpx.ASGITransport(app=app_pair.ui, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://cgb-ui.test") as client:
            yield client


def raising(error: Exception) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        raise error

    return handle


def replying(response: Callable[[], httpx.Response]) -> Handler:
    return lambda _: response()


# 讀模型清單的五種失敗(US1-AJ-01、US1-AJ-02 共用)與它們經 UI API 該回的狀態碼與 `code`
TAGS_FAILURES: dict[str, Handler] = {
    "A": raising(httpx.ConnectError("cgb-test 連不到")),
    "B": raising(httpx.ReadTimeout("cgb-test 逾時")),
    "C": replying(lambda: httpx.Response(500, json={"error": "boom"})),
    "D": replying(lambda: httpx.Response(200, text="<html>維護中</html>", headers={"Content-Type": "text/html"})),
    "E": replying(lambda: httpx.Response(200, json={"models": [{"name": "qwen2.5:latest"}]})),
}
EXPECTED_TAGS_FAILURES = {
    "A": (502, "OLLAMA_UNREACHABLE"),
    "B": (504, "OLLAMA_TIMEOUT"),
    "C": (502, "OLLAMA_BAD_RESPONSE"),
    "D": (502, "OLLAMA_BAD_RESPONSE"),
    "E": (502, "OLLAMA_BAD_RESPONSE"),
}


# ---- 003 US1-AJ-01


async def test_試算時讀不到執行環境上的模型清單_經兩層回合約的狀態碼_沒有_500(
    make_app: Callable[..., Any], fakes: Any
) -> None:
    # Arrange:工作階段就緒;遠端 Ollama 的 /api/tags 依情況失敗
    downloadable(fakes)
    ollama = SwitchableOllama(replying(lambda: httpx.Response(200, json={"models": []})))

    # Act
    results: dict[str, tuple[int, str | None]] = {}
    async with ui_with_remote_ollama(make_app, ollama) as client:
        await open_ready(client)
        for case, tags in TAGS_FAILURES.items():
            ollama.tags = tags
            response = await client.post("/api/downloads/estimate", json={"models": [QWEN_7B]})
            results[case] = (response.status_code, error_code(response))

    # Assert
    assert results == EXPECTED_TAGS_FAILURES


# ---- 003 US1-AJ-02


async def test_加入下載時讀不到執行環境上的模型清單_經兩層回合約的狀態碼_佇列沒有東西_沒有_500(
    make_app: Callable[..., Any], fakes: Any
) -> None:
    # Arrange:工作階段就緒;遠端 Ollama 的 /api/tags 依情況失敗
    downloadable(fakes)
    ollama = SwitchableOllama(replying(lambda: httpx.Response(200, json={"models": []})))

    # Act
    results: dict[str, tuple[int, str | None]] = {}
    jobs_after: dict[str, Any] = {}
    async with ui_with_remote_ollama(make_app, ollama) as client:
        await open_ready(client)
        for case, tags in TAGS_FAILURES.items():
            ollama.tags = tags
            response = await client.post("/api/downloads", json={"models": [QWEN_7B, "llama3.2"]})
            results[case] = (response.status_code, error_code(response))
            jobs_after[case] = (await client.get("/api/downloads")).json().get("jobs")

    # Assert
    assert results == EXPECTED_TAGS_FAILURES
    assert jobs_after == {case: [] for case in TAGS_FAILURES}


# ---- 003 US1-AJ-03

# 桌機 Ollama 0.32.15 `/api/tags` 的形狀(003 research.md R1),名稱帶版本
DESKTOP_SHAPED_TAGS = {
    "models": [
        {
            "name": "qwen2.5:latest",
            "model": "qwen2.5:latest",
            "modified_at": "2026-11-13T09:00:00Z",
            "size": 4683087332,
            "digest": "0" * 64,
            "details": {"format": "gguf"},
        }
    ]
}


async def test_沒寫版本的名稱和真的模型清單裡的_latest_判定為已下載_試算與加入都不取_manifest(
    make_app: Callable[..., Any], fakes: Any
) -> None:
    # Arrange:工作階段就緒;遠端 Ollama 的 /api/tags 回桌機 Ollama 形狀的 qwen2.5:latest
    downloadable(fakes)
    ollama = SwitchableOllama(replying(lambda: httpx.Response(200, json=DESKTOP_SHAPED_TAGS)))

    # Act
    async with ui_with_remote_ollama(make_app, ollama) as client:
        await open_ready(client)
        fakes.model_library.get_manifest.reset_calls()
        estimated = await client.post("/api/downloads/estimate", json={"models": ["qwen2.5"]})
        enqueued = await client.post("/api/downloads", json={"models": ["qwen2.5"]})
        jobs = (await client.get("/api/downloads")).json().get("jobs")

    # Assert
    assert (estimated.status_code, error_code(estimated), estimated.json().get("model")) == (
        409,
        "MODEL_ALREADY_DOWNLOADED",
        "qwen2.5:latest",
    )
    assert (enqueued.status_code, error_code(enqueued)) == (409, "MODEL_ALREADY_DOWNLOADED")
    assert jobs == []
    assert fakes.model_library.get_manifest.call_count == 0


# ---- 003 US1-AJ-04


async def test_連不到執行環境上的_Ollama_時回應只帶固定訊息_不帶例外文字與轉發位址(
    make_app: Callable[..., Any], fakes: Any
) -> None:
    # Arrange:工作階段就緒;遠端 Ollama 的 /api/tags 丟出帶底層細節的 ConnectError
    downloadable(fakes)
    ollama = SwitchableOllama(raising(httpx.ConnectError("cgb-test-底層細節 127.0.0.1:11435")))

    # Act
    async with ui_with_remote_ollama(make_app, ollama) as client:
        await open_ready(client)
        response = await client.post("/api/downloads/estimate", json={"models": [QWEN_7B]})

    # Assert
    assert response.json().get("message") == MESSAGES["OLLAMA_UNREACHABLE"]
    assert "cgb-test-底層細節" not in response.text
    assert "11435" not in response.text
    assert "model" not in response.json()
