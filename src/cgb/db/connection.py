"""SQLite 連線(research.md R10;contracts/store.dbml)。"""

import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    """開一條連線;自動 commit,讓每一次寫入立即落到檔案。

    UI 與 Ollama 相容端點在同一個事件迴圈裡共用這條連線;測試行程內的 uvicorn 跑在別的執行緒,所以不綁執行緒。
    """
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
