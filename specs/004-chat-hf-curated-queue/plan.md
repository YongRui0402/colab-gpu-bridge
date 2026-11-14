# 系統分析規劃: 佇列隨工作階段清空、測試對話框、Hugging Face 模型來源與可編輯的精選清單

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Techstack**: [techstack.md](./techstack.md) | **Date**: 2026-11-14

建立在前一次迭代 [003-download-dedup-model-cache 的 plan.md](../003-download-dedup-model-cache/plan.md) 之上;端點編號照 003 沿用 001 的 [plan.md](../001-session-model-catalog/plan.md)(E1~E11),這一輪新的 Hugging Face Hub 接在後面編 E12。

## Project Structure

### Documentation (this feature)

```text
specs/004-chat-hf-curated-queue/
├── spec.md              # 輸入(specify 產出)
├── research.md          # 輸入(technical-research 產出)
├── techstack.md         # 輸入(technical-research 產出)
├── plan.md              # 本文件
├── prototype/           # S3 產出(E1 前端 UI,ui-plan)
└── contracts/
    ├── remote-ollama.openapi.yaml   # S1 產出(E7 遠端 Ollama,api-plan)
    ├── huggingface.openapi.yaml     # S2 產出(E12 Hugging Face Hub,api-plan)
    ├── ui.openapi.yaml              # S4 產出(E2 後端 UI API,api-plan)
    ├── ui-events.asyncapi.yaml      # S4 產出(E2 後端 UI API 的 SSE 事件,api-plan)
    └── store.dbml                   # S5 產出(E4 資料庫,data-plan)
```

### Source Code (repository root)

```text
src/cgb/
├── api/chat.py                # 新增:E2 對話轉送的路由(串流回 NDJSON,不記本文)
├── api/huggingface.py         # 新增:E2 Hugging Face 搜尋與展開的路由
├── api/curated.py             # E2 精選清單:新增、修改、刪除與自動下載設定
├── api/downloads.py           # E2 試算與加入下載:接受 hf.co 名稱;自動下載結果的讀取與關閉
├── services/downloads.py      # 用例:佇列隨工作階段清除(掛 SessionsRepo.listeners)、取大小依 hf.co 分流、比對不分大小寫
├── services/auto_download.py  # 新增:用例:第一次就緒時依精選清單自動排入與跳過判定
├── services/runtime_switch.py # 用例:變更類型改順序,重新載入的項目以新工作階段名稱寫入
├── services/recovery.py       # 用例:後端重新啟動時清掉不屬於接回中工作階段的項目
├── repos/                     # E4 資料庫的存取:downloads(session_name、origin auto)、curated(auto_download)、auto_download_results
├── db/schema.py               # E4 資料庫:新版 schema 與 PRAGMA user_version 0 → 1 的遷移
├── adapters/huggingface.py    # 新增:E12 Hugging Face Hub 的搜尋、tree 與 manifest
├── adapters/remote_ollama.py  # E7 遠端 Ollama:/api/chat 串流
├── ollama_compat/forward.py   # _relay 被呼叫端中斷時不留下未取回的例外(對話頁與相容端點共用,介面不變)
├── domain/model_name.py       # hf.co 名稱格式、補 latest、不分大小寫的比對鍵(純函式)
├── domain/hf_quants.py        # 新增:檔名切出量化名稱與去重(純函式)
└── static/                    # E1 前端 UI:新增對話頁,下載頁加 Hugging Face 搜尋與精選清單編輯,模型頁下載佇列上方加自動下載提示區

tests/
├── unit/                      # model_name、hf_quants
├── integration/               # E2 經 ASGI transport,E7、E12 用替身或 httpx.MockTransport
├── fakes/                     # 新增 Hugging Face 替身;遠端 Ollama 替身補 /api/chat
└── e2e/                       # 對話頁、精選清單編輯、Hugging Face 搜尋、H100 隱藏
```

**Structure Decision**: 沿用 001 的單一 Python 專案與單一映像,這一輪不新增服務、port 與掛載(分身決策紀錄 D13);Hugging Face 由容器對外連線,精選清單照舊存在掛載的 `/data` 裡的 SQLite(NFR-004)。規格檔照 003 的做法以前一次的同名檔為底、只收這一輪新增或改變的操作、事件與表:

- `remote-ollama.openapi.yaml` 以 001 的同名檔為底,只收對話 `POST /api/chat` 與下載 `POST /api/pull`(帶 hf.co 名稱);其他操作以 001、003 的檔為準。
- `huggingface.openapi.yaml` 是新檔,收搜尋、檔案清單與 manifest 三個對方的介面與失敗歸類。
- `ui.openapi.yaml` 以 001~003 的同名檔為底,只收這一輪新增或改變的操作;`ui-events.asyncapi.yaml` 以 001 的同名檔為底,只收這一輪新增或改變的事件。`x-requirements` 指 004 的需求編號。
- `store.dbml` 以 001 的同名檔為底,只收這一輪改變的表與新表,並寫出遷移的對應。
- `prototype/` 只放這一輪新增或改變的畫面,共用的樣式與假資料以 001 的 `prototype/` 為底。

後端分層沿用 001 的 `api / ollama_compat → services → (repos → db | adapters/*)`:新增的 `adapters/huggingface.py` 接 E12,逾時與錯誤歸類照 `adapters/model_library.py`;對話轉送在 `api/chat.py` 呼叫 `ollama_compat/forward.py` 的 `_relay` 與 `IdleMonitor` 的兩個方法,不經 Ollama 相容端點的路由;佇列清除掛在 `SessionsRepo.listeners` 一處,涵蓋每一種結束方式(research.md R1);自動下載掛在 `SessionLifecycle.ready_listeners`,以 `auto_download_results` 判斷是不是第一次就緒(research.md R6)。

前端沿用 001 的 `static/` 照畫面分檔:新增對話頁與它的 `js/chat.js`,Hugging Face 搜尋與精選清單編輯加在下載頁的 `js/library.js`,自動下載提示區加在模型頁下載佇列上方的 `js/models.js`(Q29、D43);共用的 API 呼叫與 SSE 訂閱照舊放在 `js/api.js`。

## 分析流程規劃

> 本段排定分析的順序與每一步指派的 planner;分析由 Phase 3 照波段交給 sub agent 執行,產出寫在 Documentation 樹列的路徑。

### 端點盤點

這次需求涉及 5 個端點。每個端點視為一個獨立系統,分析的對象是它對外的介面:

| # | 端點 | 介面 | 需求出處 |
|---|---|---|---|
| E1 | 前端 UI(瀏覽器,原生 HTML/CSS/JS) | 畫面與互動:對話頁(選模型、逐段顯示、停止、清空、耗時與速度、不能送出與中斷的呈現)、精選清單的新增修改刪除與自動下載開關、Hugging Face 搜尋區與量化版本展開、自動下載提示區、佇列清空的即時反映、類型選單隱藏 H100 | FR-001、FR-004–FR-010、FR-012–FR-017、NFR-001、NFR-003、NFR-007、SC-001、SC-005 |
| E2 | 後端 UI API(FastAPI REST 與 SSE) | 資源、操作、錯誤與狀態碼、串流回應、狀態推送事件:對話轉送、精選清單編輯與自動下載設定、Hugging Face 搜尋與展開、自動下載結果的讀取與關閉、佇列清除的推送、模型名稱格式的放寬 | FR-001–FR-016、FR-018、NFR-002、NFR-005、NFR-006、SC-001–SC-004、SC-006 |
| E4 | 資料庫(SQLite) | 資料表、欄位、關聯、唯一性與狀態約束、既有資料庫的遷移 | FR-001–FR-003、FR-010–FR-012、NFR-004、關鍵實體 |
| E7 | 遠端 Ollama(Colab 執行環境上,Ollama API) | Ollama 提供的 API:對話的串流格式與結束時的統計、下載 Hugging Face 模型的名稱與進度、失敗的判定 | FR-004、FR-005、FR-008、FR-014、FR-018、NFR-003 |
| E12 | Hugging Face Hub(huggingface.co 公開 API) | 對方提供的介面:模型搜尋與分頁、檔案清單、manifest 與大小、需要登入的判定、每個請求的逾時與失敗歸類 | FR-013–FR-016、NFR-005、SC-004 |

沒有列的 001 端點:E3 Ollama 相容端點(對話走 UI API;`_relay` 的修正是共用程式,相容端點的介面不變)、E5 Colab CLI(自動下載的剩餘空間沿用 `probe_resources`,介面不變)、E8 Ollama 官方模型庫(官方名稱的試算不變)、E6、E9、E10、E11(資料庫檔、掛載、port 與部署都不變)(分身決策紀錄 D13)。

### 分析波段

排序原則:**一個介面排在它所依賴的介面都分析完之後**;同一波裡的介面彼此不依賴,可以各開一個 sub agent 平行分析。

第三方端點的介面是對方定好的,我們只能照著接、不能改,所以它不依賴我們任何一個介面;
反過來,我們這邊碰到它的介面都要遷就它。因此**第三方端點排在最前面**,依賴它的介面往後推一波。

| Wave | 步驟 | 介面 | Planner | 平行 | 排在這一波的理由 |
|---|---|---|---|---|---|
| 1 | S1 | E7 遠端 Ollama | api-plan | ✅ 與 S2 平行 | Ollama 的 API 已經定好,不依賴任何介面;對話轉送的串流格式、結束統計與下載 hf.co 名稱都要照它 |
| 1 | S2 | E12 Hugging Face Hub | api-plan | ✅ 與 S1 平行 | Hugging Face 的公開 API 已經定好,不依賴任何介面;搜尋分頁、量化版本、大小與失敗原因都要照它 |
| 2 | S3 | E1 前端 UI | ui-plan | ✅ 與 S4 平行 | 由使用者故事推出;對話的逐段顯示、耗時與速度要照 S1 的串流格式與結束統計,搜尋結果的載入更多與量化版本要照 S2 的分頁與 manifest。前端與後端以同一份需求為準,不必等對方 |
| 2 | S4 | E2 後端 UI API | api-plan | ✅ 與 S3 平行 | 由 FR 推出;對話轉送與串流前的錯誤照 S1,Hugging Face 搜尋、展開與試算取大小的錯誤代碼照 S2 |
| 3 | S5 | E4 資料庫 | data-plan | — | 要存什麼由 S4 的資源與操作決定(下載項目的所屬工作階段與加入原因、精選的自動下載設定、自動下載結果) |

共 3 個 wave、5 個步驟:Wave 1 兩個介面平行,Wave 2 兩個介面平行,Wave 3 一個介面。

## 待決問題

> Phase 3 每一波交回的待決問題都登記在這裡;有問題擋住下一波時,在下一波開始之前把所有還沒決定的一次問完,沒有擋住就等最後一波之後一起問。

| Q | 提出的步驟 | 問題與可選的做法 | 擋住 | 決定 |
|---|---|---|---|---|
| Q1 | S2 | HF 失敗原因的代碼:A 各給 `HF_AUTH_REQUIRED`、`HF_QUANT_UNAVAILABLE`、`HF_NO_GGUF`;B 併成 `HF_BAD_RESPONSE` | S4 | A(分身決策紀錄 D15) |
| Q2 | S2 | tree 對不存在的 repo 回 401:A 併成 `HF_AUTH_REQUIRED`「需要登入、私有或不存在」;B 歸 `HF_BAD_RESPONSE` | S4 | A(D16) |
| Q3 | S2 | tree 要不要照 `Link` 翻頁:A 只讀第一頁;B 讀完 | — | A(D17) |
| Q4 | S2 | 展開版本的時間上限:A 每個請求各 10 秒;B 整個展開共用 10 秒期限(SC-004 的 11 秒) | S4 | B(D18):S2 合約 `info` 補整體期限 |
| Q5 | S2 | manifest 200 但沒有模型層:A 歸 `HF_BAD_RESPONSE` 不列出;B 照常列出 | — | A(D19) |
| Q6 | S1 | 串流開始後的 error 行:A `OLLAMA_SERVER_ERROR`;B `OLLAMA_STREAM_INTERRUPTED`;C 新代碼 | S3、S4 | A(D20) |
| Q7 | S1 | 合約的 400/500/連線逾時代碼與現有 `pull_model`、`forward` 不符:A 照合約、實作修程式;B 改合約 | S4 | A(D21) |
| Q8 | S1 | 結束行缺 `eval_count`/`eval_duration` 或為 0:A 算完成、不顯示每秒 token 數;B `OLLAMA_BAD_RESPONSE` | S3、S4 | A(D22) |
| Q9 | S1 | 對話請求帶不帶 `keep_alive: -1`:A 不帶;B 帶 | S4 | B(D23):S1 合約與 research R5 照改;是否真的覆寫待實作確認 |
| Q10 | S1 | 思考型模型的 `message.thinking`:A 不顯示;B 帶 `think: false`;C 前端也逐段顯示(可收合) | S3、S4 | C(D24) |
| Q11 | S4 | 對話串流開始後的失敗:A 本系統補最後一行錯誤物件;B 原樣轉送;C 改 SSE | S3 | A(D25) |
| Q12 | S4 | 回覆途中工作階段被結束:A `SESSION_ENDED`;B `NO_READY_SESSION` | S3 | A(D26) |
| Q13 | S4 | 遠端對對話回 400:A 502 `OLLAMA_BAD_REQUEST`;B 400 | — | A(D27) |
| Q14 | S4 | 對話前先確認模型在執行環境上:A 不先查、404 `OLLAMA_NOT_FOUND`;B 先讀清單 | — | A(D28) |
| Q15 | S4 | 自動下載切換:A 併進 `PUT /curated/{id}` 整筆取代(實作補 404、`recommendedRuntimeType`);B 專用端點 | S3 | A(D29) |
| Q16 | S4 | 自動下載時讀不到執行環境模型清單:A 視為沒有模型照常判定;B 全部跳過;C 整次不做 | S5 | A(D30) |
| Q17 | S4 | 讀不到剩餘空間的跳過原因:A 新增 `DISK_SPACE_UNKNOWN`,spec 關鍵實體補上;B 併進 `SIZE_UNAVAILABLE` | S3、S5 | A(D31):spec.md 關鍵實體已補 |
| Q18 | S4 | 自動下載全都不必排時:A 有結果、兩清單皆空,前端決定顯示;B `result` 為 null | S3、S5 | A(D32) |
| Q19 | S4 | hf.co 不能下載的狀態碼:A 422;B 403/404 | — | A(D33) |
| Q20 | S4 | 試算遇到非 GGUF repo:A 照 S2 歸 `HF_QUANT_UNAVAILABLE`、合併說明;B 從本文分出 `HF_NO_GGUF` | — | A(D34) |
| Q21 | S4 | 展開時讀不到執行環境模型清單:A `runtimeChecked` false 照常 200;B 展開失敗 | S3 | A(D35) |
| Q22 | S4 | `DownloadJob.source`:A 必填、依前綴推出不另存;B 不加 | S3、S5 | A(D36) |
| Q23 | S4 | `ModelName` 大小寫:A 前綴與官方名稱只收小寫、作者與模型照原樣;B 全放寬 | — | A(D37) |
| Q24 | S5 | 沒設自動下載時寫不寫結果列:A 寫 `target_count = 0`;B 不寫;C 改看 `session_transitions` | — | A(D38) |
| Q25 | S5 | 不分大小寫的比對要不要資料庫擋:A `lower()` 唯一索引;B 只在程式;C COLLATE NOCASE | — | A(D39):research R7 的遷移步驟照 store.dbml 補 |
| Q26 | S5 | 跳過清單:A 子表 `auto_download_items`;B JSON 欄 | — | A(D40) |
| Q27 | S5 | 沒開 `foreign_keys`:A repos 交易內自己刪;B 開 `foreign_keys=ON` | — | A(D41) |
| Q28 | S5 | 分辨新舊資料庫:A `user_version` 0 時看有沒有 `sessions`;B 先建舊版再遷移 | — | A(D42) |
| Q29 | S3 | 自動下載提示區放哪頁:A 模型頁的佇列上方、spec 用詞改;B 佇列搬到下載頁;C 兩頁都放 | — | A(D43):spec.md 已改用詞;`models.html` 沒有工作階段時的「保留著、重新開啟後會繼續下載」說明要跟著改(FR-001) |
| Q30 | S3 | 全部不必排時顯示提示區:A 不顯示;B 顯示 | — | A(D44) |
| Q31 | S3 | 修改既有 H100 精選項目的選單:A 不列 H100、加「維持目前設定」;B 列出但不能選 | — | A(D45) |
| Q32 | S3 | 精選清單顯示大小:A 不顯示;B `CuratedModel` 加大小 | — | A(D46) |
| Q33 | S3 | 自動下載判定中:A 不顯示;B 顯示「正在依精選清單排入…」 | — | B(D47):原型補判定中的狀態 |
| Q34 | testplan | 案例 ID 和 001~003 測試檔的標記撞號:A 照 003 Q7,註解 `# ---- 004 US1-API-01`、全域案例放 `tests/integration/test_004_g_NN.py`;B ID 帶迭代前綴;C 不處理 | — | A(D48) |
| Q35 | testplan | 對話轉送要不要有遠端 Ollama 的轉接層方法:A 不新增,`api/chat.py` 以 httpx 打 forward target、`_relay` 轉送,S1 `chat` 的歸類由 E2 經 `FakeOllamaServer`(真 HTTP)測,E7 只測 `pull_model`;B 新增 `RemoteOllama.chat` | — | A(D49):Source 樹 `adapters/remote_ollama.py` 的「/api/chat 串流」照此解讀,不新增方法 |
| Q36 | testplan | Hugging Face 轉接層的介面:A `HuggingFaceHub` 的 `search_models`、`list_repo_files`、`get_manifest` 加組合用的 `list_quants`(整體 10 秒期限在轉接層),E2 替身 `FakeHuggingFaceHub` 以 `create_app(huggingface=...)` 注入;B 組合放 `api/huggingface.py` | — | A(D50) |
| Q37 | testplan | 遷移測試的舊資料庫:A 改 schema 前把現行 `create_schema` 的 DDL 凍結成 `tests/fixtures/db/schema_v0.sql`;B 手寫最小舊表;C 每次從 git 取舊版 | — | A(D51) |
| Q38 | testplan | 帶真實時間的門檻(SC-002、SC-003、SC-004):A 照 003 Q9,行為測試壓到 0.3 秒內,原樣門檻另寫全域 📏 量測、標 `realrun`;B 行為測試用原樣時間、從快速層 deselect | — | A(D52) |
| Q39 | testplan | 遷移(`user_version` 0 → 1)失敗時怎麼辦?A. `create_schema` 把原例外往上丟,後端起不來;B. 記 log、照舊庫繼續啟動 | — | A,往上丟,後端起不來(D53) |
| Q40 | testplan | 舊庫已有只差大小寫的名稱,建 `lower()` 唯一索引會讓遷移失敗,怎麼辦?A. 遷移失敗、後端起不來,由使用者手動處理;B. 建索引前在同一個交易裡每組只留 id 最小的那一筆、其他刪掉,刪掉的名稱寫進日誌;C. 有衝突就不建索引,只靠程式檢查;D. 把重複的那幾筆改名 | — | B,同一個交易裡每組留 id 最小的、其他刪掉並寫進日誌(D54) |
| Q41 | testplan | `auto_download_results.target_count` 要不要加 `CHECK (target_count >= 0)`?A. 加;B. 不加 | — | A,加(D55) |
| Q42 | testplan | `pull_model` 收到 404 要歸哪個代碼?A. 歸 `OLLAMA_BAD_RESPONSE`;B. 歸 `OLLAMA_NOT_FOUND` | — | A,歸 `OLLAMA_BAD_RESPONSE`(D56) |
| Q43 | testplan | `pull_model` 串流開始前的失敗在 `await` 時丟,還是第一次迭代時丟?A. 兩者都算通過,呼叫端兩段都包住;B. 規定在 `await` 時丟 | — | A,兩者都算,呼叫端兩段都包住(D57) |
| Q44 | testplan | 各處的短逾時要從哪裡注入?A. `cgb.app.Timeouts` 加 `chat_connect`(10)、`chat_read`(300)只給對話,加 `hf_expand_deadline`(10)給展開時讀模型清單;`HuggingFaceHub(transport, base_url, request_timeout=10, expand_deadline=10)`;`pull_model` 以半截串流丟 `ReadTimeout` 驗歸類、以 `request.extensions["timeout"]` 驗設定值,真的計時留給 001 的 `D-silent`;B. 對話共用相容端點的 `forward_read`、展開不另設期限 | — | A,照建議的注入點(D58) |
| Q45 | testplan | `Content-Type: application/x-ndjson; charset=utf-8` 算不算 NDJSON?A. 只比 media type、忽略參數;B. 必須完全相等 | — | A,只比 media type(D59) |
| Q46 | testplan | `GET /api/downloads` 要不要依目前工作階段的名稱過濾?A. 不過濾;B. 依目前工作階段的名稱過濾 | — | A,不過濾(D60) |
| Q47 | testplan | 變更類型時,清除後的 `downloads.snapshot` 裡有沒有重新載入的那一筆?A. 快照是空的,接著推那一筆的 `download.updated`;B. 等重新載入的項目排入後才推快照 | — | A,快照空的,接著推那一筆(D61) |
| Q48 | testplan | 測試檔與 helper 怎麼分?A. 照各端點節節首:新檔 `tests/integration/test_api_queue_clearing.py`、`test_api_chat.py`、`test_api_auto_download.py`、`test_api_huggingface.py`、`test_huggingface.py`,`tests/unit/test_hf_quants.py`、`test_model_name.py`;新 helper `mixed_queue`、`queue_events`、`set_hf`、`curate`、`wait_auto`;`Fakes` 多一個 `huggingface`;B. 全部塞進既有檔 | — | A,照各節節首分檔(D62) |
| Q49 | testplan | Hugging Face 轉接層、替身與純函式的介面形狀怎麼統一?A. `search_models` 回 `{"items":[{"id","downloads"}],"nextCursor"}`;`list_repo_files` 回套過 `hf_quants` 規則的候選名稱 list(沒有候選丟 `HF_NO_GGUF`);`get_manifest(author=, model=, tag=)` 回 `{"sizeBytes"}`;`list_quants` 回 `[{"quant","sizeBytes"}]`;`hf_quants` 的 `quant_name(path)`、`candidates(paths)`;`model_name` 新增 `match_key`、`is_valid`、`source_of`,`with_version` 沿用;B. 另定 | — | A,照建議統一,`list_quants` 回 list(D63) |
| Q50 | testplan | 展開時某個量化版本的 manifest 回 200 但沒有模型層,怎麼辦?A. 整個展開歸 `HF_BAD_RESPONSE`;B. 只略過那一個版本,像 400 一樣(要改合約) | — | A,整個展開歸 `HF_BAD_RESPONSE`(D64) |
| Q51 | testplan | 展開整體期限的預設 10 秒,沒辦法在 0.3 秒內經公開介面斷言,怎麼驗?A. 交給 G-04 原樣量;B. 開一個唯讀屬性來斷言 | — | A,交給 G-04 原樣量(D65) |
| Q52 | testplan | 自動下載讀不到剩餘磁碟時,已經因為取不到大小或可能無法載入而跳過的項目,原因要不要改?A. 保留原本的原因,只有還沒判定的標 `DISK_SPACE_UNKNOWN`;B. 全部改標 `DISK_SPACE_UNKNOWN` | — | A,保留原本的原因(D66) |
| Q53 | testplan | `PUT /api/curated/{id}` 同時 id 不存在、本文又不合法,先回哪一個?A. 先驗本文,回 400;B. 先查 id,回 404 | — | A,先驗本文(D67) |
| Q54 | testplan | 和 004 衝突的既有測試怎麼處理?A. 前者刪掉、由 US4-API-19 取代;後者改成先開工作階段;B. 保留並標 xfail | — | A,刪掉被取代的,另一支改成先開工作階段(D68) |
| Q55 | testplan | `EMPTY_MODEL_LIST` 這一輪要不要一起做?A. 一起做;B. 照舊範圍外 | — | A,一起做(D69) |
| Q56 | testplan | `retryDownload` 的 `DOWNLOAD_NOT_FOUND`、`DOWNLOAD_NOT_RETRYABLE`、`OLLAMA_*`、`NO_READY_SESSION` 這一輪要不要補?A. 這一輪補做;B. 只做 `MODEL_ALREADY_DOWNLOADED` | — | A,這一輪補做(D70) |
| Q57 | testplan | 對話「停止」時,怎麼看出遠端的請求被斷開了?A. `FakeOllamaServer` 新增 `client_closed` 紀錄;B. 只看後端沒有留下例外 | — | A,替身記下 `client_closed`(D71) |
| Q58 | testplan | `POST /api/chat` 的 400 各情況對到哪個代碼?A. 本文壞了或不是物件 → `INVALID_REQUEST_BODY`;`model` 缺少、型別錯或格式不符 → `INVALID_MODEL_NAME`;`messages` 缺少、不是陣列或是空的 → `EMPTY_CHAT_MESSAGES`;某一則不合法 → `INVALID_CHAT_MESSAGE`;B. 缺欄位一律 `INVALID_REQUEST_BODY` | — | A,照欄位分代碼(D72) |
| Q59 | testplan | `messages` 每一則多出來的鍵(例如 `images`、`thinking`)怎麼處理?A. 只轉 `role` 與 `content`,US2-API-02 補一條則;B. 原樣轉送 | — | A,只轉 `role` 與 `content`(D73) |
| Q60 | testplan | 回覆途中工作階段被判定失聯(`lost`),要不要結束轉送(`SESSION_ENDED`)?A. 對話與 Ollama 相容端點都在失聯時結束轉送;B. 只有對話頁這樣做,相容端點不變 | — | B,只有對話頁這樣做(D74) |
| Q61 | testplan | 對話頁沿用的 `OLLAMA_*` 說明文字怎麼辦?A. 依操作分表;B. 改成兩邊都通的通用說法 | — | B,改成通用說法(D75) |
| Q62 | testplan | 照 testplan.md 交給 /tasks、實跑案例照護欄執行:A 同意,G-01~G-05 節內實跑、G-06 延後等使用者本人;B 先改再交;C G-01、G-02 也延後 | — | A(D76):G-06 這一輪延後,不實跑(要開 Colab、花 compute units,分身不能核准) |
| Q63 | tasks | 紅燈任務寫完一執行就通過(要測的程式路徑已被既有程式或更早的綠燈做到,排任務時沒標成對照組)時怎麼辦?A. 照 003 Q24 的做法反過來用:改當對照組,暫時放入「要抓的錯」確認斷言失敗後撤回,綠燈確認不需要改程式碼,完成報告記一筆(先採用);B. 每遇到一次就停下來在本表登記一題再決定 | — | A,改當對照組,完成報告記一筆(D77) |
| Q64 | tasks | US1-API-13 要驗結束時清掉自動下載結果,但精選清單的 `autoDownload`、第一次就緒時排入、`GET /api/downloads/auto-result` 與 `autoDownload.updated` 都屬於故事 3:A. 由 US1-API-13 的綠燈 T013b 只做到讓它通過的最小版本(欄位與表由故事 1 的 E4 節照 store.dbml 建,T013b 依賴 T024b),故事 3 碰到已做到的照 Q63 改當對照組(先採用);B. 把 US1-API-13 的任務移到故事 3 的 E2 節(故事 1 的 Checkpoint 就驗不到結束時清除結果);C. 回 /testplan 把 US1-API-13 改成故事 3 的案例 | — | A,T013b 只做最小版本,故事 3 碰到做過的當對照組(D78) |
| Q65 | tasks | `FakeHuggingFaceHub` 在故事 3 就要用(US3-API-01 起斷言 `get_manifest` 被呼叫 0 次、自動下載取 hf.co 大小),真的 `HuggingFaceHub` 到故事 4 的 E12 才建,`test_fake_signatures.py` 又要求每個轉接層類別都有一對:A. T072a 在 `tests/fakes/adapters.py` 照 Q49 一次寫齊四個方法的簽章並接進 `Fakes`;T072b 讓 `create_app` 接受 `huggingface=`(預設 None);T136b(US4-HF-05)建 `HuggingFaceHub` 時在 `PAIRS` 加這一對;正式的預設 `HuggingFaceHub()` 由 T186b(US4-API-01)接上(先採用);B. 故事 3 先建 `HuggingFaceHub` 的空殼讓簽章比對成立 | — | A,替身照 Q49 寫齊,T136b 建真類別時才加進 `PAIRS`(D79) |
| Q66 | tasks | 原型有幾個狀態沒有任何案例直接斷言:`prototype/index.html` 的 `ended-offline`,`library.html` 的 `no-space`、`no-session`、`not-found`,`models.html` 的 `cat-empty`(介面覆蓋要求每個狀態都有紅綠任務):A. 掛在流程最接近的案例的 ⚙,沿用 001 的畫面、不新增斷言:`ended-offline` → T029(US1-AJ-04 的綠燈照原型改說明)、`no-space`、`no-session` → T220(US4-AJ-03)、`not-found` → T223(US4-AJ-06)、`cat-empty` → T224(US4-AJ-07)(先採用);B. 回 /testplan 補案例(例如後端重新啟動判定停機期間結束時首頁的說明)再排紅綠任務 | — | A,掛在最接近的案例;介面覆蓋表那幾列標明「沿用,沒有新斷言」,完成報告列為未直接驗證(D80) |
| Q67 | S4 | (analyze 第 1 輪回修)展開量化版本(`listHfQuants`)時,讀執行環境模型清單(`Timeouts.hf_expand_deadline`)與 Hugging Face 的 tree 加所有 manifest(`HuggingFaceHub` 的 `expand_deadline`)的期限怎麼組,才讓 SC-004 的 11 秒成立(analysis.md A18)?A. 平行、同一個起點:收到展開請求時兩段同時開始,10 秒都從收到請求起算;HF 先完成時只等模型清單到同一個時間點,到期標 `runtimeChecked` false 回 200;HF 有 400 以外的失敗或到期就取消模型清單的讀取、整個展開回那一個代碼(到期 504 `HF_TIMEOUT`);B. 先 HF 後模型清單,模型清單只用 10 秒裡剩下的時間;C. 先 HF 後模型清單,各自 10 秒(最壞約 20 秒) | — | A,平行、都從收到展開請求起算 10 秒(D85):`ui.openapi.yaml` § `listHfQuants` 的時間上限照此改寫;testplan 要補「HF 先回、模型清單卡住」與「模型清單先回、HF 卡住」兩種,斷言回應在期限加餘裕之內 |
| Q68 | S4 | (analyze 第 1 輪回修)自動下載提示區被跳過的項目要不要顯示大小、剩餘空間與顯示記憶體(analysis.md A22)?A. `AutoDownloadSkipped` 加選填 `sizeBytes`、`freeDiskBytes`、`vramBytes`,`auto_download_items` 加三欄,原型的數字照留;B. 不顯示數字,原型只顯示原因與固定說明 | S5 | A,加三個選填欄位(D86):`ui.openapi.yaml` § `AutoDownloadSkipped`、`store.dbml` § `auto_download_items` 照改;testplan 要補三個欄位在各原因下有值或為 null 的則 |
| Q69 | S4 | (analyze 第 1 輪回修)搜尋、展開、試算、加入收到本來不會出現的 `HF_*` 代碼(例如搜尋收到 `HF_NO_GGUF`)時回什麼狀態碼(analysis.md A24)?A. `info.x-hf-error-status` 一張固定對應(502:`HF_UNREACHABLE`、`HF_SERVER_ERROR`、`HF_BAD_RESPONSE`;504:`HF_TIMEOUT`;422:`HF_AUTH_REQUIRED`、`HF_NO_GGUF`、`HF_QUANT_UNAVAILABLE`),代碼與訊息照原樣;B. 一律改歸 502 `HF_BAD_RESPONSE` | — | A,四個操作共用一張對應(D87):`ui.openapi.yaml` § `info.x-hf-error-status`;US4-API-31 照現狀即可,可補一條則斷言狀態碼照表 |
| Q70 | testplan | (analyze 第 1 輪回修)US3-AJ-08 要在同一個自動下載提示看到四種跳過原因,但 `info.x-auto-download` (3)(d)(e) 的讀不到剩餘磁碟與空間不足在同一次判定裡互斥(analysis.md A8):A. 兩個工作階段各鋪一次,第一次讀得到磁碟(取不到大小、可能無法載入、空間不足),結束後第二次讓 `probe_resources` 失敗(取不到大小、讀不到剩餘空間),則分兩條;B. 前端只驗三種,讀不到剩餘空間只靠 US3-API-20 | — | A,兩個工作階段各鋪一次(D100) |
| Q71 | testplan | (analyze 第 1 輪回修)testplan 7.0 的 Hugging Face 護欄寫「串列送出、不重試」,G-01 卻呼叫真的 `list_quants`(合約 `info.x-timeout`:manifest 同時最多 4 個)(analysis.md A11):A. 7.0 改成同時最多 4 個、不重試、每次最多 40 個請求,G-01 照舊;B. G-01 改成自己串列呼叫 `list_repo_files` 與 `get_manifest` | — | A,7.0 改成同時最多 4 個(D101) |
| Q72 | testplan | (analyze 第 1 輪回修)G-06 照 001 的 P9 取授權要讀桌機的 `~/.config/colab-cli/token.json`,和本專案 CLAUDE.md 的「不讀寫桌機的 `~/.config/colab-cli/`」相抵(analysis.md A38 (d)):A. G-06 寫明授權怎麼取得(照 P9 複製,或在暫存 HOME 另做一次登入)留到實跑前由使用者本人決定;B. 現在就改成在暫存 HOME 另做一次登入 | — | A,G-06 這一輪延後,授權取得方式留到實跑前由使用者本人決定(D102;分身不代核准憑證的取用) |
| Q73 | testplan | (analyze 第 1 輪回修)只補一條則或改文字的既有案例要不要另開新案例:A. 小修改在原案例,`tasks.md` 只改原任務的描述;新行為才開新案例(接各節最大編號),`tasks.md` 從 T238 起補紅綠任務;B. 一律開新案例、原案例不動 | — | A,小修改在原案例、新行為開新案例(D103) |
| Q74 | tasks | (analyze 第 1 輪回修)T013b 要用的 `curated_models.auto_download`、`auto_download_results`、`auto_download_items` 沒有任務建(analysis.md A1):A. 故事 1 的 T017b 照 `contracts/store.dbml` 一次寫出全新庫的整份 DDL,既有庫的遷移留在故事 3 的 E4 節,故事 3 只測全新庫的紅燈 T110a、T118a、T119a、T248a 改成對照組;B. 故事 1 的 E4 節另補三組案例與任務;C. 把 T013b 搬到故事 3 | — | A,T017b 建全新庫的整份 DDL,故事 3 只測全新庫的改對照組(D104;補足 Q64 的做法) |
| Q75 | implement T010b | (A 線)`requeue_interrupted()` 照字面移到背景的 `Recovery._reattach` 之後,會讓 003 的 `test_api_recovery.py::test_重啟時下載中的那筆回到排隊中_接回後重新下載且順序不變` 變紅(背景判定還沒跑完就讀佇列):A. 在 `Recovery.start()` 同步判定有沒有上一個行程留下的未結束工作階段,有才 `requeue_interrupted()`,被收回時由清除一起移除;B. 照字面放進 `_reattach`,改那支 003 測試的等待方式;C. A 的做法,另把描述改成「Recovery 啟動時」 | — | A,在 `Recovery.start()` 同步判定後才重新排隊(D107) |
| Q76 | implement T026a | (A 線)跑全部 e2e 時,001 的 `tests/e2e/test_us3_models.py::test_結束工作階段後下載中的那筆顯示失敗與原因可重新排隊_排隊中的保留_目錄沒有它`(001 US3-AJ-09)斷言結束後下載中的標失敗、排隊中的保留,和 FR-001(D7)矛盾;testplan § 2.1 只列了 integration 層的三支,漏列這支 e2e,T001b 合併後它一直是紅的:A. 照 testplan § 2.1 同樣的做法刪掉,由 US1-AJ-01、US1-AJ-02 取代,在跨端點驗收這一組 commit 一起刪,完成報告記一筆;B. 改寫斷言成清空的版本(等於複製 US1-AJ-01);C. 回 /testplan、/tasks 補一條任務再刪 | — | A,刪掉、由 US1-AJ-01、US1-AJ-02 取代(D108) |
| Q77 | implement T029b | (A 線)T029b 要把首頁結束類狀態(`ended`、`lost`、`ended-offline`)的說明照 `prototype/index.html` 改,但描述只列 `models.html`、`models.js`、`session.js`,那些說明寫死在 `src/cgb/static/index.html`:A. T029b 直接改 `index.html` 的 `ended`、`lost` 說明(`ended-offline` 在現有畫面就是 `ended` 區塊配 `RECLAIMED_BY_COLAB`,同一段涵蓋),完成報告記「描述漏列 index.html」;B. 只在 `session.js` 用程式塞文字,不碰 `index.html`;C. 停下 T029b 的首頁那一半,留給使用者 | — | A,直接改 `index.html`,完成報告記一筆(D109) |
