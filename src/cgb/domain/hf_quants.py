"""Hugging Face 量化版本的列表規則(research.md R3 第 1~5 步;plan.md Q49)。"""

import re

# 分割檔結尾的編號(research.md R3 第 3 步):`-00001-of-00002`,不論第幾片
_SPLIT_SUFFIX = re.compile(r"-\d{5}-of-\d{5}$")


def _filename(path: str) -> str:
    """路徑最後一段(資料夾名稱不算,research.md R3 第 2 步)。"""
    return path.rsplit("/", 1)[-1]


def _is_candidate_file(filename: str) -> bool:
    """副檔名是 `.gguf`(不分大小寫)、檔名不含 mmproj(多模態投影檔不是能單獨拉的模型)。"""
    lowered = filename.lower()
    return lowered.endswith(".gguf") and "mmproj" not in lowered


def quant_name(path: str) -> str | None:
    """檔案路徑 → 量化名稱(照檔名原樣的大小寫);只看路徑最後一段,不是 GGUF 或是 mmproj 回 None;去掉分割編號後以 `-` 或 `.` 切開取最後一段。"""
    filename = _filename(path)
    if not _is_candidate_file(filename):
        return None
    stem = _SPLIT_SUFFIX.sub("", filename[: -len(".gguf")])
    return re.split(r"[-.]", stem)[-1]


def candidates(paths: list[str]) -> list[str]:
    """檔案路徑清單 → 量化名稱候選:略過不是量化版本的檔案,依清單順序去重(不分大小寫,留第一個出現的寫法)。"""
    first_spelling: dict[str, str] = {}  # dict 依插入順序,setdefault 留第一個出現的寫法
    for path in paths:
        name = quant_name(path)
        if name is not None:
            first_spelling.setdefault(name.casefold(), name)
    return list(first_spelling.values())
