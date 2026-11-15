"""在 Colab 執行環境上停掉 `ollama serve` 並以新設定重新啟動(`contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`)。

由後端以 `colab exec -f` 送到遠端 kernel 執行;和 `start_ollama.py` 一樣,設定依量到的顯示記憶體與三個 `CGB_TUNE_*`
決定(共用約定 12),只帶給這一次啟動的 `ollama serve`,不改 kernel 自己的環境變數(共用約定 12 (d))。
遠端腳本各自是單一檔,量硬體與組環境的程式和 `start_ollama.py` 各寫一份。

目前是最小版本(plan.md Q58):停掉 pid 檔指的那一個 serve、照 `CGB_TUNE_*` 組環境啟動;
pgrep 備援、停不掉與其他失敗的行為由故事 3 擴充。結果印成 stdout 的一行 `CGB-RESULT <JSON>`(`RestartOllamaScriptResult`)。
"""

import json
import os
import signal
import subprocess
import time
import urllib.request

VERSION_URL = "http://" + (os.environ.get("OLLAMA_HOST") or "127.0.0.1:11434") + "/api/version"
SERVE_LOG = os.environ.get("CGB_SERVE_LOG") or "/root/cgb-ollama-serve.log"
SERVE_PID_FILE = os.environ.get("CGB_SERVE_PID_FILE") or "/root/cgb-ollama-serve.pid"
TUNING_FILE = os.environ.get("CGB_TUNING_FILE") or "/root/cgb-ollama-tuning.json"
PROBE_TIMEOUT_SECONDS = float(os.environ.get("CGB_PROBE_TIMEOUT_SECONDS") or 10)
STOP_SECONDS = float(os.environ.get("CGB_STOP_SECONDS") or 10)
VERIFY_SECONDS = int(os.environ.get("CGB_VERIFY_SECONDS") or 60)
MIB = 1048576
GIB = 1073741824
# spec FR-002 的級距(和 `start_ollama.py` 相同)
TIERS = (
    (64 * GIB, (16, 8192, 3)),
    (32 * GIB, (8, 8192, 2)),
    (20 * GIB, (4, 8192, 1)),
    (12 * GIB, (2, 4096, 1)),
    (0, (1, 4096, 1)),
)
TUNE_ENV = (
    ("numParallel", "CGB_TUNE_NUM_PARALLEL"),
    ("contextLength", "CGB_TUNE_CONTEXT_LENGTH"),
    ("maxLoadedModels", "CGB_TUNE_MAX_LOADED_MODELS"),
)
TUNING_ENV = (
    ("numParallel", "OLLAMA_NUM_PARALLEL"),
    ("contextLength", "OLLAMA_CONTEXT_LENGTH"),
    ("maxLoadedModels", "OLLAMA_MAX_LOADED_MODELS"),
    ("flashAttention", "OLLAMA_FLASH_ATTENTION"),
    ("kvCacheType", "OLLAMA_KV_CACHE_TYPE"),
)


def ollama_version():
    try:
        with urllib.request.urlopen(VERSION_URL, timeout=2) as response:
            return json.load(response).get("version")
    except Exception:  # noqa: BLE001 - 沒有回應的各種錯誤都當成沒有回應
        return None


def report(**result):
    print("CGB-RESULT " + json.dumps(result), flush=True)


def read_gpu():
    """第一張 GPU 的名稱與顯示記憶體總量(位元組);讀不到時兩個都是 None。"""
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        ).stdout
        name, total = (field.strip() for field in output.splitlines()[0].split(","))
        return name, int(total) * MIB
    except Exception:  # noqa: BLE001 - 讀不到顯示記憶體不算失敗
        return None, None


def read_system_memory():
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def read_overrides():
    overrides = {}
    for key, name in TUNE_ENV:
        text = os.environ.get(name) or ""
        if text:
            overrides[key] = int(text)
    return overrides


def decide(vram_total, overrides):
    """同 `start_ollama.py` 的 `decide`(共用約定 12 (c))。"""
    if vram_total is None:
        values = {"numParallel": None, "contextLength": None, "maxLoadedModels": None}
    else:
        numbers = next(values for floor, values in TIERS if vram_total >= floor)
        values = dict(zip(("numParallel", "contextLength", "maxLoadedModels"), numbers))
    fixed = vram_total is not None or bool(overrides)
    values.update(flashAttention=True if fixed else None, kvCacheType="q8_0" if fixed else None)
    tuning = {
        key: {"value": values[key], "source": "auto" if values[key] is not None else "ollama_default"}
        for key, _ in TUNING_ENV
    }
    for key, value in overrides.items():
        values[key] = value
        tuning[key] = {"value": value, "source": "manual"}
    env = {name: ("1" if values[key] is True else str(values[key])) for key, name in TUNING_ENV if values[key] is not None}
    return tuning, env


def serve_env(tuning_env):
    """kernel 的環境拿掉五個設定,再加這次決定的值;不寫回 kernel 的 `os.environ`(共用約定 12 (d))。"""
    env = dict(os.environ)
    for _, name in TUNING_ENV:
        env.pop(name, None)
    env.update(tuning_env)
    return env


def stop_from_pid_file():
    """對 pid 檔指的 serve 的行程群組送 SIGTERM,等 `/api/version` 不再回應;到時限仍在就送 SIGKILL。"""
    try:
        with open(SERVE_PID_FILE, encoding="utf-8") as f:
            pid = int(f.read().strip())
        os.killpg(pid, signal.SIGTERM)
    except (OSError, ValueError):
        return
    deadline = time.monotonic() + STOP_SECONDS
    while time.monotonic() < deadline and ollama_version():
        time.sleep(0.2)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass


def main():
    gpu_name, vram_total = read_gpu()
    machine = {"gpuName": gpu_name, "vramTotalBytes": vram_total, "systemMemoryTotalBytes": read_system_memory()}
    tuning, tuning_env = decide(vram_total, read_overrides())

    stop_from_pid_file()

    try:
        os.remove(TUNING_FILE)
    except FileNotFoundError:
        pass
    try:
        log = open(SERVE_LOG, "ab")
        serve = subprocess.Popen(
            ["ollama", "serve"],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=serve_env(tuning_env),
        )
    except OSError as error:
        report(ok=False, stage="start", stoppedBy="pid_file", detail=str(error))
        return
    try:
        with open(SERVE_PID_FILE, "w", encoding="utf-8") as f:
            f.write(f"{serve.pid}\n")
    except OSError:
        pass

    for _ in range(VERIFY_SECONDS):
        time.sleep(1)
        version = ollama_version()
        if version:
            applied = {**machine, "tuning": tuning}
            try:
                with open(TUNING_FILE, "w", encoding="utf-8") as f:
                    json.dump(applied, f)
            except OSError:
                pass
            report(ok=True, ollamaVersion=version, stoppedBy="pid_file", **applied)
            return
    report(ok=False, stage="verify", stoppedBy="pid_file", detail=f"no response from /api/version within {VERIFY_SECONDS} seconds")


# `colab exec` 在 kernel 的 `__main__` 執行(本機測試以 runpy 的 run_name="__main__" 模擬);
# 被 import 時(例如 tests/integration/test_fake_signatures.py 走訪 cgb.adapters)什麼都不做,不在桌機上量硬體、連 Ollama 或啟動 serve
if __name__ == "__main__":
    main()
