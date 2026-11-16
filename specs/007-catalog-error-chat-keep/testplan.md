# 測試計劃:模型目錄讀不到時回正確的錯誤,對話紀錄保留到工作階段結束

- **規格**:`specs/007-catalog-error-chat-keep/spec.md`
- **系統分析**:`plan.md` § 端點盤點(E1 前端 UI、E2 後端 UI API);`contracts/ui.openapi.yaml`;`prototype/models.html`、`prototype/chat.html`、`prototype/index.html`、`prototype/states.html`
- **測試技術**:`techstack.md` § 一覽;research.md R1(六種失敗組合的實測)、R3(`localStorage` 的分頁行為實測)、R4(依 `session.updated` 清除)、R6(驗收做法:替身、Playwright、SC-004 的對照組)
- **日期**:2026-11-16
- **範疇**:使用者故事 1、2;每個測試案例在 `tasks.md` 對應一組 `/tdd` 紅燈與綠燈任務,量測與人工驗證的案例對應 📏 任務
- **預設資料**:除非案例或端點節的節首說明另寫,工作階段以替身開到就緒;`FakeRemoteOllama` 讀 tags、ps 都成功;各端點節的模型目錄與對話替身寫在那一節的節首說明

## 1. 待測端點

端點、介面規格檔與公開接縫照抄 `plan.md` § 端點盤點與它指到的規格檔,本計劃不另做系統規劃;測試等級、工具與環境取自 `techstack.md` § 一覽,以及 001~006 沿用下來的整合與 Playwright 做法。上游沒寫到的,已登記到 `plan.md` 的待決問題 Q10~Q12 起,不在這裡自行補上。

| 端點 | 介面規格檔 | 公開接縫 | 測試等級 | 工具 | 測試環境 | 替身 |
|---|---|---|---|---|---|---|
| E2 後端 UI API(FastAPI REST 與 SSE) | `contracts/ui.openapi.yaml` | HTTP `GET /api/models`、`POST /api/models/preload`、`GET /api/events` 的回應;回歸:`GET /api/connect` | 整合(真的 api、services、domain;轉接層用替身) | pytest + pytest-asyncio + `httpx.ASGITransport`,沿用 `tests/conftest.py` 的 `ui_client`、`fakes`、`make_app` 與 `tests/integration/test_api_session.py` 的 `ColabWorld`、`open_ready`;要讀 SSE 的案例照既有慣例改用測試行程內 uvicorn(`live_servers`、`start_live_servers`,plan Q19) | 暫存 SQLite | `FakeRemoteOllama`(遠端 Ollama 轉接層與執行環境上的 Ollama)→ G-01<br>`FakeColabControl`、`FakeTunnel`(Colab 執行環境與通道)→ 無法實跑:spec 假設這一輪不跑 colab、不花 compute units(plan Q12)<br>`FakeOllamaServer`(執行環境上的 Ollama 的對話回覆,US2-API-09 用)→ 無法實跑:spec 假設這一輪不連真的 Ollama;007 沒有改對話轉送,004 testplan 全域案例裡的對話實跑已驗過(plan Q18) |
| 跨端點驗收 | `prototype/models.html`、`prototype/chat.html`、`prototype/index.html`、`contracts/ui.openapi.yaml` | 瀏覽器畫面上的文字與控制項、`localStorage` 的 `cgb.chat.v1` | E2E(真的 Chromium、真的後端;轉接層用替身) | Playwright(Python)+ pytest-playwright,`tests/e2e/conftest.py` 的 `e2e_servers` | 測試行程內 uvicorn,UI 127.0.0.1:8781;同一個 browser context 開多個分頁 | `FakeRemoteOllama`(遠端 Ollama 轉接層與執行環境上的 Ollama)→ G-01<br>`FakeColabControl`、`FakeTunnel`(Colab 執行環境與通道)→ 無法實跑:spec 假設這一輪不跑 colab、不花 compute units(plan Q12)<br>`add_init_script` 讓 `setItem` 丟 `QuotaExceededError`、讀 `localStorage` 丟 `SecurityError`(瀏覽器的無痕或空間不足限制,US2-AJ-22、US2-AJ-23)→ 無法實跑:Playwright 的 headless Chromium 沒有原生的無痕配額限制,真的無痕視窗要人操作,列進完成報告為未驗證(plan Q25) |
| E1 前端 UI(瀏覽器,原生 HTML/CSS/JS) | `prototype/models.html`、`prototype/chat.html`、`prototype/states.html` | — | — | — | 畫面都要先從後端拿到目錄與 `session.updated` 才看得到,照 001~006 的做法不另立端點節;畫面行為都放在跨端點驗收 | — |

### 受測操作

每個測試案例的「受測操作」欄照這張表某一列的寫法填;`tasks.md` 的 ⚙ 照「規格錨點」欄寫。

| 端點 | 受測操作 | 規格錨點 | 寫法 |
|---|---|---|---|
| E2 後端 UI API | 列出模型目錄 | `contracts/ui.openapi.yaml` § `paths./models.get`、`info.x-catalog-failure-rule`、`info.x-ollama-error-message`、`components.schemas.ModelCatalog` | `GET /api/models` |
| E2 後端 UI API | 預先載入 | `contracts/ui.openapi.yaml` § `paths./models/preload.post`、`info.x-catalog-failure-rule`、`components.schemas.PreloadState` | `POST /api/models/preload` |
| E2 後端 UI API | 訂閱推送 | `contracts/ui.openapi.yaml` § `paths./events.get` | `GET /api/events` |
| E2 後端 UI API | 連線資訊(回歸,plan Q11) | 006 的 `contracts/ui.openapi.yaml` § `getConnectInfo`(`GET /connect`;006 合約,`--contracts` 只讀 007 的檔) | `GET /api/connect` |
| E2 後端 UI API | 對話(隱私檢查,plan Q18) | 004 的 `contracts/ui.openapi.yaml` § `chat`(`POST /chat`;004 合約) | `POST /api/chat` |
| 跨端點驗收 | 模型頁:目錄、「重新讀取」、「預先載入」、預先載入失敗提示的「關閉」 | `prototype/models.html` § `[data-group="catalog"]`、`[data-state="unavailable"]`、`[data-state="empty"]`、`[data-state="preload-unavailable"]`、`#reload`、`#un-message`、`#un-code`、`#pu-message`、`#pu-close` | 模型頁 › 「<控制項>」 |
| 跨端點驗收 | 對話頁:模型選單、訊息輸入框、「送出」、「停止」、「清除」、保存狀態提示 | `prototype/chat.html` § `[data-group="chat"]`、`[data-state="chat-unavailable"]`、`[data-state="chat-model-gone"]`、`[data-group="keep"]`、`[data-state="keep-cleared"]`、`[data-state="keep-no-store"]`、`[data-group="turn"]`、`#model`、`#input`、`#send`、`#stop`、`#clear` | 對話頁 › 「<控制項>」 |
| 跨端點驗收 | 工作階段頁:「結束」、「變更類型」 | `prototype/index.html` § `#end`、`#switch` | 工作階段頁 › 「<控制項>」 |
| 跨端點驗收 | 瀏覽器本身:重新整理、另開分頁、切到別頁 | — | 瀏覽器本身 › <動作> |

### 接縫的取捨

`/tdd` 紅燈步驟直接引用這張表,不再另外和使用者確認接縫;遇到這張表沒有的接縫才停下來問。

| 接縫(公開介面) | 抓得到 | 抓不到 |
|---|---|---|
| HTTP `GET /api/models`、`POST /api/models/preload`(ASGI transport,`FakeRemoteOllama.raises()`) | 六種失敗組合的狀態碼與代碼、不回半套目錄、預先載入不改狀態、恢復後照常、`/api/connect` 回歸 | 真的轉接層遇到真的網路失敗時丟的例外是否都被歸類;由 G-01 補上 |
| HTTP `GET /api/events`(ASGI transport) | 各種結束方式推送的 `state` 與 `name` | 前端收到後真的清空;由跨端點驗收補上 |
| 瀏覽器畫面與 `localStorage`(Playwright,Chromium) | 說明文字、不顯示空目錄、保存、還原、清除、中斷標示、多分頁、5 秒內清空 | Firefox 的保存行為(research 待驗證,列進完成報告);真的 Colab 結束時的推送(plan Q12 無法實跑) |

### 測試指令

慢的測試照專案現有的方式排除(004、005、006 testplan § 測試指令):`tests/e2e`(Playwright 真瀏覽器、固定 port 8781)與 `realrun`、`realrun_local` marker(`pyproject.toml` 的 `addopts` 預設排除)。G-01 不起 `ollama serve`,但會起真的本機網路伺服器並等 10 秒逾時,照 plan Q10 標 `realrun_local`。

| 層 | 指令 | 包含 | 大約時間 |
|---|---|---|---|
| 快速層 | 照 `specs/006-agent-client-connect/testplan.md` § 1 測試指令的快速層指令(005 的快速層指令再加 `--deselect "tests/integration/test_colab_cli.py::test_重啟_Ollama_的命令列真的_colab_解讀得了"`) | `tests/unit` 與 `tests/integration`,排除 004、005 量到的慢測試與會呼叫真的 `colab` 的測試;不含 `tests/e2e`、`-m realrun`、`-m realrun_local` | 約 5 分(006 實作時每個綠燈跑一次快速層約 5 分,`specs/006-agent-client-connect/完成報告.md` 的「耗時」) |
| 全部 | `uv run pytest -q -p no:cacheprovider`,再加 `uv run pytest -m realrun_local -q -p no:cacheprovider` | 加上 `tests/e2e`(006 時 239 個)與 `realrun_local`(006 的 opencode 與 pi 本機實跑,以及本輪 G-01);`-m realrun` 這一輪不跑 | 約 12 分 |

## 2. 使用者故事 1 - 模型目錄讀不到時,看得到真正的原因(P1)

**本故事的需求**:FR-001~FR-003、NFR-001、邊界情況(只有一個查詢失敗、讀不到顯示記憶體、沒有就緒的工作階段)
**本故事涵蓋的全域 NFR**:NFR-003(彙整見第 4 節)

### 2.1 E2 後端 UI API

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-API-01 | `GET /api/models` | 工作階段就緒(`ColabWorld` + `open_ready`,T4);`FakeRemoteOllama.list_loaded_models` 回空清單 | `list_local_models` 依序以 `.raises(code, …)` 丟 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,每種各呼叫一次 `GET /api/models` | 則1:`OLLAMA_UNREACHABLE` 那一次回 502,`code` 為 `OLLAMA_UNREACHABLE`<br>則2:`OLLAMA_BAD_RESPONSE` 那一次回 502,`code` 為 `OLLAMA_BAD_RESPONSE`<br>則3:`OLLAMA_TIMEOUT` 那一次回 504,`code` 為 `OLLAMA_TIMEOUT` | `Catalog.list()` 沒接 `AdapterError`,原樣往上拋回 500(現況);或接住後一律 `ApiError(502, …)`,逾時也回 502;或代碼一律寫成 `OLLAMA_UNREACHABLE` | FR-001、使用者故事 1 驗收情境 1~3 |
| US1-API-02 | `GET /api/models` | 同 US1-API-01;替身丟錯時的 message 是 `Traceback (most recent call last): httpx.ConnectError 127.0.0.1:41234` | `list_local_models` 依序丟 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,每種各呼叫一次 `GET /api/models` | 則1:`OLLAMA_UNREACHABLE` 那一次的 `message` 等於「連不到執行環境上的 Ollama,請確認工作階段仍在運作後再試。」<br>則2:`OLLAMA_BAD_RESPONSE` 那一次的 `message` 等於「執行環境上的 Ollama 回應無法解讀,請稍後再試。」<br>則3:`OLLAMA_TIMEOUT` 那一次的 `message` 等於「執行環境上的 Ollama 在時限內沒有回應,請稍後再試。」<br>則4:三次的回應本文都不含 `Traceback`、`127.0.0.1` | 轉換時用 `ApiError(..., message=str(error))` 把轉接層的原文(traceback、本機轉發位址)交給 UI;或三個代碼共用同一句訊息 | FR-001 |
| US1-API-03 | `GET /api/models` | 工作階段就緒;`list_local_models` 回 `qwen2.5:0.5b`、`qwen2.5:7b` 兩筆 | `list_loaded_models` 依序丟 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,每種各呼叫一次 `GET /api/models` | 則1:`OLLAMA_UNREACHABLE` 那一次回 502,`code` 為 `OLLAMA_UNREACHABLE`<br>則2:`OLLAMA_BAD_RESPONSE` 那一次回 502,`code` 為 `OLLAMA_BAD_RESPONSE`<br>則3:`OLLAMA_TIMEOUT` 那一次回 504,`code` 為 `OLLAMA_TIMEOUT`<br>則4:三次的回應本文都只有 `code`、`message` 兩個鍵,沒有 `items` | 只接住 tags 的 `AdapterError`,ps 的原樣拋出回 500;或 ps 讀不到時當成「沒有已載入的模型」,回 200 與兩筆 `loaded: false` 的半套目錄 | FR-001、邊界情況(只有一個查詢失敗) |
| US1-API-04 | `GET /api/models` | 工作階段就緒 | `list_local_models` 丟 `OLLAMA_UNREACHABLE`、`list_loaded_models` 丟 `OLLAMA_TIMEOUT`,呼叫一次 `GET /api/models` | 則1:回 502,`code` 為 `OLLAMA_UNREACHABLE`(以先讀的 tags 為準) | 改成 `asyncio.gather` 並行讀兩份清單、以最後完成的 ps 的錯誤為準,回 504 `OLLAMA_TIMEOUT`;或以「逾時優先」挑代碼 | FR-001、邊界情況(只有一個查詢失敗) |
| US1-API-05 | `GET /api/models` | 工作階段就緒;tags 回 `qwen2.5:7b`(4,683,087,332 位元組)、ps 回空清單;`FakeColabControl.probe_resources` 丟 `COLAB_TIMEOUT` | 呼叫一次 `GET /api/models` | 則1:回 200<br>則2:`vramBytes` 為 null<br>則3:`qwen2.5:7b` 的 `mayNotFit` 為 null | 新加的 `except AdapterError` 包住整個 `list()`(含 `_vram_total`),或在 `_vram_total` 拿掉原本的接法,讀不到顯示記憶體也被轉成 502 | 邊界情況(讀不到顯示記憶體) |
| US1-API-06 | `GET /api/models` | 沒有開工作階段;`list_local_models`、`list_loaded_models` 都設成丟 `OLLAMA_UNREACHABLE` | 呼叫 `GET /api/models` | 則1:`GET /api/models` 回 503,`code` 為 `NO_READY_SESSION`<br>則2:`list_local_models` 的呼叫次數為 0 | 轉換寫成 `except Exception` 一律 `ollama_error`,把 `require_ready_base_url()` 丟的 503 `NO_READY_SESSION` 也轉成 502;或把讀遠端搬到檢查工作階段之前 | 邊界情況(沒有就緒的工作階段) |
| US1-API-07 | `GET /api/models` | 工作階段就緒,記下 `GET /api/session` 的 `name`;tags 回 `qwen2.5:0.5b`、`qwen2.5:7b`,ps 回 `qwen2.5:0.5b`;`list_local_models` 以 `.then()` 設成第一次丟 `OLLAMA_UNREACHABLE`、之後照常 | 連續呼叫兩次 `GET /api/models`,再呼叫 `GET /api/session` | 則1:第一次回 502,`code` 為 `OLLAMA_UNREACHABLE`<br>則2:第二次回 200,`items` 的名稱是 `qwen2.5:0.5b`、`qwen2.5:7b`<br>則3:第二次 `qwen2.5:0.5b` 的 `loaded` 為 true<br>則4:`GET /api/session` 的 `state` 為 `ready`、`name` 和開始時相同 | 讀不到目錄時把錯誤或空目錄快取起來,之後一直回同樣的結果;或讀不到時讓工作階段轉成 `lost`、`reconnecting`,要重開才恢復 | FR-001、使用者故事 1 驗收情境 5 |
| US1-API-08 | `POST /api/models/preload` → `GET /api/models` | 以 `live_servers` 起 app,工作階段就緒;tags 回 `qwen2.5:7b`、`hf.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF:Q4_K_M`,ps 回空清單;`hf.co/…` 先預先載入一次,`preload` 丟 `OLLAMA_SERVER_ERROR`,等到目錄裡它的 `preload.state` 為 `failed` 且已收到那則 `models.updated`;之後 `remote.preload.reset_calls()`,`list_local_models` 改丟 `OLLAMA_UNREACHABLE`;`/api/events` 連著 | 送 `POST /api/models/preload` `{"name":"qwen2.5:7b"}`;等 1 秒後 tags 恢復照常,呼叫 `GET /api/models` | 則1:`POST /api/models/preload` 回 502,`code` 為 `OLLAMA_UNREACHABLE`<br>則2:`remote.preload` 的呼叫次數為 0<br>則3:`GET /api/models` 裡 `qwen2.5:7b` 的 `preload.state` 為 `idle`<br>則4:`GET /api/models` 裡 `hf.co/…` 的 `preload.state` 為 `failed`、`reasonCode` 為 `OLLAMA_SERVER_ERROR`<br>則5:送出預先載入後 1 秒內 `/api/events` 沒有收到 `models.updated` | 先把 `qwen2.5:7b` 標成 `loading` 再確認目錄,失敗後殘留 `loading`;或確認失敗時把 `qwen2.5:7b` 標成 `failed`;或失敗時清空 `_preloads`,其他模型的 `failed` 不見了;或失敗時照樣 `spawn` 或 `publish()` | FR-002、使用者故事 1 驗收情境 4 |
| US1-API-09 | `POST /api/models/preload` | 工作階段就緒;ps 回空清單;`remote.preload.reset_calls()` | `list_local_models` 依序丟 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,每種各送一次 `POST /api/models/preload` `{"name":"qwen2.5:7b"}` | 則1:`OLLAMA_UNREACHABLE` 那一次回 502,`code` 為 `OLLAMA_UNREACHABLE`<br>則2:`OLLAMA_BAD_RESPONSE` 那一次回 502,`code` 為 `OLLAMA_BAD_RESPONSE`<br>則3:`OLLAMA_TIMEOUT` 那一次回 504,`code` 為 `OLLAMA_TIMEOUT`<br>則4:三次之後 `remote.preload` 的呼叫次數為 0 | `preload()` 沒接 `list()` 拋出的錯,回 500;或確認目錄讀不到時當成空目錄往下走,回 404 `OLLAMA_NOT_FOUND`;或讀不到仍受理、回 202 並送出載入 | FR-002、使用者故事 1 驗收情境 4 |
| US1-API-10 | `POST /api/models/preload` | 工作階段就緒;tags 回 `qwen2.5:7b`;`remote.preload.reset_calls()` | `list_loaded_models` 依序丟 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,每種各送一次 `POST /api/models/preload` `{"name":"qwen2.5:7b"}` | 則1:`OLLAMA_UNREACHABLE` 那一次回 502,`code` 為 `OLLAMA_UNREACHABLE`<br>則2:`OLLAMA_BAD_RESPONSE` 那一次回 502,`code` 為 `OLLAMA_BAD_RESPONSE`<br>則3:`OLLAMA_TIMEOUT` 那一次回 504,`code` 為 `OLLAMA_TIMEOUT`<br>則4:三次之後 `remote.preload` 的呼叫次數為 0 | 預先載入改成只讀 tags 確認模型在不在,ps 讀不到被略過而回 202 受理;或只接 tags 的錯,ps 的錯回 500 | FR-002、邊界情況(只有一個查詢失敗) |
| US1-API-11 | `POST /api/models/preload` | 同 US1-API-09;替身丟錯時的 message 是 `Traceback (most recent call last): httpx.ConnectError 127.0.0.1:41234` | `list_local_models` 依序丟 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,每種各送一次 `POST /api/models/preload` `{"name":"qwen2.5:7b"}` | 則1:`OLLAMA_UNREACHABLE` 那一次的 `message` 等於「連不到執行環境上的 Ollama,請確認工作階段仍在運作後再試。」<br>則2:`OLLAMA_BAD_RESPONSE` 那一次的 `message` 等於「執行環境上的 Ollama 回應無法解讀,請稍後再試。」<br>則3:`OLLAMA_TIMEOUT` 那一次的 `message` 等於「執行環境上的 Ollama 在時限內沒有回應,請稍後再試。」<br>則4:三次的回應本文都沒有 `model` 鍵 | 預先載入的路由自己接錯、用 `str(error)` 或預先載入失敗的那句 `PRELOAD_FAILED_MESSAGE` 當訊息;或照下載錯誤的寫法帶上 `Error.model`(合約說這三個錯誤沒有 `model`) | FR-002 |
| US1-API-12 | `POST /api/models/preload` | 工作階段就緒,記下 `name`;tags 回 `qwen2.5:7b`、ps 回空清單;`list_local_models` 以 `.then()` 設成第一次丟 `OLLAMA_UNREACHABLE`、之後照常;`remote.preload` 停在閘門前;`remote.preload.reset_calls()` | 送兩次 `POST /api/models/preload` `{"name":"qwen2.5:7b"}`,再呼叫 `GET /api/session` | 則1:第一次回 502,`code` 為 `OLLAMA_UNREACHABLE`<br>則2:第二次回 202,`preload.state` 為 `loading`<br>則3:第二次之後 1 秒內 `remote.preload` 被呼叫 1 次<br>則4:`GET /api/session` 的 `state` 為 `ready`、`name` 和開始時相同 | 第一次在確認目錄前就寫入 `loading`,第二次被當成「正在載入」不再送出(呼叫 0 次);或讀不到時讓工作階段轉成 `lost`、`reconnecting`,要重開才恢復 | FR-002、使用者故事 1 驗收情境 5 |
| US1-API-13 | `POST /api/models/preload` | 工作階段就緒;tags 只回 `qwen2.5:0.5b`、ps 回空清單 | 送 `POST /api/models/preload` `{"name":"qwen2.5:7b"}` | 則1:回 404,`code` 為 `OLLAMA_NOT_FOUND` | 轉換寫成同時接 `AdapterError` 與 `ApiError` 一律 `ollama_error`,把「不在目錄裡」的 404 也轉成 502 | FR-002(回歸:001 的 404 不受影響) |
| US1-API-14 | `GET /api/connect` | 工作階段就緒(T4、套用 context 4096);ps 回空清單 | `list_local_models` 依序丟 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,每種各呼叫一次 `GET /api/connect`;再讓 tags 照常、`list_loaded_models` 丟 `OLLAMA_TIMEOUT`,呼叫一次 `GET /api/connect` | 則1:tags `OLLAMA_UNREACHABLE` 那一次回 502,`code` 為 `OLLAMA_UNREACHABLE`<br>則2:tags `OLLAMA_BAD_RESPONSE` 那一次回 502,`code` 為 `OLLAMA_BAD_RESPONSE`<br>則3:tags `OLLAMA_TIMEOUT` 那一次回 504,`code` 為 `OLLAMA_TIMEOUT`<br>則4:ps `OLLAMA_TIMEOUT` 那一次回 504,`code` 為 `OLLAMA_TIMEOUT` | 轉換寫在 `api/models.py` 的兩個路由而不是 `Catalog.list()`,又照 research R1 拿掉 `connect.py` 的 `except AdapterError`,`/api/connect` 讀不到時變成 500;或 `connect.py` 改成接 `ApiError` 回 200 與 `reason: no_models` | FR-001(回歸:006 `getConnectInfo`,plan Q11) |
| US1-API-15 | `GET /api/connect` | 同 US1-API-14;替身丟錯時的 message 是 `Traceback (most recent call last): httpx.ConnectError 127.0.0.1:41234` | `list_local_models` 依序丟 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`,每種各呼叫一次 `GET /api/connect` | 則1:`OLLAMA_UNREACHABLE` 那一次的 `message` 等於「連不到執行環境上的 Ollama,請確認工作階段仍在運作後再試。」<br>則2:`OLLAMA_BAD_RESPONSE` 那一次的 `message` 等於「執行環境上的 Ollama 回應無法解讀,請稍後再試。」<br>則3:`OLLAMA_TIMEOUT` 那一次的 `message` 等於「執行環境上的 Ollama 在時限內沒有回應,請稍後再試。」 | `Catalog.list()` 轉換時另給一句目錄專用的訊息(`message=` 覆寫),`/api/connect` 跟著變成和 006 不同的說法;或帶上轉接層的原文 | FR-001(回歸:006 `getConnectInfo`,plan Q11) |
| US1-API-17 | `POST /api/models/preload` | 沒有開工作階段;`list_local_models`、`list_loaded_models` 都設成丟 `OLLAMA_UNREACHABLE` | 送 `POST /api/models/preload` `{"name":"qwen2.5:7b"}` | 則1:`POST /api/models/preload` 回 503,`code` 為 `NO_READY_SESSION`<br>則2:`list_local_models` 的呼叫次數為 0 | 轉換寫成 `except Exception` 一律 `ollama_error`,把 `require_ready_base_url()` 丟的 503 `NO_READY_SESSION` 也轉成 502;或把讀遠端搬到檢查工作階段之前 | 邊界情況(沒有就緒的工作階段) |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-API-16 | 可靠性(讀不到遠端時不回 500) | 🔴🟢 行為測試 | `GET /api/models` → `POST /api/models/preload` | 工作階段就緒;tags 回 `qwen2.5:7b`、ps 回空清單 | 失敗的清單(tags、ps)× 代碼(`OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`)六種組合,每種各呼叫一次 `GET /api/models` 與 `POST /api/models/preload` `{"name":"qwen2.5:7b"}`,共 12 次;每種組合之間把兩份清單重設成照常 | 則1:`GET /api/models` 的 6 次狀態碼依序為 502、502、504、502、502、504(tags 三種、ps 三種),`code` 依序為 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`、`OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`<br>則2:`POST /api/models/preload` 的 6 次狀態碼與 `code` 和則1 的順序相同<br>則3:12 次裡回 500 的次數為 0 | 只修了其中一個操作或其中一份清單,剩下的組合仍回 500;或某個組合被歸到錯的狀態碼 | NFR-001、SC-001 | — | — |

### 2.2 跨端點驗收

接真的 Chromium 與真的後端(測試行程內 uvicorn,UI 127.0.0.1:8781,`tests/e2e/conftest.py` 的 `e2e_servers`),遠端 Ollama、Colab 執行環境與通道用替身(`FakeRemoteOllama`、`FakeColabControl`、`FakeTunnel`,讓 `list_local_models`/`list_loaded_models` 以 `.raises(code, …)` 失敗、以 `.side_effect(world._local_models)` 等恢復),E2 端點節完成後才開始。除非案例另寫,工作階段已由工作階段頁開到就緒(`open_to_ready`),執行環境上有 `qwen2.5:0.5b`(398 MB,已載入)、`llama3.2:3b`(2.0 GB,未載入)、`qwen2.5:7b`(4.7 GB,未載入),顯示記憶體 15 GiB(三個都不會跳預先載入前的 `preload-warn`);下文的三句說明是 `contracts/ui.openapi.yaml` § `info.x-ollama-error-message` 的原句:U=「連不到執行環境上的 Ollama,請確認工作階段仍在運作後再試。」、B=「執行環境上的 Ollama 回應無法解讀,請稍後再試。」、T=「執行環境上的 Ollama 在時限內沒有回應,請稍後再試。」。

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-AJ-01 | 瀏覽器本身 › 打開模型頁 | 替身的 `list_local_models`(tags)丟 `OLLAMA_UNREACHABLE` | 打開 `/models.html` | 則1:5 秒內 `[data-state="unavailable"]` 顯示<br>則2:`#un-message` 的文字等於 U<br>則3:`#un-code` 的文字是 `OLLAMA_UNREACHABLE`(列目錄 502)<br>則4:`[data-state="empty"]` 隱藏,頁面上沒有「還沒有模型」字樣<br>則5:`[data-state="loading"]` 隱藏<br>則6:`#catalog li` 是 0 列 | `loadCatalog()` 只處理成功與 `NO_READY_SESSION`,其他失敗時畫面停在「正在讀取執行環境上的模型…」;或把非成功的回應當成空目錄顯示 `empty`;或說明寫死在前端、沒用後端的 `message` | FR-003、驗收情境 1、SC-001 |
| US1-AJ-02 | 瀏覽器本身 › 打開模型頁 | 替身的 tags 照常回 3 個模型,`list_loaded_models`(ps)丟 `OLLAMA_BAD_RESPONSE` | 打開 `/models.html` | 則1:5 秒內 `[data-state="unavailable"]` 顯示<br>則2:`#un-message` 的文字等於 B<br>則3:`#un-code` 的文字是 `OLLAMA_BAD_RESPONSE`(列目錄 502)<br>則4:`#catalog li` 是 0 列,沒有任何一個模型名稱出現在頁面上<br>則5:`[data-state="empty"]` 隱藏 | 後端只在讀 tags 時接住錯誤,ps 失敗時仍回 500,畫面停在讀取中或顯示一般錯誤;或後端/前端在 ps 失敗時回半套目錄,把 tags 讀到的 3 個模型照列 | FR-003、驗收情境 2、SC-001、邊界情況(只有其中一個查詢失敗) |
| US1-AJ-03 | 瀏覽器本身 › 打開模型頁 | 替身的 tags 丟 `OLLAMA_TIMEOUT` | 打開 `/models.html` | 則1:5 秒內 `[data-state="unavailable"]` 顯示<br>則2:`#un-message` 的文字等於 T<br>則3:`#un-code` 的文字是 `OLLAMA_TIMEOUT`(列目錄 504)<br>則4:`[data-state="empty"]` 隱藏 | 前端只認 502(例如判斷 `status === 502`),504 落到其他分支而停在讀取中或顯示成空目錄;或後端把逾時歸成 `OLLAMA_UNREACHABLE`,說明變成 U | FR-003、驗收情境 3、SC-001 |
| US1-AJ-04 | 瀏覽器本身 › 打開模型頁 → 模型頁 › 「重新讀取」 | 替身的 tags 丟 `OLLAMA_UNREACHABLE`;打開 `/models.html`,`[data-state="unavailable"]` 已顯示 | 把 tags 恢復成照常回 3 個模型,按「重新讀取」 | 則1:5 秒內 `[data-state="normal"]` 顯示<br>則2:`#catalog li` 是 3 列<br>則3:`[data-state="unavailable"]` 隱藏<br>則4:替身的 `create_session` 呼叫次數仍是 1(沒有重開工作階段) | 「重新讀取」沒有接到 `loadCatalog()`;或讀到目錄後 `unavailable` 仍留著蓋在目錄上;或後端把失敗記在工作階段上,遠端恢復後仍回 502,要重開工作階段才讀得到 | FR-003、驗收情境 5 |
| US1-AJ-05 | 瀏覽器本身 › 打開模型頁 → 模型頁 › 「重新讀取」 | 替身的 tags 丟 `OLLAMA_TIMEOUT`;打開 `/models.html`,`[data-state="unavailable"]` 已顯示 | 把 tags 恢復成回空的清單(`world.models` 清空),按「重新讀取」 | 則1:5 秒內 `[data-state="empty"]` 顯示<br>則2:`[data-state="unavailable"]` 隱藏 | 為了不顯示成空目錄,把「讀到 0 個模型」也一律顯示成 `unavailable`,真的空的執行環境再也看不到「挑選要下載的模型」 | FR-003、驗收情境 5 |
| US1-AJ-06 | 模型頁 › 「預先載入」 | 打開 `/models.html`,`#catalog li` 已顯示 3 列;之後替身的 tags 丟 `OLLAMA_UNREACHABLE` | 按 `llama3.2:3b` 那一列的「預先載入」 | 則1:5 秒內 `[data-state="preload-unavailable"]` 顯示<br>則2:`#pu-name` 的文字是 `llama3.2:3b`<br>則3:`#pu-message` 的文字等於 U<br>則4:`#pu-code` 的文字是 `OLLAMA_UNREACHABLE`(預先載入 502)<br>則5:`#catalog li` 仍是 3 列<br>則6:`llama3.2:3b` 那一列仍有「預先載入」按鈕,沒有「載入中」<br>則7:`qwen2.5:0.5b` 那一列仍標「已載入」<br>則8:`qwen2.5:7b` 那一列仍有「預先載入」按鈕<br>則9:`[data-state="unavailable"]` 隱藏<br>則10:替身的 `preload` 呼叫次數是 0 | `preload()` 收到非 202 時直接 `return`,畫面沒有任何提示;或失敗後重讀目錄,把整個目錄換成 `unavailable` 或清空,其他模型跟著消失;或後端先把那一列標成 `loading`/`failed` 才確認目錄,那一列顯示「載入中」或「預先載入失敗」 | FR-003、驗收情境 4、SC-001 |
| US1-AJ-07 | 模型頁 › 「預先載入」 → 模型頁 › 「關閉」 → 模型頁 › 「預先載入」 | 打開 `/models.html`,`#catalog li` 已顯示 3 列;之後替身的 tags 丟 `OLLAMA_TIMEOUT` | 按 `qwen2.5:7b` 的「預先載入」,看到提示後按 `#pu-close`「關閉」;把 tags 恢復成照常,再按一次 `qwen2.5:7b` 的「預先載入」 | 則1:第一次按下後 `#pu-code` 的文字是 `OLLAMA_TIMEOUT`(預先載入 504)<br>則2:第一次按下後 `#pu-message` 的文字等於 T<br>則3:按「關閉」後 `[data-state="preload-unavailable"]` 隱藏<br>則4:按「關閉」後 `#catalog li` 仍是 3 列<br>則5:第二次按下後 5 秒內 `qwen2.5:7b` 那一列顯示「載入中」<br>則6:第二次按下後 `[data-state="preload-unavailable"]` 仍隱藏<br>則7:替身的 `preload` 收到一次 `model="qwen2.5:7b"` 的呼叫 | 前端只處理預先載入的 502,504 沒有提示;或「關閉」沒接事件、提示關不掉;或第二次受理後沒先收起上一次的提示,舊的失敗說明蓋在載入中的目錄上;或後端在確認目錄失敗後留下狀態,恢復後仍不受理 | FR-003、驗收情境 4、驗收情境 5 |
| US1-AJ-08 | 瀏覽器本身 › 打開對話頁 | 替身的 tags 丟 `OLLAMA_BAD_RESPONSE` | 打開 `/chat.html` | 則1:5 秒內 `[data-state="chat-unavailable"]` 顯示<br>則2:`[data-state="chat-unavailable"] #un-message` 的文字等於 B<br>則3:`[data-state="chat-unavailable"] #un-code` 的文字是 `OLLAMA_BAD_RESPONSE`(列目錄 502)<br>則4:`[data-state="chat-no-session"]` 隱藏<br>則5:`[data-state="chat-no-models"]` 隱藏<br>則6:`#send` 停用<br>則7:`#input` 停用 | `chat.js` 的 `loadModels()` 對任何非成功的回應都設成 `chat-no-session`,讀不到目錄被說成沒有就緒的工作階段;或把失敗當成 0 個模型顯示 `chat-no-models`;或顯示說明但沒停用送出 | research R2(對話頁) |
| US1-AJ-09 | 對話頁 › 「送出」 → 瀏覽器本身 › 重新整理 | 打開 `/chat.html`,選 `qwen2.5:0.5b`,送出「你好」並收完替身的回覆「一二三四五六」;之後替身的 tags 丟 `OLLAMA_TIMEOUT` | 重新整理對話頁 | 則1:5 秒內 `[data-state="chat-unavailable"]` 顯示<br>則2:`[data-state="chat-unavailable"] #un-code` 的文字是 `OLLAMA_TIMEOUT`(列目錄 504)<br>則3:`#log .msg-user` 是 1 則,文字是「你好」<br>則4:`#log .msg-bot` 是 1 則,含「一二三四五六」<br>則5:`[data-state="keep-on"]` 顯示<br>則6:`[data-state="keep-cleared"]` 隱藏<br>則7:`localStorage` 的 `cgb.chat.v1` 仍有 2 則 `messages` | 把讀不到目錄當成工作階段結束,清掉保存的對話並顯示「工作階段已結束,對話已清除」;或讀不到目錄時不還原保存的對話,畫面只剩空白 | research R2(對話頁)、FR-004 |
| US1-AJ-10 | 瀏覽器本身 › 另開分頁 → 工作階段頁 › 「結束」 | 同一個 browser context:分頁 A 開 `/models.html`、分頁 B 開 `/chat.html`;替身的 tags 丟 `OLLAMA_UNREACHABLE`,A 已顯示 `[data-state="unavailable"]`、B 已顯示 `[data-state="chat-unavailable"]` | 另開分頁 C 打開工作階段頁,按「結束」並確認 | 則1:A 不重新整理,5 秒內 `[data-state="no-session"]` 顯示<br>則2:A 的 `[data-state="unavailable"]` 隱藏<br>則3:B 不重新整理,5 秒內 `[data-state="chat-no-session"]` 顯示<br>則4:B 的 `[data-state="chat-unavailable"]` 隱藏 | 前端把所有失敗(含 503 `NO_READY_SESSION`)都顯示成讀不到目錄,原因反過來說錯;或 `unavailable`/`chat-unavailable` 顯示後就不再跟著 `session.updated` 重讀目錄,工作階段結束了仍叫使用者「重新讀取」 | FR-003、research R2(對話頁)、邊界情況(沒有就緒的工作階段) |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-AJ-11 | 介面語言(繁體中文,代碼與模型名稱保留原文) | 🔴🟢 行為測試 | 模型頁 › 「預先載入」 → 瀏覽器本身 › 另開分頁 → 模型頁 › 「重新讀取」 | 依 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT` 各跑一次(參數化);分頁 A 打開 `/models.html`,`#catalog li` 已顯示 3 列;之後替身的 tags 丟這一次的代碼 | 在 A 按 `llama3.2:3b` 的「預先載入」;另開分頁 B 打開 `/chat.html`;回 A 按「重新讀取」 | 則1:A 的 `#pu-message` 等於這個代碼的原句(U、B 或 T)<br>則2:A 的 `#pu-code` 是這個代碼原文(全大寫,未翻譯)<br>則3:A 的 `#pu-name` 是 `llama3.2:3b` 原文<br>則4:A 的 `[data-state="preload-unavailable"]` 去掉 `#pu-message`、`#pu-code`、`#pu-name` 之後的文字(含「關閉」按鈕)不含任何 A–Z、a–z 字母<br>則5:B 的 `[data-state="chat-unavailable"]` 去掉 `#un-message`、`#un-code` 之後的文字(含「重新讀取」按鈕)不含任何 A–Z、a–z 字母<br>則6:B 的 `#un-code` 是這個代碼原文<br>則7:按「重新讀取」後 A 的 `[data-state="unavailable"]` 去掉 `#un-message`、`#un-code` 之後的文字不含任何 A–Z、a–z 字母<br>則8:A 的 `#un-message` 等於這個代碼的原句 | 前端沒有 `message` 時退回顯示 `response.statusText`(例如「Bad Gateway」「Gateway Timeout」)或「Error 502」;或新加的標題、按鈕沿用英文(「Retry」「Close」);或把代碼轉成中文或小寫、把模型名稱翻譯或截斷 | NFR-003、FR-003 | — | — |

### 2.3 交給 `/tdd` 的順序

每個案例在 `tasks.md` 是一組紅燈、綠燈任務;每一節的案例都做完後,接一個重構任務。同一個故事的端點節彼此平行,跨端點驗收在端點節都完成後才開始。

1. E2 後端 UI API:US1-API-01 → US1-API-02 → US1-API-03 → US1-API-04 → US1-API-05 → US1-API-06 → US1-API-07 → US1-API-08 → US1-API-09 → US1-API-10 → US1-API-11 → US1-API-12 → US1-API-13 → US1-API-14 → US1-API-15 → US1-API-16 → US1-API-17 → 重構
2. 跨端點驗收(2.1 完成後):US1-AJ-01 → US1-AJ-02 → US1-AJ-03 → US1-AJ-04 → US1-AJ-05 → US1-AJ-06 → US1-AJ-07 → US1-AJ-08 → US1-AJ-09 → US1-AJ-10 → US1-AJ-11 → 重構

## 3. 使用者故事 2 - 對話紀錄保留到工作階段結束(P2)

**本故事的需求**:FR-004~FR-008、NFR-002、邊界情況(兩個分頁同時開著、瀏覽器不允許保存、後端重新啟動後重連接回、保存的模型已不在目錄裡)
**本故事涵蓋的全域 NFR**:NFR-003(彙整見第 4 節)

### 3.1 E2 後端 UI API

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US2-API-01 | `GET /api/events` | `start_live_servers(make_app())` 起真的 HTTP;`ColabWorld(fakes)`,`open_ready` 開到就緒,記下 `name`;一條 `GET /api/events` 已讀完連上時的快照,之後的 `session.updated` 依序記下(含收到的 `time.monotonic()`) | 送 `DELETE /api/session`,之後讀 SSE 2 秒 | 則1:送出後 2 秒內收到一則 `session.updated`,`session.state` 為 `ended`<br>則2:那一則的 `session.name` 等於開啟時記下的 `name`<br>則3:那一則之後的 0.5 秒內,沒有任何一則 `session.updated` 的 `state` 是 `opening`、`ready`、`applying_tuning`、`reconnecting` 或 `ending` | 結束流程在 `stop_session` 確認後以 SQL 直接把那一列改成 `ended`、沒經過 `SessionsRepo.update` 的 listener,SSE 停在 `ending`,開著的對話頁永遠等不到結束狀態(既有 `test_api_events.py` 的 001 案例「US1 API 38」 只斷言到 `ending`);或推送時用的是寫入前讀到的那一列,`ended` 之後又補推一則 `ending` | FR-006 |
| US2-API-02 | `GET /api/events` | 照 US2-API-01 的訂閱方式,但用 `make_app()` 加 `fake_clock`;閒置時限以 `PUT /api/settings` 設 1 分鐘;`open_ready` 開到就緒,記下 `name` 與 `idle.deadline` | `fake_clock.set(deadline + 1 秒)`,之後讀 SSE 2 秒 | 則1:推進時鐘後 2 秒內收到一則 `session.updated`,`session.state` 為 `ended`、`session.endReason` 為 `IDLE_TIMEOUT`<br>則2:那一則的 `session.name` 等於開啟時的 `name` | 閒置監看在背景結束工作階段時走一條不觸發 listener 的寫入(例如直接呼叫 `colab.stop_session` 後只更新歷史),資料庫是 `ended` 但沒有任何 `session.updated` 推出(既有 `test_api_idle.py` 的 US4-API-12 只以 `GET /api/session` 輪詢,抓不到沒推送) | FR-006 |
| US2-API-03 | `GET /api/events` | 照 US2-API-01;`open_ready` 開到就緒,記下 `name` | `world.alive.remove(name)`,`fakes.tunnel.check_health.raises("TUNNEL_UNREACHABLE", "連不到")`,之後讀 SSE 2 秒 | 則1:開始失敗後 2 秒內收到一則 `session.updated`,`session.state` 為 `lost`、`session.endReason` 為 `RECLAIMED_BY_COLAB`<br>則2:那一則的 `session.name` 等於開啟時的 `name` | 健康檢查判定被收回時只把結果寫進記憶體裡的監看狀態、沒寫進 `sessions`,SSE 不推 `lost`,前端停在 `ready` 不清除(既有 `test_api_health.py` 的 001 案例「US1 API 17」 只以 `GET /api/session` 輪詢) | FR-006 |
| US2-API-04 | `GET /api/events` | 照 US2-API-01;重連時限 2 秒(`TEST_TIMEOUTS`);`record_rounds(world, fakes)` 讓 `open_tunnel` 一直回 `TUNNEL_UNREACHABLE`;`open_ready` 開到就緒,記下 `name` | `fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "連不到"))`,之後讀 SSE 4 秒 | 則1:收到至少一則 `state` 為 `reconnecting` 的 `session.updated`,它的 `session.name` 等於開啟時的 `name`<br>則2:第一次 `close_tunnel` 之後 1.8 到 2.5 秒之間收到 `state` 為 `lost`、`endReason` 為 `RECONNECT_TIMEOUT` 的 `session.updated`<br>則3:那一則 `lost` 的 `session.name` 等於開啟時的 `name` | 重連逾時時直接刪掉那一列或把它改回沒有工作階段,推送的是 `state: none`、沒有 `name`,前端拿不到結束狀態也比不了名稱;或重連逾時的判定只停止重連、不寫 `lost`,SSE 一直停在 `reconnecting` | FR-006 |
| US2-API-05 | `GET /api/events` | 照 US2-API-01;`with_loaded_model(world, fakes)`(`tests/integration/test_api_switch.py`);`open_ready` 開到就緒,記下 `old` 為它的 `name` | 送 `POST /api/session/restart {runtimeType:{gpu:"L4",highMem:false}}`,記下回應的 `name`;之後讀 SSE,直到收到 `name` 不是 `old` 且 `state` 為 `ready` 的一則或 4 秒到 | 則1:送出後 2 秒內收到一則 `session.name` 不等於 `old` 的 `session.updated`<br>則2:第一則 `name` 不是 `old` 的 `session.updated`,`name` 等於 restart 回應的 `name`<br>則3:收到第一則新 `name` 之後到讀完為止,沒有任何一則 `session.updated` 的 `session.name` 等於 `old` | 變更類型沿用舊的工作階段名稱、只換 `runtimeType`,前端比不出名稱不同而保留上一個工作階段的對話;或 listener 推送的是剛寫入的那一列而不是 `latest()`,舊的那台在背景改成 `ended` 時插進一則 `name` 為 `old` 的推送,前端已經在新工作階段記下的對話被誤清 | FR-006 |
| US2-API-06 | `GET /api/events` | 照 US2-API-04 讓重連一直失敗;`open_ready` 開到就緒,記下 `name`;`check_health` 失敗一次後以 `wait_until` 等到 `GET /api/session` 的 `state` 為 `reconnecting`(這時還沒有開 SSE) | 在重連中新開一條 `GET /api/events`(相當於對話頁重新整理),讀第一則事件 | 則1:這條連線收到的第一則事件(不論名稱)的 `event:` 是 `session.updated`<br>則2:那一則的 `session.state` 是 `reconnecting`<br>則3:那一則的 `session.name` 等於開啟時的 `name` | 連上時先送 `downloads.snapshot` 或 `autoDownload.updated` 再送工作階段,前端拿第一則以外的事件判斷而先畫空白;或快照在重連中把 `Session` 縮成只有 `state` 的形狀、不帶 `name`,前端比不了名稱而清掉還在的對話(既有 `test_api_health.py` 的 001 案例「US1 API 18」 是在重連前就連上,只看到變化、沒看重連中新連上的快照;`test_api_events.py` 的 001 案例「US1 API 38」 用 `next_session_update` 跳過其他事件,沒有斷言「第一則」) | FR-006、邊界情況:工作階段在後端重新啟動後重連接回 |
| US2-API-07 | `GET /api/events` | `make_app()` 以 `start_live_servers` 起一次,`ColabWorld(fakes)`、`open_ready` 開到就緒,記下 `name`,停掉 server(同一個 `db_path` 與替身狀態);`reset_calls(fakes)`(`tests/integration/test_api_recovery.py`) | 以 `start_live_servers(make_app())` 重新起後端,立刻開一條 `GET /api/events`,讀 3 秒 | 則1:第一則事件的 `event:` 是 `session.updated`<br>則2:第一則的 `session.name` 等於重啟前的 `name`<br>則3:第一則的 `session.state` 是 `ready`、`reconnecting`、`applying_tuning` 或 `ending` 其中之一(不是 `none`、`ended`、`open_failed`、`lost`)<br>則4:3 秒內收到 `state` 為 `ready`、`name` 等於重啟前 `name` 的 `session.updated` | 後端啟動時先把未結束的那一列標成 `ended` 再為同一台執行環境新增一列(新的名稱),或接回完成前快照回 `none`,前端在後端重啟後把同一個工作階段的對話清掉(既有 `test_api_recovery.py` 的 001 案例「US1 API 23」 只以 `GET /api/session` 看接回完成後的結果,沒看接回途中新連上的快照) | FR-006、邊界情況:工作階段在後端重新啟動後重連接回 |
| US2-API-08 | `GET /api/events` | 照 US2-API-01;`open_ready` 開到就緒記下 `a`,`DELETE /api/session` 後等到 `ended`;再 `open_ready` 開第二個,記下 `b` | 新開一條 `GET /api/events`(相當於新的工作階段就緒後才打開對話頁),讀第一則事件 | 則1:第一則事件的 `event:` 是 `session.updated`<br>則2:那一則的 `session.name` 等於 `b`<br>則3:那一則的 `session.state` 是 `ready` | 快照用 `ORDER BY opened_at` 取最新一列、沒有 `rowid` 的次序,假時鐘下兩個工作階段的 `opened_at` 相同時回到 `a`,前端把上一個工作階段的對話當成目前的還原(驗收情境 7) | FR-006 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US2-API-09 | 隱私(對話內容不寫進資料庫、日誌與推送) | 🔴🟢 行為測試 | `POST /api/chat` → `GET /api/events` | 沿用 `tests/integration/test_api_chat.py` 的 `bridge`(真的 HTTP、`FakeOllamaServer` 回 `/api/chat`),`bridge.ready()` 開到就緒;`caplog.set_level(logging.DEBUG)`(根 logger);標記 `CHAT_MARK = "cgb-test-007-對話-不該留下"`、對照 `CONTROL_MARK = "cgb-test-007-對照-應找得到"`;替身 `/api/chat` 回 `NdjsonReply([chunk(CHAT_MARK), DONE])`;一條 `GET /api/events` 在背景把收到的每一行原文附加進一個字串;判斷「出現幾次」只用同一個 `count_mark(text_or_bytes, mark)`(字串與 UTF-8 位元組都搜) | 先做對照:以 `logging.getLogger("cgb").info(CONTROL_MARK)` 寫一行日誌,並在 `tmp_path / "control.sqlite"`(另開、`journal_mode=WAL`,不碰 `db_path`)建一張表寫入一列 `CONTROL_MARK`、不 checkpoint;再送 `POST /api/chat {model, messages:[{role:"user",content:CHAT_MARK}]}` 讀完;再送 `DELETE /api/session` 等到 SSE 收到 `ended`;等 0.2 秒 | 則1:`count_mark(caplog.text, CONTROL_MARK)` ≥ 1<br>則2:`count_mark` 在 `control.sqlite` 與 `control.sqlite-wal` 的位元組合計找到 `CONTROL_MARK` ≥ 1 次<br>則3:`count_mark(caplog.text, CHAT_MARK)` 為 0<br>則4:`count_mark` 在 `db_path` 與同名 `-wal`、`-journal` 檔的位元組合計找到 `CHAT_MARK` 為 0 次<br>則5:以 `sqlite3` 列出 `sqlite_master` 所有表並 `SELECT *` 全表掃描,任何欄位含 `CHAT_MARK` 的列是 0 列<br>則6:SSE 原文裡 `CHAT_MARK` 出現 0 次<br>則7:SSE 原文裡至少有一則 `state` 為 `ended` 的 `session.updated`(證明這段期間的推送確實收進來了) | 為了讓對話頁判斷清除,把「最後一則對話」或對話摘要寫進 `sessions` 的欄位、在結束時隨 `session.updated` 推出,或另推一則帶對話內容的「清除對話」事件;或 chat 路由以 `logger.debug("chat %s", body)` 記下本文;或檢查本身寫錯(搜錯檔、只搜主檔不搜 `-wal`、字串與位元組編碼不一致)而 0 次空過 —— 則1、則2 會先不過 | NFR-002、SC-004 | — | — |

### 3.2 跨端點驗收

接真的 Chromium 與真的後端(`tests/e2e/conftest.py` 的 `e2e_servers`:測試行程內 uvicorn,UI 127.0.0.1:8781;同一個 browser context 開多個分頁),Colab 執行環境、通道與遠端 Ollama 用替身(`FakeColabControl`、`FakeTunnel`、`ColabWorld.models`,對話轉送打 `fakes.server`),E2 端點節完成後才開始;除非案例另寫,工作階段以 `open_to_ready` 開到就緒,目錄是 `qwen2.5:latest`、`llama3.2:3b` 兩個已載入的模型,「兩問兩答」指在對話頁送出「你好」收到 `一二三` + `DONE`、再送出「再說一次」收到 `四五六` + `DONE`(`DONE` 帶 `eval_count`、`eval_duration`),「保存」指 `localStorage.getItem("cgb.chat.v1")`,「結束後 5 秒」從測試以 `GET /api/session` 輪詢到結束狀態(或 `name` 變了)的那一刻起算。

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US2-AJ-01 | 對話頁 › 「送出」 → 瀏覽器本身 › 重新整理 | 對話頁選的是打開頁面時預設選項以外的那一個模型(記為 M),已有兩問兩答 | 重新整理對話頁 | 則1:`#log .msg` 依序是 user「你好」、assistant「一二三」、user「再說一次」、assistant「四五六」,共 4 則<br>則2:`#model` 的值是 M<br>則3:第二則回覆下方仍顯示「tokens/s」的速度 | 對話只放在頁面變數裡、沒有寫進 `cgb.chat.v1`(004 的現況);或還原時把 `messages` 依角色分組重排(先列使用者再列回覆);或沒有保存 `model`,還原時 `#model` 回到選單預設的第一個;或只保存 `role`、`content`,還原的回覆丟了 `status`、`tps` 而不顯示速度 | FR-004、SC-002、驗收情境 1 |
| US2-AJ-02 | 對話頁 › 「送出」 → 瀏覽器本身 › 切到別頁 | 對話頁已有兩問兩答 | 點頁首「模型」到模型頁,等模型頁的目錄出現後,再點頁首「對話」回到對話頁 | 則1:`#log .msg` 依序是「你好」「一二三」「再說一次」「四五六」,共 4 則 | 保存只在 `beforeunload` 寫入,而頁首連結的導覽在寫入前就把 `convo` 清掉;或還原只認 `performance.navigation` 為 reload 的載入,一般導覽回來時不讀 `cgb.chat.v1` | FR-004、SC-002、驗收情境 2 |
| US2-AJ-03 | 對話頁 › 「送出」 → 瀏覽器本身 › 另開分頁 | 對話頁(分頁 A)已有兩問兩答 | 在同一個 context `new_page()` 開分頁 B 打開 `/chat.html` | 則1:分頁 B 的 `#log .msg` 依序是「你好」「一二三」「再說一次」「四五六」,共 4 則 | 對話存在 `sessionStorage`(research R3 實測新分頁讀不到);或保存的鍵帶分頁專屬的亂數,新分頁找不到 | FR-004、SC-002、驗收情境 3 |
| US2-AJ-04 | 瀏覽器本身 › 重新整理 → 對話頁 › 「送出」 | 對話頁已有兩問兩答;以 `parametrize` 依序跑三種離開方式:重新整理、切到模型頁再回來、另開分頁(在新分頁送出);替身第三次回 `七八九` + `DONE` | 照該種方式回到對話頁後,以 `page.expect_request` 攔下送出「第三則」時瀏覽器送的 `POST /api/chat` | 則1:三種方式下,本文的 `messages` 都正好是 `[user「你好」, assistant「一二三」, user「再說一次」, assistant「四五六」, user「第三則」]`,依這個順序<br>則2:三種方式下,畫面最後一則回覆都是「七八九」 | 還原時把保存的訊息畫上畫面,但送出用的 `convo` 陣列仍是空的,只送出 `[user「第三則」]`;或送出時只帶 `status` 為 `done` 的使用者訊息、漏掉 assistant | FR-005、SC-002、驗收情境 4 |
| US2-AJ-05 | 對話頁 › 「送出」 → 瀏覽器本身 › 重新整理 | 替身對 `POST /api/chat` 回 `NdjsonReply([chunk("一"), chunk("二")], then="hang")` | 送出「你好」,等畫面最後一則回覆顯示「一二」後重新整理 | 則1:最後一則回覆的內容是「一二」<br>則2:這則回覆下方顯示「中斷:離開頁面時這則回覆還沒有完成」<br>則3:這則回覆下方不含「tokens/s」<br>則4:保存的 `messages` 最後一則 `status` 是 `left` | 只在回覆完成時才寫入,回覆途中重新整理後這一則整個不見(research R5 待驗證:已顯示的內容要都在);或還原時把 `streaming` 的那一則當成 `done` 畫上耗時與速度;或還原時把它改成 004 的 `interrupted`(「中斷:回應到一半就斷了」);或只在畫面上改標示、沒有寫回,保存裡仍是 `streaming` | FR-008、驗收情境 5 |
| US2-AJ-06 | 對話頁 › 「送出」 → 瀏覽器本身 › 切到別頁 | 替身對 `POST /api/chat` 回 `NdjsonReply([], then="hang")`(一段都還沒送) | 送出「你好」,等「正在回覆」的提示出現後,點頁首「模型」到模型頁,再點「對話」回來 | 則1:最後一則回覆下方顯示「中斷:離開頁面時這則回覆還沒有完成」<br>則2:對話頁不含「沒有回覆:Ollama 暫時無法使用」<br>則3:`#log .msg` 共 2 則(使用者「你好」與這則空的回覆) | 照原型 `restore()` 把沒收到內容的那一則改成 `unavailable`,畫面寫成「沒有回覆:Ollama 暫時無法使用」(plan.md Q4 已決定不這樣做);或沒有內容的回覆在保存時被濾掉,回來只剩使用者那一則 | FR-008、驗收情境 5 |
| US2-AJ-07 | 瀏覽器本身 › 重新整理 → 對話頁 › 「送出」 | 照 US2-AJ-05 重新整理後,最後一則是「一二」且標示中斷;替身下一次回 `四五六` + `DONE` | 送出「繼續」,以 `page.expect_request` 攔下 `POST /api/chat` | 則1:本文的 `messages` 正好是 `[user「你好」, assistant「一二」, user「繼續」]`<br>則2:原本那則回覆下方仍顯示「中斷:離開頁面時這則回覆還沒有完成」 | 送出時把 `left` 的那一則當成失敗濾掉,模型收不到已回的部分;或送出新訊息時把前面每一則的 `status` 重設,中斷標示不見 | FR-005、FR-008、驗收情境 4、驗收情境 5 |
| US2-AJ-08 | 對話頁 › 「停止」 → 瀏覽器本身 › 重新整理 | 替身回 `NdjsonReply([chunk("一"), chunk("二")], then="hang")`;送出「你好」、畫面顯示「一二」後按「停止」,出現「已停止這則回覆」 | 重新整理對話頁 | 則1:最後一則回覆下方顯示「已停止」<br>則2:這則回覆下方不含「中斷」二字 | 還原時把所有不是 `done` 的回覆一律改成 `left`,按過停止的也標成中斷;或「停止」之後沒有寫入,保存裡仍是 `streaming`,還原時被當成離開頁面 | FR-004、FR-008 |
| US2-AJ-09 | 工作階段頁 › 「結束」 → 對話頁 › 保存狀態提示 | 分頁 A 的對話頁已有兩問兩答;測試在分頁 A 設 `window.__cgbMark = 1`;同一個 context 開分頁 B 在工作階段頁 | 分頁 B 按「結束」並在確認畫面按「結束工作階段」 | 則1:結束後 5 秒內,分頁 A 顯示「工作階段已結束,對話已清除」<br>則2:結束後 5 秒內,分頁 A 的 `#log .msg` 是 0 則<br>則3:分頁 A 的保存是 null<br>則4:分頁 A 的 `window.__cgbMark` 仍是 1(沒有重新載入) | 只在載入時比對工作階段,開著的對話頁沒有處理 `session.updated`,要重新整理才清;或只清畫面上的 `convo`、沒有 `removeItem`;或收到結束就呼叫 `location.reload()` 靠載入時的檢查清空 | FR-006、SC-003、驗收情境 6 |
| US2-AJ-10 | 對話頁 › 保存狀態提示 | 照 `test_us4_idle.py`:`PUT /api/settings` 把閒置時限設成 1 分鐘,`sync_browser_clock` 讓對話頁的時鐘跟著 `fake_clock`;對話頁已有兩問兩答 | `advance_clocks(page, fake_clock, 61)`,讓後端閒置自動結束(`endReason` 為 `IDLE_TIMEOUT`) | 則1:結束後 5 秒內,對話頁顯示「工作階段已結束,對話已清除」<br>則2:結束後 5 秒內,`#log .msg` 是 0 則<br>則3:保存是 null | 依 `endReason` 判斷,只認 `USER_ENDED` 才清,閒置結束的對話留著 | FR-006、SC-003、驗收情境 6 |
| US2-AJ-11 | 對話頁 › 保存狀態提示 | 對話頁已有兩問兩答 | 照 `test_reopen_after_end.py`:`world.alive.clear()`,`fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", …))`,讓工作階段被 Colab 收回(推送 `state` 為 `lost`) | 則1:結束後 5 秒內,對話頁顯示「工作階段已結束,對話已清除」<br>則2:結束後 5 秒內,`#log .msg` 是 0 則<br>則3:保存是 null | 結束狀態只列了 `ended`,`lost`、`open_failed` 沒有算進去 | FR-006、SC-003、驗收情境 6 |
| US2-AJ-12 | 對話頁 › 保存狀態提示 | 對話頁已有兩問兩答;`fakes.tunnel.open_tunnel.raises("TUNNEL_FAILED", "ssh exited")` | `fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", …))`,讓工作階段經過 `reconnecting` 後重連逾時(推送 `state` 為 `lost`) | 則1:結束後 5 秒內,對話頁顯示「工作階段已結束,對話已清除」<br>則2:結束後 5 秒內,`#log .msg` 是 0 則<br>則3:保存是 null | 收到 `reconnecting` 時設一個「重連中先不判斷」的旗標,之後收到 `lost` 沒有解除,對話一直留著;或只在 `reconnecting` → `ready` 之間比對 | FR-006、SC-003、驗收情境 6 |
| US2-AJ-13 | 工作階段頁 › 「變更類型」 → 對話頁 › 保存狀態提示 | 分頁 A 的對話頁已有兩問兩答,記下工作階段名稱 N;分頁 B 在工作階段頁 | 分頁 B 按「變更類型」,選 L4,按「確認,結束並重開」 | 則1:`GET /api/session` 的 `name` 第一次不是 N 起 5 秒內,分頁 A 顯示「工作階段已結束,對話已清除」<br>則2:同一時限內,分頁 A 的 `#log .msg` 是 0 則<br>則3:新的工作階段就緒後,分頁 A 的保存是 null 或其 `session` 不是 N | 只看 `state` 不比 `name`:變更類型經過 `ending` → `opening` → `ready`,沒有停在結束狀態,舊對話就被當成新工作階段的接著用 | FR-006、SC-003、驗收情境 6 |
| US2-AJ-14 | 工作階段頁 › 「結束」 → 瀏覽器本身 › 重新整理 | 分頁 A 的對話頁已有一問一答,再送出「再說一次」,替身回 `NdjsonReply([chunk("四")], then="hang")`,畫面顯示「四」;分頁 B 在工作階段頁 | 分頁 B 按「結束」並確認;分頁 A 顯示「工作階段已結束,對話已清除」後等 1 秒,再重新整理分頁 A | 則1:結束後 5 秒內,分頁 A 的 `#log .msg` 是 0 則<br>則2:清空後 1 秒時,分頁 A 的保存是 null<br>則3:重新整理後,分頁 A 的 `#log .msg` 是 0 則 | 清空之後,還在讀的串流收尾(004 的 `endReply(…,"lost")`、`finishTurn`)又把中斷的那一則整份寫回 `cgb.chat.v1`,重新整理後舊對話復活;或照 004 先走 `turn-lost` 保留「四」不清 | FR-006、FR-008、SC-003、驗收情境 6 |
| US2-AJ-15 | 工作階段頁 › 「結束」 → 對話頁 › 保存狀態提示 | 對話頁有兩問兩答後關掉對話頁分頁;在工作階段頁按「結束」並確認,再按「開啟」開到新的就緒;以 `context.add_init_script` 在新分頁裝一個 `MutationObserver`,記下 `#log` 是否曾出現「再說一次」 | 新開分頁打開 `/chat.html`,等 `chat-ready` 出現後再等 1 秒 | 則1:`#log .msg` 是 0 則<br>則2:`MutationObserver` 記到「再說一次」出現 0 次<br>則3:保存是 null | 載入時先畫保存的對話、收到快照才清,上一個工作階段的對話閃一下(research R4 的「等第一則快照再畫」沒做);或載入時只比對 `state`(新的也是 `ready`)就還原 | FR-006、SC-003、驗收情境 7 |
| US2-AJ-16 | 工作階段頁 › 「變更類型」 → 對話頁 › 保存狀態提示 | 對話頁有兩問兩答後關掉對話頁分頁;在工作階段頁變更類型成 L4,等新的工作階段就緒 | 新開分頁打開 `/chat.html`,等 `chat-ready` 出現 | 則1:`#log .msg` 是 0 則<br>則2:保存是 null | 載入時只看 `state` 是不是 `ready`,不比 `name`,變更類型後換了工作階段仍還原舊對話 | FR-006、SC-003、驗收情境 7 |
| US2-AJ-17 | 工作階段頁 › 「結束」 → 對話頁 › 保存狀態提示 | 對話頁有兩問兩答後關掉對話頁分頁;在工作階段頁按「結束」並確認,不開新的 | 新開分頁打開 `/chat.html` | 則1:`chat-no-session` 的說明出現<br>則2:`#log .msg` 是 0 則<br>則3:保存是 null | 載入時只比對 `name`(結束後快照的 `name` 仍是原本那個),`state` 為 `ended` 時照樣還原 | FR-006、SC-003 |
| US2-AJ-18 | 對話頁 › 「清除」 → 瀏覽器本身 › 重新整理 | 對話頁已有兩問兩答 | 按「清除」,再重新整理 | 則1:按下後 `#log .msg` 是 0 則<br>則2:按下後保存是 null<br>則3:重新整理後 `#log .msg` 是 0 則<br>則4:`#clear` 的文字是「清除」 | 只清 `convo` 與畫面、沒有 `removeItem`,重新整理又還原;或寫入 `{messages: []}` 的空殼而不是移除(research R3);或按鈕文字沿用 004 的「清空」(plan.md Q7) | FR-007、NFR-003、驗收情境 8 |
| US2-AJ-19 | 對話頁 › 模型選單 → 瀏覽器本身 › 重新整理 | 對話頁選 `qwen2.5:latest`,已有兩問兩答 | `#model` 改選 `llama3.2:3b`,再重新整理 | 則1:改選後 `#log .msg` 是 0 則<br>則2:改選後保存是 null<br>則3:重新整理後 `#log .msg` 是 0 則<br>則4:重新整理後 `#model` 的值是 `llama3.2:3b` | 換模型只清畫面、保存裡還是舊對話;或換模型時寫入新模型的那一刻用的是舊的 `convo`,重新整理還原出舊對話 | FR-007、驗收情境 8 |
| US2-AJ-20 | 對話頁 › 「送出」 → 瀏覽器本身 › 重新整理 | 同一個 context 開分頁 A、B,都打開對話頁且都是空的 | 在分頁 A 完成一問一答(「你好」→「一二三」),再重新整理分頁 B | 則1:分頁 B 的 `#log .msg` 依序是「你好」「一二三」 | 分頁 B 在 `pagehide`、`beforeunload` 時把自己記憶體裡的空對話整份寫入(空的就 `removeItem`),重新整理前把 A 剛保存的對話刪掉 | 邊界情況(兩個分頁同時開)、FR-004 |
| US2-AJ-21 | 對話頁 › 「送出」 → 瀏覽器本身 › 另開分頁 | 分頁 A 完成一問一答(「你好」→「一二三」)後,開分頁 B 打開對話頁(還原同一輪);替身前兩次 `POST /api/chat` 各在第一段後停在一個 `Gate`,依序收 A、B 的請求 | 分頁 A 送出「甲」、分頁 B 送出「乙」;先放行 A 的到 `DONE`、等 A 完成,再放行 B 的到 `DONE`、等 B 完成;最後開分頁 C 打開對話頁 | 則1:分頁 C 的 `#log .msg` 依序是 user「你好」、assistant「一二三」、user「乙」、assistant(B 收到的回覆),共 4 則 | 寫入前先讀回保存再接上自己的新訊息,兩個分頁的對話被合併(C 出現 6 則、含「甲」);或第一次寫入後就不讓別的分頁覆寫,先保存的 A 為準 | 邊界情況(兩個分頁同時開、最後保存的為準) |
| US2-AJ-22 | 對話頁 › 保存狀態提示 → 對話頁 › 「送出」 | `context.add_init_script` 讓 `Storage.prototype.setItem` 一律丟 `DOMException("…", "QuotaExceededError")`;以 `page.on("pageerror")` 記下未處理的例外 | 打開對話頁,送出「你好」 | 則1:對話頁顯示「這個瀏覽器無法保存對話,離開或重新整理後會消失」<br>則2:回覆「一二三」出現,且下方顯示速度<br>則3:`pageerror` 記到 0 次 | 每段寫入的 `setItem` 例外沒接住,`send()` 在第一段就丟出,回覆停在「正在回覆」;或接住了但不顯示提示,使用者不知道離開會消失 | 邊界情況(瀏覽器不允許保存)、FR-004 |
| US2-AJ-23 | 對話頁 › 保存狀態提示 → 對話頁 › 「送出」 | `context.add_init_script` 把 `window.localStorage` 的 getter 改成丟 `DOMException("…", "SecurityError")`;以 `page.on("pageerror")` 記下未處理的例外 | 打開對話頁,送出「你好」 | 則1:對話頁顯示「這個瀏覽器無法保存對話,離開或重新整理後會消失」<br>則2:回覆「一二三」出現<br>則3:`pageerror` 記到 0 次 | `chat.js` 在模組頂層直接讀 `window.localStorage`,例外讓整支腳本沒跑完,頁面停在「正在確認工作階段…」;或只用 `try` 包住 `setItem`、沒包讀取 | 邊界情況(瀏覽器不允許保存)、FR-004 |
| US2-AJ-24 | 對話頁 › 保存狀態提示 → 瀏覽器本身 › 重新整理 | 對話頁已有兩問兩答,記下工作階段名稱 N;以 `add_init_script` 的 `MutationObserver` 記下「工作階段已結束,對話已清除」是否曾出現 | 照 `test_us1_session.py` 的 `restart_backend` 重新起後端,等 `GET /api/session` 回 `ready` 且 `name` 是 N,再等 3 秒;之後重新整理 | 則1:重新整理前,`#log .msg` 共 4 則<br>則2:`MutationObserver` 記到「工作階段已結束,對話已清除」出現 0 次<br>則3:重新整理後,`#log .msg` 依序是「你好」「一二三」「再說一次」「四五六」 | `EventSource` 斷線(`error` 事件)被當成工作階段結束而清空;或後端重新啟動、接回之前先推一則 `state` 為 `none` 的快照,前端照規則清掉同一個工作階段的對話 | 邊界情況(後端重新啟動後重連接回)、FR-006 |
| US2-AJ-25 | 對話頁 › 保存狀態提示 | 對話頁已有兩問兩答,記下工作階段名稱 N;以 `add_init_script` 的 `MutationObserver` 記下「工作階段已結束,對話已清除」是否曾出現 | `fakes.tunnel.check_health.then(AdapterError("TUNNEL_UNREACHABLE", …))` 一次,重連第 1 輪就接回;等 `GET /api/session` 經過 `reconnecting` 回到 `ready` 且 `name` 是 N,再等 3 秒 | 則1:`#log .msg` 共 4 則<br>則2:`MutationObserver` 記到「工作階段已結束,對話已清除」出現 0 次<br>則3:保存的 `session` 是 N | 把 `reconnecting` 列進結束狀態,重連中就清掉(research R4 第 3 點) | 邊界情況(後端重新啟動後重連接回)、FR-006 |
| US2-AJ-26 | 對話頁 › 模型選單 → 瀏覽器本身 › 重新整理 | 對話頁選 `qwen2.5:latest`,已有兩問兩答;之後從 `ColabWorld.models` 拿掉 `qwen2.5:latest`(目錄只剩 `llama3.2:3b`) | 重新整理對話頁 | 則1:載入後 5 秒內,`chat-model-gone` 的說明出現,含 `qwen2.5:latest`<br>則2:`#log .msg` 共 4 則<br>則3:`#model` 有一個 `disabled` 的選項,文字含 `qwen2.5:latest` 與「已不在執行環境上」<br>則4:`#send` 停用 | 還原時發現模型不在目錄,`#model` 自動落到 `llama3.2:3b` 且照常可送,舊對話被送給別的模型;或發現模型不在就整段清空;或要等按下送出才提示(plan.md Q5 已決定一打開就顯示) | 邊界情況(保存的模型已不在目錄裡) |
| US2-AJ-27 | 對話頁 › 模型選單 → 瀏覽器本身 › 重新整理 | 照 US2-AJ-26 已顯示 `chat-model-gone` | `#model` 改選 `llama3.2:3b`,再重新整理 | 則1:改選後 `#log .msg` 是 0 則<br>則2:改選後 `#send` 可按<br>則3:重新整理後 `#log .msg` 是 0 則 | `chat-model-gone` 狀態下選單的 `change` 沒走清除,舊對話直接接到新模型;或清了畫面但 `chat-model-gone` 沒解除,仍不能送出 | 邊界情況(保存的模型已不在目錄裡)、FR-007 |
| US2-AJ-30 | 瀏覽器本身 › 重新整理 → 對話頁 › 「送出」 | 對話頁已有兩問兩答並保存;替身對下一個 `POST /api/chat` 先停 1 秒才送第一段 `chunk("七")`,再送 `DONE`(plan Q27) | 重新整理對話頁,等對話還原後送出「第三則」 | 則1:還原完成、還沒送出時,turn 區顯示 `turn-idle` 的「在這裡送出訊息,也會讓工作階段的閒置倒數重新計時。」<br>則2:送出後、第一段到之前,turn 區顯示 `turn-loading`,文字含選的模型名稱<br>則3:收到 `DONE` 後 2 秒內 turn 區回到 `turn-idle` | 還原時把 turn 區畫成保存當時最後一則的狀態(例如停在 `turn-streaming` 或 `turn-interrupted` 的提示),沒有回到 `turn-idle`;或還原後的第一次送出跳過 `turn-loading` 直接畫成串流 | FR-004、FR-005 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US2-AJ-28 | 隱私(對話內容不寫進資料庫與日誌) | 🔴🟢 行為測試 | 對話頁 › 「送出」 → 瀏覽器本身 › 重新整理 → 瀏覽器本身 › 切到別頁 → 瀏覽器本身 › 另開分頁 → 工作階段頁 › 「結束」 | `caplog.set_level(logging.DEBUG)`(根 logger,含 `uvicorn`、`httpx`、`httpcore`、`cgb`);兩個標記 `USER_MARK = "cgb-test-007-使用者-不該留下"`、`REPLY_MARK = "cgb-test-007-回覆-不該留下"`;替身每次回 `chunk(REPLY_MARK)` + `DONE`,其中一次回 `NdjsonReply([chunk(REPLY_MARK)], then="hang")` | 照故事 2 的獨立測試跑一遍:送出含 `USER_MARK` 的兩則、重新整理、切到模型頁再回來、另開分頁、送出第三則、回覆途中重新整理、在工作階段頁結束;結束後等 1 秒;最後跑兩個對照組:以 `logging.getLogger("cgb").warning(USER_MARK)` 寫一行,並把 `db_path` 複製到暫存資料夾、在副本建一張表寫入 `USER_MARK` | 則1:結束前,保存的值含 `USER_MARK`(內容真的走過瀏覽器保存)<br>則2:`fakes.server` 收到的 `POST /api/chat` 本文含 `USER_MARK`(內容真的經過後端)<br>則3:對照組之前,`caplog.text` 裡 `USER_MARK` 出現 0 次<br>則4:對照組之前,`caplog.text` 裡 `REPLY_MARK` 出現 0 次<br>則5:以 `sqlite3` 列出 `sqlite_master` 所有表並全表掃描,任何欄位含任一標記的是 0 列<br>則6:`db_path` 與同名 `-wal`、`-journal` 檔的位元組裡兩個標記的 UTF-8 出現 0 次<br>則7:日誌對照組寫入後,同一個搜尋在 `caplog.text` 找到 `USER_MARK` 1 次<br>則8:資料庫對照組寫入後,同一個掃描函式在副本找到 1 列 | 回覆途中離開或工作階段結束時,`/api/chat` 的例外路徑以 `logger.exception` 帶出請求本文或已轉送的段落;或結束工作階段時把對話當成「最後使用紀錄」寫進 `sessions` 等表;或搜尋寫錯(用 `str` 比 `bytes`、漏掃 `-wal` 檔、表名寫死)讓 0 次空過,由則7、則8 的對照組抓出 | NFR-002、SC-004 | — | — |
| US2-AJ-29 | 在地化(繁體中文) | 🔴🟢 行為測試 | 對話頁 › 保存狀態提示 | 以 004 `test_004_us2_chat.py` 的 `assert_traditional_chinese` 檢查 `main` 的文字(去掉模型名稱、`tokens/s` 與容許清單後沒有連續 4 個以上英文字母,且至少一個中文字);四種畫面各照前面的案例做出來 | 依序做出:US2-AJ-09 的清空後、US2-AJ-22 的不能保存、US2-AJ-05 的離開頁面中斷、US2-AJ-26 的模型已不在 | 則1:清空後的畫面通過檢查,且含「工作階段已結束,對話已清除」<br>則2:不能保存的畫面通過檢查,且含「這個瀏覽器無法保存對話,離開或重新整理後會消失」<br>則3:離開頁面中斷的畫面通過檢查,且含「中斷:離開頁面時這則回覆還沒有完成」<br>則4:模型已不在的畫面通過檢查,且含「已不在執行環境上」 | 新的提示直接用狀態代碼或英文當文字(例如顯示 `left`、`keep-no-store`、`Storage unavailable`);或把 `DOMException` 的 `message`(英文)原樣當說明 | NFR-003、FR-006、FR-008 | — | — |

### 3.3 交給 `/tdd` 的順序

每個案例在 `tasks.md` 是一組紅燈、綠燈任務;每一節的案例都做完後,接一個重構任務。同一個故事的端點節彼此平行,跨端點驗收在端點節都完成後才開始。

1. E2 後端 UI API:US2-API-01 → US2-API-02 → US2-API-03 → US2-API-04 → US2-API-05 → US2-API-06 → US2-API-07 → US2-API-08 → US2-API-09 → 重構
2. 跨端點驗收(3.1 完成後):US2-AJ-01 → US2-AJ-02 → US2-AJ-03 → US2-AJ-04 → US2-AJ-05 → US2-AJ-06 → US2-AJ-07 → US2-AJ-08 → US2-AJ-09 → US2-AJ-10 → US2-AJ-11 → US2-AJ-12 → US2-AJ-13 → US2-AJ-14 → US2-AJ-15 → US2-AJ-16 → US2-AJ-17 → US2-AJ-18 → US2-AJ-19 → US2-AJ-20 → US2-AJ-21 → US2-AJ-22 → US2-AJ-23 → US2-AJ-24 → US2-AJ-25 → US2-AJ-26 → US2-AJ-27 → US2-AJ-28 → US2-AJ-29 → US2-AJ-30 → 重構

## 4. 全域測試區

適用好幾個使用者故事的 NFR 與 SC 放在這裡。故事裡已經有案例涵蓋的,只在 4.1 彙整;沒辦法歸到單一故事的,在 4.2 寫成全域案例。

### 4.1 全域 NFR 的涵蓋彙整

| 全域需求 | 適用的故事 | 故事裡涵蓋它的案例 | 全域案例 |
|---|---|---|---|
| NFR-003 新增的畫面說明與提示文字為繁體中文 | 1、2 | US1-AJ-11、US2-AJ-18、US2-AJ-29 | — |
| SC-001 三種失敗 × 兩個操作 100% 回 502/502/504、0 次 500、0 次空目錄 | 1 | US1-API-16、US1-AJ-01~US1-AJ-03、US1-AJ-06 | G-01 |
| SC-002 三種離開方式還原一致、下一則請求含先前每一輪 | 2 | US2-AJ-01~US2-AJ-04 | — |
| SC-003 五種結束方式後 5 秒內清空、新工作階段 0 則舊訊息 | 2 | US2-AJ-09~US2-AJ-17 | — |
| SC-004 資料庫檔案與日誌出現測試對話內容 0 次 | 2 | US2-API-09、US2-AJ-28 | — |

### 4.2 全域案例

G-01 在 2.1 的案例都綠燈之後就可以跑(時機:節內)。

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| G-01 | 正確性(替身與真的轉接層一致) | 📏 量測 | `GET /api/models` → `POST /api/models/preload` | 本系統以替身開工作階段到就緒,但遠端 Ollama 改用真的 `RemoteOllama`(不是 `FakeRemoteOllama`),通道的 `baseUrl` 依序指到:(1)`free_loopback_port()` 取的、沒有人在聽的 127.0.0.1 port;(2)測試行程內對任何路徑回 200 與 `<html>不是 JSON</html>` 的臨時 http 伺服器;(3)只 `accept` 連線、不回任何位元組的 socket | 每種情況各呼叫一次 `GET /api/models` 與 `POST /api/models/preload`(`{"name":"qwen2.5:3b"}`);(3)照 `LIST_TIMEOUT` 等 10 秒 | 則1:(1)`GET /api/models` 回 502,`code` 為 `OLLAMA_UNREACHABLE`<br>則2:(1)`POST /api/models/preload` 回 502,`code` 為 `OLLAMA_UNREACHABLE`<br>則3:(2)`GET /api/models` 回 502,`code` 為 `OLLAMA_BAD_RESPONSE`<br>則4:(2)`POST /api/models/preload` 回 502,`code` 為 `OLLAMA_BAD_RESPONSE`<br>則5:(3)`GET /api/models` 在送出後 10 到 12 秒之間回 504,`code` 為 `OLLAMA_TIMEOUT`<br>則6:(3)`POST /api/models/preload` 回 504,`code` 為 `OLLAMA_TIMEOUT`<br>則7:六次回應裡狀態碼 500 的次數為 0(門檻取自 SC-001) | `FakeRemoteOllama.raises()` 直接丟 `AdapterError`,真的轉接層在某種網路失敗時丟的是沒被歸類的例外(例如 `httpx.RemoteProtocolError`),`Catalog.list()` 只接 `AdapterError`,真環境照樣回 500 | FR-001、FR-002、NFR-001、SC-001 | 時機:節內;不開 Colab、不花錢、不需本人在場;不起 `ollama serve`,不對 127.0.0.1:11434 送任何請求(`RemoteOllama` 以 `tests/realrun/helpers.py` 的 `RecordingTransport(get_only=True)` 經 `check_port` 擋下),port 由 `free_loopback_port()` 取、避開 11434~11436 與 8780;臨時伺服器與 socket 只聽 127.0.0.1,fixture 收尾關閉並確認 port 已釋放;只寫 pytest 暫存資料夾;標 `realrun_local`,預設排除;約 25 秒 | 判定者:腳本;樣本:一次實跑(未用於調整) |

## 5. 需求覆蓋

範疇內的使用者故事與適用它們的全域需求,每一條需求與邊界情況都要出現在這張表;沒有案例的就標「不在範疇」,寫進第 6 節。範疇外的使用者故事不列。

| 需求 | 歸屬 | E2 後端 UI API | 跨端點驗收 | 全域 | 驗證方式 |
|---|---|---|---|---|---|
| FR-001 列目錄讀不到時回 502/504 與代碼 | 故事 1 | US1-API-01~US1-API-04、US1-API-07、US1-API-14、US1-API-15 | — | G-01 | 🔴🟢、📏 量測 |
| FR-002 預先載入確認目錄讀不到時回 502/504、不受理、不改狀態 | 故事 1 | US1-API-08~US1-API-13 | — | G-01 | 🔴🟢、📏 量測 |
| FR-003 模型頁顯示說明、不顯示空目錄、其他模型照原狀 | 故事 1 | — | US1-AJ-01~US1-AJ-07、US1-AJ-10、US1-AJ-11 | — | 🔴🟢 |
| NFR-001 讀不到時不回 500 | 故事 1 | US1-API-16 | — | G-01 | 🔴🟢、📏 量測 |
| FR-004 在瀏覽器保存並照原順序還原 | 故事 2 | — | US2-AJ-01~US2-AJ-03、US2-AJ-08、US2-AJ-20、US2-AJ-22、US2-AJ-23、US2-AJ-30、US1-AJ-09 | — | 🔴🟢 |
| FR-005 還原後送出帶上先前每一輪 | 故事 2 | — | US2-AJ-04、US2-AJ-07、US2-AJ-30 | — | 🔴🟢 |
| FR-006 工作階段結束後清除保存的對話 | 故事 2 | US2-API-01~US2-API-08 | US2-AJ-09~US2-AJ-17、US2-AJ-24、US2-AJ-25、US2-AJ-29 | — | 🔴🟢 |
| FR-007 換模型或按「清除」一起清 | 故事 2 | — | US2-AJ-18、US2-AJ-19、US2-AJ-27 | — | 🔴🟢 |
| FR-008 回覆途中離開保存並標示中斷 | 故事 2 | — | US2-AJ-05~US2-AJ-08、US2-AJ-14、US2-AJ-29 | — | 🔴🟢 |
| NFR-002 對話內容只存在瀏覽器 | 故事 2 | US2-API-09 | US2-AJ-28 | — | 🔴🟢 |
| NFR-003 繁體中文 | 全域 | — | US1-AJ-11、US2-AJ-18、US2-AJ-29 | — | 🔴🟢 |
| SC-001 讀不到時 0 次 500、0 次空目錄 | 全域 | US1-API-16 | US1-AJ-01~US1-AJ-03、US1-AJ-06 | G-01 | 🔴🟢、📏 量測 |
| SC-002 還原一致、下一則含先前每一輪 | 全域 | — | US2-AJ-01~US2-AJ-04 | — | 🔴🟢 |
| SC-003 結束後 5 秒內清空 | 全域 | — | US2-AJ-09~US2-AJ-17 | — | 🔴🟢 |
| SC-004 資料庫與日誌 0 次對話內容 | 全域 | US2-API-09 | US2-AJ-28 | — | 🔴🟢 |
| 邊界:只有一個查詢失敗,不回半套目錄 | 故事 1 | US1-API-03、US1-API-04、US1-API-10 | US1-AJ-02 | — | 🔴🟢 |
| 邊界:讀不到顯示記憶體照常 200 | 故事 1 | US1-API-05 | — | — | 🔴🟢 |
| 邊界:沒有就緒的工作階段維持 503 | 故事 1 | US1-API-06、US1-API-17 | US1-AJ-10 | — | 🔴🟢 |
| 邊界:兩個分頁同時開,最後保存的為準 | 故事 2 | — | US2-AJ-20、US2-AJ-21 | — | 🔴🟢 |
| 邊界:瀏覽器不允許保存 | 故事 2 | — | US2-AJ-22、US2-AJ-23 | — | 🔴🟢 |
| 邊界:後端重新啟動後重連接回,對話保留 | 故事 2 | US2-API-06、US2-API-07 | US2-AJ-24、US2-AJ-25 | — | 🔴🟢 |
| 邊界:保存的模型已不在目錄裡 | 故事 2 | — | US2-AJ-26、US2-AJ-27 | — | 🔴🟢 |
| research R2:對話頁讀不到目錄時的說明 | 故事 1 | — | US1-AJ-08~US1-AJ-10 | — | 🔴🟢 |

## 6. 不在本次範疇

| 需求 | 為什麼不測 | 之後怎麼驗 |
|---|---|---|
| `chat` 的 `INVALID_REQUEST_BODY`、`INVALID_MODEL_NAME`、`EMPTY_CHAT_MESSAGES`、`INVALID_CHAT_MESSAGE`、`OLLAMA_NOT_FOUND`、`OLLAMA_UNREACHABLE`、`OLLAMA_BAD_REQUEST`、`OLLAMA_SERVER_ERROR`、`OLLAMA_BAD_RESPONSE`、`NO_READY_SESSION`、`OLLAMA_TIMEOUT` | 007 沒有改 `POST /api/chat` 的路由,只在 US2-API-09 用它做隱私檢查(plan Q18);這些代碼由 004 testplan 的 US2-API 案例涵蓋 | 004 的測試照常在快速層執行 |
| `preloadModel` 的 `INVALID_REQUEST_BODY`、`INVALID_MODEL_NAME` | 001 留下的落差(程式缺 `name` 時回 500、格式不對時走到 404),不在 NFR-001 範圍;plan Q2 決定合約照原樣寫,落差列進完成報告 | 下一輪補名稱檢查時,照 001 testplan 的案例補 `preloadModel` 的 400 |
| 假設:背景推送(預先載入結束、下載完成後推 `models.updated`)讀不到遠端 | spec 假設與 D2 不在這一輪範圍 | 列進完成報告,下一輪處理 |
| 換瀏覽器或換電腦看不到對話、每個模型各保留一段、跨工作階段保存、匯出(假設) | spec 假設不在範圍內(D3、D4) | 不驗 |
| Firefox 的 `localStorage` 行為與容量 | research 待驗證:只量了 Chromium,本計劃只以 Chromium 驗 | 使用者用 Firefox 時列進完成報告 |
| 真的 Colab 上五種結束方式的推送 | plan Q12:spec 假設這一輪不跑 colab、不花 compute units;001~005 已實跑驗過工作階段推送 | 下一次有 Colab 實跑時順帶以對話頁觀察 |
