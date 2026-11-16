# Tasks: 讓 opencode 與 pi 輕鬆接上 Colab 上的 Ollama

**Input**: `specs/006-agent-client-connect/` 的設計文件(本 spec package);建立在 `specs/005-ollama-machine-tuning/` 之上(005 建立在 004、003、002、001 之上),既有程式在 `src/cgb/`、既有測試在 `tests/`

**Prerequisites**: plan.md、spec.md、research.md、techstack.md、testplan.md、contracts/ollama-compat.openapi.yaml、contracts/ui.openapi.yaml、prototype/、deploy/compose.yaml、deploy/.env.example

**Tests**: 依 `testplan.md` 切分。testplan 的每個行為測試案例對應一組 `/tdd` 紅燈與綠燈任務,每個「使用者故事 × 端點」節最後一個 `/tdd` 重構任務;量測與人工驗證的案例對應 📏 任務。

**Organization**: 依 `testplan.md` 的使用者故事分 phase;每個故事底下依 `testplan.md` 的端點分節(E3 Ollama 相容端點、E2 後端 UI API、E11 部署與網路),外加一節跨端點驗收,最後是介面覆蓋表與測試案例覆蓋表。E1 前端 UI 照 `testplan.md` § 1 不另立端點節,畫面行為都在各故事的跨端點驗收。全域測試區自成一個 phase,放在所有故事之後。

## Format: `[ID] [Story] [步驟] Description`,底下接 🧪、⚙ 與 📎

- **[Story]**:所屬的使用者故事(US1、US2、US3);全域測試區寫 `[G]`
- **[步驟]**:這個任務是 `/implement` 交給誰做的哪一步
  - 🔴 `/tdd 紅燈`:寫一個測試案例的測試,執行確認它失敗
  - 🟢 `/tdd 綠燈`:只寫讓同一個案例通過的程式碼,執行全部測試確認都通過
  - 🔵 `/tdd 重構`:在全部測試綠燈下,整理這一節綠燈任務記下的重構清單,不改行為、不改斷言
  - 📏 量測:照 testplan 案例的條件量測或人工驗證,記下數字與門檻比較;是唯一不對應 `/tdd` 的開發任務
  - 不標步驟的只限三類:工具鏈設定、原樣複製 spec package 的規格檔、CI 設定
- **紅綠成對**:一個 testplan 案例對應同一個三位數的 `a`(🔴)與 `b`(🟢),`b` 依賴 `a`
- **對照組**:案例要測的程式路徑已經由既有程式或更早的綠燈任務做到時,紅燈任務寫成「先確認通過,再暫時放入要抓的錯、確認斷言失敗後撤回」;對應的綠燈任務確認不需要改程式碼(`plan.md` § 待決問題 Q25)。一般的紅燈任務寫完一執行就通過時,也照這個做法改當對照組,並在完成報告記一筆(`plan.md` § 待決問題 Q24)
- **誰做、怎麼排**:同一個 phase 的端點節各交給一個 subagent 平行做;跨端點驗收節在端點節都完成、驗收過後由主 agent 做。每一節裡照任務編號一次做一個任務,做完才做下一個,不跳號;任務寫了「依賴」另一節的任務時,等那個任務做完才開始(同一個檔不同時改)。E3 節把 US1-OC-05 排在最前面,因為 001 三處舊測試的改寫放在它的綠燈(`plan.md` § 待決問題 Q22)
- 每個任務都寫出確切的檔案路徑
- **🧪**:這個任務對應的 `testplan.md` 案例 ID;🔵 寫這一節所有案例的範圍;不標步驟的任務不寫這一行
- **⚙**:這個任務要做出來或測到的介面元素:至少照 `testplan.md` 受測操作表的「規格錨點」欄寫,再加上這個任務實際做出或斷言的介面元素;`info.x-snippet-rule` 等 `info.x-*` 不是可單獨引用的錨點,用它的 schema 代表,規則在任務描述裡寫明;純函式 `connect.*` 與原生路徑(001 的檔)沒有本 spec package 內的錨點時,⚙ 寫它產生或斷言的 schema,或省略
- **📎**:做這個任務時要對照的依據:`spec.md` § FR / NFR / SC、`research.md` § R、`plan.md` § Q 或段落名、`techstack.md` § 段落名
- **本機的 Ollama 與 Colab**:任何任務都不對桌機 127.0.0.1:11434 送請求,也不執行沒有指定 `OLLAMA_HOST` 的 `ollama` 指令;opencode 與 pi 一律在暫存 `HOME` 執行,不讀寫使用者的 `~/.config/opencode`、`~/.pi`、`~/.config/colab-cli/`;要開 Colab 的任務(G-04)執行前先停下問使用者本人
- **本輪的設定位置**:專案沒有 `src/cgb/config.py`,設定在 `src/cgb/__main__.py` 的 `Settings` 與 `src/cgb/app.py` 的 `create_app`(`plan.md` § 待決問題 Q21)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 沿用 001~005 的工具鏈、`uv.lock` 與測試基礎(`tests/conftest.py`、`tests/fakes/`、`tests/e2e/conftest.py`、`tests/realrun/helpers.py`)與 005 T001 新增的 `realrun_local` marker;這一輪不新增套件、服務、port 與掛載,不改 CI,也沒有原樣複製的規格檔(`deploy/` 只搬差異的兩處,放在 US1-DEP-01 的綠燈,`plan.md` § 待決問題 Q3)。新的替身由第一個需要它的紅燈任務建立:`SseReply` 由 T003a。

本輪沒有 Setup 任務。

---

## Phase 2: User Story 1 - 用 opencode 接上 Colab 上的模型 (Priority: P1) 🎯 MVP

**Goal**: 使用者開好工作階段、下載了模型後,在 UI 的「連線設定」畫面複製一段 opencode 的設定貼進自己的 `opencode.json`,opencode 就能經本系統的 `/v1` 用 Colab 上的模型,包括工具呼叫;沒有工作階段或沒有模型時畫面說明原因

**Independent Test**: 照 `testplan.md` § 2 的全部案例:E3 以 `uv run pytest tests/integration/test_006_v1.py tests/integration/test_ollama_compat.py`、E2 以 `uv run pytest tests/unit/test_connect.py tests/integration/test_api_connect.py`、E11 以 `uv run pytest tests/unit/test_compose_env.py`、跨端點驗收以 `uv run pytest tests/e2e/test_006_connect.py` 執行全綠

### E3 Ollama 相容端點

> 新案例的測試在 `tests/integration/test_006_v1.py`,沿用 001 的 `bridge` fixture;`SseReply` 由 T003a 建立,T007a、T008a、T011a 用它

- [x] T001a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_006_v1.py` 寫 US1-OC-05 的測試(工作階段就緒,依序送 `POST /v1/completions`、`POST /v1/embeddings`、`GET /v1/responses`;沿用 `tests/integration/test_ollama_compat.py` 的 `bridge` fixture,以 `from integration.test_ollama_compat import bridge` 匯入),執行確認它因為「白名單用 `/v1/` 前綴整段放行;或 404 本文用原生格式」這類實作而失敗
  - 🧪 `testplan.md` § US1-OC-05
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/{path}.get`、`components.schemas.OpenAIError`、`components.schemas.Error`
  - 📎 `spec.md` § FR-011;`research.md` § R6
- [x] T001b [US1] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/forward.py`(新增 `openai_error(message, status, code, type_)`,本文 `{"error": {"message", "type", "code"}}`)與 `src/cgb/ollama_compat/routes.py`(新增 `V1_WHITELIST`,現在是空集合,後面的任務才加入路徑;`/v1/` 底下不在 `V1_WHITELIST` 的路徑,不論方法與工作階段狀態都回 404 `unsupported_path`、`type` 為 `invalid_request_error`,`message` 說明只開放 `/v1/chat/completions` 與 `/v1/models`;`/api/*` 與其他路徑的原生格式不動)只寫讓 US1-OC-05 通過的程式碼;同一個任務依 `plan.md` § 待決問題 Q18 改寫三處 001 舊測試,改用仍不開放的 `/v1/completions`:`tests/integration/test_ollama_compat.py` 的 `test_白名單外的路徑回_404_不轉送`(參數 `POST /v1/chat/completions` 改 `POST /v1/completions`,`/v1/` 路徑改讀 `error.message`)、同檔 `test_被擋下與白名單外的請求也重設閒置計時` 的 `GET /v1/models`(改 `GET /v1/completions`)、`tests/e2e/test_locale.py` 的 `oc_unlisted`(改 `/v1/completions`、讀 `error.message`);執行全部測試確認都通過;看到要整理的地方記進重構清單、不留 skip(依賴 T001a)
  - 🧪 `testplan.md` § US1-OC-05
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/{path}.get`、`components.schemas.OpenAIError`、`components.schemas.Error`
  - 📎 `spec.md` § FR-011;`plan.md` § 待決問題 Q18、Q22;`research.md` § R6
- [x] T002a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_006_v1.py` 寫 US1-OC-01 的測試(假 Ollama 的 `/v1/chat/completions` 回 `JsonReply` 一則 `chat.completion`;送 `stream:false` 的請求,帶 `Authorization: Bearer ollama`;斷言回 200、本文與假 Ollama 回的相同、假 Ollama 收到的路徑與本文),執行確認它因為「白名單沒加 `/v1/chat/completions` 回 404;或轉成原生 `/api/chat`」這類實作而失敗
  - 🧪 `testplan.md` § US1-OC-01
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionPassthrough`
  - 📎 `spec.md` § FR-009;`research.md` § R1
- [x] T002b [US1] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py` 只寫讓 US1-OC-01 通過的程式碼(`V1_WHITELIST` 加 `/v1/chat/completions`,放行後走既有的 `forward()` 原樣轉送);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T002a)
  - 🧪 `testplan.md` § US1-OC-01
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionPassthrough`
  - 📎 `spec.md` § FR-009;`research.md` § R1
- [x] T003a [US1] 🔴 /tdd 紅燈:在 `tests/fakes/ollama_server.py` 新增 `SseReply`(`events` 清單、每段間隔 `interval`、`then` 為 `end`/`disconnect`/`hang`,逐段以 `data: ` 行加空行送出;同時更新該檔開頭的說明,`plan.md` § 待決問題 Q19),再在 `tests/integration/test_006_v1.py` 寫 US1-OC-02 的測試(三段 `chat.completion.chunk`,第二段的 delta 帶完整的 `tool_calls`,最後 `data: [DONE]`;送 `stream:true`,帶 `tools` 與 `stream_options.include_usage`;斷言 `Content-Type` 是 `text/event-stream`、收到的本文與假 Ollama 送的位元組完全相同、假 Ollama 收到的本文含 `tools` 與 `stream_options`);`forward()` 已逐段原樣轉送,T002b 開放路徑後這個案例會被滿足:先執行確認通過,再暫時讓 `src/cgb/ollama_compat/forward.py` 把 SSE 當成 NDJSON 逐行解析改寫(或轉送時去掉 `tools`),確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-OC-02
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionStream`、`components.schemas.ChatCompletionRequest`
  - 📎 `spec.md` § FR-009;`research.md` § R1;`plan.md` § 待決問題 Q19、Q25
- [x] T003b [US1] 🟢 /tdd 綠燈:US1-OC-02 由 T002b 開放路徑、既有的 `forward()` 原樣轉送滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/ollama_compat/forward.py` 只寫讓 US1-OC-02 通過的程式碼(依賴 T003a)
  - 🧪 `testplan.md` § US1-OC-02
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionStream`、`components.schemas.ChatCompletionRequest`
  - 📎 `spec.md` § FR-009;`research.md` § R1
- [x] T004a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_006_v1.py` 寫 US1-OC-03 的測試(假 Ollama 的 `/v1/models` 回 `{"object":"list","data":[{"id":"qwen2.5:3b","object":"model"}]}`;送 `GET /v1/models`;斷言回 200、本文相同),執行確認它因為「只開了 `/v1/chat/completions`,`/v1/models` 仍回 404」這類實作而失敗
  - 🧪 `testplan.md` § US1-OC-03
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/models.get`、`components.schemas.ModelListPassthrough`
  - 📎 `spec.md` § FR-009;`research.md` § R1
- [x] T004b [US1] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py` 只寫讓 US1-OC-03 通過的程式碼(`V1_WHITELIST` 加 `/v1/models`);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T004a)
  - 🧪 `testplan.md` § US1-OC-03
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/models.get`、`components.schemas.ModelListPassthrough`
  - 📎 `spec.md` § FR-009;`research.md` § R1
- [x] T005a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_006_v1.py` 寫 US1-OC-04 的測試(沒有開工作階段;送 `POST /v1/chat/completions`;斷言 1 秒內回 503、本文是 `{"error":{"message":…,"type":"service_unavailable","code":"no_ready_session"}}` 且 `message` 含「沒有可用的工作階段」、假 Ollama 沒收到任何請求),執行確認它因為「`/v1` 也回原生的 `{"error":"..."}` 字串;或排隊等工作階段」這類實作而失敗
  - 🧪 `testplan.md` § US1-OC-04
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.OpenAIError`、`components.schemas.Error`
  - 📎 `spec.md` § FR-010;`research.md` § R6
- [x] T005b [US1] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py` 只寫讓 US1-OC-04 通過的程式碼(`/v1/` 路徑沒有就緒的工作階段時改回 `openai_error(no_ready_session_message(...), 503, "no_ready_session", "service_unavailable")`,`message` 沿用既有的 `no_ready_session_message`;原生路徑的 503 不動);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T005a)
  - 🧪 `testplan.md` § US1-OC-04
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.OpenAIError`、`components.schemas.Error`
  - 📎 `spec.md` § FR-010;`research.md` § R6
- [x] T006a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_006_v1.py` 寫 US1-OC-06 的測試(工作階段就緒,假 Ollama 已停止,通道的 `baseUrl` 連不上;送 `POST /v1/chat/completions`;斷言回 502、`error.code` 是 `ollama_unreachable`、`message` 不含轉發位址),執行確認它因為「連不上時回原生格式,或 `message` 帶出 `baseUrl`」這類實作而失敗
  - 🧪 `testplan.md` § US1-OC-06
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.OpenAIError`、`components.schemas.Error`
  - 📎 `spec.md` § FR-010;`research.md` § R6
- [x] T006b [US1] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/forward.py` 只寫讓 US1-OC-06 通過的程式碼(`forward()` 接到 `httpx.ConnectError` 時,請求路徑在 `/v1/` 底下改回 `openai_error(UNREACHABLE_MESSAGE, 502, "ollama_unreachable", "api_error")`,`message` 不帶轉發位址;原生路徑的 502 不動);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T006a)
  - 🧪 `testplan.md` § US1-OC-06
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.OpenAIError`、`components.schemas.Error`
  - 📎 `spec.md` § FR-010;`research.md` § R6
- [x] T007a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_006_v1.py` 寫 US1-OC-07 的測試(假 Ollama 回 `SseReply`,送完第一段後 `then="disconnect"`;送 `stream:true`;斷言收到第一段之後多一段 `data: {"error":{"message":…,"type":"api_error","code":"stream_interrupted"}}`,再一段 `data: [DONE]`,連線正常結束、用戶端讀得完本文),執行確認它因為「SSE 中途斷線沿用 `StreamAborted` 直接斷線,用戶端看不到原因」這類實作而失敗
  - 🧪 `testplan.md` § US1-OC-07
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionStream`、`components.schemas.OpenAIError`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001;`plan.md` § 待決問題 Q4;`research.md` § R1
- [x] T007b [US1] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/forward.py` 只寫讓 US1-OC-07 通過的程式碼(`_relay` 遇到 `Content-Type` 為 `text/event-stream` 的回應中途斷線時,不再丟 `StreamAborted`,改補 `data: {"error":{…}}` 與 `data: [DONE]`,前一段沒有以空行結尾時先補空行;補段的代碼用對照表依原因決定:連線非預期中斷是 `stream_interrupted`、工作階段被結束是 `no_ready_session`,`type` 都是 `api_error`,`_relay` 兩種原因共用同一個出口,T008 靠它);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T007a)
  - 🧪 `testplan.md` § US1-OC-07
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionStream`、`components.schemas.OpenAIError`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001;`plan.md` § 待決問題 Q4;`research.md` § R1
- [x] T008a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_006_v1.py` 寫 US1-OC-08 的測試(假 Ollama 回 `SseReply`,送完第一段後 `then="hang"`;送 `stream:true`,收到第一段後 `DELETE /api/session`;斷言第一段之後多一段 `error.code` 為 `no_ready_session` 的 `data:` 段與 `data: [DONE]`);`_relay` 的 SSE 補段出口已由 T007b 做到(兩種原因共用同一個代碼對照表),這個案例會被滿足:先執行確認通過,再暫時讓 `src/cgb/ollama_compat/forward.py` 在 `ended` 時不補 SSE 的錯誤段,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-OC-08
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionStream`、`components.schemas.OpenAIError`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001;`plan.md` § 待決問題 Q4、Q25
- [x] T008b [US1] 🟢 /tdd 綠燈:US1-OC-08 由 T007b 滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/ollama_compat/forward.py` 只寫讓 US1-OC-08 通過的程式碼(依賴 T008a)
  - 🧪 `testplan.md` § US1-OC-08
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionStream`、`components.schemas.OpenAIError`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-001;`plan.md` § 待決問題 Q4
- [x] T009a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_006_v1.py` 寫 US1-OC-09 的測試(假 Ollama 的 `/v1/chat/completions` 回 404 `{"error":{"message":"model \"nope\" not found","type":"api_error"}}`;送 `model:"nope"`;斷言回 404、本文與假 Ollama 回的完全相同);既有的 `forward()` 對遠端的 4xx 原樣傳回狀態碼與本文,T002b 開放路徑後這個案例會被滿足:先執行確認通過,再暫時讓 `src/cgb/ollama_compat/forward.py` 把遠端的 404 改寫成本系統自己的 OpenAI 格式,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-OC-09
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionPassthrough`
  - 📎 `spec.md` § FR-009;`plan.md` § 待決問題 Q25
- [x] T009b [US1] 🟢 /tdd 綠燈:US1-OC-09 由既有的 `forward()` 與 T002b 滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/ollama_compat/forward.py` 只寫讓 US1-OC-09 通過的程式碼(依賴 T009a)
  - 🧪 `testplan.md` § US1-OC-09
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionPassthrough`
  - 📎 `spec.md` § FR-009
- [x] T010a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_006_v1.py` 寫 US1-OC-10 的測試(沒有開工作階段;依序送 `POST /api/generate`、`POST /api/pull`、`GET /api/me`;斷言三個的本文 `error` 仍是字串,狀態碼分別是 503、403、404);既有的 `routes.ollama_endpoint` 與 `forward.ollama_error` 對原生路徑維持字串格式,T001b、T005b 只讓 `/v1/` 路徑改格式,這個案例會被滿足:先執行確認通過,再暫時讓 `ollama_error()` 一律回 OpenAI 格式,確認斷言失敗後撤回;本案例的規格錨點是 001 的 `contracts/ollama-compat.openapi.yaml` § `paths`,不在本 spec package,所以沒有 ⚙
  - 🧪 `testplan.md` § US1-OC-10
  - 📎 `spec.md` § FR-010、FR-011;`plan.md` § 待決問題 Q25
- [x] T010b [US1] 🟢 /tdd 綠燈:US1-OC-10 由既有的 `ollama_error()` 與 T001b、T005b 只改 `/v1/` 路徑滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/ollama_compat/forward.py`、`src/cgb/ollama_compat/routes.py` 只寫讓 US1-OC-10 通過的程式碼(依賴 T010a)
  - 🧪 `testplan.md` § US1-OC-10
  - 📎 `spec.md` § FR-010、FR-011
- [x] T011a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_006_v1.py` 寫 US1-OC-11 的測試(假 Ollama 回 `SseReply`,每 0.1 秒送一段、共 10 段;送 `stream:true`,記下每一段到達用戶端的時間;斷言每一段比假 Ollama 送出晚不超過 0.5 秒、第一段在最後一段送出之前就到達);既有的 `_relay` 逐段傳回、不緩衝,這個案例會被滿足:先執行確認通過,再暫時讓 `src/cgb/ollama_compat/forward.py` 先 `await upstream.aread()` 整段收完再送出,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-OC-11
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionStream`
  - 📎 `spec.md` § NFR-001、SC-003;`plan.md` § 待決問題 Q25
- [x] T011b [US1] 🟢 /tdd 綠燈:US1-OC-11 由既有的 `_relay` 逐段傳回滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/ollama_compat/forward.py` 只寫讓 US1-OC-11 通過的程式碼(依賴 T011a)
  - 🧪 `testplan.md` § US1-OC-11
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`、`components.schemas.ChatCompletionStream`
  - 📎 `spec.md` § NFR-001、SC-003
- [x] T012 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T001b~T011b 記下的重構清單(範圍限 `src/cgb/ollama_compat/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/test_006_v1.py`、`tests/integration/test_ollama_compat.py`、`tests/e2e/test_locale.py` 的斷言(依賴 T011b)
  - 🧪 `testplan.md` § US1-OC-01~US1-OC-11
  - 📎 `testplan.md` § 2.1

### E2 後端 UI API(FastAPI REST 與 SSE)

> `src/cgb/domain/connect.py` 由 T013b 建立;故事 2、3 的 E2 節與跨端點驗收的 T029b 也改它或 `src/cgb/api/connect.py`,都排在這一節之後

- [x] T013a [US1] 🔴 /tdd 紅燈:在 `tests/unit/test_connect.py` 寫 US1-API-01 的測試(以 port 11436、模型 `["qwen2.5-coder:7b","qwen2.5:3b"]`、context 32768 呼叫 `connect.opencode_snippet(...)`;斷言片段解析成 JSON 後 `provider.cgb.npm` 是 `@ai-sdk/openai-compatible`、`options.baseURL` 是 `http://{{host}}:11436/v1`、`models` 的鍵恰好是兩個模型名稱、每個模型 `limit.context` 是 32768 且 `limit.output` 是 4096),執行確認它因為「baseURL 少了 `/v1`;或模型清單寫死」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-001、FR-002;`research.md` § R2
- [x] T013b [US1] 🟢 /tdd 綠燈:在 `src/cgb/domain/connect.py`(新增,純函式)只寫讓 US1-API-01 通過的程式碼(`opencode_snippet(port, models, context_length) -> str`,縮排 2 格的 JSON 文字,位址寫成 `http://{{host}}:<port>/v1`);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T013a)
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-001、FR-002;`research.md` § R2
- [x] T014a [US1] 🔴 /tdd 紅燈:在 `tests/unit/test_connect.py` 寫 US1-API-02 的測試(以 context 4096、8191 各呼叫 `connect.opencode_snippet(...)`;斷言 `limit.output` 分別是 2048、4095),執行確認它因為「`limit.output` 固定 4096,context 4096 時一次回覆就用完」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-002;`research.md` § R2
- [x] T014b [US1] 🟢 /tdd 綠燈:在 `src/cgb/domain/connect.py` 只寫讓 US1-API-02 通過的程式碼(`limit.output` 為 `min(4096, ⌊context ÷ 2⌋)`);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T014a)
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-002;`research.md` § R2
- [x] T015a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_connect.py` 寫 US1-API-03 的測試(工作階段就緒的預設資料,沿用 `tests/integration/test_api_session.py` 的 `ColabWorld`、`open_ready` 與 `ui_client`;送 `GET /api/connect`;斷言回 200、`ollamaPort` 是 11436、`basePath` 是 `/v1`、`reason` 是 null、`models` 是 `["qwen2.5-coder:7b","qwen2.5:3b"]`、`contextLength` 是 4096、`snippets.opencode` 解析後的 `limit.context` 是 4096),執行確認它因為「片段的 context 取級距表而不是目前套用的值;port 寫死 11434」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`;`contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-001、FR-002;`research.md` § R7
- [x] T015b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/connect.py`(新增 `GET /connect`,組合 `lifecycle.current()` 的 `ollama.tuning.contextLength.value` 與 `catalog.list()` 的模型名稱,片段交給 `domain/connect.py`;其餘必填欄位先給合約的固定值,建議值與提醒的算法由故事 3 逼出)、`src/cgb/api/__init__.py`(`app.include_router(connect.router, prefix="/api")`)、`src/cgb/app.py`(`AppState` 與 `create_app` 加 `ollama_port`、`public_ollama_port`,`plan.md` § 待決問題 Q21)、`tests/conftest.py`(`make_app` 預設帶 `public_ollama_port=11436`)只寫讓 US1-API-03 通過的程式碼;執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T015a)
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`;`contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-001、FR-002;`research.md` § R7;`plan.md` § 待決問題 Q21
- [x] T016a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_connect.py` 寫 US1-API-04 的測試(`make_app(public_ollama_port=None, ollama_port=11434)`,等於沒設 `CGB_PUBLIC_OLLAMA_PORT`、容器內 `CGB_OLLAMA_PORT` 是 11434;送 `GET /api/connect`;斷言 `ollamaPort` 是 11434),執行確認它因為「沒設時回 null 或 0,片段的位址壞掉」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-001;`research.md` § R7;`plan.md` § 待決問題 Q21
- [x] T016b [US1] 🟢 /tdd 綠燈:在 `src/cgb/app.py`(`public_ollama_port` 沒給時用 `ollama_port`)與 `src/cgb/__main__.py`(`Settings` 加 `public_ollama_port`,讀 `CGB_PUBLIC_OLLAMA_PORT`,沒設時用 `ollama_port`;`build_pair` 把兩個 port 傳給 `create_app`)只寫讓 US1-API-04 通過的程式碼;執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T016a)
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-001;`research.md` § R7;`plan.md` § 待決問題 Q21
- [x] T017a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_connect.py` 寫 US1-API-05 的測試(沒有開工作階段;送 `GET /api/connect`;斷言回 200、`reason` 是 `no_ready_session`、`snippets` 是 null),執行確認它因為「沒有工作階段時回 503,畫面沒辦法說明原因」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q8
- [x] T017b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/connect.py` 只寫讓 US1-API-05 通過的程式碼(依 `info.x-reason-rule` 第 (1) 點:不是 `ready` 的任何狀態回 200、`reason` 為 `no_ready_session`、`models` 為空、`contextLength` 與 `snippets` 為 null);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T017a)
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q8
- [x] T018a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_connect.py` 寫 US1-API-06 的測試(工作階段就緒,模型目錄是空的;送 `GET /api/connect`;斷言回 200、`reason` 是 `no_models`、`models` 是 `[]`、`snippets` 是 null),執行確認它因為「目錄空時仍產生沒有模型的片段」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-012
- [x] T018b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/connect.py` 只寫讓 US1-API-06 通過的程式碼(`info.x-reason-rule` 第 (2) 點:模型目錄是空的回 `no_models`,`contextLength` 照實回);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T018a)
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-012
- [x] T019a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_connect.py` 寫 US1-API-07 的測試(工作階段就緒,替身讓讀模型目錄連不上遠端;送 `GET /api/connect`;斷言回 502、代碼是 `OLLAMA_UNREACHABLE`);`api/connect.py` 走既有的 `Catalog.list()`,它已丟 `ApiError` 502,T015b 與 T018b 都沒有接住它,這個案例會被滿足:先執行確認通過,再暫時讓 `src/cgb/api/connect.py` 接住 `ApiError` 後回 `no_models`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`;`contracts/ui.openapi.yaml` § `components.schemas.Error`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q7、Q25
- [x] T019b [US1] 🟢 /tdd 綠燈:US1-API-07 由既有的 `Catalog.list()` 滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/api/connect.py` 只寫讓 US1-API-07 通過的程式碼(依賴 T019a)
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`;`contracts/ui.openapi.yaml` § `components.schemas.Error`
  - 📎 `spec.md` § FR-012;`plan.md` § 待決問題 Q7
- [x] T020a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_connect.py` 寫 US1-API-08 的測試(工作階段就緒,閒置計時的最後請求時間是 T;以注入的時鐘在 T+30 秒送 `GET /api/connect`;斷言 `GET /api/session` 的 `idle.lastRequestAt` 仍是 T);UI app 的 `/api/*` 不經過 `IdleHook`(它只掛在 `src/cgb/ollama_compat/__init__.py`),只有 Ollama 相容端點的請求才重設閒置計時,這個案例會被滿足:先執行確認通過,再暫時讓 `src/cgb/api/connect.py` 呼叫 `services.idle.request_started()` 與 `request_finished()`,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q12、Q25
- [x] T020b [US1] 🟢 /tdd 綠燈:US1-API-08 由 UI app 不經 `src/cgb/ollama_compat/idle_hook.py` 滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/api/connect.py` 只寫讓 US1-API-08 通過的程式碼(依賴 T020a)
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q12
- [x] T021a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_connect.py` 寫 US1-API-09 的測試(工作階段就緒,通道的 `baseUrl` 是 `http://127.0.0.1:49123`;送 `GET /api/connect`;斷言整份回應本文不含 `49123`、不含 token 與授權碼,每一段非 null 的片段裡主機名稱都是 `{{host}}`;pi 的片段由故事 2 補齊,這裡先驗 `piModels` 有 `{{host}}`),執行確認它因為「片段裡寫進轉發位址」這類實作而失敗(現況沒有 `piModels`)
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`;`contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q23
- [x] T021b [US1] 🟢 /tdd 綠燈:在 `src/cgb/domain/connect.py` 與 `src/cgb/api/connect.py` 只寫讓 US1-API-09 通過的程式碼(最小版本:`pi_models_snippet(port, models, context_length)` 只含 `providers.cgb.baseUrl`,`snippets.piModels` 有值、`piSettings` 先為 null,完整格式由 US2-API-01~US2-API-03 逼出,`plan.md` § 待決問題 Q23);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T021a)
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`;`contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-001;`plan.md` § 待決問題 Q23
- [x] T022 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T013b~T021b 記下的重構清單(範圍限 `src/cgb/domain/connect.py`、`src/cgb/api/connect.py`、`src/cgb/app.py`、`src/cgb/__main__.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/unit/test_connect.py`、`tests/integration/test_api_connect.py` 的斷言(依賴 T021b)
  - 🧪 `testplan.md` § US1-API-01~US1-API-09
  - 📎 `testplan.md` § 2.2

### E11 部署與網路(Docker Compose)

- [x] T023a [US1] 🔴 /tdd 紅燈:在 `tests/unit/test_compose_env.py`(新增)寫 US1-DEP-01 的測試(以標準函式庫照縮排讀專案根目錄的 `compose.yaml`(專案沒有 YAML 函式庫,`plan.md` § 待決問題 Q29),不執行 `docker compose`;斷言 `services.cgb.environment.CGB_PUBLIC_OLLAMA_PORT` 是 `${CGB_HOST_OLLAMA_PORT:-11434}`、`services.cgb.ports` 對外的相容端點仍是 `${CGB_HOST_OLLAMA_PORT:-11434}:11434`),執行確認它因為「變數名稱打錯,或寫死 11436」這類實作而失敗(現況沒有這個變數)
  - 🧪 `testplan.md` § US1-DEP-01
  - ⚙ `deploy/compose.yaml` § `services.cgb`、`services.cgb.environment`、`services.cgb.ports`
  - 📎 `spec.md` § FR-001;`research.md` § R7
- [x] T023b [US1] 🟢 /tdd 綠燈:在根目錄的 `compose.yaml` 與 `.env.example` 只寫讓 US1-DEP-01 通過的內容:只把 `specs/006-agent-client-connect/deploy/` 兩個檔的差異搬過來,不整份覆蓋(`plan.md` § 待決問題 Q3)。`compose.yaml` 在 `services.cgb.environment` 的 `CGB_OLLAMA_PORT: 11434` 之後加那一行註解與 `CGB_PUBLIC_OLLAMA_PORT: ${CGB_HOST_OLLAMA_PORT:-11434}`;`.env.example` 的 `CGB_HOST_OLLAMA_PORT` 說明加「連線設定頁的片段也用這個 port。」。複本裡 `build.context` 的 `../../..`、`x-source`、`x-requirements` 都不搬(根目錄原本的 `context: .` 與 `x-requirements` 維持不變,`plan.md` § 待決問題 Q2),所以沒有路徑要改;執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T023a)
  - 🧪 `testplan.md` § US1-DEP-01
  - ⚙ `deploy/compose.yaml` § `services.cgb`、`services.cgb.environment`、`services.cgb.ports`
  - 📎 `spec.md` § FR-001;`research.md` § R7;`plan.md` § 待決問題 Q2、Q3
- [x] T024 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T023b 記下的重構清單(範圍限根目錄的 `compose.yaml`、`.env.example`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/unit/test_compose_env.py` 的斷言(依賴 T023b)
  - 🧪 `testplan.md` § US1-DEP-01
  - 📎 `testplan.md` § 2.3

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器接真的後端。依賴 E2 節的 `src/cgb/api/connect.py`(T015b)與 E11 節的 `compose.yaml`(T023b)

- [x] T025a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_006_connect.py` 寫 US1-AJ-01 的測試(工作階段就緒的預設資料;從首頁導覽列點「連線設定」;斷言進到連線設定頁、opencode 分頁被選取、片段的 `baseURL` 是 `http://127.0.0.1:11436/v1`、片段列出 `qwen2.5-coder:7b` 與 `qwen2.5:3b`、下方寫著放進 `opencode.json` 與 `opencode -m cgb/<模型>`)(`tests/e2e/test_006_connect.py` 沿用 `tests/e2e/test_005_us1_tuning.py` 的做法:`e2e_servers`、`from e2e.test_us1_session import ColabWorld, world`,替身回報 T4 套用 context 4096;對 127.0.0.1:11434 不送任何請求),執行確認它因為「前端沒替換 `{{host}}`;導覽列沒有入口」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `prototype/connect.html` § `[data-state="normal"]`、`#tpl-snippets`、`[data-state="${state}"]`、`.topbar`、`.tabs`、`.tab`、`.snippet`、`.code`、`.howto`、`.facts`;`contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-001、NFR-002;`plan.md` § 待決問題 Q10、Q16
- [x] T025b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/connect.html`(新增,含 favicon;`#tpl-snippets` 與 `data-state` 區塊照 `prototype/connect.html`)、`src/cgb/static/js/connect.js`(新增:讀 `GET /api/connect`,依 `reason` 與 `contextLength` 決定顯示哪個 `data-state`,只把片段文字裡的 `{{host}}` 換成 `location.hostname`,分頁切換;欄位名稱照 `ConnectInfo`,不照原型的 `minContext`)、`src/cgb/static/style.css`(把 `prototype/style.css` 末尾「006 連線設定頁」整段搬進來,只用既有的 `var(--…)`,`plan.md` § 待決問題 Q27)與導覽列 `src/cgb/static/index.html`、`models.html`、`library.html`、`chat.html`、`usage.html`、`history.html`、`login.html`(各加 `<a href="connect.html">連線設定</a>`,排在「紀錄」之後,`connect.html` 自己的連結標 `aria-current="page"`)只寫讓 US1-AJ-01 通過的程式碼;執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T025a)
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `prototype/connect.html` § `[data-state="normal"]`、`#tpl-snippets`、`[data-state="${state}"]`、`.topbar`、`.tabs`、`.tab`、`.snippet`、`.code`、`.howto`、`.facts`;`contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-001、NFR-002;`plan.md` § 待決問題 Q10、Q16、Q27
- [x] T026a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_006_connect.py` 寫 US1-AJ-02 的測試(同 US1-AJ-01 的畫面;在 opencode 分頁按「複製」,先 `context.grant_permissions(["clipboard-read", "clipboard-write"])`;斷言按鈕文字變成「已複製」、讀回剪貼簿的內容和畫面上的片段文字完全相同),執行確認它因為「複製的是 `{{host}}` 還沒替換的原文;或只複製一部分」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `prototype/connect.html` § `.btn-small`、`.snippet-head`
  - 📎 `spec.md` § FR-003
- [x] T026b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/js/connect.js` 只寫讓 US1-AJ-02 通過的程式碼(`[data-copy]` 通用的複製處理:複製畫面上已換好主機名稱的片段文字,按鈕文字變「已複製」兩秒後還原);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T026a)
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `prototype/connect.html` § `.btn-small`、`.snippet-head`
  - 📎 `spec.md` § FR-003
- [x] T027a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_006_connect.py` 寫 US1-AJ-03 的測試(沒有開工作階段;打開連線設定頁;斷言看到「目前沒有就緒的工作階段」的說明與回首頁的連結、畫面上沒有片段區塊),執行確認它因為「沒有工作階段時仍顯示空的片段」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `prototype/connect.html` § `[data-state="no-session"]`、`.empty-state`
  - 📎 `spec.md` § FR-012
- [x] T027b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/connect.html` 與 `src/cgb/static/js/connect.js` 只寫讓 US1-AJ-03 通過的程式碼(`reason` 為 `no_ready_session` 時顯示 `data-state="no-session"`,不渲染片段);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T027a)
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `prototype/connect.html` § `[data-state="no-session"]`、`.empty-state`
  - 📎 `spec.md` § FR-012
- [x] T028a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_006_connect.py` 寫 US1-AJ-04 的測試(工作階段就緒,模型目錄是空的;打開連線設定頁;斷言看到「先到模型頁下載模型」的說明與模型頁的連結、畫面上沒有片段區塊),執行確認它因為「目錄空時顯示沒有模型的片段」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-04
  - ⚙ `prototype/connect.html` § `[data-state="empty-catalog"]`
  - 📎 `spec.md` § FR-012
- [x] T028b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/connect.html` 與 `src/cgb/static/js/connect.js` 只寫讓 US1-AJ-04 通過的程式碼(`reason` 為 `no_models` 時顯示 `data-state="empty-catalog"`);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T028a)
  - 🧪 `testplan.md` § US1-AJ-04
  - ⚙ `prototype/connect.html` § `[data-state="empty-catalog"]`
  - 📎 `spec.md` § FR-012
- [x] T029a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_006_connect.py` 寫 US1-AJ-05 的測試(工作階段就緒,context 4096;打開連線設定頁,依序看 opencode 分頁、pi 分頁與提醒;斷言分頁名稱、按鈕、使用方式、提醒與說明都是繁體中文、沒有簡體字,片段本身的鍵名照原文:opencode 的 `provider`、`baseURL`、`limit`,pi 的 `providers`、`baseUrl`(故事 1 的最小版本做得到的鍵;`contextWindow`、`reserveTokens` 由故事 2 的 US2-AJ-01 驗)),執行確認它因為「說明文字留英文原型字串;或把片段的鍵名也翻成中文」這類實作而失敗(現況沒有 pi 分頁與提醒的文字)
  - 🧪 `testplan.md` § US1-AJ-05
  - ⚙ `prototype/connect.html` § `[data-state="normal"]`、`#tpl-snippets`
  - 📎 `spec.md` § NFR-002;`plan.md` § 待決問題 Q23
- [x] T029b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/connect.html`、`src/cgb/static/js/connect.js` 與 `src/cgb/api/connect.py` 只寫讓 US1-AJ-05 通過的程式碼(最小版本,`plan.md` § 待決問題 Q23:pi 分頁與提醒區塊的繁體中文文字照 `prototype/connect.html`,pi 分頁先只有 `models.json` 一段;`api/connect.py` 以 `contextLength` 不是 null 且小於 16384 算 `shouldWarn`、`recommendedContextLength` 先固定 16384;複製按鈕、`settings.json`、建議值與改法由故事 2、3 逼出);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T029a)
  - 🧪 `testplan.md` § US1-AJ-05
  - ⚙ `prototype/connect.html` § `[data-state="normal"]`、`#tpl-snippets`
  - 📎 `spec.md` § NFR-002;`plan.md` § 待決問題 Q23
- [x] T030 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T025b~T029b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T029b)
  - 🧪 `testplan.md` § US1-AJ-01~US1-AJ-05
  - 📎 `testplan.md` § 2.4

### 介面覆蓋(US1)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ollama-compat.openapi.yaml` § `paths./v1/{path}.get` | T001b | T001a |
| `ollama-compat.openapi.yaml` § `components.schemas.OpenAIError` | T001b、T005b、T006b、T007b、T008b | T001a、T005a、T006a、T007a、T008a |
| `ollama-compat.openapi.yaml` § `components.schemas.Error` | T001b、T005b、T006b、T007b、T008b | T001a、T005a、T006a、T007a、T008a |
| `ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post` | T002b、T003b、T005b、T006b、T007b、T008b、T009b、T011b | T002a、T003a、T005a、T006a、T007a、T008a、T009a、T011a |
| `ollama-compat.openapi.yaml` § `components.schemas.ChatCompletionPassthrough` | T002b、T009b | T002a、T009a |
| `ollama-compat.openapi.yaml` § `components.schemas.ChatCompletionStream` | T003b、T007b、T008b、T011b | T003a、T007a、T008a、T011a |
| `ollama-compat.openapi.yaml` § `components.schemas.ChatCompletionRequest` | T003b | T003a |
| `ollama-compat.openapi.yaml` § `paths./v1/models.get` | T004b | T004a |
| `ollama-compat.openapi.yaml` § `components.schemas.ModelListPassthrough` | T004b | T004a |
| `ui.openapi.yaml` § `components.schemas.ConnectSnippets` | T013b、T014b、T015b、T021b | T013a、T014a、T015a、T021a |
| `ui.openapi.yaml` § `paths./connect.get` | T015b、T016b、T017b、T018b、T019b、T020b、T021b、T025b | T015a、T016a、T017a、T018a、T019a、T020a、T021a、T025a |
| `ui.openapi.yaml` § `components.schemas.ConnectInfo` | T015b、T016b、T017b、T018b、T019b、T020b、T021b、T025b | T015a、T016a、T017a、T018a、T019a、T020a、T021a、T025a |
| `ui.openapi.yaml` § `components.schemas.Error` | T019b | T019a |
| `compose.yaml` § `services.cgb` | T023b | T023a |
| `compose.yaml` § `services.cgb.environment` | T023b | T023a |
| `compose.yaml` § `services.cgb.ports` | T023b | T023a |
| `connect.html` § `[data-state="normal"]` | T025b、T029b | T025a、T029a |
| `connect.html` § `#tpl-snippets` | T025b、T029b | T025a、T029a |
| `connect.html` § `[data-state="${state}"]` | T025b | T025a |
| `connect.html` § `.topbar` | T025b | T025a |
| `connect.html` § `.tabs` | T025b | T025a |
| `connect.html` § `.tab` | T025b | T025a |
| `connect.html` § `.snippet` | T025b | T025a |
| `connect.html` § `.code` | T025b | T025a |
| `connect.html` § `.howto` | T025b | T025a |
| `connect.html` § `.facts` | T025b | T025a |
| `connect.html` § `.btn-small` | T026b | T026a |
| `connect.html` § `.snippet-head` | T026b | T026a |
| `connect.html` § `[data-state="no-session"]` | T027b | T027a |
| `connect.html` § `.empty-state` | T027b | T027a |
| `connect.html` § `[data-state="empty-catalog"]` | T028b | T028a |

### 測試案例覆蓋(US1)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US1-OC-05 | T001a | T001b | T012 |
| US1-OC-01 | T002a | T002b | T012 |
| US1-OC-02 | T003a | T003b | T012 |
| US1-OC-03 | T004a | T004b | T012 |
| US1-OC-04 | T005a | T005b | T012 |
| US1-OC-06 | T006a | T006b | T012 |
| US1-OC-07 | T007a | T007b | T012 |
| US1-OC-08 | T008a | T008b | T012 |
| US1-OC-09 | T009a | T009b | T012 |
| US1-OC-10 | T010a | T010b | T012 |
| US1-OC-11 | T011a | T011b | T012 |
| US1-API-01~US1-API-09 | T013a~T021a | T013b~T021b | T022 |
| US1-DEP-01 | T023a | T023b | T024 |
| US1-AJ-01~US1-AJ-05 | T025a~T029a | T025b~T029b | T030 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 全綠(含 T001b 改寫的三處 001 舊測試已改用 `/v1/completions`、不留 skip);重構任務前後的測試結果相同

---

## Phase 3: User Story 2 - 用 pi 接上 Colab 上的模型 (Priority: P2)

**Goal**: 使用者在連線設定畫面切到 pi,複製 `models.json` 與 `settings.json` 兩段,pi 就能用 Colab 上的模型,包括工具呼叫,自動壓縮的預留不超過 context 的四分之一

**Independent Test**: 照 `testplan.md` § 3 的全部案例:E2 以 `uv run pytest tests/unit/test_connect.py tests/integration/test_api_connect.py`、跨端點驗收以 `uv run pytest tests/e2e/test_006_connect.py` 執行全綠

### E2 後端 UI API(FastAPI REST 與 SSE)

- [x] T031a [US2] 🔴 /tdd 紅燈:在 `tests/unit/test_connect.py` 寫 US2-API-01 的測試(以 port 11436、模型 `["qwen2.5-coder:7b"]`、context 32768 呼叫 `connect.pi_models_snippet(...)`;斷言 `providers.cgb.baseUrl` 是 `http://{{host}}:11436/v1`、`api` 是 `openai-completions`、`apiKey` 是 `ollama`、`compat` 是 `{"supportsDeveloperRole":false,"supportsReasoningEffort":false}`、模型項目是 `{"id":"qwen2.5-coder:7b","name":"qwen2.5-coder:7b","reasoning":false,"input":["text"],"contextWindow":32768,"maxTokens":4096}`),執行確認它因為「`api` 寫成 `openai-responses`;少了 `compat`,pi 送 developer role 給 Ollama」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-004、FR-005;`research.md` § R3
- [x] T031b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/connect.py` 只寫讓 US2-API-01 通過的程式碼(把 T021b 的最小版 `pi_models_snippet` 補成完整的 `providers.cgb`:`baseUrl`、`api`、`apiKey`、`compat` 與 `models` 陣列);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T031a)
  - 🧪 `testplan.md` § US2-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-004、FR-005;`research.md` § R3
- [x] T032a [US2] 🔴 /tdd 紅燈:在 `tests/unit/test_connect.py` 寫 US2-API-02 的測試(以 context 4096、16384、32767 各呼叫 `connect.pi_models_snippet(...)` 與 `connect.pi_settings_snippet(...)`;斷言 `maxTokens` 分別是 2048、4096、4096,`settings.json` 片段的 `compaction.reserveTokens` 分別是 1024、4096、8191),執行確認它因為「預留沒有無條件捨去;或 `maxTokens` 固定 4096」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-005、FR-013;`plan.md` § 待決問題 Q15
- [x] T032b [US2] 🟢 /tdd 綠燈:在 `src/cgb/domain/connect.py` 只寫讓 US2-API-02 通過的程式碼(`maxTokens` 為 `min(4096, ⌊context ÷ 2⌋)`;新增 `pi_settings_snippet(context_length)` 回 `{"compaction":{"reserveTokens":⌊context ÷ 4⌋}}` 的 JSON 文字,`context_length` 為 None 時回 None);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T032a)
  - 🧪 `testplan.md` § US2-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-005、FR-013;`plan.md` § 待決問題 Q15
- [x] T033a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_api_connect.py` 寫 US2-API-03 的測試(工作階段就緒的預設資料;送 `GET /api/connect`;斷言 `snippets.piModels` 解析後的 `contextWindow` 是 4096、`snippets.piSettings` 解析後是 `{"compaction":{"reserveTokens":1024}}` 且 `reserveTokens` 欄位也是 1024),執行確認它因為「回應只給 opencode 的片段」這類實作而失敗
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`;`contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-004、FR-005、FR-013
- [x] T033b [US2] 🟢 /tdd 綠燈:在 `src/cgb/api/connect.py` 只寫讓 US2-API-03 通過的程式碼(`snippets.piModels` 與 `snippets.piSettings` 改用 `domain/connect.py` 的完整函式,`reserveTokens` 為 `⌊contextLength ÷ 4⌋`);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T033a)
  - 🧪 `testplan.md` § US2-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`;`contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-004、FR-005、FR-013
- [x] T034 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T031b~T033b 記下的重構清單(範圍限 `src/cgb/domain/connect.py`、`src/cgb/api/connect.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/unit/test_connect.py`、`tests/integration/test_api_connect.py` 的斷言(依賴 T033b)
  - 🧪 `testplan.md` § US2-API-01~US2-API-03
  - 📎 `testplan.md` § 3.1

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器接真的後端

- [x] T035a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_006_connect.py` 寫 US2-AJ-01 的測試(工作階段就緒的預設資料;打開連線設定頁,切到 pi 分頁;斷言看到 `models.json` 與 `settings.json` 兩段、各有「複製」,`models.json` 的 `baseUrl` 是 `http://127.0.0.1:11436/v1`,下方寫著放進 `~/.pi/agent/models.json`、`~/.pi/agent/settings.json` 與 `pi --model cgb/<模型>`),執行確認它因為「pi 分頁只有 `models.json`;或主機名稱沒替換」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `prototype/connect.html` § `[data-state="pi"]`;`contracts/ui.openapi.yaml` § `paths./connect.get`
  - 📎 `spec.md` § FR-004、FR-013、NFR-002
- [x] T035b [US2] 🟢 /tdd 綠燈:在 `src/cgb/static/connect.html` 與 `src/cgb/static/js/connect.js` 只寫讓 US2-AJ-01 通過的程式碼(pi 分頁補上 `settings.json` 一段與使用方式,每段各有 `data-copy`;`snippets.piSettings` 為 null 時整段不顯示);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T035a)
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `prototype/connect.html` § `[data-state="pi"]`;`contracts/ui.openapi.yaml` § `paths./connect.get`
  - 📎 `spec.md` § FR-004、FR-013、NFR-002
- [x] T036a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_006_connect.py` 寫 US2-AJ-02 的測試(同 US2-AJ-01 的畫面;按 `settings.json` 那段的「複製」;斷言讀回剪貼簿的內容和畫面上的 `settings.json` 片段完全相同);T026b 的 `[data-copy]` 通用複製處理依按鈕的 `data-copy` 取對應片段,T035b 補上 `settings.json` 的按鈕後這個案例會被滿足:先執行確認通過,再暫時讓所有複製按鈕都複製第一段片段,確認斷言失敗後撤回
  - 🧪 `testplan.md` § US2-AJ-02
  - ⚙ `prototype/connect.html` § `.btn-small`
  - 📎 `spec.md` § FR-013;`plan.md` § 待決問題 Q25
- [x] T036b [US2] 🟢 /tdd 綠燈:US2-AJ-02 由 T026b 的 `[data-copy]` 通用複製處理滿足,確認不需要為這個案例改程式碼;紅燈時若它其實沒有通過,才在 `src/cgb/static/js/connect.js` 只寫讓 US2-AJ-02 通過的程式碼(依賴 T036a)
  - 🧪 `testplan.md` § US2-AJ-02
  - ⚙ `prototype/connect.html` § `.btn-small`
  - 📎 `spec.md` § FR-013
- [x] T037 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T035b~T036b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T036b)
  - 🧪 `testplan.md` § US2-AJ-01~US2-AJ-02
  - 📎 `testplan.md` § 3.2

### 介面覆蓋(US2)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui.openapi.yaml` § `components.schemas.ConnectSnippets`(pi 片段) | T031b、T032b、T033b | T031a、T032a、T033a |
| `ui.openapi.yaml` § `paths./connect.get`(pi 片段) | T033b、T035b | T033a、T035a |
| `ui.openapi.yaml` § `components.schemas.ConnectInfo`(pi 片段) | T033b | T033a |
| `connect.html` § `[data-state="pi"]` | T035b | T035a |
| `connect.html` § `.btn-small` | T036b | T036a |

### 測試案例覆蓋(US2)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US2-API-01~US2-API-03 | T031a~T033a | T031b~T033b | T034 |
| US2-AJ-01~US2-AJ-02 | T035a~T036a | T035b~T036b | T037 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 全綠;重構任務前後的測試結果相同

---

## Phase 4: User Story 3 - context 太小時提醒並給建議值 (Priority: P3)

**Goal**: 目前套用的 context 小於 16384 時,連線設定畫面顯示提醒、依顯示記憶體估的建議值與兩種改法;讀不到目前設定時片段不帶 context 並說明原因

**Independent Test**: 照 `testplan.md` § 4 的全部案例:E2 以 `uv run pytest tests/unit/test_connect.py tests/integration/test_api_connect.py`、跨端點驗收以 `uv run pytest tests/e2e/test_006_connect.py` 執行全綠

### E2 後端 UI API(FastAPI REST 與 SSE)

- [x] T038a [US3] 🔴 /tdd 紅燈:在 `tests/unit/test_connect.py` 寫 US3-API-01 的測試(依序以顯示記憶體 `12 * GIB`、`12 * GIB - 1`、`40 * GIB`、`None` 呼叫 `connect.recommended_context_length(...)`;斷言分別是 32768、16384、32768、16384,每個都不超過 131072),執行確認它因為「邊界寫成 `>`,剛好 12 GiB 掉到 16384;讀不到時回 None」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-007;`research.md` § R5;`plan.md` § 待決問題 Q11
- [x] T038b [US3] 🟢 /tdd 綠燈:在 `src/cgb/domain/connect.py` 只寫讓 US3-API-01 通過的程式碼(`recommended_context_length(vram_bytes)`:≥ 12 GiB 回 32768,否則與讀不到時回 16384,上限 131072);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T038a)
  - 🧪 `testplan.md` § US3-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-007;`research.md` § R5;`plan.md` § 待決問題 Q11
- [x] T039a [US3] 🔴 /tdd 紅燈:在 `tests/unit/test_connect.py` 寫 US3-API-02 的測試(依序以 context 4096、16383、16384、`None` 呼叫 `connect.should_warn(...)`;斷言分別是 true、true、false、false),執行確認它因為「用 `<=`,剛好 16384 也提醒;讀不到時提醒」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [x] T039b [US3] 🟢 /tdd 綠燈:在 `src/cgb/domain/connect.py` 只寫讓 US3-API-02 通過的程式碼(`should_warn(context_length)`:不是 None 且小於 16384 才是 true);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T039a)
  - 🧪 `testplan.md` § US3-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-006;`research.md` § R4
- [x] T040a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_connect.py` 寫 US3-API-03 的測試(工作階段就緒,context 4096、顯示記憶體 15360 MiB;送 `GET /api/connect`;斷言 `shouldWarn` 是 true、`recommendedMinContextLength` 是 16384、`recommendedContextLength` 是 32768),執行確認它因為「提醒由前端自己算,後端沒給」這類實作而失敗(T029b 的最小版 `recommendedContextLength` 固定 16384)
  - 🧪 `testplan.md` § US3-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-006、FR-007
- [x] T040b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/connect.py` 只寫讓 US3-API-03 通過的程式碼(`shouldWarn` 與 `recommendedContextLength` 改用 `domain/connect.py` 的 `should_warn`、`recommended_context_length`,顯示記憶體取 `catalog.list()` 的 `vramBytes`);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T040a)
  - 🧪 `testplan.md` § US3-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`
  - 📎 `spec.md` § FR-006、FR-007
- [x] T041a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_connect.py` 寫 US3-API-04 的測試(工作階段就緒,005 的 `ollama.status` 是 `unknown`;送 `GET /api/connect`;斷言 `contextLength` 是 null、`shouldWarn` 是 false、`reason` 是 null,opencode 片段沒有 `limit`、pi 片段沒有 `contextWindow` 且 `maxTokens` 是 4096,`snippets.piSettings` 是 null),執行確認它因為「讀不到時寫進 `limit.context: null` 或 4096」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`;`contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-008;`plan.md` § 待決問題 Q9、Q15
- [x] T041b [US3] 🟢 /tdd 綠燈:在 `src/cgb/domain/connect.py` 與 `src/cgb/api/connect.py` 只寫讓 US3-API-04 通過的程式碼(`contextLength` 為 null 時 `opencode_snippet` 不寫 `limit`、`pi_models_snippet` 不寫 `contextWindow` 且 `maxTokens` 為 4096、`piSettings` 為 null、`reserveTokens` 為 null);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T041a)
  - 🧪 `testplan.md` § US3-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`;`contracts/ui.openapi.yaml` § `components.schemas.ConnectSnippets`
  - 📎 `spec.md` § FR-008;`plan.md` § 待決問題 Q9、Q15
- [x] T042 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T038b~T041b 記下的重構清單(範圍限 `src/cgb/domain/connect.py`、`src/cgb/api/connect.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/unit/test_connect.py`、`tests/integration/test_api_connect.py` 的斷言(依賴 T041b)
  - 🧪 `testplan.md` § US3-API-01~US3-API-04
  - 📎 `testplan.md` § 4.1

### 跨端點驗收(`tests/e2e/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器接真的後端

- [x] T043a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_006_connect.py` 寫 US3-AJ-01 的測試(工作階段就緒,context 4096;打開連線設定頁;斷言看到提醒,寫著目前 4096、建議 32768,以及「開啟前在 Ollama 設定填 context 長度」與「套用並重啟」兩種改法,附回首頁的連結且連得到 `index.html#ollama-tuning`;片段仍然顯示、可以複製),執行確認它因為「提醒時把片段藏起來(plan Q17);或沒寫改法」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-01
  - ⚙ `prototype/connect.html` § `[data-state="low-context"]`、`.notice`、`.notice-warn`、`.note-list`;`prototype/index.html` § `[data-state="normal"]`、`[data-state="applying"]`、`#ollama-tuning`
  - 📎 `spec.md` § FR-006、FR-007、NFR-002;`plan.md` § 待決問題 Q14、Q17、Q26
- [x] T043b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/connect.html` 與 `src/cgb/static/js/connect.js` 只寫讓 US3-AJ-01 通過的程式碼(`shouldWarn` 為 true 時顯示 `low-notice`:目前值、下限、建議值、顯示記憶體與兩種改法,連結指向 005 已做好的 `index.html#ollama-tuning`,那一頁的 `normal`、`applying` 畫面不由本任務重做,`plan.md` § 待決問題 Q26;片段照樣顯示);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T043a)
  - 🧪 `testplan.md` § US3-AJ-01
  - ⚙ `prototype/connect.html` § `[data-state="low-context"]`、`.notice`、`.notice-warn`、`.note-list`;`prototype/index.html` § `[data-state="normal"]`、`[data-state="applying"]`、`#ollama-tuning`
  - 📎 `spec.md` § FR-006、FR-007、NFR-002;`plan.md` § 待決問題 Q14、Q17、Q26
- [x] T044a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_006_connect.py` 寫 US3-AJ-02 的測試(工作階段以覆蓋值 context 32768 開到就緒;打開連線設定頁;斷言沒有提醒區塊),執行確認它因為「一律顯示提醒」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-02
  - ⚙ `prototype/connect.html` § `[data-state="normal"]`
  - 📎 `spec.md` § FR-006
- [x] T044b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/js/connect.js` 只寫讓 US3-AJ-02 通過的程式碼(`shouldWarn` 為 false 時不顯示 `low-notice`);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T044a)
  - 🧪 `testplan.md` § US3-AJ-02
  - ⚙ `prototype/connect.html` § `[data-state="normal"]`
  - 📎 `spec.md` § FR-006
- [x] T045a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_006_connect.py` 寫 US3-AJ-03 的測試(工作階段就緒,005 的 `ollama.status` 是 `unknown`;打開連線設定頁;斷言看到「讀不到目前的 Ollama 設定,片段不帶 context 長度」的說明、pi 分頁沒有 `settings.json` 那段),執行確認它因為「讀不到時顯示 context `null`,或仍顯示 `settings.json`」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-03
  - ⚙ `prototype/connect.html` § `[data-state="unknown-context"]`
  - 📎 `spec.md` § FR-008、NFR-002;`plan.md` § 待決問題 Q9
- [x] T045b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/connect.html` 與 `src/cgb/static/js/connect.js` 只寫讓 US3-AJ-03 通過的程式碼(`contextLength` 為 null 時顯示 `unknown-notice`、context 欄位寫「讀不到」,`piSettings` 為 null 時 pi 分頁不渲染 `settings.json` 與它的使用步驟);執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T045a)
  - 🧪 `testplan.md` § US3-AJ-03
  - ⚙ `prototype/connect.html` § `[data-state="unknown-context"]`
  - 📎 `spec.md` § FR-008、NFR-002;`plan.md` § 待決問題 Q9
- [x] T046 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T043b~T045b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T045b)
  - 🧪 `testplan.md` § US3-AJ-01~US3-AJ-03
  - 📎 `testplan.md` § 4.2

### 介面覆蓋(US3)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui.openapi.yaml` § `components.schemas.ConnectInfo`(提醒與建議值) | T038b、T039b、T040b、T041b | T038a、T039a、T040a、T041a |
| `ui.openapi.yaml` § `paths./connect.get`(提醒、建議值與讀不到設定) | T040b、T041b | T040a、T041a |
| `ui.openapi.yaml` § `components.schemas.ConnectSnippets`(讀不到設定時不帶 context) | T041b | T041a |
| `connect.html` § `[data-state="low-context"]` | T043b | T043a |
| `connect.html` § `.notice` | T043b | T043a |
| `connect.html` § `.notice-warn` | T043b | T043a |
| `connect.html` § `.note-list` | T043b | T043a |
| `index.html` § `[data-state="normal"]` | T043b | T043a |
| `index.html` § `[data-state="applying"]` | T043b | T043a |
| `index.html` § `#ollama-tuning` | T043b | T043a |
| `connect.html` § `[data-state="normal"]` | T044b | T044a |
| `connect.html` § `[data-state="unknown-context"]` | T045b | T045a |

### 測試案例覆蓋(US3)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US3-API-01~US3-API-04 | T038a~T041a | T038b~T041b | T042 |
| US3-AJ-01~US3-AJ-03 | T043a~T045a | T043b~T045b | T046 |

**Checkpoint**: `uv run pytest -q -p no:cacheprovider` 再加 `uv run pytest -m realrun_local -q -p no:cacheprovider` 全綠;重構任務前後的測試結果相同

---

## Phase 5: 全域測試區

**Purpose**: 照 `testplan.md` § 5 驗證跨故事的 NFR 與 SC;故事裡已經有案例涵蓋的彙整見 `testplan.md` § 5.1,這裡排 § 5.2 的 4 個 📏 實跑案例(沒有全域的行為測試案例,所以沒有重構任務)。結果寫進 `specs/006-agent-client-connect/measurements.md`

### 整合實跑

> 時機為「整合」的實跑案例:要開真的 Colab、花 compute units、需要使用者本人在場。**執行前先停下問使用者本人**,同意之後才照 001 testplan 的實跑共同護欄 P1~P9 做(名稱前綴 `cgb-test-`、預算、P3 收尾);和 005 G-04 共用同一台 T4;不讀寫桌機的 `~/.config/colab-cli/`,一律用暫存的 `HOME`;token 與 endpoint 不印出,比對只印長度與 sha256 前 8 碼;只在桌機上跑,不碰 Tower、Pi、NPM、AdGuard

- [x] T047 [G] 📏 量測:撰寫 `tests/realrun/test_006_g_04.py`(標 `realrun`),在和 005 G-04 共用的那一台 T4 的 `cgb-test-` 工作階段(已下載 `qwen2.5:7b`,以覆蓋值 context 32768 開啟(順便驗 research R5 的建議值))接真的本系統相容端點,照 G-01 的做法(從 `GET /api/connect` 取 opencode 片段、換掉主機與 port、寫進暫存 `HOME` 的 `opencode.json`、在暫存專案資料夾執行 `opencode run -m cgb/qwen2.5:7b`,opencode 以 `env -i` 只留 `PATH`,`HOME` 與四個 `XDG_*` 指到暫存資料夾)做同一個讀 `secret.txt` 的任務,同時記下 `/api/ps` 的 `size` 與 `size_vram`,和門檻(輸出含 `紫色長頸鹿 42` 且有 `read` 工具呼叫;`size_vram` 等於 `size`)比較,並記下總耗時與這次用掉的 compute units,結果寫進 `specs/006-agent-client-connect/measurements.md`;開 Colab T4、花 compute units、需要本人在場;照 001 testplan 的實跑共同護欄 P1~P9(`specs/001-session-model-catalog/testplan.md` § 實跑案例的共同護欄):名稱前綴 `cgb-test-`、和 005 G-04(`specs/005-ollama-machine-tuning/tasks.md` 的 T173)共用同一台 T4、結束後照 P3 確認 `colab sessions` 沒有 `cgb-test-` 開頭的工作階段;不讀寫桌機的 `~/.config/colab-cli/`,一律用暫存的 `HOME`;token 與 endpoint 不印出,比對只印長度與 sha256 前 8 碼;只在桌機上跑,不碰 Tower、Pi、NPM、AdGuard;**執行前先停下問使用者本人**,同意之後才開始;判定者:腳本;樣本:同 G-01
  - 🧪 `testplan.md` § G-04
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`;`contracts/ui.openapi.yaml` § `paths./connect.get`
  - 📎 `spec.md` § SC-004;`research.md` § R5

### 本機實跑(`realrun_local`,時機:節內)

> 不開 Colab、不花錢;由主 agent 在全域測試區做,在 E3、E2、E1 都完成之後。臨時 `ollama serve` 另取 port、暫存 `HOME` 與 `OLLAMA_MODELS`;**不對桌機 127.0.0.1:11434 送請求**;opencode 與 pi 一律在暫存 `HOME` 執行

- [x] T048 [G] 📏 量測:撰寫 `tests/realrun/test_006_g_01.py`(標 `realrun_local`,`plan.md` § 待決問題 Q20 的做法 a):另起臨時 `ollama serve`(另取 port、暫存 `HOME` 與 `OLLAMA_MODELS`、`OLLAMA_CONTEXT_LENGTH=16384`,已下載 `qwen2.5:3b`),用 `live_servers` 起本系統,替身 `FakeTunnel` 回報的 `baseUrl` 指向臨時 serve、`FakeColabControl` 回報 context 16384,模型目錄由臨時 serve 的 `/api/tags` 讀;暫存專案資料夾放 `secret.txt`(內容 `紫色長頸鹿 42`);從 `GET /api/connect` 取 opencode 片段,把 `{{host}}` 換成 `127.0.0.1`、port 換成本系統相容端點的測試 port,原樣寫進暫存 `HOME` 的 `opencode.json`,在暫存專案資料夾執行 `opencode run -m cgb/qwen2.5:3b "讀 secret.txt,只回答檔案內容"`,上限 300 秒;記下 opencode 的結束碼、輸出有沒有 `紫色長頸鹿 42`、臨時 serve 有沒有收到帶 `tools` 的 `/v1/chat/completions`、opencode 的 JSON 事件裡有沒有 `read` 工具呼叫與總耗時,和門檻(結束碼 0、輸出含 `紫色長頸鹿 42`、有 `tools` 的請求與 `read` 工具呼叫)比較,結果寫進 `specs/006-agent-client-connect/measurements.md`;不開 Colab、不花錢;opencode 以 `env -i` 只留 `PATH`,`HOME` 與四個 `XDG_*` 指到暫存資料夾,不讀寫使用者的 `~/.config/opencode`;臨時 serve 與本系統都只聽 127.0.0.1、port 避開 11434~11436 與 8780;**不對桌機 127.0.0.1:11434 送請求**,也不執行沒有指定 `OLLAMA_HOST` 的 `ollama` 指令;結束後停掉臨時 serve 的行程群組並確認已結束;判定者:腳本;樣本:固定的 `secret.txt`(沒有用來調整規則)
  - 🧪 `testplan.md` § G-01
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`;`contracts/ui.openapi.yaml` § `paths./connect.get`
  - 📎 `spec.md` § SC-001、FR-001、FR-002、FR-003、FR-009;`research.md` § R2、R8;`plan.md` § 待決問題 Q20
- [x] T049 [G] 📏 量測:撰寫 `tests/realrun/test_006_g_02.py`(標 `realrun_local`),環境同 G-01;另以 `npm install --prefix <暫存資料夾> @mariozechner/pi-coding-agent` 安裝 pi(不全域安裝);從 `GET /api/connect` 取 pi 的 `models.json` 與 `settings.json` 片段,同樣換掉主機與 port,寫進暫存 `HOME` 的 `~/.pi/agent/`,在暫存專案資料夾執行 `PI_OFFLINE=1 pi -p --no-session --mode json --model cgb/qwen2.5:3b "讀 secret.txt,只回答檔案內容"`,上限 300 秒;記下 pi 的結束碼、輸出有沒有 `紫色長頸鹿 42`、JSON 事件裡有沒有 `read` 工具呼叫、臨時 serve 有沒有收到壓縮的請求(這一回合有沒有因為 `threshold` 觸發自動壓縮)與總耗時,和門檻(結束碼 0、輸出含 `紫色長頸鹿 42`、有 `read` 工具呼叫、沒有自動壓縮)比較,結果寫進 `specs/006-agent-client-connect/measurements.md`;不開 Colab、不花錢;護欄同 G-01(`env -i` 暫存 `HOME`、只聽 127.0.0.1、port 避開 11434~11436 與 8780、不對 11434 送請求、結束後確認臨時 serve 已結束),pi 裝在暫存資料夾,不讀寫使用者的 `~/.pi`;判定者:腳本;樣本:同 G-01
  - 🧪 `testplan.md` § G-02
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`;`contracts/ui.openapi.yaml` § `paths./connect.get`
  - 📎 `spec.md` § SC-002、FR-004、FR-005、FR-013、FR-009;`research.md` § R3、R8;`plan.md` § 待決問題 Q20
- [x] T050 [G] 📏 量測:撰寫 `tests/integration/test_006_g_03.py`(不標 `realrun`,只用測試行程內的假伺服器,`plan.md` § 待決問題 Q28),假 Ollama 回 `SseReply`、每 0.1 秒送一段、共 20 段,經本系統送 `stream:true` 的請求 5 次,記下每一段的延遲與最大值,和門檻(5 次的每一段延遲都 ≤ 0.5 秒)比較,結果寫進 `specs/006-agent-client-connect/measurements.md`;只用測試行程內的假伺服器、不開 Colab、不花錢,不對 127.0.0.1:11434 送請求;判定者:腳本;樣本:固定 20 段
  - 🧪 `testplan.md` § G-03
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post`
  - 📎 `spec.md` § SC-003、NFR-001;`plan.md` § 待決問題 Q28

### 測試案例覆蓋(全域)

| testplan 案例 | 任務 |
|---|---|
| G-01 | T048 |
| G-02 | T049 |
| G-03 | T050 |
| G-04 | T047 |

**Checkpoint**: 全部測試綠燈;`specs/006-agent-client-connect/measurements.md` 的 G-01~G-04 每一項都寫了數字與是否過門檻(G-04 只在使用者本人同意並在場時實跑,沒跑的寫「未實跑」並在完成報告列為未驗證),沒過的列為待決問題

---

## Dependencies & Execution Order

- Phase 1 Setup(無任務)→ Phase 2(US1)→ Phase 3(US2)→ Phase 4(US3)→ Phase 5 全域測試區;每個故事的 Checkpoint 交給使用者確認後才進下一個 phase
- 同一個 phase 的 E3、E2、E11 三節平行;跨端點驗收在三節都完成後由主 agent 做
- 同一個檔不同時改:`src/cgb/domain/connect.py` 由 US1 的 E2 節(T013b)建立,US2、US3 的 E2 節(T031b、T032b、T038b、T039b、T041b)接著擴充;`src/cgb/api/connect.py` 由 T015b 建立,T017b、T018b、T021b、T029b(跨端點驗收裡的最小版本)、T033b、T040b、T041b 依序修改;`src/cgb/static/js/connect.js` 由 T025b 建立,之後的跨端點驗收任務依序修改
- E3 節的 T001b 是第一個破壞 001 舊測試的綠燈,三處舊測試都在那裡改寫;`tests/fakes/ollama_server.py` 的 `SseReply` 由 T003a 建立,G-03(T050)也用它
- 📏 量測:G-01~G-03 不開 Colab,由主 agent 在全域測試區做;G-04(T047)要開 Colab、花 compute units,先停下問使用者本人,同意之後才做
