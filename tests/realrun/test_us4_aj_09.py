"""US4-AJ-09(tasks.md T288):用量頁的數字與 `colab usage` 一致;閒置時限到了自動結束、Colab 上不留這台(FR-024、FR-026、SC-006)。

前置:US1-AJ-21 之後沒有工作階段。開 1 台 T4(經 UI API)到就緒,之後**不送任何 Ollama 相容端點的請求**(閒置只看那邊的請求)。
- 用量頁的數字取 `GET /api/usage`;先等它在就緒之後讀過一次(最多 5 分鐘),同一分鐘內在主機執行 `HOME=<暫存目錄>/home colab usage`。
- 閒置時限以 `PUT /api/settings` 改成 1 分鐘(只在 cgb-test 這個實例),結束後一定改回 30。
- 每 5 秒讀一次 `GET /api/session`、`GET /api/usage` 與 `colab sessions`。
約 6 分鐘、約 0.12 compute units。判定者:腳本(0.05 差距與 1 分鐘門檻)。
"""

import time

from realrun.conftest import parse_usage
from realrun.helpers_container import TERMINAL, get_stack, now_utc, parse_time, verdict

USAGE_FRESH_DEADLINE = 300
IDLE_END_DEADLINE = 4 * 60
GONE_DEADLINE = 60


def test_us4_aj_09(realrun):
    stack = get_stack(realrun)
    stack.require("US4-AJ-09", "T288")
    leftover = stack.ensure_no_active()
    extra = [f"開之前先結束了前一個案例留下的 {leftover}"] if leftover else []
    settings = stack.ui("GET", "/api/settings").json()
    read_ats: list[str] = []

    def note_usage() -> dict:
        usage = stack.ui("GET", "/api/usage").json()
        if usage.get("readAt") and (not read_ats or read_ats[-1] != usage["readAt"]):
            read_ats.append(usage["readAt"])
        return usage

    try:
        note_usage()
        last, open_s = stack.open("T4", False)
        name = (last or {}).get("name")
        if (last or {}).get("state") != "ready":
            verdict("US4-AJ-09", "T288", {"前置": False}, f"開啟 {open_s:.1f} 秒", "就緒",
                    [f"沒有就緒:{(last or {}).get('state')}、{(last or {}).get('reasonCode')}"])  # fmt: skip
        ready_at = parse_time(last.get("readyAt")) or now_utc()

        # 則1、則2:用量頁(就緒之後讀到的那一次)與 colab usage
        started = time.monotonic()
        usage = note_usage()
        while (parse_time(usage.get("readAt")) or ready_at) < ready_at and time.monotonic() - started <= USAGE_FRESH_DEADLINE:
            time.sleep(5)
            usage = note_usage()
        cli = realrun.colab("usage", timeout=90)
        realrun.record_raw("us4_aj_09", f"$ colab usage (exit {cli.returncode})\n{cli.stdout}{cli.stderr}\n")
        cli_usage = parse_usage(cli.stdout) if cli.returncode == 0 else None
        fresh = (parse_time(usage.get("readAt")) or ready_at) >= ready_at
        if not fresh:
            extra.append("就緒後 5 分鐘內用量頁沒有新讀數,以最後一次比對")

        # 則3、則4:閒置 1 分鐘自動結束
        put = stack.ui("PUT", "/api/settings", {**settings, "idleTimeoutMinutes": 1})
        if put.status_code != 200:
            extra.append(f"PUT /api/settings 回 {put.status_code}")
        deadlines: list[str] = []
        ended_s = None
        session = None
        loop_started = time.monotonic()
        while time.monotonic() - loop_started <= IDLE_END_DEADLINE:
            session = stack.session() or {}
            note_usage()
            stack.colab_rows("US4-AJ-09 閒置中")
            idle = session.get("idle") or {}
            if idle.get("deadline") and (not deadlines or deadlines[-1] != idle["deadline"]):
                deadlines.append(idle["deadline"])
            if session.get("state") in TERMINAL:
                ended_s = now_utc()
                break
            time.sleep(5)
        gone_s = stack.wait_gone(name, GONE_DEADLINE) if ended_s else None
        note_usage()
    finally:
        restored = stack.ui("PUT", "/api/settings", {**settings, "idleTimeoutMinutes": 30})
        if restored.status_code != 200:
            extra.append(f"閒置時限改回 30 失敗:HTTP {restored.status_code}")

    deadline = parse_time(deadlines[-1]) if deadlines else None
    late = (ended_s - deadline).total_seconds() if ended_s and deadline else None
    gaps = [
        (parse_time(b) - parse_time(a)).total_seconds() for a, b in zip(read_ats, read_ats[1:], strict=False)
    ]
    balance_diff = abs(usage.get("balance") - cli_usage[0]) if cli_usage and usage.get("balance") is not None else None
    rate_diff = abs(usage.get("ratePerHour") - cli_usage[1]) if cli_usage and usage.get("ratePerHour") is not None else None
    checks = {
        "則1": balance_diff is not None and balance_diff <= 0.05,
        "則2": rate_diff is not None and rate_diff <= 0.05,
        "則3": (session or {}).get("endReason") == "IDLE_TIMEOUT" and late is not None and late <= 60,
        "則4": gone_s is not None and gone_s <= GONE_DEADLINE,
        "則5": len(read_ats) >= 2 and all(g <= 300 for g in gaps),
    }
    numbers = (
        f"開啟 {open_s:.1f} 秒;用量頁 餘額 {usage.get('balance')}、每小時 {usage.get('ratePerHour')};"
        f"colab usage {cli_usage};差 {balance_diff}、{rate_diff};"
        f"deadline 後 {late} 秒結束(endReason {(session or {}).get('endReason')});自動結束後 {gone_s} 秒 Colab 上沒有這台;"
        f"readAt 更新 {len(read_ats)} 次,間隔 {[round(g) for g in gaps]} 秒"
    )
    verdict(
        "US4-AJ-09", "T288", checks, numbers,
        "則1、則2 差 ≤ 0.05;則3 deadline 後 1 分鐘內 IDLE_TIMEOUT;則4 1 分鐘內沒有這個名稱;則5 readAt 至少更新 1 次且間隔 ≤ 5 分鐘",
        extra,
    )  # fmt: skip
