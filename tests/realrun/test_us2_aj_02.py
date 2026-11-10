"""US2-AJ-02(tasks.md T182):經本系統轉送的延遲比直連轉發多不到 0.5 秒;標準 `ollama` 用戶端讀得懂(SC-005)。

沿用 US1-AJ-17 的 T4,約 3 分鐘、約 0.06 compute units。
前置「經 UI 預先載入 qwen2.5:0.5b」:目錄只列已下載的模型,所以先經 UI API 下載(`POST /api/downloads`),
完成後 `POST /api/models/preload`(`keep_alive: -1`,之後的 US1-AJ-18 也要它在記憶體裡)。
直連:在容器裡(`docker exec`)以 Python 打 `127.0.0.1:11435`,計時只包住那一個請求,不含 docker exec 本身。
`ollama` 指令一律帶 `OLLAMA_HOST=http://127.0.0.1:11436`,不連 11434(P6)。判定者:腳本(0.5 秒門檻);樣本:20 次請求。
"""

import json
import os
import subprocess
import time

from realrun.conftest import OLLAMA_PORT, check_port
from realrun.helpers_container import OLLAMA, SMALL, generate_body, get_stack, mean, verdict

DIRECT = r"""
import json, sys, time, urllib.request
body = sys.stdin.read().encode()
req = urllib.request.Request("http://127.0.0.1:11435/api/generate", data=body, headers={"Content-Type": "application/json"})
t = time.monotonic()
with urllib.request.urlopen(req, timeout=300) as r:
    r.read()
    print(json.dumps({"s": time.monotonic() - t, "status": r.status}))
"""
DOWNLOAD_DEADLINE = 300
PRELOAD_DEADLINE = 300


def download_and_preload(stack, model: str) -> tuple[float, float, str]:
    """經 UI API 下載並預先載入;回(下載秒數, 預先載入秒數, 說明)。"""
    started = time.monotonic()
    response = stack.ui("POST", "/api/downloads", {"models": [model]})
    if response.status_code != 201:
        return -1, -1, f"POST /api/downloads 回 {response.status_code}:{response.text[:160]}"
    state = None
    while time.monotonic() - started <= DOWNLOAD_DEADLINE:
        jobs = [j for j in stack.ui("GET", "/api/downloads").json().get("jobs", []) if j["model"] == model]
        state = jobs[-1]["state"] if jobs else None
        if state in ("completed", "failed"):
            break
        time.sleep(2)
    downloaded = time.monotonic() - started
    if state != "completed":
        return downloaded, -1, f"下載沒有完成:{state}"
    started = time.monotonic()
    response = stack.ui("POST", "/api/models/preload", {"name": model})
    if response.status_code != 202:
        return downloaded, -1, f"POST /api/models/preload 回 {response.status_code}:{response.text[:160]}"
    while time.monotonic() - started <= PRELOAD_DEADLINE:
        items = [m for m in stack.ui("GET", "/api/models").json().get("items", []) if m["name"] == model]
        if items and items[0]["loaded"]:
            return downloaded, time.monotonic() - started, ""
        if items and items[0]["preload"]["state"] == "failed":
            return downloaded, -1, f"預先載入失敗:{items[0]['preload'].get('reasonCode')}"
        time.sleep(2)
    return downloaded, -1, "預先載入逾時"


def ollama_cli(*args: str) -> subprocess.CompletedProcess[str]:
    check_port(OLLAMA_PORT)
    env = {**os.environ, "OLLAMA_HOST": OLLAMA}
    return subprocess.run(["ollama", *args], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)


def test_us2_aj_02(realrun):
    stack = get_stack(realrun)
    stack.require("US2-AJ-02", "T182", "main_ready")
    extra: list[str] = []

    downloaded_s, preload_s, problem = download_and_preload(stack, SMALL)
    stack.state["small_loaded"] = not problem
    if problem:
        verdict("US2-AJ-02", "T182", {"前置": False}, f"下載 {downloaded_s:.1f} 秒", "前置:下載並預先載入 qwen2.5:0.5b", [problem])

    body = generate_body(SMALL, 8)
    via, direct, errors = [], [], []
    for _ in range(10):
        response, seconds = stack.ollama("POST", "/api/generate", body, timeout=300)
        if response.status_code == 200:
            via.append(seconds)
        else:
            errors.append(f"11436 回 {response.status_code}")
        result = stack.docker_exec("python", "-c", DIRECT, stdin=json.dumps(body), timeout=330)
        try:
            measured = json.loads(result.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            errors.append(f"直連沒有結果(exit {result.returncode})")
            continue
        if measured.get("status") == 200:
            direct.append(measured["s"])
        else:
            errors.append(f"11435 回 {measured.get('status')}")
    diff = mean(via) - mean(direct)

    listed = ollama_cli("list")
    ran = ollama_cli("run", SMALL, "你好")
    realrun.record_raw(
        "us2_aj_02",
        f"$ ollama list (exit {listed.returncode})\n{listed.stdout}{listed.stderr}\n"
        f"$ ollama run (exit {ran.returncode})\n{ran.stdout}{ran.stderr}\n",
    )
    if errors:
        extra.append(f"失敗的請求:{errors[:5]}")

    checks = {
        "則1": len(via) == 10 and len(direct) == 10 and diff <= 0.5,
        "則2": listed.returncode == 0 and SMALL in listed.stdout,
        "則3": ran.returncode == 0 and bool(ran.stdout.strip()),
    }
    numbers = (
        f"前置:下載 {downloaded_s:.1f} 秒、預先載入 {preload_s:.1f} 秒;經 11436 平均 {mean(via):.3f} 秒({len(via)} 次)、"
        f"直連 11435 平均 {mean(direct):.3f} 秒({len(direct)} 次),差 {diff:.3f} 秒;ollama run 輸出 {len(ran.stdout.strip())} 字"
    )
    verdict("US2-AJ-02", "T182", checks, numbers, "則1 平均差 ≤ 0.5 秒;則2 ollama list 列出;則3 ollama run 非空", extra)

