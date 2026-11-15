"""006 G-03(tasks.md T050):`stream:true` 經本系統轉送時每一段的延遲(testplan.md § 5.2;plan.md § 待決問題 Q28 (a))。

接縫同 US1-OC-11:`bridge` fixture(測試行程內的 uvicorn,127.0.0.1 隨機 port),工作階段經 UI 開到就緒,
轉送打到測試行程內的假 Ollama;假 Ollama 的 `/v1/chat/completions` 回 `SseReply`,每 0.1 秒送一段、共 20 段。
同一個請求送 5 次,每段的延遲 = 到達用戶端的時間 −(請求送出的時間 + i × 0.1 秒);假 Ollama 最早在那個時間送出第 i 段,
所以這是延遲的上限。門檻:5 次的每一段都 ≤ 0.5 秒(SC-003、NFR-001)。

不標 `realrun`,進快速層;只用測試行程內的假伺服器,不開 Colab、不花錢,不對 127.0.0.1:11434 送請求。
結果在環境變數 `CGB_WRITE_MEASUREMENTS=1` 時附加到 `specs/006-agent-client-connect/measurements.md`
(快速層每次執行都寫的話,追蹤中的檔案每跑一次就多一節;斷言每次都做)。
判定者:腳本;樣本:固定 20 段。
"""

import os
import statistics
import time
from datetime import datetime

from fakes.ollama_server import SseReply
from integration.test_006_v1 import CHAT_BODY, chunk
from integration.test_ollama_compat import Bridge, bridge  # noqa: F401 - bridge 是 pytest fixture
from realrun.test_006_g_01 import append_section

INTERVAL, COUNT, ROUNDS, LIMIT = 0.1, 20, 5, 0.5


async def one_round(bridge: Bridge) -> list[float]:
    arrivals: list[float] = []
    seen = 0
    started = time.monotonic()
    async with bridge.ollama.stream("POST", "/v1/chat/completions", json={**CHAT_BODY, "stream": True}) as response:
        assert response.status_code == 200
        async for part in response.aiter_raw():
            seen += part.count(b"\n\n")
            arrivals.extend([time.monotonic()] * (seen - len(arrivals)))
    assert len(arrivals) == COUNT, f"收到 {len(arrivals)} 段,應該是 {COUNT} 段"
    return [arrived - (started + i * INTERVAL) for i, arrived in enumerate(arrivals)]


async def test_006_g_03_串流每一段延遲都在_0_5_秒內(bridge: Bridge) -> None:
    # Arrange
    await bridge.ready()
    bridge.server.add("POST", "/v1/chat/completions", SseReply([chunk({"content": str(i)}) for i in range(COUNT)], interval=INTERVAL))

    # Act
    rounds = [await one_round(bridge) for _ in range(ROUNDS)]

    # Assert
    worst = max(max(r) for r in rounds)
    passed = worst <= LIMIT
    if os.environ.get("CGB_WRITE_MEASUREMENTS") == "1":
        append_section(
            "G-03(T050)`stream:true` 每一段的延遲(測試行程內的假 Ollama)",
            [
                f"日期:{datetime.now():%Y-%m-%d %H:%M};環境:桌機,`tests/integration/test_006_g_03.py`(快速層、不標 `realrun`),"
                "測試行程內的 uvicorn(127.0.0.1 隨機 port)經 httpx 轉送到測試行程內的假 Ollama,不開 Colab、不花錢",
                f"樣本:假 Ollama 的 `SseReply` 每 {INTERVAL} 秒送一段、共 {COUNT} 段,同一個請求送 {ROUNDS} 次",
                "每次的最大延遲(秒):" + "、".join(f"{max(r):.4f}" for r in rounds),
                "每次的延遲中位數(秒):" + "、".join(f"{statistics.median(r):.4f}" for r in rounds),
                f"**{ROUNDS} 次 × {COUNT} 段的最大延遲 {worst:.4f} 秒,門檻每一段 ≤ {LIMIT} 秒:{'過' if passed else '沒過'}**",
                "判定者:腳本;樣本:固定 20 段(延遲以「請求送出 + i × 間隔」當送出時間,是上限)",
                "收尾:假伺服器與 uvicorn 由 fixture 停下;沒有起任何外部行程",
            ],
        )
    assert passed, [f"{max(r):.3f}" for r in rounds]
