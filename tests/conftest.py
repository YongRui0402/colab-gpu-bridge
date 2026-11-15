"""全部測試共用的 fixture(tasks.md T007;testplan.md § 使用者故事 1 的預設資料;plan.md Q95、Q97、Q99)。

- `db_path`:每個測試一個暫存 SQLite 檔
- `fake_clock`:可推進的假時鐘;`test_timeouts`:縮短的時限;名稱前綴 `cgb-test-`
- `ollama_server`、`fakes`:假 Ollama 伺服器與五個轉接層替身(`FakeTunnel`、`FakeRemoteOllama` 接到假伺服器)
- `make_app` / `app_pair`:以上面這些呼叫 `create_app`;`make_app()` 可以用同一個 SQLite 檔與同一份替身重建(後端重新啟動)
- `ui_client`、`ollama_client`:`httpx.ASGITransport` 的用戶端(會跑 app 的 lifespan)
- `live_servers`:測試行程內的 uvicorn,UI 與 Ollama 相容端點各一個 127.0.0.1 隨機 port(Q97);
  `start_live_servers(pair, ui_port, ollama_port)` 以指定的 port 起(跨端點驗收用 8781、11437,Q99)
- `fake_cli`:`PATH` 前面加上 `tests/fixtures/bin`、`HOME` 指到暫存資料夾,並寫好假執行檔的劇本與紀錄檔路徑
"""

import asyncio
import json
import os
import socket
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from cgb.app import AppPair, Timeouts, create_app
from cgb.server import Servers
from fakes import (
    FakeColabControl,
    FakeGoogleOAuth,
    FakeHuggingFaceHub,
    FakeModelLibrary,
    FakeOllamaServer,
    FakeRemoteOllama,
    FakeTunnel,
)

TESTS_DIR = Path(__file__).resolve().parent
FAKE_BIN_DIR = TESTS_DIR / "fixtures" / "bin"
LIBRARY_FIXTURES_DIR = TESTS_DIR / "fixtures" / "library"

TEST_NAME_PREFIX = "cgb-test-"
TEST_TIMEOUTS = Timeouts(
    open_total=3.0,
    health_interval=0.2,
    health_timeout=0.3,
    reconnect_limit=2.0,
    reconnect_backoff=(0.0, 0.05, 0.1, 0.2),
    reconnect_interval=0.3,
    tunnel_ready=1.0,
)
DEFAULT_CLOCK_START = datetime(2026, 11, 9, 9, 0, 0, tzinfo=UTC)
_CLOCK_POLL_SECONDS = 0.005


# ---------------------------------------------------------------- 收集順序


# ---------------------------------------------------------------- P6 守門(005 plan Q77)
# 桌機 127.0.0.1:11434 是使用者自己的 Ollama,測試一律不連過去。任何往那裡的連線都擋下並記下來,
# 由 `_no_local_ollama` 讓那個測試失敗:只擋不記的話,程式接住連線錯誤後可能往別的路走(例如去安裝),看不出來。
_P6_PORT = 11434
_P6_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
_p6_hits: list[tuple[str, int]] = []
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex


def _is_local_ollama(address: object) -> bool:
    return isinstance(address, tuple) and len(address) >= 2 and address[1] == _P6_PORT and address[0] in _P6_HOSTS


def _guarded_connect(self: socket.socket, address: object) -> None:
    if _is_local_ollama(address):
        _p6_hits.append(address[:2])  # type: ignore[index]
        raise ConnectionRefusedError("P6 守門:測試不連使用者自己的 Ollama(127.0.0.1:11434)")
    _original_connect(self, address)  # type: ignore[arg-type]


def _guarded_connect_ex(self: socket.socket, address: object) -> int:
    if _is_local_ollama(address):
        _p6_hits.append(address[:2])  # type: ignore[index]
        return 111  # ECONNREFUSED
    return _original_connect_ex(self, address)  # type: ignore[arg-type]


socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _no_local_ollama() -> Iterator[None]:
    before = len(_p6_hits)
    yield
    if len(_p6_hits) > before:
        pytest.fail(f"P6:這個測試連了使用者自己的 Ollama {_p6_hits[before:]},測試一律不碰 127.0.0.1:11434")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """`tests/e2e/` 的測試排到最後。

    pytest-playwright 的同步 API 在第一個 e2e 測試之後,整個 session 都在主執行緒留著一個執行中的事件迴圈,
    之後的 pytest-asyncio 測試會因 `Runner.run() cannot be called from a running event loop` 失敗。
    """
    e2e_dir = TESTS_DIR / "e2e"
    items.sort(key=lambda item: Path(str(item.path)).is_relative_to(e2e_dir))


# ---------------------------------------------------------------- 時鐘與時限


class FakeClock:
    """可推進的假時鐘(實作 `cgb.app.Clock`)。

    時間照真實時間往前走(縮短的時限靠真的等待),另外可以由測試 `advance()` 往前跳或 `set()` 指定現在的時間;
    `sleep()` 等到這個時鐘的 monotonic 到了目標就醒,所以 `advance()` 會讓等待中的 sleep 提早結束。
    執行緒安全:uvicorn 在別的執行緒時,測試照樣可以推進。
    """

    def __init__(self, start: datetime = DEFAULT_CLOCK_START) -> None:
        self._lock = threading.Lock()
        self._start = start
        self._real_origin = time.monotonic()
        self._offset = 0.0

    def _elapsed(self) -> float:
        with self._lock:
            return time.monotonic() - self._real_origin + self._offset

    def now(self) -> datetime:
        return self._start + timedelta(seconds=self._elapsed())

    def monotonic(self) -> float:
        return self._elapsed()

    async def sleep(self, seconds: float) -> None:
        target = self.monotonic() + max(seconds, 0.0)
        while True:
            remaining = target - self.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, _CLOCK_POLL_SECONDS))

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._offset += seconds

    def set(self, when: datetime) -> None:
        """把現在的時間設成 `when`(只能往後,monotonic 不倒退)。"""
        delta = (when - self.now()).total_seconds()
        if delta < 0:
            raise ValueError("假時鐘不能倒退")
        self.advance(delta)


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def test_timeouts() -> Timeouts:
    return TEST_TIMEOUTS


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "cgb.sqlite3"


# ---------------------------------------------------------------- 替身


@dataclass
class Fakes:
    colab: FakeColabControl
    tunnel: FakeTunnel
    remote_ollama: FakeRemoteOllama
    model_library: FakeModelLibrary
    google_oauth: FakeGoogleOAuth
    huggingface: FakeHuggingFaceHub
    server: FakeOllamaServer

    def as_kwargs(self) -> dict[str, Any]:
        return {
            "colab": self.colab,
            "tunnel": self.tunnel,
            "remote_ollama": self.remote_ollama,
            "model_library": self.model_library,
            "google_oauth": self.google_oauth,
            "huggingface": self.huggingface,
        }


@pytest.fixture
def ollama_server() -> Iterator[FakeOllamaServer]:
    server = FakeOllamaServer().start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def fakes(ollama_server: FakeOllamaServer) -> Fakes:
    return Fakes(
        colab=FakeColabControl(),
        tunnel=FakeTunnel(ollama_server),
        remote_ollama=FakeRemoteOllama(ollama_server),
        model_library=FakeModelLibrary(),
        google_oauth=FakeGoogleOAuth(),
        huggingface=FakeHuggingFaceHub(),
        server=ollama_server,
    )


# ---------------------------------------------------------------- app


@pytest.fixture
def make_app(db_path: Path, fake_clock: FakeClock, test_timeouts: Timeouts, fakes: Fakes) -> Callable[..., AppPair]:
    """以縮短的時限、假時鐘與前綴 `cgb-test-` 建立 app;關鍵字參數可覆寫任何一個注入點。"""

    def build(**overrides: Any) -> AppPair:
        kwargs: dict[str, Any] = {
            "db_path": db_path,
            "clock": fake_clock,
            "name_prefix": TEST_NAME_PREFIX,
            "timeouts": test_timeouts,
            **fakes.as_kwargs(),
        }
        kwargs.update(overrides)
        return create_app(**kwargs)

    return build


@pytest.fixture
def app_pair(make_app: Callable[..., AppPair]) -> AppPair:
    return make_app()


@pytest.fixture
async def asgi_clients(app_pair: AppPair) -> AsyncIterator[tuple[httpx.AsyncClient, httpx.AsyncClient]]:
    """UI 與 Ollama 相容端點的 ASGI 用戶端;兩個 app 的 lifespan 在用戶端存在期間都在跑。"""
    async with AsyncExitStack() as stack:
        for app in (app_pair.ui, app_pair.ollama):
            await stack.enter_async_context(app.router.lifespan_context(app))
        ui = await stack.enter_async_context(
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app_pair.ui), base_url="http://cgb-ui.test")
        )
        ollama = await stack.enter_async_context(
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app_pair.ollama), base_url="http://cgb-ollama.test")
        )
        yield ui, ollama


@pytest.fixture
def ui_client(asgi_clients: tuple[httpx.AsyncClient, httpx.AsyncClient]) -> httpx.AsyncClient:
    return asgi_clients[0]


@pytest.fixture
def ollama_client(asgi_clients: tuple[httpx.AsyncClient, httpx.AsyncClient]) -> httpx.AsyncClient:
    return asgi_clients[1]


# ---------------------------------------------------------------- 測試行程內的 uvicorn


def _bind(port: int) -> socket.socket:
    # proto 要明寫 TCP:asyncio 只對 proto 為 TCP 的連線設 TCP_NODELAY,否則回應的標頭與第一段之間會被 Nagle 多等約 40 毫秒
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(128)
    return sock


class LiveServers:
    """兩個 uvicorn 伺服器跑在同一個背景執行緒的同一個事件迴圈裡(和正式的單一後端行程一樣共用記憶體)。"""

    START_TIMEOUT = 10.0
    # 瀏覽器開著的 SSE 連線不會自己結束;停下時最多等這麼久就關掉(後端重新啟動的案例會在頁面開著時停)
    GRACEFUL_SHUTDOWN = 0.5

    def __init__(self, pair: AppPair, ui_port: int = 0, ollama_port: int = 0) -> None:
        self.pair = pair
        self._sockets = (_bind(ui_port), _bind(ollama_port))
        self.ui_port = self._sockets[0].getsockname()[1]
        self.ollama_port = self._sockets[1].getsockname()[1]
        # 和 `python -m cgb` 走同一個 `cgb.server`(Q113);socket 事先綁好,host 與 port 只是記錄
        self._servers = Servers(
            pair,
            host="127.0.0.1",
            ui_port=self.ui_port,
            ollama_port=self.ollama_port,
            log_level="warning",
            access_log=False,
            timeout_graceful_shutdown=self.GRACEFUL_SHUTDOWN,
        )
        self._thread = threading.Thread(target=self._run, name="cgb-live-servers", daemon=True)
        self._error: BaseException | None = None

    @property
    def ui_url(self) -> str:
        return f"http://127.0.0.1:{self.ui_port}"

    @property
    def ollama_url(self) -> str:
        return f"http://127.0.0.1:{self.ollama_port}"

    def _run(self) -> None:
        try:
            asyncio.run(self._servers.serve(sockets=self._sockets))
        except BaseException as error:  # 讓測試端看得到伺服器起不來的原因
            self._error = error

    def start(self) -> "LiveServers":
        self._thread.start()
        deadline = time.monotonic() + self.START_TIMEOUT
        while not self._servers.started:
            if self._error is not None or not self._thread.is_alive():
                raise RuntimeError(f"測試行程內的 uvicorn 起不來:{self._error!r}")
            if time.monotonic() > deadline:
                raise RuntimeError("測試行程內的 uvicorn 在時限內沒有起來")
            time.sleep(0.01)
        return self

    def stop(self) -> None:
        self._servers.stop()
        self._thread.join(timeout=self.START_TIMEOUT)
        for sock in self._sockets:
            sock.close()
        if self._thread.is_alive():
            raise RuntimeError("測試行程內的 uvicorn 沒有在時限內停下")


@pytest.fixture
def start_live_servers() -> Iterator[Callable[..., LiveServers]]:
    """以指定的 app 與 port 起 uvicorn(port 0 是隨機);測試結束時全部停下。"""
    started: list[LiveServers] = []

    def start(pair: AppPair, ui_port: int = 0, ollama_port: int = 0) -> LiveServers:
        servers = LiveServers(pair, ui_port=ui_port, ollama_port=ollama_port).start()
        started.append(servers)
        return servers

    try:
        yield start
    finally:
        for servers in reversed(started):
            servers.stop()


@pytest.fixture
def live_servers(app_pair: AppPair, start_live_servers: Callable[..., LiveServers]) -> LiveServers:
    """整合測試用:127.0.0.1 隨機 port(Q97)。"""
    return start_live_servers(app_pair)


# ---------------------------------------------------------------- 假執行檔


class FakeCli:
    """假 `colab`、`ssh` 的劇本與紀錄(見 `tests/fixtures/bin/colab` 的說明)。"""

    def __init__(self, root: Path) -> None:
        self.home = root / "home"
        self.script_path = root / "fake-script.json"
        self.log_path = root / "fake-log.jsonl"
        self.home.mkdir(parents=True, exist_ok=True)
        self.script({})

    def script(self, script: dict[str, Any]) -> None:
        """整份換掉劇本,並把「第幾次呼叫」的計數歸零。"""
        self.script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
        Path(f"{self.script_path}.count.json").unlink(missing_ok=True)

    def calls(self, program: str | None = None) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        records = [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines() if line]
        return [r for r in records if program is None or r["program"] == program]


@pytest.fixture
def fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeCli:
    cli = FakeCli(tmp_path / "fake-cli")
    monkeypatch.setenv("PATH", f"{FAKE_BIN_DIR}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("HOME", str(cli.home))
    monkeypatch.setenv("CGB_FAKE_SCRIPT", str(cli.script_path))
    monkeypatch.setenv("CGB_FAKE_LOG", str(cli.log_path))
    return cli
