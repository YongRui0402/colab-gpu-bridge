# Phase 0 Research: 讓 opencode 與 pi 輕鬆接上 Colab 上的 Ollama

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-11-16

使用者指定的技術方向:

- 整體:沿用專案現有堆疊(Python 3.12 + FastAPI、httpx 轉送、原生 HTML / CSS / JS 前端);相容端點在 `src/cgb/ollama_compat/`。
- 實測:只用本機另起的臨時 `ollama serve`(別的 port、暫存 `OLLAMA_MODELS` 與 `HOME`),不連 127.0.0.1:11434、不執行 `colab`;opencode 與 pi 一律在暫存 `HOME` 執行,不讀寫使用者自己的設定。

每個「理由」都標出證據類型:**實測**(附量測環境)、**估算**(附依據)、**查證**(附來源)、**判斷**(推論)。探針(紀錄代理 `proxy.py`、token 計數 `count.py`、每個請求的本文與回應)放在 session 暫存區 `probe006-fJSe/`,不進 repo;臨時 serve 與代理用完已確認行程結束。沒有依樣本調出來的門檻。實跑環境一律是:桌機 i5-9400F、GTX 1660 Ti 6 GB,Ollama 0.32.15,模型 `qwen2.5:3b`(1.9 GB),opencode 1.18.31,pi(`@mariozechner/pi-coding-agent`)0.73.1;以下稱「本機實測環境」。SC-004 要在真的 Colab T4 重測,實跑前先問使用者。

---

## R1. `/v1` 轉送 SSE 與工具呼叫(FR-009、NFR-001、SC-003)

**決策**:

- **白名單加兩條路徑**:`/v1/chat/completions`、`/v1/models` 加進 `routes.py` 的 `WHITELIST`,照現有的 `forward()` 原樣轉送,不改寫請求或回應本文。
  - `forward()` 已經用 `aiter_raw()` 逐段傳回、不緩衝,SSE(`text/event-stream`)和 NDJSON 走同一條路。
- **串流中途斷線**:SSE 回應中途非預期斷線時,補一段 `data: {"error":{...}}` 與 `data: [DONE]` 再結束,取代目前非 NDJSON 一律 `StreamAborted` 直接斷線的做法;用戶端看得到原因。工作階段被結束時同樣補這兩段。
- **`/v1/models`**:原樣轉送到遠端 Ollama(它回 OpenAI 格式的模型清單);opencode 與 pi 都不打它,保留給其他 OpenAI 用戶端。

**理由**:

- 實測(本機實測環境,curl 直接打臨時 serve):`/v1/chat/completions` 帶 `stream:true` 與一個 tools 定義,回 `Content-Type: text/event-stream`,每段 `data: {json}` 後空一行,最後 `data: [DONE]`;工具呼叫不是逐字增量,一個 delta 就給齊 `tool_calls[0].function.arguments`,下一段 `finish_reason:"tool_calls"`。帶 `stream_options.include_usage` 時 `[DONE]` 前多一段 usage;opencode 與 pi 都會帶。
- 實測(同環境,兩個用戶端都經紀錄代理):opencode 與 pi 各只打 `POST /v1/chat/completions`(各 3 次),都沒有打 `/v1/models`;代理逐段轉送時兩者都完成工具呼叫。
- 查證(`src/cgb/ollama_compat/forward.py`):`_relay()` 以 `upstream.aiter_raw()` 逐段 `yield`,不看內容;只有中途斷線時,非 NDJSON 的回應丟 `StreamAborted`。
- 判斷:轉送本身不用改,只要開白名單;補 SSE 的錯誤段是為了讓 coding agent 顯示原因,而不是無聲斷掉重試。

**考慮過的替代方案**:

- 自己實作 OpenAI 相容層(把 `/v1` 轉成 Ollama 原生 `/api/chat`):遠端 Ollama 已經內建 `/v1`,自己轉只是多一層會出錯的程式。
- 一併開放 `/v1/completions`、`/v1/embeddings`、`/v1/responses`:兩個用戶端都用不到,照 spec 假設這一輪不開。

## R2. opencode 片段的格式(FR-001、FR-002、FR-003、SC-001)

**決策**:片段是一段可以合併進 `opencode.json` 的 JSON,provider id 用 `cgb`:

- `provider.cgb.npm` 為 `@ai-sdk/openai-compatible`,`name` 為 `colab-gpu-bridge`,`options.baseURL` 為本系統相容端點的 `/v1`(R7)。
- `provider.cgb.models` 每個模型目錄裡的模型一個鍵(鍵就是 Ollama 的模型名稱,例如 `qwen2.5-coder:7b`),值有 `name` 與 `limit.context`(目前套用的 context 長度)、`limit.output`(固定 4096,不超過 context 的一半)。
- 讀不到 context 長度時不寫 `limit`(FR-008)。
- 不帶 API key(opencode 不送 Authorization 也能用)。
- 使用方式說明:貼進 `~/.config/opencode/opencode.json` 的 `provider` 底下,用 `opencode -m cgb/<模型名稱>` 選。

**理由**:

- 實測(本機實測環境,暫存 `HOME`,log 確認只載入暫存的設定):上面這個格式(context 10240、output 2048)原樣可用;`opencode run -m cgb/qwen2.5:3b "讀 secret.txt,只回答檔案內容"` 呼叫 `read` 工具並答對,共 28.3 秒(大半是第一次載入模型);沒有要求登入,模型名稱裡的 `:` 不影響 `-m`。
- 實測(同環境,紀錄代理):主請求帶 10 個工具、`tool_choice:"auto"`、`max_tokens` 等於 `limit.output`,本文 30,833 bytes;另有一個不帶工具的標題請求與主請求同時送出。
- 判斷:`limit.output` 會直接變成每次請求的 `max_tokens`,設太大會擠掉 context;固定 4096 並受 context 一半限制,夠一次寫一個檔。

**考慮過的替代方案**:由本系統直接寫入使用者的 `opencode.json`:會改到含其他 provider 與機密的檔,分身 D1 否決。

## R3. pi 片段的格式與安裝(FR-004、FR-005、FR-013、SC-002)

**決策**:

- **`models.json` 片段**:`providers.cgb` 有 `baseUrl`(R7 的 `/v1`)、`api: "openai-completions"`、`apiKey: "ollama"`(pi 要求有值,本系統不驗證)、`compat: {"supportsDeveloperRole": false, "supportsReasoningEffort": false}`,`models` 陣列每個模型 `{id, name, reasoning: false, input: ["text"], contextWindow, maxTokens}`,`maxTokens` 同 R2 的 `limit.output` 取 `min(4096, ⌊context ÷ 2⌋)`;讀不到 context 時不寫 `contextWindow`、`maxTokens` 為 4096。
- **`settings.json` 片段**(FR-013):`{"compaction": {"reserveTokens": <context 長度的四分之一,無條件捨去>}}`;讀不到 context 時不附。
- 使用方式說明:`models.json` 放 `~/.pi/agent/models.json`、`settings.json` 放 `~/.pi/agent/settings.json`(已有檔案時合併進去),用 `pi --model cgb/<模型名稱>` 選。
- 驗證時以 `npm install --prefix <暫存資料夾> @mariozechner/pi-coding-agent` 安裝,`PI_OFFLINE=1` 關掉版本檢查。

**理由**:

- 實測(本機實測環境,暫存 `HOME`):上面的 `models.json`(contextWindow 10240)原樣可用;`pi -p --no-session --mode json --model cgb/qwen2.5:3b "讀 secret.txt,只回答檔案內容"` 呼叫 `read` 並答對,共 8.5 秒。pi 會送 `Authorization: Bearer <apiKey>`、用 `max_completion_tokens`、assistant 的 `content` 可為 `null`,遠端 Ollama 都接受。
- 實測(同環境):第三個請求是自動壓縮,原因 `threshold`;pi 預設 `compaction.reserveTokens` 16384 大於 contextWindow 10240,一回合就觸發。
- 查證(pi 套件內 `docs/models.md`):自訂模型放 `~/.pi/agent/models.json`,也可用 `PI_CODING_AGENT_DIR` 改位置。
- 判斷:不調預留,context 在 32768 以下時每回合都在壓縮,看起來就是「接得上但不能用」;預留四分之一,在 16384 時留 4096,足夠一次回覆。

**考慮過的替代方案**:不附 `settings.json`、要使用者自己調壓縮:實測一回合就觸發壓縮,不調就不能用。

## R4. coding agent 的 context 建議下限(FR-006)

**決策**:建議下限維持 spec 假設的 **16384**;低於它就提醒。

**理由**:

- 實測(本機實測環境,把兩者第一個請求本文轉成 `/api/chat`、`num_ctx` 32768、`num_predict` 1,讀 `prompt_eval_count`):

| 請求 | 本文 | prompt token |
|---|---|---|
| opencode 標題請求 | 2,481 bytes | 537 |
| opencode 第一個帶工具的請求 | 30,833 bytes | 6,469 |
| pi 第一個請求 | 6,010 bytes | 1,487 |

- 實測(同環境,`num_ctx` 4096):opencode 主請求被截成 2050 token,serve log 出現 `msg="truncating input prompt" limit=2050 prompt=6469`,HTTP 仍回 200;用 `qwen3:4b` 跑 opencode 時就是這樣,完全沒有工具呼叫也沒有文字,97 秒後結束。
- 判斷:opencode 光第一個請求就要 6.5k,加上讀進來的檔與回覆,8192 撐不了幾回合;16384 是最小可用,建議值另由 R5 往上估。截斷沒有任何錯誤訊息,所以提醒是唯一讓使用者知道的地方。

**考慮過的替代方案**:建議下限 8192:opencode 第一個請求就 6469 token,加上檔案內容撐不了幾回合。

## R5. 建議值怎麼估(FR-007)

**決策**:建議值 = 顯示記憶體 ≥ 12 GiB 時 32768,否則 16384;再受 005 覆蓋範圍上限 131072 限制。讀不到顯示記憶體時建議 16384。畫面上同時說明「以 7B 級模型估算,改完後到工作階段頁確認模型全部在 GPU」。

**理由**:

- 估算(qwen2.5 7B:28 層、KV 維度 4 頭 × 128、K 與 V 各一份、`q8_0` 每個值 1 byte):每個 token 約 28 層 × 512 × 2 × 1 ≈ 28 KB。Ollama 的總 KV = context × 平行數;T4 自動平行 2、context 32768 → 65,536 × 28 KB ≈ 1.9 GB,加上 005 G-02 量到的模型 4.9 GB,約 6.8 GB,T4 的 15 GB 放得下;12 GiB 以下的機器(平行 1)32768 約 0.9 GB 加模型也放得下,但留給 14B 模型的空間不夠,所以保守建議 16384。
- 實測(005 `measurements.md` G-02,T4,`qwen2.5:7b`):context 4096、平行 2 時 `size` 4,922,340,801 bytes,等於 `size_vram`。
- 判斷:這個估算只對 7B 級模型準;更大的模型要使用者自己看 `size_vram`。精確估算要知道每個模型的層數與 KV 維度,這一輪不做。

**考慮過的替代方案**:依模型的架構參數(`/api/show` 的 `model_info`)逐一精算:要等模型下載完才知道,片段又列出多個模型,畫面會變得複雜;7B 級是主要用途。

## R6. OpenAI 格式的錯誤(FR-010、FR-011)

**決策**:`/v1/*` 由本系統自己產生的錯誤,本文用 OpenAI 的 `{"error": {"message": "<繁體中文說明>", "type": "<類型>", "code": "<代碼>"}}`;原生路徑維持 `{"error": "<說明>"}`。

- 沒有就緒的工作階段:503,`type` 為 `service_unavailable`,`code` 為 `no_ready_session`,說明沿用目前的 `NO_READY_SESSION_MESSAGE`。
- 沒開放的 `/v1` 路徑:404,`type` 為 `invalid_request_error`,`code` 為 `unsupported_path`,說明列出開放的兩條路徑。
- 連不到遠端 Ollama:502,`type` 為 `api_error`,`code` 為 `ollama_unreachable`。
- 遠端 Ollama 自己回的錯誤原樣傳回(它在 `/v1` 底下本來就回 OpenAI 格式)。

**理由**:

- 查證(OpenAI API 錯誤格式;`@ai-sdk/openai-compatible` 與 OpenAI JS SDK 都讀 `error.message`):兩個用戶端顯示的是 `error.message`;原生格式的字串 `error` 會被當成未知錯誤。
- 查證(`src/cgb/ollama_compat/forward.py` `ollama_error()`、`routes.py`):目前錯誤都走 `ollama_error()`,在這裡依路徑是否以 `/v1/` 開頭選格式即可。
- 判斷:`code` 用英文小寫,符合 OpenAI 慣例;說明用繁體中文(憲法〈語言〉)。

**考慮過的替代方案**:`/v1` 也沿用原生的 `{"error": "..."}`:兩個用戶端讀的是 `error.message`,會顯示成未知錯誤。

## R7. 片段裡的位址怎麼得知(FR-001、FR-004)

**決策**:後端從環境變數 `CGB_PUBLIC_OLLAMA_PORT` 得知相容端點在主機上的 port,`compose.yaml` 把 `${CGB_HOST_OLLAMA_PORT:-11434}` 傳進容器;前端用目前網址的主機名稱組出 `http://<主機名稱>:<port>/v1`。沒設時用容器內的 `CGB_OLLAMA_PORT`。

**理由**:

- 查證(`compose.yaml`、`.env.example`):相容端點對外的 port 由 `CGB_HOST_OLLAMA_PORT` 決定(桌機設 11436,因為 11434 是使用者自己的 Ollama),容器內固定聽 11434;後端目前不知道主機那一側的 port。
- 判斷:使用者是從瀏覽器打開 UI,UI 的主機名稱就是 coding agent 連得到的位址(在同一台時是 `127.0.0.1` 或 `localhost`,在區網時是那台的位址);port 只有部署設定知道,所以由 compose 傳進來。

**考慮過的替代方案**:在 UI 讓使用者自己填相容端點的位址:部署時就知道 port,多一個要填的欄位沒有好處。

## R8. 本機實跑用哪個模型(SC-001、SC-002)

**決策**:SC-001、SC-002 的本機實跑用 `qwen2.5:3b`,臨時 serve 設 `OLLAMA_CONTEXT_LENGTH=16384`;本系統開工作階段時以覆蓋值 context 16384 開(在替身工作階段裡轉發到臨時 serve)。

**理由**:

- 實測(本機實測環境):`qwen2.5:3b` 兩個用戶端都一次成功。`qwen3:4b` 在 4096 被截斷;改 16384 後只有 29/37 層放進 GPU、約 7 token/s,光標題請求就思考到 4096 token 上限,opencode 600 秒逾時。`reasoning_effort:"none"` 沒有真的關掉思考,只是把思考內容改放進 `content`。
- 估算(qwen2.5 3B:36 層、KV 維度 2 頭 × 128、臨時 serve 預設 f16 每個值 2 bytes):每個 token 約 36 KB,16384 × 平行 1 ≈ 0.6 GB,加上模型 1.9 GB,6 GB 放得下;依片段規則 `limit.output` 為 4096,可用輸入 12,288 token,大於 R4 量到的 6,469。
- 判斷:6 GB 顯示記憶體上,3B、不思考的模型最穩;Colab 上的 SC-004 改用 `qwen2.5:7b`(005 已在 T4 實跑過)。

**考慮過的替代方案**:`qwen3:4b`:思考內容太多,6 GB 上 opencode 600 秒逾時。

## 待驗證

| 來源 | 待驗證 | 驗證方式 / 時機 | 擋計畫? |
|---|---|---|---|
| R1 | 經本系統(不是探針代理)轉送時,SSE 每段延遲 | SC-003 的替身案例,implement 時 | 否 |
| R2 | 在真的 Colab T4、`qwen2.5:7b` 上 opencode 完成同一個任務 | SC-004,和 005 G-04 同一台,實跑前問使用者 | 否 |
| R5 | 32768 在 T4、`qwen2.5:7b`、平行 2 時 `size_vram` 等於 `size` | SC-004 那台順便看 `/api/ps` | 否 |

## 修訂紀錄

### 2026-11-16

- R8:本機實跑的 context 從 10240 改成 16384。原因:analyze A2,依片段規則 10240 時 `limit.output` 為 4096,可用輸入只剩 6,144,小於 opencode 第一個請求的 6,469(R4);10240 只在 output 2048 時實測過。連帶:testplan G-01、G-02 與 tasks T048、T049 同步改成 16384。
- R3:pi 的 `maxTokens` 從固定 4096 改成 `min(4096, ⌊context ÷ 2⌋)`。原因:S4 原型發現 context 4096 時 `maxTokens` 等於 context,一次回覆就能用完整個 context;和 R2 的 opencode 規則一致(plan Q15)。連帶:`contracts/ui.openapi.yaml` 的 `x-snippet-rule` 同步改。
