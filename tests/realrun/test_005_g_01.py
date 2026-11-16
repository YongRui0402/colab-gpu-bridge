"""005 G-01(tasks.md T170):真的 Colab A100 上「平行數 1 對自動值」的吞吐量。

使用者本人 2026-11-16 在場、同意後才執行。照 001 testplan 的實跑共同護欄 P1~P9(`realrun` fixture、`Stack`,
不碰 11434)。US3 已完成,所以只開一台:先以自動值量,再經 `POST /api/session/tuning` 套用平行數 1 量,
省掉第二次開啟與下載(G-02 當時沒有 US3,才開兩次)。

本批預算:`CGB_G01_MINUTES` 分鐘(預設 25)、`CGB_G01_UNITS` compute units(預設 4.0);每一輪前檢查,
超過就跳過剩下的、結束工作階段。量法同 testplan G-01:暖機一次後 16 題同時送出 3 次(`num_predict` 128、
`temperature` 0),記總耗時中位數;`/api/ps` 的 `size_vram` 與 `size`;遠端 log 的 `server config` 與 `n_seq_max`。
判定者:腳本。
"""

import json
import os
import re
import statistics
import tempfile
import time
from datetime import datetime
from pathlib import Path

from realrun.helpers_container import TERMINAL, get_stack
from realrun.test_005_006_g_04 import download, ps_rows
from realrun.test_005_g_02_03 import LOG_PROBE, MODEL, REQUEST_TIMEOUT, ROUNDS, end_session, one_round, remote_log

BATCH_SECONDS = float(os.environ.get("CGB_G01_MINUTES", "25")) * 60
BATCH_UNITS = float(os.environ.get("CGB_G01_UNITS", "4.0"))
G01_RATIO = 0.60
APPLY_TIMEOUT = 600
MEASUREMENTS = Path(__file__).resolve().parents[2] / "specs/005-ollama-machine-tuning/measurements.md"
ENV_OF = {
    "OLLAMA_NUM_PARALLEL": "numParallel",
    "OLLAMA_CONTEXT_LENGTH": "contextLength",
    "OLLAMA_MAX_LOADED_MODELS": "maxLoadedModels",
    "OLLAMA_FLASH_ATTENTION": "flashAttention",
    "OLLAMA_KV_CACHE_TYPE": "kvCacheType",
}


def tuning_of(session: dict) -> dict:
    return {k: (v or {}).get("value") for k, v in ((session.get("ollama") or {}).get("tuning") or {}).items()}


def requests_ok(g: dict) -> bool:
    """暖機回 200、3 輪都量完且每輪 16 題都成功;任何一項不成立,這一組的耗時就不能下效能結論。"""
    return g.get("warmStatus") == 200 and not g.get("errors") and len(g.get("rounds") or []) == ROUNDS and g.get("median") is not None


def expected_env(tuning: dict) -> dict:
    """套用的五個值轉成 server config 的寫法(布林為 true / false)。缺值留 None,比對時算失敗。"""
    def norm(v):
        return None if v is None else str(v).lower() if isinstance(v, bool) else str(v)

    return {env: norm(tuning.get(key)) for env, key in ENV_OF.items()}


def server_config_of(log: list[str]) -> dict | None:
    """該組 log 裡最後一行 server config 的五個變數(重啟後會多一行,取最後一行);沒有那一行回 None。"""
    lines = [line for line in log if "server config" in line]
    if not lines:
        return None
    found = dict(re.findall(r"(OLLAMA_[A-Z_]+):(\S*)", lines[-1]))
    return {k: found.get(k) for k in ENV_OF}


def env_problems(name: str, g: dict) -> list[str]:
    config = server_config_of(g.get("log") or [])
    if config is None:
        return [f"{name}:log 沒有 server config 那一行"]
    expected = expected_env(g.get("tuning") or {})
    return [
        f"{name} {env}:預期 {expected[env]},實際 {config[env]}"
        for env in ENV_OF
        if expected[env] is None or config[env] is None or config[env].lower() != expected[env]
    ]


def judge(auto: dict, p1: dict) -> dict:
    """G-01 的判定(純函式,離線測試在 `tests/integration/test_005_g_01_judge.py`)。"""
    ok = requests_ok(auto) and requests_ok(p1)
    ratio = auto["median"] / p1["median"] if ok and p1["median"] else None
    vram_ok = bool(auto.get("ps")) and bool(p1.get("ps")) and all(r[1] == r[2] for g in (auto, p1) for r in g.get("ps", []))
    problems = env_problems("自動", auto) + env_problems("平行 1", p1)
    seq = {k: [int(m) for line in g.get("log", []) for m in re.findall(r"n_seq_max\s*=\s*(\d+)", line)] for k, g in (("auto", auto), ("p1", p1))}
    seq_ok = bool(seq["auto"]) and seq["auto"][-1] == auto.get("tuning", {}).get("numParallel") and bool(seq["p1"]) and seq["p1"][-1] == 1
    g01 = ratio is not None and ratio <= G01_RATIO and vram_ok and not problems and seq_ok
    return {
        "ratio": ratio, "requestsOk": ok, "vramOk": vram_ok, "envOk": not problems, "envProblems": problems,
        "nSeqMax": seq, "seqOk": seq_ok, "g01": g01,
    }


def group(stack, realrun, name: str, probe_path: Path, over) -> dict:
    out: dict = {}
    warm, warm_s = stack.ollama(
        "POST", "/api/generate", {"model": MODEL, "prompt": "hi", "stream": False, "options": {"num_predict": 8}}, timeout=REQUEST_TIMEOUT
    )
    out["warm"] = f"{warm.status_code},{warm_s:.1f} 秒"
    out["warmStatus"] = warm.status_code
    out["tuning"] = tuning_of(stack.session() or {})
    rounds: list[float] = []
    for i in range(ROUNDS):
        reason = over()
        if reason:
            out["stopped"] = f"第 {i + 1} 輪前:{reason}"
            break
        seconds, errors = one_round(stack)
        if errors:
            # 有請求失敗的輪次不算有效的耗時,不進中位數;只留紀錄
            out.setdefault("errors", []).append(f"第 {i + 1} 輪:{errors}")
            out.setdefault("failedRounds", []).append(round(seconds, 1))
        else:
            rounds.append(seconds)
        if i == 0:
            out["ps"] = ps_rows(stack)
    out["rounds"] = [round(r, 1) for r in rounds]
    out["median"] = statistics.median(rounds) if len(rounds) == ROUNDS else None
    out["log"] = remote_log(realrun, name, probe_path)
    return out


def test_005_g_01(realrun):
    stack = get_stack(realrun)
    if not stack.colab_ok:
        raise AssertionError(f"沒有開執行環境:{stack.colab_reason}")
    probe_path = realrun.root / "logprobe.py"
    probe_path.write_text(LOG_PROBE, encoding="utf-8")
    t0 = time.monotonic()
    start_usage, _ = realrun.read_usage()
    start_balance = start_usage[0] if start_usage else None
    data: dict = {"startBalance": start_balance, "budget": {"minutes": BATCH_SECONDS / 60, "units": BATCH_UNITS}}

    def over() -> str | None:
        if time.monotonic() - t0 > BATCH_SECONDS:
            return "超過本批時間"
        usage, _ = realrun.read_usage()
        if usage is None or start_balance is None:
            return "讀不到餘額"
        data["rate"] = usage[1]
        if round(start_balance - usage[0], 2) >= BATCH_UNITS:
            return f"餘額少了 {start_balance - usage[0]:.2f}"
        return None

    auto: dict = {}
    p1: dict = {}
    try:
        leftover = stack.ensure_no_active()
        if leftover:
            data["leftover"] = leftover
        last, open_s = stack.open(gpu="A100")
        last = last or {}
        data["open"] = {"seconds": round(open_s, 1), "state": last.get("state"), "reason": last.get("reasonCode")}
        if last.get("state") != "ready":
            raise RuntimeError(f"沒有就緒:{last.get('reasonCode')} {last.get('message')}")
        name = last["name"]
        data["machine"] = (last.get("ollama") or {}).get("machine")
        data["pull"] = download(stack)
        auto = group(stack, realrun, name, probe_path, over)
        reason = over()
        if reason:
            data["p1-skipped"] = reason
        else:
            started = time.monotonic()
            response = stack.ui("POST", "/api/session/tuning", {"numParallel": 1, "contextLength": None, "maxLoadedModels": None})
            data["apply"] = {"accepted": response.status_code}
            if response.status_code != 202:
                raise RuntimeError(f"套用平行數 1 回 {response.status_code}:{response.text[:200]}")
            after, _, _ = stack.poll_session(lambda s: s.get("state") in ("ready", *TERMINAL), APPLY_TIMEOUT, 1)
            data["apply"].update(seconds=round(time.monotonic() - started, 1), state=(after or {}).get("state"))
            if (after or {}).get("state") != "ready":
                raise RuntimeError(f"套用後沒有回到就緒:{(after or {}).get('reasonCode')}")
            p1 = group(stack, realrun, name, probe_path, over)
    except RuntimeError as error:
        data["error"] = str(error)
    finally:
        end_session(stack)
        end_usage, _ = realrun.read_usage()
        if end_usage and start_balance is not None:
            data["used"] = round(start_balance - end_usage[0], 2)
        data["minutes"] = round((time.monotonic() - t0) / 60, 1)
        stack.stop_recording()
        data["p3Problems"] = realrun.p3_cleanup()
        data["p3Rows"] = stack.test_rows("P3 之後")

    verdict = judge(auto, p1)
    ratio, vram_ok, env_ok, seq, seq_ok, g01 = (verdict[k] for k in ("ratio", "vramOk", "envOk", "nSeqMax", "seqOk", "g01"))
    data.update(verdict, auto=auto, p1=p1)

    raw = Path(os.environ.get("CGB_REALRUN_OUT") or tempfile.gettempdir()) / f"cgb-005-g01-{datetime.now():%Y%m%d-%H%M%S}.json"
    raw.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    other = {k: data[k] for k in ("error", "leftover", "p3Problems", "p1-skipped") if data.get(k)}
    with MEASUREMENTS.open("a", encoding="utf-8") as f:
        f.write(
            f"\n## G-01(T170)真的 Colab A100\n\n"
            f"- 日期:{datetime.now():%Y-%m-%d %H:%M};開啟 {data.get('open')};下載 {data.get('pull')};整批 {data['minutes']} 分,"
            f"用掉 {data.get('used')} compute units(用量 {data.get('rate')}/hr);P3 之後 cgb-test- 的行 {data['p3Rows']}\n"
            f"- 硬體:{data.get('machine')}\n"
            f"- 自動值:設定 {auto.get('tuning')};3 輪 {auto.get('rounds')} 秒,中位數 {auto.get('median')}\n"
            f"- 平行數 1(開著時套用 {data.get('apply')}):設定 {p1.get('tuning')};3 輪 {p1.get('rounds')} 秒,中位數 {p1.get('median')}\n"
            f"- `/api/ps`(name, size, size_vram, context_length):自動 {auto.get('ps')};平行 1 {p1.get('ps')};n_seq_max {seq}\n"
            f"- **G-01 自動值 / 平行 1 = {None if ratio is None else round(ratio, 3)},門檻 ≤ {G01_RATIO};size_vram = size {vram_ok};"
            f"請求全部成功(兩組暖機 200、各 {ROUNDS} 輪 16 題都沒失敗){verdict['requestsOk']};"
            f"server config 五個變數的值等於套用值 {env_ok};n_seq_max 等於套用值 {seq_ok}:{'過' if g01 else '沒過'}**\n"
            f"- 請求失敗:自動 {auto.get('errors')};平行 1 {p1.get('errors')};server config 比對問題:{verdict['envProblems']}\n"
            f"- 其他:{other}\n"
        )
    assert g01, json.dumps(
        {k: data[k] for k in ("ratio", "vramOk", "requestsOk", "envOk", "envProblems", "seqOk")} | {"error": data.get("error")}, ensure_ascii=False
    )
