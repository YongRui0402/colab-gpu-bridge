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
│                            # 新增 test_downloads_cross.py(故事 1 跨端點驗收,Q25)
│                            # 新增 test_003_g_01.py(G-01,標 realrun:測試自己在另一個 127.0.0.1 port 起臨時的 ollama serve,Q27)
│                            # 新增 test_003_g_02.py(G-02,標 realrun:測試行程內的 uvicorn,Q9)
├── e2e/test_locale.py       # 錯誤代碼繁中訊息的對照表補 OLLAMA_UNREACHABLE、OLLAMA_BAD_RESPONSE、OLLAMA_TIMEOUT 三列
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
| Q7 | testplan | 003 的案例 ID 和 001、002 已寫在測試檔裡的分隔註解撞號(`US1-API`、`US2-API`、`US1-RO`、`US2-RO`、`G-`),怎麼分:(a)testplan 照骨架的 ID,測試檔的分隔註解寫成 `# ---- 003 US1-API-01`,全域案例照 002 放 `tests/integration/test_003_g_NN.py`(先採用)(b)ID 改帶迭代前綴(c)不處理 | — | (a)ID 照骨架,測試檔標記加 `003 `,全域案例放 `test_003_g_NN.py`(kevin-twin 代為決定,分身決策紀錄 D21) |
| Q8 | testplan | E7 的 `httpx.MockTransport` 與 E2 的 `FakeRemoteOllama` 指到哪個實跑:(a)G-01,真的 `RemoteOllama` 對桌機 Ollama 0.32.15 只送 `GET /api/tags`、`GET /api/ps`,另對沒有在聽的 port 驗連不到;時機:節內;Colab 上的 Ollama 寫未驗證(先採用)(b)無法實跑(c)整合時開 Colab 照 001 的 US2-RO-03 實跑 | — | (a)G-01 對桌機 Ollama 唯讀實跑,Colab 上的寫未驗證(kevin-twin 代為決定,分身決策紀錄 D22)(已被 Q27 取代) |
| Q9 | testplan | SC-002 的「替身每次延遲 3 秒」放哪一層測(快速層照 002 plan.md Q20 排除單支超過 1 秒的測試):(a)E2 行為案例用 0.3 秒延遲留在快速層,SC-002 原樣的 3 秒寫成 G-02,經測試行程內的 uvicorn,標 `realrun`、放 `tests/integration/test_003_g_02.py`(先採用)(b)行為案例直接用 3 秒並加進快速層的 `--deselect`(c)只寫 3 秒的行為案例 | — | (a)行為案例 0.3 秒留在快速層,3 秒另寫 G-02(kevin-twin 代為決定,分身決策紀錄 D23) |
| Q10 | testplan | E7 列模型、查已載入的 `x-timeout` 10 秒怎麼驗(spec 沒有需求直接寫這個值,`RemoteOllama` 也沒有 list 逾時的建構參數):(a)斷言送出請求的 `extensions["timeout"]` 四項都是 10.0,不真的等(US1-RO-15、US2-RO-01)(先採用)(b)不測,列不在範疇(c)加可注入的 `list_timeout` 參數實際量逾時 | — | (a)斷言請求的逾時設定 10 秒(kevin-twin 代為決定,分身決策紀錄 D25) |
| Q11 | testplan | E7 丟出 `AdapterError` 時要不要斷言例外鏈切斷(`from None`,002 E8 的做法):(a)不斷言 `__cause__`,照同檔 `get_version` 現行的 `from error`,只要求丟出的是 `AdapterError`(先採用)(b)比照 002 斷言 `from None` | — | (a)不斷言例外鏈(kevin-twin 代為決定,分身決策紀錄 D26) |
| Q12 | testplan | E7「失敗不自動重試」怎麼斷言:(a)每種情況各一條請求數的則(b)N 種情況合計 handler 收到 N 個請求,一條則(先採用)(c)不斷言 | — | (b)合計請求數一條則(kevin-twin 代為決定,分身決策紀錄 D27) |
| Q13 | testplan | E7 的替身與 `Recorder` 放哪:(a)照待測端點表用 `httpx.MockTransport`,`Recorder`(現在在 `test_model_library.py`)搬到 `tests/fakes/` 或檔內另寫,由 `/tdd` 決定(先採用)(b)照 001 的 `test_remote_ollama.py` 改用 `FakeOllamaServer` | — | (a)MockTransport,`Recorder` 放哪由 `/tdd` 決定(kevin-twin 代為決定,分身決策紀錄 D28) |
| Q14 | testplan | 驗收情境 2「下載完成後推送 `models.updated`」:現在下載完成不推 `models.updated`(001 完成報告 Q188、Q192 的已知缺口),只有預先載入結束時推:(a)以預先載入結束的推送驗沿用(US2-API-03),下載完成的推送列不在範疇(先採用)(b)這一輪補上下載完成時推送(c)不驗推送 | — | (a)以預先載入的推送驗,下載完成的推送列不在範疇(kevin-twin 代為決定,分身決策紀錄 D29) |
| Q15 | testplan | 讀顯示記憶體時 `probe_resources` 丟 `AUTH_REQUIRED`(不是 `COLAB_` 開頭)算不算讀不到:(a)算,回 200 與 null、不快取(US2-API-11 的 parametrize 之一)(先採用)(b)照合約 (3) 字面只接 `COLAB_`,`AUTH_REQUIRED` 照舊 500 | — | (a)`AUTH_REQUIRED` 也算讀不到(kevin-twin 代為決定,分身決策紀錄 D30) |
| Q16 | testplan | US2-API-12 延遲縮成 0.3 秒後的時間門檻(SC-002 的 1 秒配 3 秒延遲,照抄就分不出有沒有快取):(a)第 2 次起每次 < 0.15 秒,另加第 1 次 ≥ 0.3 秒當對照(先採用)(b)照 SC-002 寫 1 秒(c)只數次數 | — | (a)第 2 次起 < 0.15 秒,第 1 次 ≥ 0.3 秒當對照(kevin-twin 代為決定,分身決策紀錄 D31) |
| Q17 | testplan | 同時發生的第一次讀取(spec 假設不保證合併)要不要寫案例:(a)寫 US2-API-10,次數 1 到 2 次、兩個回應都是數字、之後不再讀,抓「正在讀就回 null」(先採用)(b)不寫 | — | (a)寫 US2-API-10,斷言 1 到 2 次(kevin-twin 代為決定,分身決策紀錄 D32) |
| Q18 | testplan | US2-API-07 怎麼取代 001 的 `test_大小超過顯示記憶體總量才標可能無法載入_讀不到時是_null`:(a)在 `test_api_models.py` 原地改寫那一個函式,分隔註解改成 `# ---- 003 US2-API-07`(先採用)(b)刪掉舊函式另寫新的 | — | (a)原地改寫那一個函式(kevin-twin 代為決定,分身決策紀錄 D33) |
| Q19 | testplan | 兩個加入下載同時送出的 US1-API-22 怎麼讓結果固定:(a)`get_manifest` 用 async `side_effect`,請求 2 停在 `llama3.2` 的 manifest,等請求 1 回應後才放行,佇列內容與 SSE 都斷言得出來(先採用)(b)照 research.md R2 用 `gate()` 一起放行,則只能寫「一個 201、一個 409」 | — | (a)async `side_effect` 固定先後(kevin-twin 代為決定,分身決策紀錄 D34) |
| Q20 | testplan | `insert_jobs` 要寫入 `qwen2.5:latest`,但它從 `MANIFEST_SIZES` 查大小:(a)加 `sizes` 關鍵字參數,預設不變(先採用)(b)把 `qwen2.5:latest`、`llama3.2:latest` 補進 `MANIFEST_SIZES`(會改到 `set_library` 的預設) | — | (a)`insert_jobs` 加 `sizes` 參數(kevin-twin 代為決定,分身決策紀錄 D35) |
| Q21 | testplan | 試算與加入下載的 503 `NO_READY_SESSION` 要不要另寫「重連中」的案例:(a)只驗沒有工作階段與開啟中,重連中由同一個 `require_ready_base_url()` 涵蓋(模型目錄的重連中由 US2-API-06 驗)(先採用)(b)另寫靠健康檢查進入重連中的案例 | — | (a)不另寫重連中(kevin-twin 代為決定,分身決策紀錄 D36) |
| Q22 | testplan | 試算與加入下載的 400 `EMPTY_MODEL_LIST`、`INVALID_MODEL_NAME` 現在沒有實作(合法 JSON 缺 `models` 時 `KeyError` 回 500),Q5 的「400 最先」只能用 `INVALID_REQUEST_BODY` 驗:(a)照 001 的 Q178 留在範圍外,寫進不在範疇(先採用)(b)這一輪補做 | — | (a)留在範圍外,寫進不在範疇(kevin-twin 代為決定,分身決策紀錄 D37) |
| Q23 | tasks | 001 的 `test_大小超過顯示記憶體總量才標可能無法載入_讀不到時是_null` 在 US2-API-01 的綠燈(T055b)加上快取時就會變紅,但 Q18 決定由 US2-API-07(T061a)原地改寫它,中間 T056~T060 的「全部測試綠燈」會缺這一支:(a)T055b 同一個任務刪掉那個函式「同一個工作階段先讀到數字、再讀到 null」的後半(第二次請求與它的斷言),T061a 再原地改寫成第一次就讀到 null,不留 skip(先採用)(b)T055b 直接把它改寫成 US2-API-07 的樣子,T061a 只補分隔註解與剩下的斷言(c)T055b 先加 skip,T061a 再拿掉 | — | (a)T055b 刪掉後半、T061a 原地改寫,不留 skip(kevin-twin 代為決定,分身決策紀錄 D38) |
| Q24 | tasks | 現有程式或更早的綠燈任務已經做到的案例,紅燈怎麼排:(a)照 tasks 規則 Rule 20 預先寫成對照組紅燈(45 個:先確認通過,再暫時放入要抓的錯、確認斷言失敗後撤回;綠燈確認不需要改程式碼),為了讓預測成立,綠燈任務照 research.md R2、R3 與合約寫出共用的形狀(T017b 的 `_checked`、T019b 在同一個迴圈比對佇列、T014b 的 `size` 只套 `/api/tags`);預測不中時照任務裡寫的退路,對照組一執行就紅改當一般紅燈,T058a、T061a 一執行就綠改做對照組(先採用)(b)全部寫成一般紅燈,實作時遇到一寫完就綠的再個別處理並回 plan.md 追認 | — | (a)預先寫成對照組紅燈,預測不中照任務裡的退路(kevin-twin 代為決定,分身決策紀錄 D39) |
| Q25 | tasks | 故事 1 跨端點驗收(US1-AJ-01~US1-AJ-04)的測試檔 testplan 沒有指定:(a)新檔 `tests/integration/test_downloads_cross.py`,照 `test_library_cross.py` 的寫法(先採用)(b)加進 002 的 `tests/integration/test_library_cross.py`(c)照全域案例的命名放 `tests/integration/test_003_aj.py` | — | (a)新檔 `tests/integration/test_downloads_cross.py`(kevin-twin 代為決定,分身決策紀錄 D40) |
| Q26 | tasks | `src/cgb/api/curated.py` 的 `normalized()` 改呼叫 `domain/model_name.py`(Project Structure 列了,行為不變,沒有案例逼出它)排在哪個任務:(a)E2 故事 1 的重構任務 T042,寫明是清單之外另做的一項、不改 `tests/integration/test_api_curated.py` 的斷言(先採用)(b)併進 T017b 的綠燈(c)在 testplan 補一個精選清單的案例 | — | (a)放在重構任務 T042(kevin-twin 代為決定,分身決策紀錄 D41) |
| Q27 | testplan | 取代 Q8(analyze 第 1 輪 A1 回修):Q8(a)讓 G-01 對桌機 127.0.0.1:11434 的 Ollama 送 `GET /api/tags`、`GET /api/ps`,和 001 的實跑護欄 P6「桌機的 11434 是使用者自己的 Ollama,不送任何請求」(`../001-session-model-catalog/testplan.md` § 實跑案例的共同護欄)矛盾,`tests/realrun/helpers.py` 的 `RecordingTransport` 也會因 `check_port(11434)` 擋下(analyze 第 1 輪 A1)。E7 的 `httpx.MockTransport` 與 E2 的 `FakeRemoteOllama` 改指到哪個實跑:(a)在 003 放寬 P6,只限這兩個唯讀 GET(b)G-01 不碰 11434、P6 不動,測試自己在 `free_loopback_port()` 取得的 127.0.0.1 port(不會是 11434~11436、8780)起臨時的 `ollama serve`(`/usr/local/bin/ollama` 0.32.15),`OLLAMA_MODELS` 指向空的暫存目錄、`HOME` 也用暫存目錄,fixture 收尾結束行程並驗證行程已結束;代價:`/api/tags` 是空清單,驗不到真實模型名稱的格式(c)G-01 改列無法實跑 | — | (b)測試自己起臨時的 `ollama serve`,不碰 11434,P6 不動;`/api/tags` 是空清單,真實模型名稱的格式列未驗證(使用者 2026-11-13 決定,不是分身代答;分身決策紀錄 D42) |
