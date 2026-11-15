"""G-06(tasks.md T232):真的 Colab 上,精選清單的自動下載、拉 hf.co 模型、對話與結束後清空佇列(testplan.md § 7.2 G-06)。

照 001 testplan 的實跑共同護欄 P1~P9:`realrun` fixture 複製授權(P9,使用者 2026-11-15 選照 P9 複製,Q72)、
P2 記開始的餘額、整批結束做 P3;容器階段的 `Stack` 起 `docker compose -p cgb-test`(UI 8780、相容端點 11436)。
G-06 自己的預算比 P2 緊:整批 0.3 compute units、20 分鐘,只開一台 T4(使用者 2026-11-15 同意);超過就結束工作階段、
寫成沒過,交給 P3 收尾。

模型只用 `hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M`(約 105 MB,testplan G-06 指定;不經 `check_model`,
那是 001 P7 的清單)。則3 以 `POST /api/chat` 的最後一行判斷:對話頁顯示每秒 token 數靠的就是 `eval_count`、`eval_duration`
都 > 0(沒有時是 `turn-norate`),畫面本身由 US2-AJ 案例驗過。判定者:腳本;樣本:一次實跑。
"""

import json
import time

import httpx

from integration.test_004_g_01 import ensure_measurements
from realrun.conftest import UI_PORT, check_port, write_measurement
from realrun.helpers_container import TERMINAL, UI, get_stack, parse_time

CASE, TASK = "G-06", "T232"
MODEL = "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"
G06_SECONDS = 20 * 60
G06_UNITS = 0.3
AUTO_DEADLINE = 30
DOWNLOAD_DEADLINE = 5 * 60
CHAT_TIMEOUT = 180
CLEAR_DEADLINE = 5
PROMPTS = ("Say hi in one word.", "Now say bye in one word.")


def _names(value) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("name", "model") and isinstance(v, str):
                found.add(v)
            found |= _names(v)
    elif isinstance(value, list):
        for v in value:
            found |= _names(v)
    return found


def _chat(messages: list[dict]) -> tuple[int, str, dict | None, int, float]:
    """回(狀態碼, Content-Type, 最後一行, 行數, 秒)。"""
    check_port(UI_PORT)
    started = time.monotonic()
    lines: list[dict] = []
    with httpx.stream("POST", f"{UI}/api/chat", json={"model": MODEL, "messages": messages}, timeout=CHAT_TIMEOUT) as r:
        ctype = r.headers.get("content-type", "")
        for raw in r.iter_lines():
            if raw.strip():
                try:
                    lines.append(json.loads(raw))
                except ValueError:
                    lines.append({"unparsed": raw[:200]})
        status = r.status_code
    return status, ctype, (lines[-1] if lines else None), len(lines), time.monotonic() - started


def test_004_g_06(realrun):
    path = ensure_measurements()
    stack = get_stack(realrun)
    if not stack.colab_ok:
        write_measurement(CASE, TASK, "—", "—", None, f"沒有開執行環境:{stack.colab_reason}", path=path)
        raise AssertionError(stack.colab_reason)

    t0 = time.monotonic()
    start_usage, _ = realrun.read_usage()
    start_balance = start_usage[0] if start_usage else None
    numbers: list[str] = [f"開始餘額 {start_balance}"]
    extra: list[str] = []
    checks: dict[str, bool] = {f"則{i}": False for i in range(1, 6)}

    def over_budget() -> str | None:
        if time.monotonic() - t0 > G06_SECONDS:
            return f"超過 {G06_SECONDS // 60} 分鐘"
        usage, _ = realrun.read_usage()
        if usage and start_balance is not None and round(start_balance - usage[0], 2) >= G06_UNITS:
            return f"餘額少了 {round(start_balance - usage[0], 2)},達到 {G06_UNITS}"
        return None

    name = None
    try:
        leftover = stack.ensure_no_active()
        if leftover:
            extra.append(f"開之前先結束了留下的 {leftover}")
        # 精選清單只有這一項,設自動下載
        for item in stack.ui("GET", "/api/curated").json()["items"]:
            stack.ui("DELETE", f"/api/curated/{item['id']}")
        added = stack.ui("POST", "/api/curated", {"name": MODEL, "description": "G-06", "autoDownload": True})
        numbers.append(f"新增精選 {added.status_code}")

        last, open_s = stack.open("T4", False)
        name = (last or {}).get("name")
        numbers.append(f"開啟 {open_s:.1f} 秒,狀態 {(last or {}).get('state')}")
        if (last or {}).get("state") != "ready":
            extra.append(f"沒有就緒:{(last or {}).get('reasonCode')}")
            raise RuntimeError("沒有就緒")
        ready_at = parse_time(last.get("readyAt"))

        # 則1:就緒後 30 秒內自動下載結果 排入 1、跳過 0
        result = None
        while time.monotonic() - t0 < G06_SECONDS:
            result = stack.ui("GET", "/api/downloads/auto-result").json().get("result")
            if result and result.get("state") == "done":
                break
            time.sleep(1)
        finished = parse_time((result or {}).get("finishedAt"))
        auto_s = (finished - ready_at).total_seconds() if finished and ready_at else None
        enq, skp = (result or {}).get("enqueued") or [], (result or {}).get("skipped") or []
        numbers.append(f"自動下載就緒後 {auto_s} 秒完成判定:排入 {len(enq)}、跳過 {len(skp)} {[s.get('reasonCode') or s.get('reason') for s in skp]}")
        checks["則1"] = auto_s is not None and auto_s <= AUTO_DEADLINE and len(enq) == 1 and not skp

        # 則2:下載完成後模型目錄有這個名稱
        dl_started = time.monotonic()
        job = None
        while time.monotonic() - dl_started <= DOWNLOAD_DEADLINE:
            jobs = stack.ui("GET", "/api/downloads").json().get("jobs", [])
            job = next((j for j in jobs if j.get("model", "").lower() == MODEL.lower()), None)
            if job and job.get("state") in ("completed", "failed"):
                break
            time.sleep(3)
        catalog = stack.ui("GET", "/api/models").json()
        in_catalog = any(n.lower() == MODEL.lower() for n in _names(catalog))
        numbers.append(
            f"下載 {(job or {}).get('state')}({(job or {}).get('reasonCode')}),{time.monotonic() - dl_started:.0f} 秒;目錄有這個名稱 {in_catalog}"
        )
        checks["則2"] = (job or {}).get("state") == "completed" and in_catalog
        tags = httpx.get("http://127.0.0.1:11436/api/tags", timeout=30)
        extra.append(f"相容端點 /api/tags {tags.status_code},列出 hf.co 名稱 {MODEL.lower() in tags.text.lower()}")

        reason = over_budget()
        if reason:
            extra.append(f"G-06 預算:{reason},不送對話")
            raise RuntimeError(reason)

        # 則3:兩則對話都完成、最後一行有 eval_count、eval_duration
        messages: list[dict] = []
        ok3 = True
        for i, prompt in enumerate(PROMPTS, 1):
            messages.append({"role": "user", "content": prompt})
            status, ctype, tail, count, secs = _chat(messages)
            tail = tail or {}
            done = tail.get("done") is True
            rate = done and (tail.get("eval_count") or 0) > 0 and (tail.get("eval_duration") or 0) > 0
            numbers.append(
                f"第 {i} 則 {status} {ctype.split(';')[0]},{count} 行,{secs:.1f} 秒,done {done},"
                f"eval_count {tail.get('eval_count')}、eval_duration {tail.get('eval_duration')}"
                + (f",錯誤 {tail['error'].get('code')}" if isinstance(tail.get("error"), dict) else "")
            )
            ok3 = ok3 and status == 200 and rate
            messages.append({"role": "assistant", "content": "ok"})
        checks["則3"] = ok3
    except RuntimeError:
        pass
    finally:
        # 則4:結束後 5 秒內 GET /api/downloads 0 筆
        current = stack.session() or {}
        if current.get("state") not in TERMINAL and current.get("state") is not None:
            ended = stack.ui("DELETE", "/api/session")
            t_end = time.monotonic()
            count = None
            clear_s = None
            while time.monotonic() - t_end <= CLEAR_DEADLINE + 1:
                count = len(stack.ui("GET", "/api/downloads").json().get("jobs", []))
                if count == 0:
                    clear_s = time.monotonic() - t_end
                    break
                time.sleep(0.5)
            numbers.append(f"結束 {ended.status_code},{clear_s if clear_s is None else round(clear_s, 2)} 秒後佇列 {count} 筆")
            checks["則4"] = clear_s is not None and clear_s <= CLEAR_DEADLINE
            stack.poll_session(lambda s: s.get("state") in TERMINAL, 120)
        end_usage, _ = realrun.read_usage()
        if end_usage and start_balance is not None:
            numbers.append(f"結束餘額 {end_usage[0]}(用掉 {round(start_balance - end_usage[0], 2)})")
        numbers.append(f"總時間 {(time.monotonic() - t0) / 60:.1f} 分")

        # 則5:P3 收尾後 colab sessions 沒有 cgb-test- 開頭的行
        stack.stop_recording()
        problems = realrun.p3_cleanup()
        rows = stack.test_rows("P3 之後")
        numbers.append(f"P3 之後 cgb-test- 的行 {rows}")
        checks["則5"] = rows == [] and not problems
        if problems:
            extra.extend(problems)

    failed = [k for k, ok in checks.items() if not ok]
    note = ";".join((["沒過:" + "、".join(failed)] if failed else []) + extra)
    threshold = (
        "則1:就緒後 30 秒內排入 1、跳過 0;則2:下載完成後模型目錄有這個名稱;則3:兩則對話都 200、最後一行 eval_count 與 "
        "eval_duration > 0;則4:結束後 5 秒內 GET /api/downloads 0 筆;則5:P3 後 colab sessions 沒有 cgb-test- 的行"
    )
    write_measurement(CASE, TASK, ";".join(numbers), threshold, not failed, note, path=path)
    assert not failed, note
