"""Hugging Face 量化版本的列表規則(`cgb.domain.hf_quants`;testplan.md § 5.1 US4-HF-01~04;research.md R3)。"""

from cgb.domain.hf_quants import candidates, quant_name

# ---- 004 US4-HF-01


def test_量化名稱取自檔名的最後一段_保留原樣的大小寫且不分副檔名大小寫() -> None:
    """US4-HF-01:A 全小寫、B TheBloke 式 `<模型>.<量化>.gguf`、C 沒有分隔符、D 在子資料夾、E 副檔名大寫。"""
    paths = {
        "A": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "B": "llama-2-7b.Q4_K_M.gguf",
        "C": "Q4_K_M.gguf",
        "D": "Q8_0/SmolLM2-135M-Instruct-Q8_0.gguf",
        "E": "SmolLM2-135M-Instruct-F16.GGUF",
    }

    names = {case: quant_name(path) for case, path in paths.items()}

    assert names == {"A": "q4_k_m", "B": "Q4_K_M", "C": "Q4_K_M", "D": "Q8_0", "E": "F16"}

# ---- 004 US4-HF-02


def test_分割檔的量化名稱去掉分割編號_三片只算一個候選() -> None:
    """US4-HF-02:A 分割檔的第 1 片、B 子資料夾裡的第 2 片(最後一片);三片 `m-Q6_K-0000N-of-00003.gguf` 一起給 `candidates`。"""
    names = {
        "A": quant_name("Meta-Llama-3.1-70B-Instruct-Q5_K_M-00001-of-00002.gguf"),
        "B": quant_name("Q8_0/Meta-Llama-3.1-70B-Instruct-Q8_0-00002-of-00002.gguf"),
    }

    listed = candidates(["m-Q6_K-00001-of-00003.gguf", "m-Q6_K-00002-of-00003.gguf", "m-Q6_K-00003-of-00003.gguf"])

    assert (names, listed) == ({"A": "Q5_K_M", "B": "Q8_0"}, ["Q6_K"])

# ---- 004 US4-HF-03


def test_多模態投影檔與不是_GGUF_的檔案不算量化版本() -> None:
    """US4-HF-03:A、B 是 mmproj(B 大寫);C 只有資料夾名稱含 mmproj;D、E 不是 GGUF;F 是 `.gguf.part`。"""
    paths = {
        "A": "mmproj-model-f16.gguf",
        "B": "Qwen2-VL-2B-Instruct-MMPROJ-F16.gguf",
        "C": "mmproj/SmolLM2-135M-Instruct-Q4_K_M.gguf",
        "D": "README.md",
        "E": "model.safetensors",
        "F": "SmolLM2-135M-Instruct-Q4_K_M.gguf.part",
    }

    names = {case: quant_name(path) for case, path in paths.items()}

    assert names == {"A": None, "B": None, "C": "Q4_K_M", "D": None, "E": None, "F": None}

# ---- 004 US4-HF-04


def test_候選依清單順序去重_不分大小寫_留第一個出現的寫法_並略過不是量化版本的檔案() -> None:
    """US4-HF-04:`Q4_K_M` 與 `q4_k_m`、`f16` 與 `F16` 各算一個;mmproj 與 README 不列。"""
    paths = ["a-Q4_K_M.gguf", "b-q4_k_m.gguf", "a-f16.gguf", "a-F16.gguf", "a-Q2_K.gguf", "mmproj-a-f16.gguf", "README.md"]

    listed = candidates(paths)

    assert listed == ["Q4_K_M", "f16", "Q2_K"]
