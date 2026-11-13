# 測試計劃:官方模型庫的錯誤處理

- **規格**:`specs/002-library-error-handling/spec.md`
- **系統分析**:`plan.md` § 端點盤點(E2 後端 UI API、E8 Ollama 官方模型庫);`contracts/ui.openapi.yaml`、`contracts/model-library.openapi.yaml`
- **測試技術**:`techstack.md` § 一覽;research.md R2(逾時以建構參數縮短)、R5(替身注入與唯讀實跑)
- **日期**:2026-11-13
- **範疇**:使用者故事 1、2;每個測試案例在 `tasks.md` 對應一組 `/tdd` 紅燈與綠燈任務,量測與人工驗證的案例對應 📏 任務
- **預設資料**:除非案例另寫,關鍵字 `qwen2.5`、模型 `qwen2.5`、版本 `0.5b` 與 `7b`;搜尋頁、版本頁與 manifest 取自 `tests/fixtures/library/`;不存在的版本 `qwen2.5:cgb-test-nonexistent`;縮短的逾時 `request_timeout=0.5` 秒;試算與加入下載前工作階段已就緒(替身)

建立在 001 之上:現有的程式碼在 `src/cgb/`、測試在 `tests/`;替身只放在 `src/cgb/adapters/` 的轉接層邊界(E2 用 `tests/fakes/adapters.py` 的轉接層替身,E8 只把 ollama.com 與 registry 換成 `httpx.MockTransport`)。

## 1. 待測端點

端點、介面規格檔與公開接縫照抄 `plan.md` § 端點盤點與它指到的規格檔,本計劃不另做系統規劃;測試等級、工具與環境取自 `techstack.md` 與 research.md R5。上游沒寫到的,已登記到 `plan.md` 的待決問題 Q4~Q6,不在這裡自行補上。

| 端點 | 介面規格檔 | 公開接縫 | 測試等級 | 工具 | 測試環境 | 替身 |
|---|---|---|---|---|---|---|
| E2 後端 UI API(FastAPI REST) | `contracts/ui.openapi.yaml` | HTTP `/api/*` 的回應:搜尋、版本清單、試算、加入下載四個操作遇到模型庫失敗時的狀態碼、錯誤本文與訊息、指出出問題的模型、佇列不變 | 整合(真的 api、services、domain、repos 與 SQLite;轉接層用替身) | pytest + pytest-asyncio + `httpx.ASGITransport`,沿用 `tests/conftest.py` 的 `ui_client`、`fakes` 與 `tests/integration/test_api_session.py` 的 `ColabWorld`、`open_ready`、`error_code` | 每個測試一個暫存 SQLite 檔;`create_app` 注入替身與縮短的時限;模型庫的失敗以 `fakes.model_library.<方法>.raises(code)` 或 `.when(...).raises(code)` 注入 | `FakeModelLibrary`(官方模型庫轉接層)→ G-01、G-02<br>`httpx.ASGITransport`(uvicorn 與真的 HTTP 連線)→ G-01<br>`FakeColabControl`、`FakeTunnel`、`FakeRemoteOllama`(Colab 執行環境、SSH 通道與遠端 Ollama;只用來鋪就緒的工作階段與剩餘磁碟)→ 無法實跑:spec 假設這一輪不開 Colab、不花 compute units,這三個轉接層這一輪不改,真元件已在 001 的 US1-CLI-21、US1-TUN-10、US2-RO-03 實跑(plan.md Q5) |
| E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai) | `contracts/model-library.openapi.yaml` | `ModelLibrary` 的方法 `search_library`、`list_model_tags`、`get_manifest`:三個操作的失敗歸類(傳輸層失敗、狀態碼、回應格式不符的判定、每個請求的逾時) | 整合(真的 httpx、HTML 與 manifest 解析;對方用替身) | pytest + pytest-asyncio + `httpx.MockTransport`,沿用 `tests/integration/test_model_library.py` 的 `Recorder`、`html()` | 不連網;MockTransport 回各狀態碼、改版頁與 `tests/fixtures/library/` 的樣本,或在 handler 直接丟 `httpx.ConnectError`、`httpx.ReadTimeout`、`httpx.RemoteProtocolError`;逾時以 `ModelLibrary(request_timeout=<小值>)` 縮短(plan.md Q6),整體期限另以 127.0.0.1 上慢慢送資料的本機 socket 伺服器量(research.md R2、R5) | `httpx.MockTransport` 與存下來的頁面(ollama.com 與 registry.ollama.ai)→ G-02<br>127.0.0.1 的本機 socket 伺服器(ollama.com 與 registry 的不回應、慢慢送資料)→ 無法實跑:沒辦法叫真的 ollama.com 與 registry 不回應或慢下來(spec 假設、分身決策紀錄 D2) |
| 跨端點驗收 | E2、E8 的規格檔 | HTTP `/api/*` 的回應(真的 E2 接真的 `ModelLibrary`,plan.md Q4) | 整合(真的 api、services、domain、repos、SQLite 與 `ModelLibrary`;ollama.com 與 registry 用替身,其他轉接層用替身) | pytest + pytest-asyncio + `httpx.ASGITransport`;`make_app(model_library=ModelLibrary(transport=httpx.MockTransport(...)))` | 同 E2;MockTransport 的回應與丟出的例外同 E8 | `httpx.MockTransport`(ollama.com 與 registry.ollama.ai)→ G-02<br>`FakeColabControl`、`FakeTunnel`、`FakeRemoteOllama`(Colab 執行環境、SSH 通道與遠端 Ollama;只用來鋪就緒的工作階段與剩餘磁碟)→ 無法實跑:同 E2(plan.md Q5) |

### 受測操作

每個測試案例的「受測操作」欄照這張表某一列的寫法填;`tasks.md` 的 ⚙ 照「規格錨點」欄寫。跨端點驗收沿用 E2 的寫法。

| 端點 | 受測操作 | 規格錨點 | 寫法 |
|---|---|---|---|
| E2 後端 UI API(FastAPI REST) | 搜尋:`GET /api/library/search?q=<關鍵字>&page=<頁碼>` | `contracts/ui.openapi.yaml` § `paths./library/search.get`、`components.schemas.LibrarySearchPage`、`components.schemas.Error` | `/api/library` › 搜尋 |
| E2 後端 UI API(FastAPI REST) | 版本清單:`GET /api/library/models/{name}/tags` | `contracts/ui.openapi.yaml` § `paths./library/models/{name}/tags.get`、`components.schemas.LibraryTagList`、`components.schemas.Error` | `/api/library` › 版本清單 |
| E2 後端 UI API(FastAPI REST) | 試算:`POST /api/downloads/estimate` | `contracts/ui.openapi.yaml` § `paths./downloads/estimate.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadEstimate`、`components.schemas.Error` | `/api/downloads` › 試算 |
| E2 後端 UI API(FastAPI REST) | 加入下載:`POST /api/downloads` | `contracts/ui.openapi.yaml` § `paths./downloads.post`、`components.schemas.DownloadSelection`、`components.schemas.DownloadJobList`、`components.schemas.Error` | `/api/downloads` › 加入 |
| E2 後端 UI API(FastAPI REST) | 只用來鋪陳與觀察:列出佇列 `GET /api/downloads`、SSE `download.updated`(001 的操作,這一輪不改) | —(以 001 的規格檔為準) | `/api/downloads` › 列出 |
| E2 後端 UI API(FastAPI REST) | 只用來鋪陳與觀察:列出精選清單 `GET /api/curated`(001 的操作,這一輪不改) | —(以 001 的規格檔為準) | `/api/curated` › 列出 |
| E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai) | `ModelLibrary.search_library(q, page=1)` | `contracts/model-library.openapi.yaml` § `paths./search.get`、`components.schemas.SearchPage`、`components.schemas.SearchPageFragment`、`components.schemas.Error` | `ModelLibrary` › `search_library` |
| E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai) | `ModelLibrary.list_model_tags(name)` | `contracts/model-library.openapi.yaml` § `paths./library/{name}/tags.get`、`components.schemas.TagsPage`、`components.schemas.Error` | `ModelLibrary` › `list_model_tags` |
| E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai) | `ModelLibrary.get_manifest(name, tag)` | `contracts/model-library.openapi.yaml` § `paths./v2/library/{name}/manifests/{tag}.get`、`components.schemas.Manifest`、`components.schemas.RegistryErrorBody`、`components.schemas.Error` | `ModelLibrary` › `get_manifest` |

### 接縫的取捨

`/tdd` 紅燈步驟直接引用這張表,不再另外和使用者確認接縫;遇到這張表沒有的接縫才停下來問。

| 接縫(公開介面) | 抓得到 | 抓不到 |
|---|---|---|
| HTTP `/api/*`(`FakeModelLibrary` 丟 `AdapterError`) | 代碼到狀態碼的對應、`message` 取自固定訊息表、`model` 指出取不到的那一個、第一個失敗就停、佇列不變、不推送 `download.updated`、精選清單不受影響 | 轉接層把原生 httpx 例外漏出來(替身只會丟整齊的 `AdapterError`,由跨端點驗收補);真的 10 秒逾時(由 G-01 補) |
| `ModelLibrary` 的方法(對方是 `httpx.MockTransport` 與本機 socket 伺服器) | 傳輸層例外的歸類、狀態碼判定、搜尋頁與版本頁的格式判定、不跟著 3xx、縮短後的逾時與整體期限、例外不越過轉接層 | 真的 ollama.com 頁面結構(0 筆搜尋頁、第 2 頁社群模型)與正常路徑(由 G-02 補);UI API 的狀態碼(由 E2 與跨端點驗收補) |
| HTTP `/api/*`(真的 `ModelLibrary`,對方是 `httpx.MockTransport`) | 原生例外經兩層之後回的狀態碼與 `code`、沒有任何一次是 500、`message` 不帶例外文字或網址 | 真的頁面結構與真實時間(由 G-02、G-01 補) |

### 測試指令

慢的測試照專案現有的方式排除:`tests/e2e`(Playwright 真瀏覽器、固定 port 8781 與 11437 的 uvicorn)與 `realrun` marker(`pyproject.toml` 的 `addopts` 預設排除);單支超過 1 秒的測試專案沒有標記,照 `plan.md` Q20 的決定以 `--deselect` 逐一列出。

| 層 | 指令 | 包含 | 大約時間 |
|---|---|---|---|
| 快速層 | `uv run pytest tests/integration -q -p no:cacheprovider --deselect "tests/integration/test_model_library.py::test_沒指定逾時時搜尋在_10_秒逾時" --deselect "tests/integration/test_api_downloads.py::test_背景下載每秒最多推一則進度_完成後才出現在目錄" --deselect "tests/integration/test_secrets.py::test_登入_開啟_開啟失敗_重連逾時_結束的日誌_回應與事件都不含機密" --deselect "tests/integration/test_api_session.py::test_開啟超過總時限即失敗並釋放" --deselect "tests/integration/test_api_health.py::test_重連每一輪先關通道再確認再建立_照節奏直到時限" --deselect "tests/integration/test_api_health.py::test_重連時限到仍接不回時判定失聯並釋放執行環境" --deselect "tests/integration/test_api_health.py::test_重連逾時後釋放失敗時留下警告" --deselect "tests/integration/test_tunnel.py::test_open_tunnel_keeps_event_loop_responsive_while_ending_group_at_deadline" --deselect "tests/integration/test_tunnel.py::test_open_tunnel_has_ended_stubborn_group_when_deadline_passes" --deselect "tests/integration/test_tunnel.py::test_open_tunnel_returns_soon_after_deadline_even_when_group_ignores_sigterm" --deselect "tests/integration/test_tunnel.py::test_open_tunnel_times_out_at_deadline_even_when_group_ignores_sigterm" --deselect "tests/integration/test_logging.py::test_有轉送時輸出裡沒有_httpx_的請求行_沒有轉發位址與路徑" --deselect "tests/integration/test_colab_cli.py::test_create_session_command_line_is_accepted_by_real_cli" --deselect "tests/integration/test_tunnel.py::test_open_tunnel_stops_ssh_when_deadline_passes_with_remote_ollama_refusing" --deselect "tests/integration/test_api_health.py::test_健康檢查不重設閒置計時" --deselect "tests/integration/test_logging.py::test_正式啟動時請求紀錄輸出且含時間_沒有用戶端位址_路徑與_prompt" --deselect "tests/integration/test_tunnel.py::test_open_tunnel_stops_ssh_when_deadline_passes_with_local_port_refusing" --deselect "tests/integration/test_api_idle.py::test_後端重啟後閒置倒數接著算_不從重啟的時間重算" --deselect "tests/integration/test_tunnel.py::test_open_tunnel_keeps_waiting_until_deadline_then_reports_remote_refused" --deselect "tests/integration/test_api_idle.py::test_閒置檢查遇到非預期的例外時下一輪照常自動結束" --deselect "tests/integration/test_tunnel.py::test_open_tunnel_never_sets_gateway_ports" --deselect "tests/integration/test_tunnel.py::test_open_tunnel_keeps_waiting_until_deadline_then_times_out_when_local_port_refuses" --deselect "tests/integration/test_tunnel.py::test_open_tunnel_never_adds_gateway_remote_or_dynamic_forwarding" --deselect "tests/integration/test_tunnel.py::test_open_tunnel_binds_every_local_forward_to_loopback"` | `tests/integration`(替身、暫存 SQLite、127.0.0.1 隨機 port 的 uvicorn、MockTransport),排除 2026-11-13 實測單支超過 1 秒的 24 支(含 US1-LIB-25 的 10 秒預設逾時);不含 `tests/e2e`、`-m realrun`;`tests/unit` 目前沒有測試 | 約 140 秒(實測 139 秒,超過 30 秒的目標,見 `plan.md` Q20) |
| 全部 | `uv run pytest -q -p no:cacheprovider` | 上面加上被排除的 24 支與 `tests/e2e`(Playwright、固定 port 8781 與 11437);仍不含 `-m realrun`;e2e 用固定 port,同一時間只跑一份 | 約 6 分(實測 343 秒) |

## 2. 使用者故事 1 - 搜尋與看版本時模型庫出問題也知道原因(P1)

**本故事的需求**:FR-001~FR-003;邊界情況:搜尋第 2 頁起回 303、頁碼超過最後一頁、第 2 頁起只有社群模型、版本頁部分欄位解析不出來
**本故事涵蓋的全域 NFR**:FR-006、NFR-001、NFR-002、SC-001(彙整見第 4 節)

### 2.1 E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-LIB-01 | `ModelLibrary` › `search_library` | MockTransport 的 handler 對任何請求丟 `httpx.ConnectError("cgb-test-底層細節 ollama.com")`(代表 DNS 失敗) | 呼叫 `search_library("qwen2.5")` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:這個 `AdapterError` 的 `__cause__` 為 None,`__suppress_context__` 為 true(`from None`)<br>則3:這個 `AdapterError` 的 `message` 不含 `cgb-test-底層細節`,也不含 `ollama.com` | `_get` 沒有攔 httpx 例外,`ConnectError` 原樣往上拋(001 的行為,UI API 回 500);或攔了但用 `from error` 留著原本的例外鏈;或把 `str(原例外)` 接進 `message` | FR-001、FR-006、SC-001 |
| US1-LIB-02 | `ModelLibrary` › `search_library` | MockTransport 的 handler:情況 A 丟 `httpx.RemoteProtocolError`(讀回應到一半連線中斷),情況 B 丟 `httpx.ReadError` | 兩種情況各呼叫一次 `search_library("qwen2.5")` | 則1:情況 A 丟出 `AdapterError`,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:情況 B 丟出 `AdapterError`,`code` 為 `LIBRARY_UNREACHABLE` | 只攔 `httpx.ConnectError` 或 `httpx.NetworkError`,`RemoteProtocolError`(屬於 `ProtocolError`)原樣往上拋;或把讀到一半中斷歸成 `LIBRARY_TIMEOUT` | 邊界情況、FR-001、FR-006、SC-001 |
| US1-LIB-03 | `ModelLibrary` › `search_library` | MockTransport 的 handler:情況 A 丟 `httpx.ReadTimeout`,情況 B 丟 `httpx.ConnectTimeout` | 兩種情況各呼叫一次 `search_library("qwen2.5")` | 則1:情況 A 丟出 `AdapterError`,`code` 為 `LIBRARY_TIMEOUT`<br>則2:情況 B 丟出 `AdapterError`,`code` 為 `LIBRARY_TIMEOUT` | `except httpx.TransportError` 寫在 `except httpx.TimeoutException` 前面,逾時先被攔下、歸成 `LIBRARY_UNREACHABLE`(research.md R1);或只攔 `ReadTimeout`,連線逾時原樣往上拋 | FR-001、FR-006、SC-001 |
| US1-LIB-04 | `ModelLibrary` › `search_library` | MockTransport 回:情況 A 500、B 503、C 599,本文都是存下來的 `search-qwen2.5-page1.html` | 三種情況各呼叫一次 `search_library("qwen2.5")` | 則1:情況 A 丟出 `AdapterError`,`code` 為 `LIBRARY_SERVER_ERROR`<br>則2:情況 B 丟出 `AdapterError`,`code` 為 `LIBRARY_SERVER_ERROR`<br>則3:情況 C 丟出 `AdapterError`,`code` 為 `LIBRARY_SERVER_ERROR` | 不看狀態碼就解析本文,把 5xx 頁上的 `qwen2.5`、`qwen2.5-coder` 當成正常結果回傳(001 的行為);或只認 500 與 503 兩個值,599 被歸成 `LIBRARY_BAD_RESPONSE` | FR-001、SC-001 |
| US1-LIB-05 | `ModelLibrary` › `search_library` | MockTransport 回:情況 A 404、情況 B 429,本文都是 `search-qwen2.5-page1.html` | 兩種情況各呼叫一次 `search_library("qwen2.5")` | 則1:情況 A 丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則2:情況 B 丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE` | 三個操作共用的狀態碼判定一律把 404 歸成 `LIBRARY_NOT_FOUND`,讓搜尋回出合約沒列的代碼;或只判 404 與 5xx,其他非 200 照常解析本文、回出第 1 頁的結果 | FR-001、SC-001 |
| US1-LIB-06 | `ModelLibrary` › `search_library` | Recorder:帶 `page=2` 的請求回 303、`Location: /search?q=qwen2.5`;不帶 `page` 的請求回 `search-qwen2.5-page1.html` | 呼叫 `search_library("qwen2.5", page=2)` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則2:Recorder 總共只收到 1 個請求 | client 開了 `follow_redirects=True`,跟著導向去讀第 1 頁,把第 1 頁的 `qwen2.5`、`qwen2.5-coder` 當成第 2 頁的結果回傳;或 303 當成 200 處理、回空的 `items` | 邊界情況、FR-001、SC-001 |
| US1-LIB-07 | `ModelLibrary` › `search_library` | MockTransport 對第 1 頁回 200:情況 A `<!DOCTYPE html><html><body>維護中</body></html>`;情況 B 是改版頁,結果放在 `<div id="results">` 裡,有 `<a href="/library/qwen2.5" class="card">`,沒有 `id="searchresults"` | 兩種情況各呼叫一次 `search_library("qwen2.5")` | 則1:情況 A 丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則2:情況 B 丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE` | 找不到結果區塊時照 001 回空的 `items`,把改版當成「沒有符合的模型」;或只在解析出 0 筆時才判格式不符,情況 B 解析得出 `qwen2.5` 就照常回傳 | FR-001、SC-001 |
| US1-LIB-08 | `ModelLibrary` › `search_library` | MockTransport 對第 2 頁回 200 的片段 `<div class="notice"><p>Something went wrong</p></div>`(不是空白,也沒有任何 `<a href="/..." class="group grid` 結果) | 呼叫 `search_library("qwen2.5", page=2)` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE` | 第 2 頁起只要解析出 0 筆官方模型,就當成超過最後一頁、回空的 `items`,沒有先判斷本文是不是只有空白 | FR-001、SC-001 |
| US1-LIB-09 | `ModelLibrary` › `search_library` | 第 1 頁回 200:把 `search-qwen2.5-page1.html` 的 `<li>` 與下一頁連結全部刪掉,保留空的 `<ul role="list" id="searchresults">` | 呼叫 `search_library("zzzz-no-such-model")` | 則1:回傳的 `items` 是空陣列<br>則2:回傳的 `hasMore` 為 false | 0 筆官方模型一律當成格式不符,丟 `LIBRARY_BAD_RESPONSE`,「沒有符合的模型」變成錯誤,UI 退到 `library-down` | FR-001 |
| US1-LIB-10 | `ModelLibrary` › `search_library` | 第 2 頁回 200,本文只有 5 個換行 | 呼叫 `search_library("qwen2.5", page=34)` | 則1:回傳的 `items` 是空陣列<br>則2:回傳的 `hasMore` 為 false | 第 2 頁起也套用第 1 頁「要有 `id="searchresults"`」的條件;或沒有先 `strip()` 就判定「不是空白」,超過最後一頁被歸成 `LIBRARY_BAD_RESPONSE` | 邊界情況、FR-001 |
| US1-LIB-11 | `ModelLibrary` › `search_library` | 第 2 頁回 200 的片段,只有一筆社群模型 `<a href="/someone/qwen2.5-custom" class="group grid w-full">` | 呼叫 `search_library("qwen2.5", page=2)` | 則1:沒有丟出例外,回傳的 `items` 是空陣列 | 判定格式時只數 `/library/` 的官方模型連結,只有社群模型的頁被歸成 `LIBRARY_BAD_RESPONSE`(research.md R3) | 邊界情況、FR-001 |
| US1-LIB-12 | `ModelLibrary` › `search_library` | 第 2 頁回存下來的片段 `search-qwen2.5-page2.html`(沒有 `id="searchresults"`,有一筆 `/library/qwen2.5vl`) | 呼叫 `search_library("qwen2.5", page=2)` | 則1:回傳的 `items` 名稱只有 `qwen2.5vl` | 第 2 頁起也要求 `id="searchresults"`,正常的片段被歸成 `LIBRARY_BAD_RESPONSE`(片段本來就沒有這個區塊,見合約 `SearchPageFragment`) | FR-001 |
| US1-LIB-13 | `ModelLibrary` › `list_model_tags` | MockTransport 回 404,本文是 `<html><body>404 Not Found</body></html>` | 呼叫 `list_model_tags("no-such-model-zzz")` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_NOT_FOUND` | 不看狀態碼就解析 404 頁,得到空清單照常回傳(001 的行為,UI 顯示沒有版本);或 404 被格式判定歸成 `LIBRARY_BAD_RESPONSE` | FR-002、SC-001 |
| US1-LIB-14 | `ModelLibrary` › `list_model_tags` | MockTransport 回:情況 A 502、情況 B 503,本文都是 `tags-qwen2.5.html` | 兩種情況各呼叫一次 `list_model_tags("qwen2.5")` | 則1:情況 A 丟出 `AdapterError`,`code` 為 `LIBRARY_SERVER_ERROR`<br>則2:情況 B 丟出 `AdapterError`,`code` 為 `LIBRARY_SERVER_ERROR` | 不看狀態碼,本文解析得出版本就照常回 3 個版本;或 5xx 被歸成 `LIBRARY_BAD_RESPONSE` | FR-002、SC-001 |
| US1-LIB-15 | `ModelLibrary` › `list_model_tags` | Recorder:情況 A `/library/qwen2.5/tags` 回 301、`Location: /library/qwen2.5`,`/library/qwen2.5` 回 `tags-qwen2.5.html`;情況 B 回 403,本文是 `tags-qwen2.5.html` | 兩種情況各呼叫一次 `list_model_tags("qwen2.5")` | 則1:情況 A 丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則2:情況 A 的 Recorder 總共只收到 1 個請求<br>則3:情況 B 丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE` | client 開了 `follow_redirects=True`,跟著導向讀別的頁,並把那一頁的版本回傳;或只判 404 與 5xx,403 照常解析本文、回 3 個版本 | FR-002、SC-001 |
| US1-LIB-16 | `ModelLibrary` › `list_model_tags` | MockTransport 回 200:情況 A `<!DOCTYPE html><html><body>維護中</body></html>`;情況 B 是改版頁,版本連結變成 `href="/library/qwen2.5/tags/7b"`,另有 `href="/library/qwen2.5"` 與 `href="/library/llama3:8b"` | 兩種情況各呼叫一次 `list_model_tags("qwen2.5")` | 則1:情況 A 丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則2:情況 B 丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE` | 解析出空清單時照 001 回 `[]`,把改版當成「沒有版本」;或頁面上只要有任何 `/library/` 連結就不算格式不符 | FR-002、SC-001 |
| US1-LIB-17 | `ModelLibrary` › `list_model_tags` | MockTransport 回 200 `tags-qwen2.5.html`:`0.5b` 398MB、`7b` 4.7GB,`7b-cloud` 那一行沒有大小 | 呼叫 `list_model_tags("qwen2.5")` | 則1:沒有丟出例外,回傳的版本依序為 `0.5b`、`7b`、`7b-cloud`<br>則2:`7b-cloud` 的 `sizeLabel` 為 None | 只要有版本解析不出大小,就當成格式不符丟 `LIBRARY_BAD_RESPONSE`;或把解析不出大小的版本丟掉 | 邊界情況、FR-002 |
| US1-LIB-18 | `ModelLibrary` › `list_model_tags` | 不用 MockTransport,用真的 httpx:情況 A `ModelLibrary(ollama_base_url="http://127.0.0.1:<已關閉的 port>")`(真的連線被拒);情況 B `ollama_base_url="https://127.0.0.1:<只會講純 HTTP 的本機 socket 伺服器 port>"`(真的 TLS 交握失敗) | 兩種情況各呼叫一次 `list_model_tags("qwen2.5")` | 則1:情況 A 丟出 `AdapterError`,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:情況 B 丟出 `AdapterError`,`code` 為 `LIBRARY_UNREACHABLE`<br>則3:情況 B 的 `AdapterError` 的 `__cause__` 為 None,`__suppress_context__` 為 true | 只攔了 MockTransport 測得到的幾個例外類別,真的 httpx 在連線被拒或 TLS 失敗時丟的 `ConnectError`(底層是 `OSError`、`ssl.SSLError`)原樣往上拋;或用 `from error` 留著原本的例外鏈 | FR-002、FR-006、SC-001 |
| US1-LIB-19 | `ModelLibrary` › `list_model_tags` | 127.0.0.1 本機 socket 伺服器:收到請求後送出 `HTTP/1.1 200 OK`、`Content-Length: 2000` 的標頭與 100 bytes 本文,接著關閉連線;`ollama_base_url` 指向它 | 呼叫 `list_model_tags("qwen2.5")` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_UNREACHABLE` | 只攔 `httpx.NetworkError`,真的讀到一半斷線時 httpx 丟的 `RemoteProtocolError` 原樣往上拋;或把讀到一半中斷歸成 `LIBRARY_TIMEOUT` | 邊界情況、FR-002、FR-006、SC-001 |
| US1-LIB-20 | `ModelLibrary` › `list_model_tags` | MockTransport 的 handler:情況 A 丟 `httpx.ReadTimeout`,情況 B 丟 `httpx.ConnectTimeout` | 兩種情況各呼叫一次 `list_model_tags("qwen2.5")` | 則1:情況 A 丟出 `AdapterError`,`code` 為 `LIBRARY_TIMEOUT`<br>則2:情況 B 丟出 `AdapterError`,`code` 為 `LIBRARY_TIMEOUT` | `except httpx.TransportError` 寫在 `except httpx.TimeoutException` 前面,逾時被歸成 `LIBRARY_UNREACHABLE`;或版本清單沒有走共用的 `_get` 歸類,`ReadTimeout` 原樣往上拋 | FR-002、FR-006、SC-001 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-LIB-21 | 可靠性(每個請求的逾時) | 🔴🟢 行為測試 | `ModelLibrary` › `search_library` | 127.0.0.1 本機 socket 伺服器接受連線後一直不回;`ModelLibrary(ollama_base_url=<它>, request_timeout=0.5)` | 呼叫 `search_library("qwen2.5")` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_TIMEOUT`<br>則2:從呼叫到丟出在 0.5 到 0.8 秒之間 | `request_timeout` 沒有接到 client,httpx 沿用預設的 5 秒,約 5 秒才逾時;或整體期限到期時丟出的 `TimeoutError` 沒有歸類、原樣往上拋 | NFR-001、FR-001、FR-006、SC-001 | — | — |
| US1-LIB-22 | 可靠性(每個請求的逾時) | 🔴🟢 行為測試 | `ModelLibrary` › `list_model_tags` | 127.0.0.1 本機 socket 伺服器接受連線後一直不回;`ModelLibrary(ollama_base_url=<它>, request_timeout=0.5)` | 呼叫 `list_model_tags("qwen2.5")` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_TIMEOUT`<br>則2:從呼叫到丟出在 0.5 到 0.8 秒之間 | 版本清單自己建 client,沒有用 `request_timeout`,約 5 秒才逾時;或整體期限的 `TimeoutError` 原樣往上拋 | NFR-001、FR-002、FR-006、SC-001 | — | — |
| US1-LIB-23 | 可靠性(整體期限) | 🔴🟢 行為測試 | `ModelLibrary` › `search_library` | 127.0.0.1 本機 socket 伺服器立刻送出 200 的標頭與 `Content-Length: 40`,本文每 0.2 秒送 1 byte(全部送完要 8 秒);`request_timeout=0.5` | 呼叫 `search_library("qwen2.5")` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_TIMEOUT`<br>則2:從呼叫到丟出在 0.5 到 0.8 秒之間 | 只設了 httpx 的 `Timeout`,沒有用 `asyncio.timeout` 包住整個請求;每次讀取都在 0.5 秒內有資料,約 8 秒讀完才回(或回 `LIBRARY_BAD_RESPONSE`);或 `asyncio.timeout` 到期的 `TimeoutError` 沒有歸成 `LIBRARY_TIMEOUT` | 邊界情況、NFR-001、FR-001、FR-006、SC-001 | — | — |
| US1-LIB-24 | 可靠性(整體期限) | 🔴🟢 行為測試 | `ModelLibrary` › `list_model_tags` | 127.0.0.1 本機 socket 伺服器立刻送出 200 的標頭與 `Content-Length: 40`,本文每 0.2 秒送 1 byte;`request_timeout=0.5` | 呼叫 `list_model_tags("qwen2.5")` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_TIMEOUT`<br>則2:從呼叫到丟出在 0.5 到 0.8 秒之間 | 整體期限只包在 `search_library` 裡,版本清單沒包,約 8 秒讀完才回;或 `TimeoutError` 原樣往上拋 | 邊界情況、NFR-001、FR-002、FR-006、SC-001 | — | — |
| US1-LIB-25 | 可靠性(預設逾時 10 秒) | 🔴🟢 行為測試 | `ModelLibrary` › `search_library` | 127.0.0.1 本機 socket 伺服器接受連線後一直不回;`ModelLibrary(ollama_base_url=<它>)` 不帶 `request_timeout` | 呼叫 `search_library("qwen2.5")` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_TIMEOUT`<br>則2:從呼叫到丟出在 10.0 到 10.8 秒之間 | `request_timeout` 的預設值不是 `REQUEST_TIMEOUT_SECONDS`(10 秒),沿用 httpx 預設的 5 秒(001 的行為),或寫成其他秒數 | NFR-001、FR-001 | — | — |
| US1-LIB-26 | 可靠性(逾時每個請求各自計算) | 🔴🟢 行為測試 | `ModelLibrary` › `search_library` | 127.0.0.1 本機 socket 伺服器每個請求等 0.3 秒才送出完整回應(不帶 `page` 回 `search-qwen2.5-page1.html`,帶 `page=2` 回 `search-qwen2.5-page2.html`);同一個 `ModelLibrary(ollama_base_url=<它>, request_timeout=0.5)` | 依序呼叫 `search_library("qwen2.5")`、`search_library("qwen2.5", page=2)`(合計約 0.6 秒) | 則1:第 1 頁回傳的 `items` 名稱為 `qwen2.5`、`qwen2.5-coder`<br>則2:第 2 頁回傳的 `items` 名稱為 `qwen2.5vl` | 整體期限在建構 `ModelLibrary` 或第一次呼叫時起算、多個請求共用,第 2 頁在累計 0.5 秒時被判 `LIBRARY_TIMEOUT`(合約:「顯示更多」每讀一頁是一個請求,各自計算) | NFR-001、FR-001 | — | — |

### 2.2 E2 後端 UI API(FastAPI REST)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-API-01 | `/api/library` › 搜尋(`LIBRARY_UNREACHABLE`) | `ColabWorld(fakes)`,沒有開工作階段;`fakes.model_library.search_library.raises("LIBRARY_UNREACHABLE", "ConnectError: [Errno -2] Name or service not known")` | `GET /api/library/search?q=qwen2.5` | 則1:回 502,`error_code` 為 `LIBRARY_UNREACHABLE`<br>則2:回應本文的鍵只有 `code` 與 `message`,沒有 `model` | 搜尋先檢查有沒有就緒的工作階段,沒有就回 503 `NO_READY_SESSION`,沒有去問模型庫;或拿 `library_error(code, model=q)` 把關鍵字放進 `model` | FR-003 |
| US1-API-02 | `/api/library` › 搜尋(`LIBRARY_SERVER_ERROR`) | 工作階段就緒(`ColabWorld` + `open_ready`);`search_library.raises("LIBRARY_SERVER_ERROR", "HTTP 503 Service Unavailable")` | `GET /api/library/search?q=qwen2.5` | 則1:回 502,`error_code` 為 `LIBRARY_SERVER_ERROR` | 把模型庫的失敗都改寫成同一個 `LIBRARY_UNREACHABLE` 回傳(只對了 502、沒照轉接層的代碼);或把對方的 503 當成 UI API 的狀態碼回 503 | FR-003 |
| US1-API-03 | `/api/library` › 搜尋(`LIBRARY_BAD_RESPONSE`) | 沒有開工作階段;`search_library.raises("LIBRARY_BAD_RESPONSE", "no result rows on page 2")` | 按「顯示更多」:`GET /api/library/search?q=qwen2.5&page=2` | 則1:回 502,`error_code` 為 `LIBRARY_BAD_RESPONSE` | 第 2 頁起的 `LIBRARY_BAD_RESPONSE` 被當成「沒有下一頁」,回 200、空的 `items`、`hasMore` 為 false | FR-003 |
| US1-API-04 | `/api/library` › 搜尋(`LIBRARY_TIMEOUT`) | 沒有開工作階段;`search_library.raises("LIBRARY_TIMEOUT", "ReadTimeout: timed out")` | `GET /api/library/search?q=qwen2.5` | 則1:回 504<br>則2:回應是 JSON,`error_code` 為 `LIBRARY_TIMEOUT` | 沿用 001 的 `ApiError(502, error.code)`,把逾時也回 502;或 `MESSAGES` 沒有補 `LIBRARY_TIMEOUT`,`ApiError.body()` 丟 `KeyError`,結果變成不是 JSON 的 500 | FR-003 |
| US1-API-05 | `/api/library` › 搜尋(找不到符合的模型) | 沒有開工作階段;`search_library.returns({"items": [], "hasMore": False})` | `GET /api/library/search?q=no-such-model-xyz` | 則1:回 200,`items` 是空陣列<br>則2:`hasMore` 為 false | 這一輪加錯誤處理時,把 0 筆結果也當成格式不符,回 502 `LIBRARY_BAD_RESPONSE` | FR-003 |
| US1-API-06 | `/api/library` › 版本清單(`LIBRARY_NOT_FOUND`) | 沒有開工作階段;`list_model_tags.when(name="qwen2.6").raises("LIBRARY_NOT_FOUND", "HTTP 404 Not Found")` | `GET /api/library/models/qwen2.6/tags` | 則1:回 404,`error_code` 為 `LIBRARY_NOT_FOUND`<br>則2:回應本文的鍵只有 `code` 與 `message`,沒有 `model` | `Library.tags()` 沒有接 `AdapterError`,原樣往上拋成 500;或比照 001 的搜尋把所有代碼都回 502;或把 `name` 放進 `model` | FR-003 |
| US1-API-07 | `/api/library` › 版本清單(`LIBRARY_UNREACHABLE`) | 工作階段就緒(`ColabWorld` + `open_ready`);`list_model_tags.raises("LIBRARY_UNREACHABLE", "ConnectError: connection refused")` | `GET /api/library/models/qwen2.5/tags` | 則1:回 502,`error_code` 為 `LIBRARY_UNREACHABLE` | `tags()` 只用 `if error.code == "LIBRARY_NOT_FOUND"` 接住 404,其他代碼重新拋出,變成 500 | FR-003 |
| US1-API-08 | `/api/library` › 版本清單(`LIBRARY_SERVER_ERROR`) | 沒有開工作階段;`list_model_tags.raises("LIBRARY_SERVER_ERROR", "HTTP 500 Internal Server Error")` | `GET /api/library/models/qwen2.5/tags` | 則1:回 502,`error_code` 為 `LIBRARY_SERVER_ERROR` | `LIBRARY_STATUS` 漏掉 `LIBRARY_SERVER_ERROR`,`.get(code, 500)` 退回 500;或把它歸成 `LIBRARY_BAD_RESPONSE` | FR-003 |
| US1-API-09 | `/api/library` › 版本清單(`LIBRARY_BAD_RESPONSE`) | 沒有開工作階段;`list_model_tags.raises("LIBRARY_BAD_RESPONSE", "no /library/qwen2.5:<tag> link")` | `GET /api/library/models/qwen2.5/tags` | 則1:回 502,`error_code` 為 `LIBRARY_BAD_RESPONSE` | 把格式不符當成「這個模型沒有版本」,回 200 與空的 `tags` | FR-003 |
| US1-API-10 | `/api/library` › 版本清單(`LIBRARY_TIMEOUT`) | 沒有開工作階段;`list_model_tags.raises("LIBRARY_TIMEOUT", "ReadTimeout: timed out")` | `GET /api/library/models/qwen2.5/tags` | 則1:回 504<br>則2:回應是 JSON,`error_code` 為 `LIBRARY_TIMEOUT` | 版本清單自己寫了一張只有 404 與 502 的對應表,沒有共用 `LIBRARY_STATUS`,逾時回 502;或 `MESSAGES` 沒有 `LIBRARY_TIMEOUT`,變成 500 | FR-003 |
| US1-API-11 | `/api/library` › 版本清單(部分欄位解析不出來) | 工作階段就緒,執行環境上有 `qwen2.5:0.5b`(`set_tags(fakes, tag(QWEN_SMALL, QWEN_SMALL_BYTES))`);`list_model_tags.returns([{"tag": "0.5b", "sizeLabel": "398MB", "contextLength": "32K", "cloudOnly": False}, {"tag": "7b", "sizeLabel": None, "contextLength": None, "cloudOnly": False}])` | `GET /api/library/models/qwen2.5/tags` | 則1:回 200,`tags` 依序有 `0.5b`、`7b` 兩筆<br>則2:`7b` 的 `sizeLabel` 是 null<br>則3:`7b` 的 `contextLength` 是 null<br>則4:`7b` 的 `fullName` 是 `qwen2.5:7b`、`downloaded` 為 false<br>則5:`0.5b` 的 `downloaded` 為 true | 補錯誤處理時加了「沒有大小就是格式不符」的檢查,回 502 `LIBRARY_BAD_RESPONSE`;或把缺大小的版本濾掉;或從 `sizeLabel` 換算 `approxSizeBytes` 時對 None 丟 `TypeError`,變成 500 | 邊界情況 |
| US1-API-12 | `/api/library` › 搜尋(`LIBRARY_UNREACHABLE`)→ `/api/curated` › 列出 → `/api/downloads` › 列出 | 工作階段就緒,`downloadable(fakes)`;精選清單直接寫入暫存 SQLite 的 `curated_models` 一筆 `llama3.2:3b`;以 `enqueue_waiting(ui_client, fakes, QWEN_7B)` 讓 `qwen2.5:7b` 停在下載中;接著 `search_library.raises("LIBRARY_UNREACHABLE", "ConnectError")` | `GET /api/library/search?q=qwen2.5`,接著 `GET /api/curated`,再 `GET /api/downloads` | 則1:搜尋回 502,`error_code` 為 `LIBRARY_UNREACHABLE`<br>則2:`GET /api/curated` 回 200,`items` 的名稱是 `["llama3.2:3b"]`<br>則3:`GET /api/downloads` 的 `states()` 是 `[("qwen2.5:7b", "downloading")]`<br>則4:`fakes.remote_ollama.pull_model.call_count` 仍是 1 | 模型庫的 `AdapterError` 被一個全域的 `AdapterError` 處理器接走,當成執行環境出問題,把下載中的那筆標成 `failed` 或重新開始 pull;或搜尋失敗時精選清單的查詢也跟著回錯誤 | 邊界情況 |
| US1-API-13 | `/api/library` › 版本清單(`LIBRARY_SERVER_ERROR`)→ `/api/library` › 搜尋 | 工作階段就緒,執行環境上有 `qwen2.5:0.5b`(`set_tags`);`list_model_tags.raises("LIBRARY_SERVER_ERROR", "HTTP 502 Bad Gateway")`;`search_library.returns(search_page("qwen2.5", has_more=False))` | `GET /api/library/models/qwen2.5/tags`,接著 `GET /api/library/search?q=qwen2.5` | 則1:版本清單回 502,`error_code` 為 `LIBRARY_SERVER_ERROR`<br>則2:搜尋回 200,`runtimeChecked` 為 true<br>則3:搜尋結果 `qwen2.5` 的 `downloadedTags` 是 `["0.5b"]` | 版本清單失敗時把工作階段轉成重連中(或清掉執行環境模型的對照),之後搜尋的 `runtimeChecked` 變成 false、已下載的版本標不出來 | 邊界情況 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-API-14 | 安全(錯誤訊息不外洩內部細節) | 🔴🟢 行為測試 | `/api/library` › 搜尋(`LIBRARY_UNREACHABLE`) | 沒有開工作階段;替身帶英文與網址的訊息:`search_library.raises("LIBRARY_UNREACHABLE", "httpx.ConnectError: [Errno -3] Temporary failure in name resolution (https://ollama.com/search?q=qwen2.5&c=local)")` | `GET /api/library/search?q=qwen2.5` | 則1:`message` 等於 `cgb.domain.errors.MESSAGES["LIBRARY_UNREACHABLE"]`<br>則2:`message` 不含 `ConnectError`<br>則3:`message` 不含 `https://`<br>則4:`message` 含「從精選清單挑選或直接輸入名稱」 | 把 `AdapterError.message` 接在固定說明後面回傳(例如 `f"{MESSAGES[code]}({error.message})"`),或直接用它取代說明 | NFR-002、FR-003 | — | — |
| US1-API-15 | 安全(錯誤訊息不外洩內部細節) | 🔴🟢 行為測試 | `/api/library` › 版本清單(`LIBRARY_TIMEOUT`) | 沒有開工作階段;`list_model_tags.raises("LIBRARY_TIMEOUT", "ReadTimeout: timed out after 10.0s (https://ollama.com/library/qwen2.5/tags)")` | `GET /api/library/models/qwen2.5/tags` | 則1:`MESSAGES` 有 `LIBRARY_TIMEOUT` 這個鍵,且 `message` 等於它<br>則2:`message` 含「從精選清單挑選或直接輸入名稱」<br>則3:`message` 不含 `ReadTimeout`<br>則4:`message` 不含 `https://` | `MESSAGES` 沒有補 `LIBRARY_TIMEOUT`,`body()` 退回去用 `AdapterError.message` 或代碼字串當 `message` | NFR-002、FR-003 | — | — |
| US1-API-16 | 一致性(同一個代碼同一句說明) | 🔴🟢 行為測試 | `/api/library` › 搜尋(`LIBRARY_SERVER_ERROR`)→ `/api/library` › 版本清單(`LIBRARY_SERVER_ERROR`) | 沒有開工作階段;`search_library.raises("LIBRARY_SERVER_ERROR", "HTTP 502 Bad Gateway")`;`list_model_tags.raises("LIBRARY_SERVER_ERROR", "HTTP 500 Internal Server Error")` | `GET /api/library/search?q=qwen2.5`,接著 `GET /api/library/models/qwen2.5/tags` | 則1:搜尋的 `message` 等於 `MESSAGES["LIBRARY_SERVER_ERROR"]`<br>則2:版本清單的 `message` 等於 `MESSAGES["LIBRARY_SERVER_ERROR"]` | 版本清單另外寫了一張訊息表,或把模型名稱或對方的狀態碼插進說明(例如「qwen2.5 的版本頁回 500」),同一個代碼在兩個操作是不同的兩句 | NFR-002 | — | — |
| US1-API-17 | 安全(錯誤訊息不外洩內部細節) | 🔴🟢 行為測試 | `/api/library` › 版本清單(`LIBRARY_NOT_FOUND`) | 沒有開工作階段;`list_model_tags.raises("LIBRARY_NOT_FOUND", "404 Not Found: https://ollama.com/library/qwen2.6/tags")` | `GET /api/library/models/qwen2.6/tags` | 則1:`message` 等於 `MESSAGES["LIBRARY_NOT_FOUND"]`<br>則2:`message` 不含 `404 Not Found`<br>則3:`message` 不含 `https://` | 只有 502 與 504 走固定訊息表,404 這條另外寫成「找不到:」加上 `AdapterError.message` | NFR-002、FR-003 | — | — |

### 2.3 跨端點驗收

真的 E2(api、services、domain、repos 與 SQLite)接真的 `ModelLibrary`,只把 ollama.com 換成 `httpx.MockTransport`(plan.md Q4);在 2.1、2.2 都完成後才開始。

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US1-AJ-01 | `/api/library` › 搜尋 | `make_app(model_library=ModelLibrary(transport=httpx.MockTransport(handler), request_timeout=0.5))`,沒有開工作階段;handler 依情況:A 丟 `httpx.ConnectError`、B 丟 `httpx.ReadTimeout`、C 丟 `httpx.RemoteProtocolError`、D 回 503、E 回 200 但沒有 `id="searchresults"` 的維護頁 | 每種情況各送一次 `GET /api/library/search?q=qwen2.5` | 則1:A 回 502,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:B 回 504,`code` 為 `LIBRARY_TIMEOUT`<br>則3:C 回 502,`code` 為 `LIBRARY_UNREACHABLE`<br>則4:D 回 502,`code` 為 `LIBRARY_SERVER_ERROR`<br>則5:E 回 502,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則6:五次回應的 Content-Type 都是 `application/json`,沒有任何一次是 500 | 轉接層只在 `get_manifest` 攔例外,`search_library` 讓 httpx 例外穿過 services 變成 500(Q178);或服務層對逾時仍回 502;或 5xx 頁照常解析、回 200 | FR-001、FR-003、FR-006、SC-001 |
| US1-AJ-02 | `/api/library` › 版本清單 | 同 US1-AJ-01 的 app;handler 依情況:A 丟 `httpx.ConnectError`、B 丟 `httpx.ConnectTimeout`、C 回 404、D 回 502、E 回 200 但沒有任何 `/library/qwen2.5:<版本>` 連結、F 回 301 | 每種情況各送一次 `GET /api/library/models/qwen2.5/tags` | 則1:A 回 502,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:B 回 504,`code` 為 `LIBRARY_TIMEOUT`<br>則3:C 回 404,`code` 為 `LIBRARY_NOT_FOUND`<br>則4:D 回 502,`code` 為 `LIBRARY_SERVER_ERROR`<br>則5:E 回 502,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則6:F 回 502,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則7:六次都沒有 500 | `Library.tags()` 沒接 `AdapterError`,轉接層丟出的錯變成 500;或轉接層不看狀態碼,404 與 5xx 頁解析成空清單回 200 | FR-002、FR-003、FR-006、SC-001 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US1-AJ-03 | 安全(錯誤訊息不外洩內部細節) | 🔴🟢 行為測試 | `/api/library` › 搜尋 | 同 US1-AJ-01 的 app;handler 丟 `httpx.ConnectError("[Errno -2] Name or service not known: https://ollama.com/search?q=qwen2.5")` | 送 `GET /api/library/search?q=qwen2.5` | 則1:回 502,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:`message` 等於 `MESSAGES["LIBRARY_UNREACHABLE"]`<br>則3:回應本文的原文不含 `ollama.com`<br>則4:回應本文的原文不含 `Errno` | 轉接層把 `str(原例外)` 放進 `AdapterError.message`,服務層又把它接進回應;或例外越層後由 FastAPI 的預設處理器把例外文字回給 UI | NFR-002、FR-006 | — | — |

### 2.4 交給 `/tdd` 的順序

每個案例在 `tasks.md` 是一組紅燈、綠燈任務;每一節的案例都做完後,接一個重構任務。同一個故事的端點節彼此平行,跨端點驗收在端點節都完成後才開始。

1. E8 Ollama 官方模型庫:US1-LIB-01 → US1-LIB-02 → … → US1-LIB-26 → 重構
2. E2 後端 UI API:US1-API-01 → US1-API-02 → … → US1-API-17 → 重構
3. 跨端點驗收(E8、E2 完成後):US1-AJ-01 → US1-AJ-02 → US1-AJ-03 → 重構

## 3. 使用者故事 2 - 試算與加入下載時取不到模型大小也知道原因(P1)

**本故事的需求**:FR-004、FR-005;邊界情況:registry 的 404 不分模型或版本
**本故事涵蓋的全域 NFR**:FR-006、NFR-001、NFR-002、SC-001(彙整見第 4 節)

### 3.1 E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US2-LIB-01 | `ModelLibrary` › `get_manifest` | `registry_reply` 回 200,Content-Type 是 `application/vnd.docker.distribution.manifest.v2+json`,本文是 `tests/fixtures/library/manifest-qwen2.5-7b.json`;`ModelLibrary(transport=…)` 不帶 `request_timeout` | 呼叫 `get_manifest("qwen2.5", "7b")` | 則1:回傳 `{"sizeBytes": 4683087332}`(4 層合計,不含 `config.size` 487)<br>則2:Recorder 收到的那個請求,`extensions["timeout"]` 是 `{"connect": 10.0, "read": 10.0, "write": 10.0, "pool": 10.0}` | 改成三個操作共用狀態碼判定時,把搜尋頁的格式判定(找 `id="searchresults"`)也套到 manifest,正常的 200 manifest 被歸成 `LIBRARY_BAD_RESPONSE`;或 `_get` 建 client 時沒帶 timeout,用的是 httpx 預設的 5 秒 | FR-004、NFR-001 |
| US2-LIB-02 | `ModelLibrary` › `get_manifest` | Recorder 的 handler 對任何路徑都回 404,Content-Type 是 `text/plain; charset=utf-8`,本文是 `{"errors":[{"code":"MANIFEST_UNKNOWN","message":"manifest unknown"}]}`(registry 對「沒有這個模型」與「沒有這個版本」回的內容相同) | 依序呼叫 `get_manifest("no-such-model", "latest")` 與 `get_manifest("qwen2.5", "999b")` | 則1:第一次丟出 `AdapterError`,`code` 為 `LIBRARY_NOT_FOUND`<br>則2:第二次丟出 `AdapterError`,`code` 為 `LIBRARY_NOT_FOUND` | 為了分辨模型與版本而去讀 404 本文的 `errors[0].code`,只有 `NAME_UNKNOWN` 才歸 `LIBRARY_NOT_FOUND`,`MANIFEST_UNKNOWN` 被歸成 `LIBRARY_BAD_RESPONSE`;或先把本文當 manifest 解析、後看狀態碼,404 本文沒有 `layers` 而被歸成 `LIBRARY_BAD_RESPONSE` | FR-004、邊界情況、SC-001 |
| US2-LIB-03 | `ModelLibrary` › `get_manifest` | 情況 A:registry 回 500;B:回 503,本文 `Service Unavailable`;C:回 599;D:回 502,本文是 `manifest-qwen2.5-7b.json` 的全文 | 每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")` | 則1:A 丟出 `AdapterError`,`code` 為 `LIBRARY_SERVER_ERROR`<br>則2:B 的 `code` 為 `LIBRARY_SERVER_ERROR`<br>則3:C 的 `code` 為 `LIBRARY_SERVER_ERROR`<br>則4:D 丟出 `AdapterError`,`code` 為 `LIBRARY_SERVER_ERROR` | 只認 `== 503`,或只認 `in (500, 502, 503, 504)`,599 被歸成 `LIBRARY_BAD_RESPONSE`;或範圍寫成 `500 < status`,漏掉 500;或先解析本文、後看狀態碼,本文是合法 manifest 的 502 被當成成功回傳 `sizeBytes` | FR-004、SC-001 |
| US2-LIB-04 | `ModelLibrary` › `get_manifest` | Recorder 的 handler 依路徑回應:`/v2/library/qwen2.5/manifests/7b` 回 301,`Location: /v2/library/qwen2.5/manifests/latest`;`…/latest` 回 200 與 `manifest-qwen2.5-7b.json`;`…/14b` 回 401;`…/32b` 回 429 | 依序呼叫 `get_manifest("qwen2.5", "7b")`、`get_manifest("qwen2.5", "14b")`、`get_manifest("qwen2.5", "32b")` | 則1:`7b` 丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則2:Recorder 收到的請求裡,沒有一個的路徑是 `/v2/library/qwen2.5/manifests/latest`<br>則3:`14b` 的 `code` 為 `LIBRARY_BAD_RESPONSE`<br>則4:`32b` 的 `code` 為 `LIBRARY_BAD_RESPONSE` | client 開了 `follow_redirects=True`,跟著 301 去讀 `latest` 的 manifest 並回傳 `sizeBytes`;或所有 4xx 一律歸成 `LIBRARY_NOT_FOUND`;或 429 被當成伺服器忙碌歸成 `LIBRARY_SERVER_ERROR` | FR-004、SC-001 |
| US2-LIB-05 | `ModelLibrary` › `get_manifest` | 情況 A:registry 回 200,Content-Type 是 `text/html; charset=utf-8`,本文是 `<!DOCTYPE html><html><body>維護中</body></html>`;B:回 200,Content-Type 是 `text/plain; charset=utf-8`,本文是 `manifest-qwen2.5-7b.json` 的前 120 個字元(截斷的 JSON);C:回 200,Content-Type 是 `text/plain; charset=utf-8`,本文是空的 | 每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")` | 則1:A 丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則2:B 的 `code` 為 `LIBRARY_BAD_RESPONSE`<br>則3:C 的 `code` 為 `LIBRARY_BAD_RESPONSE` | 沒接 `json.loads` 丟的 `JSONDecodeError`,讓它原樣往上拋;或靠 Content-Type 判斷格式,只把 `text/html` 歸成格式不符,`text/plain` 的截斷或空本文仍然丟出 `JSONDecodeError` | FR-004、SC-001 |
| US2-LIB-06 | `ModelLibrary` › `get_manifest` | registry 都回 200,本文依情況是:A `[]`;B 沒有 `layers` 鍵的物件;C `"layers": null`;D `"layers": {}`;E `layers` 有一層沒有 `size`;F `layers` 有一層的 `size` 是字串 `"4683071744"`(其餘欄位取自 `manifest-qwen2.5-7b.json`) | 每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")` | 則1:A 丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則2:B 的 `code` 為 `LIBRARY_BAD_RESPONSE`<br>則3:C 的 `code` 為 `LIBRARY_BAD_RESPONSE`<br>則4:D 的 `code` 為 `LIBRARY_BAD_RESPONSE`<br>則5:E 的 `code` 為 `LIBRARY_BAD_RESPONSE`<br>則6:F 的 `code` 為 `LIBRARY_BAD_RESPONSE` | 先用 `if not layers` 判雲端版本、後檢查型別,`null` 與 `{}` 被歸成 `LIBRARY_CLOUD_ONLY`;或直接寫 `manifest["layers"]`、`layer["size"]` 取值,`KeyError`、`TypeError` 原樣往上拋;或沒檢查 `size` 的型別,`sum` 碰到字串丟出 `TypeError` | FR-004、SC-001 |
| US2-LIB-07 | `ModelLibrary` › `get_manifest` | 情況 A:registry 回 200,Content-Type 是 `text/plain; charset=utf-8`,本文是 `tests/fixtures/library/manifest-qwen2.5-7b-cloud.json`(`layers` 是空陣列);B:本文相同,Content-Type 改成 `application/vnd.docker.distribution.manifest.v2+json` | 每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")` | 則1:A 丟出 `AdapterError`,`code` 為 `LIBRARY_CLOUD_ONLY`<br>則2:B 丟出 `AdapterError`,`code` 為 `LIBRARY_CLOUD_ONLY` | 靠 Content-Type 是 `text/plain` 判雲端版本,B 回傳了 `{"sizeBytes": 0}`;或把 `text/plain` 當成格式不符,A 被歸成 `LIBRARY_BAD_RESPONSE`;或 `layers` 空時直接回 `{"sizeBytes": 0}`,不丟錯 | FR-004、SC-001 |
| US2-LIB-08 | `ModelLibrary` › `get_manifest` | registry 回 200,帶 `Content-Encoding: gzip`,本文是 `not gzip`(不是 gzip 資料,httpx 解壓時丟出 `httpx.DecodingError`) | 呼叫 `get_manifest("qwen2.5", "7b")` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_BAD_RESPONSE` | `_get` 只接 `httpx.TimeoutException` 與 `httpx.TransportError`;`DecodingError` 是 `RequestError` 的子類別,不是 `TransportError`,於是原樣越過轉接層往上拋 | FR-006、FR-004 |
| US2-LIB-09 | `ModelLibrary` › `get_manifest` | MockTransport 的 handler 依情況丟出:A `httpx.ConnectError("[Errno -2] Name or service not known")`(DNS 失敗);B `httpx.ConnectError("[Errno 111] Connection refused")`(連線被拒);C `httpx.ConnectError("[SSL: WRONG_VERSION_NUMBER] wrong version number")`(TLS 失敗) | 每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")` | 則1:A 丟出 `AdapterError`,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:B 的 `code` 為 `LIBRARY_UNREACHABLE`<br>則3:C 的 `code` 為 `LIBRARY_UNREACHABLE`<br>則4:A 丟出的 `AdapterError`,`__cause__` 是 `None`、`__suppress_context__` 是 `True` | `get_manifest` 沒接傳輸層例外,`httpx.ConnectError` 原樣往上拋;或靠例外文字判斷,只有含 `Connection refused` 的才歸 `LIBRARY_UNREACHABLE`;或寫成 `raise AdapterError(...) from error`、或在 `except` 裡沒加 `from None` 就 raise,把原始例外鏈一起帶上去 | FR-006、FR-004、SC-001 |
| US2-LIB-10 | `ModelLibrary` › `get_manifest` | MockTransport 的 handler 依情況丟出:A `httpx.RemoteProtocolError("peer closed connection without sending complete message body")`;B `httpx.ReadError("[Errno 104] Connection reset by peer")` | 每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")` | 則1:A 丟出 `AdapterError`,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:B 的 `code` 為 `LIBRARY_UNREACHABLE` | 只接 `httpx.NetworkError` 或 `httpx.ConnectError`,屬於 `ProtocolError` 的 `RemoteProtocolError` 原樣往上拋;或以為「有連上就有回應」,讀回應時的中斷被歸成 `LIBRARY_BAD_RESPONSE` | FR-006、FR-004、邊界情況 |
| US2-LIB-11 | `ModelLibrary` › `get_manifest` | MockTransport 的 handler 依情況丟出:A `httpx.ReadTimeout("timed out")`;B `httpx.ConnectTimeout("timed out")`;C `httpx.PoolTimeout("timed out")` | 每種情況各呼叫一次 `get_manifest("qwen2.5", "7b")` | 則1:A 丟出 `AdapterError`,`code` 為 `LIBRARY_TIMEOUT`<br>則2:B 的 `code` 為 `LIBRARY_TIMEOUT`<br>則3:C 的 `code` 為 `LIBRARY_TIMEOUT` | 先寫 `except httpx.TransportError` 再寫 `except httpx.TimeoutException`,逾時被前者攔下歸成 `LIBRARY_UNREACHABLE`;或只接 `ReadTimeout`,`ConnectTimeout`、`PoolTimeout` 原樣往上拋 | FR-006、FR-004、SC-001 |
| US2-LIB-12 | `ModelLibrary` › `get_manifest` | 127.0.0.1 上的本機 socket 伺服器收到請求後,送出 `HTTP/1.1 200 OK`、`Content-Type: application/vnd.docker.distribution.manifest.v2+json`、`Content-Length: 2000`,再送 `manifest-qwen2.5-7b.json` 的前 200 位元組,然後關閉連線;`ModelLibrary(registry_base_url="http://127.0.0.1:<port>", request_timeout=0.5)` | 呼叫 `get_manifest("qwen2.5", "7b")` | 則1:丟出 `AdapterError`,`code` 為 `LIBRARY_UNREACHABLE` | 用 `client.stream` 取回應,`try` 只包住送出請求,讀本文時的 `RemoteProtocolError` 在 `try` 外原樣往上拋;或把讀到一半中斷當成內容壞掉,歸成 `LIBRARY_BAD_RESPONSE` | FR-006、FR-004、邊界情況 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US2-LIB-13 | 可靠性(每個請求的逾時) | 🔴🟢 行為測試 | `ModelLibrary` › `get_manifest` | 127.0.0.1 上的本機 socket 伺服器接受連線後,一個位元組都不送,也不關連線;`ModelLibrary(registry_base_url="http://127.0.0.1:<port>", request_timeout=0.5)` | 呼叫 `get_manifest("qwen2.5", "7b")`,從呼叫開始計時 | 則1:呼叫後 0.5 到 0.8 秒之間丟出 `AdapterError`<br>則2:該 `AdapterError` 的 `code` 為 `LIBRARY_TIMEOUT` | 建構參數 `request_timeout` 沒接到 httpx 的 `Timeout` 與 `asyncio.timeout`,仍用 httpx 預設的 5 秒或寫死的 10 秒;或 `ReadTimeout` 被歸成 `LIBRARY_UNREACHABLE` | NFR-001、FR-006 | — | — |
| US2-LIB-14 | 可靠性(讀到一半逾時) | 🔴🟢 行為測試 | `ModelLibrary` › `get_manifest` | 本機 socket 伺服器送出 `HTTP/1.1 200 OK`、`Content-Length: 2000`,再送 `manifest-qwen2.5-7b.json` 的前 200 位元組,之後不再送、也不關連線;`request_timeout=0.5` | 呼叫 `get_manifest("qwen2.5", "7b")`,從呼叫開始計時 | 則1:呼叫後 0.5 到 0.8 秒之間丟出 `AdapterError`<br>則2:該 `AdapterError` 的 `code` 為 `LIBRARY_TIMEOUT` | 只把連線階段的逾時歸成 `LIBRARY_TIMEOUT`,讀本文時的 `ReadTimeout` 在 `try` 外原樣往上拋;或把讀到一半停住當成連線中斷,歸成 `LIBRARY_UNREACHABLE` | NFR-001、FR-006、邊界情況 | — | — |
| US2-LIB-15 | 可靠性(整個請求的期限) | 🔴🟢 行為測試 | `ModelLibrary` › `get_manifest` | 本機 socket 伺服器送出 `HTTP/1.1 200 OK`、`Content-Length: 2000` 後,每 0.2 秒送 1 位元組(每次讀取的間隔都短於 0.5 秒,送完整個本文要 400 秒);`request_timeout=0.5` | 呼叫 `get_manifest("qwen2.5", "7b")`,從呼叫開始計時 | 則1:呼叫後 0.5 到 0.8 秒之間丟出 `AdapterError`<br>則2:該 `AdapterError` 的 `code` 為 `LIBRARY_TIMEOUT` | 只設 httpx 的 `Timeout`,沒有用 `asyncio.timeout` 包住整個請求,每次讀取都沒逾時,請求遠超過 0.5 秒;或 `asyncio.timeout` 只包住送出請求,沒包住讀完本文;或 `asyncio.timeout` 到期時丟出的 `TimeoutError` 沒接住,原樣往上拋 | NFR-001、FR-006 | — | — |
| US2-LIB-16 | 可靠性(逾時對每個請求各自計算) | 🔴🟢 行為測試 | `ModelLibrary` › `get_manifest` → `ModelLibrary` › `get_manifest` | 本機 socket 伺服器依路徑回應:`/v2/library/qwen2.5/manifests/7b` 回 200 與 `manifest-qwen2.5-7b.json` 全文,分 4 段送、每段間隔 0.1 秒(約 0.3 秒送完);`…/14b` 接受連線後一個位元組都不送;兩次呼叫用同一個 `ModelLibrary(registry_base_url=…, request_timeout=0.5)` | 依序呼叫 `get_manifest("qwen2.5", "7b")`、`get_manifest("qwen2.5", "14b")`,每次從自己被呼叫時開始計時 | 則1:`7b` 回傳 `{"sizeBytes": 4683087332}`<br>則2:`14b` 在被呼叫後 0.5 到 0.8 秒之間丟出 `AdapterError`<br>則3:`14b` 的 `code` 為 `LIBRARY_TIMEOUT` | 整體期限掛在 `ModelLibrary` 實例或共用的 client 上,從第一次呼叫開始算,第二個請求只剩約 0.2 秒就逾時;或依序取多個 manifest 時把它們合計在同一個時限裡 | NFR-001 | — | — |

### 3.2 E2 後端 UI API(FastAPI REST)

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US2-API-01 | `/api/downloads` › 試算 | `downloadable(fakes)`、`open_ready` 讓工作階段就緒,佇列是空的;`fakes.model_library.get_manifest.when(name="qwen2.5", tag="7b").raises("LIBRARY_UNREACHABLE", "ConnectError: [Errno -2] Name or service not known")`,其他版本照 `set_library` 回大小 | 送 `POST /api/downloads/estimate`,`models` 為 `["qwen2.5:0.5b", "qwen2.5:7b"]` | 則1:回 502,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:本文的 `model` 為 `qwen2.5:7b`<br>則3:本文沒有 `totalBytes` 欄位 | `_sized` 仍用只有 404、422 的 `_LIBRARY_STATUS` 查表,`KeyError` 變成 500;或 `model` 指成已取到大小的 `qwen2.5:0.5b`;或跳過取不到的模型,回只算 0.5b 的部分試算 | FR-005 |
| US2-API-02 | `/api/downloads` › 試算 | 工作階段就緒;`get_manifest.when(name="qwen2.5", tag="7b").raises("LIBRARY_TIMEOUT", "ReadTimeout: timed out")` | 試算 `["qwen2.5:7b"]`(只勾一個) | 則1:回 504,`code` 為 `LIBRARY_TIMEOUT`<br>則2:本文的 `model` 為 `qwen2.5:7b`<br>則3:本文的 `message` 等於 `cgb.domain.errors.MESSAGES["LIBRARY_TIMEOUT"]` | `MESSAGES` 沒補 `LIBRARY_TIMEOUT`,`ApiError.body()` 丟 `KeyError`、回 500;或逾時照連不到回 502;或把替身的 `ReadTimeout: timed out` 放進 `message` | FR-005、NFR-002 |
| US2-API-03 | `/api/downloads` › 試算 | 工作階段就緒;`get_manifest.when(name="qwen2.5", tag="0.5b").raises("LIBRARY_SERVER_ERROR", "HTTP 503")`,1.5b、7b 照 `set_library` 回大小 | 試算 `["qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:7b"]` | 則1:回 502,`code` 為 `LIBRARY_SERVER_ERROR`<br>則2:本文的 `model` 為 `qwen2.5:0.5b`<br>則3:`fakes.model_library.get_manifest` 一共只被呼叫 1 次 | 用 `asyncio.gather` 同時取三個 manifest,或全部取完才回第一個失敗,多送了後面兩個請求;或 `LIBRARY_SERVER_ERROR` 在對應表裡漏掉、回 500 | FR-005 |
| US2-API-04 | `/api/downloads` › 試算 | 工作階段就緒;`get_manifest.when(name="qwen2.5", tag="latest").raises("LIBRARY_BAD_RESPONSE", "manifest is not JSON")` | 試算 `["qwen2.5:0.5b", "qwen2.5"]`(第二個沒寫版本) | 則1:回 502,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則2:本文的 `model` 為 `qwen2.5:latest` | `model` 放使用者輸入的原樣 `qwen2.5`,沒補 `latest`;或沒寫版本時 `model.split(":", 1)` 丟 `ValueError`、回 500 | FR-005 |
| US2-API-05 | `/api/downloads` › 試算 | 工作階段就緒;`set_library` 只認得 0.5b、1.5b、7b,其他版本丟 `LIBRARY_NOT_FOUND` | 試算 `["qwen2.5:0.5b", "qwen2.5:999b", "qwen2.5:7b"]` | 則1:回 404,`code` 為 `LIBRARY_NOT_FOUND`<br>則2:本文的 `model` 為 `qwen2.5:999b`<br>則3:`get_manifest` 依序以 `tag="0.5b"`、`tag="999b"` 被呼叫,共 2 次,沒有 `tag="7b"` 那一次 | `model` 指成第一個或最後一個選取的模型;或遇到失敗後仍取完第三個的 manifest | FR-005 |
| US2-API-06 | `/api/downloads` › 試算 | 工作階段就緒;`get_manifest.when(name="gpt-oss", tag="120b-cloud").raises("LIBRARY_CLOUD_ONLY", "gpt-oss:120b-cloud is cloud only")` | 試算 `["qwen2.5:0.5b", "gpt-oss:120b-cloud"]` | 則1:回 422,`code` 為 `LIBRARY_CLOUD_ONLY`<br>則2:本文的 `model` 為 `gpt-oss:120b-cloud`<br>則3:本文的 `message` 等於 `MESSAGES["LIBRARY_CLOUD_ONLY"]` | 改成共用的 `LIBRARY_STATUS` 時漏了 `LIBRARY_CLOUD_ONLY`,退回預設 502;或 `library_error` 沒把 `model` 傳進 `ApiError`,本文少了 `model` | FR-005、NFR-002 |
| US2-API-07 | `/api/downloads` › 加入 → `/api/downloads` › 列出 | 工作階段就緒,佇列是空的;`set_library` 只認得 0.5b、1.5b、7b;`fakes.remote_ollama.pull_model` 每一筆都停在閘門前(加入了就看得到下載中或排隊中) | 送 `POST /api/downloads`,`models` 為 `["qwen2.5:0.5b", "qwen2.5:999b", "qwen2.5:7b"]`,之後 `GET /api/downloads` | 則1:加入回 404,`code` 為 `LIBRARY_NOT_FOUND`<br>則2:加入的本文 `model` 為 `qwen2.5:999b`<br>則3:`GET /api/downloads` 的 `jobs` 是空陣列<br>則4:`get_manifest` 沒有以 `tag="7b"` 被呼叫<br>則5:`pull_model` 被呼叫 0 次 | 每取到一個 manifest 就寫進佇列,第一個 `qwen2.5:0.5b` 留在佇列並開始下載;或失敗後仍取完第三個 | FR-005 |
| US2-API-08 | `/api/downloads` › 加入 → `/api/downloads` › 列出 | 工作階段就緒,佇列是空的;`get_manifest.when(name="gpt-oss", tag="120b-cloud").raises("LIBRARY_CLOUD_ONLY", "cloud only")`;`pull_model` 停在閘門前 | 加入 `["qwen2.5:7b", "gpt-oss:120b-cloud"]`,之後 `GET /api/downloads` | 則1:加入回 422,`code` 為 `LIBRARY_CLOUD_ONLY`<br>則2:加入的本文 `model` 為 `gpt-oss:120b-cloud`<br>則3:`GET /api/downloads` 的 `jobs` 是空陣列 | 7b 先寫進佇列,遇到雲端版本才停,沒有撤掉;或 `LIBRARY_CLOUD_ONLY` 回 502 | FR-005 |
| US2-API-09 | `/api/downloads` › 加入 → `/api/downloads` › 列出 | 工作階段就緒,佇列是空的;`get_manifest.when(name="qwen2.5", tag="7b").raises("LIBRARY_UNREACHABLE", "ConnectError: connection refused")`;`pull_model` 停在閘門前 | 加入 `["qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:7b"]`(第三個取不到),之後 `GET /api/downloads` | 則1:加入回 502,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:加入的本文 `model` 為 `qwen2.5:7b`<br>則3:`GET /api/downloads` 的 `jobs` 是空陣列 | 前兩個取到大小就寫進 SQLite,第三個失敗時沒有回滾,佇列留下 0.5b 與 1.5b;或 `LIBRARY_UNREACHABLE` 查表 `KeyError`、回 500 | FR-005 |
| US2-API-10 | `/api/downloads` › 加入 → `/api/downloads` › 列出 | 工作階段就緒,佇列是空的;`get_manifest.when(name="qwen2.5", tag="7b").raises("LIBRARY_TIMEOUT", "ReadTimeout: timed out")`;`pull_model` 停在閘門前 | 加入 `["qwen2.5:7b"]`,之後 `GET /api/downloads` | 則1:加入回 504,`code` 為 `LIBRARY_TIMEOUT`<br>則2:加入的本文 `model` 為 `qwen2.5:7b`<br>則3:加入的本文 `message` 等於 `MESSAGES["LIBRARY_TIMEOUT"]`<br>則4:`GET /api/downloads` 的 `jobs` 是空陣列 | 加入的錯誤處理只改了試算那條路,`enqueue` 的逾時仍丟 `KeyError`、回 500;或逾時照連不到回 502 | FR-005、NFR-002 |
| US2-API-11 | `/api/downloads` › 加入 → `/api/downloads` › 列出(SSE `download.updated`) | `live_servers` 起好,工作階段就緒,已訂閱 `GET /api/events`;`get_manifest.when(name="qwen2.5", tag="1.5b").raises("LIBRARY_SERVER_ERROR", "HTTP 503")`;`pull_model` 停在閘門前 | 加入 `["qwen2.5:0.5b", "qwen2.5:1.5b"]`;0.5 秒後再加入 `["qwen2.5:7b"]`(對照組) | 則1:第一次加入回 502,`code` 為 `LIBRARY_SERVER_ERROR`<br>則2:第一次加入的本文 `model` 為 `qwen2.5:1.5b`<br>則3:第一次加入送出後到對照組送出前的 0.5 秒內,SSE 沒有收到任何 `download.updated`<br>則4:對照組送出後 1 秒內,SSE 收到 `job.model` 為 `qwen2.5:7b` 的 `download.updated` | 先 `_repo.enqueue` 並 `_publish` 0.5b、再取 1.5b 的 manifest,UI 收到一筆之後就不存在的 `download.updated` | FR-005 |
| US2-API-12 | `/api/downloads` › 加入 → `/api/downloads` › 列出 | 工作階段就緒,佇列是空的;`get_manifest.when(name="qwen2.5", tag="latest").raises("LIBRARY_BAD_RESPONSE", "manifest layers is not a list")`;`pull_model` 停在閘門前 | 加入 `["qwen2.5"]`(沒寫版本),之後 `GET /api/downloads` | 則1:加入回 502,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則2:加入的本文 `model` 為 `qwen2.5:latest`<br>則3:`GET /api/downloads` 的 `jobs` 是空陣列 | `model` 放原樣的 `qwen2.5`;或沒寫版本時 `split(":", 1)` 丟 `ValueError`、回 500 | FR-005 |
| US2-API-13 | `/api/downloads` › 加入 → `/api/downloads` › 列出 → `/api/curated` › 列出 | 工作階段就緒;執行環境已有 `qwen2.5:0.5b`(`set_tags`);以 `enqueue_waiting` 讓佇列有下載中的 `qwen2.5:0.5b-instruct` 與排隊中的 `qwen2.5:7b`;精選清單有一筆 `qwen2.5:7b`(以 001 的 `POST /api/curated` 鋪陳),記下這時 `GET /api/curated` 的 `items`;`get_manifest.when(name="qwen2.5", tag="1.5b").raises("LIBRARY_UNREACHABLE", "ConnectError")` | 加入 `["qwen2.5:1.5b"]`,之後 `GET /api/downloads`、`GET /api/curated`,再放行 0.5b-instruct 的閘門 | 則1:加入回 502,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:`GET /api/downloads` 依序是 (`qwen2.5:0.5b-instruct`, `downloading`)、(`qwen2.5:7b`, `queued`)<br>則3:`GET /api/curated` 的 `items` 和失敗前記下的相同<br>則4:放行之前 `pull_model` 只被呼叫過 1 次,`model` 為 `qwen2.5:0.5b-instruct`<br>則5:放行後 2 秒內 `qwen2.5:0.5b-instruct` 的 `state` 變成 `completed` | 模型庫失敗時把整個佇列清掉,或把下載中那一筆標成 `failed`;或失敗後暫停背景下載,下載中那一筆完成不了;或精選清單依模型庫的結果被過濾 | 邊界情況 |

#### 非功能案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| US2-API-14 | 安全(錯誤本文不外流) | 🔴🟢 行為測試 | `/api/downloads` › 試算 | 工作階段就緒;`get_manifest.when(name="qwen2.5", tag="7b").raises("LIBRARY_SERVER_ERROR", "Server error '503 Service Unavailable' for url 'https://registry.ollama.ai/v2/library/qwen2.5/manifests/7b' Traceback (most recent call last)")` | 試算 `["qwen2.5:7b"]` | 則1:回 502,`code` 為 `LIBRARY_SERVER_ERROR`<br>則2:回應本文的原文不含 `registry.ollama.ai`<br>則3:回應本文的原文不含 `Traceback`<br>則4:本文的鍵只有 `code`、`message`、`model`<br>則5:`message` 等於 `MESSAGES["LIBRARY_SERVER_ERROR"]` | 把 `AdapterError.message` 或 `str(error)` 放進 `message`;或另外帶 `detail` 欄位放底層例外的文字 | NFR-002、FR-005 | — | — |
| US2-API-15 | 一致性(固定訊息表) | 🔴🟢 行為測試 | `/api/downloads` › 加入 | 工作階段就緒,佇列是空的;對 `LIBRARY_NOT_FOUND`、`LIBRARY_CLOUD_ONLY`、`LIBRARY_UNREACHABLE`、`LIBRARY_SERVER_ERROR`、`LIBRARY_BAD_RESPONSE`、`LIBRARY_TIMEOUT` 每一個代碼,替身對 7b 丟這個代碼並帶 `"failed A https://registry.ollama.ai/a"`,對 1.5b 丟同一個代碼並帶 `"failed B https://registry.ollama.ai/b"` | 每一個代碼各加入 `["qwen2.5:7b"]` 一次、`["qwen2.5:1.5b"]` 一次 | 則1:每一個代碼兩次回應的 `message` 完全相同<br>則2:每一個 `message` 至少含一個中日韓統一表意文字(U+4E00 到 U+9FFF)<br>則3:`LIBRARY_UNREACHABLE`、`LIBRARY_TIMEOUT`、`LIBRARY_SERVER_ERROR`、`LIBRARY_BAD_RESPONSE` 的 `message` 含「從精選清單挑選或直接輸入名稱」 | 訊息用 f-string 嵌入模型名稱或替身的英文說明,同一個代碼兩次不一樣;或新加的 `LIBRARY_TIMEOUT` 說明沒寫退路 | NFR-002 | — | — |

### 3.3 跨端點驗收

真的 E2 接真的 `ModelLibrary`,只把 registry 換成 `httpx.MockTransport`(plan.md Q4);工作階段就緒用 E2 的替身鋪陳;在 3.1、3.2 都完成後才開始。

#### 功能案例

| ID | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 |
|---|---|---|---|---|---|---|
| US2-AJ-01 | `/api/downloads` › 試算 | `make_app(model_library=ModelLibrary(transport=httpx.MockTransport(handler), request_timeout=0.5))`,`downloadable(fakes)`、`open_ready` 讓工作階段就緒;handler 對 `qwen2.5:7b` 的 manifest 依情況:A 丟 `httpx.ConnectError`、B 丟 `httpx.ReadTimeout`、C 回 503、D 回 200 但本文是 HTML、E 回 404、F 回 `manifest-qwen2.5-7b-cloud.json`(`layers` 空) | 每種情況各試算一次 `["qwen2.5:7b"]` | 則1:A 回 502,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:B 回 504,`code` 為 `LIBRARY_TIMEOUT`<br>則3:C 回 502,`code` 為 `LIBRARY_SERVER_ERROR`<br>則4:D 回 502,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則5:E 回 404,`code` 為 `LIBRARY_NOT_FOUND`<br>則6:F 回 422,`code` 為 `LIBRARY_CLOUD_ONLY`<br>則7:六次的 `model` 都是 `qwen2.5:7b`<br>則8:六次都沒有 500 | `get_manifest` 的 httpx 例外沒在轉接層攔下,穿過 `_sized` 變成 500;或 `_sized` 仍用只有兩個代碼的 `_LIBRARY_STATUS`,502、504 的代碼 `KeyError` 變成 500 | FR-004、FR-005、FR-006、SC-001 |
| US2-AJ-02 | `/api/downloads` › 加入 → `/api/downloads` › 列出 | 同 US2-AJ-01 的 app 與六種情況 | 每種情況各加入一次 `["qwen2.5:7b"]`,每次之後 `GET /api/downloads` | 則1:A 回 502,`code` 為 `LIBRARY_UNREACHABLE`<br>則2:B 回 504,`code` 為 `LIBRARY_TIMEOUT`<br>則3:C 回 502,`code` 為 `LIBRARY_SERVER_ERROR`<br>則4:D 回 502,`code` 為 `LIBRARY_BAD_RESPONSE`<br>則5:E 回 404,`code` 為 `LIBRARY_NOT_FOUND`<br>則6:F 回 422,`code` 為 `LIBRARY_CLOUD_ONLY`<br>則7:六次之後 `GET /api/downloads` 的 `jobs` 都是空陣列<br>則8:六次都沒有 500 | 加入的路徑和試算分開處理,只修了試算;或轉接層的例外在 `enqueue` 裡被別的 `except` 接走、仍把模型寫進佇列 | FR-004、FR-005、FR-006、SC-001 |
| US2-AJ-03 | `/api/downloads` › 加入 → `/api/downloads` › 列出 | 同 US2-AJ-01 的 app;handler 對 `qwen2.5:0.5b` 回 `manifest-qwen2.5-7b.json`、對 `qwen2.5:cgb-test-nonexistent` 回 404、對 `qwen2.5:7b` 回 `manifest-qwen2.5-7b.json`,並記下收到的請求 | 加入 `["qwen2.5:0.5b", "qwen2.5:cgb-test-nonexistent", "qwen2.5:7b"]`,之後 `GET /api/downloads` | 則1:加入回 404,`code` 為 `LIBRARY_NOT_FOUND`<br>則2:本文的 `model` 為 `qwen2.5:cgb-test-nonexistent`<br>則3:handler 只收到 2 個 manifest 請求,沒有 `qwen2.5:7b` 的<br>則4:`GET /api/downloads` 的 `jobs` 是空陣列 | 依序取 manifest 時遇到失敗沒有停,仍去取第三個(plan.md Q3);或第一個取到大小就先寫進佇列 | FR-005、FR-004 |

### 3.4 交給 `/tdd` 的順序

每個案例在 `tasks.md` 是一組紅燈、綠燈任務;每一節的案例都做完後,接一個重構任務。同一個故事的端點節彼此平行,跨端點驗收在端點節都完成後才開始。

1. E8 Ollama 官方模型庫:US2-LIB-01 → US2-LIB-02 → … → US2-LIB-16 → 重構
2. E2 後端 UI API:US2-API-01 → US2-API-02 → … → US2-API-15 → 重構
3. 跨端點驗收(E8、E2 完成後):US2-AJ-01 → US2-AJ-02 → US2-AJ-03 → 重構

## 4. 全域測試區

適用好幾個使用者故事的 NFR 與 SC 放在這裡。故事裡已經有案例涵蓋的,只在 4.1 彙整;沒辦法歸到單一故事的,在 4.2 寫成全域案例。

### 4.1 全域 NFR 的涵蓋彙整

| 全域需求 | 適用的故事 | 故事裡涵蓋它的案例 | 全域案例 |
|---|---|---|---|
| FR-006 傳輸層失敗同一套歸類、例外不越過轉接層 | 1、2 | US1-LIB-01~US1-LIB-03、US1-LIB-18~US1-LIB-24、US2-LIB-08~US2-LIB-15、US1-AJ-01~US1-AJ-03、US2-AJ-01、US2-AJ-02 | — |
| NFR-001 每個請求 10 秒 | 1、2 | US1-LIB-21~US1-LIB-26、US2-LIB-01、US2-LIB-13~US2-LIB-16 | G-01 |
| NFR-002 固定的繁中訊息,不帶底層文字 | 1、2 | US1-API-14~US1-API-17、US2-API-02、US2-API-06、US2-API-10、US2-API-14、US2-API-15、US1-AJ-03 | — |
| SC-001 每種失敗經 UI API 回的狀態碼與 `code` 100% 符合、沒有 500 | —(跨故事的 SC) | US1-API-01~US1-API-10、US2-API-01~US2-API-12、US1-LIB-01~US1-LIB-08、US1-LIB-13~US1-LIB-16、US2-LIB-02~US2-LIB-07、US1-AJ-01、US1-AJ-02、US2-AJ-01、US2-AJ-02 | — |
| SC-002 11 秒內收到 504 | —(跨故事的 SC) | — | G-01 |
| SC-003 正常路徑沒有退化 | —(跨故事的 SC) | — | G-02 |

### 4.2 全域案例

| ID | 品質屬性 | 驗證方式 | 受測操作 | 假如 | 當 | 則 | 要抓的錯 | 需求 | 副作用與護欄 | 判定者與樣本 |
|---|---|---|---|---|---|---|---|---|---|---|
| G-01 | 效能(逾時的上限) | 📏 量測 | `/api/library` › 搜尋 → `/api/library` › 版本清單 → `/api/downloads` › 試算 | 後端以測試行程內的 uvicorn 起在 127.0.0.1 隨機 port(`live_servers`,真的 HTTP 連線,不經 `httpx.ASGITransport`);注入真的 `ModelLibrary(ollama_base_url=…, registry_base_url=…)`,不帶 `request_timeout`(預設 10 秒),兩個位址都指到 127.0.0.1 上接受連線但永不回應的本機 socket 伺服器;另一個本機 socket 伺服器送出 200 標頭後每 0.4 秒送 1 byte;工作階段就緒(E2 的替身) | 依序送一次搜尋、一次版本清單、一次只勾 `qwen2.5:7b` 的試算,各量送出到收到回應的秒數;再把 `ollama_base_url` 指到慢慢送的伺服器,送一次搜尋 | 則1:搜尋在送出後 10 到 11 秒之間收到 504、`code` 為 `LIBRARY_TIMEOUT`<br>則2:版本清單在送出後 10 到 11 秒之間收到 504、`code` 為 `LIBRARY_TIMEOUT`<br>則3:試算在送出後 10 到 11 秒之間收到 504、`code` 為 `LIBRARY_TIMEOUT`<br>則4:慢慢送資料時的搜尋在送出後 10 到 11 秒之間收到 504、`code` 為 `LIBRARY_TIMEOUT` | 沒帶 timeout,仍是 httpx 預設的 5 秒,約 5 秒就回;或只設 httpx 每次讀取的 timeout、沒有整體期限,慢慢送資料時拖過 11 秒 | NFR-001、SC-002 | 時機:節內;只連 127.0.0.1(uvicorn 與兩個本機 socket 伺服器都綁 127.0.0.1 隨機 port),`ollama_base_url`、`registry_base_url` 以建構參數指到本機,不連 ollama.com 與 registry;資料庫是 pytest 暫存資料夾的 SQLite;Colab、通道、遠端 Ollama 用替身,不執行任何 `colab` 指令、不花 compute units;約 45 秒 | 判定者:腳本(量到的秒數和 10~11 秒比較);樣本:一次量測,每個操作各一次(未用於調整) |
| G-02 | 正確性(替身與真模型庫一致) | 📏 量測 | `ModelLibrary` › `search_library` → `ModelLibrary` › `list_model_tags` → `ModelLibrary` › `get_manifest` | 002 實作完成後,在桌機;真的 ollama.com 與 registry.ollama.ai;沿用 `tests/realrun/test_us3_lib_05.py` 的 `RecordingTransport` | 依序呼叫 `search_library(q="qwen2.5")` 第 1 頁、`search_library(q="zzzz-no-such-model")` 第 1 頁、`search_library(q="qwen2.5", page=2)`、`list_model_tags("qwen2.5")`、`get_manifest("qwen2.5", "7b")` | 則1:`qwen2.5` 第 1 頁至少 1 筆官方模型,含 `qwen2.5`<br>則2:`zzzz-no-such-model` 第 1 頁回 0 筆,沒有丟出 `AdapterError`(真頁面 0 筆時仍有 `id="searchresults"`,research.md R3 待驗證)<br>則3:`qwen2.5` 第 2 頁沒有丟出 `LIBRARY_BAD_RESPONSE`(真的第 2 頁結果是 `group grid` 結構)<br>則4:版本清單名稱不含 `cloud` 的每個版本 `sizeLabel` 都不是 null<br>則5:`qwen2.5:7b` 的 `sizeBytes` 在 4,600,000,000 到 4,800,000,000 之間(和 001 一致) | 新的格式判定在真頁面誤判:0 筆的真搜尋頁沒有 `id="searchresults"` 被當成格式不符;或真的第 2 頁結構不是 `group grid`,正常頁被判 `LIBRARY_BAD_RESPONSE`;或共用的狀態碼函式把正常的 200 誤判 | SC-003、FR-001、FR-002、FR-004 | 時機:節內;只送 GET,`RecordingTransport(get_only=True, max_requests=10, min_interval=1.0)` 強制總共不超過 10 個請求(這次 5 個)、間隔 1 秒、不重試、不帶 token;只在桌機跑,不碰 Tower、Pi 與共用服務,不開 Colab、0 compute units;錄下的只有狀態碼與長度,結果只寫 pytest 暫存資料夾;連不到就標無法實跑,不改用存下來的頁面 | 判定者:腳本;樣本:執行當下的 ollama.com 與 registry 一次(未用於調整) |

## 5. 需求覆蓋

範疇內的使用者故事與適用它們的全域需求,每一條需求與邊界情況都要出現在這張表;沒有案例的就標「不在範疇」,寫進第 6 節。

| 需求 | 歸屬 | E2 後端 UI API(FastAPI REST) | E8 Ollama 官方模型庫(ollama.com 與 registry.ollama.ai) | 跨端點驗收 | 全域 | 驗證方式 |
|---|---|---|---|---|---|---|
| FR-001 搜尋頁的失敗歸類 | 故事 1 | — | US1-LIB-01~US1-LIB-12、US1-LIB-21、US1-LIB-23、US1-LIB-25、US1-LIB-26 | US1-AJ-01 | G-02 | 🔴🟢、📏 量測 |
| FR-002 版本頁的失敗歸類 | 故事 1 | — | US1-LIB-13~US1-LIB-20、US1-LIB-22、US1-LIB-24 | US1-AJ-02 | G-02 | 🔴🟢、📏 量測 |
| FR-003 搜尋與版本清單的狀態碼 | 故事 1 | US1-API-01~US1-API-10、US1-API-12~US1-API-17 | — | US1-AJ-01、US1-AJ-02 | — | 🔴🟢 |
| FR-004 manifest 的失敗歸類 | 故事 2 | — | US2-LIB-01~US2-LIB-12 | US2-AJ-01~US2-AJ-03 | G-02 | 🔴🟢、📏 量測 |
| FR-005 試算與加入下載的狀態碼、`model`、整批不加入 | 故事 2 | US2-API-01~US2-API-12、US2-API-14 | — | US2-AJ-01~US2-AJ-03 | — | 🔴🟢 |
| FR-006 傳輸層失敗同一套歸類 | 全域 | — | US1-LIB-01~US1-LIB-03、US1-LIB-18~US1-LIB-24、US2-LIB-08~US2-LIB-15 | US1-AJ-01~US1-AJ-03、US2-AJ-01、US2-AJ-02 | — | 🔴🟢 |
| NFR-001 每個請求 10 秒 | 全域 | — | US1-LIB-21~US1-LIB-26、US2-LIB-01、US2-LIB-13~US2-LIB-16 | — | G-01 | 🔴🟢、📏 量測 |
| NFR-002 固定的繁中訊息 | 全域 | US1-API-14~US1-API-17、US2-API-02、US2-API-06、US2-API-10、US2-API-14、US2-API-15 | — | US1-AJ-03 | — | 🔴🟢 |
| SC-001 每種失敗 100% 符合、沒有 500 | 全域 | US1-API-01~US1-API-10、US2-API-01~US2-API-12 | US1-LIB-01~US1-LIB-08、US1-LIB-13~US1-LIB-16、US2-LIB-02~US2-LIB-07 | US1-AJ-01、US1-AJ-02、US2-AJ-01、US2-AJ-02 | — | 🔴🟢 |
| SC-002 11 秒內收到 504 | 全域 | — | — | — | G-01 | 📏 量測 |
| SC-003 正常路徑沒有退化 | 全域 | — | — | — | G-02 | 📏 量測 |
| 邊界:搜尋第 2 頁起回 303 歸 `LIBRARY_BAD_RESPONSE`,不跟著導向 | 故事 1 | — | US1-LIB-06 | — | — | 🔴🟢 |
| 邊界:搜尋頁碼超過最後一頁是 0 筆的正常結果 | 故事 1 | — | US1-LIB-10 | — | — | 🔴🟢 |
| 邊界:搜尋第 2 頁起只有社群模型是正常結果 | 故事 1 | — | US1-LIB-11 | — | G-02 | 🔴🟢、📏 量測 |
| 邊界:registry 的 404 不分模型或版本都歸 `LIBRARY_NOT_FOUND` | 故事 2 | — | US2-LIB-02 | US2-AJ-03 | — | 🔴🟢 |
| 邊界:讀回應到一半中斷歸 `LIBRARY_UNREACHABLE`,讀到一半逾時歸 `LIBRARY_TIMEOUT` | 全域 | — | US1-LIB-02、US1-LIB-19、US1-LIB-23、US1-LIB-24、US2-LIB-10、US2-LIB-12、US2-LIB-14 | US1-AJ-01 | — | 🔴🟢 |
| 邊界:版本頁部分欄位解析不出來不算格式不符 | 故事 1 | US1-API-11 | US1-LIB-17 | — | — | 🔴🟢 |
| 邊界:模型庫失敗時已下載的模型、下載中的項目與精選清單不受影響 | 全域 | US1-API-12、US1-API-13、US2-API-13 | — | — | — | 🔴🟢 |

## 6. 不在本次範疇

| 需求 | 為什麼不測 | 之後怎麼驗 |
|---|---|---|
| `INVALID_QUERY`、`INVALID_PAGE`(`searchLibrary` 的 400) | spec 假設把 UI API 的 400 輸入驗證列為範圍外;這一輪不改 | 之後處理輸入驗證的迭代補案例;現有行為靠 001 的測試回歸 |
| `INVALID_MODEL_NAME`(`listLibraryTags`、`estimateDownloads`、`enqueueDownloads` 的 400) | 同上 | 同上 |
| `INVALID_REQUEST_BODY`、`EMPTY_MODEL_LIST`(`estimateDownloads`、`enqueueDownloads` 的 400) | 同上 | 同上 |
| `MODEL_ALREADY_DOWNLOADED`、`DOWNLOAD_ALREADY_QUEUED`(`estimateDownloads`、`enqueueDownloads` 的 409) | 001 的行為,不是模型庫的錯誤,這一輪不改 | 001 的 US3-API-16 照常回歸 |
| `DISK_SPACE_INSUFFICIENT`(`enqueueDownloads` 的 409) | 同上 | 001 的 US3-API-13 照常回歸 |
| `NO_READY_SESSION`、`DISK_SPACE_UNKNOWN`(`estimateDownloads`、`enqueueDownloads` 的 503) | 同上;Colab CLI 轉接層的錯誤處理在 spec 假設列為範圍外 | 001 的 US3-API-14、US3-API-15 照常回歸 |
| `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT`(`estimateDownloads`、`enqueueDownloads` 的 502、504) | spec 假設把遠端 Ollama 轉接層的錯誤處理列為範圍外 | 之後處理遠端 Ollama 錯誤的迭代補 UI API 層的案例;轉接層由 001 的 US2-RO-01 回歸 |
| 沒有就緒的工作階段又遇到模型庫失敗時,先回哪一個(plan.md Q14) | 合約沒定先後;這一輪的案例一律先鋪好就緒的工作階段 | 之後的迭代在合約定下先後再補 |
| manifest 的 `size` 是 JSON `true`(plan.md Q11) | research.md R3 決定 manifest 判定保留不動;registry 實際不會回布林值 | 若日後改判定,另補案例 |

## 7. 待決問題

Phase 1 提出的 Q4~Q6 與端點節交回的 Q7~Q15 都已登記到 `plan.md` 的待決問題並決定(kevin-twin 代為決定,見分身決策紀錄 D15~D17、D18~D26;D27 同意交給 `/tasks` 與 G-01、G-02 的實跑);本計劃照決定寫。
