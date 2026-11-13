# 技術堆疊:官方模型庫的錯誤處理

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Date**: 2026-11-13

## 一覽

| 層 | 技術 | 版本 | 用途 | 決策 |
|---|---|---|---|---|
| 後端 | Python | 3.12 | 執行環境,沿用 001 | R1 |
| 後端 | `httpx` | 0.28.1 | 對 ollama.com 與 registry 的 HTTP client;例外階層用來歸類傳輸層失敗,`Timeout(10.0)` 設逾時 | R1、R2 |
| 後端 | `asyncio.timeout` | 不適用 | 每個請求的整體 10 秒期限(標準函式庫) | R2 |
| 後端 | FastAPI | 0.162.2 | UI API;`ApiError` 處理器回錯誤本文,沿用 001 | R4 |
| 測試 | `pytest` | 9.2.0 | 轉接層與 UI API 的參數化錯誤案例 | R5 |
| 測試 | `pytest-asyncio` | 1.4.1.post1 | 非同步案例 | R5 |
| 測試 | `httpx.MockTransport` | 0.28.1 | ollama.com 與 registry 的替身,含丟出傳輸層例外 | R5 |

## 依賴

- 後端 runtime(2 個):`httpx`(R1)、`fastapi`(R4)
- 前端 runtime(0 個):無(R4)
- 開發(2 個):`pytest`(R5)、`pytest-asyncio`(R5)
- 系統套件(apt,0 個):無(R5)

## 新引入與沿用

- 依賴全部沿用 001 的 `pyproject.toml` 與 `uv.lock`,這一輪不新增任何套件(R1)
- 新引入:沒有新的服務或元件(R1)
- 沿用:Ollama 官方模型庫 ollama.com 與 registry.ollama.ai(R3)、001 的 `tests/realrun/test_us3_lib_05.py` 唯讀實跑(R5)

## 自寫取代套件

- 搜尋頁與版本頁的格式判定:兩個條件判斷加一條正規式,約 15 行,放在 001 的 `domain/library_html.py` 旁(R3)
- 傳輸層例外與狀態碼的歸類:`_get` 裡兩個 except 加一個狀態碼函式,約 20 行(R1、R3)

## 刻意不用

- HTML 解析套件(BeautifulSoup、selectolax):001 已決定不引入,兩個結構條件用正規式就夠(R3)
- 重試套件(tenacity、httpx 的 retries):spec 假設失敗時不自動重試(R1)
