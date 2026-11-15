"""E2 後端 UI API:連線設定片段的純函式(testplan.md § 2.2,`domain/connect.py` 純函式)。

接縫:`cgb.domain.connect` 的公開函式,不接任何轉接層。
"""

import json

from cgb.domain import connect


# ---------------------------------------------------------------- US1-API-01


def test_opencode_片段指向_v1_並依模型清單與_context_列出模型() -> None:
    # Arrange
    models = ["qwen2.5-coder:7b", "qwen2.5:3b"]

    # Act
    snippet = json.loads(connect.opencode_snippet(11436, models, 32768))

    # Assert
    provider = snippet["provider"]["cgb"]
    assert provider["npm"] == "@ai-sdk/openai-compatible"
    assert provider["options"]["baseURL"] == "http://{{host}}:11436/v1"
    assert set(provider["models"]) == {"qwen2.5-coder:7b", "qwen2.5:3b"}
    assert [m["limit"] for m in provider["models"].values()] == [{"context": 32768, "output": 4096}] * 2


# ---------------------------------------------------------------- US1-API-02


def test_opencode_片段的單次回覆上限不超過_context_的一半() -> None:
    # Arrange
    contexts = [4096, 8191]

    # Act
    outputs = [
        json.loads(connect.opencode_snippet(11436, ["qwen2.5:3b"], context))["provider"]["cgb"]["models"]["qwen2.5:3b"]["limit"]["output"]
        for context in contexts
    ]

    # Assert
    assert outputs == [2048, 4095]


# ---------------------------------------------------------------- US2-API-01


def test_pi_的_models_片段用_completions_並關掉_developer_role_與_reasoning_effort() -> None:
    # Act
    snippet = json.loads(connect.pi_models_snippet(11436, ["qwen2.5-coder:7b"], 32768))

    # Assert
    provider = snippet["providers"]["cgb"]
    assert provider["baseUrl"] == "http://{{host}}:11436/v1"
    assert provider["api"] == "openai-completions"
    assert provider["apiKey"] == "ollama"
    assert provider["compat"] == {"supportsDeveloperRole": False, "supportsReasoningEffort": False}
    assert provider["models"] == [
        {
            "id": "qwen2.5-coder:7b",
            "name": "qwen2.5-coder:7b",
            "reasoning": False,
            "input": ["text"],
            "contextWindow": 32768,
            "maxTokens": 4096,
        }
    ]


# ---------------------------------------------------------------- US2-API-02


def test_pi_的單次回覆上限與壓縮預留隨_context_縮小且預留無條件捨去() -> None:
    # Arrange
    contexts = [4096, 16384, 32767]

    # Act
    max_tokens = [json.loads(connect.pi_models_snippet(11436, ["qwen2.5:3b"], context))["providers"]["cgb"]["models"][0]["maxTokens"] for context in contexts]
    reserve_tokens = [json.loads(connect.pi_settings_snippet(context))["compaction"]["reserveTokens"] for context in contexts]

    # Assert
    assert max_tokens == [2048, 4096, 4096]
    assert reserve_tokens == [1024, 4096, 8191]


# ---------------------------------------------------------------- US3-API-01

GIB = 2**30


def test_建議的_context_長度依顯示記憶體算且讀不到時用下限且不超過上限() -> None:
    # Arrange
    vram_cases = [12 * GIB, 12 * GIB - 1, 40 * GIB, None]

    # Act
    recommended = [connect.recommended_context_length(vram) for vram in vram_cases]

    # Assert
    assert recommended == [32768, 16384, 32768, 16384]
    assert all(value <= 131072 for value in recommended)


# ---------------------------------------------------------------- US3-API-02


def test_context_小於建議下限才提醒且讀不到時不提醒() -> None:
    # Arrange
    context_cases = [4096, 16383, 16384, None]

    # Act
    warnings = [connect.should_warn(context) for context in context_cases]

    # Assert
    assert warnings == [True, True, False, False]
