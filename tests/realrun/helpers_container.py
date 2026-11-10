"""容器階段(P9 的第二段)共用的工具;護欄 P1–P9 仍由 `conftest.py` 的 `realrun` fixture 執行。

整個容器階段共用一個 `Stack`(模組層級的單例,`get_stack(realrun)` 第一次呼叫時起容器):
- compose 一律經 `realrun.compose()`(`-p cgb-test --env-file <暫存目錄>/.env`),`up` 帶 `--no-build`,沿用已建好的映像。
- 名稱前綴(P1):`compose.yaml` 沒有注入前綴的方法,這裡以 `COMPOSE_FILE` 環境變數多疊一份
  `tests/realrun/compose.cgb-test.yaml`(只設 `CGB_NAME_PREFIX=cgb-test-`)。`realrun.compose()` 繼承 `os.environ`,
  所以 `up`、`restart`、P3 的 `down` 都看得到這份設定;`.env` 仍只有那四個變數(P6、G-07)。
- 起來之後先做「預檢」:容器裡的 `CGB_NAME_PREFIX` 是 `cgb-test-`,而且 `python -m cgb` 有接上遠端 Ollama 與官方模型庫的轉接層,
  授權有效;沒過就不開任何執行環境(要開 Colab 的案例 skip,寫成未驗證),不需要 Colab 的案例照跑。
- 每次開啟或變更類型後,回傳的名稱不是 `cgb-test-` 開頭就立即結束那台、停下所有要開 Colab 的案例(P1 的第二道防線)。
- UI 用 127.0.0.1:8780,Ollama 相容端點用 127.0.0.1:11436;每個請求都先過 `check_port`(絕不連 11434)。
- G-05 要掃的東西:UI API 的每個回應、`/api/events` 的 SSE、P3 之前的 `docker compose logs`,原文存在 `<暫存目錄>/g05/`
  (0700 目錄、0600 檔,不印出、不遮蔽,免得藏在網址裡的 token 被遮掉而數不到);整批結束隨暫存目錄刪除。
"""

import contextlib
import json
import os
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from cgb.adapters.colab_cli import SESSION_LINE
from realrun.conftest import (
    OLLAMA_PORT,
    REALRUN_DIR,
    TEST_PREFIX,
    UI_PORT,
    check_model,
    check_port,
    mask_urls,
    parse_session_names,
    write_measurement,
)

UI = f"http://127.0.0.1:{UI_PORT}"
OLLAMA = f"http://127.0.0.1:{OLLAMA_PORT}"
IMAGE = "colab-gpu-bridge:0.1.0"
CONTAINER = "cgb-test-cgb-1"
OVERRIDE = REALRUN_DIR / "compose.cgb-test.yaml"
COMPOSE_FILES = os.pathsep.join(["compose.yaml", str(OVERRIDE.relative_to(REALRUN_DIR.parents[1]))])
ACTIVE = ("opening", "ready", "reconnecting", "ending")
TERMINAL = ("ended", "open_failed", "lost")
OPEN_DEADLINE = 330  # 開啟流程本身 5 分鐘(SC-001)再多等 30 秒
HEALTH_DEADLINE = 120
SMALL, LARGE = "qwen2.5:0.5b", "qwen2.5:7b"
for _model in (SMALL, LARGE):
    check_model(_model)

# 預檢:在容器裡讀環境變數與 `cgb.__main__` 的原始碼(不啟動任何東西)
PREFLIGHT = r"""
import json, os, tempfile
from cgb.__main__ import build_pair, read_settings
# 真的走一次正式組裝(資料庫指到暫存路徑,不碰正在跑的那份),看轉接層型別與名稱前綴
env = dict(os.environ, CGB_DB_PATH=os.path.join(tempfile.mkdtemp(), "preflight.sqlite3"))
state = build_pair(read_settings(env)).state
print(json.dumps({
    "prefix": state.name_prefix,
    "readsPrefix": state.name_prefix == os.environ.get("CGB_NAME_PREFIX"),
    "remoteOllamaWired": type(state.remote_ollama).__name__ == "RemoteOllama",
    "modelLibraryWired": type(state.model_library).__name__ == "ModelLibrary",
}))
"""


def now_utc() -> datetime:
    return datetime.now(UTC)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def private_file(path: Path) -> Path:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.close(fd)
    return path


class SseRecorder(threading.Thread):
    """持續訂閱 `/api/events`,原文附加到檔案(G-05);後端重啟時斷線就重接。"""

    def __init__(self, path: Path) -> None:
        super().__init__(name="cgb-realrun-sse", daemon=True)
        self.path = private_file(path)
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                with httpx.stream("GET", f"{UI}/api/events", timeout=httpx.Timeout(10, read=None)) as response:
                    with self.path.open("a", encoding="utf-8") as f:
                        for line in response.iter_lines():
                            f.write(line + "\n")
                            f.flush()
                            if self.stop_event.is_set():
                                return
            except httpx.HTTPError:
                pass
            self.stop_event.wait(2)

    def stop(self) -> None:
        self.stop_event.set()


class Stack:
    def __init__(self, realrun) -> None:
        self.realrun = realrun
        self.g05 = realrun.root / "g05"
        self.api_log = private_file(self.g05 / "api.txt")
        self.sse: SseRecorder | None = None
        self.colab_ok = False
        self.colab_reason = "還沒做預檢"
        self.state: dict[str, Any] = {}

    # ---- 起容器與預檢 ----

    def start(self) -> None:
        os.environ["COMPOSE_FILE"] = COMPOSE_FILES
        image = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True, text=True, timeout=30)
        if image.returncode != 0:
            raise AssertionError(f"找不到映像 {IMAGE}(容器階段沿用已建好的映像,不 build)")
        # 先在主機跑一次 colab sessions:讓 sessions.json 等檔由主機使用者建立;容器(root)先建的話是 0600、
        # 主機的 colab 讀不到,之後的 P2、P3 都會失敗(P9「主機階段先跑」的理由;單獨重跑容器案例時踩到)
        self.realrun.colab("sessions", timeout=90)
        up = self.realrun.compose("up", "-d", "--no-build", timeout=240)
        self.realrun.record_raw("compose", f"$ docker compose up -d --no-build (exit {up.returncode})\n{up.stdout}{up.stderr}\n")
        if up.returncode != 0:
            raise AssertionError(f"docker compose up 失敗(exit {up.returncode}):{mask_urls(up.stderr).strip()[-300:]}")
        healthy_after = self.wait_healthy(HEALTH_DEADLINE)
        if healthy_after is None:
            raise AssertionError(f"容器 {HEALTH_DEADLINE} 秒內沒有變成 healthy")
        self.sse = SseRecorder(self.g05 / "sse.txt")
        self.sse.start()
        self.preflight()

    def preflight(self) -> None:
        result = self.docker_exec("python", "-c", PREFLIGHT)
        try:
            info = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            self.colab_reason = f"預檢腳本沒有結果(exit {result.returncode})"
            return
        problems = []
        if info.get("prefix") != TEST_PREFIX or not info.get("readsPrefix"):
            problems.append(
                f"容器沒有以 {TEST_PREFIX} 為名稱前綴(CGB_NAME_PREFIX={info.get('prefix')!r}、程式讀取={info.get('readsPrefix')})"
            )
        if not info.get("remoteOllamaWired"):
            problems.append("python -m cgb 沒有接上遠端 Ollama 的轉接層(remote_ollama=None)")
        if not info.get("modelLibraryWired"):
            problems.append("python -m cgb 沒有接上官方模型庫的轉接層(model_library=None)")
        auth = self.ui("GET", "/api/auth").json()
        if auth.get("state") != "logged_in":
            problems.append(f"GET /api/auth 的 state 是 {auth.get('state')!r},不是 logged_in")
        self.colab_ok = not problems
        self.colab_reason = ";".join(problems) or "預檢通過"
        self.realrun.record_raw("compose", f"預檢:{self.colab_reason}\n")

    def require_colab(self, case: str, task: str) -> None:
        self.require_cases([(case, task)])

    def require(self, case: str, task: str, *keys: str) -> None:
        self.require_cases([(case, task)], *keys)

    def require_cases(self, cases: list[tuple[str, str]], *keys: str) -> None:
        """預檢沒過,或前面的案例沒留下 `keys`:每個案例寫一列未驗證,然後 skip。"""
        if not self.colab_ok:
            reason = f"沒有開執行環境:{self.colab_reason}"
        else:
            missing = [k for k in keys if not self.state.get(k)]
            if not missing:
                return
            reason = f"前置沒成立:{'、'.join(missing)}"
        for case, task in cases:
            write_measurement(case, task, "—", "—", None, reason)
        pytest.skip(reason + ",列為未驗證")

    def wait_healthy(self, deadline: float) -> float | None:
        started = time.monotonic()
        while time.monotonic() - started <= deadline:
            status = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Health.Status}}", CONTAINER], capture_output=True, text=True, timeout=30
            ).stdout.strip()
            if status == "healthy":
                return time.monotonic() - started
            time.sleep(2)
        return None

    # ---- 請求 ----

    def _log(self, method: str, url: str, status: int | str, body: str) -> None:
        with self.api_log.open("a", encoding="utf-8") as f:
            f.write(f"{now_utc().isoformat()} {method} {url} → {status}\n{body}\n")

    def ui(self, method: str, path: str, json_body: Any = None, timeout: float = 30) -> httpx.Response:
        check_port(UI_PORT)
        response = httpx.request(method, f"{UI}{path}", json=json_body, timeout=timeout)
        self._log(method, path, response.status_code, response.text)
        return response

    def ollama(self, method: str, path: str, json_body: Any = None, timeout: float = 300) -> tuple[httpx.Response, float]:
        """經 Ollama 相容端點(11436)送一個請求;回(回應, 秒)。"""
        check_port(OLLAMA_PORT)
        if isinstance(json_body, dict) and "model" in json_body:
            check_model(json_body["model"])
        started = time.monotonic()
        response = httpx.request(method, f"{OLLAMA}{path}", json=json_body, timeout=timeout)
        elapsed = time.monotonic() - started
        self._log(method, f"[11436]{path}", response.status_code, response.text)
        return response, elapsed

    def session(self) -> dict[str, Any] | None:
        try:
            return self.ui("GET", "/api/session", timeout=10).json()
        except (httpx.HTTPError, ValueError):
            return None

    def poll_session(
        self, until: Callable[[dict[str, Any]], bool], deadline: float, interval: float = 5
    ) -> tuple[dict[str, Any] | None, float, list[tuple[float, str]]]:
        """每 `interval` 秒讀一次 `GET /api/session`,直到 `until` 成立或超過 `deadline` 秒;回(最後一次, 秒, [(秒, state)])。"""
        started = time.monotonic()
        samples: list[tuple[float, str]] = []
        last = None
        while True:
            elapsed = time.monotonic() - started
            current = self.session()
            samples.append((round(elapsed, 1), current.get("state") if current else "讀不到"))
            if current is not None:
                last = current
                if until(current):
                    return current, elapsed, samples
            if elapsed > deadline:
                return last, elapsed, samples
            time.sleep(interval)

    # ---- 工作階段 ----

    def guard_name(self, name: str | None) -> None:
        """P1 第二道防線:本系統開出的名稱不是 cgb-test- 開頭,就立即結束它並停下所有要開 Colab 的案例。"""
        if name and name.startswith(TEST_PREFIX):
            return
        self.colab_ok = False
        self.colab_reason = f"本系統開出的名稱 {name!r} 不是 {TEST_PREFIX} 開頭,已立即結束"
        self.ui("DELETE", "/api/session")
        self.poll_session(lambda s: s.get("state") in TERMINAL, 120)
        pytest.fail(self.colab_reason, pytrace=False)

    def ensure_no_active(self) -> str | None:
        """還有占著位子的工作階段(前一個案例沒收好)就先結束它;回傳被結束的名稱。"""
        current = self.session() or {}
        if current.get("state") not in ACTIVE:
            return None
        self.ui("DELETE", "/api/session")
        self.poll_session(lambda s: s.get("state") in TERMINAL, 120)
        return current.get("name")

    def open(self, gpu: str = "T4", high_mem: bool = False) -> tuple[dict[str, Any] | None, float]:
        """經 UI API 開一台並等到就緒或失敗;回(最後的工作階段, 從受理起的秒數)。"""
        response = self.ui("POST", "/api/session", {"runtimeType": {"gpu": gpu, "highMem": high_mem}})
        if response.status_code != 202:
            pytest.fail(f"POST /api/session 回 {response.status_code}:{response.text[:200]}", pytrace=False)
        self.guard_name(response.json().get("name"))
        last, elapsed, _ = self.poll_session(lambda s: s.get("state") in ("ready", *TERMINAL), OPEN_DEADLINE, 2)
        return last, elapsed

    # ---- 主機上的 colab 與 docker ----

    def colab_rows(self, label: str) -> list[dict[str, str]] | None:
        """主機上 `HOME=<暫存目錄>/home colab sessions`(和容器共用 `<暫存目錄>/data/colab-cli`),依轉接層的 regex 解析。"""
        result = self.realrun.colab("sessions", timeout=90)
        raw = f"$ colab sessions (exit {result.returncode}) [{label}]\n{result.stdout}{result.stderr}\n"
        self.realrun.record_raw("container_colab", raw)
        if result.returncode != 0:
            return None
        rows = []
        for line in result.stdout.splitlines():
            m = SESSION_LINE.match(line)
            if m:
                rows.append({"name": m.group(1), "hardware": m.group(3), "shape": m.group(4)})
        if not rows and parse_session_names(result.stdout):
            return None
        return rows

    def test_rows(self, label: str) -> list[dict[str, str]] | None:
        rows = self.colab_rows(label)
        return None if rows is None else [r for r in rows if r["name"].startswith(TEST_PREFIX)]

    def wait_gone(self, name: str, deadline: float, interval: float = 5) -> float | None:
        """每 `interval` 秒執行一次 `colab sessions`,回傳不再列出 `name` 的秒數;超過 `deadline` 回 None。"""
        started = time.monotonic()
        while time.monotonic() - started <= deadline:
            rows = self.colab_rows("回讀")
            if rows is not None and all(r["name"] != name for r in rows):
                return time.monotonic() - started
            time.sleep(interval)
        return None

    def docker_exec(self, *cmd: str, stdin: str | None = None, timeout: float = 120) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "exec", *(["-i"] if stdin is not None else []), CONTAINER, *cmd],
            input=stdin,
            stdin=None if stdin is not None else subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def save_compose_logs(self, name: str) -> Path:
        """`docker compose logs` 原文存進 `<暫存目錄>/g05/`(0600,不印出);P3 會移除容器,之前要先存。"""
        result = self.realrun.compose("logs", "--no-color", "--timestamps", timeout=120)
        path = private_file(self.g05 / name)
        with path.open("a", encoding="utf-8") as f:
            f.write(result.stdout + result.stderr)
        return path

    def stop_recording(self) -> None:
        if self.sse is not None:
            self.sse.stop()
            self.sse.join(timeout=15)


_stack: Stack | None = None


def get_stack(realrun) -> Stack:
    """整個容器階段共用的一份;第一次呼叫時起容器並預檢。容器由整批結束時的 P3(`compose down`)收掉。"""
    global _stack
    if _stack is None:
        stack = Stack(realrun)
        stack.start()
        _stack = stack
    return _stack


def verdict(case: str, task: str, checks: dict[str, bool], numbers: str, threshold: str, extra: list[str]) -> None:
    failed = [k for k, ok in checks.items() if not ok]
    note = ";".join((["沒過:" + "、".join(failed)] if failed else []) + extra)
    write_measurement(case, task, numbers, threshold, not failed, note)
    assert not failed, note


def generate_body(model: str, num_predict: int, **extra: Any) -> dict[str, Any]:
    return {
        "model": model,
        "prompt": "你好",
        "stream": False,
        "options": {"num_predict": num_predict, "seed": 1, "temperature": 0},
        **extra,
    }


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


@contextlib.contextmanager
def browser_page() -> Iterator[Any]:
    """自己開一個 headless Chromium 分頁。

    不用 pytest-playwright 的 `page` fixture:它以 session 範圍的 `browser_name` 參數化,
    pytest 會把用到它的測試排到一起,打亂 P9 的執行順序。
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            yield browser.new_page()
        finally:
            browser.close()
