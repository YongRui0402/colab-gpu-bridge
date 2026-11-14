# 跨產出物分析: 佇列隨工作階段清空、測試對話框、Hugging Face 模型來源與可編輯的精選清單

**Feature**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md) | **Constitution**: `constitution/`

## 判定

**最新一輪:第 1 輪(2026-11-14)— ⛔ 不能進 `/implement`**

還沒解決的 HIGH:A1~A12、A14~A18。最上游的是 `research.md` 停在 plan.md 決定之前的說法(A5、A6、A2 的 R7),其次是合約與 store.dbml 沒跟上 testplan 階段的決定(A2、A7、A14~A18)、原型與合約的錯誤代碼對不上(A9、A10、A12)、testplan 有案例鋪不出來或違反自己的護欄(A8、A9、A11),以及 tasks 故事 1 沒有任務建 T013b 要用的表(A1)。另有 MEDIUM 10 個、LOW 11 個,不擋實作,建議跟著修正順序一起改。

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
| `分身決策紀錄.md`(D1~D80,對照 `plan.md` § 待決問題 Q1~Q66;依使用者 2026-11-14 授權由分身代答) | 各步驟的 kevin-twin 代答 |
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
| A4 | 遺漏 | HIGH | `plan.md` § 待決問題 Q61;`testplan.md` § US2-API-12、US2-API-13;`tasks.md`(無對應任務);`src/cgb/domain/errors.py` § `OLLAMA_UNREACHABLE`、`OLLAMA_BAD_RESPONSE`、`OLLAMA_TIMEOUT` | Q61(D75)決定對話頁沿用的 `OLLAMA_*` 說明改成兩邊都通的通用說法;現行三句都寫「無法確認哪些模型已經下載」,testplan 只驗「說明是中文」,tasks 沒有任務改這三句。決定沒有落地 | `/testplan` |
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
