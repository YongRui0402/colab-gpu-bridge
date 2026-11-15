"""連線設定頁的設定片段(純函式,contracts/ui.openapi.yaml § info.x-snippet-rule)。"""

import json


def _base_url(port: int) -> str:
    """相容端點的位址;`{{host}}` 由前端換成目前網址的主機名稱(info.x-snippet-rule)。"""
    return f"http://{{{{host}}}}:{port}/v1"


def _max_output(context_length: int | None) -> int:
    """單次回覆上限 `min(4096, ⌊context ÷ 2⌋)`;`context_length` 為 None 時 4096(plan.md Q15)。"""
    return 4096 if context_length is None else min(4096, context_length // 2)


def reserve_tokens(context_length: int | None) -> int | None:
    """pi 壓縮要預留的 token 數 `⌊context ÷ 4⌋`;讀不到 context 時為 None(FR-013)。"""
    return None if context_length is None else context_length // 4


def opencode_snippet(port: int, models: list[str], context_length: int | None) -> str:
    """可合併進 `opencode.json` 的 JSON 文字;位址寫成 `http://{{host}}:<port>/v1`,`{{host}}` 由前端換掉。"""
    models_entry: dict[str, dict[str, object]] = {}
    for model in models:
        entry: dict[str, object] = {"name": model}
        if context_length is not None:
            entry["limit"] = {"context": context_length, "output": _max_output(context_length)}
        models_entry[model] = entry
    cgb = {
        "npm": "@ai-sdk/openai-compatible",
        "name": "colab-gpu-bridge",
        "options": {"baseURL": _base_url(port)},
        "models": models_entry,
    }
    return json.dumps({"provider": {"cgb": cgb}}, indent=2)


def pi_models_snippet(port: int, models: list[str], context_length: int | None) -> str:
    """pi `~/.pi/agent/models.json` 的 JSON 文字(research.md R3);`context_length` 為 None 時不附 `contextWindow`。"""
    entries = []
    for model in models:
        entry: dict[str, object] = {"id": model, "name": model, "reasoning": False, "input": ["text"]}
        if context_length is not None:
            entry["contextWindow"] = context_length
        entry["maxTokens"] = _max_output(context_length)
        entries.append(entry)
    cgb = {
        "baseUrl": _base_url(port),
        "api": "openai-completions",
        "apiKey": "ollama",
        "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": False},
        "models": entries,
    }
    return json.dumps({"providers": {"cgb": cgb}}, indent=2)


def pi_settings_snippet(context_length: int | None) -> str | None:
    """pi `~/.pi/agent/settings.json` 的 JSON 文字;`context_length` 為 None 時回 None(FR-013)。"""
    reserve = reserve_tokens(context_length)
    if reserve is None:
        return None
    return json.dumps({"compaction": {"reserveTokens": reserve}}, indent=2)


_GIB = 2**30
# coding agent 的建議下限(R4)與依顯示記憶體估算的建議值(R5、Q11)
RECOMMENDED_MIN_CONTEXT = 16384
_LARGE_VRAM_BYTES = 12 * _GIB
_CONTEXT_FOR_LARGE_VRAM = 32768
_CONTEXT_CEILING = 131072


def recommended_context_length(vram_bytes: int | None) -> int:
    """建議的 context 長度:顯示記憶體 ≥ 12 GiB 為 32768,否則與讀不到時為 16384(FR-007、Q11);上限 131072。"""
    large = vram_bytes is not None and vram_bytes >= _LARGE_VRAM_BYTES
    return min(_CONTEXT_CEILING, _CONTEXT_FOR_LARGE_VRAM if large else RECOMMENDED_MIN_CONTEXT)


def should_warn(context_length: int | None) -> bool:
    """讀得到 context 且小於建議下限才提醒(FR-006、R4);讀不到時不提醒。"""
    return context_length is not None and context_length < RECOMMENDED_MIN_CONTEXT
