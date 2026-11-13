"""G-01(tasks.md T087):模型庫在逾時內沒有回應時,經真的 HTTP 連線量 UI API 多久收到 504(testplan.md § 4.2)。

後端以測試行程內的 uvicorn 起在 127.0.0.1 隨機 port(`live_servers`,不經 `httpx.ASGITransport`),
注入真的 `ModelLibrary`、不帶 `request_timeout`(預設 10 秒,spec NFR-001);ollama.com 與 registry 的位址
以建構參數指到 127.0.0.1 上的本機 socket 伺服器:一個接受連線後永不回應,一個送出 200 標頭後每 0.4 秒送 1 byte。

標 `realrun`,預設排除;不放 `tests/realrun/`,不經會執行 `colab usage` 的 `realrun` fixture(plan.md Q16)。
護欄:只連 127.0.0.1,不連 ollama.com 與 registry;資料庫是 pytest 暫存資料夾的 SQLite;Colab、通道、
遠端 Ollama 用替身,不執行任何 `colab` 指令、不花 compute units;約 45 秒。
判定者:腳本(量到的秒數和 10~11 秒比較);樣本:一次量測,每個操作各一次(未用於調整)。
執行:`uv run pytest -m realrun tests/integration/test_002_g_01.py`
"""

import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from cgb.adapters.model_library import ModelLibrary
from integration.test_api_downloads import downloadable
from integration.test_api_session import error_code, open_ready
from integration.test_model_library import LocalSocketServer, never_reply, slow_body
from realrun.conftest import REPO_ROOT, write_measurement

pytestmark = pytest.mark.realrun

CASE, TASK = "G-01", "T087"
MEASUREMENTS = REPO_ROOT / "specs" / "002-library-error-handling" / "measurements.md"
QWEN_7B = "qwen2.5:7b"
LOWER_SECONDS, UPPER_SECONDS = 10.0, 11.0
EXPECTED = (504, "LIBRARY_TIMEOUT")
# 慢慢送資料:每 0.4 秒 1 byte,100 bytes 要送 40 秒,遠超過 10 秒的整體期限
SLOW_INTERVAL, SLOW_LENGTH = 0.4, 100


def ensure_measurements(path: Path = MEASUREMENTS) -> Path:
    """002 的 measurements.md 還沒有時先寫好標頭;`write_measurement` 自己建的標頭是 001 的標題。"""
    if not path.exists():
        path.write_text(
            "# 實跑量測結果:官方模型庫的錯誤處理\n\n"
            "由 `tests/realrun/conftest.py` 的 `write_measurement` 寫入(tasks.md T087、T088);"
            "護欄見 `testplan.md` § 4.2 各案例的「副作用與護欄」。\n\n"
            "| 時間 | 案例 | 任務 | 數字 | 門檻 | 結果 | 備註 |\n"
            "|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    return path


async def timed(send: Callable[[], Awaitable[httpx.Response]]) -> tuple[float, int, str | None]:
    """送出到收到回應的秒數、狀態碼與 `code`。"""
    started = time.monotonic()
    response = await send()
    return time.monotonic() - started, response.status_code, error_code(response)


def within(result: tuple[float, int, str | None]) -> bool:
    seconds, status, code = result
    return LOWER_SECONDS <= seconds <= UPPER_SECONDS and (status, code) == EXPECTED


async def test_g_01(
    make_app: Callable[..., Any], start_live_servers: Callable[..., Any], fakes: Any, tmp_path: Path
) -> None:
    # Arrange:工作階段可開到就緒(E2 的替身);兩個本機 socket 伺服器都綁 127.0.0.1 隨機 port
    downloadable(fakes)
    results: dict[str, tuple[float, int, str | None]] = {}
    with (
        LocalSocketServer(never_reply) as silent,
        LocalSocketServer(slow_body(interval=SLOW_INTERVAL, length=SLOW_LENGTH)) as slow,
    ):
        silent_library = ModelLibrary(ollama_base_url=silent.url(), registry_base_url=silent.url())
        silent_ui = start_live_servers(make_app(model_library=silent_library))
        # 第四次量測要把 ollama_base_url 指到慢慢送的伺服器:另起一個 app(另一個暫存 SQLite)
        slow_library = ModelLibrary(ollama_base_url=slow.url(), registry_base_url=silent.url())
        slow_ui = start_live_servers(make_app(db_path=tmp_path / "g01-slow.sqlite3", model_library=slow_library))

        # Act:依序搜尋、版本清單、只勾 qwen2.5:7b 的試算,再對慢慢送的伺服器搜尋一次
        async with httpx.AsyncClient(base_url=silent_ui.ui_url, timeout=30.0) as client:
            await open_ready(client)
            results["搜尋"] = await timed(lambda: client.get("/api/library/search", params={"q": "qwen2.5"}))
            results["版本清單"] = await timed(lambda: client.get("/api/library/models/qwen2.5/tags"))
            results["試算"] = await timed(lambda: client.post("/api/downloads/estimate", json={"models": [QWEN_7B]}))
        async with httpx.AsyncClient(base_url=slow_ui.ui_url, timeout=30.0) as client:
            results["慢慢送資料時的搜尋"] = await timed(
                lambda: client.get("/api/library/search", params={"q": "qwen2.5"})
            )

    # 則1~則4:每一次都在送出後 10 到 11 秒之間收到 504 LIBRARY_TIMEOUT
    checks = {f"則{i}": within(result) for i, result in enumerate(results.values(), start=1)}
    numbers = ";".join(f"{name} {seconds:.2f} 秒 {status} {code}" for name, (seconds, status, code) in results.items())
    failed = [name for name, ok in checks.items() if not ok]
    write_measurement(
        CASE, TASK, numbers,
        "則1~則4:送出後 10~11 秒之間收到 504、code 為 LIBRARY_TIMEOUT",
        not failed, "沒過:" + "、".join(failed) if failed else "只連 127.0.0.1;預設 10 秒逾時,沒帶 request_timeout",
        path=ensure_measurements(),
    )  # fmt: skip

    # Assert
    assert not failed, numbers
