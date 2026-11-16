"""007 G-01(tasks.md T072):替身與真的轉接層一致,讀不到目錄時回 502/504、不回 500(testplan.md § 4.2)。

做法照 plan.md § 待決問題 Q10 (a):本系統以替身開工作階段到就緒(`ColabWorld`),遠端 Ollama 改用真的
`RemoteOllama`,以 `RecordingTransport(get_only=True)` 注入(所有請求經 `check_port`,不是 GET 就擋下)。
通道的 `baseUrl` 固定指到 `free_loopback_port()` 取的一個 127.0.0.1 port P,依序換 P 上的東西:
(0)開啟時的 `GET /api/version` 由測試行程內的臨時 http 伺服器回 `{"version": …}`(開啟要先驗版本,不量);
(1)P 上沒有人在聽;(2)臨時 http 伺服器對任何路徑回 200 與 `<html>不是 JSON</html>`;
(3)只 `accept` 連線、不回任何位元組的 socket。每種情況各呼叫一次 `GET /api/models` 與
`POST /api/models/preload` `{"name":"qwen2.5:3b"}`,(3)照 `LIST_TIMEOUT` 等 10 秒。
結果附加到 `specs/007-catalog-error-chat-keep/measurements.md`;沒過門檻照樣寫進去,由 Checkpoint 列為待決問題。

護欄:不開 Colab、不花錢、不需本人在場;不起 `ollama serve`,不對 127.0.0.1:11434 送任何請求;
P 與本系統的 port 都由 `free_loopback_port()` 取,避開 11434~11436、8780 與 e2e 的 8781、11437;
臨時伺服器與 socket 只聽 127.0.0.1,收尾關閉並確認 P 已釋放;只寫 pytest 暫存資料夾。
`tests/realrun/` 的 autouse P2 預算閘(要 `-m realrun` 並執行 `colab usage`)在這裡換成不做事的同名 fixture。
判定者:腳本;樣本:一次實跑(未用於調整)。
執行:`uv run pytest -m realrun_local tests/realrun/test_007_g_01.py -q -p no:cacheprovider`
"""

import socket
import threading
import time
from collections.abc import Callable
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from cgb.adapters.remote_ollama import LIST_TIMEOUT, RemoteOllama
from cgb.app import AppPair
from integration.test_api_session import ColabWorld, open_ready
from realrun.conftest import REPO_ROOT
from realrun.helpers import RecordingTransport, free_loopback_port, port_listening, run

pytestmark = pytest.mark.realrun_local

CASE, TASK = "G-01", "T072"
MODEL = "qwen2.5:3b"
VERSION = "0.40.15"
NOT_JSON = "<html>不是 JSON</html>"
E2E_PORTS = frozenset({8781, 11437})
MEASUREMENTS = REPO_ROOT / "specs" / "007-catalog-error-chat-keep" / "measurements.md"
# 門檻(testplan G-01 則1~則6):(情況, 端點) → (狀態碼, code)
EXPECTED = {
    ("1", "GET /api/models"): (502, "OLLAMA_UNREACHABLE"),
    ("1", "POST /api/models/preload"): (502, "OLLAMA_UNREACHABLE"),
    ("2", "GET /api/models"): (502, "OLLAMA_BAD_RESPONSE"),
    ("2", "POST /api/models/preload"): (502, "OLLAMA_BAD_RESPONSE"),
    ("3", "GET /api/models"): (504, "OLLAMA_TIMEOUT"),
    ("3", "POST /api/models/preload"): (504, "OLLAMA_TIMEOUT"),
}
SITUATION = {"1": "沒有人在聽的 port", "2": "回 200 與 HTML 的 http 伺服器", "3": "只 accept、不回位元組的 socket"}


@pytest.fixture(autouse=True)
def _p2_budget_gate() -> None:
    """覆寫 `tests/realrun/conftest.py` 的同名 autouse fixture:本機實跑不開 Colab,不需要 P2 預算與 `colab usage`。"""


def loopback_port() -> int:
    while True:
        port = free_loopback_port()
        if port not in E2E_PORTS:
            return port


# ---------------------------------------------------------------- P 上的東西


class _Handler(BaseHTTPRequestHandler):
    mode = "version"

    def do_GET(self) -> None:  # noqa: N802 - http.server 的命名
        if type(self).mode == "version" and self.path == "/api/version":
            body, kind = f'{{"version": "{VERSION}"}}'.encode(), "application/json"
        else:
            body, kind = NOT_JSON.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET  # noqa: N815 - 照 GET 回;RecordingTransport 本來就不讓 POST 出去

    def log_message(self, *args: Any) -> None:
        return None


class HttpOnPort:
    """P 上的臨時 http 伺服器;`mode` 是 `version`(開啟時驗版本)或 `html`(情況 2)。"""

    def __init__(self, port: int, mode: str) -> None:
        handler = type("Handler", (_Handler,), {"mode": mode})
        ThreadingHTTPServer.allow_reuse_address = True
        self.server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class SilentSocket:
    """P 上只 `accept`、留著連線、不回任何位元組(情況 3)。"""

    def __init__(self, port: int) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(16)
        self.sock.settimeout(0.2)
        self.accepted: list[socket.socket] = []
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self) -> None:
        while not self.stopping.is_set():
            try:
                conn, _ = self.sock.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            self.accepted.append(conn)

    def close(self) -> None:
        self.stopping.set()
        self.thread.join(timeout=5)
        for conn in self.accepted:
            conn.close()
        self.sock.close()


# ---------------------------------------------------------------- 量測紀錄


def append_measurement(lines: list[str]) -> None:
    if not MEASUREMENTS.exists():
        MEASUREMENTS.write_text(
            "# 量測紀錄:007-catalog-error-chat-keep\n\n"
            "由各案例的測試附加(tasks.md T072);護欄見 `testplan.md` § 4.2 各案例的「副作用與護欄」。\n",
            encoding="utf-8",
        )
    title = f"{CASE}({TASK})替身與真的轉接層一致:讀不到目錄時回 502/504、不回 500"
    with MEASUREMENTS.open("a", encoding="utf-8") as f:
        f.write(f"\n## {title}\n\n" + "".join(f"- {line}\n" for line in lines))


def call(ui: httpx.Client, endpoint: str) -> tuple[int, str | None, float]:
    started = time.monotonic()
    if endpoint == "GET /api/models":
        response = ui.get("/api/models")
    else:
        response = ui.post("/api/models/preload", json={"name": MODEL})
    seconds = time.monotonic() - started
    try:
        code = response.json().get("code")
    except ValueError:
        code = None
    return response.status_code, code, seconds


# ---------------------------------------------------------------- 案例


def test_g01_讀不到目錄的三種網路失敗都回_502_或_504_不回_500(
    fakes: Any, make_app: Callable[..., AppPair], start_live_servers: Callable[..., Any]
) -> None:
    # Arrange:替身開工作階段到就緒,通道的 baseUrl 指到 P;開啟時的版本確認由 P 上的臨時伺服器回答
    target = loopback_port()
    ColabWorld(fakes)
    fakes.tunnel.open_tunnel.side_effect(
        lambda *a, **k: {
            "sessionName": k["session_name"],
            "baseUrl": f"http://127.0.0.1:{target}",
            "remoteOllamaVersion": VERSION,
            "connectedAt": "2026-11-16T09:00:00Z",
            "elapsedMs": 0,
        }
    )
    recording = RecordingTransport(get_only=True)
    pair = make_app(remote_ollama=RemoteOllama(transport=recording), public_ollama_port=loopback_port())
    servers = start_live_servers(pair, ollama_port=loopback_port())
    results: dict[tuple[str, str], tuple[int, str | None, float]] = {}
    cleanup: list[str] = []
    on_port: HttpOnPort | SilentSocket | None = HttpOnPort(target, "version")
    try:
        run(_open(servers.ui_url))
        on_port.close()
        on_port = None

        with httpx.Client(base_url=servers.ui_url, timeout=30.0) as ui:
            # Act:(1)沒有人在聽
            assert not port_listening(target), "情況 1 開始前 P 還有人在聽"
            for endpoint in ("GET /api/models", "POST /api/models/preload"):
                results[("1", endpoint)] = call(ui, endpoint)
            # (2)回 200 與 HTML
            on_port = HttpOnPort(target, "html")
            for endpoint in ("GET /api/models", "POST /api/models/preload"):
                results[("2", endpoint)] = call(ui, endpoint)
            on_port.close()
            # (3)只 accept、不回位元組
            on_port = SilentSocket(target)
            for endpoint in ("GET /api/models", "POST /api/models/preload"):
                results[("3", endpoint)] = call(ui, endpoint)
    finally:
        if on_port is not None:
            on_port.close()
        run(recording.close_inner())
        released = not port_listening(target)
        cleanup.append(f"P(127.0.0.1 上的臨時 port)收尾後{'已釋放' if released else '仍有人在聽'}")

    # Assert:記下數字與門檻的比較(沒過也照實寫進 measurements.md)
    verdicts = []
    for key, (status, code) in EXPECTED.items():
        got_status, got_code, seconds = results[key]
        ok = (got_status, got_code) == (status, code)
        extra = f",耗時 {seconds:.2f} 秒" if key[0] == "3" else ""
        verdicts.append(
            f"({key[0]}){SITUATION[key[0]]} `{key[1]}`:{got_status} `{got_code}`{extra}"
            f"(門檻 {status} `{code}`,{'過' if ok else '沒過'})"
        )
    list_seconds = results[("3", "GET /api/models")][2]
    timing_ok = LIST_TIMEOUT <= list_seconds <= LIST_TIMEOUT + 2
    count_500 = sum(1 for status, _, _ in results.values() if status == 500)
    all_ok = all((results[k][0], results[k][1]) == v for k, v in EXPECTED.items()) and timing_ok and count_500 == 0
    sent = sorted({f"{e.method} {e.path}" for e in recording.exchanges})
    append_measurement(
        [
            f"日期:{datetime.now():%Y-%m-%d %H:%M};環境:桌機 Ubuntu,本系統測試行程內 uvicorn,替身開工作階段、遠端 Ollama 用真的 `RemoteOllama`(`RecordingTransport(get_only=True)`)",
            *verdicts,
            f"(3)`GET /api/models` 送出後 {list_seconds:.2f} 秒回應(門檻 {LIST_TIMEOUT:g}~{LIST_TIMEOUT + 2:g} 秒,{'過' if timing_ok else '沒過'})",
            f"六次回應裡 500 的次數:{count_500}(門檻 0,SC-001,{'過' if count_500 == 0 else '沒過'})",
            f"轉接層實際送出的請求:{'、'.join(f'`{s}`' for s in sent)};收到回應的往返 {len(recording.exchanges)} 次(連不上與逾時的沒有回應,不留紀錄)",
            f"**判定:{'全部過門檻' if all_ok else '有沒過門檻的項目,列為待決問題'}**",
            "判定者:腳本;樣本:一次實跑(未用於調整)",
            "收尾:" + ";".join(cleanup),
        ]
    )
    assert released, cleanup[-1]


async def _open(ui_url: str) -> None:
    async with httpx.AsyncClient(base_url=ui_url, timeout=30.0) as ui:
        await open_ready(ui)

