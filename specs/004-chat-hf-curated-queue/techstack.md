# 技術堆疊:佇列隨工作階段清空、測試對話框、Hugging Face 模型來源與可編輯的精選清單

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Date**: 2026-11-14

## 一覽

| 層 | 技術 | 版本 | 用途 | 決策 |
|---|---|---|---|---|
| 後端 | Python | 3.12 | 執行環境,沿用 001~003 | R1 |
| 後端 | FastAPI | 0.162.2 | UI API;新增對話轉送、Hugging Face 搜尋與展開、自動下載結果的路由 | R2、R5、R6 |
| 後端 | `httpx` | 0.28.1 | 呼叫 huggingface.co 的搜尋、tree 與 manifest;串流轉送 `/api/chat` | R2、R3、R5 |
| 後端 | `SessionsRepo.listeners` | 不適用 | 工作階段進入結束類狀態時清佇列,沿用 001 的掛法 | R1 |
| 後端 | `ollama_compat/forward.py` 的 `_relay` | 不適用 | 對話頁的 NDJSON 串流轉送與中斷補行,沿用 001 | R5 |
| 領域 | Hugging Face Hub 公開 API | 不適用(線上服務,2026-11-14 實測) | `/api/models` 搜尋、`/api/models/<repo>/tree/main` 檔案清單、`/v2/<repo>/manifests/<量化>` 驗證與大小 | R2、R3、R4 |
| 領域 | Ollama(遠端) | 安裝時取最新(本機實測 0.32.15,001 遠端實測 0.40.15) | 拉取 `hf.co/` 模型、`/api/chat` 串流對話 | R4、R5 |
| 前端 | 原生 HTML / CSS / JS | 不適用 | 對話頁、精選清單編輯、Hugging Face 搜尋區、自動下載提示區 | R5、R6 |
| 前端 | `fetch` + `ReadableStream` + `AbortController` | 不適用 | 逐段讀對話回覆、按「停止」斷開 | R5 |
| 資料 | SQLite(`sqlite3` 標準函式庫) | 不適用(桌機實測 3.53.1) | `PRAGMA user_version` 遷移、`download_jobs.session_name`、`curated_models.auto_download`、`auto_download_results` | R1、R6、R7 |
| 測試 | `pytest` | 9.2.0 | 驗收情境的整合測試 | R1 |
| 測試 | `pytest-asyncio` | 1.4.1.post1 | 非同步案例 | R1 |
| 測試 | `tests/fakes` 的替身與 `httpx.MockTransport` | 0.28.1 | 遠端 Ollama、`colab`、Hugging Face 的替身 | R1、R3、R5 |

## 依賴

- 後端 runtime(2 個):`fastapi`(R5)、`httpx`(R2)
- 前端 runtime(0 個):無(R5)
- 開發(2 個):`pytest`(R1)、`pytest-asyncio`(R1)
- 系統套件(apt,0 個):無(R7)

## 新引入與沿用

- 新引入:Hugging Face Hub 的公開 API 與對應的轉接層(搜尋、檔案清單、manifest),不帶 token(R2)
- 沿用:Colab 執行環境上的遠端 Ollama(R4、R5)、001 的下載佇列與 `/api/pull` 進度判讀(R4)、001 的 Ollama 相容端點轉送與閒置計時(R5)、003 的顯示記憶體快取(R6)、001~003 的替身與 UI API 測試接縫(R1)

## 自寫取代套件

- 資料庫遷移:`PRAGMA user_version` 加一段 0 → 1 的 SQL,約 30 行,取代遷移工具(R7)
- 量化版本列表規則:檔名切出量化名稱、去重、以 manifest 驗證,約 40 行,取代自己維護量化型別清單(R3)

## 刻意不用

- Alembic 等遷移工具:這一輪不新增套件,只有一次遷移(R7)
- `huggingface_hub` Python 套件:只用到 3 個公開端點,`httpx` 就夠,也能沿用官方模型庫轉接層的逾時與錯誤歸類(R2、R3)
- SSE 包對話串流:`EventSource` 不能送 POST 本文,也不能中途斷開讓遠端停止產生(R5)
- 瀏覽器直連 Ollama 相容端點:不同 port 要處理 CORS,spec 要求對話走 UI 的後端(R5)
- 掛在 `end_listeners` 清佇列:只涵蓋使用者結束與閒置結束,漏掉開啟失敗、失聯與被收回(R1)
