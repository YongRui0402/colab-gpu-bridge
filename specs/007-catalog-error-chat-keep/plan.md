# 系統分析規劃: 模型目錄讀不到時回正確的錯誤,對話紀錄保留到工作階段結束

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Techstack**: [techstack.md](./techstack.md) | **Date**: 2026-11-16

建立在前一次迭代 [006-agent-client-connect 的 plan.md](../006-agent-client-connect/plan.md) 之上;端點編號照 006 沿用 001 的 [plan.md](../001-session-model-catalog/plan.md)(E1~E12),這一輪沒有新的端點。

## Project Structure

### Documentation (this feature)

```text
specs/007-catalog-error-chat-keep/
├── spec.md              # 輸入(specify 產出)
├── research.md          # 輸入(technical-research 產出)
├── techstack.md         # 輸入(technical-research 產出)
├── plan.md              # 本文件
├── prototype/           # S2 產出(E1 前端 UI,ui-plan)
└── contracts/
    └── ui.openapi.yaml  # S1 產出(E2 後端 UI API,api-plan)
```

### Source Code (repository root)

```text
src/cgb/
├── services/catalog.py         # E2:Catalog.list() 讀 tags、ps 失敗時轉成 502/504(research R1)
├── api/connect.py              # E2:拿掉自己接 AdapterError 的那段,錯誤只在 catalog 轉一次(research R1)
└── static/
    ├── models.html、js/models.js   # E1:目錄讀不到、預先載入確認目錄失敗的說明(research R2)
    └── chat.html、js/chat.js       # E1:對話的保存、還原、清除與中斷標示;讀不到目錄的說明(research R2~R5)

tests/
├── integration/                # E2 列目錄與預先載入的 502/504(六種組合)
└── e2e/                        # 模型頁的說明;對話頁重新整理、切頁、另開分頁、工作階段結束清空
```

**Structure Decision**: 沿用 001 的單一 Python 專案與單一映像,不新增服務、掛載、環境變數與資料表。規格檔照 005、006 的做法以前一次的同名檔為底、只收這一輪改變的部分:

- `ui.openapi.yaml` 以 001 的同名檔為底(`listCatalog` 另參照 003 的同名檔),只收 `listCatalog`、`preloadModel` 與它們用到的 components;另收 `subscribeEvents` 一筆,內容照 001 原樣,只在描述寫明對話頁依 `session.updated` 清除保存的對話(FR-006,Q1);其他操作以 001~006 的檔為準。
- 原型以 004 的 `prototype/` 為底,只收模型頁與對話頁這一輪新增的狀態。
- 推送事件(`session.updated`、`models.updated`)的內容與時機不變,不另收 `ui-events.asyncapi.yaml`,以 001、005 的檔為準(research R4)。
- 對話只存在瀏覽器的 `localStorage`(research R3),它的形狀由前端那一步定,不交 data-plan;資料庫不變。

後端分層是 api → services → domain / repos / adapters:`services/catalog.py` 把遠端 Ollama 轉接層(`adapters/remote_ollama.py`,E7)的 `AdapterError` 以 `domain/errors.py` 的 `ollama_error()` 轉成 `ApiError`,三個呼叫者(`/api/models`、`/api/models/preload`、`/api/connect`)共用。

前端沿用原生 JS 分頁:對話的保存、還原與清除寫在 `js/chat.js`;共用的狀態切換仍用 `view.js` 的 `showGroupState`。

## 分析流程規劃

> 本段排定分析的順序與每一步指派的 planner;分析由 Phase 3 照波段交給 sub agent 執行,產出寫在 Documentation 樹列的路徑。

### 端點盤點

這次需求涉及 2 個端點。每個端點視為一個獨立系統,分析的對象是它對外的介面:

| # | 端點 | 介面 | 需求出處 |
|---|---|---|---|
| E1 | 前端 UI(瀏覽器,原生 HTML/CSS/JS) | 畫面與互動:模型頁讀不到目錄與預先載入確認目錄失敗時的說明、對話頁讀不到目錄時的說明、對話在瀏覽器裡的保存、還原與清除、回覆中斷的標示、工作階段結束時的清空與說明、不能保存時的說明 | FR-003、FR-004、FR-005、FR-006、FR-007、FR-008、NFR-002、NFR-003、SC-002、SC-003 |
| E2 | 後端 UI API(FastAPI REST 與 SSE) | 資源與錯誤:列出模型目錄與預先載入讀不到遠端時的狀態碼、錯誤代碼與訊息;工作階段結束時的推送 | FR-001、FR-002、FR-006、NFR-001、SC-001 |

沒有列的 001 端點:E4 資料庫(對話不寫入,NFR-002)、E7 遠端 Ollama(介面與失敗代碼照 001、003,research R1 已實測)、E11 部署與網路(沒有改動)、E3、E5、E6、E8、E9、E10、E12(與這次無關)。

### 分析波段

排序原則:**一個介面排在它所依賴的介面都分析完之後**;同一波裡的介面彼此不依賴,可以各開一個 sub agent 平行分析。

第三方端點的介面是對方定好的,我們只能照著接、不能改,所以它不依賴我們任何一個介面;
反過來,我們這邊碰到它的介面都要遷就它。因此**第三方端點排在最前面**,依賴它的介面往後推一波。

| Wave | 步驟 | 介面 | Planner | 平行 | 排在這一波的理由 |
|---|---|---|---|---|---|
| 1 | S1 | E2 後端 UI API | api-plan | ✅ 與 S2 平行 | 由 FR 推出;錯誤代碼與狀態碼是 001 合約已定的,遠端 Ollama 的失敗代碼照 001、003,不依賴本系統其他介面 |
| 1 | S2 | E1 前端 UI | ui-plan | ✅ 與 S1 平行 | 由使用者故事推出;要顯示的錯誤代碼照 001 合約、說明用後端給的訊息,工作階段結束照 001、005 的 `session.updated`,不必等 S1 |

共 1 個 wave、2 個步驟:Wave 1 兩個介面平行。

## 待決問題

> Phase 3 每一波交回的待決問題都登記在這裡;有問題擋住下一波時,在下一波開始之前把所有還沒決定的一次問完,沒有擋住就等最後一波之後一起問。

| Q | 提出的步驟 | 問題與可選的做法 | 擋住 | 決定 |
|---|---|---|---|---|
| Q1 | S1 | FR-006 是 E2 的需求出處,要對到一個操作:a 另收 `subscribeEvents`(`GET /api/events`)一筆,內容照 001 原樣,只在描述寫明對話頁依 `session.updated` 的 `state` 與 `name` 判斷清除(research R4),標 `x-requirements: [FR-006]`(先採用;Structure Decision 已照這樣改寫);b 不收,把 FR-006 從 E2 的需求出處拿掉 | — | a(分身決策紀錄 D11) |
| Q2 | S1 | `preloadModel` 的 400 和現有程式對不上:合約寫沒有 `name` 或格式不對回 400 `INVALID_MODEL_NAME`,程式缺 `name` 時回 500、格式不對時走到 404 `OLLAMA_NOT_FOUND`(001 留下的落差,不在 NFR-001 範圍):a 這一輪順手補檢查;b 規格檔照合約原樣寫,落差列進完成報告留下一輪(先採用) | — | b(D11):`preloadModel` 的 400 落差列進完成報告 |
| Q3 | S1 | `PreloadInput.name` 的名稱格式:a 用 004 放寬後的 `ModelName`(接受 `hf.co/<作者>/<模型>`,004 起目錄裡可能有 Hugging Face 的模型)(先採用);b 照字面用 001 的版本 | — | a(D11) |
| Q4 | S2 | 回覆途中離開、還沒收到任何內容的那一則怎麼標示。原型照 research R5 改成 `unavailable`,畫面是「沒有回覆:Ollama 暫時無法使用」,和 spec 使用者故事 2 驗收情境 5「這則回覆標示為中斷(和 004 使用者故事 2 驗收情境 8 的中斷標示一致),不顯示成正常完成」不一致(寫的是「沒有回覆」不是「中斷」,原因也說成 Ollama),所以不先採用:a 照原型用 `unavailable`;b 回覆途中離開的那一則(不論有沒有收到內容)都改成新的中斷狀態,標示「中斷:離開頁面時這則回覆還沒有完成」,research R5 改寫、原型的假資料不改 | — | b(D11):回覆途中離開的那一則一律改成新的中斷狀態,標示「中斷:離開頁面時這則回覆還沒有完成」;research R5 已改,原型的假資料不改,實作照這個 |
| Q5 | S2 | 保存的模型已不在目錄裡時什麼時候提示:a 一打開頁面就顯示 `chat-model-gone`,選單列出那個模型(標「已不在執行環境上」、不能選),送出鈕停用(先採用);b 照 research R5 字面,按下送出時才提示 | — | a(D11) |
| Q6 | S2 | 讀不到目錄的說明要不要顯示錯誤代碼:a 後端的 `message` 當主說明,底下小字附 `code`(先採用);b 只顯示 `message` | — | a(D11) |
| Q7 | S2 | 對話頁的按鈕文字:a 現有的「清空」改成「清除」,和 spec 驗收情境 8 的用字一致(先採用);b 沿用「清空」 | — | a(D11) |
| Q8 | S2 | 狀態總覽裡讀不到目錄的三種代碼只有一格:a 照 research R2 只用一個 `unavailable` 狀態,那一格演 `OLLAMA_UNREACHABLE`,另外兩種的訊息寫在說明文字;對話頁那一格演 `OLLAMA_BAD_RESPONSE`(先採用);b 每個代碼各開一個狀態 | — | a(D11) |
| Q9 | S2 | 審美方向:a 沿用現有 UI 與 004~006 原型的配色與排版,只加提示的排版(先採用);b 重新訂 | — | a(D11) |
| Q10 | testplan | `FakeRemoteOllama`(遠端 Ollama 轉接層)怎麼實跑:a 加 G-01(📏 量測,時機:節內):真的 `RemoteOllama` + 真的 app,通道位址分別指到沒人聽的 127.0.0.1 port、回非 JSON 的臨時 http.server、只接連線不回應的 socket,斷言列目錄與預先載入 502/502/504、沒有 500;不起 `ollama serve`、不碰 11434,標 `realrun_local` 預設排除(先採用);b 無法實跑,引用 003 G-01;c a 再加臨時 `ollama serve` 驗恢復 | — | a(分身決策紀錄 D12) |
| Q11 | testplan | research R1 要拿掉 `api/connect.py` 自己接 `AdapterError` 的那段,`GET /api/connect` 要不要回歸:a E2 節加回歸案例,三種代碼仍回同樣的 502/504 與訊息,錨點用 006 `contracts/ui.openapi.yaml` § `paths./connect.get`(先採用);b 不加,寫進不在範疇 | — | a(D12) |
| Q12 | testplan | e2e 的 `FakeColabControl`、`FakeTunnel`(Colab 執行環境與通道)與五種結束方式的實跑:a 寫「無法實跑:spec 假設這一輪不跑 colab、不花 compute units」(先採用);b 另排 Colab 實跑 | — | a(D12) |
| Q13 | testplan | `preloadModel` 確認目錄失敗時合約寫「也不推送 `models.updated`」,要不要驗:a US1-API-08 改用 `live_servers` 連著 `/api/events`,斷言送出後 1 秒內沒有 `models.updated`(先採用);b 不驗,寫進不在範疇 | — | a(分身決策紀錄 D13) |
| Q14 | testplan | Q3 的 `hf.co` 名稱要不要有專門案例:a 不另寫,只在 US1-API-08 用一個 `hf.co/...` 模型當「其他模型」,名稱格式屬 400、照 Q2 排除(先採用);b 另寫一個 `hf.co` 名稱受理的案例 | — | a(分身決策紀錄 D13) |
| Q15 | testplan | 三種代碼寫成同一個案例的三條則還是拆三個案例:a 同一個案例分三條則,訊息另拆成 US1-API-02、11、15,實作可用 `parametrize`(先採用);b 每種代碼各一個案例 | — | a(分身決策紀錄 D13) |
| Q16 | testplan | 畫面出現說明、另一個分頁結束工作階段後畫面換狀態的時限 spec 沒寫:a 照 Playwright 預設 5 秒,和 SC-003 一致;預設資料用顯示記憶體 15 GiB 與不會跳 `preload-warn` 的模型(先採用);b 另訂更短的門檻 | — | a(分身決策紀錄 D13) |
| Q17 | testplan | NFR-003「不含英文字母」怎麼判斷(後端三句說明本身有「Ollama」):a 說明比對合約原句,其餘提示文字(標題、按鈕、小字)去掉代碼與模型名稱後斷言不含 A–Z、a–z(先採用);b 整塊字串白名單比對 | — | a(分身決策紀錄 D13) |
| Q18 | testplan | US2-API-09 的隱私檢查要用不在受測操作表的 `POST /api/chat`:a 受測操作表加一列(004 合約 § `chat`),替身 `FakeOllamaServer` 寫無法實跑(007 沒改對話轉送,004 已實跑),`chat` 的錯誤碼寫進不在範疇(由 004 案例涵蓋)(先採用);b 把 US2-API-09 移到跨端點驗收 | — | a(分身決策紀錄 D13) |
| Q19 | testplan | 要讀 SSE 的 E2 案例用哪種伺服器:a 照既有慣例用測試行程內 uvicorn(`live_servers`、`start_live_servers`),端點表的工具欄補一句(先採用);b 用 ASGITransport 讀串流 | — | a(分身決策紀錄 D13) |
| Q20 | testplan | NFR-002 放在 E2 節還是只放跨端點驗收:a 兩邊都有,US2-API-09 驗後端的資料庫、日誌與 SSE(含對照組),US2-AJ-28 跑整段 SC-004(先採用);b 只放 US2-AJ | — | a(分身決策紀錄 D13) |
| Q21 | testplan | 對話頁說明區塊的「重新讀取」(`chat.html` `#reload`)受測操作表沒列:a 這一輪不用它,對話頁恢復改用重新整理或切頁,US1-AJ-11 只斷言它的文字是中文(先採用);b 補進受測操作表,加一個恢復後可以送出的案例 | — | a(分身決策紀錄 D13) |
| Q22 | testplan | 回覆途中工作階段結束:007 FR-006 與 research R4 要清空並顯示「工作階段已結束,對話已清除」(US2-AJ-14),但 004 spec FR-008 與驗收情境 8 寫「回覆途中工作階段中斷…必須保留已收到的部分並標示中斷與原因」,004 的 e2e `test_回覆途中工作階段被結束_保留已收到的內容並標示中斷`、`test_回覆途中在另一個分頁變更類型_保留已收到的內容並說明正在變更類型` 會轉紅。a 照 007 FR-006 清空,tasks 排任務改寫或刪掉那兩支 004 測試(先採用);b 保留 004 的行為,先顯示中斷幾秒後再清 | — | 待使用者本人決定(和 004 spec FR-008 矛盾,分身不代答,見分身決策紀錄「停下的矛盾」);testplan 先照 007 FR-006 寫 US2-AJ-14 |
| Q23 | testplan | Q7 把「清空」改成「清除」後,004 測試名稱與斷言用的「清空」:a tasks 一起更新 004 的相關斷言(先採用);b 不動 004 的測試 | — | a(分身決策紀錄 D13) |
| Q24 | testplan | SC-003 的 5 秒從什麼時候起算:a 從測試以 `GET /api/session` 輪詢到結束狀態(變更類型是 `name` 第一次變了)的那一刻起算,因為閒置、被收回、重連逾時沒有使用者動作可以當起點(先採用);b 從使用者按下確認起算 | — | a(分身決策紀錄 D13) |
| Q25 | testplan | 「瀏覽器不允許保存」怎麼模擬:a 用 `add_init_script` 讓 `setItem` 丟 `QuotaExceededError`、讀 `localStorage` 丟 `SecurityError`,替身寫無法實跑,真的無痕模式列進完成報告為未驗證(先採用);b 寫成 📏 人工,本人用真的無痕視窗驗(時機:整合) | — | a(分身決策紀錄 D13) |
| Q26 | testplan | 變更類型時 `#cleared-name` 與實作的狀態名稱:a US2-AJ-13 不斷言 `#cleared-name`;實作照原型的 `data-state` 名稱與 spec 原文做(`keep-*`、`chat-model-gone`、「中斷:離開頁面時這則回覆還沒有完成」),案例不用改(先採用);b 加一條則斷言 `#cleared-name`,實作另取名稱再回頭改案例 | — | a(分身決策紀錄 D13) |
