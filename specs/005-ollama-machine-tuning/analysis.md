# 跨產出物分析: 依機器配置調整遠端 Ollama 的設定,並在 UI 顯示與修改

**Feature**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md) | **Constitution**: `constitution/`

## 判定

**最新一輪:第 2 輪(2026-11-15)— ✅ 可以進 `/implement`**

沒有未解決的 CRITICAL 或 HIGH;第 1 輪的 A1~A3、A5~A7 已修正,SC-004 已澄清(D49)。剩 2 個 LOW(A4 仍存在、新的 A8),不擋實作,建議實作前順手修掉。

## 檢查範圍

| 產出物 | 產出的步驟 |
|---|---|
| `spec.md` | `/specify`、`/clarify-over-specs` |
| `research.md`、`techstack.md` | `/technical-research` |
| `plan.md` | `/system-analysis` |
| `contracts/colab-cli.openapi.yaml`、`contracts/ui.openapi.yaml`、`contracts/ui-events.asyncapi.yaml` | `/api-plan` |
| `contracts/store.dbml` | `/data-plan` |
| `prototype/`(`index.html`、`history.html`、`states.html`、`mock.js`、`style.css`) | `/ui-plan` |
| `testplan.md` | `/testplan` |
| `tasks.md` | `/tasks` |
| `constitution/_shared/語言.md` | `/constitution` |

決定的出處是 `plan.md` § 待決問題 Q1~Q63 與 `分身決策紀錄.md`(D1~D47);這一輪不質疑決定本身,只檢查決定有沒有正確寫進各產出物。

---

## 第 1 輪(2026-11-15)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `specify/scripts/check_spec.py` | ✅ 通過 |
| `system-analysis/scripts/check_plan.py` | ✅ 通過(帶 `--previous-plan specs/004-chat-hf-curated-queue/plan.md`) |
| `testplan/scripts/check_testplan.py` | ✅ 通過 |
| `tasks/scripts/check_tasks.py` | ✅ 通過 |

### 問題

| ID | 類別 | 嚴重度 | 位置 | 摘要 | 回哪一步 |
|---|---|---|---|---|---|
| A1 | 矛盾 | HIGH | `research.md` § R1;`contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post`;`plan.md` § Source Code;`plan.md` § 待決問題 Q5 | R1 決策寫「pid 檔不存在……改用 `pkill -f "^ollama serve"` 停掉」,替代方案也寫「`pkill` 只當備援」;Q5 決定 b(D16),合約 `restartOllama` (c) 已改成「`pgrep -f "^ollama serve"` 找出符合的 pid,對每一個 pid 的行程群組同樣送 `SIGTERM`、10 秒後仍在就送 `SIGKILL`」,`tasks.md` T109b 也照 `pgrep` 做。R1 沒有跟著修(修訂紀錄只記了 R9),`plan.md` Source Code 樹的 `restart_ollama.py` 仍寫「pid 檔,備援 pkill」。照 R1 做,`pkill -f` 只停 serve 本身、群組裡載入模型的子行程留著(testplan US3-CLI-10 要抓的錯正是這個),行為不同 | `/technical-research` |
| A2 | 矛盾 | HIGH | `contracts/ui.openapi.yaml` § `components.schemas.TuningRecord`;`contracts/ui.openapi.yaml` § `info.x-apply-flow`;`contracts/store.dbml` § `Project colab_gpu_bridge`;`testplan.md` § US3-API-02;`prototype/mock.js` § `advanceApply`;`tasks.md` § T148b | 重啟成功、進入 `reloading_models` 時(這一筆仍是 `in_progress`)各處寫法不同:`x-apply-flow` (4) 與 asyncapi `sendSessionUpdated` 寫「重啟成功:`Session.ollama.tuning`、`machine` 換成這次 S1 回報的值」,testplan US3-API-02 則5 斷言重新載入中 `ollama.tuning.numParallel` 為 `{"value": 4, "source": "manual"}`;`TuningRecord.machine`、`tuning` 卻寫「`in_progress`、`failed` 時為 null」,而 store.dbml 寫入時機寫「重啟成功寫入 machine 與 tuning 的欄位」(這時 `result` 仍是 `in_progress`),原型 `advanceApply` 也把 `tuning` 寫進 `in_progress` 的那一筆,`lastApply` 會帶非 null 的 `tuning`;store.dbml「不建表的資料」又寫 `Session.ollama` 的 `tuning` 只取 `result` 為 `applied`、`fell_back_to_auto` 或 `probed_at` 不為 NULL 的 `interrupted` 那一列,不含 `in_progress`,照它推導,重新載入中顯示的是重啟前的舊設定,US3-API-02 則5 會失敗。T148b 只寫「目前生效的設定取最新一筆有讀到設定的紀錄(含 `interrupted`)」,沒有寫 `in_progress` 算不算,做法不確定 | `/api-plan`、`/data-plan` |
| A3 | 矛盾 | MEDIUM | `plan.md` § Source Code;`contracts/store.dbml` § `Table runtime_type_tunings`;`contracts/store.dbml` § `Table session_tuning_models` | Source Code 樹的 `repos/` 寫「E4:runtime_type_tuning、session_tunings」;store.dbml 的表名是 `runtime_type_tunings`(Q26、D37 照 S4 改成複數),另有 `session_tuning_models`,樹裡都沒有。同一張表在兩份產出物叫法不同 | `/system-analysis` |
| A4 | 矛盾 | LOW | `research.md` § R9;`research.md` § 修訂紀錄;`contracts/store.dbml` § `Table session_tuning_models`;`research.md` § R1;`techstack.md` § 新引入與沿用;`contracts/colab-cli.openapi.yaml` § `info`(共用約定 13-1) | R9 決策只列 `runtime_type_tunings`、`session_tunings` 兩張新表,同檔修訂紀錄、store.dbml 與 techstack 一覽都是三張(多 `session_tuning_models`);Q2 決定 c(D13)後,合約共用約定 13-1 新增設定檔 `/root/cgb-ollama-tuning.json`,R1 決策與 techstack「新引入」只列 pid 檔。規格檔與任務都照合約寫,照哪一份做行為都一樣 | `/technical-research` |
| A5 | 矛盾 | LOW | `testplan.md` § US3-API-28;`contracts/ui.openapi.yaml` § `info.x-applying-state`;`plan.md` § 待決問題 Q33 | US3-API-28 則4 仍註記「和 `info.x-apply-flow` (5) 的 `failed` 不一致,見待決問題」;Q33 已決定 a(D43),`x-applying-state` (4) 已改成「`startOllama` 失敗時……這一次套用仍記為 `interrupted`(不是 `failed`)」。斷言值 `interrupted` 本身一致,只有備註過時 | `/testplan` |
| A6 | 矛盾 | LOW | `spec.md` § FR-013;`spec.md` § 邊界情況;`contracts/ui.openapi.yaml` § `info.x-apply-flow`;`contracts/colab-cli.openapi.yaml` § `paths./exec/restart-ollama.post` | spec 已改寫成「仍失敗就照 FR-013 結束工作階段」與「結束工作階段(結束原因「重啟 Ollama 失敗」)」;`x-apply-flow` (3) 引用的邊界情況仍是「仍失敗就照 001 的失聯處理」,(5) 寫「FR-013「失敗時照 001 的失聯處理」」,`restartOllama` 描述寫「第二次仍失敗照 001 的失聯處理。實際流程由 S3 定」。實際定義的流程(`lost`、`OLLAMA_RESTART_FAILED`、釋放執行環境)與改寫後的 spec 一致,只有引文過時 | `/api-plan` |
| A7 | 遺漏 | LOW | `spec.md` § 關鍵實體;`contracts/ui.openapi.yaml` § `components.schemas.TuningResult`;`contracts/ui.openapi.yaml` § `info.x-applying-state` | spec「Ollama 設定」的結果只列「……或後端停機而中斷」;`TuningResult.interrupted` 是「套用到一半被結束或後端停機」,`x-applying-state` (3) 讓 `endSession` 在套用中受理並記為 `interrupted`(testplan US3-API-26 有測)。下游已一致,只有 spec 的實體說明少了「套用中被結束」 | `/specify` |

### 追溯缺口

只列有缺口的需求;其餘需求從規格檔到任務都接得上。

| 需求 | 規格檔元素 | 任務 | 缺口 |
|---|---|---|---|
| FR-004、FR-015 套用中(重新載入模型時)顯示的設定 | `ui.openapi.yaml` § `OllamaStatus.tuning`、`TuningRecord`;`store.dbml` § `Project`(`Session.ollama` 的推導,兩邊寫法不同) | T121b、T148b | A2 |

### 轉交 `/clarify-over-specs`

單份文件內的模糊不屬於本步驟,標記後轉交:

| 位置 | 為什麼要澄清 |
|---|---|
| `spec.md` § SC-004 | 後半句寫「替身讓新設定重啟失敗時,改回自動值到回到就緒在 180 秒內」,可以讀成從開始改回自動值才起算;同一份 spec 的 NFR-002 寫「從確認套用到工作階段回到就緒……180 秒內」。testplan US3-API-31 則2、US3-CLI-19 則2 照 NFR-002 從確認起算,SC-004 的字面沒辦法據以判定這兩個案例量的是不是同一段時間 |

### 修正順序

1. `/specify` 在關鍵實體「Ollama 設定」的結果補上「套用中被結束」(A7);`/clarify-over-specs` 澄清 SC-004 改回自動值那段的起算點
2. `/technical-research` 把 R1 決策與替代方案改成 `pgrep` 找 pid 再停行程群組(A1),R1 與 techstack「新引入」補設定檔 `/root/cgb-ollama-tuning.json`、R9 決策補 `session_tuning_models`,寫進修訂紀錄(A4)
3. `/system-analysis` 修 Source Code 樹:`restart_ollama.py` 的備援改成 `pgrep`(A1 的下游)、`start_ollama.py` 補設定檔、`repos/` 的表名改成 `runtime_type_tunings`、`session_tunings`、`session_tuning_models`(A3)
4. `/api-plan` 改 `TuningRecord.machine`、`tuning` 的描述:重啟成功之後(`reloading_models` 期間)`in_progress` 那一筆也有值(A2),並把 `x-apply-flow` (3)(5)、`restartOllama` 描述裡的「照 001 的失聯處理」改成改寫後 FR-013 的寫法(A6);`/data-plan` 把 `Session.ollama` 的推導改成也取「`in_progress` 而 `probed_at` 不為 NULL」的那一列(A2)
5. `/testplan` 刪 US3-API-28 則4 過時的備註(A5);照第 4 步的 A2 寫法,在 US3-API-02 補斷言重新載入中的 `lastApply.tuning`
6. `/tasks` 照第 4、5 步更新 T121b、T148b 的 ⚙ 與目前生效設定的取法(A2),並涵蓋第 5 步補的斷言
7. 重跑 `/analyze`

---

## 第 2 輪(2026-11-15)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `specify/scripts/check_spec.py` | ✅ 通過(第 1 輪的結果;這一輪的修正只改敘述文字,沒有重跑前置檢查) |
| `system-analysis/scripts/check_plan.py` | ✅ 通過(同上) |
| `testplan/scripts/check_testplan.py` | ✅ 通過(同上) |
| `tasks/scripts/check_tasks.py` | ✅ 通過(同上) |

### 上一輪的問題

| ID | 狀態 | 依據 |
|---|---|---|
| A1 | ✅ 已修正 | `research.md` § R1 改成「先用 `pgrep -f "^ollama serve"` 找出 pid,再對每個 pid 的行程群組送 `SIGTERM`/`SIGKILL`(plan Q5、D16)」,替代方案同步改;`plan.md` § Source Code 的 `restart_ollama.py` 改成「停掉 ollama serve 的行程群組(pid 檔,備援 pgrep)」,與 `colab-cli.openapi.yaml` § `restartOllama` (c)、`tasks.md` T109b 一致 |
| A2 | ✅ 已修正 | D48 選「重新載入中顯示新設定」:`ui.openapi.yaml` § `TuningRecord.machine`、`tuning` 改成「`in_progress` 而重啟還沒成功時、`failed` 時為 null,重啟成功、進入 `reloading_models` 後就有值」;`store.dbml` § Project 的 `Session.ollama` 推導加上「result 為 in_progress 而 tuning 不為 NULL」;`testplan.md` US3-API-02 則5 補斷言 `lastApply.tuning`;`tasks.md` T121b、T148b 寫明取 `in_progress` 那一筆;與 `x-apply-flow` (4)、asyncapi `sendSessionUpdated`、`prototype/mock.js` `advanceApply` 一致 |
| A3 | ✅ 已修正 | `plan.md` § Source Code 的 `repos/` 改成 `runtime_type_tunings`、`session_tunings`、`session_tuning_models`,與 `store.dbml` 一致 |
| A4 | ❌ 仍存在 | `research.md` § R9 已補 `session_tuning_models`、§ R1 已補設定狀態檔,`techstack.md` § 一覽也補了;但 `techstack.md` § 新引入與沿用的「新引入」仍只列 `restart_ollama.py` 與 pid 檔,沒有 `/root/cgb-ollama-tuning.json`(合約共用約定 13-1)。照哪一份做行為都一樣,維持 LOW |
| A5 | ✅ 已修正 | `testplan.md` US3-API-28 則4 的備註改成「store.dbml 的寫入時機、`info.x-applying-state` (4),plan Q33」,不再說不一致 |
| A6 | ✅ 已修正 | `ui.openapi.yaml` § `info.x-apply-flow` (3)(5) 改引「照 FR-013 結束工作階段」「結束工作階段(結束原因「重啟 Ollama 失敗」)」;`colab-cli.openapi.yaml` § `restartOllama` 改成「由呼叫者照 spec FR-013 結束工作階段(`OLLAMA_RESTART_FAILED`)」 |
| A7 | ✅ 已修正 | `spec.md` § 關鍵實體「Ollama 設定」的結果改成「……或套用中被結束、後端停機而中斷」,與 `TuningResult.interrupted` 一致 |
| SC-004 | ✅ 已澄清 | D49 選從確認套用起算:`spec.md` § SC-004 改成「替身讓新設定重啟失敗時,從確認到回到就緒在 180 秒內」,與 NFR-002、testplan US3-API-31 則2、US3-CLI-19 則2 一致 |

### 新問題

| ID | 類別 | 嚴重度 | 位置 | 摘要 | 回哪一步 |
|---|---|---|---|---|---|
| A8 | 矛盾 | LOW | `contracts/ui.openapi.yaml` § `components.schemas.OllamaStatus`;`contracts/store.dbml` § `Project colab_gpu_bridge` | 修 A2 時 store.dbml 的 `Session.ollama` 推導加上了「result 為 in_progress 而 tuning 不為 NULL」;`OllamaStatus.tuning` 的括號仍只列「紀錄裡最新一筆有 `tuning` 的 `applied`、`fell_back_to_auto`,或恢復時讀到設定的 `interrupted`」,沒有 `in_progress`。同一句後半已寫「套用中仍是重啟前的那一組,重啟成功才換成新的」,照哪一份做行為都一樣,只有列舉不齊 | `/api-plan` |

### 修正順序

1. `/technical-research` 在 `techstack.md` § 新引入與沿用補上設定狀態檔 `/root/cgb-ollama-tuning.json`(A4)
2. `/api-plan` 在 `OllamaStatus.tuning` 的列舉補上「重啟成功、重新載入中的 `in_progress`」(A8)
3. 重跑 `/analyze`
