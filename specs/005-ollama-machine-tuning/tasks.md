# Tasks: 依機器配置調整遠端 Ollama 的設定,並在 UI 顯示與修改

**Input**: `specs/005-ollama-machine-tuning/` 的設計文件(本 spec package);建立在 `specs/004-chat-hf-curated-queue/` 之上(004 建立在 003、002、001 之上),既有程式在 `src/cgb/`、既有測試在 `tests/`

**Prerequisites**: plan.md、spec.md、research.md、techstack.md、testplan.md、contracts/colab-cli.openapi.yaml、contracts/ui.openapi.yaml、contracts/ui-events.asyncapi.yaml、contracts/store.dbml、prototype/

**Tests**: 依 `testplan.md` 切分。testplan 的每個行為測試案例對應一組 `/tdd` 紅燈與綠燈任務,每個「使用者故事 × 端點」節最後一個 `/tdd` 重構任務;量測與人工驗證的案例對應 📏 任務。

**Organization**: 依 `testplan.md` 的使用者故事分 phase;每個故事底下依 `testplan.md` 的端點分節(E5 Colab CLI、E2 後端 UI API、E4 資料庫),外加一節跨端點驗收,最後是介面覆蓋表與測試案例覆蓋表。Q32 的共用件歸在故事 1、3 的 E5 節最前面,E2 節依賴它們(`plan.md` § 待決問題 Q32、Q55)。E1 前端 UI 照 `testplan.md` § 1 不另立端點節,畫面行為都在各故事的跨端點驗收。全域測試區自成一個 phase,放在所有故事之後。

## Format: `[ID] [Story] [步驟] Description`,底下接 🧪、⚙ 與 📎

- **[Story]**:所屬的使用者故事(US1、US2、US3);全域測試區寫 `[G]`
- **[步驟]**:這個任務是 `/implement` 交給誰做的哪一步
  - 🔴 `/tdd 紅燈`:寫一個測試案例的測試,執行確認它失敗
  - 🟢 `/tdd 綠燈`:只寫讓同一個案例通過的程式碼,執行全部測試確認都通過
  - 🔵 `/tdd 重構`:在全部測試綠燈下,整理這一節綠燈任務記下的重構清單,不改行為、不改斷言
  - 📏 量測:照 testplan 案例的條件量測或人工驗證,記下數字與門檻比較;是唯一不對應 `/tdd` 的開發任務
  - 不標步驟的只限三類:工具鏈設定、原樣複製 spec package 的規格檔、CI 設定
- **紅綠成對**:一個 testplan 案例對應同一個三位數的 `a`(🔴)與 `b`(🟢),`b` 依賴 `a`
- **對照組**:案例要測的程式路徑已經由既有程式或更早的綠燈任務做到時,紅燈任務標「(對照組)」:先確認通過,再暫時放入要抓的錯、確認斷言失敗後撤回;對應的綠燈任務確認不需要改程式碼。一般的紅燈任務寫完一執行就通過時,也照這個做法改當對照組,並在完成報告記一筆(`plan.md` § 待決問題 Q54)
- **誰做、怎麼排**:同一個 phase 的端點節各交給一個 subagent 平行做(E2 節等 E5 節寫明的共用件綠燈完成才開始);跨端點驗收節在端點節都完成、驗收過後由主 agent 做。每一節裡照任務編號一次做一個任務,做完才做下一個,不跳號;任務寫了「依賴」另一節的任務時,等那個任務做完才開始(同一個檔不同時改)
- 每個任務都寫出確切的檔案路徑
- **🧪**:這個任務對應的 `testplan.md` 案例 ID;🔵 寫這一節所有案例的範圍;不標步驟的任務不寫這一行
- **⚙**:這個任務要做出來或測到的介面元素:至少照 `testplan.md` 受測操作表的「規格錨點」欄寫,再加上這個任務實際做出或斷言的介面元素;括號裡是補充說明(`info.x-*` 不是可單獨引用的錨點)。純函式 `tuning.*` 的規格錨點是「—」,⚙ 寫它產生的 schema
- **📎**:做這個任務時要對照的依據:`spec.md` § FR / NFR / SC / 驗收情境 / 邊界情況、`research.md` § R、`plan.md` § Q 或段落名、`techstack.md` § 段落名
- **分隔註解**:每個案例的測試前寫 `# ---- 005 <案例 ID>`;延遲與逾時壓在 0.3 秒內,原樣的時間門檻交給量測任務
- **新的錯誤代碼**:`src/cgb/domain/errors.py` 的 `MESSAGES` 每加一個代碼,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等;任務裡寫明的是第一次用到它的綠燈)
- **新的狀態、步驟與結束原因**:`applying_tuning`、`restarting_ollama`、`reloading_models`、`OLLAMA_RESTART_FAILED` 的每一份清單都排在第一個需要它的綠燈:資料庫的 CHECK 在 T038b、T041b,`ACTIVE_STATES` 與進行中的查詢在 T120b,相容端點的 `_STATE_DESCRIPTIONS` 在 T144b,畫面的標籤在 T163b、T167b
- **本機的 Ollama 與 Colab**:任何任務都不對桌機 127.0.0.1:11434 送請求,也不執行沒有指定 `OLLAMA_HOST` 的 `ollama` 指令;要執行 `colab` 的任務(T002a、T100a 的命令列解析與 G-01~G-04)執行前先停下問使用者本人

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 沿用 001~004 的工具鏈、`uv.lock` 與測試基礎(`tests/conftest.py`、`tests/fakes/`、`tests/e2e/conftest.py`、`tests/realrun/helpers.py`);這一輪不新增套件、服務、port 與掛載,不複製規格檔、不改 CI(`plan.md` § Project Structure)。只新增一個 pytest marker。新的 fixture 與替身由第一個需要它的紅燈任務建立:`tests/fixtures/db/schema_v1.sql` 由 T038a(要在改 `src/cgb/db/schema.py` 之前凍結),遠端腳本的 `box` 與假 `nvidia-smi` 由 T009a,`_open_db(kind="from_v1")` 由 T089a

- [x] T001 在 `pyproject.toml` 的 `[tool.pytest.ini_options]` 新增 marker `realrun_local`(說明:接本機臨時 `ollama serve` 的實跑案例,不開 Colab、不花 compute units),`addopts` 改成 `["-m", "not realrun and not realrun_local"]`,照 `realrun` 的做法讓快速層與預設的 `uv run pytest` 排除它、全部層另外以 `uv run pytest -m realrun_local` 執行;完成條件是 `uv run pytest --markers` 列得出 `realrun_local`
  - 📎 `plan.md` § 待決問題 Q30;`testplan.md` § 測試指令

---

## Phase 2: User Story 1 - 開好工作階段,遠端 Ollama 就依這台機器的顯示記憶體調好設定 (Priority: P1) 🎯 MVP

**Goal**: 開工作階段到就緒時,遠端 Ollama 已依量到的顯示記憶體用對應級距的平行數、context 長度與同時載入模型數啟動(讀不到時照 004 的方式啟動);工作階段頁與紀錄顯示量到的硬體與套用的設定,後端重新啟動後不重新量測

**Independent Test**: 照 `testplan.md` § 2 的全部案例:E5 以 `uv run pytest tests/integration/test_colab_cli.py` 與 `uv run pytest -m realrun_local tests/integration/test_ollama_scripts.py`、E2 以 `uv run pytest tests/integration/test_api_tuning.py tests/unit/test_tuning.py`、E4 以 `uv run pytest tests/integration/test_db_schema.py`、跨端點驗收以 `uv run pytest tests/e2e/test_005_us1_tuning.py` 執行全綠

### E5 Colab CLI(`colab exec` 遠端腳本)

> E5 節最前面的 T002b、T003b 做出 `plan.md` § 待決問題 Q32 的共用件(`start_ollama(name, overrides)` 的簽章、`AdapterError.remote_stage`、`ColabWorld.start_result`),E2 節等它們的綠燈完成才開始(Q55);E4 節和 E5 平行。E5 只改 `src/cgb/adapters/`、`tests/integration/test_colab_cli.py` 與新檔 `tests/integration/test_ollama_scripts.py`;遠端腳本的測試整檔標 `realrun_local`(T001),照 `testplan.md` § 5.0 只照 P5、P6 與臨時 Ollama 的護欄:port 由 `free_loopback_port()` 取(避開 11434~11436 與 8780),`HOME`、`OLLAMA_MODELS`、pid 檔、狀態檔與 log 都在 pytest 暫存資料夾,不對 127.0.0.1:11434 送任何請求,不執行 `colab`,收尾確認行程與行程群組都已結束

- [x] T002a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-01 的測試(呼叫 `start_ollama(name="cgb-test-0001", overrides=AUTO)`;分隔註解寫 `# ---- 005 US1-CLI-01`);同一個任務在檔內新增 `testplan.md` § 2.1 的 `AUTO`、`start_argv`、`result`、`TUNING_AUTO_40G`、`TUNING_DEFAULT`;另把 `start_argv()` 交給真的 `colab` CLI 以暫存 `HOME`、未授權解析一次(照 001 `test_create_session_command_line_is_accepted_by_real_cli` 的 `run_real_colab_without_auth`,斷言沒有參數錯誤;這支加進快速層的 `--deselect`),這一步會在本機執行 `colab`,執行前先停下問使用者本人(`plan.md` § 待決問題 Q56),執行確認它因為「沒有覆蓋值時省略 `--env CGB_TUNE_*`,kernel 留著上一次的值被腳本讀到(合約共用約定 10、research.md R7)」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`
  - 📎 `spec.md` § FR-002、FR-003;`plan.md` § 待決問題 Q32、Q51
- [x] T002b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/services/session_lifecycle.py`、`tests/integration/test_colab_cli.py`、`tests/integration/test_api_session.py`、`tests/realrun/test_host_adapter.py` 只寫讓 US1-CLI-01 通過的程式碼;`ColabControl.start_ollama(name, overrides)` 每次都帶齊 `--env CGB_TUNE_NUM_PARALLEL=`、`--env CGB_TUNE_CONTEXT_LENGTH=`、`--env CGB_TUNE_MAX_LOADED_MODELS=`(None 代成空字串,合約共用約定 10),仍經 `_exec_script`;唯一的呼叫端 `src/cgb/services/session_lifecycle.py` 的 `colab.start_ollama(name=name)` 改成帶三個 None 的 `overrides`;同一個任務把 `tests/integration/test_colab_cli.py` 用 `START_OLLAMA_ARGV` 的 001 測試改成 `start_argv()`、呼叫改帶 `overrides=AUTO`(`start_ollama_script`、`test_start_ollama_reads_the_last_result_line`、`test_start_ollama_waits_up_to_240_seconds_on_the_remote`、`test_start_ollama_passes_ollama_environment_verbatim`、`test_start_ollama_retries_once_with_same_arguments_after_connection_lost`、`test_remote_traceback_without_result_is_remote_error_with_masked_url`、`test_exec_times_out_without_retry_and_ends_cli_with_its_children`、`test_start_ollama_network_failures_are_told_apart_without_retry`、`test_start_ollama_without_valid_authorization_is_auth_required_without_retry`、`CALLS_THAT_CRASH`、`test_start_ollama_on_runtime_that_is_gone_is_not_found_without_retry`、`test_start_ollama_result_not_ok_is_remote_error_with_stage_and_detail`、`start_ollama_argv`);`plan.md` § 待決問題 Q32 的共用件也在這個任務做:`tests/integration/test_api_session.py` 的 `ColabWorld._start_ollama` 改回 `self.start_result`(預設 `T4_STARTED`,定義在同一檔,`plan.md` § 待決問題 Q59),仍記 `("start_ollama", name)`,`FakeColabControl` 照真 adapter 綁定新簽章(`tests/integration/test_fake_signatures.py` 照原樣回歸);`tests/realrun/test_host_adapter.py` 的 `START_OLLAMA_ENV` 補三個 `CGB_TUNE_*`(realrun,這個任務不執行它,`plan.md` § 待決問題 Q63),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T002a)
  - 🧪 `testplan.md` § US1-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`
  - 📎 `spec.md` § FR-002、FR-003;`plan.md` § 待決問題 Q32、Q51
- [x] T003a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-05 的測試(每種各呼叫一次 `start_ollama(name="cgb-test-0001", overrides=AUTO)`;分隔註解寫 `# ---- 005 US1-CLI-05`),執行確認它因為「照現況只把 `stage` 寫進 `message`、`AdapterError` 沒有 `remoteStage`,呼叫者要解析中文訊息才知道階段(plan.md Q3)」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-05
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q3、Q32
- [x] T003b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/errors.py`、`src/cgb/adapters/colab_cli.py` 只寫讓 US1-CLI-05 通過的程式碼;`AdapterError` 加 keyword 參數 `remote_stage`(預設 None,S1 `Error.remoteStage`);結果 `ok` 為 false 時以 `stage` 填 `remote_stage`、`message` 含階段與 `detail`;沒有結果行的 traceback 時 `remote_stage` 為 None(其他建 `AdapterError` 的地方不用改),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T003a)
  - 🧪 `testplan.md` § US1-CLI-05
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q3、Q32
- [x] T004a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-02 的測試(呼叫 `start_ollama(name="cgb-test-0001", overrides=AUTO)`;分隔註解寫 `# ---- 005 US1-CLI-02`),執行確認它因為「轉接層依 `vramTotalBytes` 自己重算 `tuning`,而不是原樣交出腳本回報的(合約共用約定 12 (e))」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.MachineProbe`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-001、FR-002
- [x] T004b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`tests/integration/test_colab_cli.py` 只寫讓 US1-CLI-02 通過的程式碼;回傳加上 `machine`(`gpuName`、`vramTotalBytes`、`systemMemoryTotalBytes`,`probedAt` 取轉接層收到結果時的 UTC 時間)與原樣的 `tuning`(合約共用約定 12 (e));同一個任務刪掉 `tests/integration/test_colab_cli.py` 的 `test_start_ollama_reads_the_last_result_line`、`test_start_ollama_retries_once_with_same_arguments_after_connection_lost`(以整個結果字典斷言,由 US1-CLI-02、US1-CLI-07 取代,`testplan.md` § 2.1),執行全部測試確認都通過、不留 skip,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T004a)
  - 🧪 `testplan.md` § US1-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.MachineProbe`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-001、FR-002
- [x] T005a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-03 的測試(呼叫 `start_ollama(name="cgb-test-0001", overrides=AUTO)`;分隔註解寫 `# ---- 005 US1-CLI-03`);T004b 讓 `start_ollama` 原樣交出 `vramTotalBytes`、`gpuName` 與 `tuning`(`src/cgb/adapters/colab_cli.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「把 null 的顯示記憶體當成缺欄位歸成 `COLAB_BAD_RESPONSE`,讀不到顯示記憶體就讓開啟失敗」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US1-CLI-03
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.MachineProbe`
  - 📎 `spec.md` § FR-003
- [x] T005b [US1] 🟢 /tdd 綠燈:US1-CLI-03 由 T004b 讓 `start_ollama` 原樣交出 `vramTotalBytes`、`gpuName` 與 `tuning`(`src/cgb/adapters/colab_cli.py`)滿足,確認 `src/cgb/adapters/colab_cli.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/colab_cli.py` 只寫讓 US1-CLI-03 通過的程式碼(依賴 T005a)
  - 🧪 `testplan.md` § US1-CLI-03
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.MachineProbe`
  - 📎 `spec.md` § FR-003
- [x] T006a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-04 的測試(呼叫 `start_ollama(name="cgb-test-0001", overrides={"numParallel": 4, "contextLength": None, "maxLoadedModels": None})`;分隔註解寫 `# ---- 005 US1-CLI-04`),執行確認它因為「`tuning` 為 null 時歸成 `COLAB_BAD_RESPONSE`,後端恢復時接不回 005 之前的工作階段」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-04
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 5;`plan.md` § 待決問題 Q2
- [x] T006b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py` 只寫讓 US1-CLI-04 通過的程式碼;`alreadyRunning` 為 true 時接受 `tuning` 為 null、原樣回 None,不拿這次的覆蓋值補一份,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T006a)
  - 🧪 `testplan.md` § US1-CLI-04
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 5;`plan.md` § 待決問題 Q2
- [x] T007a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-06 的測試(每種各呼叫一次 `start_ollama(name="cgb-test-0001", overrides=AUTO)`;分隔註解寫 `# ---- 005 US1-CLI-06`),執行確認它因為「照現況以 `result["ollamaVersion"]` 直接取值,缺鍵丟 `KeyError` 越過轉接層」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-06
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.Error`、`components.schemas.TuningSource`
  - 📎 `spec.md` § FR-002;`plan.md` § 待決問題 Q50
- [x] T007b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`tests/integration/test_colab_cli.py` 只寫讓 US1-CLI-06 通過的程式碼;缺鍵、型別不符、`source` 不在 `TuningSource` 的列舉、新啟動(`alreadyRunning` 為 false)卻沒有 `tuning` 都歸 `COLAB_BAD_RESPONSE`,不讓 `KeyError`、`TypeError`、`ValueError` 越過轉接層;同一個任務把 `tests/integration/test_colab_cli.py` 的 `START_OLLAMA_OK` 改成含 `gpuName`、`vramTotalBytes`、`systemMemoryTotalBytes`、`tuning` 的 005 結果行(沿用它的 001 測試只斷言命令列與分類,照原樣回歸),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T007a)
  - 🧪 `testplan.md` § US1-CLI-06
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.Error`、`components.schemas.TuningSource`
  - 📎 `spec.md` § FR-002;`plan.md` § 待決問題 Q50
- [x] T008a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-07 的測試(每種各呼叫一次 `start_ollama(name="cgb-test-0001", overrides=AUTO)`;分隔註解寫 `# ---- 005 US1-CLI-07`);既有的 `_exec_script`(`src/cgb/adapters/colab_cli.py`:失敗分類、逾時整組終止、`Connection was lost` 以同一組參數重跑一次),加上 T002b 讓 `start_ollama` 經它組命令列已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「加覆蓋值時另寫一條組命令列、直接呼叫 `_run` 的路徑,繞過 `_exec_script`,失去 001 的分類、整組終止與 `Connection was lost` 重跑」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US1-CLI-07
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [x] T008b [US1] 🟢 /tdd 綠燈:US1-CLI-07 由 既有的 `_exec_script`(`src/cgb/adapters/colab_cli.py`:失敗分類、逾時整組終止、`Connection was lost` 以同一組參數重跑一次),加上 T002b 讓 `start_ollama` 經它組命令列滿足,確認 `src/cgb/adapters/colab_cli.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/colab_cli.py` 只寫讓 US1-CLI-07 通過的程式碼(依賴 T008a)
  - 🧪 `testplan.md` § US1-CLI-07
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [x] T009a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US1-CLI-08 的測試(`box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US1-CLI-08`);同一個任務在這個新檔建 `testplan.md` § 2.1 的 fixture `box`(`fake_gpu`、`run`、`start_old_serve`、`serve_env`、`pid_file`、`state`、`version`、`marked`、socket 守門與收尾),整檔標 `pytest.mark.realrun_local`(T001);`/usr/local/bin/ollama` 不存在就 `pytest.skip("無法實跑:…")`、不替它安裝(`plan.md` § 待決問題 Q47);假 `nvidia-smi` 依收到的參數產生輸出:照 `--query-gpu` 的欄位順序與 `--format` 的 `noheader`、`nounits` 決定有沒有表頭與單位,印 `<名稱>, <MiB>`,不寫死整行(給 `raw` 時才原樣印);port 只用 `free_loopback_port()`,不對 127.0.0.1:11434 送任何請求,執行確認它因為「邊界用 `>` 判斷,剛好 12288、20480、32768、65536 MiB 落到下一級」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-08
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(剛好落在級距邊界);`research.md` § R2、R4、R6;`plan.md` § 待決問題 Q27、Q45、Q46、Q47
- [x] T009b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-08 通過的程式碼;腳本以 `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits` 讀第一張 GPU,依 FR-002 的級距(MiB × 1048576,「以上、未滿」,不看 GPU 名稱)決定三項,只把決定的五個 `OLLAMA_*` 加進 `ollama serve` 的環境,`CGB-RESULT` 回報 `gpuName`、`vramTotalBytes`、`tuning`;讓 `OLLAMA_HOST`(version URL)、`CGB_SERVE_PID_FILE`、`CGB_TUNING_FILE`、`CGB_SERVE_LOG`、`CGB_INSTALL_COMMAND`、`CGB_PROBE_TIMEOUT_SECONDS`、`CGB_VERIFY_SECONDS` 可覆寫,預設值不變,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T009a)
  - 🧪 `testplan.md` § US1-CLI-08
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(剛好落在級距邊界);`research.md` § R2、R4、R6;`plan.md` § 待決問題 Q27、Q45、Q46、Q47
- [x] T010a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US1-CLI-09 的測試(每種各 `box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US1-CLI-09`),執行確認它因為「讀不到時當成 0 GiB 套第一級 1/4096/1」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-09
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-003、FR-001;`research.md` § R6
- [x] T010b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-09 通過的程式碼;讀不到(沒有 `nvidia-smi`、非 0 結束、`[N/A]`)時 `vramTotalBytes`、`gpuName` 為 null,`tuning` 五項都是 `ollama_default`,serve 的環境不帶五個變數,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T010a)
  - 🧪 `testplan.md` § US1-CLI-09
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-003、FR-001;`research.md` § R6
- [x] T011a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_ollama_scripts.py` 寫 US1-CLI-10 的測試(`box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US1-CLI-10`);T009b(`src/cgb/adapters/scripts/start_ollama.py` 只取第一行、查詢參數和 `probe_resources.py` 相同)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「取最後一行,或把兩張的顯示記憶體加總(96 GiB 仍是 16/8192/3,所以另有則1、則2)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US1-CLI-10
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-001、邊界情況(多張 GPU)
- [x] T011b [US1] 🟢 /tdd 綠燈:US1-CLI-10 由 T009b(`src/cgb/adapters/scripts/start_ollama.py` 只取第一行、查詢參數和 `probe_resources.py` 相同)滿足,確認 `src/cgb/adapters/scripts/start_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-10 通過的程式碼(依賴 T011a)
  - 🧪 `testplan.md` § US1-CLI-10
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-001、邊界情況(多張 GPU)
- [x] T012a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US1-CLI-11 的測試(`box.run([start_ollama.py])`,之後讓 `box.run` 的子行程結束;分隔註解寫 `# ---- 005 US1-CLI-11`),執行確認它因為「系統記憶體用 `MemAvailable`,或沒乘 1024」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-11
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-001、FR-002;`plan.md` § 待決問題 Q2
- [x] T012b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-11 通過的程式碼;系統記憶體取 `/proc/meminfo` 的 `MemTotal` × 1024;serve 以 `start_new_session=True` 啟動,pid 檔寫 serve 的 pid,狀態檔寫 `gpuName`、`vramTotalBytes`、`systemMemoryTotalBytes`、`tuning`(和 `CGB-RESULT` 同名),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T012a)
  - 🧪 `testplan.md` § US1-CLI-11
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-001、FR-002;`plan.md` § 待決問題 Q2
- [x] T013a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US1-CLI-12 的測試(每種各 `box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US1-CLI-12`),執行確認它因為「啟動前沒刪舊的狀態檔,之後重跑走已在執行時讀到描述另一個 serve 的設定(合約共用約定 13-1)」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-12
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 5
- [x] T013b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-12 通過的程式碼;啟動前先刪狀態檔;驗證失敗不寫狀態檔,`detail` 取 serve 紀錄檔最後一行;啟動丟出的 `OSError` 回 `stage: start`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T013a)
  - 🧪 `testplan.md` § US1-CLI-12
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 5
- [x] T014a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US1-CLI-13 的測試(`box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US1-CLI-13`),執行確認它因為「已在執行時照這次的 `CGB_TUNE_*` 重算 `tuning`(回報平行數 4,遠端實際是 8)」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-13
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 5;`plan.md` § 待決問題 Q2
- [x] T014b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-13 通過的程式碼;已在回應時讀狀態檔交出 `tuning`(不照這次的 `CGB_TUNE_*` 重算),硬體用這次量到的,不再啟動 serve、不覆寫 pid 檔,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T014a)
  - 🧪 `testplan.md` § US1-CLI-13
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 5;`plan.md` § 待決問題 Q2
- [x] T015a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US1-CLI-14 的測試(每種各 `box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US1-CLI-14`),執行確認它因為「讀檔時的 `FileNotFoundError` 或 `JSONDecodeError` 沒接住,變成遠端例外,後端恢復 005 之前的工作階段時失敗」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-14
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 5
- [x] T015b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-14 通過的程式碼;狀態檔不存在、不是 JSON 或格式不符時 `tuning` 為 null,照樣印結果行,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T015a)
  - 🧪 `testplan.md` § US1-CLI-14
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、使用者故事 1 驗收情境 5
- [x] T016a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US1-CLI-15 的測試(`box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US1-CLI-15`),執行確認它因為「寫 pid 檔或狀態檔的 `OSError` 沒接住,serve 已經在跑卻回報失敗,後端以為開啟失敗而釋放執行環境(合約共用約定 13、13-1:寫入失敗不算失敗)」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-15
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-001
- [x] T016b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-15 通過的程式碼;寫 pid 檔與狀態檔的 `OSError` 接住、不算失敗(合約共用約定 13、13-1),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T016a)
  - 🧪 `testplan.md` § US1-CLI-15
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-001
- [x] T017a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US1-CLI-16 的測試(`box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US1-CLI-16`),執行確認它因為「呼叫 `nvidia-smi` 沒設逾時,開啟被拖到 CLI 的 240 秒時限」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-16
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § NFR-001、FR-003;`research.md` § R6;`plan.md` § 待決問題 Q48
- [x] T017b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-16 通過的程式碼;`nvidia-smi` 以 `CGB_PROBE_TIMEOUT_SECONDS`(預設 10)逾時,逾時就結束它並當成讀不到,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T017a)
  - 🧪 `testplan.md` § US1-CLI-16
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § NFR-001、FR-003;`research.md` § R6;`plan.md` § 待決問題 Q48
- [x] T018a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_ollama_scripts.py` 寫 US1-CLI-17 的測試(`box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US1-CLI-17`);T009b 讓 version URL 取自 `OLLAMA_HOST`(`src/cgb/adapters/scripts/start_ollama.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「腳本照現況寫死 `VERSION_URL = "http://127.0.0.1:11434/api/version"`,不讀 `OLLAMA_HOST`(在 Colab 上碰巧正確,在桌機上會打到使用者自己的 Ollama,並把它當成已在執行)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US1-CLI-17
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § NFR-003;`plan.md` § 待決問題 Q46
- [x] T018b [US1] 🟢 /tdd 綠燈:US1-CLI-17 由 T009b 讓 version URL 取自 `OLLAMA_HOST`(`src/cgb/adapters/scripts/start_ollama.py`)滿足,確認 `src/cgb/adapters/scripts/start_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-17 通過的程式碼(依賴 T018a)
  - 🧪 `testplan.md` § US1-CLI-17
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § NFR-003;`plan.md` § 待決問題 Q46
- [x] T019 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T002b~T018b 記下的重構清單(範圍限 `src/cgb/adapters/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_colab_cli.py`、`tests/integration/test_ollama_scripts.py` 的斷言(依賴 T018b)
  - 🧪 `testplan.md` § US1-CLI-01、US1-CLI-05、US1-CLI-02~US1-CLI-04、US1-CLI-06~US1-CLI-17
  - 📎 `testplan.md` § 2.1
- [x] T020 [US1] 📏 量測:在 `tests/integration/test_ollama_scripts.py` 寫 US1-CLI-18(標 `realrun_local`),照案例在桌機有 `/usr/bin/nvidia-smi`(GTX 1660 Ti)時以 `box.start_old_serve()` 起好已在執行的 serve 與狀態檔,組 A 的 `bin/nvidia-smi` 連到 `/usr/bin/nvidia-smi`、組 B 沒有 `nvidia-smi`,測試先自己跑一次 `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits` 記下第一行;A、B 交錯各 `box.run([start_ollama.py])` 5 次,記下 A、B 各 5 次的耗時與中位數、A 每次的 `vramTotalBytes` 與 `gpuName`,和門檻(A 中位數減 B 中位數 ≤ 5 秒,SC-003;`vramTotalBytes` 等於讀到的 MiB × 1048576、`gpuName` 等於讀到的名稱)比較,結果寫進 `specs/005-ollama-machine-tuning/measurements.md`;只對桌機 GPU 送唯讀的 `nvidia-smi --query-gpu`,不改 GPU 設定、不跑 CUDA 程式;serve 是 `box` 起的臨時 `ollama serve`(`free_loopback_port()`、暫存 `HOME` 與 `OLLAMA_MODELS`,不 pull 任何模型),腳本裡的 socket 守門只放行那個 port,不對 127.0.0.1:11434 送請求;不執行 `colab`、不花 compute units;紀錄只寫 pytest 暫存資料夾;收尾照 `box` 確認行程與行程群組都已結束;沒有 `/usr/bin/nvidia-smi` 或 `/usr/local/bin/ollama` 就標無法實跑;判定者:腳本;樣本:一次實跑,A、B 各 5 次(未用於調整)
  - 🧪 `testplan.md` § US1-CLI-18
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`
  - 📎 `spec.md` § NFR-001、FR-001、SC-003

### E2 後端 UI API(FastAPI REST 與 SSE)

> 依賴 E5 節的 US1-CLI-01、US1-CLI-05 綠燈(T002b、T003b)完成才開始(`plan.md` § 待決問題 Q32、Q55),之後和 E5、E4 平行。E2 只改 `src/cgb/services/`、`src/cgb/repos/`、`src/cgb/api/`、`src/cgb/domain/tuning.py`、`tests/integration/test_api_tuning.py`、`tests/unit/test_tuning.py`(及綠燈任務寫明的既有測試);`src/cgb/db/schema.py` 由 E4 節負責,寫 `session_tunings` 的 T021b、T026b 依賴 E4 的 T038b。E2 不重算設定(`info.x-tuning-rule` (2)),級距由 US1-API-11~16 的單元案例驗;等待以 `wait_for_state`、`wait_until` 帶 1 秒上限,時間以 `fake_clock` 推進

- [x] T021a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US1-API-01 的測試(以 `open_ready(ui_client, A100)` 開到就緒,`GET /api/session`;分隔註解寫 `# ---- 005 US1-API-01`);同一個任務在檔內新增 `testplan.md` § 2.2 的 `GIB`、`A100`、`L4`、`applied`、`started`、`restarted`、`A100_STARTED`、`record_of`、`sent_overrides`(`T4_STARTED` 從 `tests/integration/test_api_session.py` 匯入,`plan.md` § 待決問題 Q59),執行確認它因為「`Session` 沒有 `ollama` 欄位,或 `startOllama` 的結果只取 `ollamaVersion` 就丟掉」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § FR-004、FR-002、FR-001、使用者故事 1 驗收情境 1、使用者故事 1 驗收情境 2、使用者故事 1 獨立測試;`research.md` § R9
- [x] T021b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py`、`tests/e2e/test_us1_session.py` 只寫讓 US1-API-01 通過的程式碼;`startOllama` 回傳的 `machine`、`tuning` 原樣存起來,`Session.ollama` 照 `OllamaStatus` 回(E2 不重算,`info.x-tuning-rule` (2));同一個任務把 `tests/e2e/test_us1_session.py` 的 `ColabWorld` 裡 `start_ollama` 的回傳改成 T4 的 `OllamaStarted`(和 `T4_STARTED` 同值),既有 e2e 照原樣回歸,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T021a、T002b、T003b、T038b)
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § FR-004、FR-002、FR-001、使用者故事 1 驗收情境 1、使用者故事 1 驗收情境 2、使用者故事 1 獨立測試;`research.md` § R9
- [x] T022a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_tuning.py` 寫 US1-API-02 的測試(`open_ready(ui_client, A100)`,`GET /api/session`;分隔註解寫 `# ---- 005 US1-API-02`);T021b 原樣轉交遠端回報的 `tuning` 與 `machine`(`src/cgb/services/session_lifecycle.py`),不依 `runtimeType.gpu` 查表、不用 `probe_resources` 的值已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「後端以 `runtimeType.gpu` 為 A100 就填 32~64 GiB 那一級(8、2),或用 001 `probe_resources` 讀到的 T4 值覆蓋遠端回報」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § FR-002(只看顯示記憶體)、FR-004
- [x] T022b [US1] 🟢 /tdd 綠燈:US1-API-02 由 T021b 原樣轉交遠端回報的 `tuning` 與 `machine`(`src/cgb/services/session_lifecycle.py`),不依 `runtimeType.gpu` 查表、不用 `probe_resources` 的值滿足,確認 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 只寫讓 US1-API-02 通過的程式碼(依賴 T022a)
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § FR-002(只看顯示記憶體)、FR-004
- [x] T023a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US1-API-03 的測試(送 `POST /api/session`(`A100`);等閘門被走到時 `GET /api/session`;放行閘門,讀 SSE 直到收到 `state` 為 `ready` 的 `session.updated`(最多 1 秒);分隔註解寫 `# ---- 005 US1-API-03`),執行確認它因為「`ollama` 等到 `ready` 那一則才寫入(連線中與驗證中畫面一直是「量測中」)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-004、FR-001
- [x] T023b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 只寫讓 US1-API-03 通過的程式碼;`startOllama` 一回來就寫 `ollama` 並推 `session.updated`,不等 `ready`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T023a)
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-004、FR-001
- [x] T024a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US1-API-04 的測試(`POST /api/session`(`T4`),`wait_for_state(ui_client, "ready")`;`GET /api/session`、`GET /api/sessions/{name}`;分隔註解寫 `# ---- 005 US1-API-04`),執行確認它因為「顯示記憶體是 null 就當成量測失敗、開啟失敗」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-003、FR-004、使用者故事 1 驗收情境 3
- [x] T024b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py`、`src/cgb/api/history.py`(Q68)只寫讓 US1-API-04 通過的程式碼;`machine.vramTotalBytes` 為 null 時照常就緒,`ollama` 標出讀不到顯示記憶體,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T024a)
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-003、FR-004、使用者故事 1 驗收情境 3
- [x] T025a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US1-API-05 的測試(`POST /api/session`(`T4`),等 `ready`;`GET /api/session`、`GET /api/sessions/{name}`;分隔註解寫 `# ---- 005 US1-API-05`),執行確認它因為「`tuning` 為 null 時取 `["numParallel"]` 丟 `TypeError`,開啟變成 `open_failed` 或 `GET /api/session` 回 500」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-004、FR-003
- [x] T025b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 只寫讓 US1-API-05 通過的程式碼;`tuning` 為 null 時不取值,`ollama` 照合約回讀不到設定,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T025a)
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-004、FR-003
- [x] T026a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US1-API-06 的測試(送 `POST /api/session`(`A100`);等閘門被走到後 `fake_clock.advance(30)`,放行閘門;等 `ready`,`GET /api/sessions/{name}`;分隔註解寫 `# ---- 005 US1-API-06`),執行確認它因為「受理時就寫開啟那一筆(`at` 是受理的時間)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-005、使用者故事 1 驗收情境 4;`research.md` § R9
- [x] T026b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/session_lifecycle.py`、`src/cgb/repos/tunings.py`、`src/cgb/api/history.py` 只寫讓 US1-API-06 通過的程式碼;`startOllama` 成功時以它回來的時間寫開啟那一筆 `session_tunings`(`trigger` 為 `open`,`src/cgb/repos/tunings.py`),`getSessionRecord` 回 `tunings`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T026a、T038b)
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-005、使用者故事 1 驗收情境 4;`research.md` § R9
- [x] T027a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US1-API-07 的測試(各送 `POST /api/session`(`T4`),`wait_for_state(ui_client, "open_failed")`;`GET /api/session`、`GET /api/sessions/{name}`;分隔註解寫 `# ---- 005 US1-API-07`),執行確認它因為「開啟時先寫一筆 `in_progress` 或 `failed` 的開啟紀錄,失敗時沒刪」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-005
- [x] T027b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 只寫讓 US1-API-07 通過的程式碼;開啟失敗時不留開啟那一筆,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T027a)
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-005
- [x] T028a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US1-API-08 的測試(以同一個 SQLite 檔 `running(make_app())` 跑第二個 app,`wait_until` `state` 為 `ready` 且 `world.calls("open_tunnel")` 不是空的(最多 1 秒);`GET /api/session`、`GET /api/sessions/{name}`;分隔註解寫 `# ---- 005 US1-API-08`),執行確認它因為「`Session.ollama` 只存在記憶體,重新啟動後是 `pending` 或 `unknown`」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § 使用者故事 1 驗收情境 5、FR-004
- [x] T028b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/repos/tunings.py` 只寫讓 US1-API-08 通過的程式碼;後端重新啟動接回時從 `session_tunings` 讀回 `Session.ollama`,不重新量測、不重啟遠端 Ollama,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T028a)
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § 使用者故事 1 驗收情境 5、FR-004
- [x] T029a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_tuning.py` 寫 US1-API-09 的測試(`GET /api/sessions/cgb-test-not-there`;分隔註解寫 `# ---- 005 US1-API-09`);既有 `src/cgb/api/history.py` 的 `getSessionRecord`(名稱不存在回 404 `SESSION_NOT_FOUND`),加上 T026b 先查 `sessions` 再讀 `tunings`已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「查詢改成 `sessions LEFT JOIN session_tunings` 後,名稱不存在時組出 `{"tunings": []}` 回 200」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-005(getSessionRecord 的 SESSION_NOT_FOUND)
- [x] T029b [US1] 🟢 /tdd 綠燈:US1-API-09 由 既有 `src/cgb/api/history.py` 的 `getSessionRecord`(名稱不存在回 404 `SESSION_NOT_FOUND`),加上 T026b 先查 `sessions` 再讀 `tunings`滿足,確認 `src/cgb/api/history.py`、`src/cgb/repos/tunings.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/history.py`、`src/cgb/repos/tunings.py` 只寫讓 US1-API-09 通過的程式碼(依賴 T029a)
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-005(getSessionRecord 的 SESSION_NOT_FOUND)
- [x] T030a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US1-API-10 的測試(跑第二個 app,等 `state` 為 `ready`;`GET /api/session`、`GET /api/sessions/{name}`;分隔註解寫 `# ---- 005 US1-API-10`),執行確認它因為「沒有紀錄時照「沒有就是開啟中」回 `pending`,UI 一直顯示量測中」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-004
- [x] T030b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py`、`src/cgb/services/session_lifecycle.py`(Q68)只寫讓 US1-API-10 通過的程式碼;005 之前開的工作階段沒有紀錄時,`ollama.status` 照合約回 `unknown`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T030a)
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-004
- [x] T031a [US1] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US1-API-11 的測試(依序以 `0`、`6 * GIB`、`12_000_000_000`(十進位的 12 GB,約 11.18 GiB)、`12 * GIB - 1` 呼叫;分隔註解寫 `# ---- 005 US1-API-11`),執行確認它因為「單位用 10⁹ 換算,十進位 12 GB 被歸到 12~20 GiB 那一級」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(級距邊界);`research.md` § R4;`plan.md` § 待決問題 Q31
- [x] T031b [US1] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US1-API-11 通過的程式碼;新增 `auto_tier(vram_total_bytes)`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T031a)
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(級距邊界);`research.md` § R4;`plan.md` § 待決問題 Q31
- [x] T032a [US1] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US1-API-12 的測試(依序以 `12 * GIB`、`15 * GIB`(T4)、`20 * GIB - 1` 呼叫;分隔註解寫 `# ---- 005 US1-API-12`),執行確認它因為「下邊界寫成 `>`,剛好 12 GiB 掉到第一級」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(級距邊界);`plan.md` § 待決問題 Q31
- [x] T032b [US1] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US1-API-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T032a)
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(級距邊界);`plan.md` § 待決問題 Q31
- [x] T033a [US1] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US1-API-13 的測試(依序以 `20 * GIB`、`int(22.5 * GIB)`(L4)、`32 * GIB - 1` 呼叫;分隔註解寫 `# ---- 005 US1-API-13`),執行確認它因為「下邊界寫成 `>`,剛好 20 GiB 掉到第二級」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(L4 22.5 GiB);`plan.md` § 待決問題 Q31
- [x] T033b [US1] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US1-API-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T033a)
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(L4 22.5 GiB);`plan.md` § 待決問題 Q31
- [x] T034a [US1] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US1-API-14 的測試(依序以 `32 * GIB`、`40 * GIB`(A100)、`64 * GIB - 1` 呼叫;分隔註解寫 `# ---- 005 US1-API-14`),執行確認它因為「剛好 32 GiB 被歸到 20~32 那一級(spec 邊界情況點名的錯)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(剛好 32 GiB);`plan.md` § 待決問題 Q31
- [x] T034b [US1] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US1-API-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T034a)
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(剛好 32 GiB);`plan.md` § 待決問題 Q31
- [x] T035a [US1] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US1-API-15 的測試(依序以 `64 * GIB`、`80 * GIB`(H100)、`96 * GIB` 呼叫;分隔註解寫 `# ---- 005 US1-API-15`),執行確認它因為「剛好 64 GiB 掉到第四級」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(級距邊界);`plan.md` § 待決問題 Q31
- [x] T035b [US1] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US1-API-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T035a)
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-002、SC-005、邊界情況(級距邊界);`plan.md` § 待決問題 Q31
- [x] T036a [US1] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US1-API-16 的測試(以 `None` 呼叫;分隔註解寫 `# ---- 005 US1-API-16`),執行確認它因為「讀不到時回最低一級 `(1, 4096, 1)`,開啟時就會帶 FR-002 的變數,違反 FR-003」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-003、SC-005;`plan.md` § 待決問題 Q31
- [x] T036b [US1] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US1-API-16 通過的程式碼;`auto_tier(None)` 回 None(讀不到就不帶 FR-002 的變數),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T036a)
  - 🧪 `testplan.md` § US1-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-003、SC-005;`plan.md` § 待決問題 Q31
- [x] T037 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T021b~T036b 記下的重構清單(範圍限 `src/cgb/services/`、`src/cgb/repos/`、`src/cgb/api/`、`src/cgb/domain/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_api_tuning.py`、`tests/unit/test_tuning.py` 的斷言(依賴 T036b)
  - 🧪 `testplan.md` § US1-API-01~US1-API-16
  - 📎 `testplan.md` § 2.2

### E4 資料庫(SQLite)

> 只改 `src/cgb/db/schema.py`、`tests/integration/test_db_schema.py` 與 `tests/fixtures/db/`。連線一律用 `cgb.db.connection.connect`(遷移的交易要明寫 `BEGIN`);001、004 的案例保留,斷言 `user_version == 1` 的 8 處照 `plan.md` § 待決問題 Q41 在 T038b、T045b 改成 2;失敗注入照 `testplan.md` § 2.3 的 `set_authorizer`。全新庫的整份 DDL(含故事 2、3 用到的表)由 T038b 照 `contracts/store.dbml` 建,故事 2、3 的 E4 節因此都是對照組

- [x] T038a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-01 的測試(以 `connect` 開檔並呼叫 `create_schema(conn)`,再讀 `PRAGMA user_version`、`sqlite_master`、`PRAGMA table_info(session_tunings)`、`PRAGMA index_list(session_tunings)`、`PRAGMA foreign_key_list(session_tunings)` 與同一條連線的 `PRAGMA foreign_keys`;分隔註解寫 `# ---- 005 US1-DB-01`);**在改 `src/cgb/db/schema.py` 之前**,照 `testplan.md` § 2.3 以現行(commit 7a2f328)的 `create_schema` 建空庫,匯出 `tests/fixtures/db/schema_v1.sql`(15 句,每句以 `;` 結尾,另加 `INSERT INTO settings (id) VALUES (1);`,最後一行寫 `PRAGMA user_version = 1;`),在檔內加 helper `_build_v1`,`_insert_session` 加 `step`、`end_reason`、`reason_code` 與其他 001 欄位的 keyword 參數(預設值不變),執行確認它因為「全新庫的 `_create_fresh` 沒有改,仍設 `user_version = 1`,新表只在 1 → 2 的路徑建,全新庫要等第二次啟動才有 `session_tunings`」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-01
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`、`Table runtime_type_tunings`、`Table session_tunings`、`Table session_tuning_models`
  - 📎 `spec.md` § FR-005;`research.md` § R9;`plan.md` § 待決問題 Q22、Q28、Q41、Q42、Q44、Q62
- [x] T038b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py`、`tests/integration/test_db_schema.py` 只寫讓 US1-DB-01 通過的程式碼;全新庫照 `contracts/store.dbml` 建出整份 DDL:`sessions`、`session_transitions` 收下 `applying_tuning` 與 `restarting_ollama`、`reloading_models`(`end_reason` 不加 CHECK),新表 `runtime_type_tunings`、`session_tunings`、`session_tuning_models` 與 `uq_session_tunings_in_progress`,新表的列舉欄位寫 `CHECK IN`;`user_version` 設 2;同一個任務把 `tests/integration/test_db_schema.py` 斷言全新庫 `user_version == 1` 的 `test_全新資料庫建出_user_version_為_1_且_download_jobs_有所屬工作階段與不分大小寫的唯一索引`(第 143 行)與 `test_後端重新啟動後精選清單_自動下載設定與自動下載結果都還在`(第 1048 行)改成 2,執行全部測試確認都通過、不留 skip,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T038a)
  - 🧪 `testplan.md` § US1-DB-01
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`、`Table runtime_type_tunings`、`Table session_tunings`、`Table session_tuning_models`
  - 📎 `spec.md` § FR-005;`research.md` § R9;`plan.md` § 待決問題 Q22、Q28、Q41、Q42、Q44、Q62
- [x] T039a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US1-DB-02 的測試(依序執行:①寫入「開啟那一筆(A100)」;②以 `SELECT * FROM session_tunings WHERE session_name='cgb-a'` 與 `SELECT typeof(vram_total_bytes), typeof(system_memory_total_bytes) FROM session_tunings` 讀回;③再寫一筆 `cgb-a` 的 `trigger='open'`(其他同 ①、`at` 改成 `'2026-11-15T08:10:00Z'`);④寫一筆 `cgb-b` 的開啟那一筆(T4:`gpu_name='Tesla T4'`、`vram_total_bytes=16106127360`、`num_parallel=2`、`context_length=4096`、`max_loaded_models=1`);⑤寫一筆 `cgb-c` 的 `trigger='open'`、`attempt='requested'`(`cgb-c` 還沒有開啟那一筆,被擋只會是因為 CHECK);分隔註解寫 `# ---- 005 US1-DB-02`);T038b 照 `contracts/store.dbml` 宣告 `session_tunings` 的欄位型別(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「顯示記憶體、系統記憶體的欄位宣告成 REAL 或 TEXT(例如照 UI 顯示存成 GiB),`typeof` 不是 `integer`,換算回位元組時和級距表的邊界比不準」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US1-DB-02
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-005、使用者故事 1 驗收情境 4
- [x] T039b [US1] 🟢 /tdd 綠燈:US1-DB-02 由 T038b 照 `contracts/store.dbml` 宣告 `session_tunings` 的欄位型別(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US1-DB-02 通過的程式碼(依賴 T039a)
  - 🧪 `testplan.md` § US1-DB-02
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-005、使用者故事 1 驗收情境 4
- [x] T040a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US1-DB-03 的測試(依序寫入開啟那一筆(其他欄位同「開啟那一筆(A100)」):①`cgb-a`:讀不到顯示記憶體,`gpu_name`、`vram_total_bytes` NULL,`system_memory_total_bytes=13605273600`,五項值都是 NULL、五個 `*_source` 都是 `ollama_default`;②`cgb-b`:遠端 Ollama 已在執行而讀不到設定檔(plan Q2),五項值與五個 `*_source` 全部 NULL;③~⑨ 依序寫在 `cgb-c3`~`cgb-c9`(各自還沒有開啟那一筆,被擋只會是因為 CHECK 或 NOT NULL):③`vram_total_bytes=-1`;④`num_parallel=0`;⑤`flash_attention=2`;⑥`num_parallel_source='default'`;⑦`kv_cache_type='q4_0'`;⑧`trigger='restart'`;⑨`result` NULL;⑩`session_name` 改成 `sessions` 沒有的 `cgb-zzz`;分隔註解寫 `# ---- 005 US1-DB-03`);T038b 照 `contracts/store.dbml` 讓硬體欄位可為空、沒有預設 0(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`vram_total_bytes` 設成 `NOT NULL` 或預設 0,讀不到顯示記憶體(FR-003)時開啟那一筆寫不進去,或寫成 0、UI 顯示「顯示記憶體 0 GB」而不是「讀不到」」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US1-DB-03
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-005、FR-003
- [x] T040b [US1] 🟢 /tdd 綠燈:US1-DB-03 由 T038b 照 `contracts/store.dbml` 讓硬體欄位可為空、沒有預設 0(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US1-DB-03 通過的程式碼(依賴 T040a)
  - 🧪 `testplan.md` § US1-DB-03
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-005、FR-003
- [x] T041a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-04 的測試(以 `connect` 開同一個檔,呼叫 `create_schema(conn)`;分隔註解寫 `# ---- 005 US1-DB-04`),執行確認它因為「`create_schema` 照 004 的寫法「`user_version` 不是 0 就直接 return」,v1 舊庫什麼都沒做,`user_version` 停在 1、沒有新表」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-04
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`、`Table session_tunings`
  - 📎 `spec.md` § FR-005、FR-015、FR-016
- [x] T041b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US1-DB-04 通過的程式碼;`user_version` 為 1 時照 `contracts/store.dbml` 開頭的步驟遷移到 2,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T041a)
  - 🧪 `testplan.md` § US1-DB-04
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`、`Table session_tunings`
  - 📎 `spec.md` § FR-005、FR-015、FR-016
- [x] T042a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-05 的測試(兩個庫各讀 `PRAGMA table_info(sessions)`、`PRAGMA table_info(session_transitions)`;遷移後的庫再讀 `PRAGMA index_list(sessions)`、`PRAGMA index_list(session_transitions)`、`PRAGMA foreign_key_list(...)`(`session_transitions`、`download_jobs`、`auto_download_results`)、`PRAGMA foreign_key_check`,再插入一筆 `session_transitions(session_name='cgb-live', at='2026-11-15T08:00:00Z', state='ready')`;分隔註解寫 `# ---- 005 US1-DB-05`),執行確認它因為「照「舊表改名 `sessions_old` → 建新表 → 複製 → DROP 舊表」的順序重建,SQLite 把 `download_jobs`、`session_transitions`、`auto_download_results` 的外鍵改寫成指到 `sessions_old`(節首實測),DROP 之後外鍵指到不存在的表」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-05
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-015、FR-016
- [x] T042b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US1-DB-05 通過的程式碼;重建用「建 `sessions_new` → 複製 → DROP 舊表 → 改名」(`session_transitions` 同法、照原值複製 `id`),不用 `ALTER TABLE ... RENAME` 舊表,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T042a)
  - 🧪 `testplan.md` § US1-DB-05
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-015、FR-016
- [x] T043a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-06 的測試(呼叫 `create_schema(conn)`;關掉連線後以新的 `connect` 開同一個檔(`foreign_keys` 為 0)讀回;分隔註解寫 `# ---- 005 US1-DB-06`),執行確認它因為「遷移沒有先檢查 `PRAGMA foreign_keys` 就 `DROP TABLE sessions`,外鍵開著時 SQLite 對 `session_transitions`、`download_jobs`、`auto_download_results` 做 `ON DELETE CASCADE`,狀態變化紀錄與佇列被刪光、還照常 commit(節首實測讀回 0 筆)」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-06
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-015、FR-016;`plan.md` § 待決問題 Q40
- [x] T043b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US1-DB-06 通過的程式碼;遷移前先讀 `PRAGMA foreign_keys`,開著就丟 `RuntimeError`(訊息含 `foreign_keys`)、不碰任何資料,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T043a)
  - 🧪 `testplan.md` § US1-DB-06
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-015、FR-016;`plan.md` § 待決問題 Q40
- [x] T044a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-07 的測試(呼叫 `create_schema(conn)`;接著 `conn.set_authorizer(None)`,再呼叫一次 `create_schema(conn)`;分隔註解寫 `# ---- 005 US1-DB-07`),執行確認它因為「1 → 2 沒有包在交易裡,或用 `with conn:` 包起來(`connect` 是 `isolation_level=None`,不會開交易),失敗時 `sessions` 已經重建、新表已經建好,下次啟動在 `CREATE TABLE sessions_new` 或 `CREATE TABLE runtime_type_tunings` 就失敗,後端起不來」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-07
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_tunings`
  - 📎 `spec.md` § FR-005、FR-016
- [x] T044b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US1-DB-07 通過的程式碼;1 → 2 包在明寫的 `BEGIN` … `COMMIT`,失敗時 rollback、原例外往上丟,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T044a)
  - 🧪 `testplan.md` § US1-DB-07
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_tunings`
  - 📎 `spec.md` § FR-005、FR-016
- [x] T045a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-08 的測試(以 `connect` 開檔,呼叫一次 `create_schema(conn)`;分隔註解寫 `# ---- 005 US1-DB-08`),執行確認它因為「0 → 1 做完就 return(沿用 004「做完一段就結束」的結構),要第二次啟動才升到 2,這次啟動的後端以 v1 的 schema 寫 `session_tunings` 就失敗」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-08
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_tunings`
  - 📎 `spec.md` § FR-005;`plan.md` § 待決問題 Q41、Q62
- [x] T045b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py`、`tests/integration/test_db_schema.py` 只寫讓 US1-DB-08 通過的程式碼;0 → 1 之後在同一次 `create_schema` 接著跑 1 → 2;同一個任務把 `tests/integration/test_db_schema.py` 斷言 v0 舊庫遷移後 `user_version == 1` 的 `test_舊資料庫升級後保留三筆舊項目且下載項目表與全新庫一致`(第 257 行)、`test_遷移中途失敗時整個還原_原例外往上丟_下次啟動可再升級`(第 369 行)、`test_升級過的資料庫再啟動一次不重跑遷移_項目的所屬工作階段不變`(第 396 行)、`test_從沒開過工作階段的舊資料庫也升級_sessions_表在就是舊庫`(第 416 行)、`test_舊資料庫有只差大小寫的排隊項目時留_id_最小的並把刪掉的名稱寫進日誌`(第 460 行)、`test_舊資料庫有只差大小寫的精選名稱時留_id_最小的並把刪掉的名稱寫進日誌`(第 738 行)改成 2,執行全部測試確認都通過、不留 skip,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T045a)
  - 🧪 `testplan.md` § US1-DB-08
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_tunings`
  - 📎 `spec.md` § FR-005;`plan.md` § 待決問題 Q41、Q62
- [x] T046a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-09 的測試(呼叫 `create_schema(conn)`;接著 `conn.set_authorizer(None)`,再呼叫一次 `create_schema(conn)`;分隔註解寫 `# ---- 005 US1-DB-09`),執行確認它因為「0 → 1 與 1 → 2 包在同一個交易裡,1 → 2 失敗時連 0 → 1 也 rollback,停在 0(store.dbml:兩個交易,1 → 2 失敗停在 1)」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-09
  - ⚙ `contracts/store.dbml` § `Table sessions`
  - 📎 `spec.md` § FR-005
- [x] T046b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US1-DB-09 通過的程式碼;0 → 1 與 1 → 2 是兩個交易,1 → 2 失敗時停在 1,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T046a)
  - 🧪 `testplan.md` § US1-DB-09
  - ⚙ `contracts/store.dbml` § `Table sessions`
  - 📎 `spec.md` § FR-005
- [x] T047a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US1-DB-10 的測試(A:`conn.close()`,以新的 `connect` 開同一個檔,再呼叫 `create_schema(conn)`(後端重新啟動);B:呼叫 `create_schema(conn)`;分隔註解寫 `# ---- 005 US1-DB-10`);T041b 讓 `user_version` 已是 2 的庫不再跑遷移(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「已經是 2 的庫每次啟動都重跑 1 → 2 的某一步(例如 `DROP TABLE IF EXISTS session_tunings` 再建),後端重啟後開啟那一筆不見,工作階段頁與紀錄看不到這次量到的設定(驗收情境 5)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US1-DB-10
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-005、使用者故事 1 驗收情境 5
- [x] T047b [US1] 🟢 /tdd 綠燈:US1-DB-10 由 T041b 讓 `user_version` 已是 2 的庫不再跑遷移(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US1-DB-10 通過的程式碼(依賴 T047a)
  - 🧪 `testplan.md` § US1-DB-10
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-005、使用者故事 1 驗收情境 5
- [x] T048a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US1-DB-11 的測試(呼叫 `create_schema(conn)`,再讀 `cgb-odd` 的 `sessions.end_reason` 與它的 `session_transitions.end_reason`;分隔註解寫 `# ---- 005 US1-DB-11`);T042b 照 `contracts/store.dbml` 重建 `sessions_new`、`session_transitions_new`,不補 `end_reason` 的 CHECK(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「趁重建在 `sessions_new` 或 `session_transitions_new` 補了 `end_reason IN (...)` 的 CHECK(Q22 定為不補),既有資料只要有一筆不在清單裡,`INSERT ... SELECT` 就丟 `IntegrityError`、整個遷移 rollback,之後每次啟動都失敗、後端起不來」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US1-DB-11
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-016、FR-015;`plan.md` § 待決問題 Q22
- [x] T048b [US1] 🟢 /tdd 綠燈:US1-DB-11 由 T042b 照 `contracts/store.dbml` 重建 `sessions_new`、`session_transitions_new`,不補 `end_reason` 的 CHECK(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US1-DB-11 通過的程式碼(依賴 T048a)
  - 🧪 `testplan.md` § US1-DB-11
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-016、FR-015;`plan.md` § 待決問題 Q22
- [x] T049 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T038b~T048b 記下的重構清單(範圍限 `src/cgb/db/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_db_schema.py` 的斷言(依賴 T048b)
  - 🧪 `testplan.md` § US1-DB-01~US1-DB-11
  - 📎 `testplan.md` § 2.3

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(Playwright)接測試行程內真的後端(`tests/e2e/conftest.py` 的 `e2e_servers`,UI 127.0.0.1:8781),轉接層用替身;e2e 用固定 port,同一時間只跑一份

- [x] T050a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us1_tuning.py` 寫 US1-AJ-01 的測試(使用者在開啟畫面選 A100 開啟,等到就緒;分隔註解寫 `# ---- 005 US1-AJ-01`),執行確認它因為「設定卡顯示 GPU 類型名稱查表的值而不是量到的顯示記憶體算出的值;來源標成手動」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `prototype/index.html` § `[data-state="starting"]`、`[data-state="ready"]`、`#t-summary`、`#t-hardware`、`#t-table`、`#t-rows`、`.tuning-summary`、`.tuning-table`、`.tuning-fixed`;`contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § FR-002、FR-004;`research.md` § R11;`plan.md` § 待決問題 Q16
- [x] T050b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js`、`src/cgb/static/js/view.js`、`src/cgb/static/style.css` 只寫讓 US1-AJ-01 通過的程式碼;工作階段頁加 Ollama 設定卡:量到的顯示記憶體與系統記憶體、三項設定與來源,flash attention 與 KV cache 標固定開啟、沒有欄位;級距與來源的顯示文字放在 `src/cgb/static/js/view.js`;同一個任務把 `prototype/style.css` 的「005:Ollama 設定」區段(第 1199 行起)搬進 `src/cgb/static/style.css`,只用既有的 `var(--…)`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T050a)
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `prototype/index.html` § `[data-state="starting"]`、`[data-state="ready"]`、`#t-summary`、`#t-hardware`、`#t-table`、`#t-rows`、`.tuning-summary`、`.tuning-table`、`.tuning-fixed`;`contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § FR-002、FR-004;`research.md` § R11;`plan.md` § 待決問題 Q16
- [x] T051a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us1_tuning.py` 寫 US1-AJ-02 的測試(使用者開 T4 到就緒;分隔註解寫 `# ---- 005 US1-AJ-02`),執行確認它因為「讀不到時讓開啟失敗;設定卡空白、沒有說明」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `prototype/index.html` § `[data-state="ready-no-vram"]`、`[data-state="ready-unknown-tuning"]`、`[data-state="ready"]`
  - 📎 `spec.md` § FR-003、FR-004;`plan.md` § 待決問題 Q57
- [x] T051b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js`、`src/cgb/static/js/view.js` 只寫讓 US1-AJ-02 通過的程式碼;讀不到顯示記憶體時設定卡說明「讀不到顯示記憶體,使用 Ollama 預設值」;`tuning` 為 null(005 之前開的)時照原型 `ready-unknown-tuning` 說明(這個狀態沒有案例斷言,完成報告列為未直接驗證,`plan.md` § 待決問題 Q57),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T051a)
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `prototype/index.html` § `[data-state="ready-no-vram"]`、`[data-state="ready-unknown-tuning"]`、`[data-state="ready"]`
  - 📎 `spec.md` § FR-003、FR-004;`plan.md` § 待決問題 Q57
- [x] T052a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us1_tuning.py` 寫 US1-AJ-03 的測試(使用者到紀錄頁點這一筆工作階段;分隔註解寫 `# ---- 005 US1-AJ-03`),執行確認它因為「紀錄頁沒有呈現 Ollama 設定;只呈現最後一筆以外的資料」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `prototype/history.html` § `[data-state="normal"]`、`[data-state="tuning-log"]`、`[data-state="empty"]`、`#rows`、`#d-body`、`.tuning-table`;`contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`
  - 📎 `spec.md` § FR-005;`plan.md` § 待決問題 Q57
- [x] T052b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/history.html`、`src/cgb/static/js/history.js`、`src/cgb/static/js/view.js` 只寫讓 US1-AJ-03 通過的程式碼;紀錄頁的明細列出每一筆 Ollama 設定(觸發、時間、量到的硬體、三項與來源、結果);`empty` 沿用 001、這一輪不改,完成報告列為未直接驗證(`plan.md` § 待決問題 Q57),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T052a)
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `prototype/history.html` § `[data-state="normal"]`、`[data-state="tuning-log"]`、`[data-state="empty"]`、`#rows`、`#d-body`、`.tuning-table`;`contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`
  - 📎 `spec.md` § FR-005;`plan.md` § 待決問題 Q57
- [x] T053 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T050b~T052b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T052b)
  - 🧪 `testplan.md` § US1-AJ-01~US1-AJ-03
  - 📎 `testplan.md` § 2.4

### 介面覆蓋(US1)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui-events.asyncapi.yaml` § `operations.sendSessionUpdated` | T023b | T023a |
| `colab-cli.openapi.yaml` § `paths./exec/start-ollama.post` | T002b~T018b | T002a~T018a |
| `ui.openapi.yaml` § `paths./session.get` | T021b~T025b、T027b~T028b、T030b、T050b | T021a~T025a、T027a~T028a、T030a、T050a |
| `ui.openapi.yaml` § `paths./session.post` | T021b~T027b | T021a~T027a |
| `ui.openapi.yaml` § `paths./sessions/{name}.get` | T024b~T030b、T052b | T024a~T030a、T052a |
| `store.dbml` § `Table sessions` | T038b、T041b~T046b、T048b | T038a、T041a~T046a、T048a |
| `store.dbml` § `Table session_transitions` | T038b、T041b~T043b、T048b | T038a、T041a~T043a、T048a |
| `store.dbml` § `Table runtime_type_tunings` | T038b | T038a |
| `store.dbml` § `Table session_tunings` | T038b~T041b、T044b~T045b、T047b | T038a~T041a、T044a~T045a、T047a |
| `store.dbml` § `Table session_tuning_models` | T038b | T038a |
| `history.html` § `[data-state="normal"]` | T052b | T052a |
| `history.html` § `[data-state="tuning-log"]` | T052b | T052a |
| `history.html` § `[data-state="empty"]` | T052b | T052a |
| `index.html` § `[data-state="starting"]` | T050b | T050a |
| `index.html` § `[data-state="ready"]` | T050b~T051b | T050a~T051a |
| `index.html` § `[data-state="ready-no-vram"]` | T051b | T051a |
| `index.html` § `[data-state="ready-unknown-tuning"]` | T051b | T051a |

### 測試案例覆蓋(US1)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US1-CLI-01、US1-CLI-05、US1-CLI-02~US1-CLI-04、US1-CLI-06~US1-CLI-17 | T002a~T018a | T002b~T018b | T019 |
| US1-CLI-18 | — | — | T020(📏) |
| US1-API-01~US1-API-16 | T021a~T036a | T021b~T036b | T037 |
| US1-DB-01~US1-DB-11 | T038a~T048a | T038b~T048b | T049 |
| US1-AJ-01~US1-AJ-03 | T050a~T052a | T050b~T052b | T053 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 再加 `uv run pytest -m realrun_local -q -p no:cacheprovider` 全綠(含 T004b 刪掉的兩支 001 測試已不在、`tests/integration/test_db_schema.py` 的 8 處 `user_version` 已改成 2);重構任務前後的測試結果相同;`specs/005-ollama-machine-tuning/measurements.md` 有 US1-CLI-18 的數字

---

## Phase 3: User Story 2 - 開啟前手動覆蓋設定,並依 GPU 類型記住 (Priority: P2)

**Goal**: 開啟畫面的「Ollama 設定」可以填平行數、context 長度與同時載入模型數(留空 = 自動),填了的項目覆蓋自動值帶給遠端;填過的值依 GPU 類型記住、下次預先填入,「全部改回自動」開啟時清除;超出範圍時擋下、不開啟、不記住

**Independent Test**: 照 `testplan.md` § 3 的全部案例:E5 以 `uv run pytest tests/integration/test_colab_cli.py` 與 `uv run pytest -m realrun_local tests/integration/test_ollama_scripts.py`、E2 以 `uv run pytest tests/integration/test_api_tuning.py tests/unit/test_tuning.py`、E4 以 `uv run pytest tests/integration/test_db_schema.py`、跨端點驗收以 `uv run pytest tests/e2e/test_005_us2_overrides.py` 執行全綠

### E5 Colab CLI(`colab exec` 遠端腳本)

> E5、E2、E4 三節平行;檔案範圍與護欄同故事 1 的 E5 節。`box.run` 一次跑好幾步時各步在同一個 kernel 子行程依序執行(`testplan.md` § 3.1);覆蓋值的字串格式是 `^[0-9]+$` 再比範圍(`plan.md` § 待決問題 Q49)

- [x] T054a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US2-CLI-01 的測試(呼叫 `start_ollama(name="cgb-test-0001", overrides={"numParallel": 4, "contextLength": None, "maxLoadedModels": None})`;分隔註解寫 `# ---- 005 US2-CLI-01`),執行確認它因為「只帶填了的那一項,沒填的兩項 kernel 留著上一次的覆蓋值被腳本讀到」這類實作而失敗
  - 🧪 `testplan.md` § US2-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-007
- [x] T054b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py` 只寫讓 US2-CLI-01 通過的程式碼;覆蓋值的整數轉成十進位字串帶進 `CGB_TUNE_*`,沒填的仍是空字串,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T054a)
  - 🧪 `testplan.md` § US2-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-007
- [x] T055a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US2-CLI-02 的測試(依序呼叫 `start_ollama` 帶 `{"numParallel": 32, "contextLength": 131072, "maxLoadedModels": 4}` 與 `{"numParallel": 1, "contextLength": 2048, "maxLoadedModels": 1}`;分隔註解寫 `# ---- 005 US2-CLI-02`),執行確認它因為「範圍用 `<` 判斷,上限 32、131072、4 或下限 1、2048、1 被擋成 `COLAB_INVALID_TUNING`」這類實作而失敗
  - 🧪 `testplan.md` § US2-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-007、FR-017;`plan.md` § 待決問題 Q3
- [x] T055b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py` 只寫讓 US2-CLI-02 通過的程式碼;呼叫 `colab` 之前先檢查範圍(平行數 1~32、context 2048~131072、同時載入 1~4,含上下限),不符丟 `COLAB_INVALID_TUNING`、不呼叫 `colab`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T055a)
  - 🧪 `testplan.md` § US2-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-007、FR-017;`plan.md` § 待決問題 Q3
- [x] T056a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US2-CLI-03 的測試(每種各呼叫一次 `start_ollama(name="cgb-test-0001", overrides=<那一種>)`;分隔註解寫 `# ---- 005 US2-CLI-03`),執行確認它因為「以 `isinstance(value, int)` 檢查,`True` 通過後代成 `CGB_TUNE_NUM_PARALLEL=True`」這類實作而失敗
  - 🧪 `testplan.md` § US2-CLI-03
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.Error`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-017
- [x] T056b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py` 只寫讓 US2-CLI-03 通過的程式碼;只收 `int` 而且不是 `bool` 的值,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T056a)
  - 🧪 `testplan.md` § US2-CLI-03
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.Error`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-017
- [x] T057a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US2-CLI-04 的測試(呼叫 `start_ollama(name="cgb-test-0001", overrides={"numParallel": 4, "contextLength": None, "maxLoadedModels": None})`;分隔註解寫 `# ---- 005 US2-CLI-04`),執行確認它因為「照現況所有 `ok: false` 都歸成 `COLAB_REMOTE_ERROR`」這類實作而失敗
  - 🧪 `testplan.md` § US2-CLI-04
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.Error`、`components.schemas.ScriptStage`
  - 📎 `spec.md` § FR-017;`plan.md` § 待決問題 Q3
- [x] T057b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py` 只寫讓 US2-CLI-04 通過的程式碼;遠端回 `stage: input` 時歸 `COLAB_INVALID_TUNING`(`remote_stage` 為 `input`),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T057a)
  - 🧪 `testplan.md` § US2-CLI-04
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaInput`、`components.schemas.OllamaStarted`、`components.schemas.Error`、`components.schemas.ScriptStage`
  - 📎 `spec.md` § FR-017;`plan.md` § 待決問題 Q3
- [x] T058a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US2-CLI-05 的測試(`box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US2-CLI-05`),執行確認它因為「有一個覆蓋值就三項都改用覆蓋值、沒填的兩項變成 Ollama 預設」這類實作而失敗
  - 🧪 `testplan.md` § US2-CLI-05
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 1;`research.md` § R7;`plan.md` § 待決問題 Q49
- [x] T058b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US2-CLI-05 通過的程式碼;`CGB_TUNE_*` 有值的項目(`^[0-9]+$` 再比範圍)取代級距、來源 `manual`,沒值的照級距、來源 `auto`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T058a)
  - 🧪 `testplan.md` § US2-CLI-05
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 1;`research.md` § R7;`plan.md` § 待決問題 Q49
- [x] T059a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_ollama_scripts.py` 寫 US2-CLI-06 的測試(`box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US2-CLI-06`);T058b 只看 `CGB_TUNE_*` 有沒有值決定來源(`src/cgb/adapters/scripts/start_ollama.py`),不和級距比已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「覆蓋值和級距相同時把來源標成 `auto`,使用者明確填的值在畫面上變成自動」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US2-CLI-06
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、邊界情況(覆蓋值和自動值相同)
- [x] T059b [US2] 🟢 /tdd 綠燈:US2-CLI-06 由 T058b 只看 `CGB_TUNE_*` 有沒有值決定來源(`src/cgb/adapters/scripts/start_ollama.py`),不和級距比滿足,確認 `src/cgb/adapters/scripts/start_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US2-CLI-06 通過的程式碼(依賴 T059a)
  - 🧪 `testplan.md` § US2-CLI-06
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、邊界情況(覆蓋值和自動值相同)
- [x] T060a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_ollama_scripts.py` 寫 US2-CLI-07 的測試(`box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US2-CLI-07`);T058b 照覆蓋值原樣套用、不估算顯示記憶體(`src/cgb/adapters/scripts/start_ollama.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「腳本估算顯示記憶體放不下,把覆蓋值壓回級距(FR-017:不估算)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US2-CLI-07
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、FR-017
- [x] T060b [US2] 🟢 /tdd 綠燈:US2-CLI-07 由 T058b 照覆蓋值原樣套用、不估算顯示記憶體(`src/cgb/adapters/scripts/start_ollama.py`)滿足,確認 `src/cgb/adapters/scripts/start_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US2-CLI-07 通過的程式碼(依賴 T060a)
  - 🧪 `testplan.md` § US2-CLI-07
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、FR-017
- [x] T061a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US2-CLI-08 的測試(`box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US2-CLI-08`),執行確認它因為「讀不到顯示記憶體就整組照 FR-003 不帶,連覆蓋值也丟掉」這類實作而失敗
  - 🧪 `testplan.md` § US2-CLI-08
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 5
- [x] T061b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US2-CLI-08 通過的程式碼;讀不到顯示記憶體時只帶填了的項目與 `OLLAMA_FLASH_ATTENTION`、`OLLAMA_KV_CACHE_TYPE`,沒填的兩項來源 `ollama_default`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T061a)
  - 🧪 `testplan.md` § US2-CLI-08
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 5
- [x] T062a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US2-CLI-09 的測試(每種各 `box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US2-CLI-09`),執行確認它因為「照 004 以 `env=dict(os.environ)` 原樣繼承,kernel 裡的舊值跟著帶給 serve(research.md R7)」這類實作而失敗
  - 🧪 `testplan.md` § US2-CLI-09
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、FR-003、邊界情況(同名環境變數);`research.md` § R7
- [x] T062b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US2-CLI-09 通過的程式碼;serve 的環境以 kernel 的環境去掉所有 `OLLAMA_NUM_PARALLEL`、`OLLAMA_CONTEXT_LENGTH`、`OLLAMA_MAX_LOADED_MODELS`、`OLLAMA_FLASH_ATTENTION`、`OLLAMA_KV_CACHE_TYPE` 後,再加這次決定的值(同一個變數只出現一次),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T062a)
  - 🧪 `testplan.md` § US2-CLI-09
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、FR-003、邊界情況(同名環境變數);`research.md` § R7
- [x] T063a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US2-CLI-10 的測試(同一個 kernel 依序跑兩步:`start_ollama.py` 帶 `CGB_TUNE_NUM_PARALLEL=4`;`restart_ollama.py` 三個 `CGB_TUNE_*` 都是空字串;之後讀 kernel 的 `os.environ`;分隔註解寫 `# ---- 005 US2-CLI-10`),執行確認它因為「腳本把決定的值寫進 kernel 的 `os.environ` 再讓 `Popen` 繼承,改回自動之後新的 serve 仍是平行數 4(合約共用約定 12 (d))」這類實作而失敗
  - 🧪 `testplan.md` § US2-CLI-10
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`paths./exec/restart-ollama.post`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、FR-003;`research.md` § R1、R7;`plan.md` § 待決問題 Q58
- [x] T063b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py`、`src/cgb/adapters/scripts/restart_ollama.py` 只寫讓 US2-CLI-10 通過的程式碼;建立 `src/cgb/adapters/scripts/restart_ollama.py`,只做到讓 US2-CLI-10 通過的最小版本:停掉 pid 檔指的 serve,再以三個 `CGB_TUNE_*` 照 `start_ollama.py` 的同一套規則組環境啟動(遠端腳本各自是單一檔,組環境的程式兩檔各寫一份;停止、驗證與其他失敗的行為由故事 3 的 E5 節擴充);兩支腳本都不把決定的值寫回 kernel 的 `os.environ`(合約共用約定 12 (d)),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T063a)
  - 🧪 `testplan.md` § US2-CLI-10
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`paths./exec/restart-ollama.post`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、FR-003;`research.md` § R1、R7;`plan.md` § 待決問題 Q58
- [x] T064a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US2-CLI-11 的測試(每種各 `box.run([start_ollama.py])`;分隔註解寫 `# ---- 005 US2-CLI-11`),執行確認它因為「先量硬體、安裝、刪狀態檔或啟動才檢查覆蓋值」這類實作而失敗
  - 🧪 `testplan.md` § US2-CLI-11
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`、`components.schemas.ScriptStage`
  - 📎 `spec.md` § FR-017;`plan.md` § 待決問題 Q49
- [x] T064b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US2-CLI-11 通過的程式碼;一開始先檢查三個 `CGB_TUNE_*`(`^[0-9]+$` 再比範圍),不符回 `stage: input`、`detail` 含變數名稱,不量硬體、不安裝、不刪狀態檔、不啟動,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T064a)
  - 🧪 `testplan.md` § US2-CLI-11
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.StartOllamaScriptResult`、`components.schemas.AppliedTuning`、`components.schemas.ScriptStage`
  - 📎 `spec.md` § FR-017;`plan.md` § 待決問題 Q49
- [x] T065 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T054b~T064b 記下的重構清單(範圍限 `src/cgb/adapters/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_colab_cli.py`、`tests/integration/test_ollama_scripts.py` 的斷言(依賴 T064b)
  - 🧪 `testplan.md` § US2-CLI-01~US2-CLI-11
  - 📎 `testplan.md` § 3.1

### E2 後端 UI API(FastAPI REST 與 SSE)

> 不改 `src/cgb/db/schema.py`(`runtime_type_tunings` 已由故事 1 的 T038b 建立)。類型覆蓋值受理時寫、開啟失敗不還原(`plan.md` § 待決問題 Q9),三個 null 開啟時刪列清除(Q8、Q23);範圍的每個邊界在單元案例 US2-API-16~22 驗,整合案例只驗 api 接上同一個檢查

- [x] T066a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US2-API-01 的測試(`open_with(ui_client, A100, tuning_body(4, None, None))`,等 `ready`;`GET /api/session`、`GET /api/sessions/{name}`;分隔註解寫 `# ---- 005 US2-API-01`);同一個任務在檔內新增 `testplan.md` § 3.2 的 `tuning_body`、`NONE3`、`open_with`、`overrides`、`remember`、`log_out`,執行確認它因為「api 解析了 `runtimeType` 卻沒把 `tuning` 交給 `start_ollama`(遠端收到三個空字串,全部是自動)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 1、使用者故事 2 獨立測試
- [x] T066b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US2-API-01 通過的程式碼;`openSession` 接受 `tuning`,交給 `start_ollama(name, overrides)`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T066a)
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 1、使用者故事 2 獨立測試
- [x] T067a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US2-API-02 的測試(`open_with(ui_client, A100, tuning_body(4, None, None))`;等閘門被走到時 `GET /api/tuning/overrides`;放行閘門,`wait_for_state(ui_client, "open_failed")`,再 `GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US2-API-02`),執行確認它因為「等 `startOllama` 成功或就緒後才寫入(Q9 已決定受理時寫)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-018、FR-008;`research.md` § R9;`plan.md` § 待決問題 Q9
- [x] T067b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/repos/tunings.py`、`src/cgb/api/tuning.py`、`src/cgb/api/__init__.py` 只寫讓 US2-API-02 通過的程式碼;受理時以這次的三個值寫入這種類型的覆蓋值(`updatedAt` 是受理的時間,`src/cgb/repos/tunings.py`);新增 `getTuningOverrides`(`src/cgb/api/tuning.py`,在 `src/cgb/api/__init__.py` 註冊路由)回 `items`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T067a)
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-018、FR-008;`research.md` § R9;`plan.md` § 待決問題 Q9
- [x] T068a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US2-API-03 的測試(送 `POST /api/session`(`{"runtimeType": A100}`,沒有 `tuning`),等 `ready`;記下 `sent_overrides(fakes)`;`GET /api/tuning/overrides`、`GET /api/sessions/{name}`;再 `DELETE /api/session` 等 `ended`,送 `POST /api/session`(`{"runtimeType": T4}`,沒有 `tuning`)等 `ready`,記下 `sent_overrides(fakes)`;分隔註解寫 `# ---- 005 US2-API-03`),執行確認它因為「沒有帶 `tuning` 時一律當成三個 null(記住的值只在 UI 預先填入,UI 沒填時就失效)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-008、FR-018、使用者故事 2 驗收情境 2
- [x] T068b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 只寫讓 US2-API-03 通過的程式碼;沒帶 `tuning` 時改用這種類型記住的值,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T068a)
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-008、FR-018、使用者故事 2 驗收情境 2
- [x] T069a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US2-API-04 的測試(`open_with(ui_client, A100, NONE3)`,等 `ready`;`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US2-API-04`),執行確認它因為「把三個 null 的 `tuning` 和「沒有帶 `tuning`」當成同一種,改用記住的 4/16384/2 開啟、也沒清除」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-009、使用者故事 2 驗收情境 3;`plan.md` § 待決問題 Q8、Q23
- [x] T069b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 只寫讓 US2-API-04 通過的程式碼;`tuning` 三個都是 null 時清除這種類型的覆蓋值:刪掉那一列,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T069a)
  - 🧪 `testplan.md` § US2-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-009、使用者故事 2 驗收情境 3;`plan.md` § 待決問題 Q8、Q23
- [x] T070a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_tuning.py` 寫 US2-API-05 的測試(`open_with(ui_client, L4, tuning_body(2, None, None))`,等 `ready`;`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US2-API-05`);T067b 以這次的三個值整份寫入(`src/cgb/repos/tunings.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「逐欄合併(只覆寫這次有值的欄位),上一次的 16384 留下來;合約寫的是「以這次的三個值整份取代」」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US2-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-018(只記填了的項目)
- [x] T070b [US2] 🟢 /tdd 綠燈:US2-API-05 由 T067b 以這次的三個值整份寫入(`src/cgb/repos/tunings.py`)滿足,確認 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 只寫讓 US2-API-05 通過的程式碼(依賴 T070a)
  - 🧪 `testplan.md` § US2-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-018(只記填了的項目)
- [x] T071a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_tuning.py` 寫 US2-API-06 的測試(以同一個 SQLite 檔 `running(make_app())` 跑第二個 app,`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US2-API-06`);T067b 把覆蓋值寫進 SQLite 的 `runtime_type_tunings`(`src/cgb/repos/tunings.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「覆蓋值放在 service 的記憶體 dict,重新啟動後全部消失」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US2-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-018
- [x] T071b [US2] 🟢 /tdd 綠燈:US2-API-06 由 T067b 把覆蓋值寫進 SQLite 的 `runtime_type_tunings`(`src/cgb/repos/tunings.py`)滿足,確認 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 只寫讓 US2-API-06 通過的程式碼(依賴 T071a)
  - 🧪 `testplan.md` § US2-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-018
- [x] T072a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_tuning.py` 寫 US2-API-07 的測試(`open_with(ui_client, A100, tuning_body(8, None, None))`(8 剛好是 A100 40 GiB 的自動值),等 `ready`;`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US2-API-07`);T066b 把覆蓋值原樣交給轉接層、不和自動值比較,T067b 原樣寫入已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「api 依 GPU 類型查表,把和自動值相同的覆蓋值正規化成 None,沒有傳給遠端也沒有記住(spec 邊界情況:仍標手動並記住)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US2-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § 邊界情況(覆蓋值和自動值相同)、FR-018
- [x] T072b [US2] 🟢 /tdd 綠燈:US2-API-07 由 T066b 把覆蓋值原樣交給轉接層、不和自動值比較,T067b 原樣寫入滿足,確認 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 只寫讓 US2-API-07 通過的程式碼(依賴 T072a)
  - 🧪 `testplan.md` § US2-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § 邊界情況(覆蓋值和自動值相同)、FR-018
- [x] T073a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_tuning.py` 寫 US2-API-08 的測試(`open_with(ui_client, A100, tuning_body(4, None, None))`,`wait_for_state(ui_client, "ready")`;`GET /api/session`;分隔註解寫 `# ---- 005 US2-API-08`);T021b 原樣存下遠端回報的 `tuning`(`src/cgb/services/session_lifecycle.py`),不依 `vramTotalBytes` 改寫已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`machine.vramTotalBytes` 為 null 時後端把五項一律改寫成 `ollama_default`(蓋掉遠端回報的手動 4)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US2-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 5
- [x] T073b [US2] 🟢 /tdd 綠燈:US2-API-08 由 T021b 原樣存下遠端回報的 `tuning`(`src/cgb/services/session_lifecycle.py`),不依 `vramTotalBytes` 改寫滿足,確認 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 只寫讓 US2-API-08 通過的程式碼(依賴 T073a)
  - 🧪 `testplan.md` § US2-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 5
- [x] T074a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US2-API-09 的測試(`open_with(ui_client, A100, 那一組)`;`GET /api/tuning/overrides`、`GET /api/session`;分隔註解寫 `# ---- 005 US2-API-09`),執行確認它因為「交給 FastAPI 以 Pydantic 的 `ge`/`le` 驗證,回 422 與英文的 `detail`」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`
  - 📎 `spec.md` § FR-017、使用者故事 2 驗收情境 4(openSession 的 INVALID_NUM_PARALLEL、INVALID_CONTEXT_LENGTH、INVALID_MAX_LOADED_MODELS);`plan.md` § 待決問題 Q31
- [x] T074b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py`、`src/cgb/api/session.py`、`src/cgb/domain/errors.py`、`tests/e2e/test_locale.py` 只寫讓 US2-API-09 通過的程式碼;新增 `parse_overrides(body)`(不符丟 `ApiError(400, code)`),`openSession` 在開啟前呼叫它;新代碼 `INVALID_NUM_PARALLEL`、`INVALID_CONTEXT_LENGTH`、`INVALID_MAX_LOADED_MODELS` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同樣三個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T074a)
  - 🧪 `testplan.md` § US2-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`
  - 📎 `spec.md` § FR-017、使用者故事 2 驗收情境 4(openSession 的 INVALID_NUM_PARALLEL、INVALID_CONTEXT_LENGTH、INVALID_MAX_LOADED_MODELS);`plan.md` § 待決問題 Q31
- [x] T075a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US2-API-10 的測試(依序送 7 個 `POST /api/session`(前 6 個各自被擋,不會開啟):(a)`tuning` 是字串 `"4"`;(b)`tuning` 是 `{"numParallel": 4, "contextLength": None}`(少了 `maxLoadedModels`);(c)`numParallel` 是 `True`;(d)`numParallel` 是字串 `"4"`;(e)`tuning_body(0, 1, 0)`;(f)`runtimeType` 為 `{"gpu": "V100", "highMem": False}`、`tuning` 為 `tuning_body(4, None, None)`;(g)`open_with(ui_client, A100, {"numParallel": 4.0, "contextLength": None, "maxLoadedModels": None})`;分隔註解寫 `# ---- 005 US2-API-10`),執行確認它因為「少了欄位時當成 null 照常開啟」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`
  - 📎 `spec.md` § FR-017(openSession 的 INVALID_REQUEST_BODY、INVALID_RUNTIME_TYPE、INVALID_NUM_PARALLEL);`plan.md` § 待決問題 Q31
- [x] T075b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py`、`src/cgb/api/session.py` 只寫讓 US2-API-10 通過的程式碼;`tuning` 不是物件或少了鍵時回 400 `INVALID_REQUEST_BODY`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T075a)
  - 🧪 `testplan.md` § US2-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`
  - 📎 `spec.md` § FR-017(openSession 的 INVALID_REQUEST_BODY、INVALID_RUNTIME_TYPE、INVALID_NUM_PARALLEL);`plan.md` § 待決問題 Q31
- [x] T076a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US2-API-11 的測試(送 `POST /api/session/restart`(那一組本文);等 0.2 秒,`GET /api/session`、`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US2-API-11`),執行確認它因為「`restartSession` 只驗 `runtimeType`、沒驗 `tuning`,先結束舊的 T4,新的在 `start_ollama` 才因 `COLAB_INVALID_TUNING` 開啟失敗(使用者失去原本可用的工作階段)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`
  - 📎 `spec.md` § FR-017(restartSession 的 INVALID_NUM_PARALLEL、INVALID_CONTEXT_LENGTH、INVALID_MAX_LOADED_MODELS、INVALID_REQUEST_BODY、INVALID_RUNTIME_TYPE)
- [x] T076b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/runtime_switch.py` 只寫讓 US2-API-11 通過的程式碼;`restartSession` 在結束舊的工作階段之前先 `parse_overrides`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T076a)
  - 🧪 `testplan.md` § US2-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`
  - 📎 `spec.md` § FR-017(restartSession 的 INVALID_NUM_PARALLEL、INVALID_CONTEXT_LENGTH、INVALID_MAX_LOADED_MODELS、INVALID_REQUEST_BODY、INVALID_RUNTIME_TYPE)
- [x] T077a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US2-API-12 的測試(`open_with(ui_client, L4, tuning_body(4, None, None))`;`GET /api/tuning/overrides`(結束中那一種在放行閘門之前讀);分隔註解寫 `# ---- 005 US2-API-12`),執行確認它因為「一解析完本文就寫入類型覆蓋值,之後才做 001 的 409 檢查;使用者被擋下時以為沒開成,下次選 L4 卻預先填了 4(Q9:受理時才寫)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`
  - 📎 `spec.md` § FR-018(openSession 的 SESSION_ALREADY_ACTIVE、SESSION_ENDING、AUTH_REQUIRED);`plan.md` § 待決問題 Q9
- [x] T077b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/session_lifecycle.py`、`src/cgb/api/session.py`、`src/cgb/repos/tunings.py` 只寫讓 US2-API-12 通過的程式碼;通過 001 的 409 檢查、受理之後才寫入類型覆蓋值,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T077a)
  - 🧪 `testplan.md` § US2-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`
  - 📎 `spec.md` § FR-018(openSession 的 SESSION_ALREADY_ACTIVE、SESSION_ENDING、AUTH_REQUIRED);`plan.md` § 待決問題 Q9
- [x] T078a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US2-API-13 的測試(送 `POST /api/session/restart`(`{"runtimeType": L4, "tuning": tuning_body(4, None, None)}`);`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US2-API-13`),執行確認它因為「變更類型的路由在呼叫 `RuntimeSwitch.restart` 之前就寫入新類型的覆蓋值,被 409 擋下也留著」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`
  - 📎 `spec.md` § FR-018(restartSession 的 NO_ACTIVE_SESSION、SESSION_ENDING、AUTH_REQUIRED);`plan.md` § 待決問題 Q9
- [x] T078b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/runtime_switch.py`、`src/cgb/repos/tunings.py` 只寫讓 US2-API-13 通過的程式碼;`restartSession` 被 409 擋下時不寫入類型覆蓋值,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T078a)
  - 🧪 `testplan.md` § US2-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`
  - 📎 `spec.md` § FR-018(restartSession 的 NO_ACTIVE_SESSION、SESSION_ENDING、AUTH_REQUIRED);`plan.md` § 待決問題 Q9
- [x] T079a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US2-API-14 的測試(送 `POST /api/session/restart`(`{"runtimeType": A100}`,沒有 `tuning`),`wait_until` 新的工作階段 `ready`;`GET /api/session`、`GET /api/sessions/{old}`、`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US2-API-14`),執行確認它因為「變更類型沿用舊工作階段的 `requested`(把 T4 的 context 8192 帶到 A100)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`、`paths./session/restart.post`
  - 📎 `spec.md` § 邊界情況(變更執行階段類型)、FR-008、FR-005
- [x] T079b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/runtime_switch.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US2-API-14 通過的程式碼;變更類型時新的工作階段不沿用舊的覆蓋值;沒帶 `tuning` 時用新類型記住的值,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T079a)
  - 🧪 `testplan.md` § US2-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`、`paths./session/restart.post`
  - 📎 `spec.md` § 邊界情況(變更執行階段類型)、FR-008、FR-005
- [x] T080a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning.py` 寫 US2-API-15 的測試(送 `POST /api/session/restart`(`{"runtimeType": A100, "tuning": tuning_body(None, None, 2)}`);回應後立刻 `GET /api/tuning/overrides`;放行閘門,等新的 `ready`;分隔註解寫 `# ---- 005 US2-API-15`),執行確認它因為「變更類型把覆蓋值寫到目前(舊)工作階段的類型 T4」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-018、FR-009、邊界情況(變更執行階段類型);`plan.md` § 待決問題 Q9
- [x] T080b [US2] 🟢 /tdd 綠燈:在 `src/cgb/services/runtime_switch.py`、`src/cgb/repos/tunings.py` 只寫讓 US2-API-15 通過的程式碼;變更類型帶的覆蓋值寫到新的類型,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T080a)
  - 🧪 `testplan.md` § US2-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-018、FR-009、邊界情況(變更執行階段類型);`plan.md` § 待決問題 Q9
- [x] T081a [US2] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US2-API-16 的測試(依序以 `numParallel` 為 1、32、0、33(另兩項 None)呼叫;分隔註解寫 `# ---- 005 US2-API-16`),執行確認它因為「上限寫成 `< 32`,32 被擋」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.TuningOverrides`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017;`plan.md` § 待決問題 Q31
- [x] T081b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US2-API-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T081a)
  - 🧪 `testplan.md` § US2-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.TuningOverrides`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017;`plan.md` § 待決問題 Q31
- [x] T082a [US2] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US2-API-17 的測試(依序以 `contextLength` 為 2048、131072、2047、131073(另兩項 None)呼叫;分隔註解寫 `# ---- 005 US2-API-17`),執行確認它因為「範圍寫成 2000~128000 這類十進位的近似值」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.TuningOverrides`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017;`plan.md` § 待決問題 Q31
- [x] T082b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US2-API-17 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T082a)
  - 🧪 `testplan.md` § US2-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.TuningOverrides`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017;`plan.md` § 待決問題 Q31
- [x] T083a [US2] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US2-API-18 的測試(依序以 `maxLoadedModels` 為 1、4、0、5(另兩項 None)呼叫;分隔註解寫 `# ---- 005 US2-API-18`),執行確認它因為「上限照 Ollama 自己的預設(3)寫」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.TuningOverrides`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017;`plan.md` § 待決問題 Q31
- [x] T083b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US2-API-18 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T083a)
  - 🧪 `testplan.md` § US2-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.TuningOverrides`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017;`plan.md` § 待決問題 Q31
- [x] T084a [US2] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US2-API-19 的測試(依序以 `numParallel` 為 `4.5`、`"4"`、`True`、`False`、`4.0`、`None`(另兩項 None)呼叫;分隔註解寫 `# ---- 005 US2-API-19`),執行確認它因為「以 `isinstance(v, int)` 判斷,`True` 被當成 1、`False` 被當成 0(訊息卻是範圍錯)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.TuningOverrides`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017(info.x-tuning-rule (1));`plan.md` § 待決問題 Q31
- [x] T084b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US2-API-19 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T084a)
  - 🧪 `testplan.md` § US2-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.TuningOverrides`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017(info.x-tuning-rule (1));`plan.md` § 待決問題 Q31
- [x] T085a [US2] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US2-API-20 的測試(依序以 `"4"`(不是物件)、`[]`、`{"numParallel": 4, "contextLength": None}`(少一個鍵)、`tuning_body(0, 1, 0)`、`tuning_body(4, 1, 0)`、`tuning_body(4, 4096, 0)` 呼叫;分隔註解寫 `# ---- 005 US2-API-20`),執行確認它因為「以 `body.get(...)` 取值,少了的鍵當成 None(自動)通過」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.TuningOverrides`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017(info.x-tuning-rule (1) 的順序);`plan.md` § 待決問題 Q31
- [x] T085b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US2-API-20 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T085a)
  - 🧪 `testplan.md` § US2-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.TuningOverrides`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017(info.x-tuning-rule (1) 的順序);`plan.md` § 待決問題 Q31
- [x] T086a [US2] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US2-API-21 的測試(依序呼叫 `resolve(40 * GIB, tuning_body(4, None, None))`、`resolve(40 * GIB, tuning_body(8, None, None))`、`resolve(15 * GIB, NONE3)`;分隔註解寫 `# ---- 005 US2-API-21`),執行確認它因為「有任何一項覆蓋時整組改用覆蓋值、沒填的變成 `ollama_default`」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、FR-002、邊界情況(覆蓋值和自動值相同);`plan.md` § 待決問題 Q31
- [x] T086b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US2-API-21 通過的程式碼;新增 `resolve(vram_total_bytes, overrides)`:「覆蓋值 > 級距 > 不帶」逐項決定,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T086a)
  - 🧪 `testplan.md` § US2-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、FR-002、邊界情況(覆蓋值和自動值相同);`plan.md` § 待決問題 Q31
- [x] T087a [US2] 🔴 /tdd 紅燈:在 `tests/unit/test_tuning.py` 寫 US2-API-22 的測試(依序呼叫 `resolve(None, NONE3)`、`resolve(None, tuning_body(4, None, None))`、`resolve(None, tuning_body(None, None, 2))`;分隔註解寫 `# ---- 005 US2-API-22`),執行確認它因為「讀不到顯示記憶體時一律不帶 flash attention 與 KV cache(FR-007 要在有覆蓋值時帶)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、FR-003、使用者故事 2 驗收情境 5;`plan.md` § 待決問題 Q31
- [x] T087b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/tuning.py` 只寫讓 US2-API-22 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T087a)
  - 🧪 `testplan.md` § US2-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-007、FR-003、使用者故事 2 驗收情境 5;`plan.md` § 待決問題 Q31
- [x] T088 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T066b~T087b 記下的重構清單(範圍限 `src/cgb/services/`、`src/cgb/repos/`、`src/cgb/api/`、`src/cgb/domain/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_api_tuning.py`、`tests/unit/test_tuning.py` 的斷言(依賴 T087b)
  - 🧪 `testplan.md` § US2-API-01~US2-API-22
  - 📎 `testplan.md` § 3.2

### E4 資料庫(SQLite)

> 只驗 `runtime_type_tunings` 這一側的事實;DDL 已由故事 1 的 T038b、T041b 照 `contracts/store.dbml` 建出,這一節都是對照組;「情況 A」「情況 B」照 `testplan.md` § 3.3

- [x] T089a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US2-DB-01 的測試(兩個庫各讀 `PRAGMA table_info(runtime_type_tunings)`;分隔註解寫 `# ---- 005 US2-DB-01`);同一個任務在 `_open_db` 加 `kind="from_v1"`(`_build_v1` 建空的 v1 舊庫再 `create_schema`,`plan.md` § 待決問題 Q43),「情況 A」「情況 B」以 `pytest.mark.parametrize` 跑同一組斷言;US1 的 T038b(全新庫)與 T041b(1 → 2 遷移)照 `contracts/store.dbml` 建出 `runtime_type_tunings`(`gpu` 為主鍵,`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「主鍵設成自動遞增的 `id`、`gpu` 只是普通欄位,同一種類型可以有好幾列,讀的時候取到哪一列不一定」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US2-DB-01
  - ⚙ `contracts/store.dbml` § `Table runtime_type_tunings`
  - 📎 `spec.md` § FR-018;`plan.md` § 待決問題 Q43
- [x] T089b [US2] 🟢 /tdd 綠燈:US2-DB-01 由 US1 的 T038b(全新庫)與 T041b(1 → 2 遷移)照 `contracts/store.dbml` 建出 `runtime_type_tunings`(`gpu` 為主鍵,`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US2-DB-01 通過的程式碼(依賴 T089a)
  - 🧪 `testplan.md` § US2-DB-01
  - ⚙ `contracts/store.dbml` § `Table runtime_type_tunings`
  - 📎 `spec.md` § FR-018;`plan.md` § 待決問題 Q43
- [x] T090a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US2-DB-02 的測試(每種情況依序執行:①`INSERT INTO runtime_type_tunings (gpu, num_parallel, context_length, max_loaded_models, updated_at) VALUES ('A100', 4, NULL, NULL, '2026-11-15T08:00:00Z')`;②再一次 ① 但 `num_parallel=8`;③`('T4', NULL, 8192, NULL, ...)`;④`('H100', NULL, NULL, 3, ...)`;⑤`('a100', 4, NULL, NULL, ...)`;⑥`('V100', 4, NULL, NULL, ...)`;⑦`INSERT ... VALUES ('A100', NULL, 16384, NULL, '2026-11-15T09:00:00Z') ON CONFLICT (gpu) DO UPDATE SET num_parallel = excluded.num_parallel, context_length = excluded.context_length, max_loaded_models = excluded.max_loaded_models, updated_at = excluded.updated_at`;⑧讀 `SELECT gpu, num_parallel, context_length, max_loaded_models FROM runtime_type_tunings ORDER BY gpu`;分隔註解寫 `# ---- 005 US2-DB-02`);US1 的 T038b、T041b 照 `contracts/store.dbml` 以 `gpu` 為主鍵(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`gpu` 沒有主鍵或 UNIQUE,第二次寫 A100 多出一列,`ON CONFLICT (gpu)` 丟 `OperationalError`(沒有對應的唯一約束)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US2-DB-02
  - ⚙ `contracts/store.dbml` § `Table runtime_type_tunings`
  - 📎 `spec.md` § FR-018、FR-008
- [x] T090b [US2] 🟢 /tdd 綠燈:US2-DB-02 由 US1 的 T038b、T041b 照 `contracts/store.dbml` 以 `gpu` 為主鍵(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US2-DB-02 通過的程式碼(依賴 T090a)
  - 🧪 `testplan.md` § US2-DB-02
  - ⚙ `contracts/store.dbml` § `Table runtime_type_tunings`
  - 📎 `spec.md` § FR-018、FR-008
- [x] T091a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US2-DB-03 的測試(每種情況以 `gpu='L4'` 逐句 `INSERT`(其他兩個值 NULL,寫完一句成功的就 `DELETE` 掉再寫下一句):`num_parallel` 為 1、32、0、33;`context_length` 為 2048、131072、2047、131073;`max_loaded_models` 為 1、4、0、5;最後一句三個值都合法但 `updated_at` 為 NULL;分隔註解寫 `# ---- 005 US2-DB-03`);US1 的 T038b、T041b 照 `contracts/store.dbml` 寫三個範圍的 CHECK(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「範圍只在 api 檢查、表上沒有 CHECK(store.dbml 定為最後一道),repos 的錯誤或手動改庫寫進 64,下次開啟把平行數 64 帶給遠端」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US2-DB-03
  - ⚙ `contracts/store.dbml` § `Table runtime_type_tunings`
  - 📎 `spec.md` § FR-017、FR-018
- [x] T091b [US2] 🟢 /tdd 綠燈:US2-DB-03 由 US1 的 T038b、T041b 照 `contracts/store.dbml` 寫三個範圍的 CHECK(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US2-DB-03 通過的程式碼(依賴 T091a)
  - 🧪 `testplan.md` § US2-DB-03
  - ⚙ `contracts/store.dbml` § `Table runtime_type_tunings`
  - 📎 `spec.md` § FR-017、FR-018
- [x] T092a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US2-DB-04 的測試(每種情況依序執行:①`UPDATE runtime_type_tunings SET num_parallel = NULL WHERE gpu = 'A100'`;②`INSERT ... VALUES ('T4', NULL, NULL, NULL, '2026-11-15T08:10:00Z')`;③`DELETE FROM runtime_type_tunings WHERE gpu = 'A100'`;④`INSERT ... VALUES ('A100', NULL, NULL, 2, '2026-11-15T08:20:00Z')`;分隔註解寫 `# ---- 005 US2-DB-04`);US1 的 T038b、T041b 照 `contracts/store.dbml` 寫「至少一個不為 NULL」的表層級 CHECK(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「照 Q23 的另一個選項,清除時把三個值改成 NULL、留下那一列,表上沒有「至少一個不為 NULL」的表層級 CHECK,`getTuningOverrides` 對清除過的類型回出 `updatedAt` 有值、三個 null 的資料,和「沒有記過」分不出來」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US2-DB-04
  - ⚙ `contracts/store.dbml` § `Table runtime_type_tunings`
  - 📎 `spec.md` § FR-018、FR-009;`plan.md` § 待決問題 Q23
- [x] T092b [US2] 🟢 /tdd 綠燈:US2-DB-04 由 US1 的 T038b、T041b 照 `contracts/store.dbml` 寫「至少一個不為 NULL」的表層級 CHECK(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US2-DB-04 通過的程式碼(依賴 T092a)
  - 🧪 `testplan.md` § US2-DB-04
  - ⚙ `contracts/store.dbml` § `Table runtime_type_tunings`
  - 📎 `spec.md` § FR-018、FR-009;`plan.md` § 待決問題 Q23
- [x] T093a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US2-DB-05 的測試(每種情況 `conn.close()`,以新的 `connect` 開同一個檔,再呼叫 `create_schema(conn)`(後端重新啟動),讀 `SELECT gpu, num_parallel, context_length, max_loaded_models, updated_at FROM runtime_type_tunings ORDER BY gpu`;分隔註解寫 `# ---- 005 US2-DB-05`);US1 的 T047b(`user_version` 已是 2 就不跑遷移,`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「已經是 2 的庫每次啟動都重跑 1 → 2 的步驟 3,以 `DROP TABLE IF EXISTS runtime_type_tunings` 再建,後端一重啟記住的覆蓋值全部消失(FR-018「跨後端重新啟動保留」)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US2-DB-05
  - ⚙ `contracts/store.dbml` § `Table runtime_type_tunings`
  - 📎 `spec.md` § FR-018、使用者故事 2 驗收情境 2
- [x] T093b [US2] 🟢 /tdd 綠燈:US2-DB-05 由 US1 的 T047b(`user_version` 已是 2 就不跑遷移,`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US2-DB-05 通過的程式碼(依賴 T093a)
  - 🧪 `testplan.md` § US2-DB-05
  - ⚙ `contracts/store.dbml` § `Table runtime_type_tunings`
  - 📎 `spec.md` § FR-018、使用者故事 2 驗收情境 2
- [x] T094 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T089b~T093b 記下的重構清單(範圍限 `src/cgb/db/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_db_schema.py` 的斷言(依賴 T093b)
  - 🧪 `testplan.md` § US2-DB-01~US2-DB-05
  - 📎 `testplan.md` § 3.3

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(Playwright)接測試行程內真的後端(`tests/e2e/conftest.py` 的 `e2e_servers`,UI 127.0.0.1:8781),轉接層用替身;e2e 用固定 port,同一時間只跑一份

- [x] T095a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us2_overrides.py` 寫 US2-AJ-01 的測試(使用者在開啟畫面選 A100、展開「Ollama 設定」,平行數填 4、其他留空,按開啟;分隔註解寫 `# ---- 005 US2-AJ-01`),執行確認它因為「沒填的欄位送成 0 或空字串被當成手動;覆蓋值沒有帶到遠端」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `prototype/index.html` § `[data-state="normal"]`、`#open`、`.tuning-block`、`.tuning-fields`、`.hint`、`[data-state="ready-manual"]`、`#t-manual-note`、`[data-state="ready-no-vram-manual"]`;`contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-006、FR-007;`research.md` § R11;`plan.md` § 待決問題 Q57
- [x] T095b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js`、`src/cgb/static/js/view.js` 只寫讓 US2-AJ-01 通過的程式碼;開啟與變更類型共用的 `renderPicker` 加「Ollama 設定」區塊(三個欄位、欄位旁「留空 = 自動」),開啟時把填了的值與 null 送進 `POST /api/session` 的 `tuning`;設定卡把手動的項目標「手動」;讀不到顯示記憶體又有覆蓋值時照原型 `ready-no-vram-manual` 說明(這個狀態沒有案例斷言,完成報告列為未直接驗證,`plan.md` § 待決問題 Q57),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T095a)
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `prototype/index.html` § `[data-state="normal"]`、`#open`、`.tuning-block`、`.tuning-fields`、`.hint`、`[data-state="ready-manual"]`、`#t-manual-note`、`[data-state="ready-no-vram-manual"]`;`contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-006、FR-007;`research.md` § R11;`plan.md` § 待決問題 Q57
- [x] T096a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us2_overrides.py` 寫 US2-AJ-02 的測試(使用者再開開啟畫面,先選 A100、再改選 T4;分隔註解寫 `# ---- 005 US2-AJ-02`),執行確認它因為「預先填入不分類型,T4 也帶出 4;換類型後殘留上一個類型的值」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-02
  - ⚙ `prototype/index.html` § `[data-state="tuning-prefilled"]`、`#prefill-note`、`.type-picker`、`[data-state="confirm-switch"]`、`[data-state="switching"]`、`#cw-current`;`contracts/ui.openapi.yaml` § `paths./tuning/overrides.get`
  - 📎 `spec.md` § FR-008、FR-018;`plan.md` § 待決問題 Q57
- [x] T096b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US2-AJ-02 通過的程式碼;選一種類型時以 `GET /api/tuning/overrides` 預先填入那一種記住的值、沒記過的留空,換類型時不殘留;變更類型的確認畫面共用同一個區塊(`confirm-switch`、`switching` 沒有案例斷言,完成報告列為未直接驗證,`plan.md` § 待決問題 Q57),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T096a)
  - 🧪 `testplan.md` § US2-AJ-02
  - ⚙ `prototype/index.html` § `[data-state="tuning-prefilled"]`、`#prefill-note`、`.type-picker`、`[data-state="confirm-switch"]`、`[data-state="switching"]`、`#cw-current`;`contracts/ui.openapi.yaml` § `paths./tuning/overrides.get`
  - 📎 `spec.md` § FR-008、FR-018;`plan.md` § 待決問題 Q57
- [x] T097a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us2_overrides.py` 寫 US2-AJ-03 的測試(使用者選 A100、按「全部改回自動」並開啟,就緒後結束,再開開啟畫面選 A100;分隔註解寫 `# ---- 005 US2-AJ-03`),執行確認它因為「按鈕只清畫面欄位、沒有清除記住的值;按下按鈕當下就清除而不是開啟時」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-03
  - ⚙ `prototype/index.html` § `[data-state="normal"]`、`.tuning-block`、`[data-state="confirm-stop"]`、`[data-state="stopping"]`、`[data-state="ended"]`
  - 📎 `spec.md` § FR-009
- [x] T097b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US2-AJ-03 通過的程式碼;「全部改回自動」只清空三個欄位,開啟時送三個 null(清除由後端在開啟時做),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T097a)
  - 🧪 `testplan.md` § US2-AJ-03
  - ⚙ `prototype/index.html` § `[data-state="normal"]`、`.tuning-block`、`[data-state="confirm-stop"]`、`[data-state="stopping"]`、`[data-state="ended"]`
  - 📎 `spec.md` § FR-009
- [x] T098a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us2_overrides.py` 寫 US2-AJ-04 的測試(使用者選 A100、平行數填 64,按開啟;分隔註解寫 `# ---- 005 US2-AJ-04`),執行確認它因為「範圍檢查只在前端或只在後端漏掉;超出範圍的值被記住」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-04
  - ⚙ `prototype/index.html` § `[data-state="tuning-invalid"]`、`#invalid-note`、`.field-error`;`contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-017
- [x] T098b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US2-AJ-04 通過的程式碼;開啟回 400 的三個範圍代碼時在 `#invalid-note` 與欄位旁顯示範圍說明,不離開開啟畫面,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T098a)
  - 🧪 `testplan.md` § US2-AJ-04
  - ⚙ `prototype/index.html` § `[data-state="tuning-invalid"]`、`#invalid-note`、`.field-error`;`contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-017
- [x] T099 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T095b~T098b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T098b)
  - 🧪 `testplan.md` § US2-AJ-01~US2-AJ-04
  - 📎 `testplan.md` § 3.4

### 介面覆蓋(US2)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`(故事 2 擴充:覆蓋值) | T054b~T064b | T054a~T064a |
| `colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post` | T063b | T063a |
| `ui.openapi.yaml` § `paths./session.get`(故事 2 擴充:覆蓋值) | T066b、T073b、T079b | T066a、T073a、T079a |
| `ui.openapi.yaml` § `paths./session.post`(故事 2 擴充:覆蓋值) | T066b~T070b、T072b~T075b、T077b、T095b、T098b | T066a~T070a、T072a~T075a、T077a、T095a、T098a |
| `ui.openapi.yaml` § `paths./session/restart.post` | T076b、T078b~T080b | T076a、T078a~T080a |
| `ui.openapi.yaml` § `paths./tuning/overrides.get` | T067b~T072b、T080b、T096b | T067a~T072a、T080a、T096a |
| `ui.openapi.yaml` § `paths./sessions/{name}.get`(故事 2 擴充:覆蓋值) | T066b、T068b、T079b | T066a、T068a、T079a |
| `store.dbml` § `Table runtime_type_tunings`(故事 2 擴充:覆蓋值) | T089b~T093b | T089a~T093a |
| `index.html` § `[data-state="normal"]` | T095b、T097b | T095a、T097a |
| `index.html` § `[data-state="tuning-prefilled"]` | T096b | T096a |
| `index.html` § `[data-state="tuning-invalid"]` | T098b | T098a |
| `index.html` § `[data-state="ready-no-vram-manual"]` | T095b | T095a |
| `index.html` § `[data-state="ready-manual"]` | T095b | T095a |
| `index.html` § `[data-state="confirm-switch"]` | T096b | T096a |
| `index.html` § `[data-state="switching"]` | T096b | T096a |
| `index.html` § `[data-state="confirm-stop"]` | T097b | T097a |
| `index.html` § `[data-state="stopping"]` | T097b | T097a |
| `index.html` § `[data-state="ended"]` | T097b | T097a |

### 測試案例覆蓋(US2)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US2-CLI-01~US2-CLI-11 | T054a~T064a | T054b~T064b | T065 |
| US2-API-01~US2-API-22 | T066a~T087a | T066b~T087b | T088 |
| US2-DB-01~US2-DB-05 | T089a~T093a | T089b~T093b | T094 |
| US2-AJ-01~US2-AJ-04 | T095a~T098a | T095b~T098b | T099 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 再加 `uv run pytest -m realrun_local -q -p no:cacheprovider` 全綠(含 `tests/e2e/test_locale.py` 加了三個範圍代碼);重構任務前後的測試結果相同

---

## Phase 4: User Story 3 - 工作階段開著時改設定,重啟遠端 Ollama 套用 (Priority: P3)

**Goal**: 工作階段就緒時可以在工作階段頁改三項設定並「套用並重啟 Ollama」:確認後重啟遠端 Ollama、依 `/api/ps` 的順序重新載入到新的上限、回到就緒並記住這次的值;有下載或請求進行中、非就緒、已在套用時擋下;新設定起不來時改回自動值,再失敗就以「重啟 Ollama 失敗」結束;每一次套用都留紀錄

**Independent Test**: 照 `testplan.md` § 4 的全部案例:E5 以 `uv run pytest tests/integration/test_colab_cli.py` 與 `uv run pytest -m realrun_local tests/integration/test_ollama_scripts.py`、E2 以 `uv run pytest tests/integration/test_api_tuning_apply.py`、E4 以 `uv run pytest tests/integration/test_db_schema.py`、跨端點驗收以 `uv run pytest tests/e2e/test_005_us3_apply.py` 執行全綠

### E5 Colab CLI(`colab exec` 遠端腳本)

> E5 節最前面的 T100b 做出 `plan.md` § 待決問題 Q32 的共用件(`restart_ollama(name, overrides)`、`CliTimeouts.restart_ollama`、`FakeColabControl.restart_ollama`、`ColabWorld.restart_result`),E2 節等它的綠燈完成才開始(Q55)。檔案範圍與護欄同故事 1 的 E5 節。pgrep 的案例一律設 `CGB_SERVE_PGREP_PATTERN=^<暫存資料夾>/oldbin/ollama serve`,沒有任何案例以預設的 `^ollama serve` 執行 `pgrep`,桌機上使用者自己的 `ollama serve` 不會被比對到、也不會收到訊號(`testplan.md` § 4.1);`restart_ollama.py` 從故事 2 的 T063b 的最小版本擴充

- [x] T100a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US3-CLI-01 的測試(依序呼叫 `restart_ollama` 帶 `{"numParallel": 4, "contextLength": None, "maxLoadedModels": None}` 與 `AUTO`(FR-013 改回自動值);分隔註解寫 `# ---- 005 US3-CLI-01`);同一個任務在檔內新增 `testplan.md` § 4.1 的 `RESTART_OLLAMA_SCRIPT`、`restart_argv`、`RESTARTED_T4_P4`;另把 `restart_argv(np="4")` 交給真的 `colab` CLI 以暫存 `HOME`、未授權解析一次(同 T002a,加進快速層的 `--deselect`),這一步會在本機執行 `colab`,執行前先停下問使用者本人(`plan.md` § 待決問題 Q56),執行確認它因為「沿用 `start_ollama` 的腳本路徑或 `--timeout 240`」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`
  - 📎 `spec.md` § FR-012、FR-013;`plan.md` § 待決問題 Q32、Q51
- [x] T100b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`tests/fakes/adapters.py`、`tests/integration/test_api_session.py` 只寫讓 US3-CLI-01 通過的程式碼;新增 `ColabControl.restart_ollama(name, overrides)`:`restart_ollama.py`、`--timeout 120`、帶齊三個 `CGB_TUNE_*`、經 `_exec_script`,`CliTimeouts` 加 `restart_ollama`(預設 180 秒);`plan.md` § 待決問題 Q32 的共用件也在這個任務做:`tests/fakes/adapters.py` 的 `FakeColabControl.METHODS` 加 `restart_ollama`(照真 adapter 綁定參數,`tests/integration/test_fake_signatures.py` 照原樣回歸),`tests/integration/test_api_session.py` 的 `ColabWorld` 新增 `_restart_ollama` 回 `self.restart_result`、記 `("restart_ollama", name)`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T100a)
  - 🧪 `testplan.md` § US3-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`
  - 📎 `spec.md` § FR-012、FR-013;`plan.md` § 待決問題 Q32、Q51
- [x] T101a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US3-CLI-02 的測試(呼叫 `restart_ollama(name="cgb-test-0001", overrides={"numParallel": 4, "contextLength": None, "maxLoadedModels": None})`;分隔註解寫 `# ---- 005 US3-CLI-02`),執行確認它因為「照 `OllamaStarted` 的形狀回傳,少了 `stoppedBy`、多了 `alreadyRunning`」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.StoppedBy`、`components.schemas.MachineProbe`
  - 📎 `spec.md` § FR-012
- [x] T101b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py` 只寫讓 US3-CLI-02 通過的程式碼;回 `OllamaRestarted`(`stoppedBy`、`machine`、`tuning`,沒有 `alreadyRunning`),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T101a)
  - 🧪 `testplan.md` § US3-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.StoppedBy`、`components.schemas.MachineProbe`
  - 📎 `spec.md` § FR-012
- [x] T102a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US3-CLI-03 的測試(每種各呼叫一次 `restart_ollama` 帶平行數 4;分隔註解寫 `# ---- 005 US3-CLI-03`),執行確認它因為「只把 `verify` 帶出 `remoteStage`,`stop` 被當成別的錯,呼叫者不改用自動值重試(plan.md Q4)」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-03
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`、`components.schemas.ScriptStage`
  - 📎 `spec.md` § FR-013;`plan.md` § 待決問題 Q4
- [x] T102b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py` 只寫讓 US3-CLI-03 通過的程式碼;`stage` 為 `stop`、`start`、`verify` 時都帶 `remote_stage`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T102a)
  - 🧪 `testplan.md` § US3-CLI-03
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`、`components.schemas.ScriptStage`
  - 📎 `spec.md` § FR-013;`plan.md` § 待決問題 Q4
- [x] T103a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US3-CLI-04 的測試(劇本一呼叫 `restart_ollama` 帶平行數 4;劇本二呼叫 `restart_ollama` 帶 `{"numParallel": 33, "contextLength": None, "maxLoadedModels": None}`;分隔註解寫 `# ---- 005 US3-CLI-04`),執行確認它因為「範圍檢查只寫在 `start_ollama`,`restart_ollama` 把 33 送到遠端」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-04
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017、FR-013
- [x] T103b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py` 只寫讓 US3-CLI-04 通過的程式碼;重啟也在呼叫 `colab` 之前檢查範圍,和 `start_ollama` 共用同一段檢查,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T103a)
  - 🧪 `testplan.md` § US3-CLI-04
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017、FR-013
- [x] T104a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_colab_cli.py` 寫 US3-CLI-05 的測試(各呼叫一次 `restart_ollama` 帶平行數 4;分隔註解寫 `# ---- 005 US3-CLI-05`);T100b 讓 `restart_ollama` 經 `_exec_script`(`Connection was lost` 以同一組參數重跑一次,`src/cgb/adapters/colab_cli.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「重啟不走 `_exec_script`,`Connection was lost` 直接失敗、套用變成結束工作階段」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-CLI-05
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013、邊界情況(重啟時 colab exec 斷線)
- [x] T104b [US3] 🟢 /tdd 綠燈:US3-CLI-05 由 T100b 讓 `restart_ollama` 經 `_exec_script`(`Connection was lost` 以同一組參數重跑一次,`src/cgb/adapters/colab_cli.py`)滿足,確認 `src/cgb/adapters/colab_cli.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/colab_cli.py` 只寫讓 US3-CLI-05 通過的程式碼(依賴 T104a)
  - 🧪 `testplan.md` § US3-CLI-05
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013、邊界情況(重啟時 colab exec 斷線)
- [x] T105a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_colab_cli.py` 寫 US3-CLI-06 的測試(各呼叫一次 `restart_ollama` 帶平行數 4;分隔註解寫 `# ---- 005 US3-CLI-06`);T100b 讓 `restart_ollama` 用 `CliTimeouts.restart_ollama`(`src/cgb/adapters/colab_cli.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「重啟沿用 `start_ollama` 的 300 秒時限(`CliTimeouts` 沒有 `restart_ollama`,縮短的設定沒有作用)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-CLI-06
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013;`plan.md` § 待決問題 Q51
- [x] T105b [US3] 🟢 /tdd 綠燈:US3-CLI-06 由 T100b 讓 `restart_ollama` 用 `CliTimeouts.restart_ollama`(`src/cgb/adapters/colab_cli.py`)滿足,確認 `src/cgb/adapters/colab_cli.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/colab_cli.py` 只寫讓 US3-CLI-06 通過的程式碼(依賴 T105a)
  - 🧪 `testplan.md` § US3-CLI-06
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013;`plan.md` § 待決問題 Q51
- [x] T106a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_colab_cli.py` 寫 US3-CLI-07 的測試(每種各呼叫一次 `restart_ollama` 帶平行數 4;分隔註解寫 `# ---- 005 US3-CLI-07`);T100b 讓 `restart_ollama` 經 `_exec_script` 的失敗分類與 stderr 遮罩(`src/cgb/adapters/colab_cli.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「重啟自己解析輸出,只認 `CGB-RESULT`,其他失敗一律歸 `COLAB_REMOTE_ERROR`,呼叫者照 Q10 改回自動值又重啟一次(執行環境已不在或未授權時白跑)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-CLI-07
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013、NFR-003;`plan.md` § 待決問題 Q10
- [x] T106b [US3] 🟢 /tdd 綠燈:US3-CLI-07 由 T100b 讓 `restart_ollama` 經 `_exec_script` 的失敗分類與 stderr 遮罩(`src/cgb/adapters/colab_cli.py`)滿足,確認 `src/cgb/adapters/colab_cli.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/colab_cli.py` 只寫讓 US3-CLI-07 通過的程式碼(依賴 T106a)
  - 🧪 `testplan.md` § US3-CLI-07
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013、NFR-003;`plan.md` § 待決問題 Q10
- [x] T107a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US3-CLI-08 的測試(每種各呼叫一次 `restart_ollama` 帶平行數 4;分隔註解寫 `# ---- 005 US3-CLI-08`),執行確認它因為「照 `start_ollama` 的寬鬆規則接受 `tuning` 為 null,重啟後後端寫進一筆沒有設定的紀錄」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-08
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`、`components.schemas.StoppedBy`
  - 📎 `spec.md` § FR-012
- [x] T107b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py` 只寫讓 US3-CLI-08 通過的程式碼;重啟的結果 `tuning` 不得為 null、`stoppedBy` 要在列舉裡,不符歸 `COLAB_BAD_RESPONSE`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T107a)
  - 🧪 `testplan.md` § US3-CLI-08
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaInput`、`components.schemas.OllamaRestarted`、`components.schemas.Error`、`components.schemas.StoppedBy`
  - 📎 `spec.md` § FR-012
- [x] T108a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US3-CLI-09 的測試(`box.run([restart_ollama.py])`;分隔註解寫 `# ---- 005 US3-CLI-09`),執行確認它因為「只對 pid 送訊號、不送行程群組,載入模型的子行程留著佔顯示記憶體(research.md R1)」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-09
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-012;`research.md` § R1;`plan.md` § 待決問題 Q53
- [x] T108b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/restart_ollama.py` 只寫讓 US3-CLI-09 通過的程式碼;對 pid 檔那個 pid 的行程群組送 SIGTERM(`os.killpg`),`stoppedBy` 為 `pid_file`;pid 被重用不另檢查,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T108a)
  - 🧪 `testplan.md` § US3-CLI-09
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-012;`research.md` § R1;`plan.md` § 待決問題 Q53
- [x] T109a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US3-CLI-10 的測試(每種各 `box.run([restart_ollama.py])`;分隔註解寫 `# ---- 005 US3-CLI-10`),執行確認它因為「pid 檔不在就直接啟動新的,舊的佔著 port,新的起不來、回報 `verify`」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-10
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-012;`research.md` § R1;`plan.md` § 待決問題 Q5、Q45
- [x] T109b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/restart_ollama.py` 只寫讓 US3-CLI-10 通過的程式碼;pid 檔不在或內容不是數字時以 `pgrep -f`(`CGB_SERVE_PGREP_PATTERN`,預設 `^ollama serve`)找 pid,再停整個行程群組,`stoppedBy` 為 `pgrep`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T109a)
  - 🧪 `testplan.md` § US3-CLI-10
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-012;`research.md` § R1;`plan.md` § 待決問題 Q5、Q45
- [x] T110a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US3-CLI-11 的測試(`box.run([restart_ollama.py])`;分隔註解寫 `# ---- 005 US3-CLI-11`),執行確認它因為「找不到要停的行程就回報 `stage: "stop"`,Ollama 自己掛掉時無法以重啟救回」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-11
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-012
- [x] T110b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/restart_ollama.py` 只寫讓 US3-CLI-11 通過的程式碼;找不到要停的行程不算失敗,`stoppedBy` 為 `none`,照常啟動,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T110a)
  - 🧪 `testplan.md` § US3-CLI-11
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-012
- [x] T111a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US3-CLI-12 的測試(`box.run([restart_ollama.py])`;分隔註解寫 `# ---- 005 US3-CLI-12`),執行確認它因為「送了 SIGTERM 就不再確認,忽略 SIGTERM 的成員留在執行環境上」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-12
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-012;`research.md` § R1;`plan.md` § 待決問題 Q45
- [x] T111b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/restart_ollama.py` 只寫讓 US3-CLI-12 通過的程式碼;`CGB_STOP_SECONDS`(預設 10)內行程群組沒結束就送 SIGKILL,確認都結束才往下,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T111a)
  - 🧪 `testplan.md` § US3-CLI-12
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-012;`research.md` § R1;`plan.md` § 待決問題 Q45
- [x] T112a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US3-CLI-13 的測試(`box.run([restart_ollama.py])`;分隔註解寫 `# ---- 005 US3-CLI-13`),執行確認它因為「不確認舊的已停止回應就啟動,新的 bind 失敗、回報成 `verify`」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-13
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-013;`research.md` § R1
- [x] T112b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/restart_ollama.py` 只寫讓 US3-CLI-13 通過的程式碼;確認舊的已停止回應 `/api/version` 才啟動新的,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T112a)
  - 🧪 `testplan.md` § US3-CLI-13
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-013;`research.md` § R1
- [x] T113a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US3-CLI-14 的測試(`box.run([restart_ollama.py])`;分隔註解寫 `# ---- 005 US3-CLI-14`),執行確認它因為「啟動丟出的 `OSError` 沒接住,變成沒有結果行的 traceback(轉接層歸成 `remoteStage` 為 null)」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-14
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-013
- [x] T113b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/restart_ollama.py` 只寫讓 US3-CLI-14 通過的程式碼;啟動丟出的 `OSError` 回 `stage: start`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T113a)
  - 🧪 `testplan.md` § US3-CLI-14
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-013
- [x] T114a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US3-CLI-15 的測試(`box.run([restart_ollama.py])`;分隔註解寫 `# ---- 005 US3-CLI-15`),執行確認它因為「驗證失敗時寫了狀態檔或留著舊的」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-15
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-013
- [x] T114b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/restart_ollama.py` 只寫讓 US3-CLI-15 通過的程式碼;驗證失敗時不寫狀態檔、刪掉舊的,並停掉新起的那一個,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T114a)
  - 🧪 `testplan.md` § US3-CLI-15
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-013
- [x] T115a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US3-CLI-16 的測試(`box.run([restart_ollama.py])`;分隔註解寫 `# ---- 005 US3-CLI-16`),執行確認它因為「先停舊的才檢查覆蓋值,使用者打錯一個值,已載入的模型就被清掉、還要改回自動值重啟一次」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-16
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-017、FR-013
- [x] T115b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/restart_ollama.py` 只寫讓 US3-CLI-16 通過的程式碼;停舊的之前先檢查三個 `CGB_TUNE_*`,不符回 `stage: input`、不碰舊的 serve,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T115a)
  - 🧪 `testplan.md` § US3-CLI-16
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-017、FR-013
- [x] T116a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US3-CLI-17 的測試(同一個 kernel 以同一組環境連跑兩次 `restart_ollama.py`(`Connection was lost` 的重跑);分隔註解寫 `# ---- 005 US3-CLI-17`),執行確認它因為「第二次讀到的 pid 檔還是第一次之前的舊 pid(第一次沒寫回),停不到第一次起的 serve,新的起不來」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-17
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-013、邊界情況(重啟時 colab exec 斷線)
- [x] T116b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/restart_ollama.py` 只寫讓 US3-CLI-17 通過的程式碼;新的 serve 起來就寫回 pid 檔,重跑時停得到上一次起的那一個,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T116a)
  - 🧪 `testplan.md` § US3-CLI-17
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-013、邊界情況(重啟時 colab exec 斷線)
- [x] T117a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_scripts.py` 寫 US3-CLI-18 的測試(同一個 kernel 依序跑兩步:`restart_ollama.py` 帶 `CGB_TUNE_NUM_PARALLEL=4`;再以三個 `CGB_TUNE_*` 都是空字串跑一次(FR-013 改回自動值);分隔註解寫 `# ---- 005 US3-CLI-18`),執行確認它因為「第一步失敗後 pid 檔指著已結束的 pid,第二步 `os.killpg` 丟例外變成 traceback,改回自動值也失敗、工作階段被結束」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-18
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-013
- [x] T117b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/scripts/restart_ollama.py` 只寫讓 US3-CLI-18 通過的程式碼;pid 指著已結束的行程時(`ProcessLookupError`)當成已停止,不丟例外,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T117a)
  - 🧪 `testplan.md` § US3-CLI-18
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`、`components.schemas.AppliedTuning`
  - 📎 `spec.md` § FR-013
- [x] T118 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T100b~T117b 記下的重構清單(範圍限 `src/cgb/adapters/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_colab_cli.py`、`tests/integration/test_ollama_scripts.py` 的斷言(依賴 T117b)
  - 🧪 `testplan.md` § US3-CLI-01~US3-CLI-18
  - 📎 `testplan.md` § 4.1
- [x] T119 [US3] 📏 量測:在 `tests/integration/test_ollama_scripts.py` 寫 US3-CLI-19(標 `realrun_local`),照案例起好舊的 serve、pid 檔指著它、量到 15360 MiB,`CGB_STOP_SECONDS`、`CGB_VERIFY_SECONDS` 都不設(用預設 10、60);情況 A 以 `CGB_TUNE_NUM_PARALLEL=4` 連續重啟 5 次、記每次從開始到結果行的時間與 `ok`,情況 B 跑一次 US3-CLI-18 的兩步(新設定起不來、等滿 60 秒,再改回自動值)、記兩步合計的時間,和門檻(A 的 5 次都 ≤ 90 秒且 `ok` 都是 true、B ≤ 180 秒,SC-004,只含遠端腳本)比較,結果寫進 `specs/005-ollama-machine-tuning/measurements.md`;serve 是 `box` 起的臨時 `ollama serve`(`free_loopback_port()`、暫存 `HOME` 與 `OLLAMA_MODELS`,不 pull 任何模型),腳本裡的 socket 守門只放行那個 port,不對 127.0.0.1:11434 送請求;停止靠 pid 檔,不以預設樣式執行 `pgrep`;不執行 `colab`、不花 compute units;紀錄只寫 pytest 暫存資料夾;約 2 分鐘;收尾照 `box` 確認行程與行程群組都已結束;Colab 上含 `colab exec` 來回的時間由 G-04 量;判定者:腳本;樣本:一次實跑,A 5 次、B 1 次(未用於調整)
  - 🧪 `testplan.md` § US3-CLI-19
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`、`components.schemas.RestartOllamaScriptResult`
  - 📎 `spec.md` § NFR-002、SC-004

### E2 後端 UI API(FastAPI REST 與 SSE)

> 依賴 E5 節的 US3-CLI-01 綠燈(T100b)完成才開始(`plan.md` § 待決問題 Q32、Q55)。測試寫進新檔 `tests/integration/test_api_tuning_apply.py`;套用的流程與時機照 `contracts/ui.openapi.yaml` 的 `info.x-apply-flow`、`info.x-applying-state` 與 `contracts/store.dbml` 的寫入時機,每支測試 1 秒內結束,閒置與時間的案例以 `fake_clock` 推進。001 的閒置、健康檢查與恢復測試照原樣回歸。「套用時排隊中的項目不擋、套用期間暫停、回到就緒照常開始」這一輪不測(`plan.md` § 待決問題 Q36,`testplan.md` § 7)

- [x] T120a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-01 的測試(`apply(ui_client, tuning_body(4, None, None))`;`wait_applied(ui_client)`,`GET /api/session`;分隔註解寫 `# ---- 005 US3-API-01`);同一個任務在這個新檔新增 `testplan.md` § 4.2 的 `LLAMA`、`A100_RESTARTED_4`、`AUTO_RESTARTED`、`apply_ready`、`apply`、`wait_applied`、`remote_error`、`restart_overrides`、`preloaded`、`fallback_split`,執行確認它因為「路由 `await` 整個重啟才回應(202 時已是 `ready`)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-012、FR-010、使用者故事 3 驗收情境 1、使用者故事 3 獨立測試;`research.md` § R1、R8;`plan.md` § 待決問題 Q7、Q12
- [x] T120b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py`、`src/cgb/api/__init__.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py`、`src/cgb/repos/tunings.py` 只寫讓 US3-API-01 通過的程式碼;新增 `applyTuning`(`src/cgb/api/tuning.py`,在 `src/cgb/api/__init__.py` 註冊):受理後立即回 202,`state` 改 `applying_tuning`、`step` 為 `restarting_ollama`,追加一筆 `trigger` 為 `apply`、`result` 為 `in_progress` 的紀錄,在背景呼叫 `restart_ollama`、依序重新載入、回到 `ready` 並把那一筆改成 `applied`(`info.x-apply-flow`);`applying_tuning` 加進同一個概念的每一份清單:`src/cgb/domain/session_state.py` 的 `ACTIVE_STATES`、`src/cgb/repos/sessions.py` 第 71 行進行中的查詢(畫面的狀態與步驟標籤由跨端點驗收的 T163b 加),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T120a、T100b)
  - 🧪 `testplan.md` § US3-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-012、FR-010、使用者故事 3 驗收情境 1、使用者故事 3 獨立測試;`research.md` § R1、R8;`plan.md` § 待決問題 Q7、Q12
- [x] T121a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-02 的測試(`apply`(`tuning_body(4, None, None)`);等 `restart_gate` 被走到時 `GET /api/session`;放行,等 `preload_gate` 被走到時 `GET /api/session`;放行,讀 SSE 直到 `state` 為 `ready` 的 `session.updated`(最多 1 秒);分隔註解寫 `# ---- 005 US3-API-02`),執行確認它因為「只在受理與完成時各推一次,`step` 從 `restarting_ollama` 直接跳到 `ready`」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`、`operations.sendModelsUpdated`
  - 📎 `spec.md` § FR-015、FR-012、使用者故事 3 驗收情境 1;`plan.md` § 待決問題 Q21
- [x] T121b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-02 通過的程式碼;`step` 依序推 `restarting_ollama`、`reloading_models` 的 `session.updated`,重新載入每個模型後推 `models.updated`;重啟成功時就把量到的硬體與新設定寫進 `in_progress` 那一筆,目前生效的設定也取它(analysis A2、D48),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T121a)
  - 🧪 `testplan.md` § US3-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`、`operations.sendModelsUpdated`
  - 📎 `spec.md` § FR-015、FR-012、使用者故事 3 驗收情境 1;`plan.md` § 待決問題 Q21
- [x] T122a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-03 的測試(`apply`(`tuning_body(4, None, None)`);等閘門被走到時 `GET /api/tuning/overrides`;放行,`wait_applied`,再 `GET /api/tuning/overrides` 與 `GET /api/session`;`DELETE /api/session` 等 `ended`,送 `POST /api/session`(`{"runtimeType": A100}`,不帶 `tuning`)等 `ready`;分隔註解寫 `# ---- 005 US3-API-03`),執行確認它因為「照 `openSession` 的做法在受理時就寫入,重啟失敗時記住的已經是失敗的值」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-014、FR-018、使用者故事 3 驗收情境 5;`plan.md` § 待決問題 Q39
- [x] T122b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/repos/tunings.py` 只寫讓 US3-API-03 通過的程式碼;套用成功才寫這種類型的覆蓋值,`updatedAt` 等於 `lastApply.finishedAt`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T122a)
  - 🧪 `testplan.md` § US3-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-014、FR-018、使用者故事 3 驗收情境 5;`plan.md` § 待決問題 Q39
- [x] T123a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-04 的測試(`apply`(`NONE3`),`wait_applied`,`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US3-API-04`),執行確認它因為「寫入時把三個 null 當成「沒有要記的值」而跳過,記住的 4/16384/2 留著」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-014、FR-009(info.x-tuning-rule (3));`plan.md` § 待決問題 Q23
- [x] T123b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/repos/tunings.py` 只寫讓 US3-API-04 通過的程式碼;三個 null 套用成功時清除這種類型的覆蓋值(刪掉那一列),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T123a)
  - 🧪 `testplan.md` § US3-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-014、FR-009(info.x-tuning-rule (3));`plan.md` § 待決問題 Q23
- [x] T124a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-05 的測試(`apply`(`NONE3`),`wait_applied`;分隔註解寫 `# ---- 005 US3-API-05`);T120b 每次套用都呼叫 `restart_ollama`(`src/cgb/services/tuning.py`),不和目前生效的設定比較已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「和目前生效的設定相同就直接回 200、不重啟(合約寫明「和目前生效的設定相同也照常重啟」,使用者用它重啟卡住的 Ollama)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-012
- [x] T124b [US3] 🟢 /tdd 綠燈:US3-API-05 由 T120b 每次套用都呼叫 `restart_ollama`(`src/cgb/services/tuning.py`),不和目前生效的設定比較滿足,確認 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-05 通過的程式碼(依賴 T124a)
  - 🧪 `testplan.md` § US3-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-012
- [x] T125a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-06 的測試(`apply`(`tuning_body(4, None, None)`);等 `restart_ollama.call_count` 為 2 時 `GET /api/session`;`fallback_gate.release()`,`wait_applied`,`GET /api/session`、`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US3-API-06`),執行確認它因為「改回自動值時帶記住的 2 而不是三個 null」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-013、FR-014、使用者故事 3 驗收情境 6、使用者故事 3 獨立測試;`plan.md` § 待決問題 Q10、Q20
- [x] T125b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-06 通過的程式碼;`COLAB_REMOTE_ERROR` 時改以三個 null 再呼叫一次 `restart_ollama`,成功時那一筆記 `fell_back_to_auto`(`requested` 保留這次的值)、不寫類型覆蓋值,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T125a)
  - 🧪 `testplan.md` § US3-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-013、FR-014、使用者故事 3 驗收情境 6、使用者故事 3 獨立測試;`plan.md` § 待決問題 Q10、Q20
- [x] T126a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-07 的測試(`apply`(`tuning_body(4, None, None)`),`wait_applied`;分隔註解寫 `# ---- 005 US3-API-07`),執行確認它因為「只有 `remoteStage` 為 `start`、`verify` 才改回自動值(Q4 已決定 `stop` 也重試)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-013(COLAB_REMOTE_ERROR、COLAB_INVALID_TUNING);`plan.md` § 待決問題 Q4、Q10
- [x] T126b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-07 通過的程式碼;`COLAB_INVALID_TUNING` 與 `remoteStage` 為 `stop` 的 `COLAB_REMOTE_ERROR` 也改回自動值,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T126a)
  - 🧪 `testplan.md` § US3-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-013(COLAB_REMOTE_ERROR、COLAB_INVALID_TUNING);`plan.md` § 待決問題 Q4、Q10
- [x] T127a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-08 的測試(`apply`(`tuning_body(4, None, None)`),`wait_applied`,`GET /api/session`;分隔註解寫 `# ---- 005 US3-API-08`),執行確認它因為「所有失敗都改回自動值再試(多一次 `colab exec`,還要等第二次逾時)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-013、邊界情況(colab exec 斷線)、使用者故事 3 驗收情境 7;`plan.md` § 待決問題 Q10、Q11
- [x] T127b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-08 通過的程式碼;其他失敗(逾時、斷線重跑後仍失敗、`COLAB_UNREACHABLE` 等)不改回自動值,直接照 `info.x-apply-flow` (5) 標成 `lost`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T127a)
  - 🧪 `testplan.md` § US3-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-013、邊界情況(colab exec 斷線)、使用者故事 3 驗收情境 7;`plan.md` § 待決問題 Q10、Q11
- [x] T128a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-09 的測試(`apply`(`tuning_body(4, None, None)`),`wait_applied`;`GET /api/session`、`GET /api/sessions/{name}`、`GET /api/downloads`、`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US3-API-09`),執行確認它因為「紀錄的是第一次的失敗(`verify`),UI 說不出最後停在哪」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-013、使用者故事 3 驗收情境 7;`plan.md` § 待決問題 Q11、Q12、Q19
- [x] T128b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-09 通過的程式碼;改回自動值也失敗時標成 `lost`、`endReason` 為 `OLLAMA_RESTART_FAILED`、釋放執行環境、清空下載佇列,那一筆記 `failed` 與最後一次失敗的階段,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T128a)
  - 🧪 `testplan.md` § US3-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § FR-013、使用者故事 3 驗收情境 7;`plan.md` § 待決問題 Q11、Q12、Q19
- [x] T129a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-10 的測試(各 `apply`(`tuning_body(4, None, None)`),`wait_applied`;`GET /api/session`、`GET /api/auth`;分隔註解寫 `# ---- 005 US3-API-10`),執行確認它因為「被 Colab 收回也標成 `OLLAMA_RESTART_FAILED`,UI 叫使用者「重新開啟」而不是說明被收回」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-013、info.x-apply-flow (5)(COLAB_NOT_FOUND、AUTH_REQUIRED);`plan.md` § 待決問題 Q11
- [x] T129b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-10 通過的程式碼;`COLAB_NOT_FOUND` 照 001 標成 `lost`、`endReason` 為 `RECLAIMED_BY_COLAB`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T129a)
  - 🧪 `testplan.md` § US3-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-013、info.x-apply-flow (5)(COLAB_NOT_FOUND、AUTH_REQUIRED);`plan.md` § 待決問題 Q11
- [x] T130a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-11 的測試(`apply`(`tuning_body(4, None, None)`),`wait_applied`,`GET /api/session`;分隔註解寫 `# ---- 005 US3-API-11`),執行確認它因為「失聯後的釋放沒有接住 `AdapterError`,例外讓套用的工作中止,`state` 停在 `applying_tuning`、使用者以為還在套用,執行環境繼續扣 compute units」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-013(釋放不了寫 releaseWarning)
- [x] T130b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-11 通過的程式碼;失聯後的釋放失敗時接住 `AdapterError`、寫 `releaseWarning`,`state` 不停在 `applying_tuning`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T130a)
  - 🧪 `testplan.md` § US3-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-013(釋放不了寫 releaseWarning)
- [x] T131a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-12 的測試(`apply`(`tuning_body(4, None, None)`);`GET /api/session`;放行 `gate`,等那一筆不是 `downloading`(最多 1 秒),`GET /api/downloads`;分隔註解寫 `# ---- 005 US3-API-12`),執行確認它因為「套用前呼叫下載佇列的 `interrupt()`,下載被標成失敗」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-011、使用者故事 3 驗收情境 3、使用者故事 3 獨立測試(applyTuning 的 DOWNLOAD_IN_PROGRESS);`research.md` § R10;`plan.md` § 待決問題 Q34
- [x] T131b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py`、`src/cgb/domain/errors.py` 只寫讓 US3-API-12 通過的程式碼;有模型正在下載時回 409 `DOWNLOAD_IN_PROGRESS`,`ApiError` 加 `message` 參數覆寫成「有模型正在下載,下載完才能套用」,不中斷下載,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T131a)
  - 🧪 `testplan.md` § US3-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-011、使用者故事 3 驗收情境 3、使用者故事 3 獨立測試(applyTuning 的 DOWNLOAD_IN_PROGRESS);`research.md` § R10;`plan.md` § 待決問題 Q34
- [x] T132a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-13 的測試(`bridge.ui.post("/api/session/tuning", json=tuning_body(4, None, None))`;放行 `gate`,讀完那一條串流;分隔註解寫 `# ---- 005 US3-API-13`),執行確認它因為「只看 UI 對話自己的計數,相容端點的請求進行中照樣重啟(或反過來)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-011、使用者故事 3 驗收情境 4(applyTuning 的 REQUESTS_IN_PROGRESS);`research.md` § R10
- [x] T132b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/api/chat.py`、`src/cgb/domain/errors.py`、`tests/e2e/test_locale.py` 只寫讓 US3-API-13 通過的程式碼;UI 對話與相容端點各記進行中的請求數,有任何一個在進行就回 409 `REQUESTS_IN_PROGRESS`;新代碼加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T132a)
  - 🧪 `testplan.md` § US3-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-011、使用者故事 3 驗收情境 4(applyTuning 的 REQUESTS_IN_PROGRESS);`research.md` § R10
- [x] T133a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-14 的測試(`apply`(`tuning_body(4, None, None)`);分隔註解寫 `# ---- 005 US3-API-14`),執行確認它因為「只判斷 `state != "none"`,開啟中或重連中也受理,`restart_ollama` 對還沒裝好或連不到的執行環境執行」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § 邊界情況(非就緒時按套用)(applyTuning 的 NO_READY_SESSION)
- [x] T133b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-14 通過的程式碼;工作階段不是 `ready` 時回 503 `NO_READY_SESSION`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T133a)
  - 🧪 `testplan.md` § US3-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § 邊界情況(非就緒時按套用)(applyTuning 的 NO_READY_SESSION)
- [x] T134a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-15 的測試(以 `asyncio.gather` 同時送 `apply(tuning_body(4, None, None))` 與 `apply(tuning_body(16, None, None))`;等閘門被走到後再送一次 `apply(tuning_body(8, None, None))`;放行閘門,`wait_applied`;分隔註解寫 `# ---- 005 US3-API-15`),執行確認它因為「先檢查、`await` 讀 `/api/ps` 之後才改狀態,兩個分頁都通過、遠端重啟兩次」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § 邊界情況(兩個分頁同時套用)、FR-012(applyTuning 的 TUNING_IN_PROGRESS)
- [x] T134b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py`、`src/cgb/domain/errors.py`、`tests/e2e/test_locale.py` 只寫讓 US3-API-15 通過的程式碼;通過檢查的同一步(沒有 `await`)就改成 `applying_tuning`;已在套用時回 409 `TUNING_IN_PROGRESS`,新代碼加進 `MESSAGES` 與 `tests/e2e/test_locale.py` 的 `API_ERRORS`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T134a)
  - 🧪 `testplan.md` § US3-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § 邊界情況(兩個分頁同時套用)、FR-012(applyTuning 的 TUNING_IN_PROGRESS)
- [x] T135a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-16 的測試(`apply`(`tuning_body(4, None, None)`);`GET /api/session`;分隔註解寫 `# ---- 005 US3-API-16`),執行確認它因為「套用前沒有檢查授權,重啟一半才 `AUTH_REQUIRED` 而失聯(Q15 已決定受理前擋下)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § (applyTuning 的 AUTH_REQUIRED);`plan.md` § 待決問題 Q15、Q37
- [x] T135b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py`、`src/cgb/services/auth.py` 只寫讓 US3-API-16 通過的程式碼;受理前照 `openSession` 呼叫 `auth.check()`,未登入回 409 `AUTH_REQUIRED`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T135a)
  - 🧪 `testplan.md` § US3-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § (applyTuning 的 AUTH_REQUIRED);`plan.md` § 待決問題 Q15、Q37
- [x] T136a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-17 的測試(`apply`(那一組本文);`GET /api/session`、`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US3-API-17`),執行確認它因為「套用的路由沒有呼叫 `tuning.parse_overrides`,範圍外的值交給轉接層,遠端回 `COLAB_INVALID_TUNING` 後改回自動值重啟(使用者看到「已改回自動值」而不是範圍說明)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-017(applyTuning 的 INVALID_REQUEST_BODY、INVALID_NUM_PARALLEL、INVALID_CONTEXT_LENGTH、INVALID_MAX_LOADED_MODELS);`plan.md` § 待決問題 Q31
- [x] T136b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/tuning.py`、`src/cgb/domain/tuning.py` 只寫讓 US3-API-17 通過的程式碼;`applyTuning` 先呼叫 `tuning.parse_overrides`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T136a)
  - 🧪 `testplan.md` § US3-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-017(applyTuning 的 INVALID_REQUEST_BODY、INVALID_NUM_PARALLEL、INVALID_CONTEXT_LENGTH、INVALID_MAX_LOADED_MODELS);`plan.md` § 待決問題 Q31
- [x] T137a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-18 的測試((a)送 `apply(tuning_body(33, None, None))`;(b)送 `apply(tuning_body(4, None, None))`;(c)送 `apply(tuning_body(4, None, None))`;分隔註解寫 `# ---- 005 US3-API-18`),執行確認它因為「檢查順序和合約 (1)~(6) 不同:先擋 `TUNING_IN_PROGRESS` 再驗本文,UI 收不到範圍說明」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-011、FR-017(applyTuning 的檢查順序)
- [x] T137b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/tuning.py`、`src/cgb/services/tuning.py` 只寫讓 US3-API-18 通過的程式碼;檢查順序照 `paths./session/tuning.post` 的 (1)~(6):本文 → 套用中 → 就緒 → 授權 → 下載 → 請求,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T137a)
  - 🧪 `testplan.md` § US3-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-011、FR-017(applyTuning 的檢查順序)
- [x] T138a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-19 的測試(`apply`(`tuning_body(None, None, 1)`),`wait_applied`;分隔註解寫 `# ---- 005 US3-API-19`),執行確認它因為「重啟前讀到幾個就全部重新載入(讓 Ollama 自己換出,分身 D6 已否決)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`components.schemas.NotReloadedModel`
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 9;`research.md` § R8
- [x] T138b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-19 通過的程式碼;依重啟前 `/api/ps` 的順序重新載入,載到新的 `maxLoadedModels` 為止,其餘列進 `notReloaded`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T138a)
  - 🧪 `testplan.md` § US3-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`components.schemas.NotReloadedModel`
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 9;`research.md` § R8
- [x] T139a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-20 的測試(`apply`(`tuning_body(None, None, 2)`);等 `first_gate` 被走到時記下 `preload.call_count`;放行,`wait_applied`;分隔註解寫 `# ---- 005 US3-API-20`);T138b 逐一 `await` 預先載入(`src/cgb/services/tuning.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「以 `asyncio.gather` 同時送預先載入,兩個模型同時爭顯示記憶體(research R8)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-012(依 /api/ps 的順序);`research.md` § R8
- [x] T139b [US3] 🟢 /tdd 綠燈:US3-API-20 由 T138b 逐一 `await` 預先載入(`src/cgb/services/tuning.py`)滿足,確認 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-20 通過的程式碼(依賴 T139a)
  - 🧪 `testplan.md` § US3-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-012(依 /api/ps 的順序);`research.md` § R8
- [x] T140a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-21 的測試(`apply`(`tuning_body(4, None, None)`),`wait_applied`;分隔註解寫 `# ---- 005 US3-API-21`),執行確認它因為「`maxLoadedModels.value` 為 None 時寫成 `models[:None or 0]`,一個都不載入」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q14
- [x] T140b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-21 通過的程式碼;`maxLoadedModels.value` 為 None 時全部重新載入,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T140a)
  - 🧪 `testplan.md` § US3-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q14
- [x] T141a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-22 的測試(`apply`(`tuning_body(4, None, None)`),`wait_applied`;`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US3-API-22`),執行確認它因為「預先載入失敗讓整次套用算失敗(改回自動值或失聯)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`、`components.schemas.NotReloadedModel`
  - 📎 `spec.md` § FR-012、FR-014;`plan.md` § 待決問題 Q14
- [x] T141b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-22 通過的程式碼;單一模型預先載入失敗時列進 `notReloaded`,套用仍算成功、照常寫類型覆蓋值,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T141a)
  - 🧪 `testplan.md` § US3-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`、`components.schemas.NotReloadedModel`
  - 📎 `spec.md` § FR-012、FR-014;`plan.md` § 待決問題 Q14
- [x] T142a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-23 的測試(`apply`(`tuning_body(4, None, None)`),`wait_applied`;分隔註解寫 `# ---- 005 US3-API-23`),執行確認它因為「讀 `/api/ps` 的 `AdapterError` 沒接住,受理時回 500 或套用的工作中止、`state` 停在 `applying_tuning`」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-012(info.x-apply-flow (1) 讀不到當作沒有已載入的模型)
- [x] T142b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-23 通過的程式碼;讀 `/api/ps` 丟 `AdapterError` 時當作沒有已載入的模型,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T142a)
  - 🧪 `testplan.md` § US3-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § FR-012(info.x-apply-flow (1) 讀不到當作沒有已載入的模型)
- [x] T143a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-24 的測試(`fake_clock.set(t + 50 秒)`,`apply`(`tuning_body(4, None, None)`);等閘門被走到,`fake_clock.set(t + 120 秒)`,`states_for(client, 0.3)`;放行,`wait_applied`,記下 `back_at = fake_clock.now()`,`GET /api/session`,再 `states_for(client, 0.3)`;分隔註解寫 `# ---- 005 US3-API-24`),執行確認它因為「`IdleMonitor` 只比 deadline、不看 `state`,套用到一半被 `IDLE_TIMEOUT` 結束」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § 邊界情況(重啟期間閒置倒數暫停);`research.md` § R10
- [x] T143b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/idle_monitor.py`、`src/cgb/services/tuning.py` 只寫讓 US3-API-24 通過的程式碼;`applying_tuning` 時暫停閒置倒數,回到 `ready` 時重設,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T143a)
  - 🧪 `testplan.md` § US3-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § 邊界情況(重啟期間閒置倒數暫停);`research.md` § R10
- [x] T144a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-25 的測試(`bridge.ui.post("/api/session/tuning", ...)`;等閘門被走到後,記下時間送 `bridge.ollama.post("/api/generate", json={"model": "qwen2.5:7b", "prompt": "hi"})`;再送 `bridge.ui.post("/api/chat", ...)` 與 `bridge.ui.post("/api/downloads", json={"models": ["qwen2.5:0.5b"]})`;分隔註解寫 `# ---- 005 US3-API-25`),執行確認它因為「相容端點只看有沒有 `base_url`(套用中仍在),把請求轉到正在重啟的遠端 Ollama」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § 使用者故事 3 驗收情境 8、FR-012(info.x-applying-state (2));`plan.md` § 待決問題 Q35
- [x] T144b [US3] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py` 只寫讓 US3-API-25 通過的程式碼;套用中回 001 工作階段未就緒的錯誤、不排隊,`_STATE_DESCRIPTIONS` 補 `applying_tuning`「工作階段正在套用 Ollama 設定」,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T144a)
  - 🧪 `testplan.md` § US3-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § 使用者故事 3 驗收情境 8、FR-012(info.x-applying-state (2));`plan.md` § 待決問題 Q35
- [x] T145a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-26 的測試(`apply`(`tuning_body(4, None, None)`);閘門被走到後送 `DELETE /api/session`,等 0.2 秒記下 `stop_session.call_count`;放行閘門(重啟成功),`wait_for_state(ui_client, "ended")`;分隔註解寫 `# ---- 005 US3-API-26`),執行確認它因為「套用中 `DELETE` 回 409 `NO_ACTIVE_SESSION`(結束的前提只認 `opening`、`ready`、`reconnecting`)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-26
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § info.x-applying-state (3)、FR-014;`plan.md` § 待決問題 Q12
- [x] T145b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/session_lifecycle.py`、`src/cgb/services/tuning.py` 只寫讓 US3-API-26 通過的程式碼;`endSession` 在 `applying_tuning` 也受理:停止套用、等進行中的 `colab exec` 結束再照 001 結束,那一筆記 `interrupted`、不寫類型覆蓋值,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T145a)
  - 🧪 `testplan.md` § US3-API-26
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`、`paths./tuning/overrides.get`、`components.schemas.RuntimeTypeTuningOverrideList`
  - 📎 `spec.md` § info.x-applying-state (3)、FR-014;`plan.md` § 待決問題 Q12
- [x] T146a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-27 的測試(以同一個 SQLite 檔跑第二個 app,`wait_until` `state` 不是 `applying_tuning` 且 `resuming` 為 false(最多 1 秒);`GET /api/session`、`GET /api/tuning/overrides`;分隔註解寫 `# ---- 005 US3-API-27`),執行確認它因為「恢復時看到 `applying_tuning` 不認得,照 001 當成未結束卻不接回、停在 `applying_tuning`」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § 邊界情況(後端在重啟到一半停機);`plan.md` § 待決問題 Q13、Q24、Q38
- [x] T146b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/services/tuning.py`、`src/cgb/api/__init__.py` 只寫讓 US3-API-27 通過的程式碼;恢復時看到 `applying_tuning`,以這次要求的值呼叫一次 `start_ollama`(已在執行就讀它的設定)、不呼叫 `restart_ollama`,那一筆記 `interrupted`、回到 `ready`;lifespan 結束時直接取消停在重啟中的套用工作,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T146a)
  - 🧪 `testplan.md` § US3-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § 邊界情況(後端在重啟到一半停機);`plan.md` § 待決問題 Q13、Q24、Q38
- [x] T147a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-28 的測試(跑第二個 app,`wait_for_state(client, "lost")`;`GET /api/session`、`GET /api/sessions/{name}`;分隔註解寫 `# ---- 005 US3-API-28`),執行確認它因為「被收回時只改 `sessions`,套用那一筆永遠停在 `in_progress`(UI 一直顯示套用中)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-28
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § 邊界情況(後端在重啟到一半停機)、info.x-applying-state (4);`plan.md` § 待決問題 Q13、Q33
- [x] T147b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/services/tuning.py` 只寫讓 US3-API-28 通過的程式碼;恢復時被 Colab 收回或 `start_ollama` 又失敗,那一筆記 `interrupted`(store.dbml 的寫入時機)、`endReason` 照 `info.x-apply-flow` (5),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T147a)
  - 🧪 `testplan.md` § US3-API-28
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`、`paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § 邊界情況(後端在重啟到一半停機)、info.x-applying-state (4);`plan.md` § 待決問題 Q13、Q33
- [x] T148a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-29 的測試(跑第二個 app,等 `state` 為 `ready`;`GET /api/session`;分隔註解寫 `# ---- 005 US3-API-29`),執行確認它因為「目前生效的設定只找 `result` 為 `applied` 的最新一筆(顯示 4,但遠端其實是自動值 8)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-29
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § 使用者故事 3 驗收情境 5(故事 1)、FR-013;`plan.md` § 待決問題 Q24
- [x] T148b [US3] 🟢 /tdd 綠燈:在 `src/cgb/repos/tunings.py`、`src/cgb/api/session.py` 只寫讓 US3-API-29 通過的程式碼;目前生效的設定取最新一筆有讀到設定的紀錄(含 `interrupted`,以及重啟成功、重新載入中的 `in_progress`),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T148a)
  - 🧪 `testplan.md` § US3-API-29
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.Session`、`components.schemas.OllamaStatus`
  - 📎 `spec.md` § 使用者故事 3 驗收情境 5(故事 1)、FR-013;`plan.md` § 待決問題 Q24
- [x] T149a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-30 的測試(`apply(tuning_body(4, None, None))`、`wait_applied`;`apply(tuning_body(8, None, None))`、`wait_applied`;`GET /api/sessions/{name}`、`GET /api/session`;分隔註解寫 `# ---- 005 US3-API-30`);T120b 每次套用追加一筆紀錄(`src/cgb/repos/tunings.py`),不更新開啟那一筆已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「套用時更新開啟那一筆而不是追加」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-API-30
  - ⚙ `contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-016、使用者故事 3 驗收情境 10、FR-015
- [x] T149b [US3] 🟢 /tdd 綠燈:US3-API-30 由 T120b 每次套用追加一筆紀錄(`src/cgb/repos/tunings.py`),不更新開啟那一筆滿足,確認 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-30 通過的程式碼(依賴 T149a)
  - 🧪 `testplan.md` § US3-API-30
  - ⚙ `contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`
  - 📎 `spec.md` § FR-016、使用者故事 3 驗收情境 10、FR-015
- [x] T150a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-33 的測試(送 `POST /api/session/restart`(`{"runtimeType": L4}`);放行閘門,`wait_applied`,`GET /api/session`;分隔註解寫 `# ---- 005 US3-API-33`),執行確認它因為「`restartSession` 的前提只擋 `ending`,套用中就結束了執行環境、開一台 L4,套用的工作接著對已不在的執行環境重新載入」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-33
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`
  - 📎 `spec.md` § 邊界情況(兩個分頁同時套用)、info.x-applying-state (3)(restartSession 的 TUNING_IN_PROGRESS)
- [x] T150b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/runtime_switch.py`、`src/cgb/api/session.py` 只寫讓 US3-API-33 通過的程式碼;`restartSession` 在 `applying_tuning` 時回 409 `TUNING_IN_PROGRESS`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T150a)
  - 🧪 `testplan.md` § US3-API-33
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`
  - 📎 `spec.md` § 邊界情況(兩個分頁同時套用)、info.x-applying-state (3)(restartSession 的 TUNING_IN_PROGRESS)
- [x] T151a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-34 的測試(送 `POST /api/session`(`{"runtimeType": T4}`);放行閘門,`wait_applied`;分隔註解寫 `# ---- 005 US3-API-34`);T120b 把 `applying_tuning` 加進 `ACTIVE_STATES` 與 `src/cgb/repos/sessions.py` 的進行中查詢(`openSession` 因此回 409 `SESSION_ALREADY_ACTIVE`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`active_slot` 或「已有工作階段」的判斷沒有涵蓋 `applying_tuning`,套用中可以再開一台(同時兩台在扣 compute units)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-API-34
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`
  - 📎 `spec.md` § info.x-applying-state (1)(openSession 的 SESSION_ALREADY_ACTIVE)
- [x] T151b [US3] 🟢 /tdd 綠燈:US3-API-34 由 T120b 把 `applying_tuning` 加進 `ACTIVE_STATES` 與 `src/cgb/repos/sessions.py` 的進行中查詢(`openSession` 因此回 409 `SESSION_ALREADY_ACTIVE`)滿足,確認 `src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US3-API-34 通過的程式碼(依賴 T151a)
  - 🧪 `testplan.md` § US3-API-34
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.OpenSessionInput`
  - 📎 `spec.md` § info.x-applying-state (1)(openSession 的 SESSION_ALREADY_ACTIVE)
- [x] T152a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-31 的測試(`apply`(`tuning_body(4, None, None)`);等 `preload_gate` 被走到,`GET /api/sessions/{name}`;放行,`wait_applied`;分隔註解寫 `# ---- 005 US3-API-31`),執行確認它因為「重啟成功後另外以 `clock.sleep` 等 `tunnel_ready` 或健康檢查一輪(15~30 秒)才切步驟,超出 90 秒」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-31
  - ⚙ `contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § NFR-002、SC-004、FR-015
- [x] T152b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-31 通過的程式碼;重啟成功就直接切到 `reloading_models`,不另等健康檢查或通道,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T152a)
  - 🧪 `testplan.md` § US3-API-31
  - ⚙ `contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`、`components.schemas.SessionRecordDetail`、`components.schemas.TuningRecord`、`paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § NFR-002、SC-004、FR-015
- [x] T153a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_tuning_apply.py` 寫 US3-API-32 的測試(連續送 10 次 `apply(tuning_body(4, None, None))`;之後先放行對話、讀完串流,再放行下載,等那一筆不是 `downloading`(最多 1 秒);分隔註解寫 `# ---- 005 US3-API-32`);T131b、T132b 的忙碌檢查(`src/cgb/services/tuning.py`;被擋下時不留任何旗標)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「被擋下時留了一個「準備套用」的旗標,第 2 次起回 `TUNING_IN_PROGRESS` 或把相容端點當成未就緒」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-API-32
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § SC-006、FR-011
- [x] T153b [US3] 🟢 /tdd 綠燈:US3-API-32 由 T131b、T132b 的忙碌檢查(`src/cgb/services/tuning.py`;被擋下時不留任何旗標)滿足,確認 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/tuning.py`、`src/cgb/api/tuning.py` 只寫讓 US3-API-32 通過的程式碼(依賴 T153a)
  - 🧪 `testplan.md` § US3-API-32
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`components.schemas.TuningOverrides`
  - 📎 `spec.md` § SC-006、FR-011
- [x] T154 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T120b~T153b 記下的重構清單(範圍限 `src/cgb/services/`、`src/cgb/repos/`、`src/cgb/api/`、`src/cgb/domain/`、`src/cgb/ollama_compat/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_api_tuning_apply.py` 的斷言(依賴 T153b)
  - 🧪 `testplan.md` § US3-API-01~US3-API-30、US3-API-33~US3-API-34、US3-API-31~US3-API-32
  - 📎 `testplan.md` § 4.2

### E4 資料庫(SQLite)

> 只驗套用在資料庫這一側的事實;DDL 已由故事 1 的 T038b、T041b、T042b 照 `contracts/store.dbml` 建出,這一節都是對照組;「套用那一筆」「改成成功」照 `testplan.md` § 4.3

- [x] T155a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-01 的測試(每種情況依序執行:①`UPDATE sessions SET state = 'applying_tuning', step = 'restarting_ollama' WHERE name = 'cgb-a'`;②`INSERT INTO session_transitions (session_name, at, state, step) VALUES ('cgb-a', '2026-11-15T09:00:00Z', 'applying_tuning', 'restarting_ollama')`;③`UPDATE sessions SET step = 'reloading_models' WHERE name = 'cgb-a'`;④`session_transitions` 再寫一筆 `('cgb-a', '2026-11-15T09:00:45Z', 'applying_tuning', 'reloading_models')`;⑤`INSERT INTO sessions (name, runtime_type_gpu, runtime_type_high_mem, state, active_slot, step, opened_at) VALUES ('cgb-b', 'T4', 0, 'opening', 1, 'allocating', '2026-11-15T09:01:00Z')`;⑥`UPDATE sessions SET state = 'applying' WHERE name = 'cgb-a'`;⑦`UPDATE sessions SET step = 'restarting' WHERE name = 'cgb-a'`;⑧`session_transitions` 寫一筆 `state='applying_tuning'`、`step='reloading'`;分隔註解寫 `# ---- 005 US3-DB-01`);US1 的 T038b(全新庫)與 T042b(重建 `sessions_new`、`session_transitions_new`)照 `contracts/store.dbml` 收下 `applying_tuning` 與兩個新 step(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`sessions` 只在全新庫的 DDL 加了 `applying_tuning`,遷移時 `sessions_new` 照抄 001 的 CHECK,升級過的使用者一套用就寫不進去」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-DB-01
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-012、FR-015、使用者故事 3 驗收情境 8
- [x] T155b [US3] 🟢 /tdd 綠燈:US3-DB-01 由 US1 的 T038b(全新庫)與 T042b(重建 `sessions_new`、`session_transitions_new`)照 `contracts/store.dbml` 收下 `applying_tuning` 與兩個新 step(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-01 通過的程式碼(依賴 T155a)
  - 🧪 `testplan.md` § US3-DB-01
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-012、FR-015、使用者故事 3 驗收情境 8
- [x] T156a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-02 的測試(呼叫 `create_schema(conn)`,再讀 `cgb-odd` 的 `sessions.step` 與它的 `session_transitions.step`;分隔註解寫 `# ---- 005 US3-DB-02`);US1 的 T042b 照 `contracts/store.dbml` 只寫 note、不加 state 與 step 的跨欄位 CHECK(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「重建時把 state 與 step 的對應寫成跨欄位 CHECK(例如 `step IS NULL OR state IN ('opening', 'applying_tuning')`,或逐一列出兩組對應;Q25 定為只寫 note),既有資料只要有一筆不合,`INSERT ... SELECT` 就丟 `IntegrityError`、整個遷移 rollback,之後每次啟動都失敗、後端起不來」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-DB-02
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-015;`plan.md` § 待決問題 Q25
- [x] T156b [US3] 🟢 /tdd 綠燈:US3-DB-02 由 US1 的 T042b 照 `contracts/store.dbml` 只寫 note、不加 state 與 step 的跨欄位 CHECK(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-02 通過的程式碼(依賴 T156a)
  - 🧪 `testplan.md` § US3-DB-02
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-015;`plan.md` § 待決問題 Q25
- [x] T157a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-03 的測試(每種情況依序執行:①寫入「套用那一筆」;②再寫一筆 `cgb-a` 的套用、`result='in_progress'`、`at='2026-11-15T09:00:01Z'`、`requested_num_parallel=8`;③寫一筆 `cgb-b` 的套用、`result='in_progress'`;④把 ① 改成成功;⑤再寫一筆 `cgb-a` 的套用、`at='2026-11-15T09:10:00Z'`、`requested_num_parallel=8`、`result='in_progress'`;⑥把 ⑤ 照「改成成功」改,但 `num_parallel=8`、`finished_at='2026-11-15T09:11:00Z'`;⑦讀 `SELECT trigger, result, requested_num_parallel FROM session_tunings WHERE session_name = 'cgb-a' ORDER BY at, id`;分隔註解寫 `# ---- 005 US3-DB-03`);US1 的 T038b、T041b 建出 `uq_session_tunings_in_progress`(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「沒建 `uq_session_tunings_in_progress`,兩個分頁同時套用時兩筆 `in_progress` 都寫得進去,兩個流程同時重啟遠端 Ollama」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-DB-03
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-016、使用者故事 3 驗收情境 10、邊界情況(兩個分頁同時按套用)
- [x] T157b [US3] 🟢 /tdd 綠燈:US3-DB-03 由 US1 的 T038b、T041b 建出 `uq_session_tunings_in_progress`(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-03 通過的程式碼(依賴 T157a)
  - 🧪 `testplan.md` § US3-DB-03
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-016、使用者故事 3 驗收情境 10、邊界情況(兩個分頁同時按套用)
- [x] T158a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-04 的測試(每種情況依「套用那一筆」的欄位依序寫入,全部寫在 `cgb-a`、`at` 每句加 1 秒;除了 ⑨,`result` 都不是 `in_progress`,寫不寫得進去不受 `uq_session_tunings_in_progress` 影響:①`result='applied'`、`finished_at` 有值;②`result='fell_back_to_auto'`、`attempt='auto_fallback'`、`finished_at` 有值;③`result='failed'`、`finished_at` 有值;④`result='interrupted'`、`finished_at` 有值、`probed_at`、五項值與來源照「改成成功」(後端恢復時讀到的設定,Q13、Q24);⑤`result='interrupted'`、`finished_at` 有值,硬體與五項值都是 NULL;⑥`result='success'`;⑦`result='fallback'`;⑧`result` NULL;⑨`result='in_progress'`、`finished_at` 有值;⑩`result='applied'`、`finished_at` NULL;⑪`result='applied'`、`finished_at` 有值、`attempt` NULL;⑫`result='applied'`、`finished_at` 有值、`attempt='auto'`;分隔註解寫 `# ---- 005 US3-DB-04`);US1 的 T038b 照 `contracts/store.dbml` 寫 `result` 等列舉欄位的 `CHECK IN`(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`result` 的 CHECK 照 Q12 的另一個選項只列 `applied`、`fell_back_to_auto`,受理時的 `in_progress`、失聯的 `failed`、中斷的 `interrupted` 寫不進去,套用一開始就失敗」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-DB-04
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-016、FR-013;`plan.md` § 待決問題 Q44
- [x] T158b [US3] 🟢 /tdd 綠燈:US3-DB-04 由 US1 的 T038b 照 `contracts/store.dbml` 寫 `result` 等列舉欄位的 `CHECK IN`(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-04 通過的程式碼(依賴 T158a)
  - 🧪 `testplan.md` § US3-DB-04
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-016、FR-013;`plan.md` § 待決問題 Q44
- [x] T159a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-05 的測試(每種情況依序寫入套用的列(`result` 不是 `in_progress` 的都帶 `finished_at`):①`cgb-a`:`result='fell_back_to_auto'`、`attempt='auto_fallback'`、`requested_num_parallel=32`、`requested_context_length=131072`、`requested_max_loaded_models=4`、`reason_code='COLAB_REMOTE_ERROR'`、`remote_stage='verify'`、`message='手動設定沒有套用成功,已改回自動值'`、`num_parallel=8`、五個 `*_source` 為 `auto`、其他五項值與硬體照「改成成功」;②`cgb-b`:`result='failed'`、`attempt='auto_fallback'`、`reason_code='COLAB_INVALID_TUNING'`、`remote_stage='start'`,硬體與五項值、五個來源都是 NULL;③`cgb-c`:三個 `requested_*` 都是 NULL(全部改回自動);④~⑧ 都寫在 `cgb-d`、`result='failed'`、帶 `finished_at`(不是 `in_progress`,前一句沒被擋時不會讓下一句撞到唯一索引):④`requested_num_parallel=33`;⑤`requested_context_length=2047`;⑥`requested_max_loaded_models=5`;⑦`remote_stage='unknown'`;⑧`remote_stage='Verify'`;分隔註解寫 `# ---- 005 US3-DB-05`);US1 的 T038b 照 `contracts/store.dbml` 建出三個 `requested_*` 與它們的範圍 CHECK(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`session_tunings` 只存實際套用的值,沒有 `requested_*`,改回自動值的那一筆讀不出使用者要求的 32、131072、4(Q20 定為紀錄要顯示)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-DB-05
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-016、FR-013、FR-017
- [x] T159b [US3] 🟢 /tdd 綠燈:US3-DB-05 由 US1 的 T038b 照 `contracts/store.dbml` 建出三個 `requested_*` 與它們的範圍 CHECK(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-05 通過的程式碼(依賴 T159a)
  - 🧪 `testplan.md` § US3-DB-05
  - ⚙ `contracts/store.dbml` § `Table session_tunings`
  - 📎 `spec.md` § FR-016、FR-013、FR-017
- [x] T160a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-06 的測試(每種情況讀 `PRAGMA table_info(session_tuning_models)`、`PRAGMA foreign_key_list(session_tuning_models)`,再依序寫入 `(tuning_id, position, model, reason, reason_code)`:①`(X, 0, 'qwen2.5:7b', NULL, NULL)`;②`(X, 1, 'llama3.2:3b', 'OVER_LIMIT', NULL)`;③`(X, 2, 'gemma3:1b', 'PRELOAD_FAILED', 'OLLAMA_SERVER_ERROR')`;④`(Y, 0, 'qwen2.5:7b', NULL, NULL)`;⑤`(X, 1, 'phi4:14b', NULL, NULL)`;⑥`(X, 3, 'phi4:14b', 'over_limit', NULL)`;⑦`(X, 4, 'phi4:14b', 'SKIPPED', NULL)`;⑧`(X, 5, NULL, NULL, NULL)`;⑨`(X, NULL, 'phi4:14b', NULL, NULL)`(⑥~⑧ 各用不同的 `position`,被擋只會是因為 CHECK 或 NOT NULL);最後讀 `SELECT position, model, reason FROM session_tuning_models WHERE tuning_id = X ORDER BY position`;分隔註解寫 `# ---- 005 US3-DB-06`);US1 的 T038b 照 `contracts/store.dbml` 建出 `session_tuning_models`(`reason` 可為空、外鍵指到 `session_tunings`,`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`reason` 設成 NOT NULL,只記得下沒有重新載入的模型,紀錄頁的「已重新載入」永遠是空的(FR-012 要依 `/api/ps` 順序重新載入,S3 `reloaded`)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-DB-06
  - ⚙ `contracts/store.dbml` § `Table session_tuning_models`
  - 📎 `spec.md` § FR-012、FR-016、使用者故事 3 驗收情境 9
- [x] T160b [US3] 🟢 /tdd 綠燈:US3-DB-06 由 US1 的 T038b 照 `contracts/store.dbml` 建出 `session_tuning_models`(`reason` 可為空、外鍵指到 `session_tunings`,`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-06 通過的程式碼(依賴 T160a)
  - 🧪 `testplan.md` § US3-DB-06
  - ⚙ `contracts/store.dbml` § `Table session_tuning_models`
  - 📎 `spec.md` § FR-012、FR-016、使用者故事 3 驗收情境 9
- [x] T161a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-07 的測試(每種情況依序執行:①`UPDATE sessions SET state = 'lost', active_slot = NULL, step = NULL, end_reason = 'OLLAMA_RESTART_FAILED', reason_code = 'COLAB_INVALID_TUNING', message = '遠端 Ollama 重啟失敗,可以重新開啟一個工作階段', ended_at = '2026-11-15T09:03:00Z' WHERE name = 'cgb-a'`;②`INSERT INTO session_transitions (session_name, at, state, step, end_reason, reason_code) VALUES ('cgb-a', '2026-11-15T09:03:00Z', 'lost', NULL, 'OLLAMA_RESTART_FAILED', 'COLAB_INVALID_TUNING')`;③插入 `sessions` 一筆 `cgb-new`(`opening`,`active_slot=1`);分隔註解寫 `# ---- 005 US3-DB-07`);US1 的 T042b 重建時不補 `end_reason` 的 CHECK(`src/cgb/db/schema.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「趁重建替 `end_reason` 補了 CHECK,卻照 001 的六個值列,`OLLAMA_RESTART_FAILED` 寫不進去,改回自動值也失敗時結束工作階段那一步丟 `IntegrityError`,工作階段卡在 `applying_tuning`、執行環境沒有釋放(FR-013)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q54)
  - 🧪 `testplan.md` § US3-DB-07
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-013、使用者故事 3 驗收情境 7;`plan.md` § 待決問題 Q22
- [x] T161b [US3] 🟢 /tdd 綠燈:US3-DB-07 由 US1 的 T042b 重建時不補 `end_reason` 的 CHECK(`src/cgb/db/schema.py`)滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-07 通過的程式碼(依賴 T161a)
  - 🧪 `testplan.md` § US3-DB-07
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-013、使用者故事 3 驗收情境 7;`plan.md` § 待決問題 Q22
- [x] T162 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T155b~T161b 記下的重構清單(範圍限 `src/cgb/db/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_db_schema.py` 的斷言(依賴 T161b)
  - 🧪 `testplan.md` § US3-DB-01~US3-DB-07
  - 📎 `testplan.md` § 4.3

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(Playwright)接測試行程內真的後端(`tests/e2e/conftest.py` 的 `e2e_servers`,UI 127.0.0.1:8781),轉接層用替身;e2e 用固定 port,同一時間只跑一份

- [x] T163a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us3_apply.py` 寫 US3-AJ-01 的測試(使用者在設定卡把平行數改成 4,按「套用並重啟 Ollama」並在確認視窗按確認;分隔註解寫 `# ---- 005 US3-AJ-01`),執行確認它因為「確認視窗少了重新載入的說明;重啟中仍顯示就緒;回到就緒後仍顯示舊設定」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-01
  - ⚙ `prototype/index.html` § `[data-state="edit-tuning"]`、`#et-fields`、`#apply`、`#edit-clear`、`[data-state="confirm-apply"]`、`#ca-rows`、`#ca-effects`、`#confirm-apply`、`[data-state="restarting"]`、`[data-state="reloading"]`、`[data-state="${view}"]`、`[data-state="ready-manual"]`;`contracts/ui.openapi.yaml` § `paths./session/tuning.post`
  - 📎 `spec.md` § FR-010、FR-012、FR-015;`research.md` § R11;`plan.md` § 待決問題 Q18、Q21、Q57
- [x] T163b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js`、`src/cgb/static/js/view.js`、`src/cgb/static/js/header.js` 只寫讓 US3-AJ-01 通過的程式碼;設定卡可修改三項並按「套用並重啟 Ollama」,確認視窗寫出會重啟、要重新載入、這段時間無法對話與送請求;套用中照 001 開啟步驟的方式依序顯示「重啟 Ollama」「重新載入模型」(`[data-apply-steps]`、`[data-apply-elapsed]` 寫進目前的畫面);`applying_tuning` 與 `restarting_ollama`、`reloading_models` 加進 `src/cgb/static/js/session.js` 與 `src/cgb/static/js/header.js` 的狀態與步驟標籤,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T163a)
  - 🧪 `testplan.md` § US3-AJ-01
  - ⚙ `prototype/index.html` § `[data-state="edit-tuning"]`、`#et-fields`、`#apply`、`#edit-clear`、`[data-state="confirm-apply"]`、`#ca-rows`、`#ca-effects`、`#confirm-apply`、`[data-state="restarting"]`、`[data-state="reloading"]`、`[data-state="${view}"]`、`[data-state="ready-manual"]`;`contracts/ui.openapi.yaml` § `paths./session/tuning.post`
  - 📎 `spec.md` § FR-010、FR-012、FR-015;`research.md` § R11;`plan.md` § 待決問題 Q18、Q21、Q57
- [x] T164a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us3_apply.py` 寫 US3-AJ-02 的測試(使用者改平行數並按套用並確認;分隔註解寫 `# ---- 005 US3-AJ-02`),執行確認它因為「擋下後下載被中斷;沒有說明原因」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-02
  - ⚙ `prototype/index.html` § `[data-state="apply-blocked-download"]`、`#blocked-download-text`、`[data-state="${state}"]`、`[data-state="apply-blocked-request"]`、`#blocked-request-text`、`[data-state="apply-conflict"]`、`[data-state="apply-not-ready"]`、`[data-state="apply-auth-required"]`、`[data-state="apply-invalid"]`、`#apply-invalid-note`;`contracts/ui.openapi.yaml` § `paths./session/tuning.post`
  - 📎 `spec.md` § FR-011;`plan.md` § 待決問題 Q57
- [x] T164b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US3-AJ-02 通過的程式碼;套用回 409、503、400 時依代碼顯示對應的說明(`[data-error-message]` 寫進那一個狀態),不改工作階段與下載;`apply-blocked-request`、`apply-conflict`、`apply-not-ready`、`apply-auth-required`、`apply-invalid` 沒有案例斷言,完成報告列為未直接驗證,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T164a)
  - 🧪 `testplan.md` § US3-AJ-02
  - ⚙ `prototype/index.html` § `[data-state="apply-blocked-download"]`、`#blocked-download-text`、`[data-state="${state}"]`、`[data-state="apply-blocked-request"]`、`#blocked-request-text`、`[data-state="apply-conflict"]`、`[data-state="apply-not-ready"]`、`[data-state="apply-auth-required"]`、`[data-state="apply-invalid"]`、`#apply-invalid-note`;`contracts/ui.openapi.yaml` § `paths./session/tuning.post`
  - 📎 `spec.md` § FR-011;`plan.md` § 待決問題 Q57
- [x] T165a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us3_apply.py` 寫 US3-AJ-03 的測試(使用者把平行數改成 16 並套用確認;分隔註解寫 `# ---- 005 US3-AJ-03`),執行確認它因為「失敗後直接結束工作階段;改回自動值後仍顯示 16」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-03
  - ⚙ `prototype/index.html` § `[data-state="fallback-restarting"]`、`#fb-note`、`[data-state="ready-fallback"]`、`#t-fallback`
  - 📎 `spec.md` § FR-013;`plan.md` § 待決問題 Q20
- [x] T165b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js`、`src/cgb/static/js/view.js` 只寫讓 US3-AJ-03 通過的程式碼;改回自動值的重啟中顯示 `fallback-restarting`,回到就緒後設定卡說明「手動設定沒有套用成功,已改回自動值」並列出要求的值,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T165a)
  - 🧪 `testplan.md` § US3-AJ-03
  - ⚙ `prototype/index.html` § `[data-state="fallback-restarting"]`、`#fb-note`、`[data-state="ready-fallback"]`、`#t-fallback`
  - 📎 `spec.md` § FR-013;`plan.md` § 待決問題 Q20
- [x] T166a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us3_apply.py` 寫 US3-AJ-04 的測試(使用者把同時載入模型數改成 1 並套用確認;分隔註解寫 `# ---- 005 US3-AJ-04`),執行確認它因為「全部重新載入;沒有列出沒重新載入的模型」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-04
  - ⚙ `prototype/index.html` § `[data-state="ready-not-reloaded"]`、`#t-not-reloaded`、`[data-state="ready-preload-failed"]`、`#t-preload-failed`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q57
- [x] T166b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US3-AJ-04 通過的程式碼;回到就緒後列出沒有重新載入的模型;預先載入失敗的說明照原型 `ready-preload-failed`(沒有案例斷言,完成報告列為未直接驗證),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T166a)
  - 🧪 `testplan.md` § US3-AJ-04
  - ⚙ `prototype/index.html` § `[data-state="ready-not-reloaded"]`、`#t-not-reloaded`、`[data-state="ready-preload-failed"]`、`#t-preload-failed`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q57
- [x] T167a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us3_apply.py` 寫 US3-AJ-05 的測試(使用者套用確認;分隔註解寫 `# ---- 005 US3-AJ-05`),執行確認它因為「兩次失敗後工作階段停在套用中;結束原因顯示成一般的失聯」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-05
  - ⚙ `prototype/index.html` § `[data-state="lost-restart"]`、`#lr-message`、`#lr-requested`、`#lr-stage`
  - 📎 `spec.md` § FR-013;`plan.md` § 待決問題 Q19
- [x] T167b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js`、`src/cgb/static/js/history.js` 只寫讓 US3-AJ-05 通過的程式碼;`OLLAMA_RESTART_FAILED` 加進 `src/cgb/static/js/session.js` 的結束原因與畫面對應,以及 `src/cgb/static/js/history.js` 的結束原因標籤;畫面顯示「重啟 Ollama 失敗」、要求的值與失敗的階段,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T167a)
  - 🧪 `testplan.md` § US3-AJ-05
  - ⚙ `prototype/index.html` § `[data-state="lost-restart"]`、`#lr-message`、`#lr-requested`、`#lr-stage`
  - 📎 `spec.md` § FR-013;`plan.md` § 待決問題 Q19
- [x] T168a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_005_us3_apply.py` 寫 US3-AJ-06 的測試(使用者到紀錄頁點這一筆;分隔註解寫 `# ---- 005 US3-AJ-06`),執行確認它因為「只留最後一筆;套用的紀錄沒有要求的值」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-06
  - ⚙ `prototype/history.html` § `[data-state="tuning-log"]`、`#d-body`、`.tuning-table`;`contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`
  - 📎 `spec.md` § FR-016;`plan.md` § 待決問題 Q20
- [x] T168b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/history.html`、`src/cgb/static/js/history.js`、`src/cgb/static/js/view.js` 只寫讓 US3-AJ-06 通過的程式碼;紀錄頁的明細依時間列出開啟與每一次套用,套用的那幾筆寫出要求的值與結果,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T168a)
  - 🧪 `testplan.md` § US3-AJ-06
  - ⚙ `prototype/history.html` § `[data-state="tuning-log"]`、`#d-body`、`.tuning-table`;`contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`
  - 📎 `spec.md` § FR-016;`plan.md` § 待決問題 Q20
- [x] T169 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T163b~T168b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T168b)
  - 🧪 `testplan.md` § US3-AJ-01~US3-AJ-06
  - 📎 `testplan.md` § 4.4

### 介面覆蓋(US3)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`(故事 3 擴充:套用並重啟) | T121b | T121a |
| `ui-events.asyncapi.yaml` § `operations.sendModelsUpdated` | T121b | T121a |
| `colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`(故事 3 擴充:套用並重啟) | T100b~T117b | T100a~T117a |
| `ui.openapi.yaml` § `paths./session.get`(故事 3 擴充:套用並重啟) | T120b~T121b、T125b~T130b、T138b~T148b | T120a~T121a、T125a~T130a、T138a~T148a |
| `ui.openapi.yaml` § `paths./session.post`(故事 3 擴充:套用並重啟) | T122b、T151b | T122a、T151a |
| `ui.openapi.yaml` § `paths./session/restart.post`(故事 3 擴充:套用並重啟) | T150b | T150a |
| `ui.openapi.yaml` § `paths./session/tuning.post` | T120b~T145b、T152b~T153b、T163b~T164b | T120a~T145a、T152a~T153a、T163a~T164a |
| `ui.openapi.yaml` § `paths./tuning/overrides.get`(故事 3 擴充:套用並重啟) | T122b~T123b、T125b、T128b、T141b、T145b | T122a~T123a、T125a、T128a、T141a、T145a |
| `ui.openapi.yaml` § `paths./sessions/{name}.get`(故事 3 擴充:套用並重啟) | T128b、T147b、T149b、T152b、T168b | T128a、T147a、T149a、T152a、T168a |
| `store.dbml` § `Table sessions`(故事 3 擴充:套用並重啟) | T155b~T156b、T161b | T155a~T156a、T161a |
| `store.dbml` § `Table session_transitions`(故事 3 擴充:套用並重啟) | T155b~T156b、T161b | T155a~T156a、T161a |
| `store.dbml` § `Table session_tunings`(故事 3 擴充:套用並重啟) | T157b~T159b | T157a~T159a |
| `store.dbml` § `Table session_tuning_models`(故事 3 擴充:套用並重啟) | T160b | T160a |
| `history.html` § `[data-state="tuning-log"]`(故事 3 擴充:套用並重啟) | T168b | T168a |
| `index.html` § `[data-state="ready-fallback"]` | T165b | T165a |
| `index.html` § `[data-state="ready-not-reloaded"]` | T166b | T166a |
| `index.html` § `[data-state="ready-preload-failed"]` | T166b | T166a |
| `index.html` § `[data-state="ready-manual"]`(故事 3 擴充:套用並重啟) | T163b | T163a |
| `index.html` § `[data-state="edit-tuning"]` | T163b | T163a |
| `index.html` § `[data-state="apply-invalid"]` | T164b | T164a |
| `index.html` § `[data-state="apply-blocked-download"]` | T164b | T164a |
| `index.html` § `[data-state="apply-blocked-request"]` | T164b | T164a |
| `index.html` § `[data-state="apply-conflict"]` | T164b | T164a |
| `index.html` § `[data-state="apply-not-ready"]` | T164b | T164a |
| `index.html` § `[data-state="apply-auth-required"]` | T164b | T164a |
| `index.html` § `[data-state="confirm-apply"]` | T163b | T163a |
| `index.html` § `[data-state="restarting"]` | T163b | T163a |
| `index.html` § `[data-state="reloading"]` | T163b | T163a |
| `index.html` § `[data-state="fallback-restarting"]` | T165b | T165a |
| `index.html` § `[data-state="lost-restart"]` | T167b | T167a |
| `index.html` § `[data-state="${state}"]` | T164b | T164a |
| `index.html` § `[data-state="${view}"]` | T163b | T163a |

### 測試案例覆蓋(US3)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US3-CLI-01~US3-CLI-18 | T100a~T117a | T100b~T117b | T118 |
| US3-CLI-19 | — | — | T119(📏) |
| US3-API-01~US3-API-30、US3-API-33~US3-API-34、US3-API-31~US3-API-32 | T120a~T153a | T120b~T153b | T154 |
| US3-DB-01~US3-DB-07 | T155a~T161a | T155b~T161b | T162 |
| US3-AJ-01~US3-AJ-06 | T163a~T168a | T163b~T168b | T169 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 再加 `uv run pytest -m realrun_local -q -p no:cacheprovider` 全綠(含 `tests/e2e/test_locale.py` 加了 `REQUESTS_IN_PROGRESS`、`TUNING_IN_PROGRESS`、`tests/integration/test_fake_signatures.py` 比對到 `restart_ollama`);重構任務前後的測試結果相同;`specs/005-ollama-machine-tuning/measurements.md` 有 US3-CLI-19 的數字

---

## Phase 5: 全域測試區

**Purpose**: 照 `testplan.md` § 5 驗證跨故事的 NFR 與 SC;故事裡已經有案例涵蓋的彙整見 `testplan.md` § 5.1,這裡排 § 5.2 的 4 個 📏 實跑案例與 1 個行為測試案例。結果寫進 `specs/005-ollama-machine-tuning/measurements.md`

### 整合實跑

> 時機為「整合」的實跑案例:要開真的 Colab、花 compute units、需要使用者本人在場。**每一個任務執行前先停下問使用者本人**,同意之後才照 001 testplan 的實跑共同護欄 P1~P9 做(名稱前綴 `cgb-test-`、預算、P3 收尾);T4 一台(G-02、G-03、G-04 共用)與 A100 一台,每台 30 分鐘內(`plan.md` § 待決問題 Q29);不讀寫桌機的 `~/.config/colab-cli/`,一律用暫存的 `HOME`;token 與 endpoint 不印出,比對只印長度與 sha256 前 8 碼;只在桌機上跑,不碰 Tower、Pi、NPM、AdGuard

- [x] T170 [G] 📏 量測:撰寫 `tests/realrun/test_005_g_01.py`(標 `realrun`),開一台 A100 的 `cgb-test-` 工作階段到就緒、下載 `qwen2.5:7b`,暖機一次後以平行數 1(開啟或 `POST /api/session/tuning` 套用覆蓋)與自動值各經相容端點把同一批 16 題同時送出 3 次(每題 `num_predict` 128、`temperature` 0),記下每次總耗時與兩組的中位數、量測期間 `/api/ps` 的 `size_vram` 與 `size`、遠端 `/root/cgb-ollama-serve.log` 的 `server config` 裡五個環境變數與 `n_seq_max`,和門檻(自動值中位數 ≤ 平行數 1 的 60%;`size_vram` 等於 `size`;`n_seq_max` 等於套用的平行數)比較,結果寫進 `specs/005-ollama-machine-tuning/measurements.md`;開 Colab A100、花 compute units、需要本人在場;照 001 testplan 的實跑共同護欄 P1~P9(`specs/001-session-model-catalog/testplan.md` § 實跑案例的共同護欄):名稱前綴 `cgb-test-`、本台 30 分鐘內(`plan.md` § 待決問題 Q29)、結束後照 P3 確認 `colab sessions` 沒有 `cgb-test-` 開頭的工作階段;不讀寫桌機的 `~/.config/colab-cli/`,一律用暫存的 `HOME`;token 與 endpoint 不印出,比對只印長度與 sha256 前 8 碼;**執行前先停下問使用者本人**,同意之後才開始;判定者:腳本;樣本:固定 16 題(未用來調整級距)
  - 🧪 `testplan.md` § G-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`、`paths./session.post`
  - 📎 `spec.md` § SC-001、FR-002
- [x] T171 [G] 📏 量測:撰寫 `tests/realrun/test_005_g_02.py`(標 `realrun`),在 T4 的 `cgb-test-` 工作階段(和 G-03、G-04 共用同一台,`plan.md` § 待決問題 Q29)以 G-01 的同一套量法量平行數 1 與自動值,記下兩組的中位數、`size_vram` 與 `size`、遠端 log 有沒有 `flash_attn = enabled` 與 `K (q8_0)`,另驗合約的預設路徑、URL 與秒數在 Colab 上成立(`plan.md` § 待決問題 Q52),和門檻(自動值中位數 ≤ 平行數 1 的 85%;`size_vram` 等於 `size`;兩行 log 都在)比較,結果寫進 `specs/005-ollama-machine-tuning/measurements.md`;開 Colab T4、花 compute units、需要本人在場;照 001 testplan 的實跑共同護欄 P1~P9(`specs/001-session-model-catalog/testplan.md` § 實跑案例的共同護欄):名稱前綴 `cgb-test-`、本台 30 分鐘內(`plan.md` § 待決問題 Q29)、結束後照 P3 確認 `colab sessions` 沒有 `cgb-test-` 開頭的工作階段;不讀寫桌機的 `~/.config/colab-cli/`,一律用暫存的 `HOME`;token 與 endpoint 不印出,比對只印長度與 sha256 前 8 碼;**執行前先停下問使用者本人**,同意之後才開始;判定者:腳本;樣本:同 G-01
  - 🧪 `testplan.md` § G-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`;`contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`paths./exec/restart-ollama.post`
  - 📎 `spec.md` § SC-002、FR-002
- [x] T172 [G] 📏 量測:撰寫 `tests/realrun/test_005_g_03.py`(標 `realrun`),在 G-02 的那一台 T4 之前,以 005 的程式 `POST /api/session` 開一台 T4 到就緒,記下開啟到就緒的秒數,和 004 的同類型量測(`specs/004-chat-hf-curated-queue/measurements.md` 與完成報告的紀錄)比較,門檻是增加不超過 5 秒,結果寫進 `specs/005-ollama-machine-tuning/measurements.md`;開 Colab T4、花 compute units、需要本人在場(和 G-02、G-04 同一台);照 001 testplan 的實跑共同護欄 P1~P9(`specs/001-session-model-catalog/testplan.md` § 實跑案例的共同護欄):名稱前綴 `cgb-test-`、本台 30 分鐘內(`plan.md` § 待決問題 Q29)、結束後照 P3 確認 `colab sessions` 沒有 `cgb-test-` 開頭的工作階段;不讀寫桌機的 `~/.config/colab-cli/`,一律用暫存的 `HOME`;token 與 endpoint 不印出,比對只印長度與 sha256 前 8 碼;**執行前先停下問使用者本人**,同意之後才開始;判定者:腳本;樣本:一次開啟(與 004 比)
  - 🧪 `testplan.md` § G-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § SC-003、NFR-001
- [x] T173 [G] 📏 量測:撰寫 `tests/realrun/test_005_g_04.py`(標 `realrun`),在 G-02 的 T4 工作階段就緒、已載入 `qwen2.5:7b`、沒有下載與請求時,以 `POST /api/session/tuning` 套用平行數 4,記下確認到回到就緒(不含重新載入模型)的秒數、之後 `/api/ps` 是否列出 `qwen2.5:7b`、遠端 log 的 `n_seq_max`,和門檻(90 秒內;列出 `qwen2.5:7b`;`n_seq_max` 為 4)比較,結果寫進 `specs/005-ollama-machine-tuning/measurements.md`;開 Colab T4、花 compute units、需要本人在場(和 G-02、G-03 同一台);照 001 testplan 的實跑共同護欄 P1~P9(`specs/001-session-model-catalog/testplan.md` § 實跑案例的共同護欄):名稱前綴 `cgb-test-`、本台 30 分鐘內(`plan.md` § 待決問題 Q29)、結束後照 P3 確認 `colab sessions` 沒有 `cgb-test-` 開頭的工作階段;不讀寫桌機的 `~/.config/colab-cli/`,一律用暫存的 `HOME`;token 與 endpoint 不印出,比對只印長度與 sha256 前 8 碼;**執行前先停下問使用者本人**,同意之後才開始;判定者:腳本;樣本:一次套用
  - 🧪 `testplan.md` § G-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/tuning.post`;`contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`
  - 📎 `spec.md` § SC-004、NFR-002、FR-012

### 全域案例

> 不開 Colab;替身的 token 與轉發位址是已知的假值,測試行程內攔截所有對外連線,不對 127.0.0.1:11434 送任何請求

- [x] T174a [G] 🔴 /tdd 紅燈:在 `tests/integration/test_005_g_05.py` 寫 G-05 的測試(依序開啟(帶覆蓋值)、讀工作階段狀態與紀錄、套用並重啟、讓重啟失敗一次;分隔註解寫 `# ---- 005 G-05`),執行確認它因為「錯誤訊息或設定紀錄夾帶 `colab exec` 的命令列與 token;測試或程式連到使用者自己的 Ollama」這類實作而失敗
  - 🧪 `testplan.md` § G-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.get`、`paths./sessions/{name}.get`、`paths./session/tuning.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § NFR-003
- [x] T174b [G] 🟢 /tdd 綠燈:在 `src/cgb/services/tuning.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/logging_setup.py` 只寫讓 G-05 通過的程式碼;錯誤訊息、紀錄與日誌不帶 `colab exec` 的命令列、token 與轉發位址,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T174a)
  - 🧪 `testplan.md` § G-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.get`、`paths./sessions/{name}.get`、`paths./session/tuning.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § NFR-003
- [x] T175 [G] 🔵 /tdd 重構:在全部測試綠燈下整理 T174b~T174b 記下的重構清單(範圍限 `src/cgb/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_005_g_05.py` 的斷言(依賴 T174b)
  - 🧪 `testplan.md` § G-05
  - 📎 `testplan.md` § 5.2

### 測試案例覆蓋(全域)

| testplan 案例 | 任務 |
|---|---|
| G-01 | T170 |
| G-02 | T171 |
| G-03 | T172 |
| G-04 | T173 |
| G-05 | T174a、T174b、T175 |

**Checkpoint**: 全部測試綠燈;`specs/005-ollama-machine-tuning/measurements.md` 的 US1-CLI-18、US3-CLI-19、G-01~G-04 每一項都寫了數字與是否過門檻(G-01~G-04 只在使用者本人同意並在場時實跑,沒跑的寫「未實跑」並在完成報告列為未驗證),沒過的列為待決問題

---

## Dependencies & Execution Order

- Phase 1 Setup → Phase 2(US1)→ Phase 3(US2)→ Phase 4(US3)→ Phase 5 全域測試區;每個故事的 Checkpoint 交給使用者確認後才進下一個 phase
- 故事 1、3 的 E2 節依賴 E5 節最前面的共用件綠燈(T002b、T003b、T100b),其餘各節平行;跨端點驗收在三節都完成後由主 agent 做
- 跨節依賴寫在任務的「依賴」裡:E2 寫 `session_tunings` 的綠燈依賴 E4 的 T038b;`restart_ollama.py` 由故事 2 的 T063b 建最小版本,故事 3 的 E5 節擴充
- 📏 量測:節內的 US1-CLI-18、US3-CLI-19 在那一節的重構任務之後做(不開 Colab);整合實跑 G-01~G-04 要開 Colab,每一個都先停下問使用者本人,同意之後才做
