"""全域:設定與重啟不把 `colab exec` 的命令列、token 與轉發位址帶出去,也不連使用者自己的 Ollama(testplan.md § G-05;spec.md § NFR-003)。

接縫:測試行程內的 uvicorn(SSE 要經真的 HTTP 連線讀),轉接層用替身;
替身的錯誤訊息與 stderr 都帶著已知的假命令列、假 token 與假轉發位址。
擷取的範圍:caplog(DEBUG 起的每一筆)、行程的 stdout 與 stderr(capfd)、每一個 API 回應的本文、SSE 的每一行、SQLite 資料庫的全部內容。
11434 的守門在 `tests/conftest.py`(連線一律擋下並讓測試失敗);這裡另外確認守門沒有記到任何一次連線。
"""

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from conftest import _p6_hits
from integration.test_api_session import ColabWorld, wait_until
from integration.test_api_tuning import A100, A100_STARTED, NONE3, tuning_body
from integration.test_api_tuning_apply import AUTO_RESTARTED, wait_applied

FAKE_TOKEN = "cgb-test-fake-token-0123456789"
FAKE_FORWARD_HOST = "cgb-test-fake-forward"
FAKE_PROXY_TOKEN = "cgb-test-fake-proxy"
FAKE_COMMAND = f"colab exec cgb-test-session --token {FAKE_TOKEN} -- python /tmp/cgb-restart.py"
FAKE_URL = f"https://{FAKE_FORWARD_HOST}.example/?colab-runtime-proxy-token={FAKE_PROXY_TOKEN}"
SECRETS = (FAKE_TOKEN, FAKE_FORWARD_HOST, FAKE_PROXY_TOKEN, "colab exec", "cgb-restart.py")


class Recorder:
    """依序記下每一個 API 回應的本文;SSE 的每一行由背景工作記下。"""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.responses: list[str] = []
        self.sse_lines: list[str] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        response = await self.client.request(method, url, **kwargs)
        self.responses.append(f"{method} {url} {response.status_code}\n{response.text}")
        return response

    async def read_events(self) -> None:
        async with self.client.stream("GET", "/api/events") as stream:
            async for line in stream.aiter_lines():
                self.sse_lines.append(line)


def leaked(texts: list[str], secret: str) -> list[str]:
    return [text for text in texts if secret in text]


def database_dump(path: Path) -> list[str]:
    """資料庫每一張表的每一列,各轉成一行文字。"""
    connection = sqlite3.connect(path)
    try:
        return list(connection.iterdump())
    finally:
        connection.close()


# ---- 005 G-05


async def test_開啟帶覆蓋值_讀狀態與紀錄_套用並重啟失敗一次_輸出都不含命令列與機密也沒連使用者的_Ollama(
    live_servers: Any,
    fakes: Any,
    db_path: Path,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
) -> None:
    # Arrange:遠端腳本第一次失敗,錯誤訊息與 stderr 都帶著命令列、token 與轉發位址;第二次(改用自動值)成功
    caplog.set_level(logging.DEBUG)
    world = ColabWorld(fakes)
    world.start_result = A100_STARTED
    world.loaded = []
    hits_before = len(_p6_hits)

    async def restart(*args: Any, **kwargs: Any) -> dict[str, Any]:
        world.log.append(("restart_ollama", kwargs.get("name")))
        if kwargs["overrides"] != NONE3:
            raise AdapterError(
                "COLAB_REMOTE_ERROR",
                f"遠端腳本失敗:{FAKE_COMMAND} {FAKE_URL}",
                stderr_last_line=f"{FAKE_COMMAND}: connect to {FAKE_URL} failed",
                remote_stage="verify",
            )
        return AUTO_RESTARTED

    fakes.colab.restart_ollama.side_effect(restart)

    async with httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as ui:
        recorder = Recorder(ui)
        reading = asyncio.create_task(recorder.read_events())
        try:
            # Act 1:開啟(帶覆蓋值)到就緒
            opened = await recorder.request("POST", "/api/session", json={"runtimeType": A100, "tuning": tuning_body(4, None, None)})
            assert opened.status_code == 202, opened.text
            session = await wait_until(ui, lambda s: s.get("state") == "ready")
            name = session["name"]

            # Act 2:讀工作階段狀態與紀錄
            await recorder.request("GET", "/api/session")
            await recorder.request("GET", "/api/sessions")
            await recorder.request("GET", f"/api/sessions/{name}")

            # Act 3:套用並重啟(第一次失敗、改用自動值成功),再讀一次狀態與紀錄
            accepted = await recorder.request("POST", "/api/session/tuning", json=tuning_body(2, 4096, 1))
            assert accepted.status_code == 202, accepted.text
            final = await wait_applied(ui)
            await recorder.request("GET", "/api/session")
            await recorder.request("GET", f"/api/sessions/{name}")
            await recorder.request("GET", "/api/sessions")
            await asyncio.sleep(0.2)
        finally:
            reading.cancel()
            await asyncio.gather(reading, return_exceptions=True)

    captured = capfd.readouterr()
    logs = [record.getMessage() for record in caplog.records] + [
        str(record.exc_info) for record in caplog.records if record.exc_info
    ]
    replies = recorder.responses + recorder.sse_lines
    everything = logs + [captured.out, captured.err] + replies + database_dump(db_path)

    # Assert(則1):有走到失敗改回自動值,UI API 回應、SSE、日誌與資料庫都不含命令列、token 與轉發位址
    assert final["ollama"]["lastApply"]["result"] == "fell_back_to_auto", final["ollama"]["lastApply"]
    assert any("fell_back_to_auto" in line for line in recorder.sse_lines)
    for secret in SECRETS:
        assert leaked(everything, secret) == [], (secret, leaked(everything, secret)[:3])

    # Assert(則2):沒有任何連線送往 127.0.0.1:11434
    assert _p6_hits[hits_before:] == []
