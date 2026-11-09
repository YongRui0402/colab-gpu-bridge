# 測試計劃:Colab GPU 工作階段管理與模型目錄

- **規格**:`specs/001-session-model-catalog/spec.md`
- **系統分析**:`plan.md` § 端點盤點(E1 前端 UI、E2 後端 UI API、E3 Ollama 相容端點、E4 資料庫、E5 Colab CLI、E6 SSH 通道、E7 遠端 Ollama、E8 Ollama 官方模型庫、E9 Google OAuth、E10 檔案系統、E11 部署與網路);`contracts/ui.openapi.yaml`、`contracts/ui-events.asyncapi.yaml`、`contracts/ollama-compat.openapi.yaml`、`contracts/colab-cli.openapi.yaml`、`contracts/tunnel.openapi.yaml`、`contracts/remote-ollama.openapi.yaml`、`contracts/model-library.openapi.yaml`、`contracts/google-oauth.openapi.yaml`;`contracts/store.dbml`;`prototype/index.html`、`prototype/login.html`、`prototype/history.html`、`prototype/models.html`、`prototype/library.html`、`prototype/usage.html`;`deploy/compose.yaml`、`deploy/Dockerfile`、`deploy/prepare-data.sh`、`deploy/healthcheck.py`
- **測試技術**:`techstack.md` § 一覽(測試列:pytest 9.2.0、pytest-asyncio 1.4.1.post1、httpx ASGI transport 0.28.1、Playwright(Python)1.64.1、pytest-playwright 0.10.0);research.md R12(替身只放在 adapter,每個 adapter 至少一個打真實服務的實跑案例)、R1(CLI 的 exit code 不可信、`colab exec` 偶發 `Connection was lost`)、R3(健康檢查 15 秒、斷線模擬是殺掉 ssh)、R5(背景下載不影響推論)、R8(轉送延遲在雜訊內)
- **日期**:2026-11-09
- **範疇**:使用者故事 1、2、3、4(plan.md Q110);每個測試案例在 `tasks.md` 對應一組 `/tdd` 紅燈與綠燈任務,量測與人工驗證的案例對應 📏 任務
- **預設資料**:除非案例另寫,工作階段名稱 `cgb-test-0001`(第二個 `cgb-test-0002`),類型 `{gpu:"T4",highMem:false}`;模型 `qwen2.5:0.5b`(替身回 397,821,319 位元組)與 `qwen2.5:7b`(替身回 4,683,087,332 位元組);替身回的剩餘磁碟 225,485,783,040 位元組、顯示記憶體總量 16,106,127,360 位元組;已登入(`FakeColabControl.get_usage` 成功);SQLite 是每個測試各自的暫存檔;自動化測試注入縮短的時限(Q95 先採用):開啟總時限 3 秒、健康檢查間隔 0.2 秒、重連時限 2 秒、重連節奏「立即、0.05、0.1、0.2 秒,之後每 0.3 秒」、通道就緒期限 1 秒、健康檢查逾時 0.3 秒

## 1. 待測端點

端點、介面規格檔與公開接縫照抄 `plan.md` § 端點盤點與它指到的規格檔,本計劃不另做系統規劃;測試等級、工具與環境取自 `techstack.md` § 一覽的測試列與 research.md R12。上游沒寫到的,登記到 `plan.md` 的待決問題,不在這裡自行補上;這張表與下面各節標「Qnn 先採用」的,是第 9 節列出的待決問題(Q95~Q107 已登記並決定,本次新提的見第 9 節)。

| 端點 | 介面規格檔 | 公開接縫 | 測試等級 | 工具 | 測試環境 | 替身 |
|---|---|---|---|---|---|---|
| E2 後端 UI API(FastAPI REST 與 SSE) | `contracts/ui.openapi.yaml`、`contracts/ui-events.asyncapi.yaml` | 資源、操作、錯誤、長時間操作的進度與取消、狀態推送事件:HTTP `/api/*` 的回應與 SSE `/api/events` 的事件 | 整合(真的 api、services、domain、repos 與 SQLite;五個轉接層用替身) | pytest + pytest-asyncio + httpx ASGI transport;SSE 與串流的案例改用測試行程內的 uvicorn(127.0.0.1 隨機 port,Q97 先採用) | 每個測試一個暫存 SQLite 檔;`create_app` 注入縮短的時限、時鐘與名稱前綴 `cgb-test-`(Q95 先採用);轉接層替身以建構參數注入 services(Q96 先採用) | `httpx.ASGITransport`(uvicorn 與真的 HTTP 連線)→ US1-AJ-17<br>`FakeColabControl`(Colab CLI 轉接層)→ US1-CLI-21、US1-AJ-17、US4-AJ-09<br>`FakeTunnel`(SSH 通道轉接層)→ US1-TUN-10、US1-AJ-18<br>`FakeRemoteOllama`(遠端 Ollama 轉接層)→ US2-RO-03、US3-AJ-12<br>`FakeModelLibrary`(官方模型庫轉接層)→ US3-LIB-05<br>`FakeGoogleOAuth`(Google OAuth 轉接層)→ US1-OA-06<br>注入的時鐘與縮短的時限(真實時間與 5 分鐘時限、閒置時限)→ US1-AJ-17、US1-AJ-22、US4-AJ-09 |
| E3 Ollama 相容端點(FastAPI 轉送) | `contracts/ollama-compat.openapi.yaml` | 開放與阻擋的路徑、沒有工作階段時的錯誤、串流轉送、閒置計時的觸發:Ollama 相容 port 上的 HTTP 回應(狀態碼、`OllamaError` 本文、NDJSON 每一行) | 整合(真的 ollama_compat、services 與 SQLite;轉接層用替身) | pytest + httpx ASGI transport;要看「逐段傳回、不緩衝」的案例改用 uvicorn(Q97 先採用) | 同 E2;`FakeRemoteOllama` 是測試行程內 127.0.0.1 隨機 port 的假 HTTP 伺服器,讓轉送真的經過 httpx 的網路連線 | `httpx.ASGITransport`(uvicorn 與真的 HTTP 連線)→ US2-AJ-03<br>`FakeRemoteOllama`(Colab 上的遠端 Ollama 經通道)→ US2-RO-03、US2-AJ-02<br>`FakeTunnel`、`FakeColabControl`(工作階段就緒所需的通道與執行環境)→ US2-AJ-02 |
| E4 資料庫(SQLite) | `contracts/store.dbml` | 資料表、關聯、唯一性與狀態約束:`db` 模組建立的 schema,以標準函式庫 `sqlite3` 下 SQL(Q98 先採用) | 整合(真的 SQLite 檔) | pytest | 暫存資料夾裡的 SQLite 檔,WAL 模式 | 無 |
| E5 Colab CLI(google-colab-cli,外部程式) | `contracts/colab-cli.openapi.yaml` | 外部程式呼叫:要用的指令與參數、輸出的解析、失敗的判定、逾時與重試:`ColabControl` 的方法(Q96 先採用) | 整合(真的子行程;`colab` 是假的執行檔) | pytest;假執行檔 `tests/fixtures/bin/colab` 依測試寫好的劇本印 stdout、stderr、exit code,並記下每次的 argv、stdin 與環境變數(Q96 先採用) | `PATH` 前面加上假執行檔的資料夾;`HOME` 指到暫存資料夾 | `tests/fixtures/bin/colab`(Colab CLI 0.7.5 與 Colab 後端)→ US1-CLI-21 |
| E6 SSH 通道(OpenSSH 與 `colab ssh --proxy-mode`) | `contracts/tunnel.openapi.yaml` | 外部程式呼叫:轉發的建立與參數、健康檢查、斷線判定與重連:`Tunnel` 的方法;重連的每一輪由 services 組成(Q100 先採用) | 整合(真的子行程與真的 `ssh-keygen`;`ssh` 是假的執行檔) | pytest;假執行檔 `tests/fixtures/bin/ssh` 依劇本印 stderr、結束或常駐,並記下 argv | 暫存資料夾放金鑰;假的 `/api/version` HTTP 伺服器聽 127.0.0.1 隨機 port,代表轉發的另一端 | `tests/fixtures/bin/ssh`(OpenSSH 與 `colab ssh --proxy-mode`)→ US1-TUN-10<br>假的 `/api/version` 伺服器(經通道的遠端 Ollama)→ US1-TUN-10 |
| E7 遠端 Ollama(Colab 執行環境上,Ollama API) | `contracts/remote-ollama.openapi.yaml` | Ollama 提供的 API:列模型、查已載入、預先載入、下載與進度、推論、版本:`RemoteOllama` 的方法 | 整合(真的 httpx 用戶端;對方是假的 HTTP 伺服器) | pytest + pytest-asyncio | 測試行程內 127.0.0.1 隨機 port 的假 Ollama 伺服器,依劇本回 JSON、NDJSON、中途斷線或不回應 | 假的 Ollama 伺服器(Colab 上的 Ollama 0.40.15)→ US2-RO-03、US3-AJ-12 |
| E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai) | `contracts/model-library.openapi.yaml` | 對方提供的介面:搜尋、版本清單、manifest 與大小:`ModelLibrary` 的方法 | 整合(真的 HTML 與 manifest 解析;對方用 `httpx.MockTransport`) | pytest | `tests/fixtures/library/` 存下來的搜尋頁、版本頁 HTML 與 manifest JSON(合成的資料) | `httpx.MockTransport` 與存下來的頁面(ollama.com 與 registry.ollama.ai)→ US3-LIB-05 |
| E9 Google OAuth(授權碼流程) | `contracts/google-oauth.openapi.yaml` | 對方提供的介面:授權網址、授權碼換 token、token 更新:`GoogleOAuth` 的方法(Q96 先採用) | 整合(真的 google-auth-oauthlib 流程;token 端點用 `httpx.MockTransport` 或等價的假端點) | pytest | 假的 token 端點依劇本回 200、400、401、5xx 或連不到 | 假的 token 端點(Google OAuth `oauth2.googleapis.com/token`)→ US1-OA-06 |
| E1 前端 UI(瀏覽器,原生 HTML/CSS/JS) | `prototype/index.html`、`prototype/login.html`、`prototype/history.html`、`prototype/models.html`、`prototype/library.html`、`prototype/usage.html` | — | — | — | 四個故事都沒有不靠後端就看得到的畫面行為(每個畫面都要先從 `/api/session` 或 SSE 拿到狀態才有內容),不測;畫面行為都放在各故事的跨端點驗收 | — |
| E10 檔案系統(`/data` 掛載) | `deploy/compose.yaml`(`x-data-layout`)、`deploy/prepare-data.sh`、`deploy/Dockerfile` | 授權檔、CLI 狀態檔、SSH 金鑰、資料庫檔的路徑、權限與持久化:`cgb-prepare-data` 的結果與 `/data` 底下檔案的類型與權限 | 整合(真的 shell 腳本)、📏 量測(真的容器) | pytest(以子行程跑 `prepare-data.sh`) | `CGB_DATA_DIR`、`CGB_COLAB_CONFIG_DIR`、`CGB_SSH_IDENTITY_PATH` 指到暫存資料夾;只出現在全域測試區(NFR-010、NFR-012) | 暫存資料夾(容器裡的 `/data` 掛載)→ G-07 |
| E11 部署與網路(Docker Compose) | `deploy/compose.yaml`、`deploy/healthcheck.py` | 服務、區網 port 與綁定、掛載、環境變數:compose 起的容器、兩個入口的 port 與 `cgb-healthcheck` 的結果 | 整合(真的 `healthcheck.py`)、📏 量測與 📏 人工(真的容器與區網裝置) | pytest;`docker compose -p cgb-test`;另一台區網裝置的瀏覽器 | 只出現在全域測試區(NFR-009、NFR-012);容器一律 `-p cgb-test`、port 8780 與 11436、資料在暫存資料夾 | 假的 TCP 與 HTTP 監聽(容器裡的 UI 與 Ollama 相容端點)→ G-07 |
| 跨端點驗收 | E1、E2、E3 的規格檔 | 瀏覽器畫面上的文字、按鈕與狀態區塊;區網程式送到 Ollama 相容 port 的請求 | E2E(真的瀏覽器、真的後端;轉接層用替身)、📏 量測(真的 Colab) | Playwright(Python)+ pytest-playwright;區網程式用 httpx 或桌機已有的 `ollama` 指令 | 測試行程內的 uvicorn:UI 127.0.0.1:8781、Ollama 相容端點 127.0.0.1:11437,替身由測試直接操控(Q99 先採用);實跑改用 `docker compose -p cgb-test`、UI 8780、Ollama 相容端點 11436 | `FakeColabControl`、`FakeTunnel`、`FakeRemoteOllama`(Colab 執行環境、通道與遠端 Ollama)→ US1-AJ-17、US1-AJ-18、US1-AJ-19、US1-AJ-20、US1-AJ-21、US1-AJ-22、US4-AJ-09<br>`FakeModelLibrary`(官方模型庫)→ US3-AJ-12<br>`FakeGoogleOAuth`(Google OAuth)→ US1-OA-06 |

### 受測操作

每個測試案例的「受測操作」欄照這張表某一列的寫法填;`tasks.md` 的 ⚙ 照「規格錨點」欄寫。

| 端點 | 受測操作 | 規格錨點 | 寫法 |
|---|---|---|---|
| E2 後端 UI API | 登入:查狀態、取得授權連結、送出授權碼 | `contracts/ui.openapi.yaml` § `paths./auth.get`、`paths./auth/authorizations.post`、`paths./auth/authorizations/{flowId}/code.post`、`components.schemas.AuthStatus`、`components.schemas.AuthorizationFlow`、`components.schemas.Error`;`contracts/ui-events.asyncapi.yaml` § `operations.sendAuthUpdated` | `/api/auth` › <動作> |
| E2 後端 UI API | 工作階段:查詢、開啟、結束、變更類型重開 | `contracts/ui.openapi.yaml` § `paths./session.get`、`paths./session.post`、`paths./session.delete`、`paths./session/restart.post`、`components.schemas.Session`、`components.schemas.SessionState`、`components.schemas.OpeningStep`、`components.schemas.EndReason`、`components.schemas.ReasonCode`、`components.schemas.ReleaseWarning`、`components.schemas.UnmanagedRuntime`、`components.schemas.Reconnect`、`components.schemas.IdleCountdown`、`components.schemas.Error`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSessionUpdated` | `/api/session` › <動作> |
| E2 後端 UI API | 紀錄:列出、查一筆 | `contracts/ui.openapi.yaml` § `paths./sessions.get`、`paths./sessions/{name}.get`、`components.schemas.SessionHistoryPage`、`components.schemas.SessionRecord`、`components.schemas.SessionRecordDetail`、`components.schemas.StateTransition` | `/api/sessions` › <動作> |
| E2 後端 UI API | 模型目錄:列出、預先載入 | `contracts/ui.openapi.yaml` § `paths./models.get`、`paths./models/preload.post`、`components.schemas.ModelCatalog`、`components.schemas.CatalogModel`、`components.schemas.PreloadState`;`contracts/ui-events.asyncapi.yaml` § `operations.sendModelsUpdated` | `/api/models` › <動作> |
| E2 後端 UI API | 模型庫:搜尋、列版本 | `contracts/ui.openapi.yaml` § `paths./library/search.get`、`paths./library/models/{name}/tags.get`、`components.schemas.LibrarySearchPage`、`components.schemas.LibraryTagList` | `/api/library` › <動作> |
| E2 後端 UI API | 精選清單:列出、新增、修改、移除 | `contracts/ui.openapi.yaml` § `paths./curated.get`、`paths./curated.post`、`paths./curated/{id}.put`、`paths./curated/{id}.delete`、`components.schemas.CuratedList` | `/api/curated` › <動作> |
| E2 後端 UI API | 下載佇列:試算、列出、加入、清除已完成、移除、重新排隊 | `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`paths./downloads.get`、`paths./downloads.post`、`paths./downloads/clear-completed.post`、`paths./downloads/{id}.delete`、`paths./downloads/{id}/retry.post`、`components.schemas.DownloadEstimate`、`components.schemas.DownloadJob`、`components.schemas.DownloadQueue`;`contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot`、`operations.sendDownloadUpdated`、`operations.sendDownloadRemoved` | `/api/downloads` › <動作> |
| E2 後端 UI API | SSE 訂閱 | `contracts/ui.openapi.yaml` § `paths./events.get`;`contracts/ui-events.asyncapi.yaml` § `channels.uiEvents` | `/api/events` › 訂閱 |
| E2 後端 UI API | 用量:查詢 | `contracts/ui.openapi.yaml` § `paths./usage.get`、`components.schemas.Usage`;`contracts/ui-events.asyncapi.yaml` § `operations.sendUsageUpdated` | `/api/usage` › <動作> |
| E2 後端 UI API | 設定:查詢、修改 | `contracts/ui.openapi.yaml` § `paths./settings.get`、`paths./settings.put`、`components.schemas.Settings`、`components.schemas.IdleCountdown`;`contracts/ui-events.asyncapi.yaml` § `operations.sendSettingsUpdated` | `/api/settings` › <動作> |
| E2 後端 UI API | 後端行程本身:以同一個 SQLite 檔與同一份轉接層替身狀態重建 app | — | 後端行程 › 重新啟動 |
| E2 後端 UI API | 排程:健康檢查到期、重連每一輪、定時讀用量、閒置到期(注入的時鐘推進) | `contracts/tunnel.openapi.yaml` § `paths./tunnels/{sessionName}/health.get`、`paths./tunnels/{sessionName}/reconnect.post`;`contracts/colab-cli.openapi.yaml` § `paths./usage.get`;`contracts/ui.openapi.yaml` § `components.schemas.IdleCountdown` | 排程 › <到期的事> |
| E3 Ollama 相容端點 | 推論與查詢(白名單):`/`、`/api/version`、`/api/tags`、`/api/ps`、`/api/show`、`/api/generate`、`/api/chat`、`/api/embed`、`/api/embeddings` | `contracts/ollama-compat.openapi.yaml` § `paths./.get`、`paths./.head`、`paths./api/version.get`、`paths./api/tags.get`、`paths./api/ps.get`、`paths./api/show.post`、`paths./api/generate.post`、`paths./api/chat.post`、`paths./api/embed.post`、`paths./api/embeddings.post`、`components.schemas.OllamaError`、`components.schemas.Error` | Ollama 端點 › `<方法> <路徑>` |
| E3 Ollama 相容端點 | 管理操作(阻擋) | `contracts/ollama-compat.openapi.yaml` § `paths./api/pull.post`、`paths./api/push.post`、`paths./api/create.post`、`paths./api/copy.post`、`paths./api/delete.delete`、`paths./api/blobs/{digest}.head`、`paths./api/blobs/{digest}.post` | Ollama 端點 › 管理操作 |
| E3 Ollama 相容端點 | 白名單外的路徑 | `contracts/ollama-compat.openapi.yaml` § `components.schemas.Error` | Ollama 端點 › 白名單外 |
| E4 資料庫 | 資料表與約束 | `contracts/store.dbml` § `Table sessions`、`Table session_transitions`、`Table download_jobs`、`Table curated_models`、`Table settings`、`Table usage_snapshots` | SQLite › <SQL 動作> |
| E5 Colab CLI | `ColabControl`:`get_cli_version`、`list_sessions`、`create_session`、`start_ollama`、`probe_resources`、`stop_session`、`get_usage` | `contracts/colab-cli.openapi.yaml` § `paths./version.get`、`paths./sessions.get`、`paths./new.post`、`paths./exec/start-ollama.post`、`paths./exec/probe-resources.post`、`paths./stop.post`、`paths./usage.get`、`components.schemas.StartOllamaScriptResult`、`components.schemas.ProbeScriptResult`、`components.schemas.Error`(各操作 `default` 回應的 `x-failure-rules` 與 `x-timeout`) | `ColabControl` › `<方法>` |
| E5 Colab CLI | 真的 `colab` 0.7.5 子指令(只在實跑) | `contracts/colab-cli.openapi.yaml` § `paths./version.get`、`paths./sessions.get`、`paths./new.post`、`paths./exec/start-ollama.post`、`paths./exec/probe-resources.post`、`paths./stop.post`、`paths./usage.get` | `colab` 指令 › <子指令> |
| E6 SSH 通道 | `Tunnel`:`ensure_key`、`open_tunnel`、`check_health`、`close_tunnel`、`cleanup_residual` | `contracts/tunnel.openapi.yaml` § `paths./key.post`、`paths./tunnels.post`、`paths./tunnels/{sessionName}/health.get`、`paths./tunnels/{sessionName}.delete`、`components.schemas.Error` | `Tunnel` › `<方法>` |
| E7 遠端 Ollama | `RemoteOllama`:`get_version`、`list_local_models`、`list_loaded_models`、`pull_model`、`show_model`、`generate`、`chat`、`embed`、`preload` | `contracts/remote-ollama.openapi.yaml` § `paths./api/version.get`、`paths./api/tags.get`、`paths./api/ps.get`、`paths./api/pull.post`、`paths./api/show.post`、`paths./api/generate.post`、`paths./api/chat.post`、`paths./api/embed.post`、`components.schemas.PullProgress`、`components.schemas.Error` | `RemoteOllama` › `<方法>` |
| E8 Ollama 官方模型庫 | `ModelLibrary`:`search_library`、`list_model_tags`、`get_manifest` | `contracts/model-library.openapi.yaml` § `paths./search.get`、`paths./library/{name}/tags.get`、`paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.Error` | `ModelLibrary` › `<方法>` |
| E9 Google OAuth | `GoogleOAuth`:`build_authorization_url`、`request_token` | `contracts/google-oauth.openapi.yaml` § `paths./o/oauth2/auth.get`、`paths./token.post`、`components.schemas.TokenResponse`、`components.schemas.OAuthError`、`components.schemas.Error` | `GoogleOAuth` › `<方法>` |
| E10 檔案系統 | `cgb-prepare-data`:啟動前整理、`--check` | `deploy/compose.yaml` § `x-data-layout`;`deploy/prepare-data.sh` | `cgb-prepare-data` › <動作> |
| E10 檔案系統 | repo 追蹤的檔案與排除清單(機密檔不得進版本控制) | `deploy/Dockerfile.dockerignore`;`deploy/compose.yaml` § `x-data-layout` | repo › <檢查> |
| E11 部署與網路 | compose 服務:起、重建、健康檢查 | `deploy/compose.yaml` § `services.cgb`、`x-ports` | compose › <動作> |
| E11 部署與網路 | 健康檢查腳本 | `deploy/healthcheck.py` | `cgb-healthcheck` › 執行 |
| E11 部署與網路 | 區網裝置與外網的連線 | `deploy/compose.yaml` § `x-ports` | 區網裝置 › <動作> |
| 跨端點驗收 | 首頁(工作階段面板):「開啟」、類型選擇、「結束工作階段」、「變更類型」、「停止開啟」與各狀態區塊 | `prototype/index.html` § `#open`、`#stop`、`#switch`、`#cancel-open`、`#s-steps`、`#r-type`、`#r-name`、`#e-reason`、`#f-reason`、`[data-state="starting"]`、`[data-state="ready"]`、`[data-state="stopping"]`、`[data-state="ended"]`、`[data-state="failed"]`、`[data-state="lost"]`、`[data-state="lost-timeout"]`、`[data-state="reconnecting"]`、`[data-state="resuming"]`、`[data-state="release-failed"]`、`[data-state="already-open"]`、`[data-state="needs-login"]`、`[data-state="confirm-stop"]`、`[data-state="confirm-switch"]`、`[data-state="switching"]`、`[data-state="foreign"]`、`[data-state="low-balance"]`、`[data-state="ended-idle"]`、`[data-state="lost-zero"]`、`#r-countdown` | 首頁 › 「<按鈕>」 |
| 跨端點驗收 | 用量頁:用量顯示與設定表單 | `prototype/usage.html` § `[data-state="loading"]`、`[data-state="normal"]`、`[data-state="low"]`、`[data-state="stale"]`、`[data-state="unknown"]`、`#n-balance`、`#n-rate`、`#n-hours`、`#n-read`、`#l-warn`、`#settings-form`、`#idle`、`#warn`、`#saved` | 用量頁 › 「<按鈕>」或列表 |
| 跨端點驗收 | 登入頁:「取得授權連結」、授權碼輸入框與送出 | `prototype/login.html` § `[data-action="get-link"]`、`#auth-link`、`#code-form`、`#code`、`#auth-chip`、`[data-state="link"]`、`[data-state="failed"]`、`[data-state="link-expired"]`、`[data-state="signed-in"]` | 登入頁 › 「<按鈕>」 |
| 跨端點驗收 | 紀錄頁 | `prototype/history.html` § `#rows`、`[data-state="normal"]`、`[data-state="empty"]` | 紀錄頁 › 列表 |
| 跨端點驗收 | 模型頁:模型目錄、「預先載入」、下載佇列的取消與重新排隊 | `prototype/models.html` § `#catalog`、`[data-preload]`、`#queue`、`[data-cancel]`、`[data-retry]`、`[data-progress-text]`、`[data-state="preload-warn"]`、`#pw-go`、`[data-state="no-session"]` | 模型頁 › 「<按鈕>」 |
| 跨端點驗收 | 下載模型頁:搜尋、精選清單、輸入名稱、勾選、確認加入 | `prototype/library.html` § `#search-form`、`#results`、`#more`、`#curated`、`#name-form`、`#tray`、`#add`、`#confirm-table`、`#confirm-disk`、`#confirm-eta`、`#confirm-go`、`[data-state="no-space"]`、`[data-state="not-found"]`、`[data-state="cloud-only"]`、`[data-state="no-session"]` | 下載模型頁 › 「<按鈕>」 |
| 跨端點驗收 | 區網程式:對 Ollama 相容 port 送請求(httpx 或 `ollama` 指令) | `contracts/ollama-compat.openapi.yaml` § `paths./api/generate.post`、`paths./api/tags.get`、`paths./api/version.get` | 區網程式 › <請求> |
| 跨端點驗收 | 實跑時對真元件的外部操作:殺掉 ssh 行程、另開終端機 `colab stop`、`docker compose restart` | — | 實跑操作 › <動作> |

### 接縫的取捨

`/tdd` 紅燈步驟直接引用這張表,不再另外和使用者確認接縫;遇到這張表沒有的接縫才停下來問。

| 接縫(公開介面) | 抓得到 | 抓不到 |
|---|---|---|
| HTTP `/api/*` 與 SSE `/api/events`(轉接層用替身) | 狀態轉換與結束原因、只能有一個工作階段、開啟失敗與結束時的釋放與警告、重連節奏與時限、後端重啟接回、變更類型時的重新下載、下載佇列的順序與空間檢查、錯誤代碼 | 真的 CLI、ssh、Ollama、ollama.com、Google 的輸出格式和替身不同(由各轉接層的 📏 實跑案例補);真實時間下的門檻 SC-001~SC-008(由跨端點驗收的 📏 案例補);畫面有沒有顯示(由跨端點驗收補) |
| Ollama 相容 port 的 HTTP(遠端是假伺服器) | 白名單與阻擋、沒有工作階段時 1 秒內回 503、串流逐段傳回與中途補的錯誤行、換類型過程中的回應 | 真的遠端 Ollama 的 CORS、載入行為與錯誤文字(由 US2-RO-03 補);轉送延遲(由 US2-AJ-02 補) |
| `sqlite3` 直接下 SQL | 唯一性約束讓第二個開啟中的工作階段、重複排隊的模型寫不進去;WAL 與重開連線後資料仍在 | repos 有沒有用對約束(由 E2 的案例補) |
| `ColabControl`(假的 `colab` 執行檔) | 命令列逐字、stdin 接 `/dev/null`、不信 exit code、回讀確認、`Connection was lost` 只重試一次、錯誤訊息遮蔽網址 | CLI 0.7.5 真正的輸出字樣與時間(由 US1-CLI-21 補) |
| `Tunnel`(假的 `ssh` 執行檔與真的 `ssh-keygen`) | 命令列逐字、`Creating runtime` 立即關閉、stderr 對應代碼、就緒期限、process group 與殭屍回收 | OpenSSH 與 `colab ssh` 真正的錯誤字樣、半開連線多久才放掉(Q69,由 US1-TUN-10 補) |
| `RemoteOllama`、`ModelLibrary`、`GoogleOAuth`(假的 HTTP 對方) | 回應解析、錯誤分類、逾時、串流中斷 | 對方真正的格式與改版(由 US2-RO-03、US3-LIB-05、US1-OA-06 補) |
| 瀏覽器畫面(接真的後端、轉接層用替身) | 每個狀態都看得到對應的文字與按鈕、確認對話框、引導登入、紀錄列表、下載進度與錯誤提示、用量與過期標示、閒置倒數 | 真的 Colab 的時間門檻(由 📏 實跑案例補) |

### 實跑案例的共同護欄

📏 實跑案例的「副作用與護欄」欄以 P1~P9 引用這裡,再寫各自多出的做法(plan.md Q108 已決定照護欄執行)。US1-OA-06 與 G-01 需要本人在場,延後到使用者回來另跑,不在這一批(Q101、Q108)。

- **P1 名稱**:只用前綴 `cgb-test-` 的工作階段。本系統以注入的名稱前綴 `cgb-test-` 產生名稱(Q95 先採用);轉接層層級的實跑名稱寫死 `cgb-test-<YYYYmmddHHMM>-adapter`。任何 `colab stop` 只帶 `cgb-test-` 開頭的名稱,不對 `[?]` 或其他名稱下指令。
- **P2 預算**:整批上限 2 compute units、總時間 60 分鐘。開始前與結束後各執行一次 `colab usage`(`HOME` 指到暫存目錄)記下三行;每個案例開始前看已用時間與餘額,超過 60 分鐘或餘額比開始時少 1.8 以上,就跳過剩下的案例直接做 P3,沒跑到的案例在完成報告列為未驗證。GPU 只用 `--gpu T4`(加不加高 RAM),不用其他類型(CLI 會把認不得的名稱當成 A100)。
- **P3 收尾**(不論成敗,包含中途中止):`colab sessions` 確認沒有 `cgb-test-` 開頭的行;有就逐一 `colab stop -s <名稱>` 再回讀,仍在就停下來請使用者到 Colab 網頁手動結束;`docker compose -p cgb-test down`;確認主機上沒有命令列含 `ProxyCommand=colab ssh --proxy-mode -s cgb-test-` 的行程。
- **P4 Google Drive**:不執行 `colab drivemount`,遠端腳本不 import `google.colab.drive`,不開任何 Drive 授權網址。
- **P5 共用服務**:只在桌機執行;不碰 Tower、Pi、NPM、AdGuard,不改 DNS 與路由器;外網驗證用手機行動網路或 check-host.net,不在區網內連公網 IP(NAT hairpin 的結果不可信)。
- **P6 port 與資料夾**:本系統的 Ollama 相容端點用 11436、UI 用 8780;桌機的 11434 是使用者自己的 Ollama,不送任何請求。資料夾用 `mktemp -d` 的 `<暫存目錄>`,資料放 `<暫存目錄>/data`(`.env` 的 `CGB_HOST_DATA`),不掛正式的 `/data` 或 named volume `cgb-data`;compose 一律 `docker compose -p cgb-test --env-file <暫存目錄>/.env`。在主機上直接跑的實跑,子行程帶 `HOME=<暫存目錄>/home`,其 `.config/colab-cli` 是指向 `<暫存目錄>/data/colab-cli` 的符號連結,不讀寫桌機的 `~/.config/colab-cli/`。
- **P7 模型**:只用 `qwen2.5:0.5b`(約 0.4GB)與 `qwen2.5:7b`(約 4.7GB);要「不存在的模型」時只用 `qwen2.5:cgb-test-nonexistent`(registry 沒有,pull 會失敗、不會下載)。
- **P8 機密**:執行任何 `colab` 指令之前,先以 `CGB_DATA_DIR=<暫存目錄>/data` 跑一次 `cgb-prepare-data`,讓 `colab.log` 指到 `/dev/null`(Q59);token、proxy token、endpoint 一律不印出,比對只印長度與 sha256 前 8 碼;錄下的原始輸出先把網址換成 `<網址>`(遮蔽先用一個已知的假 endpoint 驗過),只存在 `<暫存目錄>`,P3 之後刪除。
- **P9 授權與順序**:授權照 Q101(b):把桌機既有的 `~/.config/colab-cli/token.json` 複製到 `<暫存目錄>/data/colab-cli/token.json`(權限 0600),只比對兩邊的長度與 sha256 前 8 碼,不印內容、不複製 `sessions.json`;複製後先以 `HOME=<暫存目錄>/home colab usage` 確認授權有效(沒過就停下,不改用其他授權)。順序:主機階段(複製授權 → US3-LIB-05 → 同一台 `cgb-test-…-adapter` 依序 US1-CLI-21、US2-RO-03、US1-TUN-10,最後 stop)→ 容器階段(US2-AJ-03 → US1-AJ-17 → US2-AJ-02 → US3-AJ-12 與 US3-AJ-13 → US2-AJ-04 → US1-AJ-18 → US1-AJ-19 → US1-AJ-20 → US1-AJ-21 → US4-AJ-09 → US1-AJ-22)→ P3 → G-07 → G-05。主機階段先跑,是因為容器以 root 寫入的檔案主機使用者讀不到。估計 Colab 占用約 47 分鐘、約 0.93 compute units(主機 11 分鐘 0.21、容器第一台 18 分鐘 0.36、T4 高 RAM 7 分鐘 0.14、US4-AJ-09 6 分鐘 0.12、US1-AJ-22 5 分鐘 0.1),加上不開執行環境的步驟約 12 分鐘,共約 59 分鐘;超過 60 分鐘時照 P2 從 US1-AJ-19 起往後跳過。

## 2. 使用者故事 1 - 一鍵開啟與結束 GPU 工作階段(P1)

**本故事的需求**:FR-001~FR-010;NFR-001、NFR-002;邊界情況:連按兩次「開啟」、開啟到一半按「結束」、Colab 帳號授權過期、後端重啟時發現不是本系統開啟的執行環境
**本故事涵蓋的全域 NFR**:FR-028、NFR-010(彙整見第 6 節)

### 2.1 E2 後端 UI API(FastAPI REST 與 SSE)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-API-01 | `/api/session` › 開啟 → `/api/session` › 查詢 | 沒有工作階段;`create_session`、`start_ollama`、`open_tunnel` 三個替身各自等測試放行 | 送 `POST /api/session {runtimeType:{gpu:"T4",highMem:false}}`,再依序放行三個步驟 | 則1:放行任何步驟之前 `POST` 就回 202,`state` 為 `opening`<br>則2:`open_tunnel` 放行之前,`GET /api/session` 的 `state` 都不是 `ready`<br>則3:全部放行後 `GET /api/session` 的 `state` 為 `ready`,`runtimeType` 為 `{gpu:"T4",highMem:false}`<br>則4:`FakeColabControl.create_session` 被呼叫 1 次,帶 `gpu=T4`、`high_mem=false`,名稱符合 `^cgb-test-[a-z0-9-]+$` | 等開啟流程跑完才回應;或 `create_session` 成功就標成就緒,沒等通道與模型服務可回應 | FR-001、FR-003 |
| US1-API-02 | `/api/session` › 開啟 | 沒有工作階段;`create_session` 回 `highMemIgnored: true` | 送 `POST /api/session {runtimeType:{gpu:"L4",highMem:true}}` | 則1:`FakeColabControl.create_session` 帶 `gpu=L4`、`high_mem=true`<br>則2:就緒後 `GET /api/session` 的 `runtimeType` 為 `{gpu:"L4",highMem:true}` | 開啟時忽略使用者選的類型,一律用 T4;或 CLI 回報忽略高 RAM 時把紀錄改成 `highMem:false` | FR-009 |
| US1-API-03 | `/api/session` › 開啟 | 沒有工作階段 | 分別送 `gpu` 為 `"t4"`、`"TPU"`、`"V100"`,以及 `highMem` 為 `"yes"` 的開啟 | 則1:四次都回 400,`code` 為 `INVALID_RUNTIME_TYPE` 或 `INVALID_REQUEST_BODY`<br>則2:`FakeColabControl.create_session` 一次都沒被呼叫 | 把使用者字串直接放進 `--gpu`(CLI 會把認不得的名稱當成 A100,扣更多點數);或不分大小寫接受 `t4` | FR-009 |
| US1-API-04 | `/api/session` › 開啟 | 沒有工作階段;`create_session` 等測試放行 | 同時送兩個 `POST /api/session`(`asyncio.gather`) | 則1:一個回 202,另一個回 409,`code` 為 `SESSION_ALREADY_ACTIVE`<br>則2:`FakeColabControl.create_session` 只被呼叫 1 次 | 先查「有沒有工作階段」再寫入,兩個請求都通過檢查而各開一台 | FR-006、邊界情況 |
| US1-API-05 | `/api/session` › 開啟 | 情況 A:工作階段 `ready`;情況 B:工作階段 `ending`(`stop_session` 等測試放行) | 各送一次 `POST /api/session` | 則1:情況 A 回 409,`code` 為 `SESSION_ALREADY_ACTIVE`,`message` 含「已有工作階段」<br>則2:情況 B 回 409,`code` 為 `SESSION_ENDING`<br>則3:兩種情況 `create_session` 都沒有再被呼叫 | 只擋 `opening`,`ready` 時照樣再開;或 `ending` 不算占位就讓新的開起來,和正在結束的那台重疊 | FR-006 |
| US1-API-06 | `/api/session` › 開啟 | `FakeColabControl.get_usage` 回 `AUTH_REQUIRED` | 送 `POST /api/session` | 則1:回 409,`code` 為 `AUTH_REQUIRED`<br>則2:`create_session` 沒被呼叫<br>則3:`GET /api/auth` 的 `state` 為 `logged_out` | 不先確認授權就開,等 `colab new` 卡在等授權碼或失敗才回報 | FR-008 |
| US1-API-07 | `/api/session` › 結束 | 工作階段 `ready`;`stop_session` 等測試放行 | 送 `DELETE /api/session`,再放行 `stop_session` | 則1:`DELETE` 回 202,`state` 為 `ending`<br>則2:`FakeTunnel.close_tunnel` 在 `FakeColabControl.stop_session` 之前被呼叫<br>則3:`stop_session` 回成功後 `state` 為 `ended`,`endReason` 為 `USER_ENDED`,`endedAt` 不為 null<br>則4:`releaseWarning` 為 null | 只關通道沒有呼叫 `stop_session`(執行環境繼續扣點);或先 stop 再關通道,串流斷掉時被當成非預期斷線 | FR-002、FR-003 |
| US1-API-08 | `/api/session` › 結束 | 工作階段 `ready`;`stop_session` 回 `COLAB_STOP_UNCONFIRMED` | 送 `DELETE /api/session`;等狀態穩定後再送一次 `DELETE /api/session`,這次 `stop_session` 回成功 | 則1:第一次之後 `releaseWarning.message` 不為 null,`releaseWarning.reasonCode` 為 `COLAB_STOP_UNCONFIRMED`<br>則2:第二次 `DELETE` 回 202<br>則3:`stop_session` 總共被呼叫 2 次<br>則4:第二次之後 `releaseWarning` 為 null | 釋放失敗時照樣標成乾淨的已結束、沒有警告;或有警告時再按結束回 409,使用者沒辦法再試一次 | FR-007 |
| US1-API-09 | `/api/session` › 結束 | 情況 A:從沒開過;情況 B:上一個已 `ended` 且沒有釋放警告 | 各送一次 `DELETE /api/session` | 則1:兩種情況都回 409,`code` 為 `NO_ACTIVE_SESSION`<br>則2:`stop_session` 沒被呼叫 | 沒有工作階段時仍呼叫 `colab stop`,或回 202 讓 UI 顯示「結束中」 | FR-002 |
| US1-API-10 | `/api/session` › 開啟 | `create_session` 回 `COLAB_ALLOCATION_REFUSED` | 送 `POST /api/session` | 則1:`state` 為 `open_failed`,`endReason` 為 `OPEN_FAILED`,`reasonCode` 為 `COLAB_ALLOCATION_REFUSED`<br>則2:`message` 不為空<br>則3:失敗之後 `FakeColabControl.list_sessions` 至少被呼叫 1 次(確認沒有遺留) | 開啟失敗時沒附原因;或沒有回讀確認 Colab 帳號下有沒有遺留 | FR-003、FR-007 |
| US1-API-11 | `/api/session` › 開啟 | `create_session` 成功;`start_ollama` 回 `COLAB_REMOTE_ERROR` | 送 `POST /api/session` | 則1:`state` 為 `open_failed`,`reasonCode` 為 `COLAB_REMOTE_ERROR`<br>則2:`FakeColabControl.stop_session` 以 `cgb-test-0001` 被呼叫 1 次<br>則3:`releaseWarning` 為 null | `start_ollama` 失敗就直接標失敗,沒有釋放已配置好的執行環境 | FR-007 |
| US1-API-12 | `/api/session` › 開啟 | 開啟總時限注入 3 秒;`start_ollama` 一直不放行 | 送 `POST /api/session` | 則1:受理後 3 到 3.5 秒之間 `state` 變成 `open_failed`,`reasonCode` 為 `COLAB_TIMEOUT`<br>則2:`stop_session` 以 `cgb-test-0001` 被呼叫 1 次 | 只有各步驟自己的時限(`start_ollama` 300 秒),沒有開啟流程的總時限;或逾時後沒有釋放 | FR-007、SC-001 |
| US1-API-13 | `/api/session` › 開啟 → `/api/session` › 結束 | `create_session` 等測試放行(`step` 為 `allocating`) | 送 `DELETE /api/session`,之後才放行 `create_session` | 則1:`DELETE` 回 202,`state` 為 `ending`<br>則2:放行之前 `create_session` 的子行程沒有被取消(替身記錄沒有收到取消)<br>則3:放行之後 `stop_session` 以 `cgb-test-0001` 被呼叫<br>則4:最後 `state` 為 `ended`,`endReason` 為 `USER_ENDED`<br>則5:`start_ollama` 沒被呼叫 | 中途取消 `colab new`(伺服器已配置、本機卻沒記下名稱,留下 `[?]` 的遺留);或按結束後仍繼續做後面的步驟 | 邊界情況、FR-007 |
| US1-API-14 | `/api/session` › 開啟 | `list_sessions` 開啟前回 `unnamed: []`;`create_session` 回 `COLAB_TIMEOUT`;之後的 `list_sessions` 回 `unnamed: [{hardware:"T4"}]` | 送 `POST /api/session` | 則1:`state` 為 `open_failed`,`reasonCode` 為 `COLAB_TIMEOUT`<br>則2:`releaseWarning.message` 不為 null<br>則3:`stop_session` 沒有對 `[?]` 那台被呼叫 | 沒比對開啟前後的 `unnamed` 清單,把逾時當成乾淨的失敗;或試圖以名稱結束 `[?]` 的那台 | FR-007 |
| US1-API-15 | `/api/session` › 開啟 | `create_session`、`start_ollama` 成功;`create_session` 之後的 `list_sessions` 沒有列出 `cgb-test-0001` | 送 `POST /api/session` | 則1:`FakeTunnel.open_tunnel` 一次都沒被呼叫<br>則2:`state` 為 `open_failed`,`reasonCode` 為 `COLAB_NOT_FOUND` 或 `TUNNEL_NOT_FOUND` | 不先確認名稱在列就建立通道(`colab ssh --proxy-mode` 找不到名稱會自己開一台新的,Q64) | FR-001、FR-006 |
| US1-API-16 | `/api/session` › 開啟 | `open_tunnel` 回 `TUNNEL_NOT_FOUND`(代表 `colab ssh` 意外開出新的執行環境並已被關閉) | 送 `POST /api/session` | 則1:`FakeColabControl.stop_session` 以 `cgb-test-0001` 被呼叫<br>則2:`stop_session` 之後 `list_sessions` 被呼叫<br>則3:`state` 為 `open_failed`,`reasonCode` 為 `TUNNEL_NOT_FOUND` | 收到 `TUNNEL_NOT_FOUND` 只標失敗,沒有結束意外開出的那台(扣點、違反只有一個工作階段) | FR-006、FR-007 |
| US1-API-17 | 排程 › 健康檢查 | 工作階段 `ready`;健康檢查間隔 0.2 秒 | `FakeTunnel.check_health` 開始回 `TUNNEL_UNREACHABLE`,同時 `list_sessions` 不再列出 `cgb-test-0001` | 則1:替身開始失敗後 1 秒內 `state` 為 `lost`<br>則2:`endReason` 為 `RECLAIMED_BY_COLAB`<br>則3:`message` 含「重新開啟」<br>則4:失敗之後 `open_tunnel` 沒有再被呼叫 | 健康檢查失敗後只是一直重連到時限才失聯(沒有查 `colab sessions`);或判成 `RECONNECT_TIMEOUT` | FR-003、FR-004 |
| US1-API-18 | 排程 › 健康檢查 → 排程 › 重連 | 工作階段 `ready`;`list_loaded_models` 有 `qwen2.5:0.5b` | `check_health` 回失敗 1 次;重連第 1 輪 `open_tunnel` 回 `TUNNEL_ALREADY_CONNECTED`、第 2 輪成功 | 則1:SSE `session.updated` 依序出現 `reconnecting`、`ready`<br>則2:回到 `ready` 後 `name` 仍是 `cgb-test-0001`<br>則3:`create_session` 總共只被呼叫 1 次<br>則4:`reconnecting` 期間 `reconnect.deadline` 減 `reconnect.startedAt` 等於注入的重連時限 2 秒 | 重連時另開新的執行環境;或第一輪失敗就標失聯 | FR-004 |
| US1-API-19 | 排程 › 重連 | 工作階段 `reconnecting`,重連節奏注入「立即、0.05、0.1、0.2,之後每 0.3 秒」,時限 2 秒;`open_tunnel` 一直失敗 | 讓重連跑到時限 | 則1:每一輪依序呼叫 `close_tunnel`、`list_sessions`、`open_tunnel`<br>則2:第 1 到 5 輪開始時間與第 1 輪的差依序為 0、0.05、0.15、0.35、0.65 秒(各容許 ±0.03 秒)<br>則3:開始時間超過時限的那一輪沒有開始 | 每輪沒先 `close_tunnel`,新連線撞上 `TUNNEL_ALREADY_CONNECTED`;或固定間隔重試、或無間隔狂試 | FR-004 |
| US1-API-20 | 排程 › 重連 | 工作階段 `reconnecting`;`list_sessions` 回 `COLAB_UNREACHABLE`;`open_tunnel` 第 2 輪成功 | 讓重連進行 | 則1:`state` 回到 `ready`<br>則2:`endReason` 一直沒有出現 `RECLAIMED_BY_COLAB` | `colab sessions` 本身失敗(例如家裡網路斷了)就當成執行環境不在,誤判被收回 | FR-004 |
| US1-API-21 | 排程 › 重連 | 工作階段 `reconnecting`,時限 2 秒;`open_tunnel` 一直回 `TUNNEL_UNREACHABLE` | 讓重連跑到時限 | 則1:進入重連後 1.8 到 2.5 秒之間 `state` 變成 `lost`<br>則2:`endReason` 為 `RECONNECT_TIMEOUT`,`reasonCode` 為 `TUNNEL_UNREACHABLE`<br>則3:`stop_session` 以 `cgb-test-0001` 被呼叫 | 時限到只改狀態,沒有釋放執行環境;或 `reasonCode` 填 `TUNNEL_TIMEOUT`,看不出接不回的原因 | FR-004 |
| US1-API-22 | 排程 › 重連 | 同 US1-API-21,但 `stop_session` 回 `COLAB_STOP_UNCONFIRMED` | 讓重連跑到時限 | 則1:`state` 為 `lost`<br>則2:`releaseWarning.message` 不為 null | 重連逾時後釋放失敗卻沒有警告 | FR-004、FR-007 |
| US1-API-23 | 後端行程 › 重新啟動 | 工作階段 `ready`(`cgb-test-0001` 在 SQLite);`list_sessions` 列出 `[cgb-test-0001]` | 關掉 app,以同一個 SQLite 檔與同一份替身狀態建立新的 app | 則1:新的 app 起來後 `GET /api/session` 的 `state` 為 `ready`,`name` 為 `cgb-test-0001`<br>則2:新的 app 沒有呼叫 `create_session`<br>則3:新的 app 先呼叫 `cleanup_residual`,再呼叫 `open_tunnel` 1 次 | 重啟後把工作階段當成不存在、回 `none` 或另開一台;或沒清殘留的 ssh 就建立通道 | FR-005 |
| US1-API-24 | 後端行程 › 重新啟動 | 工作階段 `ready`;`list_sessions` 沒有列出 `cgb-test-0001` | 重建 app | 則1:`state` 為 `lost`,`endReason` 為 `RECLAIMED_BY_COLAB`<br>則2:`open_tunnel` 沒被呼叫 | 重啟後照資料庫標成就緒,沒有確認執行環境還在 | FR-005 |
| US1-API-25 | 後端行程 › 重新啟動 | 沒有未結束的工作階段;`list_sessions` 回一台 `[?]`、硬體 T4 | 重建 app,送 `GET /api/session` | 則1:`unmanagedRuntimes` 有 1 筆,`hardware` 為 `T4`<br>則2:`stop_session` 沒被呼叫<br>則3:`open_tunnel` 沒被呼叫 | 把不是本系統開的執行環境接手或關掉 | 邊界情況 |
| US1-API-26 | 後端行程 › 重新啟動 | SQLite 有一筆 `cgb-test-0001`(`ready`)與一筆已 `ended` 的 `cgb-test-0002`;`list_sessions` 列出 `[cgb-test-0001]`、`[cgb-test-0002]`、`[cgb-other-9]` | 重建 app | 則1:`stop_session` 以 `cgb-test-0002` 被呼叫<br>則2:`stop_session` 沒有以 `cgb-test-0001` 或 `cgb-other-9` 被呼叫<br>則3:`GET /api/session` 的 `unmanagedRuntimes` 恰有 1 筆,`hardware` 與 `list_sessions` 回的 `[cgb-other-9]` 那台硬體相同、`detectedAt` 不為 null(資料庫不認得、CLI 記得的只警告不關,FR-007、Q122 先採用) | 只看 `cgb-` 前綴就結束(會關到別的實例開的執行環境,Q100);或資料庫裡已結束的那台還在卻不釋放;或資料庫不認得的那台沒有任何提示 | FR-007 |
| US1-API-27 | `/api/session` › 變更類型 | 工作階段 `ready`(T4);`list_loaded_models` 有 `qwen2.5:0.5b` | 送 `POST /api/session/restart {runtimeType:{gpu:"L4",highMem:false}}`,讓流程跑完 | 則1:回 202,新的工作階段 `state` 為 `opening`、`step` 為 `ending_previous`<br>則2:`GET /api/sessions` 裡 `cgb-test-0001` 的 `endReason` 為 `RUNTIME_TYPE_CHANGED`<br>則3:`stop_session(cgb-test-0001)` 在 `create_session(gpu=L4)` 之前被呼叫<br>則4:`GET /api/downloads` 有一筆 `qwen2.5:0.5b`,`origin` 為 `restore`、`preloadOnComplete` 為 true<br>則5:新工作階段就緒後 `FakeRemoteOllama` 依序收到 `pull qwen2.5:0.5b` 與 `keep_alive:-1` 的 `generate` | 先開新的再關舊的(同時兩台);或沒有記下原本載入的模型,換類型後模型沒了 | FR-010 |
| US1-API-28 | `/api/session` › 變更類型 | 工作階段 `ready`(T4,`qwen2.5:0.5b` 已載入);新類型的 `create_session` 回 `COLAB_ACCELERATOR_REJECTED` | 送 `POST /api/session/restart {runtimeType:{gpu:"L4",highMem:false}}` | 則1:新的工作階段 `state` 為 `open_failed`,`reasonCode` 為 `COLAB_ACCELERATOR_REJECTED`<br>則2:`stop_session(cgb-test-0001)` 回成功,`list_sessions` 不再列出它<br>則3:`GET /api/downloads` 的 `qwen2.5:0.5b`(`restore`)仍是 `queued` | 新類型開不起來時回頭沿用舊的,或舊的沒關;或把要重新下載的項目丟掉 | FR-010 |
| US1-API-29 | `/api/session` › 變更類型 | 沒有工作階段 | 送 `POST /api/session/restart {runtimeType:{gpu:"L4",highMem:false}}` | 則1:回 409,`code` 為 `NO_ACTIVE_SESSION`<br>則2:`create_session` 沒被呼叫 | 沒有工作階段時把 restart 當成開啟 | FR-010 |
| US1-API-30 | `/api/auth` › 取得授權連結 | 未登入 | 送兩次 `POST /api/auth/authorizations`,再以第一次的 `flowId` 送授權碼 | 則1:兩次都回 201,`authorizationUrl` 以 `https://accounts.google.com/o/oauth2/auth?` 開頭<br>則2:兩次的 `flowId` 不同<br>則3:用第一次的 `flowId` 送授權碼回 404,`code` 為 `AUTH_LINK_EXPIRED` | 多次取得連結都共用同一組 `state` 與 `code_verifier`;或舊流程沒失效 | FR-008 |
| US1-API-31 | `/api/auth` › 送出授權碼 | 已取得授權連結;`FakeGoogleOAuth.request_token` 回含 refresh token 的成功結果 | 以 `{code:"  4/cgb-test-code  "}` 送出 | 則1:回 200,`state` 為 `logged_in`<br>則2:`FakeGoogleOAuth` 收到的授權碼是 `4/cgb-test-code`(去掉前後空白)<br>則3:`<CGB_COLAB_CONFIG_DIR>/token.json` 存在,權限 0600<br>則4:SSE 收到 `auth.updated`,`state` 為 `logged_in` | 沒去空白,貼上時多帶的空白讓 Google 回 invalid_grant;或 token 檔用預設 umask 寫成 0644 | FR-008 |
| US1-API-32 | `/api/auth` › 送出授權碼 | 已取得授權連結;`request_token` 第一次回 `OAUTH_INVALID_GRANT`,第二次成功 | 送錯的授權碼,再以同一個 `flowId` 送正確的 | 則1:第一次回 400,`code` 為 `OAUTH_INVALID_GRANT`,`message` 不為空<br>則2:第二次回 200,`state` 為 `logged_in` | 換 token 失敗就讓流程代號失效,使用者只能重新取得連結;或錯誤只回 500 沒有原因 | FR-008 |
| US1-API-33 | `/api/auth` › 送出授權碼 | 已取得授權連結 | 重建 app 後以原本的 `flowId` 送授權碼 | 則1:回 404,`code` 為 `AUTH_LINK_EXPIRED`<br>則2:`request_token` 沒被呼叫 | 把 `code_verifier` 寫進檔案或資料庫(違反 Q17);或沒有流程時回 500 | FR-008 |
| US1-API-34 | `/api/session` › 開啟 | `get_usage` 成功(已登入);`create_session` 回 `AUTH_REQUIRED`(授權在這時過期) | 送 `POST /api/session` | 則1:`state` 為 `open_failed`,`reasonCode` 為 `AUTH_REQUIRED`<br>則2:`GET /api/auth` 的 `state` 為 `logged_out`<br>則3:`state` 不是 `lost` | 授權過期被當成工作階段失聯;或登入狀態沒跟著更新,UI 不知道要重新登入 | 邊界情況、FR-008 |
| US1-API-35 | `/api/sessions` › 列出紀錄 | 依序開過三次:第一次使用者結束(運行 120 秒)、第二次開啟失敗、第三次目前 `ready` | 送 `GET /api/sessions` | 則1:回 3 筆,依開啟時間由新到舊<br>則2:第三筆(最舊)`endReason` 為 `USER_ENDED`、`durationSeconds` 為 120、`endedAt` 不為 null<br>則3:第二筆 `endReason` 為 `OPEN_FAILED`<br>則4:第一筆 `endedAt` 為 null,`runtimeType` 為 `{gpu:"T4",highMem:false}` | 只列已結束的;或運行時長以就緒時間起算 | FR-028 |
| US1-API-36 | `/api/sessions` › 查一筆 | 一次開啟到使用者結束 | 送 `GET /api/sessions/cgb-test-0001` | 則1:狀態變化依時間是 `opening`(`allocating`)、`opening`(`starting_ollama`)、`opening`(`connecting`)、`opening`(`verifying`)、`ready`、`ending`、`ended`<br>則2:最後一筆的 `endReason` 為 `USER_ENDED` | 開啟中的每一步沒有各記一筆;或只記最後狀態 | FR-028、FR-003 |
| US1-API-37 | 排程 › 健康檢查 | 工作階段 `ready`,健康檢查間隔 0.2 秒 | 等 1.1 秒(至少 5 次健康檢查),不送任何 Ollama 相容端點的請求 | 則1:`GET /api/session` 的 `idle.lastRequestAt` 等於 `readyAt`<br>則2:`FakeTunnel.check_health` 至少被呼叫 5 次 | 健康檢查經過 Ollama 相容端點送 `/api/version`,每 15 秒重設閒置計時,工作階段永遠不會閒置結束(Q89) | FR-004 |
| US1-API-38 | `/api/events` › 訂閱 | 工作階段 `ready` | 開一條 `/api/events` | 則1:第一則 `session.updated` 是完整現況,`state` 為 `ready`、`name` 為 `cgb-test-0001`<br>則2:之後送 `DELETE /api/session`,同一條連線收到 `state` 為 `ending` 的 `session.updated` | 連上時不送快照,UI 要等下一次變化才知道狀態;或只推差異 | FR-003 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-API-39 | 可觀察性(開啟進度) | 🔴🟢 行為測試 | `/api/session` › 開啟 → `/api/session` › 查詢 | 三個步驟的替身各自等測試放行 | 送開啟,每放行一步就送一次 `GET /api/session` | 則1:四次查詢的 `step` 依序為 `allocating`、`starting_ollama`、`connecting`、`verifying`<br>則2:`ready` 之後 `step` 為 null | 開啟中只回 `opening`、不更新 `step`;或 `step` 在步驟開始後才更新,使 UI 停在上一步 | NFR-001 | — | — |
| US1-API-40 | 機密 | 🔴🟢 行為測試 | `/api/session` › 開啟 → `/api/events` › 訂閱 | `FakeColabControl` 回的錯誤 `stderrLastLine` 為 `Failed to issue request POST <網址>: 500`,替身內部記著的 endpoint 是 `https://cgb-test-fake-endpoint.example` | 開啟失敗後,讀 `GET /api/session`、`GET /api/sessions` 與 SSE 收到的每一則事件 | 則1:回應與事件裡都沒有 `cgb-test-fake-endpoint`<br>則2:回應與事件裡都沒有 `https://` 開頭、指向 Colab 的網址 | 把轉接層的原始錯誤或 endpoint 放進 `message` 給 UI | NFR-010、FR-007 | — | — |

### 2.2 E5 Colab CLI(google-colab-cli,外部程式)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-CLI-01 | `ColabControl` › `get_cli_version` | 假 `colab` 情況 A 印 `Version: 0.7.5`;情況 B 印 `Version: 0.7.6` | 各呼叫一次 | 則1:情況 A 回版本 `0.7.5`<br>則2:情況 B 回 `COLAB_UNSUPPORTED_VERSION` | 不檢查版本,改版後的輸出照舊規則解析出錯的值 | FR-001 |
| US1-CLI-02 | `ColabControl` › `get_cli_version` | `PATH` 上沒有 `colab` | 呼叫 | 則1:回 `COLAB_NOT_INSTALLED` | 找不到執行檔時拋未處理的 `FileNotFoundError` 讓後端啟動失敗 | FR-001 |
| US1-CLI-03 | `ColabControl` › `list_sessions` | 假 `colab sessions` 依序印:一行 `[colab] ` 開頭的新版本提示、一行空白、`[colab] Pruned 1 stale local session(s).`、照 `x-stdout` 格式的 `[cgb-test-0001]` 一行(endpoint `https://cgb-test-fake-endpoint.example`、Hardware T4、Shape Standard、Variant GPU)、同格式的 `[?]` 一行(Hardware T4、Shape High-RAM) | 呼叫 | 則1:具名的結果只有 `cgb-test-0001`,硬體 `T4`、形狀 `Standard`<br>則2:`unnamed` 有 1 筆,硬體 `T4`<br>則3:結果的任何欄位都不含 `cgb-test-fake-endpoint` | 把 `[colab] ` 提示行或空行當成資料而解析失敗;或把 endpoint 帶進結果 | FR-003、FR-005 |
| US1-CLI-04 | `ColabControl` › `list_sessions` | 假 `colab sessions` 只印 `[colab] No active sessions found on server.` | 呼叫 | 則1:具名與 `unnamed` 都是空清單,不是錯誤 | 把「沒有執行環境」當成格式不符而回 `COLAB_BAD_RESPONSE` | FR-003 |
| US1-CLI-05 | `ColabControl` › `list_sessions` | 假 `colab sessions` 多印一行 `[cgb-test-0001] x Hardware T4`(欄位格式改了) | 呼叫 | 則1:回 `COLAB_BAD_RESPONSE` | 比對不到的行直接略過,使改版後所有執行環境「消失」、被判成收回 | FR-004 |
| US1-CLI-06 | `ColabControl` › `create_session` | 假 `colab new` 印 `[colab] Creating session 'cgb-test-0001'...` 與 `[colab] Session READY.`;回讀的 `sessions` 列出它 | 以 `name=cgb-test-0001, gpu=T4, high_mem=false` 呼叫;再以 `high_mem=true` 呼叫一次 | 則1:第一次的 argv 逐字為 `colab new -s cgb-test-0001 --gpu T4`<br>則2:第二次的 argv 最後一個參數是 `--high-mem`<br>則3:假 `colab` 讀 stdin 立即得到 EOF<br>則4:環境變數 `COLAB_CLI_REQUEST_TIMEOUT` 為 `60` | stdin 繼承後端的,CLI 等授權碼時整個開啟卡住;或少帶逾時環境變數 | FR-001、FR-009 |
| US1-CLI-07 | `ColabControl` › `create_session` | 假 `colab new` 印 `Session READY.` 並 exit 0;回讀的 `sessions` 沒有列出 `cgb-test-0001` | 呼叫 | 則1:回 `COLAB_NOT_FOUND` | 看到 `Session READY.` 或 exit 0 就當成功 | FR-001、FR-007 |
| US1-CLI-08 | `ColabControl` › `create_session` | 無 | 以 `gpu="t4"` 與 `gpu="TPU"` 各呼叫一次 | 則1:兩次都在啟動子行程前回錯誤<br>則2:假 `colab` 一次都沒被執行 | 把不在 `GpuType` 的字串放進命令列(CLI 會當成 A100) | FR-009 |
| US1-CLI-09 | `ColabControl` › `create_session` | 假 `colab new` 成功,stderr 有 `[colab] --high-mem ignored: this accelerator only offers one machine shape.` | 以 `gpu=L4, high_mem=true` 呼叫 | 則1:回成功,`highMemIgnored` 為 true | 把這行 stderr 當成失敗;或忽略它,UI 不知道高 RAM 沒生效 | FR-009 |
| US1-CLI-10 | `ColabControl` › `get_usage` | 假 `colab` 在 stderr 印 `To authorize colab-cli, visit this URL: https://accounts.google.com/o/oauth2/auth?x=1`,從 stdin 讀授權碼;讀到 EOF 時印 `EOFError` traceback 並 exit 1 | 呼叫 | 則1:回 `AUTH_REQUIRED`<br>則2:呼叫在 2 秒內回來 | stdin 沒接 `/dev/null`,CLI 永遠等授權碼;或歸成 `COLAB_FAILED`,UI 不知道要登入 | FR-008 |
| US1-CLI-11 | `ColabControl` › `start_ollama` | 假 `colab exec` 印 30 行安裝程式輸出,最後一行 `CGB-RESULT {"ok": true, "ollamaVersion": "0.40.15", "alreadyRunning": false}` | 呼叫 | 則1:回 `ollamaVersion` 為 `0.40.15`<br>則2:argv 含 `--timeout 240`<br>則3:argv 有一個參數逐字為 `OLLAMA_HOST=127.0.0.1:11434`、一個逐字為 `OLLAMA_ORIGINS=*` | 解析第一行而不是最後一個 `CGB-RESULT` 行;或 `*` 被 shell 展開成檔名 | FR-001 |
| US1-CLI-12 | `ColabControl` › `start_ollama` | 假 `colab exec` 第一次在 stderr 印 `RuntimeError: Connection was lost` 並 exit 0、第二次正常印 `CGB-RESULT` | 呼叫 | 則1:回成功<br>則2:假 `colab exec` 被執行 2 次,兩次 argv 相同 | 第一次就判開啟失敗(research.md R1 實測會偶發);或重試時改了參數 | FR-001 |
| US1-CLI-13 | `ColabControl` › `probe_resources` | 假 `colab exec` 每次都在 stderr 印 `RuntimeError: Connection was lost` | 呼叫 | 則1:回 `COLAB_UNREACHABLE`<br>則2:假 `colab exec` 恰好被執行 2 次 | 無限重試;或不重試 | FR-001 |
| US1-CLI-14 | `ColabControl` › `start_ollama` | 假 `colab exec` 在 stderr 印 `Traceback (most recent call last):` 與 `ValueError: see https://cgb-test-fake-endpoint.example/x`,沒有 `CGB-RESULT` 行,exit 0 | 呼叫 | 則1:回 `COLAB_REMOTE_ERROR`<br>則2:`stderrLastLine` 為 `ValueError: see <網址>` | 信 exit 0 當成功;或 `stderrLastLine` 原樣帶出網址 | FR-001、FR-007 |
| US1-CLI-15 | `ColabControl` › `stop_session` | 假 `colab stop` 印 `[colab] Session 'cgb-test-0001' not found.` 並 exit 0;回讀的 `sessions` 沒有它 | 呼叫 | 則1:回成功<br>則2:回讀的 `colab sessions` 被執行 1 次 | 看到 `not found` 就回錯誤(結束應該是冪等的);或沒有回讀 | FR-002、FR-007 |
| US1-CLI-16 | `ColabControl` › `stop_session` | 假 `colab stop` 每次都印 `[colab] Session terminated.` 並 exit 0;回讀的 `sessions` 一直列出 `cgb-test-0001` | 呼叫 | 則1:回 `COLAB_STOP_UNCONFIRMED`<br>則2:`colab stop` 被執行 2 次<br>則3:回讀的 `colab sessions` 被執行 2 次 | 信 `Session terminated.` 或 exit 0 就回成功(research.md R1:stop 的 exit code 不反映結果) | FR-007、SC-003 |
| US1-CLI-17 | `ColabControl` › `stop_session` | 第一次回讀仍列出、第二次回讀沒有 | 呼叫 | 則1:回成功<br>則2:`colab stop` 被執行 2 次 | 第一次回讀還在就直接回 `COLAB_STOP_UNCONFIRMED`,沒有再試一次 | FR-007 |
| US1-CLI-18 | `ColabControl` › `stop_session` | 假 `colab stop` 在 stderr 印 `Failed to issue request POST https://cgb-test-fake-endpoint.example/unassign/abc: 500` 並 exit 1;回讀的 `sessions` 仍列出 | 呼叫 | 則1:回 `COLAB_STOP_UNCONFIRMED`<br>則2:`stderrLastLine` 為 `Failed to issue request POST <網址>: 500` | 遮蔽寫錯,endpoint 原樣進入錯誤訊息與日誌;或 exit 1 就不回讀 | FR-007、NFR-010 |
| US1-CLI-19 | `ColabControl` › `get_usage` | 情況 A 假 `colab usage` 印三行 `Current balance: 381.66 compute units`、`Usage rate: 1.15/hr`、`Active assignments: 1`;情況 B stderr 印 `[colab] Warning: failed to fetch compute-unit info: timeout` 並 exit 1 | 各呼叫一次 | 則1:情況 A 回 `balance` 381.66、`ratePerHour` 1.15、`activeAssignments` 1<br>則2:情況 B 回的代碼不是 `AUTH_REQUIRED` | 讀不到用量就當成未登入,把使用者趕去重新登入 | FR-008 |
| US1-CLI-20 | `ColabControl` › `list_sessions` | 子行程逾時注入 0.5 秒;假 `colab sessions` 睡 10 秒 | 呼叫 | 則1:0.5 到 1.5 秒之間回 `COLAB_TIMEOUT`<br>則2:之後 `ps` 看不到假 `colab` 行程,也沒有 defunct 行程 | 逾時後沒殺子行程或沒 `wait`,留下殭屍 | FR-004 |
| US1-CLI-22 | `ColabControl` › `get_cli_version` | 子行程時限注入 0.5 秒(Q95);假 `colab` 先以 `sleep 30 &` 分出一個子行程,自己再睡 30 秒 | 呼叫 | 則1:0.5 到 1.5 秒之間回 `COLAB_TIMEOUT`<br>則2:回傳後假 `colab` 已結束<br>則3:回傳後它分出的 `sleep` 子行程也已結束<br>則4:`ps` 看不到 defunct 行程 | 沒設子行程時限,CLI 卡住時後端啟動一直等;或只殺 `colab` 本身,分出的子行程留著(Q138) | FR-001 |
| US1-CLI-23 | `ColabControl` › `create_session` | 子行程時限注入 0.5 秒(Q95);假 `colab` 先以 `sleep 30 &` 分出一個子行程,自己再睡 30 秒 | 以 `cgb-test-0001`、T4 呼叫 | 則1:0.5 到 1.5 秒之間回 `COLAB_TIMEOUT`<br>則2:回傳後假 `colab` 與它分出的子行程都已結束<br>則3:`ps` 看不到 defunct 行程 | `colab new` 沒有時限,卡住時開啟流程永遠停在配置、一直扣點;或逾時只回錯誤沒有終止子行程 | FR-001、FR-007 |
| US1-CLI-24 | `ColabControl` › `start_ollama` | 子行程時限注入 0.5 秒(Q95);假 `colab` 先以 `sleep 30 &` 分出一個子行程,自己再睡 30 秒 | 分別呼叫 `start_ollama` 與 `probe_resources`(parametrize) | 則1:兩個都在 0.5 到 1.5 秒之間回 `COLAB_TIMEOUT`<br>則2:兩個回傳後假 `colab` 與它分出的子行程都已結束<br>則3:兩個的假 `colab exec` 都只被執行 1 次 | 只靠 CLI 的 `--timeout`,CLI 自己卡住時沒有硬時限;或把逾時當成 `Connection was lost` 重跑 | FR-001 |
| US1-CLI-25 | `ColabControl` › `stop_session` | 子行程時限注入 0.5 秒(Q95);假 `colab stop` 睡 30 秒;回讀的 `colab sessions` 沒有列出 `cgb-test-0001` | 以 `cgb-test-0001` 呼叫 | 則1:回成功(結果照回讀判定)<br>則2:回讀的 `colab sessions` 在 `colab stop` 被終止之後才執行,共 1 次<br>則3:回傳後假 `colab stop` 已結束 | `colab stop` 沒有時限,卡住時結束流程永遠停在結束中;或 `colab stop` 逾時就直接回錯誤、不回讀(合約:成功與否一律以回讀為準,Q139) | FR-002、FR-007 |
| US1-CLI-26 | `ColabControl` › `stop_session` | 子行程時限注入 0.5 秒(Q95);假 `colab stop` 立即印 `[colab] Session terminated.`;回讀的 `colab sessions` 睡 30 秒 | 以 `cgb-test-0001` 呼叫 | 則1:回 `COLAB_TIMEOUT`<br>則2:回傳後假 `colab sessions` 已結束 | 回讀逾時被當成「看不到名稱」而回成功,實際上執行環境可能還在 | FR-007 |
| US1-CLI-27 | `ColabControl` › `get_usage` | 子行程時限注入 0.5 秒(Q95);假 `colab` 先以 `sleep 30 &` 分出一個子行程,自己再睡 30 秒 | 呼叫 | 則1:0.5 到 1.5 秒之間回 `COLAB_TIMEOUT`<br>則2:回傳後假 `colab` 與它分出的子行程都已結束 | 定時讀用量沒有時限,一次卡住後所有讀取都排在它後面 | FR-024 |
| US1-CLI-28 | `ColabControl` › `list_sessions` | 假 `colab sessions` 以 exit 1 結束,stderr 最後一行依參數是 `requests.exceptions.ConnectionError: x`、`Max retries exceeded with url: /tun/m`、`NameResolutionError: x`、`Temporary failure in name resolution`、`requests.exceptions.ReadTimeout: x`、`Read timed out.` | 每種字樣各呼叫一次(parametrize) | 則1:前四種都回 `COLAB_UNREACHABLE`<br>則2:後兩種都回 `COLAB_TIMEOUT` | 依 exit code 一律歸成 `COLAB_FAILED`,家裡斷網時健康檢查判不出是連不到 | FR-004 |
| US1-CLI-29 | `ColabControl` › `create_session` | 假 `colab new` 以 exit 1 結束,stderr 依參數含 `ConnectionError`、`Max retries exceeded`、`NameResolutionError`、`Temporary failure in name resolution`、`ReadTimeout`、`timed out` | 每種字樣各呼叫一次(parametrize) | 則1:前四種都回 `COLAB_UNREACHABLE`<br>則2:後兩種都回 `COLAB_TIMEOUT` | 開啟失敗的原因一律是 `COLAB_FAILED`,UI 說不出是網路問題 | FR-001 |
| US1-CLI-30 | `ColabControl` › `start_ollama` | 假 `colab exec` 以 exit 1 結束,stderr 依參數含 `ConnectionError`、`Max retries exceeded`、`NameResolutionError`、`Temporary failure in name resolution`、`TimeoutError`、`ReadTimeout`、`timed out` | 每種字樣各呼叫一次(parametrize) | 則1:前四種都回 `COLAB_UNREACHABLE`<br>則2:後三種都回 `COLAB_TIMEOUT`<br>則3:每一種的假 `colab exec` 都只被執行 1 次 | 把所有連線錯誤都當成 `Connection was lost` 重跑;或漏了 exec 才有的 `TimeoutError` | FR-001 |
| US1-CLI-31 | `ColabControl` › `get_usage` | 假 `colab usage` 以 exit 1 結束,stderr 依參數含 `ConnectionError`、`Max retries exceeded`、`NameResolutionError`、`Temporary failure in name resolution`、`ReadTimeout`、`timed out` | 每種字樣各呼叫一次(parametrize) | 則1:前四種都回 `COLAB_UNREACHABLE`<br>則2:後兩種都回 `COLAB_TIMEOUT` | 讀用量失敗一律歸成同一個代碼,UI 說不出原因 | FR-024 |
| US1-CLI-32 | `ColabControl` › `list_sessions` | 假 `colab sessions` 以 exit 1 結束;情況 A stderr 有 `To authorize colab-cli, visit this URL: https://accounts.google.com/o/oauth2/auth?x=1`;情況 B stderr 有 `requests.exceptions.HTTPError: 401 Client Error: Unauthorized for url: https://cgb-test-fake-endpoint.example/x` | 各呼叫一次 | 則1:情況 A 回 `AUTH_REQUIRED`<br>則2:情況 B 回 `AUTH_REQUIRED` | 只認授權網址那一種,Colab 後端回 401 時歸成 `COLAB_FAILED`;健康檢查把授權過期當成連不到而重連 | FR-008、FR-004 |
| US1-CLI-33 | `ColabControl` › `create_session` | 假 `colab new` 以 exit 1 結束;情況 A stderr 有 `To authorize colab-cli, visit this URL: https://accounts.google.com/o/oauth2/auth?x=1`;情況 B stderr 有 `HTTPError: 401 Client Error: Unauthorized for url: https://cgb-test-fake-endpoint.example/x` | 各呼叫一次 | 則1:情況 A 回 `AUTH_REQUIRED`<br>則2:情況 B 回 `AUTH_REQUIRED` | 授權過期時開啟失敗的原因是 `COLAB_FAILED`,UI 沒有引導重新登入(spec 邊界情況) | FR-008 |
| US1-CLI-34 | `ColabControl` › `start_ollama` | 假 `colab exec` 以 exit 1 結束;情況 A stderr 有 `To authorize colab-cli, visit this URL: https://accounts.google.com/o/oauth2/auth?x=1`;情況 B stderr 有 `HTTPError: 401 Client Error: Unauthorized for url: https://cgb-test-fake-endpoint.example/x` | 各呼叫一次 | 則1:情況 A 回 `AUTH_REQUIRED`<br>則2:情況 B 回 `AUTH_REQUIRED`<br>則3:兩種情況的假 `colab exec` 都只被執行 1 次 | 授權失效被當成可重試的錯誤重跑;或歸成 `COLAB_FAILED` | FR-008 |
| US1-CLI-35 | `ColabControl` › `stop_session` | 假 `colab stop` 以 exit 1 結束,stderr 有 `To authorize colab-cli, visit this URL: https://accounts.google.com/o/oauth2/auth?x=1` | 以 `cgb-test-0001` 呼叫 | 則1:回 `AUTH_REQUIRED`<br>則2:回讀的 `colab sessions` 沒有被執行 | 授權失效時照樣回讀,回讀也失敗後歸成別的代碼,UI 不知道要重新登入 | FR-008、FR-007 |
| US1-CLI-36 | `ColabControl` › `create_session` | 假 `colab new` 以 exit 1 結束;情況 A stderr 有 `[colab] Allocation refused (precondition failed).`;情況 B stderr 有 `[colab] Backend rejected accelerator 'L4' for this account.` | 情況 A 以 T4、情況 B 以 L4 各呼叫一次 | 則1:情況 A 回 `COLAB_ALLOCATION_REFUSED`<br>則2:情況 B 回 `COLAB_ACCELERATOR_REJECTED` | 兩種配置失敗都歸成 `COLAB_FAILED`,UI 說不出是同時開太多還是帳號沒有這種 GPU | FR-003、FR-009 |
| US1-CLI-37 | `ColabControl` › `get_cli_version` → `ColabControl` › `list_sessions` → `ColabControl` › `create_session` → `ColabControl` › `start_ollama` | 假 `colab` 對 `version`、`sessions`、`new`、`exec` 都以 exit 2 結束,stderr 依序是 `Traceback (most recent call last):`、`  File x`、`RuntimeError: boom at https://cgb-test-fake-endpoint.example/x`、一行空白;stdout 是空的 | 四個方法各呼叫一次 | 則1:四個都回 `COLAB_FAILED`<br>則2:四個的 `stderrLastLine` 都是 `RuntimeError: boom at <網址>`(最後一個非空行,網址已遮蔽) | `stderrLastLine` 取到最後那行空白;或沒有遮蔽,endpoint 進入錯誤訊息與日誌 | FR-001、NFR-010 |
| US1-CLI-38 | `ColabControl` › `create_session` | 假 `colab new` 只印 `[colab] Creating session 'cgb-test-0001'...` 並 exit 0 | 呼叫 | 則1:回 `COLAB_BAD_RESPONSE` | exit 0 就往下回讀、回讀看到名稱就當成功(配置其實沒完成) | FR-001 |
| US1-CLI-39 | `ColabControl` › `start_ollama` | 情況 A 假 `colab exec` 在 stdout 印 `[colab] Session 'cgb-test-0001' not found.` 並 exit 0;情況 B 在 stdout 印 `[colab] Runtime appears to be lost (404/401).` 並 exit 0 | 各呼叫一次 | 則1:情況 A 回 `COLAB_NOT_FOUND`<br>則2:情況 B 回 `COLAB_NOT_FOUND`<br>則3:兩種情況的假 `colab exec` 都只被執行 1 次 | 沒有結果行就歸成 `COLAB_BAD_RESPONSE`,呼叫者不知道執行環境已經不在;或對已被收回的執行環境重跑 | FR-001、FR-004 |
| US1-CLI-40 | `ColabControl` › `start_ollama` | 假 `colab exec` 在 stdout 最後印 `CGB-RESULT {"ok": false, "stage": "install", "detail": "curl: (22) error 503"}` 並 exit 0 | 呼叫 | 則1:回 `COLAB_REMOTE_ERROR`<br>則2:`message` 含 `install`<br>則3:`message` 含 `curl: (22) error 503` | 有 `CGB-RESULT` 行就當成功,沒看 `ok`;或 `message` 沒帶失敗的階段與原因 | FR-001 |
| US1-CLI-41 | `ColabControl` › `probe_resources` | 情況 A 假 `colab exec` 只印安裝程式的雜訊行、沒有 `CGB-RESULT` 行、stderr 是空的,exit 0;情況 B 最後一行是 `CGB-RESULT {ok: true`(不是合法 JSON),exit 0 | 各呼叫一次 | 則1:情況 A 回 `COLAB_BAD_RESPONSE`<br>則2:情況 B 回 `COLAB_BAD_RESPONSE` | 沒有結果行時當成成功並回預設值(例如剩餘磁碟 0);或把 JSON 解析例外往上拋成 500 | FR-001、FR-022 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-CLI-21 | 正確性(替身與真 CLI 一致) | 📏 量測 | `colab` 指令 › `version` → `colab` 指令 › `new` → `colab` 指令 › `exec` → `colab` 指令 › `stop` | 主機上真的 google-colab-cli 0.7.5(不經假執行檔);`<暫存目錄>` 已有照 P9 複製來的 token.json | 依序執行 `version`、`usage`、`sessions`、`new -s cgb-test-<時間>-adapter --gpu T4`、`sessions`、`exec -f` 啟動 Ollama 腳本、`exec -f` 讀資源腳本、`stop -s cgb-test-<時間>-none`(不存在的名稱)、(US2-RO-03、US1-TUN-10 跑完後)`stop -s cgb-test-<時間>-adapter`、`sessions`;每行輸出用轉接層的同一組 regex 解析 | 則1:`version` 的 stdout 是 `Version: 0.7.5`<br>則2:`usage` 三行都符合 `x-stdout` 的三個 regex<br>則3:兩次 `sessions` 的每一行都符合 `x-stdout` 的 regex 或以 `[colab] ` 開頭<br>則4:`new` 的 stdout 有 `[colab] Session READY.`,接著的 `sessions` 列出這個名稱、硬體 T4<br>則5:兩次 `exec` 的 stdout 最後一個 `CGB-RESULT` 行可解析,`ok` 為 true、`vramTotalBytes` 大於 0<br>則6:`stop` 不存在的名稱印 `not found` 且 exit code 為 0(替身照這個行為寫)<br>則7:`stop` 之後 60 秒內 `sessions` 不再列出這個名稱(SC-003)<br>則8:`tests/fixtures/bin/colab` 劇本裡每一種輸出,和這次錄到的對應輸出,解析出的欄位名稱相同 | 替身照文件想像的格式寫,和 0.7.5 真的輸出不同,自動化測試全綠、接上真的 CLI 就解析失敗;或 stop 的回讀判定在真實延遲下不成立 | FR-001、FR-002、FR-007、SC-003 | P1~P9;執行環境 1 台 T4,開到關約 11 分鐘(含 US2-RO-03 與 US1-TUN-10 各約 3 分鐘),整台約 0.21 compute units;子行程帶 `HOME=<暫存目錄>/home`;不呼叫本系統後端;記下 `Connection was lost` 出現的次數 | 判定者:腳本(regex 比對與 60 秒門檻);樣本:一次實跑(未用於調整替身以外的規則) |

### 2.3 E6 SSH 通道(OpenSSH 與 `colab ssh --proxy-mode`)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-TUN-01 | `Tunnel` › `ensure_key` | 情況 A:`<keyPath>` 不存在;情況 B:`<keyPath>` 是一把 RSA 私鑰 | 各呼叫一次(真的 `ssh-keygen`) | 則1:情況 A 產生 ed25519 金鑰,權限 0600,回類型 `ssh-ed25519` 與 `SHA256:` 開頭的指紋<br>則2:情況 A 的回傳值不含公鑰本文<br>則3:情況 B 回 `TUNNEL_KEY_REJECTED`<br>則4:情況 B 的檔案 sha256 和呼叫前相同 | 已有金鑰時覆寫(可能是使用者自己放的);或接受 RSA(伺服器會拒絕) | FR-001 |
| US1-TUN-02 | `Tunnel` › `open_tunnel` | 金鑰就緒;假 `ssh` 常駐不印任何東西;假 `/api/version` 伺服器回 `{"version":"0.40.15"}` | 以 `cgb-test-0001`、`localPort` 為隨機 port 呼叫 | 則1:argv 含 `-F none`、`-N`、`-o BatchMode=yes`、`-o IdentitiesOnly=yes`、`-o ExitOnForwardFailure=yes`、`-o ServerAliveInterval=15`、`-o ServerAliveCountMax=3`<br>則2:argv 的 ProxyCommand 逐字為 `colab ssh --proxy-mode -s cgb-test-0001 --identity <keyPath>`,不含 `--gpu`、`--tpu`、`--high-mem`、`--rm`<br>則3:argv 的轉發逐字為 `-L 127.0.0.1:<localPort>:127.0.0.1:11434`,沒有 `-g`<br>則4:假伺服器回 200 後才回成功 | ProxyCommand 帶了 `--rm`(斷線就結束執行環境)或開啟用的旗標;或 ssh 一啟動就回成功、沒等模型服務可回應 | FR-001、FR-004 |
| US1-TUN-03 | `Tunnel` › `open_tunnel` | 假 `ssh` 啟動後在 stderr 印 `[colab] Creating runtime 'cgb-test-0001'...` 然後常駐 | 呼叫 | 則1:回 `TUNNEL_NOT_FOUND`<br>則2:這行出現後 1 秒內 ssh 的整個 process group 都已結束 | 沒比對這行,讓 `colab ssh` 意外開出的執行環境繼續跑(扣點,Q64) | FR-006 |
| US1-TUN-04 | `Tunnel` › `open_tunnel` | 假 `ssh` 依參數在 stderr 印 `Error.x-stderr-patterns` 的每一條比對字樣後結束 | 每一條字樣各呼叫一次(parametrize) | 則1:每一次回的代碼都是那一條比對字樣對應的代碼<br>則2:印出 `Warning: Permanently added 'colab-runtime'` 那一次不算失敗 | 比對順序錯,使 `TUNNEL_ALREADY_CONNECTED` 之類落到 `TUNNEL_FAILED`;或把每次連線都會印的 known_hosts 警告當成失敗 | FR-004 |
| US1-TUN-05 | `Tunnel` › `open_tunnel` | 就緒期限注入 1 秒;情況 A 假伺服器一直拒絕連線;情況 B 假 `ssh` 在 stderr 印 `open failed: connect failed` 且轉發的連線被立即關閉 | 各呼叫一次 | 則1:情況 A 在 1 到 1.5 秒之間回 `TUNNEL_TIMEOUT`<br>則2:情況 B 在 1 到 1.5 秒之間回 `TUNNEL_REMOTE_REFUSED`<br>則3:兩種情況回傳時 ssh 都已結束 | 期限內第一次被拒就放棄(Ollama 剛啟動還沒聽);或期限到沒關掉 ssh | FR-001 |
| US1-TUN-06 | `Tunnel` › `check_health` | 通道已建立 | 情況 A 假伺服器回 200 與 version;情況 B 假 `ssh` 印 `Timeout, server colab-runtime not responding.` 後結束;情況 C 假伺服器 0.3 秒內不回應;情況 D 假伺服器回 200 與 `<html>` | 則1:情況 A 回健康<br>則2:情況 B 回 `TUNNEL_TIMEOUT`<br>則3:情況 C 回 `TUNNEL_TIMEOUT`<br>則4:情況 D 回 `TUNNEL_BAD_RESPONSE` | 只看 ssh 行程還在就算健康,沒打 `/api/version`;或 ssh 結束後仍回健康 | FR-004 |
| US1-TUN-07 | `Tunnel` › `close_tunnel` | 通道已建立;假 `ssh` 會再分出一個忽略 SIGTERM 的子行程(代表 ProxyCommand);SIGTERM 後等待時間注入 0.5 秒 | 呼叫兩次 | 則1:第一次回成功時,`localPort` 已沒有在聽<br>則2:之後 `ps` 看不到假 `ssh` 與它的子行程,也沒有 defunct 行程<br>則3:第二次回成功(冪等) | 只對 ssh 的 pid 送訊號,ProxyCommand 留著;或沒有 `wait`,留下殭屍 | FR-002、FR-004 |
| US1-TUN-08 | `Tunnel` › `cleanup_residual` | 主機上有一個命令列符合 `ssh -F none -N -i <keyPath> … ProxyCommand=colab ssh --proxy-mode -s cgb-test-0001 …` 的假行程,和一個命令列是 `ssh -N user@example` 的假行程 | 呼叫 | 則1:第一個行程已結束<br>則2:第二個行程仍在執行 | 用 `pkill ssh` 一類的寬鬆比對,關掉使用者自己的 ssh | FR-005 |
| US1-TUN-11 | `Tunnel` › `open_tunnel` | `Tunnel` 建構時注入 `term_wait=0.3`、`kill_wait=0.2`(秒);假 `ssh` 劇本設定「自己與分出的子行程都忽略 SIGTERM」(需要的 fixture 欄位,Q141);假 `ssh` 啟動後在 stderr 印 `[colab] Creating runtime 'cgb-test-0001'...` 然後常駐;同一個事件迴圈上另跑一個每 0.05 秒記一次時間的 task | 以 `cgb-test-0001` 呼叫 | 則1:回 `TUNNEL_NOT_FOUND`<br>則2:這行出現後 1 秒內回傳(0.3 + 0.2 秒的等待加上餘裕)<br>則3:回傳時假 `ssh` 與它分出的子行程都已結束<br>則4:`ps` 看不到 defunct 行程<br>則5:記時 task 相鄰兩次的最大間隔不超過 0.2 秒 | 收尾只送 SIGTERM、沒有接著 SIGKILL,忽略 SIGTERM 的行程一直留著(`colab ssh` 意外開出的連線不放);或用同步的 `wait()` 等子行程,卡住整個事件迴圈 | FR-006、FR-007 |
| US1-TUN-12 | `Tunnel` › `open_tunnel` | `Tunnel` 建構時注入 `term_wait=0.3`、`kill_wait=0.2`(秒);假 `ssh` 先分出一個忽略 SIGTERM 的子行程(代表 ProxyCommand,需要的 fixture 欄位,Q141),自己在 stderr 印 `cgb-test unknown failure` 後結束;同一個事件迴圈上另跑一個每 0.05 秒記一次時間的 task | 以 `cgb-test-0001` 呼叫 | 則1:回 `TUNNEL_FAILED`<br>則2:假 `ssh` 結束後 1 秒內回傳<br>則3:回傳時那個子行程已結束<br>則4:記時 task 相鄰兩次的最大間隔不超過 0.2 秒 | ssh 自己結束就以為整組都結束了,沒有對 process group 收尾,留下孤兒的 ProxyCommand | FR-004 |
| US1-TUN-13 | `Tunnel` › `open_tunnel` | `Tunnel` 建構時注入 `term_wait=0.3`、`kill_wait=0.2`(秒);就緒期限注入 0.5 秒;假 `ssh` 劇本設定「自己與分出的子行程都忽略 SIGTERM」(需要的 fixture 欄位,Q141);假 `ssh` 常駐不印任何東西;測試先呼叫 `ForwardStandIn.server.stop()`,`localPort` 一直拒絕連線(不用「不回應」,免得單次探測的 5 秒逾時蓋過就緒期限);同一個事件迴圈上另跑一個每 0.05 秒記一次時間的 task | 以 `cgb-test-0001` 呼叫 | 則1:回 `TUNNEL_TIMEOUT`<br>則2:呼叫後 0.5 到 1.5 秒之間回傳<br>則3:回傳時假 `ssh` 與它分出的子行程都已結束<br>則4:記時 task 相鄰兩次的最大間隔不超過 0.2 秒 | 就緒期限到了只回錯誤沒有關掉 ssh;或關閉時忽略 SIGTERM 的行程讓呼叫卡住不回 | FR-001 |
| US1-TUN-14 | `Tunnel` › `open_tunnel` → `Tunnel` › `ensure_key` | 情況 A:`PATH` 上沒有 `ssh`;情況 B:`PATH` 上沒有 `ssh-keygen`、`<keyPath>` 不存在 | 情況 A 呼叫 `open_tunnel`,情況 B 呼叫 `ensure_key` | 則1:情況 A 回 `TUNNEL_NOT_INSTALLED`,沒有丟出 `FileNotFoundError`<br>則2:情況 B 回 `TUNNEL_NOT_INSTALLED`,沒有丟出 `FileNotFoundError` | 啟動子行程時找不到執行檔就拋例外,開啟流程以 500 中止、UI 沒有原因 | FR-001 |
| US1-TUN-15 | `Tunnel` › `ensure_key` | `Tunnel` 建構時注入 `ssh-keygen` 的時限 0.3 秒(合約 10 秒,Q149);`PATH` 上的假 `ssh-keygen` 睡 30 秒(需要的 fixture,Q141) | 以不存在的 `<keyPath>` 呼叫 | 則1:回 `TUNNEL_FAILED`(合約:逾時視為 `TUNNEL_FAILED`,Q147)<br>則2:呼叫後 0.3 到 1.3 秒之間回傳<br>則3:回傳時假 `ssh-keygen` 已結束 | `ssh-keygen` 沒有時限(例如停下來等輸入密碼),後端啟動卡住;或逾時後沒有終止子行程 | FR-001 |
| US1-TUN-16 | `Tunnel` › `ensure_key` | 情況 A:`<keyPath>` 不存在,假 `ssh-keygen` 產生金鑰時 exit 0 卻沒有寫出檔案;情況 B:`<keyPath>` 是真的 ed25519 私鑰,假 `ssh-keygen` 對 `-y` 回正常的公鑰行,對 `-l` 的 stdout 印 `not a fingerprint`、stderr 印 `warning see https://cgb-test-fake-endpoint.example/k`(需要的 fixture,Q141) | 各呼叫一次 | 則1:情況 A 回 `TUNNEL_FAILED`(第一行之後金鑰不存在,Q148)<br>則2:情況 B 回 `TUNNEL_FAILED`<br>則3:情況 B 的 `stderrLastLine` 為 `warning see <url>` | 指紋格式不對時照樣回成功並帶出亂碼;或 `stderrLastLine` 沒遮蔽網址 | FR-001、NFR-010 |
| US1-TUN-17 | `Tunnel` › `close_tunnel` | `Tunnel` 建構時注入 `term_wait=0.3`、`kill_wait=0.2`;通道已建立;`ForwardStandIn` 設定成假 `ssh` 結束後仍繼續聽 `localPort`(代表別的行程占用,需要的 fixture 選項,Q141) | 呼叫 `close_tunnel` | 則1:回 `TUNNEL_FAILED`<br>則2:呼叫後 1.5 秒內回傳<br>則3:回傳時假 `ssh` 已結束 | 送完訊號就回成功,沒確認 port 已經沒人聽,下一次建立通道撞 `TUNNEL_PORT_IN_USE` | FR-002 |
| US1-TUN-18 | `Tunnel` › `check_health` | 通道已建立,假 `ssh` 仍常駐 | 測試呼叫 `ForwardStandIn.server.stop()` 讓 `localPort` 沒人聽,再呼叫 `check_health` | 則1:回 `TUNNEL_UNREACHABLE` | 連線被拒當成 `TUNNEL_TIMEOUT` 或丟出 `httpx.ConnectError` | FR-004 |
| US1-TUN-19 | `Tunnel` › `check_health` | 通道已建立,假 `ssh` 仍常駐;`ForwardStandIn` 的 `/api/version` 改成連上後不回應就關閉連線,同時假 `ssh` 在 stderr 印 `channel 2: open failed: connect failed: Connection refused` | 呼叫 `check_health` | 則1:回 `TUNNEL_REMOTE_REFUSED` | 把遠端 Ollama 不在當成通道斷了(`TUNNEL_UNREACHABLE`),重建通道永遠不會好 | FR-004 |
| US1-TUN-20 | `Tunnel` › `check_health` | 情況 A:從沒為 `cgb-test-9999` 建立通道;情況 B:`cgb-test-0001` 的通道已 `close_tunnel` | 情況 A 以 `cgb-test-9999`、情況 B 以 `cgb-test-0001` 呼叫 | 則1:情況 A 回 `TUNNEL_NOT_FOUND`<br>則2:情況 B 回 `TUNNEL_NOT_FOUND` | 沒有這條轉發時丟出 `KeyError`;或關閉後仍回健康 | FR-004 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-TUN-09 | 機密 | 🔴🟢 行為測試 | `Tunnel` › `open_tunnel` | 假 `ssh` 在 stderr 印一行無法歸類的錯誤 `ws error wss://cgb-test-fake-endpoint.example/x?colab-runtime-proxy-token=cgb-test-fake-token&a=1 refused` 後結束 | 呼叫 | 則1:回 `TUNNEL_FAILED`<br>則2:`stderrLastLine` 不含 `cgb-test-fake-token`<br>則3:`stderrLastLine` 不含 `cgb-test-fake-endpoint`<br>則4:pytest 擷取到的日誌不含 `cgb-test-fake-token` | 遮蔽 regex 只換網址的主機、沒換 query 裡的 token;或把 stderr 全文寫進日誌 | NFR-010 | — | — |
| US1-TUN-10 | 正確性(替身與真 ssh 一致)、可用性(斷線重連) | 📏 量測 | `Tunnel` › `open_tunnel` → 實跑操作 › 殺掉 ssh → `Tunnel` › `check_health` → `Tunnel` › `open_tunnel` → `Tunnel` › `close_tunnel` | 主機上真的 OpenSSH 與 `colab ssh --proxy-mode`;US1-CLI-21 開好的 `cgb-test-<時間>-adapter` 已啟動 Ollama,`colab sessions` 列出它;US2-RO-03 已載入 `qwen2.5:0.5b` | 建立通道;健康檢查 3 次;以 SIGKILL 殺掉 ssh;立即健康檢查;每 2 秒嘗試一次 `open_tunnel` 直到成功或 120 秒;查 `/api/ps`;`close_tunnel` | 則1:第一次建立在 30 秒內就緒<br>則2:殺掉 ssh 後的那次健康檢查回失敗,代碼不是健康<br>則3:重新建立在 120 秒內成功,並記下等了幾秒、中間出現過哪些代碼(Q69)<br>則4:重新建立後 `/api/ps` 仍有 `qwen2.5:0.5b`<br>則5:`close_tunnel` 後 `localPort` 沒有在聽、沒有 defunct 行程<br>則6:`close_tunnel` 後 `colab sessions` 仍列出這台(關通道不結束執行環境)<br>則7:這次 stderr 出現過的每一行,都比對得到 `x-stderr-patterns` 的一條或屬於可忽略的行 | 假 `ssh` 的錯誤字樣照 OpenSSH 原始碼推測、和真的不同;或半開連線要很久才放掉,重連流程 5 分鐘內接不回 | FR-004、FR-005、NFR-002 | P1~P9;與 US1-CLI-21 共用同一台 T4,本案例約 3 分鐘,占用算在 US1-CLI-21 的 0.21 compute units 之內;本機轉發只綁 127.0.0.1 的隨機 port,不用 11434~11436;金鑰放 `<暫存目錄>/data/ssh/`,不用桌機的 `~/.ssh` | 判定者:腳本(30 秒與 120 秒門檻);樣本:一次實跑(未用於調整) |

### 2.4 E9 Google OAuth(授權碼流程)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-OA-01 | `GoogleOAuth` › `build_authorization_url` | CLI 內建的 client 設定 | 呼叫兩次 | 則1:網址的 `redirect_uri` 為 `https://sdk.cloud.google.com/applicationdefaultauthcode.html`<br>則2:網址有 `code_challenge` 且 `code_challenge_method=S256`<br>則3:`scope` 含 colaboratory<br>則4:兩次的 `state` 與 `code_challenge` 都不同 | 沒用 PKCE;或每次沿用同一個 `code_verifier` | FR-008 |
| US1-OA-02 | `GoogleOAuth` › `request_token` | 假 token 端點回 200,含 `access_token`、`refresh_token`、`expires_in`、`scope` | 以授權碼與同一次的 `code_verifier` 呼叫 | 則1:假端點收到 `grant_type=authorization_code`、`code`、`code_verifier`<br>則2:寫出的授權檔含 CLI 讀取所需的欄位(`refresh_token`、`client_id`、`client_secret`、`token_uri`)<br>則3:授權檔不在暫存資料夾以外的地方 | 沒帶 `code_verifier`;或寫出 CLI 讀不懂的格式,CLI 仍要求登入 | FR-008 |
| US1-OA-03 | `GoogleOAuth` › `request_token` | 假端點依序回 400 `{"error":"invalid_grant"}`、400 `{"error":"invalid_request"}`、401 `{"error":"invalid_client"}` | 各呼叫一次 | 則1:依序回 `OAUTH_INVALID_GRANT`、`OAUTH_INVALID_REQUEST`、`OAUTH_INVALID_CLIENT` | 所有 4xx 都歸成同一個代碼,UI 分不出是授權碼錯還是設定錯 | FR-008 |
| US1-OA-04 | `GoogleOAuth` › `request_token` | 情況 A 假端點回 200 但沒有 `refresh_token`;情況 B 回 200 但 `scope` 不含 colaboratory | 各呼叫一次 | 則1:情況 A 回 `OAUTH_BAD_RESPONSE`<br>則2:情況 B 回 `OAUTH_SCOPE_NOT_GRANTED`<br>則3:兩種情況都沒有寫出授權檔 | 沒有 refresh token 也存檔,一小時後授權就過期;或使用者取消勾選權限仍顯示已登入 | FR-008 |
| US1-OA-05 | `GoogleOAuth` › `request_token` | 情況 A 連線被拒;情況 B 逾時(注入 0.3 秒);情況 C 回 503 | 各呼叫一次 | 則1:依序回 `OAUTH_UNREACHABLE`、`OAUTH_TIMEOUT`、`OAUTH_SERVER_ERROR` | 連不到時拋未處理的例外,API 回 500 沒有原因 | FR-008 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-OA-06 | 正確性(替身與真 Google 一致)、易用性 | 📏 人工 | 登入頁 › 「取得授權連結」 → 登入頁 › 「送出」 | 延後到使用者在場時另跑(Q101、Q108),不在 P9 這一批;主機上直接跑本系統後端(uvicorn,UI 127.0.0.1:8780、Ollama 相容端點 127.0.0.1:11436),`CGB_DATA_DIR` 指到另一個新的暫存目錄(不沿用複製來的授權);真的 Google OAuth | 使用者在自己的瀏覽器開連結、登入、貼回授權碼;再取一次連結,貼回 `4/cgb-test-invalid` | 則1:貼回正確授權碼後 30 秒內登入頁顯示已登入<br>則2:`<暫存目錄>/data/colab-cli/token.json` 存在,權限 0600<br>則3:`HOME=<暫存目錄>/home colab usage` 印出三行用量(R2 待驗證:CLI 讀得到後端寫的授權檔)<br>則4:貼回 `4/cgb-test-invalid` 後頁面顯示登入失敗與原因,`POST` 的回應 `code` 為 `OAUTH_INVALID_GRANT`<br>則5:失敗之後「重新取得授權連結」可以按 | 替身照文件寫的 token 回應和真的不同,或後端寫出的 token.json CLI 讀不懂,自動化測試全綠、真的登入後 CLI 仍要求授權 | FR-008 | P5、P6、P8;不呼叫 Colab 執行環境,0 compute units,約 5 分鐘;token.json 不印出、不複製到暫存目錄以外,只記長度與 sha256 前 8 碼;使用者在場操作瀏覽器 | 判定者:使用者(登入是否完成、畫面是否顯示原因);腳本判定則2、則3;樣本:使用者的 Colab Pro 帳號一次(未用於調整) |

### 2.5 E4 資料庫(SQLite)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-DB-01 | SQLite › 寫入 `sessions` | `db` 模組建立的 schema;已有一筆 `active_slot=1`(`ready`) | 再插入一筆 `active_slot=1`;再插入一筆 `active_slot` 為 null 的 `ending` | 則1:第二筆 `active_slot=1` 丟出 `sqlite3.IntegrityError`<br>則2:`active_slot` 為 null 的那一筆插入成功 | `active_slot` 沒有 unique,兩個開啟中的工作階段寫得進去;或 null 也被當成重複,變更類型時寫不進新的 | FR-006 |
| US1-DB-02 | SQLite › 重新開啟連線 | 寫入一筆 `sessions` 與三筆 `session_transitions` | 關閉連線,以新的連線開同一個檔 | 則1:`PRAGMA journal_mode` 為 `wal`<br>則2:三筆 `session_transitions` 依 `at` 排序讀回,內容與寫入的相同 | 沒開 WAL;或交易沒 commit,重啟後紀錄不見 | FR-005、FR-028 |

### 2.6 E1 前端 UI(瀏覽器,原生 HTML/CSS/JS)

本故事沒有不靠後端就看得到的行為,這一節沒有案例;工作階段面板、登入頁與紀錄頁的行為都放在 2.11。

### 2.7 E3 Ollama 相容端點(FastAPI 轉送)

本故事沒有經 Ollama 相容端點的需求,這一節沒有案例(健康檢查不經這個端點,由 US1-API-37 驗證)。

### 2.8 E7 遠端 Ollama(Colab 執行環境上,Ollama API)

本故事只用到 `/api/version`(經 E6 的健康檢查)與 `/api/ps`(變更類型時記下已載入的模型),由 E2、E6 的案例經替身涵蓋;`RemoteOllama` 的案例在第 3、4 節,這一節沒有案例。

### 2.9 E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai)

本故事不涉及模型庫,這一節沒有案例。

### 2.10 E10 檔案系統、E11 部署與網路

本故事沒有只屬於這兩個端點的需求,這一節沒有案例;授權檔權限與持久化在第 6 節全域測試區。

### 2.11 跨端點驗收

真的瀏覽器接真的後端(測試行程內的 uvicorn,UI 127.0.0.1:8781,轉接層用替身,Q99 先採用),在 2.1~2.5 都完成後才開始;📏 案例改接真的 Colab。

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-AJ-01 | 首頁 › 「開啟」 | 沒有工作階段;三個步驟的替身各自等測試放行 | 打開首頁,不改類型,按「開啟」,依序放行三個步驟 | 則1:按下前類型選擇預設為 T4、不開高 RAM<br>則2:按下後不需重新整理就出現「開啟中」區塊,`#s-steps` 標出目前在「在 Colab 配置 T4 執行環境」<br>則3:放行後出現「就緒」區塊,`#r-type` 顯示 T4<br>則4:`FakeColabControl.create_session` 收到 `gpu=T4` | 前端沒有預選 T4,開啟送出空的 `runtimeType` 回 400;或狀態要重新整理才更新 | FR-001、FR-003、FR-009 |
| US1-AJ-02 | 首頁 › 「結束工作階段」 | 工作階段就緒 | 按「結束工作階段」,在確認畫面先按「取消」;再按一次並確認 | 則1:第一次按下後出現確認畫面(`[data-state="confirm-stop"]`)<br>則2:按「取消」後仍是「就緒」,`stop_session` 沒被呼叫<br>則3:確認後出現「已結束」,`#e-reason` 顯示「使用者結束」 | 沒有確認步驟,一按就結束;或取消後仍送出結束 | FR-002、FR-003 |
| US1-AJ-03 | 首頁 › 「開啟」 | `create_session` 回 `COLAB_ALLOCATION_REFUSED` | 按「開啟」 | 則1:出現「開啟失敗」區塊<br>則2:`#f-reason` 有繁體中文的原因,不是空白也不是代碼本身<br>則3:「開啟」按鈕可以再按 | 失敗後停在「開啟中」;或只顯示 `COLAB_ALLOCATION_REFUSED` 代碼 | FR-003 |
| US1-AJ-04 | 首頁 › 「開啟」 → 首頁 › 「重新開啟」 | 工作階段就緒 | `check_health` 失敗且 `list_sessions` 不再列出它;再按「重新開啟」 | 則1:不需重新整理就出現「失聯」區塊,結束原因顯示「被 Colab 收回」<br>則2:「重新開啟」可以按,按下後出現「開啟中」 | 收回後畫面仍顯示就緒;或失聯後沒有重新開啟的入口 | FR-003、FR-004 |
| US1-AJ-05 | 首頁 › 「開啟」 | 工作階段就緒 | `check_health` 失敗 1 次,重連第 2 輪成功 | 則1:出現「重連中」區塊<br>則2:之後回到「就緒」,`#r-name` 與重連前相同 | 重連中沒有顯示,使用者以為還在就緒;或重連後顯示成新的工作階段 | FR-004 |
| US1-AJ-06 | 首頁 › 「開啟」 | 工作階段就緒;重連時限 2 秒;`open_tunnel` 一直失敗;`stop_session` 回 `COLAB_STOP_UNCONFIRMED` | 讓重連逾時 | 則1:出現「失聯」區塊,結束原因含「重連逾時」<br>則2:出現釋放警告(`[data-state="release-failed"]`),文字含「沒辦法確認執行環境已經釋放」<br>則3:「再試一次釋放」可以按 | 釋放失敗的警告只在 API 有、畫面沒顯示,使用者不知道還在扣點 | FR-004、FR-007 |
| US1-AJ-07 | 首頁 › 「開啟」 | 同一個瀏覽器開兩個分頁,第一個分頁已按「開啟」、`create_session` 還沒放行 | 第二個分頁按「開啟」 | 則1:第二個分頁顯示「目前已有工作階段」<br>則2:`create_session` 只被呼叫 1 次 | 前端只靠自己的狀態擋,另一個分頁照樣送出;或 409 被當成一般錯誤顯示 | FR-006 |
| US1-AJ-08 | 首頁 › 「開啟」 → 登入頁 › 「取得授權連結」 → 登入頁 › 「送出」 | 未登入;`FakeGoogleOAuth.request_token` 會成功 | 在首頁按「開啟」;依引導到登入頁,按「取得授權連結」,在輸入框貼上 `4/cgb-test-code` 送出 | 則1:首頁按「開啟」後出現「開啟前要先登入 Colab」與往登入頁的連結,`create_session` 沒被呼叫<br>則2:登入頁出現授權連結 `#auth-link` 與授權碼輸入框<br>則3:送出後出現已登入(`[data-state="signed-in"]`)<br>則4:頁首 `#auth-chip` 顯示已登入 | 未登入時「開啟」照送,等 CLI 失敗才回報;或登入成功後頁首沒更新 | FR-008 |
| US1-AJ-09 | 登入頁 › 「送出」 | 已取得授權連結;`request_token` 回 `OAUTH_INVALID_GRANT` | 送出 `4/wrong`;再讓後端重建後以舊連結送出 | 則1:第一次出現登入失敗(`[data-state="failed"]`),有繁體中文原因<br>則2:第一次之後「重新取得授權連結」可以按<br>則3:第二次出現「授權連結已失效」(`[data-state="link-expired"]`),和第一次的文字不同 | 兩種失敗顯示同一句話,使用者不知道要重新取連結還是重貼授權碼 | FR-008 |
| US1-AJ-10 | 首頁 › 「開啟」 | 沒有工作階段 | 類型選 G4、勾高 RAM,按「開啟」並放行(Q166:L4 不支援高 RAM) | 則1:`create_session` 收到 `gpu=G4`、`high_mem=true`<br>則2:就緒區塊 `#r-type` 顯示 G4 與「高 RAM」 | 選擇器的值沒帶進請求;或就緒畫面固定顯示 T4 | FR-009 |
| US1-AJ-11 | 首頁 › 「變更類型」 | 工作階段就緒(T4),`qwen2.5:0.5b` 已載入 | 選 L4,按「變更類型」,在確認畫面按「確認,結束並重開」,放行全部步驟 | 則1:確認畫面有「會結束目前的工作階段並重開」<br>則2:確認後出現「開啟中」,步驟顯示結束原本的 T4 執行環境<br>則3:最後出現「就緒」,`#r-type` 顯示 L4<br>則4:模型頁 `#catalog` 顯示 `qwen2.5:0.5b` 已載入 | 沒有確認就直接重開;或重開後沒有重新下載並載入原本的模型 | FR-010 |
| US1-AJ-12 | 首頁 › 「變更類型」 | 工作階段就緒(T4);L4 的 `create_session` 回 `COLAB_ACCELERATOR_REJECTED` | 選 L4,確認變更 | 則1:出現「開啟失敗」,有繁體中文原因<br>則2:畫面說明原本的 T4 執行環境已經結束 | 失敗後畫面回到舊的就緒狀態(實際上已經關掉) | FR-010 |
| US1-AJ-13 | 紀錄頁 › 列表 | 經 API 開過三次(使用者結束、開啟失敗、目前就緒) | 打開紀錄頁 | 則1:`#rows` 有 3 列,依開啟時間由新到舊<br>則2:最舊那一列有開啟時間、結束時間、類型 T4、結束原因「使用者結束」,運行時長含「2 分」<br>則3:最新那一列結束時間是空的或「—」 | 紀錄頁只讀前端自己的狀態,重新整理就空了;或運行時長顯示秒數原始值 | FR-028 |
| US1-AJ-14 | 首頁 › 「開啟」 → 後端行程 › 重新啟動 | 工作階段就緒 | 停掉 uvicorn,以同一個 SQLite 檔與替身狀態重新起,重新整理首頁 | 則1:首頁顯示「就緒」,`#r-name` 與重建前相同<br>則2:`create_session` 總共只被呼叫 1 次 | 前端重新整理後顯示「未開啟」;或後端重建後另開一台 | FR-005 |
| US1-AJ-15 | 首頁 › 「開啟」 | 沒有工作階段;`list_sessions` 有一台 `[?]`、硬體 T4 | 打開首頁 | 則1:出現「不是本系統開啟的執行環境」提示(`[data-state="foreign"]`),含硬體 T4<br>則2:提示裡沒有結束那台的按鈕 | 把它顯示成本系統的工作階段,或提供結束按鈕 | 邊界情況 |
| US1-AJ-16 | 首頁 › 「停止開啟」 | 按「開啟」後 `create_session` 還沒放行 | 按「停止開啟」(`#cancel-open`),再放行 `create_session` | 則1:出現「結束中」<br>則2:放行後出現「已結束」<br>則3:`stop_session` 以這次的名稱被呼叫 | 開啟中沒有停止的入口;或停止後沒釋放已配置的執行環境 | 邊界情況、FR-007 |
| US1-AJ-23 | 首頁 › 「開啟」 → 後端行程 › 重新啟動 → 排程 › 健康檢查 | 測試行程內的 uvicorn(UI 8781),轉接層用替身;`CGB_SSH_IDENTITY_PATH`、`CGB_TUNNEL_LOCAL_PORT` 在重啟前後相同;SQLite 有目前 `ready` 的 `cgb-test-0001` 與已 `ended` 的 `cgb-test-0002`;`list_sessions` 列出 `[cgb-test-0001]` 與 `[cgb-test-0002]`;`stop_session(cgb-test-0002)` 回 `COLAB_STOP_UNCONFIRMED`;替身照 G-09 以真 adapter 的簽章綁定參數 | 首頁開到就緒後記下 `FakeTunnel.open_tunnel` 第一次收到的參數;停掉 uvicorn,以同一個 SQLite 檔與替身狀態重新起;接回就緒後讓 `check_health` 失敗 1 次、重連第 1 輪成功;再打開首頁 | 則1:重啟接回後 `GET /api/session` 的 `releaseWarning.message` 不為 null(Q161 先採用:掛在目前那筆工作階段)<br>則2:`releaseWarning.reasonCode` 為 `COLAB_STOP_UNCONFIRMED`<br>則3:首頁出現釋放警告(`[data-state="release-failed"]`)<br>則4:重啟接回與重連時 `open_tunnel` 收到的 `key_path` 都和第一次相同<br>則5:重啟接回與重連時 `open_tunnel` 收到的 `local_port` 都和第一次相同<br>則6:`state` 最後為 `ready`,`name` 仍是 `cgb-test-0001` | 重啟接回時釋放遺留失敗就默默略過,使用者不知道舊的那台還在扣點(FR-007);或重連只帶 `session_name`,真 adapter 會丟 TypeError、替身照單全收(Q159) | FR-004、FR-005、FR-007 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-AJ-17 | 效能(開啟時間)、可觀察性 | 📏 量測 | 首頁 › 「開啟」 | 容器 `docker compose -p cgb-test` 已起,UI 8780、Ollama 相容端點 11436;已登入(照 P9 複製來的 token.json);真的 Colab、CLI、ssh、遠端 Ollama;沒有 `cgb-test-` 執行環境 | Playwright 打開 `http://127.0.0.1:8780`,類型 T4,按「開啟」,每秒記錄一次 `#s-steps` 的目前步驟,直到「就緒」 | 則1:從按下到「就緒」在 5 分鐘內(SC-001)<br>則2:就緒前記錄到的步驟依序包含配置、安裝並啟動 Ollama、建立 SSH 通道、確認模型服務有回應<br>則3:就緒時 `curl http://127.0.0.1:11436/api/version` 回 200<br>則4:`colab sessions` 列出 `[cgb-test-…]`、硬體 T4 | 開啟流程在真實延遲下串錯步驟或卡在某一步;或就緒判定沒有真的確認模型服務 | FR-001、NFR-001、SC-001 | P1~P9;開 1 台 T4(之後的 US2-AJ-02 到 US1-AJ-19 都用這一台,不在本案例結束);本案例約 3 分鐘、約 0.06 compute units;`.env` 只設 `CGB_HOST_DATA=<暫存目錄>/data`、`CGB_HOST_UI_PORT=8780`、`CGB_HOST_OLLAMA_PORT=11436`、`CGB_BIND_ADDR=127.0.0.1` | 判定者:腳本(5 分鐘門檻);樣本:一次實跑(未用於調整) |
| US1-AJ-18 | 可用性(斷線重連) | 📏 量測 | 實跑操作 › 殺掉 ssh → 首頁 › 「開啟」 | US1-AJ-17 的工作階段就緒,`qwen2.5:0.5b` 已載入(US2-AJ-02 之後) | `docker exec` 在容器內以 SIGKILL 殺掉命令列含 `ProxyCommand=colab ssh --proxy-mode -s cgb-test-` 的 ssh 行程,每 5 秒讀一次 `GET /api/session` | 則1:殺掉後 1 分鐘內 `state` 為 `reconnecting`(SC-002)<br>則2:之後 5 分鐘內回到 `ready`,`name` 與殺掉前相同<br>則3:回到 `ready` 後經 11436 的 `/api/ps` 仍有 `qwen2.5:0.5b`<br>則4:`colab sessions` 的 `cgb-test-` 執行環境仍是 1 台 | 真的 ssh 斷線後健康檢查沒察覺(例如只看行程物件,行程被別人殺掉沒更新);或重連時另開一台 | FR-004、NFR-002、SC-002 | P1~P9;沿用同一台 T4,約 3 分鐘、約 0.06 compute units;只殺符合 `cgb-test-` 命令列的 ssh,不用 `pkill ssh` | 判定者:腳本(1 分鐘與 5 分鐘門檻);樣本:一次實跑(未用於調整) |
| US1-AJ-19 | 可用性(後端重啟) | 📏 量測 | 實跑操作 › `docker compose restart` → 首頁 › 「開啟」 | US1-AJ-18 之後,工作階段就緒 | `docker compose -p cgb-test restart cgb`,每 5 秒讀一次 `GET /api/session` | 則1:重啟後 2 分鐘內 `state` 為 `ready`,`name` 與重啟前相同<br>則2:重啟前後 `colab sessions` 的 `cgb-test-` 執行環境都是 1 台、名稱相同 | 後端重啟後把工作階段當成不存在或另開一台;或 CLI 狀態檔沒持久化使名稱變成 `[?]` | FR-005 | P1~P9;沿用同一台 T4,約 3 分鐘、約 0.06 compute units;只 restart `cgb-test` 這個 project | 判定者:腳本;樣本:一次實跑(未用於調整) |
| US1-AJ-20 | 正確性(變更類型) | 📏 量測 | 首頁 › 「變更類型」 | US1-AJ-19 之後,工作階段就緒(T4),`/api/ps` 只有 `qwen2.5:0.5b`(US3-AJ-12 以 `keep_alive:0` 推論,`qwen2.5:7b` 不留在記憶體) | 在首頁勾「高 RAM」、按「變更類型」並確認,等到「就緒」與重新下載完成 | 則1:原本的名稱在 1 分鐘內從 `colab sessions` 消失<br>則2:新的名稱在 `colab sessions` 的形狀是 `High-RAM`、硬體 T4<br>則3:新的工作階段就緒後 5 分鐘內,經 11436 的 `/api/ps` 有 `qwen2.5:0.5b`<br>則4:`GET /api/sessions` 裡舊的那筆 `endReason` 為 `RUNTIME_TYPE_CHANGED` | 真的 CLI 下高 RAM 旗標沒帶進命令列;或重新下載只下載不預先載入 | FR-010、SC-003 | P1~P9;結束 T4、開 1 台 T4 高 RAM(Q102 先採用,不用 L4);本案例約 5 分鐘、約 0.1 compute units;只重新下載 `qwen2.5:0.5b`;若 `/api/ps` 意外有 `qwen2.5:7b`,照實記錄並讓它一起重新下載,時間另計 | 判定者:腳本;樣本:一次實跑(未用於調整) |
| US1-AJ-21 | 資源釋放 | 📏 量測 | 首頁 › 「結束工作階段」 | US1-AJ-20 的 T4 高 RAM 工作階段就緒 | 在首頁按「結束工作階段」並確認,每 5 秒執行一次 `colab sessions` | 則1:按下後 1 分鐘內 `colab sessions` 沒有這個名稱(SC-003)<br>則2:首頁顯示「已結束」與「使用者結束」 | 只關通道沒結束執行環境;或回讀的時間不夠就宣布結束 | FR-002、FR-007、SC-003 | P1~P9;結束 1 台,約 2 分鐘、約 0.04 compute units | 判定者:腳本(1 分鐘門檻);樣本:一次實跑(未用於調整) |
| US1-AJ-22 | 可用性(收回偵測) | 📏 量測 | 首頁 › 「開啟」 → 實跑操作 › 另開終端機 `colab stop` | 沒有工作階段 | 開一台 T4 到就緒;另開終端機以 `HOME=<暫存目錄>/home colab stop -s <這個名稱>` 模擬被 Colab 收回(Q103 先採用),每 5 秒讀一次 `GET /api/session` | 則1:`colab stop` 回來後 2 分鐘內 `state` 為 `lost`(SC-002)<br>則2:`endReason` 為 `RECLAIMED_BY_COLAB`<br>則3:首頁顯示「失聯」與「重新開啟」 | 真實環境下健康檢查失敗後沒有查 `colab sessions`,一直重連到 5 分鐘才失聯 | FR-004、NFR-002、SC-002 | P1~P9;開 1 台 T4 後由終端機結束,約 5 分鐘、約 0.1 compute units;`colab stop` 只帶這次的 `cgb-test-` 名稱;容器內與終端機共用 `<暫存目錄>/data/colab-cli` | 判定者:腳本(2 分鐘門檻);樣本:一次實跑(未用於調整) |

### 2.12 交給 `/tdd` 的順序

每個案例在 `tasks.md` 是一組紅燈、綠燈任務;每一節的案例都做完後,接一個重構任務。同一個故事的端點節彼此平行,跨端點驗收在端點節都完成後才開始。📏 案例對應 📏 任務,照第 1 節 P9 的順序在使用者同意後一次跑完。

1. E2 後端 UI API:US1-API-01 → US1-API-02 → … → US1-API-40 → 重構
2. E5 Colab CLI:US1-CLI-01 → US1-CLI-02 → … → US1-CLI-20 → US1-CLI-22 → US1-CLI-23 → … → US1-CLI-41 → 重構;US1-CLI-21 為 📏 任務
3. E6 SSH 通道:US1-TUN-01 → US1-TUN-02 → … → US1-TUN-09 → US1-TUN-11 → US1-TUN-12 → … → US1-TUN-20 → 重構;US1-TUN-10 為 📏 任務
4. E9 Google OAuth:US1-OA-01 → US1-OA-02 → … → US1-OA-05 → 重構;US1-OA-06 為 📏 任務
5. E4 資料庫:US1-DB-01 → US1-DB-02 → 重構
6. E1 前端 UI、E3、E7、E8、E10、E11:本故事沒有案例
7. 跨端點驗收(2.1~2.5 完成後):US1-AJ-01 → US1-AJ-02 → … → US1-AJ-16 → US1-AJ-23 → 重構;US1-AJ-17~US1-AJ-22 為 📏 任務

## 3. 使用者故事 2 - 透過固定的 Ollama 相容端點使用遠端模型(P1)

**本故事的需求**:FR-011~FR-013;NFR-003、NFR-004;邊界情況:變更類型的過程中端點收到請求、Ollama 相容端點正在串流回應時連線中斷
**本故事涵蓋的全域 NFR**:NFR-010(彙整見第 6 節)

### 3.1 E3 Ollama 相容端點(FastAPI 轉送)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US2-OC-01 | Ollama 端點 › `POST /api/generate` | 工作階段就緒;`FakeRemoteOllama` 對 `generate` 依序送 3 行 NDJSON,第 2、3 行之前各等測試放行;本案例用 uvicorn(Q97 先採用) | 用 httpx 串流讀 `POST /api/generate {model:"qwen2.5:0.5b",prompt:"你好"}` | 則1:放行第 2 行之前,用戶端已讀到第 1 行<br>則2:三行全部讀到後,用戶端收到的位元組與假伺服器送出的完全相同<br>則3:回應的 `Content-Type` 是 `application/x-ndjson` | 用 `r.aread()` 讀完整份再回,串流變成一次傳回;或改寫了 NDJSON 內容 | FR-011 |
| US2-OC-02 | Ollama 端點 › `POST /api/generate` | 工作階段就緒;假伺服器對 `stream:false` 回一個 JSON 與標頭 `X-Cgb-Test: 1` | 送 `POST /api/generate?x=1 {model:"qwen2.5:0.5b",prompt:"你好",stream:false}`,帶 `Connection: keep-alive` | 則1:用戶端收到的狀態碼、本文與假伺服器回的相同<br>則2:用戶端收到標頭 `X-Cgb-Test: 1`<br>則3:假伺服器收到的 query 是 `x=1`,`Host` 是轉發位址<br>則4:假伺服器收到的標頭沒有 `Connection` | 沒轉 query 或改寫本文;或 hop-by-hop 標頭照轉 | FR-011 |
| US2-OC-03 | Ollama 端點 › `GET /api/tags` | 工作階段就緒 | 依序送 `GET /`、`HEAD /`、`GET /api/version`、`GET /api/tags`、`GET /api/ps`、`POST /api/show`、`POST /api/chat`、`POST /api/embed`、`POST /api/embeddings`(parametrize) | 則1:每一個請求,假伺服器都收到相同的方法、路徑與本文<br>則2:每一個請求,用戶端收到的狀態碼與本文都和假伺服器回的相同 | 白名單漏了 `HEAD /`(有些用戶端用它檢查存活)或 `/api/embeddings` | FR-011 |
| US2-OC-04 | Ollama 端點 › 管理操作 | 工作階段就緒 | 依序送 `POST /api/pull`、`POST /api/push`、`POST /api/create`、`POST /api/copy`、`DELETE /api/delete`、`HEAD /api/blobs/sha256:00`、`POST /api/blobs/sha256:00`(parametrize) | 則1:每一個都回 403<br>則2:每一個本文都是 `{"error": ...}`,`error` 是繁體中文且含「UI」<br>則3:假伺服器一個請求都沒收到 | 只擋 R8 的五個路徑,`/api/blobs` 照轉;或回 403 前已經轉送 | FR-012 |
| US2-OC-05 | Ollama 端點 › 管理操作 | 沒有工作階段 | 送 `POST /api/pull {model:"qwen2.5:0.5b"}` | 則1:回 403,不是 503<br>則2:`error` 含「UI」 | 先判斷有沒有工作階段才判斷路徑,管理操作在沒有工作階段時回「沒有可用的工作階段」 | FR-012、FR-013 |
| US2-OC-06 | Ollama 端點 › 白名單外 | 工作階段就緒 | 送 `POST /v1/chat/completions` 與 `GET /api/me` | 則1:兩個都回 404,`error` 是繁體中文<br>則2:假伺服器沒收到請求 | 用黑名單轉送,`/v1/*` 被轉到遠端(等於另外提供 OpenAI 相容 API) | FR-011 |
| US2-OC-07 | Ollama 端點 › `POST /api/generate` | 沒有工作階段;假伺服器若收到請求會睡 5 秒 | 送 `POST /api/generate {model:"qwen2.5:0.5b",prompt:"你好"}` | 則1:1 秒內回 503<br>則2:`error` 含「沒有可用的工作階段」<br>則3:假伺服器沒收到請求 | 沒有工作階段時仍往轉發位址送,等連線逾時才回錯誤 | FR-013、SC-007 |
| US2-OC-08 | Ollama 端點 › `POST /api/chat` | 情況 A 工作階段 `opening`;情況 B `reconnecting`;情況 C `ending` | 各送一次 `POST /api/chat` | 則1:三種情況都在 1 秒內回 503<br>則2:三種情況假伺服器都沒收到請求 | 只把 `none` 當成沒有工作階段,重連中照樣轉送、排隊等通道回來 | FR-013 |
| US2-OC-09 | Ollama 端點 › `GET /api/version` | 第一個工作階段就緒時假伺服器 A 回 `{"version":"cgb-test-a"}`;結束後開第二個,假伺服器換成 B 回 `{"version":"cgb-test-b"}` | 第一個就緒時送一次 `GET /api/version`;第二個就緒後用同一個用戶端物件再送一次 | 則1:第一次回 `cgb-test-a`<br>則2:第二次回 `cgb-test-b` | 轉發目標在啟動時就固定成第一個工作階段的連線,新的工作階段要重啟才接得上 | FR-011 |
| US2-OC-10 | `/api/session` › 變更類型 → Ollama 端點 › `POST /api/generate` | 工作階段就緒;`create_session`(新類型)等測試放行 | 送 `POST /api/session/restart`,在 `step` 為 `ending_previous` 與 `allocating` 時各送一次 `POST /api/generate` | 則1:兩次都在 1 秒內回 503<br>則2:`error` 含「沒有可用的工作階段」 | 變更類型時把請求排隊等新的工作階段就緒 | 邊界情況、FR-013 |
| US2-OC-11 | Ollama 端點 › `POST /api/generate` → 排程 › 健康檢查 | 工作階段就緒;假伺服器送 2 行 NDJSON 後直接關閉連線;`FakeTunnel.check_health` 回 `TUNNEL_UNREACHABLE` | 串流讀 `POST /api/generate` | 則1:用戶端讀到 2 行後,最後多一行 `{"error": ...}`,`error` 含「串流中斷」<br>則2:斷線後 0.2 秒內 `FakeTunnel.check_health` 被呼叫(不等下一個排程)<br>則3:之後 `GET /api/session` 的 `state` 為 `reconnecting` | 串流中斷時靜默關閉,用戶端以為回應結束;或直接標失聯 | 邊界情況、FR-004 |
| US2-OC-12 | Ollama 端點 › `POST /api/generate` → `/api/session` › 結束 | 工作階段就緒;假伺服器送 1 行後等測試放行 | 串流讀 `POST /api/generate`,讀到第 1 行後送 `DELETE /api/session` | 則1:用戶端最後一行的 `error` 含「工作階段已結束」<br>則2:最後一行的 `error` 不含「串流中斷」<br>則3:`check_health` 沒有因為這次中斷被額外呼叫 | 使用者結束造成的中斷被當成非預期斷線,觸發重連 | FR-013 |
| US2-OC-13 | Ollama 端點 › `POST /api/generate` | 工作階段就緒;假伺服器的 port 已關閉 | 送 `POST /api/generate` | 則1:回 502<br>則2:`error` 是繁體中文,不含 `127.0.0.1` | 連不到時回 500 與 Python 例外文字 | FR-011 |
| US2-OC-14 | Ollama 端點 › `POST /api/chat` | 工作階段就緒 | 帶 `Origin: http://192.168.0.50:3000` 送 `POST /api/chat` | 則1:假伺服器收到的 `Origin` 是 `http://192.168.0.50:3000` | 轉送時丟掉或改寫 `Origin` | FR-011 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US2-OC-15 | 安全(不暴露遠端) | 🔴🟢 行為測試 | Ollama 端點 › `GET /api/tags` | 工作階段就緒;假伺服器回 302 與 `Location: http://127.0.0.1:11435/x` | 送 `GET /api/tags`,另送一次 `POST /api/generate` 讓假伺服器回 500 | 則1:用戶端收到的任何標頭與本文都不含轉發位址的 port(本案例的假伺服器 port)<br>則2:本系統自己產生的錯誤 `error` 不含 `127.0.0.1` | 把遠端的轉址照樣傳回,讓用戶端知道並嘗試直連轉發位址;或錯誤訊息帶出轉發位址 | NFR-003、NFR-010 | — | — |

### 3.2 E7 遠端 Ollama(Colab 執行環境上,Ollama API)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US2-RO-01 | `RemoteOllama` › `get_version` | 假伺服器情況 A 回 200 `{"version":"0.40.15"}`;B 回 200 `<html>`;C port 關閉;D 6 秒不回(逾時注入 0.3 秒) | 各呼叫一次 | 則1:依序回 `0.40.15`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_UNREACHABLE`、`OLLAMA_TIMEOUT` | 不檢查 JSON 就回成功;或逾時沒設,健康檢查卡住 | FR-011 |
| US2-RO-02 | `RemoteOllama` › `generate` | 假伺服器情況 A 回 404 `{"error":"model 'x' not found"}`;B 回 400;C 回 500;D 串流 2 行後關閉、沒有 `done:true` | 各呼叫一次 | 則1:依序回 `OLLAMA_NOT_FOUND`、`OLLAMA_BAD_REQUEST`、`OLLAMA_SERVER_ERROR`、`OLLAMA_STREAM_INTERRUPTED`<br>則2:情況 A 的結果保留遠端的英文 `error` 原文 | 串流中斷當成正常結束;或 404 與 500 不分 | FR-011 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US2-RO-03 | 正確性(替身與真 Ollama 一致) | 📏 量測 | `RemoteOllama` › `get_version` → `RemoteOllama` › `pull_model` → `RemoteOllama` › `generate` → `RemoteOllama` › `list_loaded_models` | 主機階段,US1-CLI-21 開好並啟動 Ollama 的 `cgb-test-<時間>-adapter`,經 `Tunnel.open_tunnel` 建立本機轉發(真的遠端 Ollama 0.40.x) | 依序呼叫 `get_version`、`list_local_models`、`pull_model qwen2.5:0.5b`、`pull_model qwen2.5:cgb-test-nonexistent`、`generate`(非串流與串流各一次,`num_predict` 8)、`list_loaded_models`、帶 `Origin: http://192.168.0.50:3000` 的 `chat`、`generate` 指名 `qwen2.5:7b`(還沒下載) | 則1:`get_version` 回含 `version` 的 JSON<br>則2:`pull qwen2.5:0.5b` 的每一行都符合 `components.schemas.PullProgress`,最後一行 `status` 為 `success`<br>則3:`pull qwen2.5:cgb-test-nonexistent` 回 HTTP 200,串流裡的 error 含 `file does not exist`,轉接層回 `OLLAMA_NOT_FOUND`(Q3)<br>則4:兩次 `generate` 都成功,串流的最後一行 `done` 為 true<br>則5:`list_loaded_models` 有 `qwen2.5:0.5b`<br>則6:帶 `Origin` 的 `chat` 回 200(`OLLAMA_ORIGINS=*` 生效,Q20)<br>則7:指名 `qwen2.5:7b` 回 404,轉接層回 `OLLAMA_NOT_FOUND`,`list_local_models` 仍沒有 `qwen2.5:7b`<br>則8:假伺服器劇本裡每一種回應,和這次錄到的對應回應有相同的欄位名稱 | 假 Ollama 照文件想像寫,和 0.40.x 真的 pull 錯誤格式或 CORS 行為不同,自動化測試全綠、接上真的就分錯失敗原因 | FR-011、FR-016、FR-017 | P1~P9;與 US1-CLI-21 共用同一台 T4,本案例約 3 分鐘,占用算在 US1-CLI-21 的 0.21 compute units 之內;只下載 `qwen2.5:0.5b`;本機轉發只綁 127.0.0.1 | 判定者:腳本;樣本:一次實跑(未用於調整) |

### 3.3 E6 SSH 通道(OpenSSH 與 `colab ssh --proxy-mode`)

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US2-TUN-01 | 安全(不暴露遠端) | 🔴🟢 行為測試 | `Tunnel` › `open_tunnel` | 金鑰就緒;假 `ssh` 常駐 | 以 `localPort=11435` 呼叫 | 則1:argv 裡所有 `-L` 的綁定位址都是 `127.0.0.1`<br>則2:argv 沒有 `-g`、`-R`、`-D`<br>則3:argv 沒有 `GatewayPorts` | 轉發綁 `0.0.0.0` 或加 `-g`,區網任何裝置都能繞過本系統直連遠端 Ollama | NFR-003 | — | — |

### 3.4 E5 Colab CLI(google-colab-cli,外部程式)

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US2-CLI-01 | 安全(不暴露遠端) | 🔴🟢 行為測試 | `ColabControl` › `start_ollama` | 假 `colab exec` 印成功的 `CGB-RESULT` | 呼叫;讀本系統提供的初始化腳本內容 | 則1:argv 的 `OLLAMA_HOST` 值是 `127.0.0.1:11434`<br>則2:初始化腳本沒有 `0.0.0.0`,也沒有 cloudflared、ngrok、localtunnel 等字樣 | 為了方便除錯把 Ollama 綁 `0.0.0.0`,或在腳本裡開公開通道 | NFR-003 | — | — |

### 3.5 E2 後端 UI API、E4 資料庫、E8、E9、E10、E11

本故事的請求只經 Ollama 相容端點,不涉及 UI API、資料庫、模型庫、登入與部署;這一節沒有案例(區網開放在第 6 節 G-01)。

### 3.6 E1 前端 UI(瀏覽器,原生 HTML/CSS/JS)

本故事沒有畫面,這一節沒有案例。

### 3.7 跨端點驗收

真的區網程式(httpx;📏 案例另用桌機已有的 `ollama` 指令)接真的後端,在 3.1~3.4 都完成後才開始。

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US2-AJ-01 | 首頁 › 「開啟」 → 區網程式 › `POST /api/generate` | 測試行程內的 uvicorn(UI 8781、Ollama 相容端點 11437),轉接層用替身;`FakeRemoteOllama` 對 `generate` 回 `{"response":"cgb-test-ok"}` | 在首頁按「開啟」到就緒,用 httpx 對 `127.0.0.1:11437` 送 `POST /api/generate {stream:false}`;在首頁結束工作階段後再送一次 | 則1:就緒時那一次回 200,`response` 為 `cgb-test-ok`<br>則2:結束後那一次在 1 秒內回 503,`error` 含「沒有可用的工作階段」 | UI 開啟的工作階段和 Ollama 相容端點看到的不是同一份狀態(兩個 uvicorn 各自一份) | FR-011、FR-013 |
| US2-AJ-05 | 首頁 › 「開啟」 → 後端行程 › 重新啟動 → 排程 › 健康檢查 → 區網程式 › `POST /api/generate` | 測試行程內的 uvicorn(UI 8781、Ollama 相容端點 11437),轉接層用替身;`CGB_TUNNEL_LOCAL_PORT` 在重啟前後相同;轉發目標是可以回 `cgb-test-ok` 的假 Ollama(實作時依 US2-AJ-01 的做法) | 首頁開到就緒;停掉 uvicorn,以同一個 SQLite 檔與替身狀態重新起;接回就緒後用 httpx 對 `127.0.0.1:11437` 送 `POST /api/generate {stream:false}`;再讓 `check_health` 失敗 1 次、重連第 1 輪成功後再送一次 | 則1:重啟接回後那一次回 200,`response` 為 `cgb-test-ok`<br>則2:重連後那一次回 200<br>則3:兩次之間 `GET /api/session` 的 `state` 最後為 `ready` | 重啟接回或重連後沒寫回轉發位址,UI 顯示就緒、端點卻一直回 503(Q170) | FR-005、FR-011 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US2-AJ-02 | 效能(轉送延遲)、相容性 | 📏 量測 | 區網程式 › `POST /api/generate` | 容器階段,US1-AJ-17 的工作階段就緒;經 UI 預先載入 `qwen2.5:0.5b` | 交替送 20 次非串流 `POST /api/generate {model:"qwen2.5:0.5b",prompt:"你好",stream:false,options:{num_predict:8,seed:1,temperature:0}}`:10 次到 `127.0.0.1:11436`,10 次在容器內(`docker exec`)直接打轉發 `127.0.0.1:11435`;再以 `OLLAMA_HOST=http://127.0.0.1:11436 ollama list` 與 `ollama run qwen2.5:0.5b 你好` 各一次 | 則1:經本系統的平均延遲減直連的平均延遲不超過 0.5 秒(SC-005)<br>則2:`ollama list` 列出 `qwen2.5:0.5b`<br>則3:`ollama run` 印出非空的回應 | 轉送時緩衝或每次重新建立 httpx 連線,延遲增加超過門檻;或回應格式被改寫,標準的 Ollama 用戶端讀不懂 | FR-011、NFR-004、SC-005 | P1~P9;沿用 US1-AJ-17 的 T4,約 3 分鐘、約 0.06 compute units;`ollama` 指令一律帶 `OLLAMA_HOST=http://127.0.0.1:11436`,不連 11434 | 判定者:腳本(0.5 秒門檻);樣本:20 次請求(未用於調整) |
| US2-AJ-03 | 效能(沒有工作階段時的錯誤) | 📏 量測 | 區網程式 › `POST /api/generate` | 容器階段一開始,真的 uvicorn(不經 ASGI transport),沒有工作階段 | 連續送 10 次 `POST /api/generate` 到 `127.0.0.1:11436`,各記延遲 | 則1:10 次都回 503<br>則2:10 次中最長的延遲不超過 1 秒(SC-007)<br>則3:`error` 含「沒有可用的工作階段」 | 真的伺服器下仍去連轉發位址,等 TCP 逾時才回 | FR-013、SC-007 | P5、P6;不開執行環境,0 compute units,約 1 分鐘 | 判定者:腳本(1 秒門檻);樣本:10 次請求(未用於調整) |
| US2-AJ-04 | 安全(不暴露遠端) | 📏 量測 | 實跑操作 › 讀監聽位址 → 區網程式 › `GET /api/version` | 容器階段,US1-AJ-17 的工作階段就緒 | 以 `colab exec -s <名稱> -f tests/realrun/scripts/listen_check.py`(只讀的腳本,印出 `ss -ltn` 的結果)讀執行環境的監聽位址;`docker port cgb-test-cgb-1`;從桌機主機對 `127.0.0.1:11435` 送 `GET /api/version` | 則1:執行環境上 11434 只聽 `127.0.0.1`<br>則2:`docker port` 只有 8780 與 11434(對應主機 11436),沒有 11435<br>則3:主機對 `127.0.0.1:11435` 連不上<br>則4:`GET /api/session` 與首頁 HTML 不含任何 `colab` 執行環境的網址 | 遠端 Ollama 綁 `0.0.0.0`,或部署時把轉發 port 發布出來,讓區網裝置繞過本系統 | NFR-003 | P1~P9;沿用 US1-AJ-17 的 T4,約 2 分鐘、約 0.04 compute units;遠端腳本只讀不寫,不安裝任何東西 | 判定者:腳本;樣本:一次實跑(未用於調整) |

### 3.8 交給 `/tdd` 的順序

每個案例在 `tasks.md` 是一組紅燈、綠燈任務;每一節的案例都做完後,接一個重構任務。同一個故事的端點節彼此平行,跨端點驗收在端點節都完成後才開始。

1. E3 Ollama 相容端點:US2-OC-01 → US2-OC-02 → … → US2-OC-15 → 重構
2. E7 遠端 Ollama:US2-RO-01 → US2-RO-02 → 重構;US2-RO-03 為 📏 任務
3. E6 SSH 通道:US2-TUN-01 → 重構
4. E5 Colab CLI:US2-CLI-01 → 重構
5. E1、E2、E4、E8、E9、E10、E11:本故事沒有案例
6. 跨端點驗收(3.1~3.4 完成後):US2-AJ-01 → US2-AJ-05 → 重構;US2-AJ-02~US2-AJ-04 為 📏 任務

## 4. 使用者故事 3 - 挑選要下載的模型並使用執行環境上的模型目錄(P2)

**本故事的需求**:FR-014~FR-018、FR-020~FR-022(FR-019、FR-023 已移除);NFR-005~NFR-007;邊界情況:執行環境被收回或結束時模型消失、佇列保留;遠端磁碟或顯示記憶體不足以載入;兩個程式同時指名同一個尚未載入的模型
**本故事涵蓋的全域 NFR**:無(彙整見第 6 節)

### 4.1 E2 後端 UI API(FastAPI REST 與 SSE)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US3-API-01 | `/api/models` › 列出目錄 | 工作階段就緒;`FakeRemoteOllama` 的 tags 有 `qwen2.5:0.5b` 與 `qwen2.5:7b`,ps 只有 `qwen2.5:0.5b` | 送 `GET /api/models` | 則1:回 2 個模型,`sizeBytes` 分別是 397821319 與 4683087332<br>則2:`qwen2.5:0.5b` 的 `loaded` 為 true<br>則3:`qwen2.5:7b` 的 `loaded` 為 false | 只讀 tags 沒讀 ps,全部顯示未載入;或大小用約略值 | FR-014 |
| US3-API-02 | `/api/models` › 列出目錄 | 工作階段 `reconnecting` | 送 `GET /api/models` | 則1:回 503,`code` 為 `NO_READY_SESSION`<br>則2:`FakeRemoteOllama` 沒收到請求 | 重連中仍去連轉發位址,等逾時回 504 | FR-014 |
| US3-API-03 | `/api/models` › 預先載入 | 工作階段就緒;`qwen2.5:7b` 在 tags、不在 ps;假伺服器的 `generate` 等測試放行 | 送 `POST /api/models/preload {name:"qwen2.5:7b"}`,再放行 | 則1:回 202,這個模型的 `preload.state` 為 `loading`<br>則2:假伺服器收到的 `generate` 本文只有 `model:"qwen2.5:7b"` 與 `keep_alive:-1`,沒有 `prompt`<br>則3:放行後 SSE `models.updated` 裡 `qwen2.5:7b` 的 `loaded` 為 true | 用一個真的 prompt 預熱(多花時間、產生輸出);或 `keep_alive` 用預設 5 分鐘,過一下又被卸載 | FR-015 |
| US3-API-04 | `/api/models` › 預先載入 | 工作階段就緒;tags 沒有 `qwen2.5:7b` | 送 `POST /api/models/preload {name:"qwen2.5:7b"}` | 則1:回 404,`code` 為 `OLLAMA_NOT_FOUND`<br>則2:假伺服器沒收到 `pull` | 目錄沒有的模型就順手下載 | FR-015、FR-016 |
| US3-API-05 | `/api/models` › 預先載入 | 工作階段就緒;ps 有 `qwen2.5:0.5b`;假伺服器對 `qwen2.5:7b` 的 `generate` 回 500 `{"error":"model requires more system memory"}` | 送 `POST /api/models/preload {name:"qwen2.5:7b"}` | 則1:`qwen2.5:7b` 的 `preload.state` 變成 `failed`,`reasonCode` 為 `OLLAMA_SERVER_ERROR`<br>則2:`GET /api/models` 的 `qwen2.5:0.5b` 仍是 `loaded: true` | 載入失敗時把整個目錄標成錯誤,或清掉其他模型的已載入狀態 | 邊界情況、FR-015 |
| US3-API-06 | `/api/models` › 預先載入 | 工作階段就緒;`generate` 等測試放行 | 對 `qwen2.5:7b` 連送兩次預先載入 | 則1:兩次都回 202<br>則2:假伺服器只收到 1 次 `generate` | 每按一次就送一次載入 | FR-015 |
| US3-API-07 | `/api/downloads` › 加入 → `/api/models` › 列出目錄 | 工作階段就緒;`FakeModelLibrary` 的 manifest 有 `qwen2.5:7b`;假伺服器的 `pull` 每 0.1 秒送一行進度,共 30 行,最後 `success`;tags 在 `success` 之後才加上 `qwen2.5:7b` | 送 `POST /api/downloads {models:["qwen2.5:7b"]}`,同時訂閱 SSE | 則1:回 201,這一筆 `state` 為 `queued` 或 `downloading`<br>則2:下載中 `download.updated` 每秒最多 1 則,`progress` 遞增<br>則3:下載中 `GET /api/models` 沒有 `qwen2.5:7b`<br>則4:`success` 後這一筆 `state` 為 `completed`,`GET /api/models` 有 `qwen2.5:7b` | 每一行進度都推一則事件;或下載中就把名稱放進目錄 | FR-017、FR-018 |
| US3-API-08 | `/api/downloads` › 加入 | 工作階段就緒;`FakeModelLibrary.get_manifest` 對 `qwen2.5:cgb-test-nonexistent` 回 `LIBRARY_NOT_FOUND` | 送 `POST /api/downloads {models:["qwen2.5:cgb-test-nonexistent"]}` | 則1:回 404,`code` 為 `LIBRARY_NOT_FOUND`,`model` 為 `qwen2.5:cgb-test-nonexistent`<br>則2:`GET /api/downloads` 沒有這一筆<br>則3:假伺服器沒收到 `pull` | 不先查模型庫就排進佇列,等 pull 失敗才發現 | FR-017 |
| US3-API-09 | `/api/downloads` › 加入 | 工作階段就緒;情況 A 假伺服器的 `pull` 串流出現 `{"error":"pull model manifest: file does not exist"}`;情況 B 出現 `{"error":"no space left on device"}` | 各加入一個模型 | 則1:情況 A 那一筆 `state` 為 `failed`、`reasonCode` 為 `OLLAMA_NOT_FOUND`<br>則2:情況 B 那一筆 `reasonCode` 為 `OLLAMA_PULL_FAILED`<br>則3:兩種情況之後 `GET /api/models` 和加入前相同 | pull 回 HTTP 200 就當成功;或不分失敗原因 | FR-017 |
| US3-API-10 | `/api/downloads` › 加入 | 工作階段就緒;假伺服器記錄每次 `pull` 的開始與結束時間 | 一次送 `POST /api/downloads {models:["qwen2.5:0.5b","qwen2.5:7b","qwen2.5:1.5b"]}` | 則1:三筆依加入順序下載,第 2 筆的 `pull` 在第 1 筆 `success` 之後才開始<br>則2:第 3 筆的 `pull` 在第 2 筆 `success` 之後才開始<br>則3:三筆最後都是 `completed` | 三個 pull 同時送出,搶頻寬與磁碟,也無法逐一顯示狀態 | FR-021 |
| US3-API-11 | `/api/downloads` › 移除 | 佇列有三筆:第 1 筆下載中、第 2、3 筆排隊中 | 送 `DELETE /api/downloads/<第 3 筆>`,再送 `DELETE /api/downloads/<第 1 筆>` | 則1:第一個回 204,SSE 收到 `download.removed`<br>則2:第 3 筆的 `pull` 從頭到尾沒被送出<br>則3:第二個回 409,`code` 為 `DOWNLOAD_IN_PROGRESS`,第 1 筆仍在下載 | 取消排隊中的項目時連正在下載的一起中斷;或正在下載的也能取消、留下半個模型 | FR-021 |
| US3-API-12 | `/api/downloads` › 試算 | 工作階段就緒;佇列是空的 | 送 `POST /api/downloads/estimate {models:["qwen2.5:7b","qwen2.5:0.5b"]}` | 則1:`totalBytes` 為 5080908651(manifest `layers[].size` 加總,不含 `config.size`)<br>則2:`freeDiskBytes` 為 225485783040<br>則3:`estimatedSeconds` 在 101 到 102 之間(5,080,908,651 ÷ 50,000,000)<br>則4:`fits` 為 true<br>則5:`GET /api/downloads` 仍是空的 | 大小把 `config.size` 也加進去,或用版本頁四捨五入的值;或試算順手加入佇列 | FR-022 |
| US3-API-13 | `/api/downloads` › 加入 | 工作階段就緒;剩餘磁碟 5,000,000,000 位元組;佇列已有排隊中的 `qwen2.5:7b`(4,683,087,332) | 先試算再加入 `qwen2.5:0.5b`(397,821,319) | 則1:試算的 `fits` 為 false,`pendingQueueBytes` 為 4683087332<br>則2:加入回 409,`code` 為 `DISK_SPACE_INSUFFICIENT`<br>則3:佇列仍只有 `qwen2.5:7b` | 只比這次選的大小和剩餘空間,沒算佇列裡還沒下載的 | FR-022 |
| US3-API-14 | `/api/downloads` › 加入 | 工作階段就緒;`FakeColabControl.probe_resources` 回 `COLAB_UNREACHABLE` | 送 `POST /api/downloads {models:["qwen2.5:0.5b"]}` | 則1:回 503,`code` 為 `DISK_SPACE_UNKNOWN`,`reasonCode` 為 `COLAB_UNREACHABLE`<br>則2:佇列沒有這一筆 | 讀不到剩餘空間就當成夠用直接加入 | FR-022 |
| US3-API-15 | `/api/downloads` › 加入 | 沒有工作階段 | 送 `POST /api/downloads {models:["qwen2.5:0.5b"]}` | 則1:回 503,`code` 為 `NO_READY_SESSION`<br>則2:佇列沒有這一筆 | 沒有工作階段時照樣加入,使用者以為在下載 | FR-017 |
| US3-API-16 | `/api/downloads` › 加入 | 工作階段就緒;tags 已有 `qwen2.5:0.5b`;佇列有排隊中的 `qwen2.5:7b` | 分別送 `{models:["qwen2.5:0.5b","qwen2.5:1.5b"]}` 與 `{models:["qwen2.5:7b"]}` | 則1:第一次回 409,`code` 為 `MODEL_ALREADY_DOWNLOADED`<br>則2:第一次之後佇列沒有 `qwen2.5:1.5b`(整批不加入)<br>則3:第二次回 409,`code` 為 `DOWNLOAD_ALREADY_QUEUED` | 一批裡有一個不合法時,其他照樣加入;或同一個模型排兩次 | FR-021 |
| US3-API-17 | `/api/downloads` › 加入 | 工作階段就緒;`FakeModelLibrary.get_manifest` 對 `qwen3-coder:480b-cloud` 回 `LIBRARY_CLOUD_ONLY` | 送 `POST /api/downloads {models:["qwen3-coder:480b-cloud"]}` | 則1:回 422,`code` 為 `LIBRARY_CLOUD_ONLY`<br>則2:佇列沒有這一筆 | 雲端專用版本 manifest 沒有層、大小算成 0,照樣排進佇列 | FR-020 |
| US3-API-18 | `/api/session` › 結束 | 工作階段就緒;佇列第 1 筆下載中、第 2 筆排隊中 | 送 `DELETE /api/session`;之後開新的工作階段(新的假伺服器 tags 為空) | 則1:第 1 筆 `state` 為 `failed`,`reasonCode` 為 `SESSION_ENDED`<br>則2:結束後到新的工作階段就緒前,第 2 筆仍是 `queued`<br>則3:新的工作階段就緒後 `GET /api/models` 是空的 | 結束時把下載中的那筆標成完成或留在下載中;或把排隊中的一起清掉 | 邊界情況、FR-018 |
| US3-API-19 | `/api/session` › 開啟 → `/api/downloads` › 列出 | 佇列有排隊中的 `qwen2.5:0.5b`,沒有工作階段 | 開新的工作階段到就緒 | 則1:沒有工作階段時 `GET /api/downloads` 的 `paused` 為 true<br>則2:就緒後 1 秒內假伺服器收到 `pull qwen2.5:0.5b`<br>則3:開始前 `probe_resources` 被呼叫(重新檢查空間) | 新的工作階段就緒後佇列沒有自動繼續;或繼續前沒有重新檢查空間 | 邊界情況、FR-021 |
| US3-API-20 | `/api/downloads` › 重新排隊 | 佇列依序有 completed 的 A、failed 的 B(`SESSION_ENDED`)、queued 的 C | 送 `POST /api/downloads/<B>/retry`,再送 `POST /api/downloads/clear-completed` | 則1:retry 回 200,B 的 `state` 為 `queued`,排在 C 之後<br>則2:clear-completed 回的 `removedIds` 只有 A<br>則3:之後佇列依序是 C、B | 重新排隊插回原位,插隊到 C 前面;或清除已完成時連失敗的一起清 | FR-021 |
| US3-API-21 | `/api/library` › 搜尋 | 工作階段就緒,tags 有 `qwen2.5:0.5b`;`FakeModelLibrary.search_library` 回 `qwen2.5`、`qwen2.5-coder`,有下一頁連結 | 送 `GET /api/library/search?q=qwen2.5` | 則1:`items` 依序是 `qwen2.5`、`qwen2.5-coder`<br>則2:`qwen2.5` 的 `downloadedTags` 為 `["0.5b"]`<br>則3:`hasMore` 為 true | `downloadedTags` 沒對照執行環境;或 `hasMore` 用筆數猜 | FR-020 |
| US3-API-22 | `/api/library` › 列版本 | 工作階段就緒,tags 有 `qwen2.5:0.5b`;`list_model_tags` 回 `0.5b`(398MB)、`7b`(4.7GB)、`7b-cloud` | 送 `GET /api/library/models/qwen2.5/tags` | 則1:`0.5b` 的 `sizeLabel` 為 `398MB`,`downloaded` 為 true<br>則2:`7b` 的 `downloaded` 為 false<br>則3:`7b-cloud` 的 `cloudOnly` 為 true | 雲端專用版本沒標出,UI 讓它被勾選 | FR-020 |
| US3-API-23 | `/api/library` › 搜尋 | `search_library` 回 `LIBRARY_BAD_RESPONSE` | 送 `GET /api/library/search?q=qwen2.5` 與 `GET /api/curated` | 則1:搜尋回 502,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則2:精選清單照常回 200 | 模型庫壞掉時連精選清單也讀不到(spec 假設的退路不成立) | FR-020 |
| US3-API-24 | `/api/curated` › 新增 | 精選清單是空的 | 依序新增 `qwen2.5:7b`(說明「日常用」)、新增 `qwen2.5`、再新增 `qwen2.5:latest`、修改第一筆說明為 201 個字元、刪除第二筆 | 則1:前兩次回 201<br>則2:第三次回 409,`code` 為 `CURATED_DUPLICATE`(沒寫版本視為 `latest`)<br>則3:修改回 400,`code` 為 `INVALID_CURATED_DESCRIPTION`<br>則4:刪除回 204,之後 `GET /api/curated` 只有 `qwen2.5:7b` | 沒把沒寫版本的名稱正規化成 `:latest`,同一個模型存成兩筆 | FR-020 |
| US3-API-25 | 後端行程 › 重新啟動 | 工作階段就緒,`qwen2.5:7b` 下載中 | 重建 app(`list_sessions` 仍列出這台) | 則1:重建後這一筆 `state` 先回到 `queued`<br>則2:工作階段接回後假伺服器再收到一次 `pull qwen2.5:7b`<br>則3:這一筆在佇列的順序沒變 | 重啟後永遠停在 `downloading`,佇列卡住 | FR-021 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US3-API-26 | 可用性(可能無法載入) | 🔴🟢 行為測試 | `/api/models` › 列出目錄 | 工作階段就緒,顯示記憶體總量 16,106,127,360;tags 有 `qwen2.5:7b`(4,683,087,332)與一個合成的 `cgb-test-big:70b`(20,000,000,000) | 送 `GET /api/models`;再讓 `probe_resources` 回 `vramTotalBytes: null` 後送一次 | 則1:第一次 `cgb-test-big:70b` 的 `mayNotFit` 為 true<br>則2:第一次 `qwen2.5:7b` 的 `mayNotFit` 為 false<br>則3:第二次兩個的 `mayNotFit` 都是 null | 用剩餘顯示記憶體比較,已載入一個模型後全部標成可能無法載入(Q62);或讀不到時標 false | NFR-006 | — | — |
| US3-API-27 | 效能(背景下載不影響推論) | 🔴🟢 行為測試 | `/api/downloads` › 加入 → Ollama 端點 › `POST /api/generate` | 工作階段就緒;假伺服器的 `pull` 每 0.1 秒一行、持續 3 秒;`generate` 立即回應 | 加入下載後 0.5 秒,經 Ollama 相容端點送 5 次非串流 `generate` | 則1:5 次都在 0.2 秒內回 200<br>則2:5 次都回完時 `pull` 仍在進行 | 下載與推論共用一把鎖或同一條 httpx 連線,推論要等下載結束 | NFR-007 | — | — |

### 4.2 E3 Ollama 相容端點(FastAPI 轉送)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US3-OC-01 | Ollama 端點 › `POST /api/generate` | 工作階段就緒;假伺服器對 `qwen2.5:7b` 回 404 `{"error":"model 'qwen2.5:7b' not found"}` | 送 `POST /api/generate {model:"qwen2.5:7b",prompt:"你好"}` | 則1:回 404,本文和假伺服器回的完全相同(英文原文)<br>則2:假伺服器沒收到 `pull`<br>則3:`GET /api/downloads` 沒有新增項目 | 模型不存在時自動排下載 | FR-016 |
| US3-OC-02 | Ollama 端點 › `POST /api/chat` | 工作階段就緒;tags 有 `qwen2.5:7b`、ps 沒有;假伺服器回應前睡 0.3 秒(代表載入) | 送 `POST /api/chat {model:"qwen2.5:7b",stream:false}` | 則1:回 200,本文是假伺服器的回應<br>則2:假伺服器只收到這 1 個請求,沒有另外的預先載入或 pull | 本系統自己先送預先載入再轉送,多一次往返 | FR-016 |
| US3-OC-03 | Ollama 端點 › `GET /api/tags` | 工作階段就緒;`qwen2.5:7b` 下載中;假伺服器的 tags 只有 `qwen2.5:0.5b` | 送 `GET /api/tags` | 則1:回的 `models` 只有 `qwen2.5:0.5b`,和假伺服器回的完全相同 | 把佇列裡下載中的名稱合併進清單,讓程式以為可用 | FR-016、FR-018 |
| US3-OC-04 | Ollama 端點 › `POST /api/generate` | 工作階段就緒;ps 沒有 `qwen2.5:7b`;假伺服器回應前睡 0.5 秒 | 同時送兩個指名 `qwen2.5:7b` 的 `generate` | 則1:兩個都回 200<br>則2:假伺服器剛好收到 2 個 `generate`,沒有其他請求 | 本系統為了「只載入一次」自己排隊或另送預先載入,第二個請求被擋或多一次載入 | 邊界情況 |

### 4.3 E7 遠端 Ollama(Colab 執行環境上,Ollama API)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US3-RO-01 | `RemoteOllama` › `pull_model` | 假伺服器送 `{"status":"pulling manifest"}`、兩行 `{"status":"pulling <digest>","digest":"sha256:a","total":100,"completed":50}` 與 `completed:100`、`{"status":"success"}` | 呼叫並收集進度 | 則1:進度依序有 50/100、100/100<br>則2:最後回成功 | 把沒有 `total` 的狀態行當成 0% 進度;或沒等 `success` 就回成功 | FR-017 |
| US3-RO-02 | `RemoteOllama` › `pull_model` | 假伺服器情況 A HTTP 200 後送 `{"error":"pull model manifest: file does not exist"}`;B 送 `{"error":"max retries exceeded"}`;C 送兩行進度後關閉;D 送一行後 0.5 秒不再送(進度間隔逾時注入 0.3 秒) | 各呼叫一次 | 則1:依序回 `OLLAMA_NOT_FOUND`、`OLLAMA_PULL_FAILED`、`OLLAMA_STREAM_INTERRUPTED`、`OLLAMA_TIMEOUT` | 只看 HTTP 狀態碼,200 就當成功;或設了總時長,大模型下載到一半被砍 | FR-017 |
| US3-RO-03 | `RemoteOllama` › `list_local_models` | 假伺服器的 tags 回兩個模型、ps 回一個 | 呼叫 `list_local_models` 與 `list_loaded_models` | 則1:`list_local_models` 回兩個名稱與 `size`<br>則2:`list_loaded_models` 回一個名稱 | 欄位名稱拼錯(`model` 與 `name` 混用)而解析成空清單 | FR-014 |
| US3-RO-04 | `RemoteOllama` › `preload` | 假伺服器記下 `generate` 的本文 | 以 `qwen2.5:7b` 呼叫 | 則1:本文恰為 `{"model":"qwen2.5:7b","keep_alive":-1}` | 預先載入帶了 `prompt`,或 `keep_alive` 不是 -1 | FR-015 |

### 4.4 E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US3-LIB-01 | `ModelLibrary` › `search_library` | 存下來的搜尋頁 HTML 有 `href="/library/qwen2.5"`、`href="/library/qwen2.5-coder"`、`href="/someone/qwen2.5-custom"` | 以 `q=qwen2.5` 呼叫第 1 頁與第 2 頁 | 則1:結果只有 `qwen2.5`、`qwen2.5-coder`<br>則2:兩次請求都帶 `c=local`<br>則3:第 2 頁的請求帶 `page=2` 與標頭 `HX-Request: true`,第 1 頁沒有 | 把社群模型也列出(Q9);或第 2 頁沒帶 `HX-Request`,拿到整頁 HTML 而重複解析 | FR-020 |
| US3-LIB-02 | `ModelLibrary` › `search_library` | 情況 A 頁尾有 `hx-get="/search?page=2"` 的連結;情況 B 沒有 | 各呼叫一次第 1 頁 | 則1:情況 A 的 `hasMore` 為 true<br>則2:情況 B 的 `hasMore` 為 false | 以「滿 20 筆」推斷有下一頁(Q54 已改) | FR-020 |
| US3-LIB-03 | `ModelLibrary` › `list_model_tags` | 存下來的版本頁有 `0.5b` 398MB、`7b` 4.7GB、`7b-cloud` | 以 `qwen2.5` 呼叫 | 則1:`0.5b` 的大小顯示值為 `398MB`<br>則2:`7b-cloud` 的 `cloudOnly` 為 true<br>則3:`7b` 的 `cloudOnly` 為 false | 名稱含 cloud 沒標出 | FR-020 |
| US3-LIB-04 | `ModelLibrary` › `get_manifest` | 存下來的 manifest:`qwen2.5:7b` 4 層合計 4,683,087,332、`config.size` 487;另有沒有任何層的雲端版本;registry 情況 A 回 404、B 回 503、C 回 HTML | 各呼叫一次 | 則1:`qwen2.5:7b` 的大小為 4683087332(不含 config)<br>則2:沒有層的回 `LIBRARY_CLOUD_ONLY`<br>則3:A、B、C 依序回 `LIBRARY_NOT_FOUND`、`LIBRARY_SERVER_ERROR`、`LIBRARY_BAD_RESPONSE` | 大小加進 config;或沒有層時回大小 0 | FR-022 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US3-LIB-05 | 正確性(替身與真模型庫一致) | 📏 量測 | `ModelLibrary` › `search_library` → `ModelLibrary` › `list_model_tags` → `ModelLibrary` › `get_manifest` | 主機階段,真的 ollama.com 與 registry.ollama.ai | 呼叫 `search_library(q="qwen2.5")` 第 1、2 頁、`list_model_tags("qwen2.5")`、`get_manifest("qwen2.5","7b")`、`get_manifest("qwen2.5","cgb-test-nonexistent")`、版本頁上任一個名稱含 `cloud` 的版本的 `get_manifest`(沒有就記下沒有) | 則1:第 1 頁含 `qwen2.5`,`hasMore` 為 true<br>則2:版本頁含 `0.5b` 與 `7b`,`7b` 的大小顯示值在 4.6GB 到 4.8GB 之間<br>則3:`qwen2.5:7b` 的大小在 4,600,000,000 到 4,800,000,000 位元組之間<br>則4:`cgb-test-nonexistent` 回 `LIBRARY_NOT_FOUND`<br>則5:雲端版本(若有)回 `LIBRARY_CLOUD_ONLY`<br>則6:`tests/fixtures/library/` 存的頁面與這次抓到的頁面,用同一組解析規則得到相同的欄位 | 存下來的 HTML 是舊版或手寫的,ollama.com 改版後解析全空,自動化測試照樣全綠 | FR-020、FR-022 | P5、P8;不開執行環境,0 compute units,約 1 分鐘;只送 GET,總共不超過 10 個請求,請求間隔 1 秒 | 判定者:腳本;樣本:2026 年 11 月的 ollama.com 一次(未用於調整) |

### 4.5 E5 Colab CLI(google-colab-cli,外部程式)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US3-CLI-01 | `ColabControl` › `probe_resources` | 假 `colab exec` 最後印 `CGB-RESULT {"ok": true, "diskFreeBytes": 225485783040, "diskTotalBytes": 253338115072, "gpuName": "Tesla T4", "vramTotalBytes": 16106127360, "vramFreeBytes": 15727591424}` | 呼叫 | 則1:回 `diskFreeBytes` 225485783040、`vramTotalBytes` 16106127360<br>則2:argv 含 `--timeout 30` | 欄位對錯(把總容量當剩餘) | FR-022 |
| US3-CLI-02 | `ColabControl` › `probe_resources` | 情況 A `CGB-RESULT` 的三個顯示記憶體欄位都是 null、`ok` 為 true;情況 B `ok` 為 false | 各呼叫一次 | 則1:情況 A 回成功,`vramTotalBytes` 為 null<br>則2:情況 B 回錯誤 | 沒有 GPU 資訊就當成失敗,連剩餘磁碟都拿不到 | FR-022、NFR-006 |

### 4.6 E4 資料庫(SQLite)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US3-DB-01 | SQLite › 寫入 `download_jobs` | `db` 模組建立的 schema;已有一筆 `pending_model='qwen2.5:7b'`、`queue_position=1` | 再插入 `pending_model='qwen2.5:7b'`;再插入 `queue_position=1` 的另一個模型;再插入兩筆 `pending_model` 為 null 的已完成項目;在 `curated_models` 插入兩筆 `name='qwen2.5:latest'` | 則1:重複的 `pending_model` 丟出 `IntegrityError`<br>則2:重複的 `queue_position` 丟出 `IntegrityError`<br>則3:兩筆 `pending_model` 為 null 都插入成功<br>則4:`curated_models` 第二筆丟出 `IntegrityError` | `pending_model` 沒有 unique,同一個模型排兩次;或用 `model` 欄位做 unique,完成過的模型不能再下載 | FR-021、FR-020 |

### 4.7 E1、E6、E9、E10、E11

本故事不涉及這些端點的需求,這一節沒有案例(E1 的畫面行為都要後端,放在 4.8)。

### 4.8 跨端點驗收

真的瀏覽器接真的後端(測試行程內的 uvicorn,UI 127.0.0.1:8781,轉接層用替身),在 4.1~4.6 都完成後才開始;📏 案例改接真的 Colab 與真的模型庫。

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US3-AJ-01 | 模型頁 › 「預先載入」 | 工作階段就緒;tags 有 `qwen2.5:0.5b`、`qwen2.5:7b`,ps 有 `qwen2.5:0.5b` | 打開模型頁 | 則1:`#catalog` 有兩列,各顯示名稱與大小(0.4 GB、4.7 GB)<br>則2:`qwen2.5:0.5b` 那一列標示「已載入」<br>則3:`qwen2.5:7b` 那一列有「預先載入」按鈕 | 大小顯示位元組原始值;或已載入的沒標出 | FR-014 |
| US3-AJ-02 | 模型頁 › 「預先載入」 | 同 US3-AJ-01;`generate` 等測試放行 | 按 `qwen2.5:7b` 的「預先載入」,再放行 | 則1:按下後那一列顯示載入中<br>則2:放行後不需重新整理就標示「已載入」 | 按下後沒有任何回饋;或要重新整理才看得到結果 | FR-015 |
| US3-AJ-03 | 下載模型頁 › 「下載」 → 模型頁 › 「預先載入」 | 工作階段就緒;`pull` 每 0.1 秒一行進度、共 20 行 | 在 `#name-form` 輸入 `qwen2.5:7b` 送出並確認;再打開模型頁 | 則1:下載中佇列那一列的進度文字(`[data-progress-text]`)至少變化 2 次<br>則2:完成後那一列顯示「完成」<br>則3:模型頁 `#catalog` 有 `qwen2.5:7b` | 進度只在完成時更新一次;或完成後目錄沒更新 | FR-017 |
| US3-AJ-04 | 下載模型頁 › 「下載」 | 工作階段就緒;manifest 對 `qwen2.5:cgb-test-nonexistent` 回 `LIBRARY_NOT_FOUND` | 輸入 `qwen2.5:cgb-test-nonexistent` 送出 | 則1:出現「找不到這個模型」(`[data-state="not-found"]`)<br>則2:佇列沒有新增項目 | 錯誤只顯示代碼或沒有提示 | FR-017 |
| US3-AJ-05 | 下載模型頁 › 「搜尋」 | 工作階段就緒,tags 有 `qwen2.5:0.5b`;精選清單有 `qwen2.5:7b`;搜尋結果 `qwen2.5`、`qwen2.5-coder`,有下一頁 | 打開下載模型頁,搜尋 `qwen2.5`,展開 `qwen2.5` 的版本,按「顯示更多」 | 則1:`#curated` 在 `#results` 之上<br>則2:`qwen2.5` 的版本清單有 `0.5b` 與大小,`0.5b` 標示「已下載」<br>則3:按「顯示更多」後 `#results` 的列數增加 | 精選清單排在搜尋結果下面;或已下載的沒標示 | FR-020 |
| US3-AJ-06 | 下載模型頁 › 「加入下載」 → 下載模型頁 › 「確認加入」 | 工作階段就緒;勾選 `qwen2.5:0.5b`、`qwen2.5:1.5b`、`qwen2.5:7b` | 按「加入下載」,看確認畫面,按「確認加入」 | 則1:確認畫面 `#confirm-table` 列出三個模型與總大小<br>則2:`#confirm-disk` 顯示剩餘磁碟空間<br>則3:`#confirm-eta` 顯示預估時間並標示為估計<br>則4:確認後佇列依序顯示三筆,第一筆「下載中」、其他「排隊中」<br>則5:全部完成後三筆都顯示「完成」 | 沒有確認畫面就直接加入;或確認畫面缺剩餘空間或預估時間 | FR-021、FR-022 |
| US3-AJ-07 | 模型頁 › 「取消」 | 佇列第 1 筆下載中、第 2 筆排隊中 | 按第 2 筆的「取消」 | 則1:第 2 筆從佇列消失<br>則2:第 1 筆仍顯示下載中、進度繼續增加<br>則3:第 1 筆沒有「取消」按鈕 | 正在下載的也顯示取消按鈕,按了回 409 卻沒有說明 | FR-021 |
| US3-AJ-08 | 下載模型頁 › 「加入下載」 | 工作階段就緒;剩餘磁碟 1,000,000,000 位元組 | 勾選 `qwen2.5:7b`,按「加入下載」 | 則1:出現「空間不足」提示(`[data-state="no-space"]`)<br>則2:「確認加入」不可按,或按了也沒有加入<br>則3:佇列沒有新增項目 | 前端沒看 `fits`,讓使用者送出被伺服器拒絕後才知道 | FR-022 |
| US3-AJ-09 | 首頁 › 「結束工作階段」 → 模型頁 › 「重新排隊」 | 工作階段就緒;`qwen2.5:7b` 下載中、`qwen2.5:1.5b` 排隊中 | 在首頁結束工作階段,打開模型頁 | 則1:`qwen2.5:7b` 那一列顯示失敗與原因,有「重新排隊」<br>則2:`qwen2.5:1.5b` 仍顯示排隊中<br>則3:`#catalog` 沒有 `qwen2.5:7b` | 結束後下載中的那筆仍顯示下載中或可用 | FR-018 |
| US3-AJ-10 | 下載模型頁 › 「搜尋」 | 版本清單有 `7b-cloud` | 展開 `qwen2.5` 的版本 | 則1:`7b-cloud` 那一列有「只能在雲端執行」的說明<br>則2:`7b-cloud` 不能勾選 | 雲端專用版本可以勾選,加入時才被 422 擋下 | FR-020 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US3-AJ-11 | 可用性(可能無法載入) | 🔴🟢 行為測試 | 模型頁 › 「預先載入」 | 工作階段就緒;目錄有 `cgb-test-big:70b`(`mayNotFit` 為 true)與 `qwen2.5:7b`(false) | 打開模型頁,按 `cgb-test-big:70b` 的「預先載入」,在提示裡按取消;再按 `qwen2.5:7b` 的「預先載入」 | 則1:`cgb-test-big:70b` 那一列標示「可能無法載入」<br>則2:按它的「預先載入」先出現提示(`[data-state="preload-warn"]`),取消後 `generate` 沒被送出<br>則3:`qwen2.5:7b` 按下後沒有提示,直接開始載入 | 只在目錄標示、預先載入前沒有提示;或每個模型都跳提示 | NFR-006 | — | — |
| US3-AJ-12 | 效能(下載到可推論) | 📏 量測 | 下載模型頁 › 「下載」 → 區網程式 › `POST /api/generate` | 容器階段,US1-AJ-17 的 T4 工作階段就緒,執行環境上沒有 `qwen2.5:7b`;真的模型庫與遠端 Ollama | 在下載模型頁輸入 `qwen2.5:7b` 下載並確認;下載中每 2 秒經 11436 讀一次 `/api/tags`;完成後立即經 11436 送一次非串流 `generate`(`num_predict` 8、`keep_alive` 0,推論完即卸載) | 則1:從按「確認加入」到 `generate` 回 200 在 3 分鐘內(SC-004)<br>則2:下載完成前每一次 `/api/tags` 都沒有 `qwen2.5:7b`(FR-018、Q2)<br>則3:下載完成後的 `/api/tags` 有 `qwen2.5:7b` | 真的 Ollama 在下載中就把名稱寫進 tags,信任 `/api/tags` 的 Q2 不成立;或下載走了較慢的路徑 | FR-017、FR-018、NFR-005、SC-004 | P1~P9;沿用 US1-AJ-17 的 T4,約 4 分鐘、約 0.08 compute units;只下載 `qwen2.5:7b` 一次 | 判定者:腳本(3 分鐘門檻);樣本:一次實跑(未用於調整) |
| US3-AJ-13 | 效能(背景下載不影響推論) | 📏 量測 | 區網程式 › `POST /api/generate` | 容器階段,US1-AJ-17 的 T4 工作階段就緒,`qwen2.5:0.5b` 已載入 | 先在沒有下載時經 11436 送 5 次非串流 `generate`(`qwen2.5:0.5b`,`num_predict` 16、`seed` 1、`temperature` 0);接著在 US3-AJ-12 的 `qwen2.5:7b` 下載期間再送 5 次 | 則1:下載期間 5 次的平均延遲減沒有下載時 5 次的平均延遲不超過 0.5 秒(SC-008)<br>則2:下載期間的 5 次都在下載完成之前送完(若下載先完成,本次不算,記為未驗證) | 下載與推論在本系統共用同一條連線或鎖,下載時推論排隊 | NFR-007、SC-008 | P1~P9;與 US3-AJ-12 同一段時間,不另外增加占用;只用 `qwen2.5:0.5b` 推論 | 判定者:腳本(0.5 秒門檻);樣本:10 次請求(未用於調整) |

### 4.9 交給 `/tdd` 的順序

每個案例在 `tasks.md` 是一組紅燈、綠燈任務;每一節的案例都做完後,接一個重構任務。同一個故事的端點節彼此平行,跨端點驗收在端點節都完成後才開始。

1. E2 後端 UI API:US3-API-01 → US3-API-02 → … → US3-API-27 → 重構
2. E3 Ollama 相容端點:US3-OC-01 → US3-OC-02 → US3-OC-03 → US3-OC-04 → 重構
3. E7 遠端 Ollama:US3-RO-01 → US3-RO-02 → US3-RO-03 → US3-RO-04 → 重構
4. E8 Ollama 官方模型庫:US3-LIB-01 → US3-LIB-02 → US3-LIB-03 → US3-LIB-04 → 重構;US3-LIB-05 為 📏 任務
5. E5 Colab CLI:US3-CLI-01 → US3-CLI-02 → 重構
6. E4 資料庫:US3-DB-01 → 重構
7. E1、E6、E9、E10、E11:本故事沒有案例
8. 跨端點驗收(4.1~4.6 完成後):US3-AJ-01 → US3-AJ-02 → … → US3-AJ-11 → 重構;US3-AJ-12、US3-AJ-13 為 📏 任務

## 5. 使用者故事 4 - 掌握用量並避免忘了關(P3)

**本故事的需求**:FR-024~FR-027;NFR-008;邊界情況:餘額歸零
**本故事涵蓋的全域 NFR**:FR-028(彙整見第 6 節)

### 5.1 E2 後端 UI API(FastAPI REST 與 SSE)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US4-API-01 | `/api/usage` › 查詢 | `FakeColabControl.get_usage` 回 `balance` 381.66、`ratePerHour` 1.15、`activeAssignments` 1;注入的時鐘在讀取時為 `2026-11-10T08:00:00Z` | app 啟動後把時鐘推進 10 秒,送 `GET /api/usage` | 則1:`state` 為 `known`,`balance` 為 381.66,`ratePerHour` 為 1.15<br>則2:`hoursRemaining` 在 331.8 到 331.9 之間(381.66 ÷ 1.15)<br>則3:`readAt` 為 `2026-11-10T08:00:00Z`(讀取的時間,不是查詢的時間)<br>則4:`stale` 為 false | 估計時數用耗用 ÷ 餘額;或 `readAt` 填成每次查詢的現在,過期永遠不會出現 | FR-024 |
| US4-API-02 | `/api/usage` › 查詢 | 情況 A `get_usage` 回 `ratePerHour` 0.00(沒有執行環境在跑);情況 B 回 `balance` -0.50、`ratePerHour` 1.15 | 各送一次 `GET /api/usage` | 則1:情況 A 的 `hoursRemaining` 為 null<br>則2:情況 B 的 `hoursRemaining` 為 0(Q120 先採用)<br>則3:情況 B 的 `balance` 為 -0.5 | 耗用為 0 時除以零丟出例外,`/api/usage` 回 500;或餘額為負時回負的時數 | FR-024 |
| US4-API-03 | `/api/usage` › 查詢 → `/api/session` › 開啟 | 從 app 啟動起 `get_usage` 都回 `COLAB_UNREACHABLE`(從沒讀到過) | 送 `GET /api/usage`;再送 `POST /api/session` 開到就緒;再送 `DELETE /api/session` | 則1:`GET /api/usage` 的 `state` 為 `unknown`,`reasonCode` 為 `COLAB_UNREACHABLE`,`message` 不為空<br>則2:`POST /api/session` 回 202,之後 `state` 為 `ready`<br>則3:`DELETE /api/session` 回 202,之後 `state` 為 `ended` | 讀不到用量就擋下開啟或結束;或 `unknown` 時沒有原因 | FR-024 |
| US4-API-04 | `/api/usage` › 查詢 → `/api/session` › 開啟 | 設定的警告門檻 10;情況 A `get_usage` 回餘額 9.50;情況 B 回 10.00 | 各送 `GET /api/usage`;情況 A 再送 `POST /api/session` | 則1:情況 A 的 `lowBalance` 為 true<br>則2:情況 B 的 `lowBalance` 為 false(「低於」不含等於,Q121 先採用)<br>則3:情況 A 的 `POST /api/session` 回 202 | 低餘額時擋下開啟(FR-025 只警告);或用 `<=` 判斷 | FR-025 |
| US4-API-05 | 排程 › 讀用量 | 工作階段 `ready`;警告門檻 10;`get_usage` 第一次回 50.00,之後回 0.50 | 時鐘推進 5 分鐘,讓下一次讀用量發生 | 則1:SSE 收到 `usage.updated`,`lowBalance` 為 true<br>則2:`state` 仍是 `ready`<br>則3:`stop_session` 沒被呼叫 | 餘額過低時自動結束工作階段 | FR-025 |
| US4-API-06 | `/api/settings` › 查詢 | 全新的 SQLite 檔 | 啟動 app,送 `GET /api/settings` | 則1:`idleTimeoutMinutes` 為 30<br>則2:`lowBalanceThreshold` 為 10 | 預設值寫錯或沒有在第一次啟動時寫入,回 404 或 null | FR-027 |
| US4-API-07 | `/api/settings` › 修改 | 預設設定;訂閱 SSE | 送 `PUT /api/settings {idleTimeoutMinutes:10,lowBalanceThreshold:5}`,再送 `GET /api/settings`,再重建 app 後送一次 `GET /api/settings` | 則1:`PUT` 回 200,本文是新的值<br>則2:SSE 收到 `settings.updated`,值為 10 與 5<br>則3:重建前後的 `GET` 都是 10 與 5 | 只改記憶體沒寫進資料庫,重啟後回到預設;或沒推送事件 | FR-027 |
| US4-API-08 | `/api/settings` › 修改 | 設定為 30 與 10 | 分別送 `idleTimeoutMinutes` 為 0、1441、10.5,以及 `lowBalanceThreshold` 為 -1、10001 的 `PUT`(另一個欄位用合法值) | 則1:前三次回 400,`code` 為 `INVALID_IDLE_TIMEOUT`<br>則2:後兩次回 400,`code` 為 `INVALID_BALANCE_THRESHOLD`<br>則3:之後 `GET /api/settings` 仍是 30 與 10 | 範圍檢查漏了邊界(1441 或 0 被接受);或驗證失敗時另一個欄位已經被寫進去 | FR-027 |
| US4-API-09 | `/api/settings` › 修改 | 工作階段 `ready`,閒置時限 30 分鐘,`idle.lastRequestAt` 為 T | 時鐘在 T+3 分鐘時送 `PUT /api/settings {idleTimeoutMinutes:10,lowBalanceThreshold:10}` | 則1:之後 `GET /api/session` 的 `idle.timeoutMinutes` 為 10<br>則2:`idle.deadline` 為 T+10 分鐘(以最後一次請求起算,不是以修改的時間起算)<br>則3:SSE 收到 `session.updated`,`idle.deadline` 為 T+10 分鐘 | 新時限要等下一個工作階段才生效;或從修改的時間重新起算 | FR-027、FR-026 |
| US4-API-10 | `/api/settings` › 修改 | 工作階段 `ready`,閒置時限 30 分鐘,時鐘已在 `idle.lastRequestAt` 之後 12 分鐘 | 送 `PUT /api/settings {idleTimeoutMinutes:10,lowBalanceThreshold:10}` | 則1:`PUT` 回 200<br>則2:之後 1 秒內 `state` 變成 `ending` 或 `ended`,`endReason` 為 `IDLE_TIMEOUT`<br>則3:`stop_session` 以 `cgb-test-0001` 被呼叫 | 新時限已經到了卻等到下一次檢查(或從現在起算 10 分鐘)才結束 | FR-027、FR-026 |
| US4-API-11 | `/api/settings` › 修改 → `/api/usage` › 查詢 | 最後讀到的餘額 15.00,門檻 10 | 送 `PUT /api/settings {idleTimeoutMinutes:30,lowBalanceThreshold:20}`,不再讀用量,送 `GET /api/usage` | 則1:`lowBalance` 為 true,`warningThreshold` 為 20<br>則2:SSE 收到 `usage.updated`,`lowBalance` 為 true<br>則3:`get_usage` 沒有因為這次修改被多呼叫 | 門檻變更要等下一次讀用量才反映在警告上 | FR-027、FR-025 |
| US4-API-12 | 排程 › 閒置到期 | 工作階段 `ready`,閒置時限 1 分鐘,沒有任何請求 | 注入的時鐘推進到 `idle.deadline` 再加 1 分鐘(SC-006 的上限) | 則1:時鐘到 `deadline` 之前 `state` 都是 `ready`<br>則2:時鐘推進到 `deadline` 加 1 分鐘之內,`state` 變成 `ended`,`endReason` 為 `IDLE_TIMEOUT`<br>則3:`close_tunnel` 與 `stop_session(cgb-test-0001)` 都被呼叫<br>則4:`GET /api/sessions` 那一筆的 `endReason` 為 `IDLE_TIMEOUT` | 閒置計時沒有在背景檢查,要等下一個請求才發現逾時;或自動結束只關通道沒釋放 | FR-026、FR-028、SC-006 |
| US4-API-13 | Ollama 端點 › `GET /api/tags` → 排程 › 閒置到期 | 工作階段 `ready`,閒置時限 1 分鐘,`readyAt` 為 T | 時鐘在 T+50 秒時經 Ollama 相容端點送 `GET /api/tags`,再推進到 T+80 秒 | 則1:`GET /api/session` 的 `idle.lastRequestAt` 為 T+50 秒,`deadline` 為 T+110 秒<br>則2:T+80 秒時 `state` 仍是 `ready` | 請求沒有重設閒置計時,工作階段在 T+60 秒被結束 | FR-026 |
| US4-API-14 | `/api/session` › 查詢 → 排程 › 閒置到期 | 工作階段 `ready`,閒置時限 1 分鐘,`readyAt` 為 T | 時鐘在 T+50 秒時送 `GET /api/session`、`GET /api/models`、`GET /api/usage`(都是 UI API),再推進到 T+70 秒 | 則1:T+50 秒之後 `idle.lastRequestAt` 仍為 T<br>則2:T+70 秒時 `state` 為 `ending` 或 `ended`,`endReason` 為 `IDLE_TIMEOUT` | UI 的輪詢與 SSE 也重設閒置計時,開著 UI 的頁面就永遠不會自動結束(Q24) | FR-026 |
| US4-API-15 | 後端行程 › 重新啟動 | 工作階段 `ready`,閒置時限 10 分鐘,`idle.lastRequestAt` 為 T | 時鐘在 T+6 分鐘時重建 app(`list_sessions` 仍列出這台) | 則1:重建後 `idle.deadline` 為 T+10 分鐘<br>則2:時鐘推進到 T+11 分鐘時 `endReason` 為 `IDLE_TIMEOUT` | 重啟後閒置倒數從重啟的時間重算(`last_request_at` 沒存或沒讀回,Q75) | FR-026 |
| US4-API-16 | 排程 › 閒置到期 | 同 US4-API-12,但 `stop_session` 回 `COLAB_STOP_UNCONFIRMED` | 時鐘推進到 `deadline` 之後 | 則1:`endReason` 為 `IDLE_TIMEOUT`<br>則2:`releaseWarning.message` 不為 null | 閒置自動結束時釋放失敗沒有警告,使用者以為已經關了 | FR-026、FR-007 |
| US4-API-17 | 排程 › 健康檢查 | 工作階段 `ready`;最後一次讀到的餘額為 0.00 | `check_health` 開始失敗,`list_sessions` 仍列出這台(重連中) | 則1:`state` 為 `reconnecting`<br>則2:`balanceMayBeDepleted` 為 true<br>則3:另一個測試在最後餘額為 50.00 時做同樣的事,`balanceMayBeDepleted` 為 false | 不看最後讀到的餘額,永遠不提示可能已經歸零;或餘額歸零就直接標失聯、不重連 | 邊界情況、FR-024 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US4-API-18 | 資訊新鮮度 | 🔴🟢 行為測試 | 排程 › 讀用量 → `/api/usage` › 查詢 | `get_usage` 第一次成功(`readAt` 為 T),之後一直回 `COLAB_UNREACHABLE`;注入的時鐘 | 時鐘從 T 推進到 T+20 分鐘,記下每次 `get_usage` 被呼叫的時間;在 T+14 分 59 秒與 T+15 分 01 秒各送一次 `GET /api/usage`;在 T+20 分(讀取仍失敗)之後讓 `get_usage` 恢復成功,時鐘推進到 T+25 分讓下一次排程讀取發生,T+25 分 30 秒再送一次 `GET /api/usage` | 則1:相鄰兩次 `get_usage` 的間隔都不超過 5 分鐘<br>則2:T+14 分 59 秒的 `stale` 為 false<br>則3:T+15 分 01 秒的 `stale` 為 true<br>則4:T+15 分 01 秒的 `balance` 仍是第一次讀到的值,`readAt` 仍是 T(Q119 先採用)<br>則5:T+15 分 01 秒的 `reasonCode` 為 `COLAB_UNREACHABLE`,`lastFailedAt` 不為 null(Q123)<br>則6:T+25 分 30 秒(恢復後的那一次讀取之後)的 `reasonCode`、`message`、`lastFailedAt` 都是 null,`stale` 為 false(Q123) | 只在 UI 打開時才讀用量;或讀取失敗就把舊快照清掉,過期標示永遠不會出現;或讀取失敗時沒寫入失敗原因與時間,使用者看不出為什麼過期;或恢復成功後沒清掉失敗說明,一直顯示讀取失敗 | NFR-008 | — | — |

### 5.2 E3 Ollama 相容端點(FastAPI 轉送)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US4-OC-01 | Ollama 端點 › 管理操作 → Ollama 端點 › 白名單外 | 工作階段 `ready`,閒置時限 1 分鐘,`readyAt` 為 T | 時鐘在 T+20 秒送 `POST /api/pull`(被擋下),在 T+40 秒送 `GET /v1/models`(白名單外) | 則1:`POST /api/pull` 回 403 之後,`idle.lastRequestAt` 為 T+20 秒<br>則2:`GET /v1/models` 回 404 之後,`idle.lastRequestAt` 為 T+40 秒 | 只有轉送出去的請求才重設計時,被擋下的請求不算(與 FR-026「任何經 Ollama 相容端點的請求」不符,Q52) | FR-026 |
| US4-OC-02 | Ollama 端點 › `POST /api/generate` | 工作階段 `ready`,閒置時限 1 分鐘;假伺服器的串流每 10 秒送一行、共 10 行(注入的時鐘) | 時鐘在 T 開始串流讀 `POST /api/generate`,串流進行中推進到 T+90 秒,再讀完最後一行(T+100 秒) | 則1:串流進行中 `idle.activeRequests` 為 1,`idle.deadline` 為 null<br>則2:T+90 秒時 `state` 仍是 `ready`<br>則3:串流結束後 `idle.deadline` 為 T+100 秒加 1 分鐘<br>則4:串流結束後 `idle.activeRequests` 為 0 | 只在請求開始時重設,長串流跑超過閒置時限就被自動結束,回應被切斷 | FR-026 |

### 5.3 E4 資料庫(SQLite)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US4-DB-01 | SQLite › 讀寫 `settings` | `db` 模組建立 schema(第一次啟動) | 讀 `settings`;把 `idle_timeout_minutes` 改成 10;再呼叫一次建立 schema(第二次啟動);再讀 | 則1:第一次讀到 1 列,`id` 為 1、`idle_timeout_minutes` 為 30、`low_balance_threshold` 為 10<br>則2:第二次啟動後仍只有 1 列<br>則3:第二次啟動後 `idle_timeout_minutes` 仍是 10 | 每次啟動都以預設值覆寫使用者改過的設定;或每次啟動多插一列 | FR-027 |
| US4-DB-02 | SQLite › 讀寫 `usage_snapshots` | `db` 模組建立的 schema | 寫入一次用量(381.66、1.15、T),再寫入一次(380.00、1.15、T+5 分鐘),關閉連線後重新開啟再讀 | 則1:`usage_snapshots` 只有 1 列,`id` 為 1<br>則2:那一列的 `balance` 為 380.00、`read_at` 為 T+5 分鐘 | 每次讀用量都插入新列,表無限成長(Q76 只留最後一筆);或重啟後讀不到最後一次的用量 | FR-024 |

### 5.4 E5 Colab CLI(google-colab-cli,外部程式)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US4-CLI-01 | `ColabControl` › `get_usage` | 假 `colab usage` 先印一行 `[colab] ` 開頭的新版本提示,再印 `Current balance: -0.50 compute units`、`Usage rate: 0.00/hr`、`Active assignments: 0` | 呼叫 | 則1:`balance` 為 -0.5<br>則2:`ratePerHour` 為 0<br>則3:`activeAssignments` 為 0 | regex 沒允許負號,餘額歸零後變成負數時解析失敗;或把提示行當成資料 | FR-024、邊界情況 |
| US4-CLI-02 | `ColabControl` › `get_usage` | 假 `colab usage` 印 `Current balance: 381.7 compute units`(只有一位小數)與另外兩行正常的輸出 | 呼叫 | 則1:回 `COLAB_BAD_RESPONSE` | 用寬鬆的 regex 照樣解析,CLI 改版後默默顯示錯的值 | FR-024 |

### 5.5 E1、E6、E7、E8、E9、E10、E11

本故事不涉及這些端點的需求,這一節沒有案例(E1 的畫面行為都要後端,放在 5.6;E5 真的 `colab usage` 的格式由 US1-CLI-21 實跑)。

### 5.6 跨端點驗收

真的瀏覽器接真的後端(測試行程內的 uvicorn,UI 127.0.0.1:8781,轉接層用替身、時鐘由測試注入),在 5.1~5.4 都完成後才開始;📏 案例改接真的 Colab。

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US4-AJ-01 | 用量頁 › 列表 | `get_usage` 回 381.66、1.15 | 打開用量頁 | 則1:出現 `[data-state="normal"]`<br>則2:`#n-balance` 含 381.66<br>則3:`#n-rate` 含 1.15<br>則4:`#n-hours` 含 331<br>則5:`#n-read` 顯示讀取時間 | 畫面只顯示餘額,缺耗用、可用時數或讀取時間 | FR-024 |
| US4-AJ-02 | 用量頁 › 列表 | `get_usage` 等測試放行 | 打開用量頁,過 1 秒再放行 | 則1:放行前出現 `[data-state="loading"]`<br>則2:放行後不需重新整理就變成 `[data-state="normal"]` | 第一次讀到之前顯示 0 或空白的數字,看起來像餘額為 0 | FR-024 |
| US4-AJ-03 | 用量頁 › 列表 → 首頁 › 「開啟」 | `get_usage` 從啟動起一直回 `COLAB_UNREACHABLE` | 打開用量頁;再到首頁按「開啟」並放行全部步驟 | 則1:用量頁出現 `[data-state="unknown"]`,餘額顯示「未知」<br>則2:用量頁有繁體中文的原因<br>則3:首頁最後出現「就緒」 | 讀不到用量時首頁的「開啟」被停用 | FR-024 |
| US4-AJ-04 | 用量頁 › 列表 → 首頁 › 「開啟」 | 門檻 10;`get_usage` 回 9.50 | 打開用量頁;再打開首頁,按「開啟」並放行 | 則1:用量頁出現 `[data-state="low"]`,`#l-warn` 不是空的<br>則2:首頁出現低餘額警告(`[data-state="low-balance"]`),含「compute units 快用完了」<br>則3:首頁的「開啟」可以按,按下後最後出現「就緒」 | 低餘額警告只在用量頁有;或警告畫面把「開啟」停用 | FR-025 |
| US4-AJ-05 | 用量頁 › 「儲存」 → 首頁 › 「開啟」 | 工作階段就緒,閒置時限 30 分鐘,剛收到一個請求 | 在用量頁 `#settings-form` 把閒置時限改成 10、警告門檻改成 400 並儲存;打開首頁 | 則1:用量頁出現已儲存的提示 `#saved`<br>則2:不需重新整理,用量頁變成 `[data-state="low"]`(381.66 低於 400)<br>則3:首頁的閒置倒數 `#r-countdown` 顯示的剩餘時間在 9 到 10 分鐘之間 | 儲存後要重新整理才生效;或倒數仍以 30 分鐘計算 | FR-027 |
| US4-AJ-06 | 首頁 › 「開啟」 → 用量頁 › 「儲存」 | 工作階段就緒;閒置時限 1 分鐘;注入的時鐘 | 打開首頁,時鐘推進 30 秒;再推進到超過 `deadline` | 則1:推進 30 秒後 `#r-countdown` 顯示的剩餘時間在 20 到 30 秒之間<br>則2:超過 `deadline` 後出現 `[data-state="ended-idle"]`,結束原因含「閒置自動結束」 | 倒數不跟著時間走;或自動結束後畫面沒更新,仍顯示就緒 | FR-026 |
| US4-AJ-07 | 首頁 › 「開啟」 | 工作階段就緒;最後一次讀到的餘額 0.00 | `check_health` 失敗、`list_sessions` 不再列出這台 | 則1:首頁出現 `[data-state="lost-zero"]`<br>則2:畫面含「餘額可能已經歸零」 | 失聯時沒有提示可能是餘額歸零,使用者只看到一般的失聯 | 邊界情況 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US4-AJ-08 | 資訊新鮮度 | 🔴🟢 行為測試 | 用量頁 › 列表 | `get_usage` 第一次成功之後一直失敗;注入的時鐘 | 打開用量頁,把時鐘推進 16 分鐘 | 則1:出現 `[data-state="stale"]`<br>則2:畫面標示資料已過期,並顯示原本的讀取時間 | 後端標了 `stale`,前端沒有顯示;或過期時把數字清掉 | NFR-008 | — | — |
| US4-AJ-09 | 正確性(真的用量)、資源釋放(閒置自動結束) | 📏 量測 | 首頁 › 「開啟」 → 用量頁 › 「儲存」 → 用量頁 › 列表 | 容器階段,US1-AJ-21 之後,沒有工作階段;真的 Colab、CLI、ssh、遠端 Ollama | 開一台 T4 到就緒;在用量頁把閒置時限設成 1 分鐘並儲存;記下用量頁的餘額與耗用,同一分鐘內在終端機執行 `HOME=<暫存目錄>/home colab usage`;之後不送任何 Ollama 相容端點的請求,每 5 秒讀一次 `GET /api/session` 與 `colab sessions` | 則1:用量頁的餘額和 `colab usage` 的差不超過 0.05 compute units<br>則2:用量頁的每小時耗用和 `colab usage` 的差不超過 0.05<br>則3:`idle.deadline` 到了之後 1 分鐘內 `endReason` 為 `IDLE_TIMEOUT`(SC-006)<br>則4:自動結束後 1 分鐘內 `colab sessions` 沒有這個名稱(SC-003)<br>則5:案例期間 `GET /api/usage` 的 `readAt` 至少更新過 1 次,相鄰兩次的間隔不超過 5 分鐘 | 真的環境下閒置檢查沒在跑,或健康檢查重設了閒置計時(Q89),工作階段一直扣點;或用量顯示的數字與 Colab 不一致 | FR-024、FR-026、NFR-008、SC-003、SC-006 | P1~P9;開 1 台 T4,約 6 分鐘、約 0.12 compute units;閒置時限只在 `cgb-test` 這個實例改,結束後改回 30;不送任何 Ollama 相容端點的請求 | 判定者:腳本(0.05 差距與 1 分鐘門檻);樣本:一次實跑(未用於調整) |

### 5.7 交給 `/tdd` 的順序

每個案例在 `tasks.md` 是一組紅燈、綠燈任務;每一節的案例都做完後,接一個重構任務。同一個故事的端點節彼此平行,跨端點驗收在端點節都完成後才開始。

1. E2 後端 UI API:US4-API-01 → US4-API-02 → … → US4-API-18 → 重構
2. E3 Ollama 相容端點:US4-OC-01 → US4-OC-02 → 重構
3. E4 資料庫:US4-DB-01 → US4-DB-02 → 重構
4. E5 Colab CLI:US4-CLI-01 → US4-CLI-02 → 重構
5. E1、E6、E7、E8、E9、E10、E11:本故事沒有案例
6. 跨端點驗收(5.1~5.4 完成後):US4-AJ-01 → US4-AJ-02 → … → US4-AJ-08 → 重構;US4-AJ-09 為 📏 任務

## 6. 全域測試區

適用好幾個使用者故事的 NFR 與 SC 放在這裡。故事裡已經有案例涵蓋的,只在 6.1 彙整;沒辦法歸到單一故事的,在 6.2 寫成全域案例。

### 6.1 全域 NFR 的涵蓋彙整

| 全域需求 | 適用的故事 | 故事裡涵蓋它的案例 | 全域案例 |
|---|---|---|---|
| FR-028 狀態變化與結束的紀錄 | 1、4 | US1-API-35、US1-API-36、US1-DB-02、US1-AJ-13、US4-API-12 | — |
| NFR-009 區網開放、不需登入、不對外網 | 1、2、3、4 | — | G-01 |
| NFR-010 機密只在權限受限的設定檔 | 1、2、3、4 | US1-API-40、US1-CLI-18、US1-TUN-09、US2-OC-15 | G-02、G-03、G-04、G-05 |
| NFR-011 介面語言為繁體中文 | 1、2、3、4 | — | G-06 |
| NFR-012 容器交付、資料夾持久化 | 1、2、3、4 | — | G-07、G-08 |
| SC-001 開啟到就緒 5 分鐘內 | —(NFR-001 引用的門檻) | US1-API-12、US1-AJ-17 | — |
| SC-002 收回 2 分鐘內失聯、斷線 1 分鐘內重連中 | —(NFR-002 引用的門檻) | US1-AJ-18、US1-AJ-22 | — |
| SC-003 結束後 1 分鐘內無遺留 | —(FR-007 的驗收門檻) | US1-CLI-16、US1-CLI-21、US1-AJ-20、US1-AJ-21、US4-AJ-09 | — |
| SC-006 閒置時限到達後 1 分鐘內自動結束 | —(FR-026 的驗收門檻) | US4-API-12、US4-AJ-09 | — |
| SC-004 4.7GB 模型 3 分鐘內可推論 | —(NFR-005 引用的門檻) | US3-AJ-12 | — |
| SC-005 轉送增加的延遲 ≤ 0.5 秒 | —(NFR-004 引用的門檻) | US2-AJ-02 | — |
| SC-007 沒有工作階段時 1 秒內回錯誤 | —(FR-013 引用的門檻) | US2-OC-07、US2-AJ-03 | — |
| SC-008 背景下載時延遲增加 ≤ 0.5 秒 | —(NFR-007 引用的門檻) | US3-AJ-13 | — |

### 6.2 全域案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| G-01 | 存取範圍 | 📏 人工 | 區網裝置 › 打開 UI → 區網裝置 › 連 Ollama 相容端點 | 延後到使用者在場時另跑(Q108),不在 P9 這一批;`docker compose -p cgb-test` 起在桌機,`.env` 的 `CGB_BIND_ADDR=0.0.0.0`(本案例暫時改,其他案例用 127.0.0.1)、UI 8780、Ollama 相容端點 11436;沒有工作階段 | 使用者用同一個區網的另一台裝置(手機連 Wi-Fi 或另一台電腦)打開 `http://<桌機區網 IP>:8780`,並對 `http://<桌機區網 IP>:11436/api/version` 送請求;再把手機切到行動網路,或用 check-host.net,對桌機的公網 IP 連 8780 與 11436 | 則1:區網裝置不需要任何登入就看到首頁<br>則2:區網裝置對 11436 收到 503 與「沒有可用的工作階段」<br>則3:行動網路或 check-host.net 對 8780 連不上<br>則4:行動網路或 check-host.net 對 11436 連不上 | compose 只綁 127.0.0.1,區網用不到;或 UI 加了登入;或路由器有轉發使外網連得到 | NFR-009 | P5、P6;不開執行環境,0 compute units,約 5 分鐘;不改路由器設定,只觀察;不在區網內連公網 IP(NAT hairpin 結果不可信);測完把 `CGB_BIND_ADDR` 改回 127.0.0.1 並重建容器 | 判定者:使用者(則1、則2 看畫面與回應);腳本或 check-host.net 結果判定則3、則4;樣本:一台區網裝置與一個外網來源(未用於調整) |
| G-02 | 機密 | 🔴🟢 行為測試 | `/api/session` › 開啟 → `/api/auth` › 送出授權碼 | ASGI transport 起 app,轉接層用替身;授權檔寫入已知的假 token `cgb-test-fake-token-0123456789`;`FakeColabControl` 的錯誤訊息與 `FakeTunnel` 的 stderr 都含 `https://cgb-test-fake-endpoint.example/?colab-runtime-proxy-token=cgb-test-fake-proxy` | 依序走過:登入成功、開啟成功、開啟失敗、重連逾時、結束;擷取所有日誌(caplog 與 stdout、stderr)、所有 API 回應與 SSE 事件 | 則1:日誌、回應與事件都沒有 `cgb-test-fake-token-0123456789`<br>則2:日誌、回應與事件都沒有 `cgb-test-fake-endpoint`<br>則3:日誌、回應與事件都沒有 `cgb-test-fake-proxy`<br>則4:日誌裡每一筆 Ollama 相容端點的請求紀錄只含時間、模型、耗時與狀態碼,不含 prompt | 用 DEBUG 等級記下子行程的 stdout、stderr 全文;或把轉接層的原始錯誤原樣放進 `message` | NFR-010 | — | — |
| G-03 | 機密 | 🔴🟢 行為測試 | repo › 檢查追蹤的檔案 | repo 的工作目錄 | 列出 `git ls-files`,讀 `.gitignore` 與 `deploy/Dockerfile.dockerignore` | 則1:`git ls-files` 沒有 `token.json`、`sessions.json`、`id_ed25519`、`.env`、`*.sqlite3`<br>則2:`.gitignore` 排除 `.env`、`data/` 與 `*.sqlite3`<br>則3:dockerignore 排除 `.env` 與 `data/` | 實跑後把暫存資料或 `.env` 誤 commit 進 repo | NFR-010 | — | — |
| G-04 | 機密、持久化 | 🔴🟢 行為測試 | `cgb-prepare-data` › 啟動前整理 → `cgb-prepare-data` › `--check` | 暫存資料夾當 `CGB_DATA_DIR`;`colab-cli/colab.log` 是內含 `cgb-test-fake-token-0123456789` 的一般檔;`colab-cli/settings.json` 為 `{"enable_update_check": true, "x": 1}` | 以子行程跑 `prepare-data.sh true`,再跑 `prepare-data.sh --check` | 則1:`colab.log` 是指向 `/dev/null` 的符號連結<br>則2:暫存資料夾裡沒有任何檔案含 `cgb-test-fake-token-0123456789`<br>則3:`settings.json` 的 `enable_update_check` 為 false、`x` 仍為 1<br>則4:`<CGB_DATA_DIR>`、`colab-cli/`、`ssh/` 的權限是 0700<br>則5:`--check` 的 exit code 為 0 | 把舊的 `colab.log` 改名保留(含 token 的 DEBUG 紀錄還在);或改寫 settings 時丟掉其他欄位 | NFR-010、NFR-012 | — | — |
| G-05 | 機密 | 📏 量測 | compose › 掃描日誌與資料夾 | 整批實跑結束、P3 之後;`<暫存目錄>/data/colab-cli/token.json` 仍在 | 從 token.json 取出 access token 與 refresh token 寫進一個 0600 的暫存 pattern 檔(不印出);對 `docker compose -p cgb-test logs`、`<暫存目錄>/data` 底下 `token.json` 與 `sessions.json` 以外的每個檔、實跑錄下的所有 API 回應與 SSE 事件,執行 `grep -c -F -f <pattern 檔>`,只印每個來源的次數 | 則1:每個來源的次數都是 0<br>則2:`colab.log` 是指向 `/dev/null` 的符號連結<br>則3:`docker inspect` 的環境變數裡沒有 token | 真的 CLI 或後端在某個路徑把 token 寫進日誌或資料夾,只用假 token 的 G-02 沒抓到 | NFR-010 | P6、P8;不開執行環境,0 compute units,約 2 分鐘;pattern 檔放 `<暫存目錄>`,用完立即刪除;先以一個已知的假 token 驗一次這條 grep 指令真的數得到 | 判定者:腳本(次數 0);樣本:整批實跑產生的日誌與檔案(未用於調整) |
| G-06 | 在地化 | 🔴🟢 行為測試 | 首頁 › 「開啟」 → Ollama 端點 › `POST /api/generate` | 測試行程內的 uvicorn,轉接層用替身;簡體字與大陸用語清單:会话、服务器、默认、用户、数据、设置、登录、网络、内存、信息、程序、文件、接口、支持(Q105 先採用) | 用 Playwright 打開首頁、登入頁、紀錄頁、模型頁、下載模型頁、用量頁(Q111)的每個 `data-state`,取可見文字;觸發 UI API 每一個錯誤代碼一次與 Ollama 相容端點本系統自己產生的每一種錯誤一次 | 則1:每一頁的可見文字都不含清單裡的字詞<br>則2:每一個 UI API 錯誤的 `message` 至少含一個中文字<br>則3:Ollama 相容端點本系統自己產生的每一個 `error` 至少含一個中文字<br>則4:每一頁的 `<html lang>` 是 `zh-Hant-TW` 或 `zh-TW` | 錯誤訊息直接用 Python 例外的英文;或從其他專案搬來的簡體字串 | NFR-011 | — | — |
| G-07 | 部署與持久化 | 📏 量測 | compose › 起 → compose › 重建 | 整批實跑的最後(P3 之後),`<暫存目錄>/.env` 只有 `CGB_HOST_DATA`、`CGB_HOST_UI_PORT=8780`、`CGB_HOST_OLLAMA_PORT=11436`、`CGB_BIND_ADDR=127.0.0.1`;資料夾裡已有複製來的授權與 US1-AJ-17~US1-AJ-22、US4-AJ-09 的紀錄 | `docker compose -p cgb-test --env-file <暫存目錄>/.env down`,再 `up -d --force-recreate`(沿用已建好的映像);等健康;讀 `GET /api/auth`、`GET /api/sessions`;`docker exec` 讀 `/data` 底下的權限 | 則1:`up` 後 90 秒內容器狀態為 healthy<br>則2:`GET /api/auth` 的 `state` 為 `logged_in`<br>則3:`GET /api/sessions` 的筆數與重建前相同<br>則4:`/data/cgb.sqlite3`、`/data/colab-cli/token.json`、`/data/ssh/id_ed25519` 的權限是 0600<br>則5:`/data/colab-cli/history` 是 tmpfs,重建後是空的 | 授權或紀錄寫在容器內沒掛載的路徑,重建後要重新登入;或健康檢查一直不過 | NFR-012、NFR-010 | P3、P5、P6、P8;不開執行環境,0 compute units,約 3 分鐘;只操作 `-p cgb-test`,不碰 named volume `cgb-data`;重建後不按「開啟」 | 判定者:腳本;樣本:整批實跑留下的資料(未用於調整) |
| G-08 | 部署(健康檢查不影響閒置) | 🔴🟢 行為測試 | `cgb-healthcheck` › 執行 | 測試行程在 127.0.0.1 隨機 port 起一個假 UI(`GET /api/session` 回 200)與一個假 Ollama 相容端點(只 accept 連線、記錄收到的位元組);`CGB_UI_PORT`、`CGB_OLLAMA_PORT` 指到它們 | 以子行程跑 `deploy/healthcheck.py`;再把假 UI 改成回 503 跑一次 | 則1:第一次 exit code 為 0<br>則2:假 Ollama 相容端點收到 0 位元組<br>則3:假 UI 收到 1 個 `GET /api/session`<br>則4:第二次 exit code 不為 0 | 健康檢查對 Ollama 相容 port 送 HTTP,每 30 秒重設閒置計時,工作階段永遠不會閒置結束(Q89) | NFR-012 | — | — |
| G-09 | 可測試性(替身與真轉接層一致) | 🔴🟢 行為測試 | `ColabControl` › `<方法>` → `Tunnel` › `<方法>` → `GoogleOAuth` › `<方法>` | 比對清單目前是 `FakeColabControl` 對 `ColabControl`(`colab_cli.py`)、`FakeTunnel` 對 `Tunnel`(`tunnel.py`)、`FakeGoogleOAuth` 對 `GoogleOAuth`(`google_oauth.py`);`RemoteOllama`(E7)與 `ModelLibrary`(E8)的 adapter 還沒建立,各自的端點節完成時把配對加進清單 | 對清單裡每一對,列出真 adapter 的每個公開方法(不以 `_` 開頭),比對替身同名方法;再對每個方法少帶一個必填參數、多帶一個真方法沒有的參數名,各呼叫替身一次 | 則1:真 adapter 的每個公開方法,替身都有同名方法<br>則2:每個同名方法 `inspect.signature` 的參數名、順序、有沒有預設值都和真方法相同<br>則3:真方法是 async 時,替身方法的呼叫結果是 awaitable;真方法不是 async 時不是<br>則4:少帶必填參數時替身丟 `TypeError`<br>則5:多帶真方法沒有的參數名時替身丟 `TypeError`<br>則6:`src/cgb/adapters/` 裡每個定義了轉接層類別的模組都在比對清單裡(E7、E8 的檔一出現就要加入,否則這條不過) | 替身用 `*args, **kwargs` 照單全收,呼叫端少帶參數(例如重連只傳 `session_name` 給 `open_tunnel`)自動化測試全綠、接上真 adapter 才丟 TypeError | FR-004、FR-005、FR-007 | — | — |

## 7. 需求覆蓋

範疇內的使用者故事與適用它們的全域需求,每一條需求與邊界情況都要出現在這張表;沒有案例的就標「不在範疇」,寫進第 8 節。範疇外的使用者故事不列。

| 需求 | 歸屬 | E1 前端 UI | E2 後端 UI API | E3 Ollama 相容端點 | E4 資料庫 | E5 Colab CLI | E6 SSH 通道 | E7 遠端 Ollama | E8 Ollama 官方模型庫 | E9 Google OAuth | E10 檔案系統 | E11 部署與網路 | 跨端點驗收 | 全域 | 驗證方式 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FR-001 一鍵開啟 | 故事 1 | — | US1-API-01、US1-API-15 | — | — | US1-CLI-01、US1-CLI-02、US1-CLI-06、US1-CLI-07、US1-CLI-11~US1-CLI-14、US1-CLI-21、US1-CLI-22~US1-CLI-24、US1-CLI-29、US1-CLI-30、US1-CLI-37~US1-CLI-41 | US1-TUN-01、US1-TUN-02、US1-TUN-05、US1-TUN-13~US1-TUN-16 | — | — | — | — | — | US1-AJ-01、US1-AJ-17 | — | 🔴🟢、📏 量測 |
| FR-002 結束與確認 | 故事 1 | — | US1-API-07、US1-API-09 | — | — | US1-CLI-15、US1-CLI-21、US1-CLI-25 | US1-TUN-07、US1-TUN-17 | — | — | — | — | — | US1-AJ-02、US1-AJ-21 | — | 🔴🟢、📏 量測 |
| FR-003 狀態追蹤與結束原因 | 故事 1 | — | US1-API-01、US1-API-07、US1-API-10、US1-API-17、US1-API-36、US1-API-38 | — | — | US1-CLI-03、US1-CLI-04、US1-CLI-36 | — | — | — | — | — | — | US1-AJ-01~US1-AJ-04 | — | 🔴🟢 |
| FR-004 健康檢查、重連與失聯 | 故事 1 | — | US1-API-17~US1-API-22、US1-API-37 | US2-OC-11 | — | US1-CLI-05、US1-CLI-20、US1-CLI-28、US1-CLI-32、US1-CLI-39 | US1-TUN-02、US1-TUN-04、US1-TUN-06、US1-TUN-07、US1-TUN-10、US1-TUN-12、US1-TUN-18~US1-TUN-20 | — | — | — | — | — | US1-AJ-04~US1-AJ-06、US1-AJ-18、US1-AJ-22、US1-AJ-23 | G-09 | 🔴🟢、📏 量測 |
| FR-005 後端重啟接回 | 故事 1 | — | US1-API-23、US1-API-24 | — | US1-DB-02 | US1-CLI-03 | US1-TUN-08、US1-TUN-10 | — | — | — | — | — | US1-AJ-14、US1-AJ-19、US1-AJ-23、US2-AJ-05 | G-09 | 🔴🟢、📏 量測 |
| FR-006 最多一個工作階段 | 故事 1 | — | US1-API-04、US1-API-05、US1-API-15、US1-API-16 | — | US1-DB-01 | — | US1-TUN-03、US1-TUN-11 | — | — | — | — | — | US1-AJ-07 | — | 🔴🟢 |
| FR-007 不留遺留、釋放不了要警告 | 故事 1 | — | US1-API-08、US1-API-10~US1-API-14、US1-API-16、US1-API-22、US1-API-26、US1-API-40 | — | — | US1-CLI-07、US1-CLI-14~US1-CLI-18、US1-CLI-21、US1-CLI-23、US1-CLI-25、US1-CLI-26、US1-CLI-35 | US1-TUN-11 | — | — | — | — | — | US1-AJ-06、US1-AJ-16、US1-AJ-21、US1-AJ-23 | G-09 | 🔴🟢、📏 量測 |
| FR-008 UI 內登入 | 故事 1 | — | US1-API-06、US1-API-30~US1-API-34 | — | — | US1-CLI-10、US1-CLI-19、US1-CLI-32~US1-CLI-35 | — | — | — | US1-OA-01~US1-OA-06 | — | — | US1-AJ-08、US1-AJ-09 | — | 🔴🟢、📏 人工 |
| FR-009 選擇執行階段類型 | 故事 1 | — | US1-API-02、US1-API-03 | — | — | US1-CLI-06、US1-CLI-08、US1-CLI-09、US1-CLI-36 | — | — | — | — | — | — | US1-AJ-01、US1-AJ-10 | — | 🔴🟢 |
| FR-010 變更類型重開 | 故事 1 | — | US1-API-27~US1-API-29 | — | — | — | — | — | — | — | — | — | US1-AJ-11、US1-AJ-12、US1-AJ-20 | — | 🔴🟢、📏 量測 |
| NFR-001 開啟進度與時間 | 故事 1 | — | US1-API-39 | — | — | — | — | — | — | — | — | — | US1-AJ-17 | — | 🔴🟢、📏 量測 |
| NFR-002 收回後失聯的時間 | 故事 1 | — | — | — | — | — | US1-TUN-10 | — | — | — | — | — | US1-AJ-18、US1-AJ-22 | — | 📏 量測 |
| FR-011 固定位址轉送 | 故事 2 | — | — | US2-OC-01~US2-OC-03、US2-OC-06、US2-OC-09、US2-OC-13、US2-OC-14 | — | — | — | US2-RO-01~US2-RO-03 | — | — | — | — | US2-AJ-01、US2-AJ-02、US2-AJ-05 | — | 🔴🟢、📏 量測 |
| FR-012 管理操作回錯誤 | 故事 2 | — | — | US2-OC-04、US2-OC-05 | — | — | — | — | — | — | — | — | — | — | 🔴🟢 |
| FR-013 沒有工作階段時回錯誤 | 故事 2 | — | — | US2-OC-05、US2-OC-07、US2-OC-08、US2-OC-10、US2-OC-12 | — | — | — | — | — | — | — | — | US2-AJ-01、US2-AJ-03 | — | 🔴🟢、📏 量測 |
| NFR-003 不經公開網址 | 故事 2 | — | — | US2-OC-15 | — | US2-CLI-01 | US2-TUN-01 | — | — | — | — | — | US2-AJ-04 | — | 🔴🟢、📏 量測 |
| NFR-004 轉送延遲 | 故事 2 | — | — | — | — | — | — | — | — | — | — | — | US2-AJ-02 | — | 📏 量測 |
| FR-014 列出已下載的模型 | 故事 3 | — | US3-API-01、US3-API-02 | — | — | — | — | US3-RO-03 | — | — | — | — | US3-AJ-01 | — | 🔴🟢 |
| FR-015 預先載入 | 故事 3 | — | US3-API-03~US3-API-06 | — | — | — | — | US3-RO-04 | — | — | — | — | US3-AJ-02 | — | 🔴🟢 |
| FR-016 指名時載入、不在就回不存在 | 故事 3 | — | US3-API-04 | US3-OC-01~US3-OC-03 | — | — | — | US2-RO-03 | — | — | — | — | — | — | 🔴🟢、📏 量測 |
| FR-017 輸入名稱下載與進度 | 故事 3 | — | US3-API-07~US3-API-09、US3-API-15 | — | — | — | — | US2-RO-03、US3-RO-01、US3-RO-02 | — | — | — | — | US3-AJ-03、US3-AJ-04、US3-AJ-12 | — | 🔴🟢、📏 量測 |
| FR-018 未完成的下載不顯示為可用 | 故事 3 | — | US3-API-07、US3-API-18 | US3-OC-03 | — | — | — | — | — | — | — | — | US3-AJ-09、US3-AJ-12 | — | 🔴🟢、📏 量測 |
| FR-019(已移除) | 故事 3 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | — | — |
| FR-020 精選清單與模型庫搜尋 | 故事 3 | — | US3-API-17、US3-API-21~US3-API-24 | — | US3-DB-01 | — | — | — | US3-LIB-01~US3-LIB-03、US3-LIB-05 | — | — | — | US3-AJ-05、US3-AJ-10 | — | 🔴🟢、📏 量測 |
| FR-021 多選排隊、逐一顯示、可取消 | 故事 3 | — | US3-API-10、US3-API-11、US3-API-16、US3-API-19、US3-API-20、US3-API-25 | — | US3-DB-01 | — | — | — | — | — | — | — | US3-AJ-06、US3-AJ-07 | — | 🔴🟢 |
| FR-022 加入前顯示大小、空間與時間 | 故事 3 | — | US3-API-12~US3-API-14 | — | — | US3-CLI-01、US3-CLI-02、US1-CLI-41 | — | — | US3-LIB-04、US3-LIB-05 | — | — | — | US3-AJ-06、US3-AJ-08 | — | 🔴🟢、📏 量測 |
| FR-023(已移除) | 故事 3 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | 不在範疇 | — | — |
| NFR-005 下載到可推論的時間 | 故事 3 | — | — | — | — | — | — | — | — | — | — | — | US3-AJ-12 | — | 📏 量測 |
| NFR-006 可能無法載入的標示與提示 | 故事 3 | — | US3-API-26 | — | — | US3-CLI-02 | — | — | — | — | — | — | US3-AJ-11 | — | 🔴🟢 |
| NFR-007 背景下載不影響推論 | 故事 3 | — | US3-API-27 | — | — | — | — | — | — | — | — | — | US3-AJ-13 | — | 🔴🟢、📏 量測 |
| FR-024 自動取得並顯示用量 | 故事 4 | — | US4-API-01~US4-API-03、US4-API-17 | — | US4-DB-02 | US1-CLI-19、US4-CLI-01、US4-CLI-02、US1-CLI-27、US1-CLI-31 | — | — | — | — | — | — | US4-AJ-01~US4-AJ-03、US4-AJ-09 | — | 🔴🟢、📏 量測 |
| FR-025 低餘額只警告不阻止 | 故事 4 | — | US4-API-04、US4-API-05、US4-API-11 | — | — | — | — | — | — | — | — | — | US4-AJ-04 | — | 🔴🟢 |
| FR-026 閒置自動結束 | 故事 4 | — | US4-API-09、US4-API-10、US4-API-12~US4-API-16 | US4-OC-01、US4-OC-02 | — | — | — | — | — | — | — | — | US4-AJ-06、US4-AJ-09 | — | 🔴🟢、📏 量測 |
| FR-027 設定閒置時限與警告門檻 | 故事 4 | — | US4-API-06~US4-API-11 | — | US4-DB-01 | — | — | — | — | — | — | — | US4-AJ-05 | — | 🔴🟢 |
| NFR-008 用量至少 5 分鐘更新、15 分鐘未更新標過期 | 故事 4 | — | US4-API-18 | — | — | — | — | — | — | — | — | — | US4-AJ-08、US4-AJ-09 | — | 🔴🟢、📏 量測 |
| FR-028 狀態變化與結束的紀錄 | 全域 | — | US1-API-35、US1-API-36、US4-API-12 | — | US1-DB-02 | — | — | — | — | — | — | — | US1-AJ-13 | — | 🔴🟢 |
| NFR-009 區網開放、不對外網 | 全域 | — | — | — | — | — | — | — | — | — | — | — | — | G-01 | 📏 人工 |
| NFR-010 機密不出現在 UI、日誌與版本控制 | 全域 | — | US1-API-40 | US2-OC-15 | — | US1-CLI-18、US1-CLI-37 | US1-TUN-09、US1-TUN-16 | — | — | — | — | — | — | G-02~G-05 | 🔴🟢、📏 量測 |
| NFR-011 繁體中文介面 | 全域 | — | — | — | — | — | — | — | — | — | — | — | — | G-06 | 🔴🟢 |
| NFR-012 容器交付與持久化 | 全域 | — | — | — | — | — | — | — | — | — | — | — | — | G-04、G-07、G-08 | 🔴🟢、📏 量測 |
| SC-001 開啟到就緒 5 分鐘內 | 全域 | — | US1-API-12 | — | — | — | — | — | — | — | — | — | US1-AJ-17 | — | 🔴🟢、📏 量測 |
| SC-002 收回 2 分鐘內失聯、斷線 1 分鐘內重連中 | 全域 | — | — | — | — | — | — | — | — | — | — | — | US1-AJ-18、US1-AJ-22 | — | 📏 量測 |
| SC-003 結束後 1 分鐘內無遺留 | 全域 | — | — | — | — | US1-CLI-16、US1-CLI-21 | — | — | — | — | — | — | US1-AJ-20、US1-AJ-21、US4-AJ-09 | — | 🔴🟢、📏 量測 |
| SC-006 閒置時限到達後 1 分鐘內自動結束 | 全域 | — | US4-API-12 | — | — | — | — | — | — | — | — | — | US4-AJ-09 | — | 🔴🟢、📏 量測 |
| SC-004 4.7GB 模型 3 分鐘內可推論 | 全域 | — | — | — | — | — | — | — | — | — | — | — | US3-AJ-12 | — | 📏 量測 |
| SC-005 轉送增加的延遲 ≤ 0.5 秒 | 全域 | — | — | — | — | — | — | — | — | — | — | — | US2-AJ-02 | — | 📏 量測 |
| SC-007 沒有工作階段時 1 秒內回錯誤 | 全域 | — | — | US2-OC-07 | — | — | — | — | — | — | — | — | US2-AJ-03 | — | 🔴🟢、📏 量測 |
| SC-008 背景下載時延遲增加 ≤ 0.5 秒 | 全域 | — | — | — | — | — | — | — | — | — | — | — | US3-AJ-13 | — | 📏 量測 |
| 邊界:連按兩次「開啟」 | 故事 1 | — | US1-API-04 | — | — | — | — | — | — | — | — | — | US1-AJ-07 | — | 🔴🟢 |
| 邊界:變更類型的過程中端點收到請求 | 故事 2 | — | — | US2-OC-10 | — | — | — | — | — | — | — | — | — | — | 🔴🟢 |
| 邊界:開啟到一半按「結束」 | 故事 1 | — | US1-API-13 | — | — | — | — | — | — | — | — | — | US1-AJ-16 | — | 🔴🟢 |
| 邊界:串流回應時連線中斷 | 故事 2 | — | — | US2-OC-11 | — | — | — | — | — | — | — | — | — | — | 🔴🟢 |
| 邊界:餘額歸零 | 故事 4 | — | US4-API-17 | — | — | US4-CLI-01 | — | — | — | — | — | — | US4-AJ-07 | — | 🔴🟢 |
| 邊界:Colab 帳號授權過期 | 故事 1 | — | US1-API-34 | — | — | US1-CLI-10 | — | — | — | — | — | — | — | — | 🔴🟢 |
| 邊界:後端重啟時發現不是本系統開啟的執行環境 | 故事 1 | — | US1-API-25 | — | — | US1-CLI-03 | — | — | — | — | — | — | US1-AJ-15 | — | 🔴🟢 |
| 邊界:執行環境被收回或結束時模型消失、佇列保留 | 故事 3 | — | US3-API-18、US3-API-19 | — | — | — | — | — | — | — | — | — | US3-AJ-09 | — | 🔴🟢 |
| 邊界:遠端磁碟或顯示記憶體不足以載入 | 故事 3 | — | US3-API-05 | — | — | — | — | — | — | — | — | — | — | — | 🔴🟢 |
| 邊界:兩個程式同時指名同一個尚未載入的模型 | 故事 3 | — | — | US3-OC-04 | — | — | — | — | — | — | — | — | — | — | 🔴🟢 |

## 8. 不在本次範疇

| 需求 | 為什麼不測 | 之後怎麼驗 |
|---|---|---|
| FR-019、FR-023(spec 已移除) | spec 已移除這兩條(Drive 拿掉後失去理由,research.md R4、R7),沒有要實作的行為 | 之後若加回 Drive 快取或刪除模型,另寫需求與案例 |
| NFR-012 的 Unraid 部分(在 Unraid 上以同一份 compose 啟動) | spec 假設第一個迭代只在 Ubuntu 桌機驗收,Tower 留到下一個迭代;本次實跑也不碰 Tower | 下一個迭代搬上 Tower 時,以 G-07 同樣的步驟在 Unraid 重跑,另外確認 SQLite 不放在 `/mnt/user` FUSE(Q88) |
| research.md R1 待驗證:L4、A100 等其他類型能否開到與耗用 | 實跑只用 T4(護欄 P2),其他類型耗用較高、可能開不到 | 使用者另外同意預算後,以「開啟後立即結束」的 📏 案例逐一試 |
| research.md R3 待驗證:通道連續超過 2 小時、執行環境閒置回收時的行為 | 要長時間占用執行環境,超出本次 60 分鐘、2 compute units 的預算 | 實際使用時觀察;或另開一個長時間的 📏 案例 |

## 9. 待決問題(待登記到 plan.md)

Q95~Q107 已登記到 plan.md 並決定(本計劃照決定寫:Q100 以資料庫判定遺留、資料庫不認得的只警告;Q101 授權改為複製既有 token.json,US1-OA-06 延後)。下列是這次補故事 4 時新提出、還沒登記的;編號接在 plan.md 的 Q118 之後,是提議。

| Q | 問題與可選的做法 | 先採用 |
|---|---|---|
| Q119 | 讀用量失敗、但之前讀到過時,`GET /api/usage` 回什麼:(a)回最後一次的快照(`state` 為 `known`、原本的 `readAt`),超過 15 分鐘 `stale` 為 true,`reasonCode`、`message` 說明最近一次讀取失敗;(b)一律回 `state` 為 `unknown`、數字為 null(NFR-008 的過期標示就永遠不會出現) | (a);`unknown` 只用在從來沒讀到過 |
| Q120 | 餘額為 0 或負數時的估計可用時數:(a)回 0;(b)回負數(違反 S5 `hoursRemaining` 的 `minimum: 0`);(c)回 null | (a) |
| Q121 | FR-025「低於警告門檻」含不含等於:(a)不含,`balance < threshold`;(b)含 | (a) |
| Q122 | Q100 決定「資料庫不認得、CLI 記得的執行環境在 UI 警告」放在哪個欄位:(a)`Session.unmanagedRuntimes` 多一筆(只含硬體,與 `[?]` 同樣顯示「不是本系統開啟的執行環境」);(b)放進 `releaseWarning`(會和「本系統這次釋放失敗」混在一起) | (a) |
| Q138 | `colab-cli.openapi.yaml` 的子行程逾時只寫「被終止」,沒說要不要連它分出的子行程一起清掉。(a)每個 `colab` 子行程以新的 process group 啟動,逾時時對整個 group 送 SIGTERM、等不到再 SIGKILL,並 `wait` 回收(和 S9 `closeTunnel` 同樣的做法),S8 合約補這一句;(b)只終止 `colab` 本身 | (a);US1-CLI-22~US1-CLI-27 照 (a) 斷言 |
| Q139 | `stopSession` 的 `x-failure-rules` 沒有「`colab stop` 本身超過 60 秒」這一條。(a)照合約共用約定(1)與「不論輸出是什麼都回讀」:終止 `colab stop` 後照常回讀,結果以回讀為準,不回 `COLAB_TIMEOUT`;只有回讀逾時才回 `COLAB_TIMEOUT`;(b)`colab stop` 逾時就回 `COLAB_TIMEOUT`、不回讀 | (a);US1-CLI-25、US1-CLI-26 照 (a) 斷言 |
| Q140 | `startOllama` 等 exec 的 `COLAB_NOT_FOUND` 規則寫「stdout 含 `[colab] Session '<名稱>' not found.`,或含 `appears to be lost (404/401)`」,後一個字樣是在 stdout 還是 stderr 不明。(a)兩個都看;(b)只看 stdout | (a);US1-CLI-39 的假執行檔把它印在 stdout,兩種做法都會過 |
| Q147 | `ssh-keygen` 超過時限回哪個代碼:合約 `ensureTunnelKey` 的 `x-timeout` 寫「每個命令 10 秒;逾時視為 `TUNNEL_FAILED`」,修訂指示寫 `TUNNEL_TIMEOUT`。(a)照合約回 `TUNNEL_FAILED`;(b)改合約為 `TUNNEL_TIMEOUT`(`TUNNEL_TIMEOUT` 的說明目前只有就緒期限、健康檢查、keepalive、重連時限) | (a);US1-TUN-15 照 (a) 斷言 |
| Q148 | `ensureTunnelKey` 判定寫「第一行或第三行 stdout 為空 → `TUNNEL_FAILED`」,但第一行是 `ssh-keygen -q`,成功時 stdout 本來就是空的,照字面永遠失敗。(a)第一行改讀成「跑完後 `<keyPath>` 仍不存在」;(b)照字面 | (a);S9 合約補改這句,US1-TUN-16 情況 A 照 (a) 斷言 |
| Q149 | `ssh-keygen` 的 10 秒時限要能在測試縮短:(a)`Tunnel` 建構參數加 `keygen_timeout`(和 `term_wait`、`kill_wait` 同一種做法);(b)不縮短,測試等 10 秒 | (a) |
| Q160 | G-09 比對替身與真 adapter 簽章的範圍:(a)只比真 adapter 有的公開方法,替身另有的測試控制成員(例如 `method()`、`local_port`)不比;(b)替身不得有真 adapter 沒有的公開成員 | (a) |
| Q161 | 後端重啟接回時,釋放資料庫記錄過的遺留失敗,`releaseWarning` 掛在哪:(a)掛在 `GET /api/session` 回的那筆工作階段(目前或最近一筆),寫進它的 `release_warning_*` 欄位;(b)另立一個不屬於工作階段的警告欄位(S5 要改) | (a);US1-AJ-23 照 (a) 斷言 |
