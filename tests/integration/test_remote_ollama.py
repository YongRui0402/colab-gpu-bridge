"""E7 遠端 Ollama 轉接層(testplan.md § 3.2;接縫:`RemoteOllama` 的方法,另一端是 `tests/fakes/ollama_server.py` 的假 Ollama 伺服器)。

`base_url` 直接指到假伺服器,相當於 SSH 本機轉發已經建好(contracts/remote-ollama.openapi.yaml § servers)。
"""

import socket
import time

import pytest

from cgb.adapters.errors import AdapterError
from cgb.adapters.remote_ollama import RemoteOllama
from fakes import FakeOllamaServer, HangReply, JsonReply, NdjsonReply


def closed_port_url() -> str:
    """一個沒有人在聽的 127.0.0.1 port(先綁再放掉)。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}"


# ---------------------------------------------------------------- US2-RO-01 get_version


async def test_get_version_回傳遠端的版本(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-01 情況 A:假伺服器回 200 `{"version":"0.40.15"}`。"""
    ollama_server.add("GET", "/api/version", JsonReply({"version": "0.40.15"}))

    result = await RemoteOllama().get_version(ollama_server.base_url)

    assert result["version"] == "0.40.15"
    ollama_server.assert_all_matched()


async def test_get_version_回應不是_JSON_時回_OLLAMA_BAD_RESPONSE(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-01 情況 B:假伺服器回 200 `<html>`。"""
    ollama_server.add(
        "GET", "/api/version", JsonReply(b"<html>", headers={"Content-Type": "text/html"})
    )

    with pytest.raises(AdapterError) as caught:
        await RemoteOllama().get_version(ollama_server.base_url)

    assert caught.value.code == "OLLAMA_BAD_RESPONSE"


async def test_get_version_port_關閉時回_OLLAMA_UNREACHABLE() -> None:
    """US2-RO-01 情況 C:本機轉發的 port 沒有在聽。"""
    with pytest.raises(AdapterError) as caught:
        await RemoteOllama().get_version(closed_port_url())

    assert caught.value.code == "OLLAMA_UNREACHABLE"


async def test_get_version_不回應時在逾時內回_OLLAMA_TIMEOUT(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-01 情況 D:假伺服器 6 秒不回(逾時注入 0.3 秒);逾時沒設的話健康檢查會卡住。"""
    ollama_server.add("GET", "/api/version", HangReply())
    remote = RemoteOllama(version_timeout=0.3)

    started = time.monotonic()
    with pytest.raises(AdapterError) as caught:
        await remote.get_version(ollama_server.base_url)
    elapsed = time.monotonic() - started

    assert caught.value.code == "OLLAMA_TIMEOUT"
    assert elapsed < 2.0, f"注入 0.3 秒逾時,卻等了 {elapsed:.2f} 秒"


# ---------------------------------------------------------------- US2-RO-02 generate

GENERATE_BODY = {"model": "x", "prompt": "hi"}


async def _generate_all(remote: RemoteOllama, base_url: str) -> list[dict]:
    return [line async for line in await remote.generate(base_url, GENERATE_BODY)]


async def test_generate_模型不在執行環境上時回_OLLAMA_NOT_FOUND_並保留英文原文(
    ollama_server: FakeOllamaServer,
) -> None:
    """US2-RO-02 情況 A:假伺服器回 404 `{"error":"model 'x' not found"}`。"""
    ollama_server.add("POST", "/api/generate", JsonReply({"error": "model 'x' not found"}, status=404))

    with pytest.raises(AdapterError) as caught:
        await _generate_all(RemoteOllama(), ollama_server.base_url)

    assert caught.value.code == "OLLAMA_NOT_FOUND"
    assert caught.value.message == "model 'x' not found"
    ollama_server.assert_all_matched()


async def test_generate_回_400_時回_OLLAMA_BAD_REQUEST(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-02 情況 B:假伺服器回 400。"""
    ollama_server.add(
        "POST", "/api/generate", JsonReply({"error": "invalid character 'x' looking for beginning of value"}, status=400)
    )

    with pytest.raises(AdapterError) as caught:
        await _generate_all(RemoteOllama(), ollama_server.base_url)

    assert caught.value.code == "OLLAMA_BAD_REQUEST"


async def test_generate_回_500_時回_OLLAMA_SERVER_ERROR(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-02 情況 C:假伺服器回 500;和 404 要分得開。"""
    ollama_server.add("POST", "/api/generate", JsonReply({"error": "model requires more system memory"}, status=500))

    with pytest.raises(AdapterError) as caught:
        await _generate_all(RemoteOllama(), ollama_server.base_url)

    assert caught.value.code == "OLLAMA_SERVER_ERROR"


async def test_generate_串流在_done_之前斷線時回_OLLAMA_STREAM_INTERRUPTED(ollama_server: FakeOllamaServer) -> None:
    """US2-RO-02 情況 D:串流 2 行後關閉、沒有 `done:true`;不能當成正常結束。"""
    lines = [
        {"model": "x", "created_at": "2026-11-10T09:00:00Z", "response": "a", "done": False},
        {"model": "x", "created_at": "2026-11-10T09:00:01Z", "response": "b", "done": False},
    ]
    ollama_server.add("POST", "/api/generate", NdjsonReply(lines, then="disconnect"))
    received: list[dict] = []

    with pytest.raises(AdapterError) as caught:
        async for line in await RemoteOllama().generate(ollama_server.base_url, GENERATE_BODY):
            received.append(line)

    assert caught.value.code == "OLLAMA_STREAM_INTERRUPTED"
    assert [line["response"] for line in received] == ["a", "b"]
