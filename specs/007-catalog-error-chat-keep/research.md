# Phase 0 Research: 模型目錄讀不到時回正確的錯誤,對話紀錄保留到工作階段結束

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-11-16

使用者指定的技術方向:

- 整體:沿用專案現有堆疊(Python 3.12 + FastAPI、原生 HTML / CSS / JS 前端),不加新套件。
- 實測:只用替身與本機瀏覽器,不連 127.0.0.1:11434、不執行 `colab`(spec.md 假設)。

每個「理由」都標出證據類型:**實測**(附量測環境)、**估算**(附依據)、**查證**(附來源)、**判斷**(推論)。探針放在 session 暫存區 `probe007/`,不進 repo:R1 的探針是暫時放進 `tests/integration/` 的一支 pytest(跑完已刪,`catalog.py` 的試改已還原);R3 的探針是一支 Playwright 腳本,臨時 `http.server` 用 port 18790,跑完已確認關閉。這一輪沒有真實資料樣本,也沒有依樣本調出來的門檻或規則,所以不分調整用與驗收用。以下「替身環境」指桌機 i5-9400F、Python 3.12、專案 `tests/conftest.py` 的替身(`FakeRemoteOllama` 等);「瀏覽器環境」指同一台桌機、Playwright 1.64.1、Chromium 156.0.8078.4(headless)。SC-001~SC-004 都在 testplan 以替身與 Playwright 重測。

---

## R1. 目錄讀不到遠端時在哪一層轉成 502/504(FR-001、FR-002、NFR-001、SC-001)

**決策**:在 `services/catalog.py` 的 `Catalog.list()` 讀 tags、ps 時接住 `AdapterError`,以 `domain/errors.py` 既有的 `ollama_error(code)` 轉成 `ApiError`(502 `OLLAMA_UNREACHABLE`、502 `OLLAMA_BAD_RESPONSE`、504 `OLLAMA_TIMEOUT`);`preload()` 先呼叫 `list()`,所以同一處就一起修到。

- **只接 tags、ps**:讀顯示記憶體(`_vram_total`)照 003 原樣,讀不到回 null,不算錯誤(spec 邊界情況)。
- **兩份清單任一失敗就整份失敗**:不回半套目錄(spec 邊界情況);照讀取順序,先失敗的那一個代碼為準。
- **預先載入**:`list()` 拋出時還沒有標成 `loading`,也還沒 `spawn`,所以不受理、不改任何模型的狀態(FR-002)。
- **`/api/connect`**:原本自己接 `AdapterError` 的 `except` 留著不會再進去;`ApiError` 照全域處理器回同一個 502/504,行為不變。實作時把那段 `except` 拿掉,讓錯誤只在一處轉換。
- **背景推送**(`publish()`、`_run_preload` 結束後):拋出的型別從 `AdapterError` 變成 `ApiError`,背景工作原本就沒有接,行為一樣;照 D2 不在這一輪範圍,列進完成報告。

**理由**:

- 實測(替身環境,暫時的 pytest 探針:工作階段就緒、目錄先讀成功一次,再讓 `list_local_models` 或 `list_loaded_models` 丟出指定代碼,各呼叫一次 `GET /api/models` 與 `POST /api/models/preload`):

| 失敗的清單 | 代碼 | 現況 列目錄 / 預先載入 | 在 `Catalog.list()` 轉換後 列目錄 / 預先載入 |
|---|---|---|---|
| tags | `OLLAMA_UNREACHABLE` | 500 / 500 | 502 / 502 |
| tags | `OLLAMA_BAD_RESPONSE` | 500 / 500 | 502 / 502 |
| tags | `OLLAMA_TIMEOUT` | 500 / 500 | 504 / 504 |
| ps | `OLLAMA_UNREACHABLE` | 500 / 500 | 502 / 502 |
| ps | `OLLAMA_BAD_RESPONSE` | 500 / 500 | 502 / 502 |
| ps | `OLLAMA_TIMEOUT` | 500 / 500 | 504 / 504 |

- 實測(同環境):轉換後的本文是 `{"code": "OLLAMA_UNREACHABLE", "message": "連不到執行環境上的 Ollama,請確認工作階段仍在運作後再試。"}` 這類,訊息取自既有的 `MESSAGES`;同時跑 `test_api_connect.py`、`test_api_models.py` 共 35 個測試全過。
- 查證(`src/cgb/adapters/remote_ollama.py` `_get_list`、`_parse_model_list`):讀兩份清單只會丟 `OLLAMA_TIMEOUT`、`OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE` 三種代碼,`OLLAMA_STATUS` 都有對應的狀態碼。
- 查證(001 `contracts/ui.openapi.yaml` § listCatalog、preloadModel;003 同檔 § listCatalog):兩個操作的 502、504 與代碼早就寫在合約裡,這一輪不改合約,只讓程式照做。
- 判斷:轉換放在服務層,`/api/models`、`/api/models/preload`、`/api/connect` 三個呼叫者都拿到同一套錯誤,不必各自接。

**考慮過的替代方案**:

- 在 `api/models.py` 的兩個路由各自接 `AdapterError`:要寫兩次,`/api/connect` 還留著第三份,三處要一起改才一致。
- 加全域的 `AdapterError` 例外處理器一律轉 502:別的轉接層(Colab、通道、模型庫)的代碼也會被吞成 502,蓋掉各操作合約定好的狀態碼。

## R2. 模型頁與對話頁收到 502/504 時的畫面(FR-003、NFR-003)

**決策**:

- **模型頁的目錄**:`models.html` 的 `catalog` 群組加一個狀態 `unavailable`(標題「執行環境上的模型」、`notice-error` 顯示後端 `Error.message`、一個「重新讀取」按鈕);`loadCatalog()` 收到 502 或 504 時清空目錄清單並顯示它,不顯示 `empty`。重新讀取成功就回到 `normal` 或 `empty`(驗收情境 5)。
- **模型頁的預先載入**:`preload()` 收到 502 或 504 時,在目錄上方蓋一個 `preload-unavailable` 提示(模型名稱 + 後端 `Error.message` + 「關閉」),目錄裡其他模型照原狀顯示(驗收情境 4)。目前 `preload()` 失敗時什麼都不顯示。
- **對話頁**:`chat.js` 的 `loadModels()` 收到 502 或 504 時不再顯示成「沒有就緒的工作階段」,改顯示同樣的說明(`chat-unavailable`),不能送出;保存的對話照常顯示(R4)。
- 說明文字一律用後端給的 `message`,前端不寫死原因;新加的標題與按鈕用繁體中文。

**理由**:

- 查證(`src/cgb/static/js/models.js` `loadCatalog()`、`preload()`):`loadCatalog()` 只處理 `ok` 與 `NO_READY_SESSION`,其他失敗時畫面停在 `loading`(「正在讀取執行環境上的模型…」),不會更新;`preload()` 不是 `ok` 時直接 `return`。
- 查證(`src/cgb/static/js/chat.js` `loadModels()`):不是 `ok` 時一律設成 `chat-no-session`,502/504 會被說成沒有工作階段。
- 查證(001 `prototype/models.html`、`src/cgb/static/models.html`):已有的 `preload-failed`、`no-session` 用的是同一種 `panel` + `notice` 排版,新狀態照抄即可。
- 判斷:對話頁的部分不是 FR-003 要求的,但它會讓保存的對話旁邊顯示錯的原因;照 D7 放在這一項一起處理,不另開研究項。

**考慮過的替代方案**:讀不到時沿用 `empty` 狀態加一行小字:畫面仍寫著「這台執行環境上還沒有模型」,正是 FR-003 不准的。

## R3. 對話存在瀏覽器的哪裡(FR-004、FR-007、NFR-002、D3)

同類產品:nextjs-ollama-llm-ui、ollama-gui(HelgeSverre)—— 對照它們把對話存在 localStorage 還是 IndexedDB,以及不開後端資料庫的做法。

**決策**:存在 `localStorage`,鍵 `cgb.chat.v1`,值是一份 JSON:`{session, model, messages, updatedAt}`(`messages` 每則 `{role, content, thinking, status, message, ms, tps}`,也就是 `chat.js` 現有的 `convo` 欄位)。

- **寫入時機**:每次 `convo` 改變(送出、每收到一段、結束、清除)就整份寫入。
- **不能保存時**:`setItem` 或啟動時的試寫丟出例外(`QuotaExceededError`、`SecurityError`)就停止保存,對話頁照 004 照常可用,顯示「這個瀏覽器無法保存對話,離開或重新整理後會消失」。
- **多分頁**:不即時同步,最後寫入的為準(spec 邊界情況);另一個分頁重新整理或重新打開時讀到最新的。
- 清除與換模型(FR-007):`removeItem`,不留空殼。

**理由**:

- 實測(瀏覽器環境,同一個 context 的兩個分頁):

| 情況 | `localStorage` | `sessionStorage` |
|---|---|---|
| 同一個分頁重新整理 | 讀得到 | 讀得到 |
| 同一個瀏覽器另開分頁 | 讀得到 | 讀不到 |
| 另一個分頁寫入時 | 這個分頁收到 `storage` 事件 | — |
| 新的 context(相當於另一個瀏覽器設定檔) | 讀不到 | — |

- 實測(同環境):50 則、每則 1,000 字(`JSON.stringify` 後 53,576 個字元)的對話,每次改最後一則再整份 `setItem`,2,000 次平均每次 0.37 ms;寫入 6M 個字元丟 `QuotaExceededError`。
- 估算(上面的實測):Ollama 每秒幾十段,每段整份寫入 0.37 ms,佔不到 2% 的時間;一般對話遠小於 5 萬字,到不了容量上限,上限只在極端長對話或瀏覽器禁止時發生,照「不能保存」處理。
- 查證(nextjs-ollama-llm-ui README):「Stores chats in localstorage for convenience. No need to run a database.」
- 查證(ollama-gui README):對話存在瀏覽器的 IndexedDB,不離開使用者的電腦。
- 判斷:`sessionStorage` 擋不住驗收情境 3(另開分頁);IndexedDB 是非同步 API,這裡只有一段對話,用不到它的索引與大容量,卻要多處理非同步寫入的先後。

**考慮過的替代方案**:

- `sessionStorage`:新分頁讀不到(實測),做不到驗收情境 3。
- IndexedDB:只存一段對話,用不到它的能力,非同步寫入在每一段都寫時要自己排序。
- 存在後端記憶體:D3 否決,也違反 NFR-002 只存在瀏覽器裡。
- 即時同步多個分頁(`storage` 事件或 `BroadcastChannel`):spec 只要求重新整理或重新打開時看到最新的,同步要處理兩邊同時送出的衝突,範圍長出去。

## R4. 保存的對話怎麼綁工作階段、什麼時候清(FR-006、SC-003、邊界情況)

**決策**:保存時記下當時的 `Session.name`;以 `session.updated` 推送(含連上時的快照)判斷要保留、還原還是清除。

1. 對話頁載入時**先不畫保存的對話**,等第一則 `session.updated` 快照:`state` 是 `ready`、`applying_tuning`、`reconnecting` 或 `ending`,且 `name` 和保存的 `session` 相同 → 還原;否則清掉保存的對話,畫空白(驗收情境 7、SC-003 的 0 則)。
2. 對話頁開著時收到 `session.updated`:`state` 是 `none`、`ended`、`open_failed`、`lost`,或 `name` 和保存的不同 → 清空畫面與保存,顯示「工作階段已結束,對話已清除」(驗收情境 6、D5);回覆途中就先停止那一則。
3. `reconnecting`、`applying_tuning` 不清(重連接回與後端重啟後 `name` 不變,spec 邊界情況);`ending` 不清,等推送到 `ended` 再清。
4. 沒有保存過、或還沒有工作階段時第一次送出:以當時快照的 `name` 記下。

**理由**:

- 查證(`src/cgb/domain/session_state.py` `session_payload`、`ACTIVE_STATES`、`TERMINAL_STATES`):`Session` 有 `name`;結束狀態是 `ended`、`open_failed`、`lost`,沒有任何工作階段時是 `none`。
- 查證(003 `contracts/ui.openapi.yaml` § listCatalog (4)、`services/runtime_switch.py`):變更執行階段類型會換一個新的工作階段名稱;同一個工作階段經過重連中又接回時名稱不變,後端重新啟動後接回同一個工作階段也一樣(003 (5))。
- 查證(005 `contracts/ui-events.asyncapi.yaml` 開頭說明):連上 `/api/events` 時先送 `session.updated` 快照,重新整理或另一個分頁連上時就有目前的工作階段;事件都是完整現況。
- 查證(004 spec SC-001、`static/js/header.js`):下載佇列已經靠同一則 `session.updated` 在 5 秒內不重新整理就清空,對話頁的 `startHeader` 已訂閱同一條推送。
- 判斷:用名稱比對同時涵蓋五種結束方式(使用者結束、閒置、被收回、重連逾時都會到結束狀態;變更類型換了名稱),不必在前端分辨結束原因;等快照再畫,避免上一個工作階段的對話閃一下。

**考慮過的替代方案**:

- 用 `Session.openedAt` 當歸屬:和名稱一樣能分辨,但 003 已經用名稱判斷「同一個工作階段」(顯示記憶體快取),兩處用同一個依據。
- 只在打開對話頁時檢查、開著時不檢查:做不到驗收情境 6 與 D5。
- 後端在工作階段結束時推一則「清除對話」事件:多一種事件與合約變更,前端從 `session.updated` 就能判斷。

## R5. 回覆途中重新整理的保存與中斷標示(FR-005、FR-008、SC-002)

**決策**:

- 回覆中的那一則照 R3 每收到一段就寫入,`status` 維持 `streaming`。
- 還原時遇到 `status` 是 `streaming` 的那一則(頁面在回覆途中離開或重新整理),不論有沒有收到內容,都改成新的中斷狀態 `left`,標示「中斷:離開頁面時這則回覆還沒有完成」(和 004 的中斷標示同一種樣式,不顯示成正常完成);改完立刻寫回。
- 還原後送出新訊息照現有的 `convo.map(({role, content}) => ...)`,把還原的每一輪(含中斷的部分回覆)一起送出,和沒有離開頁面時一樣(FR-005)。
- 送出時保存的模型已不在目錄裡:不送出,提示從目錄重新選一個模型(spec 邊界情況);選了別的模型照 FR-007 清空。

**理由**:

- 查證(`src/cgb/static/js/chat.js`):`send()` 已經把 `convo` 每一則的 `role`、`content` 都送出;中斷、停止的狀態與 `CUT` 標示都在 `convo` 的欄位裡,存下來就能照原樣畫。
- 查證(004 spec 使用者故事 2 驗收情境 8):中斷時已收到的部分保留,畫面標示中斷與原因,不顯示成正常完成。
- 實測(R3 的瀏覽器環境):每次整份寫入 0.37 ms,每段都寫,不必等 `pagehide` 才存;重新整理時最多少掉最後一段還沒到的內容。
- 判斷:`pagehide`、`beforeunload` 在手機與分頁被丟棄時不一定觸發,每段都寫比依賴離開事件可靠。

**考慮過的替代方案**:只在 `beforeunload` 或 `pagehide` 時寫入:分頁被瀏覽器丟棄或當掉時不觸發,已收到的部分會不見。

## R6. 驗收做法(SC-001、SC-002、SC-003、SC-004、NFR-002)

**決策**:

- **故事 1**:整合測試用 `FakeRemoteOllama` 的 `list_local_models`、`list_loaded_models` 分別丟三種代碼(R1 的六種組合),斷言列目錄與預先載入的狀態碼、代碼與不是 500;Playwright 打開模型頁,斷言顯示 `unavailable` 的說明、不顯示 `empty`。
- **故事 2**:Playwright 在同一個 browser context 開對話頁,替身回兩輪,依序重新整理、切到模型頁再回來、另開分頁,斷言訊息數、順序、內容;攔截下一個 `POST /api/chat` 的本文,斷言含前兩輪;以替身讓工作階段依五種方式結束,斷言 5 秒內不重新整理就清空。
- **SC-004**:跑完故事 2 後,在測試的資料庫檔(`db_path`)與日誌輸出裡搜尋測試對話用的唯一字串,出現 0 次;加一個對照組:先把同一個字串寫進日誌確認搜尋找得到。
- 不需要 `colab` 實跑,也不需要臨時 `ollama serve`。

**理由**:

- 查證(`tests/e2e/conftest.py`、`tests/e2e/test_004_us2_chat.py`):e2e 已有 Playwright 接測試行程內 uvicorn(UI 8781)與替身的做法,對話頁的串流替身也在。
- 查證(`tests/integration/test_api_models.py`):替身可以用 `.raises(code, message)` 讓指定的清單失敗,R1 探針就是這樣寫的。
- 查證(004 spec NFR-002、001 的日誌規則):日誌只記時間、模型、耗時與狀態碼;這一輪後端沒有新增寫入對話的地方。
- 判斷:搜尋 0 次的檢查容易空過(搜尋寫錯也是 0),所以要先用對照組證明找得到。

**考慮過的替代方案**:以臨時 `ollama serve` 實跑故事 2:驗的是瀏覽器保存,和遠端是不是真的 Ollama 無關,替身就夠。

## 待驗證

| 來源 | 待驗證 | 驗證方式 / 時機 | 擋計畫? |
|---|---|---|---|
| R3 | 只量了 Chromium;Firefox 的 `storage` 行為與容量沒有量 | testplan 只以 Chromium 驗;使用者用 Firefox 時列進完成報告 | 否 |
| R5 | 重新整理時最多少掉最後一段的內容,實際少多少沒有量 | 故事 2 的 Playwright 案例在回覆途中重新整理,斷言已顯示的內容都還在 | 否 |

## 修訂紀錄

2026-11-16 初版。

### 2026-11-16

- R5:回覆途中離開的那一則,從「有內容改 `interrupted`、沒內容改 `unavailable`」改成一律改成新的中斷狀態 `left`,標示「中斷:離開頁面時這則回覆還沒有完成」。原因:`unavailable` 的畫面是「沒有回覆:Ollama 暫時無法使用」,和 spec 使用者故事 2 驗收情境 5「這則回覆標示為中斷」不一致,原因也說錯(plan.md Q4、分身決策紀錄 D11)。連帶:無;原型的假資料不改,實作照這個。
