# 跨產出物分析: 官方模型庫的錯誤處理

**Feature**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md) | **Constitution**: `constitution/`

## 判定

**最新一輪:第 2 輪(2026-11-13)— ✅ 可以進 `/implement`**

沒有未解決的 CRITICAL 或 HIGH;第 1 輪的 A1、A2、A4 已修正,剩 2 個 LOW(A3、A5),都是 `plan.md` 的說明沒跟上,不擋實作,可在實作前順手由 `/system-analysis` 補上。

## 檢查範圍

| 產出物 | 產出的步驟 |
|---|---|
| `spec.md` | `/specify` |
| `research.md`、`techstack.md` | `/technical-research` |
| `plan.md` | `/system-analysis` |
| `contracts/model-library.openapi.yaml`、`contracts/ui.openapi.yaml` | `/api-plan` |
| `testplan.md` | `/testplan` |
| `tasks.md` | `/tasks` |
| `constitution/_shared/語言.md` | `/constitution` |

---

## 第 1 輪(2026-11-13)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `specify/scripts/check_spec.py` | ✅ 通過 |
| `system-analysis/scripts/check_plan.py` | ✅ 通過 |
| `testplan/scripts/check_testplan.py` | ✅ 通過 |
| `tasks/scripts/check_tasks.py` | ✅ 通過(168 個任務、11 列介面覆蓋、80 個行為案例與 2 個量測案例都有任務) |

### 問題

| ID | 類別 | 嚴重度 | 位置 | 摘要 | 回哪一步 |
|---|---|---|---|---|---|
| A1 | 無法實作 | HIGH | `research.md` § R1;`contracts/model-library.openapi.yaml` § `info.x-transport-error-rules`;`plan.md` § 待決問題 Q10;`testplan.md` § US2-LIB-08;`spec.md` § FR-006 | R1 的決策只寫「`httpx.TimeoutException` 歸 `LIBRARY_TIMEOUT`,其餘 `httpx.TransportError` 歸 `LIBRARY_UNREACHABLE`」,並說「兩個 except 就涵蓋全部傳輸層失敗」;合約 `x-transport-error-rules` 也只列這兩類。Q10 已決定 `httpx.DecodingError`(不是 `TransportError`)以 `httpx.HTTPError` 兜底歸 `LIBRARY_BAD_RESPONSE`,US2-LIB-08 照它斷言,但 Q10 的決定欄自己寫「R1 與合約的補句待後續處理」。照 R1 與合約實作,`DecodingError` 會越過轉接層(違反 FR-006「任何底層程式庫的例外都不得越過轉接層往上拋」),和照 testplan 做出來的行為不同 | `/technical-research`、`/api-plan` |
| A2 | 無法實作 | HIGH | `research.md` § R3、R4;`tasks.md` § T009a~T012a、T017a、T028a~T030a、T032a、T038a、T039a、T041a、T051a~T056a、T071a~T074a、T085a;`testplan.md` § US1-LIB-09~US1-LIB-12、US1-LIB-17、US1-API-01~US1-API-03、US1-API-05、US1-API-11、US1-API-12、US1-API-14、US2-LIB-02~US2-LIB-07、US2-API-05~US2-API-08、US2-AJ-03 | 這些紅燈任務都寫「執行確認它因為『…』這類實作而失敗」,但 R4 的實測表寫 001 的 `Library.search` 對 `LIBRARY_UNREACHABLE`、`LIBRARY_SERVER_ERROR`、`LIBRARY_BAD_RESPONSE` 已經回 502、`_sized` 對 `LIBRARY_NOT_FOUND` 已回 404、`LIBRARY_CLOUD_ONLY` 已回 422;R3 寫「`get_manifest` 已經會分 404、5xx、非預期與格式不符」並決定 manifest 判定「保留不動」;US1-LIB-09~12、US1-LIB-17、US1-API-05、US1-API-11 是 testplan 寫明的 001 正常結果,其餘(US1-API-12、US1-API-14、US2-API-07、US2-API-08、US2-AJ-03)讀 `src/cgb/services/` 推斷也已滿足(未執行)。現有程式一寫完測試就綠,`/tdd` 紅燈步驟「不是斷言失敗 → 回 Phase 2 Step 1 重寫測試」會一直繞回去,任務照寫的做不完 | `/tasks` |
| A3 | 遺漏 | LOW | `plan.md` § Project Structure(Source Code 樹);`tasks.md` § T031b、T046a、T087、T088 | Source Code 樹的 `tests/` 只列 `integration/` 的三個檔、`fakes/` 與 `realrun/test_us3_lib_05.py`;tasks 另外新增 `tests/integration/test_library_cross.py`(Q18)、`tests/integration/test_002_g_01.py`(Q16)、`tests/integration/test_002_g_02.py`(Q17,取代 Source Code 樹寫的 `realrun/test_us3_lib_05.py` 跑 SC-003),並改 `tests/e2e/test_locale.py`;照哪一份做出來的行為都一樣,只是結構說明沒跟上 | `/system-analysis` |
| A4 | 矛盾 | LOW | `contracts/ui.openapi.yaml` § `info.x-library-error-message`;`research.md` § R4;`plan.md` § 待決問題 Q13 | 合約寫四個代碼的說明都「帶『也可以從精選清單挑選或直接輸入名稱』的退路」,R4 也寫「同其他 `LIBRARY_*` 帶『也可以…』」;Q13 已決定 `LIBRARY_BAD_RESPONSE` 現有的「可以從精選清單挑選或直接輸入名稱」不改、只斷言退路片語。實作後這一句和合約字面差一個「也」字,退路的意思相同 | `/api-plan` |

### 追溯缺口

只列有缺口的需求;其餘需求從規格檔到任務都接得上。

| 需求 | 規格檔元素 | 任務 | 缺口 |
|---|---|---|---|
| FR-006 例外不越過轉接層(`DecodingError`) | `model-library.openapi.yaml` § `info.x-transport-error-rules`(沒有寫到) | T057a、T057b | A1 |

### 修正順序

1. `/technical-research` 在 `research.md` § R1 補上 `httpx.DecodingError` 等非傳輸層的 `httpx.HTTPError` 以兜底歸 `LIBRARY_BAD_RESPONSE`(Q10 的決定),並記進修訂紀錄(A1)
2. `/api-plan` 在 `model-library.openapi.yaml` § `info.x-transport-error-rules` 補同一句(A1);可一併把 `ui.openapi.yaml` § `info.x-library-error-message` 的「也可以」改成不限定字面的退路(A4)
3. `/system-analysis` 把 A3 列的測試檔補進 Source Code 樹(A3,不擋實作,可留到之後)
4. `/tasks` 把 A2 列的紅燈任務改成現有程式已滿足時也做得完的寫法,綠燈任務跟著改,重跑 `check_tasks.py`(A2)
5. 重跑 `/analyze`

---

## 第 2 輪(2026-11-13)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `specify/scripts/check_spec.py` | ✅ 通過 |
| `system-analysis/scripts/check_plan.py` | ✅ 通過 |
| `testplan/scripts/check_testplan.py` | ✅ 通過 |
| `tasks/scripts/check_tasks.py` | ✅ 通過(168 個任務、11 列介面覆蓋,0 個不符項) |

### 上一輪的問題

| ID | 狀態 | 依據 |
|---|---|---|
| A1 | ✅ 已修正 | `research.md` § R1 的決策補上第三個 `except httpx.HTTPError`,把 `httpx.DecodingError` 歸 `LIBRARY_BAD_RESPONSE`,理由補 `probe_decoding.py` 實測,修訂紀錄記 2026-11-13;`model-library.openapi.yaml` § `info.x-transport-error-rules` 補同一句;和 `testplan.md` § US2-LIB-08、`tasks.md` § T057a、T057b 一致 |
| A2 | ✅ 已修正 | `tasks.md` 的 23 組紅綠(T009~T012、T017、T028~T030、T032、T038、T039、T041、T051~T056、T071~T074、T085)改成「先確認通過,再暫時改成『要抓的錯』確認斷言失敗後撤回;一執行就失敗則當一般紅燈」,綠燈確認不需改程式碼(`plan.md` § 待決問題 Q19);`LIBRARY_STATUS`、`library_error` 的建立移到 T031b |
| A3 | ❌ 仍存在 | `plan.md` § Project Structure 的 Source Code 樹仍沒列 `tests/integration/test_library_cross.py`、`test_002_g_01.py`、`test_002_g_02.py` 與 `tests/e2e/test_locale.py`;LOW,不擋實作 |
| A4 | ✅ 已修正 | `ui.openapi.yaml` § `info.x-library-error-message` 改成帶「從精選清單挑選或直接輸入名稱」的退路,並註明 `LIBRARY_BAD_RESPONSE` 沿用 001 沒有「也」字的句子(`plan.md` § 待決問題 Q13) |

### 新問題

| ID | 類別 | 嚴重度 | 位置 | 摘要 | 回哪一步 |
|---|---|---|---|---|---|
| A5 | 矛盾 | LOW | `plan.md` § 待決問題 Q10;`research.md` § R1;`contracts/model-library.openapi.yaml` § `info.x-transport-error-rules` | Q10 的決定欄仍寫「R1 與合約的補句待後續處理」,R1 與合約這一輪已補上(A1);只是狀態說明過期,照哪一份做出來的行為都一樣 | `/system-analysis` |

### 修正順序

1. `/system-analysis` 把 A3 列的測試檔補進 Source Code 樹、把 Q10 的決定欄改成「已補進 R1 與合約」(A3、A5;都不擋實作)
2. 重跑 `/analyze`
