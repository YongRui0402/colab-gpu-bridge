# 跨產出物分析: 佇列隨工作階段清空、測試對話框、Hugging Face 模型來源與可編輯的精選清單

**Feature**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md) | **Constitution**: `constitution/`

## 判定

**最新一輪:第 2 輪(2026-11-14)— ✅ 可以進 `/implement`**

第 1 輪的 A1~A38 都已修正,兩項轉交(SC-003、FR-012)都已澄清,沒有還沒解決的 CRITICAL 或 HIGH。這一輪新找到 MEDIUM 2 個(A39、A40),都出在修 A19 時新增的對話頁錯誤說明:一個是原型把 502 的四個代碼都標成「連不到」,一個是 tasks 沒有替前端要顯示的兩個後端訊息指定文字。兩個都不擋實作,建議開工前照修正順序先改;不先改的話,至少要在 `/implement` 做到故事 2 的 T043b、T047b、T068b、T244b 時一併處理。

## 檢查範圍

| 產出物 | 產出的步驟 |
|---|---|
| `spec.md` | `/specify`、`/clarify-over-specs`(`澄清報告.md`) |
| `research.md`、`techstack.md` | `/technical-research` |
| `plan.md` | `/system-analysis` |
| `contracts/remote-ollama.openapi.yaml`、`contracts/huggingface.openapi.yaml`、`contracts/ui.openapi.yaml`、`contracts/ui-events.asyncapi.yaml` | `/api-plan` |
| `contracts/store.dbml` | `/data-plan` |
| `prototype/`(index、chat、library、models、states、mock.js、style.css) | `/ui-plan` |
| `testplan.md` | `/testplan` |
| `tasks.md` | `/tasks` |
| `分身決策紀錄.md`(D1~D104,對照 `plan.md` § 待決問題 Q1~Q74;依使用者 2026-11-14 授權由分身代答) | 各步驟的 kevin-twin 代答 |
| `constitution/_shared/語言.md` | `/constitution` |
| 前一次迭代的 `../003-download-dedup-model-cache/plan.md`;護欄另讀 `../001-session-model-catalog/testplan.md` § 實跑案例的共同護欄;D75 另讀 `src/cgb/domain/errors.py` 的訊息表 | 001、003 的 `/system-analysis`、`/testplan` |

---

## 第 1 輪(2026-11-14)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `specify/scripts/check_spec.py` | ✅ 通過 |
| `system-analysis/scripts/check_plan.py` | ✅ 通過(`--previous-plan ../003-download-dedup-model-cache/plan.md`) |
| `testplan/scripts/check_testplan.py` | ✅ 通過 |
| `tasks/scripts/check_tasks.py` | ✅ 通過 |

### 問題

| ID | 類別 | 嚴重度 | 位置 | 摘要 | 回哪一步 |
|---|---|---|---|---|---|
| A1 | 無法實作 | HIGH | `tasks.md` § T013b;`tasks.md` § T017b;`tasks.md` § T110a;`plan.md` § 待決問題 Q64 | Q64 決定「欄位與表由故事 1 的 E4 節照 store.dbml 建」,T013b 寫「`curated_models.auto_download`、`auto_download_results`、`auto_download_items` 由 E4 節照 `contracts/store.dbml` 建……這個任務不改那個檔(依賴 T013a、T024b)」;但 T017b 只寫「只寫讓 US1-DB-01 通過的程式碼」,US1-DB-01~08 只斷言 `download_jobs`,沒有任務負責建這三樣。T110a 又是一般紅燈,預期因「全新庫的 `_CURATED_MODELS` DDL 沒有改」而失敗。照嚴格 TDD,T013b 做不下去;讓 T017b 照 ⚙ 全建,T110a 起的紅燈就判斷錯 | `/tasks` |
| A2 | 矛盾 | HIGH | `plan.md` § 待決問題 Q40;`research.md` § R7;`contracts/store.dbml` § `Project` Note(遷移第 1、2 步);`testplan.md` § US3-DB-05 | Q40(D54)決定「建索引前在同一個交易裡每組只留 id 最小的那一筆、其他刪掉,刪掉的名稱寫進日誌」;store.dbml 第 1 步寫「再 `CREATE UNIQUE INDEX uq_curated_models_name_ci` …… 001 的名稱只收小寫,既有資料不會撞到」,第 2 步重建後直接建 `uq_download_jobs_pending_model_ci`,都沒有去重;R7 也沒有這一步。US3-DB-05 的「要抓的錯」正是照 store.dbml 的假設直接建索引。照 store.dbml 做,舊庫有只差大小寫的名稱時遷移 rollback、後端起不來 | `/technical-research`、`/data-plan` |
| A3 | 遺漏 | HIGH | `plan.md` § 待決問題 Q40;`testplan.md` § US3-DB-05;`testplan.md` § US1-DB-08;`tasks.md` § T114b | D54 要求刪掉的名稱寫進日誌;`download_jobs` 那一側 US1-DB-08 斷言 `caplog`,`curated_models` 那一側 US3-DB-05 沒有日誌的則,T114b 只寫「只寫讓 US3-DB-05 通過的程式碼」。照 tasks 做,被刪掉的精選名稱不會進日誌 | `/testplan` |
| A4 | 遺漏 | HIGH | `plan.md` § 待決問題 Q61;`testplan.md` § US2-API-12、US2-API-13;`tasks.md`(無對應任務);`../../src/cgb/domain/errors.py` § `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT` | Q61(D75)決定對話頁沿用的 `OLLAMA_*` 說明改成兩邊都通的通用說法;現行三句都寫「無法確認哪些模型已經下載」,testplan 只驗「說明是中文」,tasks 沒有任務改這三句。決定沒有落地 | `/testplan` |
| A5 | 矛盾 | HIGH | `research.md` § R6(判定順序後的一點);`plan.md` § 待決問題 Q52;`contracts/ui.openapi.yaml` § `info.x-auto-download` (3)(d);`testplan.md` § US3-API-20 | R6 寫「讀不到剩餘空間時全部跳過,原因『讀不到剩餘空間』」;Q52(D66)決定保留已判定的原因,合約 (d) 寫「其餘還沒判定的項目都跳過」,US3-API-20 則2 的 `999b` 仍是 `SIZE_UNAVAILABLE`。照 R6 做,已跳過的項目會被改標 `DISK_SPACE_UNKNOWN` | `/technical-research` |
| A6 | 矛盾 | HIGH | `research.md` § R5(轉送);`plan.md` § 待決問題 Q11、Q60;`contracts/ui.openapi.yaml` § `ChatStreamFailure`;`testplan.md` § US2-API-20 | R5 寫「回應沿用 `_relay`(工作階段被結束時補一行 `{"error": ...}`,非預期斷線時補『串流中斷』」;Q11(D25)與合約要最後一行是 `{"error": {"code","message"}}` 物件,Q60(D74)要失聯時對話也結束轉送。照 R5 做,前端收到字串、分不出原因;US2-API-20 的「要抓的錯」正是這種寫法。R5 的修訂紀錄只補了 `keep_alive` | `/technical-research` |
| A7 | 矛盾 | HIGH | `contracts/ui.openapi.yaml` § `retryDownload`;`testplan.md` § 9. 不在本次範疇;`plan.md` § 待決問題 Q56 | 合約寫「先確認模型不在執行環境上、再檢查剩餘磁碟」,409 列 `DISK_SPACE_INSUFFICIENT`、503 列 `DISK_SPACE_UNKNOWN`;testplan § 9 寫「這一輪重新排隊不讀剩餘磁碟」,D70 寫「`DISK_SPACE_*` 照舊範圍外」。照合約做會讀磁碟並可能回 409、503 | `/api-plan` |
| A8 | 無法實作 | HIGH | `testplan.md` § US3-AJ-08;`contracts/ui.openapi.yaml` § `info.x-auto-download` (3)(d)(e) | US3-AJ-08 要「四種跳過原因各一筆,含 `DISK_SPACE_UNKNOWN`、`DISK_SPACE_INSUFFICIENT`」同在一個提示;合約 (d) 讀不到磁碟時其餘都標 `DISK_SPACE_UNKNOWN`,(e) 只在讀得到磁碟時出現,同一次判定裡兩者互斥,e2e 用真的後端鋪不出來 | `/testplan` |
| A9 | 矛盾 | HIGH | `testplan.md` § US3-AJ-03 情況 A;`contracts/ui.openapi.yaml` § `ModelName`;`prototype/library.html` § `[data-state="cur-duplicate"]` | US3-AJ-03 A 新增 `Qwen2.5:Latest`、則1 要顯示 `cur-duplicate`;`ModelName` 官方名稱只收小寫(Q23、D37),`Qwen2.5` 會回 400 `INVALID_MODEL_NAME`,畫面是 `cur-invalid`。原型的重複範例 `Qwen2.5:7B` 同樣不合法 | `/ui-plan`、`/testplan` |
| A10 | 遺漏 | HIGH | `prototype/library.html` § `#c-type`、`submitForm`;`contracts/ui.openapi.yaml` § `RuntimeType`(`required: [gpu, highMem]`)、`updateCurated`;`spec.md` § FR-009 | FR-009 要能編輯 001 `CuratedModelInput` 的建議執行階段類型;`RuntimeType` 必填 `highMem`,`updateCurated` 整筆取代、沒給的視為清空;原型的精選表單只有 GPU 選單、`type` 存成字串,沒有高 RAM。照原型做,既有高 RAM 的項目改個說明就被清掉,也設不了高 RAM | `/ui-plan` |
| A11 | 矛盾 | HIGH | `testplan.md` § 7.0 實跑案例的共同護欄(Hugging Face);`testplan.md` § G-01;`contracts/huggingface.openapi.yaml` § `info.x-timeout`;`contracts/ui.openapi.yaml` § `listHfQuants` | 7.0 寫「只送不帶 token……的唯讀 GET,串列送出、不重試」;G-01 呼叫真的 `list_quants`,自己寫「manifest……同時最多 4 個」,合約也規定同時最多 4 個。照 G-01 做違反 7.0,照 7.0 做就不能用真的 `list_quants` | `/testplan` |
| A12 | 矛盾 | HIGH | `prototype/library.html` § `[data-state="hf-no-gguf"]`、`[data-state="hf-quant-unavailable"]`;`prototype/mock.js` § `Proto.lookup`;`plan.md` § 待決問題 Q20;`contracts/ui.openapi.yaml` § `estimateDownloads` 422;`testplan.md` § US4-AJ-08 | 原型的試算遇到沒有 GGUF 的 repo 回 `HF_NO_GGUF` 並跳出 sheet;合約與 Q20(D34)規定試算與加入的 422 只有 `LIBRARY_CLOUD_ONLY`、`HF_AUTH_REQUIRED`、`HF_QUANT_UNAVAILABLE`,`HF_NO_GGUF` 只由 `listHfQuants` 回。US4-AJ-08「依序鋪出……`hf-no-gguf`」接真的後端鋪不出來;`hf-quant-unavailable` 的文字也少了「不是 GGUF」 | `/ui-plan`、`/testplan` |
| A13 | 矛盾 | MEDIUM | `spec.md` § FR-012;`plan.md` § Project Structure(`static/` 那一行與前端段落)、§ 待決問題 Q29;`contracts/ui.openapi.yaml` § `getAutoDownloadResult`;`contracts/ui-events.asyncapi.yaml` § `components.messages.autoDownloadUpdated`;`research.md` § R6;`prototype/models.html` § `#auto-notice`;`tasks.md` § T126b | Q29(D43)把提示區定在「模型頁下載佇列上方」,spec、原型、T126b(`js/models.js`)照改;plan.md 仍寫「自動下載提示區加在下載頁的 `js/library.js`」,合約與 AsyncAPI 寫「下載頁佇列上方的提示區」,R6 寫「下載頁讀 UI API」;testplan US3-API-26 與 T097a 也寫「打開下載頁」 | `/technical-research`、`/system-analysis`、`/api-plan` |
| A14 | 矛盾 | HIGH | `contracts/ui.openapi.yaml` § `listDownloads`、`components.schemas.DownloadQueue.paused`;`contracts/ui.openapi.yaml` § `info.x-queue-clearing` (1)(3);`testplan.md` § US1-API-05、US1-API-11 | `paused` 那兩句寫「這時佇列只可能有……重新載入而排入的項目,其他時候是空的」;x-queue-clearing 只在結束類狀態清除、接回時不移除,US1-API-05 則1 要重連中仍有四筆。照字面做,重連中就清空(考慮過 MEDIUM:是說明文字;依「不確定選高一級」給 HIGH) | `/api-plan` |
| A15 | 矛盾 | HIGH | `contracts/ui-events.asyncapi.yaml` § `operations.sendDownloadsSnapshot.x-callers`;`plan.md` § 待決問題 Q47;`contracts/ui.openapi.yaml` § `info.x-queue-clearing` (1);`testplan.md` § US1-API-01、US1-API-08 | AsyncAPI 寫「在每一則 `download.removed` 之後送一次(佇列是空的,或變更類型時只剩重新載入的項目)」;Q47(D61)決定變更類型時快照是空的、接著推那一筆的 `download.updated`,x-queue-clearing (1) 與 US1-API-01 是「全部移除後送一則」 | `/api-plan` |
| A16 | 矛盾 | HIGH | `contracts/store.dbml` § `Table auto_download_results`(`target_count`);`plan.md` § 待決問題 Q41;`testplan.md` § US3-DB-09 | Q41(D55)決定加 `CHECK (target_count >= 0)`,US3-DB-09 ④ 寫入 -1 要丟 `IntegrityError`;store.dbml 只在 note 寫「>= 0」,沒有約束(考慮過 MEDIUM:對外沒有寫入 -1 的路徑,但建出來的 schema 不同) | `/data-plan` |
| A17 | 遺漏 | HIGH | `plan.md` § 待決問題 Q53;`contracts/ui.openapi.yaml` § `updateCurated`;`testplan.md` § US3-API-04、US3-API-09 | Q53(D67)決定 id 不存在、本文又不合法時先驗本文回 400;合約沒有寫檢查順序,也沒有案例同時給兩者 | `/api-plan`、`/testplan` |
| A18 | 遺漏 | HIGH | `contracts/ui.openapi.yaml` § `listHfQuants`(時間上限);`plan.md` § 待決問題 Q44;`testplan.md` § US4-API-08 | 合約寫檔案清單、所有 manifest 與讀模型清單「共用一個 10 秒期限」;Q44(D58)替讀模型清單另設 `hf_expand_deadline`(10)。沒寫兩段平行還是串接、從哪裡起算;串接時成功可到約 20 秒,不符 SC-004;US4-API-08 C 的 `list_quants` 立即回,抓不到 | `/system-analysis` |
| A19 | 遺漏 | MEDIUM | `contracts/ui.openapi.yaml` § `chat`(200 `x-stream-error-codes`、404、502、504);`prototype/chat.html` § `[data-state="turn-error"]`、`[data-state="turn-timeout"]`、`[data-state="turn-lost"]`;`testplan.md` § US2-AJ-08~10 | 串流中的 5 個代碼原型只對到 3 個(沒有 `OLLAMA_STREAM_INTERRUPTED`、`OLLAMA_BAD_RESPONSE`),串流開始前的 404、502、504 沒有畫面;`turn-error` 寫死「推論失敗(例如記憶體不足)」,和 D75 不一致。後端案例涵蓋 5 個代碼,前端只驗 3 種 | `/ui-plan`、`/testplan` |
| A20 | 矛盾 | MEDIUM | `contracts/ui.openapi.yaml` § `listHfQuants` 502;`prototype/library.html` § `HF_INLINE`、`[data-state="hf-expand-down"]`;`testplan.md` § G-04 | 原型的 `HF_INLINE` 沒有 502 的三個代碼,`hf-expand-down` 只寫「10 秒內沒有回應」;G-04 則3 斷言「暫時無法使用」,原型文字是「暫時無法取得 Hugging Face 的版本清單」 | `/ui-plan`、`/testplan` |
| A21 | 無法實作 | MEDIUM | `prototype/library.html` § `#name-form`;`contracts/ui.openapi.yaml` § `info.x-download-check-order` (2) | 原型沒有工作階段時按「加入勾選」也會確認大小並顯示 `hf-auth-required` 等;合約裡能取大小的只有 `estimateDownloads`,沒有就緒的工作階段時回 503 `NO_READY_SESSION` | `/ui-plan` |
| A22 | 無法實作 | MEDIUM | `prototype/mock.js` § `MOCK.autoResult.skipped[].detail`;`prototype/models.html` § `#auto-notice`;`contracts/ui.openapi.yaml` § `AutoDownloadSkipped` | 原型顯示「需要 243.2 GB,排入前面幾個之後只剩 186.0 GB」「19.9 GB,超過 T4 的顯示記憶體」;合約只有 `model`、`reason`、`reasonCode`、`message`,沒有大小與剩餘空間 | `/api-plan`、`/ui-plan` |
| A23 | 無法實作 | MEDIUM | `prototype/models.html` § `#qc-text`(`[data-state="queue-cleared"]`);`prototype/index.html` § `[data-state="ended-offline"]`;`contracts/ui.openapi.yaml` § `DownloadQueue`;`contracts/ui-events.asyncapi.yaml` § `sendDownloadRemoved` | 原型寫「佇列的 6 筆已一起清除」;`DownloadQueue` 只有 `{paused, jobs}`、`download.removed` 只有 `id`,停機期間的移除沒有 UI 時不送,筆數做不出來,重新整理後也分不出 queue-cleared 與 queue-empty | `/ui-plan` |
| A24 | 無法實作 | MEDIUM | `testplan.md` § US4-API-31;`contracts/ui.openapi.yaml` § `searchHfModels`、`listHfQuants`、`estimateDownloads`、`enqueueDownloads` 的 `x-error-codes` | US4-API-31 對四個操作都注入 7 個 `HF_*` 並要求不回 500;合約沒有定搜尋收到 `HF_NO_GGUF` 等、展開收到 `HF_QUANT_UNAVAILABLE`、試算收到 `HF_NO_GGUF` 時回哪個狀態碼 | `/api-plan` |
| A25 | 無法追溯 | MEDIUM | `testplan.md` § 3.1 節首、US2-API-06、§ 5.1 節首、US4-API-08、US4-API-27~30;`testplan.md` § 10. 待決問題;`tasks.md` § T212a、T213a、T214a | testplan 多處寫「見待決問題」「待決問題 1~4」,§ 10 只有一段總結、沒有編號清單;實際應指 `plan.md` Q44、Q49、Q54、Q57。tasks 照抄 | `/testplan` |
| A26 | 矛盾 | MEDIUM | `research.md` § R5(轉送);`plan.md` § 待決問題 Q44;`tasks.md` § T031b | R5 寫「逾時沿用 `FORWARD_TIMEOUT`」;Q44(D58)改成 `Timeouts.chat_connect`、`chat_read`,T031b 照 D58。秒數相同,只差注入點 | `/technical-research` |
| A27 | 矛盾 | MEDIUM | `contracts/ui.openapi.yaml` § `info.x-auto-download` (1);`contracts/store.dbml` § `auto_download_results.target_count`;`plan.md` § 待決問題 Q24 | 合約寫「沒有任何一項設 `autoDownload` 時不做,也沒有結果」;Q24(D38)與 store.dbml 仍寫一列 `target_count = 0`。對外都回 null,「不做」可能被讀成連那一列都不寫 | `/api-plan` |
| A28 | 矛盾 | LOW | `contracts/store.dbml` § `idx_download_jobs_session`;`contracts/ui.openapi.yaml` § `listDownloads`、`DownloadQueue.jobs`;`plan.md` § 待決問題 Q46 | 三處寫「listDownloads 只列目前工作階段的項目」;Q46(D60)決定不過濾。清除是同步的,過濾與否結果相同 | `/data-plan`、`/api-plan` |
| A29 | 遺漏 | LOW | `plan.md` § 待決問題 Q45;`contracts/remote-ollama.openapi.yaml` § `info.x-failure-rules` 第 4 條 | D59 決定只比 media type;合約仍寫「`Content-Type` 不是 `application/x-ndjson`」,沒寫參數,也沒有帶 charset 的案例 | `/api-plan` |
| A30 | 遺漏 | LOW | `spec.md` § FR-017、使用者故事 5 驗收情境 4;`testplan.md` § US5-AJ-04 | 只驗「修改」表單的 `#c-type` 沒有 H100,「新增」表單沒有案例 | `/testplan` |
| A31 | 矛盾 | LOW | `testplan.md` § 1 受測操作(關閉自動下載提示);`contracts/ui.openapi.yaml` § `dismissAutoDownloadResult` | testplan 錨點寫 `AutoDownloadNotice`,dismiss 的 200 回 `AutoDownloadResult` | `/testplan` |
| A32 | 矛盾 | LOW | `tasks.md` § US3 E4 節首;`plan.md` § 待決問題 Q27、Q40、Q41、Q54 | tasks 寫「`foreign_keys` 不開……(Q41)」「精選名稱只差大小寫……(Q40、Q54)」;外鍵是 Q27,Q41 是 `target_count`,Q54 是舊測試 | `/tasks` |
| A33 | 矛盾 | LOW | `tasks.md` § T072a、T083a、T098a;`tasks.md` § T013b;`plan.md` § 待決問題 Q63、Q64 | T013b 已做 `autoDownload` 存讀與第一次就緒排入;T072a、T083a、T098a 的預期失敗原因仍是「沒有 `autoDownload`」「`ready_listeners` 只掛了 `resume`」,可能一跑就通過;Q63 有對照組的退路 | `/tasks` |
| A34 | 矛盾 | LOW | `prototype/models.html` § `[data-state="auto-running"]`;`contracts/ui.openapi.yaml` § `dismissAutoDownloadResult` | 合約寫 `running` 時也可以關閉,原型判定中的提示沒有關閉鈕 | `/ui-plan` |
| A35 | 矛盾 | LOW | `prototype/mock.js` § `validName`、`isHf`;`contracts/ui.openapi.yaml` § `ModelName` | mock 接受 `<使用者>/<名稱>` 與大寫的 `HF.CO/`,合約都拒絕;前端接 400 後畫面一樣 | `/ui-plan` |
| A36 | 遺漏 | LOW | `spec.md` § 使用者故事 1 驗收情境 3;`prototype/index.html`(沒有 `failed`、`lost-timeout` 的改寫) | 沒有畫面呈現「開啟失敗、重連逾時時佇列也清空」 | `/ui-plan` |
| A37 | 矛盾 | LOW | `prototype/chat.html` § `[data-state="turn-lost"]`;`contracts/ui.openapi.yaml` § `chat` 200 | 原型寫「工作階段已結束或失聯」;`SESSION_ENDED` 還包含變更類型 | `/ui-plan` |
| A38 | 矛盾 | LOW | `research.md` § R3 第 6 步;`plan.md` § 待決問題 Q4、Q5;`spec.md` § 使用者故事 4 獨立測試;`contracts/ui.openapi.yaml` § `estimateDownloads`;`testplan.md` § G-01、G-06;`research.md` § R2 | (a) R3 沒寫展開的整體期限(Q4)與「200 但沒有模型層」(Q5);(b) spec 寫「試算大小與替身給的檔案大小一致」,合約是 manifest `layers[].size` 的總和;(c) G-01 說 `qwen2.5-0.5b`「未用於調整」,R2 研究時用過;(d) G-06 寫「不讀寫桌機的 `~/.config/colab-cli/`」又說照 001 的 P1~P9,P9 會讀桌機的 `token.json`(G-06 這一輪延後) | `/technical-research`、`/specify`、`/testplan` |

### 追溯缺口

只列有缺口的需求;其餘需求從規格檔到任務都接得上。

| 需求 | 規格檔元素 | 任務 | 缺口 |
|---|---|---|---|
| FR-011、FR-012(US1-API-13 用到的自動下載表) | `store.dbml` § `auto_download_results`、`auto_download_items`、`curated_models.auto_download` | T013b(依賴的表沒有任務建) | A1 |
| NFR-004 遷移(只差大小寫的舊名稱) | `store.dbml` § `Project` Note(沒有去重) | T024b(`download_jobs` 有)、T114b(沒寫日誌) | A2、A3 |
| FR-008 對話中斷的原因 | `ui.openapi.yaml` § `chat`;`prototype/chat.html` 只有 3 種 | 無(D75 的通用說法) | A4、A19 |
| FR-012 讀不到剩餘空間 | `ui.openapi.yaml` § `info.x-auto-download` (3)(d) | T091(照合約);`research.md` § R6 相反 | A5 |
| FR-009 建議類型的高 RAM | `ui.openapi.yaml` § `RuntimeType` | 無(原型沒有高 RAM) | A10 |
| NFR-007、FR-012(四種跳過原因的畫面) | `prototype/models.html` § `#auto-notice` | US3-AJ-08 的任務(鋪不出來) | A8 |
| FR-015、FR-016(試算與展開的畫面) | `prototype/library.html` § `hf-no-gguf`、`hf-expand-down` | US4-AJ-08 的任務(鋪不出來) | A12、A20 |
| SC-004(展開 11 秒) | `ui.openapi.yaml` § `listHfQuants` | T193b(期限怎麼組沒定) | A18 |

### 轉交 `/clarify-over-specs`

單份文件內的模糊不屬於本步驟,標記後轉交:

| 位置 | 為什麼要澄清 |
|---|---|
| `spec.md` § SC-003 | 「設了自動下載的項目……100% 被排入佇列或在 UI 標示跳過原因」;同一份 spec 的驗收情境 5 寫已在執行環境上或佇列中的不再排入、也不列為跳過。照 SC 字面要連這些也列出,量測不知道分母要不要扣掉 |
| `spec.md` § FR-012 | 跳過原因只列三種,第四種「讀不到剩餘空間」(Q17)只補在關鍵實體;下游不確定 FR-012 的範圍包不包含它 |

### 修正順序

1. `/clarify-over-specs` 澄清 SC-003 的分母與 FR-012 的第四種原因;`/specify` 把使用者故事 4 獨立測試的「檔案大小」改成 manifest 大小(A38 (b))
2. `/technical-research` 改 `research.md`:R5 對齊 Q11、Q60、Q44(A6、A26),R6 對齊 Q52、提示區改模型頁(A5、A13),R7 補遷移前去重並寫日誌(A2),R3 補整體期限與沒有模型層(A38 (a)),修訂紀錄記上
3. `/system-analysis` 改 `plan.md`:Project Structure 的提示區改模型頁與 `js/models.js`(A13);定下展開時讀模型清單與 HF 期限怎麼組(A18,新的待決問題接 Q67)
4. `/api-plan` 改合約:A7、A13、A14、A15、A17、A18、A22、A24、A27、A28、A29;`/data-plan` 改 store.dbml:A2、A16、A28
5. `/ui-plan` 改原型:A9、A10、A12、A19、A20、A21、A22、A23、A34~A37
6. `/testplan` 改 `testplan.md`:A3、A4、A8、A9、A11、A12、A17、A18、A19、A20、A25、A30、A31、A38 (c)(d),並涵蓋第 4、5 步新增的錨點
7. `/tasks` 在故事 1 的 E4 節指定建表的綠燈、故事 3 已做到的紅燈改對照組(A1、A33)、Q 編號引用(A32),並照第 6 步從 T238 起補任務
8. 重跑 `/analyze`

---

## 第 2 輪(2026-11-14)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `specify/scripts/check_spec.py` | ✅ 通過 |
| `system-analysis/scripts/check_plan.py` | ✅ 通過(`--previous-plan ../003-download-dedup-model-cache/plan.md`) |
| `testplan/scripts/check_testplan.py` | ✅ 通過 |
| `tasks/scripts/check_tasks.py` | ✅ 通過 |

### 上一輪的問題

| ID | 狀態 | 依據 |
|---|---|---|
| A1 | ✅ 已修正 | `tasks.md` § T017b 照 `store.dbml` 一次建全新庫的整份 DDL(含 `curated_models.auto_download`、`auto_download_results`、`auto_download_items`),T013b 改成依賴 T017b;T110a、T118a、T119a、T248a 改成對照組(`plan.md` Q74、D104) |
| A2 | ✅ 已修正 | `research.md` § R7 補「建索引前先去重」與修訂紀錄;`store.dbml` § `Project` Note 遷移第 1、2 步在建唯一索引前依 `lower(...)` 分組、留 `id` 最小的一筆並寫日誌,去重後建索引仍失敗就整個 rollback |
| A3 | ✅ 已修正 | `testplan.md` § US3-DB-05 在 `caplog` 底下執行,則5 斷言被刪名稱 `qwen2.5:Latest` 的 WARNING;`tasks.md` § T114b 寫進日誌 |
| A4 | ✅ 已修正 | `testplan.md` § US2-API-28 斷言三句不含「無法確認哪些模型已經下載」;`tasks.md` § T241a、T241b 改 `src/cgb/domain/errors.py` 的三句 |
| A5 | ✅ 已修正 | `research.md` § R6 改成保留已判定的原因、只有還沒判定的標 `DISK_SPACE_UNKNOWN`;`spec.md` § FR-012 與使用者故事 3 驗收情境 11 同一個說法 |
| A6 | ✅ 已修正 | `research.md` § R5 補「串流開始後的失敗」(最後一行是 `{"error": {"code","message"}}`)與「工作階段結束或失聯」(失聯時也結束轉送) |
| A7 | ✅ 已修正 | `ui.openapi.yaml` § `retryDownload` 寫明不讀剩餘磁碟,409、503 拿掉 `DISK_SPACE_*`,和 `testplan.md` § 9、D70 一致 |
| A8 | ✅ 已修正 | `testplan.md` § US3-AJ-08 改成兩個工作階段各鋪一次(`plan.md` Q70、D100),則2、則3 分開斷言 |
| A9 | ✅ 已修正 | `testplan.md` § US3-AJ-03 情況 A 改成合法的 `qwen2.5:Latest`;`prototype/library.html` 的 `cur-duplicate` 範例改成 `nomic-embed-text` 對 `nomic-embed-text:latest` |
| A10 | ✅ 已修正 | `prototype/library.html` § `#c-highmem`、`submitForm` 改送 `{gpu, highMem}`(D95);`testplan.md` § US3-AJ-11 |
| A11 | ✅ 已修正 | `testplan.md` § 7.0 的 Hugging Face 護欄改成同時最多 4 個、不重試、每次最多 40 個請求(`plan.md` Q71、D101);G-01 則9 斷言請求總數 ≤ 40 |
| A12 | ✅ 已修正 | `prototype/library.html` 刪掉 `hf-no-gguf`,`prototype/mock.js` § `Proto.lookup` 改回 `HF_QUANT_UNAVAILABLE`、文字補「不是 GGUF」(D99);`testplan.md` § US4-AJ-08 不再鋪 `hf-no-gguf`,另加 US4-AJ-09 |
| A13 | ✅ 已修正 | `plan.md` § Project Structure、`research.md` § R6、`ui.openapi.yaml` § `getAutoDownloadResult`、`ui-events.asyncapi.yaml` § `autoDownloadUpdated` 都改成模型頁下載佇列上方;`testplan.md` § US3-API-26 與 `tasks.md` § T097a 改寫「模型頁」 |
| A14 | ✅ 已修正 | `ui.openapi.yaml` § `listDownloads`、`DownloadQueue.paused` 分情況寫明:重連中照樣留著、變更類型只有重新載入的項目、其他時候是空的 |
| A15 | ✅ 已修正 | `ui-events.asyncapi.yaml` § `sendDownloadsSnapshot.x-callers` 改成全部推完 `download.removed` 之後只送一次空的快照,變更類型時接著推重新載入項目的 `download.updated`(Q47、D61) |
| A16 | ✅ 已修正 | `store.dbml` § `auto_download_results.target_count` 寫明建表加 `CHECK (target_count >= 0)`(pydbml 解析不了 checks,所以寫在 note);`tasks.md` § T017b 與遷移第 3 步照建 |
| A17 | ✅ 已修正 | `ui.openapi.yaml` § `updateCurated` 補檢查順序 400 → 404 → 409(Q53、D67);`testplan.md` § US3-API-38 |
| A18 | ✅ 已修正 | `plan.md` Q67(D85)定為兩段平行、都從收到展開請求起算;`ui.openapi.yaml` § `listHfQuants` 的時間上限改寫成 (a)~(d);`testplan.md` § US4-API-08 則5、US4-API-32 |
| A19 | ✅ 已修正 | `prototype/chat.html` 補 `turn-interrupted`、`turn-bad-response`、`turn-not-found`、`turn-unavailable`、`turn-start-timeout`,`turn-error` 改成通用說法(D96);`testplan.md` § US2-AJ-10 則6、則7、US2-AJ-13、US2-AJ-14。修正帶出的文字問題另開 A39、A40 |
| A20 | ✅ 已修正 | `prototype/library.html` § `HF_INLINE` 補 502 的三個代碼,`hf-expand-down` 改成「Hugging Face 暫時無法使用」;`testplan.md` § US4-AJ-10、G-04 則3 |
| A21 | ✅ 已修正 | `prototype/library.html` § `[data-state="direct-unchecked"]`:沒有就緒的工作階段時只檢查格式就加入勾選(D97);`testplan.md` § US4-AJ-11 |
| A22 | ✅ 已修正 | `ui.openapi.yaml` § `AutoDownloadSkipped` 加選填 `sizeBytes`、`freeDiskBytes`、`vramBytes`,`store.dbml` § `auto_download_items` 加三欄(Q68、D86);`prototype/mock.js` 照合約欄位;`testplan.md` § US3-API-39、US3-DB-13 |
| A23 | ✅ 已修正 | `prototype/models.html` 與 `prototype/index.html` 拿掉筆數,改依工作階段狀態判斷 `queue-cleared`(D98);`testplan.md` § US1-AJ-07 則4 斷言不含「筆」 |
| A24 | ✅ 已修正 | `ui.openapi.yaml` § `info.x-hf-error-status` 定下四個操作共用的對應(Q69、D87);`testplan.md` § US4-API-31 則6 |
| A25 | ✅ 已修正 | `testplan.md` § 10 寫明一律引用 `plan.md` 的 Q 編號,全檔不再有「見待決問題」「待決問題 1~4」 |
| A26 | ✅ 已修正 | `research.md` § R5 改成從 `Timeouts.chat_connect`、`chat_read` 注入(Q44、D58) |
| A27 | ✅ 已修正 | `ui.openapi.yaml` § `info.x-auto-download` (1) 寫明不判定、不排入,但仍記下這個工作階段做過(Q24、D38) |
| A28 | ✅ 已修正 | `store.dbml` § `idx_download_jobs_session`、`ui.openapi.yaml` § `listDownloads`、`DownloadQueue.jobs` 都改成不依工作階段過濾(Q46、D60) |
| A29 | ✅ 已修正 | `remote-ollama.openapi.yaml` § `info.x-failure-rules` (4) 只比 media type、忽略參數(Q45、D59);`testplan.md` § US2-API-29、US4-RO-15 有帶 charset 的情況 |
| A30 | ✅ 已修正 | `testplan.md` § US5-AJ-05 驗新增表單的 `#c-type` 沒有 H100 |
| A31 | ✅ 已修正 | `testplan.md` § 1 受測操作的「關閉自動下載提示」錨點改成 `AutoDownloadResult` |
| A32 | ✅ 已修正 | `tasks.md` § US3 E4 節首的外鍵改引 `plan.md` Q27 |
| A33 | ✅ 已修正 | `tasks.md` § T072a、T083a 改寫預期失敗的原因並排除 T013b 已做到的部分;T098a 改成對照組 |
| A34 | ✅ 已修正 | `prototype/models.html` § `[data-state="auto-running"]` 加關閉鈕(`[data-dismiss]`),`prototype/mock.js` 判定完成時保留 `dismissed`;`testplan.md` § US3-AJ-10 |
| A35 | ✅ 已修正 | `prototype/mock.js` § `validName`、`isHf` 改用 `ModelName` 的 pattern |
| A36 | ✅ 已修正 | `prototype/index.html` 補 `[data-state="lost-timeout"]`、`[data-state="failed"]`;`testplan.md` § US1-AJ-05、US1-AJ-06 |
| A37 | ✅ 已修正 | `prototype/chat.html` § `[data-state="turn-lost"]` 含「正在變更類型」;`testplan.md` § US2-AJ-15 |
| A38 | ✅ 已修正 | (a)`research.md` § R3 補第 8 步整體期限與 200 沒有模型層;(b)`spec.md` § 使用者故事 4 獨立測試改成 manifest `layers[].size` 的總和;(c)`testplan.md` § G-01 改寫成「research.md R2 研究時用過,調整用」;(d)G-06 的授權取得留到實跑前由使用者本人決定(`plan.md` Q72、D102) |
| SC-003 | ✅ 已澄清 | `spec.md` § SC-003 的分母限定在 FR-011 的範圍(D81);`testplan.md` § US3-API-36 則4 |
| FR-012 | ✅ 已澄清 | `spec.md` § FR-012 列出四種跳過原因,新增使用者故事 3 驗收情境 11(D82);`testplan.md` § US3-API-20 追溯到驗收情境 11 |

### 新問題

| ID | 類別 | 嚴重度 | 位置 | 摘要 | 回哪一步 |
|---|---|---|---|---|---|
| A39 | 矛盾 | MEDIUM | `prototype/chat.html` § `[data-state="turn-unavailable"]`、`CUT.unavailable`;`contracts/ui.openapi.yaml` § `chat` 502;`分身決策紀錄.md` § D96;`testplan.md` § US2-AJ-14 | 合約的 502 有 `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_REQUEST`、`OLLAMA_SERVER_ERROR`(「回 500,例如記憶體不足載入失敗」)、`OLLAMA_BAD_RESPONSE` 四個代碼,D96 決定四個共用一個畫面、顯示後端的 `message`;原型的 `turn-unavailable` 卻寫死「沒有送出:連不到執行環境上的 Ollama」,回覆下方的標示 `CUT.unavailable` 也寫死「沒有回覆:連不到 Ollama」。照原型做,遠端記憶體不足、載入失敗也會被標成「連不到」;US2-AJ-14 B 只驗 `OLLAMA_UNREACHABLE`,測不出來(考慮過 HIGH:T244b 已寫「說明用錯誤回應的 `message`」,會錯的只剩標示文字,畫面狀態不受影響) | `/ui-plan` |
| A40 | 無法實作 | MEDIUM | `tasks.md` § T068b;`tasks.md` § T043b、T047b;`testplan.md` § US2-AJ-10 則6、US2-AJ-13 則2、US2-API-13 則4;`prototype/chat.html` § `[data-state="turn-error"]`、`[data-state="turn-interrupted"]`;`tasks.md` § T241b | T068b 要求 `turn-error`「照 `prototype/chat.html` 寫成固定開頭加後端 `error.message` 的通用說法」,檔案範圍只有 `js/chat.js`;US2-AJ-10 則6 要畫面含「處理時發生錯誤」,這段字只能來自 `MESSAGES` 的 `OLLAMA_SERVER_ERROR`,但新增它的 T043b 只寫「加進 `MESSAGES`」、沒有指定文字,US2-API-13 則4 也只驗「是中文」;`OLLAMA_STREAM_INTERRUPTED`(T047b;US2-AJ-13 則2「回應到一半就斷了」)同樣。T241b 已替另外三個代碼指定照原型文字,這兩個沒有。照 tasks 做,T043b 寫的文字不一定含原型的那句,T068b 的綠燈得去改不在它檔案範圍的 `errors.py`(考慮過 HIGH:US2-AJ-10 會紅燈,不會靜默做錯) | `/tasks` |

### 追溯缺口

只列有缺口的需求;其餘需求從規格檔到任務都接得上。

| 需求 | 規格檔元素 | 任務 | 缺口 |
|---|---|---|---|
| FR-008 對話中斷的原因(串流前 502 的四個代碼、串流中的伺服器錯誤與中斷) | `ui.openapi.yaml` § `chat` 502、`x-stream-error-codes`;`prototype/chat.html` § `turn-unavailable`、`turn-error`、`turn-interrupted` | T043b、T047b(沒指定文字)、T068b、T243b、T244b | A39、A40 |

### 修正順序

1. `/ui-plan` 改 `prototype/chat.html`:`turn-unavailable` 的說明改成「沒有送出:」加後端 `message` 的寫法,`CUT.unavailable` 改成不指名原因的標示(例如「沒有回覆:Ollama 暫時無法使用」)(A39)
2. `/testplan` 在 US2-AJ-14 補一個 502 不是 `OLLAMA_UNREACHABLE` 的情況(例如遠端回 500 的 `OLLAMA_SERVER_ERROR`),斷言畫面顯示那個代碼的 `message`、不含「連不到」(照 Q73 在原案例上補,A39)
3. `/tasks`:T043b、T047b 指定 `OLLAMA_SERVER_ERROR`、`OLLAMA_STREAM_INTERRUPTED` 的 `MESSAGES` 文字照 `prototype/chat.html` 的 `turn-error`、`turn-interrupted`(A40),並照第 2 步更新 T244a、T244b 的描述
4. 重跑 `/analyze`
