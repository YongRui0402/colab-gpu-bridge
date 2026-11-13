# 系統分析規劃: 加入下載的重複判定與模型目錄快取

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Techstack**: [techstack.md](./techstack.md) | **Date**: 2026-11-13

建立在前一次迭代 [002-library-error-handling 的 plan.md](../002-library-error-handling/plan.md) 之上;002 的端點編號沿用 001 的 [plan.md](../001-session-model-catalog/plan.md),這一輪也沿用 001 的編號(E7 遠端 Ollama 在 002 沒有列,編號照 001)。

## Project Structure

### Documentation (this feature)

```text
specs/003-download-dedup-model-cache/
├── spec.md              # 輸入(specify 產出)
├── research.md          # 輸入(technical-research 產出)
├── techstack.md         # 輸入(technical-research 產出)
├── plan.md              # 本文件
└── contracts/
    ├── remote-ollama.openapi.yaml   # S1 產出(E7 遠端 Ollama,api-plan)
    └── ui.openapi.yaml              # S2 產出(E2 後端 UI API,api-plan)
```

### Source Code (repository root)

```text
src/cgb/
├── api/downloads.py         # E2 後端 UI API:試算與加入下載的路由(不改)
├── api/models.py            # E2 後端 UI API:模型目錄與預先載入的路由(不改)
├── api/curated.py           # E2 精選清單:normalized() 改呼叫 domain/model_name.py,行為不變
├── services/downloads.py    # 用例:試算與加入下載共用的重複檢查(補版本、同一批合併、比對已下載與佇列中),過了才取 manifest
├── services/catalog.py      # 用例:模型目錄的顯示記憶體快取,以工作階段名稱比對;讀不到時回 null、不快取
├── repos/downloads.py       # E4 資料庫的存取:整批寫入包一個 SQLite 交易,撞到 pending_model 唯一限制時整批撤回
├── adapters/remote_ollama.py  # E7 遠端 Ollama:_get_list(列模型、查已載入)把傳輸層失敗、逾時、非 200 與非 JSON 歸成 AdapterError
└── domain/
    ├── model_name.py        # 新增:補 latest 的共用規則 with_version()(純函式)
    └── errors.py            # 錯誤代碼的繁中訊息表:MESSAGES 補 OLLAMA_UNREACHABLE、OLLAMA_BAD_RESPONSE、OLLAMA_TIMEOUT

tests/
├── integration/             # test_remote_ollama.py(E7,真的 RemoteOllama 接 httpx.MockTransport)、test_api_downloads.py、test_api_models.py(E2)
└── fakes/                   # adapters.py 的 FakeMethod.invoke 接受 async 的 side_effect
```

**Structure Decision**: 沿用 001 的單一 Python 專案與單一映像,這一輪不新增檔案以外的元件,也不改部署與資料表。規格檔照 002 的做法以前一次的同名檔為底、只收這一輪範圍內的操作:

- `remote-ollama.openapi.yaml` 以 001 的同名檔(001 的 S1)為底,只收共用 `_get_list` 的兩個操作(列模型 `GET /api/tags`、查已載入 `GET /api/ps`)與它們用到的 components;001 已列的 `x-adapter-error-codes`(`OLLAMA_UNREACHABLE`、`OLLAMA_TIMEOUT`、`OLLAMA_BAD_RESPONSE`)不變,這一輪補上每個代碼出現的條件(research.md R2:照同檔 `getVersion` 的歸類)。其他操作仍以 001 的檔為準。
- `ui.openapi.yaml` 以 002 的同名檔為底(試算、加入下載),再從 001 的同名檔收進列出模型目錄 `GET /api/models`;只收這三個操作與它們用到的 components。預先載入與 `models.updated` 推送都經同一份模型目錄(research.md R3),回應與事件本文不變,所以不另外收,`ui-events.asyncapi.yaml` 仍以 001 的檔為準。路徑、operationId、參數、成功回應、錯誤代碼與狀態碼照前一次原樣(spec.md 假設:這一輪不改合約);只補這一輪定下的地方:補版本後才比對、同一批合併、檢查的先後、讀模型清單失敗時的 502、504、同時加入時整批不加入、顯示記憶體在一個工作階段只讀成功一次。`x-requirements` 指 003 的需求編號。

好處是下游的 testplan 與 tasks 只看得到這一輪改到的東西,`x-requirements` 不會和 001、002 同號的 FR 混在一起。

這一輪要一起交代的三個既有元素(research.md R2、R4):

- **轉接層 `RemoteOllama._get_list` 改歸類**:現在把 httpx 的例外與 `JSONDecodeError` 原樣往上拋(research.md R2 以 `httpx.MockTransport` 實測)。改成照同檔 `get_version` 歸成 `AdapterError` 之後,呼叫它的模型目錄、變更執行階段類型、預先載入、搜尋的 `downloadedTags` 收到的從原生例外變成 `AdapterError`,但這些服務沒有接,照樣是 500(001 完成報告 Q203,不在範圍內);只有試算與加入下載接住並轉成 502、504。
- **`domain/errors.py` 的 `MESSAGES` 只補三個代碼**:`OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,讓試算與加入下載的 `ApiError(...).body()` 不再因 `KeyError` 變成 500;Q203 其他代碼不補(分身決策紀錄 D9)。
- **既有測試 US3-API-26 和快取衝突**:`tests/integration/test_api_models.py` 的 `test_大小超過顯示記憶體總量才標可能無法載入_讀不到時是_null` 在同一個工作階段先讀到數字、再讓替身回 null,斷言第二次是 null;有了快取,第二次會沿用數字(FR-003)。這是案例的寫法和新需求衝突,不是程式錯,由 testplan 改寫這個案例(例如讀不到的那一半改成第一次就讀到 null),不能為了讓它綠而讓快取在 null 之後失效。

後端分層沿用 001 的 `api → services → (repos → db | adapters)`:`adapters/remote_ollama.py` 把 E7 的失敗在 `_get_list` 一處歸成 `AdapterError`;`services/downloads.py` 先補版本、合併、比對,再呼叫 E8 取 manifest,並以 `domain/errors.py` 的共用對應表把代碼轉成 UI API 的狀態碼與繁中訊息;`services/catalog.py` 在 `_vram_total()` 一處以工作階段名稱比對快取,打開目錄、推送 `models.updated` 與預先載入都經它;`repos/downloads.py` 把整批寫入包成一個交易。`domain/model_name.py` 是不依賴 I/O 的純函式,精選清單與下載共用。

前端不改,沿用 001 的 `static/`,依 `code` 與 `message` 顯示 409、502、504 的失敗。

## 分析流程規劃

> 本段排定分析的順序與每一步指派的 planner;分析由 Phase 3 照波段交給 sub agent 執行,產出寫在 Documentation 樹列的路徑。

### 端點盤點

這次需求涉及 2 個端點。每個端點視為一個獨立系統,分析的對象是它對外的介面:

| # | 端點 | 介面 | 需求出處 |
|---|---|---|---|
| E2 | 後端 UI API(FastAPI REST 與 SSE) | 試算與加入下載:重複判定的比對對象與先後、同一批合併、讀模型清單失敗與同時加入時的狀態碼、錯誤本文與佇列不變;模型目錄(打開目錄、`models.updated` 推送、預先載入前確認目錄):顯示記憶體的讀取時機、沿用與失效、讀不到時的回應 | FR-001–FR-005、NFR-001–NFR-003、SC-001–SC-003 |
| E7 | 遠端 Ollama(Colab 執行環境上,Ollama API) | 列模型與查已載入兩個操作的失敗歸類:傳輸層失敗、逾時、狀態碼、回應格式不符的判定 | FR-001、NFR-003、Assumptions(讀模型清單失敗回 502、504) |

沒有列的 001 端點:E1 前端 UI(spec 假設「這一輪不改 UI」)、E4 資料庫(`pending_model` 的唯一限制 001 `store.dbml` 已有,整批寫入包交易是後端 repo 的寫法,表與約束不變)、E5 Colab CLI(`probeResources` 的指令、輸出與失敗代碼照 001 `colab-cli.openapi.yaml`,快取放在後端服務裡,這個介面不變)、E8 Ollama 官方模型庫(取 manifest 的介面 002 已定,這一輪只改呼叫的先後)、E3、E6、E9、E10、E11(沒有需求用到)(分身決策紀錄 D11)。

### 分析波段

排序原則:**一個介面排在它所依賴的介面都分析完之後**;同一波裡的介面彼此不依賴,可以各開一個 sub agent 平行分析。

第三方端點的介面是對方定好的,我們只能照著接、不能改,所以它不依賴我們任何一個介面;
反過來,我們這邊碰到它的介面都要遷就它。因此**第三方端點排在最前面**,依賴它的介面往後推一波。

| Wave | 步驟 | 介面 | Planner | 平行 | 排在這一波的理由 |
|---|---|---|---|---|---|
| 1 | S1 | E7 遠端 Ollama | api-plan | — | Ollama 的 API 已經定好,不依賴任何介面;試算與加入下載讀模型清單失敗時要轉接的代碼與它們出現的條件都照它 |
| 2 | S2 | E2 後端 UI API | api-plan | — | 試算與加入下載讀模型清單失敗時會收到哪些代碼,由 S1 列模型的失敗歸類決定 |

共 2 個 wave、2 個步驟:Wave 1 一個介面,Wave 2 一個介面。

## 待決問題

> Phase 3 每一波交回的待決問題都登記在這裡;有問題擋住下一波時,在下一波開始之前把所有還沒決定的一次問完,沒有擋住就等最後一波之後一起問。

| Q | 提出的步驟 | 問題與可選的做法 | 擋住 | 決定 |
|---|---|---|---|---|
| Q1 | S1 | 列模型、查已載入回 200 但底層解壓本文失敗(`httpx.DecodingError`,不是 `TransportError`;同檔 `get_version` 現在也沒接)歸成什麼:(a)`OLLAMA_BAD_RESPONSE`,和 002 `model-library.openapi.yaml` 對解壓失敗的歸類一致(002 plan.md Q10)(先採用)(b)`OLLAMA_UNREACHABLE`(c)照 `get_version` 現況不接,例外往上拋 | — | (a)`OLLAMA_BAD_RESPONSE`(kevin-twin 代為決定,分身決策紀錄 D14) |
| Q2 | S1 | 200 且是 JSON 但形狀不符時檢查到多細:(a)只檢查最上層 `models` 是陣列(b)再檢查每一筆是物件、有字串的 `name`,`/api/tags` 另要有非負整數的 `size`(後端實際會讀的欄位),不符一律 `OLLAMA_BAD_RESPONSE`,其他欄位缺了不算失敗(先採用)(c)照 schema 所有必填欄位全部驗證 | — | (b)只檢查 `models`、`name`、`size`(kevin-twin 代為決定,分身決策紀錄 D15) |
| Q3 | S1 | `listLoadedModels`(`GET /api/ps`)不在試算與加入下載的路徑上,`x-requirements` 指哪一條:(a)FR-004,模型目錄「照常列出模型」要讀它(先採用)(b)NFR-003(c)FR-003 | — | (a)FR-004(kevin-twin 代為決定,分身決策紀錄 D16) |
| Q4 | S2 | `listCatalog` 的 502 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、504 `OLLAMA_TIMEOUT`(讀 tags、ps 失敗)照 001 原樣保留,但這一輪模型目錄收到這些代碼照舊回 500(001 完成報告 Q203,不在範圍內),合約和實作不一致:(a)照 001 原樣保留,description 註明這一輪不處理(先採用)(b)從本檔拿掉這兩個回應,只留 200、503(c)把模型目錄接住這三個代碼納入這一輪 | — | (a)照 001 原樣保留,註明這一輪不處理;testplan 寫進不在範疇(kevin-twin 代為決定,分身決策紀錄 D17) |
| Q5 | S2 | 試算與加入下載的請求本文格式檢查(400 `INVALID_REQUEST_BODY`、`EMPTY_MODEL_LIST`、`INVALID_MODEL_NAME`)和 503 `NO_READY_SESSION` 誰先:(a)400 最先,格式檢查不需要工作階段,現有路由也先 `read_json`(先採用)(b)503 最先 | — | (a)400 最先(kevin-twin 代為決定,分身決策紀錄 D18) |
| Q6 | S2 | 502 `OLLAMA_BAD_RESPONSE` 的條件沿用 S1 的 `x-failure-rules`,S1 的 Q1、Q2 還沒拍板:(a)沿用 S1 先採用的做法(先採用)(b)S1 的 Q1、Q2 改判後跟著改 502 的描述 | — | (a)沿用 S1 先採用的做法(kevin-twin 代為決定,分身決策紀錄 D19) |
