"""006 G-02(tasks.md T049):pi 照 `GET /api/connect` 的 `models.json` 與 `settings.json` 片段接上本系統(testplan.md § 5.2)。

環境同 G-01(`test_006_g_01.py` 的臨時 `ollama serve`、本系統與替身、`env -i` 的暫存 `HOME`);
另以 `npm install --prefix <暫存資料夾> @mariozechner/pi-coding-agent` 安裝 pi(npm 也在 `env -i` 的暫存 `HOME` 執行,
快取落在暫存資料夾,不全域安裝、不讀寫使用者的 `~/.npm` 與 `~/.pi`)。
環境變數 `CGB_006_PI_PREFIX` 指到一個已經 `npm install --prefix` 過的資料夾時改為整個複製過來(省下載時間),紀錄照實寫來源。

壓縮的判定:pi 的 JSON 事件有沒有 `compaction_start`(`reason` 為 `threshold`),以及臨時 serve 收到的
`/v1/chat/completions` 裡有沒有 pi 的壓縮系統提示(`SUMMARIZATION_SYSTEM_PROMPT` 開頭那句)。
護欄同 G-01;判定者:腳本;樣本:同 G-01。
執行:`uv run pytest -m realrun_local tests/realrun/test_006_g_02.py -q -p no:cacheprovider`
"""

import json
import os
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from cgb.app import AppPair
from realrun.test_006_g_01 import (  # noqa: F401 - serve、_p2_budget_gate 是 pytest fixture
    MODEL,
    PROMPT,
    RUN_SECONDS,
    SECRET,
    Report,
    TempServe,
    _p2_budget_gate,
    client_env,
    fill_host,
    json_lines,
    make_project,
    make_report,
    run_client,
    serve,
    serve_ps,
    start_bridge,
    verdict,
)

pytestmark = pytest.mark.realrun_local

CASE, TASK = "G-02", "T049"
PACKAGE = "@mariozechner/pi-coding-agent"
PREFIX_ENV = "CGB_006_PI_PREFIX"
INSTALL_SECONDS = 600
# pi 壓縮時送出的系統提示開頭(pi-coding-agent dist/core/compaction/utils.js 的 SUMMARIZATION_SYSTEM_PROMPT)
COMPACTION_MARK = "You are a context summarization assistant"


@pytest.fixture
def report() -> Iterator[Report]:
    yield from make_report(f"{CASE}({TASK})pi 照片段接上本系統(本機臨時 `ollama serve`)")


def install_pi(root: Path, home: Path, report: Report) -> Path:
    """回 pi 執行檔的路徑。"""
    prefix = root / "pi"
    seed = os.environ.get(PREFIX_ENV)
    if seed:
        shutil.copytree(seed, prefix, symlinks=True)
        how = f"複製已安裝的 `{PREFIX_ENV}`"
    else:
        npm = shutil.which("npm")
        if npm is None:
            report.unavailable = "PATH 上沒有 `npm`"
            pytest.skip("無法實跑:PATH 上沒有 npm")
        run = run_client(
            [npm, "install", "--prefix", str(prefix), "--no-audit", "--no-fund", "--cache", str(root / "npm-cache"), PACKAGE],
            root, client_env(home), INSTALL_SECONDS,
        )  # fmt: skip
        report.cleanup.append(f"npm install(結束碼 {run.code}){run.cleanup}")
        if run.code != 0:
            pytest.fail(f"npm install 失敗(exit {run.code}):{run.stderr[-500:]}")
        how = f"`npm install --prefix <暫存資料夾> {PACKAGE}` {run.seconds:.0f} 秒"
    package = json.loads((prefix / "node_modules" / PACKAGE / "package.json").read_text(encoding="utf-8"))
    report.environment.append(f"pi({PACKAGE}){package.get('version')},{how}")
    return prefix / "node_modules" / ".bin" / "pi"


def compaction_requests(chats: list[dict[str, Any]]) -> int:
    return sum(COMPACTION_MARK in json.dumps(c.get("messages"), ensure_ascii=False) for c in chats)


async def test_006_g_02(
    serve: TempServe,
    report: Report,
    make_app: Callable[..., AppPair],
    start_live_servers: Callable[..., Any],
    fakes: Any,
    tmp_path: Path,
) -> None:
    # Arrange:安裝 pi;本系統開到就緒,從 /api/connect 取 pi 的兩段片段原樣寫進暫存 HOME 的 ~/.pi/agent/
    home = tmp_path / "client-home"
    env = client_env(home, {"PI_OFFLINE": "1"})
    pi = install_pi(tmp_path, home, report)
    bridge = await start_bridge(serve, fakes, make_app, start_live_servers)
    report.environment.append("pi 以 `env -i` 只留 `PATH`,`HOME` 與四個 `XDG_*` 指到暫存資料夾,另加 `PI_OFFLINE=1`")
    report.environment.append(f"本系統:測試行程內的 uvicorn,相容端點 127.0.0.1:{bridge.ollama_port},Colab 與通道用替身,不開 Colab、不花錢")
    snippets = bridge.connect["snippets"]
    agent_dir = home / ".pi" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "models.json").write_text(fill_host(snippets["piModels"]), encoding="utf-8")
    assert snippets["piSettings"] is not None, "context 讀得到時應該有 settings.json 片段"
    (agent_dir / "settings.json").write_text(snippets["piSettings"], encoding="utf-8")
    project = make_project(tmp_path)

    # Act
    run = run_client(
        [str(pi), "-p", "--no-session", "--mode", "json", "--model", f"cgb/{MODEL}", PROMPT], project, env, RUN_SECONDS
    )
    report.cleanup.append(f"pi(結束碼 {run.code}){run.cleanup}")
    ps = serve_ps(serve)

    # Assert(先算好全部數字再寫紀錄,斷言放最後)
    events = json_lines(run.stdout)
    tools = [e.get("toolName") for e in events if e.get("type") == "tool_execution_start"]
    finals = [
        e["message"] for e in events
        if e.get("type") == "message_end" and isinstance(e.get("message"), dict) and e["message"].get("role") == "assistant"
    ]  # fmt: skip
    text = "".join(p.get("text", "") for m in finals for p in m.get("content", []) if p.get("type") == "text")
    usage = [(m.get("usage") or {}).get("input") for m in finals]
    compaction_events = [e for e in events if "compaction" in str(e.get("type"))]
    chats = bridge.relay.chats()
    compacted = compaction_requests(chats)
    then1 = run.code == 0 and not run.timed_out and SECRET in text
    then2 = "read" in tools
    then3 = not compaction_events and compacted == 0
    settings = json.loads(snippets["piSettings"])
    report.numbers += [
        f"`/api/connect`:contextLength {bridge.connect.get('contextLength')}、reserveTokens {bridge.connect.get('reserveTokens')}、"
        f"settings.json `{json.dumps(settings, ensure_ascii=False)}`",
        f"pi 結束碼 {run.code}{'(逾時)' if run.timed_out else ''};總耗時 {run.seconds:.1f} 秒(上限 {RUN_SECONDS} 秒)",
        f"回答文字(assistant 的 `message_end`)含 `{SECRET}`:{'是' if SECRET in text else '否'};前 80 字 `{text[:80]!r}`",
        f"工具呼叫 {len(tools)} 次:{tools};每則 assistant 訊息的 input tokens {usage}",
        f"壓縮:JSON 事件 {[e.get('type') + '/' + str(e.get('reason')) for e in compaction_events]};"
        f"臨時 serve 收到的 `POST /v1/chat/completions` {len(chats)} 個,其中壓縮的請求 {compacted} 個",
        f"臨時 serve 的 `/api/ps`:{ps}",
    ]
    report.verdicts += [
        f"則1 結束碼 0、輸出含 `{SECRET}`,門檻同左:{verdict(then1)}",
        f"則2 JSON 事件裡有 `read` 工具呼叫,門檻同左:{verdict(then2)}",
        f"則3 這一回合沒有因為 `threshold` 觸發自動壓縮(沒有壓縮事件、臨時 serve 沒收到壓縮的請求),門檻同左:{verdict(then3)}",
        f"則4 總耗時 {run.seconds:.1f} 秒(只記錄,沒有門檻)",
    ]
    if not (then1 and then2 and then3):
        report.numbers.append(f"pi stderr 最後 3 行:{run.stderr.strip().splitlines()[-3:]!r}")
    assert then1, f"exit {run.code},text {text[:200]!r},stderr {run.stderr[-500:]!r}"
    assert then2, f"tools {tools}"
    assert then3, f"compaction events {compaction_events},compaction requests {compacted}"
