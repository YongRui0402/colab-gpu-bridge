# 技術堆疊:讓 opencode 與 pi 輕鬆接上 Colab 上的 Ollama

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Date**: 2026-11-16

## 一覽

| 層 | 技術 | 版本 | 用途 | 決策 |
|---|---|---|---|---|
| 後端 | FastAPI | 沿用專案鎖定的版本 | 相容端點的路由與錯誤格式 | R1、R6 |
| 後端 | httpx | 沿用專案鎖定的版本 | 原樣轉送 `/v1` 請求與 SSE 回應 | R1 |
| 前端 | 原生 HTML / CSS / JS | 不適用 | 連線設定畫面、產生片段與一鍵複製 | R2、R3、R5、R7 |
| 部署 | Docker Compose | 沿用 | 把 `CGB_HOST_OLLAMA_PORT` 以 `CGB_PUBLIC_OLLAMA_PORT` 傳進容器 | R7 |
| 測試 | pytest | 沿用 | 替身與整合測試;`realrun_local` 接臨時 `ollama serve` | R1、R8 |
| 測試 | Playwright | 沿用 | 連線設定畫面的 e2e | R2 |
| 測試 | opencode | 1.18.31 | SC-001 本機實跑的用戶端(桌機已裝,暫存 `HOME` 執行) | R2 |
| 測試 | pi(`@mariozechner/pi-coding-agent`) | 0.73.1 | SC-002 本機實跑的用戶端(暫存資料夾安裝) | R3 |
| 測試 | Ollama | 0.32.15(桌機) | 本機實跑的遠端替代,模型 `qwen2.5:3b` | R8 |

## 依賴

- 後端 runtime(0 個):無(R1)
- 前端 runtime(0 個):無(R2)
- 開發(0 個):無(R3)
- 系統套件(apt,0 個):無(R8)

## 新引入與沿用

- 新引入:無新服務;實跑時在暫存資料夾安裝 pi(R3)
- 沿用:Ollama 相容端點(R1)、005 的 Ollama 設定與覆蓋(R5)、臨時 `ollama serve` 的實跑做法(R8)

## 自寫取代套件

- SSE 中途斷線時補 `data:` 錯誤段與 `[DONE]`,約 15 行(R1)

## 刻意不用

- 自寫 OpenAI 相容轉換層:遠端 Ollama 已內建 `/v1`(R1)
- 開放 `/v1/completions`、`/v1/embeddings`、`/v1/responses`:兩個用戶端都用不到(R1)
- 依模型架構精算建議 context:要等下載完、畫面變複雜(R5)
- `qwen3` 系列當本機實跑模型:思考內容太多,6 GB 上逾時(R8)
