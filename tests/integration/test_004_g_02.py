"""G-02(tasks.md T234):`RemoteOllama.pull_model` 與對話轉送,對真的 Ollama 一致(004 testplan.md § 7.2)。

測試自己起一個臨時的 `ollama serve`(`/usr/local/bin/ollama`,空的 `OLLAMA_MODELS`;做法同 003 的 G-01):port 由
`free_loopback_port()` 取(127.0.0.1,另外避開 e2e 的 8781、11437),環境變數只給 `PATH`、`HOME`、`OLLAMA_MODELS`
(都在 pytest 暫存資料夾)與 `OLLAMA_HOST`,以 `start_new_session=True` 起在自己的行程群組。
後端以 `start_live_servers` 起在 127.0.0.1 隨機 port,遠端 Ollama 用真的 `RemoteOllama(transport=RecordingTransport())`,
`FakeTunnel.open_tunnel` 回報的 `baseUrl` 指到臨時 serve,`FakeColabControl` 開到就緒;對話轉送的 client 換成
包著真傳輸、會留下請求本文的 transport(照樣經 `check_port`),量臨時 serve 收到的 `messages` 則數。

標 `realrun`,預設排除;不放 `tests/realrun/`,不經會執行 `colab usage` 的 `realrun` fixture。
護欄(testplan.md § 7.0):不對 127.0.0.1:11434 送任何請求,所有對 Ollama 的 HTTP 都經 `check_port`;不執行沒有指定
`OLLAMA_HOST` 的 `ollama` 指令;從 Hugging Face 下載約 105 MB 到 pytest 暫存資料夾(不花錢、只讀對方),`Q4_K_L` 在
manifest 就失敗、不下載;Colab、SSH 都用替身,不執行任何 `colab` 指令;收尾送 SIGTERM、10 秒內沒結束就 SIGKILL,
並驗行程與行程群組都已結束(則9);約 60 秒。`/usr/local/bin/ollama` 不存在就標無法實跑,不替它安裝。
判定者:腳本;樣本:`hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M`(一次實跑)。
執行:`uv run pytest -m realrun tests/integration/test_004_g_02.py`
"""

import json
import logging
import os
import sqlite3
import subprocess
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.adapters.remote_ollama import RemoteOllama
from cgb.app import AppPair
from integration.test_003_g_01 import end_group, wait_ready
from integration.test_004_g_01 import ensure_measurements
from integration.test_api_session import ColabWorld, open_ready
from realrun.conftest import check_port, write_measurement
from realrun.helpers import RecordingTransport, free_loopback_port, ndjson

pytestmark = pytest.mark.realrun

CASE, TASK = "G-02", "T234"
OLLAMA_BIN = Path("/usr/local/bin/ollama")
E2E_PORTS = frozenset({8781, 11437})
REPO = "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF"
MODEL = f"{REPO}:Q4_K_M"
PROMPT = "Say hi in one word."
THRESHOLD = (
    "則1:第一次 pull 最後一筆是 success、中間有帶 total 的進度;則2:list_local_models 有這個名稱;"
    "則3:Q4_K_L 丟 OLLAMA_PULL_FAILED;則4:兩次 /api/chat 都 200 application/x-ndjson、最後一行 done true;"
    "則5:兩次最後一行 eval_count、eval_duration 都 > 0;則6:臨時 serve 收到的第二個 /api/chat messages 3 則;"
    "則7:沒下載的模型 404 OLLAMA_NOT_FOUND;則8:日誌與 SQLite 檔裡 'Say hi in one word.' 0 次;則9:收尾後行程與行程群組都已結束"
)


@dataclass
class Report:
    numbers: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    unavailable: str | None = None


@dataclass
class TempServe:
    port: int
    process: subprocess.Popen[bytes]
    version: str

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


class BodyRecorder(httpx.AsyncBaseTransport):
    """對話轉送用:留下每個送往臨時 serve 的請求本文;每個請求都先經 `check_port`。"""

    def __init__(self) -> None:
        self.inner = httpx.AsyncHTTPTransport()
        self.bodies: list[tuple[str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.port is not None:
            check_port(request.url.port)
        body = await request.aread()
        self.bodies.append((request.url.path, json.loads(body) if body else None))
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()


@pytest.fixture
def report() -> Iterator[Report]:
    """`serve` 依賴這個 fixture:`serve` 先收尾,則9 的結果也寫得進同一列。"""
    got = Report()
    yield got
    if got.unavailable is not None:
        write_measurement(CASE, TASK, got.unavailable, THRESHOLD, None, "無法實跑", path=ensure_measurements())
        return
    names = [f"則{i}" for i in range(1, 10)]
    failed = [name for name in names if not got.checks.get(name, False)]
    note = ("沒過:" + "、".join(failed) + ";" if failed else "") + "臨時 serve 只綁 127.0.0.1,不碰 11434;Colab、SSH 用替身"
    write_measurement(CASE, TASK, ";".join(got.numbers), THRESHOLD, not failed, note, path=ensure_measurements())
    assert got.checks.get("則9", False), "臨時 ollama serve 收尾後行程或行程群組還在:" + ";".join(got.numbers)


def loopback_port() -> int:
    while True:
        port = free_loopback_port()
        if port not in E2E_PORTS:
            return port


@pytest.fixture
def serve(report: Report, tmp_path: Path) -> Iterator[TempServe]:
    if not OLLAMA_BIN.is_file():
        report.unavailable = f"{OLLAMA_BIN} 不存在"
        pytest.skip(f"無法實跑:{OLLAMA_BIN} 不存在,不替它安裝")
    port = loopback_port()
    home, models = tmp_path / "home", tmp_path / "models"
    home.mkdir()
    models.mkdir()
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "OLLAMA_MODELS": str(models), "OLLAMA_HOST": f"127.0.0.1:{port}"}
    with (tmp_path / "ollama-serve.log").open("wb") as log:
        process = subprocess.Popen(
            [str(OLLAMA_BIN), "serve"], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )  # fmt: skip
    try:
        version = wait_ready(port, process)
        yield TempServe(port, process, version)
    finally:
        ended, group_empty, how = end_group(process)
        report.numbers.append(
            f"收尾:{how};行程已結束 {'是' if ended else '否'}(poll() = {process.poll()}),行程群組已空 {'是' if group_empty else '否'}"
        )
        report.checks["則9"] = ended and group_empty


async def pull_all(ollama: RemoteOllama, base_url: str, model: str) -> tuple[list[dict[str, Any]], str | None]:
    lines: list[dict[str, Any]] = []
    try:
        async for line in await ollama.pull_model(base_url=base_url, model=model):
            lines.append(line)
    except AdapterError as error:
        return lines, error.code
    return lines, None


async def chat_once(client: httpx.AsyncClient, messages: list[dict[str, str]]) -> tuple[int, str, list[Any]]:
    async with client.stream("POST", "/api/chat", json={"model": MODEL, "messages": messages}) as response:
        body = await response.aread()
    return response.status_code, response.headers.get("content-type", ""), ndjson(body)


def stored_count(db_path: Path, text: str) -> int:
    count = 0
    with sqlite3.connect(db_path) as conn:
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            count += repr(conn.execute(f'SELECT * FROM "{table}"').fetchall()).count(text)
    for suffix in ("", "-wal", "-journal"):
        path = Path(str(db_path) + suffix)
        if path.exists():
            count += path.read_bytes().count(text.encode())
    return count


async def test_g_02(
    serve: TempServe,
    report: Report,
    make_app: Callable[..., AppPair],
    start_live_servers: Callable[..., Any],
    fakes: Any,
    db_path: Path,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    # Arrange:真的 RemoteOllama 接臨時 serve;Colab、通道用替身,通道的 baseUrl 指到臨時 serve
    caplog.set_level(logging.DEBUG)
    # 測試直接呼叫的與後端用的各一份:後端跑在 uvicorn 自己的執行緒與事件迴圈,連線池不跨迴圈共用
    transport, app_transport = RecordingTransport(), RecordingTransport()
    ollama = RemoteOllama(transport=transport)
    world = ColabWorld(fakes)
    fakes.tunnel.open_tunnel.side_effect(
        lambda *a, **k: {
            "sessionName": k["session_name"],
            "baseUrl": serve.base_url,
            "remoteOllamaVersion": serve.version,
            "connectedAt": "2026-11-09T09:00:00Z",
            "elapsedMs": 0,
        }
    )
    pair = make_app(remote_ollama=RemoteOllama(transport=app_transport))
    servers = start_live_servers(pair)
    relay = BodyRecorder()
    # 原本的 client 留給 lifespan 收尾;換上的這個第一次用在後端的事件迴圈
    pair.ui.state.chat_client = httpx.AsyncClient(transport=relay, timeout=httpx.Timeout(10.0, read=300.0))

    # Act
    try:
        pulled, pull_error = await pull_all(ollama, serve.base_url, MODEL)
        local = await ollama.list_local_models(base_url=serve.base_url)
        _, q4kl_error = await pull_all(ollama, serve.base_url, f"{REPO}:Q4_K_L")
        async with httpx.AsyncClient(base_url=servers.ui_url, timeout=120.0) as client:
            await open_ready(client)
            first = await chat_once(client, [{"role": "user", "content": PROMPT}])
            reply = "".join(line.get("message", {}).get("content", "") for line in first[2] if isinstance(line, dict))
            second = await chat_once(
                client,
                [
                    {"role": "user", "content": PROMPT},
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": "Again, one word."},
                ],
            )
            missing = await client.post("/api/chat", json={"model": f"{REPO}:Q8_0", "messages": [{"role": "user", "content": "hi"}]})
            await client.delete("/api/session")
    finally:
        await transport.close_inner()
    (tmp_path / "g_02_exchanges.txt").write_text(
        "".join(f"{e.method} {e.path} → {e.status}\n{bytes(e.body)[-4000:].decode(errors='replace')}\n" for e in transport.exchanges)
        + "".join(f"relay {path}: {json.dumps(body, ensure_ascii=False)[:2000]}\n" for path, body in relay.bodies),
        encoding="utf-8",
    )

    # 量到的數字
    with_total = [line for line in pulled if "total" in line]
    last = pulled[-1] if pulled else None
    local_names = [m["name"] for m in local["models"]]
    chats = [first, second]
    finals = [c[2][-1] if c[2] else {} for c in chats]
    relayed = [body for path, body in relay.bodies if path == "/api/chat"]
    missing_code = missing.json().get("code") if missing.headers.get("content-type", "").startswith("application/json") else None
    leaks = caplog.text.count(PROMPT) + stored_count(db_path, PROMPT)
    report.checks.update(
        {
            "則1": pull_error is None and last == {"status": "success"} and bool(with_total),
            "則2": MODEL in local_names,
            "則3": q4kl_error == "OLLAMA_PULL_FAILED",
            "則4": all(c[0] == 200 and c[1].startswith("application/x-ndjson") for c in chats) and all(f.get("done") is True for f in finals),
            "則5": all(int(f.get("eval_count") or 0) > 0 and int(f.get("eval_duration") or 0) > 0 for f in finals),
            "則6": len(relayed) >= 2 and len(relayed[1]["messages"]) == 3,
            "則7": missing.status_code == 404 and missing_code == "OLLAMA_NOT_FOUND",
            "則8": leaks == 0,
        }
    )
    report.numbers[:0] = [
        f"臨時 ollama serve 版本 {serve.version}(127.0.0.1 port {serve.port})",
        f"pull {MODEL}:{len(pulled)} 筆、帶 total 的 {len(with_total)} 筆"
        f"(最後 total {with_total[-1].get('total') if with_total else '—'}),最後一筆 {json.dumps(last, ensure_ascii=False)},丟出 {pull_error or '無'}",
        f"list_local_models {local_names}",
        f"Q4_K_L 丟出 {q4kl_error or '無'}",
        *(
            f"第 {i} 次對話 {c[0]} {c[1]},{len(c[2])} 行,最後一行 done={f.get('done')}、"
            f"eval_count={f.get('eval_count')}、eval_duration={f.get('eval_duration')}"
            for i, (c, f) in enumerate(zip(chats, finals, strict=True), start=1)
        ),
        f"臨時 serve 收到 /api/chat {len(relayed)} 次,第二次 messages {len(relayed[1]['messages']) if len(relayed) >= 2 else '—'} 則",
        f"沒下載的 Q8_0:{missing.status_code} {missing_code}",
        f"日誌與 SQLite 檔裡 {PROMPT!r} {leaks} 次",
        f"往 Ollama 的往返:測試直接 {len(transport.exchanges)} 個、後端 {len(app_transport.exchanges)} 個;Colab 呼叫 create {len(world.calls('create_session'))}、stop {len(world.calls('stop_session'))}",
    ]

    # Assert(則9 在 report fixture 收尾時斷言)
    failed = [name for name in (f"則{i}" for i in range(1, 9)) if not report.checks[name]]
    assert not failed, ";".join(report.numbers)
