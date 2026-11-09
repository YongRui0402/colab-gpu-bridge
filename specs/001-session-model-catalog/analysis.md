# 跨產出物分析: Colab GPU 工作階段管理與模型目錄

**Feature**: [spec.md](./spec.md) | **Tasks**: [tasks.md](./tasks.md) | **Constitution**: `constitution/`

## 判定

**最新一輪:第 1 輪(2026-11-10)— ⛔ 不能進 `/implement`**

還沒解決的 CRITICAL 1 個(A1)、HIGH 4 個(A2、A3、A4、A5);另有 4 個 LOW(A6–A9)不擋實作,建議一併修掉。

## 檢查範圍

| 產出物 | 產出的步驟 |
|---|---|
| `spec.md` | `/specify` |
| `research.md`、`techstack.md` | `/technical-research` |
| `plan.md` | `/system-analysis` |
| `contracts/ui.openapi.yaml`、`contracts/ui-events.asyncapi.yaml`、`contracts/ollama-compat.openapi.yaml`、`contracts/colab-cli.openapi.yaml`、`contracts/tunnel.openapi.yaml`、`contracts/remote-ollama.openapi.yaml`、`contracts/model-library.openapi.yaml`、`contracts/google-oauth.openapi.yaml` | `/api-plan` |
| `contracts/store.dbml` | `/data-plan` |
| `prototype/`(index、login、history、models、library、usage、states 與 mock.js、style.css) | `/ui-plan` |
| `deploy/`(compose.yaml、Dockerfile、Dockerfile.dockerignore、.env.example、prepare-data.sh、healthcheck.py) | `/deploy-plan` |
| `testplan.md` | `/testplan` |
| `tasks.md` | `/tasks` |
| `constitution/_shared/語言.md` | `/constitution` |

---

## 第 1 輪(2026-11-10)

### 前置檢查

| 腳本 | 結果 |
|---|---|
| `specify/scripts/check_spec.py` | ✅ 通過 |
| `system-analysis/scripts/check_plan.py` | ✅ 通過 |
| `tasks/scripts/check_tasks.py` | ✅ 通過(preflight 以不帶 `--testplan` 的方式呼叫;tasks.md 已補 `## SC 量測` 表,屬 skill 的已知缺口,不算產出物的問題) |

### 問題

| ID | 類別 | 嚴重度 | 位置 | 摘要 | 回哪一步 |
|---|---|---|---|---|---|
| A1 | 憲法 | CRITICAL | `constitution/_shared/語言.md` 〈給人讀的文字一律用繁體中文與台灣用語〉;`plan.md` § 待決問題 Q115;`tasks.md` § T061a | 憲法 MUST 條文明列「程式(不是程序)」;Q115 寫「外部程序參數交給真工具解讀」,T061a 寫「外部程序端點要有讓真的工具解讀參數的測試」,兩處都是指外部程式,應改「外部程式」 | `/system-analysis`、`/tasks` |
| A2 | 矛盾 | HIGH | `research.md` § R8;`research.md` § R1;`techstack.md` § 自寫取代套件;`plan.md` § 待決問題 Q18、Q20;`contracts/ollama-compat.openapi.yaml` § `x-unlisted-paths`;`contracts/colab-cli.openapi.yaml` § `paths./exec/start-ollama.post` | 白名單轉送與 `OLLAMA_ORIGINS` 兩個決定沒有回寫技術研究:R8 決策仍是「管理操作直接回 403」加「我們只需要原樣轉送加黑名單」,techstack 寫「Ollama 原樣轉送代理加管理操作黑名單」;R1 的遠端初始化只帶 `OLLAMA_HOST=127.0.0.1:11434`。Q18 已改為白名單、Q20 已決定啟動時設 `OLLAMA_ORIGINS=*`,ollama-compat 規定白名單外一律回 404 `PATH_NOT_SUPPORTED`(含 `/v1/*`),start-ollama 的命令列帶 `--env 'OLLAMA_ORIGINS=*'`。照 R8 做會把 `/v1/*` 轉到遠端(等於提供 OpenAI 相容 API),照 R1 做區網網頁帶 `Origin` 的請求會被遠端回 403 | `/technical-research` |
| A3 | 矛盾 | HIGH | `plan.md` § 待決問題 Q119;`contracts/ui.openapi.yaml` § `paths./usage.get`、`components.schemas.Usage`;`testplan.md` § US4-API-18;`prototype/usage.html` § `[data-state="stale"]` | Q119 決定「讀過用量但最近一次失敗時回最後快照、超過 15 分鐘標 `stale`,`unknown` 只用在從沒讀到過」,原型的過期畫面也照樣顯示 11.97 CU 等舊數字;`getUsage` 的說明卻仍寫「讀不到時 `state` 為 `unknown`」,`Usage.state` 寫「讀得到,或讀不到」、`reasonCode` 寫「讀不到的原因」。照規格檔做,第一次讀取失敗就變成「未知」,NFR-008 的過期標示永遠不會出現;Q119 的「擋住」欄是「—」,沒有人回頭改 S5 | `/api-plan` |
| A4 | 矛盾 | HIGH | `prototype/index.html` § `[data-state="release-failed"]`;`contracts/ui.openapi.yaml` § `paths./session.delete`;`contracts/store.dbml` § `Table sessions` | 原型的釋放失敗區塊寫「系統每分鐘會再試一次」並有「再試一次釋放」按鈕;`endSession` 只寫「`releaseWarning` 不為空時呼叫這個操作會再試一次釋放」,`release_warning_message` 的 note 也只寫「endSession 會再試一次釋放」,沒有任何規格檔定義每分鐘自動重試。照原型做後端會多一個排程,照規格檔做畫面文字會承諾一件不會發生的事;spec FR-007 只要求警告,自動重試是原型自己加的 | `/ui-plan` |
| A5 | 矛盾 | HIGH | `spec.md` § FR-007;`spec.md` § 釐清紀錄;`plan.md` § 待決問題 Q100;`contracts/colab-cli.openapi.yaml` § `paths./sessions.get`;`contracts/store.dbml` § `Table sessions` | FR-007 寫「發現遺留必須釋放,釋放不了必須在 UI 明確警告」;Q100 的 (a') 自己寫明「在資料庫遺失時使 FR-007『發現遺留必須釋放』不成立」,決定「資料庫不認得、CLI 記得的執行環境一律在 UI 警告」,listSessions 與 `sessions.name` 的 note 都照此寫「不接手、不關閉」。同類的 Q19、Q57、Q58 都已回寫 spec(FR-013、SC-002、SC-001 與釐清紀錄),這一題沒有,FR-007 與邊界情況的原文未改;資料庫遺失時,照 spec 要釋放、照規格檔只警告 | `/specify` |
| A6 | 矛盾 | LOW | `research.md` § R3;`spec.md` § SC-002;`research.md` § R8;`spec.md` § FR-013 | R3 的判斷寫「斷線最晚約 1 分鐘內進入『重連中』,符合 SC-002 的 2 分鐘」,SC-002 改寫後單純斷線的門檻已是 1 分鐘內顯示重連中、2 分鐘是被收回的門檻;R8 寫「沒有就緒的工作階段時立即回 503」,FR-013 改寫後門檻是 SC-007 的 1 秒。兩處估算都仍在新門檻內,照哪一份做行為都一樣 | `/technical-research` |
| A7 | 矛盾 | LOW | `research.md` § R9;`techstack.md` § 一覽;`prototype/` § 7 個頁面 | R9 以「畫面只有工作階段面板、模型目錄、下載佇列、設定、紀錄五塊」當作不用前端框架的理由,techstack 前端列同樣列五塊;原型有首頁、登入、紀錄、模型、下載模型、用量 6 頁加狀態總覽,登入與下載模型不在那五塊內。不用框架的決策不受影響 | `/technical-research` |
| A8 | 矛盾 | LOW | `contracts/remote-ollama.openapi.yaml` § `paths./api/version.get`、`paths./api/tags.get`、`paths./api/ps.get`、`paths./api/pull.post`、`paths./api/generate.post`;`plan.md` § 待決問題 Q2、Q3、Q4、Q5 | 規格檔仍寫「建議 5 秒(research.md 沒有定下,見待決問題)」「沒有實測,見待決問題」,預先載入寫「`keep_alive` 沒給時是 Ollama 的預設 5 分鐘(見待決問題)」;Q2–Q5 都已決定,值與規格檔的建議相同,Q4 的 `keep_alive: -1` 已寫在 `ui.openapi.yaml` § `paths./models/preload.post` 與 testplan US3-RO-04 | `/api-plan` |
| A9 | 矛盾 | LOW | `testplan.md` § 1. 待測端點(E1 列);`plan.md` § 待決問題 Q110;`prototype/usage.html` § `#settings-form`;`testplan.md` § US1-API-26;`contracts/ui.openapi.yaml` § `components.schemas.UnmanagedRuntime` | E1 列的介面規格檔只列 5 頁、說明寫「三個故事都沒有不靠後端就看得到的畫面行為」,Q110 已把故事 4 拉回範疇,usage.html 沒列(受測操作表與 G-06 已涵蓋它,不測 E1 的結論不變)。另 US1-API-26 則3 寫「`unmanagedRuntimes` 有 `cgb-other-9` 那台」,`UnmanagedRuntime` 只有 `hardware`、`detectedAt` 且註明「不含名稱與位址」,只能以筆數與硬體判斷,假如欄也沒寫 `cgb-other-9` 的硬體 | `/testplan` |

### 追溯缺口

只列有缺口的需求;其餘需求從規格檔到任務都接得上。

| 需求 | 規格檔元素 | 任務 | 缺口 |
|---|---|---|---|
| FR-007 遺留釋放 | `colab-cli.openapi.yaml` § `paths./sessions.get`、`store.dbml` § `Table sessions`(資料庫不認得的只警告) | T040a、T040b | A5 |
| FR-007 釋放失敗的警告 | `ui.openapi.yaml` § `paths./session.delete`(只有手動再試);`prototype/index.html` § `[data-state="release-failed"]`(寫每分鐘自動再試) | T104a、T104b | A4 |
| NFR-008 過期標示 | `ui.openapi.yaml` § `paths./usage.get`(讀不到即 `unknown`) | T231a、T231b | A3 |
| FR-011 只開放推論與查詢(不提供 OpenAI 相容 API) | `ollama-compat.openapi.yaml` § `x-unlisted-paths`(白名單);`research.md` § R8(黑名單) | T127a、T127b | A2 |
| FR-011 帶 `Origin` 的區網程式 | `colab-cli.openapi.yaml` § `paths./exec/start-ollama.post`(`OLLAMA_ORIGINS=*`);`research.md` § R1(沒有) | T066a、T066b、T135a、T135b | A2 |

### 轉交 `/clarify-over-specs`

單份文件內的模糊不屬於本步驟,標記後轉交:

| 位置 | 為什麼要澄清 |
|---|---|
| `spec.md` § 假設(重連時限預設 5 分鐘) | 寫「預設」暗示可以調整,但 FR-027 只讓使用者設定閒置時限與餘額警告門檻;下游(Q67)已定為固定 5 分鐘不可設定,spec 應明確寫出是固定值或補進 FR-027 |
| `spec.md` § 假設(SC-007 的「1 秒內」) | 註明「是澄清時採用的預設(使用者未逐題拍板)…不合用可以推翻」,門檻仍是待確認狀態;下游的 US2-OC-07、US2-AJ-03 都以 1 秒驗收,應由使用者確認後拿掉這句保留 |

### 修正順序

1. `/specify` 把 Q100 的決定回寫 FR-007、邊界情況與釐清紀錄,寫明資料庫不認得、CLI 記得的執行環境只警告不關閉(A5);`/clarify-over-specs` 澄清重連時限是否固定、確認 SC-007 的 1 秒
2. `/technical-research` 把 R8 與 techstack 改成白名單轉送、R1 的遠端初始化補上 `OLLAMA_ORIGINS=*`(A2),R3、R8 的門檻文字對齊改寫後的 SC-002、SC-007(A6),R9 與 techstack 的畫面清單對齊原型(A7)
3. `/system-analysis` 把 Q115 的「外部程序」改為「外部程式」(A1)
4. `/api-plan` 把 `getUsage` 與 `Usage` 的說明改成 Q119 的語意:讀過之後失敗回最後快照與 `stale`,`unknown` 只用在從沒讀到過(A3);remote-ollama 的「見待決問題」改寫成已決定的值(A8)
5. `/ui-plan` 拿掉釋放失敗區塊「系統每分鐘會再試一次」的說法,或改由 `/api-plan` 補定自動重試的排程後再保留(A4)
6. `/testplan` E1 列補上 usage.html 並改掉「三個故事」,US1-API-26 的假如補上 `cgb-other-9` 的硬體、則3 改為以筆數與硬體斷言(A9)
7. `/tasks` 把 T061a 的「外部程序」改為「外部程式」(A1),並依第 1、4、5、6 步改過的錨點與案例重新核對 T040、T104、T231 等任務
8. 重跑 `/analyze`
