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
└── static/                    # E1 前端 UI:新增對話頁,下載頁加 Hugging Face 搜尋、精選清單編輯與自動下載提示區

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

前端沿用 001 的 `static/` 照畫面分檔:新增對話頁與它的 `js/chat.js`,Hugging Face 搜尋、精選清單編輯與自動下載提示區加在下載頁的 `js/library.js`;共用的 API 呼叫與 SSE 訂閱照舊放在 `js/api.js`。

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
