"""在 Colab 執行環境上停掉 `ollama serve` 並以新設定重新啟動(`contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`)。

由後端以 `colab exec -f` 送到遠端 kernel 執行;和 `start_ollama.py` 一樣,設定依量到的顯示記憶體與三個 `CGB_TUNE_*`
決定(共用約定 12),只帶給這一次啟動的 `ollama serve`,不改 kernel 自己的環境變數(共用約定 12 (d))。
遠端腳本各自是單一檔,量硬體與組環境的程式和 `start_ollama.py` 各寫一份。

依序:檢查覆蓋值(不符就不碰舊的)→ 停掉舊的 serve 的整個行程群組(pid 檔,備援 `pgrep`)→ 確認 port 不再回應 →
刪狀態檔、以新設定啟動 → 驗證 `/api/version`(失敗就停掉新的)。結果印成 stdout 的一行 `CGB-RESULT <JSON>`(`RestartOllamaScriptResult`)。
"""

import json
import os
import re
import signal
import subprocess
import time
import urllib.request

ADDRESS = os.environ.get("OLLAMA_HOST") or "127.0.0.1:11434"
VERSION_URL = "http://" + ADDRESS + "/api/version"
SERVE_LOG = os.environ.get("CGB_SERVE_LOG") or "/root/cgb-ollama-serve.log"
SERVE_PID_FILE = os.environ.get("CGB_SERVE_PID_FILE") or "/root/cgb-ollama-serve.pid"
TUNING_FILE = os.environ.get("CGB_TUNING_FILE") or "/root/cgb-ollama-tuning.json"
PROBE_TIMEOUT_SECONDS = float(os.environ.get("CGB_PROBE_TIMEOUT_SECONDS") or 10)
PGREP_PATTERN = os.environ.get("CGB_SERVE_PGREP_PATTERN") or "^ollama serve"
STOP_SECONDS = float(os.environ.get("CGB_STOP_SECONDS") or 10)
VERIFY_SECONDS = int(os.environ.get("CGB_VERIFY_SECONDS") or 60)
# SIGKILL 之後等行程群組結束的上限(秒);SIGKILL 擋不住,通常立刻結束
KILL_WAIT_SECONDS = 5
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


# 覆蓋值的範圍(spec FR-017,含上下限;共用約定 11);格式用整串比對,結尾多一個換行的 "4\n" 不算(Q72)
TUNE_RANGES = {"numParallel": (1, 32), "contextLength": (2048, 131072), "maxLoadedModels": (1, 4)}
DIGITS = re.compile(r"[0-9]+")


def invalid_override():
    """第一個不符的 `CGB_TUNE_*` 的說明(英文,放進 `detail`);都符合(或是空字串)時是 None。"""
    for key, name in TUNE_ENV:
        text = os.environ.get(name) or ""
        if not text:
            continue
        low, high = TUNE_RANGES[key]
        if not (DIGITS.fullmatch(text) and low <= int(text) <= high):
            return f"{name} must be an integer between {low} and {high}"
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


def pid_file_group():
    """pid 檔指的行程群組(pid 被重用不另檢查,Q53);pid 檔不在、內容不是數字或那個行程已不在時是 None。"""
    try:
        with open(SERVE_PID_FILE, encoding="utf-8") as f:
            pid = int(f.read().strip())
        os.killpg(pid, 0)
    except (OSError, ValueError):
        return None
    return pid


def pgrep_groups():
    """`pgrep -f` 比對到的行程各自的行程群組(Q5、Q45);不含自己所在的群組。"""
    try:
        output = subprocess.run(
            ["pgrep", "-f", PGREP_PATTERN], capture_output=True, text=True, check=False, timeout=PROBE_TIMEOUT_SECONDS
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    groups = set()
    for word in output.split():
        try:
            groups.add(os.getpgid(int(word)))
        except (OSError, ValueError):
            continue
    groups.discard(os.getpgrp())
    return sorted(groups)


def signal_groups(groups, sig):
    for group in groups:
        try:
            os.killpg(group, sig)
        except OSError:
            pass  # 已經結束的群組不算錯誤


def group_alive(group):
    """行程群組裡還有沒結束的行程(已結束、還沒被父行程回收的 defunct 不算)。"""
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="utf-8") as f:
                fields = f.read().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if int(fields[2]) == group and fields[0] != "Z":
            return True
    return False


def wait_groups_gone(groups, seconds):
    """等這些行程群組都結束,最多 `seconds` 秒;回傳是否都結束了。"""
    deadline = time.monotonic() + seconds
    while any(group_alive(group) for group in groups):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


def terminate_groups(groups):
    """對這些行程群組送 SIGTERM;`CGB_STOP_SECONDS` 內沒有全部結束(例如有成員忽略 SIGTERM)就送 SIGKILL,確認都結束才回來。"""
    signal_groups(groups, signal.SIGTERM)
    if not wait_groups_gone(groups, STOP_SECONDS):
        signal_groups(groups, signal.SIGKILL)
        wait_groups_gone(groups, KILL_WAIT_SECONDS)


def stop_old_serve():
    """停掉舊的 `ollama serve` 的整個行程群組(載入模型的子行程也要結束,research.md R1);回傳是怎麼找到的:
    `pid_file`(pid 檔)、`pgrep`(備援),或 `not_running`(找不到)。"""
    group = pid_file_group()
    if group is not None:
        stopped_by, groups = "pid_file", [group]
    else:
        groups = pgrep_groups()
        stopped_by = "pgrep" if groups else "not_running"
    terminate_groups(groups)
    return stopped_by


def wait_not_responding(seconds):
    """等 `/api/version` 不再有回應,最多 `seconds` 秒;回傳是否已經沒有回應(舊的確實停了,新的才綁得到 port)。"""
    deadline = time.monotonic() + seconds
    while ollama_version():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)
    return True


def last_line(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def stop_new_serve(group):
    """驗證失敗時停掉剛起的那一個,不留半死不活的 serve 佔著 port 與顯示記憶體。"""
    terminate_groups([group])


def main():
    # 停舊的之前先檢查覆蓋值:使用者打錯一個值不該清掉已載入的模型(合約步驟 (a))
    invalid = invalid_override()
    if invalid:
        report(ok=False, stage="input", detail=invalid)
        return
    gpu_name, vram_total = read_gpu()
    machine = {"gpuName": gpu_name, "vramTotalBytes": vram_total, "systemMemoryTotalBytes": read_system_memory()}
    tuning, tuning_env = decide(vram_total, read_overrides())

    stopped_by = stop_old_serve()
    if not wait_not_responding(STOP_SECONDS):
        # 不認得、也停不掉 port 上的行程(不用 `fuser -k` 之類殺掉任意行程):不啟動新的,交給呼叫者處理
        report(ok=False, stage="stop", stoppedBy=stopped_by, detail=f"{ADDRESS} still responding after {STOP_SECONDS:g} seconds")
        return

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
        report(ok=False, stage="start", stoppedBy=stopped_by, detail=str(error))
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
            report(ok=True, ollamaVersion=version, stoppedBy=stopped_by, **applied)
            return
    stop_new_serve(serve.pid)
    try:
        with open(SERVE_LOG, encoding="utf-8", errors="replace") as f:
            detail = last_line(f.read())
    except OSError:
        detail = ""
    report(
        ok=False,
        stage="verify",
        stoppedBy=stopped_by,
        detail=detail or f"no response from /api/version within {VERIFY_SECONDS} seconds",
    )


# `colab exec` 在 kernel 的 `__main__` 執行(本機測試以 runpy 的 run_name="__main__" 模擬);
# 被 import 時(例如 tests/integration/test_fake_signatures.py 走訪 cgb.adapters)什麼都不做,不在桌機上量硬體、連 Ollama 或啟動 serve
if __name__ == "__main__":
    main()
