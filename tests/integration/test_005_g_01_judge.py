"""005 G-01(T170)判定函式的離線回歸:請求失敗不得算過、server config 要比對實際值。

不標 `realrun`,進快速層;只餵手寫的資料給 `judge`,不開 Colab、不花錢,不對 127.0.0.1:11434 送請求。
"""

from realrun.test_005_g_01 import judge

TUNING_AUTO = {"numParallel": 8, "contextLength": 8192, "maxLoadedModels": 2, "flashAttention": True, "kvCacheType": "q8_0"}
TUNING_P1 = TUNING_AUTO | {"numParallel": 1}


def config_line(**over: str) -> str:
    env = {
        "OLLAMA_CONTEXT_LENGTH": "8192", "OLLAMA_FLASH_ATTENTION": "true", "OLLAMA_KV_CACHE_TYPE": "q8_0",
        "OLLAMA_MAX_LOADED_MODELS": "2", "OLLAMA_NUM_PARALLEL": "8",
    } | over
    return "LOGPROBE server config " + " ".join(f"{k}:{v}" for k, v in env.items())


def make(tuning: dict, median: float, seq: int, **over) -> dict:
    g = {
        "warmStatus": 200, "tuning": tuning, "rounds": [median] * 3, "median": median,
        "ps": [("qwen2.5:7b", 100, 100, 8192)],
        "log": [config_line(OLLAMA_NUM_PARALLEL=str(tuning["numParallel"])), f"LOGPROBE llama_context: n_seq_max = {seq}"],
    }
    return g | over


def good() -> tuple[dict, dict]:
    return make(TUNING_AUTO, 6.4, 8), make(TUNING_P1, 12.8, 1)


def test_全部成功且值一致時通過() -> None:
    verdict = judge(*good())
    assert verdict["g01"] is True, verdict
    assert verdict["envProblems"] == []


def test_自動組有請求失敗時不通過() -> None:
    auto, p1 = good()
    auto = auto | {"errors": ["第 1 輪:['500', '500']", "第 2 輪:['500']", "第 3 輪:['500']"], "rounds": [], "median": None}
    verdict = judge(auto, p1)
    assert verdict["g01"] is False and verdict["requestsOk"] is False and verdict["ratio"] is None


def test_只有一輪有失敗也不通過() -> None:
    auto, p1 = good()
    auto = auto | {"errors": ["第 2 輪:['500']"], "rounds": [6.4, 6.4], "median": None}
    assert judge(auto, p1)["g01"] is False


def test_即使留著_median_只要有_errors_就不通過() -> None:
    auto, p1 = good()
    assert judge(auto | {"errors": ["第 1 輪:['500']"]}, p1)["g01"] is False


def test_暖機沒回_200_不通過() -> None:
    auto, p1 = good()
    assert judge(auto, p1 | {"warmStatus": 500})["g01"] is False
    assert judge(auto | {"warmStatus": None}, p1)["g01"] is False


def test_平行1組請求失敗時不通過() -> None:
    auto, p1 = good()
    assert judge(auto, p1 | {"errors": ["第 1 輪:['Timeout']"], "rounds": [12.8, 12.8], "median": None})["g01"] is False


def test_五個變數的值全錯時不通過() -> None:
    auto, p1 = good()
    wrong = {k: "WRONG" for k in ("OLLAMA_NUM_PARALLEL", "OLLAMA_CONTEXT_LENGTH", "OLLAMA_MAX_LOADED_MODELS", "OLLAMA_FLASH_ATTENTION", "OLLAMA_KV_CACHE_TYPE")}
    auto = auto | {"log": [config_line(**wrong), "LOGPROBE llama_context: n_seq_max = 8"]}
    verdict = judge(auto, p1)
    assert verdict["g01"] is False and verdict["envOk"] is False
    assert len(verdict["envProblems"]) == 5 and "預期 8,實際 WRONG" in verdict["envProblems"][0]


def test_單一變數不符時指出預期值與實際值() -> None:
    auto, p1 = good()
    auto = auto | {"log": [config_line(OLLAMA_CONTEXT_LENGTH="4096"), "LOGPROBE llama_context: n_seq_max = 8"]}
    verdict = judge(auto, p1)
    assert verdict["g01"] is False
    assert verdict["envProblems"] == ["自動 OLLAMA_CONTEXT_LENGTH:預期 8192,實際 4096"]


def test_平行1組沒有_server_config_時不通過() -> None:
    auto, p1 = good()
    p1 = p1 | {"log": ["LOGPROBE llama_context: n_seq_max = 8", "LOGPROBE llama_context: n_seq_max = 1"]}
    verdict = judge(auto, p1)
    assert verdict["g01"] is False and verdict["envProblems"] == ["平行 1:log 沒有 server config 那一行"]


def test_平行1組取重啟後最後一行_server_config() -> None:
    auto, p1 = good()
    p1 = p1 | {"log": [config_line(), "LOGPROBE llama_context: n_seq_max = 8", config_line(OLLAMA_NUM_PARALLEL="1"), "LOGPROBE llama_context: n_seq_max = 1"]}
    assert judge(auto, p1)["g01"] is True


def test_平行1組只留著重啟前的值時不通過() -> None:
    auto, p1 = good()
    p1 = p1 | {"log": [config_line(), "LOGPROBE llama_context: n_seq_max = 8", "LOGPROBE llama_context: n_seq_max = 1"]}
    assert judge(auto, p1)["g01"] is False


def test_布林值大小寫正規化() -> None:
    auto, p1 = good()
    auto = auto | {"log": [config_line(OLLAMA_FLASH_ATTENTION="True"), "LOGPROBE llama_context: n_seq_max = 8"]}
    assert judge(auto, p1)["g01"] is True
    auto = auto | {"log": [config_line(OLLAMA_FLASH_ATTENTION="false"), "LOGPROBE llama_context: n_seq_max = 8"]}
    assert judge(auto, p1)["g01"] is False


def test_耗時比超過門檻時不通過() -> None:
    assert judge(make(TUNING_AUTO, 9.0, 8), make(TUNING_P1, 12.8, 1))["g01"] is False
