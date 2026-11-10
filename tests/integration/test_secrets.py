"""全域:機密不出現在日誌、API 回應與 SSE 事件(testplan.md § G-02;spec.md § NFR-010)。

接縫:測試行程內的 uvicorn(SSE 要經真的 HTTP 連線讀),轉接層用替身;
替身的錯誤訊息與 stderr 都帶著已知的假 endpoint 與假 proxy token,授權檔寫入已知的假 token。
擷取的範圍:caplog(DEBUG 起的每一筆)、行程的 stdout 與 stderr(capfd)、每一個 API 回應的本文、SSE 的每一行。

Ollama 相容端點的請求紀錄是 logger `cgb.ollama_compat.access_log` 的紀錄(spec.md § 假設:
只記時間、模型、耗時與狀態碼;時間由 logging 的 formatter 加上,訊息本身只放後三者)。
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from fakes import JsonReply
from integration.test_api_auth import google_flows
from integration.test_api_session import T4, ColabWorld, open_ready, wait_until

FAKE_TOKEN = "cgb-test-fake-token-0123456789"
FAKE_ENDPOINT_HOST = "cgb-test-fake-endpoint"
FAKE_PROXY_TOKEN = "cgb-test-fake-proxy"
FAKE_URL = f"https://{FAKE_ENDPOINT_HOST}.example/?colab-runtime-proxy-token={FAKE_PROXY_TOKEN}"
SECRETS = (FAKE_TOKEN, FAKE_ENDPOINT_HOST, FAKE_PROXY_TOKEN)

ACCESS_LOGGER = "cgb.ollama_compat.access_log"
MODEL = "qwen2.5:0.5b"
PROMPT_MARKER = "cgb-test-prompt-不該出現在日誌"
REPLY_MARKER = "cgb-test-reply-不該出現在日誌"


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


async def test_登入_開啟_開啟失敗_重連逾時_結束的日誌_回應與事件都不含機密(
    live_servers: Any,
    fakes: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
) -> None:
    # Arrange:授權檔照 E9 轉接層的行為寫在 $CGB_COLAB_CONFIG_DIR,內含已知的假 token
    caplog.set_level(logging.DEBUG)
    config_dir = tmp_path / "colab-cli"
    monkeypatch.setenv("CGB_COLAB_CONFIG_DIR", str(config_dir))
    world = ColabWorld(fakes)
    google_flows(fakes)

    def write_token(*args: Any, **kwargs: Any) -> Path:
        config_dir.mkdir(mode=0o700, exist_ok=True)
        token = config_dir / "token.json"
        token.touch(mode=0o600)
        token.write_text(json.dumps({"access_token": FAKE_TOKEN, "refresh_token": FAKE_TOKEN}), encoding="utf-8")
        return token

    def create_failing(*args: Any, **kwargs: Any) -> None:
        world.log.append(("create_session", kwargs["name"]))
        raise AdapterError("COLAB_FAILED", f"colab new 失敗:Failed to issue request POST {FAKE_URL}: 500", stderr_last_line=f"POST {FAKE_URL}")

    def tunnel_failing(*args: Any, **kwargs: Any) -> None:
        raise AdapterError("TUNNEL_UNREACHABLE", f"ssh 失敗:{FAKE_URL}", stderr_last_line=f"ssh: connect to {FAKE_URL} refused")

    fakes.google_oauth.request_token.side_effect(write_token)
    fakes.server.add("POST", "/api/generate", JsonReply({"model": MODEL, "response": REPLY_MARKER, "done": True}))
    fakes.server.add("POST", "/api/chat", JsonReply({"model": MODEL, "message": {"role": "assistant", "content": REPLY_MARKER}, "done": True}))
    ollama_requests = 0

    async with (
        httpx.AsyncClient(base_url=live_servers.ui_url, timeout=5.0) as ui,
        httpx.AsyncClient(base_url=live_servers.ollama_url, timeout=5.0) as ollama,
    ):
        recorder = Recorder(ui)
        reading = asyncio.create_task(recorder.read_events())
        try:
            # Act 1:登入成功
            flow_id = (await recorder.request("POST", "/api/auth/authorizations")).json().get("flowId")
            await recorder.request("POST", f"/api/auth/authorizations/{flow_id}/code", json={"code": "4/cgb-test-code"})
            await recorder.request("GET", "/api/auth")

            # Act 2:開啟成功,經 Ollama 相容端點送帶 prompt 的請求,再結束
            await open_ready(ui)
            for path, body in (
                ("/api/generate", {"model": MODEL, "prompt": PROMPT_MARKER, "stream": False}),
                ("/api/chat", {"model": MODEL, "messages": [{"role": "user", "content": PROMPT_MARKER}], "stream": False}),
            ):
                response = await ollama.post(path, json=body)
                recorder.responses.append(response.text)
                ollama_requests += 1
            await recorder.request("DELETE", "/api/session")
            await wait_until(ui, lambda s: s.get("state") == "ended")

            # Act 3:開啟失敗(轉接層的錯誤帶著 endpoint)
            fakes.colab.create_session.side_effect(create_failing)
            await recorder.request("POST", "/api/session", json={"runtimeType": T4})
            await wait_until(ui, lambda s: s.get("state") == "open_failed")
            await recorder.request("GET", "/api/session")

            # Act 4:重連逾時(通道的錯誤與 stderr 帶著 endpoint;重連時限 2 秒)
            fakes.colab.create_session.side_effect(world._create)
            await open_ready(ui)
            fakes.tunnel.open_tunnel.side_effect(tunnel_failing)
            fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", f"連不到 {FAKE_URL}", stderr_last_line=FAKE_URL)
            await wait_until(ui, lambda s: s.get("state") == "lost", timeout=4.0)
            await wait_until(ui, lambda s: bool(world.calls("stop_session")) and s.get("releaseWarning") is None, timeout=1.0)

            # Act 5:結束之後再查一次現況、紀錄,再按一次結束
            await recorder.request("GET", "/api/session")
            await recorder.request("GET", "/api/sessions")
            await recorder.request("DELETE", "/api/session")
            await asyncio.sleep(0.2)
        finally:
            reading.cancel()
            await asyncio.gather(reading, return_exceptions=True)

    captured = capfd.readouterr()
    logs = [record.getMessage() for record in caplog.records] + [
        str(record.exc_info) for record in caplog.records if record.exc_info
    ]
    outputs = [captured.out, captured.err]
    replies = recorder.responses + recorder.sse_lines
    everything = logs + outputs + replies

    # Assert(則1~3):日誌、回應與事件都沒有假 token、假 endpoint、假 proxy token
    assert any("open_failed" in line for line in recorder.sse_lines) and any('"lost"' in line for line in recorder.sse_lines)
    for secret in SECRETS:
        assert leaked(everything, secret) == [], (secret, leaked(everything, secret)[:3])

    # Assert(則4):每個 Ollama 相容端點的請求一筆紀錄,只有模型、耗時與狀態碼,沒有 prompt 與回應的內容
    access = [record.getMessage() for record in caplog.records if record.name == ACCESS_LOGGER]
    assert len(access) == ollama_requests, access
    for message in access:
        assert MODEL in message and "200" in message and re.search(r"\d+(\.\d+)?\s*ms", message), message
        assert all(marker not in message for marker in (PROMPT_MARKER, REPLY_MARKER, "/api/", "127.0.0.1")), message
