"""005 G-04(tasks.md T173)與 006 G-04(tasks.md T047):同一台真的 Colab T4。

使用者本人 2026-11-16 在場、同意後才執行。照 001 testplan 的實跑共同護欄 P1~P9:`realrun` fixture 以暫存 `HOME`
複製授權(P9)、P2 記開始的餘額、整批結束做 P3;`Stack` 起 `docker compose -p cgb-test`(127.0.0.1:8780、11436,
不碰 11434)。本批自己的預算:30 分鐘、0.8 compute units,超過就結束工作階段。

順序:
1. 以覆蓋值 context 32768 開一台 T4(006 G-04 的前提,順便驗 research R5 的建議值),經 UI 的下載佇列下載 `qwen2.5:7b`。
2. 006 G-04:opencode 照 `GET /api/connect` 的片段原樣接上本系統相容端點,做 G-01 同一個讀檔任務;
   記 `/api/ps` 的 `size` 與 `size_vram`。opencode 用暫存 `HOME`,不讀寫使用者的 `~/.config/opencode`。
3. 005 G-04:沒有下載與請求時,以平行數 4 套用並重啟,記確認到重啟完成(`step` 離開 `restarting_ollama`)
   與回到就緒的時間;`/api/ps` 列出 `qwen2.5:7b`;遠端 log 的 `n_seq_max` 為 4。
判定者:腳本。
"""

import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

from realrun.conftest import check_model, mask_urls
from realrun.helpers_container import TERMINAL, get_stack
from realrun.test_005_g_02_03 import LOG_PROBE, end_session, remote_log
from realrun.test_006_g_01 import PROMPT, SECRET, client_env, fill_host, json_lines, make_project, run_client

MODEL = "qwen2.5:7b"
CONTEXT = 32768
BATCH_SECONDS = 30 * 60
BATCH_UNITS = 0.8
PULL_TIMEOUT = 15 * 60
OPENCODE_SECONDS = 600
RESTART_LIMIT = 90.0
APPLY_TIMEOUT = 600
REPO = Path(__file__).resolve().parents[2]
M005 = REPO / "specs/005-ollama-machine-tuning/measurements.md"
M006 = REPO / "specs/006-agent-client-connect/measurements.md"


def ps_rows(stack) -> list[tuple]:
    ps, _ = stack.ollama("GET", "/api/ps")
    models = ps.json().get("models", []) if ps.status_code == 200 else []
    return [(m.get("name"), m.get("size"), m.get("size_vram"), m.get("context_length")) for m in models]


def download(stack) -> str:
    check_model(MODEL)
    queued = stack.ui("POST", "/api/downloads", {"models": [MODEL]})
    started = time.monotonic()
    job = None
    while time.monotonic() - started <= PULL_TIMEOUT and queued.status_code in (200, 201, 202):
        jobs = stack.ui("GET", "/api/downloads").json().get("jobs", [])
        job = next((j for j in jobs if j.get("model", "").lower() == MODEL), None)
        if job and job.get("state") in ("completed", "failed"):
            break
        time.sleep(3)
    summary = f"加入 {queued.status_code};{(job or {}).get('state')}({(job or {}).get('reasonCode')}),{time.monotonic() - started:.0f} 秒"
    if (job or {}).get("state") != "completed":
        raise RuntimeError(f"下載 {MODEL} 沒有完成:{summary}")
    return summary


def g04_006(stack, root: Path) -> dict:
    out: dict = {}
    opencode = shutil.which("opencode")
    if opencode is None:
        raise RuntimeError("PATH 上沒有 opencode")
    connect = stack.ui("GET", "/api/connect").json()
    out["connect"] = {k: connect.get(k) for k in ("ollamaPort", "contextLength", "recommendedContextLength", "shouldWarn", "models")}
    home = root / "oc-home"
    env = client_env(home)
    config = home / ".config" / "opencode" / "opencode.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(fill_host(connect["snippets"]["opencode"]), encoding="utf-8")
    out["version"] = run_client([opencode, "--version"], root, env, 60).stdout.strip()
    project = make_project(root)
    run = run_client([opencode, "run", "--format", "json", "-m", f"cgb/{MODEL}", PROMPT], project, env, OPENCODE_SECONDS)
    events = json_lines(run.stdout)
    tools = [e["part"].get("tool") for e in events if e.get("type") == "tool_use" and isinstance(e.get("part"), dict)]
    text = "".join(e["part"].get("text", "") for e in events if e.get("type") == "text" and isinstance(e.get("part"), dict))
    tokens = [e["part"].get("tokens", {}).get("input") for e in events if e.get("type") == "step_finish" and isinstance(e.get("part"), dict)]
    out.update(code=run.code, timedOut=run.timed_out, seconds=round(run.seconds, 1), tools=tools, tokens=tokens,
               text=text[:80], cleanup=run.cleanup, ps=ps_rows(stack))  # fmt: skip
    if not (SECRET in text and "read" in tools):
        out["stderrTail"] = [mask_urls(line)[:200] for line in run.stderr.strip().splitlines()[-3:]]
    out["then1"] = run.code == 0 and not run.timed_out and SECRET in text and "read" in tools
    out["then2"] = bool(out["ps"]) and all(size == vram for _, size, vram, _ in out["ps"])
    return out


def g04_005(stack, realrun, name: str, probe_path: Path) -> dict:
    out: dict = {"before": ps_rows(stack)}
    body = {"numParallel": 4, "contextLength": CONTEXT, "maxLoadedModels": None}
    started = time.monotonic()
    response = stack.ui("POST", "/api/session/tuning", body)
    out["accepted"] = response.status_code
    if response.status_code != 202:
        out["body"] = response.text[:300]
        return out
    restarted_at = None
    last: dict = {}
    while time.monotonic() - started <= APPLY_TIMEOUT:
        last = stack.session() or {}
        if restarted_at is None and (last.get("step") != "restarting_ollama" or last.get("state") != "applying_tuning"):
            restarted_at = time.monotonic() - started
        if last.get("state") in ("ready", *TERMINAL):
            break
        time.sleep(1)
    out["restartSeconds"] = None if restarted_at is None else round(restarted_at, 1)
    out["readySeconds"] = round(time.monotonic() - started, 1)
    out["state"] = last.get("state")
    out["reason"] = last.get("reasonCode")
    out["tuning"] = {k: (v or {}).get("value") for k, v in ((last.get("ollama") or {}).get("tuning") or {}).items()}
    out["after"] = ps_rows(stack)
    out["log"] = remote_log(realrun, name, probe_path)
    seq = [int(m) for line in out["log"] for m in re.findall(r"n_seq_max\s*=\s*(\d+)", line)]
    out["nSeqMax"] = seq
    # testplan G-04 則1:確認到回到就緒、不含重新載入模型 → 以重啟完成(離開 restarting_ollama)的時間判定
    out["then1"] = out["state"] == "ready" and out["restartSeconds"] is not None and out["restartSeconds"] <= RESTART_LIMIT
    out["then2"] = any((row[0] or "").startswith(MODEL) for row in out["after"])
    out["then3"] = bool(seq) and seq[-1] == 4
    return out


def test_005_006_g_04(realrun):
    stack = get_stack(realrun)
    if not stack.colab_ok:
        raise AssertionError(f"沒有開執行環境:{stack.colab_reason}")
    probe_path = realrun.root / "logprobe.py"
    probe_path.write_text(LOG_PROBE, encoding="utf-8")
    t0 = time.monotonic()
    start_usage, _ = realrun.read_usage()
    start_balance = start_usage[0] if start_usage else None
    data: dict = {"startBalance": start_balance}
    try:
        leftover = stack.ensure_no_active()
        if leftover:
            data["leftover"] = leftover
        response = stack.ui(
            "POST", "/api/session",
            {"runtimeType": {"gpu": "T4", "highMem": False}, "tuning": {"numParallel": None, "contextLength": CONTEXT, "maxLoadedModels": None}},
        )  # fmt: skip
        if response.status_code != 202:
            raise RuntimeError(f"POST /api/session 回 {response.status_code}:{response.text[:200]}")
        stack.guard_name(response.json().get("name"))
        last, open_s, _ = stack.poll_session(lambda s: s.get("state") in ("ready", *TERMINAL), 330, 2)
        last = last or {}
        data["open"] = {"seconds": round(open_s, 1), "state": last.get("state"), "reason": last.get("reasonCode")}
        if last.get("state") != "ready":
            raise RuntimeError(f"沒有就緒:{last.get('reasonCode')} {last.get('message')}")
        name = last["name"]
        data["pull"] = download(stack)
        data["006"] = g04_006(stack, realrun.root)
        usage, _ = realrun.read_usage()
        if time.monotonic() - t0 > BATCH_SECONDS or (usage and start_balance is not None and start_balance - usage[0] >= BATCH_UNITS):
            data["005-skipped"] = "超過本批時間或額度"
        else:
            data["005"] = g04_005(stack, realrun, name, probe_path)
    except RuntimeError as error:
        data["error"] = str(error)
        failed_name = (stack.session() or {}).get("name") or "unknown"
        log_text = stack.save_compose_logs(failed_name).read_text(encoding="utf-8", errors="replace")
        keys = ("ERROR", "WARNING", "Traceback", "通道")
        data["composeTail"] = [mask_urls(line)[:300] for line in log_text.splitlines() if any(k in line for k in keys) and "token" not in line.lower()][-30:]
    finally:
        end_session(stack)
        end_usage, _ = realrun.read_usage()
        if end_usage and start_balance is not None:
            data["used"] = round(start_balance - end_usage[0], 2)
        data["minutes"] = round((time.monotonic() - t0) / 60, 1)
        stack.stop_recording()
        data["p3Problems"] = realrun.p3_cleanup()
        data["p3Rows"] = stack.test_rows("P3 之後")

    raw = Path(os.environ.get("CGB_REALRUN_OUT") or tempfile.gettempdir()) / f"cgb-g04-{datetime.now():%Y%m%d-%H%M%S}.json"
    raw.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    common = f"- 日期:{datetime.now():%Y-%m-%d %H:%M};同一台 T4(context 覆蓋 {CONTEXT});開啟 {data.get('open')};下載 {data.get('pull')};整批 {data['minutes']} 分,用掉 {data.get('used')} compute units;P3 之後 cgb-test- 的行 {data['p3Rows']}\n"
    other = {k: data[k] for k in ("error", "leftover", "p3Problems", "005-skipped") if data.get(k)}
    o6, o5 = data.get("006", {}), data.get("005", {})
    with M006.open("a", encoding="utf-8") as f:
        f.write(
            f"\n## G-04(T047)真的 Colab T4 上的 opencode\n\n{common}"
            f"- `/api/connect`:{o6.get('connect')};opencode {o6.get('version')}\n"
            f"- opencode 結束碼 {o6.get('code')}{'(逾時)' if o6.get('timedOut') else ''},{o6.get('seconds')} 秒;工具呼叫 {o6.get('tools')};每步 input tokens {o6.get('tokens')};回答前 80 字 {o6.get('text')!r}\n"
            f"- `/api/ps`(name, size, size_vram, context_length):{o6.get('ps')}\n"
            f"- **則1 輸出含 `{SECRET}` 且有 `read`:{'過' if o6.get('then1') else '沒過'};則2 size_vram = size:{'過' if o6.get('then2') else '沒過'};則3 見上方耗時與 compute units**\n"
            f"- 其他:{other} {({'stderrTail': o6['stderrTail']} if o6.get('stderrTail') else '')}\n"
        )
    with M005.open("a", encoding="utf-8") as f:
        f.write(
            f"\n## G-04(T173)真的 Colab T4 套用並重啟\n\n{common}"
            f"- 套用平行數 4:受理 {o5.get('accepted')};重啟完成 {o5.get('restartSeconds')} 秒、回到就緒 {o5.get('readySeconds')} 秒;狀態 {o5.get('state')}({o5.get('reason')});設定 {o5.get('tuning')}\n"
            f"- `/api/ps` 之前 {o5.get('before')};之後 {o5.get('after')};遠端 log 的 n_seq_max {o5.get('nSeqMax')}\n"
            f"- **則1 重啟 {RESTART_LIMIT:.0f} 秒內完成(不含重新載入模型):{'過' if o5.get('then1') else '沒過'};則2 `/api/ps` 列出 {MODEL}:{'過' if o5.get('then2') else '沒過'};"
            f"則3 n_seq_max = 4:{'過' if o5.get('then3') else '沒過'}**\n"
            f"- 其他:{other}\n"
        )
    summary = {"006": {k: o6.get(k) for k in ("then1", "then2")}, "005": {k: o5.get(k) for k in ("then1", "then2", "then3")}, "error": data.get("error")}
    assert o6.get("then1") and o6.get("then2") and o5.get("then1") and o5.get("then2") and o5.get("then3"), json.dumps(summary, ensure_ascii=False)
