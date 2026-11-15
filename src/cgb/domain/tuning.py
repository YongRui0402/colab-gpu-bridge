"""Ollama 設定的級距與覆蓋值(plan.md Q31;contracts/ui.openapi.yaml § components.schemas.AppliedTuning)。純函式,不碰 I/O。"""

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
