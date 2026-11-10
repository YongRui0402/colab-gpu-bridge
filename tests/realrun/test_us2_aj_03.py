"""US2-AJ-03(tasks.md T183):沒有工作階段時,Ollama 相容端點 1 秒內回 503 與「沒有可用的工作階段」(SC-007)。

容器階段的第一個案例:真的 uvicorn(容器裡的 `python -m cgb`,不經 ASGI transport),沒有工作階段。
不開執行環境,0 compute units,約 1 分鐘;護欄 P5、P6(只連 127.0.0.1:11436)。判定者:腳本(1 秒門檻);樣本:10 次請求。
"""

from realrun.helpers_container import SMALL, generate_body, get_stack, verdict

NO_SESSION_TEXT = "沒有可用的工作階段"


def test_us2_aj_03(realrun):
    stack = get_stack(realrun)
    current = stack.session() or {}
    assert current.get("state") not in ("opening", "ready", "reconnecting"), f"容器階段一開始就有工作階段:{current.get('state')}"

    results = [stack.ollama("POST", "/api/generate", generate_body(SMALL, 8), timeout=30) for _ in range(10)]
    statuses = [r.status_code for r, _ in results]
    latencies = [s for _, s in results]
    texts_ok = [NO_SESSION_TEXT in r.text for r, _ in results]

    checks = {"則1": all(s == 503 for s in statuses), "則2": max(latencies) <= 1.0, "則3": all(texts_ok)}
    numbers = f"狀態碼 {sorted(set(statuses))};延遲最長 {max(latencies):.3f} 秒、平均 {sum(latencies) / 10:.3f} 秒"
    verdict("US2-AJ-03", "T183", checks, numbers, "則1 10 次都 503;則2 最長 ≤ 1 秒;則3 error 含「沒有可用的工作階段」", [])
