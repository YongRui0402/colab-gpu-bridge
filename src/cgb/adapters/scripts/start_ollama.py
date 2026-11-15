"""在 Colab 執行環境上安裝並啟動 Ollama(`contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`)。

由後端以 `colab exec -f` 送到遠端 kernel 執行;`OLLAMA_HOST=127.0.0.1:11434`、`OLLAMA_ORIGINS=*`
由命令列的 `--env` 設進 kernel 的環境變數,這裡啟動的 `ollama serve` 繼承它們(只聽執行環境本機,NFR-003)。
啟動前量第一張 GPU 的顯示記憶體,依級距決定平行數、context 長度與同時載入模型數(共用約定 12),
只帶給這一次啟動的 `ollama serve`,不改 kernel 自己的環境變數。
冪等:Ollama 已在回應時不安裝也不再啟動。結果印成 stdout 的一行 `CGB-RESULT <JSON>`(`StartOllamaScriptResult`)。

路徑、安裝指令與秒數可以用環境變數覆寫(預設值就是在 Colab 上用的值;本機測試接臨時 `ollama serve` 用,plan.md Q27、Q45、Q46)。
"""

import json
import os
import subprocess
import time
import urllib.request

# version URL 跟著 `OLLAMA_HOST`(Colab 上就是 127.0.0.1:11434)
VERSION_URL = "http://" + (os.environ.get("OLLAMA_HOST") or "127.0.0.1:11434") + "/api/version"
# 官方安裝程式要 zstd 解壓縮,Colab 的映像沒有內建(spike 的做法;實跑 US1-CLI-21 第一次在這裡失敗)
INSTALL_COMMAND = os.environ.get("CGB_INSTALL_COMMAND") or (
    "(command -v zstd >/dev/null || apt-get -qq install -y zstd >/dev/null) "
    "&& curl -fsSL https://ollama.com/install.sh | sh"
)
SERVE_LOG = os.environ.get("CGB_SERVE_LOG") or "/root/cgb-ollama-serve.log"
SERVE_PID_FILE = os.environ.get("CGB_SERVE_PID_FILE") or "/root/cgb-ollama-serve.pid"
TUNING_FILE = os.environ.get("CGB_TUNING_FILE") or "/root/cgb-ollama-tuning.json"
PROBE_TIMEOUT_SECONDS = float(os.environ.get("CGB_PROBE_TIMEOUT_SECONDS") or 10)
VERIFY_SECONDS = int(os.environ.get("CGB_VERIFY_SECONDS") or 60)
MIB = 1048576
GIB = 1073741824
# spec FR-002 的級距:顯示記憶體「以上、未滿」→(平行數, context 長度, 同時載入模型數);只看總量,不看 GPU 名稱
TIERS = (
    (64 * GIB, (16, 8192, 3)),
    (32 * GIB, (8, 8192, 2)),
    (20 * GIB, (4, 8192, 1)),
    (12 * GIB, (2, 4096, 1)),
    (0, (1, 4096, 1)),
)
TUNING_SOURCES = ("auto", "manual", "ollama_default")
# 交給 `ollama serve` 的五個設定;組環境前先從 kernel 的環境拿掉,同一個變數不會有兩個值
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
    except Exception:  # noqa: BLE001 - 還沒起來的各種錯誤都當成沒有回應
        return None


def last_line(text):
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def report(**result):
    print("CGB-RESULT " + json.dumps(result), flush=True)


def read_gpu():
    """第一張 GPU 的名稱與顯示記憶體總量(位元組);查詢參數和 `probe_resources.py` 相同,單位 MiB。

    沒有 `nvidia-smi`、非 0 結束或讀到 `[N/A]` 時兩個都是 None,不算失敗(FR-003)。
    """
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
    """`/proc/meminfo` 的 `MemTotal`(kB)轉成位元組;讀不到是 None。"""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def read_running_tuning():
    """設定檔裡的 `tuning`;檔案不存在、不是 JSON 或不是 `AppliedTuning` 的形狀(例如 005 之前開的)時是 None。"""
    try:
        with open(TUNING_FILE, encoding="utf-8") as f:
            tuning = json.load(f).get("tuning")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(tuning, dict):
        return None
    for key, _ in TUNING_ENV:
        item = tuning.get(key)
        if not (isinstance(item, dict) and "value" in item and item.get("source") in TUNING_SOURCES):
            return None
    return tuning


def decide(vram_total):
    """依顯示記憶體得到五項設定(`AppliedTuning`)與要帶給 `ollama serve` 的環境變數。"""
    if vram_total is None:
        # 讀不到:五項都不帶,`ollama serve` 只繼承 OLLAMA_HOST、OLLAMA_ORIGINS(和 004 相同)
        return {key: {"value": None, "source": "ollama_default"} for key, _ in TUNING_ENV}, {}
    numbers = next(values for floor, values in TIERS if vram_total >= floor)
    values = dict(zip(("numParallel", "contextLength", "maxLoadedModels"), numbers))
    values.update(flashAttention=True, kvCacheType="q8_0")
    tuning = {key: {"value": values[key], "source": "auto"} for key, _ in TUNING_ENV}
    env = {name: ("1" if values[key] is True else str(values[key])) for key, name in TUNING_ENV}
    return tuning, env


def serve_env(tuning_env):
    env = dict(os.environ)
    for _, name in TUNING_ENV:
        env.pop(name, None)
    env.update(tuning_env)
    return env


def main():
    # 啟動之前量硬體(共用約定 12 (a))
    gpu_name, vram_total = read_gpu()
    machine = {"gpuName": gpu_name, "vramTotalBytes": vram_total, "systemMemoryTotalBytes": read_system_memory()}
    tuning, tuning_env = decide(vram_total)

    # (a)已有回應:重跑的情況,不再啟動;設定照設定檔回報(不照這次的 CGB_TUNE_* 重算),硬體用這次量到的
    version = ollama_version()
    if version:
        report(ok=True, ollamaVersion=version, alreadyRunning=True, **machine, tuning=read_running_tuning())
        return

    # (b)官方安裝程式
    install = subprocess.run(INSTALL_COMMAND, shell=True, capture_output=True, text=True, check=False)
    if install.returncode != 0:
        report(ok=False, stage="install", detail=last_line(install.stderr) or last_line(install.stdout))
        return

    # (c)背景啟動,不跟著這次 exec 結束;先刪掉舊的設定檔,它只描述正在回應的那一個 serve(共用約定 13-1)
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
        report(ok=False, stage="start", detail=str(error))
        return
    # pid 檔:重啟腳本靠它找到要停的行程(共用約定 13);寫不了不算失敗,重啟改用 pgrep
    try:
        with open(SERVE_PID_FILE, "w", encoding="utf-8") as f:
            f.write(f"{serve.pid}\n")
    except OSError:
        pass

    # (d)每秒打一次 /api/version,60 秒內有回應即成功
    for _ in range(VERIFY_SECONDS):
        time.sleep(1)
        version = ollama_version()
        if version:
            applied = {**machine, "tuning": tuning}
            # 設定檔只描述正在回應的這一個 serve;已在執行時讀它回報(共用約定 13-1)
            try:
                with open(TUNING_FILE, "w", encoding="utf-8") as f:
                    json.dump(applied, f)
            except OSError:
                pass  # 寫不了不算失敗(共用約定 13-1)
            report(ok=True, ollamaVersion=version, alreadyRunning=False, **applied)
            return
    try:
        with open(SERVE_LOG, encoding="utf-8", errors="replace") as f:
            detail = last_line(f.read())
    except OSError:
        detail = ""
    report(ok=False, stage="verify", detail=detail or "no response from /api/version within 60 seconds")


main()
