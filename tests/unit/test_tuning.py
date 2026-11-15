"""E2 `domain/tuning.py` 的級距、範圍檢查與組合規則(testplan.md § 2.2 US1-API-11~16、§ 3.2 US2-API-16~22;spec FR-002、FR-003、FR-007、FR-017)。

接縫:`domain/tuning.py` 純函式(testplan.md § 接縫的取捨)。1 GiB = 1073741824 位元組。
"""

from cgb.domain import tuning
from cgb.domain.errors import ApiError

GIB = 1073741824


# ---- 005 US1-API-11


def test_未滿_12_GiB_的顯示記憶體用第一級():
    # Arrange
    vram = [0, 6 * GIB, 12_000_000_000, 12 * GIB - 1]  # 12_000_000_000 是十進位的 12 GB,約 11.18 GiB

    # Act
    tiers = [tuning.auto_tier(v) for v in vram]

    # Assert
    assert tiers == [(1, 4096, 1)] * 4


# ---- 005 US1-API-12


def test_12_GiB_起到未滿_20_GiB_用第二級():
    # Arrange
    vram = [12 * GIB, 15 * GIB, 20 * GIB - 1]  # 15 GiB 是 T4

    # Act
    tiers = [tuning.auto_tier(v) for v in vram]

    # Assert
    assert tiers == [(2, 4096, 1)] * 3


# ---- 005 US1-API-13


def test_20_GiB_起到未滿_32_GiB_用第三級():
    # Arrange
    vram = [20 * GIB, int(22.5 * GIB), 32 * GIB - 1]  # 22.5 GiB 是 L4

    # Act
    tiers = [tuning.auto_tier(v) for v in vram]

    # Assert
    assert tiers == [(4, 8192, 1)] * 3


# ---- 005 US1-API-14


def test_32_GiB_起到未滿_64_GiB_用第四級():
    # Arrange
    vram = [32 * GIB, 40 * GIB, 64 * GIB - 1]  # 40 GiB 是 A100

    # Act
    tiers = [tuning.auto_tier(v) for v in vram]

    # Assert
    assert tiers == [(8, 8192, 2)] * 3


# ---- 005 US1-API-15


def test_64_GiB_以上用最高一級_沒有上限():
    # Arrange
    vram = [64 * GIB, 80 * GIB, 96 * GIB]  # 80 GiB 是 H100

    # Act
    tiers = [tuning.auto_tier(v) for v in vram]

    # Assert
    assert tiers == [(16, 8192, 3)] * 3


# ---- 005 US1-API-16


def test_讀不到顯示記憶體時沒有自動值():
    # Arrange
    vram = None

    # Act
    tier = tuning.auto_tier(vram)

    # Assert
    assert tier is None


# ================================================================ 故事 2(testplan.md § 3.2,US2-API-16~22)


def tuning_body(np, ctx, mlm):
    return {"numParallel": np, "contextLength": ctx, "maxLoadedModels": mlm}


NONE3 = tuning_body(None, None, None)


def rejected_code(body):
    """`parse_overrides(body)` 丟出的 `ApiError`;沒有丟時是 None。"""
    try:
        tuning.parse_overrides(body)
    except ApiError as error:
        return error
    return None


def parsed_or_code(body, key):
    """`parse_overrides(body)` 回傳的 `key` 那一項;丟出 `ApiError` 時改回它的 `code`。"""
    try:
        return tuning.parse_overrides(body)[key]
    except ApiError as error:
        return error.code


# ---- 005 US2-API-16


def test_平行數接受_1_到_32_其他回平行數的代碼與範圍():
    # Arrange
    accepted = [tuning_body(1, None, None), tuning_body(32, None, None)]
    rejected = [tuning_body(0, None, None), tuning_body(33, None, None)]

    # Act
    parsed = [parsed_or_code(b, "numParallel") for b in accepted]
    errors = [rejected_code(b) for b in rejected]

    # Assert
    assert parsed == [1, 32]
    assert [e.code if e else None for e in errors] == ["INVALID_NUM_PARALLEL"] * 2
    assert errors[0] is not None and errors[0].body()["message"] == "平行數要是 1~32 的整數"


# ---- 005 US2-API-17


def test_context_長度接受_2048_到_131072_其他回_context_長度的代碼與範圍():
    # Arrange
    accepted = [tuning_body(None, 2048, None), tuning_body(None, 131072, None)]
    rejected = [tuning_body(None, 2047, None), tuning_body(None, 131073, None)]

    # Act
    parsed = [parsed_or_code(b, "contextLength") for b in accepted]
    errors = [rejected_code(b) for b in rejected]

    # Assert
    assert parsed == [2048, 131072]
    assert [e.code if e else None for e in errors] == ["INVALID_CONTEXT_LENGTH"] * 2
    assert errors[0] is not None and errors[0].body()["message"] == "context 長度要是 2048~131072 的整數"


# ---- 005 US2-API-18


def test_同時載入模型數接受_1_到_4_其他回同時載入模型數的代碼與範圍():
    # Arrange
    accepted = [tuning_body(None, None, 1), tuning_body(None, None, 4)]
    rejected = [tuning_body(None, None, 0), tuning_body(None, None, 5)]

    # Act
    parsed = [parsed_or_code(b, "maxLoadedModels") for b in accepted]
    errors = [rejected_code(b) for b in rejected]

    # Assert
    assert parsed == [1, 4]
    assert [e.code if e else None for e in errors] == ["INVALID_MAX_LOADED_MODELS"] * 2
    assert errors[0] is not None and errors[0].body()["message"] == "同時載入模型數要是 1~4 的整數"


# ---- 005 US2-API-19


def test_覆蓋值只接受_JSON_的整數_沒有小數部分的數字照整數_null_是自動():
    # Arrange
    rejected = [4.5, "4", True, False]

    # Act
    errors = [rejected_code(tuning_body(v, None, None)) for v in rejected]
    whole = parsed_or_code(tuning_body(4.0, None, None), "numParallel")
    auto = parsed_or_code(tuning_body(None, None, None), "numParallel")

    # Assert
    assert [e.code if e else None for e in errors] == ["INVALID_NUM_PARALLEL"] * 4
    assert type(whole) is int and whole == 4
    assert auto is None


# ---- 005 US2-API-20


def test_本文不是物件或少了欄位時回本文格式錯_範圍依平行數_context_同時載入模型數的順序檢查():
    # Arrange
    bodies = [
        "4",
        [],
        {"numParallel": 4, "contextLength": None},
        tuning_body(0, 1, 0),
        tuning_body(4, 1, 0),
        tuning_body(4, 4096, 0),
    ]

    # Act
    errors = [rejected_code(b) for b in bodies]

    # Assert
    assert [e.code if e else None for e in errors] == [
        "INVALID_REQUEST_BODY",
        "INVALID_REQUEST_BODY",
        "INVALID_REQUEST_BODY",
        "INVALID_NUM_PARALLEL",
        "INVALID_CONTEXT_LENGTH",
        "INVALID_MAX_LOADED_MODELS",
    ]


# ---- 005 US2-API-21


def applied(np, ctx, mlm, sources=("auto", "auto", "auto"), fa="auto"):
    """組出 `AppliedTuning`:來源是 `ollama_default` 的項目 `value` 為 None。"""

    def item(value, source):
        return {"value": None if source == "ollama_default" else value, "source": source}

    return {
        "numParallel": item(np, sources[0]),
        "contextLength": item(ctx, sources[1]),
        "maxLoadedModels": item(mlm, sources[2]),
        "flashAttention": item(True, fa),
        "kvCacheType": item("q8_0", fa),
    }


def test_每一項各自決定_覆蓋值優先_沒填的用級距_和自動值相同仍標手動():
    # Arrange
    a100, t4 = 40 * GIB, 15 * GIB

    # Act
    first = tuning.resolve(a100, tuning_body(4, None, None))
    second = tuning.resolve(a100, tuning_body(8, None, None))
    third = tuning.resolve(t4, NONE3)

    # Assert
    assert first.get("numParallel") == {"value": 4, "source": "manual"}
    assert first.get("contextLength") == {"value": 8192, "source": "auto"}
    assert first.get("maxLoadedModels") == {"value": 2, "source": "auto"}
    assert first.get("flashAttention") == {"value": True, "source": "auto"}
    assert first.get("kvCacheType") == {"value": "q8_0", "source": "auto"}
    assert second.get("numParallel") == {"value": 8, "source": "manual"}
    assert third == applied(2, 4096, 1)


# ---- 005 US2-API-22


def test_讀不到顯示記憶體時沒填的用_Ollama_預設值_有覆蓋值時仍帶_flash_attention_與_KV_cache():
    # Arrange
    vram = None

    # Act
    first = tuning.resolve(vram, NONE3)
    second = tuning.resolve(vram, tuning_body(4, None, None))
    third = tuning.resolve(vram, tuning_body(None, None, 2))

    # Assert
    assert first == applied(None, None, None, sources=("ollama_default",) * 3, fa="ollama_default")
    assert second.get("numParallel") == {"value": 4, "source": "manual"}
    assert second.get("contextLength") == {"value": None, "source": "ollama_default"}
    assert second.get("flashAttention") == {"value": True, "source": "auto"}
    assert third.get("maxLoadedModels") == {"value": 2, "source": "manual"}
    assert third.get("kvCacheType") == {"value": "q8_0", "source": "auto"}
