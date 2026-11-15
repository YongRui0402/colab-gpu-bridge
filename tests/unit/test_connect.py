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
