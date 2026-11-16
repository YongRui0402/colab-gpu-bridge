"""E2 後端 UI API:模型目錄讀不到遠端 Ollama 時的錯誤(testplan.md § 2.1,`GET /api/models`、`POST /api/models/preload`、`GET /api/connect`)。

接縫:HTTP `/api/*`(ASGI transport;要讀 SSE 的案例用測試行程內 uvicorn 的 `live_servers`),五個轉接層用替身(testplan.md § 接縫的取捨)。
「遠端 Ollama 的 tags、ps」是 `FakeRemoteOllama.list_local_models`、`list_loaded_models` 的回傳或丟出的 `AdapterError`。
"""

import asyncio
import contextlib
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from integration.test_api_events import sse_events
from integration.test_api_models import (
    QWEN_7B,
    QWEN_7B_BYTES,
    QWEN_SMALL,
    QWEN_SMALL_BYTES,
    by_name,
    next_event,
    set_loaded,
    set_tags,
    tag,
)
from integration.test_api_session import ColabWorld, error_code, get_session, open_ready, ui_client  # noqa: F401(ui_client 是 fixture)

# 三種失敗代碼與各自對應的狀態碼(contracts/ui.openapi.yaml § info.x-catalog-failure-rule 第 3 點)
OLLAMA_FAILURES = [("OLLAMA_UNREACHABLE", 502), ("OLLAMA_BAD_RESPONSE", 502), ("OLLAMA_TIMEOUT", 504)]
# contracts/ui.openapi.yaml § info.x-ollama-error-message:三個代碼固定的說明(照規格原句寫,不從程式碼的 `MESSAGES` 取)
OLLAMA_MESSAGES = {
    "OLLAMA_UNREACHABLE": "連不到執行環境上的 Ollama,請確認工作階段仍在運作後再試。",
    "OLLAMA_BAD_RESPONSE": "執行環境上的 Ollama 回應無法解讀,請稍後再試。",
    "OLLAMA_TIMEOUT": "執行環境上的 Ollama 在時限內沒有回應,請稍後再試。",
}
# 替身丟錯時帶的底層訊息:含 traceback 與本機轉發的位址,不能出現在給使用者的訊息裡
HF_MODEL = "hf.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M"
LEAKY_MESSAGE = "Traceback (most recent call last): httpx.ConnectError 127.0.0.1:41234"


# ---------------------------------------------------------------- US1-API-01


@pytest.mark.parametrize(("code", "status"), OLLAMA_FAILURES)
async def test_讀不到已下載清單時列目錄回_502_或_504_與對應代碼(
    ui_client: httpx.AsyncClient, fakes: Any, code: str, status: int
) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_loaded(fakes)
    fakes.remote_ollama.list_local_models.raises(code)

    # Act
    response = await ui_client.get("/api/models")

    # Assert
    assert (response.status_code, error_code(response)) == (status, code)


# ---------------------------------------------------------------- US1-API-02


@pytest.mark.parametrize("code", OLLAMA_MESSAGES)
async def test_列目錄失敗的訊息是固定的繁體中文說明_不帶底層例外(ui_client: httpx.AsyncClient, fakes: Any, code: str) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_loaded(fakes)
    fakes.remote_ollama.list_local_models.raises(code, LEAKY_MESSAGE)

    # Act
    response = await ui_client.get("/api/models")

    # Assert
    assert response.json()["message"] == OLLAMA_MESSAGES[code]
    assert "Traceback" not in response.text
    assert "127.0.0.1" not in response.text


# ---------------------------------------------------------------- US1-API-03


@pytest.mark.parametrize(("code", "status"), OLLAMA_FAILURES)
async def test_讀不到已載入清單時列目錄也回_502_或_504_不回半套目錄(
    ui_client: httpx.AsyncClient, fakes: Any, code: str, status: int
) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES), tag(QWEN_7B, QWEN_7B_BYTES))
    fakes.remote_ollama.list_loaded_models.raises(code)

    # Act
    response = await ui_client.get("/api/models")

    # Assert
    assert (response.status_code, error_code(response)) == (status, code)
    assert set(response.json()) == {"code", "message"}


# ---------------------------------------------------------------- US1-API-04


async def test_兩份清單都讀不到時以先失敗的那一份為準(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    fakes.remote_ollama.list_local_models.raises("OLLAMA_UNREACHABLE")
    fakes.remote_ollama.list_loaded_models.raises("OLLAMA_TIMEOUT")

    # Act
    response = await ui_client.get("/api/models")

    # Assert
    assert (response.status_code, error_code(response)) == (502, "OLLAMA_UNREACHABLE")


# ---------------------------------------------------------------- US1-API-05


async def test_讀不到顯示記憶體不算失敗_目錄照回_200_顯示記憶體是_null(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes)
    fakes.colab.probe_resources.raises("COLAB_TIMEOUT")

    # Act
    response = await ui_client.get("/api/models")

    # Assert
    assert response.status_code == 200
    assert response.json()["vramBytes"] is None
    assert response.json()["items"][0]["name"] == QWEN_7B
    assert response.json()["items"][0]["mayNotFit"] is None


# ---------------------------------------------------------------- US1-API-06


async def test_沒有就緒的工作階段時列目錄回_503_不去讀遠端(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段,遠端兩份清單就算被讀也會丟 `OLLAMA_UNREACHABLE`
    ColabWorld(fakes)
    remote = fakes.remote_ollama
    remote.list_local_models.raises("OLLAMA_UNREACHABLE")
    remote.list_loaded_models.raises("OLLAMA_UNREACHABLE")

    # Act
    response = await ui_client.get("/api/models")

    # Assert
    assert (response.status_code, error_code(response)) == (503, "NO_READY_SESSION")
    assert remote.list_local_models.call_count == 0


# ---------------------------------------------------------------- US1-API-07


async def test_遠端恢復後下一次列目錄照常成功_不重開工作階段(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:第一次讀 tags 丟 `OLLAMA_UNREACHABLE`,之後照常
    ColabWorld(fakes)
    name = (await open_ready(ui_client))["name"]
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES), tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes, QWEN_SMALL)
    fakes.remote_ollama.list_local_models.then(AdapterError("OLLAMA_UNREACHABLE", "連不到"))

    # Act
    first = await ui_client.get("/api/models")
    second = await ui_client.get("/api/models")
    session = await get_session(ui_client)

    # Assert
    assert (first.status_code, error_code(first)) == (502, "OLLAMA_UNREACHABLE")
    assert second.status_code == 200
    items = {item["name"]: item for item in second.json()["items"]}
    assert set(items) == {QWEN_SMALL, QWEN_7B}
    assert items[QWEN_SMALL]["loaded"] is True
    assert (session["state"], session["name"]) == ("ready", name)


# ---------------------------------------------------------------- US1-API-08


async def test_確認目錄失敗的預先載入不受理_不改任何模型的狀態_也不推送(live_servers: Any, fakes: Any) -> None:
    # Arrange:`hf.co/…` 先預先載入失敗(`OLLAMA_SERVER_ERROR`),`/api/events` 連著
    ColabWorld(fakes)
    remote = fakes.remote_ollama
    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as client:
        await open_ready(client)
        set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES), tag(HF_MODEL, QWEN_SMALL_BYTES))
        set_loaded(fakes)
        remote.preload.raises("OLLAMA_SERVER_ERROR")
        async with client.stream("GET", "/api/events") as stream:
            events = sse_events(stream)
            await next_event(events, "session.updated")
            await client.post("/api/models/preload", json={"name": HF_MODEL})
            failed = await next_event(
                events, "models.updated", lambda p: by_name(p.get("catalog", {})).get(HF_MODEL, {}).get("preload", {}).get("state") == "failed"
            )
            remote.preload.reset_calls()
            remote.list_local_models.raises("OLLAMA_UNREACHABLE")

            # Act:確認目錄失敗後等 1 秒(看有沒有推送),tags 恢復後再讀一次目錄
            response = await client.post("/api/models/preload", json={"name": QWEN_7B})
            pushed = await next_event(events, "models.updated", timeout=1.0)
            set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES), tag(HF_MODEL, QWEN_SMALL_BYTES))
            catalog = (await client.get("/api/models")).json()

    # Assert
    assert failed is not None
    assert (response.status_code, error_code(response)) == (502, "OLLAMA_UNREACHABLE")
    assert remote.preload.call_count == 0
    assert by_name(catalog)[QWEN_7B]["preload"]["state"] == "idle"
    assert by_name(catalog)[HF_MODEL]["preload"]["state"] == "failed"
    assert by_name(catalog)[HF_MODEL]["preload"]["reasonCode"] == "OLLAMA_SERVER_ERROR"
    assert pushed is None


# ---------------------------------------------------------------- US1-API-09


async def test_讀不到已下載清單時預先載入回_502_或_504_不送載入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_loaded(fakes)
    remote = fakes.remote_ollama
    remote.preload.reset_calls()

    # Act:三種代碼各送一次預先載入
    responses = []
    for code, _ in OLLAMA_FAILURES:
        remote.list_local_models.raises(code)
        responses.append(await ui_client.post("/api/models/preload", json={"name": QWEN_7B}))

    # Assert
    assert [(r.status_code, error_code(r)) for r in responses] == [(status, code) for code, status in OLLAMA_FAILURES]
    assert remote.preload.call_count == 0


# ---------------------------------------------------------------- US1-API-10


async def test_讀不到已載入清單時預先載入也回_502_或_504_不送載入(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    remote = fakes.remote_ollama
    remote.preload.reset_calls()

    # Act:三種代碼各送一次預先載入
    responses = []
    for code, _ in OLLAMA_FAILURES:
        remote.list_loaded_models.raises(code)
        responses.append(await ui_client.post("/api/models/preload", json={"name": QWEN_7B}))

    # Assert
    assert [(r.status_code, error_code(r)) for r in responses] == [(status, code) for code, status in OLLAMA_FAILURES]
    assert remote.preload.call_count == 0


# ---------------------------------------------------------------- US1-API-11


async def test_預先載入失敗的訊息是固定的繁體中文說明_不帶底層例外也沒有_model(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_loaded(fakes)
    remote = fakes.remote_ollama

    # Act:三種代碼各送一次預先載入,替身丟錯的訊息帶 traceback 與本機位址
    responses = []
    for code, _ in OLLAMA_FAILURES:
        remote.list_local_models.raises(code, LEAKY_MESSAGE)
        responses.append(await ui_client.post("/api/models/preload", json={"name": QWEN_7B}))

    # Assert
    assert [r.json()["message"] for r in responses] == [OLLAMA_MESSAGES[code] for code, _ in OLLAMA_FAILURES]
    assert all("model" not in r.json() for r in responses)
    assert all("Traceback" not in r.text and "127.0.0.1" not in r.text for r in responses)


# ---------------------------------------------------------------- US1-API-12


async def test_遠端恢復後下一次預先載入照常受理_不重開工作階段(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:第一次讀 tags 丟 `OLLAMA_UNREACHABLE`,之後照常;預先載入停在閘門前
    ColabWorld(fakes)
    name = (await open_ready(ui_client))["name"]
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    set_loaded(fakes)
    remote = fakes.remote_ollama
    remote.list_local_models.then(AdapterError("OLLAMA_UNREACHABLE", "連不到"))
    gate = remote.preload.gate()
    remote.preload.returns({"model": QWEN_7B, "done": True})
    remote.preload.reset_calls()

    # Act
    first = await ui_client.post("/api/models/preload", json={"name": QWEN_7B})
    second = await ui_client.post("/api/models/preload", json={"name": QWEN_7B})
    with contextlib.suppress(TimeoutError):  # 沒有送出載入時由下面的呼叫次數斷言失敗,不是逾時例外
        await asyncio.wait_for(gate.wait_entered_async(), timeout=1.0)
    session = await get_session(ui_client)
    gate.release()

    # Assert
    assert (first.status_code, error_code(first)) == (502, "OLLAMA_UNREACHABLE")
    assert (second.status_code, second.json()["preload"]["state"]) == (202, "loading")
    assert remote.preload.call_count == 1
    assert (session["state"], session["name"]) == ("ready", name)


# ---------------------------------------------------------------- US1-API-13


async def test_目錄讀得到但沒有這個模型時預先載入仍回_404(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES))
    set_loaded(fakes)

    # Act
    response = await ui_client.post("/api/models/preload", json={"name": QWEN_7B})

    # Assert
    assert (response.status_code, error_code(response)) == (404, "OLLAMA_NOT_FOUND")


# ---------------------------------------------------------------- US1-API-14
# `/api/connect` 的規格錨點是 006 的 contracts/ui.openapi.yaml § paths./connect.get,不在本 spec package(plan.md Q11)


async def test_連線設定讀不到目錄時回_502_或_504_與對應代碼(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:工作階段就緒(T4、套用 context 4096)
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_loaded(fakes)
    remote = fakes.remote_ollama

    # Act:tags 依序丟三種代碼各讀一次;再讓 tags 照常、ps 丟 `OLLAMA_TIMEOUT` 讀一次
    responses = []
    for code, _ in OLLAMA_FAILURES:
        remote.list_local_models.raises(code)
        responses.append(await ui_client.get("/api/connect"))
    set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
    remote.list_loaded_models.raises("OLLAMA_TIMEOUT")
    responses.append(await ui_client.get("/api/connect"))

    # Assert
    assert [(r.status_code, error_code(r)) for r in responses] == [
        (502, "OLLAMA_UNREACHABLE"),
        (502, "OLLAMA_BAD_RESPONSE"),
        (504, "OLLAMA_TIMEOUT"),
        (504, "OLLAMA_TIMEOUT"),
    ]


# ---------------------------------------------------------------- US1-API-15


async def test_連線設定失敗的訊息和模型目錄是同一句固定說明(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_loaded(fakes)
    remote = fakes.remote_ollama

    # Act:tags 依序丟三種代碼各讀一次,替身丟錯的訊息帶 traceback 與本機位址
    responses = []
    for code, _ in OLLAMA_FAILURES:
        remote.list_local_models.raises(code, LEAKY_MESSAGE)
        responses.append(await ui_client.get("/api/connect"))

    # Assert
    assert [r.json()["message"] for r in responses] == [OLLAMA_MESSAGES[code] for code, _ in OLLAMA_FAILURES]


# ---------------------------------------------------------------- US1-API-16


async def test_兩份清單乘三種代碼_列目錄與預先載入都不回_500(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    remote = fakes.remote_ollama
    remote.preload.reset_calls()

    # Act:失敗的清單(tags、ps)× 三種代碼共六種組合;每種各列一次目錄、送一次預先載入,組合之間把兩份清單重設成照常
    outcomes = []
    for failing in ("list_local_models", "list_loaded_models"):
        for code, _ in OLLAMA_FAILURES:
            set_tags(fakes, tag(QWEN_7B, QWEN_7B_BYTES))
            set_loaded(fakes)
            getattr(remote, failing).raises(code)
            listed = await ui_client.get("/api/models")
            preloaded = await ui_client.post("/api/models/preload", json={"name": QWEN_7B})
            outcomes.extend([listed, preloaded])

    # Assert
    expected = [(status, code) for _ in range(2) for code, status in OLLAMA_FAILURES for _ in range(2)]
    assert [(r.status_code, error_code(r)) for r in outcomes] == expected
    assert [r.status_code for r in outcomes].count(500) == 0
    assert remote.preload.call_count == 0


# ---------------------------------------------------------------- US1-API-17


async def test_沒有就緒的工作階段時預先載入回_503_不去讀遠端(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段,遠端兩份清單就算被讀也會丟 `OLLAMA_UNREACHABLE`
    ColabWorld(fakes)
    remote = fakes.remote_ollama
    remote.list_local_models.raises("OLLAMA_UNREACHABLE")
    remote.list_loaded_models.raises("OLLAMA_UNREACHABLE")

    # Act
    response = await ui_client.post("/api/models/preload", json={"name": QWEN_7B})

    # Assert
    assert (response.status_code, error_code(response)) == (503, "NO_READY_SESSION")
    assert remote.list_local_models.call_count == 0
