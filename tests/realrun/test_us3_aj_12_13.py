"""US3-AJ-12(T246)與 US3-AJ-13(T247):同一段時間量測,所以合成一個檔、一個測試函式,寫兩列結果。

- US3-AJ-12:下載 `qwen2.5:7b` 到可推論在 3 分鐘內(SC-004);下載完成前 `/api/tags` 都沒有它(FR-018、Q2)。
- US3-AJ-13:背景下載期間的推論平均延遲,比沒有下載時多不到 0.5 秒(SC-008)。

順序:沒有下載時經 11436 送 5 次 `generate`(qwen2.5:0.5b,num_predict 16)→ `POST /api/downloads`(相當於下載模型頁的「確認加入」)
→ 主執行緒每 2 秒經 11436 讀 `/api/tags` 與 `GET /api/downloads`,另一條執行緒在下載中送 5 次 `generate`
→ 下載完成後立即經 11436 對 `qwen2.5:7b` 送一次非串流 `generate`(num_predict 8、`keep_alive: 0`,推論完即卸載)。
沿用 US1-AJ-17 的 T4,約 4 分鐘、約 0.08 compute units;只下載 `qwen2.5:7b` 一次。判定者:腳本(3 分鐘、0.5 秒門檻)。
"""

import threading
import time
from datetime import datetime
from typing import Any

from realrun.conftest import write_measurement
from realrun.helpers_container import LARGE, SMALL, generate_body, get_stack, mean, now_utc, parse_time, verdict

DOWNLOAD_DEADLINE = 360
POLL = 2


def model_names(response) -> list[str]:
    try:
        return [m.get("name") for m in response.json().get("models", [])]
    except ValueError:
        return []


def test_us3_aj_12_and_13(realrun):
    stack = get_stack(realrun)
    stack.require_cases([("US3-AJ-12", "T246"), ("US3-AJ-13", "T247")], "main_ready", "small_loaded")
    write_aj13 = True
    try:
        _measure(realrun, stack)
        write_aj13 = False
    finally:
        if write_aj13 and not stack.state.get("aj13_written"):
            write_measurement("US3-AJ-13", "T247", "—", "—", None, "與 US3-AJ-12 同一段量測,量測中斷")


def _measure(realrun, stack) -> None:
    tags_before = model_names(stack.ollama("GET", "/api/tags", timeout=30)[0])
    if LARGE in tags_before:
        write_measurement("US3-AJ-12", "T246", "—", "—", None, f"執行環境上已經有 {LARGE},前置不成立")
        write_measurement("US3-AJ-13", "T247", "—", "—", None, f"執行環境上已經有 {LARGE},前置不成立")
        stack.state["aj13_written"] = True
        return

    small = generate_body(SMALL, 16)
    baseline = []
    for _ in range(5):
        response, seconds = stack.ollama("POST", "/api/generate", small)
        baseline.append(seconds if response.status_code == 200 else float("nan"))

    during: list[dict[str, Any]] = []
    downloading = threading.Event()

    def infer_during_download() -> None:
        downloading.wait(timeout=120)
        for _ in range(5):
            response, seconds = stack.ollama("POST", "/api/generate", small)
            during.append({"s": seconds, "status": response.status_code, "endedAt": now_utc()})

    worker = threading.Thread(target=infer_during_download, name="aj13-infer", daemon=True)
    worker.start()

    confirmed = time.monotonic()
    enqueued = stack.ui("POST", "/api/downloads", {"models": [LARGE]})
    tags_early: list[bool] = []  # 每次讀 tags 時:tags 有 7b 而之後讀到的佇列還沒完成 → 違反 FR-018
    polls = 0
    job: dict[str, Any] = {}
    completed_seen: datetime | None = None
    while enqueued.status_code == 201 and time.monotonic() - confirmed <= DOWNLOAD_DEADLINE:
        has_large = LARGE in model_names(stack.ollama("GET", "/api/tags", timeout=30)[0])
        jobs = [j for j in stack.ui("GET", "/api/downloads").json().get("jobs", []) if j["model"] == LARGE]
        job = jobs[-1] if jobs else {}
        polls += 1
        if job.get("state") == "downloading":
            downloading.set()
        if job.get("state") == "completed":
            completed_seen = now_utc()
            break
        if job.get("state") == "failed":
            break
        tags_early.append(has_large)
        time.sleep(POLL)
    downloading.set()
    worker.join(timeout=300)

    gen_status = None
    total_s = None
    tags_after: list[str] = []
    if completed_seen is not None:
        response, _ = stack.ollama("POST", "/api/generate", generate_body(LARGE, 8, keep_alive=0), timeout=300)
        gen_status = response.status_code
        total_s = time.monotonic() - confirmed
        tags_after = model_names(stack.ollama("GET", "/api/tags", timeout=30)[0])

    finished_at = parse_time(job.get("finishedAt")) or completed_seen
    extra12 = [] if enqueued.status_code == 201 else [f"POST /api/downloads 回 {enqueued.status_code}:{enqueued.text[:160]}"]
    if job.get("state") == "failed":
        extra12.append(f"下載失敗:{job.get('reasonCode')}")
    checks12 = {
        "則1": gen_status == 200 and total_s is not None and total_s <= 180,
        "則2": completed_seen is not None and not any(tags_early),
        "則3": LARGE in tags_after,
    }
    numbers12 = (
        f"確認加入到 generate 200:{f'{total_s:.1f} 秒' if total_s is not None else '沒有完成'};"
        f"下載中讀 tags {len(tags_early)} 次,其中有 {LARGE} 的 {sum(tags_early)} 次;generate HTTP {gen_status}"
    )

    # US3-AJ-13
    ok_during = [d for d in during if d["status"] == 200]
    all_before_done = bool(finished_at) and len(ok_during) == 5 and all(d["endedAt"] <= finished_at for d in ok_during)
    diff = mean([d["s"] for d in ok_during]) - mean(baseline)
    numbers13 = (
        f"沒有下載時平均 {mean(baseline):.3f} 秒;下載期間平均 {mean([d['s'] for d in ok_during]):.3f} 秒"
        f"({len(ok_during)}/5 次成功);差 {diff:.3f} 秒"
    )
    if not all_before_done:
        write_measurement("US3-AJ-13", "T247", numbers13, "則1 平均差 ≤ 0.5 秒;則2 都在下載完成前送完", None,
                          "下載期間的 5 次沒有全部在下載完成前送完(或下載沒完成),本次不算")  # fmt: skip
    else:
        write_measurement("US3-AJ-13", "T247", numbers13, "則1 平均差 ≤ 0.5 秒;則2 都在下載完成前送完", diff <= 0.5,
                          "" if diff <= 0.5 else "沒過:則1")  # fmt: skip
    stack.state["aj13_written"] = True
    stack.state["large_downloaded"] = LARGE in tags_after

    verdict(
        "US3-AJ-12", "T246", checks12, numbers12,
        "則1 確認加入到 generate 200 ≤ 3 分鐘;則2 下載完成前 tags 都沒有;則3 完成後 tags 有",
        extra12,
    )  # fmt: skip
    assert not all_before_done or diff <= 0.5, f"US3-AJ-13 沒過:差 {diff:.3f} 秒"
