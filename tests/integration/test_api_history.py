"""E2 後端 UI API:工作階段紀錄(testplan.md § 2.1,`/api/sessions` › 列出紀錄、查一筆;FR-028)。

接縫:HTTP `/api/*`,五個轉接層用替身;運行時長以注入的假時鐘推進。
"""

from typing import Any

import httpx

from cgb.adapters.errors import AdapterError
from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    T4,
    ColabWorld,
    open_ready,
    ui_client,
    wait_until,
)


# ---------------------------------------------------------------- US1-API-35


async def test_紀錄依開啟時間由新到舊列出_含還沒結束的那一筆(ui_client: httpx.AsyncClient, fakes: Any, fake_clock: Any) -> None:
    # Arrange:第一次使用者結束(運行 120 秒)、第二次開啟失敗、第三次目前就緒
    ColabWorld(fakes)
    await open_ready(ui_client)
    fake_clock.advance(120)
    await ui_client.delete("/api/session")
    await wait_until(ui_client, lambda s: s.get("state") == "ended")
    fake_clock.advance(60)
    fakes.colab.create_session.then(AdapterError("COLAB_ALLOCATION_REFUSED", "Colab 拒絕配置"))
    await ui_client.post("/api/session", json={"runtimeType": T4})
    await wait_until(ui_client, lambda s: s.get("state") == "open_failed")
    fake_clock.advance(60)
    await open_ready(ui_client)

    # Act
    response = await ui_client.get("/api/sessions")

    # Assert
    items = response.json().get("items", [])
    assert len(items) == 3
    opened = [str(item.get("openedAt")) for item in items]
    assert None not in [item.get("openedAt") for item in items] and opened == sorted(opened, reverse=True), opened
    oldest, failed, current = items[2], items[1], items[0]
    assert (oldest.get("endReason"), oldest.get("durationSeconds")) == ("USER_ENDED", 120)
    assert oldest.get("endedAt") is not None
    assert failed.get("endReason") == "OPEN_FAILED"
    assert (current.get("endedAt", "missing"), current.get("runtimeType")) == (None, T4)


# ---------------------------------------------------------------- US1-API-36


async def test_一筆紀錄列出開啟中的每一步與之後的每次狀態變化(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    name = (await open_ready(ui_client))["name"]
    await ui_client.delete("/api/session")
    await wait_until(ui_client, lambda s: s.get("state") == "ended")

    # Act
    response = await ui_client.get(f"/api/sessions/{name}")

    # Assert
    transitions = response.json().get("transitions", []) if response.status_code == 200 else []
    assert [(t.get("state"), t.get("step")) for t in transitions] == [
        ("opening", "allocating"),
        ("opening", "starting_ollama"),
        ("opening", "connecting"),
        ("opening", "verifying"),
        ("ready", None),
        ("ending", None),
        ("ended", None),
    ]
    assert transitions[-1].get("endReason") == "USER_ENDED"
