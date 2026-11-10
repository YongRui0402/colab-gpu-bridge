"""US3-LIB-05(tasks.md T228):真的 ollama.com 與 registry.ollama.ai,和 `tests/fixtures/library/` 的存檔用同一組解析規則得到相同的欄位。

主機階段的第一個案例(P9),不開執行環境,0 compute units,約 1 分鐘。
護欄:P5(只在桌機、只連公開網站)、P8(錄下的只有狀態碼與長度);只送 GET、總共不超過 10 個請求、請求間隔 1 秒,
由 `RecordingTransport` 強制。判定者:腳本;樣本:2026 年 11 月的 ollama.com 一次(未用於調整)。
"""

import json
import re
from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.adapters.model_library import ModelLibrary
from cgb.domain.library_html import has_next_page, parse_model_tags, parse_search_models
from realrun.conftest import REPO_ROOT, write_measurement
from realrun.helpers import RecordingTransport, field_names, run

CASE, TASK = "US3-LIB-05", "T228"
LIBRARY_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "library"
SIZE_LABEL = re.compile(r"^(\d+(?:\.\d+)?)([KMGT])B$")
UNIT = {"K": 1e-6, "M": 1e-3, "G": 1.0, "T": 1e3}


def label_gb(label: str | None) -> float | None:
    """大小顯示值(例如 `4.7GB`)換成 GB;讀不懂就是 None。"""
    m = SIZE_LABEL.match(label or "")
    return float(m.group(1)) * UNIT[m.group(2)] if m else None


def fixture_text(name: str) -> str:
    return (LIBRARY_FIXTURES / name).read_text(encoding="utf-8")


def manifest_shape(manifest: Any) -> dict[str, list[str]]:
    """manifest 的欄位名稱:最上層、config、每一層(layers)的鍵。"""
    if not isinstance(manifest, dict):
        return {"top": []}
    layers = manifest.get("layers") if isinstance(manifest.get("layers"), list) else []
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    return {"top": sorted(manifest), "config": sorted(config), "layers": field_names(layers)}


async def measure() -> dict[str, Any]:
    transport = RecordingTransport(get_only=True, max_requests=10, min_interval=1.0)
    library = ModelLibrary(transport=transport)
    got: dict[str, Any] = {}
    try:
        got["page1"] = await library.search_library(q="qwen2.5", page=1)
        got["page1_html"] = bytes(transport.exchanges[-1].body).decode(errors="replace")
        got["page2"] = await library.search_library(q="qwen2.5", page=2)
        got["page2_html"] = bytes(transport.exchanges[-1].body).decode(errors="replace")
        got["tags"] = await library.list_model_tags("qwen2.5")
        got["tags_html"] = bytes(transport.exchanges[-1].body).decode(errors="replace")
        got["manifest_7b"] = await library.get_manifest("qwen2.5", "7b")
        got["manifest_7b_raw"] = transport.exchanges[-1].json()
        try:
            await library.get_manifest("qwen2.5", "cgb-test-nonexistent")
            got["nonexistent"] = "沒有丟錯誤"
        except AdapterError as error:
            got["nonexistent"] = error.code
        cloud = next((t for t in got["tags"] if t["cloudOnly"]), None)
        got["cloud_tag"] = cloud["tag"] if cloud else None
        if cloud is not None:
            try:
                await library.get_manifest("qwen2.5", cloud["tag"])
                got["cloud"] = "沒有丟錯誤"
            except AdapterError as error:
                got["cloud"] = error.code
    finally:
        got["requests"] = [f"{e.method} {e.path} → {e.status}({len(e.body)} 位元組)" for e in transport.exchanges]
        await transport.close_inner()
    return got


def test_us3_lib_05(realrun):
    # Act
    got = run(measure())
    realrun.record_raw("us3_lib_05", "\n".join(got["requests"]) + "\n")

    # 則1:第 1 頁含 qwen2.5,還有下一頁
    names1 = [item["name"] for item in got["page1"]["items"]]
    c1 = "qwen2.5" in names1 and got["page1"]["hasMore"] is True

    # 則2:版本頁含 0.5b 與 7b,7b 的大小顯示值在 4.6GB~4.8GB
    tags = {t["tag"]: t for t in got["tags"]}
    label_7b = tags.get("7b", {}).get("sizeLabel")
    gb_7b = label_gb(label_7b)
    c2 = "0.5b" in tags and "7b" in tags and gb_7b is not None and 4.6 <= gb_7b <= 4.8

    # 則3:qwen2.5:7b 的 manifest 大小在 4.6e9~4.8e9 位元組
    size_7b = got["manifest_7b"]["sizeBytes"]
    c3 = 4_600_000_000 <= size_7b <= 4_800_000_000

    # 則4:不存在的版本
    c4 = got["nonexistent"] == "LIBRARY_NOT_FOUND"

    # 則5:雲端版本(若有)
    c5 = True if got["cloud_tag"] is None else got.get("cloud") == "LIBRARY_CLOUD_ONLY"

    # 則6:存檔與這次抓到的頁面,用同一組解析規則得到相同的欄位
    fixture_page1 = fixture_text("search-qwen2.5-page1.html")
    fixture_page2 = fixture_text("search-qwen2.5-page2.html")
    fixture_tags = parse_model_tags(fixture_text("tags-qwen2.5.html"), "qwen2.5")
    live_tags = parse_model_tags(got["tags_html"], "qwen2.5")
    fixture_manifest = json.loads(fixture_text("manifest-qwen2.5-7b.json"))
    comparisons = {
        "搜尋頁第 1 頁:有名稱、有下一頁": (
            (bool(parse_search_models(fixture_page1)), has_next_page(fixture_page1)),
            (bool(parse_search_models(got["page1_html"])), has_next_page(got["page1_html"])),
        ),
        "搜尋頁第 2 頁:有名稱": (bool(parse_search_models(fixture_page2)), bool(parse_search_models(got["page2_html"]))),
        "版本頁每個版本的欄位": (field_names(fixture_tags), field_names(live_tags)),
        "版本頁有大小顯示值的版本占比 > 0": (
            any(t["sizeLabel"] for t in fixture_tags),
            any(t["sizeLabel"] for t in live_tags),
        ),
        "manifest 的欄位": (manifest_shape(fixture_manifest), manifest_shape(got["manifest_7b_raw"])),
    }
    diffs = [f"{k}:存檔 {a!r},這次 {b!r}" for k, (a, b) in comparisons.items() if a != b]
    c6 = not diffs

    checks = {"則1": c1, "則2": c2, "則3": c3, "則4": c4, "則5": c5, "則6": c6}
    numbers = (
        f"第 1 頁 {len(names1)} 個名稱、hasMore={got['page1']['hasMore']};第 2 頁 {len(got['page2']['items'])} 個;"
        f"版本 {len(tags)} 個,7b 顯示 {label_7b};7b manifest {size_7b:,} 位元組;不存在 → {got['nonexistent']};"
        f"雲端版本 {got['cloud_tag'] or '沒有'}{(' → ' + got['cloud']) if got['cloud_tag'] else ''};請求 {len(got['requests'])} 個"
    )
    failed = [k for k, ok in checks.items() if not ok]
    note = "沒過:" + "、".join(failed) if failed else ""
    if got["cloud_tag"] is None:
        note += (";" if note else "") + "版本頁沒有名稱含 cloud 的版本,則5 不適用"
    if diffs:
        note += ";" + ";".join(diffs)
    write_measurement(
        CASE, TASK, numbers,
        "則1~則6(4.6~4.8GB、4.6e9~4.8e9 位元組、LIBRARY_NOT_FOUND、LIBRARY_CLOUD_ONLY、欄位相同)",
        not failed, note,
    )  # fmt: skip

    # Assert
    assert not failed, note
