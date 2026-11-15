# 系統分析規劃: 讓 opencode 與 pi 輕鬆接上 Colab 上的 Ollama

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Techstack**: [techstack.md](./techstack.md) | **Date**: 2026-11-16

建立在前一次迭代 [005-ollama-machine-tuning 的 plan.md](../005-ollama-machine-tuning/plan.md) 之上;端點編號照 005 沿用 001 的 [plan.md](../001-session-model-catalog/plan.md)(E1~E12),這一輪沒有新的端點。

## Project Structure

### Documentation (this feature)

```text
specs/006-agent-client-connect/
├── spec.md              # 輸入(specify 產出)
├── research.md          # 輸入(technical-research 產出)
├── techstack.md         # 輸入(technical-research 產出)
├── plan.md              # 本文件
├── prototype/           # S4 產出(E1 前端 UI,ui-plan)
├── deploy/              # S2 產出(E11 部署與網路,deploy-plan)
└── contracts/
    ├── ollama-compat.openapi.yaml   # S1 產出(E3 Ollama 相容端點,api-plan)
    └── ui.openapi.yaml              # S3 產出(E2 後端 UI API,api-plan)
```

### Source Code (repository root)

```text
src/cgb/
├── ollama_compat/routes.py     # E3:白名單加 /v1/chat/completions、/v1/models;/v1 的錯誤用 OpenAI 格式
├── ollama_compat/forward.py    # E3:SSE 中途斷線時補 data: 錯誤段與 [DONE]
├── domain/connect.py           # 新增:片段產生與 context 建議值(純函式)
├── api/connect.py              # 新增:E2 連線資訊(相容端點的 port、目前 context、建議值、模型清單)
├── config.py                   # 讀 CGB_PUBLIC_OLLAMA_PORT
└── static/                     # E1:新頁 connect.html 與 js/connect.js,導覽列加「連線設定」

compose.yaml                    # E11:把 CGB_HOST_OLLAMA_PORT 以 CGB_PUBLIC_OLLAMA_PORT 傳進容器

tests/
├── unit/                       # 片段格式、建議值、reserveTokens
├── integration/                # E3 /v1 白名單、錯誤格式、SSE 逐段;E2 連線資訊
├── e2e/                        # 連線設定畫面、一鍵複製、提醒
└── realrun/                    # SC-001、SC-002 接臨時 ollama serve(realrun_local);SC-004 真的 Colab
```

**Structure Decision**: 沿用 001 的單一 Python 專案與單一映像,不新增服務與掛載;只多傳一個環境變數。規格檔照 005 的做法以前一次的同名檔為底、只收這一輪新增或改變的部分:

- `ollama-compat.openapi.yaml` 以 001 的同名檔為底,只收 `/v1/chat/completions`、`/v1/models` 與 `/v1` 的錯誤格式;其他路徑以 001 的檔為準。
- `ui.openapi.yaml` 以 005 的同名檔為底,只收新的連線資訊操作。
- `deploy/` 是根目錄 `compose.yaml`、`.env.example` 的整份複本,差異只有 `CGB_PUBLIC_OLLAMA_PORT` 一行與一句說明;實作時只把這兩處搬到根目錄,不整份覆蓋(Q1、Q3)。

後端分層是 api → services → domain / repos / adapters:`api/connect.py` 組合目前工作階段的 Ollama 設定(005)與模型目錄(001),片段與建議值由 `domain/connect.py` 產生;相容端點仍在 `ollama_compat/`。

前端沿用原生 JS 分頁:新增 `connect.html` 與 `js/connect.js`,切換 opencode 與 pi 的分頁、一鍵複製;共用的狀態文字放 `view.js`。

## 分析流程規劃

> 本段排定分析的順序與每一步指派的 planner;分析由 Phase 3 照波段交給 sub agent 執行,產出寫在 Documentation 樹列的路徑。

### 端點盤點

這次需求涉及 4 個端點。每個端點視為一個獨立系統,分析的對象是它對外的介面:

| # | 端點 | 介面 | 需求出處 |
|---|---|---|---|
| E1 | 前端 UI(瀏覽器,原生 HTML/CSS/JS) | 畫面與互動:連線設定頁(opencode 與 pi 分頁、片段、一鍵複製、使用方式)、context 太小的提醒與建議值、讀不到設定、沒有工作階段或沒有模型時的說明 | FR-001–FR-008、FR-012、FR-013、NFR-002 |
| E2 | 後端 UI API(FastAPI REST 與 SSE) | 資源與錯誤:連線資訊(相容端點的 port、目前 context、建議值、模型清單、片段)、沒有工作階段時的回應 | FR-001、FR-002、FR-004–FR-008、FR-012、FR-013 |
| E3 | Ollama 相容端點(FastAPI 轉送) | 開放的 `/v1` 路徑、OpenAI 格式的錯誤、SSE 串流轉送與中途斷線 | FR-009–FR-011、NFR-001、SC-003 |
| E11 | 部署與網路(Docker Compose) | 環境變數:相容端點在主機上的 port 傳進容器 | FR-001、FR-004(位址,research R7) |

沒有列的 001 端點:E7 遠端 Ollama(它內建的 `/v1` 原樣轉送,介面以 Ollama 為準,research R1 已實測)、E4 資料庫(片段不儲存)、E5 Colab CLI、E6 SSH 通道、E8、E9、E10、E12(與這次無關)。

### 分析波段

排序原則:**一個介面排在它所依賴的介面都分析完之後**;同一波裡的介面彼此不依賴,可以各開一個 sub agent 平行分析。

第三方端點的介面是對方定好的,我們只能照著接、不能改,所以它不依賴我們任何一個介面;
反過來,我們這邊碰到它的介面都要遷就它。因此**第三方端點排在最前面**,依賴它的介面往後推一波。

| Wave | 步驟 | 介面 | Planner | 平行 | 排在這一波的理由 |
|---|---|---|---|---|---|
| 1 | S1 | E3 Ollama 相容端點 | api-plan | ✅ 與 S2 平行 | `/v1` 的請求與回應是遠端 Ollama(OpenAI 相容)定好的,research R1、R6 已實測;不依賴本系統其他介面 |
| 1 | S2 | E11 部署與網路 | deploy-plan | ✅ 與 S1 平行 | 只決定相容端點在主機上的 port 怎麼傳進容器(research R7),不依賴其他介面 |
| 2 | S3 | E2 後端 UI API | api-plan | ✅ 與 S4 平行 | 連線資訊裡的位址要照 S1 開放的路徑與 S2 傳進來的 port |
| 2 | S4 | E1 前端 UI | ui-plan | ✅ 與 S3 平行 | 由使用者故事推出;片段的 `/v1` 位址照 S1、S2。前端與後端以同一份需求為準,不必等對方 |

共 2 個 wave、4 個步驟:Wave 1 兩個介面平行,Wave 2 兩個介面平行。

## 待決問題

> Phase 3 每一波交回的待決問題都登記在這裡;有問題擋住下一波時,在下一波開始之前把所有還沒決定的一次問完,沒有擋住就等最後一波之後一起問。

| Q | 提出的步驟 | 問題與可選的做法 | 擋住 | 決定 |
|---|---|---|---|---|
| Q1 | S2 | `deploy/` 放整份還是只放改動的那一段:a 整份複本,plan.md 改寫成「差異只有一行」(先採用,檢查腳本要整份);b 只放片段 | — | a(分身決策紀錄 D9):plan.md Structure Decision 已改 |
| Q2 | S2 | 複本的 `x-requirements` 只列 006 的 FR-001、FR-004,001 的編號拿掉:a 照這樣(先採用);b 保留 001 的編號 | — | a(D9):根目錄 `compose.yaml` 維持原本的 `x-requirements` |
| Q3 | S2 | 複本 `build.context` 為 `../../..`,只在 `specs/006-agent-client-connect/deploy/` 成立:a 實作時只把 `CGB_PUBLIC_OLLAMA_PORT` 與說明搬到根目錄(先採用);b 整份覆蓋根目錄 | — | a(D9) |
| Q4 | S1 | `/v1` 串流中途補的錯誤段 `error.code`:a 與執行環境斷線補 `stream_interrupted`、工作階段被結束補 `no_ready_session`,`type` 都是 `api_error`(先採用);b 兩種同一個新代碼;c 另開 `session_ended` | — | a(D10) |
| Q5 | S1 | `/v1` 的逾時(001 的 504):a 本檔不收,照 001(先採用);b 補 504 `gateway_timeout` | — | a(D10) |
| Q6 | S1 | `/v1/{path}` 以單一操作代表所有方法:a 照這樣,描述寫明不論方法(先採用);b 每個方法各一個操作 | — | a(D10) |
