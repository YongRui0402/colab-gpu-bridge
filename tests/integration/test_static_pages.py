"""前端靜態檔:結束類狀態可以再開新的工作階段(docs/觀察紀錄.md 2026-11-14)。

接縫:`src/cgb/static/` 底下的 HTML 本身(以標準函式庫的 `html.parser` 解析);
不需要瀏覽器,快速層就跑得到。按下按鈕真的送出開啟的行為由 `tests/e2e/test_reopen_after_end.py` 驗。
"""

from html.parser import HTMLParser
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "cgb" / "static"

# 結束類狀態:工作階段已經不占位子,後端允許直接開新的(session_lifecycle.open() 只擋 ending 與未登入)
ENDED_STATES = ("ended", "ended-idle", "failed", "lost", "lost-timeout", "lost-zero")


class Elements(HTMLParser):
    """記下每個元素的標籤、屬性與它所在的 `data-state` 區塊。"""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[tuple[str, dict[str, str | None], str | None]] = []
        self._stack: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        state = attributes.get("data-state") or (self._stack[-1][1] if self._stack else None)
        self.items.append((tag, attributes, state))
        if tag not in {"meta", "link", "input", "br", "img"}:
            self._stack.append((tag, state))

    def handle_endtag(self, tag: str) -> None:
        while self._stack:
            if self._stack.pop()[0] == tag:
                break


def parse(page: str) -> Elements:
    parser = Elements()
    parser.feed((STATIC / page).read_text(encoding="utf-8"))
    return parser


def in_state(state: str) -> list[tuple[str, dict[str, str | None]]]:
    return [(tag, attrs) for tag, attrs, where in parse("index.html").items if where == state]


@pytest.mark.parametrize("state", ENDED_STATES)
def test_結束類狀態區塊有類型選單與開啟按鈕(state: str) -> None:
    elements = in_state(state)
    assert elements, f"index.html 沒有 data-state={state} 的區塊"

    pickers = [attrs["data-picker"] for _, attrs in elements if "data-picker" in attrs]
    open_buttons = [attrs for tag, attrs in elements if tag == "button" and attrs.get("data-action") == "open"]

    assert pickers == [state], f"{state} 區塊的 data-picker 是 {pickers}"
    assert len(open_buttons) == 1, f"{state} 區塊有 {len(open_buttons)} 個 data-action=open 的按鈕"


def test_釋放不了的區塊沒有開啟按鈕() -> None:
    # FR-007:舊執行環境可能還在扣 compute units,要先處理釋放
    elements = in_state("release-failed")

    assert elements
    assert not [attrs for _, attrs in elements if "data-picker" in attrs]
    assert not [attrs for _, attrs in elements if attrs.get("data-action") == "open" or attrs.get("id") == "open"]
