"""全域:正式啟動路徑的請求紀錄(testplan.md § G-10;spec.md § NFR-010;plan.md Q199)。

接縫:以子行程跑 `python -m cgb`(正式的 `logging_setup.setup()` 與 `serve()`/`Servers`),收它的 stdout 與 stderr。
真的轉接層在這裡只會碰到 `tests/fixtures/bin` 的假 `colab`、`ssh`(劇本為空,一律 exit 2):
`PATH` 不含使用者的 `~/.local/bin`,`HOME` 與各資料路徑都是暫存資料夾,不碰真的 Colab 與 `~/.config/colab-cli/`。
"""

import http.client
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FAKE_BIN = REPO / "tests" / "fixtures" / "bin"
MODEL = "qwen2.5:0.5b"
PROMPT_MARKER = "cgb-test-prompt-不該出現在日誌"
START_TIMEOUT = 15.0


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def backend_env(root: Path, ui_port: int, ollama_port: int) -> dict[str, str]:
    home = root / "home"
    home.mkdir()
    (root / "fake-script.json").write_text("{}", encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith("CGB_")}
    env.update(
        PATH=f"{FAKE_BIN}{os.pathsep}/usr/bin{os.pathsep}/bin",
        HOME=str(home),
        CGB_FAKE_SCRIPT=str(root / "fake-script.json"),
        CGB_FAKE_LOG=str(root / "fake-log.jsonl"),
        CGB_LISTEN_HOST="127.0.0.1",
        CGB_UI_PORT=str(ui_port),
        CGB_OLLAMA_PORT=str(ollama_port),
        CGB_DB_PATH=str(root / "data" / "cgb.sqlite3"),
        CGB_COLAB_CONFIG_DIR=str(root / "data" / "colab-cli"),
        CGB_SSH_IDENTITY_PATH=str(root / "data" / "ssh" / "id_ed25519"),
        PYTHONUNBUFFERED="1",
    )
    (root / "data").mkdir()
    return env


def wait_ui_ready(process: subprocess.Popen[str], port: int) -> None:
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"後端行程提早結束,exit {process.returncode}")
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            conn.request("GET", "/api/session")
            if conn.getresponse().status == 200:
                conn.close()
                return
            conn.close()
        except OSError:
            pass
        time.sleep(0.1)
    raise AssertionError("後端行程在時限內沒有就緒")


def post_generate(port: int) -> tuple[int, int]:
    """送一次帶 prompt 標記的請求;交回(狀態碼,這條連線的用戶端 port)。"""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.connect()
    client_port = conn.sock.getsockname()[1]
    body = json.dumps({"model": MODEL, "prompt": PROMPT_MARKER, "stream": False})
    conn.request("POST", "/api/generate", body=body, headers={"Content-Type": "application/json"})
    status = conn.getresponse().status
    conn.close()
    return status, client_port


def test_正式啟動時請求紀錄輸出且含時間_沒有用戶端位址_路徑與_prompt(tmp_path: Path) -> None:
    # Arrange
    ui_port, ollama_port = free_port(), free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "cgb"],
        env=backend_env(tmp_path, ui_port, ollama_port),
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_ui_ready(process, ui_port)

        # Act
        status, client_port = post_generate(ollama_port)
        time.sleep(0.2)
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            out, err = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            out, err = process.communicate()
    output = out + err
    lines = output.splitlines()

    # Assert
    assert status == 503
    access = [line for line in lines if "cgb.ollama_compat.access_log" in line]
    assert len(access) == 1, output[-2000:]  # 則1
    assert MODEL in access[0] and "503" in access[0] and re.search(r"\d{2}:\d{2}:\d{2}", access[0]), access[0]  # 則1
    leaked = [line for line in lines if f":{client_port}" in line or "/api/generate" in line or PROMPT_MARKER in line]
    assert leaked == []  # 則2


# ---------------------------------------------------------------- G-10 則3(Q200)

# 子行程的進入點:正式的 `logging_setup.setup()` 加 `Servers`(預設的 log 設定),轉接層換成替身。
# 正式路徑的真轉接層開不到就緒的工作階段,轉送這一條只能這樣測(testplan.md § G-10)。
FORWARDING_DRIVER = """
import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
from cgb.logging_setup import setup
setup()
from cgb.app import create_app
from cgb.server import Servers
from fakes import FakeColabControl, FakeGoogleOAuth, FakeModelLibrary, FakeOllamaServer, FakeRemoteOllama, FakeTunnel, JsonReply
from integration.test_api_session import ColabWorld

db_path, ui_port, ollama_port, model = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
server = FakeOllamaServer().start()
server.add("POST", "/api/generate", JsonReply({"model": model, "response": "ok", "done": True}))
fakes = type("F", (), {})()
fakes.colab, fakes.tunnel, fakes.remote_ollama = FakeColabControl(), FakeTunnel(server), FakeRemoteOllama(server)
fakes.model_library, fakes.google_oauth, fakes.server = FakeModelLibrary(), FakeGoogleOAuth(), server
ColabWorld(fakes)
pair = create_app(db_path=db_path, colab=fakes.colab, tunnel=fakes.tunnel, remote_ollama=fakes.remote_ollama,
                  model_library=fakes.model_library, google_oauth=fakes.google_oauth)
print(json.dumps({"forward_port": server.port}), flush=True)
asyncio.run(Servers(pair, host="127.0.0.1", ui_port=ui_port, ollama_port=ollama_port).serve())
"""


def wait_ready_session(port: int) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", "/api/session", body=json.dumps({"runtimeType": {"gpu": "T4", "highMem": False}}),
                 headers={"Content-Type": "application/json"})
    status = conn.getresponse().status
    conn.close()
    assert status == 202, status
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/session")
        state = json.loads(conn.getresponse().read()).get("state")
        conn.close()
        if state == "ready":
            return
        time.sleep(0.05)
    raise AssertionError(f"工作階段在時限內沒有就緒(最後是 {state})")


def test_有轉送時輸出裡沒有_httpx_的請求行_沒有轉發位址與路徑(tmp_path: Path) -> None:
    # Arrange
    driver = tmp_path / "driver.py"
    driver.write_text(FORWARDING_DRIVER, encoding="utf-8")
    ui_port, ollama_port = free_port(), free_port()
    env = {key: value for key, value in os.environ.items() if not key.startswith("CGB_")}
    env.update(PYTHONUNBUFFERED="1", HOME=str(tmp_path), CGB_COLAB_CONFIG_DIR=str(tmp_path / "colab-cli"),
               CGB_SSH_IDENTITY_PATH=str(tmp_path / "ssh" / "id_ed25519"))
    process = subprocess.Popen(
        [sys.executable, str(driver), str(REPO / "tests"), str(tmp_path / "cgb.sqlite3"), str(ui_port), str(ollama_port), MODEL],
        env=env, cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        forward_port = json.loads(process.stdout.readline())["forward_port"]
        wait_ui_ready(process, ui_port)
        wait_ready_session(ui_port)

        # Act
        status, _ = post_generate(ollama_port)
        time.sleep(0.2)
    finally:
        process.send_signal(signal.SIGTERM)
        try:
            out, err = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            out, err = process.communicate()
    lines = (out + err).splitlines()

    # Assert
    assert status == 200, (out + err)[-2000:]
    assert any("cgb.ollama_compat.access_log" in line and "200" in line for line in lines), (out + err)[-2000:]
    leaked = [line for line in lines if "HTTP Request:" in line or f":{forward_port}" in line or "/api/generate" in line]
    assert leaked == []  # 則3
