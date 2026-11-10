"""全域:容器的健康檢查不碰 Ollama 相容端點的 HTTP(testplan.md § G-08;spec.md § NFR-012;plan.md Q89)。

接縫:以子行程跑 `deploy/healthcheck.py`(容器的 `cgb-healthcheck`);
測試行程在 127.0.0.1 隨機 port 起一個假 UI(`GET /api/session` 回設定的狀態碼)與一個假 Ollama 相容端點
(只 accept 連線、記下收到的位元組)。
"""

import os
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "deploy" / "healthcheck.py"


class FakeUi:
    def __init__(self) -> None:
        self.status = 200
        self.requests: list[tuple[str, str]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802(BaseHTTPRequestHandler 的命名)
                fake.requests.append(("GET", self.path))
                body = b'{"state": "none"}'
                self.send_response(fake.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class FakeOllamaPort:
    """只 accept 連線、讀到對方關閉為止,記下收到的位元組數。"""

    READ_TIMEOUT = 5.0

    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.received = 0
        self.connections = 0
        self.readers: list[threading.Thread] = []
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.connections += 1
            reader = threading.Thread(target=self._read, args=(conn,), daemon=True)
            self.readers.append(reader)
            reader.start()

    def _read(self, conn: socket.socket) -> None:
        conn.settimeout(self.READ_TIMEOUT)
        with conn:
            try:
                while chunk := conn.recv(4096):
                    self.received += len(chunk)
            except OSError:
                pass

    def wait_readers(self) -> None:
        for reader in list(self.readers):
            reader.join(self.READ_TIMEOUT + 1)

    def stop(self) -> None:
        self.sock.close()


@pytest.fixture
def fake_ui() -> Iterator[FakeUi]:
    ui = FakeUi()
    try:
        yield ui
    finally:
        ui.stop()


@pytest.fixture
def fake_ollama_port() -> Iterator[FakeOllamaPort]:
    port = FakeOllamaPort()
    try:
        yield port
    finally:
        port.stop()


def run_healthcheck(ui: FakeUi, ollama: FakeOllamaPort) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("CGB_")}
    env.update(CGB_UI_PORT=str(ui.port), CGB_OLLAMA_PORT=str(ollama.port))
    return subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)


def test_健康檢查只問_UI_的狀態_Ollama_相容端點只連_TCP_不送位元組(fake_ui: FakeUi, fake_ollama_port: FakeOllamaPort) -> None:
    # Act
    healthy = run_healthcheck(fake_ui, fake_ollama_port)
    fake_ollama_port.wait_readers()
    requests_when_healthy = list(fake_ui.requests)
    fake_ui.status = 503
    unhealthy = run_healthcheck(fake_ui, fake_ollama_port)

    # Assert
    assert healthy.returncode == 0, healthy.stderr  # 則1
    assert fake_ollama_port.connections >= 1 and fake_ollama_port.received == 0  # 則2
    assert requests_when_healthy == [("GET", "/api/session")]  # 則3
    assert unhealthy.returncode != 0  # 則4
