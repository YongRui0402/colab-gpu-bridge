"""G-03(tasks.md T235):對話頁第一段的延遲與內容不落地(004 testplan.md § 7.2)。

`e2e_servers` 起真的後端(UI 127.0.0.1:8781);`FakeOllamaServer` 對 `/api/chat` 每 0.1 秒吐一段、共 20 段再吐 `DONE`,
並以同一台機器的牆上時鐘記下吐出第一段的時間;瀏覽器裡以 MutationObserver 記下畫面第一次出現第一段文字的時間
(`performance.timeOrigin + performance.now()`),以 `page.wait_for_function` 等它記到。做 5 次,每次按「清空」。

標 `realrun`,預設排除。護欄:UI 只綁 127.0.0.1:8781(e2e 的固定 port,同一時間只跑一份);資料庫是 pytest 暫存資料夾的
SQLite;Colab、通道、遠端 Ollama 都用替身,不執行任何 `colab` 指令;約 15 秒。
判定者:腳本(和 0.5 秒比較);樣本:一次量測 5 次(未用於調整)。
執行:`uv run pytest -m realrun tests/e2e/test_004_g_03.py`
"""

import logging
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from e2e.test_004_us2_chat import DONE, QWEN, chunk, open_chat, replies, send
from e2e.test_us1_session import ColabWorld, world  # noqa: F401 - `world` 是 fixture
from fakes import Gate, NdjsonReply
from integration.test_004_g_01 import ensure_measurements
from realrun.conftest import write_measurement

pytestmark = pytest.mark.realrun

CASE, TASK = "G-03", "T235"
ROUNDS = 5
SEGMENTS = 20
INTERVAL = 0.1
LIMIT = 0.5
SENT = "cgb-test-G03-送出內容-不該留下"
THRESHOLD = "則1:5 次的「畫面出現第一段 − 替身吐出第一段」都 ≤ 0.5 秒;則2:5 次的回覆下方都顯示耗時與每秒 token 數;則3:測試前後 SQLite 檔與後端日誌中送出內容 0 次"


class Stamp(Gate):
    """放在第一段之前:記下替身要吐出第一段的牆上時間,不等待。"""

    def __init__(self, sink: list[float]) -> None:
        super().__init__()
        self.sink = sink

    def pass_sync(self, stop: threading.Event | None = None) -> bool:
        self.sink.append(time.time())
        return True


class Pause(Gate):
    """兩段之間停 0.1 秒。"""

    def pass_sync(self, stop: threading.Event | None = None) -> bool:
        time.sleep(INTERVAL)
        return True


WATCH = """first => {
  window.__firstSeen = null;
  const log = document.getElementById("log");
  const seen = () => [...log.querySelectorAll(".msg-bot")].some((el) => el.textContent.includes(first));
  const observer = new MutationObserver(() => {
    if (window.__firstSeen === null && seen()) {
      window.__firstSeen = performance.timeOrigin + performance.now();
      observer.disconnect();
    }
  });
  observer.observe(log, { childList: true, subtree: true, characterData: true });
}"""


def count_in_db(db_path: Path, text: str) -> int:
    count = 0
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
                count += repr(conn.execute(f'SELECT * FROM "{table}"').fetchall()).count(text)
    for suffix in ("", "-wal", "-journal"):
        path = Path(str(db_path) + suffix)
        if path.exists():
            count += path.read_bytes().count(text.encode())
    return count


def test_g_03(page: Page, e2e_servers: Any, world: ColabWorld, fakes: Any, db_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    # Arrange
    caplog.set_level(logging.DEBUG)
    open_chat(page, world, QWEN)
    page.select_option("#model", QWEN)
    before = count_in_db(db_path, SENT) + caplog.text.count(SENT)
    emitted: list[float] = []
    delays: list[float] = []
    feet: list[bool] = []

    # Act
    for round_no in range(ROUNDS):
        first = f"第{round_no}輪第一段"
        lines: list[Any] = [Stamp(emitted), chunk(first)]
        for n in range(1, SEGMENTS):
            lines += [Pause(), chunk(f"段{n}")]
        fakes.server.add("POST", "/api/chat", NdjsonReply([*lines, DONE]), times=1)
        page.evaluate(WATCH, first)
        send(page, f"{SENT}-{round_no}")
        page.wait_for_function("window.__firstSeen !== null", timeout=10_000)
        seen_at = page.evaluate("window.__firstSeen") / 1000
        delays.append(seen_at - emitted[-1])
        expect(page.locator('[data-state="turn-streaming"]')).to_be_hidden(timeout=10_000)
        foot = replies(page).last.locator(".msg-foot")
        expect(foot).to_contain_text(re.compile(r"耗時 \S+ 秒"), timeout=10_000)
        feet.append(bool(re.search(r"tokens/s", foot.inner_text())))
        page.click("#clear")
        expect(page.locator("#log .msg")).to_have_count(0)
    time.sleep(0.2)
    after = count_in_db(db_path, SENT) + caplog.text.count(SENT)

    # 量到的數字
    checks = {"則1": len(delays) == ROUNDS and all(d <= LIMIT for d in delays), "則2": len(feet) == ROUNDS and all(feet), "則3": before == 0 and after == 0}
    numbers = [
        "5 次的延遲(秒)" + "、".join(f"{d:.3f}" for d in delays) + f",最大 {max(delays):.3f}",
        f"回覆下方有耗時與 tokens/s 的 {sum(feet)} / {ROUNDS} 次",
        f"送出內容出現次數:測試前 {before}、測試後 {after}(SQLite 檔含 -wal、-journal,加上後端日誌)",
    ]
    failed = [name for name, ok in checks.items() if not ok]
    note = ("沒過:" + "、".join(failed) + ";" if failed else "") + "替身每 0.1 秒一段、共 20 段;時間是同一台機器的牆上時鐘"
    write_measurement(CASE, TASK, ";".join(numbers), THRESHOLD, not failed, note, path=ensure_measurements())

    # Assert
    assert not failed, ";".join(numbers)
