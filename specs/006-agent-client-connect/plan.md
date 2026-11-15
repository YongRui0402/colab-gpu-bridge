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
├── __main__.py、app.py        # Settings 讀 CGB_PUBLIC_OLLAMA_PORT,create_app 收 public_ollama_port(Q21;專案沒有 config.py)
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
| Q7 | S3 | 模型清單讀不到時:a 回 502/504,代碼同 001 `listCatalog`(先採用);b 回 200、`reason` 為 `no_models` | — | a(D11) |
| Q8 | S3 | Google 沒授權時:a 一律當沒有就緒的工作階段,回 200 `no_ready_session`,不另列授權錯誤(先採用);b `reason` 多加一個值 | — | a(D11) |
| Q9 | S3 | `ollama.status` 為 `pending`/`unknown` 時:a `contextLength` null、`reason` null、`shouldWarn` false,前端依 null 顯示固定說明(先採用);b 加 `contextReason` | — | a(D11) |
| Q10 | S3 | 片段交付:a 後端回結構化資料加 `{{host}}` 佔位的片段文字,前端只換主機名稱(先採用);b 片段由前端組 | — | a(D11) |
| Q11 | S3 | 讀不到顯示記憶體或沒有工作階段時 `recommendedContextLength`:a 回 16384(先採用);b 回 null | — | a(D11) |
| Q12 | S3 | `GET /api/connect` 不計入閒置:a 照 001 `listCatalog`(先採用);b 計入 | — | a(D11) |
| Q13 | S4 | 審美方向:a 沿用 005 與現有 UI(先採用);b 另提新方向 | — | a(D12) |
| Q14 | S4 | 原型的 `index.html` 是為了「提醒連到首頁」做的示意頁:a 保留,只當原型的入口,不是新需求(先採用);b 改連到 005 原型 | — | a(D12) |
| Q15 | S4 | pi 的 `maxTokens` 固定 4096 時,context 4096 會等於 context:a 改成 `min(4096, ⌊context ÷ 2⌋)`,和 opencode 一致;b 維持固定 4096(原型先採用) | — | a(D12):research R3 與 `ui.openapi.yaml` 已改,原型的假資料不改 |
| Q16 | S4 | 原型由前端組片段、欄位名稱(`minContext`、`suggestedContext`)和 S3 合約不同:a 實作照 S3 合約與 Q10(後端產生片段、前端換主機名稱,欄位名稱照 `ConnectInfo`),原型只當畫面與 `data-state` 的依據(先採用);b 改合約照原型 | — | a(D12) |
| Q17 | S4 | context 太小時仍顯示片段:a 仍顯示,不擋複製(先採用);b 提醒時隱藏片段 | — | a(D12) |
| Q18 | testplan | 001 有三處把 `/v1` 當成白名單外的例子,開放後會失敗:`tests/integration/test_ollama_compat.py` 的 `test_白名單外的路徑回_404_不轉送`(參數 `POST /v1/chat/completions`)、同檔閒置案例的 `GET /v1/models`、`tests/e2e/test_locale.py` 的 `oc_unlisted`:a 改用仍不開放的 `/v1/completions`(閒置案例與 `oc_unlisted` 照 OpenAI 格式讀 `error.message`),在 006 US1-OC-05 的綠燈一起改(先採用);b 刪掉,由 US1-OC-05 取代 | — | a(D13) |
| Q19 | testplan | 假 Ollama 伺服器沒有 SSE 的回覆型別:a 在 `tests/fakes/ollama_server.py` 新增 `SseReply`(`events` 清單、每段間隔、`then` 可為 `end`/`disconnect`/`hang`),由 US1-OC-02 的紅燈任務建立(先採用);b 用 `NdjsonReply` 硬塞 | — | a(D13) |
| Q20 | testplan | G-01、G-02 本機實跑怎麼接:a 用 `live_servers` 起本系統,替身 `FakeTunnel` 回報的 `baseUrl` 指向臨時 serve、`FakeColabControl` 回報 context 10240,模型目錄由臨時 serve 的 `/api/tags` 讀(先採用);b 用 `docker compose` 起整個系統 | — | a(D13) |
| Q21 | tasks | 專案沒有 `src/cgb/config.py`(設定在 `src/cgb/__main__.py` 的 `Settings` 與 `create_app` 的參數):a `__main__.Settings` 加 `public_ollama_port`(沒設 `CGB_PUBLIC_OLLAMA_PORT` 時用 `ollama_port`),`create_app` 與 `AppState` 加 `ollama_port`(預設 11434)與 `public_ollama_port`(預設 None,沒給時用 `ollama_port`),`tests/conftest.py` 的 `make_app` 預設帶 11436(先採用);b 新建 `src/cgb/config.py` 集中讀環境變數 | — | a(D15) |
| Q22 | tasks | E3 節的任務順序:001 三處舊測試(Q18)改寫放在 US1-OC-05 的綠燈,但照 testplan 的順序,US1-OC-01 的綠燈一開放 `/v1/chat/completions` 就先破壞其中一處:a US1-OC-05 排在 E3 節最前面(T001),其餘照 testplan 順序(先採用);b 照 testplan 順序,把三處舊測試的改寫拆進 US1-OC-01、US1-OC-03 的綠燈 | — | a(D15) |
| Q23 | tasks | US1-API-09 要驗 pi 的片段、US1-AJ-05 要看 pi 分頁與提醒,但完整的 pi 片段與提醒在故事 2、3:a 照 `任務-規範` Rule 17,由第一個需要的綠燈做最小版本:US1-API-09 的綠燈做 `piModels` 只含 `providers.cgb.baseUrl`、`piSettings` 先為 null;US1-AJ-05 的綠燈做 pi 分頁與提醒的繁體中文文字,並在 `api/connect.py` 以 `contextLength < 16384` 算 `shouldWarn`、`recommendedContextLength` 先固定 16384;完整版由 US2、US3 的案例逼出(先採用);b 在 testplan 補案例,或把 US1-AJ-05 的樣本縮成 opencode 分頁 | — | a(D15) |
| Q24 | tasks | 一般紅燈任務寫完一執行就通過時(前面任務順手做到):a 改當對照組,放入「要抓的錯」確認斷言失敗後撤回,並在完成報告記一筆(同 005 Q54;先採用);b 停下來問使用者 | — | a(D15) |
| Q25 | tasks | US1-OC-02、US1-OC-08~US1-OC-11、US1-API-07、US1-API-08、US2-AJ-02 要測的程式路徑既有程式或前面任務已做到(`forward()` 原樣轉送、`_relay` 的補段出口、`Catalog.list` 的例外、UI app 不經 `IdleHook`、`data-copy` 通用的複製處理):a 照 Rule 20 排成對照組,紅燈任務指出做到它的檔案或任務(先採用);b 全排一般紅燈,寫完就綠的由 Q24 處理 | — | a(D15) |
| Q26 | tasks | 原型 `index.html` 的 `[data-state="normal"]`、`[data-state="applying"]` 是 005 已做好的工作階段頁(提醒連過去的位置,Q14),必須覆蓋的介面元素清單仍列了它們:a 在 US3-AJ-01 的紅綠任務 ⚙ 列出,只斷言連過去到得了 `#ollama-tuning`,不重做 005 的畫面(先採用);b 從清單剔除,改 plan.md 的 Documentation 樹 | — | a(D15) |
| Q27 | tasks | `prototype/style.css` 末尾「006 連線設定頁」增補(`.tabs`、`.tab`、`.snippet`、`.snippet-head`、`.code`、`.copied`、`.howto`、`.facts`、`.empty-state`、`.note-list`)要搬進 `src/cgb/static/style.css`:a 併進第一個用到的 US1-AJ-01 綠燈任務(先採用);b Setup 排一個不標步驟的任務(不合 Rule 17 的三類) | — | a(D15) |
| Q28 | tasks | G-03(串流延遲量測)只用測試行程內的假伺服器、不開 Colab:a 寫成 `tests/integration/test_006_g_03.py`、不標 `realrun`,進快速層,結果寫進 `measurements.md`(先採用);b 標 `realrun_local`,只在全部層跑 | — | a(D15) |
| Q29 | implement T023a | testplan 寫 E11 用 PyYAML 讀 `compose.yaml`,但專案的依賴裡沒有 YAML 函式庫:a 加 `pyyaml` 當開發依賴;b 用標準函式庫照縮排讀出 `services.cgb.environment` 與 `ports`,不加套件 | — | b(D17):testplan、tasks 已改 |
