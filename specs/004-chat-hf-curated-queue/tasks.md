# Tasks: 佇列隨工作階段清空、測試對話框、Hugging Face 模型來源與可編輯的精選清單

**Input**: `specs/004-chat-hf-curated-queue/` 的設計文件(本 spec package);建立在 `specs/003-download-dedup-model-cache/` 之上(003 建立在 002、001 之上),既有程式在 `src/cgb/`、既有測試在 `tests/`

**Prerequisites**: plan.md、spec.md、research.md、techstack.md、testplan.md、contracts/remote-ollama.openapi.yaml、contracts/huggingface.openapi.yaml、contracts/ui.openapi.yaml、contracts/ui-events.asyncapi.yaml、contracts/store.dbml、prototype/

**Tests**: 依 `testplan.md` 切分。testplan 的每個行為測試案例對應一組 `/tdd` 紅燈與綠燈任務,每個「使用者故事 × 端點」節最後一個 `/tdd` 重構任務;量測與人工驗證的案例對應 📏 任務。

**Organization**: 依 `testplan.md` 的使用者故事分 phase;每個故事底下依 `testplan.md` 的端點分節(E2 後端 UI API、E4 資料庫、E7 遠端 Ollama、E12 Hugging Face Hub),外加一節跨端點驗收,最後是介面覆蓋表與測試案例覆蓋表。E1 前端 UI 照 `testplan.md` § 1 不另立端點節,畫面行為都在各故事的跨端點驗收。全域測試區自成一個 phase,放在所有故事之後。

## Format: `[ID] [Story] [步驟] Description`,底下接 🧪、⚙ 與 📎

- **[Story]**:所屬的使用者故事(US1、US2、US3、US4、US5);全域測試區寫 `[G]`
- **[步驟]**:這個任務是 `/implement` 交給誰做的哪一步
  - 🔴 `/tdd 紅燈`:寫一個測試案例的測試,執行確認它失敗
  - 🟢 `/tdd 綠燈`:只寫讓同一個案例通過的程式碼,執行全部測試確認都通過
  - 🔵 `/tdd 重構`:在全部測試綠燈下,整理這一節綠燈任務記下的重構清單,不改行為、不改斷言
  - 📏 量測:照 testplan 案例的條件量測或人工驗證,記下數字與門檻比較;是唯一不對應 `/tdd` 的開發任務
  - 不標步驟的只限三類:工具鏈設定、原樣複製 spec package 的規格檔、CI 設定
- **紅綠成對**:一個 testplan 案例對應同一個三位數的 `a`(🔴)與 `b`(🟢),`b` 依賴 `a`
- **對照組**:案例要測的程式路徑已經由既有程式或更早的綠燈任務做到時,紅燈任務標「(對照組)」:先確認通過,再暫時放入要抓的錯、確認斷言失敗後撤回;對應的綠燈任務確認不需要改程式碼。一般的紅燈任務寫完一執行就通過時,也照這個做法改當對照組,並在完成報告記一筆(`plan.md` § 待決問題 Q63)
- **誰做、怎麼排**:同一個 phase 的端點節各交給一個 subagent 平行做;跨端點驗收節在端點節都完成、驗收過後由主 agent 做。每一節裡照任務編號一次做一個任務,做完才做下一個,不跳號;任務寫了「依賴」另一節的任務時,等那個任務做完才開始(同一個檔不同時改)
- 每個任務都寫出確切的檔案路徑
- **🧪**:這個任務對應的 `testplan.md` 案例 ID;🔵 寫這一節所有案例的範圍;不標步驟的任務不寫這一行
- **⚙**:這個任務要做出來或測到的介面元素:至少照 `testplan.md` 受測操作表的「規格錨點」欄寫,再加上這個任務實際做出或斷言的介面元素;括號裡是補充說明(`info.x-*`、`Enum`、`Ref` 不是可單獨引用的錨點)。只用來鋪陳或觀察、規格錨點是「—」的操作(`/api/models` › 列出目錄、`/api/library` › 搜尋、`hf_quants` › 函式、紀錄頁 › 列表)不寫進 ⚙
- **📎**:做這個任務時要對照的依據:`spec.md` § FR / NFR / SC / 驗收情境 / 邊界情況、`research.md` § R、`plan.md` § Q 或段落名、`techstack.md` § 段落名
- **分隔註解**:每個案例的測試前寫 `# ---- 004 <案例 ID>`,全域案例放 `tests/integration/test_004_g_NN.py` 或 `tests/e2e/test_004_g_NN.py`(`plan.md` § 待決問題 Q34);延遲與逾時壓在 0.3 秒內,原樣的時間門檻交給全域量測(`plan.md` § 待決問題 Q38)
- **新的錯誤代碼**:`src/cgb/domain/errors.py` 的 `MESSAGES` 每加一個代碼,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等;任務裡寫明的是第一次用到它的綠燈)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 沿用 001~003 的工具鏈、`pyproject.toml`、`uv.lock` 與測試基礎(`tests/conftest.py`、`tests/fakes/`、`tests/e2e/conftest.py`);這一輪不新增套件(Hugging Face 也用既有的 httpx,`techstack.md` § 一覽)、不新增服務與 port、不複製規格檔、不改 CI(`plan.md` § Project Structure),這個 phase 沒有任務。新的替身與 fixture 由第一個需要它的紅燈任務建立:`FakeHuggingFaceHub` 由 T072a,`tests/fixtures/db/schema_v0.sql` 由 T017a(要在改 `src/cgb/db/schema.py` 之前凍結,`plan.md` § 待決問題 Q37),`FakeOllamaServer` 的 `client_closed` 由 T036a。

---

## Phase 2: User Story 1 - 工作階段結束後,下載佇列不留舊紀錄 (Priority: P1) 🎯 MVP

**Goal**: 工作階段變成結束中、已結束、開啟失敗或失聯時,佇列裡屬於它的每一個項目都移除並推送給 UI,模型頁不用重新整理就清空;變更執行階段類型只留下為了重新載入而排入的項目;後端重新啟動時判定已結束的照樣清除,接回同一個時不清

**Independent Test**: 照 `testplan.md` § 2 的全部案例:E2 以 `uv run pytest tests/integration/test_api_queue_clearing.py`、E4 以 `uv run pytest tests/integration/test_db_schema.py`、跨端點驗收以 `uv run pytest tests/e2e/test_004_us1_queue.py` 執行全綠

### E2 後端 UI API(FastAPI REST 與 SSE)

> E2 與 E4 兩節平行;E2 只改 `src/cgb/services/`、`src/cgb/repos/`、`src/cgb/api/`、`tests/integration/test_api_queue_clearing.py`(及綠燈任務寫明要刪的舊測試),E4 只改 `src/cgb/db/schema.py`、`tests/integration/test_db_schema.py` 與 `tests/fixtures/db/`。`src/cgb/db/schema.py` 由 E4 節負責:E2 不改它;用到新欄位或新表的 T012b(`download_jobs.session_name`)依賴 T019b,T013b(`curated_models.auto_download`、`auto_download_results`、`auto_download_items`)依賴 T017b(照 `contracts/store.dbml` 建全新庫的這三樣,`plan.md` § 待決問題 Q64)與 T024b。清除只掛在 `SessionsRepo.listeners` 一處(T001b,research.md R1),之後涵蓋其他結束方式的案例都是對照組。沿用的 fixture 與 helper 見 `testplan.md` § 2.1;`test_api_switch.py`、`test_api_recovery.py`、`test_api_health.py`、`test_api_idle.py` 的既有測試照原樣回歸

- [X] T001a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-01 的測試(送 `DELETE /api/session`,回應後立刻 `GET /api/downloads`;以 `queue_events` 收 0.5 秒;之後放行 `stop_session` 閘門,等 `state` 為 `ended` 再 `GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-01`(`plan.md` § 待決問題 Q34));同一個任務在檔內新增 `testplan.md` § 2.1 的 helper `mixed_queue`、`queue_events`,執行確認它因為「清除只掛在 `_run_end` 寫入 `ended` 之後,結束中時佇列還在」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 1、NFR-001、SC-001;`research.md` § R1
- [X] T001b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py`、`src/cgb/repos/sessions.py`、`src/cgb/services/runtime_switch.py`、`src/cgb/api/__init__.py` 只寫讓 US1-API-01 通過的程式碼;照 `contracts/ui.openapi.yaml` 的 `info.x-queue-clearing` (1),在 `SessionsRepo.listeners` 掛一個清除:工作階段變成 `ending`、`ended`、`open_failed`、`lost` 時移除佇列的每一個項目(下載中的那筆不先標成失敗),每移除一筆推 `download.removed`,全部移除後推 `downloads.snapshot`(research.md R1);拿掉 `DownloadsService.__init__` 的 `lifecycle.end_listeners.append(self.interrupt)` 與 `interrupt`;`src/cgb/services/runtime_switch.py` 的 `restart` 改成先讓舊的工作階段變成結束中、清除之後才 `enqueue_restore`(否則 001 `tests/integration/test_api_switch.py` 的變更類型測試排入的重新載入項目會被一起清掉);同一個任務刪掉 `tests/integration/test_api_downloads.py` 的 `test_結束工作階段時下載中的那筆失敗_排隊中的保留`、`test_新的工作階段就緒後佇列自動繼續_開始前重新檢查空間`,以及 `tests/integration/test_api_switch.py` 的 `test_新類型開不起來時舊的已結束_要重新下載的項目留在佇列`(分別由 US1-API-01、US1-API-02、US1-API-07 取代,`testplan.md` § 2.1),執行全部測試確認都通過、不留 skip;看到要整理的地方記進重構清單(依賴 T001a)
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 1、NFR-001、SC-001;`research.md` § R1
- [X] T002a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-02 的測試(送 `DELETE /api/session`,等 `state` 為 `ended`;放行 pull 的閘門(`qwen2.5:7b` 的 pull 這時才會送完 `success`)並等 0.2 秒,`GET /api/downloads`;`set_tags(fakes)` 讓新的執行環境上沒有任何模型,`open_ready` 再開一個,就緒後等 0.3 秒,`GET /api/downloads`、`GET /api/models`;分隔註解寫 `# ---- 004 US1-API-02`(`plan.md` § 待決問題 Q34)),執行確認它因為「worker 沒有被取消,閘門放行後那一筆被寫成 `completed`、重新出現在佇列」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 2、使用者故事 1 獨立測試
- [X] T002b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py` 只寫讓 US1-API-02 通過的程式碼;結束時取消下載中那一筆的 worker(閘門放行後不寫成 `completed`);`DownloadsService.resume` 只開始屬於新工作階段的排隊中項目、佇列是空的就不讀剩餘空間(`info.x-queue-clearing` (4)),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T002a)
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 2、使用者故事 1 獨立測試
- [X] T003a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-03 的測試(`fake_clock.set(deadline + 1 秒)`,等 `is_idle_ended` 成立(最多 1 秒),立刻 `GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-03`(`plan.md` § 待決問題 Q34));T001b 掛在 `SessionsRepo.listeners` 的清除(`src/cgb/services/downloads.py`;閒置自動結束也經 `repo.update` 寫入 `ending`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「清除寫在 `DELETE /api/session` 的路由裡,`IdleMonitor` 直接呼叫 `lifecycle.end("IDLE_TIMEOUT")` 時沒清」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 3、SC-001
- [X] T003b [US1] 🟢 /tdd 綠燈:US1-API-03 由 T001b 掛在 `SessionsRepo.listeners` 的清除(`src/cgb/services/downloads.py`;閒置自動結束也經 `repo.update` 寫入 `ending`) 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US1-API-03 通過的程式碼(依賴 T003a)
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 3、SC-001
- [X] T004a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-04 的測試(`world.alive.remove(name)`、`fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")`;等 `state` 為 `lost`(最多 1 秒),立刻 `GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-04`(`plan.md` § 待決問題 Q34));T001b 掛在 `SessionsRepo.listeners` 的清除(`HealthMonitor._mark_reclaimed` 的 `repo.update` 寫入 `lost` 時也會觸發)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「清除照現況掛在 `end_listeners`,`HealthMonitor._mark_reclaimed` 只呼叫 `repo.update(reclaimed_fields)`,佇列原封不動(research.md R1 查到的 4 條漏網路徑之一)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 3、SC-001;`research.md` § R1
- [X] T004b [US1] 🟢 /tdd 綠燈:US1-API-04 由 T001b 掛在 `SessionsRepo.listeners` 的清除(`HealthMonitor._mark_reclaimed` 的 `repo.update` 寫入 `lost` 時也會觸發) 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US1-API-04 通過的程式碼(依賴 T004a)
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 3、SC-001;`research.md` § R1
- [X] T005a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-05 的測試(`fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))`;等 `state` 為 `reconnecting` 時 `GET /api/downloads`;再等 `state` 為 `lost`(最多 1 秒),立刻 `GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-05`(`plan.md` § 待決問題 Q34));T001b 掛在 `SessionsRepo.listeners` 的清除(只對 `ending`、`ended`、`open_failed`、`lost` 清,`reconnecting` 不清)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「listener 只看「不是 `ready`」就清,重連中(還可能接回同一台)就把佇列清掉」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 3、SC-001
- [X] T005b [US1] 🟢 /tdd 綠燈:US1-API-05 由 T001b 掛在 `SessionsRepo.listeners` 的清除(只對 `ending`、`ended`、`open_failed`、`lost` 清,`reconnecting` 不清) 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US1-API-05 通過的程式碼(依賴 T005a)
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 3、SC-001
- [X] T006a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-06 的測試(新的開啟中時 `GET /api/downloads`;送 `DELETE /api/session`,回應後立刻 `GET /api/downloads`;放行閘門,等 `state` 為 `ended` 再等 0.2 秒,`GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-06`(`plan.md` § 待決問題 Q34));T001b 掛在 `SessionsRepo.listeners` 的清除(看的是狀態,不看有沒有就緒過)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「清除只在工作階段曾經就緒過時才做(例如掛在 `ready_listeners` 的反面、或檢查 `ready_at`),開啟中結束時重新載入的項目留著」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、邊界情況、SC-001
- [X] T006b [US1] 🟢 /tdd 綠燈:US1-API-06 由 T001b 掛在 `SessionsRepo.listeners` 的清除(看的是狀態,不看有沒有就緒過) 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US1-API-06 通過的程式碼(依賴 T006a)
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、邊界情況、SC-001
- [X] T007a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-07 的測試(送 `POST /api/session/restart`(`L4`),等新的 `state` 為 `open_failed`,立刻 `GET /api/downloads`;再以 T4 `open_ready` 開一個,就緒後等 0.3 秒,`GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-07`(`plan.md` § 待決問題 Q34));T001b 掛在 `SessionsRepo.listeners` 的清除(`open_failed` 也清)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「照 001 把重新載入的項目留在佇列,等下一個工作階段就緒再下載(現況)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、FR-002、使用者故事 1 驗收情境 3、邊界情況、SC-001
- [X] T007b [US1] 🟢 /tdd 綠燈:US1-API-07 由 T001b 掛在 `SessionsRepo.listeners` 的清除(`open_failed` 也清) 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US1-API-07 通過的程式碼(依賴 T007a)
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-001、FR-002、使用者故事 1 驗收情境 3、邊界情況、SC-001
- [X] T008a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-08 的測試(送 `POST /api/session/restart`(`L4`),回應後立刻 `GET /api/downloads`;以 `queue_events` 收 0.3 秒;放行閘門,等新的工作階段就緒且 `preload` 被呼叫,`GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-08`(`plan.md` § 待決問題 Q34));T001b 的清除與 `src/cgb/services/runtime_switch.py` 改成先清除再 `enqueue_restore` 的順序已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「照現況先 `enqueue_restore` 再把舊的改 `ending`,清除把剛排入的重新載入項目一起刪掉(新的就緒後沒有下載與載入)」這類實作,執行確認斷言失敗後撤回;則7、則8 斷言清除時先送一則空的 `downloads.snapshot`、之後才推重新載入那一筆的 `download.updated`(`plan.md` § 待決問題 Q47),T001b 的「全部移除後推一次快照」若沒做到這個順序,就當成一般的紅燈;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-002、FR-001、使用者故事 1 驗收情境 4、SC-001
- [X] T008b [US1] 🟢 /tdd 綠燈:US1-API-08 由 T001b 的清除與 `src/cgb/services/runtime_switch.py` 改成先清除再 `enqueue_restore` 的順序 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/services/runtime_switch.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/services/runtime_switch.py` 只寫讓 US1-API-08 通過的程式碼(依賴 T008a)
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-002、FR-001、使用者故事 1 驗收情境 4、SC-001
- [X] T009a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-09 的測試(再送一次 `POST /api/session/restart`(`runtimeType` 為 T4),回應後立刻 `GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-09`(`plan.md` § 待決問題 Q34));T001b 的清除(舊的變成 `ending` 時佇列整個清空,再排入這一次的重新載入項目)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「清除用「`origin` 為 `restore` 的保留」而不是看所屬的工作階段,上一次變更類型留下、已完成的 restore 項目被帶過來(research.md R1 的判斷)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-002、FR-001;`research.md` § R1
- [X] T009b [US1] 🟢 /tdd 綠燈:US1-API-09 由 T001b 的清除(舊的變成 `ending` 時佇列整個清空,再排入這一次的重新載入項目) 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/services/runtime_switch.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/services/runtime_switch.py` 只寫讓 US1-API-09 通過的程式碼(依賴 T009a)
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-002、FR-001;`research.md` § R1
- [X] T010a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-10 的測試(以同一個 SQLite 檔 `running(make_app())` 跑第二個 app,等 `state` 為 `lost`(最多 1 秒),立刻 `GET /api/downloads`;再 `open_ready` 開一個,就緒後等 0.3 秒,`GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-10`(`plan.md` § 待決問題 Q34)),執行確認它因為「`Recovery._reattach` 照現況只寫 `reclaimed_fields`、沒清佇列,`requeue_interrupted` 改回排隊中的那幾筆在下一個工作階段就緒時被下載」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-003、FR-001、使用者故事 1 驗收情境 5
- [X] T010b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/services/downloads.py`、`src/cgb/api/__init__.py` 只寫讓 US1-API-10 通過的程式碼;`Recovery` 判定先前的工作階段已在停機期間結束時照 (1) 清除(`info.x-queue-clearing` (3));`src/cgb/api/__init__.py` 啟動時呼叫 `downloads_service.requeue_interrupted()` 的位置改成在判定之後,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T010a)
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-003、FR-001、使用者故事 1 驗收情境 5
- [X] T011a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-11 的測試(跑第二個 app;接回停在閘門前時 `GET /api/downloads`;放行,等 `state` 為 `ready`,再等佇列四筆都不是 `queued`、`downloading`(最多 1 秒),`GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-11`(`plan.md` § 待決問題 Q34));既有的 `Recovery._reattach`(`src/cgb/services/recovery.py`)與 `DownloadsService.requeue_interrupted`,加上 T010b 只在判定已結束時才清除已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`Recovery._run` 啟動時不看名稱一律清空」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-003、邊界情況
- [X] T011b [US1] 🟢 /tdd 綠燈:US1-API-11 由 既有的 `Recovery._reattach`(`src/cgb/services/recovery.py`)與 `DownloadsService.requeue_interrupted`,加上 T010b 只在判定已結束時才清除 滿足,確認 `src/cgb/services/recovery.py`、`src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/recovery.py`、`src/cgb/services/downloads.py` 只寫讓 US1-API-11 通過的程式碼(依賴 T011a)
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-003、邊界情況
- [X] T012a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-12 的測試(各跑第二個 app;A 等 `state` 為 `ready` 且 `qwen2.5:1.5b` 完成,`GET /api/downloads`;B 啟動後等 0.3 秒,`GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-12`(`plan.md` § 待決問題 Q34)),執行確認它因為「以 SQL `DELETE ... WHERE session_name != ?` 刪,NULL 比較結果是 NULL、升級前的項目沒被刪,`qwen2.5:7b` 在接回後被下載」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-003
- [X] T012b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py`、`src/cgb/services/runtime_switch.py` 只寫讓 US1-API-12 通過的程式碼;`src/cgb/repos/downloads.py` 寫入與讀取 `session_name`,加入下載、`enqueue_restore` 寫入所屬工作階段的名稱(`src/cgb/services/runtime_switch.py` 用新工作階段的名稱);後端啟動時刪掉 `session_name` 為 NULL 的項目(用 `IS NULL`,不用 `!=`)。`download_jobs.session_name` 由 E4 節的 `src/cgb/db/schema.py` 建立,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T012a、T019b)
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-003
- [X] T013a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-13 的測試(結束後(A 等 `DELETE` 回應,B 等 `state` 為 `lost`)立刻 `GET /api/downloads/auto-result`;以 `queue_events` 收 0.5 秒;分隔註解寫 `# ---- 004 US1-API-13`(`plan.md` § 待決問題 Q34)),執行確認它因為「自動下載結果照「保留到這個工作階段結束」做成看 `lifecycle.current()["state"]` 決定要不要回,`auto_download_results` 那一列沒刪,重新整理後在下一個工作階段就緒前仍讀得到舊結果」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendAutoDownloadUpdated`
  - 📎 `spec.md` § FR-001、SC-001;`plan.md` § 待決問題 Q64
- [X] T013b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py`、`src/cgb/repos/curated.py`、`src/cgb/api/curated.py`、`src/cgb/api/downloads.py`、`src/cgb/api/events.py`、`src/cgb/services/event_bus.py`、`src/cgb/api/__init__.py` 只寫讓 US1-API-13 通過的程式碼;只做到讓這個案例通過的最小版本(`plan.md` § 待決問題 Q64):精選清單的 `autoDownload` 存讀、工作階段第一次就緒時把設了自動下載的項目排入(`origin` `auto`)並寫 `auto_download_results`、`GET /api/downloads/auto-result`、結束時照 `info.x-queue-clearing` (5) 刪結果並推 `autoDownload.updated`(`result` 為 null);用到的 `curated_models.auto_download`、`auto_download_results`、`auto_download_items` 由 E4 節的 T017b 照 `contracts/store.dbml` 建在 `src/cgb/db/schema.py`(全新庫),這個任務不改那個檔,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T013a、T017b、T024b)
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendAutoDownloadUpdated`
  - 📎 `spec.md` § FR-001、SC-001;`plan.md` § 待決問題 Q64
- [X] T014a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-14 的測試(觸發那一種結束(`DELETE`;`fake_clock.set` 過 deadline;`world.alive.remove` 加健康檢查失敗;`check_health.then` 失敗加 `open_tunnel` 一直失敗;送 `restart` 讓新的開不起來),以 `queue_events` 收 1 秒,之後 `GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-14`(`plan.md` § 待決問題 Q34));T001b 的清除(五種結束方式都經 `SessionsRepo.update`,每筆推 `download.removed`、最後推 `downloads.snapshot`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「只有使用者結束與閒置結束(都走 `end()`)推了事件,收回、重連逾時與開啟失敗只刪了表、UI 要重新整理才清空」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`
  - 📎 `spec.md` § NFR-001、SC-001、FR-001、使用者故事 1 驗收情境 1、使用者故事 1 驗收情境 3
- [X] T014b [US1] 🟢 /tdd 綠燈:US1-API-14 由 T001b 的清除(五種結束方式都經 `SessionsRepo.update`,每筆推 `download.removed`、最後推 `downloads.snapshot`) 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US1-API-14 通過的程式碼(依賴 T014a)
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`
  - 📎 `spec.md` § NFR-001、SC-001、FR-001、使用者故事 1 驗收情境 1、使用者故事 1 驗收情境 3
- [X] T015a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_queue_clearing.py` 寫 US1-API-15 的測試(送 `DELETE /api/session`;結束中時依序送 `GET /api/downloads`、`POST /api/downloads/{失敗那筆的 id}/retry`、`POST /api/downloads`(`models` 為 `["qwen2.5:7b"]`)、`GET /api/downloads/auto-result`;之後讓 `stop_session` 丟 `AdapterError("COLAB_UNREACHABLE")` 再放行閘門,等 `state` 為 `ended`,再 `GET /api/downloads`;分隔註解寫 `# ---- 004 US1-API-15`(`plan.md` § 待決問題 Q34)),執行確認它因為「清除後 `retry` 對不存在的 id 以 `self._repo.get(job_id)` 取到 None 再取欄位丟 `TypeError`、回 500」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`、`paths./downloads/{id}/retry.post`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`、`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § NFR-006、FR-001
- [X] T015b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US1-API-15 通過的程式碼;清除後 `retry` 對不存在的 id 回 404;新代碼 `DOWNLOAD_NOT_FOUND` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T015a)
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`、`paths./downloads/{id}/retry.post`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`、`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § NFR-006、FR-001
- [X] T016 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T001b~T015b 記下的重構清單(範圍限 `src/cgb/services/`、`src/cgb/repos/`、`src/cgb/api/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T015b)
  - 🧪 `testplan.md` § US1-API-01~US1-API-15
  - 📎 `testplan.md` § 2.1

### E4 資料庫(SQLite)

> 連線一律用 `cgb.db.connection.connect`(`isolation_level=None`,遷移的交易要明寫 `BEGIN`);001 的 `US1-DB-01`、`US1-DB-02` 保留不動。失敗注入、舊庫三筆與「13 個舊欄位」照 `testplan.md` § 2.2;遷移失敗時原例外往上丟(`plan.md` § 待決問題 Q39),只差大小寫的 `pending_model` 在同一個交易裡留 id 最小的那筆並寫日誌(`plan.md` § 待決問題 Q40)

- [X] T017a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-01 的測試(以 `connect` 開檔並呼叫 `create_schema(conn)`;分隔註解寫 `# ---- 004 US1-DB-01`(`plan.md` § 待決問題 Q34));**在改 `src/cgb/db/schema.py` 之前**,照 `testplan.md` § 2.2 以現行 `create_schema` 建空庫、匯出 `tests/fixtures/db/schema_v0.sql`(10 句,每句以 `;` 結尾,另加 `INSERT INTO settings (id) VALUES (1);`),在 `tests/integration/test_db_schema.py` 加 helper `_build_v0`,`_insert_job` 加 `session_name`、`origin`、`preload_on_complete`、`reason_code`、`message`、`started_at`、`finished_at` 這幾個 keyword 參數(預設值不變;`plan.md` § 待決問題 Q37),執行確認它因為「全新庫照 001 的 DDL 建,只把 `user_version` 設成 1,沒有 `session_name`」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-01
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q27
- [X] T017b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US1-DB-01 通過的程式碼,並照 `contracts/store.dbml` 寫出全新庫的整份 DDL:除了 US1-DB-01 斷言的 `download_jobs` 新欄位,也一併建 `curated_models.auto_download`(`INTEGER NOT NULL DEFAULT 0` 與 CHECK)、`uq_curated_models_name_ci`、`auto_download_results`(含 `CHECK (target_count >= 0)`)、`auto_download_items`(含 `size_bytes`、`free_disk_bytes`、`vram_bytes`)與它們的索引;這幾樣 US1-DB-01 不斷言,是 E2 節 T013b 要用的(`plan.md` § 待決問題 Q64、Q68),故事 3 的 E4 節對全新庫的案例(T110a、T118a、T119a、T248a)是對照組;既有庫的遷移(`curated_models` 加欄、去重與建新表)留給故事 3 的 E4 節,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T017a)
  - 🧪 `testplan.md` § US1-DB-01
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q27
- [X] T018a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US1-DB-02 的測試(依序插入:(1)`origin='auto'`、`session_name='cgb-a'`、`pending_model='llama3.2:3b'`、`queue_position=2`;(2)`origin='manual'`、`queue_position=3`;(3)`pending_model='Qwen2.5:7B'`、`queue_position=4`;(4)兩筆 `model='qwen2.5:7b'`、`pending_model` NULL、`state='completed'`、`queue_position` 5、6;分隔註解寫 `# ---- 004 US1-DB-02`(`plan.md` § 待決問題 Q34));T017b 照 `contracts/store.dbml` 寫出的全新庫 DDL(`origin` 的 CHECK 含 `auto`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`origin` 的 CHECK 沒加 `auto`,自動下載排入一寫就失敗」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-DB-02
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-001
- [X] T018b [US1] 🟢 /tdd 綠燈:US1-DB-02 由 T017b 照 `contracts/store.dbml` 寫出的全新庫 DDL(`origin` 的 CHECK 含 `auto`) 滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US1-DB-02 通過的程式碼(依賴 T018a)
  - 🧪 `testplan.md` § US1-DB-02
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-001
- [X] T019a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-03 的測試(以 `connect` 開同一個檔,呼叫 `create_schema(conn)`;分隔註解寫 `# ---- 004 US1-DB-03`(`plan.md` § 待決問題 Q34)),執行確認它因為「判斷新舊之前就先跑了新版的 `CREATE TABLE IF NOT EXISTS`,或只看 `user_version` 是 0,把舊庫當成全新庫,只設 `user_version=1` 沒有重建,`session_name` 不存在」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-03
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-001、FR-003;`plan.md` § 待決問題 Q28
- [X] T019b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US1-DB-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T019a)
  - 🧪 `testplan.md` § US1-DB-03
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-001、FR-003;`plan.md` § 待決問題 Q28
- [X] T020a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US1-DB-04 的測試(依序插入:(1)`origin='auto'`、`session_name='cgb-new'`、`model='phi4:14b'`、`pending_model='phi4:14b'`、`queue_position=4`;(2)`pending_model='Qwen2.5:7B'`、`queue_position=5`(和 A 只差大小寫);(3)`origin='manual'`、`queue_position=6`;(4)`pending_model='mistral:7b'`、`queue_position=1`(和 A 相同);(5)`size_bytes=-1`、`queue_position=7`;分隔註解寫 `# ---- 004 US1-DB-04`(`plan.md` § 待決問題 Q34));T019b 重建 `download_jobs` 時用的新版 DDL(和全新庫同一份)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「重建時 `download_jobs_new` 照抄 001 的 `origin IN ('user','restore')`,升級過的使用者自動下載一寫就失敗」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-DB-04
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`、`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-001
- [X] T020b [US1] 🟢 /tdd 綠燈:US1-DB-04 由 T019b 重建 `download_jobs` 時用的新版 DDL(和全新庫同一份) 滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US1-DB-04 通過的程式碼(依賴 T020a)
  - 🧪 `testplan.md` § US1-DB-04
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`、`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-001
- [X] T021a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-05 的測試(呼叫 `create_schema(conn)`;接著 `conn.set_authorizer(None)`,再呼叫一次 `create_schema(conn)`;分隔註解寫 `# ---- 004 US1-DB-05`(`plan.md` § 待決問題 Q34)),執行確認它因為「遷移沒有包在交易裡,或用 `with conn:` 包起來,但 `connect` 是 `isolation_level=None`,`with` 不會開交易,失敗時前面的 `ALTER`、重建已經各自 commit,留下一半新、一半舊的庫」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-05
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-001、FR-003;`plan.md` § 待決問題 Q39
- [X] T021b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US1-DB-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T021a)
  - 🧪 `testplan.md` § US1-DB-05
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-001、FR-003;`plan.md` § 待決問題 Q39
- [X] T022a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US1-DB-06 的測試(再呼叫一次 `create_schema(conn)`(模擬後端重新啟動);分隔註解寫 `# ---- 004 US1-DB-06`(`plan.md` § 待決問題 Q34));T019b 先看 `user_version` 再看 `sessions` 表存不存在的分辨(`plan.md` § 待決問題 Q28)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「只看「`sessions` 表存在」就判定是舊庫,沒有先看 `user_version`,每次啟動都重跑一次重建,以 001 的欄位清單複製,D 的 `session_name` 變回 NULL,下一次啟動被 Recovery 當成升級前的項目刪掉」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-DB-06
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-001、FR-003
- [X] T022b [US1] 🟢 /tdd 綠燈:US1-DB-06 由 T019b 先看 `user_version` 再看 `sessions` 表存不存在的分辨(`plan.md` § 待決問題 Q28) 滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US1-DB-06 通過的程式碼(依賴 T022a)
  - 🧪 `testplan.md` § US1-DB-06
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-001、FR-003
- [X] T023a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US1-DB-07 的測試(以 `connect` 開檔,呼叫 `create_schema(conn)`;分隔註解寫 `# ---- 004 US1-DB-07`(`plan.md` § 待決問題 Q34));T019b 以 `sessions` 表存不存在分辨新舊庫(`plan.md` § 待決問題 Q28)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「判斷新舊時看的是 `sessions` 有沒有資料列(`SELECT count(*)`),或看 `download_jobs` 有沒有資料,而不是 `sessions` 表存不存在(Q28),空的舊庫被當成全新庫,只設 `user_version=1`,`download_jobs` 仍是 001 的表」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-DB-07
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q28
- [X] T023b [US1] 🟢 /tdd 綠燈:US1-DB-07 由 T019b 以 `sessions` 表存不存在分辨新舊庫(`plan.md` § 待決問題 Q28) 滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US1-DB-07 通過的程式碼(依賴 T023a)
  - 🧪 `testplan.md` § US1-DB-07
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q28
- [X] T024a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-08 的測試(以 `connect` 開檔,在 `caplog` 底下呼叫 `create_schema(conn)`;分隔註解寫 `# ---- 004 US1-DB-08`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒有先去重就建 `lower()` 唯一索引,遷移丟 `IntegrityError`,只差大小寫的舊庫永遠升不上去」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-08
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-001、FR-003;`plan.md` § 待決問題 Q40
- [X] T024b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US1-DB-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T024a)
  - 🧪 `testplan.md` § US1-DB-08
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-001、FR-003;`plan.md` § 待決問題 Q40
- [X] T025 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T017b~T024b 記下的重構清單(範圍限 `src/cgb/db/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_db_schema.py` 的斷言(依賴 T024b)
  - 🧪 `testplan.md` § US1-DB-01~US1-DB-08
  - 📎 `testplan.md` § 2.2

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(Playwright)接測試行程內真的後端(`tests/e2e/conftest.py` 的 `e2e_servers`,UI 127.0.0.1:8781),轉接層用替身;e2e 用固定 port,同一時間只跑一份
> 佇列裡的項目以加入下載與 `fakes.remote_ollama.pull_model` 的閘門鋪出(`testplan.md` § 2.3)

- [X] T026a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/e2e/test_004_us1_queue.py` 寫 US1-AJ-01 的測試(在首頁的另一個分頁按「結束」並確認;模型頁不重新整理;分隔註解寫 `# ---- 004 US1-AJ-01`(`plan.md` § 待決問題 Q34));既有 `src/cgb/static/js/models.js` 的 `download.removed`、`downloads.snapshot` 處理,加上 T001b 的推送已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「後端清了佇列但沒有推 `download.removed`,畫面要重新整理才清空」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`;`prototype/index.html` § `[data-state="confirm-stop"]`、`[data-state="stopping"]`、`[data-state="ended"]`
  - 📎 `spec.md` § NFR-001、SC-001、FR-001
- [X] T026b [US1] 🟢 /tdd 綠燈:US1-AJ-01 由 既有 `src/cgb/static/js/models.js` 的 `download.removed`、`downloads.snapshot` 處理,加上 T001b 的推送 滿足,確認 `src/cgb/static/js/models.js` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/models.js` 只寫讓 US1-AJ-01 通過的程式碼(依賴 T026a)
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`;`prototype/index.html` § `[data-state="confirm-stop"]`、`[data-state="stopping"]`、`[data-state="ended"]`
  - 📎 `spec.md` § NFR-001、SC-001、FR-001
- [X] T027a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/e2e/test_004_us1_queue.py` 寫 US1-AJ-02 的測試(讓 `fakes.tunnel.check_health` 一直失敗、重連逾時(縮短的時限),工作階段變成 `lost`;不重新整理;分隔註解寫 `# ---- 004 US1-AJ-02`(`plan.md` § 待決問題 Q34));既有 `src/cgb/static/js/models.js` 的 `download.removed` 處理,加上 T001b 在 `lost` 時的清除已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「只有使用者結束(`end_listeners`)才清佇列,失聯時下載中的那筆照 001 標成失敗留在畫面」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`;`prototype/index.html` § `[data-state="lost"]`
  - 📎 `spec.md` § FR-001
- [X] T027b [US1] 🟢 /tdd 綠燈:US1-AJ-02 由 既有 `src/cgb/static/js/models.js` 的 `download.removed` 處理,加上 T001b 在 `lost` 時的清除 滿足,確認 `src/cgb/static/js/models.js` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/models.js` 只寫讓 US1-AJ-02 通過的程式碼(依賴 T027a)
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`;`prototype/index.html` § `[data-state="lost"]`
  - 📎 `spec.md` § FR-001
- [X] T028a [US1] 🔴 /tdd 紅燈(對照組):在 `tests/e2e/test_004_us1_queue.py` 寫 US1-AJ-03 的測試(在首頁按「變更類型」選 L4 並確認,等到新的工作階段就緒;回到模型頁(不重新整理就在同一個分頁切換);分隔註解寫 `# ---- 004 US1-AJ-03`(`plan.md` § 待決問題 Q34));T001b 的清除順序(先清除舊的、再排入重新載入項目)與既有 `src/cgb/static/js/models.js` 的事件處理已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「變更類型時先 `enqueue_restore` 再把舊的改 `ending`,清除把剛排入的重新載入項目一起刪掉」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`;`prototype/index.html` § `[data-state="confirm-switch"]`、`[data-state="switching"]`、`[data-state="starting"]`、`[data-state="ready"]`
  - 📎 `spec.md` § FR-002
- [X] T028b [US1] 🟢 /tdd 綠燈:US1-AJ-03 由 T001b 的清除順序(先清除舊的、再排入重新載入項目)與既有 `src/cgb/static/js/models.js` 的事件處理 滿足,確認 `src/cgb/static/js/models.js` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/models.js` 只寫讓 US1-AJ-03 通過的程式碼(依賴 T028a)
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`;`prototype/index.html` § `[data-state="confirm-switch"]`、`[data-state="switching"]`、`[data-state="starting"]`、`[data-state="ready"]`
  - 📎 `spec.md` § FR-002
- [X] T029a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us1_queue.py` 寫 US1-AJ-04 的測試(結束工作階段並等到 `ended`;看沒有工作階段時的模型頁;分隔註解寫 `# ---- 004 US1-AJ-04`(`plan.md` § 待決問題 Q34)),執行確認它因為「前端照 001 留著「保留著、重新開啟後會繼續下載」的說明(`plan.md` Q29),和清空的佇列互相矛盾」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-04
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`;`prototype/index.html` § `[data-state="ended"]`、`[data-state="lost"]`、`[data-state="ended-offline"]`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q29、Q66
- [X] T029b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/models.html`、`src/cgb/static/js/models.js`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-04 通過的程式碼;沒有工作階段時的「保留著、重新開啟後會繼續下載」說明改成 `prototype/models.html` 的 `[data-state="queue-cleared"]`(`plan.md` § 待決問題 Q29);首頁結束類狀態的說明照 `prototype/index.html`(沒有清除筆數,`plan.md` § 待決問題 Q29;重連逾時與開啟失敗的畫面由 T238b、T239b 做)(`[data-state="ended"]`、`[data-state="lost"]`、`[data-state="ended-offline"]` 只改說明文字、不新增斷言,改完在瀏覽器看一眼,`plan.md` § 待決問題 Q66),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T029a)
  - 🧪 `testplan.md` § US1-AJ-04
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`;`prototype/index.html` § `[data-state="ended"]`、`[data-state="lost"]`、`[data-state="ended-offline"]`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q29、Q66
- [X] T238a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us1_queue.py` 寫 US1-AJ-05 的測試(讓 `fakes.tunnel.check_health` 一直失敗、重連逾時(縮短的時限),工作階段變成 `lost`、`endReason` 為 `RECONNECT_TIMEOUT`;不重新整理;分隔註解寫 `# ---- 004 US1-AJ-05`(`plan.md` § 待決問題 Q34)),執行確認它因為「前端只有一個失聯畫面,重連逾時也顯示被 Colab 收回的說明」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-05
  - ⚙ `prototype/index.html` § `[data-state="lost"]`、`[data-state="lost-timeout"]`、`[data-state="failed"]`;`prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 3
- [X] T238b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-05 通過的程式碼;照 `prototype/index.html` 加 `[data-state="lost-timeout"]`,`endReason` 為 `RECONNECT_TIMEOUT` 時顯示它,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T238a)
  - 🧪 `testplan.md` § US1-AJ-05
  - ⚙ `prototype/index.html` § `[data-state="lost"]`、`[data-state="lost-timeout"]`、`[data-state="failed"]`;`prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-001、使用者故事 1 驗收情境 3
- [X] T239a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us1_queue.py` 寫 US1-AJ-06 的測試(在首頁按「變更類型」選 L4 並確認,等新的工作階段變成開啟失敗(就緒之後才設 `fakes.tunnel.open_tunnel.raises("TUNNEL_UNREACHABLE", "連不到")`);不重新整理;分隔註解寫 `# ---- 004 US1-AJ-06`(`plan.md` § 待決問題 Q34)),執行確認它因為「首頁的開啟失敗畫面照 001 沒有提佇列,或沒顯示「一起清空了」」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-06
  - ⚙ `prototype/index.html` § `[data-state="lost"]`、`[data-state="lost-timeout"]`、`[data-state="failed"]`;`prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-001、FR-002、使用者故事 1 驗收情境 3
- [X] T239b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-06 通過的程式碼;照 `prototype/index.html` 的 `[data-state="failed"]` 寫開啟失敗的說明(變更類型排入的重新載入項目也一起清空),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T239a)
  - 🧪 `testplan.md` § US1-AJ-06
  - ⚙ `prototype/index.html` § `[data-state="lost"]`、`[data-state="lost-timeout"]`、`[data-state="failed"]`;`prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-001、FR-002、使用者故事 1 驗收情境 3
- [X] T240a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us1_queue.py` 寫 US1-AJ-07 的測試(情況 A 從沒開過工作階段時打開模型頁;情況 B 結束工作階段、等到 `ended` 之後才打開模型頁;分隔註解寫 `# ---- 004 US1-AJ-07`(`plan.md` § 待決問題 Q34)),執行確認它因為「前端靠只存在頁面記憶體裡的「剛清除幾筆」判斷,之後才打開或重新整理就顯示成 `queue-empty`」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-07
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q29
- [X] T240b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/js/models.js` 只寫讓 US1-AJ-07 通過的程式碼;佇列是空的時依工作階段狀態(`ended`、`lost`、`open_failed`)決定顯示 `queue-cleared` 或 `queue-empty`,`#qc-text` 寫工作階段名稱、不寫筆數(`plan.md` § 待決問題 Q29),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T240a)
  - 🧪 `testplan.md` § US1-AJ-07
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q29
- [X] T030 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T026b~T029b、T238b~T240b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T240b)
  - 🧪 `testplan.md` § US1-AJ-01~US1-AJ-04、US1-AJ-05~US1-AJ-07
  - 📎 `testplan.md` § 2.3

### 介面覆蓋(US1)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved` | T001b、T008b、T014b | T001a、T008a、T014a |
| `ui-events.asyncapi.yaml` § `operations.sendAutoDownloadUpdated` | T013b | T013a |
| `ui.openapi.yaml` § `paths./downloads.get` | T001b~T012b、T014b~T015b | T001a~T012a、T014a~T015a |
| `ui.openapi.yaml` § `paths./downloads.post`、`paths./downloads/{id}/retry.post` | T015b | T015a |
| `ui.openapi.yaml` § `paths./downloads/auto-result.get` | T013b、T015b | T013a、T015a |
| `store.dbml` § `Table sessions`、`Table auto_download_results`、`Table auto_download_items`(T017b 照 store.dbml 建全新庫的整份 DDL,`plan.md` § 待決問題 Q64) | T017b~T018b | T017a~T018a |
| `store.dbml` § `Table download_jobs`、`Table curated_models` | T017b~T024b | T017a~T024a |
| `index.html` § `[data-state="starting"]`、`[data-state="ready"]`、`[data-state="confirm-switch"]`、`[data-state="switching"]` | T028b | T028a |
| `index.html` § `[data-state="confirm-stop"]`、`[data-state="stopping"]` | T026b | T026a |
| `index.html` § `[data-state="ended"]` | T026b、T029b | T026a、T029a |
| `index.html` § `[data-state="lost"]` | T027b、T029b、T238b | T027a、T029a、T238a |
| `index.html` § `[data-state="lost-timeout"]` | T238b | T238a |
| `index.html` § `[data-state="failed"]` | T239b | T239a |
| `index.html` § `[data-state="ended-offline"]`(這一輪照原型改說明文字,沒有新的斷言;完成報告列為未直接驗證,`plan.md` § 待決問題 Q66) | T029b | T029a |
| `models.html` § `[data-state="cat-no-session"]`、`[data-state="auto-running"]`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]` | T026b~T029b、T238b~T240b | T026a~T029a、T238a~T240a |

### 測試案例覆蓋(US1)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US1-API-01~US1-API-15 | T001a~T015a | T001b~T015b | T016 |
| US1-DB-01~US1-DB-08 | T017a~T024a | T017b~T024b | T025 |
| US1-AJ-01~US1-AJ-04 | T026a~T029a | T026b~T029b | T030 |
| US1-AJ-05~US1-AJ-07 | T238a~T240a | T238b~T240b | T030 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 全綠(含 T001b 刪掉的三支舊測試已不在、`tests/e2e/test_locale.py` 加了 `DOWNLOAD_NOT_FOUND`);重構任務前後的測試結果相同

---

## Phase 3: User Story 2 - 在 UI 裡跟模型對話,試它的基本能力 (Priority: P2)

**Goal**: 使用者在對話頁選執行環境上的模型、送出多輪訊息,回覆逐段出現,完成後顯示耗時與每秒 token 數,可以停止與清空;沒有工作階段或沒有模型時不能送出,回覆途中中斷時保留已收到的部分並標示原因;對話送出會重設閒置倒數,內容不寫進資料庫與日誌

**Independent Test**: 照 `testplan.md` § 3 的全部案例:E2 以 `uv run pytest tests/integration/test_api_chat.py`(`live_servers` 接 `FakeOllamaServer`)、跨端點驗收以 `uv run pytest tests/e2e/test_004_us2_chat.py` 執行全綠

### E2 後端 UI API(FastAPI REST 與 SSE)

> 這一節只有 E2;對話轉送沒有轉接層方法,`src/cgb/api/chat.py` 以 httpx 打 forward target、用 `src/cgb/ollama_compat/forward.py` 的 `_relay` 轉送,失敗歸類照 `contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post` 的 `info.x-failure-rules` 第 1~8 條(`plan.md` § 待決問題 Q35)。串流的案例一律用 `live_servers`,對話送到 `fakes.server`(`FakeOllamaServer`,真的 HTTP);`chat_read` 以 `replace(test_timeouts, chat_read=0.2)` 注入(`plan.md` § 待決問題 Q44)。`_relay` 是 Ollama 相容端點共用的程式,改了它之後 `tests/integration/test_ollama_compat.py` 照原樣回歸。案例裡的 `MODEL`、`chunk`、`DONE` 與「送出」的寫法照 `testplan.md` § 3.1

- [X] T031a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-01 的測試(送出預設本文;讀到第 1 行後才放行 `g1`,讀到第 2 行後才放行 `g2`;分隔註解寫 `# ---- 004 US2-API-01`(`plan.md` § 待決問題 Q34)),執行確認它因為「整則收完才一次回傳(`client.post` 不帶 `stream`,或把 `aiter_lines` 收進 list 再回)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004、FR-005、使用者故事 2 驗收情境 1、使用者故事 2 驗收情境 3、SC-002
- [X] T031b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/api/__init__.py`、`src/cgb/app.py` 只寫讓 US2-API-01 通過的程式碼;新增 `src/cgb/api/chat.py`(以 httpx 打 forward target、用 `src/cgb/ollama_compat/forward.py` 的 `_relay` 逐行轉送,`plan.md` § 待決問題 Q35),在 `src/cgb/api/__init__.py` 註冊路由;`src/cgb/app.py` 的 `Timeouts` 加 `chat_connect`(10)、`chat_read`(300)(`plan.md` § 待決問題 Q44),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T031a)
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004、FR-005、使用者故事 2 驗收情境 1、使用者故事 2 驗收情境 3、SC-002
- [X] T032a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-02 的測試(送出本文 `{"model": "hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF", "messages": [{"role":"user","content":"a"}, {"role":"assistant","content":"b","thinking":"想"}, {"role":"user","content":"c","images":["aGk="]}], "stream": false, "keep_alive": "5m", "think": true, "options": {"temperature": 0}, "system": "s", "format": "json"}`;分隔註解寫 `# ---- 004 US2-API-02`(`plan.md` § 待決問題 Q34)),執行確認它因為「把整份本文原樣轉送(像相容端點的 `forward()` 那樣),`stream: false`、`think`、`options`、`system` 跟著送出,或 `keep_alive` 照瀏覽器的 `"5m"`」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004、使用者故事 2 驗收情境 2、NFR-003;`plan.md` § 待決問題 Q9、Q14、Q59
- [X] T032b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-02 通過的程式碼;只轉 `role` 與 `content`,`stream` 為 true、帶 `keep_alive: -1`(`plan.md` § 待決問題 Q9、Q59),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T032a)
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004、使用者故事 2 驗收情境 2、NFR-003;`plan.md` § 待決問題 Q9、Q14、Q59
- [X] T033a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_chat.py` 寫 US2-API-03 的測試(送出預設本文;分隔註解寫 `# ---- 004 US2-API-03`(`plan.md` § 待決問題 Q34));T031b 的逐行轉送(不檢查結束行的統計欄位)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「把缺統計或耗時為 0 的結束行當成必要欄位不符,補一行 `ChatStreamFailure`(`OLLAMA_BAD_RESPONSE`)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-005;`plan.md` § 待決問題 Q8
- [X] T033b [US2] 🟢 /tdd 綠燈:US2-API-03 由 T031b 的逐行轉送(不檢查結束行的統計欄位) 滿足,確認 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-03 通過的程式碼(依賴 T033a)
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-005;`plan.md` § 待決問題 Q8
- [X] T034a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_chat.py` 寫 US2-API-04 的測試(送出預設本文;分隔註解寫 `# ---- 004 US2-API-04`(`plan.md` § 待決問題 Q34));T031b 的逐行轉送(`message.thinking` 原樣送出)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「轉送時只留 `message.content`,把 `thinking` 濾掉(Q10、D24)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US2-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`plan.md` § 待決問題 Q10
- [X] T034b [US2] 🟢 /tdd 綠燈:US2-API-04 由 T031b 的逐行轉送(`message.thinking` 原樣送出) 滿足,確認 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-04 通過的程式碼(依賴 T034a)
  - 🧪 `testplan.md` § US2-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004;`plan.md` § 待決問題 Q10
- [X] T035a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_chat.py` 寫 US2-API-05 的測試(送出預設本文;等 0.05 秒後放行 `g`;分隔註解寫 `# ---- 004 US2-API-05`(`plan.md` § 待決問題 Q34));T031b 的逐行轉送(以行為單位判讀,半行等到換行才送)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「逐「chunk」而不是逐「行」判讀,把半行當成不是 JSON 物件,補 `OLLAMA_BAD_RESPONSE`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US2-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004、NFR-006
- [X] T035b [US2] 🟢 /tdd 綠燈:US2-API-05 由 T031b 的逐行轉送(以行為單位判讀,半行等到換行才送) 滿足,確認 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-05 通過的程式碼(依賴 T035a)
  - 🧪 `testplan.md` § US2-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004、NFR-006
- [X] T036a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-06 的測試(送出預設本文,讀到第 1 行後關閉這個串流的回應(用戶端斷開,`AbortController` 的等價);0.3 秒後放行 `g`,再等 0.2 秒、`gc.collect()`;分隔註解寫 `# ---- 004 US2-API-06`(`plan.md` § 待決問題 Q34));同一個任務在 `tests/fakes/ollama_server.py` 的 `FakeOllamaServer` 加 `client_closed` 紀錄(`plan.md` § 待決問題 Q57),執行確認它因為「用戶端斷開後沒有關上游(`upstream.aclose` 沒被呼叫,遠端 Ollama 繼續產生)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-006、使用者故事 2 驗收情境 4;`research.md` § R5
- [X] T036b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-06 通過的程式碼;用戶端斷開時關上游、`_relay` 不留下未取回的例外(`src/cgb/ollama_compat/forward.py` 的介面不變,Ollama 相容端點共用),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T036a)
  - 🧪 `testplan.md` § US2-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-006、使用者故事 2 驗收情境 4;`research.md` § R5
- [X] T037a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-07 的測試(情況 A 依序送 `Content-Type: application/json` 的本文 `{"model":`(不是合法 JSON)與 `[1, 2]`(合法 JSON 但不是物件);情況 B 送 `{"model":`;分隔註解寫 `# ---- 004 US2-API-07`(`plan.md` § 待決問題 Q34)),執行確認它因為「對陣列本文取 `body["model"]` 丟 `TypeError`,回 500」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006
- [X] T037b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T037a)
  - 🧪 `testplan.md` § US2-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006
- [X] T038a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-08 的測試(依序送 `messages` 合法、`model` 分別為:A 缺少;B `123`;C `Qwen2.5`(官方名稱有大寫);D `huggingface.co/bartowski/x`;E `bartowski/x`(社群名稱);對照組 F `hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M`;分隔註解寫 `# ---- 004 US2-API-08`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒照 `ModelName` 檢查,把格式錯的名稱轉送給遠端,遠端回 404 變成 `OLLAMA_NOT_FOUND`」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004、FR-008、NFR-006
- [X] T038b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/domain/model_name.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-08 通過的程式碼;`src/cgb/domain/model_name.py` 新增 `is_valid`(`plan.md` § 待決問題 Q49;之後精選清單與下載共用);新代碼 `INVALID_MODEL_NAME` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T038a)
  - 🧪 `testplan.md` § US2-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004、FR-008、NFR-006
- [X] T039a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-09 的測試(依序送 `model` 合法、`messages` 分別為:A 缺少;B `"你好"`(不是陣列);C `[]`;分隔註解寫 `# ---- 004 US2-API-09`(`plan.md` § 待決問題 Q34)),執行確認它因為「空陣列照轉送,等遠端回 400 才報 `OLLAMA_BAD_REQUEST`(502)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006
- [X] T039b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-09 通過的程式碼;新代碼 `EMPTY_CHAT_MESSAGES` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T039a)
  - 🧪 `testplan.md` § US2-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006
- [X] T040a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-10 的測試(依序送 `model` 合法、`messages` 為一則合法的 user 訊息加上下列一則:A `"hi"`(不是物件);B `{"role":"system","content":"x"}`;C `{"content":"x"}`(缺 `role`);D `{"role":"user","content":1}`;E `{"role":"user"}`(缺 `content`);分隔註解寫 `# ---- 004 US2-API-10`(`plan.md` § 待決問題 Q34)),執行確認它因為「只檢查第一則或最後一則,中間不合法的照轉送」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006
- [X] T040b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-10 通過的程式碼;新代碼 `INVALID_CHAT_MESSAGE` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T040a)
  - 🧪 `testplan.md` § US2-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006
- [X] T041a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-11 的測試(每種狀態送出預設本文一次;分隔註解寫 `# ---- 004 US2-API-11`(`plan.md` § 待決問題 Q34)),執行確認它因為「就緒檢查只看「有沒有工作階段」,開啟中或重連中照樣以舊的 `base_url` 轉送」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、使用者故事 2 驗收情境 7
- [X] T041b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T041a)
  - 🧪 `testplan.md` § US2-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、使用者故事 2 驗收情境 7
- [X] T042a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-12 的測試(各送出預設本文一次;分隔註解寫 `# ---- 004 US2-API-12`(`plan.md` § 待決問題 Q34)),執行確認它因為「照現行 `forward()` 只接 `httpx.ConnectError`,B 的 `httpx.RemoteProtocolError` 往上拋回 500(`x-failure-rules` 第 2 條,Q7)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006;`plan.md` § 待決問題 Q7
- [X] T042b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T042a)
  - 🧪 `testplan.md` § US2-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006;`plan.md` § 待決問題 Q7
- [X] T043a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-13 的測試(各送出預設本文一次;分隔註解寫 `# ---- 004 US2-API-13`(`plan.md` § 待決問題 Q34)),執行確認它因為「照相容端點原樣轉送遠端的狀態碼與本文,瀏覽器收到 400 以為是自己輸入錯(Q13)、或收到 500」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006;`plan.md` § 待決問題 Q13、Q14
- [X] T043b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-13 通過的程式碼;新代碼 `OLLAMA_BAD_REQUEST`、`OLLAMA_SERVER_ERROR` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`(`OLLAMA_SERVER_ERROR` 的文字照 `prototype/chat.html` 的 `turn-error` 中間那句:「執行環境上的 Ollama 處理時發生錯誤,請稍後再試。」,analysis A40、分身決策紀錄 D105),同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T043a)
  - 🧪 `testplan.md` § US2-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006;`plan.md` § 待決問題 Q13、Q14
- [X] T044a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-14 的測試(各送出預設本文一次;分隔註解寫 `# ---- 004 US2-API-14`(`plan.md` § 待決問題 Q34)),執行確認它因為「跟著 302 導向打到別的路徑」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006
- [X] T044b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T044a)
  - 🧪 `testplan.md` § US2-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006
- [X] T045a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-15 的測試(送出預設本文,記下送出的時間;分隔註解寫 `# ---- 004 US2-API-15`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒把 `httpx.ReadTimeout` 接成 `OLLAMA_TIMEOUT`,往上拋回 500(現行 `forward()` 沒接逾時,Q7)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006;`plan.md` § 待決問題 Q7
- [X] T045b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T045a)
  - 🧪 `testplan.md` § US2-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006;`plan.md` § 待決問題 Q7
- [X] T046a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-16 的測試(送出預設本文,記下讀到第 1 行的時間;分隔註解寫 `# ---- 004 US2-API-16`(`plan.md` § 待決問題 Q34)),執行確認它因為「照現行 `_relay`,`httpx.ReadTimeout` 是 `TransportError` 的子類,兩段之間逾時被歸成串流中斷(`OLLAMA_STREAM_INTERRUPTED`)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、使用者故事 2 驗收情境 8
- [X] T046b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T046a)
  - 🧪 `testplan.md` § US2-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、使用者故事 2 驗收情境 8
- [X] T047a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-17 的測試(各送出預設本文一次;分隔註解寫 `# ---- 004 US2-API-17`(`plan.md` § 待決問題 Q34)),執行確認它因為「照現行 `_relay` 在遠端正常結束(`StopAsyncIteration`)時直接收尾,沒看有沒有出現 `done: true`,前端把半則回覆顯示成正常完成」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、使用者故事 2 驗收情境 8
- [X] T047b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-17 通過的程式碼;若要把 `OLLAMA_STREAM_INTERRUPTED` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`(文字照 `prototype/chat.html` 的 `turn-interrupted` 中間那句:「執行環境上的 Ollama 回應到一半就斷了,請稍後再試。」,analysis A40、D105),同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T047a)
  - 🧪 `testplan.md` § US2-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、使用者故事 2 驗收情境 8
- [X] T048a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-18 的測試(送出預設本文;分隔註解寫 `# ---- 004 US2-API-18`(`plan.md` § 待決問題 Q34)),執行確認它因為「照 `_relay` 原樣轉送遠端的 `{"error": "<英文>"}`(Q11、D25)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、使用者故事 2 驗收情境 8;`plan.md` § 待決問題 Q6、Q11
- [X] T048b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-18 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T048a)
  - 🧪 `testplan.md` § US2-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、使用者故事 2 驗收情境 8;`plan.md` § 待決問題 Q6、Q11
- [X] T049a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-19 的測試(各送出預設本文一次;分隔註解寫 `# ---- 004 US2-API-19`(`plan.md` § 待決問題 Q34)),執行確認它因為「不判讀每一行就原樣轉送壞行,前端 `JSON.parse` 失敗」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006
- [X] T049b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-19 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T049a)
  - 🧪 `testplan.md` § US2-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006
- [X] T050a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-20 的測試(讀到第 1 行後:A 送 `DELETE /api/session`;B 送 `POST /api/session/restart`(`runtimeType` L4);C 不做事,等健康檢查判定失聯;之後 A 再送 `GET /api/models`;分隔註解寫 `# ---- 004 US2-API-20`(`plan.md` § 待決問題 Q34)),執行確認它因為「沿用 `_relay` 的 `SESSION_ENDED_MESSAGE` 字串行,沒有 `code`(Q12、D26)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、使用者故事 2 驗收情境 8、邊界情況;`plan.md` § 待決問題 Q12、Q60
- [X] T050b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/domain/errors.py` 只寫讓 US2-API-20 通過的程式碼;失聯時只結束對話頁的轉送,Ollama 相容端點不變(`plan.md` § 待決問題 Q60);若要把 `SESSION_ENDED` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T050a)
  - 🧪 `testplan.md` § US2-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、使用者故事 2 驗收情境 8、邊界情況;`plan.md` § 待決問題 Q12、Q60
- [X] T051a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-21 的測試(在 T 送出預設本文;`g0.wait_entered_async()` 後查 `GET /api/session`;推進時鐘到 T+90 秒,放行 `g0`、`g1` 讀完;等 `idle.activeRequests` 回到 0 後記下 `ended_at = fake_clock.now()`;分隔註解寫 `# ---- 004 US2-API-21`(`plan.md` § 待決問題 Q34)),執行確認它因為「UI 的 `/api/*` 不經 `IdleHook`,`api/chat.py` 沒呼叫 `request_started`/`request_finished`,對話完全不重設倒數(FR-007)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 9
- [X] T051b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py`、`src/cgb/services/idle_monitor.py` 只寫讓 US2-API-21 通過的程式碼;通過檢查 (1)(2) 之後才呼叫 `IdleMonitor.request_started`,串流結束或斷開時呼叫 `request_finished`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T051a)
  - 🧪 `testplan.md` § US2-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 9
- [X] T052a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-22 的測試(情況 A:時鐘設到 T+20 秒,送 `messages` 為 `[]` 的本文(400);情況 B:時鐘設到 T+40 秒,替身回 `JsonReply({"error":"x"}, status=500)` 送出預設本文(502);情況 C:時鐘設到 T+50 秒,替身回 `NdjsonReply([chunk("你")], then="disconnect")` 送出並讀完;每次之後查 `GET /api/session`;分隔註解寫 `# ---- 004 US2-API-22`(`plan.md` § 待決問題 Q34)),執行確認它因為「在讀本文之前就呼叫 `request_started()`,檢查不過的請求也重設倒數(違反「通過 (1)(2) 之後」)」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 9
- [X] T052b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py` 只寫讓 US2-API-22 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T052a)
  - 🧪 `testplan.md` § US2-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-007、使用者故事 2 驗收情境 9
- [X] T053a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_chat.py` 寫 US2-API-23 的測試(對話頁經 UI 送出預設本文;讀到第 1 行後,區網程式經相容端點送 `POST /api/chat`(同一個 `MODEL`);兩邊都讀到第 1 行後放行 `g`;分隔註解寫 `# ---- 004 US2-API-23`(`plan.md` § 待決問題 Q34));T031b 的轉送(`api/chat.py` 不加鎖,同一個模型的請求交給遠端 Ollama 自己排)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「對話頁自己加一把鎖或同一個模型只允許一個串流,讓區網程式的請求排隊或回 503」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US2-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § 邊界情況
- [X] T053b [US2] 🟢 /tdd 綠燈:US2-API-23 由 T031b 的轉送(`api/chat.py` 不加鎖,同一個模型的請求交給遠端 Ollama 自己排) 滿足,確認 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-23 通過的程式碼(依賴 T053a)
  - 🧪 `testplan.md` § US2-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § 邊界情況
- [X] T054a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_chat.py` 寫 US2-API-24 的測試(送出預設本文,0.1 秒後放行 `g`;分隔註解寫 `# ---- 004 US2-API-24`(`plan.md` § 待決問題 Q34));T031b 的轉送(不先預先載入,遠端 Ollama 自己載入)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「模型沒載入時先另外預先載入(`preload`)再轉送,多一次往返」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US2-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004、使用者故事 2 驗收情境 6
- [X] T054b [US2] 🟢 /tdd 綠燈:US2-API-24 由 T031b 的轉送(不先預先載入,遠端 Ollama 自己載入) 滿足,確認 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-24 通過的程式碼(依賴 T054a)
  - 🧪 `testplan.md` § US2-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-004、使用者故事 2 驗收情境 6
- [X] T055a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_chat.py` 寫 US2-API-25 的測試(送出預設本文;等 `g0` 被走到後放行 `g0` 並記下時間 t0;之後每讀到第 i 行就等 0.02 秒再放行 `g(i+1)`;分隔註解寫 `# ---- 004 US2-API-25`(`plan.md` § 待決問題 Q34));T031b 的逐行轉送(`_relay` 每讀到一行就送出)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「以 `aiter_lines` 收齊再一次 `yield`,或用 `aiter_bytes` 搭配自己的緩衝(例如湊滿 64 KB 或等到 `done: true` 才送出)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US2-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、SC-002、FR-004
- [X] T055b [US2] 🟢 /tdd 綠燈:US2-API-25 由 T031b 的逐行轉送(`_relay` 每讀到一行就送出) 滿足,確認 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-25 通過的程式碼(依賴 T055a)
  - 🧪 `testplan.md` § US2-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-003、SC-002、FR-004
- [X] T056a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_chat.py` 寫 US2-API-26 的測試(送出三次 `messages` 為 `[{"role":"user","content":USER_MARK}, {"role":"assistant","content":REPLY_MARK}, {"role":"user","content":USER_MARK}]` 的本文並讀完;再送一次第二則 `role` 為 `system`、`content` 為 `USER_MARK` 的本文(400);等 0.2 秒;分隔註解寫 `# ---- 004 US2-API-26`(`plan.md` § 待決問題 Q34));既有的日誌設定(`src/cgb/logging_setup.py` 只記時間、模型、耗時與狀態碼)與 T031b 的 `api/chat.py`(不記本文)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「路由以 `logger.debug("chat %s", body)` 或例外時 `logger.exception` 帶出本文」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US2-API-26
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-002、SC-002
- [X] T056b [US2] 🟢 /tdd 綠燈:US2-API-26 由 既有的日誌設定(`src/cgb/logging_setup.py` 只記時間、模型、耗時與狀態碼)與 T031b 的 `api/chat.py`(不記本文) 滿足,確認 `src/cgb/api/chat.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/chat.py` 只寫讓 US2-API-26 通過的程式碼(依賴 T056a)
  - 🧪 `testplan.md` § US2-API-26
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-002、SC-002
- [X] T057a [US2] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_chat.py` 寫 US2-API-27 的測試(每組送出那一個請求一次並讀完;分隔註解寫 `# ---- 004 US2-API-27`(`plan.md` § 待決問題 Q34));T037b~T052b 做出的檢查與歸類已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「任何一種組合讓 httpx 例外、`json.JSONDecodeError`、`KeyError`(`MESSAGES` 缺代碼)往上拋回 500,或串流中途直接斷線、沒有最後一行」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US2-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、SC-006、FR-008
- [X] T057b [US2] 🟢 /tdd 綠燈:US2-API-27 由 T037b~T052b 做出的檢查與歸類 滿足,確認 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-API-27 通過的程式碼(依賴 T057a)
  - 🧪 `testplan.md` § US2-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、SC-006、FR-008
- [X] T241a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-28 的測試(A~C 三輪各換鋪陳、各送出預設本文一次;分隔註解寫 `# ---- 004 US2-API-28`(`plan.md` § 待決問題 Q34)),執行確認它因為「對話頁沿用的三句 `OLLAMA_*` 說明仍寫「無法確認哪些模型已經下載」」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-28
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-007;`plan.md` § 待決問題 Q61
- [X] T241b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/errors.py` 只寫讓 US2-API-28 通過的程式碼;把 `MESSAGES` 的 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT` 改成模型目錄與對話頁都通的通用說法(去掉「無法確認哪些模型已經下載」,文字照 `prototype/chat.html` 的 `turn-unavailable`、`turn-bad-response`、`turn-start-timeout`;`plan.md` § 待決問題 Q61),不另開對話用的訊息表;`tests/e2e/test_locale.py` 的 `API_ERRORS` 只比代碼,不用改,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T241a)
  - 🧪 `testplan.md` § US2-API-28
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-007;`plan.md` § 待決問題 Q61
- [X] T242a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_chat.py` 寫 US2-API-29 的測試(各送出預設本文一次;同一個任務在 `tests/fakes/ollama_server.py` 讓 `headers` 的值為 `None` 時不送那個標頭;分隔註解寫 `# ---- 004 US2-API-29`(`plan.md` § 待決問題 Q34)),執行確認它因為「以整個 `Content-Type` 字串和 `application/x-ndjson` 比相等,帶 `charset` 或大小寫不同的 NDJSON 被當成壞回應」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-29
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006;`plan.md` § 待決問題 Q45
- [X] T242b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/chat.py` 只寫讓 US2-API-29 通過的程式碼;`Content-Type` 只比 `;` 之前、去掉空白、不分大小寫的 media type,沒有這個標頭歸 `OLLAMA_BAD_RESPONSE`(`contracts/remote-ollama.openapi.yaml` 的 `info.x-failure-rules` (4),`plan.md` § 待決問題 Q45),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T242a)
  - 🧪 `testplan.md` § US2-API-29
  - ⚙ `contracts/ui.openapi.yaml` § `paths./chat.post`、`components.schemas.ChatInput`、`components.schemas.ChatStreamLine`、`components.schemas.ChatChunk`、`components.schemas.ChatStreamFailure`、`components.schemas.Error`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-008、NFR-006;`plan.md` § 待決問題 Q45
- [X] T058 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T031b~T057b、T241b~T242b 記下的重構清單(範圍限 `src/cgb/api/chat.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/domain/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T242b)
  - 🧪 `testplan.md` § US2-API-01~US2-API-27、US2-API-28~US2-API-29
  - 📎 `testplan.md` § 3.1

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(Playwright)接測試行程內真的後端(`tests/e2e/conftest.py` 的 `e2e_servers`,UI 127.0.0.1:8781),轉接層用替身;e2e 用固定 port,同一時間只跑一份
> 對話轉送經真的 HTTP 打 `fakes.server`(`FakeOllamaServer` 以 `NdjsonReply` 排行與行間延遲,行間延遲壓在 0.05 秒),模型清單以 `set_tags`、`set_loaded` 鋪(`testplan.md` § 3.2)

- [X] T059a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-01 的測試(選 `qwen2.5`、輸入「你好」、按「送出」;分隔註解寫 `# ---- 004 US2-AJ-01`(`plan.md` § 待決問題 Q34));同一個任務照 `testplan.md` § 3.2 在 `tests/e2e/conftest.py` 的 `e2e_servers` 讓 `FakeOllamaServer` 經 `FakeTunnel` 的本機 port 接到對話轉送(既有的做法沒有就補),執行確認它因為「前端用 `response.json()` 或 `await response.text()` 等整個本文才顯示(違反逐段)」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-004
- [X] T059b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/chat.html`、`src/cgb/static/js/chat.js`、`src/cgb/static/js/api.js`、`src/cgb/static/style.css`、`src/cgb/static/index.html`、`src/cgb/static/library.html`、`src/cgb/static/models.html`、`src/cgb/static/history.html`、`src/cgb/static/usage.html`、`src/cgb/static/login.html` 只寫讓 US2-AJ-01 通過的程式碼;新增 `src/cgb/static/chat.html` 與 `src/cgb/static/js/chat.js`(照 `prototype/chat.html`),`src/cgb/static/js/api.js` 加對話的串流呼叫;把 `prototype/style.css` 的「004:對話頁」區段搬進 `src/cgb/static/style.css`,只用既有的 `var(--…)`;有導覽的 `src/cgb/static/index.html`、`library.html`、`models.html`、`history.html`、`usage.html`、`login.html` 的 `.topbar` 導覽加「對話」連到 `chat.html`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T059a)
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-004
- [X] T060a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-02 的測試(再輸入「再說一次」、按「送出」;分隔註解寫 `# ---- 004 US2-AJ-02`(`plan.md` § 待決問題 Q34)),執行確認它因為「前端每次只送最後一則,或沒把模型的回覆以 `assistant` 帶回去」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-02
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-004
- [X] T060b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T060a)
  - 🧪 `testplan.md` § US2-AJ-02
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-004
- [X] T061a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-03 的測試(送出一則並等到 `DONE`;分隔註解寫 `# ---- 004 US2-AJ-03`(`plan.md` § 待決問題 Q34)),執行確認它因為「用 `total_duration` 或 `eval_count ÷ eval_duration` 沒換成秒,算出 0.0000000394」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-03
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-005
- [X] T061b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T061a)
  - 🧪 `testplan.md` § US2-AJ-03
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-005
- [X] T062a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-04 的測試(送出一則並等到結束;分隔註解寫 `# ---- 004 US2-AJ-04`(`plan.md` § 待決問題 Q34)),執行確認它因為「缺欄位時算成 `NaN tokens/s` 或 `Infinity`」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-04
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-005;`plan.md` § 待決問題 Q8
- [X] T062b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T062a)
  - 🧪 `testplan.md` § US2-AJ-04
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-005;`plan.md` § 待決問題 Q8
- [X] T063a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-05 的測試(看到「一二」後按「停止」;再輸入「下一則」並送出(這次替身照 US2-AJ-01 回完整 6 行);分隔註解寫 `# ---- 004 US2-AJ-05`(`plan.md` § 待決問題 Q34)),執行確認它因為「「停止」只把按鈕變灰,沒有 `abort()` 連線,遠端繼續產生」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-05
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-006
- [X] T063b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T063a)
  - 🧪 `testplan.md` § US2-AJ-05
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-006
- [X] T064a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-06 的測試(情況 A 按「清空」;情況 B 重新完成一輪後,把模型選單換成 `llama3.2:3b`,再送出「嗨」;分隔註解寫 `# ---- 004 US2-AJ-06`(`plan.md` § 待決問題 Q34)),執行確認它因為「「清空」只清畫面、沒清前端保存的 `messages`,下一則仍帶舊對話」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-06
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-006
- [X] T064b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T064a)
  - 🧪 `testplan.md` § US2-AJ-06
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-006
- [X] T065a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-07 的測試(選 `qwen2.5` 送出一則;分隔註解寫 `# ---- 004 US2-AJ-07`(`plan.md` § 待決問題 Q34)),執行確認它因為「前端沒看 `GET /api/models` 的 `loaded`,第一段之前什麼都不顯示」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-07
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-004
- [X] T065b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T065a)
  - 🧪 `testplan.md` § US2-AJ-07
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-004
- [X] T066a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-08 的測試(各打開一次對話頁;分隔註解寫 `# ---- 004 US2-AJ-08`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒有工作階段時仍可送出,送出後才收到 503」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-08
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008
- [X] T066b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T066a)
  - 🧪 `testplan.md` § US2-AJ-08
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008
- [X] T067a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-09 的測試(看到「一二」後由另一個分頁結束工作階段;分隔註解寫 `# ---- 004 US2-AJ-09`(`plan.md` § 待決問題 Q34)),執行確認它因為「後端被結束時直接關閉連線、沒有補 `SESSION_ENDED` 的最後一行,前端當成正常完成」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-09
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008、邊界情況
- [X] T067b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T067a)
  - 🧪 `testplan.md` § US2-AJ-09
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008、邊界情況
- [X] T068a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-10 的測試(各送出一則;分隔註解寫 `# ---- 004 US2-AJ-10`(`plan.md` § 待決問題 Q34)),執行確認它因為「把遠端的英文 error 行原樣顯示」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-10
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008
- [X] T068b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-10 通過的程式碼;`turn-error`、`turn-timeout` 的說明照 `prototype/chat.html` 寫成固定開頭加後端 `error.message` 的通用說法,不寫死「推論失敗(例如記憶體不足)」與秒數(`plan.md` § 待決問題 Q61),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T068a)
  - 🧪 `testplan.md` § US2-AJ-10
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008
- [X] T069a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-11 的測試(送出一則;分隔註解寫 `# ---- 004 US2-AJ-11`(`plan.md` § 待決問題 Q34)),執行確認它因為「前端只讀 `message.content`,思考過程整段看不到、畫面卡在空白(`plan.md` Q10 決定顯示)」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-11
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-004;`plan.md` § 待決問題 Q10
- [X] T069b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T069a)
  - 🧪 `testplan.md` § US2-AJ-11
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-004;`plan.md` § 待決問題 Q10
- [X] T070a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-12 的測試(每種狀態下取對話頁 `main` 的 `innerText`,去掉模型名稱與 `tokens/s`;分隔註解寫 `# ---- 004 US2-AJ-12`(`plan.md` § 待決問題 Q34)),執行確認它因為「新的對話頁文案用英文(例如 `Send`、`Stop`、`Clear`、`Thinking…`)」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-12
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § NFR-007
- [X] T070b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/js/chat.js` 只寫讓 US2-AJ-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T070a)
  - 🧪 `testplan.md` § US2-AJ-12
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § NFR-007
- [X] T243a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-13 的測試(依情況 A 送 `一` 後斷線、B 送 `一` 後送一行 `not json`,各送出一則;分隔註解寫 `# ---- 004 US2-AJ-13`(`plan.md` § 待決問題 Q34)),執行確認它因為「前端只認得 `OLLAMA_SERVER_ERROR`、`OLLAMA_TIMEOUT`、`SESSION_ENDED`,`OLLAMA_STREAM_INTERRUPTED`、`OLLAMA_BAD_RESPONSE` 落到預設分支」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-13
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008;`plan.md` § 待決問題 Q61
- [X] T243b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/chat.html`、`src/cgb/static/js/chat.js` 只寫讓 US2-AJ-13 通過的程式碼;照 `prototype/chat.html` 加 `[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T243a)
  - 🧪 `testplan.md` § US2-AJ-13
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008;`plan.md` § 待決問題 Q61
- [X] T244a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-14 的測試(依情況 A 回 404、B 回 `DisconnectReply()`、C 回 `HangReply()` 並注入 0.3 秒的 `chat_read`、D 回 500 `{"error":"model requires more system memory"}`(502 `OLLAMA_SERVER_ERROR`,analysis A39、D105),各輸入「你好」並按「送出」;分隔註解寫 `# ---- 004 US2-AJ-14`(`plan.md` § 待決問題 Q34)),執行確認它因為「前端只處理 200 串流裡的最後一行,串流開始前的 404、502、504 沒有畫面、回覆一直轉圈」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-14
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008;`plan.md` § 待決問題 Q61
- [X] T244b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/chat.html`、`src/cgb/static/js/chat.js` 只寫讓 US2-AJ-14 通過的程式碼;照 `prototype/chat.html` 加 `[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`,說明用錯誤回應的 `message`(「沒有送出:」加 `message`,502 四個代碼共用 `turn-unavailable`,不寫死「連不到」),回覆下方的標示照 `prototype/chat.html` 的 `CUT.unavailable`「沒有回覆:Ollama 暫時無法使用」(analysis A39、D105),使用者的訊息留在 `#log`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T244a)
  - 🧪 `testplan.md` § US2-AJ-14
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008;`plan.md` § 待決問題 Q61
- [X] T245a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us2_chat.py` 寫 US2-AJ-15 的測試(看到「一二」後由另一個分頁按「變更類型」選 L4 並確認;分隔註解寫 `# ---- 004 US2-AJ-15`(`plan.md` § 待決問題 Q34)),執行確認它因為「`turn-lost` 只寫「已結束或失聯」,變更類型時說明不對」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-15
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008、邊界情況
- [X] T245b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/chat.html`、`src/cgb/static/js/chat.js` 只寫讓 US2-AJ-15 通過的程式碼;`[data-state="turn-lost"]` 的說明照 `prototype/chat.html` 含「正在變更類型」,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T245a)
  - 🧪 `testplan.md` § US2-AJ-15
  - ⚙ `prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-008、邊界情況
- [X] T071 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T059b~T070b、T243b~T245b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T245b)
  - 🧪 `testplan.md` § US2-AJ-01~US2-AJ-12、US2-AJ-13~US2-AJ-15
  - 📎 `testplan.md` § 3.2

### 介面覆蓋(US2)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `remote-ollama.openapi.yaml` § `paths./api/chat.post` | T031b~T057b | T031a~T057a |
| `ui.openapi.yaml` § `paths./chat.post` | T031b~T057b | T031a~T057a |
| `chat.html` § `[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-thinking"]`、`[data-state="turn-streaming"]`、`[data-state="turn-stopped"]`、`[data-state="turn-norate"]`、`[data-state="turn-error"]`、`[data-state="turn-timeout"]`、`[data-state="turn-lost"]` | T059b~T070b、T243b~T245b | T059a~T070a、T243a~T245a |
| `chat.html` § `[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]` | T243b | T243a |
| `chat.html` § `[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]` | T244b | T244a |

### 測試案例覆蓋(US2)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US2-API-01~US2-API-27 | T031a~T057a | T031b~T057b | T058 |
| US2-API-28~US2-API-29 | T241a~T242a | T241b~T242b | T058 |
| US2-AJ-01~US2-AJ-12 | T059a~T070a | T059b~T070b | T071 |
| US2-AJ-13~US2-AJ-15 | T243a~T245a | T243b~T245b | T071 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 全綠(含 `tests/integration/test_ollama_compat.py` 在 `_relay` 改過之後照原樣回歸、`tests/e2e/test_locale.py` 加了對話的新代碼);重構任務前後的測試結果相同

---

## Phase 4: User Story 3 - 在 UI 編輯精選清單,開好工作階段就自動下載 (Priority: P2)

**Goal**: 沒有工作階段時就能在 UI 新增、修改、刪除精選清單並設定「開好就自動下載」;每個工作階段第一次就緒時依清單順序排入設了自動下載、執行環境上沒有、也不在佇列的模型,放不下、取不到大小或可能無法載入的跳過,模型頁佇列上方的提示區列出結果,保留到工作階段結束或使用者關閉

**Independent Test**: 照 `testplan.md` § 4 的全部案例:E2 以 `uv run pytest tests/integration/test_api_curated.py tests/integration/test_api_auto_download.py`、E4 以 `uv run pytest tests/integration/test_db_schema.py`、跨端點驗收以 `uv run pytest tests/e2e/test_004_us3_curated.py` 執行全綠

### E2 後端 UI API(FastAPI REST 與 SSE)

> E2 與 E4 兩節平行;E2 不改 `src/cgb/db/schema.py`(自動下載的欄位與表已由故事 1 的 E4 節照 `contracts/store.dbml` 建立,這一輪的約束與遷移案例在本故事的 E4 節)。US3-API-01~11 寫進 `tests/integration/test_api_curated.py`,US3-API-12~37 寫進新的 `tests/integration/test_api_auto_download.py`(從前者匯入 `set_hf`、`curate`、`wait_auto`)。精選清單的錯誤代碼沿用 001;自動下載的判定照 `contracts/ui.openapi.yaml` 的 `info.x-auto-download` (1)~(6)。精選清單操作的案例(US3-API-01~10)不開工作階段,最後斷言兩個 `get_manifest` 被呼叫 0 次

- [X] T072a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-01 的測試(新增 `{"name":"qwen2.5","description":"日常用","recommendedRuntimeType":{"gpu":"T4","highMem":false}}`;新增 `{"name":"hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF","autoDownload":true}`;之後 `GET /api/curated`;分隔註解寫 `# ---- 004 US3-API-01`(`plan.md` § 待決問題 Q34));同一個任務在 `tests/fakes/adapters.py` 建 `FakeHuggingFaceHub`(照 `_FakeAdapter`,`search_models(query, cursor=None)`、`list_repo_files(author, model)`、`get_manifest(author, model, tag)`、`list_quants(author, model)` 四個方法照 `plan.md` § 待決問題 Q49 一次寫齊)並從 `tests/fakes/__init__.py` 匯出,`tests/conftest.py` 的 `Fakes` 加 `huggingface` 欄位並放進 `as_kwargs()`;在 `tests/integration/test_api_curated.py` 新增 `set_hf`、`curate`、`wait_auto`(`plan.md` § 待決問題 Q65),執行確認它因為「照現況 `curated_payload` 固定回 `recommendedRuntimeType: null`」這類實作而失敗(`autoDownload` 的存讀已由 T013b 做到,不能當失敗的理由;若一執行就通過,照 `plan.md` § 待決問題 Q63 改當對照組)
  - 🧪 `testplan.md` § US3-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-010、FR-018、使用者故事 3 驗收情境 1、邊界情況;`plan.md` § 待決問題 Q65
- [X] T072b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py`、`src/cgb/app.py`、`src/cgb/api/__init__.py` 只寫讓 US3-API-01 通過的程式碼;`curated_payload` 回 `recommendedRuntimeType` 與 `autoDownload`;`src/cgb/app.py` 的 `create_app` 接受 `huggingface=`(預設 None;正式的 `HuggingFaceHub()` 由故事 4 的 T186b接上,`plan.md` § 待決問題 Q65),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T072a)
  - 🧪 `testplan.md` § US3-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-010、FR-018、使用者故事 3 驗收情境 1、邊界情況;`plan.md` § 待決問題 Q65
- [X] T073a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-02 的測試(`PUT /api/curated/{b}` 帶 `{"name":"hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M","description":"小模型","recommendedRuntimeType":{"gpu":"L4","highMem":true},"autoDownload":true}`;之後列出;分隔註解寫 `# ---- 004 US3-API-02`(`plan.md` § 待決問題 Q34)),執行確認它因為「修改以「刪除再新增」實作,b 換了新 id、排到最後」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-010、使用者故事 3 驗收情境 2
- [X] T073b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py` 只寫讓 US3-API-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T073a)
  - 🧪 `testplan.md` § US3-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-010、使用者故事 3 驗收情境 2
- [X] T074a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-03 的測試(`PUT /api/curated/{a}` 只帶 `{"name":"qwen2.5:7b"}`;之後列出;分隔註解寫 `# ---- 004 US3-API-03`(`plan.md` § 待決問題 Q34)),執行確認它因為「修改做成部分更新,沒給的欄位保留舊值(合約是整筆取代,Q15、D29),前端只切換自動下載時舊的說明被意外留下或清不掉」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-010;`plan.md` § 待決問題 Q15
- [X] T074b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py` 只寫讓 US3-API-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T074a)
  - 🧪 `testplan.md` § US3-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-010;`plan.md` § 待決問題 Q15
- [X] T075a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-04 的測試(`DELETE /api/curated/{b}`;再 `DELETE /api/curated/{b}`;`PUT /api/curated/{b}` 帶 `{"name":"qwen2.5:1.5b"}`;`DELETE /api/curated/999`;之後列出;分隔註解寫 `# ---- 004 US3-API-04`(`plan.md` § 待決問題 Q34)),執行確認它因為「照現況 `remove_curated` 不看有沒有刪到就回 204」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.delete`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`、`components.schemas.CuratedModel`、`paths./curated/{id}.put`、`components.schemas.CuratedModelInput`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、NFR-006
- [X] T075b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py`、`src/cgb/domain/errors.py` 只寫讓 US3-API-04 通過的程式碼;刪除與修改對不存在的 id 回 404 `CURATED_NOT_FOUND`;若要把 `CURATED_NOT_FOUND` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T075a)
  - 🧪 `testplan.md` § US3-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.delete`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`、`components.schemas.CuratedModel`、`paths./curated/{id}.put`、`components.schemas.CuratedModelInput`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、NFR-006
- [X] T076a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-05 的測試(情況 A:新增 `qwen2.5:LATEST`;情況 B:新增 `hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m`;情況 C:新增 `hf.co/UNSLOTH/qwen3-0.6b-gguf:latest`;對照組 D:新增 `hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:Q8_0`;對照組 E:新增 `qwen2.5:7b`;之後列出;分隔註解寫 `# ---- 004 US3-API-05`(`plan.md` § 待決問題 Q34)),執行確認它因為「照現況以 SQLite `UNIQUE` 照原樣比對,大小寫不同的 A、B、C 都存進去」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018、使用者故事 3 驗收情境 3
- [X] T076b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py`、`src/cgb/domain/model_name.py` 只寫讓 US3-API-05 通過的程式碼;`src/cgb/domain/model_name.py` 新增 `match_key`(補版本後 casefold,`plan.md` § 待決問題 Q49),重複檢查改用它,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T076a)
  - 🧪 `testplan.md` § US3-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018、使用者故事 3 驗收情境 3
- [X] T077a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-06 的測試(`PUT /api/curated/{b}` 帶 `{"name":"hf.co/bartowski/SMOLLM2-135M-Instruct-GGUF:q4_k_m"}`;`PUT /api/curated/{a}` 帶 `{"name":"hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m"}`(只改自己的大小寫);之後列出;分隔註解寫 `# ---- 004 US3-API-06`(`plan.md` § 待決問題 Q34)),執行確認它因為「修改的重複檢查沒排除自己,只改自己大小寫也回 409」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018、使用者故事 3 驗收情境 3、NFR-006
- [X] T077b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py` 只寫讓 US3-API-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T077a)
  - 🧪 `testplan.md` § US3-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018、使用者故事 3 驗收情境 3、NFR-006
- [X] T078a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-07 的測試(依序新增名稱為 `Qwen2.5`、`huggingface.co/bartowski/x-GGUF`、`HF.co/bartowski/x-GGUF`、`bartowski/x`(社群名稱)、`hf.co/bartowski`、`""`、`123`(數字)的本文,以及不帶 `name` 的 `{"description":"x"}`;`PUT /api/curated/{a}` 帶 `{"name":"Qwen2.5"}`;之後列出;分隔註解寫 `# ---- 004 US3-API-07`(`plan.md` § 待決問題 Q34)),執行確認它因為「照現況完全不驗名稱,`Qwen2.5` 存成 `Qwen2.5:latest`」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated/{id}.put`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-018、NFR-006、邊界情況
- [X] T078b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py` 只寫讓 US3-API-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T078a)
  - 🧪 `testplan.md` § US3-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated/{id}.put`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-018、NFR-006、邊界情況
- [X] T079a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-08 的測試(情況 A:本文 `{"name":`(不是合法 JSON);B:本文 `[]`;C:`description` 為 201 個字;C 對照:`description` 為 200 個字;D:`recommendedRuntimeType` 為 `{"gpu":"V100","highMem":false}`;E:`{"gpu":"T4","highMem":"no"}`;F:`{"highMem":false}`;G:`autoDownload` 為 `"true"`;H:`autoDownload` 為 `1`;每個情況名稱各用不同的合法名稱;之後列出;分隔註解寫 `# ---- 004 US3-API-08`(`plan.md` § 待決問題 Q34)),執行確認它因為「`[]` 讓 `body.get` 丟 `AttributeError`、回 500」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-010、NFR-006
- [X] T079b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py`、`src/cgb/domain/errors.py` 只寫讓 US3-API-08 通過的程式碼;新代碼 `INVALID_AUTO_DOWNLOAD` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T079a)
  - 🧪 `testplan.md` § US3-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-010、NFR-006
- [X] T080a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-09 的測試(對 a 依序 `PUT` 與 US3-API-08 情況 A~H 相同的本文(名稱都用 `qwen2.5:7b`);之後列出;分隔註解寫 `# ---- 004 US3-API-09`(`plan.md` § 待決問題 Q34)),執行確認它因為「修改與新增各寫一套驗證,修改漏了 `recommendedRuntimeType` 或 `autoDownload` 的檢查」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-010、NFR-006
- [X] T080b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py` 只寫讓 US3-API-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T080a)
  - 🧪 `testplan.md` § US3-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-010、NFR-006
- [X] T081a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_curated.py` 寫 US3-API-10 的測試(新增 `{"name":"qwen2.5:32b","recommendedRuntimeType":{"gpu":"H100","highMem":false}}`(id a);新增 `qwen2.5:7b`(id b),再 `PUT /api/curated/{b}` 帶 `{"name":"qwen2.5:7b","recommendedRuntimeType":{"gpu":"H100","highMem":true}}`;之後列出;分隔註解寫 `# ---- 004 US3-API-10`(`plan.md` § 待決問題 Q34));既有 `src/cgb/api/curated.py` 的執行階段類型檢查(`GpuType` 含 H100)與 T072b 回傳的 `recommendedRuntimeType`已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「把 FR-017 的「選單不列 H100」做進後端驗證,`GpuType` 少了 H100,送 H100 回 400 `INVALID_RUNTIME_TYPE`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated/{id}.put`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-017
- [X] T081b [US3] 🟢 /tdd 綠燈:US3-API-10 由 既有 `src/cgb/api/curated.py` 的執行階段類型檢查(`GpuType` 含 H100)與 T072b 回傳的 `recommendedRuntimeType` 滿足,確認 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py` 只寫讓 US3-API-10 通過的程式碼(依賴 T081a)
  - 🧪 `testplan.md` § US3-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated/{id}.put`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、FR-017
- [X] T082a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-11 的測試(情況 A:沒有工作階段時列出;B:`open_ready` 後,`set_tags(fakes, tag("hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m", 105_471_520), tag("qwen2.5:latest", 4_683_087_332))` 再列出;C:`list_local_models.raises("OLLAMA_UNREACHABLE")` 再列出;分隔註解寫 `# ---- 004 US3-API-11`(`plan.md` § 待決問題 Q34)),執行確認它因為「照現況固定回 `runtimeChecked: false`、`downloaded: false`」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.get`、`components.schemas.CuratedList`、`components.schemas.CuratedModel`
  - 📎 `spec.md` § FR-009、FR-018、NFR-006
- [X] T082b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py`、`src/cgb/services/downloads.py` 只寫讓 US3-API-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T082a)
  - 🧪 `testplan.md` § US3-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.get`、`components.schemas.CuratedList`、`components.schemas.CuratedModel`
  - 📎 `spec.md` § FR-009、FR-018、NFR-006
- [X] T083a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-12 的測試(`open_ready`;`wait_auto` 等 `state` 為 `done`;之後 `GET /api/downloads` 與 `GET /api/downloads/auto-result`;分隔註解寫 `# ---- 004 US3-API-12`(`plan.md` § 待決問題 Q34)),執行確認它因為「T013b 的最小版本排入時不取大小,hf.co 名稱沒向 `huggingface.get_manifest` 取大小(則8)、`source` 沒依前綴推出(則4)」這類實作而失敗(第一次就緒時排入已由 T013b 做到,不能當失敗的理由;若一執行就通過,照 `plan.md` § 待決問題 Q63 改當對照組)
  - 🧪 `testplan.md` § US3-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、使用者故事 3 驗收情境 4、SC-003
- [X] T083b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/services/downloads.py`、`src/cgb/api/__init__.py` 只寫讓 US3-API-12 通過的程式碼;`src/cgb/services/auto_download.py` 依精選清單順序判定;hf.co 名稱向 `huggingface.get_manifest` 取大小、官方名稱向 `model_library` 取,分流寫在 `src/cgb/services/downloads.py` 的取大小函式(`info.x-download-check-order` (6)),自動下載與試算共用,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T083a)
  - 🧪 `testplan.md` § US3-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、使用者故事 3 驗收情境 4、SC-003
- [X] T084a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-13 的測試(`open_ready`;`wait_auto` 等 `done`;之後列出佇列;分隔註解寫 `# ---- 004 US3-API-13`(`plan.md` § 待決問題 Q34)),執行確認它因為「已在執行環境上的比對照原樣,大小寫不同就重排一次」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、FR-018、使用者故事 3 驗收情境 5
- [X] T084b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/domain/model_name.py` 只寫讓 US3-API-13 通過的程式碼;已在執行環境上與已在佇列的比對改用 `src/cgb/domain/model_name.py` 的 `match_key`(依賴 T076b),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T084a)
  - 🧪 `testplan.md` § US3-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、FR-018、使用者故事 3 驗收情境 5
- [X] T085a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-14 的測試(`POST /api/session/restart` 帶 `L4`;`wait_until` 等新的工作階段就緒;`wait_auto` 等新的那一個 `done`;之後列出佇列;分隔註解寫 `# ---- 004 US3-API-14`(`plan.md` § 待決問題 Q34)),執行確認它因為「自動下載只比對執行環境上的模型、沒比對佇列,重新載入的 `qwen2.5:7b` 又以 `auto` 排一次」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、使用者故事 3 驗收情境 5、邊界情況
- [X] T085b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T085a)
  - 🧪 `testplan.md` § US3-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、使用者故事 3 驗收情境 5、邊界情況
- [X] T086a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-15 的測試(`open_ready`;`wait_auto` 等 `done`;之後列出佇列;分隔註解寫 `# ---- 004 US3-API-15`(`plan.md` § 待決問題 Q34)),執行確認它因為「遇到第一個放不下的就停,後面較小的 `qwen2.5:0.5b` 也沒排」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 6
- [X] T086b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T086a)
  - 🧪 `testplan.md` § US3-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 6
- [X] T087a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-16 的測試(`POST /api/session/restart` 帶 `L4`;`wait_auto` 等新的工作階段 `done`;分隔註解寫 `# ---- 004 US3-API-16`(`plan.md` § 待決問題 Q34)),執行確認它因為「空間判定沒加上佇列裡還沒下載完的大小(重新載入排入、下載中的 `qwen2.5:7b` 4,683,087,332),2,019,393,189 單獨看放得下就排入」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 6
- [X] T087b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T087a)
  - 🧪 `testplan.md` § US3-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 6
- [X] T088a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-17 的測試(`open_ready`;`wait_auto` 等 `done`;之後列出佇列;分隔註解寫 `# ---- 004 US3-API-17`(`plan.md` § 待決問題 Q34)),執行確認它因為「照手動加入下載的規則,一個取不到大小就整次不排」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 7、邊界情況
- [X] T088b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-17 通過的程式碼;若要把 `HF_AUTH_REQUIRED`、`HF_QUANT_UNAVAILABLE` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T088a)
  - 🧪 `testplan.md` § US3-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 7、邊界情況
- [X] T089a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-18 的測試(`open_ready`;`wait_auto` 等 `done`;分隔註解寫 `# ---- 004 US3-API-18`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒做顯示記憶體的判斷,20 GB 的模型被排入」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 9
- [X] T089b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-18 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T089a)
  - 🧪 `testplan.md` § US3-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 9
- [X] T090a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-19 的測試(`open_ready`;`wait_auto` 等 `done`;分隔註解寫 `# ---- 004 US3-API-19`(`plan.md` § 待決問題 Q34)),執行確認它因為「讀不到顯示記憶體時把總量當成 0 或拿 None 比較,全部跳過或丟 `TypeError`」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 9
- [X] T090b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-19 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T090a)
  - 🧪 `testplan.md` § US3-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 9
- [X] T091a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-20 的測試(`open_ready`;`wait_auto` 等 `done`;之後列出佇列;分隔註解寫 `# ---- 004 US3-API-20`(`plan.md` § 待決問題 Q34)),執行確認它因為「讀不到剩餘空間時當成夠用,兩項照常排入(001 不把讀不到當成夠用)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 11;`plan.md` § 待決問題 Q17
- [X] T091b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-20 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T091a)
  - 🧪 `testplan.md` § US3-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 11;`plan.md` § 待決問題 Q17
- [X] T092a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-21 的測試(`open_ready`;`wait_auto` 等 `done`;分隔註解寫 `# ---- 004 US3-API-21`(`plan.md` § 待決問題 Q34)),執行確認它因為「讀不到模型清單時整次不做(結果停在 `running` 或為 null),或全部標成跳過(違反 Q16)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011;`plan.md` § 待決問題 Q16
- [X] T092b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-21 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T092a)
  - 🧪 `testplan.md` § US3-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011;`plan.md` § 待決問題 Q16
- [X] T093a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-22 的測試(`open_ready`;`wait_auto` 等結果不是 null 且 `state` 為 `done`;分隔註解寫 `# ---- 004 US3-API-22`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒有要排的就不寫結果、回 null,和「根本沒設自動下載」分不出來(違反 Q18)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q18
- [X] T093b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-22 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T093a)
  - 🧪 `testplan.md` § US3-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q18
- [X] T094a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-23 的測試(各自 `open_ready` 後等 0.3 秒;讀自動下載結果;B 再 `PUT` 把 `qwen2.5:0.5b` 的 `autoDownload` 改成 true,之後觸發重連、等回到 `ready` 再等 0.3 秒;列出佇列並再讀一次結果;分隔註解寫 `# ---- 004 US3-API-23`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒有設自動下載的項目時照樣寫 `running` 再寫 `done`、推送提示」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`、`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-011、FR-012、SC-003、邊界情況;`plan.md` § 待決問題 Q24
- [X] T094b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-23 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T094a)
  - 🧪 `testplan.md` § US3-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`、`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-011、FR-012、SC-003、邊界情況;`plan.md` § 待決問題 Q24
- [X] T095a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-24 的測試(`open_ready`;等 0.2 秒;記下 `get_manifest.call_count`;放行 `gate`;`wait_auto` 等 `done`;分隔註解寫 `# ---- 004 US3-API-24`(`plan.md` § 待決問題 Q34)),執行確認它因為「取大小一個一個等(放行前只有 1 次)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011
- [X] T095b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-24 通過的程式碼;取大小同時最多 4 個(`asyncio.Semaphore(4)`),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T095a)
  - 🧪 `testplan.md` § US3-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011
- [X] T096a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-25 的測試(`open_ready`;等 `gate.entered` 為 1;讀自動下載結果;放行 `gate`;等到 `state` 為 `done` 的 `autoDownload.updated`;分隔註解寫 `# ---- 004 US3-API-25`(`plan.md` § 待決問題 Q34)),執行確認它因為「判定完才寫結果、只推一次 `done`,判定中 UI 讀到 null(Q33 要顯示判定中)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendAutoDownloadUpdated`、`operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-011、FR-012;`plan.md` § 待決問題 Q33
- [X] T096b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-25 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T096a)
  - 🧪 `testplan.md` § US3-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendAutoDownloadUpdated`、`operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-011、FR-012;`plan.md` § 待決問題 Q33
- [X] T097a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-26 的測試(各自開一條 `GET /api/events`,讀到 `autoDownload.updated` 為止;分隔註解寫 `# ---- 004 US3-API-26`(`plan.md` § 待決問題 Q34)),執行確認它因為「連上時的快照沒加 `autoDownload.updated`,就緒後才打開模型頁的 UI 收不到提示(提示區在模型頁,`plan.md` § 待決問題 Q29)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-26
  - ⚙ `contracts/ui-events.asyncapi.yaml` § `operations.sendAutoDownloadUpdated`
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 10、SC-003
- [X] T097b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/events.py`、`src/cgb/services/auto_download.py` 只寫讓 US3-API-26 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T097a)
  - 🧪 `testplan.md` § US3-API-26
  - ⚙ `contracts/ui-events.asyncapi.yaml` § `operations.sendAutoDownloadUpdated`
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 10、SC-003
- [X] T098a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_auto_download.py` 寫 US3-API-27 的測試(觸發重連,等回到 `ready` 再等 0.3 秒;之後列出佇列並讀結果;分隔註解寫 `# ---- 004 US3-API-27`(`plan.md` § 待決問題 Q34));T013b 只在工作階段第一次就緒時排入(寫進 `auto_download_results` 的那一列就是「做過了」),這個案例可能已被滿足:先執行確認通過,再暫時放入「自動下載掛在 `ready_listeners` 上卻沒查這個工作階段做過沒有,重連接回又跑一次」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、使用者故事 3 驗收情境 8、SC-003
- [X] T098b [US3] 🟢 /tdd 綠燈:US3-API-27 由 T013b 以 `auto_download_results` 這個工作階段有沒有結果列判斷是不是第一次就緒(research.md R6)滿足,確認 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-27 通過的程式碼;看到要整理的地方記進重構清單(依賴 T098a)
  - 🧪 `testplan.md` § US3-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、使用者故事 3 驗收情境 8、SC-003
- [X] T099a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_auto_download.py` 寫 US3-API-28 的測試(以同一個 SQLite 檔 `running(make_app())`,等接回同一個工作階段就緒再等 0.3 秒;讀結果、列出佇列;分隔註解寫 `# ---- 004 US3-API-28`(`plan.md` § 待決問題 Q34));T098b 以 `auto_download_results` 判斷是不是第一次就緒(存在資料庫,research.md R6)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「「做過沒有」只記在記憶體,後端重新啟動接回時又排一次」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-API-28
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、FR-012、邊界情況、SC-003
- [X] T099b [US3] 🟢 /tdd 綠燈:US3-API-28 由 T098b 以 `auto_download_results` 判斷是不是第一次就緒(存在資料庫,research.md R6) 滿足,確認 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-28 通過的程式碼(依賴 T099a)
  - 🧪 `testplan.md` § US3-API-28
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、FR-012、邊界情況、SC-003
- [X] T100a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-29 的測試(送 `POST /api/downloads/auto-result/dismiss`;再讀結果;再送一次關閉;之後列出佇列;分隔註解寫 `# ---- 004 US3-API-29`(`plan.md` § 待決問題 Q34)),執行確認它因為「關閉做成刪除結果,之後讀到 null、`enqueued` 也不見了」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-29
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result/dismiss.post`、`components.schemas.AutoDownloadResult`、`components.schemas.Error`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-auto-download`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-012
- [X] T100b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-29 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T100a)
  - 🧪 `testplan.md` § US3-API-29
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result/dismiss.post`、`components.schemas.AutoDownloadResult`、`components.schemas.Error`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-auto-download`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-012
- [X] T101a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-30 的測試(`open_ready`;等 `gate.entered` 為 1;送關閉;放行 `gate`;`wait_auto` 等 `done`;分隔註解寫 `# ---- 004 US3-API-30`(`plan.md` § 待決問題 Q34)),執行確認它因為「判定完成時整列覆寫,把 `dismissed` 寫回 false」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-30
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result/dismiss.post`、`components.schemas.AutoDownloadResult`、`components.schemas.Error`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-auto-download`)
  - 📎 `spec.md` § FR-012
- [X] T101b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-30 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T101a)
  - 🧪 `testplan.md` § US3-API-30
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result/dismiss.post`、`components.schemas.AutoDownloadResult`、`components.schemas.Error`、`paths./downloads/auto-result.get`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-auto-download`)
  - 📎 `spec.md` § FR-012
- [X] T102a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-31 的測試(情況 A:沒有工作階段時送關閉;B:精選清單只有一項沒設自動下載,`open_ready` 後送關閉;C:新增一項設自動下載,`open_ready`、`wait_auto` 等 `done` 後 `DELETE /api/session`、等 `ended`,再送關閉;分隔註解寫 `# ---- 004 US3-API-31`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒有結果時對 None 取值丟例外、回 500」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-31
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result/dismiss.post`、`components.schemas.AutoDownloadResult`、`components.schemas.Error`
  - 📎 `spec.md` § FR-012、NFR-006
- [X] T102b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/repos/auto_download.py`、`src/cgb/domain/errors.py` 只寫讓 US3-API-31 通過的程式碼;新代碼 `AUTO_DOWNLOAD_RESULT_NOT_FOUND` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T102a)
  - 🧪 `testplan.md` § US3-API-31
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result/dismiss.post`、`components.schemas.AutoDownloadResult`、`components.schemas.Error`
  - 📎 `spec.md` § FR-012、NFR-006
- [X] T103a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_auto_download.py` 寫 US3-API-32 的測試(送 `DELETE /api/session`,等 `state` 為 `ended`;讀結果;分隔註解寫 `# ---- 004 US3-API-32`(`plan.md` § 待決問題 Q34));T013b 在工作階段結束時刪結果並推 `autoDownload.updated`(`result` 為 null)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「工作階段結束時只清了佇列、沒清結果,下一個工作階段開好前提示區還留著上一台的內容」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-API-32
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendAutoDownloadUpdated`
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 10
- [X] T103b [US3] 🟢 /tdd 綠燈:US3-API-32 由 T013b 在工作階段結束時刪結果並推 `autoDownload.updated`(`result` 為 null) 滿足,確認 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-32 通過的程式碼(依賴 T103a)
  - 🧪 `testplan.md` § US3-API-32
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`);`contracts/ui-events.asyncapi.yaml` § `operations.sendAutoDownloadUpdated`
  - 📎 `spec.md` § FR-012、使用者故事 3 驗收情境 10
- [X] T104a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_auto_download.py` 寫 US3-API-33 的測試(A:送開啟,`state` 為 `opening` 時送 `DELETE /api/session`,放行閘門,等 `ended`;B:送開啟,等 `open_failed`;兩者再等 0.3 秒後讀結果、列出佇列;分隔註解寫 `# ---- 004 US3-API-33`(`plan.md` § 待決問題 Q34));T083b 只掛在 `SessionLifecycle.ready_listeners`已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「自動下載掛在開啟的開頭(而不是就緒時),開啟中結束或開啟失敗也排入」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-API-33
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、邊界情況
- [X] T104b [US3] 🟢 /tdd 綠燈:US3-API-33 由 T083b 只掛在 `SessionLifecycle.ready_listeners` 滿足,確認 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-33 通過的程式碼(依賴 T104a)
  - 🧪 `testplan.md` § US3-API-33
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § FR-011、邊界情況
- [X] T105a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_auto_download.py` 寫 US3-API-34 的測試(`DELETE /api/curated/{a}`;`PUT /api/curated/{b}` 帶 `{"name":"qwen2.5:0.5b","autoDownload":false}`;放行 `hold`;`wait_queue` 等兩筆都 `completed`;分隔註解寫 `# ---- 004 US3-API-34`(`plan.md` § 待決問題 Q34));既有的佇列與精選清單互不相連(`src/cgb/repos/curated.py` 刪除時不碰 `download_jobs`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「刪除或取消自動下載時順手取消佇列裡 `origin` 為 `auto` 的同名項目」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-API-34
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.delete`、`components.schemas.Error`、`paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-009、FR-010、邊界情況
- [X] T105b [US3] 🟢 /tdd 綠燈:US3-API-34 由 既有的佇列與精選清單互不相連(`src/cgb/repos/curated.py` 刪除時不碰 `download_jobs`) 滿足,確認 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-34 通過的程式碼(依賴 T105a)
  - 🧪 `testplan.md` § US3-API-34
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.delete`、`components.schemas.Error`、`paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-009、FR-010、邊界情況
- [X] T106a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_auto_download.py` 寫 US3-API-35 的測試(以同一個 SQLite 檔建第二個 app(`running(make_app())`),列出精選清單;再 `open_ready`、`wait_auto` 等 `done`,列出佇列;分隔註解寫 `# ---- 004 US3-API-35`(`plan.md` § 待決問題 Q34));T072b 把 `autoDownload`、`recommendedRuntimeType` 寫進 `curated_models`已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`autoDownload` 或 `recommendedRuntimeType` 只放在 app 的記憶體(例如 `app.state` 的 dict),寫入資料庫的只有名稱與說明」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-API-35
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § NFR-004、FR-010
- [X] T106b [US3] 🟢 /tdd 綠燈:US3-API-35 由 T072b 把 `autoDownload`、`recommendedRuntimeType` 寫進 `curated_models` 滿足,確認 `src/cgb/repos/curated.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/repos/curated.py` 只寫讓 US3-API-35 通過的程式碼(依賴 T106a)
  - 🧪 `testplan.md` § US3-API-35
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § NFR-004、FR-010
- [X] T107a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_auto_download.py` 寫 US3-API-36 的測試(另新增第 9 個 `gemma2:2b` 設自動下載、執行環境上已有,則4 斷言它不在 `enqueued` 也不在 `skipped`(SC-003 的分母,D81);`open_ready` 回來時記下時間;`wait_auto` 等 `done`;分隔註解寫 `# ---- 004 US3-API-36`(`plan.md` § 待決問題 Q34));T095b 同時最多 4 個的取大小已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「取大小一個一個等,8 × 0.1 秒 = 0.8 秒超過界線」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-API-36
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § SC-003、FR-011、FR-012、使用者故事 3 驗收情境 5;`plan.md` § 待決問題 Q38
- [X] T107b [US3] 🟢 /tdd 綠燈:US3-API-36 由 T095b 同時最多 4 個的取大小 滿足,確認 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-36 通過的程式碼(依賴 T107a)
  - 🧪 `testplan.md` § US3-API-36
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § SC-003、FR-011、FR-012、使用者故事 3 驗收情境 5;`plan.md` § 待決問題 Q38
- [X] T108a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-37 的測試(`open_ready`;`wait_auto` 等 `done`;讀結果、列出精選清單、列出佇列、讀 `GET /api/session`;分隔註解寫 `# ---- 004 US3-API-37`(`plan.md` § 待決問題 Q34)),執行確認它因為「自動下載在 ready listener 裡讓例外往上拋,`_notify_ready` 中斷、後面的 `resume` 沒跑,或工作階段被標成失敗」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-37
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./curated.get`、`components.schemas.CuratedList`、`components.schemas.CuratedModel`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § NFR-006、SC-006、FR-012
- [X] T108b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py` 只寫讓 US3-API-37 通過的程式碼;若要把 `HF_UNREACHABLE` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T108a)
  - 🧪 `testplan.md` § US3-API-37
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`、`paths./curated.get`、`components.schemas.CuratedList`、`components.schemas.CuratedModel`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-queue-clearing`、`info.x-auto-download`)
  - 📎 `spec.md` § NFR-006、SC-006、FR-012
- [X] T246a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-38 的測試(依序送 A~D 四個 `PUT`,之後列出;分隔註解寫 `# ---- 004 US3-API-38`(`plan.md` § 待決問題 Q34)),執行確認它因為「先查 `id` 再驗本文,A、B 回 404」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-38
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、NFR-006;`plan.md` § 待決問題 Q53
- [X] T246b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py` 只寫讓 US3-API-38 通過的程式碼;檢查依序:請求本文(400)→ `id` 不存在(404 `CURATED_NOT_FOUND`)→ 名稱重複(409 `CURATED_DUPLICATE`)(`contracts/ui.openapi.yaml` § `paths./curated/{id}.put`,`plan.md` § 待決問題 Q53),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T246a)
  - 🧪 `testplan.md` § US3-API-38
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated/{id}.put`、`components.schemas.CuratedModelInput`、`components.schemas.CuratedModel`、`components.schemas.Error`、`paths./curated.get`、`components.schemas.CuratedList`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-009、NFR-006;`plan.md` § 待決問題 Q53
- [X] T247a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auto_download.py` 寫 US3-API-39 的測試(情況 A 在重新啟動前、後各讀一次 `GET /api/downloads/auto-result`;情況 B `open_ready`,`wait_auto` 等 `done`;分隔註解寫 `# ---- 004 US3-API-39`(`plan.md` § 待決問題 Q34)),執行確認它因為「跳過的項目沒有 `sizeBytes`、`freeDiskBytes`、`vramBytes`,或 `freeDiskBytes` 填剩餘磁碟的原值」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-39
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-auto-download`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q68
- [X] T247b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/auto_download.py`、`src/cgb/repos/auto_download.py`、`src/cgb/api/downloads.py` 只寫讓 US3-API-39 通過的程式碼;跳過的項目照 `AutoDownloadSkipped` 帶 `sizeBytes`、`freeDiskBytes`、`vramBytes`(依原因有值或為 null),寫進 `auto_download_items` 的 `size_bytes`、`free_disk_bytes`、`vram_bytes`(`plan.md` § 待決問題 Q68),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T247a)
  - 🧪 `testplan.md` § US3-API-39
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`、`components.schemas.AutoDownloadNotice`、`components.schemas.AutoDownloadResult`、`components.schemas.AutoDownloadSkipped`(`info.x-auto-download`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q68
- [X] T109 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T072b~T108b、T246b~T247b 記下的重構清單(範圍限 `src/cgb/api/`、`src/cgb/services/`、`src/cgb/repos/`、`src/cgb/domain/model_name.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T247b)
  - 🧪 `testplan.md` § US3-API-01~US3-API-37、US3-API-38~US3-API-39
  - 📎 `testplan.md` § 4.1

### E4 資料庫(SQLite)

> 只管 `curated_models.auto_download`、`uq_curated_models_name_ci`、`auto_download_results`、`auto_download_items`;遷移的交易、`user_version`、冪等與新舊庫的分辨由故事 1 的 E4 節做過。`foreign_keys` 不開,repos 在交易內自己刪(`plan.md` § 待決問題 Q27);`auto_download_results.target_count` 的 `CHECK (target_count >= 0)` 照 `plan.md` § 待決問題 Q41;精選名稱只差大小寫的舊資料在同一個交易裡留 id 最小的那筆、刪掉的名稱寫進日誌(`plan.md` § 待決問題 Q40)。全新庫的這幾樣 DDL 已由故事 1 的 T017b 照 `contracts/store.dbml` 建好(`plan.md` § 待決問題 Q64),本節只測全新庫的案例是對照組(T110a、T118a、T119a、T248a)

- [X] T110a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-01 的測試(`create_schema(conn)` 後讀 `PRAGMA table_info`、`PRAGMA index_list(curated_models)`;分隔註解寫 `# ---- 004 US3-DB-01`(`plan.md` § 待決問題 Q34));T017b 照 `contracts/store.dbml` 寫出的全新庫 DDL 已做到這段程式(`plan.md` § 待決問題 Q64),這個案例會被滿足:先執行確認通過,再暫時放入「只在遷移那一條路徑加 `auto_download`,全新庫的 `_CURATED_MODELS` DDL 沒有改」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-DB-01
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`
  - 📎 `spec.md` § FR-010、FR-011、FR-012
- [X] T110b [US3] 🟢 /tdd 綠燈:US3-DB-01 由 T017b 照 `contracts/store.dbml` 寫出的全新庫 DDL 滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-01 通過的程式碼(依賴 T110a)
  - 🧪 `testplan.md` § US3-DB-01
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`
  - 📎 `spec.md` § FR-010、FR-011、FR-012
- [X] T111a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US3-DB-02 的測試(`create_schema(conn)`,再讀 `SELECT id, name, description, recommended_runtime_type_gpu, recommended_runtime_type_high_mem, auto_download FROM curated_models ORDER BY id`,接著 `INSERT INTO curated_models (name) VALUES ('mistral:7b')`;分隔註解寫 `# ---- 004 US3-DB-02`(`plan.md` § 待決問題 Q34)),執行確認它因為「為了加 CHECK 把 `curated_models` 照 `download_jobs` 的做法重建,建新表時沒帶 `AUTOINCREMENT` 或沒保留 `sqlite_sequence`,刪過的 id 4 被新項目重用(UI 還開著的舊頁面改 id 4 會改到別筆)」這類實作而失敗
  - 🧪 `testplan.md` § US3-DB-02
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-010、FR-009、假設、SC-005
- [X] T111b [US3] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US3-DB-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T111a)
  - 🧪 `testplan.md` § US3-DB-02
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-010、FR-009、假設、SC-005
- [X] T112a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US3-DB-03 的測試(兩個庫各跑 `create_schema(conn)`,再各讀 `PRAGMA table_info(auto_download_results)`、`PRAGMA table_info(auto_download_items)`、`PRAGMA index_list(curated_models)`,以及 `table_info(curated_models)` 裡 `auto_download` 那一列;分隔註解寫 `# ---- 004 US3-DB-03`(`plan.md` § 待決問題 Q34)),執行確認它因為「遷移步驟 3 另寫一份新表的 DDL,和全新庫那份不一樣(例如少了 `target_count`、主鍵只設 `session_name`)」這類實作而失敗
  - 🧪 `testplan.md` § US3-DB-03
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-010、FR-011、FR-012、FR-018
- [X] T112b [US3] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US3-DB-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T112a)
  - 🧪 `testplan.md` § US3-DB-03
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-010、FR-011、FR-012、FR-018
- [X] T113a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US3-DB-04 的測試(`create_schema(conn)`;分隔註解寫 `# ---- 004 US3-DB-04`(`plan.md` § 待決問題 Q34)),執行確認它因為「遷移沒照 R7 先查 `PRAGMA table_info`,直接 `ALTER TABLE ADD COLUMN`,丟 `OperationalError: duplicate column name`,整個遷移 rollback,每次啟動都失敗」這類實作而失敗
  - 🧪 `testplan.md` § US3-DB-04
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-010、NFR-004
- [X] T113b [US3] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US3-DB-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T113a)
  - 🧪 `testplan.md` § US3-DB-04
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-010、NFR-004
- [X] T114a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US3-DB-05 的測試(在 `caplog` 底下呼叫 `create_schema(conn)`,再讀 `SELECT id, name FROM curated_models ORDER BY id`;分隔註解寫 `# ---- 004 US3-DB-05`(`plan.md` § 待決問題 Q34)),執行確認它因為「照 store.dbml 的假設(「001 的名稱只收小寫,既有資料不會撞到」)直接建 `lower(name)` 唯一索引,丟 `IntegrityError` 讓整個遷移 rollback,`user_version` 停在 0,之後每次啟動都失敗,後端起不來」這類實作而失敗
  - 🧪 `testplan.md` § US3-DB-05
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-018、NFR-004、使用者故事 3 驗收情境 3
- [X] T114b [US3] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US3-DB-05 通過的程式碼;遷移第 1 步建 `uq_curated_models_name_ci` 之前,在同一個交易裡依 `lower(name)` 分組、每組留 `id` 最小的那一筆,刪掉的每一筆名稱以 WARNING 寫進日誌(`contracts/store.dbml` § `Project colab_gpu_bridge`;`plan.md` § 待決問題 Q40),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T114a)
  - 🧪 `testplan.md` § US3-DB-05
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-018、NFR-004、使用者故事 3 驗收情境 3
- [X] T115a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US3-DB-06 的測試(`create_schema(conn)`;接著 `conn.set_authorizer(None)` 後再跑一次 `create_schema(conn)`;分隔註解寫 `# ---- 004 US3-DB-06`(`plan.md` § 待決問題 Q34)),執行確認它因為「遷移沒有包在一個交易裡(`connect()` 是 `isolation_level=None` 的自動 commit,沒有明寫 `BEGIN` 的話每一句都各自落檔),失敗後 `auto_download` 欄與新表已經留下,下次啟動 `ADD COLUMN` 撞到重複欄位」這類實作而失敗
  - 🧪 `testplan.md` § US3-DB-06
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-010、NFR-004
- [X] T115b [US3] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US3-DB-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T115a)
  - 🧪 `testplan.md` § US3-DB-06
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-010、NFR-004
- [X] T116a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US3-DB-07 的測試(每種情況依序執行:`INSERT INTO curated_models (name) VALUES ('a:latest')`;`INSERT ... (name, auto_download) VALUES ('b:latest', 1)`;`INSERT ... VALUES ('c:latest', 2)`;`INSERT ... VALUES ('d:latest', -1)`;`INSERT ... VALUES ('e:latest', 'true')`;`INSERT ... VALUES ('f:latest', NULL)`;`UPDATE curated_models SET auto_download = 2 WHERE name = 'b:latest'`;分隔註解寫 `# ---- 004 US3-DB-07`(`plan.md` § 待決問題 Q34)),執行確認它因為「全新庫的 DDL 寫成 `auto_download INTEGER DEFAULT 0`,沒有 CHECK 與 NOT NULL,UI 傳來的 `true` 字串或 NULL 原樣存進去,自動下載判定 `== 1` 比不到」這類實作而失敗
  - 🧪 `testplan.md` § US3-DB-07
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-010、假設
- [X] T116b [US3] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US3-DB-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T116a)
  - 🧪 `testplan.md` § US3-DB-07
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-010、假設
- [X] T117a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US3-DB-08 的測試(每種情況依序執行:`INSERT ... (name) VALUES ('Qwen2.5:7B')`;`INSERT ... VALUES ('hf.co/Bartowski/smollm2-135m-instruct-gguf:q4_k_m')`;`INSERT ... VALUES ('qwen2.5:latest')`;`UPDATE curated_models SET name = 'LLAMA3.2:3b' WHERE id = 3`;`UPDATE curated_models SET name = 'QWEN2.5:7b' WHERE id = 3`;分隔註解寫 `# ---- 004 US3-DB-08`(`plan.md` § 待決問題 Q34)),執行確認它因為「不分大小寫的唯一性只靠 001 欄位層級的 `UNIQUE`(照原樣比對),`Qwen2.5:7B` 寫進第二筆,同時送出的兩個新增都成功(D39 要用索引擋並發)」這類實作而失敗
  - 🧪 `testplan.md` § US3-DB-08
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-018、使用者故事 3 驗收情境 3
- [X] T117b [US3] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US3-DB-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T117a)
  - 🧪 `testplan.md` § US3-DB-08
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-018、使用者故事 3 驗收情境 3
- [X] T118a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-09 的測試(依序執行:①`INSERT INTO auto_download_results (session_name, target_count) VALUES ('cgb-a', 2)`;②再一次同樣的 ①;③`INSERT ... (session_name, target_count) VALUES ('cgb-zero', 0)`;④`INSERT ... VALUES ('cgb-neg', -1)`;⑤`INSERT ... (session_name) VALUES ('cgb-null')`;⑥`INSERT ... (session_name, target_count, state) VALUES ('cgb-s', 1, 'pending')`;⑦`INSERT ... (session_name, target_count, dismissed) VALUES ('cgb-d', 1, 2)`;⑧`UPDATE auto_download_results SET state = 'done', finished_at = '2026-11-14T08:00:30Z', dismissed = 1 WHERE session_name = 'cgb-a'`;分隔註解寫 `# ---- 004 US3-DB-09`(`plan.md` § 待決問題 Q34));T017b 照 `contracts/store.dbml` 寫出的全新庫 DDL 已做到這段程式(`plan.md` § 待決問題 Q64),這個案例會被滿足:先執行確認通過,再暫時放入「`session_name` 不是主鍵而是另設 `id` 自動遞增,重連接回時再寫一列也成功」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-DB-09
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-011、FR-012、邊界情況
- [X] T118b [US3] 🟢 /tdd 綠燈:US3-DB-09 由 T017b 照 `contracts/store.dbml` 寫出的全新庫 DDL 滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-09 通過的程式碼(依賴 T118a)
  - 🧪 `testplan.md` § US3-DB-09
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-011、FR-012、邊界情況
- [X] T119a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-10 的測試(依序執行 `INSERT INTO auto_download_items (session_name, position, model, reason, reason_code, message)`:①`('cgb-a', 0, 'qwen2.5:7b', NULL, NULL, NULL)`;②`('cgb-a', 1, 'qwen2.5:32b', 'DISK_SPACE_INSUFFICIENT', NULL, '剩餘空間不足')`;③`('cgb-a', 2, 'hf.co/x/y:Q4_K_M', 'SIZE_UNAVAILABLE', 'HF_TIMEOUT', '取不到大小')`;④`('cgb-a', 3, 'llama3.1:70b', 'MAY_NOT_FIT', NULL, '這台可能無法載入')`;⑤`('cgb-b', 0, 'qwen2.5:7b', 'DISK_SPACE_UNKNOWN', 'COLAB_EXEC_FAILED', '讀不到剩餘空間')`;⑥`('cgb-a', 4, 'gemma2:2b', 'DISK_FULL', NULL, '空間不足')`;⑦`('cgb-a', 4, 'gemma2:2b', 'disk_space_insufficient', NULL, '空間不足')`;⑧`('cgb-a', 1, 'phi3:mini', NULL, NULL, NULL)`;⑨`('cgb-a', NULL, 'phi3:mini', NULL, NULL, NULL)`;⑩`('cgb-a', 5, NULL, NULL, NULL, NULL)`;分隔註解寫 `# ---- 004 US3-DB-10`(`plan.md` § 待決問題 Q34));T017b 照 `contracts/store.dbml` 寫出的全新庫 DDL 已做到這段程式(`plan.md` § 待決問題 Q64),這個案例會被滿足:先執行確認通過,再暫時放入「`reason` 的 CHECK 照 R6 草稿只列三種原因,漏了 Q17 加的 `DISK_SPACE_UNKNOWN`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-DB-10
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-012、FR-011;`plan.md` § 待決問題 Q17
- [X] T119b [US3] 🟢 /tdd 綠燈:US3-DB-10 由 T017b 照 `contracts/store.dbml` 寫出的全新庫 DDL 滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-10 通過的程式碼(依賴 T119a)
  - 🧪 `testplan.md` § US3-DB-10
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-012、FR-011;`plan.md` § 待決問題 Q17
- [X] T120a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US3-DB-11 的測試(每種情況讀 `PRAGMA foreign_keys`、`PRAGMA foreign_key_list(auto_download_items)`、`PRAGMA foreign_key_list(auto_download_results)`,再寫入 `sessions` 的 `cgb-a`、`auto_download_results` 的 `cgb-a`、`auto_download_items` 的 `('cgb-a', 0, 'qwen2.5:7b')`,執行 `DELETE FROM auto_download_results WHERE session_name = 'cgb-a'`;分隔註解寫 `# ---- 004 US3-DB-11`(`plan.md` § 待決問題 Q34)),執行確認它因為「為了讓 cascade 生效在 `connect()` 開 `PRAGMA foreign_keys=ON`,連帶改到 001 `session_transitions` 的刪除行為(D41 選 A,不開外鍵)」這類實作而失敗
  - 🧪 `testplan.md` § US3-DB-11
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-011、FR-012
- [X] T120b [US3] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US3-DB-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T120a)
  - 🧪 `testplan.md` § US3-DB-11
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § FR-011、FR-012
- [X] T121a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-12 的測試(`conn.close()`,以新的 `connect(db_path)` 開同一個檔並再跑一次 `create_schema(conn)`(模擬後端重新啟動);分隔註解寫 `# ---- 004 US3-DB-12`(`plan.md` § 待決問題 Q34));T022b 先看 `user_version`,`user_version` 為 1 時不做任何遷移已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「分辨新舊庫時只看 `user_version` 是不是 0、沒看有沒有 `sessions` 之外,把「已有 `auto_download_results`」也當成要重建的條件,每次啟動 `DROP TABLE IF EXISTS` 新表,後端重啟後自動下載會重排、提示區消失(驗收情境 8、10)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-DB-12
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § NFR-004、FR-010、FR-011
- [X] T121b [US3] 🟢 /tdd 綠燈:US3-DB-12 由 T022b 先看 `user_version`,`user_version` 為 1 時不做任何遷移 滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-12 通過的程式碼(依賴 T121a)
  - 🧪 `testplan.md` § US3-DB-12
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`、`Table auto_download_results`、`Table auto_download_items`、`Table sessions`(`Enum download_origin`、`Enum auto_download_state`、`Enum auto_download_skip_reason`、`Ref: download_jobs.session_name > sessions.name`、`Ref: auto_download_items.session_name > auto_download_results.session_name`)
  - 📎 `spec.md` § NFR-004、FR-010、FR-011
- [X] T248a [US3] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_db_schema.py` 寫 US3-DB-13 的測試(每種情況讀 `PRAGMA table_info(auto_download_items)`,再依序寫入 ①、②;分隔註解寫 `# ---- 004 US3-DB-13`(`plan.md` § 待決問題 Q34));T017b 照 `contracts/store.dbml` 寫出的全新庫 DDL 與 T112b 讓遷移步驟 3 用同一份 DDL 已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「三欄設成 `NOT NULL` 或給預設 0,排入的項目寫不進去」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US3-DB-13
  - ⚙ `contracts/store.dbml` § `Table auto_download_items`、`Table auto_download_results`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q68
- [X] T248b [US3] 🟢 /tdd 綠燈:US3-DB-13 由 T017b 照 `contracts/store.dbml` 寫出的全新庫 DDL 與 T112b 讓遷移步驟 3 用同一份 DDL 滿足,確認 `src/cgb/db/schema.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/db/schema.py` 只寫讓 US3-DB-13 通過的程式碼(依賴 T248a)
  - 🧪 `testplan.md` § US3-DB-13
  - ⚙ `contracts/store.dbml` § `Table auto_download_items`、`Table auto_download_results`(`Project colab_gpu_bridge`)
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q68
- [X] T122 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T110b~T121b、T248b 記下的重構清單(範圍限 `src/cgb/db/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_db_schema.py` 的斷言(依賴 T248b)
  - 🧪 `testplan.md` § US3-DB-01~US3-DB-12、US3-DB-13
  - 📎 `testplan.md` § 4.2

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(Playwright)接測試行程內真的後端(`tests/e2e/conftest.py` 的 `e2e_servers`,UI 127.0.0.1:8781),轉接層用替身;e2e 用固定 port,同一時間只跑一份
> 精選清單存在真的 SQLite,工作階段、剩餘磁碟、顯示記憶體與取大小用替身(`testplan.md` § 4.3)

- [X] T123a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us3_curated.py` 寫 US3-AJ-01 的測試(按「新增」,名稱 `hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M`、說明「小模型試對話」、建議類型 L4、勾「開好就自動下載」,送出;再重新整理頁面;分隔註解寫 `# ---- 004 US3-AJ-01`(`plan.md` § 待決問題 Q34));`e2e_servers` 要能注入 `FakeHuggingFaceHub`(`tests/e2e/conftest.py`,用 `Fakes.as_kwargs()` 已帶進的 `huggingface`),執行確認它因為「精選清單編輯要求有工作階段(送出被擋)」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-01
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-009、FR-010
- [X] T123b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js`、`src/cgb/static/js/api.js`、`src/cgb/static/style.css` 只寫讓 US3-AJ-01 通過的程式碼;精選清單的新增、修改、刪除與自動下載開關照 `prototype/library.html`;把 `prototype/style.css` 的「004:精選清單的自動下載開關」區段搬進 `src/cgb/static/style.css`,只用既有的 `var(--…)`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T123a)
  - 🧪 `testplan.md` § US3-AJ-01
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-009、FR-010
- [X] T124a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us3_curated.py` 寫 US3-AJ-02 的測試(把 `qwen2.5` 的說明改成「改過」;再按 `llama3.2:3b` 的「刪除」,在確認視窗按「取消」;再按一次「刪除」並在確認視窗按「刪除」;分隔註解寫 `# ---- 004 US3-AJ-02`(`plan.md` § 待決問題 Q34)),執行確認它因為「修改實作成刪掉再新增,項目跑到最後」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-02
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-009
- [X] T124b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/js/library.js` 只寫讓 US3-AJ-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T124a)
  - 🧪 `testplan.md` § US3-AJ-02
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-009
- [X] T125a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us3_curated.py` 寫 US3-AJ-03 的測試(情況 A 新增名稱 `qwen2.5:Latest`(合法的名稱,只有版本的大小寫不同);情況 B 新增名稱 `hf.co/只有作者`;分隔註解寫 `# ---- 004 US3-AJ-03`(`plan.md` § 待決問題 Q34)),執行確認它因為「重複比對沒補 `latest` 或分大小寫,A 被加成第二筆」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-03
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-009、FR-018、邊界情況
- [X] T125b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/js/library.js` 只寫讓 US3-AJ-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T125a)
  - 🧪 `testplan.md` § US3-AJ-03
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-009、FR-018、邊界情況
- [X] T126a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us3_curated.py` 寫 US3-AJ-04 的測試(開啟工作階段到就緒,打開模型頁;再重新整理一次;分隔註解寫 `# ---- 004 US3-AJ-04`(`plan.md` § 待決問題 Q34)),執行確認它因為「提示只在收到 `autoDownload.updated` 時畫,重新整理後沒有去讀 `GET /api/downloads/auto-result`」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-04
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-011、FR-012、SC-003
- [X] T126b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/models.html`、`src/cgb/static/js/models.js`、`src/cgb/static/js/api.js`、`src/cgb/static/style.css` 只寫讓 US3-AJ-04 通過的程式碼;模型頁佇列上方的自動下載提示區照 `prototype/models.html` 的 `#auto-notice`,打開頁面時讀 `GET /api/downloads/auto-result`、之後跟著 `autoDownload.updated` 更新;把 `prototype/style.css` 的「004:自動下載提示區」區段搬進 `src/cgb/static/style.css`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T126a)
  - 🧪 `testplan.md` § US3-AJ-04
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-011、FR-012、SC-003
- [X] T127a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us3_curated.py` 寫 US3-AJ-05 的測試(按 `#auto-notice` 的「關閉」;再重新整理;分隔註解寫 `# ---- 004 US3-AJ-05`(`plan.md` § 待決問題 Q34)),執行確認它因為「關閉只藏在前端、沒有送 `POST /api/downloads/auto-result/dismiss`,重新整理又出現」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-05
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-012
- [X] T127b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/js/models.js`、`src/cgb/static/js/api.js` 只寫讓 US3-AJ-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T127a)
  - 🧪 `testplan.md` § US3-AJ-05
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-012
- [X] T128a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us3_curated.py` 寫 US3-AJ-06 的測試(開啟工作階段到就緒時已打開模型頁;分隔註解寫 `# ---- 004 US3-AJ-06`(`plan.md` § 待決問題 Q34)),執行確認它因為「前端只認 `state` 為 `done` 的結果,判定中什麼都不顯示(`plan.md` Q33 決定顯示)」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-06
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q33
- [X] T128b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/js/models.js` 只寫讓 US3-AJ-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T128a)
  - 🧪 `testplan.md` § US3-AJ-06
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q33
- [X] T129a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us3_curated.py` 寫 US3-AJ-07 的測試(開啟工作階段到就緒,打開模型頁;分隔註解寫 `# ---- 004 US3-AJ-07`(`plan.md` § 待決問題 Q34)),執行確認它因為「排入與跳過都是空的時仍顯示「排入 0 個」的提示(`plan.md` Q30 決定不顯示)」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-07
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-011、FR-012;`plan.md` § 待決問題 Q30
- [X] T129b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/js/models.js` 只寫讓 US3-AJ-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T129a)
  - 🧪 `testplan.md` § US3-AJ-07
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-011、FR-012;`plan.md` § 待決問題 Q30
- [X] T130a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us3_curated.py` 寫 US3-AJ-08 的測試(自動下載提示分兩個工作階段鋪:第一個讀得到剩餘磁碟,結束後第二個讓 `probe_resources` 丟 `COLAB_UNREACHABLE`(`plan.md` § 待決問題 Q70);每種狀態取那個區塊的 `innerText`,去掉模型名稱;分隔註解寫 `# ---- 004 US3-AJ-08`(`plan.md` § 待決問題 Q34)),執行確認它因為「新的表單與提示用英文」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-08
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`;`prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § NFR-007、FR-012;`plan.md` § 待決問題 Q70
- [X] T130b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/js/library.js`、`src/cgb/static/js/models.js` 只寫讓 US3-AJ-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T130a)
  - 🧪 `testplan.md` § US3-AJ-08
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`;`prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § NFR-007、FR-012;`plan.md` § 待決問題 Q70
- [X] T249a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us3_curated.py` 寫 US3-AJ-09 的測試(開啟工作階段到就緒,打開模型頁;分隔註解寫 `# ---- 004 US3-AJ-09`(`plan.md` § 待決問題 Q34)),執行確認它因為「前端照舊原型從 `detail` 文字讀數字,數字一律不顯示」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-09
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q68
- [X] T249b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/js/models.js` 只寫讓 US3-AJ-09 通過的程式碼;跳過的項目照 `prototype/models.html` 的 `skipFigures` 顯示 `sizeBytes`、`freeDiskBytes`、`vramBytes`,沒有值的不顯示(`plan.md` § 待決問題 Q68),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T249a)
  - 🧪 `testplan.md` § US3-AJ-09
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q68
- [X] T250a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us3_curated.py` 寫 US3-AJ-10 的測試(就緒後在 `[data-state="auto-running"]` 顯示時按它的「關閉」;等判定完成後再重新整理;分隔註解寫 `# ---- 004 US3-AJ-10`(`plan.md` § 待決問題 Q34)),執行確認它因為「判定中的提示沒有關閉鈕,只能等完成」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-10
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-012
- [X] T250b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/models.html`、`src/cgb/static/js/models.js` 只寫讓 US3-AJ-10 通過的程式碼;`[data-state="auto-running"]` 加 `[data-dismiss]` 關閉鈕,送 `POST /api/downloads/auto-result/dismiss`;判定完成時看 `dismissed`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T250a)
  - 🧪 `testplan.md` § US3-AJ-10
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`
  - 📎 `spec.md` § FR-012
- [X] T251a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us3_curated.py` 寫 US3-AJ-11 的測試(情況 A 打開新增表單、`#c-type` 選「不指定」;情況 B 改成 T4、勾 `#c-highmem` 送出 `llama3.2:3b`;情況 C 打開 `qwen2.5:7b` 的修改表單只改說明送出;分隔註解寫 `# ---- 004 US3-AJ-11`(`plan.md` § 待決問題 Q34)),執行確認它因為「表單只有 GPU 選單,建議類型送成字串或少了 `highMem`,修改時把高 RAM 清掉」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-11
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-009
- [X] T251b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js` 只寫讓 US3-AJ-11 通過的程式碼;照 `prototype/library.html` 加 `#c-highmem`,跟著 `#c-type` 啟用或停用,送出時建議類型一律帶 `{gpu, highMem}`(分身決策紀錄 D95),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T251a)
  - 🧪 `testplan.md` § US3-AJ-11
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-009
- [X] T131 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T123b~T130b、T249b~T251b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T251b)
  - 🧪 `testplan.md` § US3-AJ-01~US3-AJ-08、US3-AJ-09~US3-AJ-11
  - 📎 `testplan.md` § 4.3

### 介面覆蓋(US3)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`(故事 3 擴充:精選清單編輯、自動下載的判定與提示) | T096b | T096a |
| `ui-events.asyncapi.yaml` § `operations.sendAutoDownloadUpdated`(故事 3 擴充:精選清單編輯、自動下載的判定與提示) | T096b~T097b、T103b | T096a~T097a、T103a |
| `ui.openapi.yaml` § `paths./curated.get` | T072b~T082b、T106b、T108b | T072a~T082a、T106a、T108a |
| `ui.openapi.yaml` § `paths./curated.post` | T072b、T076b、T078b~T079b、T081b、T106b | T072a、T076a、T078a~T079a、T081a、T106a |
| `ui.openapi.yaml` § `paths./curated/{id}.put` | T073b~T075b、T077b~T078b、T080b~T081b、T094b、T105b | T073a~T075a、T077a~T078a、T080a~T081a、T094a、T105a |
| `ui.openapi.yaml` § `paths./curated/{id}.delete` | T075b、T105b | T075a、T105a |
| `ui.openapi.yaml` § `paths./downloads.get`(故事 3 擴充:精選清單編輯、自動下載的判定與提示) | T083b~T086b、T088b、T091b、T094b、T098b~T100b、T105b~T106b、T108b | T083a~T086a、T088a、T091a、T094a、T098a~T100a、T105a~T106a、T108a |
| `ui.openapi.yaml` § `paths./downloads/auto-result.get`(故事 3 擴充:精選清單編輯、自動下載的判定與提示) | T083b~T096b、T098b~T101b、T103b~T104b、T107b~T108b | T083a~T096a、T098a~T101a、T103a~T104a、T107a~T108a |
| `ui.openapi.yaml` § `paths./downloads/auto-result/dismiss.post` | T100b~T102b | T100a~T102a |
| `store.dbml` § `Table sessions`、`Table auto_download_results`、`Table auto_download_items`(故事 3 擴充:精選清單編輯、自動下載的判定與提示) | T110b、T116b~T121b | T110a、T116a~T121a |
| `store.dbml` § `Table download_jobs`、`Table curated_models`(故事 3 擴充:精選清單編輯、自動下載的判定與提示) | T110b~T121b | T110a~T121a |
| `library.html` § `[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]` | T123b~T125b、T130b | T123a~T125a、T130a |
| `models.html` § `[data-state="cat-no-session"]`、`[data-state="auto-running"]`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`(故事 3 擴充:精選清單編輯、自動下載的判定與提示) | T126b~T130b | T126a~T130a |

### 測試案例覆蓋(US3)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US3-API-01~US3-API-37 | T072a~T108a | T072b~T108b | T109 |
| US3-API-38~US3-API-39 | T246a~T247a | T246b~T247b | T109 |
| US3-DB-01~US3-DB-12 | T110a~T121a | T110b~T121b | T122 |
| US3-DB-13 | T248a | T248b | T122 |
| US3-AJ-01~US3-AJ-08 | T123a~T130a | T123b~T130b | T131 |
| US3-AJ-09~US3-AJ-11 | T249a~T251a | T249b~T251b | T131 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 全綠(含 `tests/e2e/test_locale.py` 加了精選清單與自動下載的新代碼);重構任務前後的測試結果相同

---

## Phase 5: User Story 4 - 從 Hugging Face 找模型下載 (Priority: P3)

**Goal**: 下載頁可以搜尋 Hugging Face 上的 GGUF 模型、載入更多、展開量化版本與大小,勾選後和官方模型庫一起試算與加入下載;需要登入、沒有 GGUF 或版本拉不下來時阻止並說明原因;Hugging Face 失敗時只影響它自己的搜尋區;hf.co 名稱不分大小寫判定重複,下載好的模型出現在目錄與對話頁

**Independent Test**: 照 `testplan.md` § 5 的全部案例:E12 以 `uv run pytest tests/integration/test_huggingface.py tests/unit/test_hf_quants.py`、E7 以 `uv run pytest tests/integration/test_remote_ollama.py`、E2 以 `uv run pytest tests/integration/test_api_huggingface.py tests/integration/test_api_downloads.py tests/unit/test_model_name.py`、跨端點驗收以 `uv run pytest tests/e2e/test_004_us4_hf.py` 執行全綠

### E12 Hugging Face Hub(huggingface.co 公開 API)

> E12、E7、E2 三節平行。E12 只改 `src/cgb/adapters/huggingface.py`、`src/cgb/domain/hf_quants.py`、`tests/integration/test_huggingface.py`、`tests/unit/test_hf_quants.py`,以及 T136b 寫明的 `tests/integration/test_fake_signatures.py` 與 `tests/fakes/adapters.py`(`FakeHuggingFaceHub` 由故事 3 建立,簽章照 `plan.md` § 待決問題 Q49;E2 節不改它的簽章)。真的 `HuggingFaceHub` 接 `httpx.MockTransport`,不連網;每請求期限 `request_timeout` 與整體期限 `expand_deadline` 以短值注入(`plan.md` § 待決問題 Q44、Q38)

- [X] T132a [US4] 🔴 /tdd 紅燈:在 `tests/unit/test_hf_quants.py` 寫 US4-HF-01 的測試(對下列路徑各呼叫一次 `quant_name(path)`:A `qwen2.5-0.5b-instruct-q4_k_m.gguf`;B `llama-2-7b.Q4_K_M.gguf`(TheBloke 式 `<模型>.<量化>.gguf`,research.md 待驗證);C `Q4_K_M.gguf`(沒有分隔符);D `Q8_0/SmolLM2-135M-Instruct-Q8_0.gguf`(在子資料夾);E `SmolLM2-135M-Instruct-F16.GGUF`(副檔名大寫);分隔註解寫 `# ---- 004 US4-HF-01`(`plan.md` § 待決問題 Q34)),執行確認它因為「只以 `-` 切開,B 切出 `7b.Q4_K_M`」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-01
  - 📎 `spec.md` § FR-014
- [X] T132b [US4] 🟢 /tdd 綠燈:在 `src/cgb/domain/hf_quants.py` 只寫讓 US4-HF-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T132a)
  - 🧪 `testplan.md` § US4-HF-01
  - 📎 `spec.md` § FR-014
- [X] T133a [US4] 🔴 /tdd 紅燈:在 `tests/unit/test_hf_quants.py` 寫 US4-HF-02 的測試(對下列路徑各呼叫一次 `quant_name(path)`:A `Meta-Llama-3.1-70B-Instruct-Q5_K_M-00001-of-00002.gguf`;B `Q8_0/Meta-Llama-3.1-70B-Instruct-Q8_0-00002-of-00002.gguf`;再呼叫 `candidates(["m-Q6_K-00001-of-00003.gguf","m-Q6_K-00002-of-00003.gguf","m-Q6_K-00003-of-00003.gguf"])`;分隔註解寫 `# ---- 004 US4-HF-02`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒去掉分割編號,A 切出 `00002`(最後一段)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-02
  - 📎 `spec.md` § FR-014
- [X] T133b [US4] 🟢 /tdd 綠燈:在 `src/cgb/domain/hf_quants.py` 只寫讓 US4-HF-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T133a)
  - 🧪 `testplan.md` § US4-HF-02
  - 📎 `spec.md` § FR-014
- [X] T134a [US4] 🔴 /tdd 紅燈:在 `tests/unit/test_hf_quants.py` 寫 US4-HF-03 的測試(對下列路徑各呼叫一次 `quant_name(path)`:A `mmproj-model-f16.gguf`;B `Qwen2-VL-2B-Instruct-MMPROJ-F16.gguf`(research.md 待驗證的多模態投影檔);C `mmproj/SmolLM2-135M-Instruct-Q4_K_M.gguf`(只有資料夾名稱含 mmproj);D `README.md`;E `model.safetensors`;F `SmolLM2-135M-Instruct-Q4_K_M.gguf.part`;分隔註解寫 `# ---- 004 US4-HF-03`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒略過 `mmproj`,A 被列成 `f16` 候選、展開時打到 manifest 而被當成可下載的版本」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-03
  - 📎 `spec.md` § FR-014、FR-015;`research.md` § R3
- [X] T134b [US4] 🟢 /tdd 綠燈:在 `src/cgb/domain/hf_quants.py` 只寫讓 US4-HF-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T134a)
  - 🧪 `testplan.md` § US4-HF-03
  - 📎 `spec.md` § FR-014、FR-015;`research.md` § R3
- [X] T135a [US4] 🔴 /tdd 紅燈:在 `tests/unit/test_hf_quants.py` 寫 US4-HF-04 的測試(呼叫 `candidates(["a-Q4_K_M.gguf","b-q4_k_m.gguf","a-f16.gguf","a-F16.gguf","a-Q2_K.gguf","mmproj-a-f16.gguf","README.md"])`;分隔註解寫 `# ---- 004 US4-HF-04`(`plan.md` § 待決問題 Q34)),執行確認它因為「去重分大小寫,`q4_k_m` 與 `F16` 各多出一個」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-04
  - 📎 `spec.md` § FR-014;`research.md` § R3
- [X] T135b [US4] 🟢 /tdd 綠燈:在 `src/cgb/domain/hf_quants.py` 只寫讓 US4-HF-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T135a)
  - 🧪 `testplan.md` § US4-HF-04
  - 📎 `spec.md` § FR-014;`research.md` § R3
- [X] T136a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-05 的測試(呼叫 `search_models("qwen 2.5")`;分隔註解寫 `# ---- 004 US4-HF-05`(`plan.md` § 待決問題 Q34));同一個任務在 `tests/integration/test_huggingface.py` 寫 `Recorder` 與 `HalfBody`、`half_body_reply`(照 `tests/integration/test_model_library.py`、`tests/integration/test_remote_ollama.py`),執行確認它因為「漏帶 `gated=false`,需要同意條款的模型也列出來」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-05
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-013;`plan.md` § 待決問題 Q65
- [X] T136b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py`、`tests/integration/test_fake_signatures.py` 只寫讓 US4-HF-05 通過的程式碼;新增 `src/cgb/adapters/huggingface.py` 的 `HuggingFaceHub(transport=None, base_url="https://huggingface.co", request_timeout=10, expand_deadline=10)`(`plan.md` § 待決問題 Q44);同一個任務在 `tests/integration/test_fake_signatures.py` 的 `PAIRS` 加 `(HuggingFaceHub, FakeHuggingFaceHub)`(`test_adapters裡每個定義了轉接層類別的模組都在比對清單裡` 會要求),`FakeHuggingFaceHub` 的簽章不符時改 `tests/fakes/adapters.py`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T136a)
  - 🧪 `testplan.md` § US4-HF-05
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-013;`plan.md` § 待決問題 Q65
- [X] T137a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-06 的測試(呼叫 `search_models("qwen")`;分隔註解寫 `# ---- 004 US4-HF-06`(`plan.md` § 待決問題 Q34)),執行確認它因為「以筆數等於 20 判斷有沒有下一頁(這頁 3 筆),`nextCursor` 回 None」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-06
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-013
- [X] T137b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T137a)
  - 🧪 `testplan.md` § US4-HF-06
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-013
- [X] T138a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-07 的測試(依序呼叫 `search_models("qwen")` 與 `search_models("qwen", cursor="eyJpZCI6IjMifQ==")`;分隔註解寫 `# ---- 004 US4-HF-07`(`plan.md` § 待決問題 Q34)),執行確認它因為「載入更多時直接 GET `Link` 的網址,帶成 `limit=2`、`gated=true`(合約:其他參數照第一頁再帶一次)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-07
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-013
- [X] T138b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T138a)
  - 🧪 `testplan.md` § US4-HF-07
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-013
- [X] T139a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-08 的測試(每種情況各用一個新的 `HuggingFaceHub` 呼叫一次 `search_models(...)`;分隔註解寫 `# ---- 004 US4-HF-08`(`plan.md` § 待決問題 Q34)),執行確認它因為「只要有 `Link` 標頭就當成有下一頁,B 回 `abc`」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-08
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-013、使用者故事 4 驗收情境 5
- [X] T139b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T139a)
  - 🧪 `testplan.md` § US4-HF-08
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-013、使用者故事 4 驗收情境 5
- [X] T140a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-09 的測試(呼叫 `search_models("qwen")`;分隔註解寫 `# ---- 004 US4-HF-09`(`plan.md` § 待決問題 Q34)),執行確認它因為「組不出 `hf.co/<作者>/<模型>` 的那一筆沒略過,`onlyname` 進了結果、展開時路徑是 `/api/models/onlyname/tree/main`」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-09
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-013
- [X] T140b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T140a)
  - 🧪 `testplan.md` § US4-HF-09
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-013
- [X] T141a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-10 的測試(呼叫 `list_repo_files("bartowski","SmolLM2-135M-Instruct-GGUF")`;分隔註解寫 `# ---- 004 US4-HF-10`(`plan.md` § 待決問題 Q34)),執行確認它因為「照 `Link` 翻頁讀完,多送一個請求並列出 `Q8_0`(`plan.md` Q3 決定 A:只讀第一頁)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-10
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-014;`plan.md` § 待決問題 Q3
- [X] T141b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T141a)
  - 🧪 `testplan.md` § US4-HF-10
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-014;`plan.md` § 待決問題 Q3
- [X] T142a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-11 的測試(呼叫 `list_repo_files("TheBloke","Llama-2-7B-GGUF")`;分隔註解寫 `# ---- 004 US4-HF-11`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒看 `type`,資料夾 `old.gguf` 被切出 `old`」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-11
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-014;`research.md` § R3
- [X] T142b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T142a)
  - 🧪 `testplan.md` § US4-HF-11
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-014;`research.md` § R3
- [X] T143a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-12 的測試(每種情況各用一個新的 `HuggingFaceHub` 呼叫一次 `list_repo_files("bartowski","SmolLM2-135M-Instruct-GGUF")`;分隔註解寫 `# ---- 004 US4-HF-12`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒有候選時回空 list,呼叫的一方展開出 0 個版本(UI 合約 `HfQuantList.quants` 至少 1 筆)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-12
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7
- [X] T143b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T143a)
  - 🧪 `testplan.md` § US4-HF-12
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7
- [X] T144a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-13 的測試(依序呼叫 `get_manifest("unsloth","Qwen3-0.6B-GGUF","Q4_K_M")` 與 `get_manifest("unsloth","Qwen3-0.6B-GGUF","latest")`;分隔註解寫 `# ---- 004 US4-HF-13`(`plan.md` § 待決問題 Q34)),執行確認它因為「把 `config.size` 549 也加進去,回 396707681」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-13
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-014、FR-018;`research.md` § R4
- [X] T144b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T144a)
  - 🧪 `testplan.md` § US4-HF-13
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-014、FR-018;`research.md` § R4
- [X] T145a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-14 的測試(每種情況各呼叫一次 `get_manifest("bartowski","Meta-Llama-3.1-70B-Instruct-GGUF", tag)`;分隔註解寫 `# ---- 004 US4-HF-14`(`plan.md` § 待決問題 Q34)),執行確認它因為「400 走「其他非 200」歸成 `HF_BAD_RESPONSE`,試算顯示「暫時無法使用」而不是「這個量化版本無法下載」(D15)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-14
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-015;`plan.md` § 待決問題 Q1
- [X] T145b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T145a)
  - 🧪 `testplan.md` § US4-HF-14
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-015;`plan.md` § 待決問題 Q1
- [X] T146a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-15 的測試(呼叫 `list_repo_files("cgb-test","no-such-repo")`,再呼叫 `get_manifest("google","gemma-3-1b-it-qat-q4_0-gguf","Q4_0")`;分隔註解寫 `# ---- 004 US4-HF-15`(`plan.md` § 待決問題 Q34)),執行確認它因為「tree 的 401 走「其他非 200」歸 `HF_BAD_RESPONSE`(`plan.md` Q2 決定 A 要併成 `HF_AUTH_REQUIRED`)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-15
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7;`plan.md` § 待決問題 Q2
- [X] T146b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T146a)
  - 🧪 `testplan.md` § US4-HF-15
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7;`plan.md` § 待決問題 Q2
- [X] T147a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-16 的測試(每種情況各呼叫一次 `get_manifest("unsloth","Qwen3-0.6B-GGUF","Q4_K_M")`;分隔註解寫 `# ---- 004 US4-HF-16`(`plan.md` § 待決問題 Q34)),執行確認它因為「只加總 `size`、不看有沒有模型層,A 回 `{"sizeBytes":1660}` 被當成可下載(`plan.md` Q5 決定 A)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-16
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-014;`plan.md` § 待決問題 Q5
- [X] T147b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T147a)
  - 🧪 `testplan.md` § US4-HF-16
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-014;`plan.md` § 待決問題 Q5
- [X] T148a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-17 的測試(呼叫 `list_quants("bartowski","SmolLM2-135M-Instruct-GGUF")`;分隔註解寫 `# ---- 004 US4-HF-17`(`plan.md` § 待決問題 Q34)),執行確認它因為「依完成的順序收集結果,`F16` 排到 `Q4_K_M` 前面(UI 合約:依檔案清單的順序)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-17
  - 📎 `spec.md` § FR-014、使用者故事 4 驗收情境 2;`research.md` § R3
- [X] T148b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-17 通過的程式碼;`list_quants` 經 `get_manifest` 取每一個版本,結果依檔案清單的順序,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T148a)
  - 🧪 `testplan.md` § US4-HF-17
  - 📎 `spec.md` § FR-014、使用者故事 4 驗收情境 2;`research.md` § R3
- [X] T149a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-18 的測試(呼叫 `list_quants("bartowski","SmolLM2-135M-Instruct-GGUF")`;分隔註解寫 `# ---- 004 US4-HF-18`(`plan.md` § 待決問題 Q34)),執行確認它因為「用 `asyncio.gather` 一次全部送出,最大值是 6(合約:同時最多 4 個)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-18
  - 📎 `spec.md` § FR-014;`research.md` § R3
- [X] T149b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-18 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T149a)
  - 🧪 `testplan.md` § US4-HF-18
  - 📎 `spec.md` § FR-014;`research.md` § R3
- [X] T150a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-19 的測試(每種情況各用一個新的 `HuggingFaceHub` 呼叫一次 `list_quants("bartowski","SmolLM2-135M-Instruct-GGUF")`;分隔註解寫 `# ---- 004 US4-HF-19`(`plan.md` § 待決問題 Q34)),執行確認它因為「全部 400 時回空 list(UI 合約 `quants` 至少 1 筆)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-19
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7
- [X] T150b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-19 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T150a)
  - 🧪 `testplan.md` § US4-HF-19
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7
- [X] T151a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-20 的測試(每種情況各用一個新的 `HuggingFaceHub` 呼叫一次 `list_quants("google","gemma-3-1b-it-qat-q4_0-gguf")`;分隔註解寫 `# ---- 004 US4-HF-20`(`plan.md` § 待決問題 Q34)),執行確認它因為「把 manifest 的 401 當成 400 一樣略過,B 回 `Q4_K_M`、`F16` 兩筆,使用者勾了才在下載時失敗(research.md R3:401 是整個模型)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-20
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7;`research.md` § R3
- [X] T151b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-20 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T151a)
  - 🧪 `testplan.md` § US4-HF-20
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7;`research.md` § R3
- [X] T152a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-21 的測試(呼叫 `list_quants("bartowski","SmolLM2-135M-Instruct-GGUF")`,丟出後再等 0.3 秒;分隔註解寫 `# ---- 004 US4-HF-21`(`plan.md` § 待決問題 Q34)),執行確認它因為「用 `gather(return_exceptions=True)` 等全部完成再看有沒有失敗,0.25 秒後才丟」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-21
  - 📎 `spec.md` § FR-016、FR-014
- [X] T152b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-21 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T152a)
  - 🧪 `testplan.md` § US4-HF-21
  - 📎 `spec.md` § FR-016、FR-014
- [X] T153a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-22 的測試(每種情況各用一個新的 `HuggingFaceHub`,依序呼叫三個方法(`search_models("qwen")`、`list_repo_files("a","b")`、`get_manifest("a","b","Q4_K_M")`);分隔註解寫 `# ---- 004 US4-HF-22`(`plan.md` § 待決問題 Q34)),執行確認它因為「只接 `httpx.ConnectError`,屬於 `ProtocolError` 的 C 原樣往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-22
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016、使用者故事 4 驗收情境 6
- [X] T153b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-22 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T153a)
  - 🧪 `testplan.md` § US4-HF-22
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016、使用者故事 4 驗收情境 6
- [X] T154a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-23 的測試(每種情況各用一個新的 `HuggingFaceHub`,依序呼叫三個方法(參數同 US4-HF-22);分隔註解寫 `# ---- 004 US4-HF-23`(`plan.md` § 待決問題 Q34)),執行確認它因為「先寫 `except httpx.TransportError` 再判逾時,逾時被攔成 `HF_UNREACHABLE`(合約第 1 條:先看逾時)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-23
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016、NFR-005、使用者故事 4 驗收情境 6
- [X] T154b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-23 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T154a)
  - 🧪 `testplan.md` § US4-HF-23
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016、NFR-005、使用者故事 4 驗收情境 6
- [X] T155a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-24 的測試(每種情況各用一個新的 `HuggingFaceHub`,依序呼叫三個方法(參數同 US4-HF-22);分隔註解寫 `# ---- 004 US4-HF-24`(`plan.md` § 待決問題 Q34)),執行確認它因為「不看狀態碼就解析本文,D 照常回傳結果」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-24
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016、使用者故事 4 驗收情境 6
- [X] T155b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-24 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T155a)
  - 🧪 `testplan.md` § US4-HF-24
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016、使用者故事 4 驗收情境 6
- [X] T156a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-25 的測試(每種情況各用一個新的 `HuggingFaceHub`,依序呼叫 `search_models("qwen")` 與 `list_repo_files("a","b")`;分隔註解寫 `# ---- 004 US4-HF-25`(`plan.md` § 待決問題 Q34)),執行確認它因為「三個方法共用一張狀態碼對照表,搜尋的 401 也歸 `HF_AUTH_REQUIRED`、tree 的 400 也歸 `HF_QUANT_UNAVAILABLE`(合約第 4 條:點名的狀態碼只屬於該操作;搜尋的 UI API 對不到這兩個代碼)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-25
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016
- [X] T156b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-25 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T156a)
  - 🧪 `testplan.md` § US4-HF-25
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016
- [X] T157a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_huggingface.py` 寫 US4-HF-26 的測試(每種情況各用一個新的 `HuggingFaceHub`,依序呼叫三個方法(參數同 US4-HF-22);分隔註解寫 `# ---- 004 US4-HF-26`(`plan.md` § 待決問題 Q34));T136b 建立的 `httpx.AsyncClient`(httpx 預設 `follow_redirects=False`)與 T155b 的狀態碼歸類已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「client 開了 `follow_redirects=True`,模型改名後的轉址被跟過去,讀到別的 repo」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-HF-26
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016
- [X] T157b [US4] 🟢 /tdd 綠燈:US4-HF-26 由 T136b 建立的 `httpx.AsyncClient`(httpx 預設 `follow_redirects=False`)與 T155b 的狀態碼歸類 滿足,確認 `src/cgb/adapters/huggingface.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-26 通過的程式碼(依賴 T157a)
  - 🧪 `testplan.md` § US4-HF-26
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016
- [X] T158a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-27 的測試(每種情況各用一個新的 `HuggingFaceHub`,依序呼叫三個方法(參數同 US4-HF-22);分隔註解寫 `# ---- 004 US4-HF-27`(`plan.md` § 待決問題 Q34)),執行確認它因為「`json.JSONDecodeError` 原樣往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-27
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016、使用者故事 4 驗收情境 6
- [X] T158b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-27 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T158a)
  - 🧪 `testplan.md` § US4-HF-27
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016、使用者故事 4 驗收情境 6
- [X] T159a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-28 的測試(每種情況各用一個新的 `HuggingFaceHub` 呼叫一次 `search_models("qwen")`;分隔註解寫 `# ---- 004 US4-HF-28`(`plan.md` § 待決問題 Q34)),執行確認它因為「只要 JSON 解析成功就原樣回傳,E2 讀 `item["id"]` 時 `KeyError` 變 500」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-28
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016
- [X] T159b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-28 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T159a)
  - 🧪 `testplan.md` § US4-HF-28
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016
- [X] T160a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-29 的測試(每種情況各用一個新的 `HuggingFaceHub` 呼叫一次 `list_repo_files("a","b")`;分隔註解寫 `# ---- 004 US4-HF-29`(`plan.md` § 待決問題 Q34)),執行確認它因為「只檢查是陣列、不檢查每一筆,C、D 的 `KeyError` 原樣往上拋」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-29
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016
- [X] T160b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-29 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T160a)
  - 🧪 `testplan.md` § US4-HF-29
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016
- [X] T161a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-30 的測試(每種情況各用一個新的 `HuggingFaceHub` 呼叫一次 `get_manifest("unsloth","Qwen3-0.6B-GGUF","Q4_K_M")`;分隔註解寫 `# ---- 004 US4-HF-30`(`plan.md` § 待決問題 Q34)),執行確認它因為「寫成 `manifest.get("layers") or []`,B、C 被當成沒有層」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-30
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016
- [X] T161b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-30 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T161a)
  - 🧪 `testplan.md` § US4-HF-30
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016
- [X] T162a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-31 的測試(用兩組 handler 各呼叫一次三個方法(參數同 US4-HF-22);分隔註解寫 `# ---- 004 US4-HF-31`(`plan.md` § 待決問題 Q34)),執行確認它因為「message 把對方的 `error` 原文接在後面(合約:固定繁體中文,不帶英文原文)」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-31
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`、`paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016、FR-015
- [X] T162b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-31 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T162a)
  - 🧪 `testplan.md` § US4-HF-31
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`、`paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § FR-016、FR-015
- [X] T163a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-32 的測試(依序呼叫三個方法;分隔註解寫 `# ---- 004 US4-HF-32`(`plan.md` § 待決問題 Q34)),執行確認它因為「建 client 時沒帶 `timeout`,沿用 httpx 預設的 5 秒」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-32
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § NFR-005
- [X] T163b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-32 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T163a)
  - 🧪 `testplan.md` § US4-HF-32
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § NFR-005
- [X] T164a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-33 的測試(依序呼叫三個方法,各自量從呼叫到丟出的時間;分隔註解寫 `# ---- 004 US4-HF-33`(`plan.md` § 待決問題 Q34)),執行確認它因為「只設 `httpx.Timeout`、沒有 `asyncio.timeout` 包住整個請求(MockTransport 不會觸發 httpx 的逾時,對方一直不回時就沒有期限),等到 0.5 秒才回傳結果」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-33
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § NFR-005、SC-004;`plan.md` § 待決問題 Q38
- [X] T164b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-33 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T164a)
  - 🧪 `testplan.md` § US4-HF-33
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § NFR-005、SC-004;`plan.md` § 待決問題 Q38
- [X] T165a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_huggingface.py` 寫 US4-HF-34 的測試(依序呼叫三個方法,各自量時間;分隔註解寫 `# ---- 004 US4-HF-34`(`plan.md` § 待決問題 Q34));T164b 以 `asyncio.timeout` 包住整個請求(`client.get` 讀完本文才回)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「改用 `client.stream`,期限只包住收標頭,讀本文不受限(合約 `x-timeout`:整個請求含讀完本文不超過 10 秒)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-HF-34
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § NFR-005、SC-004
- [X] T165b [US4] 🟢 /tdd 綠燈:US4-HF-34 由 T164b 以 `asyncio.timeout` 包住整個請求(`client.get` 讀完本文才回) 滿足,確認 `src/cgb/adapters/huggingface.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-34 通過的程式碼(依賴 T165a)
  - 🧪 `testplan.md` § US4-HF-34
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § NFR-005、SC-004
- [X] T166a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_huggingface.py` 寫 US4-HF-35 的測試(依序呼叫 `search_models("qwen")` 與 `search_models("qwen", cursor="c2")`(合計約 0.3 秒);分隔註解寫 `# ---- 004 US4-HF-35`(`plan.md` § 待決問題 Q34));T164b 每次呼叫各自起算的期限已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「把期限放在 `HuggingFaceHub` 建立時起算或整個搜尋共用一個計時器,第二頁在 0.2 秒到期時被歸 `HF_TIMEOUT`(合約:每讀一頁各自計算)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-HF-35
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § NFR-005
- [X] T166b [US4] 🟢 /tdd 綠燈:US4-HF-35 由 T164b 每次呼叫各自起算的期限 滿足,確認 `src/cgb/adapters/huggingface.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-35 通過的程式碼(依賴 T166a)
  - 🧪 `testplan.md` § US4-HF-35
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § NFR-005
- [X] T167a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_huggingface.py` 寫 US4-HF-36 的測試(呼叫 `list_quants("bartowski","SmolLM2-135M-Instruct-GGUF")`,量從呼叫到丟出的時間,丟出後再等 0.3 秒;分隔註解寫 `# ---- 004 US4-HF-36`(`plan.md` § 待決問題 Q34)),執行確認它因為「只有每個請求各自的期限(`plan.md` Q4 的 A),0.45 秒回傳 5 筆」這類實作而失敗
  - 🧪 `testplan.md` § US4-HF-36
  - 📎 `spec.md` § SC-004、NFR-005;`plan.md` § 待決問題 Q4
- [X] T167b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-36 通過的程式碼;`list_quants` 整個展開套 `expand_deadline` 的整體期限,到期取消還在跑的請求,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T167a)
  - 🧪 `testplan.md` § US4-HF-36
  - 📎 `spec.md` § SC-004、NFR-005;`plan.md` § 待決問題 Q4
- [X] T168a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_huggingface.py` 寫 US4-HF-37 的測試(呼叫 `list_quants("bartowski","SmolLM2-135M-Instruct-GGUF")`,量時間;分隔註解寫 `# ---- 004 US4-HF-37`(`plan.md` § 待決問題 Q34));T148b 的 `list_quants` 經 `get_manifest` 取每個版本(共用每請求期限)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「`list_quants` 自己開 client 打 manifest、繞過 `get_manifest` 共用的每請求期限,只剩整體期限,0.6 秒才丟」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-HF-37
  - 📎 `spec.md` § NFR-005、SC-004;`research.md` § R3
- [X] T168b [US4] 🟢 /tdd 綠燈:US4-HF-37 由 T148b 的 `list_quants` 經 `get_manifest` 取每個版本(共用每請求期限) 滿足,確認 `src/cgb/adapters/huggingface.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-37 通過的程式碼(依賴 T168a)
  - 🧪 `testplan.md` § US4-HF-37
  - 📎 `spec.md` § NFR-005、SC-004;`research.md` § R3
- [X] T169a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_huggingface.py` 寫 US4-HF-38 的測試(呼叫 `get_manifest("unsloth","Qwen3-0.6B-GGUF","Q4_K_M")`;分隔註解寫 `# ---- 004 US4-HF-38`(`plan.md` § 待決問題 Q34));T167b 只在 `list_quants` 套整體期限已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「把整體期限做在三個方法共用的 `_get` 裡,單獨取大小也在 0.1 秒被歸 `HF_TIMEOUT`(合約 `x-timeout`:試算、加入下載與自動下載取大小時每個 manifest 各自計算,不套整體期限)」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-HF-38
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § NFR-005、FR-018
- [X] T169b [US4] 🟢 /tdd 綠燈:US4-HF-38 由 T167b 只在 `list_quants` 套整體期限 滿足,確認 `src/cgb/adapters/huggingface.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/huggingface.py` 只寫讓 US4-HF-38 通過的程式碼(依賴 T169a)
  - 🧪 `testplan.md` § US4-HF-38
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get`(`info.x-failure-rules`、`info.x-timeout`)
  - 📎 `spec.md` § NFR-005、FR-018
- [X] T170 [US4] 🔵 /tdd 重構:在全部測試綠燈下整理 T132b~T169b 記下的重構清單(範圍限 `src/cgb/adapters/huggingface.py`、`src/cgb/domain/hf_quants.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_huggingface.py`、`tests/unit/test_hf_quants.py` 的斷言(依賴 T169b)
  - 🧪 `testplan.md` § US4-HF-01~US4-HF-38
  - 📎 `testplan.md` § 5.1

### E7 遠端 Ollama(Colab 執行環境上,Ollama API)

> 只改 `src/cgb/adapters/remote_ollama.py` 與 `tests/integration/test_remote_ollama.py`;只測 `pull_model`(`plan.md` § 待決問題 Q35)。001 的 `test_pull_model_只把帶_total_的行當進度_最後回成功` 與 `test_pull_model_的失敗依串流內容分類` 保留不動。歸類照 `contracts/remote-ollama.openapi.yaml` 的 `info.x-failure-rules`,現行程式和合約不符的地方照 `plan.md` § 待決問題 Q7、Q42、Q43 改;hf.co 的進度行常數照 `testplan.md` § 5.2

- [X] T171a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-01 的測試(依情況各用一個新的 `RemoteOllama` 呼叫一次 `pull_model`,`model` 為:A `HF_Q4`;B `hf.co/Bartowski/smollm2-135M-Instruct-GGUF:q4_k_m`;C `hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:latest`;分隔註解寫 `# ---- 004 US4-RO-01`(`plan.md` § 待決問題 Q34));既有 `RemoteOllama.pull_model`(`src/cgb/adapters/remote_ollama.py`)把 `model` 原樣放進本文已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「為了不分大小寫的重複判定(FR-018),把送出的名稱也換成比對鍵(`casefold()`),B 送成全小寫」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-RO-01
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-018、FR-014、使用者故事 4 驗收情境 3
- [X] T171b [US4] 🟢 /tdd 綠燈:US4-RO-01 由 既有 `RemoteOllama.pull_model`(`src/cgb/adapters/remote_ollama.py`)把 `model` 原樣放進本文 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-01 通過的程式碼(依賴 T171a)
  - 🧪 `testplan.md` § US4-RO-01
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-018、FR-014、使用者故事 4 驗收情境 3
- [X] T172a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-02 的測試(呼叫一次 `pull_model`,`model` 為 `HF_Q4`;分隔註解寫 `# ---- 004 US4-RO-02`(`plan.md` § 待決問題 Q34));既有 `RemoteOllama.pull_model` 只把帶 `total` 的行當進度(001 的 `test_pull_model_只把帶_total_的行當進度_最後回成功`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「把 `pulling manifest`、`verifying sha256 digest`、`writing manifest` 也當進度產出,佇列的進度掉回 0%」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-RO-02
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-018、FR-014、使用者故事 4 驗收情境 3;`research.md` § R4;`plan.md` § 待決問題 Q7
- [X] T172b [US4] 🟢 /tdd 綠燈:US4-RO-02 由 既有 `RemoteOllama.pull_model` 只把帶 `total` 的行當進度(001 的 `test_pull_model_只把帶_total_的行當進度_最後回成功`) 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-02 通過的程式碼(依賴 T172a)
  - 🧪 `testplan.md` § US4-RO-02
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-018、FR-014、使用者故事 4 驗收情境 3;`research.md` § R4;`plan.md` § 待決問題 Q7
- [X] T173a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-03 的測試(每種情況各用一個新的 `RemoteOllama` 呼叫一次 `pull_model`,`model` 為 `HF_Q4`;分隔註解寫 `# ---- 004 US4-RO-03`(`plan.md` § 待決問題 Q34)),執行確認它因為「`client.send` 不在 `try` 裡,`ConnectTimeout` 原樣往上拋(現況)」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-03
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T173b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T173a)
  - 🧪 `testplan.md` § US4-RO-03
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T174a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-04 的測試(每種情況各用一個新的 `RemoteOllama` 呼叫一次 `pull_model`,`model` 為 `HF_Q4`;分隔註解寫 `# ---- 004 US4-RO-04`(`plan.md` § 待決問題 Q34)),執行確認它因為「`ConnectError` 原樣往上拋(現況)」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-04
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T174b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T174a)
  - 🧪 `testplan.md` § US4-RO-04
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T175a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-05 的測試(每種情況各用一個新的 `RemoteOllama` 呼叫一次 `pull_model`,`model` 為 `HF_Q4`;分隔註解寫 `# ---- 004 US4-RO-05`(`plan.md` § 待決問題 Q34)),執行確認它因為「不看狀態碼,把錯誤本文當成 NDJSON 的 error 行,A 歸成 `OLLAMA_PULL_FAILED`(現況)、B 歸成 `OLLAMA_NOT_FOUND`」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-05
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T175b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T175a)
  - 🧪 `testplan.md` § US4-RO-05
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T176a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-06 的測試(每種情況各用一個新的 `RemoteOllama` 呼叫一次 `pull_model`,`model` 為 `HF_Q4`;分隔註解寫 `# ---- 004 US4-RO-06`(`plan.md` § 待決問題 Q34)),執行確認它因為「不看狀態碼就讀本文,A 因為含 `file does not exist` 歸成 `OLLAMA_NOT_FOUND`(現況)」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-06
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T176b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T176a)
  - 🧪 `testplan.md` § US4-RO-06
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T177a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-07 的測試(每種情況各用一個新的 `RemoteOllama` 呼叫一次 `pull_model`,`model` 為 `HF_Q4`;分隔註解寫 `# ---- 004 US4-RO-07`(`plan.md` § 待決問題 Q34)),執行確認它因為「沿用同檔的 `_STATUS_CODES`,把 pull 的 404 歸成 `OLLAMA_NOT_FOUND`(合約第 3 條:404 → `OLLAMA_NOT_FOUND` 只有 `chat`,`pullModel` 沒有 404 回應,歸 `default`)」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-07
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T177b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T177a)
  - 🧪 `testplan.md` § US4-RO-07
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T178a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-08 的測試(每種情況各用一個新的 `RemoteOllama` 呼叫一次 `pull_model`,`model` 為 `HF_Q4`;分隔註解寫 `# ---- 004 US4-RO-08`(`plan.md` § 待決問題 Q34)),執行確認它因為「不看 `Content-Type`,A、C 照常回成功(現況),中間的代理或錯誤頁被當成下載完成」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-08
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T178b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T178a)
  - 🧪 `testplan.md` § US4-RO-08
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T179a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-09 的測試(呼叫一次 `pull_model`,`model` 為 `HF_Q4`,邊迭代邊把產出的行記下;分隔註解寫 `# ---- 004 US4-RO-09`(`plan.md` § 待決問題 Q34)),執行確認它因為「修 Q7 時把整段包成一個 `except httpx.TransportError`,串流中的 `ReadTimeout` 被歸成 `OLLAMA_STREAM_INTERRUPTED` 或 `OLLAMA_UNREACHABLE`」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-09
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018;`plan.md` § 待決問題 Q7、Q38
- [X] T179b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T179a)
  - 🧪 `testplan.md` § US4-RO-09
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018;`plan.md` § 待決問題 Q7、Q38
- [X] T180a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-10 的測試(每種情況各用一個新的 `RemoteOllama` 呼叫一次 `pull_model`,`model` 為 `HF_Q4`;分隔註解寫 `# ---- 004 US4-RO-10`(`plan.md` § 待決問題 Q34)),執行確認它因為「修 Q7 時把串流開始前與開始後的傳輸層失敗共用一個 `except`,A、B 被歸成 `OLLAMA_UNREACHABLE`」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-10
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018;`plan.md` § 待決問題 Q7
- [X] T180b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T180a)
  - 🧪 `testplan.md` § US4-RO-10
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018;`plan.md` § 待決問題 Q7
- [X] T181a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-11 的測試(呼叫一次 `pull_model`,`model` 為 `qwen2.5:7b`,邊迭代邊把產出的行記下;分隔註解寫 `# ---- 004 US4-RO-11`(`plan.md` § 待決問題 Q34));既有 `RemoteOllama.pull_model` 對 200 之後 error 行的歸類(001 的 `test_pull_model_的失敗依串流內容分類`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「加 Content-Type 與型別檢查時改寫歸類,error 行一律歸 `OLLAMA_PULL_FAILED`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-RO-11
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T181b [US4] 🟢 /tdd 綠燈:US4-RO-11 由 既有 `RemoteOllama.pull_model` 對 200 之後 error 行的歸類(001 的 `test_pull_model_的失敗依串流內容分類`) 滿足,確認 `src/cgb/adapters/remote_ollama.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-11 通過的程式碼(依賴 T181a)
  - 🧪 `testplan.md` § US4-RO-11
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T182a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-12 的測試(每種情況各用一個新的 `RemoteOllama` 呼叫一次 `pull_model`;分隔註解寫 `# ---- 004 US4-RO-12`(`plan.md` § 待決問題 Q34)),執行確認它因為「從 error 原文裡的 `400:` 判成 `OLLAMA_BAD_REQUEST`(A、C;合約第 3 條的 400 只看 HTTP 狀態碼)」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-12
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018;`research.md` § R4
- [X] T182b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T182a)
  - 🧪 `testplan.md` § US4-RO-12
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018;`research.md` § R4
- [X] T183a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-13 的測試(每種情況各用一個新的 `RemoteOllama` 呼叫一次 `pull_model`,`model` 為 `HF_Q4`;分隔註解寫 `# ---- 004 US4-RO-13`(`plan.md` § 待決問題 Q34)),執行確認它因為「`json.loads` 的 `JSONDecodeError` 原樣往上拋(現況 A)」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-13
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T183b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T183a)
  - 🧪 `testplan.md` § US4-RO-13
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018
- [X] T184a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-14 的測試(每種情況呼叫一次 `pull_model`,`model` 為 `HF_Q4`;分隔註解寫 `# ---- 004 US4-RO-14`(`plan.md` § 待決問題 Q34)),執行確認它因為「修 Q7 時改用推論類的 `stream_timeout`(300 秒)或清單的 `LIST_TIMEOUT`(10 秒)建 client」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-14
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018;`plan.md` § 待決問題 Q7、Q38
- [X] T184b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T184a)
  - 🧪 `testplan.md` § US4-RO-14
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § NFR-006、FR-018;`plan.md` § 待決問題 Q7、Q38
- [X] T252a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US4-RO-15 的測試(每種情況各用一個新的 `RemoteOllama` 呼叫一次 `pull_model`,`model` 為 `HF_Q4`;分隔註解寫 `# ---- 004 US4-RO-15`(`plan.md` § 待決問題 Q34)),執行確認它因為「以整個標頭字串和 `application/x-ndjson` 比相等,帶 `charset` 的回應被歸成 `OLLAMA_BAD_RESPONSE`」這類實作而失敗
  - 🧪 `testplan.md` § US4-RO-15
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-018、NFR-006;`plan.md` § 待決問題 Q45
- [X] T252b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US4-RO-15 通過的程式碼;`Content-Type` 只比 `;` 之前、去掉空白、不分大小寫的 media type(`info.x-failure-rules` (4),`plan.md` § 待決問題 Q45),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T252a)
  - 🧪 `testplan.md` § US4-RO-15
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.PullProgress`、`components.schemas.Error`(`info.x-failure-rules`)
  - 📎 `spec.md` § FR-018、NFR-006;`plan.md` § 待決問題 Q45
- [X] T185 [US4] 🔵 /tdd 重構:在全部測試綠燈下整理 T171b~T184b、T252b 記下的重構清單(範圍限 `src/cgb/adapters/remote_ollama.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_remote_ollama.py` 的斷言(依賴 T252b)
  - 🧪 `testplan.md` § US4-RO-01~US4-RO-14、US4-RO-15
  - 📎 `testplan.md` § 5.2

### E2 後端 UI API(FastAPI REST 與 SSE)

> 搜尋與展開的案例寫進新的 `tests/integration/test_api_huggingface.py`,試算、加入、重新排隊、SSE 與目錄的案例寫進 `tests/integration/test_api_downloads.py`,`model_name` 的案例寫進新的 `tests/unit/test_model_name.py`。Hugging Face 用 `FakeHuggingFaceHub`(`fakes.huggingface`);`src/cgb/app.py` 接上正式的 `HuggingFaceHub()` 的 T186b 依賴 E12 節的 T136b。001~003 的試算與加入案例照原樣回歸;要改寫或刪掉的兩支舊測試寫在 T204b、T209b

- [X] T186a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-01 的測試(送 `GET /api/huggingface/search?q=%20qwen%20`;分隔註解寫 `# ---- 004 US4-API-01`(`plan.md` § 待決問題 Q34));同一個任務在 `tests/integration/test_api_huggingface.py` 新增 `HF_Q4`、`hf_page`、`hf_quants`,並把 `set_hf` 擴充成可以對某個完整名稱指定要丟的代碼(`testplan.md` § 5.3),執行確認它因為「搜尋前先呼叫 `require_ready_base_url()`,沒有工作階段時回 503 `NO_READY_SESSION`」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013、使用者故事 4 驗收情境 1
- [X] T186b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py`、`src/cgb/api/__init__.py`、`src/cgb/app.py` 只寫讓 US4-API-01 通過的程式碼;新增 `src/cgb/api/huggingface.py` 並在 `src/cgb/api/__init__.py` 註冊路由;`src/cgb/app.py` 的 `create_app` 沒給 `huggingface` 時用 `HuggingFaceHub()`(`src/cgb/adapters/huggingface.py` 由 E12 節建立),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T186a、T136b)
  - 🧪 `testplan.md` § US4-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013、使用者故事 4 驗收情境 1
- [X] T187a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-02 的測試(送 `GET /api/huggingface/search?q=qwen&cursor=c1`;分隔註解寫 `# ---- 004 US4-API-02`(`plan.md` § 待決問題 Q34)),執行確認它因為「載入更多時把 `cursor` 當頁碼轉成整數或丟掉,轉接層每次都拿到 `cursor=None`、一直回第一頁」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013
- [X] T187b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py` 只寫讓 US4-API-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T187a)
  - 🧪 `testplan.md` § US4-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013
- [X] T188a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_huggingface.py` 寫 US4-API-03 的測試(送 `GET /api/huggingface/search?q=zzzqqqnonexist`;分隔註解寫 `# ---- 004 US4-API-03`(`plan.md` § 待決問題 Q34));T186b 原樣交回轉接層的結果(0 筆照樣 200)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「0 筆時當成格式不符回 502 `HF_BAD_RESPONSE`,或回 404」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013、使用者故事 4 驗收情境 5
- [X] T188b [US4] 🟢 /tdd 綠燈:US4-API-03 由 T186b 原樣交回轉接層的結果(0 筆照樣 200) 滿足,確認 `src/cgb/api/huggingface.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/api/huggingface.py` 只寫讓 US4-API-03 通過的程式碼(依賴 T188a)
  - 🧪 `testplan.md` § US4-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013、使用者故事 4 驗收情境 5
- [X] T189a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-04 的測試(情況 A:`q` 只有三個空白;B:`q` 是 101 個字元;C:不帶 `q`;D:`q=qwen&cursor=`(空字串);分隔註解寫 `# ---- 004 US4-API-04`(`plan.md` § 待決問題 Q34)),執行確認它因為「以 FastAPI 的 `Query(min_length=1)` 驗,缺少或空字串時回 FastAPI 預設的 422 與 `detail`,不是合約的 `Error`」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013、NFR-006
- [X] T189b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py`、`src/cgb/domain/errors.py` 只寫讓 US4-API-04 通過的程式碼;新代碼 `INVALID_QUERY`、`INVALID_CURSOR` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T189a)
  - 🧪 `testplan.md` § US4-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-013、NFR-006
- [X] T190a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-05 的測試(依序以 `HF_UNREACHABLE`、`HF_SERVER_ERROR`、`HF_BAD_RESPONSE`、`HF_TIMEOUT` 各送一次 `GET /api/huggingface/search?q=qwen`;分隔註解寫 `# ---- 004 US4-API-05`(`plan.md` § 待決問題 Q34)),執行確認它因為「路由沒接 `AdapterError`,或 `MESSAGES` 沒補 `HF_*`、`ApiError.body()` 丟 `KeyError`,回 500」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-016、NFR-006、使用者故事 4 驗收情境 6
- [X] T190b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py`、`src/cgb/domain/errors.py` 只寫讓 US4-API-05 通過的程式碼;若要把 `HF_UNREACHABLE`、`HF_SERVER_ERROR`、`HF_BAD_RESPONSE`、`HF_TIMEOUT` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T190a)
  - 🧪 `testplan.md` § US4-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`
  - 📎 `spec.md` § FR-016、NFR-006、使用者故事 4 驗收情境 6
- [X] T191a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-06 的測試(依序送 Hugging Face 搜尋 `q=qwen`、展開 `bartowski/SmolLM2-135M-Instruct-GGUF`、官方搜尋 `q=qwen2.5`、`GET /api/curated`、試算 `["qwen2.5:7b"]`(直接輸入的官方名稱);分隔註解寫 `# ---- 004 US4-API-06`(`plan.md` § 待決問題 Q34)),執行確認它因為「試算取大小時不分前綴一律先問 Hugging Face,官方名稱也被 HF 的失敗擋下」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`、`paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`paths./curated.get`、`components.schemas.CuratedList`、`components.schemas.CuratedModel`、`paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-016、使用者故事 4 驗收情境 6、SC-004、SC-006
- [X] T191b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py` 只寫讓 US4-API-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T191a)
  - 🧪 `testplan.md` § US4-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`、`paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`paths./curated.get`、`components.schemas.CuratedList`、`components.schemas.CuratedModel`、`paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-016、使用者故事 4 驗收情境 6、SC-004、SC-006
- [X] T192a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-07 的測試(送 `GET /api/huggingface/models/bartowski/SmolLM2-135M-Instruct-GGUF/quants`;分隔註解寫 `# ---- 004 US4-API-07`(`plan.md` § 待決問題 Q34)),執行確認它因為「「已下載」照原樣比對,大小寫不同的 `q4_k_m` 比不到、標成 false」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`
  - 📎 `spec.md` § FR-014、FR-018、使用者故事 4 驗收情境 2
- [X] T192b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py` 只寫讓 US4-API-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T192a)
  - 🧪 `testplan.md` § US4-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`
  - 📎 `spec.md` § FR-014、FR-018、使用者故事 4 驗收情境 2
- [X] T193a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-08 的測試(情況 A:沒有開工作階段;B:工作階段就緒,`list_local_models.raises("OLLAMA_UNREACHABLE")`;C:工作階段就緒,`list_local_models.gate()` 一直不放行;`list_quants` 以 async `side_effect` 先等 0.2 秒再回(C 的期限從收到請求起算,`plan.md` § 待決問題 Q67);三種各展開 `bartowski/SmolLM2-135M-Instruct-GGUF` 一次;分隔註解寫 `# ---- 004 US4-API-08`(`plan.md` § 待決問題 Q34)),執行確認它因為「展開沿用試算的 `require_ready_base_url()`,沒有工作階段時回 503」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`
  - 📎 `spec.md` § FR-014、NFR-006、SC-004;`plan.md` § 待決問題 Q21、Q67
- [X] T193b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py`、`src/cgb/app.py` 只寫讓 US4-API-08 通過的程式碼;`src/cgb/app.py` 的 `Timeouts` 加 `hf_expand_deadline`(10),展開時讀模型清單套它,並和 Hugging Face 這一段同時開始、從收到展開請求起算(`plan.md` § 待決問題 Q44、Q21、Q67),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T193a)
  - 🧪 `testplan.md` § US4-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`
  - 📎 `spec.md` § FR-014、NFR-006、SC-004;`plan.md` § 待決問題 Q21、Q67
- [X] T194a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-09 的測試(依序以 `HF_AUTH_REQUIRED`、`HF_NO_GGUF` 各展開一次 `google/gemma-3-1b-it-qat-q4_0-gguf`;分隔註解寫 `# ---- 004 US4-API-09`(`plan.md` § 待決問題 Q34)),執行確認它因為「不能下載的原因照連不到處理回 502,前端顯示成「暫時無法使用」而不是說明原因」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7
- [X] T194b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py`、`src/cgb/domain/errors.py` 只寫讓 US4-API-09 通過的程式碼;若要把 `HF_AUTH_REQUIRED`、`HF_NO_GGUF` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T194a)
  - 🧪 `testplan.md` § US4-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7
- [X] T195a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-10 的測試(依序以 `HF_UNREACHABLE`、`HF_SERVER_ERROR`、`HF_BAD_RESPONSE`、`HF_TIMEOUT` 各展開一次 `bartowski/SmolLM2-135M-Instruct-GGUF`;分隔註解寫 `# ---- 004 US4-API-10`(`plan.md` § 待決問題 Q34)),執行確認它因為「展開只接了 422 那兩個代碼,其他 `AdapterError` 往上拋回 500」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`
  - 📎 `spec.md` § FR-016、NFR-006、使用者故事 4 驗收情境 6
- [X] T195b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py` 只寫讓 US4-API-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T195a)
  - 🧪 `testplan.md` § US4-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`
  - 📎 `spec.md` § FR-016、NFR-006、使用者故事 4 驗收情境 6
- [X] T196a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-11 的測試(情況 A:作者 `-bartowski`;B:模型 `Smol%20LM`(含空白);C:作者 `_x`;各展開一次;分隔註解寫 `# ---- 004 US4-API-11`(`plan.md` § 待決問題 Q34)),執行確認它因為「以 FastAPI 的 `Path(pattern=...)` 驗,回預設的 422」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`
  - 📎 `spec.md` § FR-014、NFR-006
- [X] T196b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py`、`src/cgb/domain/errors.py` 只寫讓 US4-API-11 通過的程式碼;新代碼 `INVALID_HF_MODEL_ID` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T196a)
  - 🧪 `testplan.md` § US4-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`
  - 📎 `spec.md` § FR-014、NFR-006
- [X] T197a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US4-API-12 的測試(試算 `[HF_Q4, "qwen2.5:7b"]`(`HF_Q4` = `hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M`);分隔註解寫 `# ---- 004 US4-API-12`(`plan.md` § 待決問題 Q34)),執行確認它因為「照現況以 `split(":", 1)` 把 `hf.co/...` 送去官方 registry,`model_library.get_manifest` 收到 `name="hf.co/bartowski/..."`」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-014、使用者故事 4 驗收情境 3
- [X] T197b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 只寫讓 US4-API-12 通過的程式碼;試算與加入下載的取大小改用故事 3 的分流函式(依賴 T083b),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T197a)
  - 🧪 `testplan.md` § US4-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-014、使用者故事 4 驗收情境 3
- [X] T198a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US4-API-13 的測試(加入 `[HF_Q4, "qwen2.5:7b"]`,等第一筆變成下載中後 `GET /api/downloads`;放行閘門,等兩筆都 `completed`;分隔註解寫 `# ---- 004 US4-API-13`(`plan.md` § 待決問題 Q34));T197b 的取大小分流與既有的單一佇列 worker(`src/cgb/services/downloads.py`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「hf.co 的項目另開一個佇列或背景工作,兩筆同時下載」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-014、使用者故事 4 驗收情境 3
- [X] T198b [US4] 🟢 /tdd 綠燈:US4-API-13 由 T197b 的取大小分流與既有的單一佇列 worker(`src/cgb/services/downloads.py`) 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 只寫讓 US4-API-13 通過的程式碼(依賴 T198a)
  - 🧪 `testplan.md` § US4-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-014、使用者故事 4 驗收情境 3
- [X] T199a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US4-API-14 的測試(加入 `[HF_Q4]`;分隔註解寫 `# ---- 004 US4-API-14`(`plan.md` § 待決問題 Q34)),執行確認它因為「`job_payload()` 只在 REST 回應補 `source`,SSE 推送用另一份舊的組法,少了 `source` 或寫成 `library`」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`);`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-014
- [X] T199b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 只寫讓 US4-API-14 通過的程式碼;`job_payload()` 帶 `source`(依名稱前綴推出,不另存;`plan.md` § 待決問題 Q22),REST 回應與 SSE 推送共用,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T199a)
  - 🧪 `testplan.md` § US4-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`);`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-014
- [X] T200a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US4-API-15 的測試(試算 `[HF_Q4, "qwen2.5:7b"]`;加入同一批;之後 `GET /api/downloads`;對照組:加入 `["qwen2.5:7b"]`;分隔註解寫 `# ---- 004 US4-API-15`(`plan.md` § 待決問題 Q34));T197b 把 hf.co 的大小一起加進總大小已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「空間檢查只加總官方的大小,hf.co 那 105,455,145 沒算進去,4,683,087,332 ≤ 4,700,000,000 就放行」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-014、使用者故事 4 驗收情境 3
- [X] T200b [US4] 🟢 /tdd 綠燈:US4-API-15 由 T197b 把 hf.co 的大小一起加進總大小 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 只寫讓 US4-API-15 通過的程式碼(依賴 T200a)
  - 🧪 `testplan.md` § US4-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-014、使用者故事 4 驗收情境 3
- [X] T201a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US4-API-16 的測試(情況 A:試算 `["qwen2.5:7b", "hf.co/google/gemma-3-1b-it-qat-q4_0-gguf:Q4_0"]`;B:`["hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_L"]`;C:`["hf.co/Qwen/Qwen2.5-0.5B-Instruct"]`;分隔註解寫 `# ---- 004 US4-API-16`(`plan.md` § 待決問題 Q34)),執行確認它因為「HF 的 422 類代碼照官方 `_LIBRARY_STATUS` 的表查不到,`KeyError` 回 500」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7;`plan.md` § 待決問題 Q20
- [X] T201b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US4-API-16 通過的程式碼;若要把 `HF_QUANT_UNAVAILABLE` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T201a)
  - 🧪 `testplan.md` § US4-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7;`plan.md` § 待決問題 Q20
- [X] T202a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US4-API-17 的測試(加入 `["qwen2.5:7b", "hf.co/google/gemma-3-1b-it-qat-q4_0-gguf:Q4_0"]`;加入 `["hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_L"]`;之後 `GET /api/downloads`;分隔註解寫 `# ---- 004 US4-API-17`(`plan.md` § 待決問題 Q34)),執行確認它因為「前面的 `qwen2.5:7b` 已經寫進佇列、取到第二個才失敗,沒撤回」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7
- [X] T202b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 只寫讓 US4-API-17 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T202a)
  - 🧪 `testplan.md` § US4-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-015、使用者故事 4 驗收情境 7
- [X] T203a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US4-API-18 的測試(每個代碼(`HF_UNREACHABLE`、`HF_SERVER_ERROR`、`HF_BAD_RESPONSE`、`HF_TIMEOUT`)各試算一次、加入一次 `[HF_Q4, "qwen2.5:7b"]`(共 8 次),最後 `GET /api/downloads`;分隔註解寫 `# ---- 004 US4-API-18`(`plan.md` § 待決問題 Q34)),執行確認它因為「HF 失敗被歸成 `LIBRARY_*`(套到官方的對應表)」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-016、NFR-006
- [X] T203b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 只寫讓 US4-API-18 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T203a)
  - 🧪 `testplan.md` § US4-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-016、NFR-006
- [X] T204a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US4-API-19 的測試(試算 `["hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"]`;加入同一個;試算 `["qwen2.5:Latest"]`;分隔註解寫 `# ---- 004 US4-API-19`(`plan.md` § 待決問題 Q34)),執行確認它因為「照 003 照原樣比對(`model in local`),大小寫不同就當成沒下載、試算多算一份」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-018、FR-014
- [X] T204b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/domain/model_name.py` 只寫讓 US4-API-19 通過的程式碼;「已下載」比對改用 `src/cgb/domain/model_name.py` 的 `match_key`;同一個任務刪掉 `tests/integration/test_api_downloads.py` 的 `test_版本大小寫不同的名稱照原樣比對_不當成已下載`(003 US1-API-12,由 US4-API-19 則4 取代,`plan.md` § 待決問題 Q54),執行全部測試確認都通過、不留 skip;看到要整理的地方記進重構清單(依賴 T204a)
  - 🧪 `testplan.md` § US4-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-018、FR-014
- [X] T205a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US4-API-20 的測試(試算 `["hf.co/bartowski/smollm2-135m-instruct-gguf:q4_k_m"]`;加入 `["qwen2.5:7b", "hf.co/BARTOWSKI/SmolLM2-135M-Instruct-GGUF:Q4_k_m"]`;之後 `GET /api/downloads`;分隔註解寫 `# ---- 004 US4-API-20`(`plan.md` § 待決問題 Q34)),執行確認它因為「「已在佇列」照原樣比對 `DownloadJob.model`,大小寫不同的寫法通過檢查、寫入時撞 `lower()` 唯一索引回 500,或寫進第二筆重複下載」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-018
- [X] T205b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 只寫讓 US4-API-20 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T205a)
  - 🧪 `testplan.md` § US4-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-018
- [X] T206a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US4-API-21 的測試(試算 `["hf.co/bartowski/SmolLM2-135M-Instruct-GGUF", "hf.co/Bartowski/smollm2-135m-instruct-gguf:LATEST", HF_Q4]`;加入同一批;之後 `GET /api/downloads`;分隔註解寫 `# ---- 004 US4-API-21`(`plan.md` § 待決問題 Q34)),執行確認它因為「同一批合併照原樣去重(`dict.fromkeys`),`:LATEST` 的寫法多成一筆、寫入時撞唯一索引回 500」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-018、邊界情況
- [X] T206b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 只寫讓 US4-API-21 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T206a)
  - 🧪 `testplan.md` § US4-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`、`paths./downloads.get`、`components.schemas.DownloadQueue`、`components.schemas.DownloadJob`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-018、邊界情況
- [X] T207a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US4-API-22 的測試(試算 `["hf.co/bartowski/SmolLM2-135M-Instruct-GGUF"]`;分隔註解寫 `# ---- 004 US4-API-22`(`plan.md` § 待決問題 Q34));T204b 以補過版本的比對鍵比對(`latest` 與 `Q4_K_M` 是不同的鍵)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「比對鍵只取 `:` 前面的 repo,或把 `latest` 當成「任何量化版本」,`HF_Q4` 被當成已下載回 409 `MODEL_ALREADY_DOWNLOADED`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-018
- [X] T207b [US4] 🟢 /tdd 綠燈:US4-API-22 由 T204b 以補過版本的比對鍵比對(`latest` 與 `Q4_K_M` 是不同的鍵) 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 只寫讓 US4-API-22 通過的程式碼(依賴 T207a)
  - 🧪 `testplan.md` § US4-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-018
- [X] T208a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US4-API-23 的測試(試算與加入各送一次:情況 A `["qwen2.5:7b", "huggingface.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M"]`;B `["HF.CO/bartowski/SmolLM2-135M-Instruct-GGUF"]`;C `["Qwen2.5:7b"]`;D `["hf.co/bartowski"]`;E `["hf.co/-bartowski/x"]`;F `{"models": []}`;對照組 `["hf.co/Bartowski/SmolLM2-135M-Instruct-GGUF:q4_k_m"]`;分隔註解寫 `# ---- 004 US4-API-23`(`plan.md` § 待決問題 Q34)),執行確認它因為「照現況完全不驗名稱,先回 503 `NO_READY_SESSION`(違反 `x-download-check-order` 的「格式最先、不需要工作階段」)」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-018、NFR-006
- [X] T208b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/domain/model_name.py`、`src/cgb/domain/errors.py` 只寫讓 US4-API-23 通過的程式碼;名稱格式檢查排在最前、不需要工作階段(`info.x-download-check-order` (1));新代碼 `EMPTY_MODEL_LIST` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T208a)
  - 🧪 `testplan.md` § US4-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`、`paths./downloads.post`、`components.schemas.DownloadJobList`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-018、NFR-006
- [X] T209a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US4-API-24 的測試(重新排隊 `HF_Q4` 那一筆;重新排隊 `qwen2.5:7b` 那一筆(對照組);之後 `GET /api/downloads`;分隔註解寫 `# ---- 004 US4-API-24`(`plan.md` § 待決問題 Q34)),執行確認它因為「重新排隊照現況不看執行環境,直接 `requeue`、重下載一次」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`、`paths./downloads/{id}/retry.post`、`components.schemas.DownloadJob`、`paths./downloads.get`、`components.schemas.DownloadQueue`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-018
- [X] T209b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py` 只寫讓 US4-API-24 通過的程式碼;重新排隊前讀執行環境上的模型清單,已下載的回 409 `MODEL_ALREADY_DOWNLOADED`;同一個任務把 `tests/integration/test_api_downloads.py` 的 `test_重新排隊排到最後_清除已完成只清完成的` 改成先開工作階段(`plan.md` § 待決問題 Q54),執行全部測試確認都通過、不留 skip;看到要整理的地方記進重構清單(依賴 T209a)
  - 🧪 `testplan.md` § US4-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`、`paths./downloads/{id}/retry.post`、`components.schemas.DownloadJob`、`paths./downloads.get`、`components.schemas.DownloadQueue`(`info.x-model-name-rule`、`info.x-download-check-order`、`info.x-queue-clearing`)
  - 📎 `spec.md` § FR-018
- [X] T210a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US4-API-25 的測試(情況 A:重新排隊 id 9999;B:重新排隊下載中的 `qwen2.5:7b`;C、D、E:`list_local_models.raises(code)` 依序為 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,各重新排隊失敗的那一筆;F:`fakes.tunnel.open_tunnel.gate()`、`fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE")`,等 `GET /api/session` 為 `reconnecting` 後重新排隊失敗的那一筆;分隔註解寫 `# ---- 004 US4-API-25`(`plan.md` § 待決問題 Q34)),執行確認它因為「新加的「已下載」檢查讀模型清單時沒接 `AdapterError`,C~E 回 500」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/{id}/retry.post`、`components.schemas.DownloadJob`、`components.schemas.Error`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018、NFR-006
- [X] T210b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US4-API-25 通過的程式碼;新代碼 `DOWNLOAD_NOT_RETRYABLE` 加進 `src/cgb/domain/errors.py` 的 `MESSAGES`,同一個任務在 `tests/e2e/test_locale.py` 的 `API_ERRORS` 加同一個代碼(該檔斷言兩份相等)(`plan.md` § 待決問題 Q56),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T210a)
  - 🧪 `testplan.md` § US4-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/{id}/retry.post`、`components.schemas.DownloadJob`、`components.schemas.Error`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018、NFR-006
- [X] T211a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US4-API-26 的測試(加入 `[HF_Q4]`,`wait_queue` 等它 `completed`;之後 `set_tags(fakes, tag(HF_Q4, 105_455_694))`,`catalog_names(ui_client)`;分隔註解寫 `# ---- 004 US4-API-26`(`plan.md` § 待決問題 Q34));既有的模型目錄(`src/cgb/services/catalog.py` 列出 `list_local_models` 的每一筆,不過濾名稱)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「目錄濾掉不是官方名稱的項目(例如套 001 的 `ModelName` pattern 或排除含 `/` 的名稱),hf.co 模型下載完成卻不出現」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-API-26
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-014、使用者故事 4 驗收情境 4
- [X] T211b [US4] 🟢 /tdd 綠燈:US4-API-26 由 既有的模型目錄(`src/cgb/services/catalog.py` 列出 `list_local_models` 的每一筆,不過濾名稱) 滿足,確認 `src/cgb/services/catalog.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/catalog.py` 只寫讓 US4-API-26 通過的程式碼(依賴 T211a)
  - 🧪 `testplan.md` § US4-API-26
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § FR-014、使用者故事 4 驗收情境 4
- [X] T212a [US4] 🔴 /tdd 紅燈:在 `tests/unit/test_model_name.py` 寫 US4-API-27 的測試(呼叫 `with_version` 與 `source_of`(`plan.md` § 待決問題 Q49);分隔註解寫 `# ---- 004 US4-API-27`(`plan.md` § 待決問題 Q34)),執行確認它因為「補版本時以 `/` 或 `.` 判斷,把 `hf.co` 的 `.co` 當成版本分隔」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ModelName`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018
- [X] T212b [US4] 🟢 /tdd 綠燈:在 `src/cgb/domain/model_name.py` 只寫讓 US4-API-27 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T212a)
  - 🧪 `testplan.md` § US4-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ModelName`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018
- [X] T213a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/unit/test_model_name.py` 寫 US4-API-28 的測試(呼叫 `match_key`(`plan.md` § 待決問題 Q49);分隔註解寫 `# ---- 004 US4-API-28`(`plan.md` § 待決問題 Q34));T076b 在 `src/cgb/domain/model_name.py` 建立的 `match_key`已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「比對鍵只用 `lower()` 沒先補版本,沒寫版本與 `LATEST` 不相等」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-API-28
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ModelName`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018
- [X] T213b [US4] 🟢 /tdd 綠燈:US4-API-28 由 T076b 在 `src/cgb/domain/model_name.py` 建立的 `match_key` 滿足,確認 `src/cgb/domain/model_name.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/domain/model_name.py` 只寫讓 US4-API-28 通過的程式碼(依賴 T213a)
  - 🧪 `testplan.md` § US4-API-28
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ModelName`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018
- [X] T214a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/unit/test_model_name.py` 寫 US4-API-29 的測試(呼叫 `is_valid`(`plan.md` § 待決問題 Q49);分隔註解寫 `# ---- 004 US4-API-29`(`plan.md` § 待決問題 Q34));T038b 在 `src/cgb/domain/model_name.py` 建立的 `is_valid`已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「pattern 對整條名稱不分大小寫」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-API-29
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ModelName`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018;`plan.md` § 待決問題 Q9
- [X] T214b [US4] 🟢 /tdd 綠燈:US4-API-29 由 T038b 在 `src/cgb/domain/model_name.py` 建立的 `is_valid` 滿足,確認 `src/cgb/domain/model_name.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/domain/model_name.py` 只寫讓 US4-API-29 通過的程式碼(依賴 T214a)
  - 🧪 `testplan.md` § US4-API-29
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ModelName`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018;`plan.md` § 待決問題 Q9
- [X] T215a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US4-API-30 的測試(試算 `["hf.co/a/b:Q4_K_M", "hf.co/c/d:Q8_0", "hf.co/e/f"]`(三個依序取,共約 0.45 秒);分隔註解寫 `# ---- 004 US4-API-30`(`plan.md` § 待決問題 Q34));T197b 經 `HuggingFaceHub.get_manifest` 取每一個大小(每請求期限,不套展開的整體期限)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「試算取大小重用展開的整體期限(包一層 `asyncio.timeout(展開期限)`),超過 0.3 秒就回 504 `HF_TIMEOUT`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-API-30
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § NFR-005
- [X] T215b [US4] 🟢 /tdd 綠燈:US4-API-30 由 T197b 經 `HuggingFaceHub.get_manifest` 取每一個大小(每請求期限,不套展開的整體期限) 滿足,確認 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py`、`src/cgb/api/downloads.py` 只寫讓 US4-API-30 通過的程式碼(依賴 T215a)
  - 🧪 `testplan.md` § US4-API-30
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § NFR-005
- [X] T216a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-31 的測試(每一輪各送一次搜尋 `q=x`、展開 `a/b`、試算與加入 `["hf.co/a/b:Q4_K_M"]`;分隔註解寫 `# ---- 004 US4-API-31`(`plan.md` § 待決問題 Q34)),執行確認它因為「把 `AdapterError.message` 或 `str(error)` 放進 `message`」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-31
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`、`paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`paths./downloads.post`、`components.schemas.DownloadJobList`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § NFR-006、SC-006、FR-016;`plan.md` § 待決問題 Q69
- [X] T216b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py`、`src/cgb/api/downloads.py`、`src/cgb/domain/errors.py` 只寫讓 US4-API-31 通過的程式碼;四個操作的 `HF_*` 狀態碼共用 `info.x-hf-error-status` 一張對應(502、504、422,`plan.md` § 待決問題 Q69),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T216a)
  - 🧪 `testplan.md` § US4-API-31
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/search.get`、`components.schemas.HfSearchPage`、`components.schemas.HfModel`、`components.schemas.Error`、`paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`paths./downloads.post`、`components.schemas.DownloadJobList`(`info.x-model-name-rule`、`info.x-download-check-order`)
  - 📎 `spec.md` § NFR-006、SC-006、FR-016;`plan.md` § 待決問題 Q69
- [X] T253a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_huggingface.py` 寫 US4-API-32 的測試(B、C、D 三種情況各展開 `bartowski/SmolLM2-135M-Instruct-GGUF` 一次,記下送出與回應的時間;分隔註解寫 `# ---- 004 US4-API-32`(`plan.md` § 待決問題 Q34)),執行確認它因為「兩段串接(先讀模型清單再問 Hugging Face,或反過來),或 Hugging Face 失敗後沒取消模型清單的讀取」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-32
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`(`info.x-hf-error-status`)
  - 📎 `spec.md` § FR-014、FR-016、SC-004、NFR-006;`plan.md` § 待決問題 Q67
- [X] T253b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/huggingface.py` 只寫讓 US4-API-32 通過的程式碼;Hugging Face 這一段與讀模型清單同時開始、都從收到請求起算 `hf_expand_deadline`;Hugging Face 先完成時只等模型清單到同一個期限;Hugging Face 逾時或 400 以外的失敗時取消模型清單的讀取(`contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get` 的時間上限 (a)~(d),`plan.md` § 待決問題 Q67),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T253a)
  - 🧪 `testplan.md` § US4-API-32
  - ⚙ `contracts/ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get`、`components.schemas.HfQuantList`、`components.schemas.HfQuant`、`components.schemas.Error`(`info.x-hf-error-status`)
  - 📎 `spec.md` § FR-014、FR-016、SC-004、NFR-006;`plan.md` § 待決問題 Q67
- [X] T254a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/integration/test_api_downloads.py` 寫 US4-API-33 的測試(送 `POST /api/downloads/{id}/retry`;分隔註解寫 `# ---- 004 US4-API-33`(`plan.md` § 待決問題 Q34));既有 `src/cgb/services/downloads.py` 的 `DownloadsService.retry`(只 `requeue` 與推送,不讀剩餘磁碟)與 T209b、T210b 加的「先確認模型不在執行環境上」已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「照 001 合約先讀剩餘磁碟,讀不到時回 503 `DISK_SPACE_UNKNOWN`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-API-33
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/{id}/retry.post`、`components.schemas.DownloadJob`、`components.schemas.Error`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018、NFR-006;`plan.md` § 待決問題 Q56
- [X] T254b [US4] 🟢 /tdd 綠燈:US4-API-33 由 既有 `src/cgb/services/downloads.py` 的 `DownloadsService.retry`(只 `requeue` 與推送,不讀剩餘磁碟)與 T209b、T210b 加的「先確認模型不在執行環境上」滿足,確認 `src/cgb/services/downloads.py` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/services/downloads.py` 只寫讓 US4-API-33 通過的程式碼(依賴 T254a)
  - 🧪 `testplan.md` § US4-API-33
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/{id}/retry.post`、`components.schemas.DownloadJob`、`components.schemas.Error`(`info.x-model-name-rule`)
  - 📎 `spec.md` § FR-018、NFR-006;`plan.md` § 待決問題 Q56
- [X] T217 [US4] 🔵 /tdd 重構:在全部測試綠燈下整理 T186b~T216b、T253b~T254b 記下的重構清單(範圍限 `src/cgb/api/`、`src/cgb/services/`、`src/cgb/domain/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/`、`tests/unit/test_model_name.py` 的斷言(依賴 T254b)
  - 🧪 `testplan.md` § US4-API-01~US4-API-31、US4-API-32~US4-API-33
  - 📎 `testplan.md` § 5.3

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(Playwright)接測試行程內真的後端(`tests/e2e/conftest.py` 的 `e2e_servers`,UI 127.0.0.1:8781),轉接層用替身;e2e 用固定 port,同一時間只跑一份
> Hugging Face 與官方模型庫用替身(`FakeHuggingFaceHub`、`FakeModelLibrary`),遠端 Ollama 用 `FakeRemoteOllama`(`testplan.md` § 5.4)

- [X] T218a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us4_hf.py` 寫 US4-AJ-01 的測試(在 `#hf-q` 輸入 `qwen` 搜尋;按「載入更多」;分隔註解寫 `# ---- 004 US4-AJ-01`(`plan.md` § 待決問題 Q34)),執行確認它因為「載入更多送頁碼而不是原樣的 `cursor`」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-01
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`[data-state="hf-idle"]`、`[data-state="hf-searching"]`
  - 📎 `spec.md` § FR-013
- [X] T218b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js`、`src/cgb/static/js/api.js` 只寫讓 US4-AJ-01 通過的程式碼;下載頁的 Hugging Face 搜尋區與「載入更多」照 `prototype/library.html`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T218a)
  - 🧪 `testplan.md` § US4-AJ-01
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`[data-state="hf-idle"]`、`[data-state="hf-searching"]`
  - 📎 `spec.md` § FR-013
- [X] T219a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us4_hf.py` 寫 US4-AJ-02 的測試(搜尋後展開 `bartowski/SmolLM2-135M-Instruct-GGUF`;分隔註解寫 `# ---- 004 US4-AJ-02`(`plan.md` § 待決問題 Q34)),執行確認它因為「已下載的比對分大小寫,`q4_k_m` 對不到 `Q4_K_M`」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-02
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`
  - 📎 `spec.md` § FR-014、FR-018
- [X] T219b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/js/library.js`、`src/cgb/static/style.css` 只寫讓 US4-AJ-02 通過的程式碼;展開量化版本照 `prototype/library.html`;把 `prototype/style.css` 的「004:Hugging Face 搜尋結果的展開」區段搬進 `src/cgb/static/style.css`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T219a)
  - 🧪 `testplan.md` § US4-AJ-02
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`
  - 📎 `spec.md` § FR-014、FR-018
- [X] T220a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us4_hf.py` 寫 US4-AJ-03 的測試(展開後勾 `Q8_0`,在官方模型庫搜尋並勾 `qwen2.5`,按「加入下載」;在確認視窗按「確定」;分隔註解寫 `# ---- 004 US4-AJ-03`(`plan.md` § 待決問題 Q34)),執行確認它因為「Hugging Face 的勾選走另一個加入流程、沒有和官方一起試算」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-03
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`[data-state="checking"]`、`[data-state="no-space"]`、`[data-state="no-session"]`
  - 📎 `spec.md` § FR-014;`plan.md` § 待決問題 Q66
- [X] T220b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/js/library.js` 只寫讓 US4-AJ-03 通過的程式碼;⚙ 裡的 `[data-state="no-space"]`、`[data-state="no-session"]` 是沿用 001 的畫面,這個任務不改、不新增斷言(`plan.md` § 待決問題 Q66),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T220a)
  - 🧪 `testplan.md` § US4-AJ-03
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`[data-state="checking"]`、`[data-state="no-space"]`、`[data-state="no-session"]`
  - 📎 `spec.md` § FR-014;`plan.md` § 待決問題 Q66
- [X] T221a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us4_hf.py` 寫 US4-AJ-04 的測試(在 `#hf-q` 搜尋 `qwen`;再在 `#lib-q` 搜尋 `qwen2.5`;分隔註解寫 `# ---- 004 US4-AJ-04`(`plan.md` § 待決問題 Q34)),執行確認它因為「HF 失敗時整個下載頁進入錯誤狀態,官方搜尋也被擋」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-04
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`[data-state="lib-idle"]`、`[data-state="lib-searching"]`
  - 📎 `spec.md` § FR-016
- [X] T221b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/js/library.js` 只寫讓 US4-AJ-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T221a)
  - 🧪 `testplan.md` § US4-AJ-04
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`[data-state="lib-idle"]`、`[data-state="lib-searching"]`
  - 📎 `spec.md` § FR-016
- [X] T222a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us4_hf.py` 寫 US4-AJ-05 的測試(搜尋 `qwne`;分隔註解寫 `# ---- 004 US4-AJ-05`(`plan.md` § 待決問題 Q34)),執行確認它因為「空結果被當成失敗顯示「暫時無法搜尋」」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-05
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`
  - 📎 `spec.md` § FR-013
- [X] T222b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/js/library.js` 只寫讓 US4-AJ-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T222a)
  - 🧪 `testplan.md` § US4-AJ-05
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`
  - 📎 `spec.md` § FR-013
- [X] T223a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us4_hf.py` 寫 US4-AJ-06 的測試(各在直接輸入名稱的欄位輸入名稱、按「加入下載」;分隔註解寫 `# ---- 004 US4-AJ-06`(`plan.md` § 待決問題 Q34)),執行確認它因為「試算沒先查 HF manifest,直接加入佇列讓 Ollama 拉取失敗」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-06
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`[data-state="not-found"]`
  - 📎 `spec.md` § FR-015;`plan.md` § 待決問題 Q66
- [X] T223b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/js/library.js` 只寫讓 US4-AJ-06 通過的程式碼;⚙ 裡的 `[data-state="not-found"]` 是沿用 001 的畫面,這個任務不改、不新增斷言(`plan.md` § 待決問題 Q66),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T223a)
  - 🧪 `testplan.md` § US4-AJ-06
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`[data-state="not-found"]`
  - 📎 `spec.md` § FR-015;`plan.md` § 待決問題 Q66
- [X] T224a [US4] 🔴 /tdd 紅燈(對照組):在 `tests/e2e/test_004_us4_hf.py` 寫 US4-AJ-07 的測試(打開模型頁;再打開對話頁的模型選單;分隔註解寫 `# ---- 004 US4-AJ-07`(`plan.md` § 待決問題 Q34));既有 `src/cgb/static/js/models.js` 的模型目錄與 T059b 的對話頁模型選單(都列 `GET /api/models` 的每一筆)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「模型目錄或對話頁的模型清單過濾掉含 `/` 或 `hf.co/` 的名稱」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US4-AJ-07
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`、`[data-state="cat-normal"]`、`[data-state="cat-empty"]`;`prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-014;`plan.md` § 待決問題 Q66
- [X] T224b [US4] 🟢 /tdd 綠燈:US4-AJ-07 由 既有 `src/cgb/static/js/models.js` 的模型目錄與 T059b 的對話頁模型選單(都列 `GET /api/models` 的每一筆) 滿足,確認 `src/cgb/static/js/models.js`、`src/cgb/static/js/chat.js` 不需要為它改程式碼;⚙ 裡的 `[data-state="cat-empty"]` 是沿用 001 的畫面,這個任務不改、不新增斷言(`plan.md` § 待決問題 Q66),執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/models.js`、`src/cgb/static/js/chat.js` 只寫讓 US4-AJ-07 通過的程式碼(依賴 T224a)
  - 🧪 `testplan.md` § US4-AJ-07
  - ⚙ `prototype/models.html` § `#queue-panel`、`#queue`、`#qc-text`、`#auto-notice`、`#catalog`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`、`[data-state="auto-running"]`、`[data-state="cat-no-session"]`、`[data-state="cat-normal"]`、`[data-state="cat-empty"]`;`prototype/chat.html` § `#model`、`#input`、`#send`、`#stop`、`#clear`、`#log`、`[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-stopped"]`、`[data-state="turn-error"]`、`[data-state="turn-interrupted"]`、`[data-state="turn-bad-response"]`、`[data-state="turn-lost"]`、`[data-state="turn-timeout"]`、`[data-state="turn-not-found"]`、`[data-state="turn-unavailable"]`、`[data-state="turn-start-timeout"]`、`[data-state="turn-norate"]`、`[data-state="turn-thinking"]`
  - 📎 `spec.md` § FR-014;`plan.md` § 待決問題 Q66
- [X] T225a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us4_hf.py` 寫 US4-AJ-08 的測試(每種狀態取那個區塊的 `innerText`,去掉模型名稱與量化版本;分隔註解寫 `# ---- 004 US4-AJ-08`(`plan.md` § 待決問題 Q34)),執行確認它因為「Hugging Face 或 Ollama 的英文錯誤原文直接顯示在畫面上」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-08
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`
  - 📎 `spec.md` § NFR-007、FR-016
- [X] T225b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/js/library.js` 只寫讓 US4-AJ-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T225a)
  - 🧪 `testplan.md` § US4-AJ-08
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`
  - 📎 `spec.md` § NFR-007、FR-016
- [X] T255a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us4_hf.py` 寫 US4-AJ-09 的測試(在直接輸入名稱的欄位輸入 `hf.co/ggml-org/Qwen2.5-VL-7B-Instruct-mmproj-GGUF:Q4_K_M`、按「加入下載」;分隔註解寫 `# ---- 004 US4-AJ-09`(`plan.md` § 待決問題 Q34)),執行確認它因為「收到 `HF_QUANT_UNAVAILABLE` 時說明只寫「沒有這個量化版本」,看不出是 repo 不是 GGUF」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-09
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`#name-form`、`[data-state="direct-unchecked"]`
  - 📎 `spec.md` § FR-015;`plan.md` § 待決問題 Q20
- [X] T255b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js` 只寫讓 US4-AJ-09 通過的程式碼;`[data-state="hf-quant-unavailable"]` 的說明照 `prototype/library.html` 補「不是 GGUF」,不做 `hf-no-gguf` 確認框(分身決策紀錄 D99),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T255a)
  - 🧪 `testplan.md` § US4-AJ-09
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`#name-form`、`[data-state="direct-unchecked"]`
  - 📎 `spec.md` § FR-015;`plan.md` § 待決問題 Q20
- [X] T256a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us4_hf.py` 寫 US4-AJ-10 的測試(依情況讓 `list_quants` 丟 `HF_UNREACHABLE`、`HF_SERVER_ERROR`、`HF_BAD_RESPONSE`,各展開一次;分隔註解寫 `# ---- 004 US4-AJ-10`(`plan.md` § 待決問題 Q34)),執行確認它因為「前端只把 `HF_TIMEOUT` 對到 `hf-expand-down`,502 的三個代碼落到預設分支」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-10
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`#name-form`、`[data-state="direct-unchecked"]`
  - 📎 `spec.md` § FR-016
- [X] T256b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js` 只寫讓 US4-AJ-10 通過的程式碼;展開的 502、504 四個代碼都顯示 `[data-state="hf-expand-down"]`,說明照 `prototype/library.html`,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T256a)
  - 🧪 `testplan.md` § US4-AJ-10
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`#name-form`、`[data-state="direct-unchecked"]`
  - 📎 `spec.md` § FR-016
- [X] T257a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us4_hf.py` 寫 US4-AJ-11 的測試(沒有工作階段時在直接輸入名稱的欄位輸入 `hf.co/unsloth/Qwen3-0.6B-GGUF:Q8_0`、按「加入勾選」;分隔註解寫 `# ---- 004 US4-AJ-11`(`plan.md` § 待決問題 Q34)),執行確認它因為「沒有工作階段時照常送 `POST /api/downloads/estimate`,收到 503 就擋下不加入勾選」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-11
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`#name-form`、`[data-state="direct-unchecked"]`
  - 📎 `spec.md` § FR-014、FR-015
- [X] T257b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js` 只寫讓 US4-AJ-11 通過的程式碼;沒有就緒的工作階段時只檢查名稱格式就加入勾選,顯示 `[data-state="direct-unchecked"]`,不送試算(分身決策紀錄 D97),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T257a)
  - 🧪 `testplan.md` § US4-AJ-11
  - ⚙ `prototype/library.html` § `#hf-form`、`#hf-q`、`#hf-results`、`#hf-more`、`#tray`、`#add`、`#confirm-table`、`#confirm-go`、`#lib-form`、`#lib-q`、`#lib-results`、`[data-state="hf-results"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]`、`[data-state="confirm"]`、`[data-state="lib-results"]`、`#name-form`、`[data-state="direct-unchecked"]`
  - 📎 `spec.md` § FR-014、FR-015
- [X] T226 [US4] 🔵 /tdd 重構:在全部測試綠燈下整理 T218b~T225b、T255b~T257b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T257b)
  - 🧪 `testplan.md` § US4-AJ-01~US4-AJ-08、US4-AJ-09~US4-AJ-11
  - 📎 `testplan.md` § 5.4

### 介面覆蓋(US4)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved`(故事 4 擴充:hf.co 名稱、來源分流與不分大小寫的比對) | T199b | T199a |
| `huggingface.openapi.yaml` § `paths./api/models.get` | T136b~T140b、T153b~T159b、T162b~T166b | T136a~T140a、T153a~T159a、T162a~T166a |
| `huggingface.openapi.yaml` § `paths./api/models/{author}/{model}/tree/main.get` | T141b~T143b、T146b、T153b~T158b、T160b、T162b~T165b | T141a~T143a、T146a、T153a~T158a、T160a、T162a~T165a |
| `huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get` | T144b~T147b、T153b~T155b、T157b~T158b、T161b~T165b、T169b | T144a~T147a、T153a~T155a、T157a~T158a、T161a~T165a、T169a |
| `remote-ollama.openapi.yaml` § `paths./api/pull.post` | T171b~T184b | T171a~T184a |
| `ui.openapi.yaml` § `paths./huggingface/search.get` | T186b~T191b、T216b | T186a~T191a、T216a |
| `ui.openapi.yaml` § `paths./huggingface/models/{author}/{model}/quants.get` | T191b~T196b、T216b | T191a~T196a、T216a |
| `ui.openapi.yaml` § `paths./curated.get`(故事 4 擴充:hf.co 名稱、來源分流與不分大小寫的比對) | T191b | T191a |
| `ui.openapi.yaml` § `paths./downloads.get`(故事 4 擴充:hf.co 名稱、來源分流與不分大小寫的比對) | T198b、T200b、T202b~T203b、T205b~T206b、T209b | T198a、T200a、T202a~T203a、T205a~T206a、T209a |
| `ui.openapi.yaml` § `paths./downloads.post`(故事 4 擴充:hf.co 名稱、來源分流與不分大小寫的比對) | T198b~T200b、T202b~T206b、T208b~T209b、T211b、T216b | T198a~T200a、T202a~T206a、T208a~T209a、T211a、T216a |
| `ui.openapi.yaml` § `paths./downloads/estimate.post` | T191b、T197b、T200b~T201b、T203b~T208b、T215b~T216b | T191a、T197a、T200a~T201a、T203a~T208a、T215a~T216a |
| `ui.openapi.yaml` § `paths./downloads/{id}/retry.post`(故事 4 擴充:hf.co 名稱、來源分流與不分大小寫的比對) | T209b~T210b | T209a~T210a |
| `chat.html` § `[data-state="chat-ready"]`、`[data-state="chat-no-session"]`、`[data-state="chat-no-models"]`、`[data-state="turn-idle"]`、`[data-state="turn-loading"]`、`[data-state="turn-thinking"]`、`[data-state="turn-streaming"]`、`[data-state="turn-stopped"]`、`[data-state="turn-norate"]`、`[data-state="turn-error"]`、`[data-state="turn-timeout"]`、`[data-state="turn-lost"]`(故事 4 擴充:hf.co 名稱、來源分流與不分大小寫的比對) | T224b | T224a |
| `library.html` § `[data-state="lib-idle"]`、`[data-state="lib-searching"]` | T221b | T221a |
| `library.html` § `[data-state="lib-results"]`、`[data-state="hf-results"]`、`[data-state="hf-expand-down"]`、`[data-state="hf-empty"]`、`[data-state="hf-down"]`、`[data-state="confirm"]`、`[data-state="hf-auth-required"]`、`[data-state="hf-quant-unavailable"]`、`[data-state="hf-size-down"]` | T218b~T223b、T225b、T255b~T256b | T218a~T223a、T225a、T255a~T256a |
| `library.html` § `[data-state="direct-unchecked"]` | T257b | T257a |
| `library.html` § `[data-state="hf-idle"]`、`[data-state="hf-searching"]` | T218b | T218a |
| `library.html` § `[data-state="checking"]` | T220b | T220a |
| `library.html` § `[data-state="no-space"]`、`[data-state="no-session"]`(沿用 001 的畫面,沒有新的斷言;完成報告列為未直接驗證,`plan.md` § 待決問題 Q66) | T220b | T220a |
| `library.html` § `[data-state="not-found"]`(沿用 001 的畫面,沒有新的斷言;完成報告列為未直接驗證,`plan.md` § 待決問題 Q66) | T223b | T223a |
| `models.html` § `[data-state="cat-normal"]` | T224b | T224a |
| `models.html` § `[data-state="cat-empty"]`(沿用 001 的畫面,沒有新的斷言;完成報告列為未直接驗證,`plan.md` § 待決問題 Q66) | T224b | T224a |
| `models.html` § `[data-state="cat-no-session"]`、`[data-state="auto-running"]`、`[data-state="queue-list"]`、`[data-state="queue-empty"]`、`[data-state="queue-cleared"]`(故事 4 擴充:hf.co 名稱、來源分流與不分大小寫的比對) | T224b | T224a |

### 測試案例覆蓋(US4)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US4-HF-01~US4-HF-38 | T132a~T169a | T132b~T169b | T170 |
| US4-RO-01~US4-RO-14 | T171a~T184a | T171b~T184b | T185 |
| US4-RO-15 | T252a | T252b | T185 |
| US4-API-01~US4-API-31 | T186a~T216a | T186b~T216b | T217 |
| US4-API-32~US4-API-33 | T253a~T254a | T253b~T254b | T217 |
| US4-AJ-01~US4-AJ-08 | T218a~T225a | T218b~T225b | T226 |
| US4-AJ-09~US4-AJ-11 | T255a~T257a | T255b~T257b | T226 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 全綠(含 T204b 刪掉、T209b 改寫的兩支舊測試,`tests/integration/test_fake_signatures.py` 比對到 `HuggingFaceHub`);重構任務前後的測試結果相同

---

## Phase 6: User Story 5 - 開工作階段時不列出開不到的 H100 (Priority: P3)

**Goal**: 開啟工作階段、變更執行階段類型與精選項目建議類型的選單只列 T4、L4、G4、A100,開啟的預設仍是 T4;紀錄與精選清單裡既有的 H100 照常顯示

**Independent Test**: 照 `testplan.md` § 6 的全部案例:跨端點驗收以 `uv run pytest tests/e2e/test_004_us5_h100.py` 執行全綠

### 跨端點驗收(`tests/e2e/`)

> 本故事只在 UI 選單隱藏 H100,後端的 `GpuType` 與 `INVALID_RUNTIME_TYPE` 不變,`testplan.md` § 6 沒有 E2、E4 的端點節(紀錄與精選清單的 H100 項目以 API 或 repos 直接寫入真的 SQLite)。端點節沒有任務,這一節由主 agent 直接開始

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(Playwright)接測試行程內真的後端(`tests/e2e/conftest.py` 的 `e2e_servers`,UI 127.0.0.1:8781),轉接層用替身;e2e 用固定 port,同一時間只跑一份

- [x] T227a [US5] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us5_h100.py` 寫 US5-AJ-01 的測試(打開首頁的開啟面板;分隔註解寫 `# ---- 004 US5-AJ-01`(`plan.md` § 待決問題 Q34)),執行確認它因為「只從畫面藏掉 H100 的文字、`<input value="H100">` 還在」這類實作而失敗
  - 🧪 `testplan.md` § US5-AJ-01
  - ⚙ `prototype/index.html` § `#open`、`#switch`、`[data-state="normal"]`、`[data-state="ready"]`、`[data-state="confirm-switch"]`
  - 📎 `spec.md` § FR-017、SC-005
- [x] T227b [US5] 🟢 /tdd 綠燈:在 `src/cgb/static/js/session.js` 只寫讓 US5-AJ-01 通過的程式碼;開啟面板的選單改用不含 H100 的清單,`RUNTIME_TYPES` 與 `typeInfo` 保留 H100(頁首、紀錄與精選清單照常顯示),預設仍是 T4,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T227a)
  - 🧪 `testplan.md` § US5-AJ-01
  - ⚙ `prototype/index.html` § `#open`、`#switch`、`[data-state="normal"]`、`[data-state="ready"]`、`[data-state="confirm-switch"]`
  - 📎 `spec.md` § FR-017、SC-005
- [x] T228a [US5] 🔴 /tdd 紅燈(對照組):在 `tests/e2e/test_004_us5_h100.py` 寫 US5-AJ-02 的測試(按「變更類型」打開選單;分隔註解寫 `# ---- 004 US5-AJ-02`(`plan.md` § 待決問題 Q34));T227b 改的類型選單(開啟面板與變更類型共用 `src/cgb/static/js/session.js` 的同一段 `RUNTIME_TYPES.map`)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「只改了開啟面板的清單,變更類型的選單用的是另一份 `RUNTIME_TYPES`」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US5-AJ-02
  - ⚙ `prototype/index.html` § `#open`、`#switch`、`[data-state="normal"]`、`[data-state="ready"]`、`[data-state="confirm-switch"]`
  - 📎 `spec.md` § FR-017、SC-005
- [x] T228b [US5] 🟢 /tdd 綠燈:US5-AJ-02 由 T227b 改的類型選單(開啟面板與變更類型共用 `src/cgb/static/js/session.js` 的同一段 `RUNTIME_TYPES.map`) 滿足,確認 `src/cgb/static/js/session.js` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/session.js` 只寫讓 US5-AJ-02 通過的程式碼(依賴 T228a)
  - 🧪 `testplan.md` § US5-AJ-02
  - ⚙ `prototype/index.html` § `#open`、`#switch`、`[data-state="normal"]`、`[data-state="ready"]`、`[data-state="confirm-switch"]`
  - 📎 `spec.md` § FR-017、SC-005
- [x] T229a [US5] 🔴 /tdd 紅燈(對照組):在 `tests/e2e/test_004_us5_h100.py` 寫 US5-AJ-03 的測試(打開紀錄頁;分隔註解寫 `# ---- 004 US5-AJ-03`(`plan.md` § 待決問題 Q34));既有 `src/cgb/static/js/history.js` 的類型顯示,加上 T227b 只從選單拿掉 H100、`RUNTIME_TYPES` 保留 H100已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「從 `RUNTIME_TYPES` 刪掉 H100,紀錄頁查不到就顯示空白或「未知」」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US5-AJ-03
  - 📎 `spec.md` § FR-017、SC-005
- [x] T229b [US5] 🟢 /tdd 綠燈:US5-AJ-03 由 既有 `src/cgb/static/js/history.js` 的類型顯示,加上 T227b 只從選單拿掉 H100、`RUNTIME_TYPES` 保留 H100 滿足,確認 `src/cgb/static/js/history.js` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/history.js` 只寫讓 US5-AJ-03 通過的程式碼(依賴 T229a)
  - 🧪 `testplan.md` § US5-AJ-03
  - 📎 `spec.md` § FR-017、SC-005
- [x] T230a [US5] 🔴 /tdd 紅燈:在 `tests/e2e/test_004_us5_h100.py` 寫 US5-AJ-04 的測試(情況 A 看清單;情況 B 打開 `llama3.2:3b` 的修改表單;情況 C 打開 `qwen2.5` 的修改表單,不改類型就送出;分隔註解寫 `# ---- 004 US5-AJ-04`(`plan.md` § 待決問題 Q34)),執行確認它因為「修改既有 H100 項目時選單沒有對應的選項,預設跳成「不指定」,一送出就把 H100 清掉(`plan.md` Q31)」這類實作而失敗
  - 🧪 `testplan.md` § US5-AJ-04
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-017、SC-005;`plan.md` § 待決問題 Q31
- [x] T230b [US5] 🟢 /tdd 綠燈:在 `src/cgb/static/js/library.js` 只寫讓 US5-AJ-04 通過的程式碼;精選清單建議類型選單不列 H100,修改既有 H100 項目時加「維持目前設定」(`#c-type-keep`,`plan.md` § 待決問題 Q31),執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T230a)
  - 🧪 `testplan.md` § US5-AJ-04
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-017、SC-005;`plan.md` § 待決問題 Q31
- [x] T258a [US5] 🔴 /tdd 紅燈(對照組):在 `tests/e2e/test_004_us5_h100.py` 寫 US5-AJ-05 的測試(按「新增」打開新增表單;分隔註解寫 `# ---- 004 US5-AJ-05`(`plan.md` § 待決問題 Q34));T230b 讓精選表單的 `#c-type` 不列 H100(新增與修改共用同一份選項,「維持目前設定」只在修改既有 H100 項目時加)已做到這段程式,這個案例會被滿足:先執行確認通過,再暫時放入「只在修改表單過濾 H100,新增表單用的是另一份清單」這類實作,執行確認斷言失敗後撤回;若一執行就斷言失敗,就當成一般的紅燈,不必再暫時改壞(`plan.md` § 待決問題 Q63)
  - 🧪 `testplan.md` § US5-AJ-05
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-017、SC-005
- [x] T258b [US5] 🟢 /tdd 綠燈:US5-AJ-05 由 T230b 讓精選表單的 `#c-type` 不列 H100(新增與修改共用同一份選項,「維持目前設定」只在修改既有 H100 項目時加)滿足,確認 `src/cgb/static/js/library.js` 不需要為它改程式碼,執行全部測試確認都通過;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/library.js` 只寫讓 US5-AJ-05 通過的程式碼(依賴 T258a)
  - 🧪 `testplan.md` § US5-AJ-05
  - ⚙ `prototype/library.html` § `#curated`、`#cur-add`、`#cur-form`、`#c-name`、`#c-note`、`#c-type`、`#c-type-keep`、`#c-highmem`、`#c-auto`、`#c-submit`、`#c-dup`、`#del-go`、`[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`
  - 📎 `spec.md` § FR-017、SC-005
- [ ] T231 [US5] 🔵 /tdd 重構:在全部測試綠燈下整理 T227b~T230b、T258b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T258b)
  - 🧪 `testplan.md` § US5-AJ-01~US5-AJ-04、US5-AJ-05
  - 📎 `testplan.md` § 6.1

### 介面覆蓋(US5)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `index.html` § `[data-state="normal"]` | T227b~T228b | T227a~T228a |
| `index.html` § `[data-state="ready"]`、`[data-state="confirm-switch"]`(故事 5 擴充:類型選單隱藏 H100) | T227b~T228b | T227a~T228a |
| `library.html` § `[data-state="cur-list"]`、`[data-state="cur-empty"]`、`[data-state="cur-form"]`、`[data-state="cur-form-edit"]`、`[data-state="cur-duplicate"]`、`[data-state="cur-invalid"]`、`[data-state="cur-delete"]`(故事 5 擴充:類型選單隱藏 H100) | T230b | T230a |

### 測試案例覆蓋(US5)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US5-AJ-01~US5-AJ-04 | T227a~T230a | T227b~T230b | T231 |
| US5-AJ-05 | T258a | T258b | T231 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 全綠;重構任務前後的測試結果相同

---

## Phase 7: 全域測試區

**Purpose**: 照 `testplan.md` § 7 驗證跨故事的 NFR 與 SC;全域需求在故事裡已經有案例涵蓋的彙整見 `testplan.md` § 7.1,這裡只排 § 7.2 的 6 個 📏 實跑案例。實跑一律照 `testplan.md` § 7.0 的護欄:G-01~G-05 不開 Colab、不執行任何 `colab` 指令、不花 compute units,只照 001 的 P5、P6;需要真的 Ollama 時測試自己起臨時的 `ollama serve`(port 由 `tests/realrun/helpers.py` 的 `free_loopback_port()` 取,避開 11434~11436 與 8780,`HOME`、`OLLAMA_MODELS` 都在 pytest 暫存資料夾,收尾驗行程與行程群組都已結束),不對 127.0.0.1:11434 送任何請求,不執行沒有指定 `OLLAMA_HOST` 的 `ollama` 指令;Hugging Face 只送不帶 token、不帶 Cookie 的唯讀 GET,每次實跑最多 40 個請求;錄下的回應只寫 pytest 暫存資料夾。結果寫進 `specs/004-chat-hf-curated-queue/measurements.md`

### 整合實跑

> 時機為「整合」的實跑案例;**這一輪延後,不實跑**(要開真的 Colab、花 compute units、需要使用者本人在場,分身不能核准;`plan.md` § 待決問題 Q62)

- [ ] T232 [G] 📏 量測:**這一輪延後,不實跑**(使用者 2026-11-14 授權的唯一例外,`plan.md` § 待決問題 Q62)。留給使用者本人在場時照 G-06 做:撰寫 `tests/realrun/test_004_g_06.py`(標 `realrun`),照 001 testplan 的實跑共同護欄 P1~P9,以 `docker compose -p cgb-test` 起本系統(UI 8780、Ollama 相容端點 11436、資料在 `<暫存目錄>/data`),精選清單只有 `hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M` 並設自動下載;開一台 T4 的 `cgb-test-` 工作階段,記下就緒到自動下載結果的秒數(門檻 30 秒內、排入 1 個、跳過 0 個)、下載完成後模型目錄有這個名稱、對話頁兩則回覆的每秒 token 數、結束後到 `GET /api/downloads` 回 0 筆的秒數(門檻 5 秒內),P3 收尾後 `colab sessions` 沒有 `cgb-test-` 開頭的行;整批上限 0.3 compute units、20 分鐘,GPU 只用 `--gpu T4`;不讀寫桌機的 `~/.config/colab-cli/`,一律用暫存的 `HOME`;token 與 endpoint 不印出,比對只印長度與 sha256 前 8 碼;執行前先停下來問使用者本人。這一輪在 `specs/004-chat-hf-curated-queue/measurements.md` 只寫「延後,未驗證」;判定者:腳本
  - 🧪 `testplan.md` § G-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`paths./downloads/auto-result.get`、`paths./chat.post`、`paths./downloads.get`
  - 📎 `spec.md` § FR-001、FR-004、FR-005、FR-011、FR-014、SC-001、SC-003;`research.md` § R4

### 全域案例

> 時機為「節內」的實跑案例;全域測試區沒有行為測試案例,所以沒有紅綠與重構任務。都標 `realrun`,以 `uv run pytest -m realrun <檔案>` 執行

- [ ] T233 [G] 📏 量測:撰寫 `tests/integration/test_004_g_01.py`(標 `realrun`;不經會執行 `colab usage` 的 `tests/realrun` fixture),以真的 `HuggingFaceHub()`(不注入 transport,連 https://huggingface.co)外包一層錄下每次往返的 transport,依序 `search_models("qwen2.5-0.5b")`(有 `cursor` 再取一頁)、`list_quants("bartowski","SmolLM2-135M-Instruct-GGUF")`、`get_manifest("bartowski","SmolLM2-135M-Instruct-GGUF","Q4_K_L")`、`get_manifest("google","gemma-3-1b-it-qat-q4_0-gguf","Q4_0")`、`search_models("zzzqqqnonexist")`;記下第一頁筆數與每筆 `id` 是否含 `/`、有 `Link rel="next"` 時 `cursor` 是否非空、`Q4_K_M` 的大小(門檻 105,455,145)、沒有列出 `Q4_K_L`、`Q5_K_L`、兩個 manifest 的代碼(門檻 `HF_QUANT_UNAVAILABLE`、`HF_AUTH_REQUIRED`)、不存在的關鍵字回 0 筆、錄到的請求都沒有 `Authorization`、`Cookie` 標頭、請求總數(門檻 ≤ 40),和門檻比較,結果寫進 `specs/004-chat-hf-curated-queue/measurements.md`;只送不帶 token、不帶 Cookie 的唯讀 GET,串列送出、不重試,約 30 個 GET、約 10 秒,連不到就標無法實跑;錄下的回應只寫 pytest 暫存資料夾;對方改版時樣本會變,失敗先看錄到的回應再判斷;判定者:腳本
  - 🧪 `testplan.md` § G-01
  - ⚙ `contracts/huggingface.openapi.yaml` § `paths./api/models.get`、`paths./api/models/{author}/{model}/tree/main.get`、`paths./v2/{author}/{model}/manifests/{tag}.get`
  - 📎 `spec.md` § FR-013、FR-014、FR-015、FR-016、NFR-005
- [ ] T234 [G] 📏 量測:撰寫 `tests/integration/test_004_g_02.py`(標 `realrun`),照 `testplan.md` § 7.0 起臨時 `ollama serve`(`/usr/local/bin/ollama`,空的 `OLLAMA_MODELS`;不存在就標無法實跑,不替它安裝),後端以 `live_servers` 起在 127.0.0.1 隨機 port,`FakeTunnel` 的本機 port 指到臨時 serve 的 port、`FakeColabControl` 開到就緒,`RemoteOllama(transport=RecordingTransport())`;依序 `pull_model` 拉 `hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M` 讀到結束、拉 `:Q4_K_L`、經真的 HTTP 送兩輪 `POST /api/chat`、送一次沒下載的 `:Q8_0`;記下第一次拉取的最後一筆與帶 `total` 的進度、`list_local_models` 是否有這個名稱、`Q4_K_L` 的代碼(門檻 `OLLAMA_PULL_FAILED`)、兩次對話的 Content-Type 與最後一行的 `done`、`eval_count`、`eval_duration`(門檻都大於 0)、第二個請求的 `messages` 則數(門檻 3)、沒下載的模型的狀態碼與代碼(門檻 404 `OLLAMA_NOT_FOUND`)、日誌輸出與 SQLite 檔裡 `Say hi in one word.` 出現的次數(門檻 0)、收尾後臨時 serve 的行程與行程群組是否都已結束,和門檻比較,結果寫進 `specs/004-chat-hf-curated-queue/measurements.md`;從 Hugging Face 下載約 105 MB 到 pytest 暫存資料夾(不花錢、只讀對方),`Q4_K_L` 在 manifest 就失敗、不下載,整段約 60 秒;所有對 Ollama 的 HTTP 都經 `RecordingTransport` 的 `check_port`,不對 127.0.0.1:11434 送任何請求,不執行沒有指定 `OLLAMA_HOST` 的 `ollama` 指令;Colab、SSH 都用替身,不執行任何 `colab` 指令;判定者:腳本
  - 🧪 `testplan.md` § G-02
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`paths./api/chat.post`;`contracts/ui.openapi.yaml` § `paths./chat.post`
  - 📎 `spec.md` § FR-004、FR-005、FR-014、FR-018、NFR-002、NFR-003;`research.md` § R4、R5
- [ ] T235 [G] 📏 量測:撰寫 `tests/e2e/test_004_g_03.py`(標 `realrun`),`e2e_servers` 起真的後端,`FakeOllamaServer` 對 `/api/chat` 每 0.1 秒吐一段、共 20 段再吐 `DONE` 並記下吐出第一段的時間;在對話頁送出一則,以 `page.wait_for_function` 記下畫面第一次出現第一段文字的時間,做 5 次、每次清空;記下 5 次的「畫面出現第一段 − 替身吐出第一段」(門檻都 ≤ 0.5 秒)、5 次的回覆下方是否都顯示耗時與每秒 token 數、測試前後 SQLite 檔與後端日誌中送出內容出現的次數(門檻 0),和門檻比較,結果寫進 `specs/004-chat-hf-curated-queue/measurements.md`;UI 只綁 127.0.0.1:8781(e2e 的固定 port,同一時間只跑一份),資料庫是 pytest 暫存資料夾的 SQLite,Colab、通道、遠端 Ollama 都用替身,不執行任何 `colab` 指令,約 15 秒;判定者:腳本
  - 🧪 `testplan.md` § G-03
  - ⚙ `prototype/chat.html` § `#send`、`#log`、`[data-state="turn-streaming"]`、`[data-state="turn-idle"]`
  - 📎 `spec.md` § NFR-003、SC-002、NFR-002、FR-005
- [ ] T236 [G] 📏 量測:撰寫 `tests/e2e/test_004_g_04.py`(標 `realrun`),`e2e_servers` 起真的後端,Hugging Face 注入真的 `HuggingFaceHub`、transport 的 handler 收到請求就 `await asyncio.sleep(60)`(不連網),逾時用原樣的 10 秒,官方模型庫用 `FakeModelLibrary`;情況 A 在 `#hf-q` 搜尋 `qwen`,等的同時每 1 秒在官方搜尋送一次 `qwen2.5`;情況 B 直接打開 `bartowski/SmolLM2-135M-Instruct-GGUF` 的展開;記下 A 從送出到 `[data-state="hf-down"]` 顯示的秒數(門檻 ≤ 11 秒)、A 等待期間官方搜尋每一次列出 `qwen2.5` 的秒數(門檻都在 1 秒內)、B 從送出到展開區顯示暫時無法使用的秒數(門檻 ≤ 11 秒)、A、B 的 UI API 回應有沒有 500(門檻 0 次),和門檻比較,結果寫進 `specs/004-chat-hf-curated-queue/measurements.md`;不連網(handler 只 sleep),UI 只綁 127.0.0.1:8781,資料庫是 pytest 暫存資料夾的 SQLite,不執行任何 `colab` 指令,約 25 秒;判定者:腳本
  - 🧪 `testplan.md` § G-04
  - ⚙ `prototype/library.html` § `#hf-q`、`[data-state="hf-down"]`、`[data-state="hf-expand-down"]`、`#lib-q`、`[data-state="lib-results"]`
  - 📎 `spec.md` § SC-004、NFR-005、FR-016
- [ ] T237 [G] 📏 量測:撰寫 `tests/integration/test_004_g_05.py`(標 `realrun`),後端以 `make_app` 建,Hugging Face 注入真的 `HuggingFaceHub`、handler 收到請求就 `await asyncio.sleep(60)`,逾時用原樣的 10 秒;精選清單有 8 個 hf.co 名稱都設自動下載,`probe_resources` 回剩餘磁碟 225,485,783,040、顯示記憶體 16,106,127,360;開啟工作階段到就緒,從就緒起每 0.5 秒讀一次 `GET /api/downloads/auto-result`;記下就緒到 `result.state` 變成 `done` 的秒數(門檻 30 秒內)、跳過的 8 筆的 `reason` 與 `reasonCode`(門檻都是 `SIZE_UNAVAILABLE`、`HF_TIMEOUT`)、handler 同時在處理的請求數最大值(門檻 ≤ 4),和門檻比較,結果寫進 `specs/004-chat-hf-curated-queue/measurements.md`;不連網(handler 只 sleep),資料庫是 pytest 暫存資料夾的 SQLite,Colab、通道、遠端 Ollama 用替身,不執行任何 `colab` 指令,約 25 秒;判定者:腳本
  - 🧪 `testplan.md` § G-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/auto-result.get`;`contracts/huggingface.openapi.yaml` § `paths./v2/{author}/{model}/manifests/{tag}.get`
  - 📎 `spec.md` § SC-003、FR-011、FR-012;`research.md` § R6

### 測試案例覆蓋(全域)

| testplan 案例 | 任務 |
|---|---|
| G-01 | T233 |
| G-02 | T234 |
| G-03 | T235 |
| G-04 | T236 |
| G-05 | T237 |
| G-06 | T232 |

**Checkpoint**: 全部測試綠燈;`specs/004-chat-hf-curated-queue/measurements.md` 的 G-01~G-05 每一項都寫了數字與是否過門檻,沒過的列為待決問題;G-06 標「這一輪延後,未驗證」,完成報告列為未驗證
