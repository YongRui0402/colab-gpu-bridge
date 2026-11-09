"""讀 Colab 執行環境的剩餘磁碟與顯示記憶體(`contracts/colab-cli.openapi.yaml` § `paths./exec/probe-resources.post`)。

由後端以 `colab exec -f` 送到遠端 kernel 執行;只讀,不改任何東西。
結果印成 stdout 的一行 `CGB-RESULT <JSON>`(`ProbeScriptResult`);讀不到磁碟時 `ok` 為 false。
"""

import json
import os
import shutil
import subprocess

MODELS_DIR = "/root/.ollama/models"
FALLBACK_DIR = "/root"
MIB = 1048576


def report(**result):
    print("CGB-RESULT " + json.dumps(result), flush=True)


def read_gpu():
    """第一張 GPU 的名稱、總量與可用量(位元組);沒有 nvidia-smi 或失敗時三個都是 None。"""
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
        name, total, free = (field.strip() for field in output.splitlines()[0].split(","))
        return name, int(total) * MIB, int(free) * MIB
    except Exception:  # noqa: BLE001 - 讀不到顯示記憶體不算失敗
        return None, None, None


def main():
    path = MODELS_DIR if os.path.isdir(MODELS_DIR) else FALLBACK_DIR
    try:
        usage = shutil.disk_usage(path)
    except OSError as error:
        report(ok=False, detail=f"disk_usage({path}) failed: {error}")
        return
    gpu_name, vram_total, vram_free = read_gpu()
    report(
        ok=True,
        diskFreeBytes=usage.free,
        diskTotalBytes=usage.total,
        gpuName=gpu_name,
        vramTotalBytes=vram_total,
        vramFreeBytes=vram_free,
    )


main()
