"""Ollama 設定的級距與覆蓋值(plan.md Q31;contracts/ui.openapi.yaml § components.schemas.AppliedTuning)。純函式,不碰 I/O。"""

from typing import Any

from cgb.domain.errors import ApiError

GIB = 1073741824

# FR-002 的級距:(顯示記憶體下限(含), 平行數, context 長度, 同時載入模型數),由高到低;最後一級沒有上限
_TIERS = (
    (64 * GIB, 16, 8192, 3),
    (32 * GIB, 8, 8192, 2),
    (20 * GIB, 4, 8192, 1),
    (12 * GIB, 2, 4096, 1),
    (0, 1, 4096, 1),
)


def auto_tier(vram_total_bytes: int | None) -> tuple[int, int, int] | None:
    """依顯示記憶體總量(位元組)回自動值 (平行數, context 長度, 同時載入模型數)(FR-002)。"""
    if vram_total_bytes is None:
        # 讀不到就不帶 FR-002 的變數,用 Ollama 預設值(FR-003)
        return None
    # 第一個下限不超過顯示記憶體的那一級;都不符時(只有負值)和重構前一樣落在最低一級
    tier = next((t for t in _TIERS if vram_total_bytes >= t[0]), _TIERS[-1])
    return tier[1:]


# FR-017 的範圍:(覆蓋值的名稱, 下限, 上限, 不符時的代碼),依檢查的順序(contracts/ui.openapi.yaml § info.x-tuning-rule (1))
_RANGES = (
    ("numParallel", 1, 32, "INVALID_NUM_PARALLEL"),
    ("contextLength", 2048, 131072, "INVALID_CONTEXT_LENGTH"),
    ("maxLoadedModels", 1, 4, "INVALID_MAX_LOADED_MODELS"),
)


def parse_overrides(body: Any) -> dict[str, int | None]:
    """驗證 `TuningOverrides`,回傳三個覆蓋值;不符時丟 `ApiError(400, code)`。"""
    if not isinstance(body, dict) or any(key not in body for key, *_ in _RANGES):
        # 不是物件或少了三個欄位之一
        raise ApiError(400, "INVALID_REQUEST_BODY")
    overrides: dict[str, int | None] = {}
    for key, low, high, code in _RANGES:
        value = body[key]
        if value is None:
            overrides[key] = None
            continue
        # 只接受 JSON 的整數;布林值不算,沒有小數部分的數字(4.0)照整數接受
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not float(value).is_integer():
            raise ApiError(400, code)
        value = int(value)
        if not low <= value <= high:
            raise ApiError(400, code)
        overrides[key] = value
    return overrides


def resolve(vram_total_bytes: int | None, overrides: dict[str, int | None]) -> dict[str, Any]:
    """「覆蓋值 > 級距 > 不帶」逐項決定 `AppliedTuning`(FR-007);和自動值相同的覆蓋值仍是 `manual`。"""
    tier = auto_tier(vram_total_bytes)
    tuning: dict[str, Any] = {}
    for index, (key, *_) in enumerate(_RANGES):
        value = overrides[key]
        if value is not None:
            tuning[key] = {"value": value, "source": "manual"}
        elif tier is not None:
            tuning[key] = {"value": tier[index], "source": "auto"}
        else:
            # 讀不到顯示記憶體:沒填的項目不帶,用 Ollama 預設值(FR-003)
            tuning[key] = {"value": None, "source": "ollama_default"}
    if tier is None and all(value is None for value in overrides.values()):
        # 讀不到又沒有任何覆蓋值時照 004 的方式,flash attention 與 KV cache 也不帶(FR-003)
        tuning["flashAttention"] = {"value": None, "source": "ollama_default"}
        tuning["kvCacheType"] = {"value": None, "source": "ollama_default"}
    else:
        tuning["flashAttention"] = {"value": True, "source": "auto"}
        tuning["kvCacheType"] = {"value": "q8_0", "source": "auto"}
    return tuning
