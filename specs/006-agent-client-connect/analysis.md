# 跨產出物分析: 讓 opencode 與 pi 輕鬆接上 Colab 上的 Ollama

**Feature**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md) | **Constitution**: `constitution/`

## 判定

**最新一輪:第 2 輪(2026-11-16)— ✅ 可以進 `/implement`**

第 1 輪的 A1~A4 已修正(A1、A4 改 testplan 與 tasks,A2 改 research R8 與本機實跑的 context,A3 改原型文字);A5~A7 在第 1 輪已順手修掉。修正後 spec、plan、testplan、tasks 與原型的檢查腳本都通過,沒有新的問題。

## 檢查範圍

| 產出物 | 產出的步驟 |
|---|---|
| `spec.md` | `/specify`、`/clarify-over-specs` |
| `research.md`、`techstack.md` | `/technical-research` |
| `plan.md` | `/system-analysis` |
| `contracts/ollama-compat.openapi.yaml`、`contracts/ui.openapi.yaml` | `/api-plan` |
| `prototype/`(`connect.html`、`index.html`、`states.html`、`mock.js`、`style.css`) | `/ui-plan` |
| `deploy/compose.yaml`、`deploy/.env.example` | `/deploy-plan` |
| `testplan.md` | `/testplan` |
| `tasks.md` | `/tasks` |
| `constitution/_shared/語言.md` | `/constitution` |

決定的出處是 `plan.md` § 待決問題 Q1~Q28 與 `分身決策紀錄.md`。這一輪不質疑決定本身,只檢查決定有沒有正確寫進各產出物。

---

## 第 1 輪(2026-11-16)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `specify/scripts/check_spec.py` | ✅ 通過 |
| `system-analysis/scripts/check_plan.py` | ✅ 通過(帶 `--previous-plan specs/005-ollama-machine-tuning/plan.md`) |
| `testplan/scripts/check_testplan.py` | ✅ 通過 |
| `tasks/scripts/check_tasks.py` | ✅ 通過(順手修正之後重跑,仍然通過) |

### 問題

| ID | 類別 | 嚴重度 | 位置 | 摘要 | 回哪一步 |
|---|---|---|---|---|---|
| A1 | 無法實作 | HIGH | `testplan.md` § US1-AJ-05;`tasks.md` § T029a、T029b、T021b | T029a 要斷言片段鍵名 `contextWindow` 與 `reserveTokens`,但 Q23 的最小版本(T021b、T029b)不會產生這兩個鍵,T029b 沒辦法讓 T029a 變綠 | `/tasks` |
| A2 | 矛盾 | HIGH | `research.md` § R2、R4、R8;`testplan.md` § G-01;`tasks.md` § T048 | 依片段規則,G-01 的 context 10240 時 `limit.output` 為 4096,可用輸入只剩 6,144,小於 R4 量到的 opencode 第一個請求 6,469;R2 只實測過 output 2048 的組合,SC-001 可能過不了 | `/technical-research` |
| A3 | 矛盾 | MEDIUM | `testplan.md` § US1-AJ-03、US1-AJ-04、US3-AJ-03;`prototype/connect.html` § `[data-state="no-session"]`、`[data-state="empty-catalog"]`、`[data-part="unknown-notice"]`;`spec.md` § 使用者故事 1 驗收情境 3 | 三處畫面文字和 testplan、spec 不同(「沒有可用的」對「沒有就緒的」、「先到「下載模型」」對「先到模型頁下載模型」、讀不到設定的說明),綠燈時得二選一 | `/ui-plan`、`/testplan` |
| A4 | 遺漏 | MEDIUM | `research.md` § 待驗證(R5);`testplan.md` § G-04;`tasks.md` § T047 | R5 要在 T4 驗 32768,G-04 與 T047 只寫「16384 以上」,32768 可能一直沒驗到 | `/testplan` |
| A5 | 矛盾 | LOW | `testplan.md` § US1-API-05、US1-API-06;`contracts/ui.openapi.yaml` § `info.x-reason-rule` | testplan 寫「`snippets` 的三段都是 null」,合約是 `snippets` 本身為 null。**本輪已修** | `/testplan` |
| A6 | 矛盾 | LOW | `plan.md` § Source Code;`plan.md` § 待決問題 Q21 | 原始碼樹列了 `config.py`,和 Q21 決定不建 `config.py` 不一致。**本輪已修** | `/system-analysis` |
| A7 | 矛盾 | LOW | `tasks.md` § T020a;`../001-session-model-catalog/plan.md` § 待決問題 Q24 | 依據引用「001 Q24」不對,真正的依據是 `IdleHook` 只掛在 `src/cgb/ollama_compat/__init__.py`。**本輪已修** | `/tasks` |

### 已確認一致的重點

| 檢查項目 | 結果 |
|---|---|
| `ConnectInfo`、`snippets`、`reason` 的欄位名稱(合約與 tasks) | 一致 |
| 原型用的欄位名稱(`minContext`、`suggestedContext`)與片段由前端組 | 和合約不同,但 Q16 已決定以合約為準,T025b 明寫照 `ConnectInfo`,不列為問題 |
| FR-013 與 Q15 的 `maxTokens`、`reserveTokens` 規則 | research R3、`ui.openapi.yaml`、testplan US2-API-02 與 US3-API-04、tasks T032、T041 一致 |
| Q18 改寫 001 的三處舊測試 | 已排進 T001b,三處在 `tests/` 實際存在 |
| 憲法〈語言〉 | 沒有違反 |

## 第 2 輪(2026-11-16)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `technical-research/scripts/check_research.py` | ✅ 通過 |
| `ui-plan/scripts/check_prototype.py`(S4) | ✅ 通過 |
| `testplan/scripts/check_testplan.py` | ✅ 通過 |
| `tasks/scripts/check_tasks.py` | ✅ 通過 |

### 上一輪的問題

| ID | 狀態 | 依據 |
|---|---|---|
| A1 | ✅ 已修正 | `testplan.md` § US1-AJ-05 則2 與 `tasks.md` § T029a 只斷言故事 1 的最小版本做得到的鍵(opencode 的 `provider`、`baseURL`、`limit`,pi 的 `providers`、`baseUrl`);`contextWindow`、`reserveTokens` 由 US2-AJ-01 驗 |
| A2 | ✅ 已修正 | `research.md` § R8 本機實跑的 context 改成 16384,補估算(`limit.output` 4096 時可用輸入 12,288,大於 6,469;3B 模型在 6 GB 放得下),修訂紀錄記一筆;`testplan.md` § G-01、G-02 與 `tasks.md` § T048、T049 同步 |
| A3 | ✅ 已修正 | `prototype/connect.html` 三段文字照 testplan 與 spec 改:「目前沒有就緒的工作階段」「先到模型頁下載模型」「讀不到目前的 Ollama 設定,片段不帶 context 長度」 |
| A4 | ✅ 已修正 | `testplan.md` § G-04 與 `tasks.md` § T047 限定以覆蓋值 context 32768 開啟,順便驗 R5 |
| A5 | ✅ 已修正 | 第 1 輪已修 |
| A6 | ✅ 已修正 | 第 1 輪已修 |
| A7 | ✅ 已修正 | 第 1 輪已修 |
