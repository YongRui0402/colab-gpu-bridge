"""E2 後端 UI API:官方模型庫的搜尋與版本(testplan.md § 4.1,`/api/library` › 搜尋、`/api/library` › 列版本)。

接縫:HTTP `/api/*`,五個轉接層用替身;模型庫的回傳照 `ModelLibrary`(E8)的形狀。
"""

from typing import Any

import httpx

from cgb.db.connection import connect
from cgb.domain.errors import MESSAGES
from integration.test_api_downloads import downloadable, enqueue_waiting, queue, states
from integration.test_api_models import QWEN_7B, QWEN_SMALL, QWEN_SMALL_BYTES, set_loaded, set_tags, tag
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


# ================================================================ 002:模型庫出問題時的代碼與狀態碼(002 testplan.md § 2.2)

# ---------------------------------------------------------------- US1-API-01


async def test_沒有工作階段時搜尋連不到模型庫回_502_本文不帶_model(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.model_library.search_library.raises("LIBRARY_UNREACHABLE", "ConnectError: [Errno -2] Name or service not known")

    # Act
    response = await ui_client.get("/api/library/search", params={"q": "qwen2.5"})

    # Assert
    assert (response.status_code, error_code(response)) == (502, "LIBRARY_UNREACHABLE")
    assert sorted(response.json()) == ["code", "message"]


# ---------------------------------------------------------------- US1-API-02


async def test_搜尋時模型庫暫時發生錯誤回_502_LIBRARY_SERVER_ERROR(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:工作階段就緒
    ColabWorld(fakes)
    await open_ready(ui_client)
    fakes.model_library.search_library.raises("LIBRARY_SERVER_ERROR", "HTTP 503 Service Unavailable")

    # Act
    response = await ui_client.get("/api/library/search", params={"q": "qwen2.5"})

    # Assert
    assert (response.status_code, error_code(response)) == (502, "LIBRARY_SERVER_ERROR")


# ---------------------------------------------------------------- US1-API-03


async def test_按顯示更多時第_2_頁解析不出來回_502_LIBRARY_BAD_RESPONSE(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.model_library.search_library.raises("LIBRARY_BAD_RESPONSE", "no result rows on page 2")

    # Act
    response = await ui_client.get("/api/library/search", params={"q": "qwen2.5", "page": 2})

    # Assert
    assert (response.status_code, error_code(response)) == (502, "LIBRARY_BAD_RESPONSE")


# ---------------------------------------------------------------- US1-API-04


async def test_搜尋時模型庫逾時回_504_LIBRARY_TIMEOUT(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.model_library.search_library.raises("LIBRARY_TIMEOUT", "ReadTimeout: timed out")

    # Act
    response = await ui_client.get("/api/library/search", params={"q": "qwen2.5"})

    # Assert
    assert response.status_code == 504
    assert error_code(response) == "LIBRARY_TIMEOUT"


# ---------------------------------------------------------------- US1-API-05


async def test_找不到符合的模型時搜尋回_200_與空的結果(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.model_library.search_library.returns({"items": [], "hasMore": False})

    # Act
    response = await ui_client.get("/api/library/search", params={"q": "no-such-model-xyz"})
    page = response.json() if response.status_code == 200 else {}

    # Assert
    assert (response.status_code, page.get("items")) == (200, [])
    assert page.get("hasMore") is False


# ---------------------------------------------------------------- US1-API-06


async def test_模型庫沒有這個模型時版本清單回_404_本文不帶_model(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.model_library.list_model_tags.when(name="qwen2.6").raises("LIBRARY_NOT_FOUND", "HTTP 404 Not Found")

    # Act
    response = await ui_client.get("/api/library/models/qwen2.6/tags")

    # Assert
    assert (response.status_code, error_code(response)) == (404, "LIBRARY_NOT_FOUND")
    assert sorted(response.json()) == ["code", "message"]


# ---------------------------------------------------------------- US1-API-07


async def test_版本清單連不到模型庫回_502_LIBRARY_UNREACHABLE(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:工作階段就緒
    ColabWorld(fakes)
    await open_ready(ui_client)
    fakes.model_library.list_model_tags.raises("LIBRARY_UNREACHABLE", "ConnectError: connection refused")

    # Act
    response = await ui_client.get("/api/library/models/qwen2.5/tags")

    # Assert
    assert (response.status_code, error_code(response)) == (502, "LIBRARY_UNREACHABLE")


# ---------------------------------------------------------------- US1-API-08


async def test_版本清單時模型庫暫時發生錯誤回_502_LIBRARY_SERVER_ERROR(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.model_library.list_model_tags.raises("LIBRARY_SERVER_ERROR", "HTTP 500 Internal Server Error")

    # Act
    response = await ui_client.get("/api/library/models/qwen2.5/tags")

    # Assert
    assert (response.status_code, error_code(response)) == (502, "LIBRARY_SERVER_ERROR")


# ---------------------------------------------------------------- US1-API-09


async def test_版本頁解析不出來時版本清單回_502_LIBRARY_BAD_RESPONSE(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.model_library.list_model_tags.raises("LIBRARY_BAD_RESPONSE", "no /library/qwen2.5:<tag> link")

    # Act
    response = await ui_client.get("/api/library/models/qwen2.5/tags")

    # Assert
    assert (response.status_code, error_code(response)) == (502, "LIBRARY_BAD_RESPONSE")


# ---------------------------------------------------------------- US1-API-10


async def test_版本清單時模型庫逾時回_504_LIBRARY_TIMEOUT(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.model_library.list_model_tags.raises("LIBRARY_TIMEOUT", "ReadTimeout: timed out")

    # Act
    response = await ui_client.get("/api/library/models/qwen2.5/tags")

    # Assert
    assert response.status_code == 504
    assert error_code(response) == "LIBRARY_TIMEOUT"


# ---------------------------------------------------------------- US1-API-11


async def test_版本頁部分欄位解析不出來時版本清單照樣列出_缺的欄位是_null(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:工作階段就緒,執行環境上有 qwen2.5:0.5b
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES))
    fakes.model_library.list_model_tags.returns(
        [
            {"tag": "0.5b", "sizeLabel": "398MB", "contextLength": "32K", "cloudOnly": False},
            {"tag": "7b", "sizeLabel": None, "contextLength": None, "cloudOnly": False},
        ]
    )

    # Act
    response = await ui_client.get("/api/library/models/qwen2.5/tags")
    tags = response.json().get("tags", []) if response.status_code == 200 else []
    by_tag = {t["tag"]: t for t in tags}
    seven = by_tag.get("7b", {})

    # Assert
    assert (response.status_code, [t["tag"] for t in tags]) == (200, ["0.5b", "7b"])
    assert seven.get("sizeLabel", "缺") is None
    assert seven.get("contextLength", "缺") is None
    assert (seven.get("fullName"), seven.get("downloaded")) == ("qwen2.5:7b", False)
    assert by_tag.get("0.5b", {}).get("downloaded") is True


# ---------------------------------------------------------------- US1-API-12


async def test_搜尋連不到模型庫時精選清單與下載中的項目不受影響(
    ui_client: httpx.AsyncClient, fakes: Any, db_path: Any
) -> None:
    # Arrange:工作階段就緒;精選清單有 llama3.2:3b;qwen2.5:7b 停在下載中
    downloadable(fakes)
    await open_ready(ui_client)
    conn = connect(db_path)
    conn.execute("INSERT INTO curated_models (name) VALUES ('llama3.2:3b')")
    conn.close()
    hold = await enqueue_waiting(ui_client, fakes, QWEN_7B)
    fakes.model_library.search_library.raises("LIBRARY_UNREACHABLE", "ConnectError")

    # Act
    searched = await ui_client.get("/api/library/search", params={"q": "qwen2.5"})
    curated = await ui_client.get("/api/curated")
    downloads = await queue(ui_client)
    hold.release()

    # Assert
    assert (searched.status_code, error_code(searched)) == (502, "LIBRARY_UNREACHABLE")
    assert (curated.status_code, [item.get("name") for item in curated.json().get("items", [])]) == (200, ["llama3.2:3b"])
    assert states(downloads) == [("qwen2.5:7b", "downloading")]
    assert fakes.remote_ollama.pull_model.call_count == 1


# ---------------------------------------------------------------- US1-API-13


async def test_版本清單失敗之後搜尋照樣對照執行環境標出已下載的版本(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:工作階段就緒,執行環境上有 qwen2.5:0.5b
    ColabWorld(fakes)
    await open_ready(ui_client)
    set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES))
    fakes.model_library.list_model_tags.raises("LIBRARY_SERVER_ERROR", "HTTP 502 Bad Gateway")
    fakes.model_library.search_library.returns(search_page("qwen2.5", has_more=False))

    # Act
    tags = await ui_client.get("/api/library/models/qwen2.5/tags")
    searched = await ui_client.get("/api/library/search", params={"q": "qwen2.5"})
    page = searched.json() if searched.status_code == 200 else {}
    items = page.get("items", [])

    # Assert
    assert (tags.status_code, error_code(tags)) == (502, "LIBRARY_SERVER_ERROR")
    assert (searched.status_code, page.get("runtimeChecked")) == (200, True)
    assert [item.get("downloadedTags") for item in items] == [["0.5b"]]


# ---------------------------------------------------------------- US1-API-14

FALLBACK = "從精選清單挑選或直接輸入名稱"


async def test_搜尋連不到模型庫時說明取自固定訊息表_不帶例外文字或網址(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段;替身帶英文與網址的訊息
    ColabWorld(fakes)
    fakes.model_library.search_library.raises(
        "LIBRARY_UNREACHABLE",
        "httpx.ConnectError: [Errno -3] Temporary failure in name resolution (https://ollama.com/search?q=qwen2.5&c=local)",
    )

    # Act
    response = await ui_client.get("/api/library/search", params={"q": "qwen2.5"})
    message = response.json().get("message", "")

    # Assert
    assert message == MESSAGES["LIBRARY_UNREACHABLE"]
    assert "ConnectError" not in message
    assert "https://" not in message
    assert FALLBACK in message


# ---------------------------------------------------------------- US1-API-15


async def test_版本清單逾時時說明取自固定訊息表_不帶例外文字或網址(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.model_library.list_model_tags.raises(
        "LIBRARY_TIMEOUT", "ReadTimeout: timed out after 10.0s (https://ollama.com/library/qwen2.5/tags)"
    )

    # Act
    response = await ui_client.get("/api/library/models/qwen2.5/tags")
    message = response.json().get("message", "")

    # Assert
    assert message == MESSAGES.get("LIBRARY_TIMEOUT")
    assert FALLBACK in message
    assert "ReadTimeout" not in message
    assert "https://" not in message


# ---------------------------------------------------------------- US1-API-16


async def test_同一個代碼在搜尋與版本清單是同一句說明(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.model_library.search_library.raises("LIBRARY_SERVER_ERROR", "HTTP 502 Bad Gateway")
    fakes.model_library.list_model_tags.raises("LIBRARY_SERVER_ERROR", "HTTP 500 Internal Server Error")

    # Act
    searched = await ui_client.get("/api/library/search", params={"q": "qwen2.5"})
    tags = await ui_client.get("/api/library/models/qwen2.5/tags")

    # Assert
    assert searched.json().get("message") == MESSAGES["LIBRARY_SERVER_ERROR"]
    assert tags.json().get("message") == MESSAGES["LIBRARY_SERVER_ERROR"]


# ---------------------------------------------------------------- US1-API-17


async def test_版本清單找不到模型時說明取自固定訊息表_不帶對方的原文或網址(ui_client: httpx.AsyncClient, fakes: Any) -> None:
    # Arrange:沒有開工作階段
    ColabWorld(fakes)
    fakes.model_library.list_model_tags.raises("LIBRARY_NOT_FOUND", "404 Not Found: https://ollama.com/library/qwen2.6/tags")

    # Act
    response = await ui_client.get("/api/library/models/qwen2.6/tags")
    message = response.json().get("message", "")

    # Assert
    assert message == MESSAGES["LIBRARY_NOT_FOUND"]
    assert "404 Not Found" not in message
    assert "https://" not in message
