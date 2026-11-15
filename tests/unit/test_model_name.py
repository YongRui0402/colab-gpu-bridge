"""模型名稱的格式、補版本與比對鍵(`cgb.domain.model_name`;testplan.md § 5.1 US4-API-27~29;plan.md Q49)。"""

from cgb.domain.model_name import is_valid, match_key, source_of, with_version

# ---- 004 US4-API-27


def test_補版本只在沒寫版本時接_latest_且來源看_hf_co_前綴() -> None:
    """US4-API-27:`hf.co` 的 `.co` 不是版本分隔;補版本不轉大小寫;官方名稱的來源是 library。"""
    results = {
        "無版本補 latest": with_version("hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF"),
        "有版本照原樣": with_version("hf.co/x/y:Q4_K_M"),
        "hf.co 來源": source_of("hf.co/x/y:Q4_K_M"),
        "官方來源": source_of("qwen2.5:7b"),
    }

    assert results == {
        "無版本補 latest": "hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:latest",
        "有版本照原樣": "hf.co/x/y:Q4_K_M",
        "hf.co 來源": "huggingface",
        "官方來源": "library",
    }

# ---- 004 US4-API-28


def test_比對鍵不分大小寫_沒寫版本與_latest_視為同一個() -> None:
    """US4-API-28:鍵 = 補版本後 casefold;不同量化版本、`latest` 與別的版本不相等。"""
    results = {
        "大小寫不同的 hf.co 名稱": match_key("hf.co/Bartowski/smollm2-135M-Instruct-GGUF:Q4_K_M")
        == match_key("hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:q4_k_m"),
        "沒寫版本等於 LATEST": match_key("hf.co/x/y") == match_key("hf.co/x/y:LATEST"),
        "沒寫版本不等於 Q4_K_M": match_key("hf.co/x/y") != match_key("hf.co/x/y:Q4_K_M"),
        "官方 Latest 等於沒寫版本": match_key("qwen2.5:Latest") == match_key("qwen2.5"),
        "官方 7b 不等於 latest": match_key("qwen2.5:7b") != match_key("qwen2.5:latest"),
    }

    assert results == {
        "大小寫不同的 hf.co 名稱": True,
        "沒寫版本等於 LATEST": True,
        "沒寫版本不等於 Q4_K_M": True,
        "官方 Latest 等於沒寫版本": True,
        "官方 7b 不等於 latest": True,
    }

# ---- 004 US4-API-29


def test_名稱格式只收官方名稱與_hf_co_且_hf_co_要小寫前綴() -> None:
    """US4-API-29:`hf.co/<作者>/<模型>` 的作者與模型可大寫;`huggingface.co/`、`HF.CO/`、社群 `<使用者>/<名稱>` 與多一層 `/` 都不收。"""
    valid = [
        "qwen2.5",
        "qwen2.5:7b",
        "hf.co/bartowski/SmolLM2-135M-Instruct-GGUF",
        "hf.co/Bartowski/x.y-z:Q4_K_M",
    ]
    invalid = [
        "huggingface.co/bartowski/x:Q4_K_M",
        "HF.CO/bartowski/x",
        "Qwen2.5",
        "bartowski/x",
        "hf.co/bartowski",
        "hf.co/-a/b",
        "hf.co/a/b/c",
    ]

    results = {name: is_valid(name) for name in valid + invalid}

    assert results == {**{name: True for name in valid}, **{name: False for name in invalid}}
