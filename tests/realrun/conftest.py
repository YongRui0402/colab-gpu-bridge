"""實跑案例的共同護欄 P1–P9(tasks.md T008;testplan.md § 實跑案例的共同護欄;plan.md Q101、Q108)。

只在 `-m realrun` 時生效:`tests/realrun/` 底下的測試都會被加上 `realrun` marker(預設的 `-m "not realrun"` 會排除它們),
fixture 在沒有選到 realrun 時一律 skip,不建立暫存目錄、不讀授權檔、不執行任何指令。

`realrun` fixture(整個 session 一份)依序做:
1. P6:`mktemp -d` 的 `<暫存目錄>`;`HOME=<暫存目錄>/home`,其 `.config/colab-cli` 是指向 `<暫存目錄>/data/colab-cli` 的符號連結;
   `<暫存目錄>/.env` 只有 `CGB_HOST_DATA`、`CGB_HOST_UI_PORT=8780`、`CGB_HOST_OLLAMA_PORT=11436`、`CGB_BIND_ADDR=127.0.0.1`
2. P8:遮蔽器先以已知的假 endpoint 驗過;執行任何 `colab` 指令前以 `CGB_DATA_DIR=<暫存目錄>/data` 跑一次 `deploy/prepare-data.sh`
3. P9(Q101 (b)):把桌機既有的 `~/.config/colab-cli/token.json` 複製到 `<暫存目錄>/data/colab-cli/token.json`(0600),
   兩邊只比對長度與 sha256 前 8 碼,不印內容,不複製 `sessions.json`
4. P9、P2:以 `HOME=<暫存目錄>/home colab usage` 確認授權有效(沒過就停下整批),同時記下開始時的三行
每個案例開始前(autouse)照 P2 檢查已用時間與餘額;超過就做 P3、其餘案例 skip 並列為未驗證。
session 結束(含中途中止)一定做 P3,做完之後才刪除 `<暫存目錄>`(G-07、G-05 在 P3 之後還要用到它)。

給案例用的:`realrun.colab(...)`(強制 P1、P2 的 GPU、P4)、`realrun.env()`、`realrun.record_raw()`(先遮蔽網址)、
`realrun.p3_cleanup()`、`adapter_session_name()`、`write_measurement()`、`mask_urls()`。
"""

import atexit
import hashlib
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest
from _pytest.mark.expression import Expression

REPO_ROOT = Path(__file__).resolve().parents[2]
REALRUN_DIR = Path(__file__).resolve().parent
PREPARE_DATA = REPO_ROOT / "deploy" / "prepare-data.sh"
MEASUREMENTS = REPO_ROOT / "specs" / "001-session-model-catalog" / "measurements.md"
FAKE_BIN_DIR = REPO_ROOT / "tests" / "fixtures" / "bin"

# P1 名稱
TEST_PREFIX = "cgb-test-"
# P2 預算
BUDGET_SECONDS = 60 * 60
BUDGET_UNITS_DROP = 1.8
ALLOWED_GPU = "T4"
# P6 port(桌機 11434 是使用者自己的 Ollama,不送任何請求)
UI_PORT = 8780
OLLAMA_PORT = 11436
FORBIDDEN_PORTS = frozenset({11434})
COMPOSE_PROJECT = "cgb-test"
# P7 模型
ALLOWED_MODELS = ("qwen2.5:0.5b", "qwen2.5:7b", "qwen2.5:cgb-test-nonexistent")
# P3 殘留行程
RESIDUAL_SSH_MARK = "ProxyCommand=colab ssh --proxy-mode -s cgb-test-"

COLAB_TIMEOUT = 60
USAGE_PATTERNS = (
    re.compile(r"^Current balance: (-?\d+\.\d{2}) compute units$"),
    re.compile(r"^Usage rate: (-?\d+\.\d{2})/hr$"),
    re.compile(r"^Active assignments: (\d+)$"),
)
SESSION_LINE = re.compile(r"^\[([^\]]+)\] ")


# ---------------------------------------------------------------- 只在 -m realrun 時生效


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """`tests/realrun/` 的測試一律加上 realrun marker,讓預設的 `-m "not realrun"` 排除它們。"""
    for item in items:
        if Path(str(item.path)).is_relative_to(REALRUN_DIR):
            item.add_marker(pytest.mark.realrun)


def realrun_selected(config: pytest.Config) -> bool:
    expr = config.getoption("markexpr", "") or ""
    if not expr:
        return False
    return Expression.compile(expr).evaluate(lambda name, **kwargs: name == "realrun")


# ---------------------------------------------------------------- P8 遮蔽


URL_PATTERN = re.compile(r"\b(?:https?|wss?)://[^\s'\"<>|]+")
# `colab sessions` 的資料行:`[<名稱>] <endpoint> | Hardware: …`;endpoint 不一定帶 scheme,整欄換掉
SESSION_ENDPOINT = re.compile(r"^(\[[^\]]+\] )(\S+)( \| Hardware:)", re.MULTILINE)
MASK = "<網址>"


def mask_urls(text: str) -> str:
    """錄下原始輸出前把網址與 `colab sessions` 的 endpoint 欄換成 `<網址>`。"""
    text = SESSION_ENDPOINT.sub(lambda m: f"{m.group(1)}{MASK}{m.group(3)}", text)
    return URL_PATTERN.sub(MASK, text)


def self_check_mask() -> None:
    """P8:遮蔽器先以一個已知的假 endpoint 驗過;沒過就不能錄任何輸出。"""
    fake_endpoint = "https://cgb-test-fake-endpoint.example/tun/m/abc123?authuser=0&token=fake-proxy-token-0001"
    bare_endpoint = "cgb-test-fake-bare-endpoint-0001"
    samples = {
        f"[cgb-test-0001] {fake_endpoint} | Hardware: T4 | Shape: Standard | Variant: GPU":
            f"[cgb-test-0001] {MASK} | Hardware: T4 | Shape: Standard | Variant: GPU",
        f"[?] {bare_endpoint} | Hardware: T4 | Shape: High-RAM | Variant: GPU":
            f"[?] {MASK} | Hardware: T4 | Shape: High-RAM | Variant: GPU",
        f"[colab] To authorize colab-cli, visit this URL: {fake_endpoint}\n":
            f"[colab] To authorize colab-cli, visit this URL: {MASK}\n",
        "connect to wss://cgb-test-fake-endpoint.example/ws failed":
            f"connect to {MASK} failed",
    }
    for raw, expected in samples.items():
        masked = mask_urls(raw)
        leaked = [s for s in ("cgb-test-fake-endpoint", "fake-proxy-token", bare_endpoint) if s in masked]
        if masked != expected or leaked:
            raise AssertionError(f"遮蔽器自我檢查沒過(第 {list(samples).index(raw) + 1} 個樣本),不能錄下任何輸出")


# ---------------------------------------------------------------- P9 授權


def fingerprint(path: Path) -> tuple[int, str]:
    """只回長度與 sha256 前 8 碼,不回內容。"""
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()[:8]


def copy_token(source: Path, dest: Path) -> tuple[int, str]:
    """把 token.json 複製成 0600,兩邊的長度與 sha256 前 8 碼一致才算成功;不印內容、不複製 sessions.json。"""
    if not source.is_file():
        raise FileNotFoundError(f"找不到桌機既有的授權檔:{source}")
    dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, source.read_bytes())
    finally:
        os.close(fd)
    os.chmod(dest, 0o600)
    src_fp, dst_fp = fingerprint(source), fingerprint(dest)
    if src_fp != dst_fp:
        raise AssertionError(f"複製後不一致:來源 長度 {src_fp[0]}、sha256 {src_fp[1]};複本 長度 {dst_fp[0]}、sha256 {dst_fp[1]}")
    return dst_fp


# ---------------------------------------------------------------- P1 名稱、P2 預算


def adapter_session_name(now: datetime | None = None) -> str:
    """P1:轉接層層級的實跑名稱 `cgb-test-<YYYYmmddHHMM>-adapter`。"""
    return f"{TEST_PREFIX}{(now or datetime.now()).strftime('%Y%m%d%H%M')}-adapter"


def parse_usage(stdout: str) -> tuple[float, float, int] | None:
    values: list[str | None] = [None, None, None]
    for line in stdout.splitlines():
        for i, pattern in enumerate(USAGE_PATTERNS):
            if m := pattern.match(line.strip()):
                values[i] = m.group(1)
    if None in values:
        return None
    return float(values[0]), float(values[1]), int(values[2])  # type: ignore[arg-type]


def parse_session_names(stdout: str) -> list[str]:
    names = []
    for line in stdout.splitlines():
        if line.startswith("[colab] "):
            continue
        if m := SESSION_LINE.match(line):
            names.append(m.group(1))
    return names


@dataclass
class Budget:
    started_at: float
    start_balance: float
    exceeded_reason: str | None = None
    skipped: list[str] = field(default_factory=list)

    def over(self, now: float, balance: float | None) -> str | None:
        if now - self.started_at > BUDGET_SECONDS:
            return f"已用 {int((now - self.started_at) // 60)} 分鐘,超過 60 分鐘"
        if balance is None:
            return "讀不到目前的餘額,無法確認預算"
        # CLI 的數字一律兩位小數;先四捨五入,免得 100.00 - 98.20 算成 1.7999… 而漏判
        drop = round(self.start_balance - balance, 2)
        if drop >= BUDGET_UNITS_DROP:
            return f"餘額比開始時少 {drop:.2f},達到 {BUDGET_UNITS_DROP}"
        return None


# ---------------------------------------------------------------- 量測結果


def write_measurement(
    case_id: str,
    task_id: str,
    numbers: str,
    threshold: str,
    passed: bool | None,
    note: str = "",
    path: Path = MEASUREMENTS,
) -> None:
    """把一個案例的量測結果附加到 measurements.md;`passed` 是 None 表示未驗證(例如 P2 跳過)。內容一律先遮蔽網址。"""
    if not path.exists():
        path.write_text(
            "# 實跑量測結果:Colab GPU 工作階段管理與模型目錄\n\n"
            "由 `tests/realrun/conftest.py` 的 `write_measurement` 寫入(tasks.md T008);護欄見 `testplan.md` § 實跑案例的共同護欄。\n\n"
            "| 時間 | 案例 | 任務 | 數字 | 門檻 | 結果 | 備註 |\n"
            "|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    verdict = "未驗證" if passed is None else ("過" if passed else "沒過")

    def cell(text: str) -> str:
        return mask_urls(text).replace("|", "\\|").replace("\n", "<br>")

    row = [datetime.now().astimezone().isoformat(timespec="seconds"), case_id, task_id, numbers, threshold, verdict, note]
    with path.open("a", encoding="utf-8") as f:
        f.write("| " + " | ".join(cell(c) for c in row) + " |\n")


# ---------------------------------------------------------------- 實跑環境


class GuardViolation(AssertionError):
    """案例要做的事違反了 P1–P9。"""


class Realrun:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.data = root / "data"
        self.colab_dir = self.data / "colab-cli"
        self.raw_dir = root / "raw"
        self.env_file = root / ".env"
        self.budget: Budget | None = None
        self.token_fingerprint: tuple[int, str] | None = None
        self._p3_done_at_end = False

    # ---- 準備 ----

    def prepare_dirs(self) -> None:
        (self.home / ".config").mkdir(mode=0o700, parents=True)
        self.data.mkdir(mode=0o700)
        self.raw_dir.mkdir(mode=0o700)
        (self.home / ".config" / "colab-cli").symlink_to(self.colab_dir)
        self.write_env_file()

    def write_env_file(self) -> None:
        content = (
            f"CGB_HOST_DATA={self.data}\n"
            f"CGB_HOST_UI_PORT={UI_PORT}\n"
            f"CGB_HOST_OLLAMA_PORT={OLLAMA_PORT}\n"
            "CGB_BIND_ADDR=127.0.0.1\n"
        )
        fd = os.open(self.env_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, content.encode())
        finally:
            os.close(fd)

    def run_prepare_data(self) -> None:
        """P8:執行任何 colab 指令之前跑一次,讓 colab.log 指到 /dev/null(Q59)。"""
        env = self.env()
        env.update(
            CGB_DATA_DIR=str(self.data),
            CGB_COLAB_CONFIG_DIR=str(self.colab_dir),
            CGB_SSH_IDENTITY_PATH=str(self.data / "ssh" / "id_ed25519"),
        )
        result = subprocess.run(
            ["sh", str(PREPARE_DATA)], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise AssertionError(f"prepare-data.sh 失敗(exit {result.returncode}):{mask_urls(result.stderr).strip()[-300:]}")
        log = self.colab_dir / "colab.log"
        if not (log.is_symlink() and os.readlink(log) == os.devnull):
            raise AssertionError("prepare-data.sh 之後 colab.log 不是指向 /dev/null 的符號連結")

    # ---- 執行指令 ----

    def env(self) -> dict[str, str]:
        """在主機上直接跑的實跑子行程的環境:HOME 指到暫存目錄,PATH 不含假執行檔(要用真的 colab 與 ssh)。"""
        env = dict(os.environ)
        env["HOME"] = str(self.home)
        env["COLAB_CLI_REQUEST_TIMEOUT"] = str(COLAB_TIMEOUT)
        env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if Path(p) != FAKE_BIN_DIR)
        for name in ("CGB_FAKE_SCRIPT", "CGB_FAKE_LOG"):
            env.pop(name, None)
        return env

    def colab(self, *args: str, timeout: float = 300) -> subprocess.CompletedProcess[str]:
        """以真的 colab 執行一個子指令;stdin 接 /dev/null。強制 P1(stop 只帶 cgb-test-)、P2(只用 T4)、P4(不掛 Drive)。"""
        check_colab_args(args)
        return subprocess.run(
            ["colab", *args], env=self.env(), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout
        )

    def compose(self, *args: str, timeout: float = 300) -> subprocess.CompletedProcess[str]:
        """P6:compose 一律 `-p cgb-test --env-file <暫存目錄>/.env`。"""
        return subprocess.run(
            ["docker", "compose", "-p", COMPOSE_PROJECT, "--env-file", str(self.env_file), *args],
            cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def record_raw(self, name: str, text: str) -> Path:
        """P8:把原始輸出先遮蔽網址再存進 `<暫存目錄>/raw/`(0600);整批結束後隨暫存目錄刪除。"""
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        path = self.raw_dir / f"{safe}.txt"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, mask_urls(text).encode())
        finally:
            os.close(fd)
        return path

    # ---- P9 授權、P2 預算 ----

    def read_usage(self) -> tuple[tuple[float, float, int] | None, str]:
        result = self.colab("usage", timeout=COLAB_TIMEOUT + 30)
        self.record_raw("usage", f"$ colab usage (exit {result.returncode})\n{result.stdout}{result.stderr}\n")
        parsed = parse_usage(result.stdout) if result.returncode == 0 else None
        err_lines = mask_urls(result.stderr).strip().splitlines()
        return parsed, err_lines[-1] if err_lines else ""

    def start_budget(self) -> tuple[float, float, int]:
        usage, last_err = self.read_usage()
        if usage is None:
            raise AssertionError(f"複製來的授權無效或讀不到用量,停下(P9,不改用其他授權):{last_err}")
        self.budget = Budget(started_at=time.monotonic(), start_balance=usage[0])
        return usage

    def check_budget(self, case: str) -> None:
        assert self.budget is not None
        if self.budget.exceeded_reason is None:
            usage, _ = self.read_usage()
            reason = self.budget.over(time.monotonic(), usage[0] if usage else None)
            if reason is not None:
                self.budget.exceeded_reason = reason
                self.p3_cleanup()
        if self.budget.exceeded_reason is not None:
            self.budget.skipped.append(case)
            pytest.skip(f"P2 預算:{self.budget.exceeded_reason};跳過,列為未驗證")

    # ---- P3 收尾 ----

    def p3_cleanup(self) -> list[str]:
        """不論成敗都做;回傳需要使用者處理的問題(空清單表示收乾淨)。可以重複呼叫。"""
        problems: list[str] = []

        listed = self.colab("sessions", timeout=COLAB_TIMEOUT + 30)
        self.record_raw("p3", f"$ colab sessions (exit {listed.returncode})\n{listed.stdout}{listed.stderr}\n")
        if listed.returncode != 0:
            problems.append("colab sessions 失敗,無法確認有沒有遺留的 cgb-test- 執行環境,請到 Colab 網頁確認")
        else:
            for name in [n for n in parse_session_names(listed.stdout) if n.startswith(TEST_PREFIX)]:
                stopped = self.colab("stop", "-s", name, timeout=COLAB_TIMEOUT + 30)
                self.record_raw("p3", f"$ colab stop -s {name} (exit {stopped.returncode})\n{stopped.stdout}{stopped.stderr}\n")
                again = self.colab("sessions", timeout=COLAB_TIMEOUT + 30)
                self.record_raw("p3", f"$ colab sessions (exit {again.returncode})\n{again.stdout}{again.stderr}\n")
                if again.returncode != 0 or name in parse_session_names(again.stdout):
                    problems.append(f"{name} 在 colab stop 之後仍在(或無法回讀),請到 Colab 網頁手動結束")

        try:
            down = self.compose("down", timeout=180)
            self.record_raw("p3", f"$ docker compose -p {COMPOSE_PROJECT} down (exit {down.returncode})\n{down.stdout}{down.stderr}\n")
            if down.returncode != 0:
                problems.append(f"docker compose -p {COMPOSE_PROJECT} down 失敗(exit {down.returncode})")
        except FileNotFoundError:
            problems.append("找不到 docker,無法確認 cgb-test 的容器已停下")

        for pid in residual_ssh_pids():
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(0.5)
        remaining = residual_ssh_pids()
        if remaining:
            problems.append(f"仍有命令列含 `{RESIDUAL_SSH_MARK}` 的行程:{remaining}")
        return problems

    def finish(self) -> list[str]:
        """整批結束:最後一次 P3,之後刪除暫存目錄(含複製來的授權與錄下的輸出)。"""
        if self._p3_done_at_end:
            return []
        self._p3_done_at_end = True
        try:
            problems = self.p3_cleanup()
        finally:
            if self.budget is not None and self.budget.skipped:
                for case in self.budget.skipped:
                    write_measurement(case, "—", "—", "—", None, f"P2 預算:{self.budget.exceeded_reason}")
            shutil.rmtree(self.root, ignore_errors=True)
        return problems


def check_colab_args(args: Sequence[str]) -> None:
    if not args:
        raise GuardViolation("colab 沒有子指令")
    sub = args[0]
    if sub == "drivemount" or any("google.colab.drive" in a for a in args):
        raise GuardViolation("P4:不執行 colab drivemount、不 import google.colab.drive")
    if sub in ("stop", "new", "ssh", "exec"):
        names = [args[i + 1] for i, a in enumerate(args[:-1]) if a in ("-s", "--session")]
        if not names or not all(n.startswith(TEST_PREFIX) and n != "?" for n in names):
            raise GuardViolation(f"P1:colab {sub} 只能帶 {TEST_PREFIX} 開頭的名稱")
    if "--gpu" in args:
        gpu = args[list(args).index("--gpu") + 1] if list(args).index("--gpu") + 1 < len(args) else ""
        if gpu != ALLOWED_GPU:
            raise GuardViolation(f"P2:GPU 只用 {ALLOWED_GPU}(CLI 會把認不得的名稱當成 A100)")


def check_port(port: int) -> None:
    """P6:桌機的 11434 是使用者自己的 Ollama,不送任何請求。"""
    if port in FORBIDDEN_PORTS:
        raise GuardViolation(f"P6:port {port} 是使用者自己的 Ollama,不送請求;本系統用 {OLLAMA_PORT}")


def check_model(model: str) -> None:
    if model not in ALLOWED_MODELS:
        raise GuardViolation(f"P7:只用 {', '.join(ALLOWED_MODELS)}")


def _ancestors() -> set[int]:
    pids, pid = set(), os.getpid()
    while pid > 1:
        pids.add(pid)
        try:
            stat_fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        except OSError:
            break
        pid = int(stat_fields[1])
    return pids


def residual_ssh_pids() -> list[int]:
    """命令列含 `ProxyCommand=colab ssh --proxy-mode -s cgb-test-` 的 ssh 行程。

    只認 argv[0] 是 `ssh` 的行程,並略過自己與祖先行程:
    啟動 pytest 的 shell 命令列裡也可能出現同一段字,不能把它們當成殘留而結束掉。
    """
    pids = []
    skip = _ancestors()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) in skip:
            continue
        try:
            argv = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if not argv or os.path.basename(argv[0].decode(errors="replace")) != "ssh":
            continue
        if RESIDUAL_SSH_MARK in b" ".join(argv).decode(errors="replace"):
            pids.append(int(entry.name))
    return pids


# ---------------------------------------------------------------- fixture


@pytest.fixture(scope="session")
def realrun(request: pytest.FixtureRequest) -> Iterator[Realrun]:
    if not realrun_selected(request.config):
        pytest.skip("實跑只在 -m realrun 時執行")

    self_check_mask()
    token_source = Path(os.environ["HOME"]) / ".config" / "colab-cli" / "token.json"
    rr = Realrun(Path(tempfile.mkdtemp(prefix="cgb-realrun-")))

    def finish_at_exit() -> None:
        rr.finish()

    atexit.register(finish_at_exit)
    try:
        rr.prepare_dirs()
        rr.run_prepare_data()
        rr.token_fingerprint = copy_token(token_source, rr.colab_dir / "token.json")
        rr.start_budget()
    except BaseException as error:
        rr.finish()
        atexit.unregister(finish_at_exit)
        pytest.exit(f"實跑護欄準備失敗,整批停下:{error}", returncode=3)

    try:
        yield rr
    finally:
        problems = rr.finish()
        atexit.unregister(finish_at_exit)
        if problems:
            pytest.fail("P3 收尾有需要處理的事:" + ";".join(problems), pytrace=False)


@pytest.fixture(autouse=True)
def _p2_budget_gate(request: pytest.FixtureRequest) -> None:
    """P2:每個實跑案例開始前看已用時間與餘額。"""
    if not realrun_selected(request.config):
        pytest.skip("實跑只在 -m realrun 時執行")
    rr: Realrun = request.getfixturevalue("realrun")
    rr.check_budget(request.node.nodeid)
