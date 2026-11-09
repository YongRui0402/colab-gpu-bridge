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
| 2 | S4 | E1 前端 UI | ui-plan | ✅ 與 S5、S6 平行 | 由使用者故事推出;登入要照 S3 的授權網址與貼回授權碼的流程,下載佇列的進度要照 S1 的 pull 進度,搜尋結果與分頁要照 S2 的搜尋介面。前端與後端以同一份需求為準,不必等對方 |
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
| Q1 | S2 | **與 spec 矛盾**:搜尋只讀第 1 頁(20 筆)會讓使用者故事 3 驗收情境 9「列出符合的模型與各版本」只列前 20 筆。可選:(a)只讀第 1 頁;(b)帶 `page` 與 `HX-Request: true` 讀下一頁,UI 提供「顯示更多」 | S4、S5 | (b)讀下一頁,UI 提供「顯示更多」(kevin-twin 代為決定) |
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
| Q18 | S6 | **與 spec 矛盾**:黑名單轉送會連帶提供 `/v1/*`,使「不另外提供 OpenAI 相容 API」(假設)不成立。(a)黑名單(先採用);(b)白名單,只轉送 FR-011 點名的路徑,其他回 404 | S6、S8 | (b)白名單(kevin-twin 代為決定) |
| Q19 | S6 | **與 spec 矛盾**:管理操作且沒有工作階段時,FR-013 原文要求回「沒有可用的工作階段」。(a)一律 403 `MANAGED_IN_UI`(先採用);(b)先回 503 | S6 | (a)維持 403;spec FR-013 改為只管推論與查詢請求(kevin-twin 代為決定) |
| Q20 | S6 | **與 spec 矛盾**:帶非本機 `Origin` 的瀏覽器程式會被遠端 Ollama 回 403,使故事 2 驗收情境 1 不成立。(a)照送(先採用);(b)遠端啟動時設 `OLLAMA_ORIGINS` | S6、S8 | (b)S8 的啟動步驟設 `OLLAMA_ORIGINS=*`(kevin-twin 代為決定) |
| Q21 | S6 | `/api/blobs/{digest}` 是否算管理操作。(a)算,HEAD/POST 都擋(先採用);(b)只擋 R8 的五個 | — | (a)(kevin-twin 代為決定) |
| Q22 | S6 | 未定逾時的操作。(a)`/` 5 秒、show 10 秒、推論類連線 10 秒且首段與段間 300 秒、不設總時長(先採用);(b)推論類不設讀取逾時 | — | (a)(kevin-twin 代為決定) |
| Q23 | S6 | 遠端 Ollama 的英文錯誤說明。(a)原樣傳回(先採用);(b)改寫成繁體中文。憲法〈給人讀的文字一律用繁體中文〉管的是產出物的文字,不含執行時原樣轉送的第三方訊息 | — | (a)原樣傳回(kevin-twin 代為決定) |
| Q24 | S6 | 閒置計時。(a)任何請求都重設,進行中(含串流)不計閒置,結束後重設(先採用);(b)只在收到請求時重設 | S5 | (a)(kevin-twin 代為決定) |
| Q25 | S6 | 串流中途失敗。(a)NDJSON 補一行 `{"error"}` 再關閉;連線中斷 `OLLAMA_STREAM_INTERRUPTED`,工作階段被結束或換類型 `NO_READY_SESSION`(先採用);(b)直接關閉 | S5 | (a)(kevin-twin 代為決定) |
| Q26 | S5 | 開啟前沒有有效授權的代碼。(a)`AUTH_REQUIRED` 409(先採用);(b)等 S8 的 `COLAB_` 代碼 | S8 | (a)`AUTH_REQUIRED`;S8 不得另造同義代碼(kevin-twin 代為決定) |
| Q27 | S5 | Error 本文另加選填 `model`、`reasonCode`。(a)加(先採用);(b)只用 `{code, message}` | — | (a)(kevin-twin 代為決定) |
| Q28 | S5 | 沒有就緒工作階段能否加入下載。(a)不行,回 `NO_READY_SESSION`(先採用);(b)可以 | — | (a)(kevin-twin 代為決定) |
| Q29 | S5 | 工作階段結束後的佇列。(a)排隊中保留、就緒後自動繼續並重新檢查空間;下載中的變失敗 `SESSION_ENDED`,手動重下(先採用);(b)全部手動 | — | (a)(kevin-twin 代為決定) |
| Q30 | S5 | 本系統自己的失敗原因 `SESSION_ENDED`、`DISK_SPACE_INSUFFICIENT`。(a)保留(先採用);(b)併入 `OLLAMA_STREAM_INTERRUPTED` | — | (a)(kevin-twin 代為決定) |
| Q31 | S5 | 讀不到剩餘磁碟或顯示記憶體。(a)加入下載擋下回 `DISK_SPACE_UNKNOWN` 503,「可能無法載入」標未知(先採用);(b)只警告 | S8 | (a)(kevin-twin 代為決定) |
| Q32 | S5 | 搜尋 `hasMore` 判斷。(a)過濾前滿 20 筆即視為有下一頁(先採用,未實測);(b)多讀一頁確認。另:S2 的 model-library.openapi.yaml 仍寫只讀第 1 頁,與 Q1 衝突 | S2 | (a);S2 重做以符合 Q1(後經 Q54 改為看下一頁連結)(kevin-twin 代為決定) |
| Q33 | S5 | 模型庫逾時。(a)每請求 10 秒,試算依序送出(先採用);(b)平行或另設總時長 | — | (a)(kevin-twin 代為決定) |
| Q34 | S5 | 設定值範圍。閒置時限 1–1440 分鐘整數、警告門檻 0–10000(先採用) | S7 | 照先採用的範圍(kevin-twin 代為決定) |
| Q35 | S5 | NFR-006 預先載入前提示由誰把關。(a)只由 UI 依 `mayNotFit` 提示(先採用);(b)請求帶確認旗標 | — | (a)(kevin-twin 代為決定) |
| Q36 | S5 | 變更類型時重新載入哪些模型:當下 `/api/ps` 已載入的模型以 `origin: restore` 加入佇列,完成後自動預先載入(先採用) | S7 | 照先採用(kevin-twin 代為決定) |
| Q37 | S5 | 外部失敗代碼前綴 `^(COLAB|TUNNEL|OLLAMA|LIBRARY|OAUTH)_`。(a)照此(先採用);(b)放寬 | S8、S9 | (a);S8 用 `COLAB_`、S9 用 `TUNNEL_`(kevin-twin 代為決定) |
| Q38 | S5 | SSE 細節:protocol `http`、連上先送完整快照、事件皆完整現況、不支援 `Last-Event-ID`、倒數每 5 秒、進度每秒最多一則(先採用) | — | 照先採用(kevin-twin 代為決定) |
| Q39 | S5 | `OAUTH_AUTHORIZE_REJECTED` 不會出現在 UI API;不可自行修正的 `OAUTH_` 錯誤回 502。(a)照此(先採用);(b)另提示逾時未貼回 | — | (a)(kevin-twin 代為決定) |
| Q40 | S4 | 審美方向。(a)淺色安靜的家用控制台,墨綠主色,狀態色綠/藍/琥珀/紅,名稱用等寬字(先採用);(b)深色;(c)跟系統 | — | (a)(kevin-twin 代為決定) |
| Q41 | S4 | 畫面用到但 S1–S3 沒有的資料(剩餘磁碟、顯示記憶體等)。(a)照 Q7 由 S5、S8 提供(先採用);(b)顯示記憶體查固定表 | S8 | (a)(kevin-twin 代為決定) |
| Q42 | S4 | 搜尋規格與 Q1 不一致(同 S5 提出的那題)。(a)回 S2 改成讀下一頁(先採用) | S2 | (a)(kevin-twin 代為決定) |
| Q43 | S4 | 沒有就緒工作階段時加入下載(同 S5)。(a)擋下並提示先開啟(先採用) | — | (a)(kevin-twin 代為決定) |
| Q44 | S4 | 工作階段結束時正在下載的那一個(同 S5)。(a)標失敗並可「重新排隊」(先採用) | — | (a)(kevin-twin 代為決定) |
| Q45 | S4 | 背景下載時閒置計時照算。(a)照 spec 只看 Ollama 相容端點的請求(先採用);(b)下載時暫停計時(會使 FR-026 不成立) | — | (a)(kevin-twin 代為決定) |
| Q46 | S4 | 「授權連結已失效」與「授權碼錯誤」分開。(a)分開,S5 給獨立代碼(先採用);(b)合併 | S5 | (a);S5 補代碼(kevin-twin 代為決定) |
| Q47 | S4 | 登入頁不顯示帳號與登入時間。(a)只顯示已登入或未登入(先採用);(b)S5 另給 email | — | (a)(kevin-twin 代為決定) |
| Q48 | S4 | 搜尋結果不顯示 ollama.com 英文簡介。(a)不顯示(先採用);(b)原樣顯示 | — | (a)(kevin-twin 代為決定) |
| Q49 | S4 | 原型多加的操作:失敗項目「重新排隊」「移除」、「清除已完成」;不顯示端點位址。(a)保留三個操作,S5 補對應操作(先採用);(b)拿掉;(c)也顯示端點位址 | S5 | (a);S5 補操作(kevin-twin 代為決定) |
| Q50 | S5 | 「授權連結已失效」代碼名稱。(a)`AUTH_FLOW_NOT_FOUND` 改名 `AUTH_LINK_EXPIRED`(先採用);(b)保留原名 | — | (a)(kevin-twin 代為決定) |
| Q51 | S5 | 「清除已完成」。(a)`POST /api/downloads/clear-completed` 只清 completed(先採用);(b)`DELETE ?state=completed`;(c)連失敗一起清 | — | (a)(kevin-twin 代為決定) |
| Q52 | S5 | 被擋下的管理操作是否重設閒置計時。(a)要,任何經 Ollama 相容端點的請求都算,與 FR-026 原文一致(先採用);(b)只算推論與查詢 | — | (a)(kevin-twin 代為決定) |
| Q53 | S6 | 白名單路徑用錯方法(如 `POST /api/tags`)。(a)照樣轉送,回遠端的 405(先採用);(b)本端點回 405 並另立代碼 | — | (a)(kevin-twin 代為決定) |
| Q54 | S2 | hasMore 判斷。(a)照 Q32 滿 20 筆推斷;(b)看頁面末尾有沒有 `hx-get="/search?page=<N+1>"` 的下一頁連結(實測:第 33 頁有、第 34 頁沒有)。規格檔先寫 (a) | S2、S5 | (b)看下一頁連結,取代 Q32 的 (a);S2、S5 跟著改(kevin-twin 代為決定) |
| Q55 | S2 | 5xx 歸 `LIBRARY_SERVER_ERROR`(Q23),三個操作都改。(a)三個都改(先採用);(b)只改 searchLibrary | S5 | (a);S5 的模型庫相關操作補 `LIBRARY_SERVER_ERROR`(kevin-twin 代為決定) |
| Q56 | S2 | 下一頁連結因 ollama.com 改版消失時。(a)當成沒有下一頁,只是不出現「顯示更多」(先採用);(b)連結不見但滿 20 筆時歸 `LIBRARY_BAD_RESPONSE` | — | (a)(kevin-twin 代為決定) |
| Q57 | S9 | **與 spec 矛盾**:SC-002 原文「連線中斷後 2 分鐘內失聯」與重連時限 5 分鐘衝突。(a)被收回 2 分鐘內失聯、單純斷線 1 分鐘內重連中、時限到才失聯,改 SC-002(先採用);(b)重連時限縮為 2 分鐘;(c)中斷即失聯 | S5 | (a);spec SC-002 已改寫(kevin-twin 代為決定) |
| Q58 | S8 | **與 spec 矛盾**:new 300 秒加初始化 300 秒,最壞超過 SC-001 的 5 分鐘。(a)照各步驟時限(先採用);(b)開啟流程另設總時限 | S5 | (b)開啟流程總時限 5 分鐘,到了即開啟失敗並釋放;spec SC-001 已補上(kevin-twin 代為決定) |
| Q59 | S8 | CLI 的 `colab.log` 會寫入含 Authorization token 的 DEBUG 紀錄,無法關閉。(a)當成受限資料夾的一部分(會使 NFR-010「不出現在日誌」不成立);(b)S10 把 `colab.log` 指到 `/dev/null`,並把 `enable_update_check` 設為 false(先採用) | S10 | (b)(kevin-twin 代為決定) |
| Q60 | S8 | 約定外新增 `COLAB_ALLOCATION_REFUSED`、`COLAB_ACCELERATOR_REJECTED`、`COLAB_REMOTE_ERROR`、`COLAB_STOP_UNCONFIRMED`、`COLAB_UNSUPPORTED_VERSION`。(a)保留(先採用);(b)併入 | — | (a)(kevin-twin 代為決定) |
| Q61 | S8 | `AUTH_REQUIRED` 放不進 S5 `ReasonCode` 的前綴 pattern。(a)S5 放寬 pattern 允許 `AUTH_REQUIRED`(先採用);(b)另造 `COLAB_AUTH_REQUIRED`(違反 Q26);(c)logged_out 時 reasonCode 為 null | S5 | (a)(kevin-twin 代為決定) |
| Q62 | S8 | 可用顯示記憶體用總量或剩餘量。(a)總量(先採用);(b)剩餘量 | S5 | (a)(kevin-twin 代為決定) |
| Q63 | S8 | 開啟中途按結束或 new 逾時。(a)不中途終止,等子行程結束再 stop;逾時被終止時比對前後的 unnamed 清單,多出一台且硬體相符即視為遺留並警告(先採用);(b)立即終止 | — | (a)(kevin-twin 代為決定) |
| Q64 | S9 | `colab ssh --proxy-mode -s <名稱>` 找不到名稱會自己開新執行環境(讀原始碼,未實測)。(a)建立前先以 `colab sessions` 確認在列、不帶 `--gpu` 等旗標,stderr 出現 `Creating runtime` 立即關閉並交 S8 stop,回 `TUNNEL_NOT_FOUND`(先採用);(b)自寫 WebSocket 代理 | — | (a);列入 testplan 實跑護欄(kevin-twin 代為決定) |
| Q65 | S9 | 約定外新增 `TUNNEL_KEY_REJECTED`、`TUNNEL_TOKEN_REJECTED`、`TUNNEL_ALREADY_CONNECTED`、`TUNNEL_PORT_IN_USE`、`TUNNEL_REMOTE_REFUSED`,沿用 `TUNNEL_SERVER_ERROR`。(a)保留(先採用);(b)併入 `TUNNEL_FAILED` | S5 | (a);S5 的 ReasonCode 已涵蓋 `TUNNEL_` 前綴(kevin-twin 代為決定) |
| Q66 | S9 | `_FAILED` 判定:ssh 結束即失敗、不看 exit code;stderr 比對不到才是 `TUNNEL_FAILED`,附上的最後一行遮蔽網址與 token;不設 `LogLevel=ERROR`(先採用) | — | 照先採用;OpenSSH 錯誤字樣列入 testplan 實跑(kevin-twin 代為決定) |
| Q67 | S9 | 重連節奏:立即、5、10、20 秒,之後每 30 秒;每輪先關閉、查 sessions(不在即失聯 `RECLAIMED_BY_COLAB`)、再建立;時限固定 5 分鐘不可設定;逾時 `TUNNEL_TIMEOUT` 帶 `lastCode`(先採用) | — | 照先採用(kevin-twin 代為決定) |
| Q68 | S9 | 開啟時就緒期限:每 0.5 秒打 `/api/version`,30 秒內就緒;失敗 5 秒後重試一次(先採用) | — | 照先採用(kevin-twin 代為決定) |
| Q69 | S9 | 斷線後多久才能再連(半開連線何時被放掉,未實測)。(a)列入 testplan 實跑(先採用);(b)另訂處理 | — | (a)(kevin-twin 代為決定) |
| Q70 | S9 | 健康檢查一次失敗即進重連中,S6 遇 `OLLAMA_UNREACHABLE`/`OLLAMA_STREAM_INTERRUPTED` 立即加做一次(先採用);(b)連續 2 次 | — | (a)(kevin-twin 代為決定) |
| Q71 | S9 | Ollama 掛了但執行環境還在(`TUNNEL_REMOTE_REFUSED`)。(a)照一般重連,5 分鐘後失聯(先採用);(b)S8 以 exec 重啟 Ollama | — | (a)(kevin-twin 代為決定) |
| Q72 | S9 | 金鑰與 port:容器專用 ed25519,不存在才 `ssh-keygen`,不覆寫既有;回應只給類型與指紋;路徑由 S10 定;本機 port 預設 11435、只綁 127.0.0.1,S11 不得發布到區網(先採用) | S10、S11 | 照先採用(kevin-twin 代為決定) |
| Q73 | S9 | S8 的遠端指令只能走 `colab exec`,不得另開 `colab ssh`(同一台只能一條,HTTP 429)(先採用) | — | 照先採用;S8 現行規格已只用 exec(kevin-twin 代為決定) |
| Q74 | S7 | 後端重啟時正在下載的那一筆。(a)改回 queued 重新 pull(先採用);(b)改 failed | — | (a)(kevin-twin 代為決定) |
| Q75 | S7 | `last_request_at` 是否存。(a)存,重啟後倒數接著算(先採用);(b)不存 | — | (a)(kevin-twin 代為決定) |
| Q76 | S7 | 用量快照。(a)只留最後一筆(先採用);(b)保留歷史;(c)不存 | — | (a)(kevin-twin 代為決定) |
| Q77 | S7 | 「最多一個」的唯一性:輔助欄位 `active_slot`、`pending_model` 配 unique,`ending` 不佔位(先採用);(b)只靠應用程式;(c)另寫 partial index | — | (a)(kevin-twin 代為決定) |
| Q78 | S7 | 重新排隊的順序:內部欄位 `queue_position` 取最大值加 1(先採用);(b)改 `added_at` | — | (a)(kevin-twin 代為決定) |
| Q79 | S7 | 工作階段紀錄是否定期清除。(a)本迭代不清(先採用);(b)只留 N 筆 | — | (a)(kevin-twin 代為決定) |
| Q80 | S7 | 舊工作階段下載完成的項目。(a)保留到使用者清除(先採用);(b)結束時自動清;(c)記錄所屬工作階段 | — | (a)(kevin-twin 代為決定) |
| Q81 | S10 | 主機資料位置。(a)`${CGB_HOST_DATA:-cgb-data}`,留空用 named volume、填路徑即 bind mount(先採用);(b)必填;(c)`./data`(有把機密 commit 進 repo 的風險) | S11 | (a)(kevin-twin 代為決定) |
| Q82 | S10 | 既有的一般檔 `colab.log`。(a)刪掉換成指向 `/dev/null` 的連結(先採用);(b)改名保留;(c)啟動失敗 | — | (a)(kevin-twin 代為決定) |
| Q83 | S10 | CLI 的 `history/` 含 endpoint 與 exec 輸出。(a)掛 tmpfs(先採用);(b)持久化於 0700;(c)每次啟動清除 | S11 | (a);不屬本系統日誌,容器停止即消失(kevin-twin 代為決定) |
| Q84 | S10 | 容器執行使用者。(a)root(先採用);(b)非 root | — | (a)(kevin-twin 代為決定) |
| Q85 | S10 | Dockerfile 與 compose 位置。(a)留在 spec 的 `deploy/`(先採用);(b)implement 時搬到 repo 根目錄,符合 plan.md Source Code 樹 | — | (b)(kevin-twin 代為決定) |
| Q86 | S10 | 與 S11 的分工:本步驟不寫 ports、listen 位址、HTTP 健康檢查;已加 `init: true`(tini 回收 ssh 子行程) | S11 | 照先採用;S11 保留 `init: true` 與 `/data` 健康檢查(kevin-twin 代為決定) |
| Q87 | S10 | 後端寫檔約定:讀 `CGB_DATA_DIR`、`CGB_DB_PATH`、`CGB_COLAB_CONFIG_DIR`、`CGB_SSH_IDENTITY_PATH`,權限靠 umask 077(先採用) | — | (a)(kevin-twin 代為決定) |
| Q88 | S10 | 搬上 Unraid 的資料位置:SQLite WAL 不放 `/mnt/user` FUSE,建議 cache/pool 的 appdata 實際路徑;備份目的地要權限受限。(a)只在 `.env.example` 提醒(先採用);(b)另寫部署說明 | — | (a)(kevin-twin 代為決定) |
