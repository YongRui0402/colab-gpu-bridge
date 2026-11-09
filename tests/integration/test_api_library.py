"""E2 後端 UI API:官方模型庫的搜尋與版本(testplan.md § 4.1,`/api/library` › 搜尋、`/api/library` › 列版本)。

接縫:HTTP `/api/*`,五個轉接層用替身;模型庫的回傳照 `ModelLibrary`(E8)的形狀。
"""

from typing import Any

import httpx

from integration.test_api_models import QWEN_SMALL, QWEN_SMALL_BYTES, set_loaded, set_tags, tag
from integration.test_api_session import (  # noqa: F401(ui_client 是 fixture)
    ColabWorld,
    error_code,
    open_ready,
    ui_client,
)


def search_page(*names: str, has_more: bool) -> dict[str, Any]:
    """`ModelLibrary.search_library` 的回傳。"""
    return {
        "items": [{"name": n, "description": None, "parameterSizes": [], "capabilities": []} for n in names],
        "hasMore": has_more,
    }


# ---------------------------------------------------------------- US3-API-21


async def test_搜尋結果對照執行環境標出已下載的版本(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES))
    set_loaded(fakes)
    fakes.model_library.search_library.returns(search_page("qwen2.5", "qwen2.5-coder", has_more=True))

    # Act
    response = await ui_client.get("/api/library/search", params={"q": "qwen2.5"})
    page = response.json() if response.status_code == 200 else {}
    items = page.get("items", [])

    # Assert
    assert [item["name"] for item in items] == ["qwen2.5", "qwen2.5-coder"]
    assert items[0].get("downloadedTags") == ["0.5b"]
    assert page.get("hasMore") is True


# ---------------------------------------------------------------- US3-API-22


async def test_版本清單標出已下載與只能在雲端執行的版本(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES))
    set_loaded(fakes)
    fakes.model_library.list_model_tags.returns(
        [
            {"tag": "0.5b", "sizeLabel": "398MB", "contextLength": "32K", "cloudOnly": False},
            {"tag": "7b", "sizeLabel": "4.7GB", "contextLength": "32K", "cloudOnly": False},
            {"tag": "7b-cloud", "sizeLabel": "-", "contextLength": None, "cloudOnly": True},
        ]
    )

    # Act
    response = await ui_client.get("/api/library/models/qwen2.5/tags")
    tags = {t["tag"]: t for t in (response.json().get("tags", []) if response.status_code == 200 else [])}

    # Assert
    assert (tags.get("0.5b", {}).get("sizeLabel"), tags.get("0.5b", {}).get("downloaded")) == ("398MB", True)
    assert tags.get("7b", {}).get("downloaded") is False
    assert tags.get("7b-cloud", {}).get("cloudOnly") is True


# ---------------------------------------------------------------- US3-API-23


async def test_模型庫壞掉時搜尋回_502_精選清單照常(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange
    ColabWorld(fakes)
    fakes.model_library.search_library.raises("LIBRARY_BAD_RESPONSE", "搜尋頁解析不出來")

    # Act
    searched = await ui_client.get("/api/library/search", params={"q": "qwen2.5"})
    curated = await ui_client.get("/api/curated")

    # Assert
    assert (searched.status_code, error_code(searched)) == (502, "LIBRARY_BAD_RESPONSE")
    assert curated.status_code == 200
