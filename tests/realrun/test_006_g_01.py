"""006 G-01(tasks.md T048):opencode 照 `GET /api/connect` 的片段接上本系統,讀檔並回答(testplan.md § 5.2)。

做法照 plan.md § 待決問題 Q20 (a):測試自己起臨時的 `ollama serve`(另取 port、暫存 `HOME` 與 `OLLAMA_MODELS`、
`OLLAMA_CONTEXT_LENGTH=16384`,`start_new_session=True` 等於 `setsid`,起在自己的行程群組),本系統以
`start_live_servers` 起在 127.0.0.1(UI 隨機 port,相容端點用 `free_loopback_port()` 先取好的 port,
讓片段裡的 port 就是相容端點的實際 port);Colab 與通道用替身,`FakeTunnel` 回報的 `baseUrl` 指向臨時 serve,
`FakeColabControl` 回報 context 16384;遠端 Ollama 用真的 `RemoteOllama`,模型目錄由臨時 serve 的 `/api/tags` 讀。
相容端點的轉送 client 換成會留下請求本文的 transport,看臨時 serve 收到的 `/v1/chat/completions` 有沒有帶 `tools`。

模型:環境變數 `CGB_006_OLLAMA_MODELS_SEED` 指到一份已下載 `qwen2.5:3b` 的 `OLLAMA_MODELS` 時,以硬連結複製到
暫存資料夾(不動原本那份);沒設時經臨時 serve 的 `/api/pull` 下載(約 1.9 GB,只讀 ollama.com、不花錢)。

護欄:不對 127.0.0.1:11434 送任何請求(所有 HTTP 都經 `check_port`;`tests/conftest.py` 的 P6 守門也擋 socket);
不執行任何 `ollama` 或 `colab` 指令(臨時 serve 直接起 `/usr/local/bin/ollama serve`,帶自己的 `OLLAMA_HOST`);
opencode 以 `env -i` 的等價做法執行:環境變數只有 `PATH`、`HOME` 與四個 `XDG_*`,都指到 pytest 暫存資料夾,
不讀寫使用者的 `~/.config/opencode`;opencode 與臨時 serve 都在自己的行程群組,結束(包括失敗)一定停掉並確認已結束。
`tests/realrun/` 的 autouse P2 預算閘(要 `-m realrun` 並執行 `colab usage`)在這裡換成不做事的同名 fixture:
這個案例不開 Colab、不花 compute units。
判定者:腳本;樣本:固定的 `secret.txt`(沒有用來調整規則)。
執行:`uv run pytest -m realrun_local tests/realrun/test_006_g_01.py -q -p no:cacheprovider`
"""

import json
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from cgb.adapters.remote_ollama import RemoteOllama
from cgb.app import AppPair
from cgb.ollama_compat.forward import FORWARD_TIMEOUT
from integration.test_003_g_01 import end_group, wait_ready
from integration.test_api_session import T4_STARTED, ColabWorld, open_ready
from realrun.conftest import REPO_ROOT, check_port
from realrun.helpers import free_loopback_port, port_listening

pytestmark = pytest.mark.realrun_local

CASE, TASK = "G-01", "T048"
OLLAMA_BIN = Path("/usr/local/bin/ollama")
MODEL = "qwen2.5:3b"
CONTEXT = 16384
SECRET = "紫色長頸鹿 42"
PROMPT = "讀 secret.txt,只回答檔案內容"
RUN_SECONDS = 300
PULL_SECONDS = 1800
SEED_ENV = "CGB_006_OLLAMA_MODELS_SEED"
# e2e 固定用的 port;free_loopback_port() 已避開 11434~11436 與 8780
E2E_PORTS = frozenset({8781, 11437})
MEASUREMENTS = REPO_ROOT / "specs" / "006-agent-client-connect" / "measurements.md"
# 使用者自己的 ollama serve 不碰;收尾時只看它還在不在(找不到也不算失敗,只照實記下)
USER_OLLAMA_PID = 3585


@pytest.fixture(autouse=True)
def _p2_budget_gate() -> None:
    """覆寫 `tests/realrun/conftest.py` 的同名 autouse fixture:本機實跑不開 Colab,不需要 P2 預算與 `colab usage`。"""


# ---------------------------------------------------------------- 量測紀錄


def ensure_measurements() -> Path:
    if not MEASUREMENTS.exists():
        MEASUREMENTS.write_text(
            "# 量測紀錄:006-agent-client-connect\n\n"
            "由各案例的測試附加(tasks.md T048~T050);護欄見 `testplan.md` § 5.2 各案例的「副作用與護欄」。\n",
            encoding="utf-8",
        )
    return MEASUREMENTS


def append_section(title: str, lines: list[str]) -> None:
    with ensure_measurements().open("a", encoding="utf-8") as f:
        f.write(f"\n## {title}\n\n" + "".join(f"- {line}\n" for line in lines))


@dataclass
class Report:
    """`serve` 依賴這個 fixture:臨時 serve 先收尾,收尾的證據也寫得進同一節。"""

    title: str
    environment: list[str] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    verdicts: list[str] = field(default_factory=list)
    cleanup: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    sample: str = "判定者:腳本;樣本:固定的 `secret.txt`(內容 `紫色長頸鹿 42`,沒有用來調整規則),一次實跑"
    unavailable: str | None = None

    def write(self) -> None:
        lines = [f"日期:{datetime.now():%Y-%m-%d %H:%M};環境:" + ";".join(self.environment)]
        if self.unavailable is not None:
            lines.append(f"**無法實跑:{self.unavailable}**")
        lines += self.numbers + [f"**{v}**" for v in self.verdicts] + [self.sample]
        lines.append("收尾:" + ";".join(self.cleanup))
        append_section(self.title, lines)


def make_report(title: str) -> Iterator[Report]:
    got = Report(title)
    yield got
    got.write()
    assert got.checks.get("收尾", False), "臨時 ollama serve 收尾後行程或行程群組還在:" + ";".join(got.cleanup)


@pytest.fixture
def report() -> Iterator[Report]:
    yield from make_report(f"{CASE}({TASK})opencode 照片段接上本系統(本機臨時 `ollama serve`)")


# ---------------------------------------------------------------- 臨時 ollama serve


@dataclass
class TempServe:
    port: int
    process: subprocess.Popen[bytes]
    version: str
    log_path: Path

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def loopback_port() -> int:
    while True:
        port = free_loopback_port()
        if port not in E2E_PORTS:
            return port


def seed_models(target: Path) -> str:
    """`CGB_006_OLLAMA_MODELS_SEED` 有設時以硬連結複製(原本那份只讀);回記錄用的說明。"""
    seed = os.environ.get(SEED_ENV)
    if not seed:
        target.mkdir()
        return "空的 `OLLAMA_MODELS`,經臨時 serve 的 `/api/pull` 下載"
    source = Path(seed)
    manifest = source / "manifests" / "registry.ollama.ai" / "library" / MODEL.split(":")[0] / MODEL.split(":")[1]
    if not manifest.is_file():
        raise AssertionError(f"{SEED_ENV} 指到的資料夾沒有 {MODEL}")
    shutil.copytree(source, target, copy_function=os.link)
    return f"以硬連結複製已下載 `{MODEL}` 的 `OLLAMA_MODELS`(原本那份不動)"


def ensure_model(serve: TempServe, report: Report) -> None:
    check_port(serve.port)
    with httpx.Client(base_url=serve.base_url, timeout=httpx.Timeout(10.0, read=PULL_SECONDS)) as client:
        names = [m.get("name") for m in client.get("/api/tags").json().get("models", [])]
        if MODEL in names:
            return
        started = time.monotonic()
        last: dict[str, Any] = {}
        with client.stream("POST", "/api/pull", json={"model": MODEL}) as response:
            for line in response.iter_lines():
                if line.strip():
                    last = json.loads(line)
        report.environment.append(f"下載 `{MODEL}` {time.monotonic() - started:.0f} 秒,最後一行 `{last.get('status')}`")
        if last.get("status") != "success":
            pytest.fail(f"下載 {MODEL} 沒有成功:{last}")


def start_serve(report: Report, root: Path) -> TempServe:
    if not OLLAMA_BIN.is_file():
        report.unavailable = f"{OLLAMA_BIN} 不存在"
        report.checks["收尾"] = True
        pytest.skip(f"無法實跑:{OLLAMA_BIN} 不存在,不替它安裝")
    port = loopback_port()
    check_port(port)
    home, models = root / "serve-home", root / "models"
    home.mkdir()
    report.environment.append(seed_models(models))
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "OLLAMA_MODELS": str(models),
        "OLLAMA_HOST": f"127.0.0.1:{port}",
        "OLLAMA_CONTEXT_LENGTH": str(CONTEXT),
    }
    log_path = root / "ollama-serve.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [str(OLLAMA_BIN), "serve"], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )  # fmt: skip
    return TempServe(port, process, "", log_path)


def stop_serve(serve: TempServe, report: Report) -> None:
    ended, group_empty, how = end_group(serve.process)
    closed = not port_listening(serve.port)
    user_alive = Path(f"/proc/{USER_OLLAMA_PID}").exists()
    report.cleanup.append(
        f"臨時 serve(pid {serve.process.pid},行程群組 {serve.process.pid}){how};行程已結束 {'是' if ended else '否'}"
        f"(poll() = {serve.process.poll()}),行程群組已空 {'是' if group_empty else '否'}(`killpg(pgid, 0)` 丟 ProcessLookupError),"
        f"127.0.0.1:{serve.port} 已不在聽 {'是' if closed else '否'};使用者自己的 `ollama serve`(pid {USER_OLLAMA_PID})沒有碰,"
        f"收尾後{'仍在' if user_alive else '不在(本來就沒在跑或 pid 不同)'}"
    )
    report.checks["收尾"] = ended and group_empty and closed


@pytest.fixture
def serve(report: Report, tmp_path: Path) -> Iterator[TempServe]:
    temp = start_serve(report, tmp_path)
    try:
        temp.version = wait_ready(temp.port, temp.process)
        report.environment.append(
            f"臨時 `ollama serve` {temp.version}(127.0.0.1 隨機 port,`OLLAMA_CONTEXT_LENGTH={CONTEXT}`,暫存 `HOME` 與 `OLLAMA_MODELS`)"
        )
        ensure_model(temp, report)
        yield temp
    finally:
        stop_serve(temp, report)


# ---------------------------------------------------------------- 本系統


class BodyRecorder(httpx.AsyncBaseTransport):
    """相容端點轉送用:留下每個送往臨時 serve 的請求(方法、路徑、本文);每個請求都先經 `check_port`。"""

    def __init__(self) -> None:
        self.inner = httpx.AsyncHTTPTransport()
        self.requests: list[tuple[str, str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.port is not None:
            check_port(request.url.port)
        body = await request.aread()
        try:
            parsed = json.loads(body) if body else None
        except ValueError:
            parsed = None
        self.requests.append((request.method, request.url.path, parsed))
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()

    def chats(self) -> list[dict[str, Any]]:
        return [b for m, p, b in self.requests if (m, p) == ("POST", "/v1/chat/completions") and isinstance(b, dict)]


@dataclass
class Bridge:
    ui_url: str
    ollama_port: int
    relay: BodyRecorder
    connect: dict[str, Any]


def ctx16k_started() -> dict[str, Any]:
    """替身的 `OllamaStarted`:同 T4,context 回報 16384(testplan G-01「替身回報 context 16384」)。"""
    tuning = {**T4_STARTED["tuning"], "contextLength": {"value": CONTEXT, "source": "auto"}}
    return {**T4_STARTED, "tuning": tuning}


async def start_bridge(
    serve: TempServe, fakes: Any, make_app: Callable[..., AppPair], start_live_servers: Callable[..., Any]
) -> Bridge:
    world = ColabWorld(fakes)
    world.start_result = ctx16k_started()
    world.restart_result = {**world.restart_result, "tuning": world.start_result["tuning"]}
    fakes.tunnel.open_tunnel.side_effect(
        lambda *a, **k: {
            "sessionName": k["session_name"],
            "baseUrl": serve.base_url,
            "remoteOllamaVersion": serve.version,
            "connectedAt": "2026-11-16T09:00:00Z",
            "elapsedMs": 0,
        }
    )
    ollama_port = loopback_port()
    pair = make_app(remote_ollama=RemoteOllama(), public_ollama_port=ollama_port)
    servers = start_live_servers(pair, ollama_port=ollama_port)
    relay = BodyRecorder()
    # 原本的 client 留給 lifespan 收尾;換上的這個第一次用在後端的事件迴圈
    pair.ollama.state.forward_client = httpx.AsyncClient(transport=relay, timeout=FORWARD_TIMEOUT)
    async with httpx.AsyncClient(base_url=servers.ui_url, timeout=30.0) as ui:
        await open_ready(ui)
        response = await ui.get("/api/connect")
    assert response.status_code == 200, response.text
    return Bridge(servers.ui_url, servers.ollama_port, relay, response.json())


def fill_host(snippet: str) -> str:
    """片段原樣使用,只把 `{{host}}` 換成 127.0.0.1(port 已是相容端點的實際 port)。"""
    return snippet.replace("{{host}}", "127.0.0.1")


# ---------------------------------------------------------------- 用戶端(env -i)


def client_env(home: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """等同 `env -i`:只留 `PATH`,`HOME` 與四個 `XDG_*` 指到暫存資料夾。"""
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
    }
    for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    env.update(extra or {})
    return env


@dataclass
class Run:
    code: int | None
    seconds: float
    stdout: str
    stderr: str
    timed_out: bool
    cleanup: str


def run_client(argv: list[str], cwd: Path, env: dict[str, str], timeout: float) -> Run:
    """在自己的行程群組執行;結束後(包括逾時)停掉整個行程群組並確認已空。"""
    started = time.monotonic()
    process = subprocess.Popen(
        argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )  # fmt: skip
    timed_out = False
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        out, err = process.communicate()
    seconds = time.monotonic() - started
    try:
        os.killpg(process.pid, 0)
    except ProcessLookupError:
        group = "行程群組已空"
    else:
        os.killpg(process.pid, signal.SIGKILL)
        time.sleep(0.5)
        try:
            os.killpg(process.pid, 0)
            group = "行程群組留下的子行程 SIGKILL 後仍在"
        except ProcessLookupError:
            group = "行程群組留下的子行程已 SIGKILL,群組已空"
    return Run(process.returncode, seconds, out.decode(errors="replace"), err.decode(errors="replace"), timed_out, group)


def json_lines(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def make_project(root: Path) -> Path:
    project = root / "project"
    project.mkdir()
    (project / "secret.txt").write_text(SECRET + "\n", encoding="utf-8")
    return project


def verdict(ok: bool) -> str:
    return "過" if ok else "沒過"


def serve_ps(serve: TempServe) -> str:
    check_port(serve.port)
    try:
        models = httpx.get(f"{serve.base_url}/api/ps", timeout=5.0).json().get("models", [])
    except (httpx.HTTPError, ValueError):
        return "讀不到"
    return ", ".join(f"{m.get('name')} size {m.get('size')} size_vram {m.get('size_vram')} context {m.get('context_length')}" for m in models) or "沒有載入"


# ---------------------------------------------------------------- G-01


async def test_006_g_01(
    serve: TempServe,
    report: Report,
    make_app: Callable[..., AppPair],
    start_live_servers: Callable[..., Any],
    fakes: Any,
    tmp_path: Path,
) -> None:
    opencode = shutil.which("opencode")
    if opencode is None:
        report.unavailable = "PATH 上沒有 `opencode`"
        pytest.skip("無法實跑:PATH 上沒有 opencode,不替它安裝")

    # Arrange:本系統開到就緒,從 /api/connect 取 opencode 片段原樣寫進暫存 HOME
    bridge = await start_bridge(serve, fakes, make_app, start_live_servers)
    home = tmp_path / "client-home"
    env = client_env(home)
    version = run_client([opencode, "--version"], tmp_path, env, 60).stdout.strip()
    report.environment.append(f"opencode {version}(`env -i` 只留 `PATH`,`HOME` 與四個 `XDG_*` 指到暫存資料夾)")
    report.environment.append(f"本系統:測試行程內的 uvicorn,相容端點 127.0.0.1:{bridge.ollama_port},Colab 與通道用替身,不開 Colab、不花錢")
    snippet = bridge.connect["snippets"]["opencode"]
    config = home / ".config" / "opencode" / "opencode.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(fill_host(snippet), encoding="utf-8")
    project = make_project(tmp_path)

    # Act
    run = run_client([opencode, "run", "--format", "json", "-m", f"cgb/{MODEL}", PROMPT], project, env, RUN_SECONDS)
    report.cleanup.append(f"opencode(結束碼 {run.code}){run.cleanup}")
    ps = serve_ps(serve)

    # Assert(先算好全部數字再寫紀錄,斷言放最後)
    events = json_lines(run.stdout)
    tools = [e["part"].get("tool") for e in events if e.get("type") == "tool_use" and isinstance(e.get("part"), dict)]
    text = "".join(e["part"].get("text", "") for e in events if e.get("type") == "text" and isinstance(e.get("part"), dict))
    chats = bridge.relay.chats()
    with_tools = [c for c in chats if c.get("tools")]
    tokens = [e["part"].get("tokens", {}).get("input") for e in events if e.get("type") == "step_finish" and isinstance(e.get("part"), dict)]
    then1 = run.code == 0 and not run.timed_out and SECRET in text
    then2 = bool(with_tools) and "read" in tools
    report.numbers += [
        f"`/api/connect`:contextLength {bridge.connect.get('contextLength')}、models {bridge.connect.get('models')}、shouldWarn {bridge.connect.get('shouldWarn')}",
        f"opencode 結束碼 {run.code}{'(逾時)' if run.timed_out else ''};總耗時 {run.seconds:.1f} 秒(上限 {RUN_SECONDS} 秒)",
        f"回答文字(opencode 的 `text` 事件)含 `{SECRET}`:{'是' if SECRET in text else '否'};前 80 字 `{text[:80]!r}`",
        f"工具呼叫 {len(tools)} 次:{tools};每一步的 input tokens {tokens}",
        f"臨時 serve 收到的 `POST /v1/chat/completions` {len(chats)} 個,帶 `tools` 的 {len(with_tools)} 個"
        f"(工具數 {[len(c['tools']) for c in with_tools]},`stream` {[c.get('stream') for c in chats]})",
        f"臨時 serve 的 `/api/ps`:{ps}",
    ]
    report.verdicts += [
        f"則1 結束碼 0、輸出含 `{SECRET}`,門檻同左:{verdict(then1)}",
        f"則2 有帶 `tools` 的 `/v1/chat/completions` 與 `read` 工具呼叫,門檻同左:{verdict(then2)}",
        f"則3 總耗時 {run.seconds:.1f} 秒(只記錄,沒有門檻)",
    ]
    if not (then1 and then2):
        report.numbers.append(f"opencode stderr 最後 3 行:{run.stderr.strip().splitlines()[-3:]!r}")
    assert then1, f"exit {run.code},text {text[:200]!r},stderr {run.stderr[-500:]!r}"
    assert then2, f"tools {tools},chats with tools {len(with_tools)}"
