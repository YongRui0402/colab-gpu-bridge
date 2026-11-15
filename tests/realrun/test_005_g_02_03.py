"""005 G-03 與 G-02(tasks.md T172、T171):真的 Colab T4 上,開啟時間與「平行數 1 對自動值」的吞吐量。

使用者 2026-11-15 23:05 決定只跑 T4(G-01 的 A100 與要 US3 的 G-04 不跑,`分身決策紀錄.md`);US3 這次不做,
所以平行數 1 改用 US2 的開啟前覆蓋:同一種類型開兩次,第一次全部自動(順便量 G-03 的開啟時間),
第二次平行數填 1。照 001 testplan 的實跑共同護欄 P1~P9:`realrun` fixture 以暫存 `HOME` 複製授權(P9)、
P2 記開始的餘額、整批結束做 P3;容器階段的 `Stack` 起 `docker compose -p cgb-test`(127.0.0.1:8780、11436,
不碰 11434)。本批自己的預算:整批 50 分鐘、1.5 compute units,每台 30 分鐘內(plan Q29),超過就結束工作階段。

量法(testplan G-01/G-02):暖機一次後,把同一批 16 題經相容端點同時送出 3 次(每題 `num_predict` 128、
`temperature` 0),記每次總耗時與中位數;量測期間 `/api/ps` 的 `size_vram` 與 `size`;
遠端 `/root/cgb-ollama-serve.log` 的 `flash_attn`、`K (q8_0)`/`type_k` 與 `n_seq_max`。判定者:腳本。
"""

import json
import os
import tempfile
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path

from realrun.conftest import write_measurement  # noqa: F401 - 只用來確保 conftest 載入
from realrun.helpers_container import TERMINAL, get_stack

MODEL = "qwen2.5:7b"
BATCH_SECONDS = 50 * 60
BATCH_UNITS = 1.5
SESSION_SECONDS = 30 * 60
PULL_TIMEOUT = 15 * 60
REQUEST_TIMEOUT = 600
ROUNDS = 3
OPEN_004_T4_SECONDS = 56.7  # specs/004-chat-hf-curated-queue/measurements.md G-06 的 T4 開啟
G03_SLACK = 5.0
G02_RATIO = 0.85
MEASUREMENTS = Path(__file__).resolve().parents[2] / "specs/005-ollama-machine-tuning/measurements.md"

# 固定 16 題(未用來調整級距;testplan G-01「判定者與樣本」)
PROMPTS = [
    "用三句話說明什麼是 TCP 三向交握。",
    "Explain the difference between a process and a thread.",
    "列出五種常見的排序演算法並說明時間複雜度。",
    "What is the capital of Australia and why was it chosen?",
    "用簡單的話解釋什麼是區塊鏈。",
    "Write a haiku about autumn rain.",
    "說明 HTTP 狀態碼 404 與 500 的差別。",
    "Summarize the plot of Romeo and Juliet in four sentences.",
    "什麼是光合作用?請分步驟說明。",
    "Give three tips for writing clean Python code.",
    "解釋 CPU 快取的 L1、L2、L3 有什麼不同。",
    "What causes the seasons on Earth?",
    "用一段話介紹台灣的地理位置。",
    "Describe how a hash table works.",
    "說明什麼是機器學習的過擬合,以及如何避免。",
    "List four benefits of regular exercise.",
]

# 在遠端 kernel 讀 serve 的 log(只印和設定有關的行,不印其他內容)
LOG_PROBE = r"""
import re
keys = ("server config", "flash_attn", "type_k", "K (q8_0)", "n_seq_max", "OLLAMA_NUM_PARALLEL", "OLLAMA_KV_CACHE_TYPE")
try:
    lines = open("/root/cgb-ollama-serve.log", errors="replace").read().splitlines()
except OSError as error:
    print("LOGPROBE-ERROR", error)
    lines = []
for line in lines:
    if any(k in line for k in keys):
        print("LOGPROBE", line[:600])
print("LOGPROBE-DONE", len(lines))
"""


def one_round(stack) -> tuple[float, list[str]]:
    """16 題同時送出,回(總秒數, 失敗的說明)。"""
    errors: list[str] = []
    lock = threading.Lock()

    def ask(prompt: str) -> None:
        body = {"model": MODEL, "prompt": prompt, "stream": False, "options": {"num_predict": 128, "temperature": 0, "seed": 1}}
        try:
            response, _ = stack.ollama("POST", "/api/generate", body, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                with lock:
                    errors.append(f"{response.status_code}")
        except Exception as error:  # noqa: BLE001 - 記下來,算這一輪失敗
            with lock:
                errors.append(type(error).__name__)

    threads = [threading.Thread(target=ask, args=(p,)) for p in PROMPTS]
    started = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return time.monotonic() - started, errors


def remote_log(realrun, name: str, probe_path: Path) -> list[str]:
    result = realrun.colab("exec", "-s", name, "-f", str(probe_path), "--timeout", "60", timeout=180)
    realrun.record_raw("g02_log", f"$ colab exec -s {name} -f logprobe (exit {result.returncode})\n{result.stdout}{result.stderr}\n")
    return [line for line in result.stdout.splitlines() if line.startswith("LOGPROBE")]


def measure(stack, realrun, name: str, probe_path: Path, deadline: float) -> dict:
    """下載模型、暖機、量 3 輪;回這一組的數字。"""
    out: dict = {"name": name}
    pull, pull_s = stack.ollama("POST", "/api/pull", {"model": MODEL, "stream": False}, timeout=PULL_TIMEOUT)
    out["pull"] = f"{pull.status_code},{pull_s:.0f} 秒"
    if pull.status_code != 200:
        raise RuntimeError(f"下載 {MODEL} 回 {pull.status_code}")
    warm, warm_s = stack.ollama(
        "POST", "/api/generate", {"model": MODEL, "prompt": "hi", "stream": False, "options": {"num_predict": 8}}, timeout=REQUEST_TIMEOUT
    )
    out["warm"] = f"{warm.status_code},{warm_s:.1f} 秒"
    session = stack.session() or {}
    out["tuning"] = {k: (v or {}).get("value") for k, v in ((session.get("ollama") or {}).get("tuning") or {}).items()}
    out["sources"] = {k: (v or {}).get("source") for k, v in ((session.get("ollama") or {}).get("tuning") or {}).items()}
    out["machine"] = (session.get("ollama") or {}).get("machine")
    rounds: list[float] = []
    for i in range(ROUNDS):
        if time.monotonic() > deadline:
            out["stopped"] = f"第 {i + 1} 輪前超過時限"
            break
        seconds, errors = one_round(stack)
        rounds.append(seconds)
        if errors:
            out.setdefault("errors", []).append(f"第 {i + 1} 輪:{errors}")
        if i == 0:
            ps, _ = stack.ollama("GET", "/api/ps")
            models = ps.json().get("models", []) if ps.status_code == 200 else []
            out["ps"] = [(m.get("name"), m.get("size"), m.get("size_vram")) for m in models]
    out["rounds"] = [round(r, 1) for r in rounds]
    out["median"] = statistics.median(rounds) if rounds else None
    out["log"] = remote_log(realrun, name, probe_path)
    return out


def open_and_wait(stack, tuning: dict) -> tuple[dict, float]:
    response = stack.ui("POST", "/api/session", {"runtimeType": {"gpu": "T4", "highMem": False}, "tuning": tuning})
    if response.status_code != 202:
        raise RuntimeError(f"POST /api/session 回 {response.status_code}:{response.text[:200]}")
    stack.guard_name(response.json().get("name"))
    last, elapsed, _ = stack.poll_session(lambda s: s.get("state") in ("ready", *TERMINAL), 330, 2)
    return last or {}, elapsed


def end_session(stack) -> None:
    current = stack.session() or {}
    if current.get("state") not in TERMINAL and current.get("state") is not None:
        stack.ui("DELETE", "/api/session")
        stack.poll_session(lambda s: s.get("state") in TERMINAL, 180)


def test_005_g_02_03(realrun):
    stack = get_stack(realrun)
    if not stack.colab_ok:
        raise AssertionError(f"沒有開執行環境:{stack.colab_reason}")
    probe_path = realrun.root / "logprobe.py"
    probe_path.write_text(LOG_PROBE, encoding="utf-8")

    t0 = time.monotonic()
    start_usage, _ = realrun.read_usage()
    start_balance = start_usage[0] if start_usage else None
    data: dict = {"startBalance": start_balance, "groups": {}}
    auto_none = {"numParallel": None, "contextLength": None, "maxLoadedModels": None}
    try:
        leftover = stack.ensure_no_active()
        if leftover:
            data["leftover"] = leftover
        for label, tuning in (("auto", auto_none), ("parallel1", {**auto_none, "numParallel": 1})):
            if time.monotonic() - t0 > BATCH_SECONDS:
                data[f"{label}-skipped"] = "整批超過時限"
                break
            usage, _ = realrun.read_usage()
            if usage and start_balance is not None and start_balance - usage[0] >= BATCH_UNITS:
                data[f"{label}-skipped"] = f"餘額少了 {start_balance - usage[0]:.2f}"
                break
            opened_at = time.monotonic()
            last, open_s = open_and_wait(stack, tuning)
            group: dict = {"open": round(open_s, 1), "state": last.get("state"), "reason": last.get("reasonCode")}
            data["groups"][label] = group
            if last.get("state") != "ready":
                raise RuntimeError(f"{label} 沒有就緒:{last.get('reasonCode')} {last.get('message')}")
            group.update(measure(stack, realrun, last["name"], probe_path, opened_at + SESSION_SECONDS - 120))
            end_session(stack)
            group["sessionMinutes"] = round((time.monotonic() - opened_at) / 60, 1)
    except RuntimeError as error:
        data["error"] = str(error)
    finally:
        end_session(stack)
        end_usage, _ = realrun.read_usage()
        if end_usage and start_balance is not None:
            data["used"] = round(start_balance - end_usage[0], 2)
        data["minutes"] = round((time.monotonic() - t0) / 60, 1)
        stack.stop_recording()
        problems = realrun.p3_cleanup()
        data["p3Rows"] = stack.test_rows("P3 之後")
        data["p3Problems"] = problems

    auto, p1 = data["groups"].get("auto", {}), data["groups"].get("parallel1", {})
    g03 = auto.get("state") == "ready" and auto.get("open") is not None and auto["open"] <= OPEN_004_T4_SECONDS + G03_SLACK
    ratio = auto["median"] / p1["median"] if auto.get("median") and p1.get("median") else None
    vram_ok = all(size == vram for g in (auto, p1) for _, size, vram in g.get("ps", [])) and bool(auto.get("ps")) and bool(p1.get("ps"))
    auto_log = " ".join(auto.get("log", []))
    p1_log = " ".join(p1.get("log", []))
    fa_ok = "flash_attn" in auto_log and ("enabled" in auto_log or "= 1" in auto_log)
    kv_ok = "q8_0" in auto_log
    g02 = ratio is not None and ratio <= G02_RATIO and vram_ok and fa_ok and kv_ok
    data.update({"g03": g03, "ratio": ratio, "vramOk": vram_ok, "faOk": fa_ok, "kvOk": kv_ok, "g02": g02, "p1Log": p1_log[:300]})

    # 暫存目錄整批結束後會刪掉,原始數字另存到 CGB_REALRUN_OUT(沒設時是系統暫存資料夾)
    raw = Path(os.environ.get("CGB_REALRUN_OUT") or tempfile.gettempdir()) / f"cgb-005-g02-{datetime.now():%Y%m%d-%H%M%S}.json"
    raw.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with MEASUREMENTS.open("a", encoding="utf-8") as f:
        f.write(
            f"\n## G-03(T172)與 G-02(T171)真的 Colab T4\n\n"
            f"- 日期:{datetime.now():%Y-%m-%d %H:%M};總時間 {data['minutes']} 分,用掉 {data.get('used')} compute units;P3 之後 cgb-test- 的行 {data['p3Rows']}\n"
            f"- 自動值:開啟 {auto.get('open')} 秒;設定 {auto.get('tuning')};來源 {auto.get('sources')};3 輪 {auto.get('rounds')} 秒,中位數 {auto.get('median')}\n"
            f"- 平行數 1:開啟 {p1.get('open')} 秒;設定 {p1.get('tuning')};3 輪 {p1.get('rounds')} 秒,中位數 {p1.get('median')}\n"
            f"- `/api/ps`(size, size_vram):自動 {auto.get('ps')};平行 1 {p1.get('ps')}\n"
            f"- **G-03 開啟 {auto.get('open')} 秒,門檻 ≤ 004 的 {OPEN_004_T4_SECONDS} + {G03_SLACK} 秒:{'過' if g03 else '沒過'}**\n"
            f"- **G-02 自動值 / 平行 1 = {None if ratio is None else round(ratio, 3)},門檻 ≤ {G02_RATIO};size_vram = size {vram_ok};"
            f"flash attention {fa_ok};KV q8_0 {kv_ok}:{'過' if g02 else '沒過'}**\n"
            f"- 其他:{ {k: data[k] for k in ('error', 'leftover', 'p3Problems') if data.get(k)} }\n"
        )
    assert g03 and g02, json.dumps({k: data[k] for k in ("g03", "ratio", "vramOk", "faOk", "kvOk")}, ensure_ascii=False)
