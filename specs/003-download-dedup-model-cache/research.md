# Phase 0 Research: 加入下載的重複判定與模型目錄快取

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-11-13

使用者指定的技術方向:

- 後端:沿用 001/002 的堆疊(Python 3.12、FastAPI 0.162.2、httpx 0.28.1,見 002 的 techstack.md),這一輪不引入新套件。
- 範圍:只有 Q21(沒寫版本的名稱重複加入下載)與 Q179(`GET /api/models` 每次跑 `colab exec`);Q22 不在範圍內。不改合約、不改 UI。
- 限制:不開 Colab、不跑 `colab` 指令、0 compute units;只用替身、本機服務與讀程式。

每個「理由」都標出證據類型:**實測**(附量測環境)、**估算**(附依據)、**查證**(附來源)、**判斷**(推論)。探針放在 session 暫存區(`<session 暫存區>`),不進 repo:`probes/test_probe_baseline.py` 量改之前的現況,`probes/proto.py` 是以 monkeypatch 換掉要改的方法的原型,`probes/test_probe_proto.py`、`probes/test_probe_race.py` 照 spec 的驗收情境跑原型。實測環境都是桌機(Ubuntu,Python 3.12,專案 `.venv`),經 `tests/conftest.py` 的 fixture 與 `tests/fakes/` 的替身跑 UI API,不連 Colab;對真環境的驗收沿用 spec 的決定,以替身進行(分身決策紀錄 D4)。

樣本用途(分配表在暫存區 `樣本分配表.md`,只憑名稱寫):調整用為本機 Ollama 0.32.15 的 `/api/tags` 一次回應;驗收用為本機 Ollama 以沒寫版本的名稱查 `/api/show` 的一組對照(R1 規則定案後才打開);`tests/fixtures/library/*` 與研究項無關,不用。

---

## R1. 補 `latest` 的規則與同一批合併(FR-001、FR-002、SC-001)

**決策**:

- **規則**:名稱含 `:` 就照原樣;不含 `:` 就在後面接 `:latest`。不轉大小寫、不去空白、不檢查名稱格式(名稱格式驗證是 Q178,不在範圍內);版本照原樣比對(spec 假設)。
- **共用**:新增 `src/cgb/domain/model_name.py` 的 `with_version(name: str) -> str`,照上面的規則;`services/downloads.py` 的 `with_version()` 與 `api/curated.py` 的 `normalized()` 都改成呼叫它,精選清單的行為不變。spec 的假設寫「要不要抽成共用由系統分析決定」,這裡是建議,system-analysis 可以改放處,規則本身不變。
- **同一批合併**:試算與加入下載先把整批名稱補過版本,再以 `list(dict.fromkeys(...))` 去掉重複、保留第一次出現的順序;之後的重複檢查、取 manifest、試算大小與寫入佇列都用這份清單。
- **比對對象**:執行環境上已下載的模型以 `/api/tags` 每筆的 `name` 原樣比對,不再補版本(tags 的名稱本來就帶版本)。

**理由**:

- 查證(`src/cgb/services/downloads.py:with_version`、`src/cgb/api/curated.py:normalized` 本體):兩個函式本體都是 `model if ":" in model else f"{model}:latest"`,是同一條規則。
- 實測(桌機 `uv run python -c`,兩個函式各餵 6 個名稱):`qwen2.5` → `qwen2.5:latest`、`qwen2.5:latest`、`qwen2.5:7b`、`qwen2.5:Latest`、`a:b:c` 照原樣、空字串 → `:latest`,兩個函式 6 筆結果全部相同,所以合成一個不改變任何呼叫端的行為。
- 實測(本機 Ollama 0.32.15,`GET /api/tags`,調整用):6 筆模型的 `name` 都帶版本(含 `moondream:latest`、`huihui_ai/qwen3.5-abliterated:9b`),沒有一筆省略 `:latest`,所以已下載那一側不用補。遠端 Colab 上的 Ollama 版本不同,這個假設在遠端**未查**(要開 Colab),列進待驗證。
- 實測(本機 Ollama 0.32.15,`POST /api/show`,驗收用,規則定案後才查):`moondream` 與 `moondream:latest` 都回 200 且是同一個模型(1B);`qwen2.5`(本機只有 `qwen2.5:3b`)回 404 `model 'qwen2.5:latest' not found`。Ollama 自己就把沒寫版本的名稱當成 `<名稱>:latest`,和這條規則一致;寫了版本的 `qwen2.5:3b` 不會被當成 `qwen2.5:latest`,和「不同版本不算重複」一致。
- 實測(`probes/test_probe_baseline.py`,改之前):執行環境上已有 `qwen2.5:latest` 時,試算 `qwen2.5` 回 200、加入下載 `qwen2.5` 回 201(重複加入);同一批 `["llama3.2","llama3.2:latest"]` 試算回 200 且 `items` 列兩筆 `llama3.2:latest`、總大小算兩次,加入下載回 500。
- 實測(`probes/test_probe_proto.py`,原型照上面的決策):同一批 `["qwen2.5","qwen2.5:latest"]` 試算 `items` 只有一筆 `qwen2.5:latest`、`totalBytes` 4,683,087,332(只算一次),加入下載回 201 且佇列只多一筆;`["qwen2.5:0.5b","qwen2.5:0.5b"]` 只加入一筆;執行環境上有 `qwen2.5:latest` 時加入 `qwen2.5:7b` 回 201(驗收情境 4)。

**考慮過的替代方案**:

- 同一批重複時整批回 409:spec 已決定合併成一筆(分身決策紀錄 D2)。
- 兩個函式維持各自一份:同一條規則兩份,日後只改一份就不一致;002 完成報告「下一步」也建議抽到 `domain/`。
- 比對前把 tags 的名稱也補版本:本機實測 tags 的名稱都帶版本,補了也不變,多一步沒有好處。

## R2. 試算與加入下載的檢查順序與失敗對應(FR-001、NFR-001、NFR-003、SC-001、使用者指定)

**決策**:`DownloadsService` 加一個試算與加入下載共用的檢查,兩個操作都先走它,過了才取 manifest。

- **檢查順序**:
  1. `require_ready_base_url()`:沒有就緒的工作階段回 503 `NO_READY_SESSION`(試算現在不檢查,會在讀剩餘空間時回 500)。
  2. 補版本並合併同一批(R1)。
  3. 讀執行環境上的模型清單(`list_local_models`)與佇列中排隊中、下載中的項目(`_pending()`,失敗與已完成的不算)。
  4. 依清單順序逐一比對:在模型清單裡 → 409 `MODEL_ALREADY_DOWNLOADED`;在佇列裡 → 409 `DOWNLOAD_ALREADY_QUEUED`;`model` 都是補過版本的名稱。第一個重複的就回,整批不加入。
  5. 都沒有重複才進 `_sized()` 取 manifest,再讀剩餘空間(現有流程不變)。
- **讀模型清單失敗**(分身決策紀錄 D9):
  - 轉接層 `RemoteOllama._get_list`(`list_local_models`、`list_loaded_models` 共用)照同檔 `get_version` 的歸類:`httpx.TimeoutException` → `OLLAMA_TIMEOUT`;其他 `httpx.TransportError` → `OLLAMA_UNREACHABLE`;非 200 或本文不是 JSON → `OLLAMA_BAD_RESPONSE`;以 `AdapterError` 丟出。
  - 服務把這三個代碼對應成 502 `OLLAMA_UNREACHABLE`、502 `OLLAMA_BAD_RESPONSE`、504 `OLLAMA_TIMEOUT`(001 `ui.openapi.yaml` § estimateDownloads、enqueueDownloads);`domain/errors.py` 的 `MESSAGES` 只補這三個代碼。
  - 其他呼叫 `_get_list` 的地方(模型目錄、變更執行階段類型、預先載入)不另外接,現在是 500 的照樣是 500(Q203,不在範圍內)。
- **寫入佇列**:整批的 `repo.enqueue` 包在一個 SQLite 交易裡(`BEGIN`、全部寫完 `COMMIT`、任何一筆失敗 `ROLLBACK`);撞到 `pending_model` 的唯一限制(`sqlite3.IntegrityError`)回 409 `DOWNLOAD_ALREADY_QUEUED`、`model` 為那一筆。交易裡沒有 `await`,同一個事件迴圈裡不會有別的寫入插進來。

**理由**:

- 查證(`src/cgb/services/downloads.py:enqueue`、`estimate` 本體):`enqueue` 用原樣的名稱比對 `local` 與 `pending`,`_sized()` 才補版本;`estimate` 完全沒有重複檢查,也沒有呼叫 `require_ready_base_url()`。
- 實測(`probes/test_probe_baseline.py`,改之前):佇列裡有下載中的 `qwen2.5:latest` 時,加入下載 `qwen2.5` 回 500;沒有工作階段時試算回 500;加入下載時 `list_local_models` 丟 `OLLAMA_UNREACHABLE`、`OLLAMA_TIMEOUT`、`OLLAMA_BAD_RESPONSE` 都回 500。
- 實測(`uv run python -c` 讀 `MESSAGES`):`OLLAMA_UNREACHABLE`、`OLLAMA_TIMEOUT`、`OLLAMA_BAD_RESPONSE` 三個都不在表裡,`ApiError(...).body()` 會丟 `KeyError` 變 500(002 research R4 同一類)。
- 實測(`probe_remote_list.py`,真的 `RemoteOllama` 接 `httpx.MockTransport`):`list_local_models` 遇到連線被拒丟 `httpx.ConnectError`、逾時丟 `httpx.ReadTimeout`、回 500 或回 HTML 丟 `json.JSONDecodeError`,沒有一個是 `AdapterError`。所以只在服務接 `AdapterError` 不夠,真環境裡讀不到模型清單照樣 500;轉接層要先歸類,spec 假設的 502、504 才成立。
- 實測(`probes/test_probe_proto.py`,原型):驗收情境 1~3 的試算與加入下載都回 409 與對應的 `code`,`model` 為 `qwen2.5:latest` 或 `llama3.2:latest`,佇列不變;這 4 次重複的請求 `get_manifest` 被呼叫 0 次(NFR-001);情境 6(三個裡第二個已在佇列)回 409、佇列沒有多出任何一筆;情境 7(同名那筆下載失敗)再加入回 201;沒有工作階段時試算回 503 `NO_READY_SESSION`;試算時 `list_local_models` 丟三個代碼分別回 502、504、502。
- 實測(`probes/test_probe_race.py`,兩個加入下載同時送出,`get_manifest` 以閘門擋住直到兩個都過了重複檢查,閘門記到 2 次):請求 1 `["qwen2.5:latest"]`、請求 2 `["a","qwen2.5"]`。

| 原型 | 請求 1 | 請求 2 | 佇列 |
|---|---|---|---|
| 接 `IntegrityError`、不包交易 | 201 | 409 `DOWNLOAD_ALREADY_QUEUED` | `qwen2.5:latest` 下載中、`a:latest` 排隊中 |
| 接 `IntegrityError`、整批包交易 | 201 | 409 `DOWNLOAD_ALREADY_QUEUED` | 只有 `qwen2.5:latest` 下載中 |

- 判斷:重複檢查和寫入之間隔著取 manifest 的 `await`,先查再寫擋不住同時送來的兩個請求;最後一道是 `pending_model` 的唯一限制。只接 `IntegrityError` 會留下回了 409 卻已寫進去的 `a:latest`(違反 FR-001「整批不加入佇列」),所以要包交易。
- 查證(`src/cgb/db/connection.py:connect`):連線是 `isolation_level=None`(每個敘述各自提交),UI 與 Ollama 相容端點在同一個事件迴圈共用這條連線,repo 裡沒有交易的寫法,所以要明寫 `BEGIN`/`COMMIT`/`ROLLBACK`。
- 判斷:`retryDownload` 把失敗的那筆重新排隊時,若佇列已有同名項目也會撞唯一限制回 500;這不是試算與加入下載,不在 spec 範圍內,列進待驗證留給之後。

**考慮過的替代方案**:

- 只修服務、不動轉接層:替身會丟 `AdapterError`,測試看起來綠,但真的 `RemoteOllama` 丟的是 httpx 例外與 `JSONDecodeError`(實測),真環境照樣 500。
- 重複檢查放在 `_sized()` 取 manifest 的迴圈裡:每個模型先取 manifest 才比對,違反 NFR-001。
- 改用應用程式層的鎖(`asyncio.Lock`)把整個加入下載排成一個一個:也擋得住同時送來的請求,但要鎖住取 manifest 的那段網路時間;唯一限制本來就在,交易加上接住它就夠。
- 一次補完 Q203 的 14 個代碼:範圍外(分身決策紀錄 D9)。

## R3. 顯示記憶體快取綁到工作階段(FR-003、FR-004、FR-005、NFR-002、SC-002、SC-003)

同類產品:Open WebUI —— 對照它的 Ollama 模型清單快取用什麼當鍵、怎麼失效。

**決策**:快取放在 `Catalog` 物件裡,只存一組 `(工作階段名稱, 顯示記憶體總量)`。

- **讀取**:`_vram_total()` 取 `lifecycle.current()["name"]`;快取的名稱和它相同就直接回快取的值,不跑 `probe_resources`。
- **寫入**:名稱不同或還沒有快取時呼叫 `probe_resources`;回傳的 `vramTotalBytes` 是整數才寫入快取(覆蓋前一個工作階段的那組);是 null 就回 null、不寫入。
- **失敗**:`probe_resources` 丟 `AdapterError`(含 `COLAB_TIMEOUT`、`COLAB_REMOTE_ERROR` 等所有代碼)時回 null、不寫入,`GET /api/models` 照常回 200,`mayNotFit` 跟著是 null(現有算式 `vram is not None` 已處理)。不另外寫日誌(分身決策紀錄 D7)。
- **失效**:不掛任何監聽器;工作階段換了名稱就自然對不上。開新的工作階段與變更執行階段類型都會產生新名稱(`SessionLifecycle._new_name`、`RuntimeSwitch.restart` 走 `reserve`),重連接回沿用原名稱,後端重新啟動後 `Catalog` 是新物件、快取是空的。
- **同時的第一次讀取**:不合併,可能各跑一次 `probe_resources`,之後都沿用(spec 假設)。
- **不共用試算的讀取**:試算與加入下載的 `probe_resources` 回傳也帶 `vramTotalBytes`,但不拿來寫這個快取;快取只由模型目錄自己讀。

**理由**:

- 查證(`src/cgb/services/catalog.py:list`、`_vram_total`、`preload`、`publish` 本體):`list()` 每次都呼叫 `_vram_total()`,`_vram_total()` 每次都 `probe_resources`、沒有接 `AdapterError`;`preload()` 與 `publish()`(推送 `models.updated`)都經 `list()`,所以快取放在 `_vram_total()` 一處,三條路徑(FR-003)都吃得到。
- 實測(`probes/test_probe_baseline.py`,改之前):連續 3 次 `GET /api/models` 跑 3 次 `probe_resources`;`probe_resources` 丟 `COLAB_TIMEOUT`、`COLAB_REMOTE_ERROR` 時回 500;回 `vramTotalBytes: null` 時回 200、`vramBytes` null。
- 查證(`src/cgb/services/session_lifecycle.py:_new_name`、`reserve`;`src/cgb/services/runtime_switch.py:restart`;`src/cgb/services/health_monitor.py:_reconnect`):每次開啟都以時間與 4 碼亂數產生新名稱,變更執行階段類型也是 `reserve` 一筆新的;重連只對同一個 `name` 重開通道,不換名稱。所以「名稱相同 = 同一個工作階段」,FR-005 的換掉與保留都由名稱決定。
- 實測(`probes/test_probe_proto.py`,原型,`probe_resources` 替身每次 `asyncio.sleep(3)`):

| 量測 | 結果 |
|---|---|
| 同一個工作階段連續 10 次 `GET /api/models` 的 `probe_resources` 次數 | 1 |
| 每次耗時(秒) | 3.010、0.003、0.002、0.002、0.002、0.002、0.002、0.002、0.002、0.002 |
| 10 次的 `vramBytes` | 都相同 |
| `POST /api/session/restart` 換成新工作階段後 2 次 `GET /api/models` 的次數 | 1 |

- 實測(同上,依序改替身的回傳,每次 `GET /api/models` 後看狀態碼、`vramBytes`、第一個模型的 `mayNotFit` 與累計次數):

| 替身 | 狀態碼 | `vramBytes` | `mayNotFit` | 累計次數 |
|---|---|---|---|---|
| 丟 `COLAB_TIMEOUT` | 200 | null | null | 1 |
| 回 `vramTotalBytes: null` | 200 | null | null | 2 |
| 丟 `COLAB_REMOTE_ERROR` | 200 | null | null | 3 |
| 回 16,106,127,360 | 200 | 16,106,127,360 | false | 4 |
| 改回 1(已快取,不該再讀) | 200 | 16,106,127,360 | false | 4 |

- 判斷:失敗與 null 每次都再讀、讀到數字之後就不再讀(驗收情境 4、5;SC-003),第 2 次起的耗時 0.002–0.003 秒遠低於 SC-002 的 1 秒。
- 查證(Open WebUI `backend/open_webui/routers/ollama.py` 的 `get_all_models`,GitHub main 分支):以 aiocache 的 `@cached(ttl=MODELS_CACHE_TTL, key_builder=...)` 快取,鍵是 `ollama_all_models_<user.id>`,另由 `clear_models_cache()` 在設定變更與卸載模型時清除。它的鍵是「這份清單屬於誰」,和這裡用工作階段名稱當鍵是同一個想法;它要 TTL 與主動清除,是因為模型清單會變,這裡快取的顯示記憶體總量在同一個工作階段內不會變,不需要 TTL,也不需要清除。
- 判斷:只存一組而不是名稱對值的 dict,舊工作階段的值不會留著;一次只有一個工作階段(001 `active_slot`),一組就夠。

**考慮過的替代方案**:

- 掛 `lifecycle.end_listeners` 與 `ready_listeners` 清快取:結束、變更類型、重連都會觸發 `ready_listeners`,重連時要另外分辨不能清;用名稱比對不用分辨。
- aiocache、cachetools、`functools.lru_cache` 這類快取套件或裝飾器:要新增套件(這一輪不新增),而且要另外寫「null 與失敗不快取」的條件,比一個 tuple 複雜。
- 存進資料庫(`sessions` 表加欄位):spec 假設快取只放記憶體、後端重新啟動後重讀,存表要改 `store.dbml`。
- 試算讀到的 `vramTotalBytes` 也寫進快取:能再少跑一次,但模型目錄的快取就有兩個寫入來源,測試「`colab exec` 只跑 1 次」要把試算也算進去;好處只是少等一次。

## R4. 驗收方式:會延遲並計數的 `probe_resources` 替身(SC-002、SC-003)

**決策**:

- **替身的改法**:`tests/fakes/adapters.py` 的 `FakeMethod.invoke` 在取得結果後,結果是 awaitable(`inspect.isawaitable`)就再 `await` 一次;測試就能寫 `fakes.colab.probe_resources.side_effect(async_func)`,在函式裡 `await asyncio.sleep(3)` 再回傳。同步的 `side_effect`、`returns`、`raises`、`then`、`gate` 行為不變。
- **計數**:用替身既有的 `call_count` 與 `reset_calls()`;每次 `probe_resources` 就是一次 `colab exec`(`ColabControl.probe_resources` 本體只有一次 `_exec_script`)。
- **SC-002**:開到就緒後 `reset_calls()`,連續 10 次 `GET /api/models`,斷言 `call_count == 1`、第 2 次起每次耗時 < 1 秒、`vramBytes` 都相同;再 `POST /api/session/restart` 等到就緒,`GET /api/models` 一次,斷言多了 1 次。
- **SC-003**:替身依序丟 `COLAB_TIMEOUT`、回 null、丟其他 `COLAB_*`,每次 `GET /api/models` 斷言 200、`vramBytes` null、`call_count` 加 1。
- **既有測試**:`tests/integration/test_api_models.py` 的 US3-API-26(`test_大小超過顯示記憶體總量才標可能無法載入_讀不到時是_null`)在同一個工作階段先讀到數字、再讓替身回 null,斷言第二次是 null;有了快取第二次會沿用數字,這個案例要由 testplan 與 tasks 改寫(例如讀不到的那一半改成第一次就讀到 null)。

**理由**:

- 查證(`tests/fakes/adapters.py:FakeMethod.invoke`、`_Outcome.resolve` 本體):`side_effect` 的函式被同步呼叫,回傳值原樣交回;傳 async 函式時交回的是沒有 await 的 coroutine。
- 實測(`probes/test_probe_baseline.py`,改之前):`probe_resources.side_effect(async 函式)` 時 `GET /api/models` 回 500(`resources["vramTotalBytes"]` 對 coroutine 取值失敗)。
- 實測(同上):改用同步函式裡 `time.sleep(0.3)` 也能延遲,`GET /api/models` 0.30 秒回 200;但它會卡住整個事件迴圈(`ui_client` 是同一個迴圈的 `ASGITransport`),延遲期間其他工作(推送、背景下載)都停住,測不了「同時打開模型頁與下載完成推送」這類情況。
- 實測(`probes/proto.py` 以 monkeypatch 換掉 `FakeMethod.invoke`,R3 的兩張表):async 替身每次延遲 3 秒,第一次 3.010 秒、之後 0.002–0.003 秒;同一支探針的其他案例照樣用同步的 `returns`、`raises`、`side_effect`、`gate` 而且都通過(7 passed)。
- 判斷:US3-API-26 照現在的寫法和 FR-003 衝突,不是程式錯;要在 testplan 換寫法,不能為了讓它綠而讓快取在 null 之後失效。

**考慮過的替代方案**:

- 同步函式裡 `time.sleep(3)`:不用改替身,但卡住事件迴圈(實測),而且讓 SC-002 的測試多等 3 秒時什麼都不能做。
- 以 `gate()` 擋住再由背景執行緒 3 秒後放行:做得到,但每個案例要多管一條執行緒,比讓 `invoke` 接受 async 函式複雜。
- 改用假時鐘 `FakeClock.sleep`:`FakeColabControl` 不經過 `state.clock`,替身裡要另外拿到時鐘;3 秒的真等待只在 SC-002 一個案例,不值得。

## 待驗證

| 來源 | 待驗證 | 驗證方式 / 時機 | 擋計畫? |
|---|---|---|---|
| R1 | 遠端 Colab 上的 Ollama 的 `/api/tags` 名稱一律帶版本(本機 0.32.15 實測 6/6 帶版本) | 下一次有人開真的工作階段時順手看一次 `/api/tags`;這一輪不開 Colab(D4) | 否 |
| R2 | 真環境裡遠端 Ollama 連不到、逾時時,試算與加入下載回 502、504(只用 MockTransport 與替身量過) | 不另外實跑;轉接層以 `httpx.MockTransport` 的整合測試驗 | 否 |
| R2 | `retryDownload` 把失敗的那筆重新排隊、佇列已有同名項目時回 500 | 範圍外,留給之後的迭代 | 否 |
| R3 | 真環境裡第 2 次起 `GET /api/models` 的耗時(只剩 `/api/tags` 與 `/api/ps`) | 不另外實跑(D4);001 已量過 `colab exec` 的耗時 | 否 |

## 修訂紀錄

無(2026-11-13 初版,尚未修訂)。
