"""E8 Ollama 官方模型庫轉接層(testplan.md § 2.9、§ 4.4;接縫:`ModelLibrary` 的方法,對方是 `httpx.MockTransport`)。

ollama.com 與 registry.ollama.ai 一律由 `tests/fixtures/library/` 存下來的(合成的)頁面與 manifest 代替,不連外網。
002 的錯誤處理(specs/002-library-error-handling/testplan.md § 2.1)另用 127.0.0.1 的本機 socket 伺服器。
"""

import re
import socket
import threading
import time
from collections.abc import Awaitable, Callable
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


# ================================================================ 002 錯誤處理(specs/002-library-error-handling/testplan.md § 2.1)


async def raised_by(call: Awaitable[object]) -> BaseException | None:
    """執行呼叫並收下它丟出的例外(沒丟就是 None),讓「原生例外越過轉接層」也是斷言失敗而不是測試錯誤。"""
    try:
        await call
    except Exception as error:
        return error
    return None


async def settled(call: Awaitable[object]) -> object:
    """執行呼叫,回傳它的結果;丟出例外時回傳那個例外,讓「不該丟卻丟了」也是斷言失敗。"""
    try:
        return await call
    except Exception as error:
        return error


def failing_with(error: Exception) -> httpx.MockTransport:
    """對任何請求都丟出 `error` 的 MockTransport(代表傳輸層失敗)。"""

    def handle(request: httpx.Request) -> httpx.Response:
        raise error

    return httpx.MockTransport(handle)


# ---------------------------------------------------------------- US1-LIB-01 search_library 連不到


async def test_連不到_ollama_com_時搜尋回_LIBRARY_UNREACHABLE_且不帶底層細節() -> None:
    """US1-LIB-01:handler 丟 `httpx.ConnectError("cgb-test-底層細節 ollama.com")`(代表 DNS 失敗)。"""
    library = ModelLibrary(transport=failing_with(httpx.ConnectError("cgb-test-底層細節 ollama.com")))

    error = await raised_by(library.search_library("qwen2.5"))

    # 則1:丟出 LIBRARY_UNREACHABLE 的 AdapterError
    assert isinstance(error, AdapterError), f"預期 AdapterError,實際 {error!r}"
    assert error.code == "LIBRARY_UNREACHABLE"
    # 則2:`from None`,不留原本的例外鏈
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    # 則3:message 不帶原例外的文字或網址
    assert "cgb-test-底層細節" not in error.message
    assert "ollama.com" not in error.message


# ---------------------------------------------------------------- US1-LIB-02 search_library 讀到一半中斷


async def test_讀回應到一半中斷時搜尋回_LIBRARY_UNREACHABLE() -> None:
    """US1-LIB-02:情況 A 丟 `httpx.RemoteProtocolError`(讀回應到一半連線中斷),情況 B 丟 `httpx.ReadError`。"""
    protocol_broken = ModelLibrary(transport=failing_with(httpx.RemoteProtocolError("cgb-test 中斷")))
    read_broken = ModelLibrary(transport=failing_with(httpx.ReadError("cgb-test 中斷")))

    case_a = await raised_by(protocol_broken.search_library("qwen2.5"))
    case_b = await raised_by(read_broken.search_library("qwen2.5"))

    # 則1、則2:兩種中斷都歸成連不到
    assert isinstance(case_a, AdapterError), f"情況 A 預期 AdapterError,實際 {case_a!r}"
    assert case_a.code == "LIBRARY_UNREACHABLE"
    assert isinstance(case_b, AdapterError), f"情況 B 預期 AdapterError,實際 {case_b!r}"
    assert case_b.code == "LIBRARY_UNREACHABLE"


# ---------------------------------------------------------------- US1-LIB-03 search_library 逾時


async def test_讀取或連線逾時時搜尋回_LIBRARY_TIMEOUT() -> None:
    """US1-LIB-03:情況 A 丟 `httpx.ReadTimeout`,情況 B 丟 `httpx.ConnectTimeout`。"""
    read_timeout = ModelLibrary(transport=failing_with(httpx.ReadTimeout("cgb-test 逾時")))
    connect_timeout = ModelLibrary(transport=failing_with(httpx.ConnectTimeout("cgb-test 逾時")))

    case_a = await raised_by(read_timeout.search_library("qwen2.5"))
    case_b = await raised_by(connect_timeout.search_library("qwen2.5"))

    # 則1、則2:兩種逾時都歸成逾時,不是連不到
    assert isinstance(case_a, AdapterError), f"情況 A 預期 AdapterError,實際 {case_a!r}"
    assert case_a.code == "LIBRARY_TIMEOUT"
    assert isinstance(case_b, AdapterError), f"情況 B 預期 AdapterError,實際 {case_b!r}"
    assert case_b.code == "LIBRARY_TIMEOUT"


# ---------------------------------------------------------------- US1-LIB-04 search_library 回 5xx


def replying(response: httpx.Response) -> ModelLibrary:
    """對任何請求都回同一個回應的 ModelLibrary。"""
    return ModelLibrary(transport=httpx.MockTransport(lambda _: response))


async def test_ollama_com_回_5xx_時搜尋回_LIBRARY_SERVER_ERROR() -> None:
    """US1-LIB-04:情況 A 500、B 503、C 599,本文都是存下來的 `search-qwen2.5-page1.html`。"""
    page1 = fixture_text("search-qwen2.5-page1.html")

    case_a = await raised_by(replying(html(page1, status=500)).search_library("qwen2.5"))
    case_b = await raised_by(replying(html(page1, status=503)).search_library("qwen2.5"))
    case_c = await raised_by(replying(html(page1, status=599)).search_library("qwen2.5"))

    # 則1~則3:不看本文,5xx 一律是伺服器錯誤
    assert isinstance(case_a, AdapterError), f"情況 A 預期 AdapterError,實際 {case_a!r}"
    assert case_a.code == "LIBRARY_SERVER_ERROR"
    assert isinstance(case_b, AdapterError), f"情況 B 預期 AdapterError,實際 {case_b!r}"
    assert case_b.code == "LIBRARY_SERVER_ERROR"
    assert isinstance(case_c, AdapterError), f"情況 C 預期 AdapterError,實際 {case_c!r}"
    assert case_c.code == "LIBRARY_SERVER_ERROR"


# ---------------------------------------------------------------- US1-LIB-05 search_library 回其他非 200


async def test_搜尋遇到_404_或_429_時回_LIBRARY_BAD_RESPONSE() -> None:
    """US1-LIB-05:情況 A 404、情況 B 429,本文都是 `search-qwen2.5-page1.html`(搜尋頁沒有 404 的合約回應)。"""
    page1 = fixture_text("search-qwen2.5-page1.html")

    case_a = await raised_by(replying(html(page1, status=404)).search_library("qwen2.5"))
    case_b = await raised_by(replying(html(page1, status=429)).search_library("qwen2.5"))

    # 則1、則2:都是非預期的狀態碼,不是 LIBRARY_NOT_FOUND,也不照常解析本文
    assert isinstance(case_a, AdapterError), f"情況 A 預期 AdapterError,實際 {case_a!r}"
    assert case_a.code == "LIBRARY_BAD_RESPONSE"
    assert isinstance(case_b, AdapterError), f"情況 B 預期 AdapterError,實際 {case_b!r}"
    assert case_b.code == "LIBRARY_BAD_RESPONSE"


# ---------------------------------------------------------------- US1-LIB-06 search_library 第 2 頁回 303


async def test_搜尋第_2_頁被導向時回_LIBRARY_BAD_RESPONSE_且不跟著導向() -> None:
    """US1-LIB-06:帶 `page=2` 的請求回 303、`Location: /search?q=qwen2.5`;不帶 `page` 的請求回第 1 頁。"""

    def redirect_page2(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(303, headers={"Location": "/search?q=qwen2.5"})
        return html(fixture_text("search-qwen2.5-page1.html"))

    recorder = Recorder(redirect_page2)
    library = ModelLibrary(transport=recorder.transport())

    error = await raised_by(library.search_library("qwen2.5", page=2))

    # 則1:導向是非預期的回應,不把第 1 頁當成第 2 頁
    assert isinstance(error, AdapterError), f"預期 AdapterError,實際 {error!r}"
    assert error.code == "LIBRARY_BAD_RESPONSE"
    # 則2:沒有跟著導向
    assert len(recorder.requests) == 1


# ---------------------------------------------------------------- US1-LIB-07 search_library 第 1 頁改版

MAINTENANCE_PAGE = "<!DOCTYPE html><html><body>維護中</body></html>"


async def test_搜尋第_1_頁沒有結果區塊時回_LIBRARY_BAD_RESPONSE() -> None:
    """US1-LIB-07:情況 A 是維護中頁面;情況 B 是改版頁,結果在 `<div id="results">`,沒有 `id="searchresults"`。"""
    redesigned = (
        '<!DOCTYPE html><html><body><div id="results">'
        '<a href="/library/qwen2.5" class="card">qwen2.5</a>'
        "</div></body></html>"
    )

    case_a = await raised_by(replying(html(MAINTENANCE_PAGE)).search_library("qwen2.5"))
    case_b = await raised_by(replying(html(redesigned)).search_library("qwen2.5"))

    # 則1、則2:找不到結果區塊就是格式不符,不是「沒有符合的模型」,也不因為解析得出名稱就照常回傳
    assert isinstance(case_a, AdapterError), f"情況 A 預期 AdapterError,實際 {case_a!r}"
    assert case_a.code == "LIBRARY_BAD_RESPONSE"
    assert isinstance(case_b, AdapterError), f"情況 B 預期 AdapterError,實際 {case_b!r}"
    assert case_b.code == "LIBRARY_BAD_RESPONSE"


# ---------------------------------------------------------------- US1-LIB-08 search_library 第 2 頁改版


async def test_搜尋第_2_頁不是空白也沒有任何結果時回_LIBRARY_BAD_RESPONSE() -> None:
    """US1-LIB-08:第 2 頁回 200 的片段 `<div class="notice"><p>Something went wrong</p></div>`。"""
    library = replying(html('<div class="notice"><p>Something went wrong</p></div>'))

    error = await raised_by(library.search_library("qwen2.5", page=2))

    # 則1:不是「超過最後一頁」,是格式不符
    assert isinstance(error, AdapterError), f"預期 AdapterError,實際 {error!r}"
    assert error.code == "LIBRARY_BAD_RESPONSE"


# ---------------------------------------------------------------- US1-LIB-09 search_library 0 筆的第 1 頁


def empty_search_page() -> str:
    """把 `search-qwen2.5-page1.html` 的 `<li>` 與下一頁連結全部刪掉,保留空的 `<ul role="list" id="searchresults">`(plan.md Q9 合成頁面)。"""
    page = re.sub(r"<li\b.*?</li>", "", fixture_text("search-qwen2.5-page1.html"), flags=re.DOTALL)
    return re.sub(r'<div hx-get="/search\?page=[^"]*"[^>]*></div>', "", page)


async def test_沒有符合的模型時搜尋回空的_items() -> None:
    """US1-LIB-09:第 1 頁只剩空的結果區塊。"""
    library = replying(html(empty_search_page()))

    result = await settled(library.search_library("zzzz-no-such-model"))

    # 則1、則2:0 筆是正常結果,不是錯誤
    assert isinstance(result, dict), f"預期正常結果,實際 {result!r}"
    assert result["items"] == []
    assert result["hasMore"] is False


# ---------------------------------------------------------------- US1-LIB-10 search_library 超過最後一頁


async def test_頁碼超過最後一頁時搜尋回空的_items() -> None:
    """US1-LIB-10:第 2 頁起回 200,本文只有 5 個換行。"""
    library = replying(html("\n\n\n\n\n"))

    result = await settled(library.search_library("qwen2.5", page=34))

    # 則1、則2:超過最後一頁是正常的 0 筆
    assert isinstance(result, dict), f"預期正常結果,實際 {result!r}"
    assert result["items"] == []
    assert result["hasMore"] is False


# ---------------------------------------------------------------- US1-LIB-11 search_library 第 2 頁只有社群模型


async def test_搜尋第_2_頁只有社群模型時回空的_items() -> None:
    """US1-LIB-11:第 2 頁的片段只有一筆社群模型(plan.md Q9 合成頁面)。"""
    community_only = (
        '<li x-test-model class="flex items-baseline border-b border-neutral-200 py-6">\n'
        '  <a href="/someone/qwen2.5-custom" class="group grid w-full">someone/qwen2.5-custom</a>\n'
        "</li>\n"
    )
    library = replying(html(community_only))

    result = await settled(library.search_library("qwen2.5", page=2))

    # 則1:沒有丟出例外,0 筆官方模型
    assert isinstance(result, dict), f"預期正常結果,實際 {result!r}"
    assert result["items"] == []


# ---------------------------------------------------------------- US1-LIB-12 search_library 正常的第 2 頁片段


async def test_搜尋第_2_頁的片段沒有結果區塊也照常列出官方模型() -> None:
    """US1-LIB-12:第 2 頁回存下來的片段 `search-qwen2.5-page2.html`(沒有 `id="searchresults"`)。"""
    library = replying(html(fixture_text("search-qwen2.5-page2.html")))

    result = await settled(library.search_library("qwen2.5", page=2))

    # 則1:片段本來就沒有結果區塊(合約 SearchPageFragment)
    assert isinstance(result, dict), f"預期正常結果,實際 {result!r}"
    assert [item["name"] for item in result["items"]] == ["qwen2.5vl"]


# ---------------------------------------------------------------- US1-LIB-13 list_model_tags 沒有這個模型


async def test_沒有這個模型時版本清單回_LIBRARY_NOT_FOUND() -> None:
    """US1-LIB-13:版本頁回 404,本文是 `<html><body>404 Not Found</body></html>`。"""
    library = replying(html("<html><body>404 Not Found</body></html>", status=404))

    error = await raised_by(library.list_model_tags("no-such-model-zzz"))

    # 則1:不是空的版本清單
    assert isinstance(error, AdapterError), f"預期 AdapterError,實際 {error!r}"
    assert error.code == "LIBRARY_NOT_FOUND"


# ---------------------------------------------------------------- US1-LIB-14 list_model_tags 回 5xx


async def test_ollama_com_回_5xx_時版本清單回_LIBRARY_SERVER_ERROR() -> None:
    """US1-LIB-14:情況 A 502、情況 B 503,本文都是 `tags-qwen2.5.html`。"""
    tags_page = fixture_text("tags-qwen2.5.html")

    case_a = await raised_by(replying(html(tags_page, status=502)).list_model_tags("qwen2.5"))
    case_b = await raised_by(replying(html(tags_page, status=503)).list_model_tags("qwen2.5"))

    # 則1、則2:不看本文,5xx 一律是伺服器錯誤
    assert isinstance(case_a, AdapterError), f"情況 A 預期 AdapterError,實際 {case_a!r}"
    assert case_a.code == "LIBRARY_SERVER_ERROR"
    assert isinstance(case_b, AdapterError), f"情況 B 預期 AdapterError,實際 {case_b!r}"
    assert case_b.code == "LIBRARY_SERVER_ERROR"


# ---------------------------------------------------------------- US1-LIB-15 list_model_tags 被導向或回 403


async def test_版本頁被導向或回_403_時版本清單回_LIBRARY_BAD_RESPONSE() -> None:
    """US1-LIB-15:情況 A `/library/qwen2.5/tags` 回 301 導向 `/library/qwen2.5`(它回版本頁);情況 B 回 403、本文是版本頁。"""
    tags_page = fixture_text("tags-qwen2.5.html")

    def redirect_tags(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/library/qwen2.5/tags":
            return httpx.Response(301, headers={"Location": "/library/qwen2.5"})
        return html(tags_page)

    recorder = Recorder(redirect_tags)

    case_a = await raised_by(ModelLibrary(transport=recorder.transport()).list_model_tags("qwen2.5"))
    case_b = await raised_by(replying(html(tags_page, status=403)).list_model_tags("qwen2.5"))

    # 則1、則2:導向是非預期的回應,沒有跟著導向
    assert isinstance(case_a, AdapterError), f"情況 A 預期 AdapterError,實際 {case_a!r}"
    assert case_a.code == "LIBRARY_BAD_RESPONSE"
    assert len(recorder.requests) == 1
    # 則3:403 也是非預期的狀態碼,不照常解析本文
    assert isinstance(case_b, AdapterError), f"情況 B 預期 AdapterError,實際 {case_b!r}"
    assert case_b.code == "LIBRARY_BAD_RESPONSE"


# ---------------------------------------------------------------- US1-LIB-16 list_model_tags 版本頁改版


async def test_版本頁沒有任何版本連結時回_LIBRARY_BAD_RESPONSE() -> None:
    """US1-LIB-16:情況 A 是維護中頁面;情況 B 是改版頁,版本連結變成 `/library/qwen2.5/tags/7b`,另有兩個別的 `/library/` 連結。"""
    redesigned = (
        "<!DOCTYPE html><html><body>"
        '<a href="/library/qwen2.5">qwen2.5</a>'
        '<a href="/library/qwen2.5/tags/7b">7b</a>'
        '<a href="/library/llama3:8b">llama3:8b</a>'
        "</body></html>"
    )

    case_a = await raised_by(replying(html(MAINTENANCE_PAGE)).list_model_tags("qwen2.5"))
    case_b = await raised_by(replying(html(redesigned)).list_model_tags("qwen2.5"))

    # 則1、則2:不是「沒有版本」,是格式不符
    assert isinstance(case_a, AdapterError), f"情況 A 預期 AdapterError,實際 {case_a!r}"
    assert case_a.code == "LIBRARY_BAD_RESPONSE"
    assert isinstance(case_b, AdapterError), f"情況 B 預期 AdapterError,實際 {case_b!r}"
    assert case_b.code == "LIBRARY_BAD_RESPONSE"


# ---------------------------------------------------------------- US1-LIB-17 list_model_tags 部分版本沒有大小


async def test_有版本解析不出大小時照常列出且大小留空() -> None:
    """US1-LIB-17:`tags-qwen2.5.html` 的 `0.5b` 398MB、`7b` 4.7GB,`7b-cloud` 那一行沒有大小。"""
    library = replying(html(fixture_text("tags-qwen2.5.html")))

    tags = await settled(library.list_model_tags("qwen2.5"))

    # 則1:沒有丟出例外,三個版本照頁面順序列出
    assert isinstance(tags, list), f"預期版本清單,實際 {tags!r}"
    assert [tag["tag"] for tag in tags] == ["0.5b", "7b", "7b-cloud"]
    # 則2:解析不出的大小留 None,不丟掉這個版本
    assert tags[2]["sizeLabel"] is None


# ---------------------------------------------------------------- 127.0.0.1 本機 socket 伺服器(plan.md Q15;T087 也匯入)

# 處理一個連線:`connection` 是接受下來的 socket,`stopped` 在伺服器關閉時設定(等待中的處理要看它結束)
ConnectionHandler = Callable[[socket.socket, threading.Event], None]


class LocalSocketServer:
    """綁在 127.0.0.1 隨機 port 的本機 socket 伺服器,用來製造 MockTransport 做不出來的真實失敗。

    在背景執行緒接受連線、每個連線一個執行緒,不依賴任何 event loop(行程內的 uvicorn 也能用);
    `with` 結束時關閉所有連線並等執行緒結束,不留下殭屍執行緒。
    """

    def __init__(self, handler: ConnectionHandler) -> None:
        self._handler = handler
        self._stopped = threading.Event()
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(0.05)
        self.port: int = self._listener.getsockname()[1]
        self._threads: list[threading.Thread] = []
        self._connections: list[socket.socket] = []
        self._accepting = threading.Thread(target=self._accept_loop, daemon=True)

    def url(self, scheme: str = "http") -> str:
        return f"{scheme}://127.0.0.1:{self.port}"

    def __enter__(self) -> "LocalSocketServer":
        self._accepting.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stopped.set()
        self._accepting.join(timeout=5)
        self._listener.close()
        for connection in self._connections:
            connection.close()
        for thread in self._threads:
            thread.join(timeout=5)

    def _accept_loop(self) -> None:
        while not self._stopped.is_set():
            try:
                connection, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            self._connections.append(connection)
            thread = threading.Thread(target=self._serve, args=(connection,), daemon=True)
            self._threads.append(thread)
            thread.start()

    def _serve(self, connection: socket.socket) -> None:
        try:
            self._handler(connection, self._stopped)
        except OSError:
            pass  # 對方先斷線或伺服器關閉時的讀寫錯誤,不影響測試
        finally:
            connection.close()


def read_request_head(connection: socket.socket) -> bytes:
    """讀到請求標頭結束(空行)或對方不再送;回傳讀到的位元組。"""
    received = b""
    while b"\r\n\r\n" not in received:
        chunk = connection.recv(4096)
        if not chunk:
            break
        received += chunk
    return received


def plain_http_reply(connection: socket.socket, stopped: threading.Event) -> None:
    """只會講純 HTTP:不管收到什麼(包括 TLS 的 ClientHello)都回一個 HTTP 回應。"""
    connection.recv(4096)
    connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")


def truncated_reply(connection: socket.socket, stopped: threading.Event) -> None:
    """送出 `Content-Length: 2000` 的 200 標頭與 100 bytes 本文,接著關閉連線(讀到一半斷線)。"""
    read_request_head(connection)
    connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 2000\r\n\r\n" + b"x" * 100)


def never_reply(connection: socket.socket, stopped: threading.Event) -> None:
    """接受連線、收下請求後一直不回,直到伺服器關閉。"""
    read_request_head(connection)
    stopped.wait()


def slow_body(*, interval: float, length: int) -> ConnectionHandler:
    """立刻送出 200 的標頭與 `Content-Length: <length>`,本文每 `interval` 秒送 1 byte。"""

    def handle(connection: socket.socket, stopped: threading.Event) -> None:
        read_request_head(connection)
        connection.sendall(f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {length}\r\n\r\n".encode())
        for _ in range(length):
            if stopped.wait(interval):
                return
            connection.sendall(b"x")

    return handle


def delayed_reply(*, delay: float, body_for: Callable[[str], str]) -> ConnectionHandler:
    """每個請求等 `delay` 秒才送出完整的 200 回應;本文由 `body_for(<請求行的目標,如 /search?q=...>)` 決定。"""

    def handle(connection: socket.socket, stopped: threading.Event) -> None:
        request_line = read_request_head(connection).split(b"\r\n", 1)[0].decode()
        if stopped.wait(delay):
            return
        body = body_for(request_line.split(" ")[1]).encode()
        head = f"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(body)}\r\n\r\n"
        connection.sendall(head.encode() + body)

    return handle


def closed_port() -> int:
    """一個剛才綁過、已經關閉的 127.0.0.1 port(連上去會被拒)。"""
    with socket.create_server(("127.0.0.1", 0)) as probe:
        return probe.getsockname()[1]


# ---------------------------------------------------------------- US1-LIB-18 list_model_tags 真的連線被拒與 TLS 失敗


async def test_真的連線被拒或_TLS_交握失敗時版本清單回_LIBRARY_UNREACHABLE() -> None:
    """US1-LIB-18:不用 MockTransport;情況 A 連到已關閉的 port,情況 B 用 https 連只會講純 HTTP 的本機 socket 伺服器。"""
    refused = ModelLibrary(ollama_base_url=f"http://127.0.0.1:{closed_port()}")
    with LocalSocketServer(plain_http_reply) as plain_http:
        tls_mismatch = ModelLibrary(ollama_base_url=plain_http.url("https"))

        case_a = await raised_by(refused.list_model_tags("qwen2.5"))
        case_b = await raised_by(tls_mismatch.list_model_tags("qwen2.5"))

    # 則1、則2:真的 httpx 丟的 ConnectError 也歸成連不到
    assert isinstance(case_a, AdapterError), f"情況 A 預期 AdapterError,實際 {case_a!r}"
    assert case_a.code == "LIBRARY_UNREACHABLE"
    assert isinstance(case_b, AdapterError), f"情況 B 預期 AdapterError,實際 {case_b!r}"
    assert case_b.code == "LIBRARY_UNREACHABLE"
    # 則3:不留底層 ssl.SSLError 的例外鏈
    assert case_b.__cause__ is None
    assert case_b.__suppress_context__ is True


# ---------------------------------------------------------------- US1-LIB-19 list_model_tags 真的讀到一半斷線


async def test_真的讀到一半斷線時版本清單回_LIBRARY_UNREACHABLE() -> None:
    """US1-LIB-19:本機 socket 伺服器送出 `Content-Length: 2000` 的標頭與 100 bytes 本文後關閉連線。"""
    with LocalSocketServer(truncated_reply) as server:
        library = ModelLibrary(ollama_base_url=server.url())

        error = await raised_by(library.list_model_tags("qwen2.5"))

    # 則1:讀到一半中斷是連不到,不是逾時
    assert isinstance(error, AdapterError), f"預期 AdapterError,實際 {error!r}"
    assert error.code == "LIBRARY_UNREACHABLE"


# ---------------------------------------------------------------- US1-LIB-20 list_model_tags 逾時


async def test_讀取或連線逾時時版本清單回_LIBRARY_TIMEOUT() -> None:
    """US1-LIB-20:情況 A 丟 `httpx.ReadTimeout`,情況 B 丟 `httpx.ConnectTimeout`。"""
    read_timeout = ModelLibrary(transport=failing_with(httpx.ReadTimeout("cgb-test 逾時")))
    connect_timeout = ModelLibrary(transport=failing_with(httpx.ConnectTimeout("cgb-test 逾時")))

    case_a = await raised_by(read_timeout.list_model_tags("qwen2.5"))
    case_b = await raised_by(connect_timeout.list_model_tags("qwen2.5"))

    # 則1、則2:兩種逾時都歸成逾時,不是連不到
    assert isinstance(case_a, AdapterError), f"情況 A 預期 AdapterError,實際 {case_a!r}"
    assert case_a.code == "LIBRARY_TIMEOUT"
    assert isinstance(case_b, AdapterError), f"情況 B 預期 AdapterError,實際 {case_b!r}"
    assert case_b.code == "LIBRARY_TIMEOUT"


# ---------------------------------------------------------------- US1-LIB-21 search_library 每個請求的逾時

SHORT_TIMEOUT = 0.5  # 縮短的逾時(plan.md Q7)
TIMING_UPPER_BOUND = 0.8  # 計時案例的上界(plan.md Q8)


async def timed(call: Awaitable[object]) -> tuple[BaseException | None, float]:
    """執行呼叫,回傳它丟出的例外與從呼叫到結束的秒數。"""
    started = time.monotonic()
    error = await raised_by(call)
    return error, time.monotonic() - started


async def test_對方一直不回時搜尋在縮短的逾時內回_LIBRARY_TIMEOUT() -> None:
    """US1-LIB-21:本機 socket 伺服器接受連線後一直不回;`request_timeout=0.5`。"""
    with LocalSocketServer(never_reply) as server:
        library = ModelLibrary(ollama_base_url=server.url(), request_timeout=SHORT_TIMEOUT)

        error, elapsed = await timed(library.search_library("qwen2.5"))

    # 則1:逾時
    assert isinstance(error, AdapterError), f"預期 AdapterError,實際 {error!r}"
    assert error.code == "LIBRARY_TIMEOUT"
    # 則2:照建構參數的秒數逾時
    assert 0.5 <= elapsed <= TIMING_UPPER_BOUND, f"從呼叫到丟出 {elapsed:.2f} 秒"


# ---------------------------------------------------------------- US1-LIB-22 list_model_tags 每個請求的逾時


async def test_對方一直不回時版本清單在縮短的逾時內回_LIBRARY_TIMEOUT() -> None:
    """US1-LIB-22:本機 socket 伺服器接受連線後一直不回;`request_timeout=0.5`。"""
    with LocalSocketServer(never_reply) as server:
        library = ModelLibrary(ollama_base_url=server.url(), request_timeout=SHORT_TIMEOUT)

        error, elapsed = await timed(library.list_model_tags("qwen2.5"))

    # 則1:逾時
    assert isinstance(error, AdapterError), f"預期 AdapterError,實際 {error!r}"
    assert error.code == "LIBRARY_TIMEOUT"
    # 則2:照建構參數的秒數逾時
    assert 0.5 <= elapsed <= TIMING_UPPER_BOUND, f"從呼叫到丟出 {elapsed:.2f} 秒"


# ---------------------------------------------------------------- US1-LIB-23 search_library 整體期限


async def test_對方慢慢送資料時搜尋在縮短的期限內回_LIBRARY_TIMEOUT() -> None:
    """US1-LIB-23:本機 socket 伺服器立刻送出 `Content-Length: 40` 的標頭,本文每 0.2 秒送 1 byte(送完要 8 秒)。"""
    with LocalSocketServer(slow_body(interval=0.2, length=40)) as server:
        library = ModelLibrary(ollama_base_url=server.url(), request_timeout=SHORT_TIMEOUT)

        error, elapsed = await timed(library.search_library("qwen2.5"))

    # 則1:整個請求超過期限就是逾時
    assert isinstance(error, AdapterError), f"預期 AdapterError,實際 {error!r}"
    assert error.code == "LIBRARY_TIMEOUT"
    # 則2:期限是整個請求,不是每次讀取
    assert 0.5 <= elapsed <= TIMING_UPPER_BOUND, f"從呼叫到丟出 {elapsed:.2f} 秒"


# ---------------------------------------------------------------- US1-LIB-24 list_model_tags 整體期限


async def test_對方慢慢送資料時版本清單在縮短的期限內回_LIBRARY_TIMEOUT() -> None:
    """US1-LIB-24:本機 socket 伺服器立刻送出 `Content-Length: 40` 的標頭,本文每 0.2 秒送 1 byte。"""
    with LocalSocketServer(slow_body(interval=0.2, length=40)) as server:
        library = ModelLibrary(ollama_base_url=server.url(), request_timeout=SHORT_TIMEOUT)

        error, elapsed = await timed(library.list_model_tags("qwen2.5"))

    # 則1:整個請求超過期限就是逾時
    assert isinstance(error, AdapterError), f"預期 AdapterError,實際 {error!r}"
    assert error.code == "LIBRARY_TIMEOUT"
    # 則2:期限是整個請求,不是每次讀取
    assert 0.5 <= elapsed <= TIMING_UPPER_BOUND, f"從呼叫到丟出 {elapsed:.2f} 秒"


# ---------------------------------------------------------------- US1-LIB-25 search_library 預設逾時 10 秒


async def test_沒指定逾時時搜尋在_10_秒逾時() -> None:
    """US1-LIB-25:本機 socket 伺服器接受連線後一直不回;不帶 `request_timeout`(plan.md Q7:預設 10 秒只由這個案例驗)。"""
    with LocalSocketServer(never_reply) as server:
        library = ModelLibrary(ollama_base_url=server.url())

        error, elapsed = await timed(library.search_library("qwen2.5"))

    # 則1:逾時
    assert isinstance(error, AdapterError), f"預期 AdapterError,實際 {error!r}"
    assert error.code == "LIBRARY_TIMEOUT"
    # 則2:預設是 10 秒(spec NFR-001)
    assert 10.0 <= elapsed <= 10.8, f"從呼叫到丟出 {elapsed:.2f} 秒"


# ---------------------------------------------------------------- US1-LIB-26 search_library 逾時每個請求各自計算


def search_page_for(target: str) -> str:
    """不帶 `page` 回第 1 頁,帶 `page=2` 回第 2 頁的片段。"""
    if "page=2" in target:
        return fixture_text("search-qwen2.5-page2.html")
    return fixture_text("search-qwen2.5-page1.html")


async def test_顯示更多時每一頁的逾時各自計算() -> None:
    """US1-LIB-26:本機 socket 伺服器每個請求等 0.3 秒才回;同一個 `ModelLibrary(request_timeout=0.5)` 依序讀兩頁(合計約 0.6 秒)。"""
    with LocalSocketServer(delayed_reply(delay=0.3, body_for=search_page_for)) as server:
        library = ModelLibrary(ollama_base_url=server.url(), request_timeout=SHORT_TIMEOUT)

        first = await settled(library.search_library("qwen2.5"))
        second = await settled(library.search_library("qwen2.5", page=2))

    # 則1:第 1 頁照常回傳
    assert isinstance(first, dict), f"第 1 頁預期正常結果,實際 {first!r}"
    assert [item["name"] for item in first["items"]] == ["qwen2.5", "qwen2.5-coder"]
    # 則2:第 2 頁不因為兩頁累計超過 0.5 秒而逾時
    assert isinstance(second, dict), f"第 2 頁預期正常結果,實際 {second!r}"
    assert [item["name"] for item in second["items"]] == ["qwen2.5vl"]
