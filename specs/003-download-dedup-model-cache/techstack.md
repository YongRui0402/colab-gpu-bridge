# 技術堆疊:加入下載的重複判定與模型目錄快取

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Date**: 2026-11-13

## 一覽

| 層 | 技術 | 版本 | 用途 | 決策 |
|---|---|---|---|---|
| 後端 | Python | 3.12 | 執行環境,沿用 001/002 | R1 |
| 後端 | FastAPI | 0.162.2 | UI API;`ApiError` 處理器回 409、502、503、504 的錯誤本文,沿用 001 | R2 |
| 後端 | `httpx` | 0.28.1 | 遠端 Ollama 的 HTTP client;例外階層用來把讀模型清單的失敗歸成 `OLLAMA_*` | R2 |
| 資料 | SQLite(`sqlite3` 標準函式庫) | 不適用 | 下載佇列;整批寫入包一個交易,`pending_model` 唯一限制擋同時加入 | R2 |
| 後端 | 記憶體內的 `(工作階段名稱, 顯示記憶體總量)` | 不適用 | 模型目錄的顯示記憶體快取,放在 `Catalog` 物件裡 | R3 |
| 測試 | `pytest` | 9.2.0 | UI API 的驗收情境與參數化組合 | R4 |
| 測試 | `pytest-asyncio` | 1.4.1.post1 | 非同步案例 | R4 |
| 測試 | `tests/fakes` 的 `FakeMethod` | 不適用 | `colab`、遠端 Ollama、模型庫的替身;`invoke` 改成接受 async 的 `side_effect` | R4 |
| 測試 | `httpx.MockTransport` | 0.28.1 | 真的 `RemoteOllama` 讀模型清單失敗的替身 | R2、R4 |

## 依賴

- 後端 runtime(2 個):`fastapi`(R2)、`httpx`(R2)
- 前端 runtime(0 個):無(R2)
- 開發(2 個):`pytest`(R4)、`pytest-asyncio`(R4)
- 系統套件(apt,0 個):無(R3)

## 新引入與沿用

- 新引入:沒有新的服務、元件或套件,依賴全部沿用 001 的 `pyproject.toml` 與 `uv.lock`(R1)
- 沿用:Colab 執行環境上的遠端 Ollama(R2)、001 的 `probe_resources` 讀顯示記憶體腳本(R3)、001 的下載佇列表 `download_jobs`(R2)、001/002 的替身與 UI API 測試接縫(R4)

## 自寫取代套件

- 補 `latest` 的共用函式 `domain/model_name.py` 的 `with_version()`,1 行規則,取代兩份重複的實作(R1)
- 顯示記憶體快取:一個 tuple 加名稱比對,約 10 行,取代快取套件(R3)
- `FakeMethod.invoke` 接受 awaitable 的結果,約 2 行(R4)

## 刻意不用

- aiocache、cachetools、`functools.lru_cache`:這一輪不新增套件,而且「null 與失敗不快取」要另外寫條件(R3)
- 工作階段結束與就緒的監聽器清快取:重連也會觸發就緒,要另外分辨;用名稱比對就夠(R3)
- `asyncio.Lock` 把加入下載排成一個一個:唯一限制加交易就擋得住同時加入,不必鎖住取 manifest 的網路時間(R2)
- 同步 `time.sleep` 的延遲替身:會卡住整個事件迴圈(R4)
