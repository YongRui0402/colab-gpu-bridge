"""Hugging Face 量化版本的列表規則(research.md R3 第 1~5 步;plan.md Q49)。"""

import re

# 分割檔結尾的編號(research.md R3 第 3 步):`-00001-of-00002`,不論第幾片
_SPLIT_SUFFIX = re.compile(r"-\d{5}-of-\d{5}$")


def quant_name(path: str) -> str | None:
    """檔案路徑 → 量化名稱(照檔名原樣的大小寫);只看路徑最後一段,不是 GGUF 或是 mmproj 回 None;去掉分割編號後以 `-` 或 `.` 切開取最後一段。"""
    filename = path.rsplit("/", 1)[-1]
    # 副檔名不分大小寫;多模態投影檔(檔名含 mmproj,不分大小寫)不是能單獨拉的模型;只看檔名,資料夾名稱不算(research.md R3 第 2 步)
    if not filename.lower().endswith(".gguf") or "mmproj" in filename.lower():
        return None
    stem = _SPLIT_SUFFIX.sub("", filename[: -len(".gguf")])
    return re.split(r"[-.]", stem)[-1]


def candidates(paths: list[str]) -> list[str]:
    """檔案路徑清單 → 量化名稱候選:略過不是量化版本的檔案,依清單順序去重(不分大小寫,留第一個出現的寫法)。"""
    names: list[str] = []
    seen: set[str] = set()
    for path in paths:
        name = quant_name(path)
        if name is not None and name.casefold() not in seen:
            seen.add(name.casefold())
            names.append(name)
    return names
