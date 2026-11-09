"""E7 遠端 Ollama 轉接層(testplan.md § 3.2;接縫:`RemoteOllama` 的方法,另一端是 `tests/fakes/ollama_server.py` 的假 Ollama 伺服器)。

`base_url` 直接指到假伺服器,相當於 SSH 本機轉發已經建好(contracts/remote-ollama.openapi.yaml § servers)。
"""

import asyncio
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


# ---------------------------------------------------------------- US3-RO-01 pull_model

PULL_LAYER_50 = {"status": "pulling a", "digest": "sha256:a", "total": 100, "completed": 50}
PULL_LAYER_100 = {"status": "pulling a", "digest": "sha256:a", "total": 100, "completed": 100}


async def _pull_all(remote: RemoteOllama, base_url: str, model: str = "qwen2.5:7b") -> list[dict]:
    return [line async for line in await remote.pull_model(base_url=base_url, model=model)]


async def test_pull_model_只把帶_total_的行當進度_最後回成功(ollama_server: FakeOllamaServer) -> None:
    """US3-RO-01:`pulling manifest` 沒有 `total`,不能變成 0% 進度;要等到 `success` 才算完成。"""
    lines = [{"status": "pulling manifest"}, PULL_LAYER_50, PULL_LAYER_100, {"status": "success"}]
    ollama_server.add("POST", "/api/pull", NdjsonReply(lines), json={"model": "qwen2.5:7b"})

    received = await _pull_all(RemoteOllama(), ollama_server.base_url)

    progress = [(line["completed"], line["total"]) for line in received if "total" in line]
    assert progress == [(50, 100), (100, 100)]
    assert all("total" in line for line in received[:-1]), f"沒有 total 的狀態行被當成進度:{received}"
    assert received[-1] == {"status": "success"}
    ollama_server.assert_all_matched()


# ---------------------------------------------------------------- US3-RO-02 pull_model 的失敗


async def _pull_outcome(remote: RemoteOllama, base_url: str, within: float = 3.0) -> str:
    """跑完一次 pull,交回錯誤代碼;正常結束是「回成功」,`within` 秒內沒結束是「沒有結束」。"""
    try:
        await asyncio.wait_for(_pull_all(remote, base_url), within)
    except AdapterError as error:
        return error.code
    except TimeoutError:
        return f"{within:g} 秒內沒有結束"
    except Exception as error:  # noqa: BLE001 - 丟了別的例外也要成為斷言失敗
        return repr(error)
    return "回成功"


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        pytest.param(
            NdjsonReply([{"status": "pulling manifest"}, {"error": "pull model manifest: file does not exist"}]),
            "OLLAMA_NOT_FOUND",
            id="A-file-does-not-exist",
        ),
        pytest.param(NdjsonReply([{"error": "max retries exceeded"}]), "OLLAMA_PULL_FAILED", id="B-other-error"),
        pytest.param(NdjsonReply([PULL_LAYER_50, PULL_LAYER_100], then="disconnect"), "OLLAMA_STREAM_INTERRUPTED", id="C-disconnect"),
        pytest.param(NdjsonReply([PULL_LAYER_50], then="hang"), "OLLAMA_TIMEOUT", id="D-silent"),
    ],
)
async def test_pull_model_的失敗依串流內容分類(
    ollama_server: FakeOllamaServer, reply: NdjsonReply, expected: str
) -> None:
    """US3-RO-02:HTTP 200 之後的 error 行、中途斷線、進度停住(進度間隔逾時注入 0.3 秒)都不能當成功。"""
    ollama_server.add("POST", "/api/pull", reply, json={"model": "qwen2.5:7b"})
    remote = RemoteOllama(pull_progress_timeout=0.3)

    outcome = await _pull_outcome(remote, ollama_server.base_url)

    assert outcome == expected
    ollama_server.assert_all_matched()


# ---------------------------------------------------------------- US3-RO-03 list_local_models、list_loaded_models

DIGEST_7B = "845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e"
DIGEST_05B = "a8b0c51577010a279d933d14c2f8ab4b268079d44c5c8830c0a93900f1827c67"
DETAILS = {"format": "gguf", "family": "qwen2", "families": ["qwen2"], "parameter_size": "7.6B", "quantization_level": "Q4_K_M"}
TAGS_TWO_MODELS = {
    "models": [
        {
            "name": "qwen2.5:7b",
            "model": "qwen2.5:7b",
            "modified_at": "2026-11-10T09:00:00.000000000Z",
            "size": 4683087332,
            "digest": DIGEST_7B,
            "details": DETAILS,
        },
        {
            "name": "qwen2.5:0.5b",
            "model": "qwen2.5:0.5b",
            "modified_at": "2026-11-10T08:00:00.000000000Z",
            "size": 397821319,
            "digest": DIGEST_05B,
            "details": {**DETAILS, "parameter_size": "494.03M"},
        },
    ]
}
PS_ONE_MODEL = {
    "models": [
        {
            "name": "qwen2.5:7b",
            "model": "qwen2.5:7b",
            "size": 6654289920,
            "digest": DIGEST_7B,
            "details": DETAILS,
            "expires_at": "2318-02-19T09:00:00.000000000Z",
            "size_vram": 6654289920,
            "context_length": 4096,
        }
    ]
}


async def test_list_local_models_與_list_loaded_models_回名稱與大小(ollama_server: FakeOllamaServer) -> None:
    """US3-RO-03:tags 回兩個模型、ps 回一個。"""
    ollama_server.add("GET", "/api/tags", JsonReply(TAGS_TWO_MODELS))
    ollama_server.add("GET", "/api/ps", JsonReply(PS_ONE_MODEL))
    remote = RemoteOllama()

    local = await remote.list_local_models(base_url=ollama_server.base_url)
    loaded = await remote.list_loaded_models(base_url=ollama_server.base_url)

    assert [(m["name"], m["size"]) for m in local["models"]] == [("qwen2.5:7b", 4683087332), ("qwen2.5:0.5b", 397821319)]
    assert [m["name"] for m in loaded["models"]] == ["qwen2.5:7b"]
    ollama_server.assert_all_matched()


# ---------------------------------------------------------------- US3-RO-04 preload


async def test_preload_只送_model_與_keep_alive_負一(ollama_server: FakeOllamaServer) -> None:
    """US3-RO-04:預先載入不帶 `prompt`,`keep_alive` 一律 -1(plan.md Q4)。"""
    loaded = {
        "model": "qwen2.5:7b",
        "created_at": "2026-11-10T09:00:00Z",
        "response": "",
        "done": True,
        "done_reason": "load",
    }
    ollama_server.add("POST", "/api/generate", JsonReply(loaded))

    await RemoteOllama().preload(base_url=ollama_server.base_url, model="qwen2.5:7b")

    [request] = ollama_server.requests_to("POST", "/api/generate")
    assert request.json() == {"model": "qwen2.5:7b", "keep_alive": -1}
    ollama_server.assert_all_matched()
