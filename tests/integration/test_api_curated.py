"""E2 後端 UI API:精選清單(testplan.md § 4.1,`/api/curated` › 新增、修改、移除)。

接縫:HTTP `/api/*`,五個轉接層用替身;精選清單存在 SQLite(contracts/store.dbml § Table curated_models)。
"""

from typing import Any

import httpx

from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    ColabWorld,
    error_code,
    ui_client,
)


# ---------------------------------------------------------------- US3-API-24


async def test_沒寫版本視為_latest_同一個模型不存兩筆(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:精選清單是空的
    ColabWorld(fakes)

    # Act
    first = await ui_client.post("/api/curated", json={"name": "qwen2.5:7b", "description": "日常用"})
    second = await ui_client.post("/api/curated", json={"name": "qwen2.5"})
    third = await ui_client.post("/api/curated", json={"name": "qwen2.5:latest"})
    first_id = first.json().get("id") if first.status_code == 201 else 0
    second_id = second.json().get("id") if second.status_code == 201 else 0
    updated = await ui_client.put(f"/api/curated/{first_id}", json={"name": "qwen2.5:7b", "description": "長" * 201})
    removed = await ui_client.delete(f"/api/curated/{second_id}")
    listed = (await ui_client.get("/api/curated")).json()

    # Assert
    assert (first.status_code, second.status_code) == (201, 201)
    assert (third.status_code, error_code(third)) == (409, "CURATED_DUPLICATE")
    assert (updated.status_code, error_code(updated)) == (400, "INVALID_CURATED_DESCRIPTION")
    assert removed.status_code == 204
    assert [item.get("name") for item in listed.get("items", [])] == ["qwen2.5:7b"]
