"""模型名稱的補版本規則(research.md R1;contracts/ui.openapi.yaml § info.x-model-name-rule)。"""


def with_version(name: str) -> str:
    """含 `:` 就照原樣;不含就接 `:latest`。不轉大小寫、不去空白(`qwen2.5:Latest` 不等於 `qwen2.5:latest`)。"""
    return name if ":" in name else f"{name}:latest"
