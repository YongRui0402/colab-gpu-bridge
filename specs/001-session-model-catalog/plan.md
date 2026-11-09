# 系統分析規劃: Colab GPU 工作階段管理與模型目錄

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Techstack**: [techstack.md](./techstack.md) | **Date**: 2026-11-09

## Project Structure

### Documentation (this feature)

```text
specs/001-session-model-catalog/
├── spec.md              # 輸入(specify 產出)
├── research.md          # 輸入(technical-research 產出)
├── techstack.md         # 輸入(technical-research 產出)
├── plan.md              # 本文件
├── prototype/           # S4 產出(E1 前端 UI,ui-plan)
├── deploy/              # S10、S11 產出(E10 檔案系統、E11 部署與網路,deploy-plan)
└── contracts/
    ├── remote-ollama.openapi.yaml   # S1 產出(E7 遠端 Ollama,api-plan)
    ├── model-library.openapi.yaml   # S2 產出(E8 Ollama 官方模型庫,api-plan)
    ├── google-oauth.openapi.yaml    # S3 產出(E9 Google OAuth,api-plan)
    ├── ui.openapi.yaml              # S5 產出(E2 後端 UI API,api-plan)
    ├── ui-events.asyncapi.yaml      # S5 產出(E2 後端 UI API 的 SSE 事件,api-plan)
    ├── ollama-compat.openapi.yaml   # S6 產出(E3 Ollama 相容端點,api-plan)
    ├── store.dbml                   # S7 產出(E4 資料庫,data-plan)
    ├── colab-cli.openapi.yaml       # S8 產出(E5 Colab CLI,api-plan)
    └── tunnel.openapi.yaml          # S9 產出(E6 SSH 通道,api-plan)
```

### Source Code (repository root)

```text
pyproject.toml               # uv 專案:依賴、pytest 設定
Dockerfile                   # 單一映像:python:3.12-slim + openssh-client + google-colab-cli
compose.yaml                 # E11 部署與網路

src/cgb/
├── api/                     # E2 後端 UI API(REST 與 SSE)
├── ollama_compat/           # E3 Ollama 相容端點(轉送、阻擋管理操作、閒置計時)
├── services/                # 用例:工作階段生命週期、健康檢查與重連、下載佇列、閒置、用量
├── adapters/
│   ├── colab_cli.py         # E5 Colab CLI 的呼叫與輸出解析
│   ├── tunnel.py            # E6 SSH 通道的建立與健康檢查
│   ├── remote_ollama.py     # E7 遠端 Ollama 的 HTTP 呼叫
│   ├── model_library.py     # E8 ollama.com 與 registry
│   └── google_oauth.py      # E9 Google OAuth 授權碼流程
├── repos/                   # E4 資料庫的存取
├── db/                      # E4 資料庫的連線與 schema
├── domain/                  # 不依賴 I/O 的純函式:狀態轉換、輸出解析、閒置與用量計算
└── static/                  # E1 前端 UI(原生 HTML/CSS/JS)

tests/
├── unit/                    # domain 與解析
├── integration/             # API 經 ASGI transport,adapter 用替身
├── realrun/                 # 打真實 Colab 的實跑案例(會花 compute units,需本人在場)
└── e2e/                     # Playwright

deploy/                      # E10 檔案系統、E11 部署與網路
```

**Structure Decision**: 單一 Python 專案、單一映像:FastAPI 同時提供 UI API、Ollama 相容端點與前端靜態檔,兩個入口各占一個 port(UI 與 Ollama 端點分開,區網程式設定 Ollama 位址時不會碰到 UI)。資料用 SQLite 存在掛載的 `/data`,不另起資料庫容器;同一份 compose 先在桌機跑,之後搬到 Unraid。

後端分層是 `api / ollama_compat → services → (repos → db | adapters/*)`:`services/` 是用例,往下呼叫資料庫與五個對外部的轉接——`colab_cli.py` 接 Colab CLI、`tunnel.py` 接 SSH 通道、`remote_ollama.py` 接遠端 Ollama、`model_library.py` 接官方模型庫、`google_oauth.py` 接 Google OAuth。`domain/` 是純函式,讓狀態轉換與輸出解析能用快速的單元測試涵蓋;自動化測試只在 `adapters/` 這一層換成替身。

前端照畫面區塊分檔(工作階段、模型目錄與下載、用量與設定、紀錄),共用的 SSE 訂閱與 API 呼叫放在同一支模組。

## 分析流程規劃

> 本段排定分析的順序與每一步指派的 planner;分析由 Phase 3 照波段交給 sub agent 執行,產出寫在 Documentation 樹列的路徑。

### 端點盤點

這次需求涉及 11 個端點。每個端點視為一個獨立系統,分析的對象是它對外的介面:

| # | 端點 | 介面 | 需求出處 |
|---|---|---|---|
| E1 | 前端 UI(瀏覽器,原生 HTML/CSS/JS) | 畫面與互動:頁面、各狀態的呈現、登入與授權碼輸入、類型選擇、模型目錄、下載佇列、用量與倒數、設定、紀錄、詞彙 | FR-001–FR-010、FR-014、FR-015、FR-017、FR-018、FR-020–FR-022、FR-024–FR-028、NFR-001、NFR-006、NFR-008、NFR-011 |
| E2 | 後端 UI API(FastAPI REST 與 SSE) | 資源、操作、錯誤、長時間操作的進度與取消、狀態推送事件 | FR-001–FR-010、FR-014、FR-015、FR-017、FR-018、FR-020–FR-022、FR-024–FR-028、NFR-007、NFR-009、NFR-010 |
| E3 | Ollama 相容端點(FastAPI 轉送) | 開放與阻擋的路徑、沒有工作階段時的錯誤、串流轉送、閒置計時的觸發 | FR-011、FR-012、FR-013、FR-016、FR-026、NFR-003、NFR-004、SC-005、SC-007 |
| E4 | 資料庫(SQLite) | 資料表、關聯、唯一性與狀態約束 | FR-005、FR-021、FR-027、FR-028、關鍵實體 |
| E5 | Colab CLI(google-colab-cli,外部程式) | 外部程式呼叫:要用的指令與參數、輸出的解析、失敗的判定、逾時與重試 | FR-001、FR-002、FR-003、FR-005、FR-006、FR-007、FR-009、FR-024、SC-001、SC-003 |
| E6 | SSH 通道(OpenSSH 與 `colab ssh --proxy-mode`) | 外部程式呼叫:轉發的建立與參數、健康檢查、斷線判定與重連 | FR-004、NFR-003、SC-002 |
| E7 | 遠端 Ollama(Colab 執行環境上,Ollama API) | Ollama 提供的 API:列模型、查已載入、預先載入、下載與進度、推論、版本 | FR-011、FR-014–FR-018、NFR-005、SC-004 |
| E8 | Ollama 官方模型庫(ollama.com 與 registry.ollama.ai) | 對方提供的介面:搜尋、版本清單、manifest 與大小 | FR-020、FR-022 |
| E9 | Google OAuth(授權碼流程) | 對方提供的介面:授權網址、授權碼換 token、token 更新 | FR-008 |
| E10 | 檔案系統(`/data` 掛載) | 授權檔、CLI 狀態檔、SSH 金鑰、資料庫檔的路徑、權限與持久化 | NFR-010、NFR-012、FR-005 |
| E11 | 部署與網路(Docker Compose) | 服務、區網 port 與綁定、掛載、環境變數 | NFR-009、NFR-012、Assumptions(容器交付、先在桌機驗收) |

### 分析波段

排序原則:**一個介面排在它所依賴的介面都分析完之後**;同一波裡的介面彼此不依賴,可以各開一個 sub agent 平行分析。

第三方端點的介面是對方定好的,我們只能照著接、不能改,所以它不依賴我們任何一個介面;
反過來,我們這邊碰到它的介面都要遷就它。因此**第三方端點排在最前面**,依賴它的介面往後推一波。

| Wave | 步驟 | 介面 | Planner | 平行 | 排在這一波的理由 |
|---|---|---|---|---|---|
| 1 | S1 | E7 遠端 Ollama | api-plan | ✅ 與 S2、S3 平行 | Ollama 的 API 已經定好,不依賴任何介面;Ollama 相容端點的轉送與後端的下載、模型目錄都要照它 |
| 1 | S2 | E8 Ollama 官方模型庫 | api-plan | ✅ 與 S1、S3 平行 | ollama.com 與 registry 的介面已經定好;後端的搜尋、版本與大小要照它 |
| 1 | S3 | E9 Google OAuth | api-plan | ✅ 與 S1、S2 平行 | Google 的授權碼流程已經定好;後端的登入操作與前端的授權碼輸入要照它 |
| 2 | S4 | E1 前端 UI | ui-plan | ✅ 與 S5、S6 平行 | 由使用者故事推出;登入要照 S3 的授權網址與貼回授權碼的流程,下載佇列的進度要照 S1 的 pull 進度。前端與後端以同一份需求為準,不必等對方 |
| 2 | S5 | E2 後端 UI API | api-plan | ✅ 與 S4、S6 平行 | 由 FR 推出;登入照 S3,模型目錄與下載照 S1,搜尋與大小照 S2 |
| 2 | S6 | E3 Ollama 相容端點 | api-plan | ✅ 與 S4、S5 平行 | 要轉送與阻擋的路徑、串流格式照 S1 的 Ollama API |
| 3 | S7 | E4 資料庫 | data-plan | ✅ 與 S8、S9 平行 | 要存什麼由 S5 的資源與操作決定(工作階段紀錄、下載項目、精選清單、設定) |
| 3 | S8 | E5 Colab CLI | api-plan | ✅ 與 S7、S9 平行 | 要用哪些指令、要解析出哪些欄位、失敗要回報什麼由 S5 的工作階段操作與用量決定 |
| 3 | S9 | E6 SSH 通道 | api-plan | ✅ 與 S7、S8 平行 | 健康檢查的間隔、斷線與重連要回報什麼由 S5 的狀態事件與 S6 的「沒有工作階段」錯誤決定 |
| 4 | S10 | E10 檔案系統 | deploy-plan | — | 要放哪些檔由 S7 的資料庫檔、S8 的 CLI 授權與狀態檔、S9 的 SSH 金鑰決定 |
| 5 | S11 | E11 部署與網路 | deploy-plan | — | 要開哪些 port 由 S5、S6 決定,要掛哪些路徑由 S10 決定 |

共 5 個 wave、11 個步驟:Wave 1 三個介面平行,Wave 2 三個介面平行,Wave 3 三個介面平行,Wave 4 一個介面,Wave 5 一個介面。

## 待決問題

> Phase 3 每一波交回的待決問題都登記在這裡;有問題擋住下一波時,在下一波開始之前把所有還沒決定的一次問完,沒有擋住就等最後一波之後一起問。

| Q | 提出的步驟 | 問題與可選的做法 | 擋住 | 決定 |
|---|---|---|---|---|
| Q1 | S2 | **與 spec 矛盾**:搜尋只讀第 1 頁(20 筆)會讓使用者故事 3 驗收情境 9「列出符合的模型與各版本」只列前 20 筆。可選:(a)只讀第 1 頁;(b)帶 `page` 與 `HX-Request: true` 讀下一頁,UI 提供「顯示更多」 | S5 | (b)讀下一頁,UI 提供「顯示更多」(kevin-twin 代為決定) |
| Q2 | S1 | FR-018「未完成的下載不得顯示為可用」依賴 Ollama 下載完才寫入 manifest(只有說明文件,未實測)。可選:(a)直接信任 `/api/tags`(先採用),列給 testplan 實跑驗證;(b)後端另外排除佇列中未完成的名稱 | — | (a)信任 `/api/tags`,列給 testplan 實跑驗證(kevin-twin 代為決定) |
| Q3 | S1 | `/api/pull` 失敗回報(HTTP 200 加一行 `{"error"}`,未實測)。可選:(a)依 error 文字分成 `OLLAMA_NOT_FOUND` 與 `OLLAMA_PULL_FAILED`(先採用);(b)一律 `OLLAMA_PULL_FAILED` | S5 | (a)依 error 文字分 `OLLAMA_NOT_FOUND` 與 `OLLAMA_PULL_FAILED`(kevin-twin 代為決定) |
| Q4 | S1 | 預先載入的 `keep_alive`。可選:(a)`-1` 留到工作階段結束或被擠掉(先採用);(b)預設 5 分鐘;(c)與閒置時限相同 | — | (a)`keep_alive=-1`(kevin-twin 代為決定) |
| Q5 | S1 | 各操作逾時。可選:(a)version 5 秒、tags/ps 10 秒、pull 連線 10 秒且兩行進度間隔 60 秒不設總時長、預先載入 300 秒(先採用);(b)由 S5、S6 另定 | S5、S6 | (a)version 5 秒、tags/ps 10 秒、pull 連線 10 秒且進度間隔 60 秒、預先載入 300 秒(kevin-twin 代為決定) |
| Q6 | S1 | 約定外新增的原因後綴 `_BAD_REQUEST`(400)、`_SERVER_ERROR`(500)、`_PULL_FAILED`、`_STREAM_INTERRUPTED`。可選:(a)保留,並成為各服務共用的後綴(先採用);(b)併入約定的四個 | S5、S6 | (a)保留,`_BAD_REQUEST`、`_SERVER_ERROR`、`_PULL_FAILED`、`_STREAM_INTERRUPTED` 成為各服務共用後綴(kevin-twin 代為決定) |
| Q7 | S1 | 執行環境剩餘磁碟(FR-022)與可用顯示記憶體(NFR-006)Ollama API 不提供。可選:(a)由 S8 經 `colab exec` 提供(先採用);(b)從 `/api/ps` 的 `size_vram` 推估 | — | (a)由 S8 經 `colab exec` 提供(kevin-twin 代為決定) |
| Q8 | S2 | 約定外的原因 `LIBRARY_CLOUD_ONLY`(雲端專用版本 manifest 回 200 但沒有任何層)。可選:(a)另立代碼(先採用);(b)併入 `LIBRARY_NOT_FOUND`;(c)轉接層直接濾掉 | S5 | (a)另立 `LIBRARY_CLOUD_ONLY`(kevin-twin 代為決定) |
| Q9 | S2 | 搜尋結果是否含社群模型(`/<使用者>/<名稱>`)。可選:(a)只取官方 `/library/`(先採用);(b)也列社群模型 | S5 | (a)只取官方 `/library/`(kevin-twin 代為決定) |
| Q10 | S2 | 搜尋固定帶 `c=local` 排除雲端專用模型。可選:(a)帶(先採用);(b)不篩選 | — | (a)帶 `c=local`(kevin-twin 代為決定) |
| Q11 | S2 | 模型大小算法:清單顯示版本頁的四捨五入值,FR-022 的總大小用 manifest `layers[].size` 加總、不計 `config.size`。可選:(a)只加 layers(先採用);(b)連 config 一起算 | — | (a)只加 layers(kevin-twin 代為決定) |
| Q12 | S2 | 模型庫請求的逾時。可選:(a)交給 S5 或實作決定(先採用);(b)現在定 10 秒 | S5 | (a)交給 S5 或實作決定(kevin-twin 代為決定) |
| Q13 | S3 | Google 錯誤本文是 `{error, error_description}`,與檢查腳本要求的 `Error` 不同。可選:(a)另寫 `OAuthError` 照 Google 原樣,`Error` 只當 `OAUTH_` 代碼目錄(先採用);(b)回應直接引用 `Error` | — | (a)另寫 `OAuthError`,`Error` 只當代碼目錄(kevin-twin 代為決定) |
| Q14 | S3 | refresh token 請求要不要寫進規格(由 CLI 自己送)。可選:(a)寫,`x-callers` 標明呼叫者是 Colab CLI(先採用);(b)拿掉 | — | (a)寫入,`x-callers` 標 Colab CLI(kevin-twin 代為決定) |
| Q15 | S3 | 連不到與逾時沒有 HTTP 回應,代碼放哪。可選:(a)操作層 `x-transport-error-codes`(先採用);(b)放進 `default` 回應 | — | (a)`x-transport-error-codes`(kevin-twin 代為決定) |
| Q16 | S3 | 約定外的原因 `OAUTH_SCOPE_NOT_GRANTED`(使用者取消勾選 colaboratory)與 `OAUTH_AUTHORIZE_REJECTED`。可選:(a)保留(先採用);(b)併入 `OAUTH_BAD_RESPONSE`;(c)刪掉 | S5 | (a)保留兩個代碼(kevin-twin 代為決定) |
| Q17 | S3 | PKCE `code_verifier` 中途遺失(後端重啟)時貼回的授權碼換不到 token。可選:(a)不保存,讓使用者重新取得授權連結(先採用);(b)持久化 | S5 | (a)不保存,重新取得授權連結(kevin-twin 代為決定) |
