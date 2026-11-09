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
| Q89 | S11 | 健康檢查會重設閒置計時(FR-026)。(a)Ollama port 只確認 TCP、UI port 送 `GET /api/session`(先採用);(b)S6 排除 127.0.0.1 的檢查請求;(c)不檢查 Ollama port | — | (a)(kevin-twin 代為決定) |
| Q90 | S11 | 桌機 11434 已被使用者的 Ollama 占用。(a)預設 11434,桌機驗收在 `.env` 填 `CGB_HOST_OLLAMA_PORT=11436`(先採用);(b)停掉使用者的 Ollama;(c)預設改用別的 port | — | (a)(kevin-twin 代為決定) |
| Q91 | S11 | UI port。(a)8780,可用 `CGB_HOST_UI_PORT` 改(先採用);Tower 上是否被占用待搬遷前確認 | — | (a)(kevin-twin 代為決定) |
| Q92 | S11 | 綁定位址。(a)預設 `0.0.0.0`,不對外網靠路由器不轉發,可用 `CGB_BIND_ADDR` 限縮;Docker 發布的 port 不經 ufw(先採用);(b)`CGB_BIND_ADDR` 必填 | — | (a)(kevin-twin 代為決定) |
| Q93 | S11 | 單一行程 `python -m cgb` 跑兩個 uvicorn,環境變數 `CGB_LISTEN_HOST`、`CGB_UI_PORT`、`CGB_OLLAMA_PORT`、`CGB_TUNNEL_LOCAL_PORT`(先採用);(b)兩個行程 | — | (a)(kevin-twin 代為決定) |
| Q94 | S11 | 為放行 `healthcheck.py` 在 S10 的 `Dockerfile.dockerignore` 加一行。(a)維持(先採用);(b)改成 compose 內單行 python | — | (a)(kevin-twin 代為決定) |
| Q95 | tasks | 〔testplan 提出〕測試縮短時限、固定名稱。(a)`create_app` 參數注入時鐘、時限與名稱前綴,實跑前綴 `cgb-test-`(先採用);(b)環境變數;(c)真時間 | — | (a)(kevin-twin 代為決定) |
| Q96 | tasks | 〔testplan 提出〕替身形式:E2/E3 注入 5 個 Fake 類別;E5/E6 用假執行檔 `tests/fixtures/bin/colab`、`ssh`;E7 假 HTTP 伺服器;E8/E9 `httpx.MockTransport`;方法名為 operationId 的 snake_case(先採用) | — | 照先採用(kevin-twin 代為決定) |
| Q97 | tasks | 〔testplan 提出〕SSE 與逐段傳回 ASGI transport 看不出來(判斷)。(a)測試行程內起 uvicorn(先採用);(b)改輪詢 | — | (a)(kevin-twin 代為決定) |
| Q98 | tasks | 〔testplan 提出〕E4 公開接縫。(a)只測 `db` 建立的 schema,以 sqlite3 直接下 SQL(先採用);(b)另定 repos 介面 | — | (a)(kevin-twin 代為決定) |
| Q99 | tasks | 〔testplan 提出〕跨端點驗收的後端。(a)測試行程內起 uvicorn(UI 8781、Ollama 11437),替身由測試操控(先採用);(b)起容器 | — | (a)(kevin-twin 代為決定) |
| Q100 | tasks | 〔testplan 提出〕**與 spec 矛盾**:遺留判定。(a')以本系統資料庫 sessions 表的名稱為準,S8 listSessions 說明跟著改;(b')看 `cgb-` 前綴(正式與測試實例會互關)。(a') 在資料庫遺失時使 FR-007「發現遺留必須釋放」不成立。重連流程由 services 組成 | S8 | (a');資料庫不認得、CLI 記得的執行環境一律在 UI 警告(對應 FR-007 後半句)(kevin-twin 代為決定) |
| Q101 | tasks | 〔testplan 提出〕實跑的授權來源。(a)由 US1-OA-06 在暫存目錄登入(需使用者);(b)複製桌機既有 `token.json` 到暫存目錄,只比對 sha256 | — | (b);US1-OA-06 與 G-01 需本人,延後到使用者回來(kevin-twin 代為決定) |
| Q102 | tasks | 〔testplan 提出〕FR-010 實跑換哪種類型。(a)T4 換 T4 高 RAM(先採用);(b)T4 換 L4 | — | (a)(kevin-twin 代為決定) |
| Q103 | tasks | 〔testplan 提出〕實跑時模擬收回與斷線。(a)收回用 `colab stop`、斷線用 SIGKILL 殺 ssh(先採用);(b)等真的回收 | — | (a)(kevin-twin 代為決定) |
| Q104 | tasks | 〔testplan 提出〕NFR-003 實跑確認。(a)`colab exec -f listen_check.py` 唯讀查監聽位址,加 `docker port` 與主機直連 11435(先採用);(b)只看命令列 | — | (a)(kevin-twin 代為決定) |
| Q105 | tasks | 〔testplan 提出〕NFR-011 檢查用的詞表。(a)語言.md Rule 1 對照詞(先採用);(b)簡繁轉換套件 | — | (a)(kevin-twin 代為決定) |
| Q106 | tasks | 〔testplan 提出〕`store.dbml` 的 `sessions.reason_code` 說明缺 `AUTH_REQUIRED`(與 Q61 不一致)。(a)補改 dbml 說明(先採用);(b)維持 | S7 | (a)(kevin-twin 代為決定) |
| Q107 | tasks | 〔testplan 提出〕預估下載時間的 MB 與取整。(a)MB 以 10^6 位元組計,案例斷言落在捨去與進位之間(先採用);(b)無條件進位 | — | (a)(kevin-twin 代為決定) |
| Q108 | tasks | 〔testplan 提出〕19 個實跑案例照第 1 節護欄 P1–P9 執行(上限 2 compute units、60 分鐘、前綴 `cgb-test-`、桌機 UI 8780/Ollama 11436、暫存資料夾)。(a)照護欄執行;(b)不跑 | — | (a);需本人的 US1-OA-06、G-01 延後(kevin-twin 代為決定) |
| Q109 | S8 | S5 `Session.name` pattern 寫死 `^cgb-`,與 Q95 可注入前綴衝突。(a)S5 放寬成不寫死前綴(先採用);(b)維持 `cgb-`,規定注入的前綴必須以 `cgb-` 開頭(實跑的 `cgb-test-` 符合) | — | (b),不必重做 S5(kevin-twin 代為決定) |
| Q110 | tasks | 故事 4 的 15 個介面元素(用量、設定、閒置相關)沒有任務,`check_tasks.py` 不過,implement Phase 1 Step 2 因此無法開工。(a)列為範疇外,接受不過;(b)故事 4 拉回本迭代範疇,testplan 補案例、tasks 補任務;(c)掛在 Setup 的 `§ 全檔` 讓檢查通過 | — | (b)範疇改為故事 1–4;推翻 testplan 範疇「故事 1、2、3」的決定(kevin-twin 代為決定) |
| Q111 | tasks | G-06 要不要看用量頁。(a)只看範疇內畫面;(b)也看用量頁 | — | (b),因 Q110 故事 4 已納入範疇(kevin-twin 代為決定) |
| Q112 | tasks | Setup 放 `create_app` 注入點與 `AdapterError`(只有簽章與空 app)。(a)放 Setup(先採用);(b)併入 US1-API-01 綠燈 | — | (a)(kevin-twin 代為決定) |
| Q113 | tasks | `python -m cgb` 進入點。(a)放進 US1-AJ-01 綠燈 T131b,測試 uvicorn fixture 走同一個 `serve()`(先採用);(b)testplan 補子行程案例;(c)放 Setup | — | (a)(kevin-twin 代為決定) |
| Q114 | tasks | G-03、G-04、G-08 紅燈可能一開始就綠。(a)紅燈先對故意改壞的對照組確認抓得到,再對實物執行(先採用);(b)全域綠燈才搬入 | — | (a)(kevin-twin 代為決定) |
| Q115 | tasks | 外部程式參數交給真工具解讀。(a)E5 在 T061a 以真 `colab` 0.7.5(空暫存 HOME、無授權)只斷言無參數錯誤;E6 在 T100a 以 `ssh -G` 解讀(先採用);(b)只靠實跑 | — | (a)(kevin-twin 代為決定) |
| Q116 | tasks | 📏 實跑任務排法。(a)照規範排在各故事,Checkpoint 註明整批延到全域測試區後依 P9 執行(先採用);(b)全部標 ⏸;(c)全部移到全域 | — | (a)(kevin-twin 代為決定) |
| Q117 | tasks | 14 個範疇內畫面狀態只有 G-06 走得到。(a)由 G-06 綠燈 T250b 做出(先採用);(b)testplan 補故事內案例 | — | (a)(kevin-twin 代為決定) |
| Q118 | tasks | Q85 搬遷後的位置。(a)Dockerfile、dockerignore、compose、.env.example 放根目錄,prepare-data.sh、healthcheck.py 放 repo 的 `deploy/`(先採用);(b)全放 `deploy/` | — | (a)(kevin-twin 代為決定) |
| Q119 | tasks | 〔testplan 提出〕讀過用量但最近一次失敗時 `GET /api/usage`。(a)回最後快照,超過 15 分鐘標 `stale` 並說明讀取失敗,`unknown` 只用在從沒讀到過(先採用);(b)一律 `unknown`(會使 NFR-008 做不到) | — | (a)(kevin-twin 代為決定) |
| Q120 | tasks | 〔testplan 提出〕餘額 ≤ 0 時估計可用時數。(a)回 0(先採用);(b)負數;(c)null | — | (a)(kevin-twin 代為決定) |
| Q121 | tasks | 〔testplan 提出〕FR-025「低於警告門檻」含不含等於。(a)不含 `<`(先採用);(b)含 | — | (a)(kevin-twin 代為決定) |
| Q122 | tasks | 〔testplan 提出〕Q100 的「資料庫不認得、CLI 記得」警告放哪。(a)`Session.unmanagedRuntimes` 加一筆(先採用);(b)併入 `releaseWarning` | S5 | (a)(kevin-twin 代為決定) |
| Q123 | S5 | 讀取用量失敗的說明欄位。(a)沿用 `reasonCode`、`message`,新增 `lastFailedAt`(先採用);(b)巢狀 `lastReadError`。另:故事 4 驗收情境 5「讀不到 → 未知」與 Q119 不一致 | — | (a);spec 情境 5 改為「從來沒讀到過」(kevin-twin 代為決定) |
| Q124 | implement T004 | 替身方法名與 operationId 不完全一致(`ensure_key`、`check_health`、`build_authorization_url`、`cleanup_residual`)。(a)維持任務列出、testplan 受測操作表使用的名稱;(b)改照 operationId | — | (a)(kevin-twin 代為決定) |
| Q125 | implement T006 | 下一頁連結:任務寫 `hx-get="/search?page=2"`,合約寫含 `&q=<關鍵字>`。(a)照合約;(b)照任務原文 | — | (a)照合約(kevin-twin 代為決定) |
| Q126 | implement T008 | P8「錄下的輸出 P3 之後刪除」與 G-05、G-07 要在 P3 之後讀取的順序。(a)`p3_cleanup()` 可中途呼叫,刪除只在整批結束時最後一次 P3 之後;(b)其他 | — | (a)(kevin-twin 代為決定) |
| Q127 | implement T014 | spec 原檔 `healthcheck.py` 權限 0664,任務寫「保留可執行權限」。(a)複本設 755(Dockerfile 本來也 chmod 755);(b)照原檔 0664 | — | (a)(kevin-twin 代為決定) |
| Q128 | implement T004 | 替身一律 async;真實的 `build_authorization_url` 可能是同步。(a)綠燈任務視需要調整替身或介面;(b)現在改 | — | (a)(kevin-twin 代為決定) |
| Q129 | implement T122 | 〔任務 T122b〕授權檔由誰寫:轉接層在換 token 時寫(US1-OA-02、04 在轉接層驗),但 E2 的 `FakeGoogleOAuth` 不寫檔、US1-API-31 則3 要 token.json 存在。(a)E2 測試用替身的 side_effect 寫檔;(b)轉接層回內容、service 寫檔 | — | (a)(kevin-twin 代為決定) |
| Q130 | implement T122 | 〔任務 T122b〕換 token 用 httpx 而非 google-auth-oauthlib 的 `fetch_token`(後者走 requests,MockTransport 攔不到)。(a)授權網址用真 `InstalledAppFlow`、換 token 用 httpx、授權檔用 `Credentials.to_json()`;(b)改用 `fetch_token` 加假本機端點 | — | (a);CLI 讀檔由 US1-OA-06 實跑驗證(kevin-twin 代為決定) |
| Q131 | implement T125 | 〔任務 T125b〕合約有、testplan 沒有案例的 OAuth 行為(本文非 JSON、200 缺 `access_token`/`expires_in`、轉接層去空白、缺 `scope`)。(a)本迭代不補,列入完成報告的未覆蓋;(b)補案例 | — | (a)(kevin-twin 代為決定) |
| Q132 | implement T122 | 〔任務 T122b〕授權檔 expiry 用系統時間而非注入的 Clock,目前沒有測試看它。(a)記錄,不處理;(b)改用 Clock | — | (a)(kevin-twin 代為決定) |
| Q133 | implement T056 | 〔任務 T056b〕`src/cgb/domain/colab_output.py` 未建立(派工限制禁止動 domain/,由 E2 負責),解析全部放在 `colab_cli.py`。(a)維持;(b)之後搬到 domain | — | (a)(kevin-twin 代為決定) |
| Q134 | implement T076 | **合約有、testplan 沒有案例而未實作的 E5 失敗規則**:new/exec/stop/usage/version 的子行程時限、stderr 判定的 `COLAB_UNREACHABLE`/`COLAB_TIMEOUT`、sessions/new/exec/stop 的 `AUTH_REQUIRED`、`COLAB_ALLOCATION_REFUSED`、`COLAB_ACCELERATOR_REJECTED`、非 0 結束的 `COLAB_FAILED`、new 缺 `Session READY.` 的 `COLAB_BAD_RESPONSE`、exec 的 `COLAB_NOT_FOUND`/`ok:false`/無結果行。(a)補 testplan 案例與 tasks 後照 TDD 實作;(b)直接照合約補程式;(c)列為未覆蓋 | — | (a);擋住 T077 與跨端點驗收的實跑(實跑前必須完成);逾時缺失會讓實跑卡住扣點,必須在實跑前補上(E9 的 Q131 維持不補)(kevin-twin 代為決定) |
| Q135 | implement T063 | 〔任務 T063b〕gpu 不在 GpuType 時丟 `ValueError`(合約無輸入錯誤代碼)。(a)維持;(b)另定代碼 | — | (a)(kevin-twin 代為決定) |
| Q136 | implement T076 | 重構時 `_run` 統一處理找不到執行檔、`start_ollama` 連續兩次斷線改回 `COLAB_UNREACHABLE`,改動了沒有測試的路徑(與合約一致)。(a)接受;(b)撤回 | — | (a);由 Q134 補的案例覆蓋(kevin-twin 代為決定) |
| Q137 | implement T066 | 〔任務 T066b〕`start_ollama.py`、`probe_resources.py` 遠端腳本本節沒有測試實際執行。(a)由 US2-CLI-01 與實跑 US1-CLI-21 驗證;(b)另補 | — | (a)(kevin-twin 代為決定) |
| Q138 | tasks | 〔testplan 提出〕子行程逾時要不要清掉它分出的子行程(合約只寫「被終止」)。(a)以新 process group 啟動,逾時對整個 group 先 SIGTERM、等不到再 SIGKILL 並回收,S8 合約補這一句;(b)只終止 colab 本身 | S8 | (a)(kevin-twin 代為決定) |
| Q139 | tasks | 〔testplan 提出〕`colab stop` 本身逾時。(a)終止後照常回讀,以回讀為準,只有回讀逾時才回 `COLAB_TIMEOUT`;(b)直接回 `COLAB_TIMEOUT` | — | (a)(kevin-twin 代為決定) |
| Q140 | tasks | 〔testplan 提出〕exec 的 `appears to be lost (404/401)` 比對 stdout 或 stderr。(a)兩個都看;(b)只看 stdout | — | (a)(kevin-twin 代為決定) |
| Q141 | implement T101 | 〔任務 T101b〕**open_tunnel 失敗收尾可能卡死**:同步 `_stop_group` 只送 SIGTERM 再 `wait()`,子行程忽略 SIGTERM 就無限卡住並阻塞事件迴圈。(a)改用 close_tunnel 的 SIGTERM→等待→SIGKILL;(b)維持。行為改變,不屬重構 | — | (a);先補 testplan 案例再照 TDD 改(同 Q134)(kevin-twin 代為決定) |
| Q142 | implement T106 | 〔任務 T106b〕合約有、testplan 沒有案例的 E6 分支:`TUNNEL_NOT_INSTALLED`(找不到 ssh/ssh-keygen,現在丟 FileNotFoundError)、ssh-keygen 10 秒逾時、close_tunnel/ensure_key 的 `TUNNEL_FAILED`;已實作但無測試:check_health 的 `TUNNEL_UNREACHABLE`/`TUNNEL_REMOTE_REFUSED`/`TUNNEL_NOT_FOUND`。開啟的「5 秒後重試一次」屬 services。(a)補 testplan 案例;(b)由 services 負責 | — | (a)補案例(重試仍歸 services/E2)(kevin-twin 代為決定) |
| Q143 | implement T106 | 〔任務 T106a〕US1-TUN-08 的假 ssh 由 python 執行,命令列不以 `ssh` 開頭;測試改寫 `/proc/self/cmdline`。(a)接受;(b)fixture 另提供命令列即 `ssh …` 的假行程 | — | (a)(kevin-twin 代為決定) |
| Q144 | implement T100 | 〔任務 T100a〕`ssh -G` 不給目的地會印 usage,所以保留目的地 `root@colab-runtime`、只把 `-N` 換 `-G`。(a)接受;(b)其他 | — | (a)(kevin-twin 代為決定) |
| Q145 | tasks | 〔tasks 提出〕補充的 20 個 E5 案例可能在既有實作下一開始就是綠的(逾時、stderr 判定)。(a)紅燈先對放入「要抓的錯」的對照組確認抓得到,再記「既有實作已滿足」,綠燈只跑全部測試;(b)照 tdd 原樣,不過就停下 | — | (a),同觀察 #23(kevin-twin 代為決定) |
| Q146 | tasks | 〔tasks 提出〕Q134 在 E5 後新增一節 T078a–T098,為通過連號與紅綠成對檢查,原 T078–T260 整批改為 T099–T281;plan.md 的引用已同步加 21,已勾選的任務隨原行保留 | — | 已同步(本列為紀錄)(kevin-twin 代為決定) |
| Q147 | tasks | 〔testplan 提出〕ssh-keygen 逾時回哪個代碼。(a)照合約 `TUNNEL_FAILED`;(b)改合約為 `TUNNEL_TIMEOUT` | — | (a)(kevin-twin 代為決定) |
| Q148 | tasks | 〔testplan 提出〕`ensureTunnelKey`「第一行 stdout 為空 → `TUNNEL_FAILED`」照字面永遠失敗(`ssh-keygen -q` 成功時本來就沒輸出)。(a)讀成「第一行跑完後 keyPath 仍不存在」,S9 合約改寫;(b)照字面 | S9 | (a)(kevin-twin 代為決定) |
| Q149 | tasks | 〔testplan 提出〕ssh-keygen 10 秒時限在測試中縮短。(a)`Tunnel` 建構參數加 `keygen_timeout`;(b)不縮短 | — | (a)(kevin-twin 代為決定) |
| Q150 | tasks | 〔tasks 提出〕Q141、Q142 在 E6 後新增一節 T110a–T120,原 T110–T281 整批改為 T121–T292(Q146 那次之後的第二次平移);plan.md 的引用已同步加 11,Q146 保留當時的編號作為紀錄 | — | 已同步(本列為紀錄)(kevin-twin 代為決定) |
| Q151 | implement T095 | 〔任務 T095b〕exec 重跑後的輸出沒有再判一次 `COLAB_NOT_FOUND`(第二次輸出 not found/lost 時落到 `COLAB_BAD_RESPONSE`)。(a)補案例;(b)維持,列為未覆蓋 | — | (b);不會造成卡住或扣點,列入完成報告的未覆蓋(kevin-twin 代為決定) |
| Q152 | implement T097 | 〔任務 T097b〕`probe_resources` 成功時仍回 `{}`,由 US3-CLI-01/02 補。(a)照計畫由故事 3 補;(b)現在補 | — | (a);E2 不得依賴其回傳值(kevin-twin 代為決定) |
| Q153 | implement T078 | 〔任務 T078b〕實作途中桌機曾留下一個假 colab 分出的 `sleep` 子行程,根因未明;測試檔加了每個測試結束時清除子行程的 fixture。主 agent 連跑逾時測試 20 次,本 pytest 結束時皆無持續殘留(唯一一次的計數出現在本 pytest 結束 2 秒後,來自同時執行的 E2 全套測試)。(a)接受,實跑階段再以 ps 確認;(b)另外排查 | — | (a)(kevin-twin 代為決定) |
| Q154 | implement T032 | 〔任務 T032a/b、T045a/b〕US1-API-18、US1-API-31 要斷言 SSE 事件,但 SSE 在 T052b 才建立,兩組任務排在它之前。(a)T052b 之後補做;(b)讓它們改 events 相關檔;(c)改成輪詢 | — | (a)(kevin-twin 代為決定) |
| Q155 | implement T015 | 多個 🟢 要靠描述沒列的檔才做得出 ⚙ 元素(app.py 掛載、`GET /api/auth`、restart 路由、download_jobs 表、session_transitions 表、lifespan 接線、listeners 掛點等,E2 回報已逐一列出)。(a)追認;(b)補進 tasks 描述 | — | (a)(kevin-twin 代為決定) |
| Q156 | implement T053 | US1-API-39 的 verifying 步驟要多一個閘門(`remote_ollama.get_version`)才看得到。(a)追認;(b)testplan 改四個閘門 | — | (a)(kevin-twin 代為決定) |
| Q157 | implement T039 | `unmanagedRuntimes` 在 `state: none` 時也附上(合約說 none 時其他欄位都沒有,但 US1-API-25 要看得到)。(a)放寬合約描述;(b)另設欄位 | — | (a);合約說明於下次 api-plan 修訂時一併放寬(kevin-twin 代為決定) |
| Q158 | implement T015 | 工作階段名稱 `<前綴><yyyymmdd>-<hhmmss>-<4 碼十六進位>`,同秒開兩次 1/65536 撞名。(a)維持;(b)加長亂數 | — | (a);FR-006 一次只有一個工作階段,同秒連開已被 409 擋下(kevin-twin 代為決定) |
| Q159 | implement T055 | **替身擋住了呼叫端與真 adapter 的參數不一致**:`health_monitor.py` 重連呼叫 `open_tunnel(session_name=)`,真 `Tunnel.open_tunnel` 必填 `key_path`、`local_port`,實跑必丟 TypeError;另 `recovery.py` 釋放遺留失敗時沒有警告(FR-007)。(a)testplan 補全域案例「每個替身方法簽章與真 adapter 相同」與跨端點案例「recovery 釋放失敗要警告」,照 TDD 修;(b)直接修兩處;(c)留給實跑 | — | (a)(kevin-twin 代為決定) |
| Q160 | tasks | 〔testplan 提出〕G-09 比對範圍。(a)只比真 adapter 有的公開方法,替身另有的測試控制成員不比;(b)替身不得有真 adapter 沒有的公開成員 | — | (a)(kevin-twin 代為決定) |
| Q161 | tasks | 〔testplan 提出〕重啟接回時釋放遺留失敗,`releaseWarning` 掛在哪。(a)掛在 `GET /api/session` 回的那筆工作階段的 `release_warning_*`;(b)另立欄位(S5 要改) | — | (a)(kevin-twin 代為決定) |
| Q162 | tasks | 〔tasks 提出〕Q159 補 US1-AJ-23(T147a/b)與 G-09(T290a/b),原 T147–T288 加 1、原 T289–T292 加 2,最後一個任務成為 T294(第三次平移,只動未勾選的任務);plan.md 引用已同步 | — | 已同步(本列為紀錄)(kevin-twin 代為決定) |
| Q163 | implement T045 | 〔任務 T045b〕授權碼去掉空白後為空字串時,合約要回 400 `INVALID_AUTH_CODE`,testplan 沒有案例、未實作。(a)列為未覆蓋;(b)補案例 | — | (a);無花費風險,同 Q131 列入完成報告的未覆蓋(kevin-twin 代為決定) |
| Q164 | implement T081 | 〔任務 T081a,E5 補充〕`test_stop_that_times_out_is_still_judged_by_session_list` 平行時約 1/13 會紅(斷言耗時 ≤ 1.5 秒)。主 agent 在無平行時全部測試連跑 3 次皆 205 passed、單獨 10 次皆過。(a)放寬時間餘裕;(b)維持,實跑時留意 | — | (b)(kevin-twin 代為決定) |
| Q165 | implement T111 | 〔任務 T111b〕`_ended` 先等 stderr 讀完(最多 1 秒)再收尾整個 group;真 ProxyCommand 佔著 stderr,失敗回報固定多等 1 秒,不卡事件迴圈。(a)先收尾再讀 stderr;(b)維持 | — | (b)(kevin-twin 代為決定) |
| Q166 | implement T140 | 〔任務 T140a〕US1-AJ-10 要「L4 勾高 RAM」,但原型與 colab-cli 合約 L4 不支援高 RAM、勾選框停用。(a)testplan 改用 G4 加高 RAM;(b)原型改成 L4 也能勾 | T140a、T140b | (a)(kevin-twin 代為決定) |
| Q167 | implement T144 | 〔任務 T144b〕`[data-state="resuming"]` 接回期間 API 無欄位可分辨。(a)recovery 接回期間報 reconnecting;(b)照 Q117 留給 G-06(T250b);(c)接受 ⚙ 不完整 | T250b | (b)(kevin-twin 代為決定) |
| Q168 | implement T138 | 〔任務 T138b、T141b〕越界改檔:T138b 在 `static/index.html` 加 `needs-login` 區塊(⚙ 列的元素);T141b 在 `api/__init__.py` 掛 `models.router`。(a)追認;(b)撤回另開任務 | — | (a);照 Q155(a) 前例(kevin-twin 代為決定) |
| Q169 | implement T147 | 〔任務 T147b〕服務層寫死 `TUNNEL_LOCAL_PORT = 11435`,`CGB_TUNNEL_LOCAL_PORT` 不生效;`HealthMonitor` 自讀 `CGB_SSH_IDENTITY_PATH`,預設值寫兩份。(a)Phase 6 重構時從 `AppState` 注入;(b)列入完成報告,compose 先用預設值 | — | (b);compose 的值與預設一致,不影響本次迭代(kevin-twin 代為決定) |
