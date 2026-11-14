"""模型名稱的格式與補版本規則(research.md R1、R4;contracts/ui.openapi.yaml § components.schemas.ModelName、info.x-model-name-rule)。"""

import re

# 官方名稱(小寫,可帶 `:版本`)或 `hf.co/<作者>/<模型>[:<量化版本>]`;`huggingface.co/` 與社群的 `<使用者>/<名稱>` 都不收
_MODEL_NAME = re.compile(
    r"([a-z0-9][a-z0-9._-]*|hf\.co/[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)(:[A-Za-z0-9_][A-Za-z0-9._-]*)?"
)


def is_valid(name: object) -> bool:
    """`name` 是字串且符合 `ModelName` 的格式。"""
    return isinstance(name, str) and _MODEL_NAME.fullmatch(name) is not None


def with_version(name: str) -> str:
    """含 `:` 就照原樣;不含就接 `:latest`。不轉大小寫、不去空白(`qwen2.5:Latest` 不等於 `qwen2.5:latest`)。"""
    return name if ":" in name else f"{name}:latest"


def match_key(name: str) -> str:
    """比對用的鍵:補版本後 casefold(`info.x-model-name-rule` (2));兩個名稱的鍵相同就是同一個模型。"""
    return with_version(name).casefold()
