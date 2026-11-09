"""解析 ollama.com 搜尋頁與版本頁的 HTML(`contracts/model-library.openapi.yaml` § SearchPage、TagsPage)。

頁面不是正式 API,不引入 HTML 解析套件(techstack.md「自寫取代套件」),只認規格檔寫下的幾個結構。純函式,不碰 I/O。
"""

import re

# 官方模型的連結是 `/library/<名稱>`;社群模型是 `/<使用者>/<名稱>`,這個樣式比對不到(Q9)
_OFFICIAL_MODEL_HREF = re.compile(r'href="/library/([a-z0-9][a-z0-9._-]*)"')


def parse_search_models(page_html: str) -> list[str]:
    """搜尋頁(整頁或片段)上的官方模型名稱,照頁面順序、去重。"""
    return list(dict.fromkeys(_OFFICIAL_MODEL_HREF.findall(page_html)))


# 還有下一頁時,結果末尾有 `hx-get="/search?page=<N+1>&q=<關鍵字>"` 的連結(Q54)
_NEXT_PAGE_LINK = re.compile(r'hx-get="/search\?page=\d+')


def has_next_page(page_html: str) -> bool:
    """頁面末尾有沒有下一頁連結;沒有就是最後一頁(不以筆數推斷,Q54 取代 Q32)。"""
    return _NEXT_PAGE_LINK.search(page_html) is not None


# 版本頁的大小顯示值:`<digest 前 12 碼></span> • 398MB •`(雲端版本沒有大小)
_TAG_SIZE_LABEL = re.compile(r'class="font-mono">[0-9a-f]+</span>\s*•\s*(\d+(?:\.\d+)?[KMGT]B)\s*•')


def parse_model_tags(page_html: str, name: str) -> list[dict[str, object]]:
    """版本頁上的每個版本:名稱、大小顯示值、是否只能在雲端執行。

    同一個版本在頁面上出現兩次(窄螢幕與寬螢幕),只取第一次;大小取該連結到下一個版本連結之間的第一個大小。
    """
    tag_href = re.compile(r'href="/library/' + re.escape(name) + r':([A-Za-z0-9_][A-Za-z0-9._-]*)"')
    matches = list(tag_href.finditer(page_html))
    tags: dict[str, dict[str, object]] = {}
    for index, match in enumerate(matches):
        tag = match.group(1)
        if tag in tags:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(page_html)
        size = _TAG_SIZE_LABEL.search(page_html, match.end(), end)
        tags[tag] = {
            "tag": tag,
            "fullName": f"{name}:{tag}",
            "sizeLabel": size.group(1) if size else None,
            # 只能在雲端執行的版本名稱含 cloud(contracts § TagsPage)
            "cloudOnly": "cloud" in tag,
        }
    return list(tags.values())
