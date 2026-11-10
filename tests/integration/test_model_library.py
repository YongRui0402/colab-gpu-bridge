"""E8 Ollama 官方模型庫轉接層(testplan.md § 2.9、§ 4.4;接縫:`ModelLibrary` 的方法,對方是 `httpx.MockTransport`)。

ollama.com 與 registry.ollama.ai 一律由 `tests/fixtures/library/` 存下來的(合成的)頁面與 manifest 代替,不連外網。
"""

from pathlib import Path

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.adapters.model_library import ModelLibrary

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "library"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class Recorder:
    """依路徑與 query 回應,並記下收到的每個請求。"""

    def __init__(self, handler) -> None:
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self._handler(request)

        return httpx.MockTransport(handle)


def html(text: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=text, headers={"Content-Type": "text/html; charset=utf-8"})


# ---------------------------------------------------------------- US3-LIB-01 search_library


def search_pages(request: httpx.Request) -> httpx.Response:
    assert request.url.host == "ollama.com"
    assert request.url.path == "/search"
    if request.url.params.get("page") == "2":
        return html(fixture_text("search-qwen2.5-page2.html"))
    return html(fixture_text("search-qwen2.5-page1.html"))


async def test_搜尋只取官方模型且第_2_頁帶_HX_Request() -> None:
    """US3-LIB-01:搜尋頁有 `/library/qwen2.5`、`/library/qwen2.5-coder`、`/someone/qwen2.5-custom`。"""
    recorder = Recorder(search_pages)
    library = ModelLibrary(transport=recorder.transport())

    first = await library.search_library("qwen2.5")
    second = await library.search_library("qwen2.5", page=2)

    # 則1:社群模型(/<使用者>/<名稱>)不列出(Q9)
    assert [item["name"] for item in first["items"]] == ["qwen2.5", "qwen2.5-coder"]
    assert [item["name"] for item in second["items"]] == ["qwen2.5vl"]
    # 則2:兩次請求都帶 c=local 與同一個 q
    assert len(recorder.requests) == 2
    for request in recorder.requests:
        assert request.url.params.get("c") == "local"
        assert request.url.params.get("q") == "qwen2.5"
    # 則3:第 2 頁帶 page=2 與 HX-Request: true,第 1 頁兩者都沒有
    first_request, second_request = recorder.requests
    assert "page" not in first_request.url.params
    assert "HX-Request" not in first_request.headers
    assert second_request.url.params.get("page") == "2"
    assert second_request.headers.get("HX-Request") == "true"


# ---------------------------------------------------------------- US3-LIB-02 search_library 的 hasMore


async def test_hasMore_看頁尾有沒有下一頁連結() -> None:
    """US3-LIB-02:情況 A 頁尾有 `hx-get="/search?page=2"` 的連結;情況 B 沒有(兩頁的結果筆數相同)。"""
    with_link = ModelLibrary(transport=httpx.MockTransport(lambda _: html(fixture_text("search-qwen2.5-page1.html"))))
    without_link = ModelLibrary(
        transport=httpx.MockTransport(lambda _: html(fixture_text("search-qwen2.5-single-page.html")))
    )

    case_a = await with_link.search_library("qwen2.5")
    case_b = await without_link.search_library("qwen2.5")

    # 則1、則2:兩種情況筆數一樣,只差在有沒有下一頁連結(Q54;不以筆數推斷)
    assert len(case_a["items"]) == len(case_b["items"])
    assert case_a["hasMore"] is True
    assert case_b["hasMore"] is False


# ---------------------------------------------------------------- US3-LIB-03 list_model_tags


async def test_版本清單帶大小顯示值並標出雲端版本() -> None:
    """US3-LIB-03:版本頁有 `0.5b` 398MB、`7b` 4.7GB、`7b-cloud`(每個版本在頁面上出現兩次)。"""
    recorder = Recorder(lambda _: html(fixture_text("tags-qwen2.5.html")))
    library = ModelLibrary(transport=recorder.transport())

    tags = await library.list_model_tags("qwen2.5")

    by_tag = {tag["tag"]: tag for tag in tags}
    assert sorted(by_tag) == ["0.5b", "7b", "7b-cloud"]
    # 則1:大小是頁面上的顯示值
    assert by_tag["0.5b"]["sizeLabel"] == "398MB"
    # 則2、則3:名稱含 cloud 的是雲端專用版本
    assert by_tag["7b-cloud"]["cloudOnly"] is True
    assert by_tag["7b"]["cloudOnly"] is False
    assert str(recorder.requests[0].url) == "https://ollama.com/library/qwen2.5/tags"


async def test_真的版本頁_digest_前後有空白時照樣讀得到大小() -> None:
    """實跑 US3-LIB-05 發現:真的頁面是 `<span class="font-mono">⏎ 845dbda0ea48</span> • 4.7GB •`,
    合成樣本沒有這段空白,正規式比對不到,133 個版本的大小全是 None。樣本取自 2026-11-10 的真頁面。"""
    library = ModelLibrary(transport=httpx.MockTransport(lambda _: html(fixture_text("tags-qwen2.5-live-2026-11.html"))))

    tags = await library.list_model_tags("qwen2.5")

    by_tag = {tag["tag"]: tag["sizeLabel"] for tag in tags}
    assert by_tag == {"latest": "4.7GB", "0.5b": "398MB", "1.5b": "986MB", "3b": "1.9GB"}


# ---------------------------------------------------------------- US3-LIB-04 get_manifest

MANIFEST_TYPE = "application/vnd.docker.distribution.manifest.v2+json"
MANIFEST_UNKNOWN = '{"errors":[{"code":"MANIFEST_UNKNOWN","message":"manifest unknown"}]}'


def registry_reply(response: httpx.Response) -> Recorder:
    return Recorder(lambda _: response)


async def manifest_error_code(response: httpx.Response) -> str:
    library = ModelLibrary(transport=registry_reply(response).transport())
    with pytest.raises(AdapterError) as error:
        await library.get_manifest("qwen2.5", "7b")
    return error.value.code


async def test_manifest_的大小是各層合計且不含_config() -> None:
    """US3-LIB-04 則1:`qwen2.5:7b` 4 層合計 4,683,087,332、`config.size` 487。"""
    recorder = registry_reply(
        httpx.Response(200, text=fixture_text("manifest-qwen2.5-7b.json"), headers={"Content-Type": MANIFEST_TYPE})
    )
    library = ModelLibrary(transport=recorder.transport())

    manifest = await library.get_manifest("qwen2.5", "7b")

    assert manifest["sizeBytes"] == 4683087332
    (request,) = recorder.requests
    assert str(request.url) == "https://registry.ollama.ai/v2/library/qwen2.5/manifests/7b"
    assert request.headers.get("Accept") == MANIFEST_TYPE


async def test_沒有層的_manifest_回_LIBRARY_CLOUD_ONLY() -> None:
    """US3-LIB-04 則2:雲端版本也回 200,但 `layers` 是空陣列、Content-Type 是 text/plain。"""
    response = httpx.Response(
        200, text=fixture_text("manifest-qwen2.5-7b-cloud.json"), headers={"Content-Type": "text/plain; charset=utf-8"}
    )

    assert await manifest_error_code(response) == "LIBRARY_CLOUD_ONLY"


async def test_registry_的失敗依序歸成原因代碼() -> None:
    """US3-LIB-04 則3:registry 情況 A 回 404、B 回 503、C 回 200 的 HTML。"""
    not_found = httpx.Response(404, text=MANIFEST_UNKNOWN, headers={"Content-Type": "text/plain; charset=utf-8"})
    unavailable = httpx.Response(503, text="Service Unavailable")
    not_manifest = html("<!DOCTYPE html><html><body>維護中</body></html>")

    assert await manifest_error_code(not_found) == "LIBRARY_NOT_FOUND"
    assert await manifest_error_code(unavailable) == "LIBRARY_SERVER_ERROR"
    assert await manifest_error_code(not_manifest) == "LIBRARY_BAD_RESPONSE"
