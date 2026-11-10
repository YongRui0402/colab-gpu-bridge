"""US1-AJ-19(tasks.md T151):`docker compose -p cgb-test restart cgb` 之後 2 分鐘內接回同一台(FR-005)。

前置:US1-AJ-18 之後工作階段就緒。只 restart `cgb-test` 這個 project(`realrun.compose()`)。
沿用同一台 T4,約 3 分鐘、約 0.06 compute units。
"""

import time

from realrun.helpers_container import get_stack, verdict


def test_us1_aj_19(realrun):
    stack = get_stack(realrun)
    stack.require("US1-AJ-19", "T151", "main_ready")
    name = stack.state["main"]
    rows_before = stack.test_rows("US1-AJ-19 重啟前")

    restarted = time.monotonic()
    result = stack.realrun.compose("restart", "cgb", timeout=180)
    realrun.record_raw("compose", f"$ docker compose restart cgb (exit {result.returncode})\n{result.stdout}{result.stderr}\n")
    after, _, samples = stack.poll_session(lambda s: s.get("state") == "ready" and s.get("name") == name and not s.get("resuming"), 150)
    to_ready = time.monotonic() - restarted
    rows_after = stack.test_rows("US1-AJ-19 重啟後")

    ok_ready = (after or {}).get("state") == "ready" and after.get("name") == name and not after.get("resuming")
    stack.state["main_ready"] = ok_ready
    checks = {
        "則1": ok_ready and to_ready <= 120,
        "則2": rows_before is not None and rows_after is not None and len(rows_before) == len(rows_after) == 1
        and rows_before[0]["name"] == rows_after[0]["name"] == name,
    }
    numbers = (
        f"restart exit {result.returncode};重啟到就緒(同名){to_ready:.1f} 秒;"
        f"cgb-test- 執行環境 重啟前 {len(rows_before) if rows_before is not None else '讀不到'} 台、"
        f"重啟後 {len(rows_after) if rows_after is not None else '讀不到'} 台"
    )
    verdict("US1-AJ-19", "T151", checks, numbers, "則1 2 分鐘內就緒且名稱相同;則2 重啟前後都 1 台、名稱相同", [f"狀態取樣 {samples}"])
