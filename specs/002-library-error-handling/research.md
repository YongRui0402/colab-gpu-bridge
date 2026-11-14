# Phase 0 Research: 官方模型庫的錯誤處理

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-11-13

使用者指定的技術方向:

- 後端:未指定;沿用 001 的堆疊(Python 3.12、FastAPI 0.162.2、httpx 0.28.1,見 001 的 techstack.md),不新增套件。
- 範圍:只動 E8 轉接層(`src/cgb/adapters/model_library.py`)與 UI API 呼叫它的兩個服務(`services/library.py`、`services/downloads.py`)和訊息表(`domain/errors.py`);不改合約、不改 UI。
- 限制:技術研究只做不連網、不花錢的探針;要連 ollama.com 或 Colab 的列為「待實跑驗證」。

每個「理由」都標出證據類型:**實測**(附量測環境)、**估算**(附依據)、**查證**(附來源)、**判斷**(推論)。探針腳本放在 session 暫存區,不進 repo;實測環境都是桌機(Ubuntu,Python 3.12.14,httpx 0.28.1,專案 `.venv`),只連 127.0.0.1 或用 `httpx.MockTransport`。正常路徑要在 SC-003 的唯讀實跑(沿用 001 的 `tests/realrun/test_us3_lib_05.py` 的護欄)重測。

樣本用途(分配表在暫存區 `樣本分配表.md`,只憑檔名寫):調整用 `search-qwen2.5-page1.html`、`search-qwen2.5-page2.html`、`tags-qwen2.5.html`、兩個 manifest;驗收用 `search-qwen2.5-single-page.html`、`tags-qwen2.5-live-2026-11.html`(R3 規則定案後才第一次打開)。

---

## R1. 傳輸層例外歸類(FR-006、FR-001、FR-002、FR-004)

**決策**:在 `ModelLibrary._get` 一個地方攔住 httpx 的例外:`httpx.TimeoutException`(含 `ConnectTimeout`、`ReadTimeout`、`WriteTimeout`、`PoolTimeout`)與整體期限的 `TimeoutError`(R2)歸 `LIBRARY_TIMEOUT`;其餘 `httpx.TransportError`(`ConnectError`、`ReadError`、`RemoteProtocolError`、`UnsupportedProtocol`、`ProxyError` 等)歸 `LIBRARY_UNREACHABLE`;兩者都以 `AdapterError` 丟出、`from None` 不帶原始例外鏈。先判斷 TimeoutException 再判斷 TransportError(前者是後者的子類別)。另外以 `httpx.HTTPError` 兜底:不是 `TransportError` 的 httpx 例外(例如回應本文解壓失敗的 `httpx.DecodingError`)有收到回應、但內容無法使用,歸 `LIBRARY_BAD_RESPONSE`(plan.md Q10)。三個 except 的順序是 TimeoutException、TransportError、HTTPError。

**理由**:

- 實測(本機 socket 製造失敗,`probe_transport.py`,client `timeout=1.0`):

| 情況 | httpx 丟出 | 是 TimeoutException | 是 TransportError | 耗時 |
|---|---|---|---|---|
| 連線被拒(關閉的 port) | `ConnectError` | 否 | 是 | 0.03 秒 |
| TLS 失敗(對純 HTTP 用 https) | `ConnectError` | 否 | 是 | 0.01 秒 |
| 回應讀到一半斷線 | `RemoteProtocolError` | 否 | 是 | 0.01 秒 |
| 連上後不回就關 | `RemoteProtocolError` | 否 | 是 | 0.01 秒 |
| 連上後一直不回 | `ReadTimeout` | 是 | 是 | 1.01 秒 |

- 實測(同一支探針印出 `__mro__`):`ConnectError`、`ReadError` → `NetworkError` → `TransportError`;`RemoteProtocolError` → `ProtocolError` → `TransportError`;四種 Timeout → `TimeoutException` → `TransportError`;`UnsupportedProtocol`、`ProxyError` 直接是 `TransportError`。所以「先 Timeout、再 TransportError」兩個 except 就涵蓋全部傳輸層失敗。
- 查證(`.venv` 的 `httpcore/_backends/anyio.py` 的 `connect_tcp` 與 `httpx/_transports/default.py` 的 `map_httpcore_exceptions`):連線階段的 `OSError` 對應成 `httpcore.ConnectError`,再對應成 `httpx.ConnectError`;DNS 失敗的 `socket.gaierror` 是 `OSError`,所以 DNS 失敗也是 `ConnectError`。原本打算用替換 `socket.getaddrinfo` 的探針實測,但替換沒有生效,那次請求真的送到了 ollama.com(違反這一輪不連網的限制,結果不採用,只留這條查證)。
- 實測(`probe_adapter.py`,MockTransport 直接丟例外):001 的三個操作遇到 `ConnectError`、`ReadTimeout`、`RemoteProtocolError` 時,原生例外原樣往上拋,沒有任何一個轉成 `AdapterError`——這就是 Q178「ollama.com 連不到時搜尋回 500」的原因。
- 實測(`probe_decoding.py`,MockTransport 回 200、`Content-Encoding: gzip`、本文 `not gzip`,httpx 0.28.1):`client.get` 丟 `httpx.DecodingError`;它的 `__mro__` 是 `DecodingError` → `RequestError` → `HTTPError`,不是 `TransportError`,所以只接 TimeoutException 與 TransportError 時它會越過轉接層(違反 FR-006),要第三個 `except httpx.HTTPError` 才接得住。
- 實測(同上):MockTransport 的 handler 丟 `httpx.ConnectError` 時,呼叫端收到的就是 `ConnectError`,所以 R5 的替身可以直接用 MockTransport 注入傳輸層失敗。

**考慮過的替代方案**:在三個操作各自 try/except:三份相同的歸類日後只改一份就不一致(spec FR-006 要求同一套規則),不採用。

## R2. 逾時(NFR-001、SC-002)

**決策**:`_get` 建 client 時帶 `timeout=httpx.Timeout(10.0)`,並把整個請求(含讀完本文)包在 `asyncio.timeout(10.0)` 裡;兩種逾時都歸 `LIBRARY_TIMEOUT`(R1)。秒數寫成模組常數 `REQUEST_TIMEOUT_SECONDS = 10.0`,測試以建構參數覆寫成小值。

**理由**:

- 實測(`probe_transport.py`):httpx 0.28.1 的 `AsyncClient()` 預設是 `Timeout(timeout=5.0)`。001 的 `_get` 沒帶 timeout,所以現在實際是 5 秒,和 `ui.openapi.yaml` 的 `x-timeout` 10 秒(Q12)不一致。
- 實測(本機每 0.4 秒送 1 byte、共 20 bytes 的伺服器,client `timeout=1.0`):請求 8.01 秒後**成功**回 200;httpx 的逾時是每個讀寫動作各自計算,不是整個請求的期限。只靠 httpx 的 timeout,慢慢送資料的對方可以讓一次請求遠超過 10 秒。
- 實測(`probe_deadline.py`,同一種伺服器):外面包 `asyncio.timeout(1.0)` 時,1.00 秒丟出 `TimeoutError`,擋得住。
- 判斷:兩層都設 10 秒,一般「完全不回」的情況由 httpx 在 10 秒擋下,慢慢送的情況由整體期限擋下;SC-002 的 11 秒(10 秒加 1 秒餘裕)兩種都達得到。

**考慮過的替代方案**:只設 httpx 的 timeout:慢慢送資料時整個請求沒有上限(實測 timeout=1 時跑了 8 秒),NFR-001 的「每一個請求 10 秒」不成立,不採用。

## R3. 搜尋頁與版本頁的狀態碼與格式判定(FR-001、FR-002、FR-004)

**決策**:

- **狀態碼**(三個操作同一套,寫在 `_get` 之後的共用函式):404 → `LIBRARY_NOT_FOUND`(只有 `listModelTags` 與 `getManifest`;搜尋頁沒有 404 的合約回應,404 歸非預期);500–599 → `LIBRARY_SERVER_ERROR`;其他非 200(含 3xx,不跟著導向)→ `LIBRARY_BAD_RESPONSE`。
- **搜尋頁格式不符**:
  1. 第 1 頁:本文不含 `id="searchresults"` → `LIBRARY_BAD_RESPONSE`。
  2. 第 2 頁起:本文 `strip()` 後不是空字串,而且找不到任何一筆結果 → `LIBRARY_BAD_RESPONSE`。一筆結果是符合 `<a\s+href="/[^"]+"\s+class="group grid` 的連結,**官方與社群模型都算**;只有社群模型的頁是 0 筆官方模型的正常結果。
  3. 本文只有空白(超過最後一頁)→ 正常,0 筆。
- **版本頁格式不符**:`parse_model_tags` 回空清單(一個 `/library/<名稱>:<版本>` 連結都沒有)→ `LIBRARY_BAD_RESPONSE`;有連結但大小解析不出來照 001 留 `None`。
- **manifest**:001 的判定(不是 JSON、`layers` 不是 list 或某層沒有整數 `size` → `LIBRARY_BAD_RESPONSE`;`layers` 空 → `LIBRARY_CLOUD_ONLY`)保留不動,只把狀態碼判定改用共用函式。

**理由**:

- 實測(`probe_adapter.py`,MockTransport):001 的 `search_library` 與 `list_model_tags` 完全不看狀態碼:503、404、303 與改版的 200 HTML 都回 `{'items': [], 'hasMore': False}` 與 `[]`——搜尋失敗被當成「沒有符合的模型」靜默吞掉,比 500 更難發現。`get_manifest` 已經會分 404、5xx、非預期與格式不符。
- 查證(`src/cgb/domain/library_html.py` 的 `parse_search_models`、`parse_model_tags` 本體):兩個函式只用正規式找連結,找不到就回空清單,不會丟例外;所以格式判定要在轉接層另外做,不能靠解析函式失敗。
- 實測(`probe_parse.py`,調整用樣本):第 1 頁樣本含 `id="searchresults"`,第 2 頁片段樣本不含(與合約 `SearchPageFragment`「沒有 `id="searchresults"`」一致),所以第 2 頁起不能用同一個條件。
- 實測(`probe_rule.py`,最終規則;驗收用樣本在規則定案後才第一次打開):

| 輸入 | 用途 | 判為格式不符 | 預期 | 結果 |
|---|---|---|---|---|
| search-qwen2.5-page1.html(第 1 頁) | 調整用 | 否 | 否 | 過 |
| search-qwen2.5-page2.html(第 2 頁) | 調整用 | 否 | 否 | 過 |
| 自造:第 2 頁只有社群模型 | 調整用 | 否 | 否 | 過 |
| 自造:第 2 頁只有空白 | 調整用 | 否 | 否 | 過 |
| 自造:第 2 頁改版(沒有 `group grid` 結構) | 調整用 | 是 | 是 | 過 |
| 自造:第 1 頁改版(沒有 `searchresults`) | 調整用 | 是 | 是 | 過 |
| 自造:第 1 頁維護中 HTML | 調整用 | 是 | 是 | 過 |
| tags-qwen2.5.html | 調整用 | 否 | 否 | 過 |
| 自造:版本頁改版 | 調整用 | 是 | 是 | 過 |
| search-qwen2.5-single-page.html | 驗收用 | 否 | 否 | 過 |
| tags-qwen2.5-live-2026-11.html(真的 ollama.com 頁面) | 驗收用 | 否 | 否 | 過 |

- 判斷:驗收用的 `search-qwen2.5-single-page.html` 檔頭註明是由 page1 人工改寫的合成資料,結構和調整用樣本同源,只能說明規則沒有背錯 page1;真的 ollama.com 搜尋頁(尤其 0 筆的第 1 頁有沒有 `id="searchresults"`、第 2 頁社群模型的連結是不是 `class="group grid`)沒有本機樣本,列進待驗證。spec 對外部服務的這兩個假設在這一輪**假設未查**(要連 ollama.com)。
- 判斷:第 2 頁只有社群模型的情況會真的發生(001 完成報告 Q208「真的搜尋第 2 頁剛好沒有官方模型」),所以「一筆結果」要把社群模型算進去;這條已轉交 specify 寫進 spec 的邊界情況(分身決策紀錄 D7)。

**考慮過的替代方案**:

- 第 2 頁起只數官方模型:只有社群模型的頁會被誤判成 `LIBRARY_BAD_RESPONSE`,UI 退到 `library-down`。
- 引入 HTML 解析套件判定結構:001 techstack 刻意不用(「自寫取代套件」),這一輪不新增套件。

## R4. UI API 的代碼與狀態碼對應(FR-003、FR-005、NFR-002)

**決策**:

- **訊息表**:`domain/errors.py` 的 `MESSAGES` 補上 `LIBRARY_TIMEOUT`(繁體中文,同其他 `LIBRARY_*` 帶「也可以從精選清單挑選或直接輸入名稱」的退路)。
- **共用對應表**:在 `domain/errors.py` 加一張 `LIBRARY_STATUS`:`LIBRARY_NOT_FOUND` 404、`LIBRARY_CLOUD_ONLY` 422、`LIBRARY_UNREACHABLE`、`LIBRARY_SERVER_ERROR`、`LIBRARY_BAD_RESPONSE` 502、`LIBRARY_TIMEOUT` 504,和一個 `library_error(code, model=None) -> ApiError`(比照既有的 `oauth_error`)。
- **服務**:`services/library.py` 的 `search()` 改用 `library_error`(現在一律 502,逾時要 504);`tags()` 補上 `except AdapterError`;`services/downloads.py` 的 `_sized()` 改用 `library_error(..., model=model)`,拿掉只有兩個代碼的 `_LIBRARY_STATUS`。
- 回給 UI 的本文只有 `code`、`message`(取自 `MESSAGES`)與 `model`;`AdapterError.message` 不進回應。

**理由**:

- 實測(`probe_services.py`,替身 state 讓 `search_library`、`list_model_tags`、`get_manifest` 丟各代碼):

| 代碼 | `Library.search` | `Library.tags` | `DownloadsService._sized` |
|---|---|---|---|
| `LIBRARY_UNREACHABLE` | 502,本文可產生 | `AdapterError` 原樣拋出(500) | `KeyError`(500) |
| `LIBRARY_TIMEOUT` | 502(應為 504),本文 `KeyError`(500) | `AdapterError`(500) | `KeyError`(500) |
| `LIBRARY_SERVER_ERROR` | 502 | `AdapterError`(500) | `KeyError`(500) |
| `LIBRARY_BAD_RESPONSE` | 502 | `AdapterError`(500) | `KeyError`(500) |
| `LIBRARY_NOT_FOUND` | 502 | `AdapterError`(500) | 404 |
| `LIBRARY_CLOUD_ONLY` | 502 | `AdapterError`(500) | 422 |

- 實測(`uv run python -c`):`MESSAGES` 裡的 `LIBRARY_*` 只有五個,沒有 `LIBRARY_TIMEOUT`;`ApiError(504, "LIBRARY_TIMEOUT").body()` 丟 `KeyError`。
- 查證(`src/cgb/api/__init__.py` 的 `api_error` 本體):`ApiError` 的處理器呼叫 `error.body()` 產生回應;`body()` 丟 `KeyError` 時不在任何 handler 裡,就是 500。
- 查證(001 `contracts/ui.openapi.yaml` 的 `searchLibrary`、`listLibraryTags`、`estimateDownloads`、`enqueueDownloads`):四個操作對 `LIBRARY_*` 的狀態碼一致(404、422、502、504),所以一張共用表就夠,不必每個操作各寫一張。
- 判斷:搜尋的合約沒有列 404 與 422;R3 的搜尋不會產生 `LIBRARY_NOT_FOUND` 與 `LIBRARY_CLOUD_ONLY`,共用表不會在搜尋回出合約沒有的狀態碼。

**考慮過的替代方案**:在 `ApiError.body()` 對缺少的代碼退回通用訊息:會把漏寫的代碼藏起來,合約有的代碼照樣沒有對應的說明;這一輪只補 `LIBRARY_TIMEOUT`,其他 13 個缺的代碼(Q203)不在範圍內。

## R5. 驗收方式:替身注入與唯讀實跑(SC-001、SC-002、SC-003)

**決策**:

- **轉接層**:沿用 001 `tests/integration/test_model_library.py` 的接縫(`ModelLibrary(transport=httpx.MockTransport(...))`);handler 回各狀態碼與改版頁,或直接 `raise httpx.ConnectError / ReadTimeout / RemoteProtocolError`。逾時的實際秒數另用 127.0.0.1 上不回應的 socket 伺服器與縮小的逾時(建構參數)量,不在測試裡等 10 秒。
- **UI API**:沿用 001 `tests/integration/test_api_library.py`、`test_api_downloads.py` 的 `fakes.model_library.<方法>.raises(code)`,對四個操作逐一代碼斷言狀態碼、`code`、`model`,並斷言佇列沒有多出項目。SC-001 的「每個組合」以參數化測試列舉(操作 × 代碼)。
- **SC-002 的 11 秒**:以真的 `ModelLibrary` 接 127.0.0.1 上不回應的伺服器、逾時用預設 10 秒,經 UI API 量一次搜尋、一次版本清單、一次只勾一個模型的試算,各自量送出到收到 504 的時間。
- **SC-003**:沿用 001 的 `tests/realrun/test_us3_lib_05.py`(`-m realrun`,只送 GET、總共不超過 10 個請求、間隔 1 秒,不開 Colab、0 compute units),在這一輪實作完成後跑一次。

**理由**:

- 查證(`tests/integration/test_model_library.py` 開頭與 `Recorder`、`registry_reply`):001 已經用 MockTransport 當 ollama.com 與 registry 的替身,不連外網。
- 查證(`tests/fakes/adapters.py` 的 `FakeMethod.raises`、`tests/integration/test_api_downloads.py` 第 424 行):UI API 層的替身已經能讓 `get_manifest` 依參數丟指定代碼。
- 實測(R1 的 `probe_transport.py`):MockTransport handler 丟的 httpx 例外會原樣到呼叫端,所以傳輸層失敗也能用同一個接縫注入。
- 查證(`tests/realrun/test_us3_lib_05.py` 檔頭):這個案例本來就是「真的 ollama.com 與 registry、0 compute units、約 1 分鐘」,正好是 SC-003 要的正常路徑檢查。
- 判斷:錯誤情境沒辦法叫真的 ollama.com 配合(分身決策紀錄 D2),只能用替身;替身驗不到的是真實頁面結構,由 SC-003 與待驗證的兩項補。

**考慮過的替代方案**:測試裡真的等 10 秒逾時:每個案例多 10 秒,SC-001 的參數化組合會讓整個 suite 多數分鐘;只在 SC-002 的三次量測用 10 秒。

## 待驗證

| 來源 | 待驗證 | 驗證方式 / 時機 | 擋計畫? |
|---|---|---|---|
| R3 | 真的 ollama.com 搜尋 0 筆時,第 1 頁仍有 `id="searchresults"`(否則會被誤判成格式不符) | 待實跑驗證:implement 後的唯讀實跑,搜尋一個不存在的關鍵字(例 `zzzz-no-such-model`)看回應 | 否 |
| R3 | 真的第 2 頁起的結果(含社群模型)是 `<a href="..." class="group grid` 結構 | 待實跑驗證:同上,翻一個有社群模型的第 2 頁 | 否 |
| R3 | SC-003:真的 ollama.com 與 registry 的正常路徑沒有退化 | 待實跑驗證:`tests/realrun/test_us3_lib_05.py`,implement 完成後 | 否 |
| R2 | 真的網路環境下 DNS 失敗與連線被拒的耗時(本機實測都在 0.03 秒內) | 不另驗;SC-002 只約束逾時 | 否 |

## 修訂紀錄

### 2026-11-13

- R1:決策從「`httpx.TimeoutException`、`httpx.TransportError` 兩個 except」改成再加第三個 `except httpx.HTTPError`,把 `httpx.DecodingError` 這類非傳輸層例外歸 `LIBRARY_BAD_RESPONSE`。原因:plan.md Q10(分身決策紀錄 D21)已這樣決定、testplan US2-LIB-08 照它斷言,但 R1 沒寫(analysis.md 第 1 輪 A1);`probe_decoding.py` 實測 `DecodingError` 不是 `TransportError`。連帶:無(R2~R5 不變;合約 `x-transport-error-rules` 由 api-plan 補同一句)。
