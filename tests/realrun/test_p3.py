"""容器階段結束後的 P3 收尾(testplan.md § 實跑案例的共同護欄),排在 G-07、G-05 之前(P9)。

收尾之前先留下 G-07、G-05 要用的東西:`GET /api/sessions` 的筆數、`docker compose logs` 的原文(P3 會移除容器)。
之後停掉 SSE 紀錄、執行 `realrun.p3_cleanup()`:沒有 cgb-test- 執行環境、`docker compose -p cgb-test down`、沒有殘留的 ssh。
"""

from realrun.conftest import TEST_PREFIX
from realrun.helpers_container import get_stack


def test_p3_after_container_phase(realrun):
    stack = get_stack(realrun)
    stack.ensure_no_active()
    history = stack.ui("GET", "/api/sessions?limit=100").json()
    stack.state["history_count"] = len(history.get("items", []))
    stack.state["history_has_more"] = history.get("hasMore")
    stack.save_compose_logs("logs-before-p3.txt")
    stack.stop_recording()

    problems = realrun.p3_cleanup()
    rows = stack.colab_rows("P3 之後")
    if rows is None:
        problems.append("P3 之後 colab sessions 讀不到")
    elif any(r["name"].startswith(TEST_PREFIX) for r in rows):
        problems.append(f"P3 之後仍有 cgb-test- 執行環境:{[r['name'] for r in rows if r['name'].startswith(TEST_PREFIX)]}")
    assert not problems, ";".join(problems)
