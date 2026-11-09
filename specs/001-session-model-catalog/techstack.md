# 技術堆疊:Colab GPU 工作階段管理與模型目錄

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Date**: 2026-11-09

## 一覽

| 層 | 技術 | 版本 | 用途 | 決策 |
|---|---|---|---|---|
| 前端 | 原生 HTML / CSS / JS | 不適用 | 工作階段、登入、模型目錄、下載模型、用量與設定、紀錄 6 頁加狀態總覽,不用框架與建置工具 | R9 |
| 前端 | Server-Sent Events | 不適用 | 狀態、下載進度、閒置倒數由伺服器推送 | R9 |
| 後端 | Python | 3.12 | 執行環境(容器基底 `python:3.12-slim`) | R11 |
| 後端 | FastAPI | 0.162.2 | UI 的 REST API、Ollama 相容端點、提供前端靜態檔 | R8、R9 |
| 後端 | uvicorn | 0.54.0 | ASGI 伺服器 | R8 |
| 後端 | httpx | 0.28.1 | 串流轉送到遠端 Ollama、呼叫 ollama.com 與 registry | R6、R8 |
| 後端 | sse-starlette | 3.7.0 | SSE 回應 | R9 |
| 後端 | google-auth-oauthlib | 1.5.0 | UI 內 Colab 登入(與 CLI 同一套 InstalledAppFlow) | R2 |
| 領域 | google-colab-cli | 0.7.5 | 開關執行環境、遠端執行、讀用量、SSH ProxyCommand | R1、R3 |
| 領域 | OpenSSH 用戶端 | 不適用(Debian 套件) | `ssh -L` 本機轉發到遠端 Ollama | R3 |
| 領域 | Ollama(遠端) | 0.40.15(安裝時取最新,實測版本) | 執行環境上的模型服務,只聽 127.0.0.1 | R1、R5、R8 |
| 資料 | SQLite(`sqlite3` 標準函式庫) | 不適用 | 工作階段紀錄、下載項目、精選清單、設定;WAL 模式 | R10 |
| 測試 | pytest | 9.2.0 | 單元與整合測試 | R12 |
| 測試 | pytest-asyncio | 1.4.1.post1 | 非同步測試 | R12 |
| 測試 | httpx ASGI transport | 0.28.1 | 不起伺服器直接打 FastAPI | R12 |
| 測試 | Playwright(Python) | 1.64.1 | UI 端對端測試 | R12 |
| 測試 | pytest-playwright | 0.10.0 | Playwright 的 pytest 外掛 | R12 |
| 交付 | Docker | 29.1.3 | 單一映像 | R11 |
| 部署 | Docker Compose | 2.40.3 | 一個服務、區網 port、掛載資料夾;先在桌機,之後同一份上 Unraid | R11 |

## 依賴

- 後端 runtime(6 個):`fastapi`(R8)、`uvicorn`(R8)、`httpx`(R8)、`sse-starlette`(R9)、`google-auth-oauthlib`(R2)、`google-colab-cli`(R1)
- 前端 runtime(0 個):無(R9)
- 開發(4 個):`pytest`(R12)、`pytest-asyncio`(R12)、`playwright`(R12)、`pytest-playwright`(R12)
- 系統套件(apt,1 個):`openssh-client`(R3)

## 新引入與沿用

- 新引入:Colab Pro 執行環境(由 CLI 開關)與其上的 Ollama(R1);桌機上本系統的容器(R11)
- 沿用:使用者既有的 Colab Pro 帳號與 compute units(R1)、桌機的 Docker(R11)、桌機既有的 ed25519 金鑰(實作時改為容器專用金鑰,R3)

## 自寫取代套件

- Ollama 原樣轉送代理加推論與查詢路徑白名單(管理操作回 403、其他回 404),約 30 行(R8)
- ollama.com 搜尋頁與版本頁的 HTML 解析,不引入 HTML 解析套件(R6)
- 健康檢查與重連迴圈(R3)

## 刻意不用

- cloudflared、Tailscale、反向 SSH:有公開網址、要多一個帳號,或要碰家裡的共用服務(R3)
- Google Drive(含 Drive 快取):GPU 上比網路下載慢,且每台執行環境都要手動授權(R4)
- LiteLLM、ollama-proxy-server、Nginx:改寫格式或功能過多,仍需要應用程式層(R8)
- React、Vue、建置工具:畫面規模不需要(R9)
- PostgreSQL、JSON 檔:要多一個容器,或並行寫入要自己鎖(R10)
- 直接 import `colab_cli` 內部類別:不是公開 API(R1)
