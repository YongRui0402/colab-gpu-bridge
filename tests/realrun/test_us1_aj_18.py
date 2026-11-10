"""US1-AJ-18(tasks.md T150):容器裡的 ssh 被殺掉,1 分鐘內顯示重連中,5 分鐘內接回同一台(SC-002、NFR-002)。

前置:US1-AJ-17 的工作階段就緒,US2-AJ-02 已預先載入 `qwen2.5:0.5b`。
以 `docker exec` 在容器裡對命令列含 `ProxyCommand=colab ssh --proxy-mode -s cgb-test-` 的 ssh 行程送 SIGKILL
(只認 argv[0] 是 ssh 的行程,不用 `pkill ssh`)。沿用同一台 T4,約 3 分鐘、約 0.06 compute units。
"""

import json

from realrun.conftest import RESIDUAL_SSH_MARK
from realrun.helpers_container import SMALL, get_stack, now_utc, parse_time, verdict

KILL_SSH = r"""
import json, os, signal, sys
mark = sys.argv[1]
killed = []
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        argv = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
    except OSError:
        continue
    if argv and os.path.basename(argv[0].decode(errors="replace")) == "ssh" and mark in b" ".join(argv).decode(errors="replace"):
        os.kill(int(pid), signal.SIGKILL)
        killed.append(int(pid))
print(json.dumps(killed))
"""


def test_us1_aj_18(realrun):
    stack = get_stack(realrun)
    stack.require("US1-AJ-18", "T150", "main_ready", "small_loaded")
    before = stack.session() or {}
    name = before.get("name")
    extra: list[str] = []
    if before.get("state") != "ready" or name != stack.state["main"]:
        extra.append(f"殺掉之前的狀態 {before.get('state')}、名稱與 US1-AJ-17 {'相同' if name == stack.state['main'] else '不同'}")

    killed_at = now_utc()
    result = stack.docker_exec("python", "-c", KILL_SSH, RESIDUAL_SSH_MARK)
    try:
        killed = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        killed = []
    if len(killed) != 1:
        extra.append(f"殺掉的 ssh 行程數是 {len(killed)}")

    reconnecting, to_reconnecting, samples1 = stack.poll_session(lambda s: s.get("state") != "ready", 90)
    ready, to_ready, samples2 = stack.poll_session(lambda s: s.get("state") == "ready", 330)
    seen_reconnecting = (reconnecting or {}).get("state") == "reconnecting"
    if not seen_reconnecting:
        # 每 5 秒的取樣可能剛好跳過很短的重連中;改看這筆紀錄的狀態變化(FR-028)
        detail = stack.ui("GET", f"/api/sessions/{name}").json() if name else {}
        times = [parse_time(t["at"]) for t in detail.get("transitions", []) if t.get("state") == "reconnecting"]
        times = [t for t in times if t and t >= killed_at]
        if times:
            seen_reconnecting = True
            to_reconnecting = (times[0] - killed_at).total_seconds()
            extra.append("重連中由紀錄的狀態變化得知(取樣沒碰到)")
    ps = stack.ollama("GET", "/api/ps", timeout=30)[0] if (ready or {}).get("state") == "ready" else None
    loaded = [m.get("name") for m in ps.json().get("models", [])] if ps is not None and ps.status_code == 200 else []
    rows = stack.test_rows("US1-AJ-18 之後")

    stack.state["main_ready"] = (ready or {}).get("state") == "ready" and ready.get("name") == name
    checks = {
        "則1": seen_reconnecting and to_reconnecting <= 60,
        "則2": stack.state["main_ready"] and to_ready <= 300,
        "則3": SMALL in loaded,
        "則4": rows is not None and len(rows) == 1,
    }
    numbers = (
        f"殺掉 {len(killed)} 個 ssh;到重連中 {to_reconnecting:.1f} 秒;之後到就緒 {to_ready:.1f} 秒;"
        f"/api/ps {loaded};cgb-test- 執行環境 {len(rows) if rows is not None else '讀不到'} 台"
    )
    extra.append(f"狀態取樣 {samples1 + samples2}")
    verdict(
        "US1-AJ-18", "T150", checks, numbers,
        "則1 1 分鐘內重連中;則2 之後 5 分鐘內就緒且名稱相同;則3 /api/ps 有 qwen2.5:0.5b;則4 cgb-test- 仍 1 台",
        extra,
    )  # fmt: skip
