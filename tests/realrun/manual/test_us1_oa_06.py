"""US1-OA-06(tasks.md T127):UI 登入走一次真的 Google OAuth,後端寫出的 token.json 讓 colab CLI 讀得懂。

使用者在場時另跑(plan.md Q101、Q108),不沿用 P9 複製來的授權:另開一個新的暫存目錄,主機上直接跑後端
(UI 127.0.0.1:8780、Ollama 相容端點 127.0.0.1:11436;P6 不碰 11434)。不開 Colab 執行環境,0 compute units。

執行:`uv run pytest -m realrun -s tests/realrun/manual/test_us1_oa_06.py`,照畫面上的指示在瀏覽器操作。
判定者:使用者判定則1(30 秒內顯示已登入)、則4 的畫面與則5;腳本判定則2、則3 與則4 的回應代碼。
token.json 只記長度與 sha256 前 8 碼;整個暫存目錄(含這次登入得到的授權)在案例結束時刪除(P8)。
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from realrun.conftest import (
    PREPARE_DATA,
    REPO_ROOT,
    UI_PORT,
    OLLAMA_PORT,
    fingerprint,
    mask_urls,
    parse_usage,
    write_measurement,
)

LOGIN_WAIT_SECONDS = 15 * 60
INVALID_CODE = "4/cgb-test-invalid"
UI = f"http://127.0.0.1:{UI_PORT}"


class Backend:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.data = root / "data"
        self.colab_dir = self.data / "colab-cli"
        self.log = root / "backend.log"
        self.process: subprocess.Popen[bytes] | None = None

    def env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            HOME=str(self.home),  # 後端呼叫的 colab 只讀這個 HOME 底下的授權,不碰桌機的 ~/.config/colab-cli/
            CGB_LISTEN_HOST="127.0.0.1",
            CGB_UI_PORT=str(UI_PORT),
            CGB_OLLAMA_PORT=str(OLLAMA_PORT),
            CGB_DB_PATH=str(self.data / "cgb.sqlite3"),
            CGB_COLAB_CONFIG_DIR=str(self.colab_dir),
            CGB_SSH_IDENTITY_PATH=str(self.data / "ssh" / "id_ed25519"),
            CGB_DATA_DIR=str(self.data),
        )
        return env

    def prepare(self) -> None:
        (self.home / ".config").mkdir(mode=0o700, parents=True)
        self.data.mkdir(mode=0o700)
        (self.home / ".config" / "colab-cli").symlink_to(self.colab_dir)
        result = subprocess.run(
            ["sh", str(PREPARE_DATA)], env=self.env(), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60
        )
        assert result.returncode == 0, f"prepare-data.sh 失敗:{mask_urls(result.stderr)[-300:]}"
        log = self.colab_dir / "colab.log"
        assert log.is_symlink() and os.readlink(log) == os.devnull, "colab.log 沒有指向 /dev/null(P8)"

    def start(self) -> None:
        out = self.log.open("ab")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "cgb"], env=self.env(), cwd=REPO_ROOT, stdin=subprocess.DEVNULL, stdout=out, stderr=out
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{UI}/api/auth", timeout=2).status_code == 200:
                    return
            except httpx.TransportError:
                time.sleep(0.3)
        raise AssertionError("後端 30 秒內沒有起來")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()


@pytest.fixture
def backend() -> Iterator[Backend]:
    root = Path(tempfile.mkdtemp(prefix="cgb-realrun-oa06-"))
    b = Backend(root)
    try:
        b.prepare()
        b.start()
        yield b
    finally:
        b.stop()
        shutil.rmtree(root, ignore_errors=True)


def say(text: str) -> None:
    print(f"\n>>> {text}", flush=True)


def test_us1_oa_06_真的_google_登入後_cli_讀得到授權(backend: Backend) -> None:
    # 當:使用者在自己的瀏覽器開連結、登入、貼回授權碼
    say(f"請在瀏覽器打開 {UI}/login.html ,按「取得授權連結」、登入 Google、把授權碼貼回登入頁送出。")
    started = time.monotonic()
    status: dict = {}
    while time.monotonic() - started < LOGIN_WAIT_SECONDS:
        status = httpx.get(f"{UI}/api/auth", timeout=5).json()
        if status.get("state") == "logged_in":
            break
        time.sleep(1)
    logged_in_after = time.monotonic() - started
    say(f"後端在 {logged_in_after:.0f} 秒後回報 state={status.get('state')}")

    # 則2:token.json 存在,權限 0600(只記長度與 sha256 前 8 碼)
    token = backend.colab_dir / "token.json"
    exists = token.is_file()
    mode = oct(token.stat().st_mode & 0o777) if exists else "—"
    size, digest = fingerprint(token) if exists else (0, "—")

    # 則3:CLI 讀得到後端寫的授權檔(R2)
    usage = subprocess.run(
        ["colab", "usage"], env=backend.env(), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120
    )
    parsed = parse_usage(usage.stdout) if usage.returncode == 0 else None

    # 則4:再取一次連結,貼回錯的授權碼
    flow = httpx.post(f"{UI}/api/auth/authorizations", timeout=30)
    flow_id = flow.json().get("flowId")
    invalid = httpx.post(f"{UI}/api/auth/authorizations/{flow_id}/code", json={"code": INVALID_CODE}, timeout=60)
    invalid_code = invalid.json().get("code")
    say(
        f"請在登入頁再按一次「取得授權連結」,在授權碼欄貼上 {INVALID_CODE} 送出,"
        "看畫面是否顯示登入失敗與原因、「重新取得授權連結」能不能按(則4 畫面、則5 由你判定)。"
    )
    # 等使用者看完畫面:主 agent 建立信號檔後才收掉後端(最多等 LOGIN_WAIT_SECONDS)
    done = Path(os.environ.get("CGB_REALRUN_DONE_FILE", str(backend.root / "done")))
    say(f"畫面看完後建立信號檔:{done}")
    waited = time.monotonic()
    while not done.exists() and time.monotonic() - waited < LOGIN_WAIT_SECONDS:
        time.sleep(1)

    rule2 = exists and mode == "0o600"
    rule3 = parsed is not None
    rule4 = invalid.status_code >= 400 and invalid_code == "OAUTH_INVALID_GRANT"
    numbers = (
        f"logged_in 偵測於 {logged_in_after:.0f} 秒;token.json 存在={exists}、權限 {mode}、長度 {size}、sha256 {digest};"
        f"colab usage exit {usage.returncode}、三行={'有' if rule3 else '沒有'};"
        f"錯誤授權碼:HTTP {invalid.status_code}、code {invalid_code}"
    )
    write_measurement(
        "US1-OA-06",
        "T127",
        numbers,
        "則1 30 秒內顯示已登入(使用者判定);則2 0600;則3 三行用量;則4 OAUTH_INVALID_GRANT;則5 可重新取得(使用者判定)",
        rule2 and rule3 and rule4 if status.get("state") == "logged_in" else False,
        "則1、則4 畫面、則5 由使用者判定,見對話紀錄",
    )
    assert status.get("state") == "logged_in", f"{LOGIN_WAIT_SECONDS // 60} 分鐘內沒有登入"
    assert rule2, f"token.json 存在={exists}、權限 {mode}"
    assert rule3, f"colab usage 讀不到用量(exit {usage.returncode}):{mask_urls(usage.stderr).strip()[-200:]}"
    assert rule4, f"錯誤授權碼回 HTTP {invalid.status_code}、code {invalid_code}"
