"""連線設定頁的設定片段(純函式,contracts/ui.openapi.yaml § info.x-snippet-rule)。"""

import json


def _base_url(port: int) -> str:
    """相容端點的位址;`{{host}}` 由前端換成目前網址的主機名稱(info.x-snippet-rule)。"""
    return f"http://{{{{host}}}}:{port}/v1"


def opencode_snippet(port: int, models: list[str], context_length: int | None) -> str:
    """可合併進 `opencode.json` 的 JSON 文字;位址寫成 `http://{{host}}:<port>/v1`,`{{host}}` 由前端換掉。"""
    cgb = {
        "npm": "@ai-sdk/openai-compatible",
        "name": "colab-gpu-bridge",
        "options": {"baseURL": _base_url(port)},
        "models": {model: {"name": model, "limit": {"context": context_length, "output": min(4096, context_length // 2)}} for model in models},
    }
    return json.dumps({"provider": {"cgb": cgb}}, indent=2)


def pi_models_snippet(port: int, models: list[str], context_length: int | None) -> str:
    """pi `~/.pi/agent/models.json` 的 JSON 文字;目前只有 `providers.cgb.baseUrl`,其餘欄位由故事 2 的案例逼出(plan.md Q23)。"""
    return json.dumps({"providers": {"cgb": {"baseUrl": _base_url(port)}}}, indent=2)
