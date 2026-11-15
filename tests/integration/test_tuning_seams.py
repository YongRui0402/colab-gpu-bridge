"""套用設定的接縫回歸:正式 `RemoteOllama` 搭配假 HTTP、正式 `HealthMonitor` 搭配替身(MR !6 審查的三則討論)。"""

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.adapters.remote_ollama import RemoteOllama
from cgb.services.health_monitor import HealthMonitor
from cgb.services.tuning import TuningService

FORWARD_URL = "http://cgb-test-fake-forward.example:51234"


class FakeTunings:
    def __init__(self) -> None:
        self.models: list[dict[str, Any]] = []

    def add_model(self, record_id: int, *, position: int, model: str, reason: str | None = None, reason_code: str | None = None) -> None:
        self.models.append({"position": position, "model": model, "reason": reason, "reason_code": reason_code})


def make_service(handler: Any, tunings: FakeTunings, events: Any = None) -> TuningService:
    remote = RemoteOllama(transport=httpx.MockTransport(handler))
    state = SimpleNamespace(remote_ollama=remote)
    service = TuningService.__new__(TuningService)
    service._state = state
    service._tunings = tunings
    service._events = events or SimpleNamespace(models_updated=lambda catalog: None)
    return service


def preload_handler(failures: dict[str, Any]) -> Any:
    """`/api/generate` 依模型名稱回失敗(例外或回應),其餘回 200;目錄查詢回空清單。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in ("/api/tags", "/api/ps"):
            return httpx.Response(200, json={"models": []})
        model = __import__("json").loads(request.content)["model"]
        failure = failures.get(model)
        if isinstance(failure, Exception):
            raise failure
        if failure is not None:
            return failure
        return httpx.Response(200, json={"done": True})

    return handler


async def test_重新載入時遠端回_500_或斷線_該模型列為_PRELOAD_FAILED_並繼續載下一個() -> None:
    # Arrange:第一個模型 500(記憶體不足)、第二個斷線、第三個逾時、第四個成功
    failures = {
        "m1": httpx.Response(500, json={"error": "model requires more system memory"}),
        "m2": httpx.ReadError("boom"),
        "m3": httpx.ReadTimeout("slow"),
    }
    tunings = FakeTunings()
    service = make_service(preload_handler(failures), tunings)

    # Act
    await service._reload_models(1, FORWARD_URL, None, ["m1", "m2", "m3", "m4"], None)

    # Assert
    by_model = {row["model"]: row for row in tunings.models}
    assert by_model["m1"]["reason"] == "PRELOAD_FAILED" and by_model["m1"]["reason_code"] == "OLLAMA_SERVER_ERROR"
    assert by_model["m2"]["reason"] == "PRELOAD_FAILED" and by_model["m2"]["reason_code"] == "OLLAMA_UNREACHABLE"
    assert by_model["m3"]["reason"] == "PRELOAD_FAILED" and by_model["m3"]["reason_code"] == "OLLAMA_TIMEOUT"
    assert by_model["m4"]["reason"] is None


async def test_preload_回應不是_JSON_物件時歸成_OLLAMA_BAD_RESPONSE() -> None:
    remote = RemoteOllama(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"not json")))

    with pytest.raises(AdapterError) as caught:
        await remote.preload(base_url=FORWARD_URL, model="m1")

    assert caught.value.code == "OLLAMA_BAD_RESPONSE"


async def test_推送模型目錄失敗時日誌含_traceback_也不帶轉發位址(caplog: pytest.LogCaptureFixture) -> None:
    # Arrange:底層 ConnectError 的訊息帶轉發位址
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connect to {FORWARD_URL} failed")

    service = make_service(handler, FakeTunings())
    caplog.set_level(logging.DEBUG)

    # Act
    await service._publish_models(FORWARD_URL, None)

    # Assert:格式化後(含 traceback)的日誌沒有轉發位址
    formatter = logging.Formatter()
    text = "\n".join(formatter.format(record) for record in caplog.records)
    assert caplog.records
    assert "cgb-test-fake-forward" not in text


async def test_健康檢查跨過套用受理後失敗_不重連_狀態與通道都不動() -> None:
    # Arrange:ready 時開始檢查,檢查停在 check_health;期間受理套用(狀態改 applying_tuning),再讓檢查失敗
    release = asyncio.Event()
    calls: list[str] = []
    row = {"name": "cgb-test-s", "state": "ready"}

    async def check_health(*, session_name: str) -> None:
        await release.wait()
        raise AdapterError("TUNNEL_UNHEALTHY", "Ollama 暫停回應")

    async def close_tunnel(*, session_name: str) -> None:
        calls.append("close_tunnel")

    repo = SimpleNamespace(latest=lambda: row, update=lambda name, **fields: row.update(fields))
    state = SimpleNamespace(tunnel=SimpleNamespace(check_health=check_health, close_tunnel=close_tunnel))
    monitor = HealthMonitor(state, repo, SimpleNamespace(), key_path="/unused")
    checking = asyncio.create_task(monitor._check("cgb-test-s"))
    await asyncio.sleep(0)

    # Act
    row["state"] = "applying_tuning"
    release.set()
    await checking

    # Assert
    assert row["state"] == "applying_tuning"
    assert calls == []
