"""US1-AJ-20(tasks.md T152):變更類型為 T4 高 RAM,原本那台 1 分鐘內消失、新的就緒後重新載入原本的模型(FR-010、SC-003)。

前置:US1-AJ-19 之後工作階段就緒(T4),`/api/ps` 只有 `qwen2.5:0.5b`(US3-AJ-12 以 `keep_alive: 0` 推論 7b)。
「在首頁勾高 RAM、按變更類型並確認」走 UI API:`POST /api/session/restart {"runtimeType": {"gpu": "T4", "highMem": true}}`
(畫面上的確認只是 UI 的步驟,這個案例不判定畫面)。結束 T4、開 1 台 T4 高 RAM(Q102),約 5 分鐘、約 0.1 compute units。
`/api/ps` 意外有 `qwen2.5:7b` 時照實記錄,讓它一起重新下載,時間另計。
"""

import threading
import time

from realrun.helpers_container import OPEN_DEADLINE, SMALL, TERMINAL, get_stack, verdict

GONE_DEADLINE = 60
RELOAD_DEADLINE = 300


def loaded_models(stack) -> list[str]:
    response = stack.ollama("GET", "/api/ps", timeout=30)[0]
    return [m.get("name") for m in response.json().get("models", [])] if response.status_code == 200 else []


def test_us1_aj_20(realrun):
    stack = get_stack(realrun)
    stack.require("US1-AJ-20", "T152", "main_ready")
    old = stack.state["main"]
    extra: list[str] = []
    ps_before = loaded_models(stack)
    if ps_before != [SMALL]:
        extra.append(f"變更前 /api/ps 是 {ps_before}(預期只有 {SMALL})")

    started = time.monotonic()
    response = stack.ui("POST", "/api/session/restart", {"runtimeType": {"gpu": "T4", "highMem": True}})
    if response.status_code != 202:
        verdict("US1-AJ-20", "T152", {"受理": False}, f"HTTP {response.status_code}", "202", [response.text[:200]])
    new = response.json().get("name")
    stack.guard_name(new)
    stack.state["main"] = new
    stack.state["main_ready"] = False

    gone: dict[str, float | None] = {}
    watcher = threading.Thread(target=lambda: gone.update(s=stack.wait_gone(old, GONE_DEADLINE)), daemon=True)
    watcher.start()
    last, _, samples = stack.poll_session(lambda s: s.get("state") in ("ready", *TERMINAL), OPEN_DEADLINE, 5)
    watcher.join(timeout=GONE_DEADLINE + 30)
    ready = (last or {}).get("state") == "ready" and last.get("name") == new
    to_ready = time.monotonic() - started
    stack.state["main_ready"] = ready
    stack.state["highram_ready"] = ready

    rows = stack.colab_rows("US1-AJ-20 新的那台") or []
    mine = [r for r in rows if r["name"] == new]

    reload_s = None
    if ready:
        reload_started = time.monotonic()
        while time.monotonic() - reload_started <= RELOAD_DEADLINE:
            if SMALL in loaded_models(stack):
                reload_s = time.monotonic() - reload_started
                break
            time.sleep(10)
    history = stack.ui("GET", "/api/sessions?limit=20").json().get("items", [])
    old_record = next((item for item in history if item.get("name") == old), {})

    checks = {
        "則1": gone.get("s") is not None and gone["s"] <= GONE_DEADLINE,
        "則2": len(mine) == 1 and mine[0]["shape"] == "High-RAM" and mine[0]["hardware"] == "T4",
        "則3": reload_s is not None,
        "則4": old_record.get("endReason") == "RUNTIME_TYPE_CHANGED",
    }
    if not ready:
        extra.append(f"新的工作階段沒有就緒:{(last or {}).get('state')}、reasonCode {(last or {}).get('reasonCode')}")
    extra.append(f"狀態取樣 {samples}")
    numbers = (
        f"原本那台消失 {gone.get('s')} 秒;受理到新的就緒 {to_ready:.1f} 秒;新的那台 {mine[0] if mine else '沒有列出'};"
        f"就緒後 /api/ps 有 {SMALL}:{f'{reload_s:.1f} 秒' if reload_s is not None else '5 分鐘內沒有'};"
        f"舊紀錄 endReason {old_record.get('endReason')}"
    )
    verdict(
        "US1-AJ-20", "T152", checks, numbers,
        "則1 原本的 1 分鐘內消失;則2 新的是 T4 High-RAM;則3 就緒後 5 分鐘內 /api/ps 有 qwen2.5:0.5b;則4 舊的 RUNTIME_TYPE_CHANGED",
        extra,
    )  # fmt: skip
