"""在 Colab 執行環境上安裝並啟動 Ollama(`contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`)。

由後端以 `colab exec -f` 送到遠端 kernel 執行;`OLLAMA_HOST=127.0.0.1:11434`、`OLLAMA_ORIGINS=*`
由命令列的 `--env` 設進 kernel 的環境變數,這裡啟動的 `ollama serve` 繼承它們(只聽執行環境本機,NFR-003)。
冪等:Ollama 已在回應時不安裝也不再啟動。結果印成 stdout 的一行 `CGB-RESULT <JSON>`(`StartOllamaScriptResult`)。
"""

import json
import os
import subprocess
import time
import urllib.request

VERSION_URL = "http://127.0.0.1:11434/api/version"
# 官方安裝程式要 zstd 解壓縮,Colab 的映像沒有內建(spike 的做法;實跑 US1-CLI-21 第一次在這裡失敗)
INSTALL_COMMAND = (
    "(command -v zstd >/dev/null || apt-get -qq install -y zstd >/dev/null) "
    "&& curl -fsSL https://ollama.com/install.sh | sh"
)
SERVE_LOG = "/root/cgb-ollama-serve.log"
VERIFY_SECONDS = 60


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


def main():
    # (a)已有回應:重跑的情況,直接回報
    version = ollama_version()
    if version:
        report(ok=True, ollamaVersion=version, alreadyRunning=True)
        return

    # (b)官方安裝程式
    install = subprocess.run(INSTALL_COMMAND, shell=True, capture_output=True, text=True, check=False)
    if install.returncode != 0:
        report(ok=False, stage="install", detail=last_line(install.stderr) or last_line(install.stdout))
        return

    # (c)背景啟動,不跟著這次 exec 結束
    try:
        log = open(SERVE_LOG, "ab")
        subprocess.Popen(
            ["ollama", "serve"],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=dict(os.environ),
        )
    except OSError as error:
        report(ok=False, stage="start", detail=str(error))
        return

    # (d)每秒打一次 /api/version,60 秒內有回應即成功
    for _ in range(VERIFY_SECONDS):
        time.sleep(1)
        version = ollama_version()
        if version:
            report(ok=True, ollamaVersion=version, alreadyRunning=False)
            return
    try:
        with open(SERVE_LOG, encoding="utf-8", errors="replace") as f:
            detail = last_line(f.read())
    except OSError:
        detail = ""
    report(ok=False, stage="verify", detail=detail or "no response from /api/version within 60 seconds")


main()
