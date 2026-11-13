"""G-02(tasks.md T088):002 的格式判定在真的 ollama.com 與 registry.ollama.ai 上不誤判(testplan.md § 4.2)。

只在桌機跑;依序呼叫 `search_library(q="qwen2.5")` 第 1 頁、`search_library(q="zzzz-no-such-model")` 第 1 頁、
`search_library(q="qwen2.5", page=2)`、`list_model_tags("qwen2.5")`、`get_manifest("qwen2.5", "7b")`。

標 `realrun`,預設排除;不放 `tests/realrun/`,不經會執行 `colab usage` 與複製授權檔的 `realrun` fixture(plan.md Q17)。
護欄:只送 GET,`RecordingTransport(get_only=True, max_requests=10, min_interval=1.0)` 強制總共不超過 10 個請求
(這次 5 個)、間隔 1 秒;不重試、不帶 token;不碰 Tower、Pi 與共用服務,不開 Colab、0 compute units。
錄下的只有狀態碼與長度,只寫 pytest 暫存資料夾;連不到就標無法實跑,不改用存下來的頁面。
判定者:腳本;樣本:執行當下的 ollama.com 與 registry 一次(未用於調整)。
執行:`uv run pytest -m realrun tests/integration/test_002_g_02.py`
"""

from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import pytest

from cgb.adapters.errors import AdapterError
from cgb.adapters.model_library import ModelLibrary
from integration.test_002_g_01 import ensure_measurements
from realrun.conftest import write_measurement
from realrun.helpers import RecordingTransport

pytestmark = pytest.mark.realrun

CASE, TASK = "G-02", "T088"
SIZE_7B_RANGE = (4_600_000_000, 4_800_000_000)
THRESHOLD = (
    "則1:第 1 頁至少 1 筆且含 qwen2.5;則2:0 筆搜尋回 0 筆、不丟 AdapterError;"
    "則3:第 2 頁不丟 LIBRARY_BAD_RESPONSE;則4:非 cloud 版本 sizeLabel 為 null 0 個;"
    "則5:qwen2.5:7b sizeBytes 4,600,000,000~4,800,000,000"
)


async def outcome(call: Awaitable[Any]) -> tuple[Any, str | None]:
    """(回傳值, None) 或 (None, AdapterError 的代碼)。"""
    try:
        return await call, None
    except AdapterError as error:
        return None, error.code


async def measure() -> dict[str, Any]:
    transport = RecordingTransport(get_only=True, max_requests=10, min_interval=1.0)
    library = ModelLibrary(transport=transport)
    got: dict[str, Any] = {}
    try:
        got["page1"] = await outcome(library.search_library(q="qwen2.5"))
        got["empty"] = await outcome(library.search_library(q="zzzz-no-such-model"))
        got["page2"] = await outcome(library.search_library(q="qwen2.5", page=2))
        got["tags"] = await outcome(library.list_model_tags("qwen2.5"))
        got["manifest"] = await outcome(library.get_manifest("qwen2.5", "7b"))
    finally:
        # 只留狀態碼與長度(路徑不含查詢字串,也沒有 token)
        got["requests"] = [f"{e.method} {e.path} → {e.status}({len(e.body)} 位元組)" for e in transport.exchanges]
        await transport.close_inner()
    return got


async def test_g_02(tmp_path: Path) -> None:
    # Act
    got = await measure()
    (tmp_path / "g_02_requests.txt").write_text("\n".join(got["requests"]) + "\n", encoding="utf-8")

    # 連不到(第 1 個請求就沒有回應):標無法實跑,不改用存下來的頁面
    if not got["requests"]:
        write_measurement(
            CASE, TASK, f"第 1 頁 → {got['page1'][1]};沒有任何往返", THRESHOLD, None,
            "無法實跑:連不到 ollama.com", path=ensure_measurements(),
        )  # fmt: skip
        pytest.skip(f"無法實跑:連不到 ollama.com({got['page1'][1]})")

    page1, page1_error = got["page1"]
    empty, empty_error = got["empty"]
    page2, page2_error = got["page2"]
    tags, tags_error = got["tags"]
    manifest, manifest_error = got["manifest"]

    # 則1:qwen2.5 第 1 頁至少 1 筆官方模型,含 qwen2.5
    names1 = [item["name"] for item in page1["items"]] if page1 else []
    c1 = page1_error is None and len(names1) >= 1 and "qwen2.5" in names1
    # 則2:0 筆的真搜尋頁回 0 筆,沒有丟 AdapterError
    empty_count = len(empty["items"]) if empty else None
    c2 = empty_error is None and empty_count == 0
    # 則3:第 2 頁沒有丟 LIBRARY_BAD_RESPONSE(其他錯誤也算沒過,另寫進備註)
    c3 = page2_error is None
    # 則4:名稱不含 cloud 的版本,sizeLabel 都不是 null
    local_tags = [t for t in tags if "cloud" not in t["tag"]] if tags else []
    missing_size = [t["tag"] for t in local_tags if t["sizeLabel"] is None]
    c4 = tags_error is None and bool(local_tags) and not missing_size
    # 則5:qwen2.5:7b 的 sizeBytes 和 001 一致
    size_7b = manifest["sizeBytes"] if manifest else None
    c5 = manifest_error is None and size_7b is not None and SIZE_7B_RANGE[0] <= size_7b <= SIZE_7B_RANGE[1]

    checks = {"則1": c1, "則2": c2, "則3": c3, "則4": c4, "則5": c5}
    numbers = (
        f"第 1 頁官方模型 {len(names1)} 筆(含 qwen2.5:{'是' if 'qwen2.5' in names1 else '否'}),丟出 {page1_error or '無'};"
        f"0 筆搜尋 {empty_count} 筆,丟出 {empty_error or '無'};"
        f"第 2 頁 {len(page2['items']) if page2 else '—'} 筆,丟出 {page2_error or '無'};"
        f"版本 {len(tags) if tags else 0} 個(非 cloud {len(local_tags)} 個),sizeLabel 為 null {len(missing_size)} 個,丟出 {tags_error or '無'};"
        f"qwen2.5:7b sizeBytes {f'{size_7b:,}' if size_7b is not None else '—'},丟出 {manifest_error or '無'};"
        f"請求 {len(got['requests'])} 個"
    )
    failed = [name for name, ok in checks.items() if not ok]
    note = "沒過:" + "、".join(failed) if failed else "只送 GET,間隔 1 秒,不重試、不帶 token"
    if missing_size:
        note += ";sizeLabel 為 null 的版本:" + "、".join(missing_size)
    write_measurement(CASE, TASK, numbers, THRESHOLD, not failed, note, path=ensure_measurements())

    # Assert
    # 逾時或連不到的請求沒有往返可錄,所以只檢查沒有超過這次的 5 個
    assert len(got["requests"]) <= 5, got["requests"]
    assert not failed, numbers
