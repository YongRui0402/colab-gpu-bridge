"""G-01(tasks.md T068):`RemoteOllama` 的形狀檢查與連不到的歸類,對真的 Ollama 一致(testplan.md § 4.2)。

測試自己起一個臨時的 `ollama serve`(`/usr/local/bin/ollama`,2026-11-13 為 0.32.15):port 由 `free_loopback_port()`
取(127.0.0.1,不會是 11434~11436、8780),環境變數只給 `PATH`、`HOME`、`OLLAMA_MODELS`(都在 pytest 暫存資料夾,
`OLLAMA_MODELS` 是空的)與 `OLLAMA_HOST`,以 `start_new_session=True` 起在自己的行程群組。
`RemoteOllama(transport=RecordingTransport(get_only=True))` 依序呼叫 `list_local_models`、`list_loaded_models`,
再對另一個沒有在聽的 port 呼叫 `list_local_models`;fixture 收尾送 SIGTERM,10 秒內沒結束就 SIGKILL,
再驗證行程與行程群組都已結束(則5)。

標 `realrun`,預設排除;不放 `tests/realrun/`,不經會執行 `colab usage` 的 `realrun` fixture(plan.md Q7、Q27)。
護欄:不對 127.0.0.1:11434(使用者自己的 Ollama)送任何請求,001 的 P6 不動(`RecordingTransport` 每個請求都經
`check_port`);只送 `GET`,不 pull、generate、delete;不讀寫使用者的 `~/.ollama`;`/usr/local/bin/ollama` 不存在就標
無法實跑,不替它安裝;不經 SSH、不執行 `colab`、不花 compute units;錄到的回應只寫 pytest 暫存資料夾;約 10 秒。
代價:`/api/tags` 是空清單,真實模型名稱是否帶版本與每一筆的欄位名稱驗不到;這是桌機 0.32.15,不是 Colab 上的 0.40.x。
判定者:腳本;樣本:一次實跑(未用於調整)。
執行:`uv run pytest -m realrun tests/integration/test_003_g_01.py`
"""

import os
import signal
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.adapters.remote_ollama import RemoteOllama
from realrun.conftest import REPO_ROOT, check_port, write_measurement
from realrun.helpers import RecordingTransport, free_loopback_port

pytestmark = pytest.mark.realrun

CASE, TASK = "G-01", "T068"
MEASUREMENTS = REPO_ROOT / "specs" / "003-download-dedup-model-cache" / "measurements.md"
OLLAMA_BIN = Path("/usr/local/bin/ollama")
READY_SECONDS = 30.0
TERM_SECONDS = 10.0
THRESHOLD = (
    "則1:/api/tags 原始筆數 = list_local_models 回傳筆數;則2:/api/tags、/api/ps 都是 200,最上層是物件、models 是陣列;"
    "則3:/api/ps 原始筆數 = list_loaded_models 回傳筆數;則4:沒有在聽的 port 丟 OLLAMA_UNREACHABLE;"
    "則5:收尾後行程已結束(poll() 不是 None)、行程群組沒有剩下的行程(killpg(pgid, 0) 丟 ProcessLookupError)"
)
COST = "代價:OLLAMA_MODELS 是空的,/api/tags 是空清單,真實模型名稱是否帶版本與每一筆的欄位名稱驗不到;這是桌機 0.32.15,不是 Colab 上的 0.40.x"


def ensure_measurements(path: Path = MEASUREMENTS) -> Path:
    """003 的 measurements.md 還沒有時先寫好標頭;`write_measurement` 自己建的標頭是 001 的標題。"""
    if not path.exists():
        path.write_text(
            "# 實跑量測結果:加入下載的重複判定與模型目錄快取\n\n"
            "由 `tests/realrun/conftest.py` 的 `write_measurement` 寫入(tasks.md T068、T069);"
            "護欄見 `testplan.md` § 4.2 各案例的「副作用與護欄」。\n\n"
            "| 時間 | 案例 | 任務 | 數字 | 門檻 | 結果 | 備註 |\n"
            "|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    return path


@dataclass
class Report:
    """測試本體與 fixture 收尾各自填入,最後由 `report` fixture 寫進 measurements.md。"""

    numbers: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    unavailable: str | None = None


@dataclass
class TempServe:
    port: int
    process: subprocess.Popen[bytes]
    version: str


def shape(exchange: Any) -> tuple[bool, bool, int | None]:
    """錄到的原始本文:最上層是不是物件、`models` 是不是陣列、原始筆數。"""
    try:
        body = exchange.json()
    except ValueError:
        return False, False, None
    is_object = isinstance(body, dict)
    models = body.get("models") if is_object else None
    return is_object, isinstance(models, list), len(models) if isinstance(models, list) else None


def end_group(process: subprocess.Popen[bytes]) -> tuple[bool, bool, str]:
    """SIGTERM 整個行程群組,10 秒內沒結束就 SIGKILL;回(行程已結束、行程群組已空、經過)。"""
    pgid = process.pid  # start_new_session=True:行程自己是群組的 leader
    how = "SIGTERM"
    started = time.monotonic()
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        how = "送 SIGTERM 前已結束"
    try:
        process.wait(timeout=TERM_SECONDS)
    except subprocess.TimeoutExpired:
        how = "SIGTERM 10 秒內沒結束,改送 SIGKILL"
        os.killpg(pgid, signal.SIGKILL)
        process.wait(timeout=TERM_SECONDS)
    # 群組裡若還有子行程(leader 先走了),也一起 SIGKILL,再看一次
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        pass
    else:
        how += ";群組還有行程,SIGKILL"
        os.killpg(pgid, signal.SIGKILL)
        time.sleep(0.5)
    elapsed = time.monotonic() - started
    try:
        os.killpg(pgid, 0)
        group_empty = False
    except ProcessLookupError:
        group_empty = True
    return process.poll() is not None, group_empty, f"{how},{elapsed:.2f} 秒"


@pytest.fixture
def report() -> Iterator[Report]:
    """`serve` 依賴這個 fixture,所以 `serve` 先收尾、這裡後收尾:則5 的結果也寫得進同一列。"""
    got = Report()
    yield got
    if got.unavailable is not None:
        write_measurement(CASE, TASK, got.unavailable, THRESHOLD, None, "無法實跑", path=ensure_measurements())
        return
    failed = [name for name in ("則1", "則2", "則3", "則4", "則5") if not got.checks.get(name, False)]
    note = ("沒過:" + "、".join(failed) + ";" if failed else "") + "只綁 127.0.0.1,只送 GET,不碰 11434;" + COST
    write_measurement(CASE, TASK, ";".join(got.numbers), THRESHOLD, not failed, note, path=ensure_measurements())
    assert got.checks.get("則5", False), "臨時 ollama serve 收尾後行程或行程群組還在:" + ";".join(got.numbers)


@pytest.fixture
def serve(report: Report, tmp_path: Path) -> Iterator[TempServe]:
    if not OLLAMA_BIN.is_file():
        report.unavailable = f"{OLLAMA_BIN} 不存在"
        pytest.skip(f"無法實跑:{OLLAMA_BIN} 不存在,不替它安裝")
    port = free_loopback_port()
    home, models = tmp_path / "home", tmp_path / "models"
    home.mkdir()
    models.mkdir()
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "OLLAMA_MODELS": str(models),
        "OLLAMA_HOST": f"127.0.0.1:{port}",
    }
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
            f"收尾:{how};行程已結束 {'是' if ended else '否'}(poll() = {process.poll()}),"
            f"行程群組已空 {'是' if group_empty else '否'}"
        )
        report.checks["則5"] = ended and group_empty


def wait_ready(port: int, process: subprocess.Popen[bytes]) -> str:
    """等到 `GET /api/version` 回 200(最多 30 秒);沒等到就讓測試失敗(收尾由 fixture 的 finally 做)。"""
    check_port(port)
    deadline = time.monotonic() + READY_SECONDS
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=2.0) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(f"臨時 ollama serve 在就緒前就結束了(exit {process.returncode})")
            try:
                response = client.get("/api/version")
                if response.status_code == 200:
                    return str(response.json().get("version"))
            except httpx.TransportError:
                pass
            time.sleep(0.2)
    pytest.fail(f"臨時 ollama serve {READY_SECONDS:g} 秒內沒有就緒")


async def outcome(call: Any) -> tuple[Any, str | None]:
    try:
        return await call, None
    except AdapterError as error:
        return None, error.code


async def test_g_01(serve: TempServe, report: Report, tmp_path: Path) -> None:
    # Arrange
    transport = RecordingTransport(get_only=True)
    ollama = RemoteOllama(transport=transport)
    base_url = f"http://127.0.0.1:{serve.port}"
    dead_port = free_loopback_port()

    # Act
    try:
        tags, tags_error = await outcome(ollama.list_local_models(base_url=base_url))
        ps, ps_error = await outcome(ollama.list_loaded_models(base_url=base_url))
        dead, dead_error = await outcome(ollama.list_local_models(base_url=f"http://127.0.0.1:{dead_port}"))
    finally:
        await transport.close_inner()
    (tmp_path / "g_01_exchanges.txt").write_text(
        "".join(f"{e.method} {e.path} → {e.status}\n{bytes(e.body).decode(errors='replace')}\n" for e in transport.exchanges),
        encoding="utf-8",
    )  # fmt: skip

    raw_tags, raw_ps = transport.last("GET", "/api/tags"), transport.last("GET", "/api/ps")
    tags_obj, tags_list, tags_raw_count = shape(raw_tags) if raw_tags else (False, False, None)
    ps_obj, ps_list, ps_raw_count = shape(raw_ps) if raw_ps else (False, False, None)
    tags_count = len(tags["models"]) if tags else None
    ps_count = len(ps["models"]) if ps else None

    # 則1~則4
    report.checks["則1"] = tags_error is None and tags_raw_count is not None and tags_count == tags_raw_count
    report.checks["則2"] = (
        raw_tags is not None and raw_tags.status == 200 and tags_obj and tags_list
        and raw_ps is not None and raw_ps.status == 200 and ps_obj and ps_list
    )  # fmt: skip
    report.checks["則3"] = ps_error is None and ps_raw_count is not None and ps_count == ps_raw_count
    report.checks["則4"] = dead is None and dead_error == "OLLAMA_UNREACHABLE"
    report.numbers[:0] = [
        f"臨時 ollama serve 版本 {serve.version}(127.0.0.1 port {serve.port})",
        f"/api/tags {raw_tags.status if raw_tags else '沒有往返'}、最上層物件 {'是' if tags_obj else '否'}、"
        f"models 陣列 {'是' if tags_list else '否'}、原始 {tags_raw_count} 筆、回傳 {tags_count} 筆,丟出 {tags_error or '無'}",
        f"/api/ps {raw_ps.status if raw_ps else '沒有往返'}、最上層物件 {'是' if ps_obj else '否'}、"
        f"models 陣列 {'是' if ps_list else '否'}、原始 {ps_raw_count} 筆、回傳 {ps_count} 筆,丟出 {ps_error or '無'}",
        f"沒有在聽的 port {dead_port} 丟出 {dead_error or '無'}",
        f"往返 {len(transport.exchanges)} 個,方法 {sorted({e.method for e in transport.exchanges})}",
    ]

    # Assert(則5 在 report fixture 收尾時斷言)
    failed = [name for name in ("則1", "則2", "則3", "則4") if not report.checks[name]]
    assert not failed, ";".join(report.numbers)
