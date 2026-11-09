# Tasks: Colab GPU 工作階段管理與模型目錄

**Input**: `specs/001-session-model-catalog/` 的設計文件(本 spec package)

**Prerequisites**: plan.md、spec.md、research.md、techstack.md、testplan.md、contracts/ui.openapi.yaml、contracts/ui-events.asyncapi.yaml、contracts/ollama-compat.openapi.yaml、contracts/colab-cli.openapi.yaml、contracts/tunnel.openapi.yaml、contracts/remote-ollama.openapi.yaml、contracts/model-library.openapi.yaml、contracts/google-oauth.openapi.yaml、contracts/store.dbml、prototype/、deploy/

**Tests**: 依 `testplan.md` 切分。testplan 的每個行為測試案例對應一組 `/tdd` 紅燈與綠燈任務,每個「使用者故事 × 端點」節最後一個 `/tdd` 重構任務;量測與人工驗證的案例對應 📏 任務。

**Organization**: 依 `testplan.md` 的使用者故事分 phase;每個故事底下依 `testplan.md` 的端點分節(E1 前端 UI、E2 後端 UI API、E3 Ollama 相容端點、E4 資料庫、E5 Colab CLI、E6 SSH 通道、E7 遠端 Ollama、E8 Ollama 官方模型庫、E9 Google OAuth、E10 檔案系統、E11 部署與網路),外加一節跨端點驗收,最後是介面覆蓋表與測試案例覆蓋表。全域測試區自成一個 phase,放在所有故事之後。範疇是使用者故事 1~4(plan.md Q110 把故事 4 拉回本迭代)。

## Format: `[ID] [Story] [步驟] Description`,底下接 🧪、⚙ 與 📎

- **[Story]**:所屬的使用者故事(US1、US2、US3、US4);全域測試區寫 `[G]`
- **[步驟]**:這個任務是 `/implement` 交給誰做的哪一步
  - 🔴 `/tdd 紅燈`:寫一個測試案例的測試,執行確認它失敗
  - 🟢 `/tdd 綠燈`:只寫讓同一個案例通過的程式碼,執行全部測試確認都通過
  - 🔵 `/tdd 重構`:在全部測試綠燈下,整理這一節綠燈任務記下的重構清單,不改行為、不改斷言
  - 📏 量測:照 testplan 案例的條件量測或人工驗證,記下數字與門檻比較;是唯一不對應 `/tdd` 的開發任務
  - 不標步驟的只限三類:工具鏈設定、原樣複製 spec package 的規格檔、CI 設定
- **紅綠成對**:一個 testplan 案例對應同一個三位數的 `a`(🔴)與 `b`(🟢),`b` 依賴 `a`
- **誰做、怎麼排**:同一個 phase 的端點節各交給一個 subagent 平行做;跨端點驗收節在端點節都完成、驗收過後由主 agent 做。每一節裡照任務編號一次做一個任務,做完才做下一個,不跳號;任務寫了「依賴」別節的任務時,那幾節改成依序做
- **⏸**:描述開頭(步驟標記之後)是 ⏸ 的任務是延後的任務,原因寫在 ⏸ 後面
- 每個任務都寫出確切的檔案路徑
- **🧪**:這個任務對應的 `testplan.md` 案例 ID;🔵 寫這一節所有案例的範圍;不標步驟的任務不寫這一行
- **⚙**:這個任務要做出來或測到的介面元素:至少照 `testplan.md` 受測操作表的「規格錨點」欄寫,再加上這個任務實際做出或斷言的介面元素
- **📎**:做這個任務時要對照的依據:`spec.md` § FR / NFR / SC / 邊界情況、`research.md` § R、`plan.md` § Q 或段落名、`techstack.md` § 段落名
- **📏 實跑**:所有打真實 Colab、ollama.com、Google 或起真容器的 📏 任務,照 `testplan.md` § 實跑案例的共同護欄 P9 的順序,在全部故事與全域測試區的行為測試都綠燈、使用者同意之後整批執行;各故事的 Checkpoint 不等它們

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 建好工具鏈、套件骨架、`create_app` 的注入點、五個轉接層的替身、假執行檔、測試 fixture 與實跑護欄,並依 plan.md Q85 把 spec package 的 `Dockerfile`、`compose.yaml` 搬到 repo 根目錄、`prepare-data.sh` 與 `healthcheck.py` 搬到 `deploy/`;這裡不寫任何會被案例斷言的行為

- [ ] T001 建立 `pyproject.toml` 與 `uv.lock`(uv 專案,套件 `cgb`,`src/` 版面):runtime 依賴 `fastapi==0.162.2`、`uvicorn==0.54.0`、`httpx==0.28.1`、`sse-starlette==3.7.0`、`google-auth-oauthlib==1.5.0`、`google-colab-cli==0.7.5`;開發依賴 `pytest==9.2.0`、`pytest-asyncio==1.4.1.post1`、`playwright==1.64.1`、`pytest-playwright==0.10.0`;`[tool.pytest.ini_options]` 設 `asyncio_mode = "auto"`、`testpaths = ["tests"]`、marker `realrun`(預設以 `-m "not realrun"` 排除,實跑要明確帶 `-m realrun`);README 不寫;完成條件:`uv sync` 成功、`uv run playwright install chromium` 成功、`uv run pytest` 收集 0 個測試且 exit code 為 5
  - 📎 `techstack.md` § 一覽、依賴;`plan.md` § Project Structure
- [ ] T002 建立套件與測試的資料夾骨架(只有空的 `__init__.py`,沒有任何邏輯):`src/cgb/__init__.py`、`src/cgb/api/`、`src/cgb/ollama_compat/`、`src/cgb/services/`、`src/cgb/adapters/`、`src/cgb/adapters/scripts/`、`src/cgb/repos/`、`src/cgb/db/`、`src/cgb/domain/`、`src/cgb/static/`、`src/cgb/static/js/`、`tests/unit/`、`tests/integration/`、`tests/realrun/`、`tests/realrun/scripts/`、`tests/e2e/`、`tests/fakes/`、`tests/fixtures/`;再建立 `.gitignore`,只放 Python 工具鏈的排除(`.venv/`、`__pycache__/`、`.pytest_cache/`)與機密的排除(`.env`、`data/`、`*.sqlite3`、`token.json`、`sessions.json`、`id_ed25519*`),讓實作期間不會誤 commit(G-03 的紅燈改用對照組,plan.md Q114)
  - 📎 `plan.md` § Project Structure、待決問題 Q85
- [ ] T003 建立 `src/cgb/app.py` 的 `create_app(*, db_path, clock, name_prefix, timeouts, colab, tunnel, remote_ollama, model_library, google_oauth)`(注入點照 plan.md Q95:時鐘、開啟總時限、重連時限與節奏、健康檢查間隔、通道就緒期限、健康檢查逾時與名稱前綴,預設值是正式值、不開放給使用者;`name_prefix` 必須以 `cgb-` 開頭,Q109)與 `src/cgb/adapters/errors.py` 的 `AdapterError(code, message, stderr_last_line=None)`;`create_app` 只回傳 UI 與 Ollama 相容端點兩個還沒有任何路由的 FastAPI app(`AppPair`)與共用的 `state`,沒有任何行為;路由、服務與資料表都由各案例的綠燈任務加上(plan.md Q112)
  - 📎 `plan.md` § 待決問題 Q95、Q96、Q109;`research.md` § R12
- [ ] T004 建立 `tests/fakes/`:`FakeColabControl`、`FakeTunnel`、`FakeRemoteOllama`、`FakeModelLibrary`、`FakeGoogleOAuth` 五個替身類別,方法名照規格檔 `operationId` 的 snake_case(`get_cli_version`、`list_sessions`、`create_session`、`start_ollama`、`probe_resources`、`stop_session`、`get_usage`;`ensure_key`、`open_tunnel`、`check_health`、`close_tunnel`、`cleanup_residual`;`get_version`、`list_local_models`、`list_loaded_models`、`pull_model`、`show_model`、`generate`、`chat`、`embed`、`preload`;`search_library`、`list_model_tags`、`get_manifest`;`build_authorization_url`、`request_token`);每個方法可由測試設定回傳值或丟出 `AdapterError(code)`、可設成「等測試放行」(`gate`),並記下每次呼叫的參數;另建 `tests/fakes/ollama_server.py`:測試行程內 127.0.0.1 隨機 port 的假 Ollama HTTP 伺服器,依劇本回 JSON、NDJSON(可逐行等測試放行)、中途斷線或不回應,並記下收到的方法、路徑、query、標頭與本文;`FakeRemoteOllama` 背後就是它,`FakeTunnel.open_tunnel` 回報的本機 port 指到它
  - 📎 `plan.md` § 待決問題 Q96、Q97;`research.md` § R12
- [ ] T005 建立 `tests/fixtures/bin/colab` 與 `tests/fixtures/bin/ssh` 兩個假的執行檔(Python,`chmod 755`),依收到的參數產生輸出:測試在 `CGB_FAKE_SCRIPT` 指到的 JSON 劇本裡,以子指令與參數(argv 去掉程式名)為鍵寫好 stdout、stderr、exit code、睡多久、要不要常駐或分出子行程;argv 對不到任何一條劇本時印 `fake colab: 沒有對應這組參數的劇本` 到 stderr 並 exit 2,劇本寫錯的參數不會被當成正確;每次執行把 argv、stdin 讀到的內容(或 EOF)與環境變數附加到 `CGB_FAKE_LOG` 指到的 JSON Lines 檔
  - 📎 `plan.md` § 待決問題 Q96;`testplan.md` § 1. 待測端點
- [ ] T006 建立 `tests/fixtures/library/`:合成的 ollama.com 搜尋頁(第 1 頁有 `href="/library/qwen2.5"`、`href="/library/qwen2.5-coder"`、`href="/someone/qwen2.5-custom"` 與 `hx-get="/search?page=2"`,第 2 頁沒有下一頁連結)、`qwen2.5` 版本頁(`0.5b` 398MB、`7b` 4.7GB、`7b-cloud`)與 registry manifest JSON(`qwen2.5:7b` 4 層合計 4,683,087,332、`config.size` 487;另一個沒有任何層的雲端版本);只放合成資料,不放從 ollama.com 抓下來的原文
  - 📎 `testplan.md` § 1. 待測端點;`research.md` § R6
- [ ] T007 建立 `tests/conftest.py` 與 `tests/e2e/conftest.py` 的共用 fixture:每個測試一個暫存 SQLite 檔;以縮短的時限呼叫 `create_app`(開啟總時限 3 秒、健康檢查間隔 0.2 秒、重連時限 2 秒、重連節奏「立即、0.05、0.1、0.2 秒,之後每 0.3 秒」、通道就緒期限 1 秒、健康檢查逾時 0.3 秒,名稱前綴 `cgb-test-`)與可推進的假時鐘;`httpx.ASGITransport` 的用戶端;測試行程內的 uvicorn(整合測試用 127.0.0.1 隨機 port,跨端點驗收用 UI 127.0.0.1:8781、Ollama 相容端點 127.0.0.1:11437);`PATH` 前面加上 `tests/fixtures/bin`、`HOME` 指到暫存資料夾的 fixture;Playwright 的 `base_url`
  - 📎 `testplan.md` § 使用者故事 1 的預設資料;`plan.md` § 待決問題 Q95、Q97、Q99
- [ ] T008 建立 `tests/realrun/conftest.py`:實跑共同護欄 P1–P9 的 fixture,只在 `-m realrun` 時生效:`mktemp -d` 的暫存目錄與 `HOME=<暫存目錄>/home`(其 `.config/colab-cli` 指向 `<暫存目錄>/data/colab-cli`)、照 P9 與 Q101 把桌機既有的 `~/.config/colab-cli/token.json` 複製到 `<暫存目錄>/data/colab-cli/token.json`(0600,只比對長度與 sha256 前 8 碼、不印內容、不複製 `sessions.json`),複製後以 `HOME=<暫存目錄>/home colab usage` 確認授權有效,沒過就停下、執行任何 `colab` 指令前先以 `CGB_DATA_DIR=<暫存目錄>/data` 跑一次 `deploy/prepare-data.sh`(P8)、開始前與結束後各一次 `colab usage` 記下三行並在每個案例前檢查 60 分鐘與 1.8 compute units 的上限(P2)、不論成敗都做的 P3 收尾(只對 `cgb-test-` 開頭的名稱 `colab stop` 再回讀、`docker compose -p cgb-test down`、確認沒有殘留的 `ProxyCommand=colab ssh --proxy-mode -s cgb-test-` 行程)、錄下原始輸出前把網址換成 `<網址>` 的遮蔽器(先以一個已知的假 endpoint 驗過);量測結果寫進 `specs/001-session-model-catalog/measurements.md` 的共用函式;這個任務本身不執行任何 `colab` 指令
  - 📎 `testplan.md` § 實跑案例的共同護欄;`plan.md` § 待決問題 Q101、Q108
- [ ] T009 把 spec package 的 `deploy/Dockerfile` 複製到 repo 根目錄的 `Dockerfile`,`COPY specs/001-session-model-catalog/deploy/prepare-data.sh /usr/local/bin/cgb-prepare-data` 改成 `COPY deploy/prepare-data.sh /usr/local/bin/cgb-prepare-data`,`COPY specs/001-session-model-catalog/deploy/healthcheck.py /usr/local/bin/cgb-healthcheck` 改成 `COPY deploy/healthcheck.py /usr/local/bin/cgb-healthcheck`,其餘不改
  - ⚙ `deploy/Dockerfile` § 全檔
  - 📎 `plan.md` § Project Structure、待決問題 Q85
- [ ] T010 把 spec package 的 `deploy/Dockerfile.dockerignore` 複製到 repo 根目錄的 `Dockerfile.dockerignore`(和 `Dockerfile` 同一層,BuildKit 才讀得到),`!specs/001-session-model-catalog/deploy/prepare-data.sh` 改成 `!deploy/prepare-data.sh`,`!specs/001-session-model-catalog/deploy/healthcheck.py` 改成 `!deploy/healthcheck.py`,其餘不改
  - ⚙ `deploy/Dockerfile.dockerignore` § 全檔
  - 📎 `plan.md` § 待決問題 Q85、Q94
- [ ] T011 把 spec package 的 `deploy/compose.yaml` 複製到 repo 根目錄的 `compose.yaml`,`services.cgb.build.context` 從 `../../..` 改成 `.`,`services.cgb.build.dockerfile` 從 `specs/001-session-model-catalog/deploy/Dockerfile` 改成 `Dockerfile`,其餘不改(volumes 的 `${CGB_HOST_DATA:-cgb-data}` 不是相對路徑,不改)
  - ⚙ `deploy/compose.yaml` § 全檔
  - 📎 `plan.md` § Project Structure、待決問題 Q85
- [ ] T012 把 spec package 的 `deploy/.env.example` 複製到 repo 根目錄的 `.env.example`(和 `compose.yaml` 同一層),內容不改(打開確認過沒有相對路徑)
  - ⚙ `deploy/.env.example` § 全檔
  - 📎 `plan.md` § 待決問題 Q81、Q90、Q91、Q92
- [ ] T013 把 spec package 的 `deploy/prepare-data.sh` 複製到 repo 的 `deploy/prepare-data.sh`,保留可執行權限,內容不改(打開確認過只讀 `CGB_DATA_DIR`、`CGB_COLAB_CONFIG_DIR`、`CGB_SSH_IDENTITY_PATH`,沒有相對路徑)
  - 📎 `plan.md` § 待決問題 Q59、Q82、Q85、Q87
- [ ] T014 把 spec package 的 `deploy/healthcheck.py` 複製到 repo 的 `deploy/healthcheck.py`,保留可執行權限,內容不改(打開確認過只讀 `CGB_UI_PORT`、`CGB_OLLAMA_PORT`,沒有相對路徑)
  - 📎 `plan.md` § 待決問題 Q85、Q89

### 介面覆蓋(Setup)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `compose.yaml` § `services.cgb` | T011 | T254a、T256a |

**Checkpoint**: `uv sync`、`uv run pytest`(0 個測試)與 `docker compose config` 都成功;`git status` 沒有 `.env` 或資料夾被追蹤

---

## Phase 2: User Story 1 - 一鍵開啟與結束 GPU 工作階段 (Priority: P1) 🎯 MVP

**Goal**: 使用者在 UI 登入 Colab、選類型按一下「開啟」就有一台就緒的執行環境與模型服務,用完按「結束」就釋放;被收回、斷線、後端重啟或變更類型時,UI 顯示的狀態仍然是真的,也查得到最近的紀錄

**Independent Test**: 照 `testplan.md` § 2 的全部案例:E2、E5、E6、E9、E4 以 `uv run pytest tests/integration` 執行全綠;跨端點驗收以 `uv run pytest tests/e2e/test_us1_*.py`(Playwright,測試行程內的 uvicorn,UI 127.0.0.1:8781)執行全綠;📏 案例照 P9 在使用者同意後整批實跑

### E2 後端 UI API(FastAPI REST 與 SSE)

- [ ] T015a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-01 的測試(送 `POST /api/session {runtimeType:{gpu:"T4",highMem:false}}`,再依序放行三個步驟),執行確認它因為「等開啟流程跑完才回應」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.get`;`contracts/store.dbml` § `Table sessions`
  - 📎 `spec.md` § FR-001、FR-003
- [ ] T015b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/__init__.py`、`src/cgb/db/schema.py`、`src/cgb/db/connection.py`、`src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;同一個任務在 `src/cgb/api/__init__.py` 把 UI API 的路由掛進 Setup 建好的 `create_app`,在 `src/cgb/db/schema.py` 建出 `sessions` 表(本任務是 `src/cgb/db/schema.py` 的建立者,E4 節的任務依賴它)(依賴 T015a)
  - 🧪 `testplan.md` § US1-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.get`;`contracts/store.dbml` § `Table sessions`
  - 📎 `spec.md` § FR-001、FR-003
- [ ] T016a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-02 的測試(送 `POST /api/session {runtimeType:{gpu:"L4",highMem:true}}`),執行確認它因為「開啟時忽略使用者選的類型,一律用 T4」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.get`
  - 📎 `spec.md` § FR-009
- [ ] T016b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T016a)
  - 🧪 `testplan.md` § US1-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.get`
  - 📎 `spec.md` § FR-009
- [ ] T017a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-03 的測試(分別送 `gpu` 為 `"t4"`、`"TPU"`、`"V100"`,以及 `highMem` 為 `"yes"` 的開啟),執行確認它因為「把使用者字串直接放進 `--gpu`(CLI 會把認不得的名稱當成 A100,扣更多點數)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-009
- [ ] T017b [US1] 🟢 /tdd 綠燈:在 `src/cgb/domain/errors.py`、`src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;錯誤代碼與繁體中文訊息的對照表建在 `src/cgb/domain/errors.py`(本故事 E2 第一個斷言 `code` 的案例)(依賴 T017a)
  - 🧪 `testplan.md` § US1-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-009
- [ ] T018a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-04 的測試(同時送兩個 `POST /api/session`(`asyncio.gather`)),執行確認它因為「先查「有沒有工作階段」再寫入,兩個請求都通過檢查而各開一台」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、邊界情況
- [ ] T018b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T018a)
  - 🧪 `testplan.md` § US1-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006、邊界情況
- [ ] T019a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-05 的測試(各送一次 `POST /api/session`),執行確認它因為「只擋 `opening`,`ready` 時照樣再開」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006
- [ ] T019b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T019a)
  - 🧪 `testplan.md` § US1-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006
- [ ] T020a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-06 的測試(送 `POST /api/session`),執行確認它因為「不先確認授權就開,等 `colab new` 卡在等授權碼或失敗才回報」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./auth.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T020b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T020a)
  - 🧪 `testplan.md` § US1-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./auth.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T021a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-07 的測試(送 `DELETE /api/session`,再放行 `stop_session`),執行確認它因為「只關通道沒有呼叫 `stop_session`(執行環境繼續扣點)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.delete`
  - 📎 `spec.md` § FR-002、FR-003
- [ ] T021b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T021a)
  - 🧪 `testplan.md` § US1-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.delete`
  - 📎 `spec.md` § FR-002、FR-003
- [ ] T022a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-08 的測試(送 `DELETE /api/session`;等狀態穩定後再送一次 `DELETE /api/session`,這次 `stop_session` 回成功),執行確認它因為「釋放失敗時照樣標成乾淨的已結束、沒有警告」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.delete`
  - 📎 `spec.md` § FR-007
- [ ] T022b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T022a)
  - 🧪 `testplan.md` § US1-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.delete`
  - 📎 `spec.md` § FR-007
- [ ] T023a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-09 的測試(各送一次 `DELETE /api/session`),執行確認它因為「沒有工作階段時仍呼叫 `colab stop`,或回 202 讓 UI 顯示「結束中」」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.delete`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002
- [ ] T023b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T023a)
  - 🧪 `testplan.md` § US1-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.delete`、`components.schemas.Error`
  - 📎 `spec.md` § FR-002
- [ ] T024a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-10 的測試(送 `POST /api/session`),執行確認它因為「開啟失敗時沒附原因」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-003、FR-007
- [ ] T024b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T024a)
  - 🧪 `testplan.md` § US1-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-003、FR-007
- [ ] T025a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-11 的測試(送 `POST /api/session`),執行確認它因為「`start_ollama` 失敗就直接標失敗,沒有釋放已配置好的執行環境」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-007
- [ ] T025b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T025a)
  - 🧪 `testplan.md` § US1-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-007
- [ ] T026a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-12 的測試(送 `POST /api/session`),執行確認它因為「只有各步驟自己的時限(`start_ollama` 300 秒),沒有開啟流程的總時限」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-007、SC-001
- [ ] T026b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T026a)
  - 🧪 `testplan.md` § US1-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-007、SC-001
- [ ] T027a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-13 的測試(送 `DELETE /api/session`,之後才放行 `create_session`),執行確認它因為「中途取消 `colab new`(伺服器已配置、本機卻沒記下名稱,留下 `[?]` 的遺留)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.delete`
  - 📎 `spec.md` § 邊界情況、FR-007
- [ ] T027b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T027a)
  - 🧪 `testplan.md` § US1-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.delete`
  - 📎 `spec.md` § 邊界情況、FR-007
- [ ] T028a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-14 的測試(送 `POST /api/session`),執行確認它因為「沒比對開啟前後的 `unnamed` 清單,把逾時當成乾淨的失敗」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-007
- [ ] T028b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T028a)
  - 🧪 `testplan.md` § US1-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-007
- [ ] T029a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-15 的測試(送 `POST /api/session`),執行確認它因為「不先確認名稱在列就建立通道(`colab ssh --proxy-mode` 找不到名稱會自己開一台新的,Q64)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-001、FR-006;`plan.md` § 待決問題 Q64
- [ ] T029b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T029a)
  - 🧪 `testplan.md` § US1-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-001、FR-006;`plan.md` § 待決問題 Q64
- [ ] T030a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-16 的測試(送 `POST /api/session`),執行確認它因為「收到 `TUNNEL_NOT_FOUND` 只標失敗,沒有結束意外開出的那台(扣點、違反只有一個工作階段)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-006、FR-007
- [ ] T030b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T030a)
  - 🧪 `testplan.md` § US1-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-006、FR-007
- [ ] T031a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_health.py` 寫 US1-API-17 的測試(`FakeTunnel.check_health` 開始回 `TUNNEL_UNREACHABLE`,同時 `list_sessions` 不再列出 `cgb-test-0001`),執行確認它因為「健康檢查失敗後只是一直重連到時限才失聯(沒有查 `colab sessions`)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-17
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`
  - 📎 `spec.md` § FR-003、FR-004
- [ ] T031b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/health_monitor.py`、`src/cgb/domain/session_state.py` 只寫讓 US1-API-17 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T031a)
  - 🧪 `testplan.md` § US1-API-17
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`
  - 📎 `spec.md` § FR-003、FR-004
- [ ] T032a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_health.py` 寫 US1-API-18 的測試(`check_health` 回失敗 1 次;重連第 1 輪 `open_tunnel` 回 `TUNNEL_ALREADY_CONNECTED`、第 2 輪成功),執行確認它因為「重連時另開新的執行環境」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-18
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`、`paths./tunnels/{sessionName}/reconnect.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-004
- [ ] T032b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/health_monitor.py`、`src/cgb/domain/session_state.py` 只寫讓 US1-API-18 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T032a)
  - 🧪 `testplan.md` § US1-API-18
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`、`paths./tunnels/{sessionName}/reconnect.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-004
- [ ] T033a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_health.py` 寫 US1-API-19 的測試(讓重連跑到時限),執行確認它因為「每輪沒先 `close_tunnel`,新連線撞上 `TUNNEL_ALREADY_CONNECTED`」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-19
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/reconnect.post`
  - 📎 `spec.md` § FR-004
- [ ] T033b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/health_monitor.py`、`src/cgb/domain/session_state.py` 只寫讓 US1-API-19 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T033a)
  - 🧪 `testplan.md` § US1-API-19
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/reconnect.post`
  - 📎 `spec.md` § FR-004
- [ ] T034a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_health.py` 寫 US1-API-20 的測試(讓重連進行),執行確認它因為「`colab sessions` 本身失敗(例如家裡網路斷了)就當成執行環境不在,誤判被收回」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-20
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/reconnect.post`
  - 📎 `spec.md` § FR-004
- [ ] T034b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/health_monitor.py`、`src/cgb/domain/session_state.py` 只寫讓 US1-API-20 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T034a)
  - 🧪 `testplan.md` § US1-API-20
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/reconnect.post`
  - 📎 `spec.md` § FR-004
- [ ] T035a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_health.py` 寫 US1-API-21 的測試(讓重連跑到時限),執行確認它因為「時限到只改狀態,沒有釋放執行環境」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-21
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/reconnect.post`
  - 📎 `spec.md` § FR-004
- [ ] T035b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/health_monitor.py`、`src/cgb/domain/session_state.py` 只寫讓 US1-API-21 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T035a)
  - 🧪 `testplan.md` § US1-API-21
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/reconnect.post`
  - 📎 `spec.md` § FR-004
- [ ] T036a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_health.py` 寫 US1-API-22 的測試(讓重連跑到時限),執行確認它因為「重連逾時後釋放失敗卻沒有警告」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-22
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/reconnect.post`
  - 📎 `spec.md` § FR-004、FR-007
- [ ] T036b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/health_monitor.py`、`src/cgb/domain/session_state.py` 只寫讓 US1-API-22 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T036a)
  - 🧪 `testplan.md` § US1-API-22
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/reconnect.post`
  - 📎 `spec.md` § FR-004、FR-007
- [ ] T037a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_recovery.py` 寫 US1-API-23 的測試(關掉 app,以同一個 SQLite 檔與同一份替身狀態建立新的 app),執行確認它因為「重啟後把工作階段當成不存在、回 `none` 或另開一台」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § FR-005
- [ ] T037b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-23 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T037a)
  - 🧪 `testplan.md` § US1-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § FR-005
- [ ] T038a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_recovery.py` 寫 US1-API-24 的測試(重建 app),執行確認它因為「重啟後照資料庫標成就緒,沒有確認執行環境還在」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § FR-005
- [ ] T038b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-24 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T038a)
  - 🧪 `testplan.md` § US1-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § FR-005
- [ ] T039a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_recovery.py` 寫 US1-API-25 的測試(重建 app,送 `GET /api/session`),執行確認它因為「把不是本系統開的執行環境接手或關掉」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § 邊界情況
- [ ] T039b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-25 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T039a)
  - 🧪 `testplan.md` § US1-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § 邊界情況
- [ ] T040a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_recovery.py` 寫 US1-API-26 的測試(重建 app),執行確認它因為「只看 `cgb-` 前綴就結束(會關到別的實例開的執行環境,Q100)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-26
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § FR-007;`plan.md` § 待決問題 Q100、Q122
- [ ] T040b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-26 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T040a)
  - 🧪 `testplan.md` § US1-API-26
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § FR-007;`plan.md` § 待決問題 Q100、Q122
- [ ] T041a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_switch.py` 寫 US1-API-27 的測試(送 `POST /api/session/restart {runtimeType:{gpu:"L4",highMem:false}}`,讓流程跑完),執行確認它因為「先開新的再關舊的(同時兩台)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`、`paths./sessions.get`、`paths./downloads.get`;`contracts/store.dbml` § `Table download_jobs`
  - 📎 `spec.md` § FR-010
- [ ] T041b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/runtime_switch.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US1-API-27 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;FR-010 重新下載要的 `download_jobs` 表(`origin`、`preloadOnComplete`)與最小的 `GET /api/downloads` 在這裡建立,故事 3 的任務接著擴充(依賴 T041a)
  - 🧪 `testplan.md` § US1-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`、`paths./sessions.get`、`paths./downloads.get`;`contracts/store.dbml` § `Table download_jobs`
  - 📎 `spec.md` § FR-010
- [ ] T042a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_switch.py` 寫 US1-API-28 的測試(送 `POST /api/session/restart {runtimeType:{gpu:"L4",highMem:false}}`),執行確認它因為「新類型開不起來時回頭沿用舊的,或舊的沒關」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-28
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`、`paths./downloads.get`;`contracts/store.dbml` § `Table download_jobs`
  - 📎 `spec.md` § FR-010
- [ ] T042b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/runtime_switch.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US1-API-28 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T042a)
  - 🧪 `testplan.md` § US1-API-28
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`、`paths./downloads.get`;`contracts/store.dbml` § `Table download_jobs`
  - 📎 `spec.md` § FR-010
- [ ] T043a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_switch.py` 寫 US1-API-29 的測試(送 `POST /api/session/restart {runtimeType:{gpu:"L4",highMem:false}}`),執行確認它因為「沒有工作階段時把 restart 當成開啟」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-29
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-010
- [ ] T043b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/runtime_switch.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US1-API-29 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T043a)
  - 🧪 `testplan.md` § US1-API-29
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-010
- [ ] T044a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auth.py` 寫 US1-API-30 的測試(送兩次 `POST /api/auth/authorizations`,再以第一次的 `flowId` 送授權碼),執行確認它因為「多次取得連結都共用同一組 `state` 與 `code_verifier`」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-30
  - ⚙ `contracts/ui.openapi.yaml` § `paths./auth/authorizations.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T044b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/auth.py`、`src/cgb/services/auth.py` 只寫讓 US1-API-30 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T044a)
  - 🧪 `testplan.md` § US1-API-30
  - ⚙ `contracts/ui.openapi.yaml` § `paths./auth/authorizations.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T045a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auth.py` 寫 US1-API-31 的測試(以 `{code:"  4/cgb-test-code  "}` 送出),執行確認它因為「沒去空白,貼上時多帶的空白讓 Google 回 invalid_grant」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-31
  - ⚙ `contracts/ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendAuthUpdated`
  - 📎 `spec.md` § FR-008
- [ ] T045b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/auth.py`、`src/cgb/services/auth.py` 只寫讓 US1-API-31 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T045a)
  - 🧪 `testplan.md` § US1-API-31
  - ⚙ `contracts/ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendAuthUpdated`
  - 📎 `spec.md` § FR-008
- [ ] T046a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auth.py` 寫 US1-API-32 的測試(送錯的授權碼,再以同一個 `flowId` 送正確的),執行確認它因為「換 token 失敗就讓流程代號失效,使用者只能重新取得連結」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-32
  - ⚙ `contracts/ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T046b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/auth.py`、`src/cgb/services/auth.py` 只寫讓 US1-API-32 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T046a)
  - 🧪 `testplan.md` § US1-API-32
  - ⚙ `contracts/ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T047a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_auth.py` 寫 US1-API-33 的測試(重建 app 後以原本的 `flowId` 送授權碼),執行確認它因為「把 `code_verifier` 寫進檔案或資料庫(違反 Q17)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-33
  - ⚙ `contracts/ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008;`plan.md` § 待決問題 Q17
- [ ] T047b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/auth.py`、`src/cgb/services/auth.py` 只寫讓 US1-API-33 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T047a)
  - 🧪 `testplan.md` § US1-API-33
  - ⚙ `contracts/ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008;`plan.md` § 待決問題 Q17
- [ ] T048a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-34 的測試(送 `POST /api/session`),執行確認它因為「授權過期被當成工作階段失聯」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-34
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./auth.get`
  - 📎 `spec.md` § 邊界情況、FR-008
- [ ] T048b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-34 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T048a)
  - 🧪 `testplan.md` § US1-API-34
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./auth.get`
  - 📎 `spec.md` § 邊界情況、FR-008
- [ ] T049a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_history.py` 寫 US1-API-35 的測試(送 `GET /api/sessions`),執行確認它因為「只列已結束的」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-35
  - ⚙ `contracts/ui.openapi.yaml` § `paths./sessions.get`;`contracts/store.dbml` § `Table session_transitions`
  - 📎 `spec.md` § FR-028
- [ ] T049b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/history.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-35 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;`session_transitions` 表在這裡建立(E4 節的 US1-DB-02 依賴它)(依賴 T049a)
  - 🧪 `testplan.md` § US1-API-35
  - ⚙ `contracts/ui.openapi.yaml` § `paths./sessions.get`;`contracts/store.dbml` § `Table session_transitions`
  - 📎 `spec.md` § FR-028
- [ ] T050a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_history.py` 寫 US1-API-36 的測試(送 `GET /api/sessions/cgb-test-0001`),執行確認它因為「開啟中的每一步沒有各記一筆」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-36
  - ⚙ `contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`;`contracts/store.dbml` § `Table session_transitions`
  - 📎 `spec.md` § FR-028、FR-003
- [ ] T050b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/history.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-36 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T050a)
  - 🧪 `testplan.md` § US1-API-36
  - ⚙ `contracts/ui.openapi.yaml` § `paths./sessions/{name}.get`;`contracts/store.dbml` § `Table session_transitions`
  - 📎 `spec.md` § FR-028、FR-003
- [ ] T051a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_health.py` 寫 US1-API-37 的測試(等 1.1 秒(至少 5 次健康檢查),不送任何 Ollama 相容端點的請求),執行確認它因為「健康檢查經過 Ollama 相容端點送 `/api/version`,每 15 秒重設閒置計時,工作階段永遠不會閒置結束(Q89)」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-37
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`;`contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § FR-004;`plan.md` § 待決問題 Q89
- [ ] T051b [US1] 🟢 /tdd 綠燈:在 `src/cgb/services/health_monitor.py`、`src/cgb/domain/session_state.py` 只寫讓 US1-API-37 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T051a)
  - 🧪 `testplan.md` § US1-API-37
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`;`contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § FR-004;`plan.md` § 待決問題 Q89
- [ ] T052a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_events.py` 寫 US1-API-38 的測試(開一條 `/api/events`),執行確認它因為「連上時不送快照,UI 要等下一次變化才知道狀態」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-38
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`、`paths./session.delete`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-003
- [ ] T052b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/events.py`、`src/cgb/services/event_bus.py` 只寫讓 US1-API-38 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T052a)
  - 🧪 `testplan.md` § US1-API-38
  - ⚙ `contracts/ui.openapi.yaml` § `paths./events.get`、`paths./session.delete`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-003
- [ ] T053a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-39 的測試(送開啟,每放行一步就送一次 `GET /api/session`),執行確認它因為「開啟中只回 `opening`、不更新 `step`」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-39
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.get`
  - 📎 `spec.md` § NFR-001
- [ ] T053b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-39 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T053a)
  - 🧪 `testplan.md` § US1-API-39
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.get`
  - 📎 `spec.md` § NFR-001
- [ ] T054a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_api_session.py` 寫 US1-API-40 的測試(開啟失敗後,讀 `GET /api/session`、`GET /api/sessions` 與 SSE 收到的每一則事件),執行確認它因為「把轉接層的原始錯誤或 endpoint 放進 `message` 給 UI」這類實作而失敗
  - 🧪 `testplan.md` § US1-API-40
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./events.get`、`paths./session.get`、`paths./sessions.get`
  - 📎 `spec.md` § NFR-010、FR-007
- [ ] T054b [US1] 🟢 /tdd 綠燈:在 `src/cgb/api/session.py`、`src/cgb/services/session_lifecycle.py`、`src/cgb/domain/session_state.py`、`src/cgb/repos/sessions.py` 只寫讓 US1-API-40 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T054a)
  - 🧪 `testplan.md` § US1-API-40
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./events.get`、`paths./session.get`、`paths./sessions.get`
  - 📎 `spec.md` § NFR-010、FR-007
- [ ] T055 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T015b~T054b 記下的重構清單(範圍限 `src/cgb/api/`、`src/cgb/services/`、`src/cgb/domain/`、`src/cgb/repos/`、`src/cgb/db/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T054b)
  - 🧪 `testplan.md` § US1-API-01~US1-API-40
  - 📎 `testplan.md` § 2.1

### E5 Colab CLI(google-colab-cli,外部程式)

- [ ] T056a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-01 的測試(各呼叫一次),執行確認它因為「不檢查版本,改版後的輸出照舊規則解析出錯的值」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./version.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [ ] T056b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T056a)
  - 🧪 `testplan.md` § US1-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./version.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [ ] T057a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-02 的測試(呼叫),執行確認它因為「找不到執行檔時拋未處理的 `FileNotFoundError` 讓後端啟動失敗」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./version.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [ ] T057b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T057a)
  - 🧪 `testplan.md` § US1-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./version.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [ ] T058a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-03 的測試(呼叫),執行確認它因為「把 `[colab] ` 提示行或空行當成資料而解析失敗」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-03
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./sessions.get`
  - 📎 `spec.md` § FR-003、FR-005
- [ ] T058b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T058a)
  - 🧪 `testplan.md` § US1-CLI-03
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./sessions.get`
  - 📎 `spec.md` § FR-003、FR-005
- [ ] T059a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-04 的測試(呼叫),執行確認它因為「把「沒有執行環境」當成格式不符而回 `COLAB_BAD_RESPONSE`」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-04
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./sessions.get`
  - 📎 `spec.md` § FR-003
- [ ] T059b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T059a)
  - 🧪 `testplan.md` § US1-CLI-04
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./sessions.get`
  - 📎 `spec.md` § FR-003
- [ ] T060a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-05 的測試(呼叫),執行確認它因為「比對不到的行直接略過,使改版後所有執行環境「消失」、被判成收回」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-05
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./sessions.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004
- [ ] T060b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T060a)
  - 🧪 `testplan.md` § US1-CLI-05
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./sessions.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004
- [ ] T061a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-06 的測試(以 `name=cgb-test-0001, gpu=T4, high_mem=false` 呼叫;再以 `high_mem=true` 呼叫一次),執行確認它因為「stdin 繼承後端的,CLI 等授權碼時整個開啟卡住」這類實作而失敗;另把 `create_session` 實際傳出的兩組 argv 交給真的 `colab` 0.7.5 解讀(Setup 的 T001 已裝進開發環境):`HOME` 指到空的暫存資料夾、其 `.config/colab-cli/settings.json` 為 `{"enable_update_check": false}`、stdin 接 `/dev/null`、不帶授權檔,斷言 stderr 沒有參數錯誤(`No such option`、`Usage:`、`Invalid value`),只出現未登入或要授權的訊息(不連網、不會配置執行環境;外部程式端點要有讓真的工具解讀參數的測試)
  - 🧪 `testplan.md` § US1-CLI-06
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./new.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-009
- [ ] T061b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T061a)
  - 🧪 `testplan.md` § US1-CLI-06
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./new.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-009
- [ ] T062a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-07 的測試(呼叫),執行確認它因為「看到 `Session READY.` 或 exit 0 就當成功」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-07
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./new.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-007
- [ ] T062b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T062a)
  - 🧪 `testplan.md` § US1-CLI-07
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./new.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-007
- [ ] T063a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-08 的測試(以 `gpu="t4"` 與 `gpu="TPU"` 各呼叫一次),執行確認它因為「把不在 `GpuType` 的字串放進命令列(CLI 會當成 A100)」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-08
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./new.post`
  - 📎 `spec.md` § FR-009
- [ ] T063b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T063a)
  - 🧪 `testplan.md` § US1-CLI-08
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./new.post`
  - 📎 `spec.md` § FR-009
- [ ] T064a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-09 的測試(以 `gpu=L4, high_mem=true` 呼叫),執行確認它因為「把這行 stderr 當成失敗」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-09
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./new.post`
  - 📎 `spec.md` § FR-009
- [ ] T064b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T064a)
  - 🧪 `testplan.md` § US1-CLI-09
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./new.post`
  - 📎 `spec.md` § FR-009
- [ ] T065a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-10 的測試(呼叫),執行確認它因為「stdin 沒接 `/dev/null`,CLI 永遠等授權碼」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-10
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T065b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T065a)
  - 🧪 `testplan.md` § US1-CLI-10
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T066a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-11 的測試(呼叫),執行確認它因為「解析第一行而不是最後一個 `CGB-RESULT` 行」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-11
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`
  - 📎 `spec.md` § FR-001
- [ ] T066b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py`、`src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T066a)
  - 🧪 `testplan.md` § US1-CLI-11
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`
  - 📎 `spec.md` § FR-001
- [ ] T067a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-12 的測試(呼叫),執行確認它因為「第一次就判開啟失敗(research.md R1 實測會偶發)」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-12
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`
  - 📎 `spec.md` § FR-001
- [ ] T067b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py`、`src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T067a)
  - 🧪 `testplan.md` § US1-CLI-12
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`
  - 📎 `spec.md` § FR-001
- [ ] T068a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-13 的測試(呼叫),執行確認它因為「無限重試」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-13
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/probe-resources.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [ ] T068b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py`、`src/cgb/adapters/scripts/probe_resources.py` 只寫讓 US1-CLI-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T068a)
  - 🧪 `testplan.md` § US1-CLI-13
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/probe-resources.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [ ] T069a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-14 的測試(呼叫),執行確認它因為「信 exit 0 當成功」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-14
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-007
- [ ] T069b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py`、`src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US1-CLI-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T069a)
  - 🧪 `testplan.md` § US1-CLI-14
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001、FR-007
- [ ] T070a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-15 的測試(呼叫),執行確認它因為「看到 `not found` 就回錯誤(結束應該是冪等的)」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-15
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./stop.post`
  - 📎 `spec.md` § FR-002、FR-007
- [ ] T070b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T070a)
  - 🧪 `testplan.md` § US1-CLI-15
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./stop.post`
  - 📎 `spec.md` § FR-002、FR-007
- [ ] T071a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-16 的測試(呼叫),執行確認它因為「信 `Session terminated.` 或 exit 0 就回成功(research.md R1:stop 的 exit code 不反映結果)」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-16
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./stop.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-007、SC-003
- [ ] T071b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T071a)
  - 🧪 `testplan.md` § US1-CLI-16
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./stop.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-007、SC-003
- [ ] T072a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-17 的測試(呼叫),執行確認它因為「第一次回讀還在就直接回 `COLAB_STOP_UNCONFIRMED`,沒有再試一次」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-17
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./stop.post`
  - 📎 `spec.md` § FR-007
- [ ] T072b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-17 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T072a)
  - 🧪 `testplan.md` § US1-CLI-17
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./stop.post`
  - 📎 `spec.md` § FR-007
- [ ] T073a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-18 的測試(呼叫),執行確認它因為「遮蔽寫錯,endpoint 原樣進入錯誤訊息與日誌」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-18
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./stop.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-007、NFR-010
- [ ] T073b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-18 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T073a)
  - 🧪 `testplan.md` § US1-CLI-18
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./stop.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-007、NFR-010
- [ ] T074a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-19 的測試(各呼叫一次),執行確認它因為「讀不到用量就當成未登入,把使用者趕去重新登入」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-19
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T074b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-19 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T074a)
  - 🧪 `testplan.md` § US1-CLI-19
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T075a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US1-CLI-20 的測試(呼叫),執行確認它因為「逾時後沒殺子行程或沒 `wait`,留下殭屍」這類實作而失敗
  - 🧪 `testplan.md` § US1-CLI-20
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./sessions.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004
- [ ] T075b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US1-CLI-20 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T075a)
  - 🧪 `testplan.md` § US1-CLI-20
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./sessions.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004
- [ ] T076 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T056b~T075b 記下的重構清單(範圍限 `src/cgb/adapters/colab_cli.py`、`src/cgb/adapters/scripts/`、`src/cgb/domain/colab_output.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T075b)
  - 🧪 `testplan.md` § US1-CLI-01~US1-CLI-20
  - 📎 `testplan.md` § 2.2
- [ ] T077 [US1] 📏 量測:撰寫 `tests/realrun/test_us1_cli_21.py`(`-m realrun`),照 US1-CLI-21 量測。假如:主機上真的 google-colab-cli 0.7.5(不經假執行檔);`<暫存目錄>` 已有照 P9 複製來的 token.json。當:依序執行 `version`、`usage`、`sessions`、`new -s cgb-test-<時間>-adapter --gpu T4`、`sessions`、`exec -f` 啟動 Ollama 腳本、`exec -f` 讀資源腳本、`stop -s cgb-test-<時間>-none`(不存在的名稱)、(US2-RO-03、US1-TUN-10 跑完後)`stop -s cgb-test-<時間>-adapter`、`sessions`;每行輸出用轉接層的同一組 regex 解析。記下的數字與門檻:則1:`version` 的 stdout 是 `Version: 0.7.5`;則2:`usage` 三行都符合 `x-stdout` 的三個 regex;則3:兩次 `sessions` 的每一行都符合 `x-stdout` 的 regex 或以 `[colab] ` 開頭;則4:`new` 的 stdout 有 `[colab] Session READY.`,接著的 `sessions` 列出這個名稱、硬體 T4;則5:兩次 `exec` 的 stdout 最後一個 `CGB-RESULT` 行可解析,`ok` 為 true、`vramTotalBytes` 大於 0;則6:`stop` 不存在的名稱印 `not found` 且 exit code 為 0(替身照這個行為寫);則7:`stop` 之後 60 秒內 `sessions` 不再列出這個名稱(SC-003);則8:`tests/fixtures/bin/colab` 劇本裡每一種輸出,和這次錄到的對應輸出,解析出的欄位名稱相同。副作用與護欄:P1~P9;執行環境 1 台 T4,開到關約 11 分鐘(含 US2-RO-03 與 US1-TUN-10 各約 3 分鐘),整台約 0.21 compute units;子行程帶 `HOME=<暫存目錄>/home`;不呼叫本系統後端;記下 `Connection was lost` 出現的次數(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(regex 比對與 60 秒門檻);樣本:一次實跑(未用於調整替身以外的規則)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US1-CLI-21
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./version.get`、`paths./new.post`、`paths./exec/start-ollama.post`、`paths./stop.post`、`paths./sessions.get`、`paths./usage.get`、`paths./exec/probe-resources.post`
  - 📎 `spec.md` § FR-001、FR-002、FR-007、SC-003;`plan.md` § 待決問題 Q101、Q108

### E6 SSH 通道(OpenSSH 與 `colab ssh --proxy-mode`)

- [ ] T078a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_tunnel.py` 寫 US1-TUN-01 的測試(各呼叫一次(真的 `ssh-keygen`)),執行確認它因為「已有金鑰時覆寫(可能是使用者自己放的)」這類實作而失敗
  - 🧪 `testplan.md` § US1-TUN-01
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./key.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [ ] T078b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/tunnel.py` 只寫讓 US1-TUN-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T078a)
  - 🧪 `testplan.md` § US1-TUN-01
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./key.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [ ] T079a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_tunnel.py` 寫 US1-TUN-02 的測試(以 `cgb-test-0001`、`localPort` 為隨機 port 呼叫),執行確認它因為「ProxyCommand 帶了 `--rm`(斷線就結束執行環境)或開啟用的旗標」這類實作而失敗;另把 `open_tunnel` 實際傳出的 argv 換成 `ssh -G`(去掉 `-N` 與目的地以外不變)交給真的 OpenSSH 解讀,只印解析後的設定、不連線,斷言 `localforward`、`proxycommand`、`batchmode yes`、`identitiesonly yes`、`exitonforwardfailure yes`、`serveraliveinterval 15`、`serveralivecountmax 3` 和規格一致
  - 🧪 `testplan.md` § US1-TUN-02
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`
  - 📎 `spec.md` § FR-001、FR-004
- [ ] T079b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/tunnel.py` 只寫讓 US1-TUN-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T079a)
  - 🧪 `testplan.md` § US1-TUN-02
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`
  - 📎 `spec.md` § FR-001、FR-004
- [ ] T080a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_tunnel.py` 寫 US1-TUN-03 的測試(呼叫),執行確認它因為「沒比對這行,讓 `colab ssh` 意外開出的執行環境繼續跑(扣點,Q64)」這類實作而失敗
  - 🧪 `testplan.md` § US1-TUN-03
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006;`plan.md` § 待決問題 Q64
- [ ] T080b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/tunnel.py` 只寫讓 US1-TUN-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T080a)
  - 🧪 `testplan.md` § US1-TUN-03
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006;`plan.md` § 待決問題 Q64
- [ ] T081a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_tunnel.py` 寫 US1-TUN-04 的測試(每一條字樣各呼叫一次(parametrize)),執行確認它因為「比對順序錯,使 `TUNNEL_ALREADY_CONNECTED` 之類落到 `TUNNEL_FAILED`」這類實作而失敗
  - 🧪 `testplan.md` § US1-TUN-04
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`
  - 📎 `spec.md` § FR-004
- [ ] T081b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/tunnel.py` 只寫讓 US1-TUN-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T081a)
  - 🧪 `testplan.md` § US1-TUN-04
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`
  - 📎 `spec.md` § FR-004
- [ ] T082a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_tunnel.py` 寫 US1-TUN-05 的測試(各呼叫一次),執行確認它因為「期限內第一次被拒就放棄(Ollama 剛啟動還沒聽)」這類實作而失敗
  - 🧪 `testplan.md` § US1-TUN-05
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [ ] T082b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/tunnel.py` 只寫讓 US1-TUN-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T082a)
  - 🧪 `testplan.md` § US1-TUN-05
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-001
- [ ] T083a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_tunnel.py` 寫 US1-TUN-06 的測試(情況 A 假伺服器回 200 與 version;情況 B 假 `ssh` 印 `Timeout, server colab-runtime not responding.` 後結束;情況 C 假伺服器 0.3 秒內不回應;情況 D 假伺服器回 200 與 `<html>`),執行確認它因為「只看 ssh 行程還在就算健康,沒打 `/api/version`」這類實作而失敗
  - 🧪 `testplan.md` § US1-TUN-06
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004
- [ ] T083b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/tunnel.py` 只寫讓 US1-TUN-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T083a)
  - 🧪 `testplan.md` § US1-TUN-06
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-004
- [ ] T084a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_tunnel.py` 寫 US1-TUN-07 的測試(呼叫兩次),執行確認它因為「只對 ssh 的 pid 送訊號,ProxyCommand 留著」這類實作而失敗
  - 🧪 `testplan.md` § US1-TUN-07
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}.delete`
  - 📎 `spec.md` § FR-002、FR-004
- [ ] T084b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/tunnel.py` 只寫讓 US1-TUN-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T084a)
  - 🧪 `testplan.md` § US1-TUN-07
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}.delete`
  - 📎 `spec.md` § FR-002、FR-004
- [ ] T085a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_tunnel.py` 寫 US1-TUN-08 的測試(呼叫),執行確認它因為「用 `pkill ssh` 一類的寬鬆比對,關掉使用者自己的 ssh」這類實作而失敗
  - 🧪 `testplan.md` § US1-TUN-08
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}.delete`
  - 📎 `spec.md` § FR-005
- [ ] T085b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/tunnel.py` 只寫讓 US1-TUN-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T085a)
  - 🧪 `testplan.md` § US1-TUN-08
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}.delete`
  - 📎 `spec.md` § FR-005
- [ ] T086a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_tunnel.py` 寫 US1-TUN-09 的測試(呼叫),執行確認它因為「遮蔽 regex 只換網址的主機、沒換 query 裡的 token」這類實作而失敗
  - 🧪 `testplan.md` § US1-TUN-09
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-010
- [ ] T086b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/tunnel.py` 只寫讓 US1-TUN-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T086a)
  - 🧪 `testplan.md` § US1-TUN-09
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-010
- [ ] T087 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T078b~T086b 記下的重構清單(範圍限 `src/cgb/adapters/tunnel.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T086b)
  - 🧪 `testplan.md` § US1-TUN-01~US1-TUN-09
  - 📎 `testplan.md` § 2.3
- [ ] T088 [US1] 📏 量測:撰寫 `tests/realrun/test_us1_tun_10.py`(`-m realrun`),照 US1-TUN-10 量測。假如:主機上真的 OpenSSH 與 `colab ssh --proxy-mode`;US1-CLI-21 開好的 `cgb-test-<時間>-adapter` 已啟動 Ollama,`colab sessions` 列出它;US2-RO-03 已載入 `qwen2.5:0.5b`。當:建立通道;健康檢查 3 次;以 SIGKILL 殺掉 ssh;立即健康檢查;每 2 秒嘗試一次 `open_tunnel` 直到成功或 120 秒;查 `/api/ps`;`close_tunnel`。記下的數字與門檻:則1:第一次建立在 30 秒內就緒;則2:殺掉 ssh 後的那次健康檢查回失敗,代碼不是健康;則3:重新建立在 120 秒內成功,並記下等了幾秒、中間出現過哪些代碼(Q69);則4:重新建立後 `/api/ps` 仍有 `qwen2.5:0.5b`;則5:`close_tunnel` 後 `localPort` 沒有在聽、沒有 defunct 行程;則6:`close_tunnel` 後 `colab sessions` 仍列出這台(關通道不結束執行環境);則7:這次 stderr 出現過的每一行,都比對得到 `x-stderr-patterns` 的一條或屬於可忽略的行。副作用與護欄:P1~P9;與 US1-CLI-21 共用同一台 T4,本案例約 3 分鐘,占用算在 US1-CLI-21 的 0.21 compute units 之內;本機轉發只綁 127.0.0.1 的隨機 port,不用 11434~11436;金鑰放 `<暫存目錄>/data/ssh/`,不用桌機的 `~/.ssh`(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(30 秒與 120 秒門檻);樣本:一次實跑(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US1-TUN-10
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`、`paths./tunnels/{sessionName}/health.get`、`paths./tunnels/{sessionName}.delete`
  - 📎 `spec.md` § FR-004、FR-005、NFR-002;`plan.md` § 待決問題 Q69、Q101、Q108

### E9 Google OAuth(授權碼流程)

- [ ] T089a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_google_oauth.py` 寫 US1-OA-01 的測試(呼叫兩次),執行確認它因為「沒用 PKCE」這類實作而失敗
  - 🧪 `testplan.md` § US1-OA-01
  - ⚙ `contracts/google-oauth.openapi.yaml` § `paths./o/oauth2/auth.get`
  - 📎 `spec.md` § FR-008
- [ ] T089b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/google_oauth.py` 只寫讓 US1-OA-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T089a)
  - 🧪 `testplan.md` § US1-OA-01
  - ⚙ `contracts/google-oauth.openapi.yaml` § `paths./o/oauth2/auth.get`
  - 📎 `spec.md` § FR-008
- [ ] T090a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_google_oauth.py` 寫 US1-OA-02 的測試(以授權碼與同一次的 `code_verifier` 呼叫),執行確認它因為「沒帶 `code_verifier`」這類實作而失敗
  - 🧪 `testplan.md` § US1-OA-02
  - ⚙ `contracts/google-oauth.openapi.yaml` § `paths./token.post`
  - 📎 `spec.md` § FR-008
- [ ] T090b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/google_oauth.py` 只寫讓 US1-OA-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T090a)
  - 🧪 `testplan.md` § US1-OA-02
  - ⚙ `contracts/google-oauth.openapi.yaml` § `paths./token.post`
  - 📎 `spec.md` § FR-008
- [ ] T091a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_google_oauth.py` 寫 US1-OA-03 的測試(各呼叫一次),執行確認它因為「所有 4xx 都歸成同一個代碼,UI 分不出是授權碼錯還是設定錯」這類實作而失敗
  - 🧪 `testplan.md` § US1-OA-03
  - ⚙ `contracts/google-oauth.openapi.yaml` § `paths./token.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T091b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/google_oauth.py` 只寫讓 US1-OA-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T091a)
  - 🧪 `testplan.md` § US1-OA-03
  - ⚙ `contracts/google-oauth.openapi.yaml` § `paths./token.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T092a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_google_oauth.py` 寫 US1-OA-04 的測試(各呼叫一次),執行確認它因為「沒有 refresh token 也存檔,一小時後授權就過期」這類實作而失敗
  - 🧪 `testplan.md` § US1-OA-04
  - ⚙ `contracts/google-oauth.openapi.yaml` § `paths./token.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T092b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/google_oauth.py` 只寫讓 US1-OA-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T092a)
  - 🧪 `testplan.md` § US1-OA-04
  - ⚙ `contracts/google-oauth.openapi.yaml` § `paths./token.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T093a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_google_oauth.py` 寫 US1-OA-05 的測試(各呼叫一次),執行確認它因為「連不到時拋未處理的例外,API 回 500 沒有原因」這類實作而失敗
  - 🧪 `testplan.md` § US1-OA-05
  - ⚙ `contracts/google-oauth.openapi.yaml` § `paths./token.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T093b [US1] 🟢 /tdd 綠燈:在 `src/cgb/adapters/google_oauth.py` 只寫讓 US1-OA-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T093a)
  - 🧪 `testplan.md` § US1-OA-05
  - ⚙ `contracts/google-oauth.openapi.yaml` § `paths./token.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T094 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T089b~T093b 記下的重構清單(範圍限 `src/cgb/adapters/google_oauth.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T093b)
  - 🧪 `testplan.md` § US1-OA-01~US1-OA-05
  - 📎 `testplan.md` § 2.4
- [ ] T095 [US1] 📏 量測(人工):⏸ 延後:需要使用者本人在場,不在 P9 這一批(plan.md Q101 決定實跑授權改為複製既有 token.json、比對 sha256,US1-OA-06 與 G-01 延後到使用者回來;Q108),使用者回來並同意前不執行;撰寫 `tests/realrun/test_us1_oa_06.py`(`-m realrun`),照 US1-OA-06 量測。假如:延後到使用者在場時另跑(Q101、Q108),不在 P9 這一批;主機上直接跑本系統後端(uvicorn,UI 127.0.0.1:8780、Ollama 相容端點 127.0.0.1:11436),`CGB_DATA_DIR` 指到另一個新的暫存目錄(不沿用複製來的授權);真的 Google OAuth。當:使用者在自己的瀏覽器開連結、登入、貼回授權碼;再取一次連結,貼回 `4/cgb-test-invalid`。記下的數字與門檻:則1:貼回正確授權碼後 30 秒內登入頁顯示已登入;則2:`<暫存目錄>/data/colab-cli/token.json` 存在,權限 0600;則3:`HOME=<暫存目錄>/home colab usage` 印出三行用量(R2 待驗證:CLI 讀得到後端寫的授權檔);則4:貼回 `4/cgb-test-invalid` 後頁面顯示登入失敗與原因,`POST` 的回應 `code` 為 `OAUTH_INVALID_GRANT`;則5:失敗之後「重新取得授權連結」可以按。副作用與護欄:P5、P6、P8;不呼叫 Colab 執行環境,0 compute units,約 5 分鐘;token.json 不印出、不複製到暫存目錄以外,只記長度與 sha256 前 8 碼;使用者在場操作瀏覽器(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:使用者(登入是否完成、畫面是否顯示原因);腳本判定則2、則3;樣本:使用者的 Colab Pro 帳號一次(未用於調整)。使用者在場時另跑,不和 P9 那一批一起;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US1-OA-06
  - 📎 `spec.md` § FR-008;`plan.md` § 待決問題 Q101、Q108

### E4 資料庫(SQLite)

- [ ] T096a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-01 的測試(再插入一筆 `active_slot=1`;再插入一筆 `active_slot` 為 null 的 `ending`),執行確認它因為「`active_slot` 沒有 unique,兩個開啟中的工作階段寫得進去」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-01
  - ⚙ `contracts/store.dbml` § `Table sessions`
  - 📎 `spec.md` § FR-006
- [ ] T096b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US1-DB-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;`src/cgb/db/schema.py` 由 E2 節的 T015b 建立,本節依序接著改,不另寫一份(依賴 T096a、T015b)
  - 🧪 `testplan.md` § US1-DB-01
  - ⚙ `contracts/store.dbml` § `Table sessions`
  - 📎 `spec.md` § FR-006
- [ ] T097a [US1] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US1-DB-02 的測試(關閉連線,以新的連線開同一個檔),執行確認它因為「沒開 WAL」這類實作而失敗
  - 🧪 `testplan.md` § US1-DB-02
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-005、FR-028
- [ ] T097b [US1] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US1-DB-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;`src/cgb/db/schema.py` 與 `session_transitions` 表由 E2 節的 T015b、T049b 建立,本節依序接著改,不另寫一份(依賴 T097a、T015b、T049b)
  - 🧪 `testplan.md` § US1-DB-02
  - ⚙ `contracts/store.dbml` § `Table sessions`、`Table session_transitions`
  - 📎 `spec.md` § FR-005、FR-028
- [ ] T098 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T096b~T097b 記下的重構清單(範圍限 `src/cgb/db/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T097b)
  - 🧪 `testplan.md` § US1-DB-01~US1-DB-02
  - 📎 `testplan.md` § 2.5

### E1 前端 UI(瀏覽器,原生 HTML/CSS/JS)

本故事沒有不靠後端就看得到的行為,工作階段面板、登入頁與紀錄頁的行為都放在跨端點驗收(`testplan.md` § 2.6),這一節沒有任務。

### E3 Ollama 相容端點(FastAPI 轉送)

本故事沒有經 Ollama 相容端點的需求(健康檢查不經這個端點,由 US1-API-37 驗證)(`testplan.md` § 2.7),這一節沒有任務。

### E7 遠端 Ollama(Colab 執行環境上,Ollama API)

本故事沒有 `RemoteOllama` 的案例(`/api/version`、`/api/ps` 由 E2、E6 的案例經替身涵蓋)(`testplan.md` § 2.8),這一節沒有任務。

### E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai)

本故事不涉及模型庫(`testplan.md` § 2.9),這一節沒有任務。

### E10 檔案系統、E11 部署與網路

本故事沒有只屬於這兩個端點的需求(授權檔權限與持久化在全域測試區)(`testplan.md` § 2.10),這一節沒有任務。

### 跨端點驗收(`tests/e2e/`、`tests/realrun/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(或區網程式)接測試行程內真的後端,轉接層用替身;📏 任務改接真的 Colab,照 P9 整批實跑

- [ ] T099a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-01 的測試(打開首頁,不改類型,按「開啟」,依序放行三個步驟),執行確認它因為「前端沒有預選 T4,開啟送出空的 `runtimeType` 回 400」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `prototype/index.html` § `#open`、`#s-steps`、`#r-type`、`[data-state="normal"]`、`[data-state="starting"]`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.get`、`paths./events.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-001、FR-003、FR-009
- [ ] T099b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/style.css`、`src/cgb/static/js/api.js`、`src/cgb/server.py`、`src/cgb/__main__.py`、`src/cgb/app.py`、`src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;同一個任務把 `prototype/style.css` 搬進 `src/cgb/static/style.css`(只用原型的 `var(--…)`,不帶 `prototype/mock.js`),在 `src/cgb/static/js/api.js` 寫共用的 API 呼叫與 SSE 訂閱(plan.md Structure Decision:共用的 SSE 訂閱與 API 呼叫放在同一支模組),在 `src/cgb/app.py` 掛上 `src/cgb/static/`;並建立 `src/cgb/server.py` 的 `serve()`(以同一個 `create_app` 結果在同一個行程起 UI 與 Ollama 相容端點兩個 uvicorn,Ollama 相容端點那一個 port 在本故事先掛空的 app,故事 2 的 T122b 補上路由)與 `src/cgb/__main__.py`(`python -m cgb`:讀 `CGB_LISTEN_HOST`、`CGB_UI_PORT`、`CGB_OLLAMA_PORT`、`CGB_TUNNEL_LOCAL_PORT`、`CGB_DB_PATH`、`CGB_COLAB_CONFIG_DIR`、`CGB_SSH_IDENTITY_PATH`,組出真的轉接層後呼叫 `serve()`;plan.md Q93),測試的 uvicorn fixture 也改走 `serve()`;首頁故事 4 的 `#usage-strip`、`#open-low`、`#r-countdown`、`#r-idle` 留給故事 4 的任務(依賴 T099a)
  - 🧪 `testplan.md` § US1-AJ-01
  - ⚙ `prototype/index.html` § `#open`、`#s-steps`、`#r-type`、`[data-state="normal"]`、`[data-state="starting"]`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.get`、`paths./events.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-001、FR-003、FR-009
- [ ] T100a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-02 的測試(按「結束工作階段」,在確認畫面先按「取消」;再按一次並確認),執行確認它因為「沒有確認步驟,一按就結束」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `prototype/index.html` § `#stop`、`#e-reason`、`[data-state="confirm-stop"]`、`[data-state="ready"]`、`[data-state="ended"]`;`contracts/ui.openapi.yaml` § `paths./session.delete`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-002、FR-003
- [ ] T100b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T100a)
  - 🧪 `testplan.md` § US1-AJ-02
  - ⚙ `prototype/index.html` § `#stop`、`#e-reason`、`[data-state="confirm-stop"]`、`[data-state="ready"]`、`[data-state="ended"]`;`contracts/ui.openapi.yaml` § `paths./session.delete`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-002、FR-003
- [ ] T101a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-03 的測試(按「開啟」),執行確認它因為「失敗後停在「開啟中」」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `prototype/index.html` § `#open`、`#f-reason`、`[data-state="failed"]`;`contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-003
- [ ] T101b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T101a)
  - 🧪 `testplan.md` § US1-AJ-03
  - ⚙ `prototype/index.html` § `#open`、`#f-reason`、`[data-state="failed"]`;`contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-003
- [ ] T102a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-04 的測試(`check_health` 失敗且 `list_sessions` 不再列出它;再按「重新開啟」),執行確認它因為「收回後畫面仍顯示就緒」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-04
  - ⚙ `prototype/index.html` § `#e-reason`、`[data-state="lost"]`、`[data-state="starting"]`;`contracts/ui.openapi.yaml` § `paths./session.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-003、FR-004
- [ ] T102b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T102a)
  - 🧪 `testplan.md` § US1-AJ-04
  - ⚙ `prototype/index.html` § `#e-reason`、`[data-state="lost"]`、`[data-state="starting"]`;`contracts/ui.openapi.yaml` § `paths./session.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-003、FR-004
- [ ] T103a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-05 的測試(`check_health` 失敗 1 次,重連第 2 輪成功),執行確認它因為「重連中沒有顯示,使用者以為還在就緒」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-05
  - ⚙ `prototype/index.html` § `#r-name`、`[data-state="reconnecting"]`、`[data-state="ready"]`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-004
- [ ] T103b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T103a)
  - 🧪 `testplan.md` § US1-AJ-05
  - ⚙ `prototype/index.html` § `#r-name`、`[data-state="reconnecting"]`、`[data-state="ready"]`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-004
- [ ] T104a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-06 的測試(讓重連逾時),執行確認它因為「釋放失敗的警告只在 API 有、畫面沒顯示,使用者不知道還在扣點」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-06
  - ⚙ `prototype/index.html` § `[data-state="lost-timeout"]`、`[data-state="release-failed"]`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-004、FR-007
- [ ] T104b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T104a)
  - 🧪 `testplan.md` § US1-AJ-06
  - ⚙ `prototype/index.html` § `[data-state="lost-timeout"]`、`[data-state="release-failed"]`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-004、FR-007
- [ ] T105a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-07 的測試(第二個分頁按「開啟」),執行確認它因為「前端只靠自己的狀態擋,另一個分頁照樣送出」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-07
  - ⚙ `prototype/index.html` § `#open`、`[data-state="already-open"]`;`contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006
- [ ] T105b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T105a)
  - 🧪 `testplan.md` § US1-AJ-07
  - ⚙ `prototype/index.html` § `#open`、`[data-state="already-open"]`;`contracts/ui.openapi.yaml` § `paths./session.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-006
- [ ] T106a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_login.py` 寫 US1-AJ-08 的測試(在首頁按「開啟」;依引導到登入頁,按「取得授權連結」,在輸入框貼上 `4/cgb-test-code` 送出),執行確認它因為「未登入時「開啟」照送,等 CLI 失敗才回報」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-08
  - ⚙ `prototype/index.html` § `#open`、`[data-state="needs-login"]`;`prototype/login.html` § `#auth-link`、`#code-form`、`#code`、`#auth-chip`、`[data-state="normal"]`、`[data-state="link"]`、`[data-state="signed-in"]`;`contracts/ui.openapi.yaml` § `paths./auth.get`、`paths./auth/authorizations.post`、`paths./auth/authorizations/{flowId}/code.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendAuthUpdated`
  - 📎 `spec.md` § FR-008
- [ ] T106b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/login.html`、`src/cgb/static/js/login.js`、`src/cgb/static/js/header.js`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;頁首的 `#auth-chip`、`#session-pill` 寫在 `src/cgb/static/js/header.js`,之後每一頁共用(依賴 T106a)
  - 🧪 `testplan.md` § US1-AJ-08
  - ⚙ `prototype/index.html` § `#open`、`[data-state="needs-login"]`;`prototype/login.html` § `#auth-link`、`#code-form`、`#code`、`#auth-chip`、`[data-state="normal"]`、`[data-state="link"]`、`[data-state="signed-in"]`;`contracts/ui.openapi.yaml` § `paths./auth.get`、`paths./auth/authorizations.post`、`paths./auth/authorizations/{flowId}/code.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendAuthUpdated`
  - 📎 `spec.md` § FR-008
- [ ] T107a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_login.py` 寫 US1-AJ-09 的測試(送出 `4/wrong`;再讓後端重建後以舊連結送出),執行確認它因為「兩種失敗顯示同一句話,使用者不知道要重新取連結還是重貼授權碼」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-09
  - ⚙ `prototype/login.html` § `#code-form`、`[data-state="failed"]`、`[data-state="link-expired"]`;`contracts/ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T107b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/login.html`、`src/cgb/static/js/login.js`、`src/cgb/static/js/header.js` 只寫讓 US1-AJ-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T107a)
  - 🧪 `testplan.md` § US1-AJ-09
  - ⚙ `prototype/login.html` § `#code-form`、`[data-state="failed"]`、`[data-state="link-expired"]`;`contracts/ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-008
- [ ] T108a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-10 的測試(類型選 L4、勾高 RAM,按「開啟」並放行),執行確認它因為「選擇器的值沒帶進請求」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-10
  - ⚙ `prototype/index.html` § `#open`、`#r-type`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-009
- [ ] T108b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T108a)
  - 🧪 `testplan.md` § US1-AJ-10
  - ⚙ `prototype/index.html` § `#open`、`#r-type`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./session.post`
  - 📎 `spec.md` § FR-009
- [ ] T109a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-11 的測試(選 L4,按「變更類型」,在確認畫面按「確認,結束並重開」,放行全部步驟),執行確認它因為「沒有確認就直接重開」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-11
  - ⚙ `prototype/index.html` § `#switch`、`#r-type`、`[data-state="confirm-switch"]`、`[data-state="switching"]`、`[data-state="ready"]`;`prototype/models.html` § `#catalog`、`[data-state="normal"]`;`contracts/ui.openapi.yaml` § `paths./session/restart.post`、`paths./models.get`
  - 📎 `spec.md` § FR-010
- [ ] T109b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js`、`src/cgb/static/models.html`、`src/cgb/static/js/models.js`、`src/cgb/api/models.py`、`src/cgb/services/catalog.py` 只寫讓 US1-AJ-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;模型頁 `#catalog` 與 `GET /api/models` 只做到讓這個案例看得到已載入的模型(故事 3 的 T151b 擴充)(依賴 T109a)
  - 🧪 `testplan.md` § US1-AJ-11
  - ⚙ `prototype/index.html` § `#switch`、`#r-type`、`[data-state="confirm-switch"]`、`[data-state="switching"]`、`[data-state="ready"]`;`prototype/models.html` § `#catalog`、`[data-state="normal"]`;`contracts/ui.openapi.yaml` § `paths./session/restart.post`、`paths./models.get`
  - 📎 `spec.md` § FR-010
- [ ] T110a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-12 的測試(選 L4,確認變更),執行確認它因為「失敗後畫面回到舊的就緒狀態(實際上已經關掉)」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-12
  - ⚙ `prototype/index.html` § `#switch`、`#f-reason`、`[data-state="failed"]`;`contracts/ui.openapi.yaml` § `paths./session/restart.post`
  - 📎 `spec.md` § FR-010
- [ ] T110b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T110a)
  - 🧪 `testplan.md` § US1-AJ-12
  - ⚙ `prototype/index.html` § `#switch`、`#f-reason`、`[data-state="failed"]`;`contracts/ui.openapi.yaml` § `paths./session/restart.post`
  - 📎 `spec.md` § FR-010
- [ ] T111a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_history.py` 寫 US1-AJ-13 的測試(打開紀錄頁),執行確認它因為「紀錄頁只讀前端自己的狀態,重新整理就空了」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-13
  - ⚙ `prototype/history.html` § `#rows`、`[data-state="normal"]`;`contracts/ui.openapi.yaml` § `paths./sessions.get`
  - 📎 `spec.md` § FR-028
- [ ] T111b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/history.html`、`src/cgb/static/js/history.js` 只寫讓 US1-AJ-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T111a)
  - 🧪 `testplan.md` § US1-AJ-13
  - ⚙ `prototype/history.html` § `#rows`、`[data-state="normal"]`;`contracts/ui.openapi.yaml` § `paths./sessions.get`
  - 📎 `spec.md` § FR-028
- [ ] T112a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-14 的測試(停掉 uvicorn,以同一個 SQLite 檔與替身狀態重新起,重新整理首頁),執行確認它因為「前端重新整理後顯示「未開啟」」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-14
  - ⚙ `prototype/index.html` § `#r-name`、`[data-state="resuming"]`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § FR-005
- [ ] T112b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T112a)
  - 🧪 `testplan.md` § US1-AJ-14
  - ⚙ `prototype/index.html` § `#r-name`、`[data-state="resuming"]`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § FR-005
- [ ] T113a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-15 的測試(打開首頁),執行確認它因為「把它顯示成本系統的工作階段,或提供結束按鈕」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-15
  - ⚙ `prototype/index.html` § `[data-state="foreign"]`;`contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § 邊界情況
- [ ] T113b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T113a)
  - 🧪 `testplan.md` § US1-AJ-15
  - ⚙ `prototype/index.html` § `[data-state="foreign"]`;`contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § 邊界情況
- [ ] T114a [US1] 🔴 /tdd 紅燈:在 `tests/e2e/test_us1_session.py` 寫 US1-AJ-16 的測試(按「停止開啟」(`#cancel-open`),再放行 `create_session`),執行確認它因為「開啟中沒有停止的入口」這類實作而失敗
  - 🧪 `testplan.md` § US1-AJ-16
  - ⚙ `prototype/index.html` § `#cancel-open`、`[data-state="stopping"]`、`[data-state="ended"]`;`contracts/ui.openapi.yaml` § `paths./session.delete`
  - 📎 `spec.md` § 邊界情況、FR-007
- [ ] T114b [US1] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US1-AJ-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T114a)
  - 🧪 `testplan.md` § US1-AJ-16
  - ⚙ `prototype/index.html` § `#cancel-open`、`[data-state="stopping"]`、`[data-state="ended"]`;`contracts/ui.openapi.yaml` § `paths./session.delete`
  - 📎 `spec.md` § 邊界情況、FR-007
- [ ] T115 [US1] 🔵 /tdd 重構:在全部測試綠燈下整理 T099b~T114b 記下的重構清單(範圍限 `src/cgb/static/`、`src/cgb/server.py`、`src/cgb/__main__.py`、`src/cgb/app.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T114b)
  - 🧪 `testplan.md` § US1-AJ-01~US1-AJ-16
  - 📎 `testplan.md` § 2.11
- [ ] T116 [US1] 📏 量測:撰寫 `tests/realrun/test_us1_aj_17.py`(`-m realrun`),照 US1-AJ-17 量測。假如:容器 `docker compose -p cgb-test` 已起,UI 8780、Ollama 相容端點 11436;已登入(照 P9 複製來的 token.json);真的 Colab、CLI、ssh、遠端 Ollama;沒有 `cgb-test-` 執行環境。當:Playwright 打開 `http://127.0.0.1:8780`,類型 T4,按「開啟」,每秒記錄一次 `#s-steps` 的目前步驟,直到「就緒」。記下的數字與門檻:則1:從按下到「就緒」在 5 分鐘內(SC-001);則2:就緒前記錄到的步驟依序包含配置、安裝並啟動 Ollama、建立 SSH 通道、確認模型服務有回應;則3:就緒時 `curl http://127.0.0.1:11436/api/version` 回 200;則4:`colab sessions` 列出 `[cgb-test-…]`、硬體 T4。副作用與護欄:P1~P9;開 1 台 T4(之後的 US2-AJ-02 到 US1-AJ-19 都用這一台,不在本案例結束);本案例約 3 分鐘、約 0.06 compute units;`.env` 只設 `CGB_HOST_DATA=<暫存目錄>/data`、`CGB_HOST_UI_PORT=8780`、`CGB_HOST_OLLAMA_PORT=11436`、`CGB_BIND_ADDR=127.0.0.1`(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(5 分鐘門檻);樣本:一次實跑(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US1-AJ-17
  - ⚙ `prototype/index.html` § `#open`、`#s-steps`、`[data-state="starting"]`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.get`;`deploy/compose.yaml` § `services.cgb`
  - 📎 `spec.md` § FR-001、NFR-001、SC-001;`plan.md` § 待決問題 Q101、Q108
- [ ] T117 [US1] 📏 量測:撰寫 `tests/realrun/test_us1_aj_18.py`(`-m realrun`),照 US1-AJ-18 量測。假如:US1-AJ-17 的工作階段就緒,`qwen2.5:0.5b` 已載入(US2-AJ-02 之後)。當:`docker exec` 在容器內以 SIGKILL 殺掉命令列含 `ProxyCommand=colab ssh --proxy-mode -s cgb-test-` 的 ssh 行程,每 5 秒讀一次 `GET /api/session`。記下的數字與門檻:則1:殺掉後 1 分鐘內 `state` 為 `reconnecting`(SC-002);則2:之後 5 分鐘內回到 `ready`,`name` 與殺掉前相同;則3:回到 `ready` 後經 11436 的 `/api/ps` 仍有 `qwen2.5:0.5b`;則4:`colab sessions` 的 `cgb-test-` 執行環境仍是 1 台。副作用與護欄:P1~P9;沿用同一台 T4,約 3 分鐘、約 0.06 compute units;只殺符合 `cgb-test-` 命令列的 ssh,不用 `pkill ssh`(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(1 分鐘與 5 分鐘門檻);樣本:一次實跑(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US1-AJ-18
  - ⚙ `prototype/index.html` § `[data-state="reconnecting"]`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./session.get`;`contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/reconnect.post`
  - 📎 `spec.md` § FR-004、NFR-002、SC-002;`plan.md` § 待決問題 Q101、Q108
- [ ] T118 [US1] 📏 量測:撰寫 `tests/realrun/test_us1_aj_19.py`(`-m realrun`),照 US1-AJ-19 量測。假如:US1-AJ-18 之後,工作階段就緒。當:`docker compose -p cgb-test restart cgb`,每 5 秒讀一次 `GET /api/session`。記下的數字與門檻:則1:重啟後 2 分鐘內 `state` 為 `ready`,`name` 與重啟前相同;則2:重啟前後 `colab sessions` 的 `cgb-test-` 執行環境都是 1 台、名稱相同。副作用與護欄:P1~P9;沿用同一台 T4,約 3 分鐘、約 0.06 compute units;只 restart `cgb-test` 這個 project(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本;樣本:一次實跑(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US1-AJ-19
  - ⚙ `prototype/index.html` § `[data-state="resuming"]`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./session.get`;`deploy/compose.yaml` § `services.cgb.restart`
  - 📎 `spec.md` § FR-005;`plan.md` § 待決問題 Q101、Q108
- [ ] T119 [US1] 📏 量測:撰寫 `tests/realrun/test_us1_aj_20.py`(`-m realrun`),照 US1-AJ-20 量測。重新下載要真的 `RemoteOllama.pull_model`、`list_loaded_models`、`preload`,依賴故事 3 的 T184b、T186b、T187b;假如:US1-AJ-19 之後,工作階段就緒(T4),`/api/ps` 只有 `qwen2.5:0.5b`(US3-AJ-12 以 `keep_alive:0` 推論,`qwen2.5:7b` 不留在記憶體)。當:在首頁勾「高 RAM」、按「變更類型」並確認,等到「就緒」與重新下載完成。記下的數字與門檻:則1:原本的名稱在 1 分鐘內從 `colab sessions` 消失;則2:新的名稱在 `colab sessions` 的形狀是 `High-RAM`、硬體 T4;則3:新的工作階段就緒後 5 分鐘內,經 11436 的 `/api/ps` 有 `qwen2.5:0.5b`;則4:`GET /api/sessions` 裡舊的那筆 `endReason` 為 `RUNTIME_TYPE_CHANGED`。副作用與護欄:P1~P9;結束 T4、開 1 台 T4 高 RAM(Q102 先採用,不用 L4);本案例約 5 分鐘、約 0.1 compute units;只重新下載 `qwen2.5:0.5b`;若 `/api/ps` 意外有 `qwen2.5:7b`,照實記錄並讓它一起重新下載,時間另計(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本;樣本:一次實跑(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US1-AJ-20
  - ⚙ `prototype/index.html` § `#switch`、`[data-state="confirm-switch"]`、`[data-state="switching"]`;`contracts/ui.openapi.yaml` § `paths./session/restart.post`、`paths./downloads.get`
  - 📎 `spec.md` § FR-010、SC-003;`plan.md` § 待決問題 Q101、Q102、Q108
- [ ] T120 [US1] 📏 量測:撰寫 `tests/realrun/test_us1_aj_21.py`(`-m realrun`),照 US1-AJ-21 量測。假如:US1-AJ-20 的 T4 高 RAM 工作階段就緒。當:在首頁按「結束工作階段」並確認,每 5 秒執行一次 `colab sessions`。記下的數字與門檻:則1:按下後 1 分鐘內 `colab sessions` 沒有這個名稱(SC-003);則2:首頁顯示「已結束」與「使用者結束」。副作用與護欄:P1~P9;結束 1 台,約 2 分鐘、約 0.04 compute units(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(1 分鐘門檻);樣本:一次實跑(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US1-AJ-21
  - ⚙ `prototype/index.html` § `#stop`、`[data-state="ended"]`;`contracts/ui.openapi.yaml` § `paths./session.delete`;`contracts/colab-cli.openapi.yaml` § `paths./sessions.get`
  - 📎 `spec.md` § FR-002、FR-007、SC-003;`plan.md` § 待決問題 Q101、Q108
- [ ] T121 [US1] 📏 量測:撰寫 `tests/realrun/test_us1_aj_22.py`(`-m realrun`),照 US1-AJ-22 量測。假如:沒有工作階段。當:開一台 T4 到就緒;另開終端機以 `HOME=<暫存目錄>/home colab stop -s <這個名稱>` 模擬被 Colab 收回(Q103 先採用),每 5 秒讀一次 `GET /api/session`。記下的數字與門檻:則1:`colab stop` 回來後 2 分鐘內 `state` 為 `lost`(SC-002);則2:`endReason` 為 `RECLAIMED_BY_COLAB`;則3:首頁顯示「失聯」與「重新開啟」。副作用與護欄:P1~P9;開 1 台 T4 後由終端機結束,約 5 分鐘、約 0.1 compute units;`colab stop` 只帶這次的 `cgb-test-` 名稱;容器內與終端機共用 `<暫存目錄>/data/colab-cli`(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(2 分鐘門檻);樣本:一次實跑(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US1-AJ-22
  - ⚙ `prototype/index.html` § `[data-state="lost"]`;`contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § FR-004、NFR-002、SC-002;`plan.md` § 待決問題 Q101、Q103、Q108

### 介面覆蓋(US1)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui.openapi.yaml` § `paths./session.post` | T015b、T016b、T017b、T018b、T019b、T020b、T024b、T025b、T026b、T027b、T028b、T029b、T030b、T048b、T053b、T054b、T099b、T101b、T102b、T105b、T108b | T015a、T016a、T017a、T018a、T019a、T020a、T024a、T025a、T026a、T027a、T028a、T029a、T030a、T048a、T053a、T054a、T099a、T101a、T102a、T105a、T108a |
| `ui.openapi.yaml` § `paths./session.get` | T015b、T016b、T037b、T038b、T039b、T040b、T051b、T053b、T054b、T099b、T112b、T113b | T015a、T016a、T037a、T038a、T039a、T040a、T051a、T053a、T054a、T099a、T112a、T113a |
| `store.dbml` § `Table sessions` | T015b、T096b、T097b | T015a、T096a、T097a |
| `ui.openapi.yaml` § `paths./auth.get` | T020b、T048b、T106b | T020a、T048a、T106a |
| `ui.openapi.yaml` § `paths./session.delete` | T021b、T022b、T023b、T027b、T052b、T100b、T114b | T021a、T022a、T023a、T027a、T052a、T100a、T114a |
| `tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get` | T031b、T032b、T051b、T083b | T031a、T032a、T051a、T083a |
| `tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/reconnect.post` | T032b、T033b、T034b、T035b、T036b | T032a、T033a、T034a、T035a、T036a |
| `ui-events.asyncapi.yaml` § `operations.sendSessionUpdated` | T032b、T052b、T099b、T100b、T102b、T103b、T104b | T032a、T052a、T099a、T100a、T102a、T103a、T104a |
| `ui.openapi.yaml` § `paths./session/restart.post` | T041b、T042b、T043b、T109b、T110b | T041a、T042a、T043a、T109a、T110a |
| `ui.openapi.yaml` § `paths./sessions.get` | T041b、T049b、T054b、T111b | T041a、T049a、T054a、T111a |
| `ui.openapi.yaml` § `paths./downloads.get` | T041b、T042b | T041a、T042a |
| `store.dbml` § `Table download_jobs` | T041b、T042b | T041a、T042a |
| `ui.openapi.yaml` § `paths./auth/authorizations.post` | T044b、T106b | T044a、T106a |
| `ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post` | T045b、T046b、T047b、T106b、T107b | T045a、T046a、T047a、T106a、T107a |
| `ui-events.asyncapi.yaml` § `operations.sendAuthUpdated` | T045b、T106b | T045a、T106a |
| `store.dbml` § `Table session_transitions` | T049b、T050b、T097b | T049a、T050a、T097a |
| `ui.openapi.yaml` § `paths./sessions/{name}.get` | T050b | T050a |
| `ui.openapi.yaml` § `paths./events.get` | T052b、T054b、T099b | T052a、T054a、T099a |
| `colab-cli.openapi.yaml` § `paths./version.get` | T056b、T057b | T056a、T057a |
| `colab-cli.openapi.yaml` § `paths./sessions.get` | T058b、T059b、T060b、T075b | T058a、T059a、T060a、T075a |
| `colab-cli.openapi.yaml` § `paths./new.post` | T061b、T062b、T063b、T064b | T061a、T062a、T063a、T064a |
| `colab-cli.openapi.yaml` § `paths./usage.get` | T065b、T074b | T065a、T074a |
| `colab-cli.openapi.yaml` § `paths./exec/start-ollama.post` | T066b、T067b、T069b | T066a、T067a、T069a |
| `colab-cli.openapi.yaml` § `paths./exec/probe-resources.post` | T068b | T068a |
| `colab-cli.openapi.yaml` § `paths./stop.post` | T070b、T071b、T072b、T073b | T070a、T071a、T072a、T073a |
| `tunnel.openapi.yaml` § `paths./key.post` | T078b | T078a |
| `tunnel.openapi.yaml` § `paths./tunnels.post` | T079b、T080b、T081b、T082b、T086b | T079a、T080a、T081a、T082a、T086a |
| `tunnel.openapi.yaml` § `paths./tunnels/{sessionName}.delete` | T084b、T085b | T084a、T085a |
| `google-oauth.openapi.yaml` § `paths./o/oauth2/auth.get` | T089b | T089a |
| `google-oauth.openapi.yaml` § `paths./token.post` | T090b、T091b、T092b、T093b | T090a、T091a、T092a、T093a |
| `index.html` § `[data-state="normal"]` | T099b | T099a |
| `index.html` § `[data-state="starting"]` | T099b、T102b | T099a、T102a |
| `index.html` § `[data-state="ready"]` | T099b、T100b、T103b、T108b、T109b、T112b | T099a、T100a、T103a、T108a、T109a、T112a |
| `index.html` § `[data-state="confirm-stop"]` | T100b | T100a |
| `index.html` § `[data-state="ended"]` | T100b、T114b | T100a、T114a |
| `index.html` § `[data-state="failed"]` | T101b、T110b | T101a、T110a |
| `index.html` § `[data-state="lost"]` | T102b | T102a |
| `index.html` § `[data-state="reconnecting"]` | T103b | T103a |
| `index.html` § `[data-state="lost-timeout"]`、`[data-state="release-failed"]` | T104b | T104a |
| `index.html` § `[data-state="already-open"]` | T105b | T105a |
| `index.html` § `[data-state="needs-login"]` | T106b | T106a |
| `login.html` § `[data-state="normal"]`、`[data-state="link"]`、`[data-state="signed-in"]` | T106b | T106a |
| `login.html` § `[data-state="failed"]`、`[data-state="link-expired"]` | T107b | T107a |
| `index.html` § `[data-state="confirm-switch"]`、`[data-state="switching"]` | T109b | T109a |
| `models.html` § `[data-state="normal"]` | T109b | T109a |
| `ui.openapi.yaml` § `paths./models.get` | T109b | T109a |
| `history.html` § `[data-state="normal"]` | T111b | T111a |
| `index.html` § `[data-state="resuming"]` | T112b | T112a |
| `index.html` § `[data-state="foreign"]` | T113b | T113a |
| `index.html` § `[data-state="stopping"]` | T114b | T114a |

### 測試案例覆蓋(US1)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務;📏 案例列它的量測任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US1-API-01~US1-API-40 | T015a~T054a | T015b~T054b | T055 |
| US1-CLI-01~US1-CLI-20 | T056a~T075a | T056b~T075b | T076 |
| US1-CLI-21 | — | — | T077(📏) |
| US1-TUN-01~US1-TUN-09 | T078a~T086a | T078b~T086b | T087 |
| US1-TUN-10 | — | — | T088(📏) |
| US1-OA-01~US1-OA-05 | T089a~T093a | T089b~T093b | T094 |
| US1-OA-06 | — | — | T095(📏) |
| US1-DB-01~US1-DB-02 | T096a~T097a | T096b~T097b | T098 |
| US1-AJ-01~US1-AJ-16 | T099a~T114a | T099b~T114b | T115 |
| US1-AJ-17 | — | — | T116(📏) |
| US1-AJ-18 | — | — | T117(📏) |
| US1-AJ-19 | — | — | T118(📏) |
| US1-AJ-20 | — | — | T119(📏) |
| US1-AJ-21 | — | — | T120(📏) |
| US1-AJ-22 | — | — | T121(📏) |

**Checkpoint**: `uv run pytest tests/integration tests/e2e` 全綠(不含 `-m realrun`);重構任務前後的測試結果相同;本故事的 📏 任務留給全部故事完成後依 P9 整批實跑

---

## Phase 3: User Story 2 - 透過固定的 Ollama 相容端點使用遠端模型 (Priority: P1)

**Goal**: 區網的程式把本系統的 Ollama 相容端點設定一次,就能列模型、產生文字、對話、embeddings 與查模型資訊,串流逐段傳回;沒有就緒的工作階段時 1 秒內收到明確的錯誤,管理操作一律請到 UI;遠端模型服務不經任何公開網址暴露

**Independent Test**: 照 `testplan.md` § 3 的全部案例:E3、E7、E6、E5 以 `uv run pytest tests/integration` 執行全綠(串流與 SSE 的案例用測試行程內的 uvicorn);跨端點驗收以 `uv run pytest tests/e2e/test_us2_endpoint.py`(httpx 對 127.0.0.1:11437)執行全綠;📏 案例照 P9 在使用者同意後整批實跑

### E3 Ollama 相容端點(FastAPI 轉送)

- [ ] T122a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-01 的測試(用 httpx 串流讀 `POST /api/generate {model:"qwen2.5:0.5b",prompt:"你好"}`),執行確認它因為「用 `r.aread()` 讀完整份再回,串流變成一次傳回」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-01
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § FR-011;`plan.md` § 待決問題 Q97
- [ ] T122b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/__init__.py`、`src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-OC-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;在 `src/cgb/ollama_compat/__init__.py` 把轉送路由掛進 `create_app` 的 Ollama 相容端點 app(取代 T099b 先掛的空 app)(依賴 T122a)
  - 🧪 `testplan.md` § US2-OC-01
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § FR-011;`plan.md` § 待決問題 Q97
- [ ] T123a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-02 的測試(送 `POST /api/generate?x=1 {model:"qwen2.5:0.5b",prompt:"你好",stream:false}`,帶 `Connection: keep-alive`),執行確認它因為「沒轉 query 或改寫本文」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-02
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § FR-011
- [ ] T123b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-OC-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T123a)
  - 🧪 `testplan.md` § US2-OC-02
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § FR-011
- [ ] T124a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-03 的測試(依序送 `GET /`、`HEAD /`、`GET /api/version`、`GET /api/tags`、`GET /api/ps`、`POST /api/show`、`POST /api/chat`、`POST /api/embed`、`POST /api/embeddings`(parametrize)),執行確認它因為「白名單漏了 `HEAD /`(有些用戶端用它檢查存活)或 `/api/embeddings`」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-03
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/tags.get`、`paths./.get`、`paths./.head`、`paths./api/version.get`、`paths./api/ps.get`、`paths./api/show.post`、`paths./api/generate.post`、`paths./api/chat.post`、`paths./api/embed.post`、`paths./api/embeddings.post`;`contracts/remote-ollama.openapi.yaml` § `paths./api/version.get`、`paths./api/tags.get`、`paths./api/ps.get`、`paths./api/show.post`、`paths./api/generate.post`、`paths./api/chat.post`、`paths./api/embed.post`、`paths./api/embeddings.post`
  - 📎 `spec.md` § FR-011
- [ ] T124b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-OC-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T124a)
  - 🧪 `testplan.md` § US2-OC-03
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/tags.get`、`paths./.get`、`paths./.head`、`paths./api/version.get`、`paths./api/ps.get`、`paths./api/show.post`、`paths./api/generate.post`、`paths./api/chat.post`、`paths./api/embed.post`、`paths./api/embeddings.post`;`contracts/remote-ollama.openapi.yaml` § `paths./api/version.get`、`paths./api/tags.get`、`paths./api/ps.get`、`paths./api/show.post`、`paths./api/generate.post`、`paths./api/chat.post`、`paths./api/embed.post`、`paths./api/embeddings.post`
  - 📎 `spec.md` § FR-011
- [ ] T125a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-04 的測試(依序送 `POST /api/pull`、`POST /api/push`、`POST /api/create`、`POST /api/copy`、`DELETE /api/delete`、`HEAD /api/blobs/sha256:00`、`POST /api/blobs/sha256:00`(parametrize)),執行確認它因為「只擋 R8 的五個路徑,`/api/blobs` 照轉」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-04
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/pull.post`、`paths./api/push.post`、`paths./api/create.post`、`paths./api/copy.post`、`paths./api/delete.delete`、`paths./api/blobs/{digest}.head`、`paths./api/blobs/{digest}.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-012
- [ ] T125b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-OC-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T125a)
  - 🧪 `testplan.md` § US2-OC-04
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/pull.post`、`paths./api/push.post`、`paths./api/create.post`、`paths./api/copy.post`、`paths./api/delete.delete`、`paths./api/blobs/{digest}.head`、`paths./api/blobs/{digest}.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-012
- [ ] T126a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-05 的測試(送 `POST /api/pull {model:"qwen2.5:0.5b"}`),執行確認它因為「先判斷有沒有工作階段才判斷路徑,管理操作在沒有工作階段時回「沒有可用的工作階段」」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-05
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/pull.post`、`paths./api/push.post`、`paths./api/create.post`、`paths./api/copy.post`、`paths./api/delete.delete`、`paths./api/blobs/{digest}.head`、`paths./api/blobs/{digest}.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-012、FR-013
- [ ] T126b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-OC-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T126a)
  - 🧪 `testplan.md` § US2-OC-05
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/pull.post`、`paths./api/push.post`、`paths./api/create.post`、`paths./api/copy.post`、`paths./api/delete.delete`、`paths./api/blobs/{digest}.head`、`paths./api/blobs/{digest}.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-012、FR-013
- [ ] T127a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-06 的測試(送 `POST /v1/chat/completions` 與 `GET /api/me`),執行確認它因為「用黑名單轉送,`/v1/*` 被轉到遠端(等於另外提供 OpenAI 相容 API)」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-06
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `components.schemas.Error`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-011
- [ ] T127b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-OC-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T127a)
  - 🧪 `testplan.md` § US2-OC-06
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `components.schemas.Error`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-011
- [ ] T128a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-07 的測試(送 `POST /api/generate {model:"qwen2.5:0.5b",prompt:"你好"}`),執行確認它因為「沒有工作階段時仍往轉發位址送,等連線逾時才回錯誤」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-07
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-013、SC-007
- [ ] T128b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US2-OC-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T128a)
  - 🧪 `testplan.md` § US2-OC-07
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-013、SC-007
- [ ] T129a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-08 的測試(各送一次 `POST /api/chat`),執行確認它因為「只把 `none` 當成沒有工作階段,重連中照樣轉送、排隊等通道回來」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-08
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/chat.post`
  - 📎 `spec.md` § FR-013
- [ ] T129b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US2-OC-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T129a)
  - 🧪 `testplan.md` § US2-OC-08
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/chat.post`
  - 📎 `spec.md` § FR-013
- [ ] T130a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-09 的測試(第一個就緒時送一次 `GET /api/version`;第二個就緒後用同一個用戶端物件再送一次),執行確認它因為「轉發目標在啟動時就固定成第一個工作階段的連線,新的工作階段要重啟才接得上」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-09
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/version.get`
  - 📎 `spec.md` § FR-011
- [ ] T130b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US2-OC-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T130a)
  - 🧪 `testplan.md` § US2-OC-09
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/version.get`
  - 📎 `spec.md` § FR-011
- [ ] T131a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-10 的測試(送 `POST /api/session/restart`,在 `step` 為 `ending_previous` 與 `allocating` 時各送一次 `POST /api/generate`),執行確認它因為「變更類型時把請求排隊等新的工作階段就緒」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`;`contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § 邊界情況、FR-013
- [ ] T131b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US2-OC-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T131a)
  - 🧪 `testplan.md` § US2-OC-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session/restart.post`;`contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § 邊界情況、FR-013
- [ ] T132a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-11 的測試(串流讀 `POST /api/generate`),執行確認它因為「串流中斷時靜默關閉,用戶端以為回應結束」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-11
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`;`contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`;`contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § 邊界情況、FR-004
- [ ] T132b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/services/health_monitor.py` 只寫讓 US2-OC-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T132a)
  - 🧪 `testplan.md` § US2-OC-11
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`;`contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`;`contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § 邊界情況、FR-004
- [ ] T133a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-12 的測試(串流讀 `POST /api/generate`,讀到第 1 行後送 `DELETE /api/session`),執行確認它因為「使用者結束造成的中斷被當成非預期斷線,觸發重連」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-12
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`;`contracts/ui.openapi.yaml` § `paths./session.delete`
  - 📎 `spec.md` § FR-013
- [ ] T133b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US2-OC-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T133a)
  - 🧪 `testplan.md` § US2-OC-12
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`;`contracts/ui.openapi.yaml` § `paths./session.delete`
  - 📎 `spec.md` § FR-013
- [ ] T134a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-13 的測試(送 `POST /api/generate`),執行確認它因為「連不到時回 500 與 Python 例外文字」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-13
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-011
- [ ] T134b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-OC-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T134a)
  - 🧪 `testplan.md` § US2-OC-13
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-011
- [ ] T135a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-14 的測試(帶 `Origin: http://192.168.0.50:3000` 送 `POST /api/chat`),執行確認它因為「轉送時丟掉或改寫 `Origin`」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-14
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/chat.post`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`
  - 📎 `spec.md` § FR-011
- [ ] T135b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US2-OC-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T135a)
  - 🧪 `testplan.md` § US2-OC-14
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/chat.post`;`contracts/remote-ollama.openapi.yaml` § `paths./api/chat.post`
  - 📎 `spec.md` § FR-011
- [ ] T136a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US2-OC-15 的測試(送 `GET /api/tags`,另送一次 `POST /api/generate` 讓假伺服器回 500),執行確認它因為「把遠端的轉址照樣傳回,讓用戶端知道並嘗試直連轉發位址」這類實作而失敗
  - 🧪 `testplan.md` § US2-OC-15
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/tags.get`、`components.schemas.OllamaError`
  - 📎 `spec.md` § NFR-003、NFR-010
- [ ] T136b [US2] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/ollama_compat/access_log.py` 只寫讓 US2-OC-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T136a)
  - 🧪 `testplan.md` § US2-OC-15
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/tags.get`、`components.schemas.OllamaError`
  - 📎 `spec.md` § NFR-003、NFR-010
- [ ] T137 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T122b~T136b 記下的重構清單(範圍限 `src/cgb/ollama_compat/`、`src/cgb/services/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T136b)
  - 🧪 `testplan.md` § US2-OC-01~US2-OC-15
  - 📎 `testplan.md` § 3.1

### E7 遠端 Ollama(Colab 執行環境上,Ollama API)

- [ ] T138a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US2-RO-01 的測試(各呼叫一次),執行確認它因為「不檢查 JSON 就回成功」這類實作而失敗
  - 🧪 `testplan.md` § US2-RO-01
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/version.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-011
- [ ] T138b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US2-RO-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T138a)
  - 🧪 `testplan.md` § US2-RO-01
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/version.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-011
- [ ] T139a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US2-RO-02 的測試(各呼叫一次),執行確認它因為「串流中斷當成正常結束」這類實作而失敗
  - 🧪 `testplan.md` § US2-RO-02
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/generate.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-011
- [ ] T139b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US2-RO-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T139a)
  - 🧪 `testplan.md` § US2-RO-02
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/generate.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-011
- [ ] T140 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T138b~T139b 記下的重構清單(範圍限 `src/cgb/adapters/remote_ollama.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T139b)
  - 🧪 `testplan.md` § US2-RO-01~US2-RO-02
  - 📎 `testplan.md` § 3.2
- [ ] T141 [US2] 📏 量測:撰寫 `tests/realrun/test_us2_ro_03.py`(`-m realrun`),照 US2-RO-03 量測。假如:主機階段,US1-CLI-21 開好並啟動 Ollama 的 `cgb-test-<時間>-adapter`,經 `Tunnel.open_tunnel` 建立本機轉發(真的遠端 Ollama 0.40.x)。當:依序呼叫 `get_version`、`list_local_models`、`pull_model qwen2.5:0.5b`、`pull_model qwen2.5:cgb-test-nonexistent`、`generate`(非串流與串流各一次,`num_predict` 8)、`list_loaded_models`、帶 `Origin: http://192.168.0.50:3000` 的 `chat`、`generate` 指名 `qwen2.5:7b`(還沒下載)。記下的數字與門檻:則1:`get_version` 回含 `version` 的 JSON;則2:`pull qwen2.5:0.5b` 的每一行都符合 `components.schemas.PullProgress`,最後一行 `status` 為 `success`;則3:`pull qwen2.5:cgb-test-nonexistent` 回 HTTP 200,串流裡的 error 含 `file does not exist`,轉接層回 `OLLAMA_NOT_FOUND`(Q3);則4:兩次 `generate` 都成功,串流的最後一行 `done` 為 true;則5:`list_loaded_models` 有 `qwen2.5:0.5b`;則6:帶 `Origin` 的 `chat` 回 200(`OLLAMA_ORIGINS=*` 生效,Q20);則7:指名 `qwen2.5:7b` 回 404,轉接層回 `OLLAMA_NOT_FOUND`,`list_local_models` 仍沒有 `qwen2.5:7b`;則8:假伺服器劇本裡每一種回應,和這次錄到的對應回應有相同的欄位名稱。副作用與護欄:P1~P9;與 US1-CLI-21 共用同一台 T4,本案例約 3 分鐘,占用算在 US1-CLI-21 的 0.21 compute units 之內;只下載 `qwen2.5:0.5b`;本機轉發只綁 127.0.0.1(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本;樣本:一次實跑(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US2-RO-03
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/version.get`、`paths./api/pull.post`、`paths./api/generate.post`、`paths./api/ps.get`、`components.schemas.Error`、`paths./api/tags.get`、`paths./api/chat.post`
  - 📎 `spec.md` § FR-011、FR-016、FR-017;`plan.md` § 待決問題 Q3、Q20、Q101、Q108

### E6 SSH 通道(OpenSSH 與 `colab ssh --proxy-mode`)

- [ ] T142a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_tunnel.py` 寫 US2-TUN-01 的測試(以 `localPort=11435` 呼叫),執行確認它因為「轉發綁 `0.0.0.0` 或加 `-g`,區網任何裝置都能繞過本系統直連遠端 Ollama」這類實作而失敗
  - 🧪 `testplan.md` § US2-TUN-01
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`
  - 📎 `spec.md` § NFR-003
- [ ] T142b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/tunnel.py` 只寫讓 US2-TUN-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T142a)
  - 🧪 `testplan.md` § US2-TUN-01
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels.post`
  - 📎 `spec.md` § NFR-003
- [ ] T143 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T142b~T142b 記下的重構清單(範圍限 `src/cgb/adapters/tunnel.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T142b)
  - 🧪 `testplan.md` § US2-TUN-01
  - 📎 `testplan.md` § 3.3

### E5 Colab CLI(google-colab-cli,外部程式)

- [ ] T144a [US2] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US2-CLI-01 的測試(呼叫;讀本系統提供的初始化腳本內容),執行確認它因為「為了方便除錯把 Ollama 綁 `0.0.0.0`,或在腳本裡開公開通道」這類實作而失敗
  - 🧪 `testplan.md` § US2-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-003
- [ ] T144b [US2] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py`、`src/cgb/adapters/scripts/start_ollama.py` 只寫讓 US2-CLI-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T144a)
  - 🧪 `testplan.md` § US2-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`、`components.schemas.Error`
  - 📎 `spec.md` § NFR-003
- [ ] T145 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T144b~T144b 記下的重構清單(範圍限 `src/cgb/adapters/colab_cli.py`、`src/cgb/adapters/scripts/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T144b)
  - 🧪 `testplan.md` § US2-CLI-01
  - 📎 `testplan.md` § 3.4

### E2 後端 UI API、E4 資料庫、E8、E9、E10、E11

本故事的請求只經 Ollama 相容端點,不涉及 UI API、資料庫、模型庫、登入與部署的案例(區網開放在全域測試區 G-01)(`testplan.md` § 3.5),這一節沒有任務。

### E1 前端 UI(瀏覽器,原生 HTML/CSS/JS)

本故事沒有畫面(`testplan.md` § 3.6),這一節沒有任務。

### 跨端點驗收(`tests/e2e/`、`tests/realrun/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(或區網程式)接測試行程內真的後端,轉接層用替身;📏 任務改接真的 Colab,照 P9 整批實跑

- [ ] T146a [US2] 🔴 /tdd 紅燈:在 `tests/e2e/test_us2_endpoint.py` 寫 US2-AJ-01 的測試(在首頁按「開啟」到就緒,用 httpx 對 `127.0.0.1:11437` 送 `POST /api/generate {stream:false}`;在首頁結束工作階段後再送一次),執行確認它因為「UI 開啟的工作階段和 Ollama 相容端點看到的不是同一份狀態(兩個 uvicorn 各自一份)」這類實作而失敗
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `prototype/index.html` § `#open`、`#stop`;`contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.delete`;`contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-011、FR-013
- [ ] T146b [US2] 🟢 /tdd 綠燈:在 `src/cgb/server.py`、`src/cgb/app.py` 只寫讓 US2-AJ-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;確認 `src/cgb/server.py` 的兩個 uvicorn 共用同一份工作階段狀態(依賴 T146a)
  - 🧪 `testplan.md` § US2-AJ-01
  - ⚙ `prototype/index.html` § `#open`、`#stop`;`contracts/ui.openapi.yaml` § `paths./session.post`、`paths./session.delete`;`contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`components.schemas.OllamaError`
  - 📎 `spec.md` § FR-011、FR-013
- [ ] T147 [US2] 🔵 /tdd 重構:在全部測試綠燈下整理 T146b~T146b 記下的重構清單(範圍限 `src/cgb/server.py`、`src/cgb/app.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T146b)
  - 🧪 `testplan.md` § US2-AJ-01
  - 📎 `testplan.md` § 3.7
- [ ] T148 [US2] 📏 量測:撰寫 `tests/realrun/test_us2_aj_02.py`(`-m realrun`),照 US2-AJ-02 量測。假如:容器階段,US1-AJ-17 的工作階段就緒;經 UI 預先載入 `qwen2.5:0.5b`。當:交替送 20 次非串流 `POST /api/generate {model:"qwen2.5:0.5b",prompt:"你好",stream:false,options:{num_predict:8,seed:1,temperature:0}}`:10 次到 `127.0.0.1:11436`,10 次在容器內(`docker exec`)直接打轉發 `127.0.0.1:11435`;再以 `OLLAMA_HOST=http://127.0.0.1:11436 ollama list` 與 `ollama run qwen2.5:0.5b 你好` 各一次。記下的數字與門檻:則1:經本系統的平均延遲減直連的平均延遲不超過 0.5 秒(SC-005);則2:`ollama list` 列出 `qwen2.5:0.5b`;則3:`ollama run` 印出非空的回應。副作用與護欄:P1~P9;沿用 US1-AJ-17 的 T4,約 3 分鐘、約 0.06 compute units;`ollama` 指令一律帶 `OLLAMA_HOST=http://127.0.0.1:11436`,不連 11434(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(0.5 秒門檻);樣本:20 次請求(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US2-AJ-02
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`paths./api/tags.get`
  - 📎 `spec.md` § FR-011、NFR-004、SC-005;`plan.md` § 待決問題 Q101、Q108
- [ ] T149 [US2] 📏 量測:撰寫 `tests/realrun/test_us2_aj_03.py`(`-m realrun`),照 US2-AJ-03 量測。假如:容器階段一開始,真的 uvicorn(不經 ASGI transport),沒有工作階段。當:連續送 10 次 `POST /api/generate` 到 `127.0.0.1:11436`,各記延遲。記下的數字與門檻:則1:10 次都回 503;則2:10 次中最長的延遲不超過 1 秒(SC-007);則3:`error` 含「沒有可用的工作階段」。副作用與護欄:P5、P6;不開執行環境,0 compute units,約 1 分鐘(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(1 秒門檻);樣本:10 次請求(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US2-AJ-03
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § FR-013、SC-007;`plan.md` § 待決問題 Q101、Q108
- [ ] T150 [US2] 📏 量測:撰寫 `tests/realrun/test_us2_aj_04.py`(`-m realrun`),照 US2-AJ-04 量測。另寫只讀的 `tests/realrun/scripts/listen_check.py`(只印 `ss -ltn`,不安裝、不寫入任何東西);假如:容器階段,US1-AJ-17 的工作階段就緒。當:以 `colab exec -s <名稱> -f tests/realrun/scripts/listen_check.py`(只讀的腳本,印出 `ss -ltn` 的結果)讀執行環境的監聽位址;`docker port cgb-test-cgb-1`;從桌機主機對 `127.0.0.1:11435` 送 `GET /api/version`。記下的數字與門檻:則1:執行環境上 11434 只聽 `127.0.0.1`;則2:`docker port` 只有 8780 與 11434(對應主機 11436),沒有 11435;則3:主機對 `127.0.0.1:11435` 連不上;則4:`GET /api/session` 與首頁 HTML 不含任何 `colab` 執行環境的網址。副作用與護欄:P1~P9;沿用 US1-AJ-17 的 T4,約 2 分鐘、約 0.04 compute units;遠端腳本只讀不寫,不安裝任何東西(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本;樣本:一次實跑(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US2-AJ-04
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/version.get`;`contracts/ui.openapi.yaml` § `paths./session.get`;`deploy/compose.yaml` § `services.cgb.ports`
  - 📎 `spec.md` § NFR-003;`plan.md` § 待決問題 Q101、Q108

### 介面覆蓋(US2)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ollama-compat.openapi.yaml` § `paths./api/generate.post` | T122b、T123b、T124b、T128b、T131b、T132b、T133b、T134b、T146b | T122a、T123a、T124a、T128a、T131a、T132a、T133a、T134a、T146a |
| `ollama-compat.openapi.yaml` § `paths./api/tags.get` | T124b、T136b | T124a、T136a |
| `ollama-compat.openapi.yaml` § `paths./.get`、`paths./.head`、`paths./api/ps.get`、`paths./api/show.post`、`paths./api/embed.post`、`paths./api/embeddings.post` | T124b | T124a |
| `ollama-compat.openapi.yaml` § `paths./api/version.get` | T124b、T130b | T124a、T130a |
| `ollama-compat.openapi.yaml` § `paths./api/chat.post` | T124b、T129b、T135b | T124a、T129a、T135a |
| `remote-ollama.openapi.yaml` § `paths./api/version.get` | T124b、T138b | T124a、T138a |
| `remote-ollama.openapi.yaml` § `paths./api/tags.get`、`paths./api/ps.get`、`paths./api/show.post`、`paths./api/embed.post`、`paths./api/embeddings.post` | T124b | T124a |
| `remote-ollama.openapi.yaml` § `paths./api/generate.post` | T124b、T139b | T124a、T139a |
| `remote-ollama.openapi.yaml` § `paths./api/chat.post` | T124b、T135b | T124a、T135a |
| `ollama-compat.openapi.yaml` § `paths./api/pull.post`、`paths./api/push.post`、`paths./api/create.post`、`paths./api/copy.post`、`paths./api/delete.delete`、`paths./api/blobs/{digest}.head`、`paths./api/blobs/{digest}.post` | T125b、T126b | T125a、T126a |
| `ui.openapi.yaml` § `paths./session/restart.post`(擴充:US2-OC-10) | T131b | T131a |
| `tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`(擴充:US2-OC-11) | T132b | T132a |
| `ui.openapi.yaml` § `paths./session.get`(擴充:US2-OC-11) | T132b | T132a |
| `ui.openapi.yaml` § `paths./session.delete`(擴充:US2-OC-12、US2-AJ-01) | T133b、T146b | T133a、T146a |
| `tunnel.openapi.yaml` § `paths./tunnels.post`(擴充:US2-TUN-01) | T142b | T142a |
| `colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`(擴充:US2-CLI-01) | T144b | T144a |
| `ui.openapi.yaml` § `paths./session.post`(擴充:US2-AJ-01) | T146b | T146a |

### 測試案例覆蓋(US2)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務;📏 案例列它的量測任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US2-OC-01~US2-OC-15 | T122a~T136a | T122b~T136b | T137 |
| US2-RO-01~US2-RO-02 | T138a~T139a | T138b~T139b | T140 |
| US2-RO-03 | — | — | T141(📏) |
| US2-TUN-01 | T142a | T142b | T143 |
| US2-CLI-01 | T144a | T144b | T145 |
| US2-AJ-01 | T146a | T146b | T147 |
| US2-AJ-02 | — | — | T148(📏) |
| US2-AJ-03 | — | — | T149(📏) |
| US2-AJ-04 | — | — | T150(📏) |

**Checkpoint**: `uv run pytest tests/integration tests/e2e` 全綠(不含 `-m realrun`);重構任務前後的測試結果相同;本故事的 📏 任務留給全部故事完成後依 P9 整批實跑

---

## Phase 4: User Story 3 - 挑選要下載的模型並使用執行環境上的模型目錄 (Priority: P2)

**Goal**: 使用者在 UI 看得到執行環境上已下載的模型並可預先載入,從精選清單、官方模型庫搜尋或直接輸入名稱挑模型,看過總大小、剩餘空間與預估時間後排進佇列在背景依序下載;區網的程式指名已下載的模型就載入後回應,沒下載的回「模型不存在」

**Independent Test**: 照 `testplan.md` § 4 的全部案例:E2、E3、E7、E8、E5、E4 以 `uv run pytest tests/integration` 執行全綠;跨端點驗收以 `uv run pytest tests/e2e/test_us3_*.py` 執行全綠;📏 案例照 P9 在使用者同意後整批實跑

### E2 後端 UI API(FastAPI REST 與 SSE)

- [ ] T151a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_models.py` 寫 US3-API-01 的測試(送 `GET /api/models`),執行確認它因為「只讀 tags 沒讀 ps,全部顯示未載入」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-014
- [ ] T151b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/models.py`、`src/cgb/services/catalog.py` 只寫讓 US3-API-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T151a)
  - 🧪 `testplan.md` § US3-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-014
- [ ] T152a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_models.py` 寫 US3-API-02 的測試(送 `GET /api/models`),執行確認它因為「重連中仍去連轉發位址,等逾時回 504」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-014
- [ ] T152b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/models.py`、`src/cgb/services/catalog.py` 只寫讓 US3-API-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T152a)
  - 🧪 `testplan.md` § US3-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-014
- [ ] T153a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_models.py` 寫 US3-API-03 的測試(送 `POST /api/models/preload {model:"qwen2.5:7b"}`,再放行),執行確認它因為「用一個真的 prompt 預熱(多花時間、產生輸出)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendModelsUpdated`
  - 📎 `spec.md` § FR-015
- [ ] T153b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/models.py`、`src/cgb/services/catalog.py` 只寫讓 US3-API-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T153a)
  - 🧪 `testplan.md` § US3-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendModelsUpdated`
  - 📎 `spec.md` § FR-015
- [ ] T154a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_models.py` 寫 US3-API-04 的測試(送 `POST /api/models/preload {model:"qwen2.5:7b"}`),執行確認它因為「目錄沒有的模型就順手下載」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-015、FR-016
- [ ] T154b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/models.py`、`src/cgb/services/catalog.py` 只寫讓 US3-API-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T154a)
  - 🧪 `testplan.md` § US3-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-015、FR-016
- [ ] T155a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_models.py` 寫 US3-API-05 的測試(送 `POST /api/models/preload {model:"qwen2.5:7b"}`),執行確認它因為「載入失敗時把整個目錄標成錯誤,或清掉其他模型的已載入狀態」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`、`paths./models.get`
  - 📎 `spec.md` § 邊界情況、FR-015
- [ ] T155b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/models.py`、`src/cgb/services/catalog.py` 只寫讓 US3-API-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T155a)
  - 🧪 `testplan.md` § US3-API-05
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`、`paths./models.get`
  - 📎 `spec.md` § 邊界情況、FR-015
- [ ] T156a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_models.py` 寫 US3-API-06 的測試(對 `qwen2.5:7b` 連送兩次預先載入),執行確認它因為「每按一次就送一次載入」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § FR-015
- [ ] T156b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/models.py`、`src/cgb/services/catalog.py` 只寫讓 US3-API-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T156a)
  - 🧪 `testplan.md` § US3-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models/preload.post`
  - 📎 `spec.md` § FR-015
- [ ] T157a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-07 的測試(送 `POST /api/downloads {models:["qwen2.5:7b"]}`,同時訂閱 SSE),執行確認它因為「每一行進度都推一則事件」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`paths./models.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadUpdated`;`contracts/store.dbml` § `Table download_jobs`
  - 📎 `spec.md` § FR-017、FR-018
- [ ] T157b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US3-API-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T157a)
  - 🧪 `testplan.md` § US3-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`paths./models.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadUpdated`;`contracts/store.dbml` § `Table download_jobs`
  - 📎 `spec.md` § FR-017、FR-018
- [ ] T158a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-08 的測試(送 `POST /api/downloads {models:["qwen2.5:cgb-test-nonexistent"]}`),執行確認它因為「不先查模型庫就排進佇列,等 pull 失敗才發現」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`paths./downloads.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017
- [ ] T158b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US3-API-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T158a)
  - 🧪 `testplan.md` § US3-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`paths./downloads.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017
- [ ] T159a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-09 的測試(各加入一個模型),執行確認它因為「pull 回 HTTP 200 就當成功」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`paths./models.get`
  - 📎 `spec.md` § FR-017
- [ ] T159b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US3-API-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T159a)
  - 🧪 `testplan.md` § US3-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`paths./models.get`
  - 📎 `spec.md` § FR-017
- [ ] T160a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-10 的測試(一次送 `POST /api/downloads {models:["qwen2.5:0.5b","qwen2.5:7b","qwen2.5:1.5b"]}`),執行確認它因為「三個 pull 同時送出,搶頻寬與磁碟,也無法逐一顯示狀態」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`;`contracts/store.dbml` § `Table download_jobs`
  - 📎 `spec.md` § FR-021
- [ ] T160b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US3-API-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T160a)
  - 🧪 `testplan.md` § US3-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`;`contracts/store.dbml` § `Table download_jobs`
  - 📎 `spec.md` § FR-021
- [ ] T161a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-11 的測試(送 `DELETE /api/downloads/<第 3 筆>`,再送 `DELETE /api/downloads/<第 1 筆>`),執行確認它因為「取消排隊中的項目時連正在下載的一起中斷」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/{id}.delete`、`components.schemas.Error`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-021
- [ ] T161b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US3-API-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T161a)
  - 🧪 `testplan.md` § US3-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/{id}.delete`、`components.schemas.Error`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-021
- [ ] T162a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-12 的測試(送 `POST /api/downloads/estimate {models:["qwen2.5:7b","qwen2.5:0.5b"]}`),執行確認它因為「大小把 `config.size` 也加進去,或用版本頁四捨五入的值」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.get`
  - 📎 `spec.md` § FR-022
- [ ] T162b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py`、`src/cgb/domain/estimate.py` 只寫讓 US3-API-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T162a)
  - 🧪 `testplan.md` § US3-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.get`
  - 📎 `spec.md` § FR-022
- [ ] T163a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-13 的測試(先試算再加入 `qwen2.5:0.5b`(397,821,319)),執行確認它因為「只比這次選的大小和剩餘空間,沒算佇列裡還沒下載的」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-022
- [ ] T163b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py`、`src/cgb/domain/estimate.py` 只寫讓 US3-API-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T163a)
  - 🧪 `testplan.md` § US3-API-13
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-022
- [ ] T164a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-14 的測試(送 `POST /api/downloads {models:["qwen2.5:0.5b"]}`),執行確認它因為「讀不到剩餘空間就當成夠用直接加入」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-022
- [ ] T164b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py`、`src/cgb/domain/estimate.py` 只寫讓 US3-API-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T164a)
  - 🧪 `testplan.md` § US3-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-022
- [ ] T165a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-15 的測試(送 `POST /api/downloads {models:["qwen2.5:0.5b"]}`),執行確認它因為「沒有工作階段時照樣加入,使用者以為在下載」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017
- [ ] T165b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US3-API-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T165a)
  - 🧪 `testplan.md` § US3-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017
- [ ] T166a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-16 的測試(分別送 `{models:["qwen2.5:0.5b","qwen2.5:1.5b"]}` 與 `{models:["qwen2.5:7b"]}`),執行確認它因為「一批裡有一個不合法時,其他照樣加入」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-021
- [ ] T166b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US3-API-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T166a)
  - 🧪 `testplan.md` § US3-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-021
- [ ] T167a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-17 的測試(送 `POST /api/downloads {models:["qwen3-coder:480b-cloud"]}`),執行確認它因為「雲端專用版本 manifest 沒有層、大小算成 0,照樣排進佇列」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-020
- [ ] T167b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US3-API-17 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T167a)
  - 🧪 `testplan.md` § US3-API-17
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-020
- [ ] T168a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-18 的測試(送 `DELETE /api/session`;之後開新的工作階段(新的假伺服器 tags 為空)),執行確認它因為「結束時把下載中的那筆標成完成或留在下載中」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.delete`、`paths./models.get`
  - 📎 `spec.md` § 邊界情況、FR-018
- [ ] T168b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US3-API-18 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T168a)
  - 🧪 `testplan.md` § US3-API-18
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.delete`、`paths./models.get`
  - 📎 `spec.md` § 邊界情況、FR-018
- [ ] T169a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-19 的測試(開新的工作階段到就緒),執行確認它因為「新的工作階段就緒後佇列沒有自動繼續」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./downloads.get`
  - 📎 `spec.md` § 邊界情況、FR-021
- [ ] T169b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/downloads.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US3-API-19 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T169a)
  - 🧪 `testplan.md` § US3-API-19
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.post`、`paths./downloads.get`
  - 📎 `spec.md` § 邊界情況、FR-021
- [ ] T170a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-20 的測試(送 `POST /api/downloads/<B>/retry`,再送 `POST /api/downloads/clear-completed`),執行確認它因為「重新排隊插回原位,插隊到 C 前面」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/{id}/retry.post`、`paths./downloads/clear-completed.post`
  - 📎 `spec.md` § FR-021
- [ ] T170b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US3-API-20 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T170a)
  - 🧪 `testplan.md` § US3-API-20
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads/{id}/retry.post`、`paths./downloads/clear-completed.post`
  - 📎 `spec.md` § FR-021
- [ ] T171a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US3-API-21 的測試(送 `GET /api/library/search?q=qwen2.5`),執行確認它因為「`downloadedTags` 沒對照執行環境」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`
  - 📎 `spec.md` § FR-020
- [ ] T171b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/library.py`、`src/cgb/services/library.py` 只寫讓 US3-API-21 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T171a)
  - 🧪 `testplan.md` § US3-API-21
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`
  - 📎 `spec.md` § FR-020
- [ ] T172a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US3-API-22 的測試(送 `GET /api/library/models/qwen2.5/tags`),執行確認它因為「雲端專用版本沒標出,UI 讓它被勾選」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`
  - 📎 `spec.md` § FR-020
- [ ] T172b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/library.py`、`src/cgb/services/library.py` 只寫讓 US3-API-22 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T172a)
  - 🧪 `testplan.md` § US3-API-22
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`
  - 📎 `spec.md` § FR-020
- [ ] T173a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_library.py` 寫 US3-API-23 的測試(送 `GET /api/library/search?q=qwen2.5` 與 `GET /api/curated`),執行確認它因為「模型庫壞掉時連精選清單也讀不到(spec 假設的退路不成立)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`paths./curated.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-020
- [ ] T173b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/library.py`、`src/cgb/services/library.py` 只寫讓 US3-API-23 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T173a)
  - 🧪 `testplan.md` § US3-API-23
  - ⚙ `contracts/ui.openapi.yaml` § `paths./library/search.get`、`paths./curated.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-020
- [ ] T174a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_curated.py` 寫 US3-API-24 的測試(依序新增 `qwen2.5:7b`(說明「日常用」)、新增 `qwen2.5`、再新增 `qwen2.5:latest`、修改第一筆說明為 201 個字元、刪除第二筆),執行確認它因為「沒把沒寫版本的名稱正規化成 `:latest`,同一個模型存成兩筆」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`paths./curated.get`、`components.schemas.Error`、`paths./curated/{id}.put`、`paths./curated/{id}.delete`;`contracts/store.dbml` § `Table curated_models`
  - 📎 `spec.md` § FR-020
- [ ] T174b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/curated.py`、`src/cgb/repos/curated.py` 只寫讓 US3-API-24 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T174a)
  - 🧪 `testplan.md` § US3-API-24
  - ⚙ `contracts/ui.openapi.yaml` § `paths./curated.post`、`paths./curated.get`、`components.schemas.Error`、`paths./curated/{id}.put`、`paths./curated/{id}.delete`;`contracts/store.dbml` § `Table curated_models`
  - 📎 `spec.md` § FR-020
- [ ] T175a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_recovery.py` 寫 US3-API-25 的測試(重建 app(`list_sessions` 仍列出這台)),執行確認它因為「重啟後永遠停在 `downloading`,佇列卡住」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`;`contracts/store.dbml` § `Table download_jobs`
  - 📎 `spec.md` § FR-021
- [ ] T175b [US3] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US3-API-25 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T175a)
  - 🧪 `testplan.md` § US3-API-25
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.get`;`contracts/store.dbml` § `Table download_jobs`
  - 📎 `spec.md` § FR-021
- [ ] T176a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_models.py` 寫 US3-API-26 的測試(送 `GET /api/models`;再讓 `probe_resources` 回 `vramTotalBytes: null` 後送一次),執行確認它因為「用剩餘顯示記憶體比較,已載入一個模型後全部標成可能無法載入(Q62)」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-26
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § NFR-006;`plan.md` § 待決問題 Q62
- [ ] T176b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/models.py`、`src/cgb/services/catalog.py` 只寫讓 US3-API-26 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T176a)
  - 🧪 `testplan.md` § US3-API-26
  - ⚙ `contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § NFR-006;`plan.md` § 待決問題 Q62
- [ ] T177a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_api_downloads.py` 寫 US3-API-27 的測試(加入下載後 0.5 秒,經 Ollama 相容端點送 5 次非串流 `generate`),執行確認它因為「下載與推論共用一把鎖或同一條 httpx 連線,推論要等下載結束」這類實作而失敗
  - 🧪 `testplan.md` § US3-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`;`contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § NFR-007
- [ ] T177b [US3] 🟢 /tdd 綠燈:在 `src/cgb/api/downloads.py`、`src/cgb/services/downloads.py`、`src/cgb/repos/downloads.py` 只寫讓 US3-API-27 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T177a)
  - 🧪 `testplan.md` § US3-API-27
  - ⚙ `contracts/ui.openapi.yaml` § `paths./downloads.post`;`contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § NFR-007
- [ ] T178 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T151b~T177b 記下的重構清單(範圍限 `src/cgb/api/`、`src/cgb/services/`、`src/cgb/domain/`、`src/cgb/repos/`、`src/cgb/db/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T177b)
  - 🧪 `testplan.md` § US3-API-01~US3-API-27
  - 📎 `testplan.md` § 4.1

### E3 Ollama 相容端點(FastAPI 轉送)

- [ ] T179a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US3-OC-01 的測試(送 `POST /api/generate {model:"qwen2.5:7b",prompt:"你好"}`),執行確認它因為「模型不存在時自動排下載」這類實作而失敗
  - 🧪 `testplan.md` § US3-OC-01
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`;`contracts/ui.openapi.yaml` § `paths./downloads.get`
  - 📎 `spec.md` § FR-016
- [ ] T179b [US3] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US3-OC-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T179a)
  - 🧪 `testplan.md` § US3-OC-01
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`;`contracts/ui.openapi.yaml` § `paths./downloads.get`
  - 📎 `spec.md` § FR-016
- [ ] T180a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US3-OC-02 的測試(送 `POST /api/chat {model:"qwen2.5:7b",stream:false}`),執行確認它因為「本系統自己先送預先載入再轉送,多一次往返」這類實作而失敗
  - 🧪 `testplan.md` § US3-OC-02
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/chat.post`
  - 📎 `spec.md` § FR-016
- [ ] T180b [US3] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US3-OC-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T180a)
  - 🧪 `testplan.md` § US3-OC-02
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/chat.post`
  - 📎 `spec.md` § FR-016
- [ ] T181a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US3-OC-03 的測試(送 `GET /api/tags`),執行確認它因為「把佇列裡下載中的名稱合併進清單,讓程式以為可用」這類實作而失敗
  - 🧪 `testplan.md` § US3-OC-03
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/tags.get`
  - 📎 `spec.md` § FR-016、FR-018
- [ ] T181b [US3] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US3-OC-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T181a)
  - 🧪 `testplan.md` § US3-OC-03
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/tags.get`
  - 📎 `spec.md` § FR-016、FR-018
- [ ] T182a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US3-OC-04 的測試(同時送兩個指名 `qwen2.5:7b` 的 `generate`),執行確認它因為「本系統為了「只載入一次」自己排隊或另送預先載入,第二個請求被擋或多一次載入」這類實作而失敗
  - 🧪 `testplan.md` § US3-OC-04
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § 邊界情況
- [ ] T182b [US3] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/routes.py`、`src/cgb/ollama_compat/forward.py` 只寫讓 US3-OC-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T182a)
  - 🧪 `testplan.md` § US3-OC-04
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § 邊界情況
- [ ] T183 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T179b~T182b 記下的重構清單(範圍限 `src/cgb/ollama_compat/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T182b)
  - 🧪 `testplan.md` § US3-OC-01~US3-OC-04
  - 📎 `testplan.md` § 4.2

### E7 遠端 Ollama(Colab 執行環境上,Ollama API)

- [ ] T184a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US3-RO-01 的測試(呼叫並收集進度),執行確認它因為「把沒有 `total` 的狀態行當成 0% 進度」這類實作而失敗
  - 🧪 `testplan.md` § US3-RO-01
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`
  - 📎 `spec.md` § FR-017
- [ ] T184b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US3-RO-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T184a)
  - 🧪 `testplan.md` § US3-RO-01
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`
  - 📎 `spec.md` § FR-017
- [ ] T185a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US3-RO-02 的測試(各呼叫一次),執行確認它因為「只看 HTTP 狀態碼,200 就當成功」這類實作而失敗
  - 🧪 `testplan.md` § US3-RO-02
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017
- [ ] T185b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US3-RO-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T185a)
  - 🧪 `testplan.md` § US3-RO-02
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/pull.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017
- [ ] T186a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US3-RO-03 的測試(呼叫 `list_local_models` 與 `list_loaded_models`),執行確認它因為「欄位名稱拼錯(`model` 與 `name` 混用)而解析成空清單」這類實作而失敗
  - 🧪 `testplan.md` § US3-RO-03
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`
  - 📎 `spec.md` § FR-014
- [ ] T186b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US3-RO-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T186a)
  - 🧪 `testplan.md` § US3-RO-03
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/tags.get`
  - 📎 `spec.md` § FR-014
- [ ] T187a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_remote_ollama.py` 寫 US3-RO-04 的測試(以 `qwen2.5:7b` 呼叫),執行確認它因為「預先載入帶了 `prompt`,或 `keep_alive` 不是 -1」這類實作而失敗
  - 🧪 `testplan.md` § US3-RO-04
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § FR-015
- [ ] T187b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/remote_ollama.py` 只寫讓 US3-RO-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T187a)
  - 🧪 `testplan.md` § US3-RO-04
  - ⚙ `contracts/remote-ollama.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § FR-015
- [ ] T188 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T184b~T187b 記下的重構清單(範圍限 `src/cgb/adapters/remote_ollama.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T187b)
  - 🧪 `testplan.md` § US3-RO-01~US3-RO-04
  - 📎 `testplan.md` § 4.3

### E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai)

- [ ] T189a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US3-LIB-01 的測試(以 `q=qwen2.5` 呼叫第 1 頁與第 2 頁),執行確認它因為「把社群模型也列出(Q9)」這類實作而失敗
  - 🧪 `testplan.md` § US3-LIB-01
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`
  - 📎 `spec.md` § FR-020;`plan.md` § 待決問題 Q9
- [ ] T189b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 只寫讓 US3-LIB-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T189a)
  - 🧪 `testplan.md` § US3-LIB-01
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`
  - 📎 `spec.md` § FR-020;`plan.md` § 待決問題 Q9
- [ ] T190a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US3-LIB-02 的測試(各呼叫一次第 1 頁),執行確認它因為「以「滿 20 筆」推斷有下一頁(Q54 已改)」這類實作而失敗
  - 🧪 `testplan.md` § US3-LIB-02
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`
  - 📎 `spec.md` § FR-020;`plan.md` § 待決問題 Q54
- [ ] T190b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 只寫讓 US3-LIB-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T190a)
  - 🧪 `testplan.md` § US3-LIB-02
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`
  - 📎 `spec.md` § FR-020;`plan.md` § 待決問題 Q54
- [ ] T191a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US3-LIB-03 的測試(以 `qwen2.5` 呼叫),執行確認它因為「名稱含 cloud 沒標出」這類實作而失敗
  - 🧪 `testplan.md` § US3-LIB-03
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`
  - 📎 `spec.md` § FR-020
- [ ] T191b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 只寫讓 US3-LIB-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T191a)
  - 🧪 `testplan.md` § US3-LIB-03
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`
  - 📎 `spec.md` § FR-020
- [ ] T192a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_model_library.py` 寫 US3-LIB-04 的測試(各呼叫一次),執行確認它因為「大小加進 config」這類實作而失敗
  - 🧪 `testplan.md` § US3-LIB-04
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-022
- [ ] T192b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py` 只寫讓 US3-LIB-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T192a)
  - 🧪 `testplan.md` § US3-LIB-04
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-022
- [ ] T193 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T189b~T192b 記下的重構清單(範圍限 `src/cgb/adapters/model_library.py`、`src/cgb/domain/library_html.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T192b)
  - 🧪 `testplan.md` § US3-LIB-01~US3-LIB-04
  - 📎 `testplan.md` § 4.4
- [ ] T194 [US3] 📏 量測:撰寫 `tests/realrun/test_us3_lib_05.py`(`-m realrun`),照 US3-LIB-05 量測。假如:主機階段,真的 ollama.com 與 registry.ollama.ai。當:呼叫 `search_library(q="qwen2.5")` 第 1、2 頁、`list_model_tags("qwen2.5")`、`get_manifest("qwen2.5","7b")`、`get_manifest("qwen2.5","cgb-test-nonexistent")`、版本頁上任一個名稱含 `cloud` 的版本的 `get_manifest`(沒有就記下沒有)。記下的數字與門檻:則1:第 1 頁含 `qwen2.5`,`hasMore` 為 true;則2:版本頁含 `0.5b` 與 `7b`,`7b` 的大小顯示值在 4.6GB 到 4.8GB 之間;則3:`qwen2.5:7b` 的大小在 4,600,000,000 到 4,800,000,000 位元組之間;則4:`cgb-test-nonexistent` 回 `LIBRARY_NOT_FOUND`;則5:雲端版本(若有)回 `LIBRARY_CLOUD_ONLY`;則6:`tests/fixtures/library/` 存的頁面與這次抓到的頁面,用同一組解析規則得到相同的欄位。副作用與護欄:P5、P8;不開執行環境,0 compute units,約 1 分鐘;只送 GET,總共不超過 10 個請求,請求間隔 1 秒(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本;樣本:2026 年 11 月的 ollama.com 一次(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US3-LIB-05
  - ⚙ `contracts/model-library.openapi.yaml` § `paths./search.get`、`paths./library/{name}/tags.get`、`paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-020、FR-022;`plan.md` § 待決問題 Q101、Q108

### E5 Colab CLI(google-colab-cli,外部程式)

- [ ] T195a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US3-CLI-01 的測試(呼叫),執行確認它因為「欄位對錯(把總容量當剩餘)」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/probe-resources.post`
  - 📎 `spec.md` § FR-022
- [ ] T195b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py`、`src/cgb/adapters/scripts/probe_resources.py` 只寫讓 US3-CLI-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T195a)
  - 🧪 `testplan.md` § US3-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/probe-resources.post`
  - 📎 `spec.md` § FR-022
- [ ] T196a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US3-CLI-02 的測試(各呼叫一次),執行確認它因為「沒有 GPU 資訊就當成失敗,連剩餘磁碟都拿不到」這類實作而失敗
  - 🧪 `testplan.md` § US3-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/probe-resources.post`
  - 📎 `spec.md` § FR-022、NFR-006
- [ ] T196b [US3] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py`、`src/cgb/adapters/scripts/probe_resources.py` 只寫讓 US3-CLI-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T196a)
  - 🧪 `testplan.md` § US3-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./exec/probe-resources.post`
  - 📎 `spec.md` § FR-022、NFR-006
- [ ] T197 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T195b~T196b 記下的重構清單(範圍限 `src/cgb/adapters/colab_cli.py`、`src/cgb/adapters/scripts/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T196b)
  - 🧪 `testplan.md` § US3-CLI-01~US3-CLI-02
  - 📎 `testplan.md` § 4.5

### E4 資料庫(SQLite)

- [ ] T198a [US3] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US3-DB-01 的測試(再插入 `pending_model='qwen2.5:7b'`;再插入 `queue_position=1` 的另一個模型;再插入兩筆 `pending_model` 為 null 的已完成項目;在 `curated_models` 插入兩筆 `name='qwen2.5:latest'`),執行確認它因為「`pending_model` 沒有 unique,同一個模型排兩次」這類實作而失敗
  - 🧪 `testplan.md` § US3-DB-01
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`
  - 📎 `spec.md` § FR-021、FR-020
- [ ] T198b [US3] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US3-DB-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;`download_jobs` 的 `queue_position` 與 `curated_models` 由 E2 節的 T160b、T174b 加上,本節依序接著改 `src/cgb/db/schema.py`,不另寫一份(依賴 T198a、T160b、T174b)
  - 🧪 `testplan.md` § US3-DB-01
  - ⚙ `contracts/store.dbml` § `Table download_jobs`、`Table curated_models`
  - 📎 `spec.md` § FR-021、FR-020
- [ ] T199 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T198b~T198b 記下的重構清單(範圍限 `src/cgb/db/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T198b)
  - 🧪 `testplan.md` § US3-DB-01
  - 📎 `testplan.md` § 4.6

### E1、E6、E9、E10、E11

本故事不涉及這些端點的案例(E1 的畫面行為都要後端,放在跨端點驗收)(`testplan.md` § 4.7),這一節沒有任務。

### 跨端點驗收(`tests/e2e/`、`tests/realrun/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(或區網程式)接測試行程內真的後端,轉接層用替身;📏 任務改接真的 Colab,照 P9 整批實跑

- [ ] T200a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_us3_models.py` 寫 US3-AJ-01 的測試(打開模型頁),執行確認它因為「大小顯示位元組原始值」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-01
  - ⚙ `prototype/models.html` § `#catalog`、`[data-state="normal"]`;`contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-014
- [ ] T200b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/models.html`、`src/cgb/static/js/models.js` 只寫讓 US3-AJ-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T200a)
  - 🧪 `testplan.md` § US3-AJ-01
  - ⚙ `prototype/models.html` § `#catalog`、`[data-state="normal"]`;`contracts/ui.openapi.yaml` § `paths./models.get`
  - 📎 `spec.md` § FR-014
- [ ] T201a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_us3_models.py` 寫 US3-AJ-02 的測試(按 `qwen2.5:7b` 的「預先載入」,再放行),執行確認它因為「按下後沒有任何回饋」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-02
  - ⚙ `prototype/models.html` § `#catalog`、`[data-state="preloading"]`;`contracts/ui.openapi.yaml` § `paths./models/preload.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendModelsUpdated`
  - 📎 `spec.md` § FR-015
- [ ] T201b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/models.html`、`src/cgb/static/js/models.js` 只寫讓 US3-AJ-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T201a)
  - 🧪 `testplan.md` § US3-AJ-02
  - ⚙ `prototype/models.html` § `#catalog`、`[data-state="preloading"]`;`contracts/ui.openapi.yaml` § `paths./models/preload.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendModelsUpdated`
  - 📎 `spec.md` § FR-015
- [ ] T202a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_us3_library.py` 寫 US3-AJ-03 的測試(在 `#name-form` 輸入 `qwen2.5:7b` 送出並確認;再打開模型頁),執行確認它因為「進度只在完成時更新一次」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-03
  - ⚙ `prototype/library.html` § `#name-form`、`#confirm-go`、`[data-state="confirm"]`;`prototype/models.html` § `#queue`、`#catalog`;`contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadUpdated`、`operations.sendModelsUpdated`
  - 📎 `spec.md` § FR-017
- [ ] T202b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js`、`src/cgb/static/js/models.js` 只寫讓 US3-AJ-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T202a)
  - 🧪 `testplan.md` § US3-AJ-03
  - ⚙ `prototype/library.html` § `#name-form`、`#confirm-go`、`[data-state="confirm"]`;`prototype/models.html` § `#queue`、`#catalog`;`contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadUpdated`、`operations.sendModelsUpdated`
  - 📎 `spec.md` § FR-017
- [ ] T203a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_us3_library.py` 寫 US3-AJ-04 的測試(輸入 `qwen2.5:cgb-test-nonexistent` 送出),執行確認它因為「錯誤只顯示代碼或沒有提示」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-04
  - ⚙ `prototype/library.html` § `#name-form`、`[data-state="not-found"]`;`contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017
- [ ] T203b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js` 只寫讓 US3-AJ-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T203a)
  - 🧪 `testplan.md` § US3-AJ-04
  - ⚙ `prototype/library.html` § `#name-form`、`[data-state="not-found"]`;`contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.Error`
  - 📎 `spec.md` § FR-017
- [ ] T204a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_us3_library.py` 寫 US3-AJ-05 的測試(打開下載模型頁,搜尋 `qwen2.5`,展開 `qwen2.5` 的版本,按「顯示更多」),執行確認它因為「精選清單排在搜尋結果下面」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-05
  - ⚙ `prototype/library.html` § `#search-form`、`#results`、`#more`、`#curated`、`[data-state="normal"]`、`[data-state="results"]`;`contracts/ui.openapi.yaml` § `paths./library/search.get`、`paths./library/models/{name}/tags.get`、`paths./curated.get`
  - 📎 `spec.md` § FR-020
- [ ] T204b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js` 只寫讓 US3-AJ-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T204a)
  - 🧪 `testplan.md` § US3-AJ-05
  - ⚙ `prototype/library.html` § `#search-form`、`#results`、`#more`、`#curated`、`[data-state="normal"]`、`[data-state="results"]`;`contracts/ui.openapi.yaml` § `paths./library/search.get`、`paths./library/models/{name}/tags.get`、`paths./curated.get`
  - 📎 `spec.md` § FR-020
- [ ] T205a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_us3_library.py` 寫 US3-AJ-06 的測試(按「加入下載」,看確認畫面,按「確認加入」),執行確認它因為「沒有確認畫面就直接加入」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-06
  - ⚙ `prototype/library.html` § `#add`、`#tray`、`#confirm-table`、`#confirm-disk`、`#confirm-eta`、`#confirm-go`、`[data-state="confirm"]`;`prototype/models.html` § `#queue`;`contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`
  - 📎 `spec.md` § FR-021、FR-022
- [ ] T205b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js`、`src/cgb/static/js/models.js` 只寫讓 US3-AJ-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T205a)
  - 🧪 `testplan.md` § US3-AJ-06
  - ⚙ `prototype/library.html` § `#add`、`#tray`、`#confirm-table`、`#confirm-disk`、`#confirm-eta`、`#confirm-go`、`[data-state="confirm"]`;`prototype/models.html` § `#queue`;`contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.post`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`
  - 📎 `spec.md` § FR-021、FR-022
- [ ] T206a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_us3_models.py` 寫 US3-AJ-07 的測試(按第 2 筆的「取消」),執行確認它因為「正在下載的也顯示取消按鈕,按了回 409 卻沒有說明」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-07
  - ⚙ `prototype/models.html` § `#queue`;`contracts/ui.openapi.yaml` § `paths./downloads/{id}.delete`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-021
- [ ] T206b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/models.html`、`src/cgb/static/js/models.js` 只寫讓 US3-AJ-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T206a)
  - 🧪 `testplan.md` § US3-AJ-07
  - ⚙ `prototype/models.html` § `#queue`;`contracts/ui.openapi.yaml` § `paths./downloads/{id}.delete`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadRemoved`
  - 📎 `spec.md` § FR-021
- [ ] T207a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_us3_library.py` 寫 US3-AJ-08 的測試(勾選 `qwen2.5:7b`,按「加入下載」),執行確認它因為「前端沒看 `fits`,讓使用者送出被伺服器拒絕後才知道」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-08
  - ⚙ `prototype/library.html` § `#add`、`#confirm-go`、`[data-state="no-space"]`;`contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`
  - 📎 `spec.md` § FR-022
- [ ] T207b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js` 只寫讓 US3-AJ-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T207a)
  - 🧪 `testplan.md` § US3-AJ-08
  - ⚙ `prototype/library.html` § `#add`、`#confirm-go`、`[data-state="no-space"]`;`contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`
  - 📎 `spec.md` § FR-022
- [ ] T208a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_us3_models.py` 寫 US3-AJ-09 的測試(在首頁結束工作階段,打開模型頁),執行確認它因為「結束後下載中的那筆仍顯示下載中或可用」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-09
  - ⚙ `prototype/index.html` § `#stop`;`prototype/models.html` § `#catalog`、`#queue`、`[data-state="no-session"]`;`contracts/ui.openapi.yaml` § `paths./session.delete`、`paths./downloads.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadUpdated`
  - 📎 `spec.md` § FR-018
- [ ] T208b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/models.html`、`src/cgb/static/js/models.js` 只寫讓 US3-AJ-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T208a)
  - 🧪 `testplan.md` § US3-AJ-09
  - ⚙ `prototype/index.html` § `#stop`;`prototype/models.html` § `#catalog`、`#queue`、`[data-state="no-session"]`;`contracts/ui.openapi.yaml` § `paths./session.delete`、`paths./downloads.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadUpdated`
  - 📎 `spec.md` § FR-018
- [ ] T209a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_us3_library.py` 寫 US3-AJ-10 的測試(展開 `qwen2.5` 的版本),執行確認它因為「雲端專用版本可以勾選,加入時才被 422 擋下」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-10
  - ⚙ `prototype/library.html` § `#results`;`contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`
  - 📎 `spec.md` § FR-020
- [ ] T209b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/library.html`、`src/cgb/static/js/library.js` 只寫讓 US3-AJ-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T209a)
  - 🧪 `testplan.md` § US3-AJ-10
  - ⚙ `prototype/library.html` § `#results`;`contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`
  - 📎 `spec.md` § FR-020
- [ ] T210a [US3] 🔴 /tdd 紅燈:在 `tests/e2e/test_us3_models.py` 寫 US3-AJ-11 的測試(打開模型頁,按 `cgb-test-big:70b` 的「預先載入」,在提示裡按取消;再按 `qwen2.5:7b` 的「預先載入」),執行確認它因為「只在目錄標示、預先載入前沒有提示」這類實作而失敗
  - 🧪 `testplan.md` § US3-AJ-11
  - ⚙ `prototype/models.html` § `#catalog`、`#pw-go`、`[data-state="preload-warn"]`;`contracts/ui.openapi.yaml` § `paths./models.get`、`paths./models/preload.post`
  - 📎 `spec.md` § NFR-006
- [ ] T210b [US3] 🟢 /tdd 綠燈:在 `src/cgb/static/models.html`、`src/cgb/static/js/models.js` 只寫讓 US3-AJ-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T210a)
  - 🧪 `testplan.md` § US3-AJ-11
  - ⚙ `prototype/models.html` § `#catalog`、`#pw-go`、`[data-state="preload-warn"]`;`contracts/ui.openapi.yaml` § `paths./models.get`、`paths./models/preload.post`
  - 📎 `spec.md` § NFR-006
- [ ] T211 [US3] 🔵 /tdd 重構:在全部測試綠燈下整理 T200b~T210b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T210b)
  - 🧪 `testplan.md` § US3-AJ-01~US3-AJ-11
  - 📎 `testplan.md` § 4.8
- [ ] T212 [US3] 📏 量測:撰寫 `tests/realrun/test_us3_aj_12.py`(`-m realrun`),照 US3-AJ-12 量測。假如:容器階段,US1-AJ-17 的 T4 工作階段就緒,執行環境上沒有 `qwen2.5:7b`;真的模型庫與遠端 Ollama。當:在下載模型頁輸入 `qwen2.5:7b` 下載並確認;下載中每 2 秒經 11436 讀一次 `/api/tags`;完成後立即經 11436 送一次非串流 `generate`(`num_predict` 8、`keep_alive` 0,推論完即卸載)。記下的數字與門檻:則1:從按「確認加入」到 `generate` 回 200 在 3 分鐘內(SC-004);則2:下載完成前每一次 `/api/tags` 都沒有 `qwen2.5:7b`(FR-018、Q2);則3:下載完成後的 `/api/tags` 有 `qwen2.5:7b`。副作用與護欄:P1~P9;沿用 US1-AJ-17 的 T4,約 4 分鐘、約 0.08 compute units;只下載 `qwen2.5:7b` 一次(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(3 分鐘門檻);樣本:一次實跑(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US3-AJ-12
  - ⚙ `prototype/library.html` § `#name-form`、`#confirm-go`;`contracts/ollama-compat.openapi.yaml` § `paths./api/tags.get`、`paths./api/generate.post`;`contracts/ui.openapi.yaml` § `paths./downloads.post`
  - 📎 `spec.md` § FR-017、FR-018、NFR-005、SC-004;`plan.md` § 待決問題 Q2、Q101、Q108
- [ ] T213 [US3] 📏 量測:撰寫 `tests/realrun/test_us3_aj_13.py`(`-m realrun`),照 US3-AJ-13 量測。假如:容器階段,US1-AJ-17 的 T4 工作階段就緒,`qwen2.5:0.5b` 已載入。當:先在沒有下載時經 11436 送 5 次非串流 `generate`(`qwen2.5:0.5b`,`num_predict` 16、`seed` 1、`temperature` 0);接著在 US3-AJ-12 的 `qwen2.5:7b` 下載期間再送 5 次。記下的數字與門檻:則1:下載期間 5 次的平均延遲減沒有下載時 5 次的平均延遲不超過 0.5 秒(SC-008);則2:下載期間的 5 次都在下載完成之前送完(若下載先完成,本次不算,記為未驗證)。副作用與護欄:P1~P9;與 US3-AJ-12 同一段時間,不另外增加占用;只用 `qwen2.5:0.5b` 推論(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(0.5 秒門檻);樣本:10 次請求(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US3-AJ-13
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`
  - 📎 `spec.md` § NFR-007、SC-008;`plan.md` § 待決問題 Q101、Q108

### 介面覆蓋(US3)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui.openapi.yaml` § `paths./models.get`(擴充:US3-API-01、US3-API-02、US3-API-05、US3-API-07、US3-API-09、US3-API-18、US3-API-26、US3-AJ-01、US3-AJ-11) | T151b、T152b、T155b、T157b、T159b、T168b、T176b、T200b、T210b | T151a、T152a、T155a、T157a、T159a、T168a、T176a、T200a、T210a |
| `ui.openapi.yaml` § `paths./models/preload.post` | T153b、T154b、T155b、T156b、T201b、T210b | T153a、T154a、T155a、T156a、T201a、T210a |
| `ui-events.asyncapi.yaml` § `operations.sendModelsUpdated` | T153b、T201b、T202b | T153a、T201a、T202a |
| `ui.openapi.yaml` § `paths./downloads.post` | T157b、T158b、T159b、T160b、T163b、T164b、T165b、T166b、T167b、T177b、T202b、T205b | T157a、T158a、T159a、T160a、T163a、T164a、T165a、T166a、T167a、T177a、T202a、T205a |
| `ui-events.asyncapi.yaml` § `operations.sendDownloadUpdated` | T157b、T202b、T205b、T208b | T157a、T202a、T205a、T208a |
| `store.dbml` § `Table download_jobs`(擴充:US3-API-07、US3-API-10、US3-API-25、US3-DB-01) | T157b、T160b、T175b、T198b | T157a、T160a、T175a、T198a |
| `ui.openapi.yaml` § `paths./downloads.get`(擴充:US3-API-08、US3-API-12、US3-API-19、US3-API-25、US3-OC-01、US3-AJ-09) | T158b、T162b、T169b、T175b、T179b、T208b | T158a、T162a、T169a、T175a、T179a、T208a |
| `ui.openapi.yaml` § `paths./downloads/{id}.delete` | T161b、T206b | T161a、T206a |
| `ui-events.asyncapi.yaml` § `operations.sendDownloadRemoved` | T161b、T206b | T161a、T206a |
| `ui.openapi.yaml` § `paths./downloads/estimate.post` | T162b、T202b、T203b、T205b、T207b | T162a、T202a、T203a、T205a、T207a |
| `ui.openapi.yaml` § `paths./session.delete`(擴充:US3-API-18、US3-AJ-09) | T168b、T208b | T168a、T208a |
| `ui.openapi.yaml` § `paths./session.post`(擴充:US3-API-19) | T169b | T169a |
| `ui.openapi.yaml` § `paths./downloads/{id}/retry.post`、`paths./downloads/clear-completed.post` | T170b | T170a |
| `ui.openapi.yaml` § `paths./library/search.get` | T171b、T173b、T204b | T171a、T173a、T204a |
| `ui.openapi.yaml` § `paths./library/models/{name}/tags.get` | T172b、T204b、T209b | T172a、T204a、T209a |
| `ui.openapi.yaml` § `paths./curated.get` | T173b、T174b、T204b | T173a、T174a、T204a |
| `ui.openapi.yaml` § `paths./curated.post`、`paths./curated/{id}.put`、`paths./curated/{id}.delete` | T174b | T174a |
| `store.dbml` § `Table curated_models` | T174b、T198b | T174a、T198a |
| `ollama-compat.openapi.yaml` § `paths./api/generate.post`(擴充:US3-API-27、US3-OC-01、US3-OC-04) | T177b、T179b、T182b | T177a、T179a、T182a |
| `ollama-compat.openapi.yaml` § `paths./api/chat.post`(擴充:US3-OC-02) | T180b | T180a |
| `ollama-compat.openapi.yaml` § `paths./api/tags.get`(擴充:US3-OC-03) | T181b | T181a |
| `remote-ollama.openapi.yaml` § `paths./api/pull.post` | T184b、T185b | T184a、T185a |
| `remote-ollama.openapi.yaml` § `paths./api/tags.get`(擴充:US3-RO-03) | T186b | T186a |
| `remote-ollama.openapi.yaml` § `paths./api/generate.post`(擴充:US3-RO-04) | T187b | T187a |
| `model-library.openapi.yaml` § `paths./search.get` | T189b、T190b | T189a、T190a |
| `model-library.openapi.yaml` § `paths./library/{name}/tags.get` | T191b | T191a |
| `model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get` | T192b | T192a |
| `colab-cli.openapi.yaml` § `paths./exec/probe-resources.post`(擴充:US3-CLI-01、US3-CLI-02) | T195b、T196b | T195a、T196a |
| `models.html` § `[data-state="normal"]`(擴充:US3-AJ-01) | T200b | T200a |
| `models.html` § `[data-state="preloading"]` | T201b | T201a |
| `library.html` § `[data-state="confirm"]` | T202b、T205b | T202a、T205a |
| `library.html` § `[data-state="not-found"]` | T203b | T203a |
| `library.html` § `[data-state="normal"]`、`[data-state="results"]` | T204b | T204a |
| `ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot` | T205b | T205a |
| `library.html` § `[data-state="no-space"]` | T207b | T207a |
| `models.html` § `[data-state="no-session"]` | T208b | T208a |
| `models.html` § `[data-state="preload-warn"]` | T210b | T210a |

### 測試案例覆蓋(US3)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務;📏 案例列它的量測任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US3-API-01~US3-API-27 | T151a~T177a | T151b~T177b | T178 |
| US3-OC-01~US3-OC-04 | T179a~T182a | T179b~T182b | T183 |
| US3-RO-01~US3-RO-04 | T184a~T187a | T184b~T187b | T188 |
| US3-LIB-01~US3-LIB-04 | T189a~T192a | T189b~T192b | T193 |
| US3-LIB-05 | — | — | T194(📏) |
| US3-CLI-01~US3-CLI-02 | T195a~T196a | T195b~T196b | T197 |
| US3-DB-01 | T198a | T198b | T199 |
| US3-AJ-01~US3-AJ-11 | T200a~T210a | T200b~T210b | T211 |
| US3-AJ-12 | — | — | T212(📏) |
| US3-AJ-13 | — | — | T213(📏) |

**Checkpoint**: `uv run pytest tests/integration tests/e2e` 全綠(不含 `-m realrun`);重構任務前後的測試結果相同;本故事的 📏 任務留給全部故事完成後依 P9 整批實跑

---

## Phase 5: User Story 4 - 掌握用量並避免忘了關 (Priority: P3)

**Goal**: 使用者在 UI 隨時看得到 compute units 的餘額、每小時耗用、估計可用時數與讀取時間,餘額低於門檻時收到警告但不被擋下;工作階段就緒卻在閒置時限內沒有任何經 Ollama 相容端點的請求時自動結束;閒置時限與警告門檻可以在 UI 設定並立即生效

**Independent Test**: 照 `testplan.md` § 5 的全部案例:E2、E3、E4、E5 以 `uv run pytest tests/integration` 執行全綠(閒置與讀用量以注入的時鐘推進);跨端點驗收以 `uv run pytest tests/e2e/test_us4_*.py` 執行全綠;📏 案例照 P9 在使用者同意後整批實跑

### E2 後端 UI API(FastAPI REST 與 SSE)

- [ ] T214a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_usage.py` 寫 US4-API-01 的測試(app 啟動後把時鐘推進 10 秒,送 `GET /api/usage`),執行確認它因為「估計時數用耗用 ÷ 餘額」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./usage.get`;`contracts/store.dbml` § `Table usage_snapshots`
  - 📎 `spec.md` § FR-024
- [ ] T214b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/usage.py`、`src/cgb/services/usage.py`、`src/cgb/repos/usage.py`、`src/cgb/domain/usage_calc.py` 只寫讓 US4-API-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;`usage_snapshots` 表(只留最後一筆,Q76)在 `src/cgb/db/schema.py` 建立(E4 節的 US4-DB-02 依賴它)(依賴 T214a)
  - 🧪 `testplan.md` § US4-API-01
  - ⚙ `contracts/ui.openapi.yaml` § `paths./usage.get`;`contracts/store.dbml` § `Table usage_snapshots`
  - 📎 `spec.md` § FR-024
- [ ] T215a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_usage.py` 寫 US4-API-02 的測試(各送一次 `GET /api/usage`),執行確認它因為「耗用為 0 時除以零丟出例外,`/api/usage` 回 500」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./usage.get`
  - 📎 `spec.md` § FR-024;`plan.md` § 待決問題 Q120
- [ ] T215b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/usage.py`、`src/cgb/services/usage.py`、`src/cgb/repos/usage.py`、`src/cgb/domain/usage_calc.py` 只寫讓 US4-API-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T215a)
  - 🧪 `testplan.md` § US4-API-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./usage.get`
  - 📎 `spec.md` § FR-024;`plan.md` § 待決問題 Q120
- [ ] T216a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_usage.py` 寫 US4-API-03 的測試(送 `GET /api/usage`;再送 `POST /api/session` 開到就緒;再送 `DELETE /api/session`),執行確認它因為「讀不到用量就擋下開啟或結束」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./usage.get`、`paths./session.post`、`paths./session.delete`
  - 📎 `spec.md` § FR-024
- [ ] T216b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/usage.py`、`src/cgb/services/usage.py`、`src/cgb/repos/usage.py`、`src/cgb/domain/usage_calc.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US4-API-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T216a)
  - 🧪 `testplan.md` § US4-API-03
  - ⚙ `contracts/ui.openapi.yaml` § `paths./usage.get`、`paths./session.post`、`paths./session.delete`
  - 📎 `spec.md` § FR-024
- [ ] T217a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_usage.py` 寫 US4-API-04 的測試(各送 `GET /api/usage`;情況 A 再送 `POST /api/session`),執行確認它因為「低餘額時擋下開啟(FR-025 只警告)」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./usage.get`、`paths./session.post`
  - 📎 `spec.md` § FR-025;`plan.md` § 待決問題 Q121
- [ ] T217b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/usage.py`、`src/cgb/services/usage.py`、`src/cgb/repos/usage.py`、`src/cgb/domain/usage_calc.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US4-API-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T217a)
  - 🧪 `testplan.md` § US4-API-04
  - ⚙ `contracts/ui.openapi.yaml` § `paths./usage.get`、`paths./session.post`
  - 📎 `spec.md` § FR-025;`plan.md` § 待決問題 Q121
- [ ] T218a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_usage.py` 寫 US4-API-05 的測試(時鐘推進 5 分鐘,讓下一次讀用量發生),執行確認它因為「餘額過低時自動結束工作階段」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-05
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendUsageUpdated`;`contracts/ui.openapi.yaml` § `paths./usage.get`
  - 📎 `spec.md` § FR-025
- [ ] T218b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/usage.py`、`src/cgb/services/usage.py`、`src/cgb/repos/usage.py`、`src/cgb/domain/usage_calc.py` 只寫讓 US4-API-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T218a)
  - 🧪 `testplan.md` § US4-API-05
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendUsageUpdated`;`contracts/ui.openapi.yaml` § `paths./usage.get`
  - 📎 `spec.md` § FR-025
- [ ] T219a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_settings.py` 寫 US4-API-06 的測試(啟動 app,送 `GET /api/settings`),執行確認它因為「預設值寫錯或沒有在第一次啟動時寫入,回 404 或 null」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.get`;`contracts/store.dbml` § `Table settings`
  - 📎 `spec.md` § FR-027
- [ ] T219b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/settings.py`、`src/cgb/services/settings.py`、`src/cgb/repos/settings.py` 只寫讓 US4-API-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;`settings` 表與預設值在 `src/cgb/db/schema.py` 建立(E4 節的 US4-DB-01 依賴它)(依賴 T219a)
  - 🧪 `testplan.md` § US4-API-06
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.get`;`contracts/store.dbml` § `Table settings`
  - 📎 `spec.md` § FR-027
- [ ] T220a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_settings.py` 寫 US4-API-07 的測試(送 `PUT /api/settings {idleTimeoutMinutes:10,lowBalanceThreshold:5}`,再送 `GET /api/settings`,再重建 app 後送一次 `GET /api/settings`),執行確認它因為「只改記憶體沒寫進資料庫,重啟後回到預設」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.put`、`paths./settings.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSettingsUpdated`;`contracts/store.dbml` § `Table settings`
  - 📎 `spec.md` § FR-027
- [ ] T220b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/settings.py`、`src/cgb/services/settings.py`、`src/cgb/repos/settings.py` 只寫讓 US4-API-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T220a)
  - 🧪 `testplan.md` § US4-API-07
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.put`、`paths./settings.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSettingsUpdated`;`contracts/store.dbml` § `Table settings`
  - 📎 `spec.md` § FR-027
- [ ] T221a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_settings.py` 寫 US4-API-08 的測試(分別送 `idleTimeoutMinutes` 為 0、1441、10.5,以及 `lowBalanceThreshold` 為 -1、10001 的 `PUT`(另一個欄位用合法值)),執行確認它因為「範圍檢查漏了邊界(1441 或 0 被接受)」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.put`、`paths./settings.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-027
- [ ] T221b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/settings.py`、`src/cgb/services/settings.py`、`src/cgb/repos/settings.py` 只寫讓 US4-API-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T221a)
  - 🧪 `testplan.md` § US4-API-08
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.put`、`paths./settings.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-027
- [ ] T222a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_settings.py` 寫 US4-API-09 的測試(時鐘在 T+3 分鐘時送 `PUT /api/settings {idleTimeoutMinutes:10,lowBalanceThreshold:10}`),執行確認它因為「新時限要等下一個工作階段才生效」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.put`、`paths./session.get`、`components.schemas.IdleCountdown`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-027、FR-026
- [ ] T222b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/settings.py`、`src/cgb/services/idle_monitor.py`、`src/cgb/domain/idle.py` 只寫讓 US4-API-09 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;閒置倒數的計算建在 `src/cgb/services/idle_monitor.py`(E3 節的 US4-OC 依賴它)(依賴 T222a)
  - 🧪 `testplan.md` § US4-API-09
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.put`、`paths./session.get`、`components.schemas.IdleCountdown`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-027、FR-026
- [ ] T223a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_settings.py` 寫 US4-API-10 的測試(送 `PUT /api/settings {idleTimeoutMinutes:10,lowBalanceThreshold:10}`),執行確認它因為「新時限已經到了卻等到下一次檢查(或從現在起算 10 分鐘)才結束」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.put`、`paths./session.get`
  - 📎 `spec.md` § FR-027、FR-026
- [ ] T223b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/settings.py`、`src/cgb/services/idle_monitor.py`、`src/cgb/domain/idle.py` 只寫讓 US4-API-10 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T223a)
  - 🧪 `testplan.md` § US4-API-10
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.put`、`paths./session.get`
  - 📎 `spec.md` § FR-027、FR-026
- [ ] T224a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_settings.py` 寫 US4-API-11 的測試(送 `PUT /api/settings {idleTimeoutMinutes:30,lowBalanceThreshold:20}`,不再讀用量,送 `GET /api/usage`),執行確認它因為「門檻變更要等下一次讀用量才反映在警告上」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.put`、`paths./usage.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendUsageUpdated`
  - 📎 `spec.md` § FR-027、FR-025
- [ ] T224b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/settings.py`、`src/cgb/services/usage.py`、`src/cgb/domain/usage_calc.py` 只寫讓 US4-API-11 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T224a)
  - 🧪 `testplan.md` § US4-API-11
  - ⚙ `contracts/ui.openapi.yaml` § `paths./settings.put`、`paths./usage.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendUsageUpdated`
  - 📎 `spec.md` § FR-027、FR-025
- [ ] T225a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_idle.py` 寫 US4-API-12 的測試(注入的時鐘推進到 `idle.deadline` 再加 1 分鐘(SC-006 的上限)),執行確認它因為「閒置計時沒有在背景檢查,要等下一個請求才發現逾時」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.IdleCountdown`、`paths./sessions.get`、`paths./session.get`
  - 📎 `spec.md` § FR-026、FR-028、SC-006
- [ ] T225b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/idle_monitor.py`、`src/cgb/domain/idle.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US4-API-12 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T225a)
  - 🧪 `testplan.md` § US4-API-12
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.IdleCountdown`、`paths./sessions.get`、`paths./session.get`
  - 📎 `spec.md` § FR-026、FR-028、SC-006
- [ ] T226a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_idle.py` 寫 US4-API-13 的測試(時鐘在 T+50 秒時經 Ollama 相容端點送 `GET /api/tags`,再推進到 T+80 秒),執行確認它因為「請求沒有重設閒置計時,工作階段在 T+60 秒被結束」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-13
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/tags.get`;`contracts/ui.openapi.yaml` § `components.schemas.IdleCountdown`、`paths./session.get`
  - 📎 `spec.md` § FR-026
- [ ] T226b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/idle_monitor.py`、`src/cgb/ollama_compat/idle_hook.py` 只寫讓 US4-API-13 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;經 Ollama 相容端點的請求重設閒置計時的掛點建在 `src/cgb/ollama_compat/idle_hook.py`(E3 節的 US4-OC 依賴它)(依賴 T226a)
  - 🧪 `testplan.md` § US4-API-13
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/tags.get`;`contracts/ui.openapi.yaml` § `components.schemas.IdleCountdown`、`paths./session.get`
  - 📎 `spec.md` § FR-026
- [ ] T227a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_idle.py` 寫 US4-API-14 的測試(時鐘在 T+50 秒時送 `GET /api/session`、`GET /api/models`、`GET /api/usage`(都是 UI API),再推進到 T+70 秒),執行確認它因為「UI 的輪詢與 SSE 也重設閒置計時,開著 UI 的頁面就永遠不會自動結束(Q24)」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.IdleCountdown`、`paths./models.get`、`paths./usage.get`
  - 📎 `spec.md` § FR-026;`plan.md` § 待決問題 Q24
- [ ] T227b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/idle_monitor.py`、`src/cgb/domain/idle.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US4-API-14 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T227a)
  - 🧪 `testplan.md` § US4-API-14
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.IdleCountdown`、`paths./models.get`、`paths./usage.get`
  - 📎 `spec.md` § FR-026;`plan.md` § 待決問題 Q24
- [ ] T228a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_idle.py` 寫 US4-API-15 的測試(時鐘在 T+6 分鐘時重建 app(`list_sessions` 仍列出這台)),執行確認它因為「重啟後閒置倒數從重啟的時間重算(`last_request_at` 沒存或沒讀回,Q75)」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.IdleCountdown`
  - 📎 `spec.md` § FR-026;`plan.md` § 待決問題 Q75
- [ ] T228b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/recovery.py`、`src/cgb/services/idle_monitor.py`、`src/cgb/repos/sessions.py` 只寫讓 US4-API-15 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T228a)
  - 🧪 `testplan.md` § US4-API-15
  - ⚙ `contracts/ui.openapi.yaml` § `paths./session.get`、`components.schemas.IdleCountdown`
  - 📎 `spec.md` § FR-026;`plan.md` § 待決問題 Q75
- [ ] T229a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_idle.py` 寫 US4-API-16 的測試(時鐘推進到 `deadline` 之後),執行確認它因為「閒置自動結束時釋放失敗沒有警告,使用者以為已經關了」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.IdleCountdown`、`paths./session.get`
  - 📎 `spec.md` § FR-026、FR-007
- [ ] T229b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/idle_monitor.py`、`src/cgb/domain/idle.py`、`src/cgb/services/session_lifecycle.py` 只寫讓 US4-API-16 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T229a)
  - 🧪 `testplan.md` § US4-API-16
  - ⚙ `contracts/ui.openapi.yaml` § `components.schemas.IdleCountdown`、`paths./session.get`
  - 📎 `spec.md` § FR-026、FR-007
- [ ] T230a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_health.py` 寫 US4-API-17 的測試(`check_health` 開始失敗,`list_sessions` 仍列出這台(重連中)),執行確認它因為「不看最後讀到的餘額,永遠不提示可能已經歸零」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-17
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`;`contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § 邊界情況、FR-024
- [ ] T230b [US4] 🟢 /tdd 綠燈:在 `src/cgb/services/health_monitor.py`、`src/cgb/services/usage.py` 只寫讓 US4-API-17 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T230a)
  - 🧪 `testplan.md` § US4-API-17
  - ⚙ `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`;`contracts/ui.openapi.yaml` § `paths./session.get`
  - 📎 `spec.md` § 邊界情況、FR-024
- [ ] T231a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_api_usage.py` 寫 US4-API-18 的測試(時鐘從 T 推進到 T+20 分鐘,記下每次 `get_usage` 被呼叫的時間;在 T+14 分 59 秒與 T+15 分 01 秒各送一次 `GET /api/usage`),執行確認它因為「只在 UI 打開時才讀用量」這類實作而失敗
  - 🧪 `testplan.md` § US4-API-18
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`;`contracts/ui.openapi.yaml` § `paths./usage.get`;`contracts/ui.openapi.yaml` § `components.schemas.Usage`;`contracts/store.dbml` § `Table usage_snapshots`
  - 📎 `spec.md` § NFR-008;`plan.md` § 待決問題 Q119、Q123
- [ ] T231b [US4] 🟢 /tdd 綠燈:在 `src/cgb/api/usage.py`、`src/cgb/services/usage.py`、`src/cgb/repos/usage.py`、`src/cgb/domain/usage_calc.py` 只寫讓 US4-API-18 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T231a)
  - 🧪 `testplan.md` § US4-API-18
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`;`contracts/ui.openapi.yaml` § `paths./usage.get`;`contracts/ui.openapi.yaml` § `components.schemas.Usage`;`contracts/store.dbml` § `Table usage_snapshots`
  - 📎 `spec.md` § NFR-008;`plan.md` § 待決問題 Q119、Q123
- [ ] T232 [US4] 🔵 /tdd 重構:在全部測試綠燈下整理 T214b~T231b 記下的重構清單(範圍限 `src/cgb/api/`、`src/cgb/services/`、`src/cgb/domain/`、`src/cgb/repos/`、`src/cgb/db/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T231b)
  - 🧪 `testplan.md` § US4-API-01~US4-API-18
  - 📎 `testplan.md` § 5.1

### E3 Ollama 相容端點(FastAPI 轉送)

- [ ] T233a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US4-OC-01 的測試(時鐘在 T+20 秒送 `POST /api/pull`(被擋下),在 T+40 秒送 `GET /v1/models`(白名單外)),執行確認它因為「只有轉送出去的請求才重設計時,被擋下的請求不算(與 FR-026「任何經 Ollama 相容端點的請求」不符,Q52)」這類實作而失敗
  - 🧪 `testplan.md` § US4-OC-01
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/pull.post`、`paths./api/push.post`、`paths./api/create.post`、`paths./api/copy.post`、`paths./api/delete.delete`、`paths./api/blobs/{digest}.head`、`paths./api/blobs/{digest}.post`、`components.schemas.Error`;`contracts/ui.openapi.yaml` § `components.schemas.IdleCountdown`
  - 📎 `spec.md` § FR-026;`plan.md` § 待決問題 Q52
- [ ] T233b [US4] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/idle_hook.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/services/idle_monitor.py` 只寫讓 US4-OC-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;`src/cgb/services/idle_monitor.py` 與 `src/cgb/ollama_compat/idle_hook.py` 由 E2 節的 T222b、T226b 建立,本節依序接著改,不另寫一份(依賴 T233a、T222b、T226b)
  - 🧪 `testplan.md` § US4-OC-01
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/pull.post`、`paths./api/push.post`、`paths./api/create.post`、`paths./api/copy.post`、`paths./api/delete.delete`、`paths./api/blobs/{digest}.head`、`paths./api/blobs/{digest}.post`、`components.schemas.Error`;`contracts/ui.openapi.yaml` § `components.schemas.IdleCountdown`
  - 📎 `spec.md` § FR-026;`plan.md` § 待決問題 Q52
- [ ] T234a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_ollama_compat.py` 寫 US4-OC-02 的測試(時鐘在 T 開始串流讀 `POST /api/generate`,串流進行中推進到 T+90 秒,再讀完最後一行(T+100 秒)),執行確認它因為「只在請求開始時重設,長串流跑超過閒置時限就被自動結束,回應被切斷」這類實作而失敗
  - 🧪 `testplan.md` § US4-OC-02
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`;`contracts/ui.openapi.yaml` § `components.schemas.IdleCountdown`
  - 📎 `spec.md` § FR-026
- [ ] T234b [US4] 🟢 /tdd 綠燈:在 `src/cgb/ollama_compat/idle_hook.py`、`src/cgb/ollama_compat/forward.py`、`src/cgb/services/idle_monitor.py` 只寫讓 US4-OC-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;`src/cgb/services/idle_monitor.py` 與 `src/cgb/ollama_compat/idle_hook.py` 由 E2 節的 T222b、T226b 建立,本節依序接著改,不另寫一份(依賴 T234a、T222b、T226b)
  - 🧪 `testplan.md` § US4-OC-02
  - ⚙ `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`;`contracts/ui.openapi.yaml` § `components.schemas.IdleCountdown`
  - 📎 `spec.md` § FR-026
- [ ] T235 [US4] 🔵 /tdd 重構:在全部測試綠燈下整理 T233b~T234b 記下的重構清單(範圍限 `src/cgb/ollama_compat/`、`src/cgb/services/idle_monitor.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T234b)
  - 🧪 `testplan.md` § US4-OC-01~US4-OC-02
  - 📎 `testplan.md` § 5.2

### E4 資料庫(SQLite)

- [ ] T236a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US4-DB-01 的測試(讀 `settings`;把 `idle_timeout_minutes` 改成 10;再呼叫一次建立 schema(第二次啟動);再讀),執行確認它因為「每次啟動都以預設值覆寫使用者改過的設定」這類實作而失敗
  - 🧪 `testplan.md` § US4-DB-01
  - ⚙ `contracts/store.dbml` § `Table settings`
  - 📎 `spec.md` § FR-027
- [ ] T236b [US4] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US4-DB-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;`settings` 表由 E2 節的 T219b 建立,本節依序接著改 `src/cgb/db/schema.py`,不另寫一份(依賴 T236a、T219b)
  - 🧪 `testplan.md` § US4-DB-01
  - ⚙ `contracts/store.dbml` § `Table settings`
  - 📎 `spec.md` § FR-027
- [ ] T237a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_db_schema.py` 寫 US4-DB-02 的測試(寫入一次用量(381.66、1.15、T),再寫入一次(380.00、1.15、T+5 分鐘),關閉連線後重新開啟再讀),執行確認它因為「每次讀用量都插入新列,表無限成長(Q76 只留最後一筆)」這類實作而失敗
  - 🧪 `testplan.md` § US4-DB-02
  - ⚙ `contracts/store.dbml` § `Table usage_snapshots`
  - 📎 `spec.md` § FR-024;`plan.md` § 待決問題 Q76
- [ ] T237b [US4] 🟢 /tdd 綠燈:在 `src/cgb/db/schema.py` 只寫讓 US4-DB-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;`usage_snapshots` 表由 E2 節的 T214b 建立,本節依序接著改 `src/cgb/db/schema.py`,不另寫一份(依賴 T237a、T214b)
  - 🧪 `testplan.md` § US4-DB-02
  - ⚙ `contracts/store.dbml` § `Table usage_snapshots`
  - 📎 `spec.md` § FR-024;`plan.md` § 待決問題 Q76
- [ ] T238 [US4] 🔵 /tdd 重構:在全部測試綠燈下整理 T236b~T237b 記下的重構清單(範圍限 `src/cgb/db/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T237b)
  - 🧪 `testplan.md` § US4-DB-01~US4-DB-02
  - 📎 `testplan.md` § 5.3

### E5 Colab CLI(google-colab-cli,外部程式)

- [ ] T239a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US4-CLI-01 的測試(呼叫),執行確認它因為「regex 沒允許負號,餘額歸零後變成負數時解析失敗」這類實作而失敗
  - 🧪 `testplan.md` § US4-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`
  - 📎 `spec.md` § FR-024、邊界情況
- [ ] T239b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US4-CLI-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T239a)
  - 🧪 `testplan.md` § US4-CLI-01
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`
  - 📎 `spec.md` § FR-024、邊界情況
- [ ] T240a [US4] 🔴 /tdd 紅燈:在 `tests/integration/test_colab_cli.py` 寫 US4-CLI-02 的測試(呼叫),執行確認它因為「用寬鬆的 regex 照樣解析,CLI 改版後默默顯示錯的值」這類實作而失敗
  - 🧪 `testplan.md` § US4-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-024
- [ ] T240b [US4] 🟢 /tdd 綠燈:在 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py` 只寫讓 US4-CLI-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T240a)
  - 🧪 `testplan.md` § US4-CLI-02
  - ⚙ `contracts/colab-cli.openapi.yaml` § `paths./usage.get`、`components.schemas.Error`
  - 📎 `spec.md` § FR-024
- [ ] T241 [US4] 🔵 /tdd 重構:在全部測試綠燈下整理 T239b~T240b 記下的重構清單(範圍限 `src/cgb/adapters/colab_cli.py`、`src/cgb/domain/colab_output.py`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/` 的斷言(依賴 T240b)
  - 🧪 `testplan.md` § US4-CLI-01~US4-CLI-02
  - 📎 `testplan.md` § 5.4

### E1、E6、E7、E8、E9、E10、E11

本故事不涉及這些端點的案例(E1 的畫面行為都要後端,放在跨端點驗收;真的 `colab usage` 的格式由 US1-CLI-21 實跑)(`testplan.md` § 5.5),這一節沒有任務。

### 跨端點驗收(`tests/e2e/`、`tests/realrun/`)

> 端點節都完成、驗收過後由主 agent 開始;真的瀏覽器(或區網程式)接測試行程內真的後端,轉接層用替身;📏 任務改接真的 Colab,照 P9 整批實跑

- [ ] T242a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_us4_usage.py` 寫 US4-AJ-01 的測試(打開用量頁),執行確認它因為「畫面只顯示餘額,缺耗用、可用時數或讀取時間」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-01
  - ⚙ `prototype/usage.html` § `#n-balance`、`#n-rate`、`#n-hours`、`#n-read`、`[data-state="normal"]`;`contracts/ui.openapi.yaml` § `paths./usage.get`
  - 📎 `spec.md` § FR-024
- [ ] T242b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/usage.html`、`src/cgb/static/js/usage.js` 只寫讓 US4-AJ-01 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T242a)
  - 🧪 `testplan.md` § US4-AJ-01
  - ⚙ `prototype/usage.html` § `#n-balance`、`#n-rate`、`#n-hours`、`#n-read`、`[data-state="normal"]`;`contracts/ui.openapi.yaml` § `paths./usage.get`
  - 📎 `spec.md` § FR-024
- [ ] T243a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_us4_usage.py` 寫 US4-AJ-02 的測試(打開用量頁,過 1 秒再放行),執行確認它因為「第一次讀到之前顯示 0 或空白的數字,看起來像餘額為 0」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-02
  - ⚙ `prototype/usage.html` § `[data-state="loading"]`、`[data-state="normal"]`;`contracts/ui.openapi.yaml` § `paths./usage.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendUsageUpdated`
  - 📎 `spec.md` § FR-024
- [ ] T243b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/usage.html`、`src/cgb/static/js/usage.js` 只寫讓 US4-AJ-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T243a)
  - 🧪 `testplan.md` § US4-AJ-02
  - ⚙ `prototype/usage.html` § `[data-state="loading"]`、`[data-state="normal"]`;`contracts/ui.openapi.yaml` § `paths./usage.get`;`contracts/ui-events.asyncapi.yaml` § `operations.sendUsageUpdated`
  - 📎 `spec.md` § FR-024
- [ ] T244a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_us4_usage.py` 寫 US4-AJ-03 的測試(打開用量頁;再到首頁按「開啟」並放行全部步驟),執行確認它因為「讀不到用量時首頁的「開啟」被停用」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-03
  - ⚙ `prototype/usage.html` § `[data-state="unknown"]`;`prototype/index.html` § `#open`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./usage.get`、`paths./session.post`
  - 📎 `spec.md` § FR-024
- [ ] T244b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/usage.html`、`src/cgb/static/js/usage.js`、`src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US4-AJ-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T244a)
  - 🧪 `testplan.md` § US4-AJ-03
  - ⚙ `prototype/usage.html` § `[data-state="unknown"]`;`prototype/index.html` § `#open`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./usage.get`、`paths./session.post`
  - 📎 `spec.md` § FR-024
- [ ] T245a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_us4_usage.py` 寫 US4-AJ-04 的測試(打開用量頁;再打開首頁,按「開啟」並放行),執行確認它因為「低餘額警告只在用量頁有」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-04
  - ⚙ `prototype/usage.html` § `#l-warn`、`[data-state="low"]`;`prototype/index.html` § `#open`、`#open-low`、`[data-state="low-balance"]`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./usage.get`、`paths./session.post`
  - 📎 `spec.md` § FR-025
- [ ] T245b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/usage.html`、`src/cgb/static/js/usage.js`、`src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US4-AJ-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T245a)
  - 🧪 `testplan.md` § US4-AJ-04
  - ⚙ `prototype/usage.html` § `#l-warn`、`[data-state="low"]`;`prototype/index.html` § `#open`、`#open-low`、`[data-state="low-balance"]`、`[data-state="ready"]`;`contracts/ui.openapi.yaml` § `paths./usage.get`、`paths./session.post`
  - 📎 `spec.md` § FR-025
- [ ] T246a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_us4_usage.py` 寫 US4-AJ-05 的測試(在用量頁 `#settings-form` 把閒置時限改成 10、警告門檻改成 400 並儲存;打開首頁),執行確認它因為「儲存後要重新整理才生效」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-05
  - ⚙ `prototype/usage.html` § `#settings-form`、`#idle`、`#warn`、`#saved`、`[data-state="low"]`;`prototype/index.html` § `#r-countdown`;`contracts/ui.openapi.yaml` § `paths./settings.put`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSettingsUpdated`、`operations.sendUsageUpdated`
  - 📎 `spec.md` § FR-027
- [ ] T246b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/usage.html`、`src/cgb/static/js/usage.js`、`src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US4-AJ-05 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T246a)
  - 🧪 `testplan.md` § US4-AJ-05
  - ⚙ `prototype/usage.html` § `#settings-form`、`#idle`、`#warn`、`#saved`、`[data-state="low"]`;`prototype/index.html` § `#r-countdown`;`contracts/ui.openapi.yaml` § `paths./settings.put`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSettingsUpdated`、`operations.sendUsageUpdated`
  - 📎 `spec.md` § FR-027
- [ ] T247a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_us4_idle.py` 寫 US4-AJ-06 的測試(打開首頁,時鐘推進 30 秒;再推進到超過 `deadline`),執行確認它因為「倒數不跟著時間走」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-06
  - ⚙ `prototype/index.html` § `#r-countdown`、`#e-reason`、`[data-state="ended-idle"]`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-026
- [ ] T247b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US4-AJ-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T247a)
  - 🧪 `testplan.md` § US4-AJ-06
  - ⚙ `prototype/index.html` § `#r-countdown`、`#e-reason`、`[data-state="ended-idle"]`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § FR-026
- [ ] T248a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_us4_idle.py` 寫 US4-AJ-07 的測試(`check_health` 失敗、`list_sessions` 不再列出這台),執行確認它因為「失聯時沒有提示可能是餘額歸零,使用者只看到一般的失聯」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-07
  - ⚙ `prototype/index.html` § `[data-state="lost-zero"]`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § 邊界情況
- [ ] T248b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/js/session.js` 只寫讓 US4-AJ-07 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T248a)
  - 🧪 `testplan.md` § US4-AJ-07
  - ⚙ `prototype/index.html` § `[data-state="lost-zero"]`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`
  - 📎 `spec.md` § 邊界情況
- [ ] T249a [US4] 🔴 /tdd 紅燈:在 `tests/e2e/test_us4_usage.py` 寫 US4-AJ-08 的測試(打開用量頁,把時鐘推進 16 分鐘),執行確認它因為「後端標了 `stale`,前端沒有顯示」這類實作而失敗
  - 🧪 `testplan.md` § US4-AJ-08
  - ⚙ `prototype/usage.html` § `#n-read`、`[data-state="stale"]`;`contracts/ui.openapi.yaml` § `paths./usage.get`
  - 📎 `spec.md` § NFR-008
- [ ] T249b [US4] 🟢 /tdd 綠燈:在 `src/cgb/static/usage.html`、`src/cgb/static/js/usage.js` 只寫讓 US4-AJ-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T249a)
  - 🧪 `testplan.md` § US4-AJ-08
  - ⚙ `prototype/usage.html` § `#n-read`、`[data-state="stale"]`;`contracts/ui.openapi.yaml` § `paths./usage.get`
  - 📎 `spec.md` § NFR-008
- [ ] T250 [US4] 🔵 /tdd 重構:在全部測試綠燈下整理 T242b~T249b 記下的重構清單(範圍限 `src/cgb/static/`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/e2e/` 的斷言(依賴 T249b)
  - 🧪 `testplan.md` § US4-AJ-01~US4-AJ-08
  - 📎 `testplan.md` § 5.6
- [ ] T251 [US4] 📏 量測:撰寫 `tests/realrun/test_us4_aj_09.py`(`-m realrun`),照 US4-AJ-09 量測。假如:容器階段,US1-AJ-21 之後,沒有工作階段;真的 Colab、CLI、ssh、遠端 Ollama。當:開一台 T4 到就緒;在用量頁把閒置時限設成 1 分鐘並儲存;記下用量頁的餘額與耗用,同一分鐘內在終端機執行 `HOME=<暫存目錄>/home colab usage`;之後不送任何 Ollama 相容端點的請求,每 5 秒讀一次 `GET /api/session` 與 `colab sessions`。記下的數字與門檻:則1:用量頁的餘額和 `colab usage` 的差不超過 0.05 compute units;則2:用量頁的每小時耗用和 `colab usage` 的差不超過 0.05;則3:`idle.deadline` 到了之後 1 分鐘內 `endReason` 為 `IDLE_TIMEOUT`(SC-006);則4:自動結束後 1 分鐘內 `colab sessions` 沒有這個名稱(SC-003);則5:案例期間 `GET /api/usage` 的 `readAt` 至少更新過 1 次,相鄰兩次的間隔不超過 5 分鐘。副作用與護欄:P1~P9;開 1 台 T4,約 6 分鐘、約 0.12 compute units;閒置時限只在 `cgb-test` 這個實例改,結束後改回 30;不送任何 Ollama 相容端點的請求(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(0.05 差距與 1 分鐘門檻);樣本:一次實跑(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § US4-AJ-09
  - ⚙ `prototype/index.html` § `#open`、`[data-state="ready"]`;`prototype/usage.html` § `#settings-form`、`#n-balance`、`#n-rate`;`contracts/ui.openapi.yaml` § `paths./settings.put`、`paths./usage.get`、`paths./session.get`;`contracts/colab-cli.openapi.yaml` § `paths./usage.get`、`paths./sessions.get`
  - 📎 `spec.md` § FR-024、FR-026、NFR-008、SC-003、SC-006;`plan.md` § 待決問題 Q89、Q101、Q108

### 介面覆蓋(US4)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui.openapi.yaml` § `paths./usage.get` | T214b、T215b、T216b、T217b、T218b、T224b、T227b、T231b、T242b、T243b、T244b、T245b、T249b | T214a、T215a、T216a、T217a、T218a、T224a、T227a、T231a、T242a、T243a、T244a、T245a、T249a |
| `store.dbml` § `Table usage_snapshots` | T214b、T231b、T237b | T214a、T231a、T237a |
| `ui.openapi.yaml` § `paths./session.post`(擴充:US4-API-03、US4-API-04、US4-AJ-03、US4-AJ-04) | T216b、T217b、T244b、T245b | T216a、T217a、T244a、T245a |
| `ui.openapi.yaml` § `paths./session.delete`(擴充:US4-API-03) | T216b | T216a |
| `colab-cli.openapi.yaml` § `paths./usage.get`(擴充:US4-API-05、US4-API-18、US4-CLI-01、US4-CLI-02) | T218b、T231b、T239b、T240b | T218a、T231a、T239a、T240a |
| `ui-events.asyncapi.yaml` § `operations.sendUsageUpdated` | T218b、T224b、T243b、T246b | T218a、T224a、T243a、T246a |
| `ui.openapi.yaml` § `paths./settings.get` | T219b、T220b、T221b | T219a、T220a、T221a |
| `store.dbml` § `Table settings` | T219b、T220b、T236b | T219a、T220a、T236a |
| `ui.openapi.yaml` § `paths./settings.put` | T220b、T221b、T222b、T223b、T224b、T246b | T220a、T221a、T222a、T223a、T224a、T246a |
| `ui-events.asyncapi.yaml` § `operations.sendSettingsUpdated` | T220b、T246b | T220a、T246a |
| `ui.openapi.yaml` § `paths./session.get`(擴充:US4-API-09、US4-API-10、US4-API-12、US4-API-13、US4-API-14、US4-API-15、US4-API-16、US4-API-17) | T222b、T223b、T225b、T226b、T227b、T228b、T229b、T230b | T222a、T223a、T225a、T226a、T227a、T228a、T229a、T230a |
| `ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`(擴充:US4-API-09、US4-AJ-06、US4-AJ-07) | T222b、T247b、T248b | T222a、T247a、T248a |
| `ui.openapi.yaml` § `paths./sessions.get`(擴充:US4-API-12) | T225b | T225a |
| `ollama-compat.openapi.yaml` § `paths./api/tags.get`(擴充:US4-API-13) | T226b | T226a |
| `ui.openapi.yaml` § `paths./models.get`(擴充:US4-API-14) | T227b | T227a |
| `tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`(擴充:US4-API-17) | T230b | T230a |
| `ollama-compat.openapi.yaml` § `paths./api/pull.post`、`paths./api/push.post`、`paths./api/create.post`、`paths./api/copy.post`、`paths./api/delete.delete`、`paths./api/blobs/{digest}.head`、`paths./api/blobs/{digest}.post`(擴充:US4-OC-01) | T233b | T233a |
| `ollama-compat.openapi.yaml` § `paths./api/generate.post`(擴充:US4-OC-02) | T234b | T234a |
| `usage.html` § `[data-state="normal"]` | T242b、T243b | T242a、T243a |
| `usage.html` § `[data-state="loading"]` | T243b | T243a |
| `usage.html` § `[data-state="unknown"]` | T244b | T244a |
| `index.html` § `[data-state="ready"]`(擴充:US4-AJ-03、US4-AJ-04) | T244b、T245b | T244a、T245a |
| `usage.html` § `[data-state="low"]` | T245b、T246b | T245a、T246a |
| `index.html` § `[data-state="low-balance"]` | T245b | T245a |
| `index.html` § `[data-state="ended-idle"]` | T247b | T247a |
| `index.html` § `[data-state="lost-zero"]` | T248b | T248a |
| `usage.html` § `[data-state="stale"]` | T249b | T249a |

### 測試案例覆蓋(US4)

> `testplan.md` 本故事的每個案例都要有一組紅綠任務;每個有案例的節都要有一個重構任務;📏 案例列它的量測任務

| testplan 案例 | 紅燈 | 綠燈 | 重構 |
|---|---|---|---|
| US4-API-01~US4-API-18 | T214a~T231a | T214b~T231b | T232 |
| US4-OC-01~US4-OC-02 | T233a~T234a | T233b~T234b | T235 |
| US4-DB-01~US4-DB-02 | T236a~T237a | T236b~T237b | T238 |
| US4-CLI-01~US4-CLI-02 | T239a~T240a | T239b~T240b | T241 |
| US4-AJ-01~US4-AJ-08 | T242a~T249a | T242b~T249b | T250 |
| US4-AJ-09 | — | — | T251(📏) |

**Checkpoint**: `uv run pytest tests/integration tests/e2e` 全綠(不含 `-m realrun`);重構任務前後的測試結果相同;本故事的 📏 任務留給全部故事完成後依 P9 整批實跑

---

## Phase 6: 全域測試區

**Purpose**: 照 `testplan.md` § 6.2 驗證跨故事的 NFR 與 SC(NFR-009~NFR-012)

- [ ] T252a [G] 🔴 /tdd 紅燈:在 `tests/integration/test_secrets.py` 寫 G-02 的測試(依序走過:登入成功、開啟成功、開啟失敗、重連逾時、結束;擷取所有日誌(caplog 與 stdout、stderr)、所有 API 回應與 SSE 事件),執行確認它因為「用 DEBUG 等級記下子行程的 stdout、stderr 全文」這類實作而失敗
  - 🧪 `testplan.md` § G-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post`、`paths./session.post`、`paths./session.delete`、`components.schemas.Error`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`、`operations.sendAuthUpdated`
  - 📎 `spec.md` § NFR-010
- [ ] T252b [G] 🟢 /tdd 綠燈:在 `src/cgb/logging_setup.py`、`src/cgb/ollama_compat/access_log.py`、`src/cgb/domain/errors.py` 只寫讓 G-02 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T252a)
  - 🧪 `testplan.md` § G-02
  - ⚙ `contracts/ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post`、`paths./session.post`、`paths./session.delete`、`components.schemas.Error`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`、`operations.sendAuthUpdated`
  - 📎 `spec.md` § NFR-010
- [ ] T253a [G] 🔴 /tdd 紅燈:在 `tests/integration/test_repo_hygiene.py` 寫 G-03 的測試(列出 `git ls-files`,讀 `.gitignore` 與 `deploy/Dockerfile.dockerignore`),執行確認它因為「實跑後把暫存資料或 `.env` 誤 commit 進 repo」這類實作而失敗;testplan 寫的 `deploy/Dockerfile.dockerignore` 依 plan.md Q85 搬遷後是 repo 根目錄的 `Dockerfile.dockerignore`(plan.md Q118);先對一份故意拿掉 `.env` 排除行的 `.gitignore` 複本(對照組)執行,確認測試抓得到;再對 repo 的實物執行,實物已經通過時在任務備註記下「Setup 已滿足」
  - 🧪 `testplan.md` § G-03
  - ⚙ `deploy/Dockerfile.dockerignore` § 全檔
  - 📎 `spec.md` § NFR-010
- [ ] T253b [G] 🟢 /tdd 綠燈:在 `.gitignore`、`Dockerfile.dockerignore` 只寫讓 G-03 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;`.gitignore` 補上 `.env`、`data/`、`*.sqlite3`、`token.json`、`sessions.json`、`id_ed25519*`,`Dockerfile.dockerignore` 確認排除 `.env` 與 `data/`;Setup 已經寫進的就不重寫(依賴 T253a)
  - 🧪 `testplan.md` § G-03
  - ⚙ `deploy/Dockerfile.dockerignore` § 全檔
  - 📎 `spec.md` § NFR-010
- [ ] T254a [G] 🔴 /tdd 紅燈:在 `tests/integration/test_prepare_data.py` 寫 G-04 的測試(以子行程跑 `prepare-data.sh true`,再跑 `prepare-data.sh --check`),執行確認它因為「把舊的 `colab.log` 改名保留(含 token 的 DEBUG 紀錄還在)」這類實作而失敗;先對一份故意改成「把舊 `colab.log` 改名保留」的 `prepare-data.sh` 複本(對照組)執行,確認測試抓得到;再對 T013 搬來的 `deploy/prepare-data.sh` 執行,實物已經通過時在任務備註記下「Setup 原樣複製的腳本已滿足」
  - 🧪 `testplan.md` § G-04
  - ⚙ `deploy/compose.yaml` § `services.cgb.volumes`、`services.cgb.tmpfs`
  - 📎 `spec.md` § NFR-010、NFR-012
- [ ] T254b [G] 🟢 /tdd 綠燈:在 `deploy/prepare-data.sh` 只寫讓 G-04 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T254a)
  - 🧪 `testplan.md` § G-04
  - ⚙ `deploy/compose.yaml` § `services.cgb.volumes`、`services.cgb.tmpfs`
  - 📎 `spec.md` § NFR-010、NFR-012
- [ ] T255a [G] 🔴 /tdd 紅燈:在 `tests/e2e/test_locale.py` 寫 G-06 的測試(用 Playwright 打開首頁、登入頁、紀錄頁、模型頁、下載模型頁、用量頁(Q111)的每個 `data-state`,取可見文字;觸發 UI API 每一個錯誤代碼一次與 Ollama 相容端點本系統自己產生的每一種錯誤一次),執行確認它因為「錯誤訊息直接用 Python 例外的英文」這類實作而失敗
  - 🧪 `testplan.md` § G-06
  - ⚙ `prototype/history.html` § `[data-state="normal"]`、`[data-state="empty"]`;`prototype/index.html` § `[data-state="normal"]`、`[data-state="low-balance"]`、`[data-state="needs-login"]`、`[data-state="starting"]`、`[data-state="ready"]`、`[data-state="confirm-stop"]`、`[data-state="confirm-switch"]`、`[data-state="stopping"]`、`[data-state="switching"]`、`[data-state="ended"]`、`[data-state="ended-idle"]`、`[data-state="failed"]`、`[data-state="already-open"]`、`[data-state="reconnecting"]`、`[data-state="lost"]`、`[data-state="lost-timeout"]`、`[data-state="lost-zero"]`、`[data-state="release-failed"]`、`[data-state="resuming"]`、`[data-state="foreign"]`;`prototype/library.html` § `[data-state="normal"]`、`[data-state="searching"]`、`[data-state="results"]`、`[data-state="no-results"]`、`[data-state="library-down"]`、`[data-state="checking"]`、`[data-state="confirm"]`、`[data-state="no-space"]`、`[data-state="not-found"]`、`[data-state="cloud-only"]`、`[data-state="no-session"]`;`prototype/login.html` § `[data-state="normal"]`、`[data-state="signed-in"]`、`[data-state="loading"]`、`[data-state="link"]`、`[data-state="verifying"]`、`[data-state="failed"]`、`[data-state="link-expired"]`、`[data-state="scope-missing"]`、`[data-state="unreachable"]`;`prototype/models.html` § `[data-state="normal"]`、`[data-state="empty"]`、`[data-state="loading"]`、`[data-state="no-session"]`、`[data-state="preload-warn"]`、`[data-state="preloading"]`、`[data-state="preload-failed"]`;`prototype/usage.html` § `[data-state="normal"]`、`[data-state="low"]`、`[data-state="unknown"]`、`[data-state="stale"]`、`[data-state="loading"]`;`contracts/ui.openapi.yaml` § `components.schemas.Error`;`contracts/ollama-compat.openapi.yaml` § `components.schemas.OllamaError`
  - 📎 `spec.md` § NFR-011;`plan.md` § 待決問題 Q105、Q111
- [ ] T255b [G] 🟢 /tdd 綠燈:在 `src/cgb/static/index.html`、`src/cgb/static/login.html`、`src/cgb/static/history.html`、`src/cgb/static/models.html`、`src/cgb/static/library.html`、`src/cgb/static/usage.html`、`src/cgb/static/js/`、`src/cgb/domain/errors.py` 只寫讓 G-06 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單;補齊各故事都沒有做到的畫面狀態(登入頁 `loading`、`verifying`、`scope-missing`、`unreachable`,下載模型頁 `searching`、`checking`、`no-results`、`library-down`、`cloud-only`、`no-session`,模型頁 `empty`、`loading`、`preload-failed`,紀錄頁 `empty`),每一個都照原型的繁體中文文字;`<html lang="zh-Hant-TW">`(依賴 T255a)
  - 🧪 `testplan.md` § G-06
  - ⚙ `prototype/history.html` § `[data-state="normal"]`、`[data-state="empty"]`;`prototype/index.html` § `[data-state="normal"]`、`[data-state="low-balance"]`、`[data-state="needs-login"]`、`[data-state="starting"]`、`[data-state="ready"]`、`[data-state="confirm-stop"]`、`[data-state="confirm-switch"]`、`[data-state="stopping"]`、`[data-state="switching"]`、`[data-state="ended"]`、`[data-state="ended-idle"]`、`[data-state="failed"]`、`[data-state="already-open"]`、`[data-state="reconnecting"]`、`[data-state="lost"]`、`[data-state="lost-timeout"]`、`[data-state="lost-zero"]`、`[data-state="release-failed"]`、`[data-state="resuming"]`、`[data-state="foreign"]`;`prototype/library.html` § `[data-state="normal"]`、`[data-state="searching"]`、`[data-state="results"]`、`[data-state="no-results"]`、`[data-state="library-down"]`、`[data-state="checking"]`、`[data-state="confirm"]`、`[data-state="no-space"]`、`[data-state="not-found"]`、`[data-state="cloud-only"]`、`[data-state="no-session"]`;`prototype/login.html` § `[data-state="normal"]`、`[data-state="signed-in"]`、`[data-state="loading"]`、`[data-state="link"]`、`[data-state="verifying"]`、`[data-state="failed"]`、`[data-state="link-expired"]`、`[data-state="scope-missing"]`、`[data-state="unreachable"]`;`prototype/models.html` § `[data-state="normal"]`、`[data-state="empty"]`、`[data-state="loading"]`、`[data-state="no-session"]`、`[data-state="preload-warn"]`、`[data-state="preloading"]`、`[data-state="preload-failed"]`;`prototype/usage.html` § `[data-state="normal"]`、`[data-state="low"]`、`[data-state="unknown"]`、`[data-state="stale"]`、`[data-state="loading"]`;`contracts/ui.openapi.yaml` § `components.schemas.Error`;`contracts/ollama-compat.openapi.yaml` § `components.schemas.OllamaError`
  - 📎 `spec.md` § NFR-011;`plan.md` § 待決問題 Q105、Q111
- [ ] T256a [G] 🔴 /tdd 紅燈:在 `tests/integration/test_healthcheck.py` 寫 G-08 的測試(以子行程跑 `deploy/healthcheck.py`;再把假 UI 改成回 503 跑一次),執行確認它因為「健康檢查對 Ollama 相容 port 送 HTTP,每 30 秒重設閒置計時,工作階段永遠不會閒置結束(Q89)」這類實作而失敗;先對一份故意改成對 Ollama 相容 port 送 `GET /api/version` 的 `healthcheck.py` 複本(對照組)執行,確認測試抓得到;再對 T014 搬來的 `deploy/healthcheck.py` 執行,實物已經通過時在任務備註記下「Setup 原樣複製的腳本已滿足」
  - 🧪 `testplan.md` § G-08
  - ⚙ `deploy/compose.yaml` § `services.cgb.healthcheck`
  - 📎 `spec.md` § NFR-012;`plan.md` § 待決問題 Q89
- [ ] T256b [G] 🟢 /tdd 綠燈:在 `deploy/healthcheck.py` 只寫讓 G-08 通過的程式碼,執行全部測試確認都通過;看到要整理的地方記進重構清單(依賴 T256a)
  - 🧪 `testplan.md` § G-08
  - ⚙ `deploy/compose.yaml` § `services.cgb.healthcheck`
  - 📎 `spec.md` § NFR-012;`plan.md` § 待決問題 Q89
- [ ] T257 [G] 🔵 /tdd 重構:在全部測試綠燈下整理 T252b、T253b、T254b、T255b、T256b 記下的重構清單(範圍限 `src/cgb/`、`deploy/`、`.gitignore`、`Dockerfile.dockerignore`),每改一小步執行全部測試,變紅就撤回那一步;不改 `tests/integration/`、`tests/e2e/` 的斷言(依賴 T256b)
  - 🧪 `testplan.md` § G-02、G-03、G-04、G-06、G-08
  - 📎 `testplan.md` § 6.2
- [ ] T258 [G] 📏 量測(人工):⏸ 延後:需要使用者本人在場,不在 P9 這一批(plan.md Q101 決定實跑授權改為複製既有 token.json、比對 sha256,US1-OA-06 與 G-01 延後到使用者回來;Q108),使用者回來並同意前不執行;撰寫 `tests/realrun/test_g_01.py`(`-m realrun`),照 G-01 量測。假如:延後到使用者在場時另跑(Q108),不在 P9 這一批;`docker compose -p cgb-test` 起在桌機,`.env` 的 `CGB_BIND_ADDR=0.0.0.0`(本案例暫時改,其他案例用 127.0.0.1)、UI 8780、Ollama 相容端點 11436;沒有工作階段。當:使用者用同一個區網的另一台裝置(手機連 Wi-Fi 或另一台電腦)打開 `http://<桌機區網 IP>:8780`,並對 `http://<桌機區網 IP>:11436/api/version` 送請求;再把手機切到行動網路,或用 check-host.net,對桌機的公網 IP 連 8780 與 11436。記下的數字與門檻:則1:區網裝置不需要任何登入就看到首頁;則2:區網裝置對 11436 收到 503 與「沒有可用的工作階段」;則3:行動網路或 check-host.net 對 8780 連不上;則4:行動網路或 check-host.net 對 11436 連不上。副作用與護欄:P5、P6;不開執行環境,0 compute units,約 5 分鐘;不改路由器設定,只觀察;不在區網內連公網 IP(NAT hairpin 結果不可信);測完把 `CGB_BIND_ADDR` 改回 127.0.0.1 並重建容器(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:使用者(則1、則2 看畫面與回應);腳本或 check-host.net 結果判定則3、則4;樣本:一台區網裝置與一個外網來源(未用於調整)。使用者在場時另跑,不和 P9 那一批一起;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § G-01
  - ⚙ `deploy/compose.yaml` § `services.cgb.ports`;`prototype/index.html` § `[data-state="normal"]`;`contracts/ollama-compat.openapi.yaml` § `paths./api/version.get`、`components.schemas.OllamaError`
  - 📎 `spec.md` § NFR-009;`plan.md` § 待決問題 Q101、Q108
- [ ] T259 [G] 📏 量測:撰寫 `tests/realrun/test_g_05.py`(`-m realrun`),照 G-05 量測。假如:整批實跑結束、P3 之後;`<暫存目錄>/data/colab-cli/token.json` 仍在。當:從 token.json 取出 access token 與 refresh token 寫進一個 0600 的暫存 pattern 檔(不印出);對 `docker compose -p cgb-test logs`、`<暫存目錄>/data` 底下 `token.json` 與 `sessions.json` 以外的每個檔、實跑錄下的所有 API 回應與 SSE 事件,執行 `grep -c -F -f <pattern 檔>`,只印每個來源的次數。記下的數字與門檻:則1:每個來源的次數都是 0;則2:`colab.log` 是指向 `/dev/null` 的符號連結;則3:`docker inspect` 的環境變數裡沒有 token。副作用與護欄:P6、P8;不開執行環境,0 compute units,約 2 分鐘;pattern 檔放 `<暫存目錄>`,用完立即刪除;先以一個已知的假 token 驗一次這條 grep 指令真的數得到(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本(次數 0);樣本:整批實跑產生的日誌與檔案(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § G-05
  - ⚙ `deploy/compose.yaml` § `services.cgb`
  - 📎 `spec.md` § NFR-010;`plan.md` § 待決問題 Q101、Q108
- [ ] T260 [G] 📏 量測:撰寫 `tests/realrun/test_g_07.py`(`-m realrun`),照 G-07 量測。假如:整批實跑的最後(P3 之後),`<暫存目錄>/.env` 只有 `CGB_HOST_DATA`、`CGB_HOST_UI_PORT=8780`、`CGB_HOST_OLLAMA_PORT=11436`、`CGB_BIND_ADDR=127.0.0.1`;資料夾裡已有複製來的授權與 US1-AJ-17~US1-AJ-22、US4-AJ-09 的紀錄。當:`docker compose -p cgb-test --env-file <暫存目錄>/.env down`,再 `up -d --force-recreate`(沿用已建好的映像);等健康;讀 `GET /api/auth`、`GET /api/sessions`;`docker exec` 讀 `/data` 底下的權限。記下的數字與門檻:則1:`up` 後 90 秒內容器狀態為 healthy;則2:`GET /api/auth` 的 `state` 為 `logged_in`;則3:`GET /api/sessions` 的筆數與重建前相同;則4:`/data/cgb.sqlite3`、`/data/colab-cli/token.json`、`/data/ssh/id_ed25519` 的權限是 0600;則5:`/data/colab-cli/history` 是 tmpfs,重建後是空的。副作用與護欄:P3、P5、P6、P8;不開執行環境,0 compute units,約 3 分鐘;只操作 `-p cgb-test`,不碰 named volume `cgb-data`;重建後不按「開啟」(P1~P9 見 `testplan.md` § 實跑案例的共同護欄,由 T008 的 fixture 執行)。判定者與樣本:判定者:腳本;樣本:整批實跑留下的資料(未用於調整)。依 P9 的順序與其他實跑整批執行,開始前要使用者同意;結果(數字、是否過門檻、沒跑到的列為未驗證)寫進 `specs/001-session-model-catalog/measurements.md`
  - 🧪 `testplan.md` § G-07
  - ⚙ `deploy/compose.yaml` § `services.cgb`、`services.cgb.volumes`、`services.cgb.tmpfs`、`services.cgb.healthcheck`;`contracts/ui.openapi.yaml` § `paths./auth.get`、`paths./sessions.get`
  - 📎 `spec.md` § NFR-012、NFR-010;`plan.md` § 待決問題 Q101、Q108

### 介面覆蓋(全域)

| 介面元素 | 綠燈 | 紅燈 |
|---|---|---|
| `ui.openapi.yaml` § `paths./auth/authorizations/{flowId}/code.post`、`paths./session.post`、`paths./session.delete`(擴充:G-02) | T252b | T252a |
| `ui-events.asyncapi.yaml` § `operations.sendSessionUpdated`、`operations.sendAuthUpdated`(擴充:G-02) | T252b | T252a |
| `history.html` § `[data-state="normal"]`(擴充:G-06) | T255b | T255a |
| `history.html` § `[data-state="empty"]` | T255b | T255a |
| `index.html` § `[data-state="normal"]`、`[data-state="low-balance"]`、`[data-state="needs-login"]`、`[data-state="starting"]`、`[data-state="ready"]`、`[data-state="confirm-stop"]`、`[data-state="confirm-switch"]`、`[data-state="stopping"]`、`[data-state="switching"]`、`[data-state="ended"]`、`[data-state="ended-idle"]`、`[data-state="failed"]`、`[data-state="already-open"]`、`[data-state="reconnecting"]`、`[data-state="lost"]`、`[data-state="lost-timeout"]`、`[data-state="lost-zero"]`、`[data-state="release-failed"]`、`[data-state="resuming"]`、`[data-state="foreign"]`(擴充:G-06) | T255b | T255a |
| `library.html` § `[data-state="normal"]`、`[data-state="results"]`、`[data-state="confirm"]`、`[data-state="no-space"]`、`[data-state="not-found"]`(擴充:G-06) | T255b | T255a |
| `library.html` § `[data-state="searching"]`、`[data-state="no-results"]`、`[data-state="library-down"]`、`[data-state="checking"]`、`[data-state="cloud-only"]`、`[data-state="no-session"]` | T255b | T255a |
| `login.html` § `[data-state="normal"]`、`[data-state="signed-in"]`、`[data-state="link"]`、`[data-state="failed"]`、`[data-state="link-expired"]`(擴充:G-06) | T255b | T255a |
| `login.html` § `[data-state="loading"]`、`[data-state="verifying"]`、`[data-state="scope-missing"]`、`[data-state="unreachable"]` | T255b | T255a |
| `models.html` § `[data-state="normal"]`、`[data-state="no-session"]`、`[data-state="preload-warn"]`、`[data-state="preloading"]`(擴充:G-06) | T255b | T255a |
| `models.html` § `[data-state="empty"]`、`[data-state="loading"]`、`[data-state="preload-failed"]` | T255b | T255a |
| `usage.html` § `[data-state="normal"]`、`[data-state="low"]`、`[data-state="unknown"]`、`[data-state="stale"]`、`[data-state="loading"]`(擴充:G-06) | T255b | T255a |

### 測試案例覆蓋(全域)

| testplan 案例 | 任務 |
|---|---|
| G-01 | T258 |
| G-02 | T252a、T252b、T257 |
| G-03 | T253a、T253b、T257 |
| G-04 | T254a、T254b、T257 |
| G-05 | T259 |
| G-06 | T255a、T255b、T257 |
| G-07 | T260 |
| G-08 | T256a、T256b、T257 |

**Checkpoint**: 全部測試綠燈;`specs/001-session-model-catalog/measurements.md` 每一項都寫了數字與是否過門檻,沒過的列為待決問題;⏸ 的 US1-OA-06、G-01 等使用者回來再跑

---

## SC 量測

> 本表給 analyze 的前置檢查用(它以不帶 `--testplan` 的方式呼叫 `check_tasks.py`);SC 的量測案例以 testplan.md 為準,這裡只列對應的 📏 任務。

| SC | 量測任務 | 量測條件 |
|---|---|---|
| SC-001 | T116 | 桌機容器、真的 Colab T4;按下開啟到「就緒」(不含模型載入)≤ 5 分鐘,超過即開啟失敗並釋放 |
| SC-002 | T117、T121 | 真的 Colab;`colab stop` 模擬收回後 ≤ 2 分鐘顯示失聯;SIGKILL ssh 模擬斷線後 ≤ 1 分鐘顯示重連中,重連時限到才失聯 |
| SC-003 | T077、T119、T120、T251 | 真的 Colab;每次結束(使用者結束、閒置自動結束、開啟失敗)後 ≤ 1 分鐘,`colab sessions` 沒有本系統的遺留 |
| SC-004 | T212 | 真的 Colab T4;qwen2.5:7b(約 4.7GB)從開始下載到可推論 ≤ 3 分鐘 |
| SC-005 | T148 | 真的 Colab;單次非串流請求經 Ollama 相容端點與直連轉發 port 的延遲差 ≤ 0.5 秒 |
| SC-006 | T251 | 真的 Colab;閒置時限設 1 分鐘,到期後 ≤ 1 分鐘自動結束 |
| SC-007 | T149 | 不開執行環境;沒有就緒的工作階段時,Ollama 相容端點 ≤ 1 秒回「沒有可用的工作階段」 |
| SC-008 | T213 | 真的 Colab;背景下載期間單次非串流請求的延遲比沒有下載時增加 ≤ 0.5 秒 |

## 待決問題

排任務時先採用的做法都已登記在 `plan.md` § 待決問題 Q110~Q118 並決定(Q110 (b) 故事 4 拉回範疇、Q111 (b) G-06 也看用量頁,其餘照先採用);testplan 提出的 Q119~Q122 也已決定照先採用。這次修訂沒有新的待決問題。
