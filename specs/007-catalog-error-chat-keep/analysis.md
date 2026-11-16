# 跨產出物分析: 模型目錄讀不到時回正確的錯誤,對話紀錄保留到工作階段結束

**Feature**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md) | **Constitution**: `constitution/`

## 判定

**最新一輪:第 2 輪(2026-11-16)— ✅ 可以進 `/implement`**

第 1 輪的 A1、A2(都是 LOW)已修正;這一輪沒有新問題,沒有未解決的 CRITICAL 或 HIGH。

## 檢查範圍

| 產出物 | 產出的步驟 |
|---|---|
| `spec.md` | `/specify` |
| `research.md`、`techstack.md` | `/technical-research` |
| `plan.md` | `/system-analysis` |
| `contracts/ui.openapi.yaml` | `/api-plan` |
| `prototype/` | `/ui-plan` |
| `testplan.md` | `/testplan` |
| `tasks.md` | `/tasks` |
| `constitution/_shared/語言.md` | `/constitution` |

---

## 第 1 輪(2026-11-16)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `specify/scripts/check_spec.py` | ✅ 通過 |
| `system-analysis/scripts/check_plan.py` | ✅ 通過(帶 `--previous-plan ../006-agent-client-connect/plan.md`) |
| `testplan/scripts/check_testplan.py` | ✅ 通過 |
| `tasks/scripts/check_tasks.py` | ✅ 通過(139 個任務,錨點、介面與案例覆蓋 0 個不符) |

### 問題

| ID | 類別 | 嚴重度 | 位置 | 摘要 | 回哪一步 |
|---|---|---|---|---|---|
| A1 | 矛盾 | LOW | `spec.md` § 假設(修訂 004 FR-008 那一條);`tasks.md` § T054b;`testplan.md` § US2-AJ-13 | spec 假設與 T054b 都寫刪除的 004 `test_回覆途中在另一個分頁變更類型_保留已收到的內容並說明正在變更類型`「改由 US2-AJ-13 涵蓋」,但 US2-AJ-13 的假如是「已有兩問兩答」、沒有回覆在途中;回覆途中變更類型這個組合沒有 007 的專門案例,清除走的是和 US2-AJ-14(回覆途中使用者結束)同一段 `sessionUpdated` 與「清空後不再寫入」,實作的行為不受影響,是說明對不上 | `/specify`、`/tasks` |
| A2 | 遺漏 | LOW | `plan.md` § 端點盤點 E2;`testplan.md` § US2-API-09;`contracts/ui.openapi.yaml` § `info.description`、`paths./events.get` | testplan 在 E2 節以 US2-API-09 驗 NFR-002、SC-004,合約的 `info.description` 與 `subscribeEvents` 也寫明 E2 不收、不回、不推送對話內容(NFR-002);plan.md 端點盤點 E2 的需求出處只有 FR-001、FR-002、FR-006、NFR-001、SC-001,沒有 NFR-002、SC-004。任務照 testplan 排,行為不受影響 | `/system-analysis` |

### 修正順序

1. `/specify` 改 spec.md 假設裡修訂 004 FR-008 那一條的涵蓋說明:變更類型的清除由 US2-AJ-13、回覆途中結束後清除且不復活由 US2-AJ-14 涵蓋,回覆途中變更類型走同一段程式、沒有專門案例(A1)
2. `/system-analysis` 把 NFR-002、SC-004 補進 plan.md 端點盤點 E2 的需求出處(A2)
3. `/tasks` 把 T054b 的涵蓋說明改成和第 1 步一致(A1),重跑 `check_tasks.py`
4. 重跑 `/analyze`

---

## 第 2 輪(2026-11-16)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `specify/scripts/check_spec.py` | ✅ 通過 |
| `system-analysis/scripts/check_plan.py` | ✅ 通過(帶 `--previous-plan ../006-agent-client-connect/plan.md`) |
| `testplan/scripts/check_testplan.py` | ✅ 通過 |
| `tasks/scripts/check_tasks.py` | ✅ 通過(任務數仍是 139,0 個不符) |

### 上一輪的問題

| ID | 狀態 | 依據 |
|---|---|---|
| A1 | ✅ 已修正 | `spec.md` § 假設(修訂 004 FR-008 那一條)與 `tasks.md` § T054b 改寫:變更類型的清除由 US2-AJ-13 驗(沒有回覆在途中),回覆途中使用者結束由 US2-AJ-14 驗,回覆途中變更類型沒有專門案例、走同一段清除;和 `testplan.md` § US2-AJ-13、US2-AJ-14 的假如一致 |
| A2 | ✅ 已修正 | `plan.md` § 端點盤點 E2 的需求出處補上 NFR-002、SC-004,和 `testplan.md` § US2-API-09、`contracts/ui.openapi.yaml` § `info.description` 一致 |

### 修正順序

1. 沒有要回修的產出物;下一步進 `/implement`
2. 重跑 `/analyze`(只在實作前又改了 spec package 時)
