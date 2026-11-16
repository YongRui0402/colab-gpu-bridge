# Tasks: 模型目錄讀不到時回正確的錯誤,對話紀錄保留到工作階段結束

**Input**: `specs/007-catalog-error-chat-keep/` 的設計文件(本 spec package)

**Prerequisites**: plan.md、spec.md、research.md、techstack.md、testplan.md、`contracts/ui.openapi.yaml`、`prototype/`

**Tests**: 依 `testplan.md` 切分。testplan 的每個行為測試案例對應一組 `/tdd` 紅燈與綠燈任務,每個「使用者故事 × 端點」節最後一個 `/tdd` 重構任務;量測與人工驗證的案例對應 📏 任務。

**Organization**: 依 `testplan.md` 的使用者故事分 phase;每個故事底下依 `testplan.md` 的端點分節(E2 後端 UI API、E1 前端 UI),外加一節跨端點驗收,最後是介面覆蓋表與測試案例覆蓋表。全域測試區自成一個 phase,放在所有故事之後。

## Format: `[ID] [Story] [步驟] Description`,底下接 🧪、⚙ 與 📎

- **[Story]**:所屬的使用者故事(US1、US2);全域測試區寫 `[G]`
- **[步驟]**:這個任務是 `/implement` 交給誰做的哪一步
  - 🔴 `/tdd 紅燈`:寫一個測試案例的測試,執行確認它失敗
  - 🟢 `/tdd 綠燈`:只寫讓同一個案例通過的程式碼,執行同一組紅燈寫的測試檔確認通過
  - 🔵 `/tdd 重構`:在全部測試綠燈下,整理這一節綠燈任務記下的重構清單,每改一小步執行這一節的測試檔,重構前後執行全部測試;不改行為、不改斷言
  - 📏 量測:照 testplan 案例的條件量測或人工驗證,記下數字與門檻比較;是唯一不對應 `/tdd` 的開發任務
  - 不標步驟的只限三類:工具鏈設定、原樣複製 spec package 的規格檔、CI 設定
- **紅綠成對**:一個 testplan 案例對應同一個三位數的 `a`(🔴)與 `b`(🟢),`b` 依賴 `a`
- **誰做、怎麼排**:同一個 phase 的端點節各交給一個 subagent 平行做;跨端點驗收節在端點節都完成、驗收過後由主 agent 做。每一節裡照任務編號一次做一個任務,做完才做下一個,不跳號
- 每個任務都寫出確切的檔案路徑
- **🧪**:這個任務對應的 `testplan.md` 案例 ID;🔵 寫這一節所有案例的範圍;不標步驟的任務不寫這一行
- **⚙**:這個任務要做出來或測到的介面元素:至少照 `testplan.md` 受測操作表的「規格錨點」欄寫,再加上這個任務實際做出或斷言的介面元素
- **📎**:做這個任務時要對照的依據:`spec.md` § FR / NFR / SC / 邊界情況、`research.md` § R、`plan.md` § Q 或段落名、`techstack.md` § 段落名

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 沿用 001~006 的工具鏈、`uv.lock`、測試基礎(`tests/conftest.py`、`tests/fakes/`、`tests/e2e/conftest.py`、`tests/realrun/helpers.py`)與 005 新增的 `realrun_local` marker;這一輪不新增套件、服務、port、掛載與資料表(`techstack.md` § 依賴),不改 CI,也沒有原樣複製的規格檔。

本輪沒有 Setup 任務。

---

## Phase 2: User Story 1 - 模型目錄讀不到時,看得到真正的原因 (Priority: P1) 🎯 MVP

**Goal**: 工作階段就緒但讀不到執行環境上的 Ollama 時,列出模型目錄與預先載入照 001 合約回 502/504 與原因代碼,不再回 500;模型頁與對話頁顯示對應的繁體中文說明,不顯示成空目錄

**Independent Test**: 照 `testplan.md` § 2 的全部案例:E2 以 `uv run pytest tests/integration/test_007_catalog_errors.py`、跨端點驗收以 `uv run pytest tests/e2e/test_007_us1_catalog_errors.py` 執行全綠

### E2 後端 UI API(FastAPI REST 與 SSE)

> 測試檔全節共用新增的 `tests/integration/test_007_catalog_errors.py`(T001a 建立,後面的紅燈往裡加);沿用 `tests/conftest.py` 的 `ui_client`、`fakes`、`make_app`,`tests/integration/test_api_session.py` 的 `ColabWorld`、`open_ready`、`get_session`、`error_code`,`tests/integration/test_api_models.py` 的 `tag`、`set_tags`、`set_loaded`、`next_event`(以 `from integration.test_api_models import …` 匯入);只有 US1-API-08 用 `live_servers` 讀 `/api/events`(`plan.md` § 待決問題 Q13、Q19)。實作只改 `src/cgb/services/catalog.py`(T001b 只轉 tags、T003b 補上 ps)與 `src/cgb/api/connect.py`(T003b 拿掉自己接 `AdapterError` 的那段);`src/cgb/domain/errors.py` 的 `ollama_error()` 與 `MESSAGES` 已有三個代碼的狀態碼與訊息,不改。T001b、T003b 之後,本節其餘案例走的都是同一段 `Catalog.list()` 轉換或既有程式,照 Rule 20 寫成對照組。
- [ ] T001a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-01 的測試(工作階段就緒,`ColabWorld` + `open_ready`;ps 回空清單;`list_local_models` 以 `parametrize` 依序 `.raises()` 丟 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,每種各呼叫一次 `GET /api/models`;斷言 502/502/504 與 `code`),執行確認它因為「`Catalog.list()` 沒接 `AdapterError`,原樣往上拋回 500(現況)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 1、使用者故事 1 驗收情境 2、使用者故事 1 驗收情境 3;`research.md` § R1;`plan.md` § 待決問題 Q15;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T001b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/catalog.py` 只寫讓 US1-API-01 通過的程式碼:`Catalog.list()` 讀 tags(`list_local_models`)時接 `AdapterError`,以 `cgb.domain.errors.ollama_error(error.code)` 轉成 `ApiError` 拋出(`from None`,不帶底層例外);只包住讀 tags 那一次,讀 ps 留給 T003b,`require_ready_base_url()` 與 `_vram_total()` 不包進去(research R1)。照 Rule 5 搜過的呼叫端:`src/cgb/api/models.py` 的 `list_catalog`、`preload_model` 不改(`ApiError` 走 `src/cgb/api/__init__.py` 的全域處理器);`src/cgb/api/connect.py` 的 `get_connect_info` 這時仍接 `AdapterError`,留到 T003b 再拿掉;`Catalog.preload()` 先呼叫 `list()`,同時改到;背景推送 `Catalog.publish()` 與 `Catalog._run_preload()` 結束後的 `publish()` 拋出的型別從 `AdapterError` 變成 `ApiError`,背景工作原本就沒有接,行為不變,照 D2 不在範圍、不改,列進完成報告;`src/cgb/services/tuning.py` 的 `_publish_models` 自己讀遠端、只用 `catalog_payload`,不受影響。查過 `tests/` 沒有斷言目錄讀不到時回 500 或 `Catalog.list()` 拋 `AdapterError` 的舊測試;依賴 `connect.py` 那段 except 的 `tests/integration/test_api_connect.py` 的 `test_讀不到模型目錄時回_502_不當成目錄是空的` 改由全域處理器回同一個 502,斷言不用改。執行 `tests/integration/test_007_catalog_errors.py`、`tests/integration/test_api_models.py`、`tests/integration/test_api_connect.py` 確認通過;看到要整理的地方記進重構清單(依賴 T001a)
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-001;`research.md` § R1;`plan.md` § 待決問題 Q11;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T002a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-02 的測試(同 US1-API-01,替身丟錯的 message 是 `Traceback (most recent call last): httpx.ConnectError 127.0.0.1:41234`;斷言三次的 `message` 各等於 `info.x-ollama-error-message` 的原句、本文不含 `Traceback`、`127.0.0.1`);T001b 以 `ollama_error()` 轉換,訊息取自 `src/cgb/domain/errors.py` 既有的 `MESSAGES`、不帶底層例外,這個案例會被滿足:先執行確認通過,再暫時讓 T001b 的轉換改成 `ApiError(..., message=str(error))`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001;`research.md` § R1;`plan.md` § 待決問題 Q15;`contracts/ui.openapi.yaml` § `info.x-ollama-error-message`
- [ ] T002b [US1] 🟢 /tdd 綠燈:US1-API-02 由 T001b 的 `ollama_error()` 與既有的 `MESSAGES` 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-02 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T002a)
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-ollama-error-message`
- [ ] T003a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-03 的測試(工作階段就緒;tags 回 `qwen2.5:0.5b`、`qwen2.5:7b`;`list_loaded_models` 依序丟三種代碼,每種各呼叫一次 `GET /api/models`;斷言 502/502/504 與 `code`,本文只有 `code`、`message` 兩個鍵、沒有 `items`),執行確認它因為「只接住 tags 的 `AdapterError`,ps 的原樣拋出回 500(T001b 之後的現況);或 ps 讀不到時當成沒有已載入的模型,回 200 半套目錄」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R1;`plan.md` § 待決問題 Q15;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T003b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/catalog.py` 與 `src/cgb/api/connect.py` 只寫讓 US1-API-03 通過的程式碼:`Catalog.list()` 讀 ps(`list_loaded_models`)時也接 `AdapterError` 以 `ollama_error()` 轉換,照 tags → ps 的順序依序讀、不並行,任一份失敗就整份失敗、不回半套目錄;兩份清單都轉換之後,`src/cgb/api/connect.py` 的 `get_connect_info` 自己接 `AdapterError` 的那段 `except` 不會再進去,照 research R1、plan Q11 拿掉它與不再用到的 `AdapterError`、`ollama_error` import,讓錯誤只在 `Catalog.list()` 一處轉換(`/api/connect` 改由全域處理器回同一個 502/504,US1-API-14、US1-API-15 守住)。執行 `tests/integration/test_007_catalog_errors.py`、`tests/integration/test_api_models.py`、`tests/integration/test_api_connect.py` 確認通過;看到要整理的地方記進重構清單(依賴 T003a)
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R1;`plan.md` § 待決問題 Q11;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T004a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-04 的測試(工作階段就緒;`list_local_models` 丟 `OLLAMA_UNREACHABLE`、`list_loaded_models` 丟 `OLLAMA_TIMEOUT`,呼叫一次 `GET /api/models`;斷言 502 `OLLAMA_UNREACHABLE`);`Catalog.list()` 既有的依序讀取(先 tags 後 ps)加上 T001b、T003b 的轉換,tags 先失敗就不再讀 ps,這個案例會被滿足:先執行確認通過,再暫時把 `Catalog.list()` 改成先讀 ps 再讀 tags(或 `asyncio.gather` 以 ps 的錯誤為準),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T004b [US1] 🟢 /tdd 綠燈:US1-API-04 由 `Catalog.list()` 的依序讀取與 T001b、T003b 的轉換滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-04 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T004a)
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T005a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-05 的測試(工作階段就緒;tags 回 `qwen2.5:7b`(4,683,087,332 位元組)、ps 回空清單;`FakeColabControl.probe_resources` 丟 `COLAB_TIMEOUT`;呼叫一次 `GET /api/models`;斷言 200、`vramBytes` 為 null、`qwen2.5:7b` 的 `mayNotFit` 為 null);既有的 `src/cgb/services/catalog.py` `Catalog._vram_total()` 接住 `AdapterError` 回 None(003 起,`tests/integration/test_api_models.py` 的 `test_讀顯示記憶體失敗時目錄照常列出_顯示記憶體是_null_下一次再讀` 測過同一條路),T001b、T003b 只包 tags、ps,這個案例會被滿足:先執行確認通過,再暫時拿掉 `_vram_total()` 的 `except AdapterError`(或讓 T001b 的轉換包住整個 `list()`),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`
  - 📎 `spec.md` § 邊界情況;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T005b [US1] 🟢 /tdd 綠燈:US1-API-05 由既有的 `Catalog._vram_total()` 滿足,T001b、T003b 沒有把它包進轉換,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-05 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T005a)
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`
  - 📎 `spec.md` § 邊界情況;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T006a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-06 的測試(沒有開工作階段;`list_local_models`、`list_loaded_models` 都設成丟 `OLLAMA_UNREACHABLE`;呼叫 `GET /api/models`;斷言 503 `NO_READY_SESSION`、`list_local_models` 呼叫 0 次);既有的 `Catalog.list()` 第一行就呼叫 `src/cgb/services/session_lifecycle.py` 的 `SessionLifecycle.require_ready_base_url()` 丟 503,在 T001b 的轉換之外,這個案例會被滿足:先執行確認通過,再暫時讓 T001b 的轉換連 `require_ready_base_url()` 一起包住、以 `except Exception` 一律轉成 `ollama_error("OLLAMA_UNREACHABLE")`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § 邊界情況;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T006b [US1] 🟢 /tdd 綠燈:US1-API-06 由既有的 `SessionLifecycle.require_ready_base_url()` 在讀遠端之前檢查滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-06 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T006a)
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § 邊界情況;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T007a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-07 的測試(工作階段就緒,記下 `GET /api/session` 的 `name`;tags 回 `qwen2.5:0.5b`、`qwen2.5:7b`,ps 回 `qwen2.5:0.5b`;`list_local_models` 以 `.then()` 設成第一次丟 `OLLAMA_UNREACHABLE`、之後照常;連續呼叫兩次 `GET /api/models`,再呼叫 `GET /api/session`;斷言第一次 502、第二次 200 與兩筆名稱、`qwen2.5:0.5b` 的 `loaded` 為 true、`state` 為 `ready` 且 `name` 不變);T001b 的轉換每次呼叫都重讀遠端、不快取錯誤,也不碰工作階段,這個案例會被滿足:先執行確認通過,再暫時讓 `Catalog.list()` 把第一次的錯誤存起來、之後直接拋同一個,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 5;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T007b [US1] 🟢 /tdd 綠燈:US1-API-07 由 T001b、T003b 的轉換(不留狀態)滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-07 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T007a)
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 5;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T008a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-08 的測試(以 `live_servers` 起 app,工作階段就緒;tags 回 `qwen2.5:7b`、`hf.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M`,ps 回空清單;先讓 `hf.co/…` 預先載入一次、`preload` 丟 `OLLAMA_SERVER_ERROR`,等到目錄裡它的 `preload.state` 為 `failed` 且已收到那則 `models.updated`;之後 `remote.preload.reset_calls()`、`list_local_models` 改丟 `OLLAMA_UNREACHABLE`,`/api/events` 連著;送 `POST /api/models/preload` `{"name":"qwen2.5:7b"}`,等 1 秒後 tags 恢復照常再呼叫 `GET /api/models`;斷言 502 `OLLAMA_UNREACHABLE`、`remote.preload` 呼叫 0 次、`qwen2.5:7b` 為 `idle`、`hf.co/…` 仍是 `failed` 與 `OLLAMA_SERVER_ERROR`、1 秒內沒有 `models.updated`);既有的 `src/cgb/services/catalog.py` `Catalog.preload()` 先呼叫 `self.list()`、之後才寫 `_preloads` 與 `spawn(_run_preload)`,加上 T001b 的轉換,這個案例會被滿足:先執行確認通過,再暫時把 `self._preloads[name] = loading` 搬到 `self.list()` 之前,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`、`components.schemas.PreloadState`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 4;`research.md` § R1;`plan.md` § 待決問題 Q3、Q13、Q14、Q19
- [ ] T008b [US1] 🟢 /tdd 綠燈:US1-API-08 由既有的 `Catalog.preload()` 檢查順序與 T001b 的轉換滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-08 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T008a)
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`、`components.schemas.PreloadState`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 4;`research.md` § R1;`plan.md` § 待決問題 Q13
- [ ] T009a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-09 的測試(工作階段就緒;ps 回空清單;`remote.preload.reset_calls()`;`list_local_models` 依序丟三種代碼,每種各送一次 `POST /api/models/preload` `{"name":"qwen2.5:7b"}`;斷言 502/502/504 與 `code`、三次之後 `remote.preload` 呼叫 0 次);`Catalog.preload()` 確認目錄走 `self.list()`,T001b 已讓它把 tags 的 `AdapterError` 轉成 `ApiError`,這個案例會被滿足:先執行確認通過,再暫時在 `Catalog.preload()` 把 `self.list()` 丟的 `ApiError` 接住當成空目錄(往下走到 404),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 4;`research.md` § R1;`plan.md` § 待決問題 Q2、Q15;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T009b [US1] 🟢 /tdd 綠燈:US1-API-09 由 T001b 在 `Catalog.list()` 的轉換滿足(`preload()` 先呼叫 `list()`),確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-09 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T009a)
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § FR-002;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T010a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-10 的測試(工作階段就緒;tags 回 `qwen2.5:7b`;`remote.preload.reset_calls()`;`list_loaded_models` 依序丟三種代碼,每種各送一次 `POST /api/models/preload` `{"name":"qwen2.5:7b"}`;斷言 502/502/504 與 `code`、`remote.preload` 呼叫 0 次);`Catalog.preload()` 走 `self.list()`,T003b 已讓它把 ps 的 `AdapterError` 也轉換,這個案例會被滿足:先執行確認通過,再暫時撤回 T003b 在 `Catalog.list()` 讀 ps 的轉換(或讓 `preload()` 改成只讀 tags 確認),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § FR-002、邊界情況;`research.md` § R1;`plan.md` § 待決問題 Q15;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T010b [US1] 🟢 /tdd 綠燈:US1-API-10 由 T003b 在 `Catalog.list()` 讀 ps 的轉換滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-10 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T010a)
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § FR-002、邊界情況;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T011a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-11 的測試(同 US1-API-09,替身丟錯的 message 是 `Traceback (most recent call last): httpx.ConnectError 127.0.0.1:41234`;斷言三次的 `message` 各等於 `info.x-ollama-error-message` 的原句、本文沒有 `model` 鍵);T001b 以 `ollama_error(code)` 轉換,不帶 `model=` 與 `message=`,這個案例會被滿足:先執行確認通過,再暫時讓轉換改成 `ApiError(..., model=name, message=PRELOAD_FAILED_MESSAGE)` 這類寫法(在 `Catalog.preload()` 自己接錯),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002;`research.md` § R1;`plan.md` § 待決問題 Q15;`contracts/ui.openapi.yaml` § `info.x-ollama-error-message`
- [ ] T011b [US1] 🟢 /tdd 綠燈:US1-API-11 由 T001b 的 `ollama_error()` 與既有的 `MESSAGES` 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-11 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T011a)
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-ollama-error-message`
- [ ] T012a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-12 的測試(工作階段就緒,記下 `name`;tags 回 `qwen2.5:7b`、ps 回空清單;`list_local_models` 以 `.then()` 設成第一次丟 `OLLAMA_UNREACHABLE`、之後照常;`remote.preload` 停在閘門前、`reset_calls()`;送兩次 `POST /api/models/preload` `{"name":"qwen2.5:7b"}`,再呼叫 `GET /api/session`;斷言第一次 502、第二次 202 與 `preload.state` 為 `loading`、1 秒內 `remote.preload` 被呼叫 1 次、`state` 為 `ready` 且 `name` 不變);既有的 `Catalog.preload()` 在確認目錄之後才寫 `loading`,加上 T001b 的轉換不留狀態,這個案例會被滿足:先執行確認通過,再暫時把 `self._preloads[name] = loading` 搬到 `self.list()` 之前,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`、`components.schemas.PreloadState`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 5;`research.md` § R1
- [ ] T012b [US1] 🟢 /tdd 綠燈:US1-API-12 由既有的 `Catalog.preload()` 檢查順序與 T001b 的轉換滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-12 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T012a)
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`、`components.schemas.PreloadState`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 5;`research.md` § R1
- [ ] T013a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-13 的測試(工作階段就緒;tags 只回 `qwen2.5:0.5b`、ps 回空清單;送 `POST /api/models/preload` `{"name":"qwen2.5:7b"}`;斷言 404 `OLLAMA_NOT_FOUND`);既有的 `src/cgb/services/catalog.py` `Catalog.preload()` 找不到時 `raise ApiError(404, "OLLAMA_NOT_FOUND")`,在 T001b 的轉換之外(001 起),這個案例會被滿足:先執行確認通過,再暫時在 `Catalog.preload()` 以 `except (AdapterError, ApiError)` 包住確認目錄與 404、一律轉成 `ollama_error("OLLAMA_UNREACHABLE")`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § FR-002;`research.md` § R1;`plan.md` § 待決問題 Q2
- [ ] T013b [US1] 🟢 /tdd 綠燈:US1-API-13 由既有的 `Catalog.preload()` 的 404 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-13 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T013a)
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § FR-002;`research.md` § R1
- [ ] T014a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-14 的測試(工作階段就緒,T4、套用 context 4096;ps 回空清單;`list_local_models` 依序丟三種代碼,每種各呼叫一次 `GET /api/connect`;再讓 tags 照常、`list_loaded_models` 丟 `OLLAMA_TIMEOUT`,呼叫一次 `GET /api/connect`;斷言 502/502/504/504 與 `code`);006 起 `src/cgb/api/connect.py` 的 `get_connect_info` 已回 502/504,T003b 拿掉它自己的 `except` 之後改由 `Catalog.list()` 的轉換(T001b、T003b)與全域處理器回同樣的狀態碼,這個案例會被滿足:先執行確認通過,再暫時撤回 `Catalog.list()` 的轉換(`/api/connect` 變成 500),確認斷言失敗後撤回;`/api/connect` 的規格錨點是 006 的 `contracts/ui.openapi.yaml` § `paths./connect.get`,不在本 spec package
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ 
  - 📎 `spec.md` § FR-001;`research.md` § R1;`plan.md` § 待決問題 Q11、Q15;`contracts/ui.openapi.yaml` § `info.x-ollama-error-message`
- [ ] T014b [US1] 🟢 /tdd 綠燈:US1-API-14 由 T001b、T003b 在 `Catalog.list()` 的轉換滿足(T003b 已拿掉 `connect.py` 自己接 `AdapterError` 的那段),確認 `src/cgb/api/connect.py`、`src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-14 通過的程式碼(不在 `connect.py` 加回自己的轉換);執行 `tests/integration/test_007_catalog_errors.py`、`tests/integration/test_api_connect.py` 確認通過(依賴 T014a、T003b)
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ 
  - 📎 `spec.md` § FR-001;`research.md` § R1;`plan.md` § 待決問題 Q11;`contracts/ui.openapi.yaml` § `info.x-ollama-error-message`
- [ ] T015a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-15 的測試(同 US1-API-14,替身丟錯的 message 是 `Traceback (most recent call last): httpx.ConnectError 127.0.0.1:41234`;`list_local_models` 依序丟三種代碼,每種各呼叫一次 `GET /api/connect`;斷言三次的 `message` 各等於 `info.x-ollama-error-message` 的原句);T001b 以 `ollama_error()` 轉換、不覆寫 `message=`,`/api/connect` 拿到和 006 相同的 `MESSAGES` 說法,這個案例會被滿足:先執行確認通過,再暫時讓 `Catalog.list()` 的轉換以 `message=` 另給一句目錄專用的訊息,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ 
  - 📎 `spec.md` § FR-001;`research.md` § R1;`plan.md` § 待決問題 Q11、Q15;`contracts/ui.openapi.yaml` § `info.x-ollama-error-message`
- [ ] T015b [US1] 🟢 /tdd 綠燈:US1-API-15 由 T001b 的 `ollama_error()` 與既有的 `MESSAGES` 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-15 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T015a)
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ 
  - 📎 `spec.md` § FR-001;`research.md` § R1;`plan.md` § 待決問題 Q11;`contracts/ui.openapi.yaml` § `info.x-ollama-error-message`
- [ ] T016a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-16 的測試(工作階段就緒;tags 回 `qwen2.5:7b`、ps 回空清單;失敗的清單(tags、ps)× 三種代碼共六種組合,每種各呼叫一次 `GET /api/models` 與 `POST /api/models/preload` `{"name":"qwen2.5:7b"}`,組合之間把兩份清單重設成照常;斷言兩個操作的狀態碼依序 502、502、504、502、502、504 與對應的 `code`、12 次裡 0 次 500);T001b、T003b 在 `Catalog.list()` 的轉換涵蓋兩份清單與兩個操作,這個案例會被滿足:先執行確認通過,再暫時撤回 T003b 讀 ps 的轉換(ps 的三種組合回 500),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`paths./models/preload.post`
  - 📎 `spec.md` § NFR-001、SC-001;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T016b [US1] 🟢 /tdd 綠燈:US1-API-16 由 T001b、T003b 在 `Catalog.list()` 的轉換滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-16 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T016a)
  - 🧪 `testplan.md` § US1-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`paths./models/preload.post`
  - 📎 `spec.md` § NFR-001、SC-001;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T017a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_007_catalog_errors.py` 寫 US1-API-17 的測試(沒有開工作階段;`list_local_models`、`list_loaded_models` 都設成丟 `OLLAMA_UNREACHABLE`;送 `POST /api/models/preload` `{"name":"qwen2.5:7b"}`;斷言 503 `NO_READY_SESSION`、`list_local_models` 呼叫 0 次);既有的 `src/cgb/services/catalog.py` `Catalog.preload()` 第一行就呼叫 `SessionLifecycle.require_ready_base_url()` 丟 503,在 T001b 的轉換之外,這個案例會被滿足:先執行確認通過,再暫時在 `Catalog.preload()` 以 `except Exception` 包住 `require_ready_base_url()`、一律轉成 `ollama_error("OLLAMA_UNREACHABLE")`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § 邊界情況;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T017b [US1] 🟢 /tdd 綠燈:US1-API-17 由既有的 `Catalog.preload()` 在讀遠端之前檢查工作階段滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US1-API-17 通過的程式碼;執行 `tests/integration/test_007_catalog_errors.py` 確認通過(依賴 T017a)
  - 🧪 `testplan.md` § US1-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § 邊界情況;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`
- [ ] T018 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T001b~T017b 記下的重構清單(範圍限 `src/cgb/services/catalog.py`、`src/cgb/api/connect.py`),每改一小步執行這一節的測試檔 `tests/integration/test_007_catalog_errors.py`,變紅就撤回那一步;重構前後執行全部測試;不改 `tests/integration/test_007_catalog_errors.py`、`tests/integration/test_api_models.py`、`tests/integration/test_api_connect.py` 的斷言(依賴 T017b)
  - 🧪 `testplan.md` § US1-API-01~US1-API-17
  - 📎 `testplan.md` § 2.1;`research.md` § R1

### E1 前端 UI(瀏覽器,原生 HTML/CSS/JS)

本故事沒有不靠後端就看得到的畫面行為(`testplan.md` § 1 待測端點表 E1 那一列;畫面行為都放在跨端點驗收),這一節沒有任務。

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器接真的後端

> E2 節(T001~T018)都完成、驗收過後由主 agent 開始;真的 Chromium 接真的後端。新案例的測試都在 `tests/e2e/test_007_us1_catalog_errors.py`(新增,用 `tests/e2e/conftest.py` 的 `e2e_servers`;`ColabWorld`、`open_to_ready`、`world` 從 `e2e.test_us1_session` 匯入,對話替身的排法照 `tests/e2e/test_004_us2_chat.py` 的 `NdjsonReply`、`complete_turn`);執行環境上的模型照 `testplan.md` § 2.2 節首說明以 `world.models` 鋪,tags 以 `fakes.remote_ollama.list_local_models.raises(code, …)` 失敗、以 `.side_effect(world._local_models)` 恢復。`src/cgb/static/js/models.js`、`src/cgb/static/models.html`、`src/cgb/static/js/chat.js`、`src/cgb/static/chat.html`、`src/cgb/static/style.css` 只在這一節改,和 E2 節沒有共用檔;`chat.html`/`chat.js` 在 Phase 3 的跨端點驗收還會大改(對話保存),這一節只做讀不到目錄的說明與 US1-AJ-09 需要的最小保存。搜過 `tests/e2e/`:沒有既有測試斷言「讀不到目錄時對話頁顯示 `chat-no-session`」或「模型頁停在 `loading`」(`tests/e2e/test_locale.py` 的 `models_loading` 用閘門停住讀取,不是讀不到;`tests/e2e/test_004_us2_chat.py` 的 `chat-no-session` 都是真的沒有工作階段),這一節沒有要改寫的舊測試。

- [ ] T019a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us1_catalog_errors.py` 寫 US1-AJ-01 的測試(工作階段由工作階段頁開到就緒;替身的 `list_local_models` 丟 `OLLAMA_UNREACHABLE`;打開 `/models.html`;斷言 5 秒內 `[data-state="unavailable"]` 顯示、`#un-message` 等於合約 `info.x-ollama-error-message` 的 U 原句、`#un-code` 是 `OLLAMA_UNREACHABLE`、`[data-state="empty"]` 與 `[data-state="loading"]` 隱藏、頁面沒有「還沒有模型」、`#catalog li` 是 0 列),執行確認它因為「`loadCatalog()` 只處理成功與 `NO_READY_SESSION`,其他失敗時畫面停在『正在讀取執行環境上的模型…』」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `prototype/models.html` § `[data-state="unavailable"]`、`#un-message`、`#un-code`、`[data-state="empty"]`、`[data-state="loading"]`、`#catalog`
  - 📎 `spec.md` § FR-003、使用者故事 1 驗收情境 1、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8、Q16;`prototype/models.html` § `[data-group="catalog"]`
- [ ] T019b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/models.html`(照 `prototype/models.html` 在 `no-session` 前加 `[data-state="unavailable"]` 區塊:標題「執行環境上的模型」、`notice notice-error` 裡的「讀不到執行環境上的模型目錄」、`#un-message`、錯誤代碼小字 `#un-code`、`#reload`「重新讀取」與「看工作階段的狀態」;`#reload` 只放按鈕,點擊由 T022b 接上)、`src/cgb/static/js/models.js`(`loadCatalog()` 收到 502 時清空 `#catalog`,`#un-message` 填後端 `Error.message`、`#un-code` 填 `Error.code`,`showGroupState("catalog", "unavailable")`,不顯示 `empty`;504 由 T021b 加)與 `src/cgb/static/style.css`(把 `prototype/style.css` 檔尾「007:讀不到目錄、對話保存的提示」區段的 `.notice-line` 搬進檔尾的同名區段,只用既有的 `var(--…)`;`.notice .notice-head` 由 T024b、`.keep-line` 由 T027b 搬)只寫讓 US1-AJ-01 通過的程式碼,執行 `tests/e2e/test_007_us1_catalog_errors.py` 確認通過;看到要整理的地方記進重構清單(依賴 T019a)
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `prototype/models.html` § `[data-state="unavailable"]`、`#un-message`、`#un-code`、`[data-state="empty"]`、`[data-state="loading"]`、`#catalog`;`contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-003、NFR-003;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8、Q9;`contracts/ui.openapi.yaml` § `info.x-ollama-error-message`;`prototype/models.html` § `[data-group="catalog"]`;`prototype/style.css` § `.notice-line`
- [ ] T020a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us1_catalog_errors.py` 寫 US1-AJ-02 的測試(tags 照常回 3 個模型、替身的 `list_loaded_models` 丟 `OLLAMA_BAD_RESPONSE`;打開 `/models.html`;斷言 `unavailable` 顯示、`#un-message` 等於 B 原句、`#un-code` 是 `OLLAMA_BAD_RESPONSE`、`#catalog li` 0 列且三個模型名稱都不在頁面上、`empty` 隱藏);這個案例會被滿足:E2 節的 T003b 讓 `src/cgb/services/catalog.py` 的 `Catalog.list()` 在 ps 失敗時回 502 不回半套目錄,T019b 讓 `src/cgb/static/js/models.js` 的 `loadCatalog()` 收到 502 不分哪一份清單都顯示 `unavailable`:先執行確認通過,再暫時讓 `Catalog.list()` 把 ps 的 `AdapterError` 當成沒有已載入的模型(回 200 與三筆 `loaded: false` 的半套目錄),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `prototype/models.html` § `[data-state="unavailable"]`、`#un-message`、`#un-code`、`[data-state="empty"]`、`#catalog`
  - 📎 `spec.md` § FR-003、使用者故事 1 驗收情境 2、SC-001、邊界情況;`research.md` § R2;`plan.md` § 待決問題 Q16
- [ ] T020b [US1] 🟢 /tdd 綠燈:US1-AJ-02 由 T003b 與 T019b 滿足,確認 `src/cgb/static/js/models.js` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/models.js` 只寫讓 US1-AJ-02 通過的程式碼,執行 `tests/e2e/test_007_us1_catalog_errors.py` 確認通過;看到要整理的地方記進重構清單(依賴 T020a)
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `prototype/models.html` § `[data-state="unavailable"]`、`#un-message`、`#un-code`、`#catalog`、`[data-state="empty"]`;`contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-003、邊界情況;`research.md` § R2
- [ ] T021a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us1_catalog_errors.py` 寫 US1-AJ-03 的測試(替身的 tags 丟 `OLLAMA_TIMEOUT`;打開 `/models.html`;斷言 5 秒內 `unavailable` 顯示、`#un-message` 等於 T 原句、`#un-code` 是 `OLLAMA_TIMEOUT`、`empty` 隱藏),執行確認它因為「前端只認 502(T019b 只判斷 `status === 502`),504 落到其他分支而停在讀取中」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `prototype/models.html` § `[data-state="unavailable"]`、`#un-message`、`#un-code`、`[data-state="empty"]`
  - 📎 `spec.md` § FR-003、使用者故事 1 驗收情境 3、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q8、Q16
- [ ] T021b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/js/models.js` 的 `loadCatalog()` 只寫讓 US1-AJ-03 通過的程式碼(504 和 502 走同一個 `unavailable` 分支,說明照樣用後端的 `message`),執行 `tests/e2e/test_007_us1_catalog_errors.py` 確認通過;看到要整理的地方記進重構清單(依賴 T021a)
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `prototype/models.html` § `[data-state="unavailable"]`、`#un-message`、`#un-code`、`[data-state="empty"]`;`contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-003;`research.md` § R2;`plan.md` § 待決問題 Q8
- [ ] T022a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us1_catalog_errors.py` 寫 US1-AJ-04 的測試(tags 丟 `OLLAMA_UNREACHABLE`,打開 `/models.html` 等到 `unavailable`;把 tags 恢復成照常回 3 個模型,按 `#reload`「重新讀取」;斷言 5 秒內 `[data-state="normal"]` 顯示、`#catalog li` 3 列、`unavailable` 隱藏、替身的 `create_session` 呼叫次數仍是 1),執行確認它因為「『重新讀取』沒有接到 `loadCatalog()`(T019b 只放了按鈕)」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-04
  - ⚙ `prototype/models.html` § `#reload`、`[data-state="normal"]`、`[data-state="unavailable"]`、`#catalog`
  - 📎 `spec.md` § FR-003、使用者故事 1 驗收情境 5;`research.md` § R2;`plan.md` § 待決問題 Q16
- [ ] T022b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/js/models.js` 只寫讓 US1-AJ-04 通過的程式碼(`#reload` 的 click 接到 `loadCatalog()`,讀到目錄就照既有的 `show()` 回到 `normal`,`unavailable` 跟著 `showGroupState` 隱藏),執行 `tests/e2e/test_007_us1_catalog_errors.py` 確認通過;看到要整理的地方記進重構清單(依賴 T022a)
  - 🧪 `testplan.md` § US1-AJ-04
  - ⚙ `prototype/models.html` § `#reload`、`[data-state="normal"]`、`[data-state="unavailable"]`;`contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-003、使用者故事 1 驗收情境 5;`research.md` § R2
- [ ] T023a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us1_catalog_errors.py` 寫 US1-AJ-05 的測試(tags 丟 `OLLAMA_TIMEOUT`,打開 `/models.html` 等到 `unavailable`;清空 `world.models`、tags 恢復照常,按「重新讀取」;斷言 5 秒內 `[data-state="empty"]` 顯示、`unavailable` 隱藏);這個案例會被滿足:T022b 讓「重新讀取」走 `loadCatalog()`,既有 `src/cgb/static/js/models.js` 的 `show()` 讀到 0 個模型就顯示 `empty`:先執行確認通過,再暫時讓 `loadCatalog()` 讀到 0 個模型也顯示 `unavailable`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-AJ-05
  - ⚙ `prototype/models.html` § `[data-state="empty"]`、`[data-state="unavailable"]`、`#reload`
  - 📎 `spec.md` § FR-003、使用者故事 1 驗收情境 5;`research.md` § R2;`plan.md` § 待決問題 Q16
- [ ] T023b [US1] 🟢 /tdd 綠燈:US1-AJ-05 由 T022b 與既有的 `show()` 滿足,確認 `src/cgb/static/js/models.js` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/models.js` 只寫讓 US1-AJ-05 通過的程式碼,執行 `tests/e2e/test_007_us1_catalog_errors.py` 確認通過;看到要整理的地方記進重構清單(依賴 T023a)
  - 🧪 `testplan.md` § US1-AJ-05
  - ⚙ `prototype/models.html` § `[data-state="empty"]`、`[data-state="unavailable"]`;`contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-003;`research.md` § R2
- [ ] T024a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us1_catalog_errors.py` 寫 US1-AJ-06 的測試(打開 `/models.html` 等到 `#catalog li` 3 列;之後 tags 丟 `OLLAMA_UNREACHABLE`,按 `llama3.2:3b` 那一列的「預先載入」;斷言 5 秒內 `[data-state="preload-unavailable"]` 顯示、`#pu-name` 是 `llama3.2:3b`、`#pu-message` 等於 U 原句、`#pu-code` 是 `OLLAMA_UNREACHABLE`、`#catalog li` 仍 3 列、`llama3.2:3b` 與 `qwen2.5:7b` 仍有「預先載入」按鈕且沒有「載入中」、`qwen2.5:0.5b` 仍標「已載入」、`unavailable` 隱藏、替身的 `preload` 呼叫 0 次),執行確認它因為「`preload()` 收到非 202 時直接 `return`,畫面沒有任何提示」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-06
  - ⚙ `prototype/models.html` § `[data-state="preload-unavailable"]`、`#pu-name`、`#pu-message`、`#pu-code`、`[data-state="normal"]`、`#catalog`、`[data-state="unavailable"]`
  - 📎 `spec.md` § FR-003、使用者故事 1 驗收情境 4、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q16
- [ ] T024b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/models.html`(照 `prototype/models.html` 在 `[data-state="normal"]` 區塊的 `#catalog` 上方加 `[data-state="preload-unavailable"]` `data-group="preload-note"` 的 `notice notice-error`:「沒有預先載入 `#pu-name`」、`#pu-close`「關閉」、`#pu-message`、錯誤代碼小字 `#pu-code` 與「其他模型的狀態沒有改變…」;`#pu-close` 只放按鈕,點擊由 T025b 接上)、`src/cgb/static/js/models.js`(`preload()` 收到 502 時填 `#pu-name`、`#pu-message`、`#pu-code`,`showGroupState("preload-note", "preload-unavailable")`,不重讀目錄、不改 `current`;504 由 T025b 加;`pw-go` 經同一個 `preload()`,不另改)與 `src/cgb/static/style.css`(把 `prototype/style.css` 同一區段的 `.notice .notice-head` 搬進來)只寫讓 US1-AJ-06 通過的程式碼,執行 `tests/e2e/test_007_us1_catalog_errors.py` 確認通過;看到要整理的地方記進重構清單(依賴 T024a)
  - 🧪 `testplan.md` § US1-AJ-06
  - ⚙ `prototype/models.html` § `[data-state="preload-unavailable"]`、`#pu-name`、`#pu-message`、`#pu-code`、`[data-state="normal"]`、`[data-state="unavailable"]`;`contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § FR-002、FR-003、NFR-003;`research.md` § R2;`plan.md` § 待決問題 Q6、Q9;`prototype/style.css` § `.notice-head`
- [ ] T025a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us1_catalog_errors.py` 寫 US1-AJ-07 的測試(打開 `/models.html` 等到 3 列;tags 丟 `OLLAMA_TIMEOUT`,按 `qwen2.5:7b` 的「預先載入」,看到提示後按 `#pu-close`;tags 恢復照常,再按一次 `qwen2.5:7b` 的「預先載入」;斷言第一次的 `#pu-code` 是 `OLLAMA_TIMEOUT`、`#pu-message` 等於 T 原句,關閉後 `preload-unavailable` 隱藏且 `#catalog li` 仍 3 列,第二次 5 秒內 `qwen2.5:7b` 那一列顯示「載入中」、`preload-unavailable` 仍隱藏,替身的 `preload` 收到一次 `model="qwen2.5:7b"`),執行確認它因為「前端只處理預先載入的 502(T024b 只判斷 502),504 沒有提示」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-07
  - ⚙ `prototype/models.html` § `[data-state="preload-unavailable"]`、`#pu-code`、`#pu-message`、`#pu-close`、`#catalog`
  - 📎 `spec.md` § FR-003、使用者故事 1 驗收情境 4、驗收情境 5;`research.md` § R2;`plan.md` § 待決問題 Q16
- [ ] T025b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/js/models.js` 只寫讓 US1-AJ-07 通過的程式碼(`preload()` 的 504 和 502 走同一個提示;`#pu-close` 的 click 收起 `preload-note` 群組;`preload()` 送出前先收起上一次的提示,照原型的 `Proto.hideGroup("preload-note")`),執行 `tests/e2e/test_007_us1_catalog_errors.py` 確認通過;看到要整理的地方記進重構清單(依賴 T025a)
  - 🧪 `testplan.md` § US1-AJ-07
  - ⚙ `prototype/models.html` § `[data-state="preload-unavailable"]`、`#pu-close`、`#pu-code`、`#pu-message`;`contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § FR-003、使用者故事 1 驗收情境 5;`research.md` § R2
- [ ] T026a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us1_catalog_errors.py` 寫 US1-AJ-08 的測試(工作階段就緒、替身的 tags 丟 `OLLAMA_BAD_RESPONSE`;打開 `/chat.html`;斷言 5 秒內 `[data-state="chat-unavailable"]` 顯示、`[data-state="chat-unavailable"] #un-message` 等於 B 原句、`[data-state="chat-unavailable"] #un-code` 是 `OLLAMA_BAD_RESPONSE`、`chat-no-session` 與 `chat-no-models` 隱藏、`#send` 與 `#input` 停用),執行確認它因為「`chat.js` 的 `loadModels()` 對任何非成功的回應都設成 `chat-no-session`,讀不到目錄被說成沒有就緒的工作階段」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-08
  - ⚙ `prototype/chat.html` § `[data-state="chat-unavailable"]`、`#un-message`、`#un-code`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`#send`、`#input`
  - 📎 `research.md` § R2;`plan.md` § 待決問題 Q6、Q16
- [ ] T026b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/chat.html`(照 `prototype/chat.html` 在 `chat-no-models` 後加 `[data-state="chat-unavailable"]` `data-group="chat"`:`notice notice-error` 的 `notice-head` 裡「現在不能送出:讀不到執行環境上的模型目錄」與 `#reload`「重新讀取」、`#un-message`、錯誤代碼小字 `#un-code` 與「上面的對話保留著…」)與 `src/cgb/static/js/chat.js`(`loadModels()` 收到 502 時 `view = "chat-unavailable"`,`#un-message`、`#un-code` 填後端的 `message`、`code`,選單清空;503 與其他照舊 `chat-no-session`;`renderButtons()` 照既有的 `view !== "chat-ready"` 停用送出與輸入框;`#reload` 的 click 接到 `loadModels()`;504 由 T027b 加)只寫讓 US1-AJ-08 通過的程式碼,執行 `tests/e2e/test_007_us1_catalog_errors.py` 確認通過;看到要整理的地方記進重構清單(依賴 T026a、T019b,`.notice-line` 已由 T019b 搬進 `src/cgb/static/style.css`)
  - 🧪 `testplan.md` § US1-AJ-08
  - ⚙ `prototype/chat.html` § `[data-state="chat-unavailable"]`、`#un-message`、`#un-code`、`#reload`、`#send`、`#input`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`;`contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `research.md` § R2;`plan.md` § 待決問題 Q6、Q21;`spec.md` § NFR-003
- [ ] T027a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us1_catalog_errors.py` 寫 US1-AJ-09 的測試(打開 `/chat.html`,選 `qwen2.5:0.5b`,送出「你好」並收完替身的回覆「一二三四五六」;之後替身的 tags 丟 `OLLAMA_TIMEOUT`,重新整理對話頁;斷言 5 秒內 `chat-unavailable` 顯示、`[data-state="chat-unavailable"] #un-code` 是 `OLLAMA_TIMEOUT`、`#log .msg-user` 1 則「你好」、`#log .msg-bot` 1 則含「一二三四五六」、`[data-state="keep-on"]` 顯示、`[data-state="keep-cleared"]` 隱藏、`localStorage` 的 `cgb.chat.v1` 仍有 2 則 `messages`),執行確認它因為「讀不到目錄時不還原保存的對話,畫面只剩空白(現況對話只放在頁面變數裡,重新整理就消失)」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-09
  - ⚙ `prototype/chat.html` § `[data-state="chat-unavailable"]`、`#un-code`、`[data-state="keep-on"]`、`[data-state="keep-cleared"]`
  - 📎 `research.md` § R2、R3;`spec.md` § FR-004;`plan.md` § 待決問題 Q16;`prototype/chat.html` § `[data-group="keep"]`
- [ ] T027b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js`(`loadModels()` 的 504 和 502 走同一個 `chat-unavailable`;照 Rule 17 只做出讓這個案例通過的最小保存:`convo` 每次改變就把 research R3 的 `{session, model, messages, updatedAt}` 整份寫進 `localStorage` 的 `cgb.chat.v1`,`session` 取最近一次 `session.updated` 的 `name`,啟動時先讀回 `messages` 還原再 `loadModels()`,能保存時 `showGroupState("keep", "keep-on")`;依 `session.updated` 清除、`keep-checking`、`keep-cleared`、`keep-no-store`、中斷標示與 `chat-model-gone` 都留給 Phase 3;檔首「不寫進任何儲存,重新整理就消失」的註解改成存在瀏覽器的說法)、`src/cgb/static/chat.html`(照 `prototype/chat.html` 加 `[data-state="keep-on"]` `data-group="keep"` 的 `keep-line` 一行;`chat-ready` 的說明照原型拿掉「重新整理或離開就消失」那一句)與 `src/cgb/static/style.css`(把 `prototype/style.css` 同一區段的 `.keep-line` 搬進來)只寫讓 US1-AJ-09 通過的程式碼,執行 `tests/e2e/test_007_us1_catalog_errors.py` 確認通過,另跑一次 `tests/e2e/test_004_us2_chat.py` 確認最小保存沒有讓 004 的對話頁測試轉紅;看到要整理的地方記進重構清單(依賴 T027a、T026b)
  - 🧪 `testplan.md` § US1-AJ-09
  - ⚙ `prototype/chat.html` § `[data-state="chat-unavailable"]`、`#un-code`、`[data-state="keep-on"]`、`[data-state="keep-cleared"]`;`contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `research.md` § R2、R3;`spec.md` § FR-004、NFR-002;`prototype/chat.html` § `[data-group="keep"]`;`prototype/style.css` § `.keep-line`
- [ ] T028a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us1_catalog_errors.py` 寫 US1-AJ-10 的測試(同一個 browser context:分頁 A 開 `/models.html`、分頁 B 開 `/chat.html`,替身的 tags 丟 `OLLAMA_UNREACHABLE`,等到 A 顯示 `unavailable`、B 顯示 `chat-unavailable`;另開分頁 C 打開工作階段頁,在 `[data-state="ready"]` 按「結束」並確認(照 `tests/e2e/test_004_us2_chat.py` 的 `end_session_in_other_tab`);斷言 A 不重新整理 5 秒內 `[data-state="no-session"]` 顯示、`unavailable` 隱藏,B 不重新整理 5 秒內 `[data-state="chat-no-session"]` 顯示、`chat-unavailable` 隱藏);這個案例會被滿足:既有 `src/cgb/static/js/models.js` 的 `sessionUpdated()` 在工作階段狀態一變就 `loadCatalog()`、既有 `src/cgb/static/js/chat.js` 每則 `session.updated` 都 `loadModels()`,E2 節的 T006b 讓沒有就緒工作階段時先回 503 `NO_READY_SESSION`,兩頁既有的 `NO_READY_SESSION` 分支(T019b、T026b 保留)顯示 `no-session`/`chat-no-session`:先執行確認通過,再暫時讓 `loadCatalog()` 把 `NO_READY_SESSION` 也顯示成 `unavailable`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-AJ-10
  - ⚙ `prototype/models.html` § `[data-state="no-session"]`、`[data-state="unavailable"]`;`prototype/chat.html` § `[data-state="chat-no-session"]`、`[data-state="chat-unavailable"]`;`prototype/index.html` § `#end`
  - 📎 `spec.md` § FR-003、邊界情況;`research.md` § R2;`plan.md` § 待決問題 Q16
- [ ] T028b [US1] 🟢 /tdd 綠燈:US1-AJ-10 由既有的 `sessionUpdated()`、`startHeader` 的 `session.updated` 與 T019b、T026b 保留的 `NO_READY_SESSION` 分支滿足,確認 `src/cgb/static/js/models.js`、`src/cgb/static/js/chat.js` 不需要為它改程式碼(`src/cgb/static/index.html` 的「結束」是既有的 `data-go="confirm-stop"`,不改);紅燈時若它其實沒有通過,才在 `src/cgb/static/js/models.js`、`src/cgb/static/js/chat.js` 只寫讓 US1-AJ-10 通過的程式碼,執行 `tests/e2e/test_007_us1_catalog_errors.py` 確認通過;看到要整理的地方記進重構清單(依賴 T028a)
  - 🧪 `testplan.md` § US1-AJ-10
  - ⚙ `prototype/models.html` § `[data-state="no-session"]`、`[data-state="unavailable"]`;`prototype/chat.html` § `[data-state="chat-no-session"]`、`[data-state="chat-unavailable"]`;`prototype/index.html` § `#end`
  - 📎 `spec.md` § 邊界情況;`research.md` § R2
- [ ] T029a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us1_catalog_errors.py` 寫 US1-AJ-11 的測試(以 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT` 參數化;分頁 A 打開 `/models.html` 等到 3 列,之後 tags 丟這一次的代碼;在 A 按 `llama3.2:3b` 的「預先載入」,另開分頁 B 打開 `/chat.html`,回 A 按「重新讀取」;斷言 `#pu-message`、A 的 `#un-message` 等於這個代碼的原句,`#pu-code`、B 的 `#un-code` 是代碼原文,`#pu-name` 是 `llama3.2:3b`,`preload-unavailable` 去掉 `#pu-message`、`#pu-code`、`#pu-name`,B 的 `chat-unavailable` 與 A 的 `unavailable` 去掉 `#un-message`、`#un-code` 之後的文字(含「關閉」「重新讀取」)不含 A–Z、a–z);這個案例會被滿足:T019b、T024b、T026b 照原型放的標題、按鈕與小字都是中文,T021b、T025b、T027b 讓 504 也顯示後端的 `message`:先執行確認通過,再暫時把 `src/cgb/static/models.html` 的 `#pu-close` 文字改成「Close」,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-AJ-11
  - ⚙ `prototype/models.html` § `[data-state="preload-unavailable"]`、`#pu-message`、`#pu-code`、`#pu-name`、`#pu-close`、`[data-state="unavailable"]`、`#un-message`、`#un-code`、`#reload`;`prototype/chat.html` § `[data-state="chat-unavailable"]`、`#un-message`、`#un-code`、`#reload`
  - 📎 `spec.md` § NFR-003、FR-003;`plan.md` § 待決問題 Q17、Q21
- [ ] T029b [US1] 🟢 /tdd 綠燈:US1-AJ-11 由 T019b、T021b、T024b、T025b、T026b、T027b 滿足,確認 `src/cgb/static/models.html`、`src/cgb/static/chat.html`、`src/cgb/static/js/models.js`、`src/cgb/static/js/chat.js` 不需要為它改程式碼;紅燈時若它其實沒有通過,才在這四個檔只寫讓 US1-AJ-11 通過的程式碼,執行 `tests/e2e/test_007_us1_catalog_errors.py` 確認通過;看到要整理的地方記進重構清單(依賴 T029a)
  - 🧪 `testplan.md` § US1-AJ-11
  - ⚙ `prototype/models.html` § `[data-state="preload-unavailable"]`、`#pu-message`、`#pu-code`、`#pu-name`、`#pu-close`、`[data-state="unavailable"]`、`#un-message`、`#un-code`、`#reload`;`prototype/chat.html` § `[data-state="chat-unavailable"]`、`#un-message`、`#un-code`、`#reload`
  - 📎 `spec.md` § NFR-003;`plan.md` § 待決問題 Q17
- [ ] T030 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T019b~T029b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行這一節的測試檔 `tests/e2e/test_007_us1_catalog_errors.py`,變紅就撤回那一步;重構前後執行全部測試;不改 `tests/e2e/test_007_us1_catalog_errors.py` 的斷言(依賴 T029b)
  - 🧪 `testplan.md` § US1-AJ-01~US1-AJ-11
  - 📎 `testplan.md` § 2.2

### 介面覆蓋(US1)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui.openapi.yaml` § `paths./models.get` | T001b、T002b、T003b、T004b、T005b、T006b、T007b、T016b、T019b、T020b、T021b、T022b、T023b、T026b、T027b | T001a、T002a、T003a、T004a、T005a、T006a、T007a、T016a |
| `ui.openapi.yaml` § `components.schemas.Error` | T002b、T003b、T011b | T002a、T003a、T011a |
| `ui.openapi.yaml` § `components.schemas.ModelCatalog` | T005b | T005a |
| `ui.openapi.yaml` § `paths./models/preload.post` | T008b、T009b、T010b、T011b、T012b、T013b、T016b、T017b、T024b、T025b | T008a、T009a、T010a、T011a、T012a、T013a、T016a、T017a |
| `ui.openapi.yaml` § `components.schemas.PreloadState` | T008b、T012b | T008a、T012a |
| `models.html` § `[data-state="unavailable"]` | T019b、T020b、T021b、T022b、T023b、T024b、T028b、T029b | T019a、T020a、T021a、T022a、T023a、T024a、T028a、T029a |
| `models.html` § `#un-message` | T019b、T020b、T021b、T029b | T019a、T020a、T021a、T029a |
| `models.html` § `#un-code` | T019b、T020b、T021b、T029b | T019a、T020a、T021a、T029a |
| `models.html` § `[data-state="empty"]` | T019b、T020b、T021b、T023b | T019a、T020a、T021a、T023a |
| `models.html` § `[data-state="loading"]` | T019b | T019a |
| `models.html` § `#catalog` | T019b、T020b | T019a、T020a、T022a、T024a、T025a |
| `models.html` § `#reload` | T022b、T029b | T022a、T023a、T029a |
| `models.html` § `[data-state="normal"]` | T022b、T024b | T022a、T024a |
| `models.html` § `[data-state="preload-unavailable"]` | T024b、T025b、T029b | T024a、T025a、T029a |
| `models.html` § `#pu-name` | T024b、T029b | T024a、T029a |
| `models.html` § `#pu-message` | T024b、T025b、T029b | T024a、T025a、T029a |
| `models.html` § `#pu-code` | T024b、T025b、T029b | T024a、T025a、T029a |
| `models.html` § `#pu-close` | T025b、T029b | T025a、T029a |
| `chat.html` § `[data-state="chat-unavailable"]` | T026b、T027b、T028b、T029b | T026a、T027a、T028a、T029a |
| `chat.html` § `#un-message` | T026b、T029b | T026a、T029a |
| `chat.html` § `#un-code` | T026b、T027b、T029b | T026a、T027a、T029a |
| `chat.html` § `[data-state="chat-no-session"]` | T026b、T028b | T026a、T028a |
| `chat.html` § `[data-state="chat-no-models"]` | T026b | T026a |
| `chat.html` § `#send` | T026b | T026a |
| `chat.html` § `#input` | T026b | T026a |
| `chat.html` § `#reload` | T026b、T029b | T029a |
| `chat.html` § `[data-state="keep-on"]` | T027b | T027a |
| `chat.html` § `[data-state="keep-cleared"]` | T027b | T027a |
| `models.html` § `[data-state="no-session"]` | T028b | T028a |
| `index.html` § `#end` | T028b | T028a |

### 測試案例覆蓋(US1)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US1-API-01 | T001a | T001b | T018 |
| US1-API-02 | T002a | T002b | T018 |
| US1-API-03 | T003a | T003b | T018 |
| US1-API-04 | T004a | T004b | T018 |
| US1-API-05 | T005a | T005b | T018 |
| US1-API-06 | T006a | T006b | T018 |
| US1-API-07 | T007a | T007b | T018 |
| US1-API-08 | T008a | T008b | T018 |
| US1-API-09 | T009a | T009b | T018 |
| US1-API-10 | T010a | T010b | T018 |
| US1-API-11 | T011a | T011b | T018 |
| US1-API-12 | T012a | T012b | T018 |
| US1-API-13 | T013a | T013b | T018 |
| US1-API-14 | T014a | T014b | T018 |
| US1-API-15 | T015a | T015b | T018 |
| US1-API-16 | T016a | T016b | T018 |
| US1-API-17 | T017a | T017b | T018 |
| US1-AJ-01 | T019a | T019b | T030 |
| US1-AJ-02 | T020a | T020b | T030 |
| US1-AJ-03 | T021a | T021b | T030 |
| US1-AJ-04 | T022a | T022b | T030 |
| US1-AJ-05 | T023a | T023b | T030 |
| US1-AJ-06 | T024a | T024b | T030 |
| US1-AJ-07 | T025a | T025b | T030 |
| US1-AJ-08 | T026a | T026b | T030 |
| US1-AJ-09 | T027a | T027b | T030 |
| US1-AJ-10 | T028a | T028b | T030 |
| US1-AJ-11 | T029a | T029b | T030 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider`,再加 `uv run pytest -m realrun_local -q -p no:cacheprovider` 全綠;重構任務前後的測試結果相同

---

## Phase 3: User Story 2 - 對話紀錄保留到工作階段結束 (Priority: P2)

**Goal**: 對話頁的對話存在使用者的瀏覽器裡,重新整理、切到別頁再回來、同一個瀏覽器另開分頁都照原樣還原、可以接著講;工作階段以任何方式結束就清掉,開著的對話頁不用重新整理就清空;對話內容不寫入本系統的資料庫與日誌

**Independent Test**: 照 `testplan.md` § 3 的全部案例:E2 以 `uv run pytest tests/integration/test_007_events.py`、跨端點驗收以 `uv run pytest tests/e2e/test_007_us2_chat_keep.py` 執行全綠

### E2 後端 UI API(FastAPI REST 與 SSE)

> 這一節的測試都寫在新增的 `tests/integration/test_007_events.py`;讀 SSE 一律用測試行程內 uvicorn(`tests/conftest.py` 的 `live_servers`、`start_live_servers`,plan Q19),讀事件沿用 `tests/integration/test_api_events.py` 的 `sse_events`(以 `from integration.test_api_events import sse_events` 匯入),工作階段沿用 `tests/integration/test_api_session.py` 的 `ColabWorld`、`open_ready`、`wait_until`。T031a 在同一個檔建立共用的 `collect_session_updates(events, seconds)`(依序記下每一則 `session.updated` 的 `session` 與收到時的 `time.monotonic()`)與 `first_event(events)`(只讀第一則、不跳過其他事件),後面的紅燈沿用,同一個檔的任務依序做。007 後端不改推送(`contracts/ui.openapi.yaml` § `paths./events.get` 寫內容與時機不變,research R4):US2-API-01~US2-API-09 由既有程式做到,紅燈都寫成對照組(Rule 20)。這一節只用到本節的檔,和 E1、跨端點驗收沒有共用檔依賴。
- [ ] T031a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_007_events.py` 寫 US2-API-01 的測試(`start_live_servers(make_app())` 起真的 HTTP;`ColabWorld(fakes)`、`open_ready` 開到就緒記下 `name`;一條 `GET /api/events` 讀完快照後,送 `DELETE /api/session`,以 `collect_session_updates` 讀 2 秒;斷言 2 秒內有一則 `state` 為 `ended`、`name` 等於開啟時的 `name`,那一則之後 0.5 秒內沒有 `state` 為 `opening`、`ready`、`applying_tuning`、`reconnecting`、`ending` 的推送);既有的 `src/cgb/services/session_lifecycle.py` `SessionLifecycle._run_end` 以 `SessionsRepo.update(name, state="ended", …)` 寫入,`src/cgb/repos/sessions.py` `SessionsRepo._changed` 觸發 `src/cgb/api/__init__.py` 登記的 listener 推 `lifecycle.current()`(`SessionsRepo.latest()` 的最新一列),這個案例會被滿足:先執行確認通過,再暫時把 `_run_end` 最後那次 `self._repo.update(name, state="ended", …)` 換成直接對 `sessions` 執行 `UPDATE … SET state='ended'`(不經過 listener),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、使用者故事 2 驗收情境 6;`research.md` § R4;`plan.md` § 待決問題 Q1、Q12、Q19
- [ ] T031b [US2] 🟢 /tdd 綠燈:US2-API-01 由既有的 `SessionLifecycle._run_end` 經 `SessionsRepo.update` 與 `src/cgb/api/__init__.py` 的推送 listener 滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/session_lifecycle.py` 只寫讓 US2-API-01 通過的程式碼;執行 `tests/integration/test_007_events.py` 確認通過(依賴 T031a)
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [ ] T032a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_007_events.py` 寫 US2-API-02 的測試(照 T031a 的訂閱方式,`make_app()` 用 `fake_clock`;以 `PUT /api/settings` 把閒置時限設 1 分鐘(沿用 `tests/integration/test_api_idle.py` 的 `set_idle_timeout`),`open_ready` 開到就緒記下 `name` 與 `idle.deadline`;`fake_clock.set(deadline + 1 秒)` 後讀 SSE 2 秒;斷言 2 秒內有一則 `state` 為 `ended`、`endReason` 為 `IDLE_TIMEOUT`、`name` 等於開啟時的 `name`);既有的 `src/cgb/services/idle_monitor.py` `IdleMonitor._check` 到期時呼叫 `SessionLifecycle.end(end_reason="IDLE_TIMEOUT")`,和 T031a 走同一條 `_run_end` → `SessionsRepo.update` → listener 的路徑,這個案例會被滿足:先執行確認通過,再暫時讓 `IdleMonitor._check` 到期時改成直接呼叫 `self._state.colab.stop_session` 後以 SQL 把那一列改成 `ended`(不經過 listener),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、使用者故事 2 驗收情境 6;`research.md` § R4;`plan.md` § 待決問題 Q12、Q19
- [ ] T032b [US2] 🟢 /tdd 綠燈:US2-API-02 由既有的 `IdleMonitor._check` → `SessionLifecycle.end` 滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/idle_monitor.py` 只寫讓 US2-API-02 通過的程式碼;執行 `tests/integration/test_007_events.py` 確認通過(依賴 T032a)
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [ ] T033a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_007_events.py` 寫 US2-API-03 的測試(照 T031a;`open_ready` 開到就緒記下 `name`;`world.alive.remove(name)`、`fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")` 後讀 SSE 2 秒;斷言 2 秒內有一則 `state` 為 `lost`、`endReason` 為 `RECLAIMED_BY_COLAB`、`name` 等於開啟時的 `name`);既有的 `src/cgb/services/health_monitor.py` `HealthMonitor._reconnect` 在 `colab sessions` 列不到時呼叫 `_mark_reclaimed`,以 `SessionsRepo.update(name, **reclaimed_fields(…))`(`src/cgb/domain/session_state.py` `reclaimed_fields`)寫入並觸發推送,這個案例會被滿足:先執行確認通過,再暫時讓 `_mark_reclaimed` 只在記憶體記下被收回、不寫 `sessions`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、使用者故事 2 驗收情境 6;`research.md` § R4;`plan.md` § 待決問題 Q12、Q19
- [ ] T033b [US2] 🟢 /tdd 綠燈:US2-API-03 由既有的 `HealthMonitor._mark_reclaimed` 與 `reclaimed_fields` 滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/health_monitor.py` 只寫讓 US2-API-03 通過的程式碼;執行 `tests/integration/test_007_events.py` 確認通過(依賴 T033a)
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [ ] T034a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_007_events.py` 寫 US2-API-04 的測試(照 T031a;重連時限 2 秒(`tests/conftest.py` 的 `TEST_TIMEOUTS`);沿用 `tests/integration/test_api_health.py` 的 `record_rounds(world, fakes)` 讓 `open_tunnel` 一直回 `TUNNEL_UNREACHABLE`;`open_ready` 開到就緒記下 `name`;`fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))` 後讀 SSE 4 秒;斷言有 `state` 為 `reconnecting`、`name` 相同的一則,第一次 `close_tunnel` 之後 1.8 到 2.5 秒之間收到 `state` 為 `lost`、`endReason` 為 `RECONNECT_TIMEOUT`、`name` 相同的一則);既有的 `HealthMonitor._reconnect`(`src/cgb/services/health_monitor.py`)開始時寫 `reconnecting`、期限到時以 `SessionsRepo.update(name, state="lost", end_reason="RECONNECT_TIMEOUT", …)` 寫入同一列,這個案例會被滿足:先執行確認通過,再暫時拿掉期限到時寫 `lost` 的那次 `self._repo.update`(只停止重連),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、使用者故事 2 驗收情境 6;`research.md` § R4;`plan.md` § 待決問題 Q12、Q19
- [ ] T034b [US2] 🟢 /tdd 綠燈:US2-API-04 由既有的 `HealthMonitor._reconnect` 滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/health_monitor.py` 只寫讓 US2-API-04 通過的程式碼;執行 `tests/integration/test_007_events.py` 確認通過(依賴 T034a)
  - 🧪 `testplan.md` § US2-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [ ] T035a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_007_events.py` 寫 US2-API-05 的測試(照 T031a;沿用 `tests/integration/test_api_switch.py` 的 `with_loaded_model(world, fakes)`;`open_ready` 開到就緒記下 `old`;送 `POST /api/session/restart {runtimeType:{gpu:"L4",highMem:false}}` 記下回應的 `name`,讀 SSE 直到收到 `name` 不是 `old` 且 `state` 為 `ready` 的一則或 4 秒到;斷言 2 秒內收到 `name` 不是 `old` 的一則、第一則新 `name` 等於 restart 回應的 `name`、之後沒有任何一則 `name` 等於 `old`);既有的 `src/cgb/services/runtime_switch.py` `RuntimeSwitch.restart` 以 `SessionLifecycle.reserve`(`_new_name`)為新的執行環境寫新的一列,`src/cgb/api/__init__.py` 的 listener 推的是 `lifecycle.current()`(`SessionsRepo.latest()`),舊的那台在 `RuntimeSwitch._run` 改成 `ended` 時推出的仍是新的那一列,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/api/__init__.py` 推 `session.updated` 的 listener 改成推 `SessionsRepo.update` 剛寫入的那一列(`session_payload(repo.get(<剛寫入的 name>))`),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、使用者故事 2 驗收情境 6;`research.md` § R4;`plan.md` § 待決問題 Q12、Q19
- [ ] T035b [US2] 🟢 /tdd 綠燈:US2-API-05 由既有的 `RuntimeSwitch.restart` 換新名稱與 `src/cgb/api/__init__.py` 推 `lifecycle.current()` 的 listener 滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/runtime_switch.py` 只寫讓 US2-API-05 通過的程式碼;執行 `tests/integration/test_007_events.py` 確認通過(依賴 T035a)
  - 🧪 `testplan.md` § US2-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [ ] T036a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_007_events.py` 寫 US2-API-06 的測試(照 T034a 以 `record_rounds` 讓重連一直失敗;`open_ready` 開到就緒記下 `name`;`check_health` 失敗一次後以 `wait_until` 等到 `GET /api/session` 的 `state` 為 `reconnecting`,這時才新開一條 `GET /api/events`,以 `first_event` 讀第一則;斷言第一則的 `event:` 是 `session.updated`、`state` 是 `reconnecting`、`name` 等於開啟時的 `name`);既有的 `src/cgb/api/events.py` `subscribe_events` 連上時第一則就送 `session.updated`,內容是 `lifecycle.current()` 經 `src/cgb/domain/session_state.py` `session_payload` 的完整 `Session`(含 `name`),之後才送 `downloads.snapshot`、`autoDownload.updated`,這個案例會被滿足:先執行確認通過,再暫時把 `subscribe_events` 的 `downloads.snapshot` 移到 `session.updated` 之前送,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、邊界情況;`research.md` § R4;`plan.md` § 待決問題 Q12、Q19
- [ ] T036b [US2] 🟢 /tdd 綠燈:US2-API-06 由既有的 `subscribe_events` 快照順序與 `session_payload` 滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/api/events.py` 只寫讓 US2-API-06 通過的程式碼;執行 `tests/integration/test_007_events.py` 確認通過(依賴 T036a)
  - 🧪 `testplan.md` § US2-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、邊界情況;`research.md` § R4
- [ ] T037a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_007_events.py` 寫 US2-API-07 的測試(`start_live_servers(make_app())` 起一次,`ColabWorld(fakes)`、`open_ready` 開到就緒記下 `name`,以那個 `LiveServers.stop()` 停掉(同一個 `db_path` 與替身狀態);沿用 `tests/integration/test_api_recovery.py` 的 `reset_calls(fakes)`;再以 `start_live_servers(make_app())` 重新起後端,立刻開一條 `GET /api/events` 讀 3 秒;斷言第一則的 `event:` 是 `session.updated`、`name` 等於重啟前的 `name`、`state` 是 `ready`、`reconnecting`、`applying_tuning`、`ending` 其中之一,3 秒內收到 `state` 為 `ready`、`name` 相同的一則(連上時的快照也算));既有的 `src/cgb/services/recovery.py` `Recovery._run` 以 `SessionsRepo.latest_unfinished()` 取上一個行程留下的那一列,`_reattach` 在接回前不改它的狀態與名稱,接回完成後 `self._repo.update(name, state="ready", active_slot=1)` 寫回同一列,快照是 `lifecycle.current()` 的那一列,這個案例會被滿足:先執行確認通過,再暫時在 `Recovery._run` 開頭把 `unfinished` 那一列以 `self._repo.update(…, state="ended", active_slot=None)` 標成已結束,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、邊界情況;`research.md` § R4;`plan.md` § 待決問題 Q12、Q19
- [ ] T037b [US2] 🟢 /tdd 綠燈:US2-API-07 由既有的 `Recovery._run`、`_reattach` 接回同一列滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/services/recovery.py` 只寫讓 US2-API-07 通過的程式碼;執行 `tests/integration/test_007_events.py` 確認通過(依賴 T037a)
  - 🧪 `testplan.md` § US2-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、邊界情況;`research.md` § R4
- [ ] T038a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_007_events.py` 寫 US2-API-08 的測試(照 T031a;`open_ready` 開到就緒記下 `a`,`DELETE /api/session` 後以 `wait_until` 等到 `ended`;再 `open_ready` 開第二個記下 `b`(假時鐘下兩個的 `opened_at` 相同);新開一條 `GET /api/events` 以 `first_event` 讀第一則;斷言 `event:` 是 `session.updated`、`name` 等於 `b`、`state` 是 `ready`);既有的 `src/cgb/repos/sessions.py` `SessionsRepo.latest()` 以 `ORDER BY opened_at DESC, rowid DESC` 取最新一列,`opened_at` 相同時以 `rowid` 分出後寫入的 `b`,這個案例會被滿足:先執行確認通過,再暫時把 `latest()` 的 `, rowid DESC` 拿掉,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、使用者故事 2 驗收情境 7;`research.md` § R4;`plan.md` § 待決問題 Q12、Q19
- [ ] T038b [US2] 🟢 /tdd 綠燈:US2-API-08 由既有的 `SessionsRepo.latest()` 次序滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/repos/sessions.py` 只寫讓 US2-API-08 通過的程式碼;執行 `tests/integration/test_007_events.py` 確認通過(依賴 T038a)
  - 🧪 `testplan.md` § US2-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、使用者故事 2 驗收情境 7;`research.md` § R4
- [ ] T039a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_007_events.py` 寫 US2-API-09 的測試(沿用 `tests/integration/test_api_chat.py` 的 `bridge` fixture 與 `chunk`、`DONE`,以 `from integration.test_api_chat import DONE, bridge, chunk` 匯入,`NdjsonReply` 取自 `tests/fakes/ollama_server.py`;`bridge.ready()` 開到就緒,`caplog.set_level(logging.DEBUG)`;`CHAT_MARK = "cgb-test-007-對話-不該留下"`、`CONTROL_MARK = "cgb-test-007-對照-應找得到"`,在同一個檔建立 `count_mark(text_or_bytes, mark)`(字串與 UTF-8 位元組都搜);替身 `/api/chat` 回 `NdjsonReply([chunk(CHAT_MARK), DONE])`;一條 `GET /api/events` 在背景把每一行原文附加進字串;先以 `logging.getLogger("cgb").info(CONTROL_MARK)` 寫一行日誌,並在 `tmp_path / "control.sqlite"`(`journal_mode=WAL`、不 checkpoint、不碰 `db_path`)寫入一列 `CONTROL_MARK`;再送 `POST /api/chat {model, messages:[{role:"user",content:CHAT_MARK}]}` 讀完、`DELETE /api/session` 等到 SSE 收到 `ended`、等 0.2 秒;斷言則1~則7:對照組在日誌與 `control.sqlite`+`-wal` 都找得到,`CHAT_MARK` 在日誌、`db_path` 與同名 `-wal`、`-journal` 的位元組、`sqlite_master` 每張表的全表掃描、SSE 原文都是 0 次,SSE 原文至少有一則 `state` 為 `ended` 的 `session.updated`);既有的 `src/cgb/api/chat.py` `chat` 只轉送、不記本文也不寫 `sessions`,`src/cgb/api/events.py` 只推 `session_payload` 的欄位(004 的 `tests/integration/test_api_chat.py` `test_對話內容不寫進日誌與資料庫` 已驗日誌與資料庫),這個案例會被滿足:先執行確認通過,再暫時在 `chat` 路由裡以 `services.events.session_updated({**services.lifecycle.current(), "lastMessage": <最後一則 content>})` 推出最後一則對話,確認則6 失敗後撤回
  - 🧪 `testplan.md` § US2-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § NFR-002、SC-004;`research.md` § R6;`plan.md` § 待決問題 Q18、Q19、Q20(`POST /api/chat` 是 004 的 `contracts/ui.openapi.yaml` § `chat`,不在本 spec package)
- [ ] T039b [US2] 🟢 /tdd 綠燈:US2-API-09 由既有的 `src/cgb/api/chat.py` `chat`(不記本文、不寫資料庫)與 `subscribe_events` 只推 `Session` 滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/api/chat.py` 只寫讓 US2-API-09 通過的程式碼;執行 `tests/integration/test_007_events.py` 確認通過(依賴 T039a)
  - 🧪 `testplan.md` § US2-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § NFR-002、SC-004;`research.md` § R6;`plan.md` § 待決問題 Q18、Q20
- [ ] T040 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T031b~T039b 記下的重構清單(範圍限 `src/cgb/api/`、`src/cgb/services/`、`src/cgb/repos/`;這一節預期沒有實作改動時,只整理 `tests/integration/test_007_events.py` 的共用輔助函式,不動斷言),每改一小步執行 `tests/integration/test_007_events.py`,變紅就撤回那一步;重構前後執行全部測試;不改 `tests/integration/test_007_events.py` 的斷言(依賴 T039b)
  - 🧪 `testplan.md` § US2-API-01~US2-API-09
  - 📎 `testplan.md` § 3.1

### E1 前端 UI(瀏覽器,原生 HTML/CSS/JS)

本故事沒有不靠後端就看得到的畫面行為(`testplan.md` § 1 待測端點表 E1 那一列;保存、還原與清除都要先拿到 `session.updated`),這一節沒有任務。

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器接真的後端

> 測試檔:全部新增在 `tests/e2e/test_007_us2_chat_keep.py`(Playwright,`tests/e2e/conftest.py` 的 `e2e_servers`;同一個 browser context 以 `context.new_page()` 開多個分頁)。共用 helper 由 T041a 建立、後面的紅燈沿用:從 `tests/e2e/test_004_us2_chat.py` 匯入 `open_chat`、`send`、`complete_turn`、`start_hanging_turn`、`replies`、`chat_requests`、`chunk`、`DONE`、`QWEN`、`LLAMA`、`end_session_in_other_tab`、`assert_traditional_chinese`,從 `tests/e2e/test_us1_session.py` 匯入 `world`、`open_to_ready`、`restart_backend`、`wait_until`,從 `tests/e2e/test_us4_usage.py` 匯入 `sync_browser_clock`、`advance_clocks`,從 `tests/e2e/test_004_us4_hf.py` 匯入 `api`;本檔新增 `saved(page)`(`localStorage.getItem("cgb.chat.v1")` 解析成 dict 或 None)、`two_rounds(page, fakes)`(節首的「兩問兩答」)、`wait_session(e2e_servers, pred)`(以 `GET /api/session` 輪詢,回傳輪詢到的那一刻,當「結束後 5 秒」的起點,plan Q24)。
> 實作檔:`src/cgb/static/js/chat.js`、`src/cgb/static/chat.html`、`src/cgb/static/style.css`;Phase 2(T019~T030)已改過同兩個檔的 `loadModels()` 與 `chat-unavailable`,而且 US1-AJ-09 的綠燈(T027b)已建立 `cgb.chat.v1` 的基本保存、還原與 `[data-state="keep-on"]`,本節的綠燈以它為底、不重做。`src/cgb/static/js/header.js` 不必改:`startHeader(handlers)` 已把 `session.updated` 的 payload 轉給頁面(research R4),本節只改 `chat.js` 傳進去的處理函式。後端推送(`ended`、`lost`、新名稱、重連中與重啟後的快照)由本故事 E2 節 T031b~T039b 做到,本節在 E2 節(T040)完成後才開始。
> 原型 `prototype/index.html` 與實作的對照(紅燈照實作的 locator 寫):原型的 `#end` 是就緒畫面的「結束」,實作是 `[data-state="ready"]` 裡名為「結束」的按鈕加確認畫面的 `#stop`(004 `end_session_in_other_tab` 的做法);原型的 `#switch` 是就緒畫面的「變更類型」,實作是 `[data-state="ready"]` 的「變更類型」、`[data-state="confirm-switch"]` 選 L4、再按 `#switch`;原型的 `[data-state="ending"]`、`[data-state="opening"]` 在實作是 `[data-state="stopping"]`(或變更類型時的 `[data-state="switching"]`)與 `[data-state="starting"]`。
- [ ] T041a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-01 的測試(順手建立節首說明的 helper;`open_chat(page, world, QWEN, LLAMA)` 後把 `#model` 改選預設以外的那一個記為 M,`two_rounds` 之後重新整理;斷言 `#log .msg` 依序 4 則與內容、`#model` 的值是 M、第二則回覆下方含「tokens/s」),執行確認它因為「沒有保存 `model`,還原時 `#model` 回到選單預設的第一個;或只保存 `role`、`content`,還原的回覆丟了 `status`、`tps` 而不顯示速度」這類實作而失敗;若 Phase 2 US1-AJ-09 的綠燈已完整保存這些欄位而一寫完就通過,改照對照組做:暫時讓保存的值不帶 `model`,確認則2 失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `prototype/chat.html` § `[data-state="chat-ready"]`、`#model`、`#input`、`#send`、`#log`
  - 📎 `spec.md` § FR-004、SC-002、§ 使用者故事 2 驗收情境 1;`research.md` § R3、R6
- [ ] T041b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js`、`src/cgb/static/chat.html` 只寫讓 US2-AJ-01 通過的程式碼:以 US1-AJ-09 綠燈(T027b)的保存為底,`cgb.chat.v1` 的值補齊成 research R3 的 `{session, model, messages, updatedAt}`,`messages` 每則 `{role, content, thinking, status, message, ms, tps}`(使用者那則 `status` 為 `done`,`startedAt` 不存);`session` 取 `startHeader` 的 `session.updated` 處理函式記下的最近一則 `Session.name`,第一次送出時綁定(R4 第 4 點);送出時與 `finishTurn` 整份寫入(每收到一段就寫入留給 T045b);載入時讀回 `model` 設成 `#model` 的值,`renderModels()` 不再把它蓋成選單第一個;`chat.html` 的 `[data-state="chat-ready"]` 拿掉 004 的「對話只留在這個頁面,不寫進資料庫與日誌,重新整理或離開就消失」,文字照原型,`chat.js` 檔首「只放在這個頁面的變數裡…重新整理就消失」的註解一起改(已搜 `tests/`,沒有斷言這句話的測試);執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過;看到要整理的地方記進重構清單(依賴 T041a;同一個 `src/cgb/static/js/chat.js` 依賴 T027b)
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `prototype/chat.html` § `[data-state="chat-ready"]`、`#model`、`#log`
  - 📎 `spec.md` § FR-004、NFR-002;`research.md` § R3、R4
- [ ] T042a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-02 的測試(`two_rounds` 之後點頁首「模型」,等模型頁的目錄出現,再點頁首「對話」回來;斷言 `#log .msg` 依序 4 則);T041b 每次載入都讀 `cgb.chat.v1`、在送出與完成時就寫入(不靠 `beforeunload`),這個案例會被滿足:先執行確認通過,再暫時讓 `chat.js` 只在 `performance.getEntriesByType("navigation")[0].type === "reload"` 時還原,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-02
  - ⚙ `prototype/chat.html` § `#log`
  - 📎 `spec.md` § FR-004、SC-002、§ 使用者故事 2 驗收情境 2;`research.md` § R3
- [ ] T042b [US2] 🟢 /tdd 綠燈:US2-AJ-02 由 T041b 的載入時還原與每次改變就寫入滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-02 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T042a)
  - 🧪 `testplan.md` § US2-AJ-02
  - ⚙ `prototype/chat.html` § `#log`
  - 📎 `spec.md` § FR-004;`research.md` § R3
- [ ] T043a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-03 的測試(分頁 A `two_rounds` 之後,同一個 context `new_page()` 開分頁 B 打開 `/chat.html`;斷言 B 的 `#log .msg` 依序 4 則);T041b 存在 `localStorage`、鍵固定為 `cgb.chat.v1`,這個案例會被滿足:先執行確認通過,再暫時把 `chat.js` 的保存與讀取改成 `sessionStorage`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-03
  - ⚙ `prototype/chat.html` § `#log`
  - 📎 `spec.md` § FR-004、SC-002、§ 使用者故事 2 驗收情境 3;`research.md` § R3
- [ ] T043b [US2] 🟢 /tdd 綠燈:US2-AJ-03 由 T041b 存在 `localStorage` 的固定鍵滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-03 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T043a)
  - 🧪 `testplan.md` § US2-AJ-03
  - ⚙ `prototype/chat.html` § `#log`
  - 📎 `spec.md` § FR-004;`research.md` § R3
- [ ] T044a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-04 的測試(以 `parametrize` 跑重新整理、切到模型頁再回來、另開分頁三種;回到對話頁後以 `page.expect_request` 攔下送出「第三則」的 `POST /api/chat`,替身回 `七八九` + `DONE`;斷言本文 `messages` 正好是前兩輪加「第三則」、畫面最後一則是「七八九」);T041b 還原時把保存的 `messages` 放回 `convo`,`send()` 照 `convo.map(({role, content}) => …)` 全部送出,這個案例會被滿足:先執行確認通過,再暫時讓 `send()` 只送 `[{role:"user", content:text}]`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-04
  - ⚙ `prototype/chat.html` § `#input`、`#send`、`#log`
  - 📎 `spec.md` § FR-005、SC-002、§ 使用者故事 2 驗收情境 4;`research.md` § R5
- [ ] T044b [US2] 🟢 /tdd 綠燈:US2-AJ-04 由 T041b 把保存的訊息放回 `convo` 與既有的 `send()` 滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-04 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T044a)
  - 🧪 `testplan.md` § US2-AJ-04
  - ⚙ `prototype/chat.html` § `#send`
  - 📎 `spec.md` § FR-005;`research.md` § R5
- [ ] T045a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-05 的測試(`start_hanging_turn` 送出「你好」,替身回「一」「二」後 `then="hang"`,等最後一則回覆顯示「一二」且 `[data-state="turn-streaming"]` 可見後重新整理;斷言最後一則內容「一二」、下方顯示「中斷:離開頁面時這則回覆還沒有完成」、不含「tokens/s」、保存的最後一則 `status` 是 `left`),執行確認它因為「只在回覆完成時才寫入(T041b 的寫入時機),回覆途中重新整理後這一則整個不見;或還原時把 `streaming` 的那一則當成 `done` 畫上耗時與速度」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-05
  - ⚙ `prototype/chat.html` § `[data-state="turn-streaming"]`、`[data-state="turn-interrupted"]`、`[data-state="${name}"]`、`#log`
  - 📎 `spec.md` § FR-008、§ 使用者故事 2 驗收情境 5;`research.md` § R5;`plan.md` § 待決問題 Q4;`prototype/chat.html` § `[data-group="turn"]`
- [ ] T045b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js`、`src/cgb/static/chat.html` 只寫讓 US2-AJ-05 通過的程式碼:`send()` 每收到一段就整份寫入(`status` 維持 `streaming`,research R3、R5);還原時遇到 `status` 是 `streaming` 的回覆,不論有沒有收到內容都改成新的中斷狀態 `left`、`message` 為「離開頁面時這則回覆還沒有完成。」,改完立刻寫回,`[data-group="turn"]` 顯示 `turn-interrupted`,以 `[data-state="turn-interrupted"] [data-message]` 填入說明(和 `finishTurn` 的 `[data-state="turn-${status}"] [data-message]` 同一種寫法,原型 `turn()` 的 `[data-state="${name}"]`);頁面卸載時被中止的 `fetch` 進 `catch`,不得把 `streaming` 改成 `interrupted`、`unavailable` 再寫回(`pagehide` 只設「卸載中」旗標擋掉寫入,不在 `pagehide` 寫入,見 T060a);`chat.html` 的 `turn-streaming`、`turn-interrupted` 文字照原型。依 Rule 5 搜 `chat.js` 裡 `convo` 狀態值的每一處清單,`left` 只加進需要的:`CUT` 加 `left: "中斷:離開頁面時這則回覆還沒有完成"`(`footer()` 的 `m.status in CUT` 分支因此顯示中斷、不畫速度,`renderLog()` 的 `is-cut` 也走 `in CUT`);`finishTurn()` 的 `turn-${reply.status}` 不會收到 `left`(`left` 只在還原時出現),所以不加 `turn-left` 這一列;`STREAM_FAILURE`、`BEFORE_STREAM` 是串流結果的對照、不加;`send()` 的 `catch` 只看當次的 `reply.status === "streaming"`、不動;`send()` 組 `messages` 不依 `status` 過濾、不動(T047a 依賴);`src/cgb/static/js/view.js` 的 `interrupted` 是紀錄頁的標籤、不同概念不改;執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過;看到要整理的地方記進重構清單(依賴 T045a)
  - 🧪 `testplan.md` § US2-AJ-05
  - ⚙ `prototype/chat.html` § `[data-state="turn-streaming"]`、`[data-state="turn-interrupted"]`、`[data-state="${name}"]`
  - 📎 `spec.md` § FR-008;`research.md` § R5;`plan.md` § 待決問題 Q4、Q26;`prototype/chat.html` § `[data-group="turn"]`
- [ ] T046a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-06 的測試(替身回 `NdjsonReply([], then="hang")`,送出「你好」,等 `[data-state="turn-streaming"]` 出現後點頁首「模型」,再點「對話」回來;斷言最後一則下方顯示「中斷:離開頁面時這則回覆還沒有完成」、頁面不含「沒有回覆:Ollama 暫時無法使用」、`#log .msg` 共 2 則);T045b 不論有沒有收到內容都改成 `left`,且送出時已寫入空的那一則,這個案例會被滿足:先執行確認通過,再暫時照原型 `restore()` 寫成 `m.content || m.thinking ? "left" : "unavailable"`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-06
  - ⚙ `prototype/chat.html` § `[data-state="turn-streaming"]`、`[data-state="turn-interrupted"]`、`[data-state="${name}"]`
  - 📎 `spec.md` § FR-008、§ 使用者故事 2 驗收情境 5;`research.md` § R5;`plan.md` § 待決問題 Q4
- [ ] T046b [US2] 🟢 /tdd 綠燈:US2-AJ-06 由 T045b 的「不論有沒有內容都改成 `left`」與送出時寫入滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過(例如切頁時中止的 `fetch` 仍把這一則寫成 `unavailable`),才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-06 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T046a)
  - 🧪 `testplan.md` § US2-AJ-06
  - ⚙ `prototype/chat.html` § `[data-state="turn-interrupted"]`、`[data-state="turn-streaming"]`、`[data-state="${name}"]`
  - 📎 `spec.md` § FR-008;`plan.md` § 待決問題 Q4
- [ ] T047a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-07 的測試(照 US2-AJ-05 重新整理後,替身回 `四五六` + `DONE`,送出「繼續」並以 `page.expect_request` 攔下 `POST /api/chat`;斷言本文 `messages` 正好是 `[user「你好」, assistant「一二」, user「繼續」]`、原本那則下方仍顯示「中斷:離開頁面時這則回覆還沒有完成」);`send()` 不依 `status` 過濾、`footer()` 依每則自己的 `status` 畫(T044b、T045b),這個案例會被滿足:先執行確認通過,再暫時讓 `send()` 濾掉 `status === "left"` 的那一則,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-07
  - ⚙ `prototype/chat.html` § `#input`、`#send`、`#log`
  - 📎 `spec.md` § FR-005、FR-008、§ 使用者故事 2 驗收情境 4、§ 使用者故事 2 驗收情境 5;`research.md` § R5
- [ ] T047b [US2] 🟢 /tdd 綠燈:US2-AJ-07 由既有的 `send()` 與 T045b 的 `CUT.left` 滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-07 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T047a)
  - 🧪 `testplan.md` § US2-AJ-07
  - ⚙ `prototype/chat.html` § `#send`
  - 📎 `spec.md` § FR-005、FR-008;`research.md` § R5
- [ ] T048a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-08 的測試(`start_hanging_turn` 顯示「一二」後按 `#stop`,等 `[data-state="turn-stopped"]` 出現「已停止這則回覆」,再重新整理;斷言最後一則下方顯示「已停止」、不含「中斷」二字);`stop()` 先記成 `stopped`、`finishTurn` 寫入(T041b),T045b 只把 `streaming` 改成 `left`,這個案例會被滿足:先執行確認通過,再暫時讓還原把所有不是 `done` 的回覆都改成 `left`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-08
  - ⚙ `prototype/chat.html` § `#stop`、`[data-state="turn-stopped"]`、`[data-state="${name}"]`
  - 📎 `spec.md` § FR-004、FR-008;`research.md` § R5
- [ ] T048b [US2] 🟢 /tdd 綠燈:US2-AJ-08 由既有的 `stop()`、T041b 的完成時寫入與 T045b 只轉 `streaming` 滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過(例如中止後 `finishTurn` 前就沒寫入、保存裡仍是 `streaming`),才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-08 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T048a)
  - 🧪 `testplan.md` § US2-AJ-08
  - ⚙ `prototype/chat.html` § `[data-state="turn-stopped"]`、`[data-state="${name}"]`
  - 📎 `spec.md` § FR-008;`research.md` § R5
- [ ] T049a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-09 的測試(分頁 A `two_rounds`、`page.evaluate("window.__cgbMark = 1")`;同一個 context 以 `end_session_in_other_tab(context)` 在分頁 B 的就緒畫面按「結束」並確認;以 `wait_session` 輪詢到 `ended` 起算 5 秒;斷言 A 顯示「工作階段已結束,對話已清除」、`#log .msg` 0 則、保存是 null、`window.__cgbMark` 仍是 1),執行確認它因為「只在載入時比對工作階段,開著的對話頁沒有處理 `session.updated`,要重新整理才清」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-09
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`、`#log`;`prototype/index.html` § `[data-state="ready"]`、`#end`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、SC-003、§ 使用者故事 2 驗收情境 6;`research.md` § R4;`plan.md` § 待決問題 Q24;`prototype/chat.html` § `[data-group="keep"]`
- [ ] T049b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js`、`src/cgb/static/chat.html` 只寫讓 US2-AJ-09 通過的程式碼:`startHeader({"session.updated": …})` 的處理函式改收 `payload.session`,新增 `sessionUpdated(session)`:`END_STATES = ["none", "ended", "open_failed", "lost"]`(research R4 第 2 點;`reconnecting`、`applying_tuning`、`ending` 不算),已綁定工作階段且 `session.state` 在 `END_STATES` 時清空 `convo` 與畫面、`removeItem("cgb.chat.v1")`、`[data-group="keep"]` 顯示 `keep-cleared`(`#cleared-name` 填原本綁定的名稱)、`turn-idle`,再照舊 `loadModels()`,不呼叫 `location.reload()`;讀不到目錄(`chat-unavailable`)不算結束、不清(Phase 2 US1-AJ-09 不得轉紅);回覆途中(`busy` 不是 null)或最後一則回覆是 `lost`(串流收到 `SESSION_ENDED`)時這一則先不清,留給 T054b,讓 004 的 `tests/e2e/test_004_us2_chat.py` 的 `test_回覆途中工作階段被結束_保留已收到的內容並標示中斷`、`test_回覆途中在另一個分頁變更類型_保留已收到的內容並說明正在變更類型`、`test_對話頁各種狀態的文字都是繁體中文` 在 T054b 之前維持綠燈;執行 `tests/e2e/test_007_us2_chat_keep.py`、`tests/e2e/test_004_us2_chat.py` 確認通過;看到要整理的地方記進重構清單(依賴 T049a;推送 `ended` 由 T031b 做到)
  - 🧪 `testplan.md` § US2-AJ-09
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`;`contracts/ui.openapi.yaml` § `paths./events.get`;`prototype/index.html` § `[data-state="ready"]`
  - 📎 `spec.md` § FR-006、SC-003;`research.md` § R4;`plan.md` § 待決問題 Q22、Q26;`prototype/chat.html` § `[data-group="keep"]`
- [ ] T050a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-10 的測試(照 `tests/e2e/test_us4_idle.py`:`PUT /api/settings` 閒置時限 1 分鐘、第一次打開頁面前 `sync_browser_clock(page, fake_clock)`;`two_rounds` 之後 `advance_clocks(page, fake_clock, 61)`,以 `wait_session` 輪詢到 `ended`、`endReason` 為 `IDLE_TIMEOUT` 起算 5 秒;斷言「工作階段已結束,對話已清除」、`#log .msg` 0 則、保存是 null);T049b 只看 `state` 不看 `endReason`,後端閒置結束的推送由 T032b 做到,這個案例會被滿足:先執行確認通過,再暫時讓 `sessionUpdated` 只在 `endReason === "USER_ENDED"` 時清,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-10
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`、`#log`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、SC-003、§ 使用者故事 2 驗收情境 6;`research.md` § R4;`plan.md` § 待決問題 Q24
- [ ] T050b [US2] 🟢 /tdd 綠燈:US2-AJ-10 由 T049b 的 `END_STATES` 與 T032b 的推送滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-10 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T050a)
  - 🧪 `testplan.md` § US2-AJ-10
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [ ] T051a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-11 的測試(`two_rounds` 之後照 `tests/e2e/test_reopen_after_end.py`:`world.alive.clear()`、`fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", …))`,以 `wait_session` 輪詢到 `lost` 起算 5 秒;斷言「工作階段已結束,對話已清除」、`#log .msg` 0 則、保存是 null);T049b 的 `END_STATES` 含 `lost`,推送 `lost` 由 T033b 做到,這個案例會被滿足:先執行確認通過,再暫時把 `END_STATES` 改成只有 `["ended"]`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-11
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`、`#log`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、SC-003、§ 使用者故事 2 驗收情境 6;`research.md` § R4
- [ ] T051b [US2] 🟢 /tdd 綠燈:US2-AJ-11 由 T049b 的 `END_STATES` 與 T033b 的推送滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-11 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T051a)
  - 🧪 `testplan.md` § US2-AJ-11
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [ ] T052a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-12 的測試(`fakes.tunnel.open_tunnel.raises("TUNNEL_FAILED", "ssh exited")`;`two_rounds` 之後 `fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", …))`,經過 `reconnecting` 後重連逾時,以 `wait_session` 輪詢到 `lost` 起算 5 秒;斷言「工作階段已結束,對話已清除」、`#log .msg` 0 則、保存是 null);T049b 對每一則 `session.updated` 都依當下的 `state` 判斷、沒有「重連中先不判斷」的旗標,推送重連逾時的 `lost` 由 T034b 做到,這個案例會被滿足:先執行確認通過,再暫時在收到 `reconnecting` 時設一個不會解除的「先不判斷」旗標,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-12
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`、`#log`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、SC-003、§ 使用者故事 2 驗收情境 6;`research.md` § R4
- [ ] T052b [US2] 🟢 /tdd 綠燈:US2-AJ-12 由 T049b 與 T034b 的推送滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-12 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T052a)
  - 🧪 `testplan.md` § US2-AJ-12
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [ ] T053a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-13 的測試(分頁 A `two_rounds`、以 `GET /api/session` 記下 `name` N;分頁 B 在就緒畫面按「變更類型」、選 L4、按「確認,結束並重開」,經過實作的 `switching`/`starting` 回到 `ready`;以 `wait_session` 輪詢到 `name` 第一次不是 N 起算 5 秒;斷言 A 顯示「工作階段已結束,對話已清除」、`#log .msg` 0 則,新的工作階段就緒後保存是 null 或其 `session` 不是 N;依 plan Q26 不斷言 `#cleared-name`),執行確認它因為「只看 `state` 不比 `name`:變更類型經過 `ending` → `opening` → `ready`,沒有停在結束狀態,舊對話被當成新工作階段的接著用」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-13
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`、`#log`;`prototype/index.html` § `[data-state="ready"]`、`#switch`、`[data-state="ending"]`、`[data-state="opening"]`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、SC-003、§ 使用者故事 2 驗收情境 6;`research.md` § R4;`plan.md` § 待決問題 Q24、Q26
- [ ] T053b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-13 通過的程式碼:`sessionUpdated` 的清除條件加上「`session.name` 有值且和綁定的名稱不同」(research R4 第 2 點),`ending` 本身不清、等名稱變了或到結束狀態才清;回覆途中的例外照 T049b 留給 T054b;執行 `tests/e2e/test_007_us2_chat_keep.py`、`tests/e2e/test_004_us2_chat.py` 確認通過;看到要整理的地方記進重構清單(依賴 T053a、T049b;新名稱的推送由 T035b 做到)
  - 🧪 `testplan.md` § US2-AJ-13
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`;`contracts/ui.openapi.yaml` § `paths./events.get`;`prototype/index.html` § `[data-state="ready"]`、`[data-state="ending"]`、`[data-state="opening"]`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [ ] T054a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-14 的測試(分頁 A 一問一答後送出「再說一次」,替身回 `NdjsonReply([chunk("四")], then="hang")`,畫面顯示「四」;分頁 B `end_session_in_other_tab`;A 顯示「工作階段已結束,對話已清除」後等 1 秒,再重新整理 A;斷言結束後 5 秒內 `#log .msg` 0 則、清空後 1 秒保存是 null、重新整理後 `#log .msg` 0 則),執行確認它因為「照 004 先走 `turn-lost` 保留「四」不清(T049b 留下的回覆途中例外)」這類實作而失敗;拿掉例外後還要能抓到「清空之後,還在讀的串流收尾(`endReply(…, "lost")`、`finishTurn`、每段寫入)又把中斷的那一則整份寫回 `cgb.chat.v1`」
  - 🧪 `testplan.md` § US2-AJ-14
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`、`#log`;`prototype/index.html` § `[data-state="ready"]`、`#end`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、FR-008、SC-003、§ 使用者故事 2 驗收情境 6;`research.md` § R4、R5;`plan.md` § 待決問題 Q22
- [ ] T054b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-14 通過的程式碼:拿掉 T049b、T053b 的回覆途中例外,`sessionUpdated` 判定結束時先 `busy.controller.abort()`、`busy = null` 再清空(research R4 第 2 點「回覆途中就先停止那一則」);清空之後同一則的 `endReply`、`finishTurn` 與每段寫入一律不再寫入保存(`finishTurn` 既有的 `!convo.includes(reply)` 檢查延伸到寫入);同一個任務依 `plan.md` § 待決問題 Q22(使用者本人選 a)改寫或刪除 004 的三支舊測試:刪除 `tests/e2e/test_004_us2_chat.py` 的 `test_回覆途中工作階段被結束_保留已收到的內容並標示中斷`(行為改由 US2-AJ-14 涵蓋)與 `test_回覆途中在另一個分頁變更類型_保留已收到的內容並說明正在變更類型`(變更類型的清除改由 US2-AJ-13 涵蓋,但它沒有回覆在途中;回覆途中變更類型這個組合沒有專門案例,走和 US2-AJ-14 同一段清除與「清空後不再寫入」,見 `spec.md` § 假設),同檔 `test_對話頁各種狀態的文字都是繁體中文` 的最後一段「回覆途中工作階段被結束」把 `shown("turn-lost")` 改成斷言 `[data-state="keep-cleared"]` 可見並通過 `assert_traditional_chinese`;`chat.html` 的 `turn-lost` 留著(變更類型途中先收到 `SESSION_ENDED`、名稱還沒變之前仍會顯示);執行 `tests/e2e/test_007_us2_chat_keep.py`、`tests/e2e/test_004_us2_chat.py` 確認通過、不留 skip;看到要整理的地方記進重構清單(依賴 T054a)
  - 🧪 `testplan.md` § US2-AJ-14
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`;`contracts/ui.openapi.yaml` § `paths./events.get`;`prototype/index.html` § `[data-state="ready"]`
  - 📎 `spec.md` § FR-006、FR-008;`research.md` § R4、R5;`plan.md` § 待決問題 Q22
- [ ] T055a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-15 的測試(`two_rounds` 後關掉對話頁分頁;在工作階段頁按「結束」並確認,等 `[data-state="ended"]`,再按「開啟」經過開啟中到就緒;以 `context.add_init_script` 在新分頁裝 `MutationObserver` 記下 `#log` 是否曾出現「再說一次」;新開分頁打開 `/chat.html`,等 `[data-state="chat-ready"]` 出現後再等 1 秒;斷言 `#log .msg` 0 則、`MutationObserver` 記到 0 次、保存是 null),執行確認它因為「載入時先畫保存的對話、收到快照才清,上一個工作階段的對話閃一下(research R4 的「等第一則快照再畫」沒做)」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-15
  - ⚙ `prototype/chat.html` § `[data-state="keep-checking"]`、`[data-state="chat-ready"]`、`#log`;`prototype/index.html` § `[data-state="ready"]`、`#end`、`[data-state="ending"]`、`[data-state="ended"]`、`[data-state="opening"]`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、SC-003、§ 使用者故事 2 驗收情境 7;`research.md` § R4
- [ ] T055b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js`、`src/cgb/static/chat.html`、`src/cgb/static/style.css` 只寫讓 US2-AJ-15 通過的程式碼:載入時先不畫保存的對話,`[data-group="keep"]` 顯示 `keep-checking`、`#log` 只顯示「正在確認工作階段…」、`[data-group="chat"]` 先隱藏、`#input`、`#send`、`#model`、`#clear` 先停用;收到第一則 `session.updated` 快照才決定:`state` 是 `ready`、`applying_tuning`、`reconnecting`、`ending` 之一且 `name` 等於保存的 `session` → 還原(T041b、T045b 的還原搬到這裡,`left` 的轉換照舊),否則 `removeItem` 畫空白(research R4 第 1 點);讀不到目錄時照樣還原(Phase 2 US1-AJ-09 不得轉紅);`chat.html` 加原型的 `keep-checking` 那一行;`style.css` 照 Rule 5 打開 `prototype/style.css` 檔尾「007:讀不到目錄、對話保存的提示」比對,把 `.keep-line` 搬進來(`.notice .notice-head`、`.notice-line` 若 Phase 2 已搬就不重複),只用既有的 `var(--…)`;執行 `tests/e2e/test_007_us2_chat_keep.py`、`tests/e2e/test_004_us2_chat.py` 確認通過;看到要整理的地方記進重構清單(依賴 T055a;快照取最新一列由 T038b 做到)
  - 🧪 `testplan.md` § US2-AJ-15
  - ⚙ `prototype/chat.html` § `[data-state="keep-checking"]`、`[data-state="chat-ready"]`;`contracts/ui.openapi.yaml` § `paths./events.get`;`prototype/index.html` § `[data-state="ready"]`、`[data-state="ending"]`、`[data-state="ended"]`、`[data-state="opening"]`
  - 📎 `spec.md` § FR-006、SC-003;`research.md` § R4
- [ ] T056a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-16 的測試(`two_rounds` 後關掉對話頁分頁;在工作階段頁變更類型成 L4,等新的工作階段就緒;新開分頁打開 `/chat.html`,等 `[data-state="chat-ready"]`;斷言 `#log .msg` 0 則、保存是 null);T055b 載入時同時比對 `state` 與 `name`,這個案例會被滿足:先執行確認通過,再暫時讓載入時只看 `state` 是不是 `ready`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-16
  - ⚙ `prototype/chat.html` § `[data-state="chat-ready"]`、`#log`;`prototype/index.html` § `[data-state="ready"]`、`#switch`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、SC-003、§ 使用者故事 2 驗收情境 7;`research.md` § R4
- [ ] T056b [US2] 🟢 /tdd 綠燈:US2-AJ-16 由 T055b 載入時的名稱比對滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-16 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T056a)
  - 🧪 `testplan.md` § US2-AJ-16
  - ⚙ `prototype/chat.html` § `#log`、`[data-state="chat-ready"]`;`contracts/ui.openapi.yaml` § `paths./events.get`;`prototype/index.html` § `[data-state="ready"]`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [ ] T057a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-17 的測試(`two_rounds` 後關掉對話頁分頁;在工作階段頁按「結束」並確認、等 `[data-state="ended"]`,不開新的;新開分頁打開 `/chat.html`;斷言 `[data-state="chat-no-session"]` 出現、`#log .msg` 0 則、保存是 null);T055b 載入時要求 `state` 在可還原的四種之內,且 T049b 收到 `ended` 會清,這個案例會被滿足:先執行確認通過,再暫時讓載入時只比對 `name`、同時讓 `sessionUpdated` 不看 `END_STATES`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-17
  - ⚙ `prototype/chat.html` § `[data-state="chat-no-session"]`、`#log`;`prototype/index.html` § `[data-state="ready"]`、`#end`、`[data-state="ended"]`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、SC-003;`research.md` § R4
- [ ] T057b [US2] 🟢 /tdd 綠燈:US2-AJ-17 由 T055b 載入時的狀態比對與 T049b 滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-17 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T057a)
  - 🧪 `testplan.md` § US2-AJ-17
  - ⚙ `prototype/chat.html` § `[data-state="chat-no-session"]`;`contracts/ui.openapi.yaml` § `paths./events.get`;`prototype/index.html` § `[data-state="ready"]`、`[data-state="ended"]`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [ ] T058a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-18 的測試(`two_rounds` 後按 `#clear`,再重新整理;斷言按下後 `#log .msg` 0 則、保存是 null,重新整理後 0 則,`#clear` 的文字是「清除」),執行確認它因為「只清 `convo` 與畫面、沒有 `removeItem`,重新整理又還原;或按鈕文字沿用 004 的「清空」」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-18
  - ⚙ `prototype/chat.html` § `#clear`、`#log`
  - 📎 `spec.md` § FR-007、NFR-003、§ 使用者故事 2 驗收情境 8;`research.md` § R3;`plan.md` § 待決問題 Q7、Q23
- [ ] T058b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js`、`src/cgb/static/chat.html` 只寫讓 US2-AJ-18 通過的程式碼:`chat.html` 的 `#clear` 文字「清空」改「清除」(plan Q7 a);`clearChat()` 在清空 `convo` 後 `removeItem("cgb.chat.v1")`、不寫 `{messages: []}` 空殼(research R3),並解除綁定的工作階段;`chat.js` 裡「清空」的註解(`finishTurn` 的「回覆途中按了清空」、`clearChat` 上方)一起改成「清除」;依 plan Q23 a 搜過 `tests/`:沒有斷言按鈕文字「清空」的測試,`tests/e2e/test_004_us2_chat.py` 的 `test_清空與換模型都清掉畫面與要帶上的對話` 只用 `#clear`、不必改,`tests/e2e/test_004_g_03.py` 只有說明文字提到「清空」、不必改;執行 `tests/e2e/test_007_us2_chat_keep.py`、`tests/e2e/test_004_us2_chat.py` 確認通過;看到要整理的地方記進重構清單(依賴 T058a)
  - 🧪 `testplan.md` § US2-AJ-18
  - ⚙ `prototype/chat.html` § `#clear`
  - 📎 `spec.md` § FR-007、NFR-003;`research.md` § R3;`plan.md` § 待決問題 Q7、Q23
- [ ] T059a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-19 的測試(`#model` 選 `qwen2.5:latest` 後 `two_rounds`,改選 `llama3.2:3b`,再重新整理;斷言改選後 `#log .msg` 0 則、保存是 null,重新整理後 0 則、`#model` 的值是 `llama3.2:3b`);`#model` 的 `change` 走 `clearChat()`,T058b 已讓它 `removeItem`,這個案例會被滿足:先執行確認通過,再暫時在 `change` 處理函式裡先以舊的 `convo` 與新模型整份寫入再清畫面(不 `removeItem`),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-19
  - ⚙ `prototype/chat.html` § `#model`、`#log`
  - 📎 `spec.md` § FR-007、§ 使用者故事 2 驗收情境 8;`research.md` § R3
- [ ] T059b [US2] 🟢 /tdd 綠燈:US2-AJ-19 由既有的 `change` → `clearChat()` 與 T058b 的 `removeItem` 滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過(例如重新整理後 `#model` 沒落在 `llama3.2:3b`),才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-19 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T059a)
  - 🧪 `testplan.md` § US2-AJ-19
  - ⚙ `prototype/chat.html` § `#model`
  - 📎 `spec.md` § FR-007;`research.md` § R3
- [ ] T060a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-20 的測試(同一個 context 開分頁 A、B 都打開對話頁且都是空的;A 完成「你好」→「一二三」,再重新整理 B;斷言 B 的 `#log .msg` 依序「你好」「一二三」);T041b~T058b 只在自己的 `convo` 改變或判定結束時寫入或移除,沒有在 `pagehide`、`beforeunload` 寫入(T045b 只設旗標),而且 `sessionUpdated` 只在已綁定時清,這個案例會被滿足:先執行確認通過,再暫時在 `pagehide` 把自己的 `convo` 整份寫入(空的就 `removeItem`),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-20
  - ⚙ `prototype/chat.html` § `#log`
  - 📎 `spec.md` § FR-004、§ 邊界情況;`research.md` § R3
- [ ] T060b [US2] 🟢 /tdd 綠燈:US2-AJ-20 由「只在改變時寫入」與 `sessionUpdated` 只清已綁定的對話滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過(例如 B 收到 A 對話後推送的 `session.updated` 時以空的 `convo` 寫入),才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-20 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T060a)
  - 🧪 `testplan.md` § US2-AJ-20
  - ⚙ `prototype/chat.html` § `#log`
  - 📎 `spec.md` § 邊界情況;`research.md` § R3
- [ ] T061a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-21 的測試(A 完成「你好」→「一二三」後開分頁 B 還原同一輪;替身前兩次 `POST /api/chat` 各在第一段後停在一個 `Gate`;A 送「甲」、B 送「乙」,先放行 A 到 `DONE` 等 A 完成,再放行 B 等 B 完成;開分頁 C 打開對話頁;斷言 C 的 `#log .msg` 依序 user「你好」、assistant「一二三」、user「乙」、B 收到的回覆,共 4 則);T041b、T045b 每次都以自己的 `convo` 整份覆寫,這個案例會被滿足:先執行確認通過,再暫時讓寫入前先讀回保存、接上自己的新訊息再寫,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-21
  - ⚙ `prototype/chat.html` § `#input`、`#send`、`#log`
  - 📎 `spec.md` § 邊界情況;`research.md` § R3
- [ ] T061b [US2] 🟢 /tdd 綠燈:US2-AJ-21 由 T041b、T045b 的整份覆寫(最後寫入的為準)滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-21 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T061a)
  - 🧪 `testplan.md` § US2-AJ-21
  - ⚙ `prototype/chat.html` § `#log`
  - 📎 `spec.md` § 邊界情況;`research.md` § R3
- [ ] T062a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-22 的測試(`context.add_init_script` 讓 `Storage.prototype.setItem` 一律丟 `DOMException("…", "QuotaExceededError")`,`page.on("pageerror")` 記下未處理的例外;打開對話頁送出「你好」;斷言顯示「這個瀏覽器無法保存對話,離開或重新整理後會消失」、回覆「一二三」出現且下方顯示速度、`pageerror` 0 次),執行確認它因為「每段寫入的 `setItem` 例外沒接住,`send()` 在第一段就丟出,回覆停在「正在回覆」」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-22
  - ⚙ `prototype/chat.html` § `[data-state="keep-no-store"]`、`#send`、`#log`
  - 📎 `spec.md` § FR-004、§ 邊界情況;`research.md` § R3;`plan.md` § 待決問題 Q25;`prototype/chat.html` § `[data-group="keep"]`
- [ ] T062b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js`、`src/cgb/static/chat.html` 只寫讓 US2-AJ-22 通過的程式碼:所有寫入收進同一個函式,`setItem` 丟例外(`QuotaExceededError`)就停止保存、不再試、不往外拋,`[data-group="keep"]` 顯示 `keep-no-store`,對話照 004 照常可用(research R3「不能保存時」);提示文字照原型,不用 `DOMException.message`;`chat.html` 的 `keep-no-store` 若 Phase 2 未加就照原型加上;執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過;看到要整理的地方記進重構清單(依賴 T062a)
  - 🧪 `testplan.md` § US2-AJ-22
  - ⚙ `prototype/chat.html` § `[data-state="keep-no-store"]`
  - 📎 `spec.md` § FR-004、§ 邊界情況;`research.md` § R3;`plan.md` § 待決問題 Q25;`prototype/chat.html` § `[data-group="keep"]`
- [ ] T063a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-23 的測試(`context.add_init_script` 把 `window.localStorage` 的 getter 改成丟 `DOMException("…", "SecurityError")`,`page.on("pageerror")` 記下例外;打開對話頁送出「你好」;斷言顯示「這個瀏覽器無法保存對話,離開或重新整理後會消失」、回覆「一二三」出現、`pageerror` 0 次),執行確認它因為「`chat.js` 在模組頂層或載入時直接讀 `window.localStorage`,例外讓整支腳本沒跑完,頁面停在「正在確認工作階段…」;或只用 `try` 包住 `setItem`、沒包讀取(T062b)」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-23
  - ⚙ `prototype/chat.html` § `[data-state="keep-no-store"]`、`#log`
  - 📎 `spec.md` § FR-004、§ 邊界情況;`research.md` § R3;`plan.md` § 待決問題 Q25
- [ ] T063b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-23 通過的程式碼:取得 `window.localStorage` 本身與 `getItem`、`removeItem` 也收進 T062b 的同一處、各自以 `try` 包住,任何一個丟例外就當成不能保存(啟動時先試寫一次,research R3),讀不到時當成沒有保存過;執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過;看到要整理的地方記進重構清單(依賴 T063a、T062b)
  - 🧪 `testplan.md` § US2-AJ-23
  - ⚙ `prototype/chat.html` § `[data-state="keep-no-store"]`
  - 📎 `spec.md` § FR-004、§ 邊界情況;`research.md` § R3
- [ ] T064a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-24 的測試(`two_rounds`、記下 N;`add_init_script` 的 `MutationObserver` 記下「工作階段已結束,對話已清除」是否曾出現;以 `restart_backend(e2e_servers, start_live_servers, make_app)` 重新起後端,等 `GET /api/session` 回 `ready` 且 `name` 是 N,再等 3 秒,之後重新整理;斷言重新整理前 `#log .msg` 4 則、`MutationObserver` 0 次、重新整理後依序 4 則);`chat.js` 不處理 `EventSource` 的 `error`,T049b、T053b 只依 `session.updated` 的 `state` 與 `name` 判斷,後端重啟後的快照由 T037b 確保不是 `none`,這個案例會被滿足:先執行確認通過,再暫時在 `src/cgb/static/js/api.js` 的 `subscribe()` 加 `source.onerror = () => handlers["session.updated"]?.({session: {state: "none"}})`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-24
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`、`#log`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、§ 邊界情況;`research.md` § R4
- [ ] T064b [US2] 🟢 /tdd 綠燈:US2-AJ-24 由 T049b、T053b 只看推送內容與 T037b 的快照滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過(例如 `EventSource` 重連後的快照被 T055b 當成「第一則」而重畫或清掉),才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-24 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T064a)
  - 🧪 `testplan.md` § US2-AJ-24
  - ⚙ `prototype/chat.html` § `#log`、`[data-state="keep-cleared"]`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、§ 邊界情況;`research.md` § R4
- [ ] T065a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-25 的測試(`two_rounds`、記下 N、`MutationObserver` 同 US2-AJ-24;`fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", …))` 一次、重連第 1 輪就接回;等 `GET /api/session` 經過 `reconnecting` 回到 `ready` 且 `name` 是 N,再等 3 秒;斷言 `#log .msg` 4 則、`MutationObserver` 0 次、保存的 `session` 是 N);T049b 的 `END_STATES` 不含 `reconnecting`,重連中的推送帶同一個 `name`(T034b、T036b),這個案例會被滿足:先執行確認通過,再暫時把 `reconnecting` 加進 `END_STATES`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-25
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`、`#log`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、§ 邊界情況;`research.md` § R4
- [ ] T065b [US2] 🟢 /tdd 綠燈:US2-AJ-25 由 T049b 的 `END_STATES` 與 T034b、T036b 的推送滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-25 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T065a)
  - 🧪 `testplan.md` § US2-AJ-25
  - ⚙ `prototype/chat.html` § `#log`、`[data-state="keep-cleared"]`;`contracts/ui.openapi.yaml` § `paths./events.get`
  - 📎 `spec.md` § FR-006、§ 邊界情況;`research.md` § R4
- [ ] T066a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-26 的測試(`#model` 選 `qwen2.5:latest` 後 `two_rounds`,從 `world.models` 拿掉 `qwen2.5:latest`,重新整理;斷言 5 秒內 `[data-state="chat-model-gone"]` 出現且含 `qwen2.5:latest`、`#log .msg` 4 則、`#model` 有一個 `disabled` 的選項含 `qwen2.5:latest` 與「已不在執行環境上」、`#send` 停用),執行確認它因為「還原時發現模型不在目錄,`#model` 自動落到 `llama3.2:3b` 且照常可送,舊對話被送給別的模型」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-26
  - ⚙ `prototype/chat.html` § `[data-state="chat-model-gone"]`、`#gone-name`、`#model`、`#send`、`#log`
  - 📎 `spec.md` § 邊界情況;`research.md` § R5;`plan.md` § 待決問題 Q5
- [ ] T066b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js`、`src/cgb/static/chat.html` 只寫讓 US2-AJ-26 通過的程式碼:`loadModels()` 在 Phase 2 的 `chat-unavailable`、`chat-no-session` 分支之後、目錄有模型時,若還原的對話不是空的、保存的 `model` 不在目錄裡,`view` 設成 `chat-model-gone`,`#gone-name` 填模型名稱;`renderModels()` 在選單最前面加一個 `disabled` 的選項「<名稱>(已不在執行環境上)」並選著它;`renderButtons()` 因 `view` 不是 `chat-ready` 停用 `#send`、`#input`;一打開頁面就顯示,不等按送出(plan Q5 a);`chat.html` 照原型加上 `chat-model-gone` 區塊;執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過;看到要整理的地方記進重構清單(依賴 T066a;`loadModels()` 的讀不到目錄分支是 Phase 2 做的,不改它)
  - 🧪 `testplan.md` § US2-AJ-26
  - ⚙ `prototype/chat.html` § `[data-state="chat-model-gone"]`、`#gone-name`、`#model`、`#send`
  - 📎 `spec.md` § 邊界情況;`research.md` § R5;`plan.md` § 待決問題 Q5、Q26
- [ ] T067a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-27 的測試(照 US2-AJ-26 已顯示 `chat-model-gone`,`#model` 改選 `llama3.2:3b`,再重新整理;斷言改選後 `#log .msg` 0 則、`#send` 可按,重新整理後 0 則),執行確認它因為「清了畫面但 `chat-model-gone` 沒解除(`clearChat()` 不重算 `view`),仍不能送出」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-27
  - ⚙ `prototype/chat.html` § `[data-state="chat-model-gone"]`、`[data-state="chat-ready"]`、`#model`、`#send`、`#log`
  - 📎 `spec.md` § FR-007、§ 邊界情況;`research.md` § R5
- [ ] T067b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-27 通過的程式碼:`clearChat()`(換模型與「清除」共用,T058b)清空後重算 `view`(重讀或以目前的 `catalog` 重畫 `loadModels()`/`renderModels()`),拿掉已不在的那個 `disabled` 選項、保留使用者剛選的模型,`chat-model-gone` 換成 `chat-ready`;執行 `tests/e2e/test_007_us2_chat_keep.py`、`tests/e2e/test_004_us2_chat.py` 確認通過;看到要整理的地方記進重構清單(依賴 T067a、T066b)
  - 🧪 `testplan.md` § US2-AJ-27
  - ⚙ `prototype/chat.html` § `[data-state="chat-ready"]`、`#model`、`#send`、`[data-state="chat-model-gone"]`
  - 📎 `spec.md` § FR-007、§ 邊界情況;`research.md` § R5
- [ ] T068a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-28 的測試(`caplog.set_level(logging.DEBUG)`;標記 `USER_MARK = "cgb-test-007-使用者-不該留下"`、`REPLY_MARK = "cgb-test-007-回覆-不該留下"`,替身每次回 `chunk(REPLY_MARK)` + `DONE`、其中一次 `then="hang"`;照故事 2 的獨立測試送出兩則含 `USER_MARK` 的訊息、重新整理、切到模型頁再回來、另開分頁、送出第三則、回覆途中重新整理、在工作階段頁「結束」,等 1 秒;斷言則1~則6;最後跑兩個對照組:`logging.getLogger("cgb").warning(USER_MARK)` 後 `caplog.text` 找到 1 次、把 `db_path` 複製到 `tmp_path` 在副本建表寫入 `USER_MARK` 後同一個掃描函式找到 1 列;搜尋一律用同一個函式比字串與 UTF-8 位元組,並掃 `-wal`、`-journal`);既有後端不記對話內容(`src/cgb/api/chat.py` 沒有 logger),E2 的 T039b 已驗後端,這個案例會被滿足:先執行確認通過,再暫時在 `src/cgb/api/chat.py` 讀串流的例外路徑加 `logging.getLogger("cgb").exception("chat %s", body)`,確認則3 失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-28
  - ⚙ `prototype/chat.html` § `#input`、`#send`;`prototype/index.html` § `#end`
  - 📎 `spec.md` § NFR-002、SC-004;`research.md` § R6
- [ ] T068b [US2] 🟢 /tdd 綠燈:US2-AJ-28 由既有後端不記對話內容、T039b 與本節前端只寫 `localStorage` 滿足,確認 `src/cgb/api/chat.py`、`src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/api/chat.py`、`src/cgb/static/js/chat.js` 只寫讓 US2-AJ-28 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T068a)
  - 🧪 `testplan.md` § US2-AJ-28
  - ⚙ `prototype/chat.html` § `#send`
  - 📎 `spec.md` § NFR-002、SC-004;`research.md` § R6
- [ ] T069a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-29 的測試(以 `assert_traditional_chinese` 檢查 `main`;依序做出 US2-AJ-09 的清空後、US2-AJ-22 的不能保存、US2-AJ-05 的離開頁面中斷、US2-AJ-26 的模型已不在,四種畫面各斷言通過檢查並含指定原句);四種提示文字已由 T049b、T062b、T045b、T066b 照原型寫成中文,這個案例會被滿足:先執行確認通過,再暫時讓 `keep-no-store` 顯示 `DOMException` 的 `message`(例如 `Storage unavailable`),確認則2 失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-29
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`、`[data-state="keep-no-store"]`、`[data-state="turn-interrupted"]`、`[data-state="${name}"]`、`[data-state="chat-model-gone"]`
  - 📎 `spec.md` § NFR-003、FR-006、FR-008;`plan.md` § 待決問題 Q17、Q26
- [ ] T069b [US2] 🟢 /tdd 綠燈:US2-AJ-29 由 T049b、T062b、T045b、T066b 照原型寫的中文提示滿足,確認 `src/cgb/static/chat.html`、`src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/chat.html`、`src/cgb/static/js/chat.js` 只寫讓 US2-AJ-29 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T069a)
  - 🧪 `testplan.md` § US2-AJ-29
  - ⚙ `prototype/chat.html` § `[data-state="keep-cleared"]`、`[data-state="keep-no-store"]`、`[data-state="chat-model-gone"]`、`[data-state="turn-interrupted"]`、`[data-state="${name}"]`
  - 📎 `spec.md` § NFR-003
- [ ] T071a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_007_us2_chat_keep.py` 寫 US2-AJ-30 的測試(`two_rounds` 之後重新整理,等 `#log .msg` 還原成 4 則;替身對下一個 `POST /api/chat` 先停 1 秒才送 `chunk("七")` 再送 `DONE`;送出「第三則」;斷言還原後、送出前 turn 區是 `turn-idle` 的提示,送出後第一段之前是含模型名稱的 `turn-loading`,`DONE` 後 2 秒內回到 `turn-idle`);T041b 的還原沿用 004 載入時的 `turn("turn-idle")`、送出沿用 004 的 `turn-loading`,這個案例會被滿足:先執行確認通過,再暫時讓還原時依保存的最後一則 `status` 畫 turn 區(停在 `turn-interrupted` 的提示),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-30
  - ⚙ `prototype/chat.html` § `[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="${name}"]`、`#send`
  - 📎 `spec.md` § FR-004、FR-005;`plan.md` § 待決問題 Q27;`research.md` § R5
- [ ] T071b [US2] 🟢 /tdd 綠燈:US2-AJ-30 由 T041b 的還原與 004 既有的 `turn()` 切換滿足,確認 `src/cgb/static/js/chat.js` 不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-30 通過的程式碼,執行 `tests/e2e/test_007_us2_chat_keep.py` 確認通過(依賴 T071a)
  - 🧪 `testplan.md` § US2-AJ-30
  - ⚙ `prototype/chat.html` § `[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="${name}"]`
  - 📎 `spec.md` § FR-004、FR-005;`plan.md` § 待決問題 Q27
- [ ] T070 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T041b~T069b、T071b 記下的重構清單(範圍限 `src/cgb/static/js/chat.js`、`src/cgb/static/chat.html`、`src/cgb/static/style.css`;例如把 `finishTurn` 與還原時填 `[data-state="turn-…"] [data-message]` 的兩處收成原型那樣的 `turn(name, message)`、把保存的讀寫移除收成一處),每改一小步執行這一節的測試檔 `tests/e2e/test_007_us2_chat_keep.py` 與 `tests/e2e/test_004_us2_chat.py`,變紅就撤回那一步;重構前後執行全部測試;不改 `tests/e2e/test_007_us2_chat_keep.py`、`tests/e2e/test_004_us2_chat.py` 的斷言(依賴 T071b)
  - 🧪 `testplan.md` § US2-AJ-01~US2-AJ-30
  - 📎 `testplan.md` § 3.2;`research.md` § R3、R4、R5

### 介面覆蓋(US2)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui.openapi.yaml` § `paths./events.get` | T031b、T032b、T033b、T034b、T035b、T036b、T037b、T038b、T039b、T049b、T050b、T051b、T052b、T053b、T054b、T055b、T056b、T057b、T064b、T065b | T031a、T032a、T033a、T034a、T035a、T036a、T037a、T038a、T039a、T049a、T050a、T051a、T052a、T053a、T054a、T055a、T056a、T057a、T064a、T065a |
| `chat.html` § `[data-state="chat-ready"]` | T041b、T055b、T056b、T067b | T041a、T055a、T056a、T067a |
| `chat.html` § `#model` | T041b、T059b、T066b、T067b | T041a、T059a、T066a、T067a |
| `chat.html` § `#send` | T044b、T047b、T066b、T067b、T068b | T041a、T044a、T047a、T061a、T062a、T066a、T067a、T068a、T071a |
| `chat.html` § `#log` | T041b、T042b、T043b、T056b、T060b、T061b、T064b、T065b | T041a、T042a、T043a、T044a、T045a、T047a、T049a、T050a、T051a、T052a、T053a、T054a、T055a、T056a、T057a、T058a、T059a、T060a、T061a、T062a、T063a、T064a、T065a、T066a、T067a |
| `chat.html` § `[data-state="turn-streaming"]` | T045b、T046b | T045a、T046a |
| `chat.html` § `[data-state="turn-interrupted"]` | T045b、T046b、T069b | T045a、T046a、T069a |
| `chat.html` § `[data-state="${name}"]` | T045b、T046b、T048b、T069b、T071b | T045a、T046a、T048a、T069a、T071a |
| `chat.html` § `[data-state="turn-stopped"]` | T048b | T048a |
| `chat.html` § `[data-state="keep-cleared"]` | T049b、T050b、T051b、T052b、T053b、T054b、T064b、T065b、T069b | T049a、T050a、T051a、T052a、T053a、T054a、T064a、T065a、T069a |
| `index.html` § `[data-state="ready"]` | T049b、T053b、T054b、T055b、T056b、T057b | T049a、T053a、T054a、T055a、T056a、T057a |
| `index.html` § `[data-state="ending"]` | T053b、T055b | T053a、T055a |
| `index.html` § `[data-state="opening"]` | T053b、T055b | T053a、T055a |
| `chat.html` § `[data-state="keep-checking"]` | T055b | T055a |
| `index.html` § `[data-state="ended"]` | T055b、T057b | T055a、T057a |
| `chat.html` § `[data-state="chat-no-session"]` | T057b | T057a |
| `chat.html` § `#clear` | T058b | T058a |
| `chat.html` § `[data-state="keep-no-store"]` | T062b、T063b、T069b | T062a、T063a、T069a |
| `chat.html` § `[data-state="chat-model-gone"]` | T066b、T067b、T069b | T066a、T067a、T069a |
| `chat.html` § `#gone-name` | T066b | T066a |
| `chat.html` § `[data-state="turn-idle"]` | T071b | T071a |
| `chat.html` § `[data-state="turn-loading"]` | T071b | T071a |

### 測試案例覆蓋(US2)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US2-API-01 | T031a | T031b | T040 |
| US2-API-02 | T032a | T032b | T040 |
| US2-API-03 | T033a | T033b | T040 |
| US2-API-04 | T034a | T034b | T040 |
| US2-API-05 | T035a | T035b | T040 |
| US2-API-06 | T036a | T036b | T040 |
| US2-API-07 | T037a | T037b | T040 |
| US2-API-08 | T038a | T038b | T040 |
| US2-API-09 | T039a | T039b | T040 |
| US2-AJ-01 | T041a | T041b | T070 |
| US2-AJ-02 | T042a | T042b | T070 |
| US2-AJ-03 | T043a | T043b | T070 |
| US2-AJ-04 | T044a | T044b | T070 |
| US2-AJ-05 | T045a | T045b | T070 |
| US2-AJ-06 | T046a | T046b | T070 |
| US2-AJ-07 | T047a | T047b | T070 |
| US2-AJ-08 | T048a | T048b | T070 |
| US2-AJ-09 | T049a | T049b | T070 |
| US2-AJ-10 | T050a | T050b | T070 |
| US2-AJ-11 | T051a | T051b | T070 |
| US2-AJ-12 | T052a | T052b | T070 |
| US2-AJ-13 | T053a | T053b | T070 |
| US2-AJ-14 | T054a | T054b | T070 |
| US2-AJ-15 | T055a | T055b | T070 |
| US2-AJ-16 | T056a | T056b | T070 |
| US2-AJ-17 | T057a | T057b | T070 |
| US2-AJ-18 | T058a | T058b | T070 |
| US2-AJ-19 | T059a | T059b | T070 |
| US2-AJ-20 | T060a | T060b | T070 |
| US2-AJ-21 | T061a | T061b | T070 |
| US2-AJ-22 | T062a | T062b | T070 |
| US2-AJ-23 | T063a | T063b | T070 |
| US2-AJ-24 | T064a | T064b | T070 |
| US2-AJ-25 | T065a | T065b | T070 |
| US2-AJ-26 | T066a | T066b | T070 |
| US2-AJ-27 | T067a | T067b | T070 |
| US2-AJ-28 | T068a | T068b | T070 |
| US2-AJ-29 | T069a | T069b | T070 |
| US2-AJ-30 | T071a | T071b | T070 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider`,再加 `uv run pytest -m realrun_local -q -p no:cacheprovider` 全綠;重構任務前後的測試結果相同

---

## Phase 4: 全域測試區

**Purpose**: 照 `testplan.md` § 4 驗證跨故事的 NFR 與 SC;故事裡已經有案例涵蓋的彙整見 `testplan.md` § 4.1,這裡排 § 4.2 唯一的 📏 實跑案例 G-01(沒有全域的行為測試案例,所以沒有紅綠與重構任務)。結果寫進 `specs/007-catalog-error-chat-keep/measurements.md`

### 本機實跑(`realrun_local`,時機:節內)

> 不開 Colab、不花 compute units、不需要本人在場;Phase 2 的 E2 節(T001~T018)完成後就可以跑,由主 agent 做

- [ ] T072 [G] 📏 量測:撰寫 `tests/realrun/test_007_g_01.py`(標 `realrun_local`,`plan.md` § 待決問題 Q10 的做法 a):本系統以替身開工作階段到就緒,但遠端 Ollama 改用真的 `RemoteOllama`(不是 `FakeRemoteOllama`),以 `tests/realrun/helpers.py` 的 `RecordingTransport(get_only=True)` 注入;通道的 `baseUrl` 依序指到(1)`free_loopback_port()` 取的、沒有人在聽的 127.0.0.1 port,(2)測試行程內對任何路徑回 200 與 `<html>不是 JSON</html>` 的臨時 http 伺服器,(3)只 `accept` 連線、不回任何位元組的 socket;每種情況各呼叫一次 `GET /api/models` 與 `POST /api/models/preload`(`{"name":"qwen2.5:3b"}`),(3)照 `LIST_TIMEOUT` 等 10 秒;記下六次回應的狀態碼、`code` 與 (3) 的耗時,和門檻((1)兩次都是 502 `OLLAMA_UNREACHABLE`;(2)兩次都是 502 `OLLAMA_BAD_RESPONSE`;(3)兩次都是 504 `OLLAMA_TIMEOUT`,`GET /api/models` 在送出後 10 到 12 秒之間回應;六次裡 500 的次數為 0,SC-001)比較,結果寫進 `specs/007-catalog-error-chat-keep/measurements.md`;不開 Colab、不花錢、不需本人在場;不起 `ollama serve`,**不對 127.0.0.1:11434 送任何請求**(`RecordingTransport` 經 `check_port` 擋下),port 由 `free_loopback_port()` 取、避開 11434~11436 與 8780;臨時伺服器與 socket 只聽 127.0.0.1,fixture 收尾關閉並確認 port 已釋放;只寫 pytest 暫存資料夾;約 25 秒;判定者:腳本;樣本:一次實跑(未用於調整)
  - 🧪 `testplan.md` § G-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`paths./models/preload.post`
  - 📎 `spec.md` § FR-001、FR-002、NFR-001、SC-001;`plan.md` § 待決問題 Q10;`research.md` § R1;`contracts/ui.openapi.yaml` § `info.x-catalog-failure-rule`

### 測試案例覆蓋(全域)

| testplan 案例 | 任務 |
|---|---|
| G-01 | T072 |

**Checkpoint**: 全部測試綠燈;`specs/007-catalog-error-chat-keep/measurements.md` 的 G-01 寫了數字與是否過門檻,沒過的列為待決問題

---

## Dependencies & Execution Order

- Phase 1 Setup(無任務)→ Phase 2(US1)→ Phase 3(US2)→ Phase 4 全域測試區;每個故事的 Checkpoint 交給使用者確認後才進下一個 phase
- 同一個 phase 的 E2 節交給一個 subagent;E1 沒有任務;跨端點驗收在 E2 節完成後由主 agent 做
- 同一個檔不同時改:`src/cgb/static/chat.html`、`src/cgb/static/js/chat.js` 先由 US1 的跨端點驗收改讀不到目錄的說明,再由 US2 的跨端點驗收加對話的保存、還原與清除,兩段依序做
- 📏 量測:G-01(T072)不開 Colab,Phase 2 的 E2 節完成後由主 agent 做;這一輪沒有要花 compute units 或本人在場的實跑
- `plan.md` § 待決問題 Q22 已由使用者本人選 a(照 007 spec FR-006 清空,修訂 004 FR-008,見 spec.md 假設):US2-AJ-14 對應的 T054a、T054b 照現在寫的做,T054b 刪除與改寫 004 的三支舊測試
