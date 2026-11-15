# 測試計劃:讓 opencode 與 pi 輕鬆接上 Colab 上的 Ollama

- **規格**:`specs/006-agent-client-connect/spec.md`
- **系統分析**:`plan.md` § 端點盤點(E1 前端 UI、E2 後端 UI API、E3 Ollama 相容端點、E11 部署與網路);`contracts/ollama-compat.openapi.yaml`、`contracts/ui.openapi.yaml`;`prototype/connect.html`、`prototype/states.html`;`deploy/compose.yaml`、`deploy/.env.example`
- **測試技術**:`techstack.md` § 一覽;research.md R1(SSE 格式與工具呼叫實測)、R2、R3(opencode 與 pi 的片段實測)、R8(本機實跑用 `qwen2.5:3b`)
- **日期**:2026-11-16
- **範疇**:使用者故事 1、2、3;每個測試案例在 `tasks.md` 對應一組 `/tdd` 紅燈與綠燈任務,量測與人工驗證的案例對應 📏 任務
- **預設資料**:除非案例另寫,工作階段就緒(T4,005 的替身回報顯示記憶體 15360 MiB、套用 context 4096、平行 2);模型目錄有 `qwen2.5-coder:7b` 與 `qwen2.5:3b`;`CGB_PUBLIC_OLLAMA_PORT` 為 11436

## 1. 待測端點

端點、介面規格檔與公開接縫照抄 `plan.md` § 端點盤點與它指到的規格檔,本計劃不另做系統規劃;測試等級、工具與環境取自 `techstack.md` § 一覽,以及 001 沿用下來的整合與 Playwright 做法。上游沒寫到的,已登記到 `plan.md` 的待決問題 Q18~Q20,不在這裡自行補上。

| 端點 | 介面規格檔 | 公開接縫 | 測試等級 | 工具 | 測試環境 | 替身 |
|---|---|---|---|---|---|---|
| E3 Ollama 相容端點(FastAPI 轉送) | `contracts/ollama-compat.openapi.yaml` | 相容端點的 HTTP:`/v1/chat/completions`、`/v1/models` 與其他 `/v1` 路徑的回應 | 整合(真的路由與 `forward()`,轉送真的經過 httpx 打到測試行程內的假 Ollama 伺服器) | pytest + pytest-asyncio,沿用 `tests/integration/test_ollama_compat.py` 的 `bridge`(`live_servers`、`ColabWorld`、`open_ready`) | 測試行程內的 uvicorn,127.0.0.1 隨機 port;假 Ollama 伺服器新增 `SseReply`(逐段送 `data:` 行,可在中途斷線,plan Q19) | `FakeOllamaServer`(遠端 Ollama 的 `/v1`)→ G-01、G-02、G-04<br>`FakeColabControl`、`FakeTunnel`(Colab 執行環境與通道)→ G-04 |
| E2 後端 UI API(FastAPI REST 與 SSE) | `contracts/ui.openapi.yaml` | HTTP `GET /api/connect` 的回應;`domain/connect.py` 的片段產生與建議值(純函式) | 整合(真的 api、services、domain;轉接層用替身)、單元(`connect`) | pytest + pytest-asyncio + `httpx.ASGITransport`,沿用 `tests/conftest.py` 的 `ui_client`、`fakes`、`make_app` 與 `test_api_session.py` 的 `ColabWorld`、`open_ready` | 暫存 SQLite;`CGB_PUBLIC_OLLAMA_PORT` 由 `make_app` 的設定注入 | `FakeColabControl`(回報的顯示記憶體與套用的設定)、`FakeRemoteOllama`(模型目錄)→ G-01、G-02、G-04 |
| E11 部署與網路(Docker Compose) | `deploy/compose.yaml`、`deploy/.env.example` | 專案根目錄 `compose.yaml` 的內容(以 YAML 讀出 `cgb` 服務的 `environment`) | 單元 | pytest + PyYAML(專案既有) | 只讀檔,不執行 `docker compose` | 無 |
| 跨端點驗收 | E1、E2 的規格檔(`prototype/connect.html`、`contracts/ui.openapi.yaml`) | 瀏覽器畫面上的文字、分頁、複製按鈕與剪貼簿內容 | E2E(真的瀏覽器、真的後端;轉接層用替身) | Playwright(Python)+ pytest-playwright,`tests/e2e/conftest.py` 的 `e2e_servers` | 測試行程內的 uvicorn:UI 127.0.0.1:8781、相容端點 127.0.0.1:11437;剪貼簿以 `context.grant_permissions(["clipboard-read", "clipboard-write"])` 讀回 | `FakeColabControl`、`FakeTunnel`、`FakeRemoteOllama` → G-01、G-02、G-04 |
| E1 前端 UI(瀏覽器,原生 HTML/CSS/JS) | `prototype/connect.html`、`prototype/states.html` | — | — | — | 畫面都要先從 `GET /api/connect` 拿到資料,照 001~005 的做法不另立端點節;畫面行為都放在跨端點驗收 | — |

### 受測操作

每個測試案例的「受測操作」欄照這張表某一列的寫法填;`tasks.md` 的 ⚙ 照「規格錨點」欄寫。

| 端點 | 受測操作 | 規格錨點 | 寫法 |
|---|---|---|---|
| E3 Ollama 相容端點 | OpenAI 相容對話 | `contracts/ollama-compat.openapi.yaml` § `paths./v1/chat/completions.post` | `POST /v1/chat/completions` |
| E3 Ollama 相容端點 | OpenAI 相容模型清單 | `contracts/ollama-compat.openapi.yaml` § `paths./v1/models.get` | `GET /v1/models` |
| E3 Ollama 相容端點 | 其他 `/v1` 路徑 | `contracts/ollama-compat.openapi.yaml` § `paths./v1/{path}` | `<方法> /v1/<路徑>` |
| E3 Ollama 相容端點 | 原生路徑(回歸) | 001 `contracts/ollama-compat.openapi.yaml` § `paths` | `<方法> /api/<路徑>` |
| E2 後端 UI API | 讀連線資訊 | `contracts/ui.openapi.yaml` § `paths./connect.get`、`components.schemas.ConnectInfo`、`info.x-snippet-rule`、`info.x-recommendation-rule`、`info.x-reason-rule` | `GET /api/connect` |
| E2 後端 UI API | 片段與建議值(純函式) | `contracts/ui.openapi.yaml` § `info.x-snippet-rule`、`info.x-recommendation-rule` | `connect.<函式>(...)` |
| E11 部署與網路 | compose 的環境變數 | `deploy/compose.yaml` § `services.cgb.environment` | 讀 `compose.yaml` |
| 跨端點驗收 | 連線設定頁 | `prototype/connect.html` | 畫面上的控制項與文字 |

### 接縫的取捨

`/tdd` 紅燈步驟直接引用這張表,不再另外和使用者確認接縫;遇到這張表沒有的接縫才停下來問。

| 接縫(公開介面) | 抓得到 | 抓不到 |
|---|---|---|
| 相容端點的 HTTP(經假 Ollama 伺服器) | 白名單、OpenAI 格式錯誤、SSE 逐段轉送、中途斷線補段、工具呼叫的段原樣傳回 | 真的 Ollama 的 `/v1` 行為與真的用戶端;由 G-01、G-02、G-04 補上 |
| HTTP `GET /api/connect`(ASGI transport) | 原因判斷、port 與模型清單、片段帶的 context、不計閒置 | 片段真的被 opencode 與 pi 接受;由 G-01、G-02 補上 |
| `domain/connect.py` 純函式 | 片段的每個欄位、`limit.output` 與 `maxTokens` 的上限、`reserveTokens`、建議值的邊界 | 畫面怎麼顯示;由跨端點驗收補上 |
| 讀 `compose.yaml` | 變數名稱與預設值 | 容器裡真的讀得到;由 G-04 部署後的實跑補上 |
| 瀏覽器畫面(Playwright) | 主機名稱替換、分頁、複製到剪貼簿、提醒與說明 | 使用者實際貼上後的行為;由 G-01、G-02 補上 |

### 測試指令

| 層 | 指令 | 包含 | 大約時間 |
|---|---|---|---|
| 快速層 | 照 `specs/005-ollama-machine-tuning/testplan.md` § 1 測試指令的快速層指令,另外加上 `--deselect "tests/integration/test_colab_cli.py::test_重啟_Ollama_的命令列真的_colab_解讀得了"`(005 US3) | `tests/unit` 與 `tests/integration`,排除 005 列的慢測試與會呼叫真的 `colab` 的測試;不含 `tests/e2e`、`-m realrun`、`-m realrun_local` | 約 310 秒(005 US3 實測) |
| 全部 | `uv run pytest -q -p no:cacheprovider`,再加 `uv run pytest -m realrun_local -q -p no:cacheprovider` | 加上 `tests/e2e` 與接臨時 `ollama serve` 的 `realrun_local`(G-01、G-02);`-m realrun`(G-04)只在使用者同意並在場時執行 | 約 12 分 |

## 2. 使用者故事 1 - 用 opencode 接上 Colab 上的模型(P1)

**本故事的需求**:FR-001~FR-003、邊界情況(沒有就緒的工作階段、沒開放的 `/v1` 路徑、串流途中斷線、模型不在目錄、片段不含機密)
**本故事涵蓋的全域 NFR**:FR-009、FR-010、FR-011、FR-012、NFR-001、NFR-002(彙整見第 5 節)

### 2.1 E3 Ollama 相容端點

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-OC-01 | `POST /v1/chat/completions` | 假 Ollama 的 `/v1/chat/completions` 回 `JsonReply` 一則 `chat.completion` | 送 `{"model":"qwen2.5:3b","messages":[{"role":"user","content":"你好"}],"stream":false}`,帶 `Authorization: Bearer ollama` | 則1:回 200,本文和假 Ollama 回的完全相同<br>則2:假 Ollama 收到的路徑是 `/v1/chat/completions`、本文和送出的相同 | 白名單沒加 `/v1/chat/completions`,回 404;或轉成原生 `/api/chat` | FR-009 |
| US1-OC-02 | `POST /v1/chat/completions` | 假 Ollama 回 `SseReply`:三段 `data: {...chat.completion.chunk...}`,第二段的 delta 帶完整的 `tool_calls`,最後 `data: [DONE]` | 送同 US1-OC-01、`stream:true`、帶一個 tools 定義與 `stream_options.include_usage` | 則1:回應 `Content-Type` 是 `text/event-stream`<br>則2:收到的本文和假 Ollama 送的位元組完全相同,含 `tool_calls` 那段與 `[DONE]`<br>則3:假 Ollama 收到的本文含 `tools` 與 `stream_options` | 把 SSE 當成 NDJSON 逐行解析改寫;或轉送時去掉 `tools` | FR-009 |
| US1-OC-03 | `GET /v1/models` | 假 Ollama 的 `/v1/models` 回 `{"object":"list","data":[{"id":"qwen2.5:3b","object":"model"}]}` | 送 `GET /v1/models` | 則1:回 200,本文和假 Ollama 回的相同 | 只開了 `/v1/chat/completions`,`/v1/models` 仍回 404 | FR-009 |
| US1-OC-04 | `POST /v1/chat/completions` | 沒有開工作階段 | 送同 US1-OC-01 | 則1:1 秒內回 503<br>則2:本文是 `{"error":{"message":…,"type":"service_unavailable","code":"no_ready_session"}}`,`message` 含「沒有可用的工作階段」<br>則3:假 Ollama 沒有收到任何請求 | `/v1` 也回原生的 `{"error":"..."}` 字串;或排隊等工作階段 | FR-010 |
| US1-OC-05 | `<方法> /v1/<路徑>` | 工作階段就緒 | 依序送 `POST /v1/completions`、`POST /v1/embeddings`、`GET /v1/responses` | 則1:三個都回 404<br>則2:本文 `error.code` 是 `unsupported_path`、`error.type` 是 `invalid_request_error`,`message` 含 `/v1/chat/completions` 與 `/v1/models`<br>則3:假 Ollama 沒有收到任何請求 | 白名單用 `/v1/` 前綴整段放行;或 404 本文用原生格式 | FR-011、邊界情況(沒開放的 `/v1` 路徑) |
| US1-OC-06 | `POST /v1/chat/completions` | 工作階段就緒,假 Ollama 已停止(通道的 `baseUrl` 連不上) | 送同 US1-OC-01 | 則1:回 502<br>則2:本文 `error.code` 是 `ollama_unreachable`,`message` 不含轉發位址 | 連不上時回原生格式,或 `message` 帶出 `baseUrl` | FR-010 |
| US1-OC-07 | `POST /v1/chat/completions` | 假 Ollama 回 `SseReply`,送完第一段後斷線 | 送 `stream:true` 的請求 | 則1:收到第一段之後,多一段 `data: {"error":{"message":…,"type":"api_error","code":"stream_interrupted"}}`,再一段 `data: [DONE]`<br>則2:連線正常結束,用戶端讀得完本文(不是被重設) | SSE 中途斷線沿用 `StreamAborted` 直接斷線,用戶端看不到原因 | NFR-001、邊界情況(串流途中斷線) |
| US1-OC-08 | `POST /v1/chat/completions` | 假 Ollama 回 `SseReply`,送完第一段後停住;此時使用者結束工作階段 | 送 `stream:true` 的請求,收到第一段後 `DELETE /api/session` | 則1:收到第一段之後,多一段 `error.code` 為 `no_ready_session` 的 `data:` 段與 `data: [DONE]` | 工作階段結束時 SSE 沒補段,用戶端一直等 | NFR-001、邊界情況(串流途中斷線) |
| US1-OC-09 | `POST /v1/chat/completions` | 假 Ollama 的 `/v1/chat/completions` 回 404 `{"error":{"message":"model \"nope\" not found","type":"api_error"}}` | 送 `model:"nope"` 的請求 | 則1:回 404,本文和假 Ollama 回的完全相同 | 遠端的錯誤被本系統改寫成自己的格式 | 邊界情況(模型不在目錄) |
| US1-OC-10 | `<方法> /api/<路徑>` | 沒有開工作階段 | 依序送 `POST /api/generate`、`POST /api/pull`、`GET /api/me` | 則1:三個的本文 `error` 仍是字串(原生格式),狀態碼分別是 503、403、404 | 改 `ollama_error()` 時把原生路徑也換成 OpenAI 格式 | FR-010、FR-011 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-OC-11 | 效能(串流不緩衝) | 🔴🟢 行為測試 | `POST /v1/chat/completions` | 假 Ollama 回 `SseReply`,每 0.1 秒送一段、共 10 段 | 送 `stream:true` 的請求,記下每一段到達用戶端的時間 | 則1:每一段到達的時間比假 Ollama 送出晚不超過 0.5 秒<br>則2:第一段在最後一段送出之前就到達 | 把整段回應收完才送出(例如用 `upstream.aread()`) | NFR-001、SC-003 | — | — |

### 2.2 E2 後端 UI API

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-API-01 | `connect.<函式>(...)` | 無 | 以 port 11436、模型 `["qwen2.5-coder:7b","qwen2.5:3b"]`、context 32768 產生 opencode 片段 | 則1:片段解析成 JSON 後,`provider.cgb.npm` 是 `@ai-sdk/openai-compatible`、`options.baseURL` 是 `http://{{host}}:11436/v1`<br>則2:`provider.cgb.models` 的鍵恰好是兩個模型名稱<br>則3:每個模型的 `limit.context` 是 32768、`limit.output` 是 4096 | baseURL 少了 `/v1`;或模型清單寫死 | FR-001、FR-002 |
| US1-API-02 | `connect.<函式>(...)` | 無 | 以 context 4096、8191 各產生 opencode 片段 | 則1:context 4096 時 `limit.output` 是 2048<br>則2:context 8191 時 `limit.output` 是 4095 | `limit.output` 固定 4096,context 4096 時一次回覆就用完 | FR-002 |
| US1-API-03 | `GET /api/connect` | 工作階段就緒(預設資料) | 送 `GET /api/connect` | 則1:回 200,`ollamaPort` 是 11436、`basePath` 是 `/v1`、`reason` 是 null<br>則2:`models` 是 `["qwen2.5-coder:7b","qwen2.5:3b"]`、`contextLength` 是 4096<br>則3:`snippets.opencode` 解析後的 `limit.context` 是 4096 | 片段的 context 取級距表而不是目前套用的值;port 寫死 11434 | FR-001、FR-002 |
| US1-API-04 | `GET /api/connect` | 設定沒有 `CGB_PUBLIC_OLLAMA_PORT`,容器內 `CGB_OLLAMA_PORT` 是 11434 | 送 `GET /api/connect` | 則1:`ollamaPort` 是 11434 | 沒設時回 null 或 0,片段的位址壞掉 | FR-001 |
| US1-API-05 | `GET /api/connect` | 沒有開工作階段 | 送 `GET /api/connect` | 則1:回 200,`reason` 是 `no_ready_session`<br>則2:`snippets` 的三段都是 null | 沒有工作階段時回 503,畫面沒辦法說明原因 | FR-012、邊界情況(沒有就緒的工作階段) |
| US1-API-06 | `GET /api/connect` | 工作階段就緒,模型目錄是空的 | 送 `GET /api/connect` | 則1:回 200,`reason` 是 `no_models`、`models` 是 `[]`<br>則2:`snippets` 的三段都是 null | 目錄空時仍產生沒有模型的片段 | FR-012 |
| US1-API-07 | `GET /api/connect` | 工作階段就緒,替身讓讀模型目錄連不上遠端 | 送 `GET /api/connect` | 則1:回 502,代碼和 001 讀模型目錄的相同(`OLLAMA_UNREACHABLE`) | 讀不到當成目錄是空的,回 `no_models` 誤報原因(plan Q7) | FR-012 |
| US1-API-08 | `GET /api/connect` | 工作階段就緒,閒置計時的最後請求時間是 T | 在 T+30 秒(注入的時鐘)送 `GET /api/connect` | 則1:`GET /api/session` 的 `idle.lastRequestAt` 仍是 T | 讀連線資訊重設閒置計時(plan Q12) | FR-001 |
| US1-API-09 | `GET /api/connect` | 工作階段就緒,通道的 `baseUrl` 是 `http://127.0.0.1:49123` | 送 `GET /api/connect` | 則1:整份回應本文不含 `49123`、不含 Colab 工作階段名稱以外的機密欄位(token、授權碼)<br>則2:三段片段裡的主機名稱都是 `{{host}}` | 片段裡寫進轉發位址 | 邊界情況(片段不含機密) |

### 2.3 E11 部署與網路

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-DEP-01 | 讀 `compose.yaml` | 專案根目錄的 `compose.yaml` | 以 YAML 讀出 `services.cgb.environment` | 則1:`CGB_PUBLIC_OLLAMA_PORT` 的值是 `${CGB_HOST_OLLAMA_PORT:-11434}`<br>則2:`ports` 對外的相容端點仍是 `${CGB_HOST_OLLAMA_PORT:-11434}:11434` | 變數名稱打錯,或寫死 11436 | FR-001 |

### 2.4 跨端點驗收

接真的瀏覽器與真的後端,轉接層用替身;在 E3、E2、E11 的端點節都完成後才開始。

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-AJ-01 | 畫面上的控制項與文字 | 工作階段就緒(預設資料) | 從首頁導覽列點「連線設定」 | 則1:進到連線設定頁,opencode 分頁被選取<br>則2:片段的 `baseURL` 是 `http://127.0.0.1:11436/v1`(`{{host}}` 換成目前網址的主機名稱)<br>則3:片段列出 `qwen2.5-coder:7b` 與 `qwen2.5:3b`,下方寫著放進 `opencode.json` 與 `opencode -m cgb/<模型>` | 前端沒替換 `{{host}}`;導覽列沒有入口 | FR-001、NFR-002 |
| US1-AJ-02 | 畫面上的控制項與文字 | 同 US1-AJ-01 | 在 opencode 分頁按「複製」 | 則1:按鈕文字變成「已複製」<br>則2:讀回剪貼簿的內容和畫面上的片段文字完全相同 | 複製的是 `{{host}}` 還沒替換的原文;或只複製一部分 | FR-003 |
| US1-AJ-03 | 畫面上的控制項與文字 | 沒有開工作階段 | 打開連線設定頁 | 則1:看到「目前沒有就緒的工作階段」的說明與回首頁的連結<br>則2:畫面上沒有片段區塊 | 沒有工作階段時仍顯示空的片段 | FR-012 |
| US1-AJ-04 | 畫面上的控制項與文字 | 工作階段就緒,模型目錄是空的 | 打開連線設定頁 | 則1:看到「先到模型頁下載模型」的說明與模型頁的連結<br>則2:畫面上沒有片段區塊 | 目錄空時顯示沒有模型的片段 | FR-012 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-AJ-05 | 在地化(繁體中文) | 🔴🟢 行為測試 | 畫面上的控制項與文字 | 工作階段就緒(預設資料:context 4096) | 打開連線設定頁,依序看 opencode 分頁、pi 分頁與提醒 | 則1:分頁名稱、按鈕、使用方式、提醒與說明都是繁體中文,沒有簡體字<br>則2:片段本身的鍵名照原文(`provider`、`baseURL`、`contextWindow`、`reserveTokens`) | 說明文字留英文原型字串;或把片段的鍵名也翻成中文 | NFR-002 | — | — |

### 2.5 交給 `/tdd` 的順序

每個案例在 `tasks.md` 是一組紅燈、綠燈任務;每一節的案例都做完後,接一個重構任務。同一個故事的端點節彼此平行,跨端點驗收在端點節都完成後才開始。

1. E3 Ollama 相容端點:US1-OC-01 → US1-OC-02 → US1-OC-03 → US1-OC-04 → US1-OC-05 → US1-OC-06 → US1-OC-07 → US1-OC-08 → US1-OC-09 → US1-OC-10 → US1-OC-11 → 重構
2. E2 後端 UI API:US1-API-01 → US1-API-02 → US1-API-03 → US1-API-04 → US1-API-05 → US1-API-06 → US1-API-07 → US1-API-08 → US1-API-09 → 重構
3. E11 部署與網路:US1-DEP-01 → 重構
4. 跨端點驗收(E3、E2、E11 完成後):US1-AJ-01 → US1-AJ-02 → US1-AJ-03 → US1-AJ-04 → US1-AJ-05 → 重構

## 3. 使用者故事 2 - 用 pi 接上 Colab 上的模型(P2)

**本故事的需求**:FR-004、FR-005、FR-013
**本故事涵蓋的全域 NFR**:FR-009、NFR-002(彙整見第 5 節)

### 3.1 E2 後端 UI API

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US2-API-01 | `connect.<函式>(...)` | 無 | 以 port 11436、模型 `["qwen2.5-coder:7b"]`、context 32768 產生 pi 的 `models.json` 片段 | 則1:`providers.cgb.baseUrl` 是 `http://{{host}}:11436/v1`、`api` 是 `openai-completions`、`apiKey` 是 `ollama`<br>則2:`compat` 是 `{"supportsDeveloperRole":false,"supportsReasoningEffort":false}`<br>則3:模型項目是 `{"id":"qwen2.5-coder:7b","name":"qwen2.5-coder:7b","reasoning":false,"input":["text"],"contextWindow":32768,"maxTokens":4096}` | `api` 寫成 `openai-responses`;少了 `compat`,pi 送 developer role 給 Ollama | FR-004、FR-005 |
| US2-API-02 | `connect.<函式>(...)` | 無 | 以 context 4096、16384、32767 各產生 pi 的片段 | 則1:`maxTokens` 分別是 2048、4096、4096<br>則2:`settings.json` 片段的 `compaction.reserveTokens` 分別是 1024、4096、8191 | 預留沒有無條件捨去;或 `maxTokens` 固定 4096(plan Q15) | FR-005、FR-013 |
| US2-API-03 | `GET /api/connect` | 工作階段就緒(預設資料) | 送 `GET /api/connect` | 則1:`snippets.piModels` 解析後的 `contextWindow` 是 4096<br>則2:`snippets.piSettings` 解析後是 `{"compaction":{"reserveTokens":1024}}`,`reserveTokens` 欄位也是 1024 | 回應只給 opencode 的片段 | FR-004、FR-005、FR-013 |

### 3.2 跨端點驗收

接真的瀏覽器與真的後端,轉接層用替身;在 E2 的端點節完成後才開始。

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US2-AJ-01 | 畫面上的控制項與文字 | 工作階段就緒(預設資料) | 打開連線設定頁,切到 pi 分頁 | 則1:看到 `models.json` 與 `settings.json` 兩段,各有「複製」<br>則2:`models.json` 的 `baseUrl` 是 `http://127.0.0.1:11436/v1`<br>則3:下方寫著放進 `~/.pi/agent/models.json`、`~/.pi/agent/settings.json` 與 `pi --model cgb/<模型>` | pi 分頁只有 `models.json`;或主機名稱沒替換 | FR-004、FR-013、NFR-002 |
| US2-AJ-02 | 畫面上的控制項與文字 | 同 US2-AJ-01 | 按 `settings.json` 那段的「複製」 | 則1:讀回剪貼簿的內容和畫面上的 `settings.json` 片段完全相同 | 兩段共用一個複製按鈕,複製到另一段 | FR-013 |

### 3.3 交給 `/tdd` 的順序

1. E2 後端 UI API:US2-API-01 → US2-API-02 → US2-API-03 → 重構
2. 跨端點驗收(E2 完成後):US2-AJ-01 → US2-AJ-02 → 重構

## 4. 使用者故事 3 - context 太小時提醒並給建議值(P3)

**本故事的需求**:FR-006~FR-008
**本故事涵蓋的全域 NFR**:FR-012、NFR-002(彙整見第 5 節)

### 4.1 E2 後端 UI API

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US3-API-01 | `connect.<函式>(...)` | 無 | 依序以顯示記憶體 `12 * GIB`、`12 * GIB - 1`、`40 * GIB`、`None` 算建議值 | 則1:分別是 32768、16384、32768、16384<br>則2:每個都不超過 131072 | 邊界寫成 `>`,剛好 12 GiB 掉到 16384;讀不到時回 None | FR-007 |
| US3-API-02 | `connect.<函式>(...)` | 無 | 依序以 context 4096、16383、16384、None 判斷要不要提醒 | 則1:分別是 true、true、false、false | 用 `<=`,剛好 16384 也提醒;讀不到時提醒 | FR-006 |
| US3-API-03 | `GET /api/connect` | 工作階段就緒(預設資料:context 4096、顯示記憶體 15360 MiB) | 送 `GET /api/connect` | 則1:`shouldWarn` 是 true、`recommendedMinContextLength` 是 16384、`recommendedContextLength` 是 32768 | 提醒由前端自己算,後端沒給 | FR-006、FR-007 |
| US3-API-04 | `GET /api/connect` | 工作階段就緒,005 的 `ollama.status` 是 `unknown`(讀不到目前設定) | 送 `GET /api/connect` | 則1:`contextLength` 是 null、`shouldWarn` 是 false、`reason` 是 null<br>則2:opencode 片段沒有 `limit`、pi 片段沒有 `contextWindow` 且 `maxTokens` 是 4096<br>則3:`snippets.piSettings` 是 null | 讀不到時寫進 `limit.context: null` 或 4096 | FR-008 |

### 4.2 跨端點驗收

接真的瀏覽器與真的後端,轉接層用替身;在 E2 的端點節完成後才開始。

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US3-AJ-01 | 畫面上的控制項與文字 | 工作階段就緒(預設資料:context 4096) | 打開連線設定頁 | 則1:看到提醒,寫著目前 4096、建議 32768,以及「開啟前在 Ollama 設定填 context 長度」與「套用並重啟」兩種改法,附回首頁的連結<br>則2:片段仍然顯示,可以複製 | 提醒時把片段藏起來(plan Q17);或沒寫改法 | FR-006、FR-007、NFR-002 |
| US3-AJ-02 | 畫面上的控制項與文字 | 工作階段以覆蓋值 context 32768 開到就緒 | 打開連線設定頁 | 則1:沒有提醒區塊 | 一律顯示提醒 | FR-006 |
| US3-AJ-03 | 畫面上的控制項與文字 | 工作階段就緒,005 的 `ollama.status` 是 `unknown` | 打開連線設定頁 | 則1:看到「讀不到目前的 Ollama 設定,片段不帶 context 長度」的說明<br>則2:pi 分頁沒有 `settings.json` 那段 | 讀不到時顯示 context `null`,或仍顯示 `settings.json` | FR-008 |

### 4.3 交給 `/tdd` 的順序

1. E2 後端 UI API:US3-API-01 → US3-API-02 → US3-API-03 → US3-API-04 → 重構
2. 跨端點驗收(E2 完成後):US3-AJ-01 → US3-AJ-02 → US3-AJ-03 → 重構

## 5. 全域測試區

適用好幾個使用者故事的 NFR 與 SC 放在這裡。故事裡已經有案例涵蓋的,只在 5.1 彙整;沒辦法歸到單一故事的,在 5.2 寫成全域案例。

### 5.1 全域 NFR 的涵蓋彙整

| 全域需求 | 適用的故事 | 故事裡涵蓋它的案例 | 全域案例 |
|---|---|---|---|
| FR-009 開放 `/v1/chat/completions`、`/v1/models` | 1、2 | US1-OC-01、US1-OC-02、US1-OC-03 | G-01、G-02 |
| FR-010 沒有工作階段時 OpenAI 格式 503 | 1、2 | US1-OC-04、US1-OC-06、US1-OC-10 | — |
| FR-011 沒開放的 `/v1` 路徑 404 | 1、2 | US1-OC-05、US1-OC-10 | — |
| FR-012 沒有工作階段或模型時說明原因 | 1、2、3 | US1-API-05、US1-API-06、US1-API-07、US1-AJ-03、US1-AJ-04 | — |
| NFR-001 串流不緩衝 | 1、2 | US1-OC-07、US1-OC-08、US1-OC-11 | — |
| NFR-002 說明文字為繁體中文 | 1、2、3 | US1-AJ-01、US1-AJ-05、US2-AJ-01、US3-AJ-01 | — |
| SC-001 opencode 本機實跑 | 1 | — | G-01 |
| SC-002 pi 本機實跑 | 2 | — | G-02 |
| SC-003 串流延遲 | 1、2 | US1-OC-11 | G-03 |
| SC-004 真的 Colab T4 | 1 | — | G-04 |

### 5.2 全域案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| G-01 | 相容性(opencode) | 📏 量測 | `POST /v1/chat/completions` | 臨時 `ollama serve`(另取 port、暫存 `HOME` 與 `OLLAMA_MODELS`、`OLLAMA_CONTEXT_LENGTH=10240`)已下載 `qwen2.5:3b`;本系統以替身開工作階段到就緒,通道的 `baseUrl` 指向臨時 serve,替身回報 context 10240;暫存專案資料夾有 `secret.txt`(內容 `紫色長頸鹿 42`) | 從 `GET /api/connect` 取 opencode 片段,把 `{{host}}` 換成 `127.0.0.1`、port 換成本系統相容端點的測試 port,原樣寫進暫存 `HOME` 的 `opencode.json`;在暫存專案資料夾執行 `opencode run -m cgb/qwen2.5:3b "讀 secret.txt,只回答檔案內容"`,上限 300 秒 | 則1:opencode 結束碼 0,輸出含 `紫色長頸鹿 42`<br>則2:假 Ollama 之外的臨時 serve 收到至少一個帶 `tools` 的 `/v1/chat/completions`,且 opencode 的 JSON 事件裡有 `read` 工具呼叫<br>則3:記下總耗時 | 片段的欄位名稱或 `npm` 套件寫錯,opencode 載入失敗;或轉送改壞工具呼叫 | SC-001、FR-001~FR-003、FR-009 | 時機:節內;不開 Colab、不花錢;opencode 以 `env -i` 只留 `PATH`,`HOME` 與四個 `XDG_*` 指到暫存資料夾,不讀寫使用者的 `~/.config/opencode`;臨時 serve 與本系統都只聽 127.0.0.1、port 避開 11434~11436 與 8780;不對 11434 送請求;結束後停掉臨時 serve 的行程群組並確認已結束 | 判定者:腳本;樣本:固定的 `secret.txt`(沒有用來調整規則) |
| G-02 | 相容性(pi) | 📏 量測 | `POST /v1/chat/completions` | 同 G-01;另以 `npm install --prefix <暫存資料夾> @mariozechner/pi-coding-agent` 安裝 pi | 從 `GET /api/connect` 取 pi 的 `models.json` 與 `settings.json` 片段,同樣換掉主機與 port,寫進暫存 `HOME` 的 `~/.pi/agent/`;在暫存專案資料夾執行 `PI_OFFLINE=1 pi -p --no-session --mode json --model cgb/qwen2.5:3b "讀 secret.txt,只回答檔案內容"`,上限 300 秒 | 則1:pi 結束碼 0,輸出含 `紫色長頸鹿 42`<br>則2:pi 的 JSON 事件裡有 `read` 工具呼叫<br>則3:這一回合沒有因為 `threshold` 觸發自動壓縮(臨時 serve 沒有收到壓縮的請求)<br>則4:記下總耗時 | 少了 `settings.json` 或 `reserveTokens` 算錯,每回合都壓縮 | SC-002、FR-004、FR-005、FR-013、FR-009 | 時機:節內;同 G-01 的護欄;pi 裝在暫存資料夾,不全域安裝、不讀寫使用者的 `~/.pi` | 判定者:腳本;樣本:同 G-01 |
| G-03 | 效能(串流不緩衝) | 📏 量測 | `POST /v1/chat/completions` | 假 Ollama 回 `SseReply`,每 0.1 秒送一段、共 20 段 | 經本系統送 `stream:true` 的請求 5 次,記下每段的延遲 | 則1:5 次的每一段延遲都 ≤ 0.5 秒,記下最大值 | 把整段收完才送出 | SC-003、NFR-001 | 時機:節內;只用測試行程內的假伺服器 | 判定者:腳本;樣本:固定 20 段 |
| G-04 | 相容性(真的 Colab) | 📏 量測 | `POST /v1/chat/completions` | 使用者本人同意並在場;和 005 G-04 同一台 T4 的 `cgb-test-` 工作階段,已下載 `qwen2.5:7b`,以覆蓋值 context 16384 以上開啟 | 照 G-01 的做法,opencode 接真的本系統相容端點做同一個任務;同時記下 `/api/ps` 的 `size` 與 `size_vram` | 則1:opencode 輸出含 `紫色長頸鹿 42`,有 `read` 工具呼叫<br>則2:`size_vram` 等於 `size`<br>則3:記下總耗時與這次用掉的 compute units | 真的 Colab 上 context 或轉送和本機不同 | SC-004 | 時機:整合;開 Colab T4、花 compute units、需要本人在場;照 001 testplan 的實跑共同護欄 P1~P9(名稱前綴 `cgb-test-`、和 005 G-04 共用一台、結束後照 P3 確認沒有 `cgb-test-` 開頭的工作階段;不讀寫桌機的 `~/.config/colab-cli/`,一律用暫存的 `HOME`;token 與 endpoint 不印出);**執行前先停下問使用者本人** | 判定者:腳本;樣本:同 G-01 |

## 6. 需求覆蓋

範疇內的使用者故事與適用它們的全域需求,每一條需求與邊界情況都要出現在這張表;沒有案例的就標「不在範疇」,寫進第 7 節。範疇外的使用者故事不列。

| 需求 | 歸屬 | E3 Ollama 相容端點 | E2 後端 UI API | E11 部署與網路 | 跨端點驗收 | 全域 | 驗證方式 |
|---|---|---|---|---|---|---|---|
| FR-001 opencode 片段 | 故事 1 | — | US1-API-01、US1-API-03、US1-API-04、US1-API-08 | US1-DEP-01 | US1-AJ-01 | G-01 | 🔴🟢、📏 量測 |
| FR-002 opencode 片段帶 context | 故事 1 | — | US1-API-01~US1-API-03 | — | — | G-01 | 🔴🟢、📏 量測 |
| FR-003 一鍵複製、不碰使用者設定 | 故事 1 | — | — | — | US1-AJ-02 | G-01 | 🔴🟢、📏 量測 |
| FR-004 pi 片段 | 故事 2 | — | US2-API-01、US2-API-03 | — | US2-AJ-01 | G-02 | 🔴🟢、📏 量測 |
| FR-005 pi 片段帶 context | 故事 2 | — | US2-API-01~US2-API-03 | — | — | G-02 | 🔴🟢、📏 量測 |
| FR-013 pi 的 `settings.json` | 故事 2 | — | US2-API-02、US2-API-03 | — | US2-AJ-01、US2-AJ-02 | G-02 | 🔴🟢、📏 量測 |
| FR-006 context 太小時提醒 | 故事 3 | — | US3-API-02、US3-API-03 | — | US3-AJ-01、US3-AJ-02 | — | 🔴🟢 |
| FR-007 建議值 | 故事 3 | — | US3-API-01、US3-API-03 | — | US3-AJ-01 | — | 🔴🟢 |
| FR-008 讀不到設定 | 故事 3 | — | US3-API-04 | — | US3-AJ-03 | — | 🔴🟢 |
| FR-009 開放 `/v1` | 全域 | US1-OC-01~US1-OC-03 | — | — | — | G-01、G-02、G-04 | 🔴🟢、📏 量測 |
| FR-010 OpenAI 格式 503 | 全域 | US1-OC-04、US1-OC-06、US1-OC-10 | — | — | — | — | 🔴🟢 |
| FR-011 其他 `/v1` 404 | 全域 | US1-OC-05、US1-OC-10 | — | — | — | — | 🔴🟢 |
| FR-012 沒有工作階段或模型的說明 | 全域 | — | US1-API-05~US1-API-07 | — | US1-AJ-03、US1-AJ-04 | — | 🔴🟢 |
| NFR-001 串流不緩衝 | 全域 | US1-OC-07、US1-OC-08、US1-OC-11 | — | — | — | G-03 | 🔴🟢、📏 量測 |
| NFR-002 繁體中文 | 全域 | — | — | — | US1-AJ-01、US1-AJ-05、US2-AJ-01、US3-AJ-01 | — | 🔴🟢 |
| SC-001 opencode 本機實跑 | 全域 | — | — | — | — | G-01 | 📏 量測 |
| SC-002 pi 本機實跑 | 全域 | — | — | — | — | G-02 | 📏 量測 |
| SC-003 串流延遲 | 全域 | US1-OC-11 | — | — | — | G-03 | 🔴🟢、📏 量測 |
| SC-004 真的 Colab T4 | 全域 | — | — | — | — | G-04 | 📏 量測 |
| 邊界:沒有就緒的工作階段 | 故事 1 | US1-OC-04 | US1-API-05 | — | US1-AJ-03 | — | 🔴🟢 |
| 邊界:沒開放的 `/v1` 路徑 | 故事 1 | US1-OC-05 | — | — | — | — | 🔴🟢 |
| 邊界:串流途中斷線 | 故事 1 | US1-OC-07、US1-OC-08 | — | — | — | — | 🔴🟢 |
| 邊界:模型不在目錄 | 故事 1 | US1-OC-09 | — | — | — | — | 🔴🟢 |
| 邊界:片段不含機密 | 故事 1 | — | US1-API-09 | — | — | — | 🔴🟢 |

## 7. 不在本次範疇

| 需求 | 為什麼不測 | 之後怎麼驗 |
|---|---|---|
| FR-003 後半句「不讀取、不寫入使用者自己的 opencode 設定檔」 | 本系統沒有任何讀寫使用者設定檔的程式,不是可以用紅燈抓的行為;G-01 以暫存 `HOME` 執行間接確認 | 程式審查時確認 `src/cgb/` 沒有碰 `~/.config/opencode` |
| 支援工具呼叫與否取決於模型(假設) | 本系統只原樣轉送 | G-01、G-02 用 `qwen2.5:3b`,G-04 用 `qwen2.5:7b` |
| `getConnectInfo` 的 `OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT` | 讀模型目錄沿用 001 的同一段程式與錯誤歸類,001 的模型目錄案例已涵蓋這兩個代碼;本輪只以 US1-API-07 驗 `OLLAMA_UNREACHABLE` 確認有沿用 | 程式審查時確認 `GET /api/connect` 讀目錄走 001 的同一個函式 |
