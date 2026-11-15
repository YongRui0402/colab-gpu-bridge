"""E5 遠端腳本以子行程接臨時 `ollama serve`(testplan.md § 2.1「遠端腳本」;plan.md Q27、Q45~Q47)。

接縫:`start_ollama.py` 在模擬的 Colab kernel 子行程裡執行後印出的 `CGB-RESULT`、寫出的 pid 檔與狀態檔、
`ollama serve` 實際讀到的環境。GPU 用 `bin/` 裡的假 `nvidia-smi`;Ollama 是真的 `/usr/local/bin/ollama`,
port 由 `free_loopback_port()` 取(避開 11434~11436 與 8780),`HOME`、`OLLAMA_MODELS`、pid 檔、狀態檔與 log 都在
pytest 暫存資料夾。kernel 子行程的 socket 只放行那個 port,不對 127.0.0.1:11434 送任何請求;不執行 `colab`。
收尾對這支測試起的行程逐一結束整個行程群組,並確認都已結束。
"""

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import httpx
import pytest

from realrun.helpers import free_loopback_port

pytestmark = pytest.mark.realrun_local

OLLAMA_BIN = Path("/usr/local/bin/ollama")
PGREP_BIN = Path("/usr/bin/pgrep")
START_OLLAMA = str(files("cgb.adapters.scripts") / "start_ollama.py")
RESTART_OLLAMA = str(files("cgb.adapters.scripts") / "restart_ollama.py")
RESERVED_PORTS = frozenset({11434, 11435, 11436, 8780})
MIB = 1048576
KILL_GRACE_SECONDS = 10.0
KERNEL_TIMEOUT_SECONDS = 120

# 模擬 Colab kernel:每一步照 CLI 的 `_build_env_prelude` 先設環境變數,再以 runpy 執行腳本;
# socket 只放行 127.0.0.1:<port>,其他位址記進 blocked 檔並丟 ConnectionRefusedError(護欄 P6)
KERNEL = r"""
import contextlib, io, json, os, runpy, socket, sys, time, traceback

config = json.load(open(sys.argv[1], encoding="utf-8"))
allowed = ("127.0.0.1", config["port"])
real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex


def blocked(address):
    if isinstance(address, tuple) and tuple(address[:2]) == allowed:
        return False
    with open(config["blocked"], "a", encoding="utf-8") as f:
        f.write(json.dumps(list(address) if isinstance(address, tuple) else str(address)) + "\n")
    return True


def guarded_connect(self, address):
    if blocked(address):
        raise ConnectionRefusedError(f"cgb-test 守門:不放行 {address!r}")
    return real_connect(self, address)


def guarded_connect_ex(self, address):
    if blocked(address):
        return 111
    return real_connect_ex(self, address)


socket.socket.connect, socket.socket.connect_ex = guarded_connect, guarded_connect_ex

for step in config["steps"]:
    for key, value in step["env"].items():
        os.environ[key] = value
    out = io.StringIO()
    started = time.monotonic()
    error = None
    try:
        with contextlib.redirect_stdout(out):
            runpy.run_path(step["script"], run_name="__main__")
    except BaseException:
        error = traceback.format_exc()
    elapsed = time.monotonic() - started
    lines = [line for line in out.getvalue().splitlines() if line.startswith("CGB-RESULT ")]
    # 這一步結束時 pid 檔指的 serve 讀到的環境(下一步可能停掉它),以及 kernel 自己的環境
    serve_env = None
    try:
        pid = int(open(config["pid_file"], encoding="utf-8").read().strip())
        raw = open(f"/proc/{pid}/environ", "rb").read()
        serve_env = [item.decode(errors="replace").split("=", 1) for item in raw.split(b"\0") if b"=" in item]
    except (OSError, ValueError):
        pass
    print(json.dumps({
        "stdout": out.getvalue(), "result": lines[-1] if lines else None, "elapsed": elapsed, "error": error,
        "serve_env": serve_env, "environ": dict(os.environ),
    }))
print(json.dumps({"environ": dict(os.environ)}))
"""

# 假 `nvidia-smi`:記下 argv 與 pid,照 `--query-gpu` 的欄位與 `--format` 的 noheader、nounits 產生輸出
FAKE_NVIDIA_SMI = r"""#!{python}
import json, os, sys, time

config = json.loads({config!r})
with open(config["calls"], "a", encoding="utf-8") as f:
    f.write(json.dumps({{"argv": sys.argv[1:], "pid": os.getpid()}}) + "\n")
time.sleep(config["sleep"])
if config["raw"] is not None:
    print(config["raw"])
else:
    query = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--query-gpu=")), "")
    formats = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--format=")), "").split(",")
    fields = [field for field in query.split(",") if field]
    units = "nounits" not in formats
    if "noheader" not in formats:
        print(", ".join(field + (" [MiB]" if units and field.startswith("memory.") else "") for field in fields))
    for name, mib in config["lines"]:
        values = {{"name": name, "memory.total": f"{{mib}} MiB" if units else str(mib)}}
        print(", ".join(values.get(field, "[N/A]") for field in fields))
sys.exit(config["exit"])
"""


@dataclass
class Step:
    stdout: str
    result: dict[str, Any] | None
    elapsed: float
    error: str | None
    serve_env: list[tuple[str, str]] | None
    environ: dict[str, str]


@dataclass
class Run:
    steps: list[Step]
    environ: dict[str, str]

    @property
    def result(self) -> dict[str, Any] | None:
        """只有一步時那一步的結果行。"""
        return self.steps[-1].result


class Box:
    """一個模擬的 Colab 執行環境:暫存資料夾、臨時 port、假 GPU 與這支測試起的行程。"""

    def __init__(self, root: Path, port: int) -> None:
        assert port not in RESERVED_PORTS
        self.root, self.port = root, port
        self.bin, self.home, self.models = root / "bin", root / "home", root / "models"
        for path in (self.bin, self.home, self.models):
            path.mkdir()
        (self.bin / "ollama").symlink_to(OLLAMA_BIN)
        (self.bin / "pgrep").symlink_to(PGREP_BIN)
        self.pid_path = root / "cgb-ollama-serve.pid"
        self.tuning_path = root / "cgb-ollama-tuning.json"
        self.log_path = root / "cgb-ollama-serve.log"
        self.calls_path = root / "nvidia-smi.calls"
        self.blocked_path = root / "blocked.jsonl"
        self.marker = str(uuid.uuid4())
        self.old_serves: list[subprocess.Popen] = []

    # ---- 準備

    def fake_gpu(self, lines=(("Tesla T4", 15360),), exit=0, sleep=0, raw=None) -> None:  # noqa: A002 - testplan 的參數名
        config = {"calls": str(self.calls_path), "lines": [list(line) for line in lines], "exit": exit, "sleep": sleep, "raw": raw}
        path = self.bin / "nvidia-smi"
        path.write_text(FAKE_NVIDIA_SMI.format(python=sys.executable, config=json.dumps(config)), encoding="utf-8")
        path.chmod(0o755)

    def step_env(self, **overrides: str) -> dict[str, str]:
        env = {
            "PATH": str(self.bin),
            "HOME": str(self.home),
            "OLLAMA_MODELS": str(self.models),
            "OLLAMA_HOST": f"127.0.0.1:{self.port}",
            "OLLAMA_ORIGINS": "*",
            "CGB_TUNE_NUM_PARALLEL": "",
            "CGB_TUNE_CONTEXT_LENGTH": "",
            "CGB_TUNE_MAX_LOADED_MODELS": "",
            "CGB_SERVE_PID_FILE": str(self.pid_path),
            "CGB_TUNING_FILE": str(self.tuning_path),
            "CGB_SERVE_LOG": str(self.log_path),
            "CGB_INSTALL_COMMAND": "true",
            "CGB_TEST_MARKER": self.marker,
        }
        env.update(overrides)
        return env

    def run(self, steps: list[str | tuple[str, dict[str, str]]], **env: str) -> Run:
        """起一個 kernel 子行程依序執行 `steps` 裡的腳本;`env` 蓋過每一步的預設環境。

        一步也可以是 `(腳本, 這一步另外要蓋過的環境)`,模擬同一個 kernel 連續兩次帶不同 `--env` 的 `colab exec`。
        """
        step_env = self.step_env(**env)
        config_path = self.root / f"kernel-{uuid.uuid4().hex}.json"
        config = {
            "port": self.port,
            "blocked": str(self.blocked_path),
            "pid_file": step_env["CGB_SERVE_PID_FILE"],
            "steps": [
                {"script": step, "env": step_env} if isinstance(step, str) else {"script": step[0], "env": {**step_env, **step[1]}}
                for step in steps
            ],
        }
        config_path.write_text(json.dumps(config), encoding="utf-8")
        kernel = subprocess.run(
            [sys.executable, "-I", "-c", KERNEL, str(config_path)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            env=step_env,
            timeout=KERNEL_TIMEOUT_SECONDS,
            check=False,
        )
        records = [json.loads(line) for line in kernel.stdout.splitlines() if line.startswith("{")]
        assert records and "environ" in records[-1], f"kernel 子行程沒有跑完:{kernel.stderr[-2000:]}"
        done = [
            Step(
                stdout=r["stdout"],
                result=json.loads(r["result"].removeprefix("CGB-RESULT ")) if r["result"] else None,
                elapsed=r["elapsed"],
                error=r["error"],
                serve_env=[tuple(pair) for pair in r["serve_env"]] if r["serve_env"] is not None else None,
                environ=r["environ"],
            )
            for r in records[:-1]
        ]
        return Run(steps=done, environ=records[-1]["environ"])

    def start_old_serve(self, via=OLLAMA_BIN, with_child=False, child_ignores_term=False) -> tuple[int, int | None]:
        """測試自己以新的 session 起一個舊的 serve(模擬上一次啟動的那一個),等它回應;回傳 serve 與成員的 pid。"""
        env = {
            "PATH": str(self.bin),
            "HOME": str(self.home),
            "OLLAMA_MODELS": str(self.models),
            "OLLAMA_HOST": f"127.0.0.1:{self.port}",
            "CGB_TEST_MARKER": self.marker,
        }
        with (self.root / "old-serve.log").open("ab") as log:
            serve = subprocess.Popen(
                [str(via), "serve"], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True
            )
        self.old_serves.append(serve)
        child_pid = None
        if with_child:
            # 同一個行程群組的成員,代表載入模型的 llama-server
            code = "import signal, time\n" + ("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" if child_ignores_term else "")
            child = subprocess.Popen(
                [sys.executable, "-I", "-c", code + "time.sleep(300)"], env=env, process_group=serve.pid, stdin=subprocess.DEVNULL
            )
            self.old_serves.append(child)
            child_pid = child.pid
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if self.version().status_code == 200:
                    return serve.pid, child_pid
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise AssertionError("舊的 serve 30 秒內沒有回應")

    # ---- 觀察

    def serve_env(self, pid: int) -> list[tuple[str, str]]:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
        return [tuple(item.decode(errors="replace").split("=", 1)) for item in raw.split(b"\0") if b"=" in item]

    def pid_file(self) -> str | None:
        return self.pid_path.read_text(encoding="utf-8") if self.pid_path.exists() else None

    def state(self) -> Any:
        return json.loads(self.tuning_path.read_text(encoding="utf-8")) if self.tuning_path.exists() else None

    def version(self) -> httpx.Response:
        assert self.port not in RESERVED_PORTS
        return httpx.get(f"http://127.0.0.1:{self.port}/api/version", timeout=2)

    def marked(self) -> list[int]:
        """`/proc/*/environ` 含這支測試 `CGB_TEST_MARKER` 的行程。"""
        needle = f"CGB_TEST_MARKER={self.marker}".encode()
        pids = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                if needle in (entry / "environ").read_bytes().split(b"\0"):
                    pids.append(int(entry.name))
            except OSError:
                continue
        return pids

    def gpu_calls(self) -> list[dict[str, Any]]:
        if not self.calls_path.exists():
            return []
        return [json.loads(line) for line in self.calls_path.read_text(encoding="utf-8").splitlines() if line]

    @property
    def blocked(self) -> list[Any]:
        if not self.blocked_path.exists():
            return []
        return [json.loads(line) for line in self.blocked_path.read_text(encoding="utf-8").splitlines() if line]

    # ---- 收尾

    def close(self) -> list[str]:
        """對這支測試起的行程逐一結束整個行程群組;交回還留著的行程(空清單表示都已結束)。"""
        ours = set(self.marked()) | {p.pid for p in self.old_serves}
        groups = set()
        for pid in ours:
            try:
                groups.add(os.getpgid(pid))
            except ProcessLookupError:
                continue
        for sig in (signal.SIGTERM, signal.SIGKILL):
            for group in groups:
                try:
                    os.killpg(group, sig)
                except (ProcessLookupError, PermissionError):
                    pass
            deadline = time.monotonic() + KILL_GRACE_SECONDS
            while time.monotonic() < deadline and self._left(ours, groups):
                time.sleep(0.1)
            if not self._left(ours, groups):
                break
        return self._left(ours, groups)

    def _left(self, pids: set[int], groups: set[int]) -> list[str]:
        for serve in self.old_serves:
            serve.poll()  # 回收測試自己起的行程,不留 defunct
        left = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            except (OSError, IndexError):
                continue
            pid, state, pgrp = int(entry.name), fields[0], int(fields[2])
            if (pid in pids or pgrp in groups) and state != "Z":
                left.append(f"pid {pid}(群組 {pgrp},狀態 {state})")
        return left


@pytest.fixture
def box(tmp_path):
    if not OLLAMA_BIN.exists():
        pytest.skip(f"無法實跑:沒有 {OLLAMA_BIN}(不替它安裝,plan.md Q47)")
    the_box = Box(tmp_path, free_loopback_port())
    try:
        yield the_box
    finally:
        left = the_box.close()
    assert left == [], f"收尾後行程或行程群組還在:{left}"
    assert the_box.blocked == [], f"腳本試著連往放行以外的位址:{the_box.blocked}"


def env_value(env: list[tuple[str, str]], name: str) -> list[str]:
    return [value for key, value in env if key == name]


# ---- 005 US1-CLI-08

TIERS = [
    (6144, "Tesla T4", (1, 4096, 1)),
    (12287, "NVIDIA L4", (1, 4096, 1)),
    (12288, "Tesla T4", (2, 4096, 1)),
    (15360, "Tesla T4", (2, 4096, 1)),
    (20479, "NVIDIA A100-SXM4-40GB", (2, 4096, 1)),
    (20480, "Tesla T4", (4, 8192, 1)),
    (23040, "NVIDIA L4", (4, 8192, 1)),
    (32767, "NVIDIA L4", (4, 8192, 1)),
    (32768, "Tesla T4", (8, 8192, 2)),
    (40960, "NVIDIA A100-SXM4-40GB", (8, 8192, 2)),
    (65535, "NVIDIA H100 80GB HBM3", (8, 8192, 2)),
    (65536, "Tesla T4", (16, 8192, 3)),
    (98304, "NVIDIA L4", (16, 8192, 3)),
]
# 期望的位元組數是手算的字面值(MiB × 1048576)
TIER_BYTES = {
    6144: 6442450944, 12287: 12883853312, 12288: 12884901888, 15360: 16106127360, 20479: 21473787904,
    20480: 21474836480, 23040: 24159191040, 32767: 34358689792, 32768: 34359738368, 40960: 42949672960,
    65535: 68718428160, 65536: 68719476736, 98304: 103079215104,
}  # fmt: skip


@pytest.mark.parametrize(("mib", "gpu_name", "expected"), TIERS, ids=[f"{mib}MiB" for mib, _, _ in TIERS])
def test_新啟動依量到的顯示記憶體級距帶給_ollama_serve_對應的設定(box, mib, gpu_name, expected):
    # Arrange
    box.fake_gpu(lines=[(gpu_name, mib)])

    # Act
    started = box.run([START_OLLAMA]).result or {}

    # Assert
    np, ctx, mlm = expected
    tuning = started.get("tuning") or {}
    pid = (box.pid_file() or "").strip()
    env = box.serve_env(int(pid)) if pid.isdigit() else []
    assert started.get("vramTotalBytes") == TIER_BYTES[mib]
    assert [(tuning.get(k) or {}).get("value") for k in ("numParallel", "contextLength", "maxLoadedModels")] == [np, ctx, mlm]
    assert [(tuning.get(k) or {}).get("source") for k in ("numParallel", "contextLength", "maxLoadedModels")] == ["auto"] * 3
    assert env_value(env, "OLLAMA_NUM_PARALLEL") == [str(np)]
    assert env_value(env, "OLLAMA_CONTEXT_LENGTH") == [str(ctx)]
    assert env_value(env, "OLLAMA_MAX_LOADED_MODELS") == [str(mlm)]
    assert env_value(env, "OLLAMA_FLASH_ATTENTION") == ["1"]
    assert env_value(env, "OLLAMA_KV_CACHE_TYPE") == ["q8_0"]


# ---- 005 US1-CLI-09

TUNING_NAMES = ("OLLAMA_NUM_PARALLEL", "OLLAMA_CONTEXT_LENGTH", "OLLAMA_MAX_LOADED_MODELS", "OLLAMA_FLASH_ATTENTION", "OLLAMA_KV_CACHE_TYPE")
TUNING_DEFAULT = {
    key: {"value": None, "source": "ollama_default"}
    for key in ("numParallel", "contextLength", "maxLoadedModels", "flashAttention", "kvCacheType")
}
UNREADABLE_GPU = {
    "a-no-nvidia-smi": None,
    "b-nvidia-smi-failed": {"exit": 9, "raw": "NVIDIA-SMI has failed"},
    "c-not-available": {"raw": "[N/A], [N/A]"},
}


@pytest.mark.parametrize("gpu", UNREADABLE_GPU.values(), ids=UNREADABLE_GPU.keys())
def test_讀不到顯示記憶體時照樣啟動_不帶任何設定_用_Ollama_預設值(box, gpu):
    # Arrange
    if gpu is not None:
        box.fake_gpu(**gpu)

    # Act
    started = box.run([START_OLLAMA]).result or {}

    # Assert
    pid = (box.pid_file() or "").strip()
    env = box.serve_env(int(pid)) if pid.isdigit() else []
    assert started.get("ok") is True
    assert started.get("vramTotalBytes", "<沒有這個鍵>") is None
    assert started.get("gpuName", "<沒有這個鍵>") is None
    assert started.get("tuning") == TUNING_DEFAULT
    assert [name for name, _ in env if name in TUNING_NAMES] == []
    assert env_value(env, "OLLAMA_HOST") == [f"127.0.0.1:{box.port}"]
    assert env_value(env, "OLLAMA_ORIGINS") == ["*"]


# ---- 005 US1-CLI-10


def test_多張_GPU_時取第一張的名稱與顯示記憶體(box):
    # Arrange
    box.fake_gpu(lines=[("NVIDIA A100-SXM4-80GB", 81920), ("Tesla T4", 15360)])

    # Act
    started = box.run([START_OLLAMA]).result or {}

    # Assert
    tuning = started.get("tuning") or {}
    assert started.get("gpuName") == "NVIDIA A100-SXM4-80GB"
    assert started.get("vramTotalBytes") == 85899345920
    assert [(tuning.get(k) or {}).get("value") for k in ("numParallel", "contextLength", "maxLoadedModels")] == [16, 8192, 3]
    assert [call["argv"] for call in box.gpu_calls()] == [["--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]]


# ---- 005 US1-CLI-11


def mem_total_kb() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1])
    raise AssertionError("/proc/meminfo 沒有 MemTotal")


def test_新啟動回報系統記憶體_serve_以新的_session_起來並留下_pid_檔與狀態檔(box):
    # Arrange
    box.fake_gpu(lines=[("Tesla T4", 15360)])
    mem_total = mem_total_kb()

    # Act
    started = box.run([START_OLLAMA]).result or {}

    # Assert
    pid_text = box.pid_file() or ""
    pid = int(pid_text) if pid_text.strip().isdigit() else -1
    cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[:-1] if pid > 0 else []
    state = box.state() or {}
    assert (started.get("ok"), started.get("alreadyRunning")) == (True, False)
    assert started.get("systemMemoryTotalBytes") == mem_total * 1024
    assert pid_text.strip().isdigit() and len(pid_text.strip().splitlines()) == 1
    assert [Path(cmdline[0].decode()).name, *(a.decode() for a in cmdline[1:])] == ["ollama", "serve"]
    assert env_value(box.serve_env(pid), "CGB_TEST_MARKER") == [box.marker]
    assert os.getpgid(pid) == pid
    assert box.version().status_code == 200
    fields = ("gpuName", "vramTotalBytes", "systemMemoryTotalBytes", "tuning")
    assert {k: state.get(k) for k in fields} == {k: started.get(k) for k in fields}


# ---- 005 US1-CLI-12

TUNING_AUTO_40G = {
    "numParallel": {"value": 8, "source": "auto"},
    "contextLength": {"value": 8192, "source": "auto"},
    "maxLoadedModels": {"value": 2, "source": "auto"},
    "flashAttention": {"value": True, "source": "auto"},
    "kvCacheType": {"value": "q8_0", "source": "auto"},
}
OLD_STATE = {
    "gpuName": "NVIDIA A100-SXM4-40GB",
    "vramTotalBytes": 42949672960,
    "systemMemoryTotalBytes": 89632571392,
    "tuning": TUNING_AUTO_40G,
}


def bind_error(port):
    return f"Error: listen tcp 127.0.0.1:{port}: bind: address already in use"


def test_serve_起來但沒有回應時回報_verify_與紀錄檔最後一行_並刪掉舊的狀態檔(box):
    # Arrange
    box.fake_gpu(lines=[("Tesla T4", 15360)])
    box.tuning_path.write_text(json.dumps(OLD_STATE), encoding="utf-8")
    (box.bin / "ollama").unlink()
    (box.bin / "ollama").write_text(f'#!/bin/sh\necho "{bind_error(box.port)}" >&2\nexit 1\n', encoding="utf-8")
    (box.bin / "ollama").chmod(0o755)

    # Act
    step = box.run([START_OLLAMA], CGB_VERIFY_SECONDS="2").steps[0]

    # Assert
    failed = step.result or {}
    assert (failed.get("ok"), failed.get("stage")) == (False, "verify")
    assert failed.get("detail") == bind_error(box.port)
    assert box.state() is None
    assert 2 <= step.elapsed <= 4


def test_找不到_ollama_時回報_start_並刪掉舊的狀態檔(box):
    # Arrange
    box.fake_gpu(lines=[("Tesla T4", 15360)])
    box.tuning_path.write_text(json.dumps(OLD_STATE), encoding="utf-8")
    (box.bin / "ollama").unlink()

    # Act
    failed = box.run([START_OLLAMA]).result or {}

    # Assert
    assert failed.get("stage") == "start"
    assert "No such file or directory" in (failed.get("detail") or "")
    assert box.state() is None


# ---- 005 US1-CLI-13


def is_ollama_serve(pid: int) -> bool:
    try:
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[:-1]
    except OSError:
        return False
    return len(argv) >= 2 and Path(argv[0].decode()).name == "ollama" and argv[1] == b"serve"


def test_已在執行時回報狀態檔裡的設定與這次量到的硬體_不再啟動_serve(box):
    # Arrange
    old_pid, _ = box.start_old_serve()
    box.pid_path.write_text(f"{old_pid}\n", encoding="utf-8")
    box.tuning_path.write_text(json.dumps(OLD_STATE), encoding="utf-8")
    box.fake_gpu(lines=[("Tesla T4", 15360)])

    # Act
    started = box.run([START_OLLAMA], CGB_TUNE_NUM_PARALLEL="4").result or {}

    # Assert
    assert started.get("alreadyRunning") is True
    assert started.get("tuning") == TUNING_AUTO_40G
    assert started.get("vramTotalBytes") == 16106127360
    assert box.pid_file() == f"{old_pid}\n"
    assert [pid for pid in {*box.marked(), old_pid} if is_ollama_serve(pid)] == [old_pid]


# ---- 005 US1-CLI-14

UNREADABLE_STATES = {"a-missing": None, "b-not-json": "not json", "c-wrong-shape": json.dumps({"tuning": {"numParallel": 4}})}


@pytest.mark.parametrize("content", UNREADABLE_STATES.values(), ids=UNREADABLE_STATES.keys())
def test_已在執行而讀不到狀態檔時照樣回報結果_設定是_null(box, content):
    # Arrange
    box.start_old_serve()
    if content is not None:
        box.tuning_path.write_text(content, encoding="utf-8")
    box.fake_gpu(lines=[("Tesla T4", 15360)])

    # Act
    step = box.run([START_OLLAMA]).steps[0]

    # Assert
    started = step.result or {}
    assert (started.get("ok"), started.get("alreadyRunning")) == (True, True)
    assert started.get("tuning", "<沒有這個鍵>") is None
    assert "CGB-RESULT " in step.stdout and step.error is None


# ---- 005 US1-CLI-15


def test_寫不了_pid_檔與狀態檔時_serve_照樣啟動並回報成功(box):
    # Arrange
    box.fake_gpu(lines=[("Tesla T4", 15360)])
    missing = box.root / "no-such-dir"

    # Act
    started = box.run(
        [START_OLLAMA], CGB_SERVE_PID_FILE=str(missing / "serve.pid"), CGB_TUNING_FILE=str(missing / "tuning.json")
    ).result or {}

    # Assert
    assert started.get("ok") is True
    assert box.version().status_code == 200


# ---- 005 US1-CLI-16


def test_nvidia_smi_卡住時在量測時限內放棄_當成讀不到並結束它(box):
    # Arrange
    box.start_old_serve()
    box.tuning_path.write_text(json.dumps(OLD_STATE), encoding="utf-8")
    box.fake_gpu(lines=[("Tesla T4", 15360)], sleep=30)

    # Act
    step = box.run([START_OLLAMA], CGB_PROBE_TIMEOUT_SECONDS="1").steps[0]

    # Assert
    started = step.result or {}
    gpu_pids = [call["pid"] for call in box.gpu_calls()]
    assert started.get("ok") is True
    assert started.get("vramTotalBytes", "<沒有這個鍵>") is None
    assert 1 <= step.elapsed <= 3
    assert len(gpu_pids) == 1 and not Path(f"/proc/{gpu_pids[0]}").exists()


# ---- 005 US1-CLI-17


def test_腳本只連_OLLAMA_HOST_指的_Ollama_不碰桌機的_Ollama_也不連外(box):
    # Arrange
    box.fake_gpu(lines=[("Tesla T4", 15360)])

    # Act
    started = box.run([START_OLLAMA]).result or {}

    # Assert
    attempts = [tuple(address[:2]) for address in box.blocked if isinstance(address, list)]
    assert [a for a in attempts if a[0] == "127.0.0.1" and a[1] in RESERVED_PORTS] == []
    assert [a for a in attempts if not str(a[0]).startswith("127.")] == []
    assert started.get("ollamaVersion") == box.version().json()["version"]


# ---- 005 US1-CLI-18(📏 量測:判定者是腳本;A、B 各 5 次,未用於調整)

REAL_NVIDIA_SMI = Path("/usr/bin/nvidia-smi")
ROUNDS = 5


def test_量測_讀真的_nvidia_smi_多花的時間在_5_秒內_且格式和假的一致(box):
    # Arrange
    if not REAL_NVIDIA_SMI.exists():
        pytest.skip(f"無法實跑:沒有 {REAL_NVIDIA_SMI}")
    # 只送唯讀的 --query-gpu,不改 GPU 設定、不跑 CUDA 程式
    query = [str(REAL_NVIDIA_SMI), "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]
    first = subprocess.run(query, capture_output=True, text=True, timeout=30, check=True).stdout.splitlines()[0]
    real_name, real_mib = (field.strip() for field in first.split(","))
    box.start_old_serve()
    box.tuning_path.write_text(json.dumps(OLD_STATE), encoding="utf-8")
    link = box.bin / "nvidia-smi"
    times = {"A": [], "B": []}
    seen = []

    # Act:A(有真的 nvidia-smi)與 B(沒有)交錯各跑 5 次
    for _ in range(ROUNDS):
        for group in ("A", "B"):
            if group == "A":
                link.symlink_to(REAL_NVIDIA_SMI)
            step = box.run([START_OLLAMA]).steps[0]
            if group == "A":
                link.unlink()
                seen.append(((step.result or {}).get("vramTotalBytes"), (step.result or {}).get("gpuName")))
            times[group].append(step.elapsed)

    # Assert
    median = {group: sorted(values)[ROUNDS // 2] for group, values in times.items()}
    print(
        "\nUS1-CLI-18 量測:"
        + json.dumps({"nvidiaSmiFirstLine": first, "seconds": times, "median": median, "aSeen": seen}, ensure_ascii=False)
    )
    assert median["A"] - median["B"] <= 5
    assert seen == [(int(real_mib) * MIB, real_name)] * ROUNDS


# ---- 005 US2-CLI-05


def test_只覆蓋平行數時它取代級距_沒填的兩項照級距(box):
    # Arrange
    box.fake_gpu(lines=[("NVIDIA A100-SXM4-40GB", 40960)])

    # Act
    started = box.run([START_OLLAMA], CGB_TUNE_NUM_PARALLEL="4").result or {}

    # Assert
    tuning = started.get("tuning") or {}
    pid = (box.pid_file() or "").strip()
    env = box.serve_env(int(pid)) if pid.isdigit() else []
    log = box.log_path.read_text(encoding="utf-8", errors="replace") if box.log_path.exists() else ""
    assert tuning.get("numParallel") == {"value": 4, "source": "manual"}
    assert tuning.get("contextLength") == {"value": 8192, "source": "auto"}
    assert tuning.get("maxLoadedModels") == {"value": 2, "source": "auto"}
    assert env_value(env, "OLLAMA_NUM_PARALLEL") == ["4"]
    assert env_value(env, "OLLAMA_CONTEXT_LENGTH") == ["8192"]
    assert env_value(env, "OLLAMA_MAX_LOADED_MODELS") == ["2"]
    assert [line for line in log.splitlines() if "server config" in line and "OLLAMA_NUM_PARALLEL:4" in line] != []


# ---- 005 US2-CLI-06


def test_覆蓋值剛好等於自動值時來源仍是_manual(box):
    # Arrange
    box.fake_gpu(lines=[("NVIDIA A100-SXM4-40GB", 40960)])

    # Act
    started = box.run([START_OLLAMA], CGB_TUNE_NUM_PARALLEL="8").result or {}

    # Assert
    assert (started.get("tuning") or {}).get("numParallel") == {"value": 8, "source": "manual"}


# ---- 005 US2-CLI-07


def test_三項都覆蓋成上限時原樣套用_不依顯示記憶體壓回級距(box):
    # Arrange
    box.fake_gpu(lines=[("Tesla T4", 15360)])

    # Act
    started = box.run(
        [START_OLLAMA], CGB_TUNE_NUM_PARALLEL="32", CGB_TUNE_CONTEXT_LENGTH="131072", CGB_TUNE_MAX_LOADED_MODELS="4"
    ).result or {}

    # Assert
    tuning = started.get("tuning") or {}
    pid = (box.pid_file() or "").strip()
    env = box.serve_env(int(pid)) if pid.isdigit() else []
    assert [tuning.get(k) for k in ("numParallel", "contextLength", "maxLoadedModels")] == [
        {"value": 32, "source": "manual"},
        {"value": 131072, "source": "manual"},
        {"value": 4, "source": "manual"},
    ]
    assert env_value(env, "OLLAMA_NUM_PARALLEL") == ["32"]
    assert env_value(env, "OLLAMA_CONTEXT_LENGTH") == ["131072"]
    assert env_value(env, "OLLAMA_MAX_LOADED_MODELS") == ["4"]


# ---- 005 US2-CLI-08


def test_讀不到顯示記憶體時仍帶填了的覆蓋值與_flash_attention_KV_沒填的用_Ollama_預設值(box):
    # Arrange:沒有 nvidia-smi

    # Act
    started = box.run([START_OLLAMA], CGB_TUNE_NUM_PARALLEL="4").result or {}

    # Assert
    tuning = started.get("tuning") or {}
    pid = (box.pid_file() or "").strip()
    env = box.serve_env(int(pid)) if pid.isdigit() else []
    assert tuning.get("numParallel") == {"value": 4, "source": "manual"}
    assert tuning.get("contextLength") == {"value": None, "source": "ollama_default"}
    assert tuning.get("maxLoadedModels") == {"value": None, "source": "ollama_default"}
    assert tuning.get("flashAttention") == {"value": True, "source": "auto"}
    assert tuning.get("kvCacheType") == {"value": "q8_0", "source": "auto"}
    assert env_value(env, "OLLAMA_NUM_PARALLEL") == ["4"]
    assert env_value(env, "OLLAMA_CONTEXT_LENGTH") == []
    assert env_value(env, "OLLAMA_MAX_LOADED_MODELS") == []
    assert env_value(env, "OLLAMA_FLASH_ATTENTION") == ["1"]
    assert env_value(env, "OLLAMA_KV_CACHE_TYPE") == ["q8_0"]


# ---- 005 US2-CLI-09

# 之前以 `--env OLLAMA_*` 設進 kernel、留下來的舊值
OLD_KERNEL_TUNING = {
    "OLLAMA_NUM_PARALLEL": "16",
    "OLLAMA_CONTEXT_LENGTH": "32768",
    "OLLAMA_MAX_LOADED_MODELS": "3",
    "OLLAMA_FLASH_ATTENTION": "0",
    "OLLAMA_KV_CACHE_TYPE": "f16",
}


def test_kernel_留著舊的_OLLAMA_設定時_沒有覆蓋值的_serve_一個都不繼承(box):
    # Arrange:沒有 nvidia-smi,kernel 先有五個舊值

    # Act
    box.run([START_OLLAMA], **OLD_KERNEL_TUNING)

    # Assert
    pid = (box.pid_file() or "").strip()
    env = box.serve_env(int(pid)) if pid.isdigit() else []
    assert [name for name, _ in env if name in TUNING_NAMES] == []


def test_kernel_留著舊的_OLLAMA_設定時_覆蓋的那一項只有一個值_沒填的不繼承(box):
    # Arrange:沒有 nvidia-smi,kernel 先有五個舊值

    # Act
    box.run([START_OLLAMA], **OLD_KERNEL_TUNING, CGB_TUNE_NUM_PARALLEL="4")

    # Assert
    pid = (box.pid_file() or "").strip()
    env = box.serve_env(int(pid)) if pid.isdigit() else []
    assert env_value(env, "OLLAMA_NUM_PARALLEL") == ["4"]
    assert env_value(env, "OLLAMA_CONTEXT_LENGTH") == []


# ---- 005 US2-CLI-10


def test_改回自動之後重啟的_serve_不帶上一次的覆蓋值_kernel_也沒有留下(box):
    # Arrange:沒有 nvidia-smi,kernel 裡沒有任何 OLLAMA_NUM_PARALLEL

    # Act
    start, restart = box.run([(START_OLLAMA, {"CGB_TUNE_NUM_PARALLEL": "4"}), (RESTART_OLLAMA, {"CGB_TUNE_NUM_PARALLEL": ""})]).steps

    # Assert
    assert env_value(start.serve_env or [], "OLLAMA_NUM_PARALLEL") == ["4"]
    assert "OLLAMA_NUM_PARALLEL" not in start.environ
    assert restart.serve_env is not None and env_value(restart.serve_env, "OLLAMA_NUM_PARALLEL") == []
    assert ((restart.result or {}).get("tuning") or {}).get("numParallel") == {"value": None, "source": "ollama_default"}
    assert env_value(restart.serve_env, "OLLAMA_FLASH_ATTENTION") == []


# ---- 005 US2-CLI-11

BAD_OVERRIDES = {
    "num-parallel-64": ("CGB_TUNE_NUM_PARALLEL", "64"),
    "num-parallel-0": ("CGB_TUNE_NUM_PARALLEL", "0"),
    "num-parallel-abc": ("CGB_TUNE_NUM_PARALLEL", "abc"),
    "num-parallel-4.0": ("CGB_TUNE_NUM_PARALLEL", "4.0"),
    "num-parallel-space-4": ("CGB_TUNE_NUM_PARALLEL", " 4"),
    "num-parallel-minus-1": ("CGB_TUNE_NUM_PARALLEL", "-1"),
    "context-length-2047": ("CGB_TUNE_CONTEXT_LENGTH", "2047"),
    "max-loaded-models-5": ("CGB_TUNE_MAX_LOADED_MODELS", "5"),
    "max-loaded-models-1e3": ("CGB_TUNE_MAX_LOADED_MODELS", "1e3"),
}


def version_unreachable(box) -> bool:
    try:
        box.version()
    except httpx.HTTPError:
        return True
    return False


@pytest.mark.parametrize(("name", "value"), BAD_OVERRIDES.values(), ids=BAD_OVERRIDES.keys())
def test_覆蓋值不符時回報_input_不量硬體_不刪狀態檔也不啟動(box, name, value):
    # Arrange
    box.fake_gpu(lines=[("Tesla T4", 15360)])
    box.tuning_path.write_text(json.dumps(OLD_STATE), encoding="utf-8")

    # Act
    failed = box.run([START_OLLAMA], **{name: value}).result or {}

    # Assert
    assert (failed.get("ok"), failed.get("stage")) == (False, "input")
    assert name in (failed.get("detail") or "")
    assert version_unreachable(box)
    assert box.pid_file() is None
    assert box.gpu_calls() == []
    assert box.state() == OLD_STATE
