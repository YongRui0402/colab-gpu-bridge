# 跨產出物分析: 加入下載的重複判定與模型目錄快取

**Feature**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md) | **Constitution**: `constitution/`

## 判定

**最新一輪:第 1 輪(2026-11-13)— ⛔ 不能進 `/implement`**

還有 2 個未解決的 HIGH:A1(G-01 要對桌機 11434 的 Ollama 送請求,和 001 實跑護欄 P6「11434 不送任何請求」矛盾,`tests/realrun/helpers.py` 的 `RecordingTransport` 也會擋下)、A2(使用者故事 2 驗收情境 2 的「下載完成後推送 `models.updated`」在現有系統不存在,testplan 列為不在範疇,這一段驗收情境測不到)。A1 是跨迭代的決定矛盾,要先由使用者決定能不能推翻 001 的 P6,不由分身代答。另有 1 個 MEDIUM(A3)、2 個 LOW(A4、A5)不擋實作。

## 檢查範圍

| 產出物 | 產出的步驟 |
|---|---|
| `spec.md` | `/specify`、`/clarify-over-specs`(`澄清報告.md`) |
| `research.md`、`techstack.md` | `/technical-research` |
| `plan.md` | `/system-analysis` |
| `contracts/remote-ollama.openapi.yaml`、`contracts/ui.openapi.yaml` | `/api-plan` |
| `testplan.md` | `/testplan` |
| `tasks.md` | `/tasks` |
| `分身決策紀錄.md`(D1~D41,對照 `plan.md` § 待決問題 Q1~Q26) | 各步驟的 kevin-twin 代答 |
| `constitution/_shared/語言.md` | `/constitution` |
| 前一次迭代的 `../002-library-error-handling/plan.md`、`../001-session-model-catalog/plan.md`;追 G-01 時另讀 `../001-session-model-catalog/testplan.md` § 實跑案例的共同護欄、`../001-session-model-catalog/完成報告.md` | 001、002 的 `/system-analysis`、`/testplan` |

---

## 第 1 輪(2026-11-13)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `specify/scripts/check_spec.py` | ✅ 通過 |
| `system-analysis/scripts/check_plan.py` | ✅ 通過(`--previous-plan ../001-session-model-catalog/plan.md`:0 個不符項);❌ 不過(照 SOP 字面以 `--previous-plan ../002-library-error-handling/plan.md`:1 個不符項「遠端 Ollama 要編成 E9」,第 70 行;002 的 plan.md 只列它改到的 E2、E8,編號沿用 001,001 的 E9 是 Google OAuth。照分身決策紀錄 D12 保留 E7,不列為問題;不帶 `--previous-plan` 則有 2 個不符項,要從 E1 連號) |
| `testplan/scripts/check_testplan.py` | ✅ 通過 |
| `tasks/scripts/check_tasks.py` | ✅ 通過 |

### 問題

| ID | 類別 | 嚴重度 | 位置 | 摘要 | 回哪一步 |
|---|---|---|---|---|---|
| A1 | 矛盾 | HIGH | `testplan.md` § G-01;`tasks.md` § T068;`plan.md` § 待決問題 Q8;`../001-session-model-catalog/testplan.md` § 實跑案例的共同護欄 P6 | G-01 與 T068 寫「只送 `GET /api/tags`、`GET /api/ps` 兩個唯讀請求到 127.0.0.1:11434」,並指定用 `tests/realrun/helpers.py` 的 `RecordingTransport(get_only=True)`;001 的 P6 寫「桌機的 11434 是使用者自己的 Ollama,不送任何請求」,`RecordingTransport.handle_async_request` 每個請求都呼叫 `realrun.conftest.check_port`,11434 在 `FORBIDDEN_PORTS` 裡,會丟 `GuardViolation`。照 T068 寫出來的測試一送就被擋下,G-01 量不到任何數字;換掉 `RecordingTransport` 雖然送得出去,卻是推翻 001 的護欄。分身決策 D22、D24 寫「不和 001、002 矛盾」,漏看了 P6 | `/testplan` |
| A2 | 無法實作 | HIGH | `spec.md` § 使用者故事 2 驗收情境 2;`spec.md` § FR-003;`testplan.md` § 6. 不在本次範疇;`plan.md` § 待決問題 Q14;`../001-session-model-catalog/完成報告.md` § Q188、Q192 | 驗收情境 2 寫「下載完成後推送 `models.updated` …… 系統不再跑 `colab exec`」,FR-003 也把「推送 `models.updated`」列為沿用的路徑;001 完成報告 Q188、Q192 記載「下載完成與工作階段結束時不推 `models.updated`」,testplan 第 6 節因此把「下載完成後推送沿用快取」列為不在範疇(D29),只以預先載入結束的推送驗(US2-API-03)。spec 經 D5 同意的驗收情境,有一段在這一輪沒有任何案例、也做不出來可以觀察的推送;是下游的決定(D29)收窄了上游的驗收情境,spec 沒有跟著改 | `/specify` |
| A3 | 矛盾 | MEDIUM | `contracts/ui.openapi.yaml` § `paths./models.get`(描述 (3));`testplan.md` § US2-API-11;`tasks.md` § T065a;`../001-session-model-catalog/contracts/colab-cli.openapi.yaml` § `probeResources` | 合約 (3) 把讀不到顯示記憶體寫成「`colab exec` 失敗、逾時(任何 `COLAB_` 代碼)」;`probeResources` 的 `x-error-codes` 還有 `AUTH_REQUIRED`,US2-API-11 與 T065a 照 D30 要求 `AUTH_REQUIRED` 也回 200 與 null。合約同一段也寫「讀不到顯示記憶體不會讓這個操作回 …… 500」,照哪一份做出來都是 200,但「讀不到」的範圍兩邊寫法不同(考慮過 HIGH:合約沒有說 `AUTH_REQUIRED` 要回別的,行為一致,給 MEDIUM) | `/api-plan` |
| A4 | 矛盾 | LOW | `spec.md` § 關鍵實體(顯示記憶體快取 VramCache);`research.md` § R3;`techstack.md` § 一覽 | spec 的 VramCache 屬性列「工作階段名稱、顯示記憶體總量、讀取時間」;R3 決定只存一組 `(工作階段名稱, 顯示記憶體總量)`,techstack 也寫這個 tuple,沒有讀取時間。沒有任何 FR、SC 或案例讀「讀取時間」,照哪一份做行為都一樣 | `/specify` |
| A5 | 遺漏 | LOW | `plan.md` § Project Structure(`tests/`);`testplan.md` § 4.2 全域案例;`tasks.md` § T033b;`tasks.md` § 跨端點驗收 | Project Structure 的 `tests/` 只列 `test_remote_ollama.py`、`test_api_downloads.py`、`test_api_models.py` 與 `tests/fakes/`;testplan 另有 `tests/integration/test_003_g_01.py`、`test_003_g_02.py`(G-01、G-02),tasks 另有 `tests/integration/test_downloads_cross.py`(Q25)與 `tests/e2e/test_locale.py`(T033b 補三個 `OLLAMA_*` 列)。檔案都由下游定好,行為不受影響 | `/system-analysis` |

### 追溯缺口

只列有缺口的需求;其餘需求從規格檔到任務都接得上。

| 需求 | 規格檔元素 | 任務 | 缺口 |
|---|---|---|---|
| FR-003 / 驗收情境 2「下載完成後推送 `models.updated`」 | `ui.openapi.yaml` § `paths./models.get`(描述 (2)、(6) 提到推送;001 的 `ui-events.asyncapi.yaml` 有,實作沒有) | 無(只有預先載入的推送 T057a、T057b 對應 US2-API-03) | A2 |
| FR-001、FR-004、NFR-003 的 G-01(替身與真 Ollama 一致) | `remote-ollama.openapi.yaml` § `paths./api/tags.get`、`paths./api/ps.get` | T068(照寫的做法會被 P6 護欄擋下) | A1 |

### 修正順序

1. **先由使用者決定 A1**(跨迭代的決定矛盾,分身不代答,已記進 `分身決策紀錄.md` § 停下的矛盾):003 的 G-01 能不能對桌機 127.0.0.1:11434 的 Ollama 送兩個唯讀 GET(等於在這一輪放寬 001 的 P6),或改成不碰 11434 的做法(例如 G-01 改列無法實跑,或改用另外起在別的 port、不屬於使用者的 Ollama)
2. `/specify` 把使用者故事 2 驗收情境 2 與 FR-003 的「下載完成後推送 `models.updated`」註明是 001 的已知缺口(Q188、Q192),這一輪以預先載入結束的推送驗(A2);關鍵實體 VramCache 拿掉「讀取時間」或註明不存(A4)
3. `/system-analysis` 在 Project Structure 的 `tests/` 補上 `test_003_g_01.py`、`test_003_g_02.py`、`test_downloads_cross.py` 與 `tests/e2e/test_locale.py`(A5);依第 1 步的決定改 `plan.md` § 待決問題 Q8 的決定欄
4. `/api-plan` 把 `ui.openapi.yaml` § `paths./models.get` 描述 (3) 的「任何 `COLAB_` 代碼」改成 `probeResources` 的全部代碼(含 `AUTH_REQUIRED`)(A3);第 2 步若改了推送的寫法,描述 (2)、(6) 跟著對齊
5. `/testplan` 依第 1 步的決定改 G-01 的做法與護欄(A1),第 6 節「下載完成後推送」那一列對齊第 2 步改過的 spec(A2)
6. `/tasks` 依第 5 步改 T068(A1),並涵蓋前面幾步改到的錨點
7. 重跑 `/analyze`
