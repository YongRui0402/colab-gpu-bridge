# Tasks: 加入下載的重複判定與模型目錄快取

**Input**: `specs/003-download-dedup-model-cache/` 的設計文件(本 spec package);建立在 `specs/002-library-error-handling/` 之上(002 建立在 `specs/001-session-model-catalog/` 之上),既有程式在 `src/cgb/`、既有測試在 `tests/`

**Prerequisites**: plan.md、spec.md、research.md、techstack.md、testplan.md、contracts/remote-ollama.openapi.yaml、contracts/ui.openapi.yaml

**Tests**: 依 `testplan.md` 切分。testplan 的每個行為測試案例對應一組 `/tdd` 紅燈與綠燈任務,每個「使用者故事 × 端點」節最後一個 `/tdd` 重構任務;量測與人工驗證的案例對應 📏 任務。

**Organization**: 依 `testplan.md` 的使用者故事分 phase;每個故事底下依 `testplan.md` 的端點分節(E7 遠端 Ollama、E2 後端 UI API),外加一節跨端點驗收,最後是介面覆蓋表與測試案例覆蓋表。全域測試區自成一個 phase,放在所有故事之後。

## Format: `[ID] [Story] [步驟] Description`,底下接 🧪、⚙ 與 📎

- **[Story]**:所屬的使用者故事(US1、US2);全域測試區寫 `[G]`
- **[步驟]**:這個任務是 `/implement` 交給誰做的哪一步
  - 🔴 `/tdd 紅燈`:寫一個測試案例的測試,執行確認它失敗
  - 🟢 `/tdd 綠燈`:只寫讓同一個案例通過的程式碼,執行全部測試確認都通過
  - 🔵 `/tdd 重構`:在全部測試綠燈下,整理這一節綠燈任務記下的重構清單,不改行為、不改斷言
  - 📏 量測:照 testplan 案例的條件量測或人工驗證,記下數字與門檻比較;是唯一不對應 `/tdd` 的開發任務
  - 不標步驟的只限三類:工具鏈設定、原樣複製 spec package 的規格檔、CI 設定
- **紅綠成對**:一個 testplan 案例對應同一個三位數的 `a`(🔴)與 `b`(🟢),`b` 依賴 `a`
- **對照組**:案例要測的程式路徑已經由既有程式或更早的綠燈任務做到時,紅燈任務標「(對照組)」:先確認通過,再暫時放入要抓的錯、確認斷言失敗後撤回;對應的綠燈任務確認不需要改程式碼(`plan.md` § 待決問題 Q24)
- **誰做、怎麼排**:同一個 phase 的端點節各交給一個 subagent 平行做;跨端點驗收節在端點節都完成、驗收過後由主 agent 做。每一節裡照任務編號一次做一個任務,做完才做下一個,不跳號
- 每個任務都寫出確切的檔案路徑
- **🧪**:這個任務對應的 `testplan.md` 案例 ID;🔵 寫這一節所有案例的範圍;不標步驟的任務不寫這一行
- **⚙**:這個任務要做出來或測到的介面元素:至少照 `testplan.md` 受測操作表的「規格錨點」欄寫,再加上這個任務實際做出或斷言的介面元素
- **📎**:做這個任務時要對照的依據:`spec.md` § FR / NFR / SC / 邊界情況、`research.md` § R、`plan.md` § Q 或段落名、`techstack.md` § 段落名

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 沿用 001、002 的工具鏈、`pyproject.toml`、`uv.lock` 與測試基礎(`tests/conftest.py`、`tests/fakes/`);這一輪不新增套件、不複製規格檔、不改 CI(`techstack.md` § 新引入與沿用、`plan.md` § Project Structure),這個 phase 沒有任務。替身 `FakeMethod.invoke` 接受 async 的 `side_effect`(research.md R4)由第一個需要它的 T038a 做。

---

## Phase 2: User Story 1 - 沒寫版本的名稱不會被重複加入下載 (Priority: P1) 🎯 MVP

**Goal**: 使用者輸入沒寫版本的 `qwen2.5` 時,和執行環境上已有、或佇列裡排隊中、下載中的 `qwen2.5:latest` 判定為同一個,試算與加入下載都回 409 與對應的 `code`,同一批補過版本後相同的只算一次、只加入一筆;讀不到模型清單時回 502、504,沒有任何一次是 500

**Independent Test**: 照 `testplan.md` § 2 的全部案例:E7 以 `uv run pytest tests/integration/test_remote_ollama.py`(真的 `RemoteOllama` 接 `httpx.MockTransport`)、E2 以 `uv run pytest tests/integration/test_api_downloads.py`(`FakeRemoteOllama`、`FakeModelLibrary`、`live_servers`)、跨端點驗收以 `uv run pytest tests/integration/test_downloads_cross.py` 執行全綠

### E7 遠端 Ollama(Colab 執行環境上,Ollama API)

> E7 與 E2 兩節平行;E7 只改 `src/cgb/adapters/remote_ollama.py` 與 `tests/integration/test_remote_ollama.py`,E2 只改 `src/cgb/services/`、`src/cgb/repos/downloads.py`、`src/cgb/domain/`、`tests/integration/test_api_downloads.py`、`tests/fakes/adapters.py` 與 `tests/e2e/test_locale.py`,兩節沒有共用的檔。handler 記下請求的 `Recorder` 放哪由 `/tdd` 決定(`plan.md` § 待決問題 Q13);001 的 `test_list_local_models_與_list_loaded_models_回名稱與大小` 保留不動

- [ ] T001a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-01 的測試(handler 回兩筆模型,呼叫 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-01`(`plan.md` § 待決問題 Q7));`RemoteOllama._get_list` 現在原樣回傳 `response.json()`(`src/cgb/adapters/remote_ollama.py`),名稱、大小與請求路徑都照實,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 改成「加上形狀檢查時把清單改寫成只剩名稱的 list,丟掉 `size`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-RO-01
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001;`research.md` § R2;`plan.md` § 待決問題 Q13
- [ ] T001b [US1] 🟢 /tdd 綠燈:US1-RO-01 由 既有程式(`RemoteOllama._get_list`) 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-01 通過的程式碼(依賴 T001a)
  - 🧪 `testplan.md` § US1-RO-01
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001;`research.md` § R2;`plan.md` § 待決問題 Q13
- [ ] T002a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-02 的測試(handler 回 `qwen2.5`、`llama3.2:latest`、`hf.co/…:Q4_K_M` 三筆,呼叫 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-02`(`plan.md` § 待決問題 Q7));`_get_list` 原樣交回每筆的 `name`,沒有補版本、轉小寫或去前綴,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 改成「對 `/api/tags` 每筆的 `name` 套 `with_version()` 補成 `:latest`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-RO-02
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R1
- [ ] T002b [US1] 🟢 /tdd 綠燈:US1-RO-02 由 既有程式(`RemoteOllama._get_list`) 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-02 通過的程式碼(依賴 T002a)
  - 🧪 `testplan.md` § US1-RO-02
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R1
- [ ] T003a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-03 的測試(handler 回 `{"models":[]}`,呼叫 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-03`(`plan.md` § 待決問題 Q7));`_get_list` 現在不檢查形狀,空陣列原樣回傳,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 改成「形狀檢查寫成 `if not body.get("models")`,空陣列被當成缺少 `models` 丟 `OLLAMA_BAD_RESPONSE`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-RO-03
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q2
- [ ] T003b [US1] 🟢 /tdd 綠燈:US1-RO-03 由 既有程式(`RemoteOllama._get_list`) 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-03 通過的程式碼(依賴 T003a)
  - 🧪 `testplan.md` § US1-RO-03
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q2
- [ ] T004a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-04 的測試(handler 回只有 `name`、`size` 的一筆與其他欄位型別都不符的一筆,呼叫 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-04`(`plan.md` § 待決問題 Q7));`_get_list` 現在不檢查任何欄位,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 改成「照 `LocalModel` schema 驗全部必填欄位,缺 `digest`、`modified_at` 或型別不符就丟 `OLLAMA_BAD_RESPONSE`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-RO-04
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q2
- [ ] T004b [US1] 🟢 /tdd 綠燈:US1-RO-04 由 既有程式(`RemoteOllama._get_list`) 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-04 通過的程式碼(依賴 T004a)
  - 🧪 `testplan.md` § US1-RO-04
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q2
- [ ] T005a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-05 的測試(handler 依情況丟 `ConnectTimeout`、`ReadTimeout`、`WriteTimeout`、`PoolTimeout`,每種各用一個新的 `RemoteOllama` 呼叫一次 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-05`(`plan.md` § 待決問題 Q7)),執行確認它因為「`_get_list` 沒有接任何 httpx 例外,逾時原樣往上拋(現況,research.md R2)」這類實作而失敗
  - 🧪 `testplan.md` § US1-RO-05
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2;`plan.md` § 待決問題 Q11、Q12
- [ ] T005b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-05 通過的程式碼(照同檔 `get_version` 以 `try` 包住 `async with` 與 `client.get`(本文在 `client.get` 裡讀完),`httpx.TimeoutException` 歸成 `OLLAMA_TIMEOUT` 的 `AdapterError`,不重試),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T005a)
  - 🧪 `testplan.md` § US1-RO-05
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2;`plan.md` § 待決問題 Q11、Q12
- [ ] T006a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-06 的測試(handler 回 200,本文是先送 `{"models":[{"name":"qwen2.5:latest",` 再丟 `ReadTimeout` 的半截串流,呼叫 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-06`(`plan.md` § 待決問題 Q7));本文在 `client.get` 裡讀完,T005b 的 `try` 已包住它,讀到一半的 `ReadTimeout` 也歸成 `OLLAMA_TIMEOUT`,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 改成「改用 `client.send(..., stream=True)`,`try` 只包住送出請求,讀本文時的 `ReadTimeout` 在 `try` 外原樣往上拋」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-RO-06
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2
- [ ] T006b [US1] 🟢 /tdd 綠燈:US1-RO-06 由 T005b 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-06 通過的程式碼(依賴 T006a、T005b)
  - 🧪 `testplan.md` § US1-RO-06
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2
- [ ] T007a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-07 的測試(handler 依情況丟 `ConnectError`、`ReadError`、`RemoteProtocolError`,每種各用一個新的 `RemoteOllama` 呼叫一次 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-07`(`plan.md` § 待決問題 Q7)),執行確認它因為「`_get_list` 只接 `httpx.TimeoutException`(T005b),其他傳輸層失敗原樣往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US1-RO-07
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2;`plan.md` § 待決問題 Q12
- [ ] T007b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-07 通過的程式碼(在接逾時之後接 `httpx.TransportError`,歸成 `OLLAMA_UNREACHABLE`,不重試),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T007a)
  - 🧪 `testplan.md` § US1-RO-07
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2;`plan.md` § 待決問題 Q12
- [ ] T008a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-08 的測試(handler 回 200,本文是先送一段再丟 `RemoteProtocolError` 的半截串流,呼叫 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-08`(`plan.md` § 待決問題 Q7));`RemoteProtocolError` 屬於 `TransportError`,T007b 在 `client.get` 外接住它,讀到一半中斷也歸成 `OLLAMA_UNREACHABLE`,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 改成「只接 `httpx.ConnectError` 與 `httpx.NetworkError`,`RemoteProtocolError` 原樣往上拋」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-RO-08
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2
- [ ] T008b [US1] 🟢 /tdd 綠燈:US1-RO-08 由 T007b 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-08 通過的程式碼(依賴 T008a、T007b)
  - 🧪 `testplan.md` § US1-RO-08
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2
- [ ] T009a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-09 的測試(handler 依情況回 503(合法清單)、404、500、201(合法清單),每種各用一個新的 `RemoteOllama` 呼叫一次 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-09`(`plan.md` § 待決問題 Q7)),執行確認它因為「不看狀態碼就解析本文,503、201 帶的合法清單照常回傳(現況)」這類實作而失敗
  - 🧪 `testplan.md` § US1-RO-09
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2
- [ ] T009b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-09 通過的程式碼(狀態碼不是 200 一律歸成 `OLLAMA_BAD_RESPONSE`,不沿用同檔 `generate` 的 `_STATUS_CODES`,不重試),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T009a)
  - 🧪 `testplan.md` § US1-RO-09
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2
- [ ] T010a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-10 的測試(`/api/tags` 回 302 導到 `/elsewhere`、`/elsewhere` 回合法清單,呼叫 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-10`(`plan.md` § 待決問題 Q7));`_client` 沒有開 `follow_redirects`(httpx 預設不跟著導向),T009b 已把非 200 歸成 `OLLAMA_BAD_RESPONSE`,這個案例會被滿足:先執行確認通過,再暫時把 `RemoteOllama._client` 改成「建 client 時開了 `follow_redirects=True`,跟著導向把 `/elsewhere` 的清單當成已下載的模型回傳」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-RO-10
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2
- [ ] T010b [US1] 🟢 /tdd 綠燈:US1-RO-10 由 T009b 與既有的 `RemoteOllama._client` 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-10 通過的程式碼(依賴 T010a、T009b)
  - 🧪 `testplan.md` § US1-RO-10
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2
- [ ] T011a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-11 的測試(handler 依情況回 200 的 HTML、宣稱 gzip 卻壞掉的本文(`stream=httpx.ByteStream(b"not gzip")`)、空本文,每種各用一個新的 `RemoteOllama` 呼叫一次 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-11`(`plan.md` § 待決問題 Q7)),執行確認它因為「`response.json()` 的 `json.JSONDecodeError` 原樣往上拋(現況,research.md R2)」這類實作而失敗
  - 🧪 `testplan.md` § US1-RO-11
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2;`plan.md` § 待決問題 Q1
- [ ] T011b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-11 通過的程式碼(`response.json()` 的 `ValueError` 與讀本文時的 `httpx.DecodingError` 歸成 `OLLAMA_BAD_RESPONSE`;`DecodingError` 不屬於 `TransportError`,另外接,不併進 `RequestError`),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T011a)
  - 🧪 `testplan.md` § US1-RO-11
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`research.md` § R2;`plan.md` § 待決問題 Q1
- [ ] T012a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-12 的測試(handler 依情況回 200 的 `[]`、`{}`、`{"models":null}`、`models` 是物件、字串,每種各用一個新的 `RemoteOllama` 呼叫一次 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-12`(`plan.md` § 待決問題 Q7)),執行確認它因為「只要 JSON 解析成功就原樣回傳,不檢查最上層形狀(現況)」這類實作而失敗
  - 🧪 `testplan.md` § US1-RO-12
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`plan.md` § 待決問題 Q2
- [ ] T012b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-12 通過的程式碼(最上層不是物件、缺少 `models` 或 `models` 不是陣列 → `OLLAMA_BAD_RESPONSE`;空陣列照常回傳),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T012a)
  - 🧪 `testplan.md` § US1-RO-12
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`plan.md` § 待決問題 Q2
- [ ] T013a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-13 的測試(handler 依情況回 `models` 裡有字串、沒有 `name`、`name` 是 123、`name` 是 null、第二筆沒有 `name`,每種各用一個新的 `RemoteOllama` 呼叫一次 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-13`(`plan.md` § 待決問題 Q7)),執行確認它因為「只檢查 `models` 是陣列(T012b),不逐筆檢查是物件、有字串的 `name`」這類實作而失敗
  - 🧪 `testplan.md` § US1-RO-13
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`plan.md` § 待決問題 Q2
- [ ] T013b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-13 通過的程式碼(逐筆檢查是物件、有字串的 `name`,任何一筆不符就整份 `OLLAMA_BAD_RESPONSE`,不跳過、不轉字串),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T013a)
  - 🧪 `testplan.md` § US1-RO-13
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`plan.md` § 待決問題 Q2
- [ ] T014a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-14 的測試(handler 依情況回唯一一筆 `qwen2.5:latest` 沒有 `size`、`size` 是字串、-1、`true`、null,每種各用一個新的 `RemoteOllama` 呼叫一次 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-14`(`plan.md` § 待決問題 Q7)),執行確認它因為「沒有檢查 `size`,字串、負數、`true`、null 照常回傳」這類實作而失敗
  - 🧪 `testplan.md` § US1-RO-14
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`plan.md` § 待決問題 Q2
- [ ] T014b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-14 通過的程式碼(`/api/tags` 每一筆要有非負整數的 `size`(排除 `bool`);這個檢查只套在 `list_local_models`,`/api/ps` 不要求 `size`(合約 `info.x-failure-rules` 第 5 條)),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T014a)
  - 🧪 `testplan.md` § US1-RO-14
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、FR-001;`plan.md` § 待決問題 Q2
- [ ] T015a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US1-RO-15 的測試(handler 記下 `request.extensions["timeout"]` 並回 `{"models":[]}`,`RemoteOllama(transport=...)` 不帶逾時參數,呼叫 `list_local_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US1-RO-15`(`plan.md` § 待決問題 Q7));`_get_list` 以 `httpx.Timeout(LIST_TIMEOUT)` 建 client,四項都是 10 秒(`src/cgb/adapters/remote_ollama.py`),T005b~T014b 沒有改它,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 建 client 的逾時 改成「加歸類時改用同檔 `get_version` 的設定,沿用 `version_timeout` 的 5 秒」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-RO-15
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003;`plan.md` § 待決問題 Q10
- [ ] T015b [US1] 🟢 /tdd 綠燈:US1-RO-15 由 既有程式(`LIST_TIMEOUT`) 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US1-RO-15 通過的程式碼(依賴 T015a)
  - 🧪 `testplan.md` § US1-RO-15
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003;`plan.md` § 待決問題 Q10
- [ ] T016 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T001b~T015b 記下的重構清單(範圍限 `src/cgb/adapters/remote_ollama.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_remote_ollama.py` 的斷言(依賴 T015b)
  - 🧪 `testplan.md` § US1-RO-01~US1-RO-15
  - 📎 `testplan.md` § 2.1

### E2 後端 UI API(FastAPI REST 與 SSE)

> 沿用 `ui_client`、`fakes`、`db_path`、`live_servers` 與檔內的 `downloadable`、`set_library`、`enqueue_waiting`、`hold_pulls`、`insert_jobs`、`queue`、`states`,以及 `test_api_models.py` 的 `set_tags`、`tag`、`resources`;`set_tags` 讓執行環境上有 `qwen2.5:latest` 都在 `enqueue_waiting` 之後才設定(`testplan.md` § 2.2 說明)。試算與加入下載共用的重複檢查 `DownloadsService._checked` 由 T017b 建立,之後的綠燈任務都改同一個函式(research.md R2 的檢查順序)。001 的 `test_一批裡有已下載或已排隊的模型時整批不加入`、`test_沒有工作階段時不加入`、`test_讀不到剩餘空間時不加入`、`test_佇列裡還沒下載的大小也算進剩餘空間` 與 002 的試算、加入下載案例照原樣回歸,不改寫

- [X] T017a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US1-API-01 的測試(執行環境上已有 `qwen2.5:latest`,試算 `["qwen2.5"]`;分隔註解寫 `# ---- 003 US1-API-01`(`plan.md` § 待決問題 Q7));同一個任務在檔內新增 `LATEST_SIZES = {**MANIFEST_SIZES, "qwen2.5:latest": 4_683_087_332, "llama3.2:latest": 2_019_393_189}`,不改 `MANIFEST_SIZES`,執行確認它因為「試算照現況完全不做重複檢查,取到大小就回 200」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-001;`research.md` § R1、R2
- [X] T017b [US1] 🟢 /tdd 綠燈:在 `src/cgb/domain/model_name.py`(新增)、`src/cgb/services/downloads.py` 只寫讓 US1-API-01 通過的程式碼(新增 `with_version(name: str) -> str`(research.md R1 的規則);`src/cgb/services/downloads.py` 原本的 `with_version` 改成從 `cgb.domain.model_name` 匯入,呼叫端只有同檔的 `_sized`;`DownloadsService` 加試算與加入下載共用的 `_checked(models) -> list[str]`:先 `require_ready_base_url()`,補過版本後讀一次 `list_local_models`、依序逐一比對,回傳補過版本的名稱清單;試算先走 `_checked` 再 `_sized`),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T017a)
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-001;`research.md` § R1、R2;`plan.md` § Project Structure
- [X] T018a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US1-API-02 的測試(執行環境上已有 `qwen2.5:latest`、`hold_pulls(fakes)`,加入 `["qwen2.5"]` 後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-02`(`plan.md` § 待決問題 Q7)),執行確認它因為「`enqueue` 照現況以原樣的名稱比對 `local`,`qwen2.5` 不在 `{"qwen2.5:latest"}` 裡就照常加入、重下載一次」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001;`research.md` § R2
- [X] T018b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py` 只寫讓 US1-API-02 通過的程式碼(加入下載改走 T017b 的 `_checked` 比對執行環境上的模型,拿掉 `enqueue` 裡以原樣名稱比對 `local` 的那一段;原本比對佇列的那一段改用 `_checked` 回傳的補過版本的名稱;之後以同一份清單取 manifest),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T018a)
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001;`research.md` § R2
- [X] T019a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US1-API-03 的測試(佇列是下載中的 `qwen2.5:0.5b`、排隊中的 `qwen2.5:latest`,試算 `["qwen2.5"]` 後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-03`(`plan.md` § 待決問題 Q7)),執行確認它因為「試算只加了「已下載」的檢查、沒比對佇列,回 200」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001;`research.md` § R2
- [X] T019b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py` 只寫讓 US1-API-03 通過的程式碼(`_checked` 在同一個逐一比對的迴圈裡,每個模型比對完執行環境上的模型之後再比對 `_pending()`(排隊中、下載中)→ 409 `DOWNLOAD_ALREADY_QUEUED`(research.md R2 檢查順序 4);`enqueue` 裡另外比對佇列的那一段移除),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T019a)
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001;`research.md` § R2
- [X] T020a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-04 的測試(佇列是下載中的 `qwen2.5:latest`、排隊中的 `qwen2.5:7b`,加入 `["qwen2.5"]` 後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-04`(`plan.md` § 待決問題 Q7));T018b 讓加入下載以補過版本的名稱比對佇列,T019b 把佇列比對併進 `_checked`,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「比對佇列時用原樣的 `qwen2.5`,通過檢查後寫入時撞到 `pending_model` 的唯一限制回 500」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003;`research.md` § R2
- [X] T020b [US1] 🟢 /tdd 綠燈:US1-API-04 由 T018b、T019b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-04 通過的程式碼(依賴 T020a、T018b、T019b)
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003;`research.md` § R2
- [X] T021a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-05 的測試(執行環境上已有 `qwen2.5:latest`,加入 `["qwen2.5:7b"]` 後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-05`(`plan.md` § 待決問題 Q7));`_checked` 以補過版本的完整名稱比對(T017b、T018b),`qwen2.5:7b` 不補版本、不等於 `qwen2.5:latest`;改之前的 `enqueue` 也已經是完整名稱比對,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「比對時只取 `:` 前面的名稱部分」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R1
- [X] T021b [US1] 🟢 /tdd 綠燈:US1-API-05 由 既有程式與 T017b、T018b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-05 通過的程式碼(依賴 T021a、T018b)
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R1
- [X] T022a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US1-API-06 的測試(執行環境上沒有模型、佇列是空的,試算 `["qwen2.5", "qwen2.5:latest"]`;分隔註解寫 `# ---- 003 US1-API-06`(`plan.md` § 待決問題 Q7)),執行確認它因為「沒合併同一批,`items` 列兩筆 `qwen2.5:latest`、`totalBytes` 算兩次(現況)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-002;`research.md` § R1
- [X] T022b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py` 只寫讓 US1-API-06 通過的程式碼(`_checked` 補過版本後以 `list(dict.fromkeys(...))` 合併同一批、保留第一次出現的順序,比對、取 manifest、試算大小與寫入佇列都用合併後的清單),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T022a)
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-002;`research.md` § R1
- [X] T023a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-07 的測試(加入 `["qwen2.5:0.5b", "qwen2.5", "qwen2.5:7b", "qwen2.5:latest"]` 後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-07`(`plan.md` § 待決問題 Q7));T022b 在 `_checked` 合併同一批並保留第一次出現的順序,加入下載以合併後的清單取 manifest 與寫入(T018b),這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「沒合併,第二筆 `qwen2.5:latest` 撞唯一限制回 500」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-002;`research.md` § R1
- [X] T023b [US1] 🟢 /tdd 綠燈:US1-API-07 由 T022b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-07 通過的程式碼(依賴 T023a、T022b)
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-002;`research.md` § R1
- [X] T024a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-08 的測試(加入 `["qwen2.5:7b", "qwen2.5:7b"]` 後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-08`(`plan.md` § 待決問題 Q7));T022b 的合併對所有補過版本後相同的名稱都成立,寫了版本的相同名稱也合併,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「合併只處理「沒寫版本」和「寫了 latest」這一對,寫了版本的相同名稱沒合併、第二筆撞唯一限制回 500」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-002;`research.md` § R1
- [X] T024b [US1] 🟢 /tdd 綠燈:US1-API-08 由 T022b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-08 通過的程式碼(依賴 T024a、T022b)
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-002;`research.md` § R1
- [X] T025a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-09 的測試(佇列是下載中的 `qwen2.5:1.5b`、排隊中的 `qwen2.5:latest`,加入 `["qwen2.5:0.5b", "qwen2.5", "qwen2.5:7b"]` 後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-09`(`plan.md` § 待決問題 Q7));`_checked` 在取 manifest 與寫入之前依序比對,第一個重複的就回(T019b),加入下載也走它(T018b),這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「重複的那一個跳過、其他照常回傳並加入」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001;`research.md` § R2
- [X] T025b [US1] 🟢 /tdd 綠燈:US1-API-09 由 T018b、T019b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-09 通過的程式碼(依賴 T025a、T019b)
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001;`research.md` § R2
- [X] T026a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-10 的測試(以 `insert_jobs` 寫入一筆失敗的 `qwen2.5:latest`、開到就緒,加入 `["qwen2.5"]` 後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-10`(`plan.md` § 待決問題 Q7));同一個任務讓檔內的 `insert_jobs` 加 `sizes` 關鍵字參數(預設 `MANIFEST_SIZES`),寫得進 `qwen2.5:latest`;`DownloadsService._pending()` 只取排隊中、下載中(`src/cgb/services/downloads.py`),T019b 的佇列比對用的就是它;失敗那筆的 `pending_model` 是 null,不撞唯一限制,這個案例會被滿足:先執行確認通過,再暫時把 `_pending()` 改成「以佇列裡所有紀錄的 `model` 比對,沒排除 `failed`,回 409 `DOWNLOAD_ALREADY_QUEUED`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R2;`plan.md` § 待決問題 Q20
- [X] T026b [US1] 🟢 /tdd 綠燈:US1-API-10 由 既有的 `_pending()` 與 T019b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-10 通過的程式碼(依賴 T026a、T019b)
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R2;`plan.md` § 待決問題 Q20
- [X] T027a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-11 的測試(以 `insert_jobs(..., sizes=LATEST_SIZES)` 寫入一筆已完成的 `qwen2.5:latest`、開到就緒、執行環境上沒有模型,加入 `["qwen2.5"]` 後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-11`(`plan.md` § 待決問題 Q7));`_pending()` 不取 `completed`,已完成那筆的 `pending_model` 是 null;「已下載」只看執行環境上的模型清單(T017b),這個案例會被滿足:先執行確認通過,再暫時把 `_pending()` 改成「把 `completed` 的紀錄也算進「已在佇列」」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R2;`plan.md` § 待決問題 Q20
- [X] T027b [US1] 🟢 /tdd 綠燈:US1-API-11 由 既有的 `_pending()` 與 T017b、T019b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-11 通過的程式碼(依賴 T027a、T019b)
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、邊界情況;`research.md` § R2;`plan.md` § 待決問題 Q20
- [X] T028a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-12 的測試(`set_library` 認得 `qwen2.5:Latest`、執行環境上已有 `qwen2.5:latest`,試算 `["qwen2.5:Latest"]`;分隔註解寫 `# ---- 003 US1-API-12`(`plan.md` § 待決問題 Q7));`with_version` 不轉大小寫,`_checked` 以完整名稱原樣比對(T017b),這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「補版本或比對前把名稱轉成小寫」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、假設;`research.md` § R1
- [X] T028b [US1] 🟢 /tdd 綠燈:US1-API-12 由 T017b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-12 通過的程式碼(依賴 T028a)
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、假設;`research.md` § R1
- [X] T029a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-13 的測試(`qwen2.5:7b` 排隊中、之後執行環境上有 `qwen2.5:latest`,試算 `["qwen2.5:7b", "qwen2.5"]`、加入 `["qwen2.5", "qwen2.5:7b"]`;分隔註解寫 `# ---- 003 US1-API-13`(`plan.md` § 待決問題 Q7));T019b 在同一個迴圈裡依合併後的順序對每個模型先比已下載、再比佇列,第一個重複的就回,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「先拿整批比對已下載、全部比完才比對佇列」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001;`research.md` § R2
- [X] T029b [US1] 🟢 /tdd 綠燈:US1-API-13 由 T019b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-13 通過的程式碼(依賴 T029a、T019b)
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001;`research.md` § R2
- [X] T030a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-14 的測試(沒有開工作階段,試算 `["qwen2.5"]`;分隔註解寫 `# ---- 003 US1-API-14`(`plan.md` § 待決問題 Q7));T017b 的 `_checked` 先 `require_ready_base_url()`,沒有工作階段時在讀模型清單與取 manifest 之前回 503,這個案例會被滿足:先執行確認通過,再暫時把 `DownloadsService.estimate` 改成「試算不走 `_checked`、直接 `_sized` 取 manifest(現況),讀剩餘空間時回 500」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003、邊界情況;`research.md` § R2
- [X] T030b [US1] 🟢 /tdd 綠燈:US1-API-14 由 T017b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-14 通過的程式碼(依賴 T030a)
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003、邊界情況;`research.md` § R2
- [X] T031a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-15 的測試(`create_session` 停在閘門、工作階段開啟中,試算與加入 `["qwen2.5"]` 各一次,之後放行閘門;分隔註解寫 `# ---- 003 US1-API-15`(`plan.md` § 待決問題 Q7));`require_ready_base_url()` 在開啟中也回 503(`SessionLifecycle.ready_base_url` 只認 `ready`),試算由 T017b、加入下載本來就先呼叫它,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「工作階段檢查只看 `lifecycle.current()` 有沒有工作階段、不看是否就緒」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003;`research.md` § R2;`plan.md` § 待決問題 Q21
- [X] T031b [US1] 🟢 /tdd 綠燈:US1-API-15 由 T017b 與既有的 `require_ready_base_url()` 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-15 通過的程式碼(依賴 T031a)
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003;`research.md` § R2;`plan.md` § 待決問題 Q21
- [X] T032a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-16 的測試(沒有開工作階段,試算與加入各送一次 `{"models": [`;對照組試算合法的 `{"models": ["qwen2.5"]}`;分隔註解寫 `# ---- 003 US1-API-16`(`plan.md` § 待決問題 Q7));兩個路由先 `read_json`(`src/cgb/api/downloads.py`),壞掉的本文在服務之前回 400;對照組的 503 由 T017b 的 `_checked` 回,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/api/downloads.py` 的兩個路由 改成「在讀本文之前先呼叫 `require_ready_base_url()`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003;`plan.md` § 待決問題 Q5
- [X] T032b [US1] 🟢 /tdd 綠燈:US1-API-16 由 既有的 `read_json` 與 T017b 滿足,確認 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py` 只寫讓 US1-API-16 通過的程式碼(依賴 T032a)
  - 🧪 `testplan.md` § US1-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003;`plan.md` § 待決問題 Q5
- [X] T033a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US1-API-17 的測試(`list_local_models.raises(code)` 依序換 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,各試算一次 `["qwen2.5"]`;分隔註解寫 `# ---- 003 US1-API-17`(`plan.md` § 待決問題 Q7)),執行確認它因為「試算沒接 `AdapterError`,`MESSAGES` 也沒有這三個代碼,`ApiError.body()` 丟 `KeyError`,回 500」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003、假設;`research.md` § R2;`plan.md` § Structure Decision
- [X] T033b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py`、`tests/e2e/test_locale.py` 只寫讓 US1-API-17 通過的程式碼(`_checked` 讀 `list_local_models` 時接 `AdapterError`:`OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE` → 502,`OLLAMA_TIMEOUT` → 504,不帶 `model`;`MESSAGES` 只補這三個代碼的繁中說明(分身決策紀錄 D9);同一個任務在 `tests/e2e/test_locale.py` 加一個觸發函式(`ready_api(w)` 後 `w.fakes.remote_ollama.list_local_models.raises(code, ...)`、送試算),在 `API_ERRORS` 加這三個代碼各一列,否則 `test_錯誤代碼清單涵蓋本系統的每一個錯誤代碼` 會因為 `MESSAGES` 多三個 key 而變紅;不改那三列以外的斷言),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T033a)
  - 🧪 `testplan.md` § US1-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003、假設;`research.md` § R2;`plan.md` § Structure Decision
- [X] T034a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-18 的測試(佇列有下載中的 `qwen2.5:0.5b`,`list_local_models.raises(code)` 依序換三個代碼,各加入一次 `["qwen2.5", "qwen2.5:7b"]`,最後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-18`(`plan.md` § 待決問題 Q7));加入下載也走 `_checked`(T018b),T033b 在那裡把讀模型清單的 `AdapterError` 轉成 502、504,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「接 `AdapterError` 的那段拿掉,讓它往上拋、回 500」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003、假設;`research.md` § R2
- [X] T034b [US1] 🟢 /tdd 綠燈:US1-API-18 由 T018b、T033b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-18 通過的程式碼(依賴 T034a、T033b)
  - 🧪 `testplan.md` § US1-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003、假設;`research.md` § R2
- [X] T035a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-19 的測試(`set_library` 不認得 `qwen2.5:999b`,試算與加入 `["qwen2.5", "qwen2.5:latest", "qwen2.5:999b"]` 各一次,之後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-19`(`plan.md` § 待決問題 Q7));T022b 合併後才取 manifest,`qwen2.5:latest` 只取一次;002 已讓取 manifest 遇到第一個失敗就停、整批不寫入,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「合併只在寫入佇列前做,取 manifest 時 `qwen2.5:latest` 取了兩次」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-002、NFR-001;`research.md` § R1、R2
- [X] T035b [US1] 🟢 /tdd 綠燈:US1-API-19 由 T022b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-19 通過的程式碼(依賴 T035a、T022b)
  - 🧪 `testplan.md` § US1-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-002、NFR-001;`research.md` § R1、R2
- [X] T036a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-20 的測試(剩餘磁碟 5,000,000,000,試算 `["qwen2.5", "qwen2.5:latest"]`;對照組加入 `["qwen2.5:latest", "qwen2.5:7b"]`;再加入 `["qwen2.5", "qwen2.5:latest"]`,之後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-20`(`plan.md` § 待決問題 Q7));T022b 合併後才算總大小,同一個模型只算一次,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「合併前就算總大小,同一個模型算兩次」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-002;`research.md` § R1
- [X] T036b [US1] 🟢 /tdd 綠燈:US1-API-20 由 T022b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-20 通過的程式碼(依賴 T036a、T022b)
  - 🧪 `testplan.md` § US1-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-002;`research.md` § R1
- [X] T037a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-21 的測試(執行環境上已有 `qwen2.5:latest`、`probe_resources` 丟 `COLAB_UNREACHABLE`,試算 `["qwen2.5"]`;對照組試算 `["qwen2.5:7b"]`;分隔註解寫 `# ---- 003 US1-API-21`(`plan.md` § 待決問題 Q7));T017b 讓試算先走 `_checked`,在 `_sized`、`_estimate`(讀剩餘磁碟)之前;讀剩餘磁碟失敗回 503 `DISK_SPACE_UNKNOWN` 是既有的 `_estimate`,這個案例會被滿足:先執行確認通過,再暫時把 `DownloadsService.estimate` 改成「試算的重複檢查放在讀剩餘磁碟之後」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003;`research.md` § R2
- [X] T037b [US1] 🟢 /tdd 綠燈:US1-API-21 由 T017b 與既有的 `_estimate` 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-21 通過的程式碼(依賴 T037a)
  - 🧪 `testplan.md` § US1-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003;`research.md` § R2
- [X] T038a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US1-API-22 的測試(`live_servers` 起好、已訂閱 `GET /api/events`;背景送請求 2 加入 `["llama3.2", "qwen2.5:latest"]`,等它停在 `llama3.2` 的 manifest 後送請求 1 加入 `["qwen2.5"]`,再放行請求 2;分隔註解寫 `# ---- 003 US1-API-22`(`plan.md` § 待決問題 Q7));同一個任務讓 `tests/fakes/adapters.py` 的 `FakeMethod.invoke` 在結果是 awaitable(`inspect.isawaitable`)時再 `await` 一次(research.md R4),同步的 `returns`、`raises`、`side_effect`、`then`、`gate` 行為不變,`get_manifest` 的 async `side_effect` 才寫得出來;閘門用 `threading.Event` 輪詢,執行確認它因為「沒接 `sqlite3.IntegrityError`,請求 2 撞 `pending_model` 的唯一限制回 500」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003、SC-001;`research.md` § R2、R4;`plan.md` § 待決問題 Q19
- [X] T038b [US1] 🟢 /tdd 綠燈:在 `src/cgb/repos/downloads.py`、`src/cgb/services/downloads.py` 只寫讓 US1-API-22 通過的程式碼(`DownloadsRepo` 加整批寫入的方法,包一個 SQLite 交易(連線是 `isolation_level=None`,明寫 `BEGIN`、全部寫完 `COMMIT`、任何一筆失敗 `ROLLBACK`,交易裡沒有 `await`);`enqueue` 改用它,撞到 `sqlite3.IntegrityError` 回 409 `DOWNLOAD_ALREADY_QUEUED`、`model` 為那一筆;`download.updated` 在提交之後才推;`enqueue_restore` 照舊用單筆的 `repo.enqueue`,不用 `INSERT OR IGNORE`),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T038a)
  - 🧪 `testplan.md` § US1-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § FR-001、NFR-003、SC-001;`research.md` § R2;`plan.md` § 待決問題 Q19
- [X] T039a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-23 的測試(`qwen2.5:latest` 排隊中,試算、加入 `["qwen2.5:0.5b", "qwen2.5:7b", "qwen2.5"]` 各一次;再讓執行環境上有 `qwen2.5:latest`,同一批試算、加入各一次;分隔註解寫 `# ---- 003 US1-API-23`(`plan.md` § 待決問題 Q7));`_checked` 在 `_sized` 取 manifest 之前比對已下載(T017b)與佇列(T019b),試算與加入下載都走它(T018b),這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 改成「把重複檢查移進 `_sized` 取 manifest 的迴圈裡,每個模型先取 manifest 再比對」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § NFR-001、FR-001;`research.md` § R2
- [X] T039b [US1] 🟢 /tdd 綠燈:US1-API-23 由 T017b~T019b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-23 通過的程式碼(依賴 T039a、T019b)
  - 🧪 `testplan.md` § US1-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § NFR-001、FR-001;`research.md` § R2
- [X] T040a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-24 的測試(`pytest.mark.parametrize` 展開名稱(`qwen2.5`、`qwen2.5:latest`)× 情況(已下載、排隊中、下載中、同一批)× 操作(試算、加入)共 16 組,每組送一次後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-API-24`(`plan.md` § 待決問題 Q7));四種情況分別由 T017b(已下載)、T019b(排隊中、下載中)、T022b(同一批)做到,試算與加入下載都走 `_checked`(T018b),這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「比對佇列時用原樣的名稱(只補了使用者輸入那一側的一部分)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § NFR-003、SC-001、FR-001、FR-002;`research.md` § R1、R2
- [X] T040b [US1] 🟢 /tdd 綠燈:US1-API-24 由 T017b~T019b、T022b 滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US1-API-24 通過的程式碼(依賴 T040a、T022b)
  - 🧪 `testplan.md` § US1-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § NFR-003、SC-001、FR-001、FR-002;`research.md` § R1、R2
- [X] T041a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US1-API-25 的測試(`list_local_models.raises(code, "ConnectError: … 127.0.0.1:41234 … Traceback …")` 依序換三個代碼,各試算一次、加入一次 `["qwen2.5"]`(共 6 次);分隔註解寫 `# ---- 003 US1-API-25`(`plan.md` § 待決問題 Q7));T033b 讓 `_checked` 以 `ApiError(...).body()` 回 `code` 與 `MESSAGES[code]`,不帶 `AdapterError.message`,試算與加入下載共用同一段,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「把 `AdapterError.message` 放進回應的 `message`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § NFR-003;`research.md` § R2
- [X] T041b [US1] 🟢 /tdd 綠燈:US1-API-25 由 T033b 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-25 通過的程式碼(依賴 T041a、T033b)
  - 🧪 `testplan.md` § US1-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`)
  - 📎 `spec.md` § NFR-003;`research.md` § R2
- [X] T042 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T017b~T041b 記下的重構清單(範圍限 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py`、`src/cgb/domain/`、`src/cgb/api/curated.py`);清單之外另做一項:`src/cgb/api/curated.py` 的 `normalized()` 改成呼叫 `src/cgb/domain/model_name.py` 的 `with_version()`,行為不變(research.md R1、`plan.md` § Project Structure;呼叫端只有同檔的 `_input`;`plan.md` § 待決問題 Q26),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_api_downloads.py`、`tests/integration/test_api_curated.py`、`tests/e2e/test_locale.py` 的斷言(依賴 T041b)
  - 🧪 `testplan.md` § US1-API-01~US1-API-25
  - 📎 `testplan.md` § 2.2

### 跨端點驗收(`tests/integration/test_downloads_cross.py`)

> 端點節(E7、E2)都完成、驗收過後由主 agent 開始;真的 E2(api、services、domain、repos 與 SQLite)接真的 `RemoteOllama`,遠端 Ollama 的 HTTP 換成 `httpx.MockTransport`(`/api/version` 一律回 200 `{"version":"0.40.15"}` 讓工作階段開到就緒),其他轉接層用替身;照 `tests/integration/test_library_cross.py` 的寫法以 `make_app(remote_ollama=RemoteOllama(transport=...))` 注入。測試檔 `tests/integration/test_downloads_cross.py` 是新檔(`plan.md` § 待決問題 Q25)

- [ ] T043a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_downloads_cross.py` 寫 US1-AJ-01 的測試(MockTransport 對 `/api/tags` 依情況丟 `ConnectError`、`ReadTimeout`,回 500、200 的 HTML、缺 `size` 的清單,五種情況各試算一次 `["qwen2.5:7b"]`;分隔註解寫 `# ---- 003 US1-AJ-01`(`plan.md` § 待決問題 Q7));T005b、T007b、T009b、T011b、T014b 讓真的 `RemoteOllama._get_list` 把這五種失敗歸成 `AdapterError`,T033b 讓試算轉成 502、504,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/adapters/remote_ollama.py` 的 `_get_list` 改成「只在服務接 `AdapterError`、轉接層照舊 `return response.json()` 不接任何例外」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`);`contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001、NFR-003;`research.md` § R2
- [ ] T043b [US1] 🟢 /tdd 綠燈:US1-AJ-01 由 T005b、T007b、T009b、T011b、T014b、T033b 滿足,確認 `src/cgb/adapters/remote_ollama.py`、`src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py`、`src/cgb/services/downloads.py` 只寫讓 US1-AJ-01 通過的程式碼(依賴 T043a)
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`);`contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001、NFR-003;`research.md` § R2
- [ ] T044a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_downloads_cross.py` 寫 US1-AJ-02 的測試(同 US1-AJ-01 的五種情況,各加入一次 `["qwen2.5:7b", "llama3.2"]`,每次之後 `GET /api/downloads`;分隔註解寫 `# ---- 003 US1-AJ-02`(`plan.md` § 待決問題 Q7));同 US1-AJ-01,加入下載也走 `_checked`(T018b),這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/adapters/remote_ollama.py` 的 `_get_list` 改成「轉接層照舊不接例外,`list_local_models` 的原生例外變 500」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`);`contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001、NFR-003;`research.md` § R2
- [ ] T044b [US1] 🟢 /tdd 綠燈:US1-AJ-02 由 T005b、T007b、T009b、T011b、T014b、T018b、T033b 滿足,確認 `src/cgb/adapters/remote_ollama.py`、`src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py`、`src/cgb/services/downloads.py` 只寫讓 US1-AJ-02 通過的程式碼(依賴 T044a)
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`);`contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001、NFR-003;`research.md` § R2
- [ ] T045a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_downloads_cross.py` 寫 US1-AJ-03 的測試(MockTransport 對 `/api/tags` 回桌機 Ollama 形狀的 `qwen2.5:latest`,試算、加入 `["qwen2.5"]` 各一次;分隔註解寫 `# ---- 003 US1-AJ-03`(`plan.md` § 待決問題 Q7));真的 `RemoteOllama` 原樣交回 `name`(T001a 對照過),`_checked` 以 `name` 比對補過版本的名稱(T017b、T018b),這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「比對前把清單那一側的 `name` 去掉 `:latest`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`);`contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001、NFR-001;`research.md` § R1
- [ ] T045b [US1] 🟢 /tdd 綠燈:US1-AJ-03 由 T017b、T018b 滿足,確認 `src/cgb/adapters/remote_ollama.py`、`src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py`、`src/cgb/services/downloads.py` 只寫讓 US1-AJ-03 通過的程式碼(依賴 T045a)
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`);`contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-001、NFR-001;`research.md` § R1
- [ ] T046a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_downloads_cross.py` 寫 US1-AJ-04 的測試(MockTransport 對 `/api/tags` 丟 `ConnectError("cgb-test-底層細節 127.0.0.1:11435")`,試算 `["qwen2.5:7b"]`;分隔註解寫 `# ---- 003 US1-AJ-04`(`plan.md` § 待決問題 Q7));T007b 把 `ConnectError` 歸成 `OLLAMA_UNREACHABLE`,T033b 的回應只有 `code` 與固定的 `MESSAGES[code]`,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_checked` 改成「把 `str(原例外)` 接進 `message`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US1-AJ-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`);`contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003;`research.md` § R2
- [ ] T046b [US1] 🟢 /tdd 綠燈:US1-AJ-04 由 T007b、T033b 滿足,確認 `src/cgb/adapters/remote_ollama.py`、`src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py`、`src/cgb/services/downloads.py` 只寫讓 US1-AJ-04 通過的程式碼(依賴 T046a)
  - 🧪 `testplan.md` § US1-AJ-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-ollama-error-message`);`contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003;`research.md` § R2
- [ ] T047 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T043b~T046b 記下的重構清單(範圍限 `src/cgb/adapters/remote_ollama.py`、`src/cgb/services/downloads.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_downloads_cross.py` 的斷言(依賴 T046b)
  - 🧪 `testplan.md` § US1-AJ-01~US1-AJ-04
  - 📎 `testplan.md` § 2.3

### 介面覆蓋(US1)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `remote-ollama.openapi.yaml` § `paths./api/tags.get`、`components.schemas.TagsResponse`、`components.schemas.Error`(失敗歸類、形狀檢查、逾時) | T001b~T015b、T043b~T046b | T001a~T015a、T043a~T046a |
| `ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadEstimate`(補版本後比對、同一批合併、檢查先後、502/504) | T017b、T019b、T022b、T028b~T033b、T035b~T037b、T039b~T041b、T043b、T045b、T046b | T017a、T019a、T022a、T028a~T033a、T035a~T037a、T039a~T041a、T043a、T045a、T046a |
| `ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadJobList`(補版本後比對、同一批合併、整批不加入、同時加入) | T018b、T020b、T021b、T023b~T027b、T029b、T031b、T032b、T034b~T036b、T038b~T041b、T044b、T045b | T018a、T020a、T021a、T023a~T027a、T029a、T031a、T032a、T034a~T036a、T038a~T041a、T044a、T045a |
| `ui.openapi.yaml` § `components.schemas.DownloadSelection`、`components.schemas.Error`(409、502、503、504 的 `code`、`message`、`model`) | T017b~T041b、T043b~T046b | T017a~T041a、T043a~T046a |

### 測試案例覆蓋(US1)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US1-RO-01~US1-RO-15 | T001a~T015a | T001b~T015b | T016 |
| US1-API-01~US1-API-25 | T017a~T041a | T017b~T041b | T042 |
| US1-AJ-01~US1-AJ-04 | T043a~T046a | T043b~T046b | T047 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 全綠(含 `tests/e2e/test_locale.py` 加了三個 `OLLAMA_*` 的那三列);重構任務前後的測試結果相同

---

## Phase 3: User Story 2 - 模型目錄打開不用每次等 `colab exec` (Priority: P2)

**Goal**: 同一個工作階段只經 `colab exec` 成功讀一次顯示記憶體總量,之後打開模型目錄、推送 `models.updated` 與預先載入都沿用;讀不到或讀到 null 時回 200 與 null、不快取;換了工作階段重讀,重連接回沿用

**Independent Test**: 照 `testplan.md` § 3 的全部案例:E7 以 `uv run pytest tests/integration/test_remote_ollama.py`(`httpx.MockTransport`)、E2 以 `uv run pytest tests/integration/test_api_models.py`(`FakeColabControl` 的 async `side_effect`、`live_servers`)執行全綠

### E7 遠端 Ollama(Colab 執行環境上,Ollama API)

> 這一節只呼叫 `list_loaded_models`(`GET /api/ps`);它和 `list_local_models` 共用 `_get_list`,故事 1 的 T005b~T014b 已做出同一套歸類,所以除了形狀檢查的邊界,每個案例都是對照組。E7 與 E2 兩節平行,沒有共用的檔

- [ ] T048a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US2-RO-01 的測試(handler 對 `/api/ps` 依情況回完整的一筆、空陣列、只有 `name` 的一筆,各呼叫一次 `list_loaded_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US2-RO-01`(`plan.md` § 待決問題 Q7));`list_loaded_models` 走同一個 `_get_list`:T012b、T013b 的形狀檢查接受空陣列與只有 `name` 的那筆,T014b 的 `size` 檢查只套在 `/api/tags`,逾時沿用 `LIST_TIMEOUT` 的 10 秒,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 的形狀檢查 改成「`size` 的檢查也套到 `/api/ps`,只有 `name` 的那筆被歸成 `OLLAMA_BAD_RESPONSE`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-RO-01
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`plan.md` § 待決問題 Q2、Q3、Q10
- [ ] T048b [US2] 🟢 /tdd 綠燈:US2-RO-01 由 T012b~T014b 與既有的 `LIST_TIMEOUT` 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US2-RO-01 通過的程式碼(依賴 T048a、T014b)
  - 🧪 `testplan.md` § US2-RO-01
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`plan.md` § 待決問題 Q2、Q3、Q10
- [ ] T049a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US2-RO-02 的測試(handler 依情況丟 `ConnectTimeout`、`ReadTimeout`,各呼叫一次 `list_loaded_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US2-RO-02`(`plan.md` § 待決問題 Q7));T005b 在共用的 `_get_list` 把逾時歸成 `OLLAMA_TIMEOUT`,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 改成「先寫 `except httpx.TransportError` 再寫 `except httpx.TimeoutException`,逾時被前者攔下歸成 `OLLAMA_UNREACHABLE`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-RO-02
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`research.md` § R2
- [ ] T049b [US2] 🟢 /tdd 綠燈:US2-RO-02 由 T005b 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US2-RO-02 通過的程式碼(依賴 T049a、T005b)
  - 🧪 `testplan.md` § US2-RO-02
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`research.md` § R2
- [ ] T050a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US2-RO-03 的測試(handler 依情況丟 `ConnectError`、`RemoteProtocolError`、`ReadError`,各呼叫一次 `list_loaded_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US2-RO-03`(`plan.md` § 待決問題 Q7));T007b 在共用的 `_get_list` 把其他傳輸層失敗歸成 `OLLAMA_UNREACHABLE`,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 改成「只接 `httpx.ConnectError` 與 `httpx.NetworkError`,`RemoteProtocolError` 原樣往上拋」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-RO-03
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`research.md` § R2
- [ ] T050b [US2] 🟢 /tdd 綠燈:US2-RO-03 由 T007b 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US2-RO-03 通過的程式碼(依賴 T050a、T007b)
  - 🧪 `testplan.md` § US2-RO-03
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`research.md` § R2
- [ ] T051a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US2-RO-04 的測試(handler 對 `/api/ps` 依情況回 500 帶 `{"models":[]}`、404 純文字、302 導到 `/api/ps-moved`,各呼叫一次 `list_loaded_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US2-RO-04`(`plan.md` § 待決問題 Q7));T009b 在共用的 `_get_list` 把非 200 歸成 `OLLAMA_BAD_RESPONSE`,`_client` 不跟著導向,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 改成「不看狀態碼就解析本文,500 帶的 `{"models":[]}` 被當成沒有已載入的模型照常回傳」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-RO-04
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`research.md` § R2
- [ ] T051b [US2] 🟢 /tdd 綠燈:US2-RO-04 由 T009b 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US2-RO-04 通過的程式碼(依賴 T051a、T009b)
  - 🧪 `testplan.md` § US2-RO-04
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`research.md` § R2
- [ ] T052a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US2-RO-05 的測試(handler 對 `/api/ps` 依情況回 200 的 HTML、宣稱 gzip 卻沒壓縮的本文(照 `testplan.md` § 2.1 以 `stream=httpx.ByteStream(...)` 建),各呼叫一次 `list_loaded_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US2-RO-05`(`plan.md` § 待決問題 Q7));T011b 在共用的 `_get_list` 把非 JSON 與解壓失敗歸成 `OLLAMA_BAD_RESPONSE`,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 改成「`response.json()` 沒有接 `ValueError`,`json.JSONDecodeError` 原樣往上拋」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-RO-05
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`research.md` § R2;`plan.md` § 待決問題 Q1
- [ ] T052b [US2] 🟢 /tdd 綠燈:US2-RO-05 由 T011b 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US2-RO-05 通過的程式碼(依賴 T052a、T011b)
  - 🧪 `testplan.md` § US2-RO-05
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`research.md` § R2;`plan.md` § 待決問題 Q1
- [ ] T053a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US2-RO-06 的測試(handler 對 `/api/ps` 依情況回 `[]`、`{}`、`{"models":{}}`、字串陣列、沒有 `name`、`name` 是 7,各呼叫一次 `list_loaded_models(base_url="http://127.0.0.1:11435")`;分隔註解寫 `# ---- 003 US2-RO-06`(`plan.md` § 待決問題 Q7));T012b、T013b 在共用的 `_get_list` 檢查最上層與每一筆的形狀,這個案例會被滿足:先執行確認通過,再暫時把 `_get_list` 改成「只檢查 `models` 是陣列,沒有逐筆檢查是物件、有字串的 `name`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-RO-06
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`plan.md` § 待決問題 Q2
- [ ] T053b [US2] 🟢 /tdd 綠燈:US2-RO-06 由 T012b、T013b 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US2-RO-06 通過的程式碼(依賴 T053a、T013b)
  - 🧪 `testplan.md` § US2-RO-06
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`plan.md` § 待決問題 Q2
- [ ] T054 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T048b~T053b 記下的重構清單(範圍限 `src/cgb/adapters/remote_ollama.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_remote_ollama.py` 的斷言(依賴 T053b)
  - 🧪 `testplan.md` § US2-RO-01~US2-RO-06
  - 📎 `testplan.md` § 3.1

### E2 後端 UI API(FastAPI REST 與 SSE)

> 「讀顯示記憶體」就是 `fakes.colab.probe_resources`,次數一律在 `open_ready` 之後 `reset_calls()` 再數;要延遲的案例用 async 的 `side_effect`(`await asyncio.sleep(0.3)`),依賴 T038a 讓 `FakeMethod.invoke` 接受 awaitable(`tests/fakes/adapters.py`,同一個檔,這一節排在故事 1 的 E2 節之後)。快取只放在 `Catalog._vram_total()` 一處(research.md R3)

- [ ] T055a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_models.py` 寫 US2-API-01 的測試(顯示記憶體 16,106,127,360,連續送 3 次 `GET /api/models`;分隔註解寫 `# ---- 003 US2-API-01`(`plan.md` § 待決問題 Q7)),執行確認它因為「`Catalog._vram_total()` 照舊每次都呼叫 `probe_resources`,3 次跑了 3 次 `colab exec`」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R3
- [ ] T055b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/catalog.py`、`tests/integration/test_api_models.py` 只寫讓 US2-API-01 通過的程式碼(`_vram_total()` 讀到後記在 `Catalog` 物件裡、之後沿用;這一步就會讓 001 的 `test_大小超過顯示記憶體總量才標可能無法載入_讀不到時是_null`(同一個工作階段先讀到數字、再讓替身回 null)變紅,同一個任務改寫 `tests/integration/test_api_models.py` 的這個函式:刪掉第二次請求與它的斷言,只留第一次讀到數字的那一半;讀不到的那一半由 T061a 原地改寫成第一次就讀到 null,不留 skip),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T055a)
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R3、R4;`plan.md` § 待決問題 Q18、Q23
- [ ] T056a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_models.py` 寫 US2-API-02 的測試(送過 1 次 `GET /api/models` 後改 `set_tags` 加 `cgb-test-big:70b`、`set_loaded` `QWEN_7B`,再送 1 次;分隔註解寫 `# ---- 003 US2-API-02`(`plan.md` § 待決問題 Q7));T055b 只快取顯示記憶體總量,模型清單與已載入每次照讀,`mayNotFit` 用快取的值重算,這個案例會被滿足:先執行確認通過,再暫時把 `Catalog` 改成「把整份 `list()` 的結果(模型清單、已載入、顯示記憶體)快取起來」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R3
- [ ] T056b [US2] 🟢 /tdd 綠燈:US2-API-02 由 T055b 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US2-API-02 通過的程式碼(依賴 T056a)
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R3
- [ ] T057a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_models.py` 寫 US2-API-03 的測試(用 `live_servers` 開到就緒,送過 1 次 `GET /api/models` 後 `reset_calls()`;送 `POST /api/models/preload`,等到 `QWEN_7B` 已載入的 `models.updated`;分隔註解寫 `# ---- 003 US2-API-03`(`plan.md` § 待決問題 Q7));`Catalog.preload()` 確認目錄與 `Catalog.publish()` 推送都經 `list()` → `_vram_total()`,T055b 的快取就在那一處,這個案例會被滿足:先執行確認通過,再暫時把 快取 改成「只做在 `src/cgb/api/models.py` 的 `GET /api/models` 路由裡,`_vram_total()` 照舊每次讀」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R3;`plan.md` § 待決問題 Q14
- [ ] T057b [US2] 🟢 /tdd 綠燈:US2-API-03 由 T055b 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US2-API-03 通過的程式碼(依賴 T057a)
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003;`research.md` § R3;`plan.md` § 待決問題 Q14
- [ ] T058a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_models.py` 寫 US2-API-04 的測試(T4 讀到 16,106,127,360 後送 `POST /api/session/restart` 換成 L4,等到新的工作階段就緒,`reset_calls()` 後送 `GET /api/models`;分隔註解寫 `# ---- 003 US2-API-04`(`plan.md` § 待決問題 Q7)),執行確認它因為「快取只記值、不記工作階段名稱,變更類型後沿用 T4 的 16,106,127,360」這類實作而失敗;若一執行就通過(T055b 已經以工作階段名稱比對),就改做對照組:暫時把 `_vram_total()` 改成不比對工作階段名稱、有值就沿用,執行確認斷言失敗後撤回,T058b 改成確認不需要為這個案例改程式碼(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R3
- [ ] T058b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/catalog.py` 只寫讓 US2-API-04 通過的程式碼(快取存 `(工作階段名稱, 顯示記憶體總量)` 一組,`lifecycle.current()["name"]` 不同就重讀並覆蓋;不掛 `end_listeners`、`ready_listeners`),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T058a)
  - 🧪 `testplan.md` § US2-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005;`research.md` § R3
- [ ] T059a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_models.py` 寫 US2-API-05 的測試(讀過舊工作階段的值後結束、開新的工作階段,新工作階段第一次 `probe_resources` 丟 `COLAB_TIMEOUT`,送 2 次 `GET /api/models`;分隔註解寫 `# ---- 003 US2-API-05`(`plan.md` § 待決問題 Q7)),執行確認它因為「`_vram_total()` 沒有接 `AdapterError`,`COLAB_TIMEOUT` 往上拋成 500(現況)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、FR-004;`research.md` § R3
- [ ] T059b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/catalog.py` 只寫讓 US2-API-05 通過的程式碼(`_vram_total()` 接 `AdapterError`(不分代碼)回 None、不寫入快取,不拿上一個工作階段的值頂替;不另外寫日誌(分身決策紀錄 D7)),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T059a)
  - 🧪 `testplan.md` § US2-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、FR-004;`research.md` § R3
- [ ] T060a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_models.py` 寫 US2-API-06 的測試(讀過一次後讓健康檢查進入重連中,重連中送 `GET /api/models`;放行 `open_tunnel` 接回後再送一次;分隔註解寫 `# ---- 003 US2-API-06`(`plan.md` § 待決問題 Q7));`list()` 先 `require_ready_base_url()`(重連中回 503),重連接回沿用同一個工作階段名稱(`HealthMonitor._reconnect`),T058b 以名稱比對沿用,這個案例會被滿足:先執行確認通過,再暫時把 `Catalog` 改成「在 `lifecycle.ready_listeners` 掛清快取,重連接回也觸發清除」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、使用者故事 2 驗收情境 6;`research.md` § R3
- [ ] T060b [US2] 🟢 /tdd 綠燈:US2-API-06 由 T058b 與既有的 `Catalog.list()` 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US2-API-06 通過的程式碼(依賴 T060a、T058b)
  - 🧪 `testplan.md` § US2-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-005、使用者故事 2 驗收情境 6;`research.md` § R3
- [ ] T061a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_models.py` 寫 US2-API-07 的測試(`probe_resources` 第一次回 `vram_total=None`、之後回 16,106,127,360,連續送 3 次 `GET /api/models`;分隔註解寫 `# ---- 003 US2-API-07`(`plan.md` § 待決問題 Q7));原地改寫 T055b 留下的 `test_大小超過顯示記憶體總量才標可能無法載入_讀不到時是_null`,讀不到的那一半改成這個工作階段第一次就讀到 null(`plan.md` § 待決問題 Q18),執行確認它因為「把 `colab exec` 成功當成讀成功,快取了 null,之後一直是 null、不再讀」這類實作而失敗;若一執行就通過(T055b、T058b 已經只快取數字),就改做對照組:暫時把 `_vram_total()` 讀到 null 也寫入快取,執行確認斷言失敗後撤回,T061b 改成確認不需要為這個案例改程式碼(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、FR-003、邊界情況、SC-003;`research.md` § R3;`plan.md` § 待決問題 Q18
- [ ] T061b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/catalog.py` 只寫讓 US2-API-07 通過的程式碼(讀到的 `vramTotalBytes` 是整數才寫入快取;是 null 就回 null、不寫入,下一次再讀),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T061a)
  - 🧪 `testplan.md` § US2-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004、FR-003、邊界情況、SC-003;`research.md` § R3
- [ ] T062a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_models.py` 寫 US2-API-08 的測試(照 `test_api_recovery.py` 的寫法,第一個 app 讀過一次後關掉,以同一個 SQLite 檔與替身建第二個 app、接回同一個工作階段,`reset_calls()` 後送 `GET /api/models`;分隔註解寫 `# ---- 003 US2-API-08`(`plan.md` § 待決問題 Q7));T055b 的快取是 `Catalog` 物件的屬性,`make_app()` 建新的 app 時 `Catalog` 是新的、快取是空的,這個案例會被滿足:先執行確認通過,再暫時把 快取 改成「改放在 `src/cgb/services/catalog.py` 的模組層級全域變數(或寫進 SQLite)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003、邊界情況;`research.md` § R3
- [ ] T062b [US2] 🟢 /tdd 綠燈:US2-API-08 由 T055b 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US2-API-08 通過的程式碼(依賴 T062a)
  - 🧪 `testplan.md` § US2-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003、邊界情況;`research.md` § R3
- [ ] T063a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_models.py` 寫 US2-API-09 的測試(第一次試算 `probe_resources` 回 `vram_total=8_000_000_000`,之後送 `GET /api/models`,再改剩餘磁碟後試算一次;分隔註解寫 `# ---- 003 US2-API-09`(`plan.md` § 待決問題 Q7));快取只由 `_vram_total()` 寫入(T055b),試算的 `DownloadsService._estimate` 照讀 `probe_resources`、不碰它,這個案例會被滿足:先執行確認通過,再暫時把 `src/cgb/services/downloads.py` 的 `_estimate` 改成「試算讀剩餘空間時順手把回傳的 `vramTotalBytes` 寫進 `Catalog` 的快取」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`;`contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadEstimate`
  - 📎 `spec.md` § FR-003;`research.md` § R3
- [ ] T063b [US2] 🟢 /tdd 綠燈:US2-API-09 由 T055b 與既有的 `_estimate` 滿足,確認 `src/cgb/services/catalog.py`、`src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py`、`src/cgb/services/downloads.py` 只寫讓 US2-API-09 通過的程式碼(依賴 T063a)
  - 🧪 `testplan.md` § US2-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`;`contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadEstimate`
  - 📎 `spec.md` § FR-003;`research.md` § R3
- [ ] T064a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_models.py` 寫 US2-API-10 的測試(`probe_resources` 的 async `side_effect` 延遲 0.3 秒,以 `asyncio.gather` 同時送 2 次 `GET /api/models`,都回來後再送第 3 次;分隔註解寫 `# ---- 003 US2-API-10`(`plan.md` § 待決問題 Q7));async `side_effect` 依賴 T038a;T055b 的快取沒有「正在讀」的旗標,兩個同時的第一次各自讀到數字,之後沿用,這個案例會被滿足:先執行確認通過,再暫時把 `Catalog._vram_total()` 改成「用「正在讀」旗標擋第二個請求,讓它直接回 `vramBytes: null`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003、假設;`research.md` § R3、R4;`plan.md` § 待決問題 Q17
- [ ] T064b [US2] 🟢 /tdd 綠燈:US2-API-10 由 T055b 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US2-API-10 通過的程式碼(依賴 T064a、T038a)
  - 🧪 `testplan.md` § US2-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-003、假設;`research.md` § R3、R4;`plan.md` § 待決問題 Q17
- [ ] T065a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_models.py` 寫 US2-API-11 的測試(`pytest.mark.parametrize` 對 `probeResources` 的 8 個代碼(含 `AUTH_REQUIRED`)各跑一次:第一次丟那個代碼、之後回 16,106,127,360,連續送 3 次 `GET /api/models`;分隔註解寫 `# ---- 003 US2-API-11`(`plan.md` § 待決問題 Q7));T059b 讓 `_vram_total()` 接住所有 `AdapterError`(不分代碼)回 null、不寫入,這個案例會被滿足:先執行確認通過,再暫時把 `Catalog._vram_total()` 改成「沒有接 `AdapterError`,例外往上拋成 500」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-003、FR-004、SC-003;`research.md` § R3;`plan.md` § 待決問題 Q15
- [ ] T065b [US2] 🟢 /tdd 綠燈:US2-API-11 由 T059b 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US2-API-11 通過的程式碼(依賴 T065a、T059b)
  - 🧪 `testplan.md` § US2-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-003、FR-004、SC-003;`research.md` § R3;`plan.md` § 待決問題 Q15
- [ ] T066a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_models.py` 寫 US2-API-12 的測試(`probe_resources` 的 async `side_effect` 延遲 0.3 秒,連續送 10 次 `GET /api/models`,每次以 `time.monotonic()` 量耗時;分隔註解寫 `# ---- 003 US2-API-12`(`plan.md` § 待決問題 Q7));async `side_effect` 依賴 T038a;T055b 讀到之後沿用,第 2 次起不再 `await` `probe_resources`,這個案例會被滿足:先執行確認通過,再暫時把 `Catalog._vram_total()` 改成「沒有快取,每次都等 0.3 秒的 `colab exec`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q24)
  - 🧪 `testplan.md` § US2-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、SC-002、FR-003;`research.md` § R3、R4;`plan.md` § 待決問題 Q9、Q16
- [ ] T066b [US2] 🟢 /tdd 綠燈:US2-API-12 由 T055b 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US2-API-12 通過的程式碼(依賴 T066a、T038a)
  - 🧪 `testplan.md` § US2-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、SC-002、FR-003;`research.md` § R3、R4;`plan.md` § 待決問題 Q9、Q16
- [ ] T067 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T055b~T066b 記下的重構清單(範圍限 `src/cgb/services/catalog.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_api_models.py` 的斷言(依賴 T066b)
  - 🧪 `testplan.md` § US2-API-01~US2-API-12
  - 📎 `testplan.md` § 3.2

### 跨端點驗收

本故事沒有要接真的 `RemoteOllama` 才看得到的行為(`testplan.md` § 3.3),這一節沒有任務。

### 介面覆蓋(US2)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `remote-ollama.openapi.yaml` § `paths./api/ps.get`、`components.schemas.PsResponse`(失敗歸類、形狀檢查、逾時) | T048b~T053b | T048a~T053a |
| `ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`(`vramBytes` 的讀取時機、沿用、失效與讀不到時的 null) | T055b~T066b | T055a~T066a |
| `ui.openapi.yaml` § `paths./downloads/estimate.post`(試算不寫入模型目錄的快取) | T063b | T063a |

### 測試案例覆蓋(US2)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US2-RO-01~US2-RO-06 | T048a~T053a | T048b~T053b | T054 |
| US2-API-01~US2-API-12 | T055a~T066a | T055b~T066b | T067 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 全綠(含 T055b 改寫、T061a 原地改寫的 `test_大小超過顯示記憶體總量才標可能無法載入_讀不到時是_null`);重構任務前後的測試結果相同

---

## Phase 4: 全域測試區

**Purpose**: 照 `testplan.md` § 4.2 驗證替身與真 Ollama 一致(G-01)與打開模型目錄的回應時間(G-02);兩個案例的「副作用與護欄」都寫 `時機:節內`,放在這一節;NFR-003、SC-001、SC-003 由故事裡的案例涵蓋(`testplan.md` § 4.1)

- [ ] T068 [G] 📏 量測:在桌機撰寫並執行 `tests/integration/test_003_g_01.py`(標 `@pytest.mark.realrun`,預設排除;不放 `tests/realrun/`,不經會執行 `colab usage` 的 `tests/realrun` fixture),照 G-01 在檔內寫一個 fixture 起臨時的 `ollama serve`(`/usr/local/bin/ollama`,2026-11-13 為 0.32.15):port 由 `tests/realrun/helpers.py` 的 `free_loopback_port()` 取(127.0.0.1,不會是 11434~11436、8780),環境變數只給 `PATH`、`HOME=<tmp_path>/home`、`OLLAMA_MODELS=<tmp_path>/models`(空的資料夾)與 `OLLAMA_HOST=127.0.0.1:<port>`,以 `subprocess.Popen(..., start_new_session=True)` 起在自己的行程群組,等到 `GET /api/version` 回 200(最多 30 秒,沒等到就收掉行程並讓測試失敗);以 `RemoteOllama(transport=RecordingTransport(get_only=True))`(`tests/realrun/helpers.py`,錄下每次往返)對 base_url `http://127.0.0.1:<臨時 serve 的 port>` 依序呼叫 `list_local_models`、`list_loaded_models` 各一次,再以 `free_loopback_port()` 另取一個沒有在聽的 port 呼叫 `list_local_models` 一次;fixture 收尾(`yield` 之後、包在 `finally` 裡)對行程群組送 SIGTERM,10 秒內沒結束就 SIGKILL,再驗證 `Popen.poll()` 不是 None、`os.killpg(pgid, 0)` 丟 `ProcessLookupError`;記下錄到的 `/api/tags`、`/api/ps` 的狀態碼、本文最上層是不是物件且 `models` 是陣列、原始筆數與回傳筆數、沒有在聽的 port 丟出的 `code`、收尾後行程與行程群組是否都已結束,和門檻(兩個都是 200 且形狀相符、兩組筆數各自相等、`OLLAMA_UNREACHABLE`、都已結束)比較,以 `uv run pytest -m realrun tests/integration/test_003_g_01.py` 執行,結果以 `tests/realrun/conftest.py` 的 `write_measurement(..., path=<repo>/specs/003-download-dedup-model-cache/measurements.md)` 寫進 `specs/003-download-dedup-model-cache/measurements.md`,並照實寫出代價:`/api/tags` 是空清單,真實模型名稱是否帶版本與每一筆的欄位名稱驗不到。副作用與護欄:時機:節內;不對 127.0.0.1:11434(使用者自己的 Ollama)送任何請求,001 的實跑護欄 P6 不動(`RecordingTransport` 每個請求都經 `check_port`);臨時 serve 只綁 127.0.0.1,`OLLAMA_MODELS` 與 `HOME` 都在 pytest 暫存資料夾,不讀寫使用者的 `~/.ollama`;只送 `GET`,不 pull、generate、delete;fixture 收尾一定結束行程並驗證行程與行程群組都已結束,不留殭屍;`/usr/local/bin/ollama` 不存在就標無法實跑,不替它安裝;不經 SSH、不執行 `colab`、不花 compute units;錄到的回應只寫 pytest 暫存資料夾;約 10 秒;這是桌機 0.32.15,不是 Colab 上的 0.40.x,Colab 上的仍列未驗證(`plan.md` § 待決問題 Q27)。判定者:腳本;樣本:一次實跑(未用於調整)
  - 🧪 `testplan.md` § G-01
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`、`paths./api/ps.get`、`components.schemas.TagsResponse`、`components.schemas.PsResponse`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-004、NFR-003;`research.md` § R1、R2;`plan.md` § 待決問題 Q27
- [ ] T069 [G] 📏 量測:撰寫並執行 `tests/integration/test_003_g_02.py`(標 `@pytest.mark.realrun`,預設排除;不放 `tests/realrun/`),照 G-02 以測試行程內的 uvicorn 起在 127.0.0.1 隨機 port(`live_servers`,真的 HTTP 連線,不經 `httpx.ASGITransport`),工作階段就緒用替身,`probe_resources` 的 async 替身每次先 `await asyncio.sleep(3)` 再回顯示記憶體 16,106,127,360(依賴 T038a);就緒後 `reset_calls()`,經真的 HTTP 連續送 10 次 `GET /api/models` 並記每次耗時,再送 `POST /api/session/restart {runtimeType:{gpu:"L4",highMem:false}}`,等到就緒後送 1 次 `GET /api/models`;記下 10 次之後的 `call_count`、第 1 次耗時、第 2~10 次每次耗時、10 次的 `vramBytes`、變更類型後那 1 次之後的 `call_count`,和門檻(1 次、≥ 3 秒、每次 < 1 秒、都是 16,106,127,360、2 次)比較,以 `uv run pytest -m realrun tests/integration/test_003_g_02.py` 執行,結果以 `write_measurement(..., path=<repo>/specs/003-download-dedup-model-cache/measurements.md)` 寫進 `specs/003-download-dedup-model-cache/measurements.md`。副作用與護欄:時機:節內;uvicorn 只綁 127.0.0.1 隨機 port;資料庫是 pytest 暫存資料夾的 SQLite;Colab、通道、遠端 Ollama、模型庫都用替身,不執行任何 `colab` 指令、不花 compute units;約 7 秒(`plan.md` § 待決問題 Q9)。判定者:腳本(耗時和 1 秒、3 秒比較);樣本:一次量測(未用於調整)
  - 🧪 `testplan.md` § G-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-002、SC-002、FR-003、FR-005;`research.md` § R3、R4;`plan.md` § 待決問題 Q9

### 測試案例覆蓋(全域)

| testplan 案例 | 任務 |
|---|---|
| G-01 | T068 |
| G-02 | T069 |

**Checkpoint**: 全部測試綠燈;`specs/003-download-dedup-model-cache/measurements.md` 每一項都寫了數字與是否過門檻,沒過的列為待決問題
