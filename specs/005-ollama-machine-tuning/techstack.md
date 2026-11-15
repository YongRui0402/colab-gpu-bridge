# 技術堆疊:依機器配置調整遠端 Ollama 的設定,並在 UI 顯示與修改

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Date**: 2026-11-15

## 一覽

| 層 | 技術 | 版本 | 用途 | 決策 |
|---|---|---|---|---|
| 後端 | Python | 3.12 | 執行環境,沿用 001~004 | R7 |
| 後端 | FastAPI | 0.162.2 | 新增讀取與套用 Ollama 設定、類型覆蓋值的路由 | R11 |
| 後端 | `httpx` | 0.28.1 | 相容端點轉發沿用預設連線池(100 條),重新載入沿用預先載入 | R5、R8 |
| 後端 | `IdleMonitor.active_requests` | 不適用 | 判斷有沒有對話或相容端點的請求在進行 | R10 |
| 領域 | `colab exec -f` 遠端腳本 | 不適用 | `start_ollama.py` 加量測、級距與 pid 檔;新增 `restart_ollama.py`;設定狀態檔 `/root/cgb-ollama-tuning.json` | R1、R6、R7 |
| 領域 | Ollama(遠端) | 安裝時取最新(桌機實測 0.32.15,001 遠端實測 0.40.15) | 讀五個環境變數決定平行數、context、同時載入模型數、flash attention、KV cache | R2、R3 |
| 領域 | `nvidia-smi` | 不適用 | 在執行環境上讀顯示記憶體總量與 GPU 名稱 | R6 |
| 領域 | `/proc/meminfo` | 不適用 | 在執行環境上讀系統記憶體總量 | R6 |
| 前端 | 原生 HTML / CSS / JS | 不適用 | 開啟畫面的「Ollama 設定」區塊、工作階段頁的設定卡 | R11 |
| 資料 | SQLite(`sqlite3` 標準函式庫) | 不適用 | `PRAGMA user_version` 1 → 2,重建 `sessions`、`session_transitions`,新增 `runtime_type_tunings`、`session_tunings`、`session_tuning_models` | R9 |
| 測試 | `pytest` | 9.2.0 | 級距、覆蓋值、重啟流程的整合測試 | R4、R7 |
| 測試 | `pytest-asyncio` | 1.4.1.post1 | 非同步案例 | R1 |
| 測試 | `tests/fakes` 的替身 | 不適用 | 回報不同顯示記憶體的 `colab` 替身、重啟失敗的替身 | R1、R4 |

## 依賴

- 後端 runtime(2 個):`fastapi`(R11)、`httpx`(R5)
- 前端 runtime(0 個):無(R11)
- 開發(2 個):`pytest`(R4)、`pytest-asyncio`(R1)
- 系統套件(apt,0 個):無(R6)

## 新引入與沿用

- 新引入:遠端腳本 `restart_ollama.py`、pid 檔 `/root/cgb-ollama-serve.pid` 與設定狀態檔 `/root/cgb-ollama-tuning.json`(R1)
- 新引入:`cgb/domain/tuning.py` 的級距表(R7)
- 沿用:Colab 執行環境上的遠端 Ollama(R2)、001 的 `colab exec` 重跑一次約定(R1)、001 的預先載入(R8)、001 的閒置計時(R10)、004 的 `PRAGMA user_version` 遷移(R9)

## 自寫取代套件

- 級距與環境組合:顯示記憶體級距表與「覆蓋值 > 級距 > 不帶」的組合,約 40 行,取代設定管理套件(R7)
- 遠端行程停止:讀 pid 檔、對行程群組送 `SIGTERM`/`SIGKILL`,約 30 行,取代行程管理工具(R1)

## 刻意不用

- 在請求 `options` 帶 `num_ctx`:平行數與同時載入模型數只能在 serve 層設,相容端點也不能改請求本文(R2)
- 直接用 `--env OLLAMA_*` 傳設定:會殘留在 kernel 的環境,改回自動時套到舊值(R7)
- `supervisord` 等行程管理工具:只需要停掉一個行程群組再啟動,不值得在執行環境上多裝一套(R1)
- KV cache `f16`:記憶體是 `q8_0` 的兩倍,同一張卡的平行數減半(R3)
