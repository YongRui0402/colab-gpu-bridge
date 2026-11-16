# 技術堆疊:模型目錄讀不到時回正確的錯誤,對話紀錄保留到工作階段結束

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Date**: 2026-11-16

## 一覽

| 層 | 技術 | 版本 | 用途 | 決策 |
|---|---|---|---|---|
| 後端 | FastAPI | 0.162.2 | 模型目錄與預先載入的錯誤回應(既有的 `ApiError` 處理器) | R1 |
| 前端 | 原生 HTML / CSS / JS | 不適用 | 模型頁與對話頁的錯誤畫面、對話的保存與還原 | R2、R4、R5 |
| 前端 | Web Storage(`localStorage`) | 不適用 | 在使用者的瀏覽器裡保存對話頁目前的對話 | R3 |
| 前端 | Server-Sent Events(`/api/events`) | 不適用 | 以 `session.updated` 判斷工作階段結束、清除保存的對話 | R4 |
| 測試 | pytest | 9.2.0 | 替身的整合測試 | R1、R6 |
| 測試 | Playwright(pytest-playwright 0.10.0) | 1.64.1 | 模型頁與對話頁的 e2e,含重新整理、另開分頁 | R3、R6 |

## 依賴

- 後端 runtime(0 個):無(R1)
- 前端 runtime(0 個):無(R3)
- 開發(0 個):無(R6)
- 系統套件(apt,0 個):無(R6)

## 新引入與沿用

- 新引入:瀏覽器的 `localStorage` 鍵 `cgb.chat.v1`,本系統第一次在瀏覽器保存資料(R3)
- 沿用:`ollama_error()` 與錯誤訊息表(R1)、`session.updated` 推送(R4)、e2e 的替身與測試行程內 uvicorn(R6)

## 自寫取代套件

- 對話的保存、還原與清除,約 40 行原生 JS(R3、R4、R5)

## 刻意不用

- `sessionStorage`:另開分頁讀不到(R3)
- IndexedDB:只存一段對話,用不到,還要處理非同步寫入(R3)
- 後端保存對話:違反 NFR-002 與 D3(R3)
- 多分頁即時同步(`storage` 事件、`BroadcastChannel`):spec 不要求,範圍長出去(R3)
- 全域的 `AdapterError` 例外處理器:會蓋掉別的操作的狀態碼(R1)
