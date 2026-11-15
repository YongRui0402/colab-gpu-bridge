# 系統分析規劃: 依機器配置調整遠端 Ollama 的設定,並在 UI 顯示與修改

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md) | **Techstack**: [techstack.md](./techstack.md) | **Date**: 2026-11-15

建立在前一次迭代 [004-chat-hf-curated-queue 的 plan.md](../004-chat-hf-curated-queue/plan.md) 之上;端點編號照 004 沿用 001 的 [plan.md](../001-session-model-catalog/plan.md)(E1~E12),這一輪沒有新的端點。

## Project Structure

### Documentation (this feature)

```text
specs/005-ollama-machine-tuning/
├── spec.md              # 輸入(specify 產出)
├── research.md          # 輸入(technical-research 產出)
├── techstack.md         # 輸入(technical-research 產出)
├── plan.md              # 本文件
├── prototype/           # S2 產出(E1 前端 UI,ui-plan)
└── contracts/
    ├── colab-cli.openapi.yaml       # S1 產出(E5 Colab CLI,api-plan)
    ├── ui.openapi.yaml              # S3 產出(E2 後端 UI API,api-plan)
    ├── ui-events.asyncapi.yaml      # S3 產出(E2 後端 UI API 的 SSE 事件,api-plan)
    └── store.dbml                   # S4 產出(E4 資料庫,data-plan)
```

### Source Code (repository root)

```text
src/cgb/
├── adapters/scripts/start_ollama.py    # E5:啟動前量顯示記憶體與系統記憶體、依級距與 CGB_TUNE_* 組環境、寫 pid 檔、回報套用的設定
├── adapters/scripts/restart_ollama.py  # 新增:E5 停掉 ollama serve(pid 檔,備援 pkill)、以新設定啟動並驗證
├── adapters/colab_cli.py               # E5:start_ollama 帶齊 CGB_TUNE_*;新增 restart_ollama
├── domain/tuning.py                    # 新增:級距表、覆蓋值範圍檢查、「覆蓋值 > 級距 > 不帶」(純函式)
├── services/session_lifecycle.py       # 用例:開啟時帶覆蓋值、記下開啟時的 Ollama 設定
├── services/tuning.py                  # 新增:用例:套用並重啟、忙碌判斷、失敗改回自動值、依序重新載入
├── services/idle_monitor.py            # 用例:非就緒時暫停閒置倒數
├── api/session.py                      # E2:開啟時接受覆蓋值;工作階段狀態加 Ollama 設定
├── api/tuning.py                       # 新增:E2 類型覆蓋值的讀取與清除、套用並重啟
├── repos/                              # E4:runtime_type_tuning、session_tunings
├── db/schema.py                        # E4:PRAGMA user_version 1 → 2
└── static/                             # E1:開啟畫面的「Ollama 設定」區塊、工作階段頁的設定卡與套用流程

tests/
├── unit/                               # tuning 級距與範圍、遠端腳本內嵌級距表與 domain 一致
├── integration/                        # E2 經 ASGI transport,E5 用替身(不同顯示記憶體、重啟失敗)
├── fakes/                              # colab 替身補 restart_ollama 與回報的硬體
└── e2e/                                # 開啟畫面覆蓋、工作階段頁套用、擋下與改回自動
```

**Structure Decision**: 沿用 001 的單一 Python 專案與單一映像,這一輪不新增服務、port 與掛載;覆蓋值與每次套用的紀錄存在掛載的 `/data` 裡的 SQLite。規格檔照 004 的做法以前一次的同名檔為底、只收這一輪新增或改變的操作、事件與表:

- `colab-cli.openapi.yaml` 以 001 的同名檔為底,只收 `/exec/start-ollama`(新的 `--env`、結果欄位、pid 檔)與新的 `/exec/restart-ollama`;其他操作以 001 的檔為準。
- `ui.openapi.yaml`、`ui-events.asyncapi.yaml` 以 004 的同名檔為底,只收開啟工作階段的覆蓋值、工作階段狀態的 Ollama 設定、類型覆蓋值、套用並重啟,以及對應的事件。
- `store.dbml` 以 004 的同名檔為底,只收新增的兩張表與遷移。

後端分層是 api → services → domain / repos / adapters:api 解析與回應,services 放用例(套用並重啟、忙碌判斷),domain 放級距與範圍檢查的純函式,repos 讀寫 SQLite;E5 Colab CLI 由 `adapters/colab_cli.py` 轉接,遠端腳本放在 `adapters/scripts/`。

前端沿用 001~004 的原生 JS 分頁:開啟與變更類型共用的 `renderPicker` 加「Ollama 設定」區塊,設定卡與套用流程放在 `session.js`,級距表的顯示文字放在 `view.js`。

## 分析流程規劃

> 本段排定分析的順序與每一步指派的 planner;分析由 Phase 3 照波段交給 sub agent 執行,產出寫在 Documentation 樹列的路徑。

### 端點盤點

這次需求涉及 4 個端點。每個端點視為一個獨立系統,分析的對象是它對外的介面:

| # | 端點 | 介面 | 需求出處 |
|---|---|---|---|
| E1 | 前端 UI(瀏覽器,原生 HTML/CSS/JS) | 畫面與互動:開啟畫面的「Ollama 設定」區塊(三個欄位、留空 = 自動、依類型預先填入、全部改回自動、範圍錯誤)、工作階段頁的設定卡(量到的硬體、三項設定與來源、讀不到時的說明)、套用並重啟的確認、擋下的說明、重啟進度、改回自動值與沒有重新載入的模型的說明 | FR-004、FR-006、FR-008–FR-012、FR-015、FR-017、SC-004 |
| E2 | 後端 UI API(FastAPI REST 與 SSE) | 資源、操作、錯誤與狀態碼、狀態推送事件:開啟時的覆蓋值、工作階段狀態的 Ollama 設定、類型覆蓋值的讀取與清除、套用並重啟、忙碌與非就緒的拒絕、重啟進度與結果的推送、工作階段紀錄的設定明細 | FR-004、FR-005、FR-007–FR-018、NFR-002、NFR-003、SC-004、SC-006 |
| E4 | 資料庫(SQLite) | 資料表、欄位、關聯、唯一性與狀態約束、既有資料庫的遷移:類型覆蓋值、每次開啟或套用的 Ollama 設定 | FR-005、FR-016、FR-018、關鍵實體 |
| E5 | Colab CLI(`colab exec` 遠端腳本) | 指令與結果格式:啟動 Ollama 時帶的環境變數、量到的硬體與套用設定的回報、新的重啟指令、重啟失敗的階段、逾時與斷線重跑 | FR-001–FR-003、FR-007、FR-012、FR-013、NFR-001、SC-003、SC-005 |

沒有列的 001 端點:E3 Ollama 相容端點(重啟期間照 001「未就緒」回錯誤,介面不變)、E7 遠端 Ollama(沿用 `/api/ps` 與預先載入,介面不變)、E8 Ollama 官方模型庫、E12 Hugging Face Hub(與這次無關)、E6、E9、E10、E11(資料庫檔、掛載、port 與部署都不變)。

### 分析波段

排序原則:**一個介面排在它所依賴的介面都分析完之後**;同一波裡的介面彼此不依賴,可以各開一個 sub agent 平行分析。

第三方端點的介面是對方定好的,我們只能照著接、不能改,所以它不依賴我們任何一個介面;
反過來,我們這邊碰到它的介面都要遷就它。因此**第三方端點排在最前面**,依賴它的介面往後推一波。

| Wave | 步驟 | 介面 | Planner | 平行 | 排在這一波的理由 |
|---|---|---|---|---|---|
| 1 | S1 | E5 Colab CLI | api-plan | — | `colab exec` 的 `--env` 與 `CGB-RESULT` 行是 CLI 已經定好的形式,不依賴任何介面;遠端回報哪些硬體與設定、重啟失敗在哪一段,決定 UI API 能提供什麼 |
| 2 | S2 | E1 前端 UI | ui-plan | ✅ 與 S3 平行 | 由使用者故事推出;設定卡顯示的硬體、來源與重啟階段要照 S1 的回報欄位。前端與後端以同一份需求為準,不必等對方 |
| 2 | S3 | E2 後端 UI API | api-plan | ✅ 與 S2 平行 | 由 FR 推出;工作階段狀態的 Ollama 設定與重啟失敗的錯誤照 S1 的結果格式 |
| 3 | S4 | E4 資料庫 | data-plan | — | 要存什麼由 S3 的資源決定(類型覆蓋值、每次開啟或套用的 Ollama 設定) |

共 3 個 wave、4 個步驟:Wave 1 一個介面,Wave 2 兩個介面平行,Wave 3 一個介面。

## 待決問題

> Phase 3 每一波交回的待決問題都登記在這裡;有問題擋住下一波時,在下一波開始之前把所有還沒決定的一次問完,沒有擋住就等最後一波之後一起問。

| Q | 提出的步驟 | 問題與可選的做法 | 擋住 | 決定 |
|---|---|---|---|---|
| Q1 | S1 | 改回自動值(FR-013)最壞會超過 NFR-002 的 90 秒:a 合約維持 60 秒驗證、NFR-002 只管第一次成功(先採用);b 驗證縮到 30 秒;c 改 spec,改回自動值另訂上限 | S3 | c(分身決策紀錄 D12):spec NFR-002、SC-004 補「改回自動值時 180 秒內」;合約維持 60 秒驗證 |
| Q2 | S1 | `alreadyRunning` 時怎麼回報設定:a 讀 `/proc/<pid>/environ` 反推(先採用);b 照這次輸入重算;c 啟動時寫設定狀態檔 | S3 | c(D13):S1 合約改成寫 `/root/cgb-ollama-tuning.json`,已在執行時讀它,讀不到時 `tuning` 為 null |
| Q3 | S1 | 新增 `COLAB_INVALID_TUNING` 與 `Error.remoteStage`:a 照寫(先採用);b 不加 | S3 | a(D14) |
| Q4 | S1 | `stage: "stop"` 失敗要不要也改回自動值重試:a 所有遠端失敗都重試(建議);b 只有 start、verify | S3 | a(D15) |
| Q5 | S1 | 沒有 pid 檔時的停法:a `pkill -f`(先採用);b 先 `pgrep` 找 pid 再停整個行程群組 | — | b(D16):S1 合約照改 |
| Q6 | S1 | 改回自動值最壞約 160 秒加兩次 `colab exec` 來回,可能超過 NFR-002 的 180 秒:a 維持現狀、實跑 SC-004 時量(先採用);b 改回自動值那次驗證縮到 30~40 秒;c 兩個等待各縮到 5 秒 | — | a(D17):研究 R1 待驗證補上 |
| Q7 | S3 | 套用中怎麼表示:a 新增 `SessionState` `applying_tuning`,step 為 `restarting_ollama`/`reloading_models`(先採用);b state 維持 ready 只加 step | S2、S4 | a(分身決策紀錄 D18):001「step 只在 opening 時有值」不再成立,S2 原型對齊 |
| Q8 | S3 | 類型覆蓋值的清除:a 不另設操作,三個 null 開啟或套用時清除(先採用);b `DELETE /tuning/overrides/{gpu}` | S2 | a(D19) |
| Q9 | S3 | 開啟時何時寫入類型覆蓋值:a 受理時就寫、開啟失敗不還原(先採用);b 就緒後才寫 | — | a(D20) |
| Q10 | S3 | 哪些失敗改回自動值重試:a 只有 `COLAB_REMOTE_ERROR`、`COLAB_INVALID_TUNING`(先採用);b 所有失敗 | — | a(D21):spec FR-013 改寫成「遠端回報停止、啟動或驗證失敗時」 |
| Q11 | S3 | 「照 001 的失聯處理」:a 新增 `EndReason` `OLLAMA_RESTART_FAILED`,直接 lost、釋放執行環境、清佇列(先採用);b 走 001 重連;c 沿用既有 EndReason | S4 | a(D22):spec FR-013、US3 驗收情境 7 改寫 |
| Q12 | S3 | 紀錄結果值:a `TuningResult` 加 `in_progress`、`failed`、`interrupted`(先採用);b 只留成功、改回自動值 | S4 | a(D23):spec 關鍵實體改寫 |
| Q13 | S3 | 套用到一半後端停機:a 恢復時以這次的覆蓋值呼叫一次 `startOllama`,這次記 `interrupted`(先採用);b 不碰遠端 | — | a(D24):spec 邊界情況改寫 |
| Q14 | S3 | 重新載入細節:a `maxLoadedModels` null 時全部重新載入,單一模型載入失敗列進 `notReloaded`(先採用);b 載入失敗算套用失敗 | — | a(D25) |
| Q15 | S3 | 套用前授權檢查:a 受理前檢查,未登入回 409 `AUTH_REQUIRED`(先採用);b 不檢查 | — | a(D26) |
| Q16 | S2 | 審美方向:a 沿用 004(先採用);b 另訂 | — | a(分身決策紀錄 D27) |
| Q17 | S2 | 原型用到、S3 平行時還沒定的欄位:a S3 照原型清單提供(先採用);b 原型照 S3 合約對齊 | S2 | b(D28):S2 照 `ui.openapi.yaml` 重做欄位、`applying_tuning`、`TuningResult`、`OLLAMA_RESTART_FAILED` |
| Q18 | S2 | 忙碌什麼時候檢查:a 確認送出後由後端判斷(先採用);b 按鈕時先檢查一次 | — | a(D29):spec US3 驗收情境 3、4 改成「按套用並確認」 |
| Q19 | S2 | 改回自動值也失敗時的結束原因與紀錄:a 新增結束原因、不追加紀錄(先採用);b 沿用 001 失聯原因 | S2 | a 的結束原因照 Q11 的 `OLLAMA_RESTART_FAILED`;紀錄照 Q12 追加 `failed`(D30) |
| Q20 | S2 | 改回自動值時要不要顯示要求的手動值:a 不顯示(先採用);b 顯示 | S2 | b(D31):S3 合約已有 `TuningRecord.requested`;spec 關鍵實體補「要求的覆蓋值」 |
| Q21 | S2 | 重啟進度要不要寫目標值:a 不寫(先採用);b 加欄位 | — | a(D32) |
| Q22 | S4 | `end_reason` 要不要趁重建補 CHECK:a 補七個值(先採用);b 維持沒有 CHECK | S4 | b(分身決策紀錄 D33) |
| Q23 | S4 | 類型覆蓋值清除時:a 刪掉那一列(先採用);b 固定一列改成 NULL | — | a(D34):research R9 修訂 |
| Q24 | S4 | `interrupted` 那一筆算不算目前生效的設定:a 有讀到設定就算(先採用);b 只算 applied、fell_back_to_auto | — | a(D35):S3 `OllamaStatus.tuning` 描述已補 |
| Q25 | S4 | state 與 step 的對應要不要寫成 CHECK:a 只寫 note、由 repos 保證(先採用);b 加跨欄位 CHECK | — | a(D36) |
| Q26 | S4 | 表名 `runtime_type_tunings`,research R9「不需要重建」已不成立:a 照 S4 的表名、修 R9(先採用) | — | a(D37):research R9 修訂 |
