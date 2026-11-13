# Tasks: 官方模型庫的錯誤處理

**Input**: `specs/002-library-error-handling/` 的設計文件(本 spec package);建立在 `specs/001-session-model-catalog/` 之上,既有程式在 `src/cgb/`、既有測試在 `tests/`

**Prerequisites**: plan.md、spec.md、research.md、techstack.md、testplan.md、contracts/model-library.openapi.yaml、contracts/ui.openapi.yaml

**Tests**: 依 `testplan.md` 切分。testplan 的每個行為測試案例對應一組 `/tdd` 紅燈與綠燈任務,每個「使用者故事 × 端點」節最後一個 `/tdd` 重構任務;量測與人工驗證的案例對應 📏 任務。

**Organization**: 依 `testplan.md` 的使用者故事分 phase;每個故事底下依 `testplan.md` 的端點分節(E8 Ollama 官方模型庫、E2 後端 UI API),外加一節跨端點驗收,最後是介面覆蓋表與測試案例覆蓋表。全域測試區自成一個 phase,放在所有故事之後。

## Format: `[ID] [Story] [步驟] Description`,底下接 🧪、⚙ 與 📎

- **[Story]**:所屬的使用者故事(US1、US2);全域測試區寫 `[G]`
- **[步驟]**:這個任務是 `/implement` 交給誰做的哪一步
  - 🔴 `/tdd 紅燈`:寫一個測試案例的測試,執行確認它失敗
  - 🟢 `/tdd 綠燈`:只寫讓同一個案例通過的程式碼,執行全部測試確認都通過
  - 🔵 `/tdd 重構`:在全部測試綠燈下,整理這一節綠燈任務記下的重構清單,不改行為、不改斷言
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

**Purpose**: 沿用 001 的工具鏈、`pyproject.toml`、`uv.lock` 與測試基礎(`tests/conftest.py`、`tests/fakes/adapters.py`、`tests/fixtures/library/`);這一輪不新增套件、不複製規格檔、不改 CI(`techstack.md` § 新引入與沿用、`plan.md` § Project Structure),這個 phase 沒有任務。

---

## Phase 2: User Story 1 - 搜尋與看版本時模型庫出問題也知道原因 (Priority: P1) 🎯 MVP

**Goal**: ollama.com 連不到、逾時、回 5xx、改版或模型不存在時,UI API 的搜尋與版本清單回合約定好的狀態碼、`code` 與繁中 `message`,沒有任何一次是 500

**Independent Test**: 照 `testplan.md` § 2 的全部案例:E8 以 `uv run pytest tests/integration/test_model_library.py`(`httpx.MockTransport` 與 127.0.0.1 本機 socket 伺服器)、E2 以 `uv run pytest tests/integration/test_api_library.py`(`FakeModelLibrary`)、跨端點驗收以 `uv run pytest tests/integration/test_library_cross.py` 執行全綠

### E8 Ollama 官方模型庫

> E8 與 E2 兩節平行;E8 只改 `src/cgb/adapters/model_library.py` 與 `src/cgb/domain/library_html.py`,E2 只改 `src/cgb/services/` 與 `src/cgb/domain/errors.py`,兩節沒有共用的檔。127.0.0.1 本機 socket 伺服器的 helper 由第一個用到它的 T018a 建在 `tests/integration/test_model_library.py`(`plan.md` § 待決問題 Q15)

- [X] T001a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-01 的測試(呼叫 `search_library("qwen2.5")`),執行確認它因為「`_get` 沒有攔 httpx 例外,`ConnectError` 原樣往上拋(001 的行為,UI API 回 500)」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-01
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-006、SC-001;`research.md` § R1
- [X] T001b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T001a)
  - 🧪 `testplan.md` § US1-LIB-01
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-006、SC-001;`research.md` § R1
- [X] T002a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-02 的測試(兩種情況各呼叫一次 `search_library("qwen2.5")`),執行確認它因為「只攔 `httpx.ConnectError` 或 `httpx.NetworkError`,`RemoteProtocolError`(屬於 `ProtocolError`)原樣往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-02
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-001、FR-006、SC-001;`research.md` § R1
- [X] T002b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T002a)
  - 🧪 `testplan.md` § US1-LIB-02
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-001、FR-006、SC-001;`research.md` § R1
- [X] T003a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-03 的測試(兩種情況各呼叫一次 `search_library("qwen2.5")`),執行確認它因為「`except httpx.TransportError` 寫在 `except httpx.TimeoutException` 前面,逾時先被攔下、歸成 `LIBRARY_UNREACHABLE`(research.md R1)」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-03
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-006、SC-001;`research.md` § R1
- [X] T003b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T003a)
  - 🧪 `testplan.md` § US1-LIB-03
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-006、SC-001;`research.md` § R1
- [X] T004a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-04 的測試(三種情況各呼叫一次 `search_library("qwen2.5")`),執行確認它因為「不看狀態碼就解析本文,把 5xx 頁上的 `qwen2.5`、`qwen2.5-coder` 當成正常結果回傳(001 的行為)」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-04
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、SC-001;`research.md` § R3
- [X] T004b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T004a)
  - 🧪 `testplan.md` § US1-LIB-04
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、SC-001;`research.md` § R3
- [X] T005a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-05 的測試(兩種情況各呼叫一次 `search_library("qwen2.5")`),執行確認它因為「三個操作共用的狀態碼判定一律把 404 歸成 `LIBRARY_NOT_FOUND`,讓搜尋回出合約沒列的代碼」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-05
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、SC-001;`research.md` § R3
- [X] T005b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T005a)
  - 🧪 `testplan.md` § US1-LIB-05
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、SC-001;`research.md` § R3
- [X] T006a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-06 的測試(呼叫 `search_library("qwen2.5", page=2)`),執行確認它因為「client 開了 `follow_redirects=True`,跟著導向去讀第 1 頁,把第 1 頁的 `qwen2.5`、`qwen2.5-coder` 當成第 2 頁的結果回傳」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-06
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-001、SC-001;`research.md` § R3
- [X] T006b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T006a)
  - 🧪 `testplan.md` § US1-LIB-06
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-001、SC-001;`research.md` § R3
- [X] T007a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-07 的測試(兩種情況各呼叫一次 `search_library("qwen2.5")`),執行確認它因為「找不到結果區塊時照 001 回空的 `items`,把改版當成「沒有符合的模型」」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-07
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、SC-001;`research.md` § R3
- [X] T007b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 只寫讓 US1-LIB-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T007a)
  - 🧪 `testplan.md` § US1-LIB-07
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、SC-001;`research.md` § R3
- [X] T008a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-08 的測試(呼叫 `search_library("qwen2.5", page=2)`),執行確認它因為「第 2 頁起只要解析出 0 筆官方模型,就當成超過最後一頁、回空的 `items`,沒有先判斷本文是不是只有空白」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-08
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、SC-001;`research.md` § R3
- [X] T008b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 只寫讓 US1-LIB-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T008a)
  - 🧪 `testplan.md` § US1-LIB-08
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、SC-001;`research.md` § R3
- [X] T009a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-09 的測試(呼叫 `search_library("zzzz-no-such-model")`);現有程式已滿足這個案例(testplan 寫明的 001 正常結果),先執行確認它通過,再把 `src/cgb/adapters/model_library.py` 暫時改成「0 筆官方模型一律當成格式不符,丟 `LIBRARY_BAD_RESPONSE`,「沒有符合的模型」變成錯誤,UI 退到 `library-down`」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-LIB-09
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001;`research.md` § R3;`plan.md` § 待決問題 Q9;`plan.md` § 待決問題 Q19
- [X] T009b [US1] 🟢 /tdd 綠燈:US1-LIB-09 由現有程式滿足,確認 `src/cgb/adapters/model_library.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-09 通過的程式碼(依賴 T009a)
  - 🧪 `testplan.md` § US1-LIB-09
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001;`research.md` § R3;`plan.md` § 待決問題 Q9;`plan.md` § 待決問題 Q19
- [X] T010a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-10 的測試(呼叫 `search_library("qwen2.5", page=34)`);現有程式已滿足這個案例(testplan 寫明的 001 正常結果),先執行確認它通過,再把 `src/cgb/adapters/model_library.py` 暫時改成「第 2 頁起也套用第 1 頁「要有 `id="searchresults"`」的條件」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-LIB-10
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T010b [US1] 🟢 /tdd 綠燈:US1-LIB-10 由現有程式滿足,確認 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 只寫讓 US1-LIB-10 通過的程式碼(依賴 T010a)
  - 🧪 `testplan.md` § US1-LIB-10
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T011a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-11 的測試(呼叫 `search_library("qwen2.5", page=2)`);現有程式已滿足這個案例(testplan 寫明的 001 正常結果),先執行確認它通過,再把 `src/cgb/adapters/model_library.py` 暫時改成「判定格式時只數 `/library/` 的官方模型連結,只有社群模型的頁被歸成 `LIBRARY_BAD_RESPONSE`(research.md R3)」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-LIB-11
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-001;`research.md` § R3;`plan.md` § 待決問題 Q9;`plan.md` § 待決問題 Q19
- [X] T011b [US1] 🟢 /tdd 綠燈:US1-LIB-11 由現有程式滿足,確認 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 只寫讓 US1-LIB-11 通過的程式碼(依賴 T011a)
  - 🧪 `testplan.md` § US1-LIB-11
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-001;`research.md` § R3;`plan.md` § 待決問題 Q9;`plan.md` § 待決問題 Q19
- [X] T012a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-12 的測試(呼叫 `search_library("qwen2.5", page=2)`);現有程式已滿足這個案例(testplan 寫明的 001 正常結果),先執行確認它通過,再把 `src/cgb/adapters/model_library.py` 暫時改成「第 2 頁起也要求 `id="searchresults"`,正常的片段被歸成 `LIBRARY_BAD_RESPONSE`(片段本來就沒有這個區塊,見合約 `SearchPageFragment`)」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-LIB-12
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001;`research.md` § R3;`plan.md` § 待決問題 Q9;`plan.md` § 待決問題 Q19
- [X] T012b [US1] 🟢 /tdd 綠燈:US1-LIB-12 由現有程式滿足,確認 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 只寫讓 US1-LIB-12 通過的程式碼(依賴 T012a)
  - 🧪 `testplan.md` § US1-LIB-12
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001;`research.md` § R3;`plan.md` § 待決問題 Q9;`plan.md` § 待決問題 Q19
- [X] T013a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-13 的測試(呼叫 `list_model_tags("no-such-model-zzz")`),執行確認它因為「不看狀態碼就解析 404 頁,得到空清單照常回傳(001 的行為,UI 顯示沒有版本)」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-13
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、SC-001;`research.md` § R3
- [X] T013b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T013a)
  - 🧪 `testplan.md` § US1-LIB-13
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、SC-001;`research.md` § R3
- [X] T014a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-14 的測試(兩種情況各呼叫一次 `list_model_tags("qwen2.5")`),執行確認它因為「不看狀態碼,本文解析得出版本就照常回 3 個版本」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-14
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、SC-001;`research.md` § R3
- [X] T014b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T014a)
  - 🧪 `testplan.md` § US1-LIB-14
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、SC-001;`research.md` § R3
- [X] T015a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-15 的測試(兩種情況各呼叫一次 `list_model_tags("qwen2.5")`),執行確認它因為「client 開了 `follow_redirects=True`,跟著導向讀別的頁,並把那一頁的版本回傳」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-15
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、SC-001;`research.md` § R3
- [X] T015b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T015a)
  - 🧪 `testplan.md` § US1-LIB-15
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、SC-001;`research.md` § R3
- [X] T016a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-16 的測試(兩種情況各呼叫一次 `list_model_tags("qwen2.5")`),執行確認它因為「解析出空清單時照 001 回 `[]`,把改版當成「沒有版本」」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-16
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、SC-001;`research.md` § R3
- [X] T016b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T016a)
  - 🧪 `testplan.md` § US1-LIB-16
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、SC-001;`research.md` § R3
- [X] T017a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-17 的測試(呼叫 `list_model_tags("qwen2.5")`);現有程式已滿足這個案例(testplan 寫明的 001 正常結果),先執行確認它通過,再把 `src/cgb/adapters/model_library.py` 暫時改成「只要有版本解析不出大小,就當成格式不符丟 `LIBRARY_BAD_RESPONSE`」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-LIB-17
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-002;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T017b [US1] 🟢 /tdd 綠燈:US1-LIB-17 由現有程式滿足,確認 `src/cgb/adapters/model_library.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-17 通過的程式碼(依賴 T017a)
  - 🧪 `testplan.md` § US1-LIB-17
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-002;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T018a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-18 的測試(兩種情況各呼叫一次 `list_model_tags("qwen2.5")`),執行確認它因為「只攔了 MockTransport 測得到的幾個例外類別,真的 httpx 在連線被拒或 TLS 失敗時丟的 `ConnectError`(底層是 `OSError`、`ssl.SSLError`)原樣往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-18
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、FR-006、SC-001;`research.md` § R1
- [X] T018b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-18 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T018a)
  - 🧪 `testplan.md` § US1-LIB-18
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、FR-006、SC-001;`research.md` § R1
- [X] T019a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-19 的測試(呼叫 `list_model_tags("qwen2.5")`),執行確認它因為「只攔 `httpx.NetworkError`,真的讀到一半斷線時 httpx 丟的 `RemoteProtocolError` 原樣往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-19
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-002、FR-006、SC-001;`research.md` § R1
- [X] T019b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-19 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T019a)
  - 🧪 `testplan.md` § US1-LIB-19
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、FR-002、FR-006、SC-001;`research.md` § R1
- [X] T020a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-20 的測試(兩種情況各呼叫一次 `list_model_tags("qwen2.5")`),執行確認它因為「`except httpx.TransportError` 寫在 `except httpx.TimeoutException` 前面,逾時被歸成 `LIBRARY_UNREACHABLE`」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-20
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、FR-006、SC-001;`research.md` § R1
- [X] T020b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-20 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T020a)
  - 🧪 `testplan.md` § US1-LIB-20
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、FR-006、SC-001;`research.md` § R1
- [X] T021a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-21 的測試(呼叫 `search_library("qwen2.5")`),執行確認它因為「`request_timeout` 沒有接到 client,httpx 沿用預設的 5 秒,約 5 秒才逾時」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-21
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-001、FR-006、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T021b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-21 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T021a)
  - 🧪 `testplan.md` § US1-LIB-21
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-001、FR-006、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T022a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-22 的測試(呼叫 `list_model_tags("qwen2.5")`),執行確認它因為「版本清單自己建 client,沒有用 `request_timeout`,約 5 秒才逾時」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-22
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-002、FR-006、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T022b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-22 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T022a)
  - 🧪 `testplan.md` § US1-LIB-22
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-002、FR-006、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T023a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-23 的測試(呼叫 `search_library("qwen2.5")`),執行確認它因為「只設了 httpx 的 `Timeout`,沒有用 `asyncio.timeout` 包住整個請求;每次讀取都在 0.5 秒內有資料,約 8 秒讀完才回(或回 `LIBRARY_BAD_RESPONSE`)」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-23
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、NFR-001、FR-001、FR-006、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T023b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-23 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T023a)
  - 🧪 `testplan.md` § US1-LIB-23
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、NFR-001、FR-001、FR-006、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T024a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-24 的測試(呼叫 `list_model_tags("qwen2.5")`),執行確認它因為「整體期限只包在 `search_library` 裡,版本清單沒包,約 8 秒讀完才回」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-24
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、NFR-001、FR-002、FR-006、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T024b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-24 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T024a)
  - 🧪 `testplan.md` § US1-LIB-24
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況、NFR-001、FR-002、FR-006、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T025a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-25 的測試(呼叫 `search_library("qwen2.5")`),執行確認它因為「`request_timeout` 的預設值不是 `REQUEST_TIMEOUT_SECONDS`(10 秒),沿用 httpx 預設的 5 秒(001 的行為),或寫成其他秒數」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-25
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q7
- [X] T025b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-25 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T025a)
  - 🧪 `testplan.md` § US1-LIB-25
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q7
- [X] T026a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US1-LIB-26 的測試(依序呼叫 `search_library("qwen2.5")`、`search_library("qwen2.5", page=2)`(合計約 0.6 秒)),執行確認它因為「整體期限在建構 `ModelLibrary` 或第一次呼叫時起算、多個請求共用,第 2 頁在累計 0.5 秒時被判 `LIBRARY_TIMEOUT`(合約:「顯示更多」每讀一頁是一個請求,各自計算)」這類實作而失敗
  - 🧪 `testplan.md` § US1-LIB-26
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-001;`research.md` § R2;`plan.md` § 待決問題 Q6
- [X] T026b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US1-LIB-26 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T026a)
  - 🧪 `testplan.md` § US1-LIB-26
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-001;`research.md` § R2;`plan.md` § 待決問題 Q6
- [X] T027 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T001b~T026b 記下的重構清單(範圍限 `src/cgb/adapters/`、`src/cgb/domain/library_html.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_model_library.py` 的斷言(依賴 T026b)
  - 🧪 `testplan.md` § US1-LIB-01~US1-LIB-26
  - 📎 `testplan.md` § 2.1

### E2 後端 UI API

- [X] T028a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-01 的測試(`GET /api/library/search?q=qwen2.5`);現有程式已滿足這個案例(research.md R4 的實測表),先執行確認它通過,再把 `src/cgb/services/library.py` 暫時改成「搜尋先檢查有沒有就緒的工作階段,沒有就回 503 `NO_READY_SESSION`,沒有去問模型庫」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T028b [US1] 🟢 /tdd 綠燈:US1-API-01 由現有程式滿足,確認 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-01 通過的程式碼(依賴 T028a)
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T029a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-02 的測試(`GET /api/library/search?q=qwen2.5`);現有程式已滿足這個案例(research.md R4 的實測表),先執行確認它通過,再把 `src/cgb/services/library.py` 暫時改成「把模型庫的失敗都改寫成同一個 `LIBRARY_UNREACHABLE` 回傳(只對了 502、沒照轉接層的代碼)」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T029b [US1] 🟢 /tdd 綠燈:US1-API-02 由現有程式滿足,確認 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-02 通過的程式碼(依賴 T029a)
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T030a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-03 的測試(按「顯示更多」:`GET /api/library/search?q=qwen2.5&page=2`);現有程式已滿足這個案例(research.md R4 的實測表),先執行確認它通過,再把 `src/cgb/services/library.py` 暫時改成「第 2 頁起的 `LIBRARY_BAD_RESPONSE` 被當成「沒有下一頁」,回 200、空的 `items`、`hasMore` 為 false」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T030b [US1] 🟢 /tdd 綠燈:US1-API-03 由現有程式滿足,確認 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-03 通過的程式碼(依賴 T030a)
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T031a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-04 的測試(`GET /api/library/search?q=qwen2.5`),執行確認它因為「沿用 001 的 `ApiError(502, error.code)`,把逾時也回 502」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T031b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py`、`tests/e2e/test_locale.py` 只寫讓 US1-API-04 通過的程式碼(在 `src/cgb/domain/errors.py` 新增共用的 `LIBRARY_STATUS` 與 `library_error(code, model=None) -> ApiError`,`Library.search()` 改用它;`MESSAGES` 補上 `LIBRARY_TIMEOUT` 的繁中說明,帶「從精選清單挑選或直接輸入名稱」的退路;同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加一列 `("LIBRARY_TIMEOUT", err_search("LIBRARY_TIMEOUT"))`,否則 `test_錯誤代碼清單涵蓋本系統的每一個錯誤代碼` 會因為 `MESSAGES` 多一個 key 而變紅;不改那一列以外的斷言),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T031a)
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T032a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-05 的測試(`GET /api/library/search?q=no-such-model-xyz`);現有程式已滿足這個案例(001 的行為),先執行確認它通過,再把 `src/cgb/services/library.py` 暫時改成「這一輪加錯誤處理時,把 0 筆結果也當成格式不符,回 502 `LIBRARY_BAD_RESPONSE`」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T032b [US1] 🟢 /tdd 綠燈:US1-API-05 由現有程式滿足,確認 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-05 通過的程式碼(依賴 T032a)
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T033a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-06 的測試(`GET /api/library/models/qwen2.6/tags`),執行確認它因為「`Library.tags()` 沒有接 `AdapterError`,原樣往上拋成 500」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T033b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-06 通過的程式碼(`Library.tags()` 補上 `except AdapterError`,改用 `library_error`),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T033a)
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T034a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-07 的測試(`GET /api/library/models/qwen2.5/tags`),執行確認它因為「`tags()` 只用 `if error.code == "LIBRARY_NOT_FOUND"` 接住 404,其他代碼重新拋出,變成 500」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T034b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T034a)
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T035a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-08 的測試(`GET /api/library/models/qwen2.5/tags`),執行確認它因為「`LIBRARY_STATUS` 漏掉 `LIBRARY_SERVER_ERROR`,`.get(code, 500)` 退回 500」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T035b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T035a)
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T036a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-09 的測試(`GET /api/library/models/qwen2.5/tags`),執行確認它因為「把格式不符當成「這個模型沒有版本」,回 200 與空的 `tags`」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T036b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T036a)
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T037a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-10 的測試(`GET /api/library/models/qwen2.5/tags`),執行確認它因為「版本清單自己寫了一張只有 404 與 502 的對應表,沒有共用 `LIBRARY_STATUS`,逾時回 502」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T037b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T037a)
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R4
- [X] T038a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-11 的測試(`GET /api/library/models/qwen2.5/tags`);現有程式已滿足這個案例(001 的行為),先執行確認它通過,再把 `src/cgb/services/library.py` 暫時改成「補錯誤處理時加了「沒有大小就是格式不符」的檢查,回 502 `LIBRARY_BAD_RESPONSE`」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T038b [US1] 🟢 /tdd 綠燈:US1-API-11 由現有程式滿足,確認 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-11 通過的程式碼(依賴 T038a)
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T039a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-12 的測試(`GET /api/library/search?q=qwen2.5`,接著 `GET /api/curated`,再 `GET /api/downloads`);現有程式已滿足這個案例(001 的行為),先執行確認它通過,再把 `src/cgb/services/library.py` 暫時改成「模型庫的 `AdapterError` 被一個全域的 `AdapterError` 處理器接走,當成執行環境出問題,把下載中的那筆標成 `failed` 或重新開始 pull」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況;`research.md` § R4;`plan.md` § 待決問題 Q15;`plan.md` § 待決問題 Q19
- [X] T039b [US1] 🟢 /tdd 綠燈:US1-API-12 由現有程式滿足,確認 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-12 通過的程式碼(依賴 T039a)
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況;`research.md` § R4;`plan.md` § 待決問題 Q15;`plan.md` § 待決問題 Q19
- [X] T040a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-13 的測試(`GET /api/library/models/qwen2.5/tags`,接著 `GET /api/library/search?q=qwen2.5`),執行確認它因為「版本清單失敗時把工作階段轉成重連中(或清掉執行環境模型的對照),之後搜尋的 `runtimeChecked` 變成 false、已下載的版本標不出來」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`、`paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`
  - 📎 `spec.md` § 邊界情況;`research.md` § R4;`plan.md` § 待決問題 Q15
- [X] T040b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T040a)
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`、`paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`
  - 📎 `spec.md` § 邊界情況;`research.md` § R4;`plan.md` § 待決問題 Q15
- [X] T041a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-14 的測試(`GET /api/library/search?q=qwen2.5`);現有程式已滿足這個案例(001 的行為),先執行確認它通過,再把 `src/cgb/services/library.py` 暫時改成「把 `AdapterError.message` 接在固定說明後面回傳(例如 `f"{MESSAGES[code]}({error.message})"`),或直接用它取代說明」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、FR-003;`research.md` § R4;`plan.md` § 待決問題 Q13;`plan.md` § 待決問題 Q19
- [X] T041b [US1] 🟢 /tdd 綠燈:US1-API-14 由現有程式滿足,確認 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-14 通過的程式碼(依賴 T041a)
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、FR-003;`research.md` § R4;`plan.md` § 待決問題 Q13;`plan.md` § 待決問題 Q19
- [X] T042a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-15 的測試(`GET /api/library/models/qwen2.5/tags`),執行確認它因為「`MESSAGES` 沒有補 `LIBRARY_TIMEOUT`,`body()` 退回去用 `AdapterError.message` 或代碼字串當 `message`」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、FR-003;`research.md` § R4;`plan.md` § 待決問題 Q13
- [X] T042b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T042a)
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、FR-003;`research.md` § R4;`plan.md` § 待決問題 Q13
- [X] T043a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-16 的測試(`GET /api/library/search?q=qwen2.5`,接著 `GET /api/library/models/qwen2.5/tags`),執行確認它因為「版本清單另外寫了一張訊息表,或把模型名稱或對方的狀態碼插進說明(例如「qwen2.5 的版本頁回 500」),同一個代碼在兩個操作是不同的兩句」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`、`paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`
  - 📎 `spec.md` § NFR-002;`research.md` § R4
- [X] T043b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T043a)
  - 🧪 `testplan.md` § US1-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`、`paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`
  - 📎 `spec.md` § NFR-002;`research.md` § R4
- [X] T044a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US1-API-17 的測試(`GET /api/library/models/qwen2.6/tags`),執行確認它因為「只有 502 與 504 走固定訊息表,404 這條另外寫成「找不到:」加上 `AdapterError.message`」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、FR-003;`research.md` § R4
- [X] T044b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/library.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-17 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T044a)
  - 🧪 `testplan.md` § US1-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、FR-003;`research.md` § R4
- [X] T045 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T028b~T044b 記下的重構清單(範圍限 `src/cgb/services/`、`src/cgb/domain/errors.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_api_library.py` 的斷言(依賴 T044b)
  - 🧪 `testplan.md` § US1-API-01~US1-API-17
  - 📎 `testplan.md` § 2.2

### 跨端點驗收(`tests/integration/test_library_cross.py`)

> 端點節(E8、E2)都完成、驗收過後由主 agent 開始;真的 E2(api、services、domain、repos 與 SQLite)接真的 `ModelLibrary`,ollama.com 與 registry 換成 `httpx.MockTransport`,其他轉接層用替身(`plan.md` § 待決問題 Q4、Q18)

- [X] T046a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_library_cross.py` 寫 US1-AJ-01 的測試(每種情況各送一次 `GET /api/library/search?q=qwen2.5`),執行確認它因為「轉接層只在 `get_manifest` 攔例外,`search_library` 讓 httpx 例外穿過 services 變成 500(Q178)」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-003、FR-006、SC-001;`research.md` § R5;`plan.md` § 待決問題 Q4
- [X] T046b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py`、`src/cgb/services/library.py` 只寫讓 US1-AJ-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T046a)
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-003、FR-006、SC-001;`research.md` § R5;`plan.md` § 待決問題 Q4
- [X] T047a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_library_cross.py` 寫 US1-AJ-02 的測試(每種情況各送一次 `GET /api/library/models/qwen2.5/tags`),執行確認它因為「`Library.tags()` 沒接 `AdapterError`,轉接層丟出的錯變成 500」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、FR-003、FR-006、SC-001;`research.md` § R5;`plan.md` § 待決問題 Q4
- [X] T047b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py`、`src/cgb/services/library.py` 只寫讓 US1-AJ-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T047a)
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002、FR-003、FR-006、SC-001;`research.md` § R5;`plan.md` § 待決問題 Q4
- [X] T048a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_library_cross.py` 寫 US1-AJ-03 的測試(送 `GET /api/library/search?q=qwen2.5`),執行確認它因為「轉接層把 `str(原例外)` 放進 `AdapterError.message`,服務層又把它接進回應」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、FR-006;`research.md` § R5;`plan.md` § 待決問題 Q4
- [X] T048b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py`、`src/cgb/services/library.py` 只寫讓 US1-AJ-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T048a)
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、FR-006;`research.md` § R5;`plan.md` § 待決問題 Q4
- [X] T049 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T046b~T048b 記下的重構清單(範圍限 `src/cgb/adapters/model_library.py`、`src/cgb/services/`、`src/cgb/domain/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_library_cross.py` 的斷言(依賴 T048b)
  - 🧪 `testplan.md` § US1-AJ-01~US1-AJ-03
  - 📎 `testplan.md` § 2.3

### 介面覆蓋(US1)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`(傳輸層失敗、狀態碼、格式判定、逾時) | T001b~T012b、T021b、T023b、T025b、T026b、T046b、T048b | T001a~T012a、T021a、T023a、T025a、T026a、T046a、T048a |
| `model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`(傳輸層失敗、狀態碼、格式判定、逾時) | T013b~T020b、T022b、T024b、T047b | T013a~T020a、T022a、T024a、T047a |
| `model-library.openapi.yaml` § `components.schemas.Error`(搜尋與版本清單會丟的代碼) | T001b~T026b | T001a~T026a |
| `ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`(`LIBRARY_*` 的狀態碼與訊息) | T028b~T032b、T039b、T040b、T041b、T043b、T046b、T048b | T028a~T032a、T039a、T040a、T041a、T043a、T046a、T048a |
| `ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`(`LIBRARY_*` 的狀態碼與訊息) | T033b~T038b、T040b、T042b、T043b、T044b、T047b | T033a~T038a、T040a、T042a、T043a、T044a、T047a |
| `ui.openapi.yaml` § `components.schemas.Error`(搜尋與版本清單回的 `LIBRARY_*`) | T028b~T044b | T028a~T044a |

### 測試案例覆蓋(US1)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US1-LIB-01~US1-LIB-26 | T001a~T026a | T001b~T026b | T027 |
| US1-API-01~US1-API-17 | T028a~T044a | T028b~T044b | T045 |
| US1-AJ-01~US1-AJ-03 | T046a~T048a | T046b~T048b | T049 |

**Checkpoint**: `uv run pytest` 全綠(含 `tests/e2e/test_locale.py` 加了 `LIBRARY_TIMEOUT` 的那一列);重構任務前後的測試結果相同

---

## Phase 3: User Story 2 - 試算與加入下載時取不到模型大小也知道原因 (Priority: P1)

**Goal**: registry 連不到、逾時、回 5xx、回的不是 manifest 或模型與版本不存在時,UI API 的試算與加入下載回合約定好的狀態碼、`code`、`message` 與 `model`,整批不加入佇列,沒有任何一次是 500

**Independent Test**: 照 `testplan.md` § 3 的全部案例:E8 以 `uv run pytest tests/integration/test_model_library.py`、E2 以 `uv run pytest tests/integration/test_api_downloads.py`(`FakeModelLibrary`、`live_servers`)、跨端點驗收以 `uv run pytest tests/integration/test_library_cross.py` 執行全綠

### E8 Ollama 官方模型庫

> E8 與 E2 兩節平行;E8 只改 `src/cgb/adapters/model_library.py`,E2 只改 `src/cgb/services/downloads.py` 與 `src/cgb/domain/errors.py`(US1 的 T031b 建立的 `LIBRARY_STATUS`、`library_error` 在這一節沿用),兩節沒有共用的檔

- [X] T050a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-01 的測試(呼叫 `get_manifest("qwen2.5", "7b")`),執行確認它因為「改成三個操作共用狀態碼判定時,把搜尋頁的格式判定(找 `id="searchresults"`)也套到 manifest,正常的 200 manifest 被歸成 `LIBRARY_BAD_RESPONSE`」這類實作而失敗
  - 🧪 `testplan.md` § US2-LIB-01
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、NFR-001;`research.md` § R2、R3;`plan.md` § 待決問題 Q6
- [X] T050b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T050a)
  - 🧪 `testplan.md` § US2-LIB-01
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、NFR-001;`research.md` § R2、R3;`plan.md` § 待決問題 Q6
- [X] T051a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-02 的測試(依序呼叫 `get_manifest("no-such-model", "latest")` 與 `get_manifest("qwen2.5", "999b")`);現有程式已滿足這個案例(research.md R3:`get_manifest` 已經會分 404、5xx、非預期與格式不符),先執行確認它通過,再把 `src/cgb/adapters/model_library.py` 暫時改成「為了分辨模型與版本而去讀 404 本文的 `errors[0].code`,只有 `NAME_UNKNOWN` 才歸 `LIBRARY_NOT_FOUND`,`MANIFEST_UNKNOWN` 被歸成 `LIBRARY_BAD_RESPONSE`」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US2-LIB-02
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、邊界情況、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T051b [US2] 🟢 /tdd 綠燈:US2-LIB-02 由現有程式滿足,確認 `src/cgb/adapters/model_library.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-02 通過的程式碼(依賴 T051a)
  - 🧪 `testplan.md` § US2-LIB-02
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、邊界情況、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T052a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-03 的測試(每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")`);現有程式已滿足這個案例(research.md R3:`get_manifest` 已經會分 404、5xx、非預期與格式不符),先執行確認它通過,再把 `src/cgb/adapters/model_library.py` 暫時改成「只認 `== 503`,或只認 `in (500, 502, 503, 504)`,599 被歸成 `LIBRARY_BAD_RESPONSE`」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US2-LIB-03
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T052b [US2] 🟢 /tdd 綠燈:US2-LIB-03 由現有程式滿足,確認 `src/cgb/adapters/model_library.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-03 通過的程式碼(依賴 T052a)
  - 🧪 `testplan.md` § US2-LIB-03
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T053a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-04 的測試(依序呼叫 `get_manifest("qwen2.5", "7b")`、`get_manifest("qwen2.5", "14b")`、`get_manifest("qwen2.5", "32b")`);現有程式已滿足這個案例(research.md R3:`get_manifest` 已經會分 404、5xx、非預期與格式不符),先執行確認它通過,再把 `src/cgb/adapters/model_library.py` 暫時改成「client 開了 `follow_redirects=True`,跟著 301 去讀 `latest` 的 manifest 並回傳 `sizeBytes`」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US2-LIB-04
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T053b [US2] 🟢 /tdd 綠燈:US2-LIB-04 由現有程式滿足,確認 `src/cgb/adapters/model_library.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-04 通過的程式碼(依賴 T053a)
  - 🧪 `testplan.md` § US2-LIB-04
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T054a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-05 的測試(每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")`);現有程式已滿足這個案例(research.md R3:`get_manifest` 已經會分 404、5xx、非預期與格式不符),先執行確認它通過,再把 `src/cgb/adapters/model_library.py` 暫時改成「沒接 `json.loads` 丟的 `JSONDecodeError`,讓它原樣往上拋」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US2-LIB-05
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T054b [US2] 🟢 /tdd 綠燈:US2-LIB-05 由現有程式滿足,確認 `src/cgb/adapters/model_library.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-05 通過的程式碼(依賴 T054a)
  - 🧪 `testplan.md` § US2-LIB-05
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T055a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-06 的測試(每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")`);現有程式已滿足這個案例(research.md R3:`get_manifest` 已經會分 404、5xx、非預期與格式不符),先執行確認它通過,再把 `src/cgb/adapters/model_library.py` 暫時改成「先用 `if not layers` 判雲端版本、後檢查型別,`null` 與 `{}` 被歸成 `LIBRARY_CLOUD_ONLY`」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US2-LIB-06
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T055b [US2] 🟢 /tdd 綠燈:US2-LIB-06 由現有程式滿足,確認 `src/cgb/adapters/model_library.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-06 通過的程式碼(依賴 T055a)
  - 🧪 `testplan.md` § US2-LIB-06
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T056a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-07 的測試(每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")`);現有程式已滿足這個案例(research.md R3:`get_manifest` 已經會分 404、5xx、非預期與格式不符),先執行確認它通過,再把 `src/cgb/adapters/model_library.py` 暫時改成「靠 Content-Type 是 `text/plain` 判雲端版本,B 回傳了 `{"sizeBytes": 0}`」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US2-LIB-07
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T056b [US2] 🟢 /tdd 綠燈:US2-LIB-07 由現有程式滿足,確認 `src/cgb/adapters/model_library.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-07 通過的程式碼(依賴 T056a)
  - 🧪 `testplan.md` § US2-LIB-07
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、SC-001;`research.md` § R3;`plan.md` § 待決問題 Q19
- [X] T057a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-08 的測試(呼叫 `get_manifest("qwen2.5", "7b")`),執行確認它因為「`_get` 只接 `httpx.TimeoutException` 與 `httpx.TransportError`;`DecodingError` 是 `RequestError` 的子類別,不是 `TransportError`,於是原樣越過轉接層往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US2-LIB-08
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、FR-004;`research.md` § R1;`plan.md` § 待決問題 Q10
- [X] T057b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T057a)
  - 🧪 `testplan.md` § US2-LIB-08
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、FR-004;`research.md` § R1;`plan.md` § 待決問題 Q10
- [X] T058a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-09 的測試(每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")`),執行確認它因為「`get_manifest` 沒接傳輸層例外,`httpx.ConnectError` 原樣往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US2-LIB-09
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、FR-004、SC-001;`research.md` § R1
- [X] T058b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T058a)
  - 🧪 `testplan.md` § US2-LIB-09
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、FR-004、SC-001;`research.md` § R1
- [X] T059a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-10 的測試(每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")`),執行確認它因為「只接 `httpx.NetworkError` 或 `httpx.ConnectError`,屬於 `ProtocolError` 的 `RemoteProtocolError` 原樣往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US2-LIB-10
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、FR-004、邊界情況;`research.md` § R1
- [X] T059b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T059a)
  - 🧪 `testplan.md` § US2-LIB-10
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、FR-004、邊界情況;`research.md` § R1
- [X] T060a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-11 的測試(每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")`),執行確認它因為「先寫 `except httpx.TransportError` 再寫 `except httpx.TimeoutException`,逾時被前者攔下歸成 `LIBRARY_UNREACHABLE`」這類實作而失敗
  - 🧪 `testplan.md` § US2-LIB-11
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、FR-004、SC-001;`research.md` § R1
- [X] T060b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T060a)
  - 🧪 `testplan.md` § US2-LIB-11
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、FR-004、SC-001;`research.md` § R1
- [X] T061a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-12 的測試(呼叫 `get_manifest("qwen2.5", "7b")`),執行確認它因為「用 `client.stream` 取回應,`try` 只包住送出請求,讀本文時的 `RemoteProtocolError` 在 `try` 外原樣往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US2-LIB-12
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、FR-004、邊界情況;`research.md` § R1
- [X] T061b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T061a)
  - 🧪 `testplan.md` § US2-LIB-12
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、FR-004、邊界情況;`research.md` § R1
- [X] T062a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-13 的測試(呼叫 `get_manifest("qwen2.5", "7b")`,從呼叫開始計時),執行確認它因為「建構參數 `request_timeout` 沒接到 httpx 的 `Timeout` 與 `asyncio.timeout`,仍用 httpx 預設的 5 秒或寫死的 10 秒」這類實作而失敗
  - 🧪 `testplan.md` § US2-LIB-13
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-006;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T062b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T062a)
  - 🧪 `testplan.md` § US2-LIB-13
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-006;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T063a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-14 的測試(呼叫 `get_manifest("qwen2.5", "7b")`,從呼叫開始計時),執行確認它因為「只把連線階段的逾時歸成 `LIBRARY_TIMEOUT`,讀本文時的 `ReadTimeout` 在 `try` 外原樣往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US2-LIB-14
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-006、邊界情況;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T063b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T063a)
  - 🧪 `testplan.md` § US2-LIB-14
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-006、邊界情況;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T064a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-15 的測試(呼叫 `get_manifest("qwen2.5", "7b")`,從呼叫開始計時),執行確認它因為「只設 httpx 的 `Timeout`,沒有用 `asyncio.timeout` 包住整個請求,每次讀取都沒逾時,請求遠超過 0.5 秒」這類實作而失敗
  - 🧪 `testplan.md` § US2-LIB-15
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-006;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T064b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T064a)
  - 🧪 `testplan.md` § US2-LIB-15
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001、FR-006;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T065a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US2-LIB-16 的測試(依序呼叫 `get_manifest("qwen2.5", "7b")`、`get_manifest("qwen2.5", "14b")`,每次從自己被呼叫時開始計時),執行確認它因為「整體期限掛在 `ModelLibrary` 實例或共用的 client 上,從第一次呼叫開始算,第二個請求只剩約 0.2 秒就逾時」這類實作而失敗
  - 🧪 `testplan.md` § US2-LIB-16
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T065b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py` 只寫讓 US2-LIB-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T065a)
  - 🧪 `testplan.md` § US2-LIB-16
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001;`research.md` § R2;`plan.md` § 待決問題 Q6、Q8
- [X] T066 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T050b~T065b 記下的重構清單(範圍限 `src/cgb/adapters/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_model_library.py` 的斷言(依賴 T065b)
  - 🧪 `testplan.md` § US2-LIB-01~US2-LIB-16
  - 📎 `testplan.md` § 3.1

### E2 後端 UI API

- [X] T067a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-01 的測試(送 `POST /api/downloads/estimate`,`models` 為 `["qwen2.5:0.5b", "qwen2.5:7b"]`),執行確認它因為「`_sized` 仍用只有 404、422 的 `_LIBRARY_STATUS` 查表,`KeyError` 變成 500」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4
- [X] T067b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-01 通過的程式碼(`DownloadsService._sized` 改用 `library_error(error.code, model=model)`,刪除只有兩個代碼的 `_LIBRARY_STATUS`;搜過 `src/` 與 `tests/`,`_LIBRARY_STATUS` 的呼叫端只有 `src/cgb/services/downloads.py` 的 `_sized`),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T067a)
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4
- [X] T068a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-02 的測試(試算 `["qwen2.5:7b"]`(只勾一個)),執行確認它因為「`MESSAGES` 沒補 `LIBRARY_TIMEOUT`,`ApiError.body()` 丟 `KeyError`、回 500」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、NFR-002;`research.md` § R4
- [X] T068b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T068a)
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、NFR-002;`research.md` § R4
- [X] T069a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-03 的測試(試算 `["qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:7b"]`),執行確認它因為「用 `asyncio.gather` 同時取三個 manifest,或全部取完才回第一個失敗,多送了後面兩個請求」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q3
- [X] T069b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T069a)
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q3
- [X] T070a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-04 的測試(試算 `["qwen2.5:0.5b", "qwen2.5"]`(第二個沒寫版本)),執行確認它因為「`model` 放使用者輸入的原樣 `qwen2.5`,沒補 `latest`」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q12
- [X] T070b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-04 通過的程式碼(沒寫版本的名稱在 `_sized` 補成 `<名稱>:latest` 再取 manifest 與放進 `model`;`src/cgb/api/curated.py` 已有同一條補 `latest` 的規則,這裡只寫讓案例通過的最小版本,要不要共用記進重構清單),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T070a)
  - 🧪 `testplan.md` § US2-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q12
- [X] T071a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-05 的測試(試算 `["qwen2.5:0.5b", "qwen2.5:999b", "qwen2.5:7b"]`);現有程式已滿足這個案例(research.md R4 的實測表),先執行確認它通過,再把 `src/cgb/services/downloads.py` 暫時改成「`model` 指成第一個或最後一個選取的模型」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US2-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q3;`plan.md` § 待決問題 Q19
- [X] T071b [US2] 🟢 /tdd 綠燈:US2-API-05 由現有程式滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-05 通過的程式碼(依賴 T071a)
  - 🧪 `testplan.md` § US2-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q3;`plan.md` § 待決問題 Q19
- [X] T072a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-06 的測試(試算 `["qwen2.5:0.5b", "gpt-oss:120b-cloud"]`);現有程式已滿足這個案例(research.md R4 的實測表),先執行確認它通過,再把 `src/cgb/services/downloads.py` 暫時改成「改成共用的 `LIBRARY_STATUS` 時漏了 `LIBRARY_CLOUD_ONLY`,退回預設 502」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US2-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、NFR-002;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T072b [US2] 🟢 /tdd 綠燈:US2-API-06 由現有程式滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-06 通過的程式碼(依賴 T072a)
  - 🧪 `testplan.md` § US2-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、NFR-002;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T073a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-07 的測試(送 `POST /api/downloads`,`models` 為 `["qwen2.5:0.5b", "qwen2.5:999b", "qwen2.5:7b"]`,之後 `GET /api/downloads`);現有程式已滿足這個案例(001 的行為),先執行確認它通過,再把 `src/cgb/services/downloads.py` 暫時改成「每取到一個 manifest 就寫進佇列,第一個 `qwen2.5:0.5b` 留在佇列並開始下載」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US2-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q3;`plan.md` § 待決問題 Q19
- [X] T073b [US2] 🟢 /tdd 綠燈:US2-API-07 由現有程式滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-07 通過的程式碼(依賴 T073a)
  - 🧪 `testplan.md` § US2-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q3;`plan.md` § 待決問題 Q19
- [X] T074a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-08 的測試(加入 `["qwen2.5:7b", "gpt-oss:120b-cloud"]`,之後 `GET /api/downloads`);現有程式已滿足這個案例(001 的行為),先執行確認它通過,再把 `src/cgb/services/downloads.py` 暫時改成「7b 先寫進佇列,遇到雲端版本才停,沒有撤掉」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US2-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T074b [US2] 🟢 /tdd 綠燈:US2-API-08 由現有程式滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-08 通過的程式碼(依賴 T074a)
  - 🧪 `testplan.md` § US2-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q19
- [X] T075a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-09 的測試(加入 `["qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:7b"]`(第三個取不到),之後 `GET /api/downloads`),執行確認它因為「前兩個取到大小就寫進 SQLite,第三個失敗時沒有回滾,佇列留下 0.5b 與 1.5b」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4
- [X] T075b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T075a)
  - 🧪 `testplan.md` § US2-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4
- [X] T076a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-10 的測試(加入 `["qwen2.5:7b"]`,之後 `GET /api/downloads`),執行確認它因為「加入的錯誤處理只改了試算那條路,`enqueue` 的逾時仍丟 `KeyError`、回 500」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、NFR-002;`research.md` § R4
- [X] T076b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T076a)
  - 🧪 `testplan.md` § US2-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、NFR-002;`research.md` § R4
- [X] T077a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-11 的測試(加入 `["qwen2.5:0.5b", "qwen2.5:1.5b"]`;0.5 秒後再加入 `["qwen2.5:7b"]`(對照組)),執行確認它因為「先 `_repo.enqueue` 並 `_publish` 0.5b、再取 1.5b 的 manifest,UI 收到一筆之後就不存在的 `download.updated`」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q15
- [X] T077b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T077a)
  - 🧪 `testplan.md` § US2-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q15
- [X] T078a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-12 的測試(加入 `["qwen2.5"]`(沒寫版本),之後 `GET /api/downloads`),執行確認它因為「`model` 放原樣的 `qwen2.5`」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q12
- [X] T078b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T078a)
  - 🧪 `testplan.md` § US2-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R4;`plan.md` § 待決問題 Q12
- [X] T079a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-13 的測試(加入 `["qwen2.5:1.5b"]`,之後 `GET /api/downloads`、`GET /api/curated`,再放行 0.5b-instruct 的閘門),執行確認它因為「模型庫失敗時把整個佇列清掉,或把下載中那一筆標成 `failed`」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況;`research.md` § R4;`plan.md` § 待決問題 Q15
- [X] T079b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T079a)
  - 🧪 `testplan.md` § US2-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § 邊界情況;`research.md` § R4;`plan.md` § 待決問題 Q15
- [X] T080a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-14 的測試(試算 `["qwen2.5:7b"]`),執行確認它因為「把 `AdapterError.message` 或 `str(error)` 放進 `message`」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、FR-005;`research.md` § R4
- [X] T080b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T080a)
  - 🧪 `testplan.md` § US2-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、FR-005;`research.md` § R4
- [X] T081a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US2-API-15 的測試(每一個代碼各加入 `["qwen2.5:7b"]` 一次、`["qwen2.5:1.5b"]` 一次),執行確認它因為「訊息用 f-string 嵌入模型名稱或替身的英文說明,同一個代碼兩次不一樣」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002;`research.md` § R4;`plan.md` § 待決問題 Q13
- [X] T081b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T081a)
  - 🧪 `testplan.md` § US2-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002;`research.md` § R4;`plan.md` § 待決問題 Q13
- [X] T082 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T067b~T081b 記下的重構清單(範圍限 `src/cgb/services/`、`src/cgb/domain/errors.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_api_downloads.py` 的斷言(依賴 T081b)
  - 🧪 `testplan.md` § US2-API-01~US2-API-15
  - 📎 `testplan.md` § 3.2

### 跨端點驗收(`tests/integration/test_library_cross.py`)

> 端點節(E8、E2)都完成、驗收過後由主 agent 開始;真的 E2(api、services、domain、repos 與 SQLite)接真的 `ModelLibrary`,ollama.com 與 registry 換成 `httpx.MockTransport`,其他轉接層用替身(`plan.md` § 待決問題 Q4、Q18)

- [X] T083a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_library_cross.py` 寫 US2-AJ-01 的測試(每種情況各試算一次 `["qwen2.5:7b"]`),執行確認它因為「`get_manifest` 的 httpx 例外沒在轉接層攔下,穿過 `_sized` 變成 500」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、FR-005、FR-006、SC-001;`research.md` § R5;`plan.md` § 待決問題 Q4
- [X] T083b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py`、`src/cgb/services/downloads.py` 只寫讓 US2-AJ-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T083a)
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、FR-005、FR-006、SC-001;`research.md` § R5;`plan.md` § 待決問題 Q4
- [X] T084a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_library_cross.py` 寫 US2-AJ-02 的測試(每種情況各加入一次 `["qwen2.5:7b"]`,每次之後 `GET /api/downloads`),執行確認它因為「加入的路徑和試算分開處理,只修了試算」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、FR-005、FR-006、SC-001;`research.md` § R5;`plan.md` § 待決問題 Q4
- [X] T084b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py`、`src/cgb/services/downloads.py` 只寫讓 US2-AJ-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T084a)
  - 🧪 `testplan.md` § US2-AJ-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、FR-005、FR-006、SC-001;`research.md` § R5;`plan.md` § 待決問題 Q4
- [X] T085a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_library_cross.py` 寫 US2-AJ-03 的測試(加入 `["qwen2.5:0.5b", "qwen2.5:cgb-test-nonexistent", "qwen2.5:7b"]`,之後 `GET /api/downloads`);現有程式已滿足這個案例(001 的行為),先執行確認它通過,再把 `src/cgb/services/downloads.py` 暫時改成「依序取 manifest 時遇到失敗沒有停,仍去取第三個(plan.md Q3)」這類實作,執行確認它斷言失敗,撤回暫時的改動;若一執行就斷言失敗(前面的綠燈任務改到了這條路徑),就當成一般的紅燈,不必再暫時改壞
  - 🧪 `testplan.md` § US2-AJ-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、FR-004;`research.md` § R5;`plan.md` § 待決問題 Q4、Q3;`plan.md` § 待決問題 Q19
- [X] T085b [US2] 🟢 /tdd 綠燈:US2-AJ-03 由現有程式滿足,確認 `src/cgb/adapters/model_library.py`、`src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/model_library.py`、`src/cgb/services/downloads.py` 只寫讓 US2-AJ-03 通過的程式碼(依賴 T085a)
  - 🧪 `testplan.md` § US2-AJ-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`;`contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、FR-004;`research.md` § R5;`plan.md` § 待決問題 Q4、Q3;`plan.md` § 待決問題 Q19
- [X] T086 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T083b~T085b 記下的重構清單(範圍限 `src/cgb/adapters/model_library.py`、`src/cgb/services/`、`src/cgb/domain/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_library_cross.py` 的斷言(依賴 T085b)
  - 🧪 `testplan.md` § US2-AJ-01~US2-AJ-03
  - 📎 `testplan.md` § 3.3

### 介面覆蓋(US2)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`(傳輸層失敗、共用狀態碼判定、逾時) | T050b~T065b、T083b~T085b | T050a~T065a、T083a~T085a |
| `model-library.openapi.yaml` § `components.schemas.Error`(manifest 會丟的代碼,含 `LIBRARY_CLOUD_ONLY`) | T050b~T065b | T050a~T065a |
| `ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`(`LIBRARY_*` 的狀態碼、`model`) | T067b~T072b、T080b、T083b | T067a~T072a、T080a、T083a |
| `ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadJobList`(`LIBRARY_*` 的狀態碼、`model`、整批不加入) | T073b~T079b、T081b、T084b、T085b | T073a~T079a、T081a、T084a、T085a |
| `ui.openapi.yaml` § `components.schemas.Error`(試算與加入下載回的 `LIBRARY_*` 與 `model`) | T067b~T081b | T067a~T081a |

### 測試案例覆蓋(US2)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US2-LIB-01~US2-LIB-16 | T050a~T065a | T050b~T065b | T066 |
| US2-API-01~US2-API-15 | T067a~T081a | T067b~T081b | T082 |
| US2-AJ-01~US2-AJ-03 | T083a~T085a | T083b~T085b | T086 |

**Checkpoint**: `uv run pytest` 全綠;重構任務前後的測試結果相同

---

## Phase 4: 全域測試區

**Purpose**: 照 `testplan.md` § 4.2 驗證跨故事的 NFR-001、SC-002 與 SC-003;兩個案例的「副作用與護欄」都寫 `時機:節內`,放在這一節

- [X] T087 [G] 📏 量測:撰寫 `tests/integration/test_002_g_01.py`(標 `@pytest.mark.realrun`,預設排除;不放 `tests/realrun/`,免得觸發那裡會執行 `colab usage` 的 `realrun` fixture,`plan.md` § 待決問題 Q16),照 G-01 以測試行程內的 uvicorn 起在 127.0.0.1 隨機 port(`live_servers`,真的 HTTP 連線,不經 `httpx.ASGITransport`),注入真的 `ModelLibrary(ollama_base_url=…, registry_base_url=…)`、不帶 `request_timeout`(預設 10 秒),兩個位址都指到 127.0.0.1 上接受連線但永不回應的本機 socket 伺服器(沿用 T018a 在 `tests/integration/test_model_library.py` 建的 helper);工作階段就緒用 E2 的替身。依序送一次搜尋、一次版本清單、一次只勾 `qwen2.5:7b` 的試算,再把 `ollama_base_url` 指到送出 200 標頭後每 0.4 秒送 1 byte 的本機 socket 伺服器送一次搜尋;記下四次從送出到收到回應的秒數、狀態碼與 `code`,和門檻(10 到 11 秒之間收到 504、`code` 為 `LIBRARY_TIMEOUT`)比較,以 `uv run pytest -m realrun tests/integration/test_002_g_01.py` 執行,結果以 `tests/realrun/conftest.py` 的 `write_measurement(..., path=<repo>/specs/002-library-error-handling/measurements.md)` 寫進 `specs/002-library-error-handling/measurements.md`。副作用與護欄:只連 127.0.0.1(uvicorn 與兩個本機 socket 伺服器都綁 127.0.0.1 隨機 port),`ollama_base_url`、`registry_base_url` 以建構參數指到本機,不連 ollama.com 與 registry;資料庫是 pytest 暫存資料夾的 SQLite;Colab、通道、遠端 Ollama 用替身,不執行任何 `colab` 指令、不花 compute units;約 45 秒。判定者:腳本(量到的秒數和 10~11 秒比較);樣本:一次量測,每個操作各一次(未用於調整)
  - 🧪 `testplan.md` § G-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`paths./library/models/{name}/tags.get`、`paths./downloads/estimate.post`;`contracts/model-library.openapi.yaml` § `paths./search.get`、`paths./library/{name}/tags.get`、`paths./v2/library/{name}/manifests/{tag}.get`
  - 📎 `spec.md` § NFR-001、SC-002;`research.md` § R2、R5;`plan.md` § 待決問題 Q7、Q16
- [X] T088 [G] 📏 量測:002 實作完成後在桌機撰寫並執行 `tests/integration/test_002_g_02.py`(標 `@pytest.mark.realrun`,預設排除;不放 `tests/realrun/`,不經會執行 `colab usage` 與複製授權檔的 `realrun` fixture,`plan.md` § 待決問題 Q17),沿用 `tests/realrun/helpers.py` 的 `RecordingTransport` 接真的 ollama.com 與 registry.ollama.ai,照 G-02 依序呼叫 `search_library(q="qwen2.5")` 第 1 頁、`search_library(q="zzzz-no-such-model")` 第 1 頁、`search_library(q="qwen2.5", page=2)`、`list_model_tags("qwen2.5")`、`get_manifest("qwen2.5", "7b")`;記下第 1 頁官方模型筆數、0 筆搜尋有沒有丟 `AdapterError`、第 2 頁有沒有丟 `LIBRARY_BAD_RESPONSE`、版本清單非 cloud 版本 `sizeLabel` 為 null 的個數、`qwen2.5:7b` 的 `sizeBytes`,和門檻(至少 1 筆且含 `qwen2.5`;不丟;不丟;0 個;4,600,000,000 到 4,800,000,000)比較,以 `uv run pytest -m realrun tests/integration/test_002_g_02.py` 執行,結果以 `write_measurement(..., path=<repo>/specs/002-library-error-handling/measurements.md)` 寫進 `specs/002-library-error-handling/measurements.md`。副作用與護欄:只送 GET,`RecordingTransport(get_only=True, max_requests=10, min_interval=1.0)` 強制總共不超過 10 個請求(這次 5 個)、間隔 1 秒、不重試、不帶 token;只在桌機跑,不碰 Tower、Pi 與共用服務,不開 Colab、0 compute units;錄下的只有狀態碼與長度,結果只寫 pytest 暫存資料夾(錄下的往返;量測數字照上面另寫一列進 `measurements.md`);連不到就標無法實跑,不改用存下來的頁面。判定者:腳本;樣本:執行當下的 ollama.com 與 registry 一次(未用於調整)
  - 🧪 `testplan.md` § G-02
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`paths./library/{name}/tags.get`、`paths./v2/library/{name}/manifests/{tag}.get`
  - 📎 `spec.md` § SC-003、FR-001、FR-002、FR-004;`research.md` § R3、R5;`plan.md` § 待決問題 Q9、Q17

### 測試案例覆蓋(全域)

| testplan 案例 | 任務 |
|---|---|
| G-01 | T087 |
| G-02 | T088 |

**Checkpoint**: 全部測試綠燈;`specs/002-library-error-handling/measurements.md` 每一項都寫了數字與是否過門檻,沒過的列為待決問題
