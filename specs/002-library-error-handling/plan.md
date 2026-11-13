# 系統分析規劃: 官方模型庫的錯誤處理

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Techstack**: [techstack.md](./techstack.md) | **Date**: 2026-11-13

建立在前一次迭代 [001-session-model-catalog 的 plan.md](../001-session-model-catalog/plan.md) 之上;端點編號沿用 001。

## Project Structure

### Documentation (this feature)

```text
specs/002-library-error-handling/
├── spec.md              # 輸入(specify 產出)
├── research.md          # 輸入(technical-research 產出)
├── techstack.md         # 輸入(technical-research 產出)
├── plan.md              # 本文件
└── contracts/
    ├── model-library.openapi.yaml   # S1 產出(E8 Ollama 官方模型庫,api-plan)
    └── ui.openapi.yaml              # S2 產出(E2 後端 UI API,api-plan)
```

### Source Code (repository root)

```text
src/cgb/
├── api/library.py           # E2 後端 UI API:搜尋與版本清單的路由
├── api/downloads.py         # E2 後端 UI API:試算與加入下載的路由
├── services/library.py      # 用例:搜尋與版本清單呼叫 E8,把模型庫錯誤轉成 UI API 的錯誤
├── services/downloads.py    # 用例:試算與加入下載依序取 manifest,任何一個失敗整批不加入
├── adapters/model_library.py  # E8 ollama.com 與 registry:傳輸層例外、狀態碼與逾時的歸類
├── adapters/errors.py       # 轉接層共用的 AdapterError
└── domain/
    ├── library_html.py      # 搜尋頁與版本頁的解析與格式判定(純函式)
    └── errors.py            # 錯誤代碼的繁中訊息表與 LIBRARY_* 的狀態碼對應

tests/
├── integration/             # test_model_library.py(E8 替身)、test_api_library.py、test_api_downloads.py(E2)
├── fakes/                   # adapters.py 的模型庫替身
└── realrun/                 # test_us3_lib_05.py:真的 ollama.com 與 registry 唯讀實跑(SC-003)
```

**Structure Decision**: 沿用 001 的單一 Python 專案與單一映像,這一輪不新增檔案以外的元件,也不改部署。這一輪的規格檔以 001 的同名檔為底:`model-library.openapi.yaml` 三個操作都在範圍內,整份沿用、只改這一輪定下的地方;`ui.openapi.yaml` 只收這一輪範圍內的四個操作(搜尋、版本清單、試算、加入下載)與它們用到的 components,其餘操作仍以 001 的檔為準。好處是下游的 testplan 與 tasks 只看得到這一輪改到的東西,`x-requirements` 也能指到 002 的需求編號,不會和 001 同號的 FR 混在一起。

後端分層沿用 001 的 `api → services → adapters`:`adapters/model_library.py` 把 E8 的所有失敗在 `_get` 一處歸成 `AdapterError`(不讓 httpx 的例外往上拋),`services/library.py` 與 `services/downloads.py` 以 `domain/errors.py` 的共用對應表把代碼轉成 UI API 的狀態碼與繁中訊息。

前端不改,沿用 001 的 `static/`,依 `code` 與 `message` 顯示失敗(`library-down`、`cloud-only`)。

## 分析流程規劃

> 本段排定分析的順序與每一步指派的 planner;分析由 Phase 3 照波段交給 sub agent 執行,產出寫在 Documentation 樹列的路徑。

### 端點盤點

這次需求涉及 2 個端點。每個端點視為一個獨立系統,分析的對象是它對外的介面:

| # | 端點 | 介面 | 需求出處 |
|---|---|---|---|
| E2 | 後端 UI API(FastAPI REST) | 搜尋、版本清單、試算、加入下載四個操作遇到模型庫失敗時的狀態碼、錯誤本文與訊息、指出出問題的模型、佇列不變 | FR-003、FR-005、NFR-002、SC-001、SC-002 |
| E8 | Ollama 官方模型庫(ollama.com 與 registry.ollama.ai) | 三個操作的失敗歸類:傳輸層失敗、狀態碼、回應格式不符的判定、每個請求的逾時 | FR-001、FR-002、FR-004、FR-006、NFR-001、SC-003 |

沒有列的 001 端點:E1 前端 UI(spec 假設這一輪不改 UI)、E4 資料庫(不存新的東西)、E10 檔案系統與 E11 部署與網路(沒有新的 port、掛載或環境變數),以及 spec 假設列為範圍外的 E3、E5、E6、E7、E9(分身決策紀錄 D9)。

### 分析波段

排序原則:**一個介面排在它所依賴的介面都分析完之後**;同一波裡的介面彼此不依賴,可以各開一個 sub agent 平行分析。

第三方端點的介面是對方定好的,我們只能照著接、不能改,所以它不依賴我們任何一個介面;
反過來,我們這邊碰到它的介面都要遷就它。因此**第三方端點排在最前面**,依賴它的介面往後推一波。

| Wave | 步驟 | 介面 | Planner | 平行 | 排在這一波的理由 |
|---|---|---|---|---|---|
| 1 | S1 | E8 Ollama 官方模型庫 | api-plan | — | ollama.com 與 registry 的介面已經定好,不依賴任何介面;UI API 四個操作要轉接的代碼與它們出現的條件都照它 |
| 2 | S2 | E2 後端 UI API | api-plan | — | 每個操作會收到哪些代碼、逾時怎麼算,由 S1 三個操作的失敗歸類與逾時決定 |

共 2 個 wave、2 個步驟:Wave 1 一個介面,Wave 2 一個介面。

## 待決問題

> Phase 3 每一波交回的待決問題都登記在這裡;有問題擋住下一波時,在下一波開始之前把所有還沒決定的一次問完,沒有擋住就等最後一波之後一起問。

| Q | 提出的步驟 | 問題與可選的做法 | 擋住 | 決定 |
|---|---|---|---|---|
| Q1 | S1 | E8 三個操作的 `x-requirements` 要不要含 SC-001(端點盤點把 SC-001 列在 E2):(a)保留,SC-001 原文點名「`model-library.openapi.yaml` 三個操作列出的每一種失敗」(先採用)(b)拿掉,只留端點盤點指給 E8 的需求 | — | (a)保留 SC-001(kevin-twin 代為決定,分身決策紀錄 D11) |
| Q2 | S2 | `ui.openapi.yaml` 的 `Error.code` enum 要列哪些代碼:(a)只列四個操作會回的 19 個代碼,description 註明其他操作的代碼以 001 的檔為準(先採用;四個操作的代碼與狀態碼和 001 逐一相同)(b)照 001 原樣列出全部 49 個代碼 | — | (a)只列四個操作會回的 19 個代碼(kevin-twin 代為決定,分身決策紀錄 D12) |
| Q3 | S2 | 試算與加入下載有不止一個模型取不到 manifest 時 `model` 指哪一個:(a)依選取順序逐一取,遇到第一個失敗就停,`model` 是那一個,整批不加入、不推送 `download.updated`(先採用;和 001 的 `_sized` 一致)(b)全部取完再回第一個失敗的 | — | (a)第一個失敗就停,`model` 指那一個(kevin-twin 代為決定,分身決策紀錄 D13) |
| Q4 | testplan | 要不要加跨端點驗收(真的 E2 接真的 `ModelLibrary`,ollama.com 與 registry 換成 `httpx.MockTransport`):(a)加,經 UI API 四個操作注入原生 httpx 例外與各狀態碼,斷言沒有 500(先採用;`FakeModelLibrary` 只會丟 `AdapterError`,E2 端點節測不到例外越層)(b)不加 | — | (a)加跨端點驗收(kevin-twin 代為決定,分身決策紀錄 D15) |
| Q5 | testplan | E2 鋪就緒工作階段用的 `FakeColabControl`、`FakeTunnel`、`FakeRemoteOllama` 的實跑:(a)寫無法實跑,spec 假設不開 Colab、這三個轉接層不改,真元件已在 001 的 US1-CLI-21、US1-TUN-10、US2-RO-03 實跑(先採用)(b)加一個開 Colab 的整合實跑 | — | (a)無法實跑,完成報告列為未驗證(kevin-twin 代為決定,分身決策紀錄 D16) |
| Q6 | testplan | E8 測試縮短 10 秒逾時的接縫(research.md R2 只寫「建構參數」):(a)`ModelLibrary(..., request_timeout=<秒數>)`,預設 `REQUEST_TIMEOUT_SECONDS`,同時用在 httpx `Timeout` 與 `asyncio.timeout`(先採用)(b)monkeypatch 模組常數 | — | (a)建構參數 `request_timeout`(kevin-twin 代為決定,分身決策紀錄 D17) |
| Q7 | testplan | 預設 10 秒逾時要不要真的等 10 秒驗:(a)留 US1-LIB-25 在一般 suite,其餘用 `request_timeout=0.5`,G-01 再經 UI API 量(先採用)(b)`slow` 標記(c)不測 | — | (a)(kevin-twin 代為決定,分身決策紀錄 D18) |
| Q8 | testplan | 計時案例的上界:(a)0.8 秒(逾時 0.5 加 0.3)(先採用)(b)1.0 秒(c)逾時 1.0、上界 1.3 | — | (a)(kevin-twin 代為決定,分身決策紀錄 D19) |
| Q9 | testplan | 0 筆第 1 頁、只有社群模型的第 2 頁的真結構:(a)端點節用合成頁面,真結構併進 G-02(先採用)(b)E8 節另開實跑案例 | — | (a)(kevin-twin 代為決定,分身決策紀錄 D20) |
| Q10 | testplan | `httpx.DecodingError` 不是 `TransportError`:(a)再接 `httpx.HTTPError` 兜底歸 `LIBRARY_BAD_RESPONSE`,research.md R1 與合約 `x-transport-error-rules` 之後補一句(先採用)(b)歸 `LIBRARY_UNREACHABLE`(c)照 R1 不處理 | — | (a)(kevin-twin 代為決定,分身決策紀錄 D21);R1 與合約的補句待後續處理 |
| Q11 | testplan | manifest `size` 為 JSON `true` 被放行:(a)不測,R3 判定保留不動(先採用)(b)改成 `type(size) is int` | — | (a)(kevin-twin 代為決定,分身決策紀錄 D22) |
| Q12 | testplan | `_sized` 沒把沒寫版本的名稱補 `latest`(合約有寫):(a)這一輪補,保留 US2-API-04、US2-API-12(先採用)(b)排除 | — | (a)(kevin-twin 代為決定,分身決策紀錄 D23) |
| Q13 | testplan | `LIBRARY_BAD_RESPONSE` 說明少「也」字:(a)只斷言含「從精選清單挑選或直接輸入名稱」(先採用)(b)照合約字面並改句子 | — | (a)(kevin-twin 代為決定,分身決策紀錄 D24) |
| Q14 | testplan | 沒有就緒工作階段又遇模型庫失敗的先後:(a)這一輪不測,寫進不在範疇(先採用)(b)改合約定先後 | — | (a)(kevin-twin 代為決定,分身決策紀錄 D25) |
| Q15 | testplan | 其餘測試寫法細節(精選清單鋪陳方式、已下載模型的觀察方式、SSE 用 `live_servers`、socket helper 位置、TLS 用真 socket、`message` 比對 `MESSAGES`、轉接層 message 的則不標 NFR-002、搜尋不測 404/422):(a)照各端點節先採用(先採用)(b)逐項改 | — | (a)(kevin-twin 代為決定,分身決策紀錄 D26) |
| Q16 | tasks | G-01(📏,約 45 秒,只連 127.0.0.1)的測試檔放哪、怎麼執行:(a)`tests/integration/test_002_g_01.py`,標 `@pytest.mark.realrun` 預設排除,以 `uv run pytest -m realrun tests/integration/test_002_g_01.py` 執行;不放 `tests/realrun/`,因為那裡的 autouse `_p2_budget_gate` 會帶起 session 的 `realrun` fixture,複製 Colab 授權檔並執行 `colab usage`,違反 G-01 護欄「不執行任何 `colab` 指令」(先採用)(b)放 `tests/realrun/test_002_g_01.py`,經過 `realrun` fixture(c)放進一般 suite 不排除,每次跑全部測試多約 45 秒,而且每次都會往 `measurements.md` 追加一列 | — | (a)`tests/integration/test_002_g_01.py`、標 realrun 預設排除(kevin-twin 代為決定,分身決策紀錄 D28) |
| Q17 | tasks | G-02(📏,對真的 ollama.com 與 registry 送 5 個唯讀 GET)的測試檔放哪:(a)`tests/integration/test_002_g_02.py`,標 `@pytest.mark.realrun` 預設排除,只用 `tests/realrun/helpers.py` 的 `RecordingTransport` 當護欄,不經會複製授權檔與執行 `colab usage` 的 `realrun` fixture(G-02 護欄只列了 `RecordingTransport`、不開 Colab)(先採用)(b)照 001 的 US3-LIB-05 放 `tests/realrun/test_002_g_02.py`,經過 `realrun` fixture(多跑一次 `colab usage` 與授權檔指紋,不開執行環境、0 compute units)(c)直接加進 `tests/realrun/test_us3_lib_05.py` | — | (a)`tests/integration/test_002_g_02.py`、只靠 `RecordingTransport`(kevin-twin 代為決定,分身決策紀錄 D29) |
| Q18 | tasks | 兩個故事的跨端點驗收測試檔(plan.md Source Code 樹沒有列):(a)新增 `tests/integration/test_library_cross.py`,US1-AJ 與 US2-AJ 共用一個檔,MockTransport 的 `Recorder`、`html()` 從 `tests/integration/test_model_library.py` 匯入(先採用)(b)分別寫進 `tests/integration/test_api_library.py` 與 `test_api_downloads.py`,和 E2 端點節同檔(端點節的 subagent 與主 agent 會改同一個檔) | — | (a)新增 `tests/integration/test_library_cross.py`(kevin-twin 代為決定,分身決策紀錄 D30) |
| Q19 | tasks | 現有程式已經滿足的 23 個案例(US1-LIB-09~12、US1-LIB-17、US1-API-01~03、US1-API-05、US1-API-11、US1-API-12、US1-API-14、US2-LIB-02~07、US2-API-05~08、US2-AJ-03;analysis.md 第 1 輪 A2),紅燈怎麼做得完:(a)紅燈任務先執行確認測試通過,再把實作檔暫時改成案例「要抓的錯」的第一種錯誤實作、確認斷言失敗後撤回;綠燈任務確認不需改程式碼、全部測試通過,紅燈時若其實沒通過才寫程式碼(先採用)(b)紅燈任務照原樣寫,由 implement 遇到時自行處理(c)刪掉這些案例的任務(違反 tasks 規範一個案例一組紅綠,也和 testplan 不一致) | — | (a)先確認通過、暫時改壞確認斷言失敗再撤回(kevin-twin 代為決定,分身決策紀錄 D33) |
| Q20 | testplan | testplan「測試指令」的快速層怎麼排除單支超過 1 秒的測試:專案只有 `realrun` marker(`pyproject.toml` 的 `addopts` 預設排除)與 `tests/e2e` 資料夾(Playwright、固定 port 8781、11437),沒有標慢測試的方式;2026-11-13 實測 `tests/integration` 492 個 190 秒,其中 24 支單支超過 1 秒(`test_tunnel.py` 11 支、`test_api_health.py` 4 支、`test_api_idle.py`、`test_logging.py` 各 2 支,`test_model_library.py` 的 10 秒預設逾時、`test_api_downloads.py`、`test_api_session.py`、`test_secrets.py`、`test_colab_cli.py` 各 1 支)。可選:(a)快速層跑 `tests/integration`,以 `--deselect` 逐一列出這 24 支,不改任何測試檔,現在就能執行;排除後實測 139 秒,超過 30 秒的目標(先採用)(b)在 `pyproject.toml` 註冊 `slow` marker 並標上這 24 支,快速層寫 `-m "not realrun and not slow"`,由 `/tasks` 排一個任務;時間同 (a)(c)快速層只跑這一輪的 `test_model_library.py`、`test_api_library.py`、`test_api_downloads.py`、`test_library_cross.py`,排除其中兩支超過 1 秒的,約 24 秒;但會漏掉其他測試檔 | — | (a)`tests/integration` 加 24 個 `--deselect`(使用者回覆「照你建議的做」) |
