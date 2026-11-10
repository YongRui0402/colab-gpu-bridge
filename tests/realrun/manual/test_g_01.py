"""G-01(tasks.md T297):家中區網的裝置不需要登入就能用 UI 與 Ollama 相容端點,外網連不到(NFR-009)。

使用者在場時另跑(plan.md Q108),不在 P9 那一批。`docker compose -p cgb-test` 起在桌機,`.env` 的
`CGB_BIND_ADDR=0.0.0.0`(只有本案例暫時這樣,其他案例用 127.0.0.1)、UI 8780、Ollama 相容端點 11436;沒有工作階段。
不開 Colab 執行環境,0 compute units;不改路由器,只觀察;外網用手機的行動網路連公網位址(P5:不在區網內連公網 IP)。

執行:`CGB_REALRUN_LAN_IP=<桌機區網 IP> CGB_REALRUN_PUBLIC_HOST=<解析到公網 IP 的名稱> uv run pytest -m realrun -s tests/realrun/manual/test_g_01.py`。
判定者:使用者判定則1–則4(區網裝置看到首頁與 503、行動網路連不上);腳本另從桌機對區網位址補一次則2 的回應內容。
案例結束時 `docker compose -p cgb-test down`,暫存目錄刪除;`CGB_BIND_ADDR` 只寫在這個暫存的 `.env`,不必改回。
"""

import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from realrun.conftest import COMPOSE_PROJECT, OLLAMA_PORT, REPO_ROOT, UI_PORT, mask_urls, write_measurement

WAIT_SECONDS = 15 * 60
NO_SESSION_TEXT = "沒有可用的工作階段"


class Stack:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.data = root / "data"
        self.env_file = root / ".env"

    def write_env(self) -> None:
        self.data.mkdir(mode=0o700)
        content = (
            f"CGB_HOST_DATA={self.data}\n"
            "CGB_BIND_ADDR=0.0.0.0\n"
            f"CGB_HOST_UI_PORT={UI_PORT}\n"
            f"CGB_HOST_OLLAMA_PORT={OLLAMA_PORT}\n"
        )
        fd = os.open(self.env_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, content.encode())
        finally:
            os.close(fd)

    def compose(self, *args: str, timeout: float = 300) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "compose", "-p", COMPOSE_PROJECT, "--env-file", str(self.env_file), *args],
            cwd=REPO_ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
        )


@pytest.fixture
def stack() -> Iterator[Stack]:
    root = Path(tempfile.mkdtemp(prefix="cgb-realrun-g01-"))
    s = Stack(root)
    try:
        s.write_env()
        up = s.compose("up", "-d", "--no-build")
        assert up.returncode == 0, f"compose up 失敗:{mask_urls(up.stderr)[-400:]}"
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"http://127.0.0.1:{UI_PORT}/api/session", timeout=2).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(1)
        else:
            raise AssertionError("容器 90 秒內沒有起來")
        yield s
    finally:
        s.compose("down", timeout=180)
        # 容器以 root 寫入 data/;刪不掉的部分交給 docker 以 root 清掉
        shutil.rmtree(root, ignore_errors=True)
        if root.exists():
            subprocess.run(
                ["docker", "run", "--rm", "-v", f"{root}:/x", "python:3.12-slim", "sh", "-c", "rm -rf /x/* /x/.env"],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=120,
            )
            shutil.rmtree(root, ignore_errors=True)


def say(text: str) -> None:
    print(f"\n>>> {text}", flush=True)


def test_g_01_區網不需登入可用_外網連不到(stack: Stack) -> None:
    lan_ip = os.environ["CGB_REALRUN_LAN_IP"]
    public_host = os.environ["CGB_REALRUN_PUBLIC_HOST"]

    # 腳本從桌機對區網位址補看一次則2 的回應(真正的判定是另一台裝置)
    reply = httpx.get(f"http://{lan_ip}:{OLLAMA_PORT}/api/version", timeout=10)
    from_desktop = f"HTTP {reply.status_code}、含「{NO_SESSION_TEXT}」={NO_SESSION_TEXT in reply.text}"

    say(
        f"區網:請用手機連家裡 Wi-Fi,打開 http://{lan_ip}:{UI_PORT}/ (則1:不需登入就看到首頁),"
        f"再打開 http://{lan_ip}:{OLLAMA_PORT}/api/version (則2:應該看到「{NO_SESSION_TEXT}」)。"
    )
    say(
        f"外網:把手機的 Wi-Fi 關掉改用行動網路,打開 http://{public_host}:{UI_PORT}/ 與 "
        f"http://{public_host}:{OLLAMA_PORT}/api/version (則3、則4:都應該連不上)。"
    )
    done = Path(os.environ.get("CGB_REALRUN_DONE_FILE", str(stack.root / "done")))
    say(f"看完後建立信號檔:{done}")
    waited = time.monotonic()
    while not done.exists() and time.monotonic() - waited < WAIT_SECONDS:
        time.sleep(1)
    verdict = done.read_text(encoding="utf-8").strip() if done.exists() else ""

    write_measurement(
        "G-01",
        "T297",
        f"桌機對區網位址 {OLLAMA_PORT}/api/version:{from_desktop};使用者回報:{verdict or '(沒有回報)'}",
        "則1 區網不需登入看到首頁;則2 區網對 11436 收到 503 與沒有可用的工作階段;則3、則4 行動網路連不上 8780、11436",
        None if not verdict else verdict.startswith("過"),
        "則1–則4 由使用者判定",
    )
    assert reply.status_code == 503 and NO_SESSION_TEXT in reply.text, from_desktop
    assert verdict.startswith("過"), f"使用者判定:{verdict or '沒有回報'}"
