# Phase 0 Research: 依機器配置調整遠端 Ollama 的設定,並在 UI 顯示與修改

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-11-15

使用者指定的技術方向:

- 整體:沿用 001~004 的技術堆疊(`specs/004-chat-hf-curated-queue/techstack.md`):Python 3.12 + FastAPI 後端、原生 HTML / CSS / JS 前端、SQLite、`colab` CLI 操作執行環境。
- 實測:任何 `colab` 指令或花 compute units 的實跑先停下問使用者本人;不對桌機 127.0.0.1:11434 送請求,需要真的 Ollama 時另起臨時 `ollama serve`(別的 port、暫存 `OLLAMA_MODELS` 與 `HOME`)。

每個「理由」都標出證據類型:**實測**(附量測環境)、**估算**(附依據)、**查證**(附來源)、**判斷**(推論)。探針腳本放在 session 暫存區(`probe_serve.sh`:在 port 11499 起臨時 `ollama serve`),不進 repo;探針用完已確認行程結束、暫存模型刪除。這次沒有依樣本調出來的門檻(級距由公式估算),樣本分配表只記「沒有真實資料樣本」。級距要在真的 T4 與 A100 上以 SC-001、SC-002 重測,實跑前先問使用者。

---

## R1. 遠端 Ollama 怎麼重啟(FR-012、FR-013、SC-004)

**決策**:

- **新的遠端腳本 `restart_ollama.py`**:由後端以 `colab exec -f` 送到遠端,和 `start_ollama.py` 共用「決定設定、啟動、驗證」的程式;不改 `start_ollama.py` 的冪等行為(已在回應就不重啟)。
  1. 讀 `/root/cgb-ollama-serve.pid`,對那個行程群組送 `SIGTERM`,每 0.2 秒確認一次,10 秒內沒結束就送 `SIGKILL`。
  2. 等 `127.0.0.1:11434` 不再回應 `/api/version`。
  3. 依 R7 決定的環境變數啟動 `ollama serve`(`start_new_session=True`),把新的 pid 寫回 pid 檔。
  4. 每秒打一次 `/api/version`,60 秒內有回應就回報成功;否則回報 `stage: "verify"`,由後端照 FR-013 改用自動值再跑一次。
- **`start_ollama.py` 也寫 pid 檔**:啟動時把 `ollama serve` 的 pid 寫進 `/root/cgb-ollama-serve.pid`,重啟才找得到要停哪一個。
- **pid 檔不存在**(001~004 開的工作階段、或檔案被刪):改用 `pkill -f "^ollama serve"` 停掉,其餘步驟相同。

**理由**:

- 實測(桌機 i5-9400F、GTX 1660 Ti,Ollama 0.32.15,臨時 `ollama serve` 在 127.0.0.1:11499,已載入 `qwen2.5:0.5b`):對 `setsid` 起的 serve 行程群組送 `SIGTERM`,0.57 秒結束,載入模型的 `llama-server` 子行程一起結束(之後 `ps` 只剩新 serve 的子行程);換新的環境變數重新啟動,3 秒後 `/api/version` 回應,從送出停止到回應共 3.7 秒;新的 log 裡 `OLLAMA_NUM_PARALLEL:2`、`OLLAMA_CONTEXT_LENGTH:4096`,`/api/ps` 是空的(已載入的模型確實被清掉)。
- 查證(`src/cgb/adapters/scripts/start_ollama.py`):步驟 (a) 在 `/api/version` 有回應時直接回報 `alreadyRunning`,不會換設定重啟,所以要另一支腳本;`ollama serve` 用 `start_new_session=True` 啟動,有自己的行程群組,可以整組停掉。
- 估算(實測 3.7 秒 + 001 research R1 量到的 `colab exec` 來回數秒,加上 Colab 比桌機慢):重啟在 SC-004 的 90 秒內有很大的餘裕。
- 判斷:對照的同類產品(本次未重新查文件)中,LM Studio 與 text-generation-webui 都是在「載入模型」時設定 context 長度與平行數,改設定就重新載入;本系統的設定是 `ollama serve` 啟動時讀的環境變數,所以對應的做法是重啟 serve。

**考慮過的替代方案**:

- 讓 `start_ollama.py` 多一個「強制重啟」參數:會改到 001 合約裡冪等的定義,開啟流程重跑時也可能誤重啟。
- 只用 `pkill`:執行環境上若有使用者自己手動起的 `ollama`,也會被停掉;pid 檔比較精準,`pkill` 只當備援。

## R2. Ollama 對五個環境變數的支援(FR-002)

**決策**:用 `OLLAMA_NUM_PARALLEL`、`OLLAMA_CONTEXT_LENGTH`、`OLLAMA_MAX_LOADED_MODELS`、`OLLAMA_FLASH_ATTENTION=1`、`OLLAMA_KV_CACHE_TYPE=q8_0`,照 spec FR-002 帶給 `ollama serve`。

**理由**:

- 實測(桌機,Ollama 0.32.15,臨時 serve 在 11499):啟動 log 的 `server config` 列出 `OLLAMA_NUM_PARALLEL:4`、`OLLAMA_CONTEXT_LENGTH:8192`、`OLLAMA_MAX_LOADED_MODELS:2`、`OLLAMA_FLASH_ATTENTION:true`、`OLLAMA_KV_CACHE_TYPE:q8_0`,五個都被讀到;載入模型後 `llama_context: n_seq_max = 4`、`n_ctx_slot = 8192`,`/api/ps` 的 `context_length` 是 8192。
- 查證(`specs/004-chat-hf-curated-queue/techstack.md`):Colab 上的遠端 Ollama 是安裝時取最新版,001 遠端實測 0.40.15,比桌機的 0.32.15 新。
- 判斷:假設未查(查要開 Colab 工作階段、花 compute units):新版仍讀同樣的變數名稱。驗證方式:實跑 SC-001 時讀遠端 `/root/cgb-ollama-serve.log` 的 `server config` 與 `n_seq_max`,列在待驗證。

**考慮過的替代方案**:不帶環境變數、改在每個請求的 `options` 帶 `num_ctx`:平行數與同時載入模型數只能在 serve 層設,而且相容端點要原樣轉送區網程式的請求,不能改本文。

## R3. Turing 架構上 flash attention 與 KV `q8_0`(FR-002、SC-002)

**決策**:每一級都開 flash attention 與 KV `q8_0`,包含 T4;不做依 compute capability 的例外。

**理由**:

- 實測(桌機 GTX 1660 Ti,compute capability 7.5,和 T4 同為 Turing;Ollama 0.32.15;`qwen2.5:0.5b`):log 有 `flash_attn = enabled`,`llama_kv_cache: size = 204.00 MiB (8192 cells, 24 layers, 4/4 seqs), K (q8_0): 102.00 MiB, V (q8_0): 102.00 MiB`;`/api/ps` 的 `size_vram` 等於 `size`(全部在 GPU)。
- 估算(`qwen2.5:0.5b` 24 層、2 個 KV head、head 維度 64,q8_0 每元素 1.0625 bytes):每個 token 的 K 是 24 × 2 × 64 × 1.0625 ≈ 3.3 KB,8192 × 4 份 ≈ 102 MiB,和實測相符。**說明 KV cache 是「context 長度 × 平行數」份,不是全部共用一份**,R4 的估算照這個算。

**考慮過的替代方案**:KV 用 `f16`:記憶體是 `q8_0` 的約兩倍,同一張卡能開的平行數減半。

## R4. 級距數值與實測計畫(FR-002、SC-001、SC-002)

**決策**:先照 spec FR-002 的級距實作;實跑 SC-001、SC-002 後若不達標,依實測修正級距,同步改 spec FR-002 與本檔修訂紀錄。

**理由**:

- 估算(KV 每個 token = 2 × 層數 × KV head 數 × 128 × 1.0625 bytes,乘上 context 長度 × 平行數;權重取 Ollama 模型庫的 q4 大小;未計 compute buffer):

| 級距(代表機器) | 平行 × context | 7B(4.7 GB,KV 30 KB/token) | 14B(9 GB,KV 104 KB/token) | 32B(20 GB,KV 139 KB/token) |
|---|---|---|---|---|
| 12~20 GiB(T4 15 GiB) | 2 × 4096 | 4.7 + 0.25 GB | 9 + 0.85 GB | 放不下(權重已超過) |
| 20~32 GiB(L4 22.5 GiB) | 4 × 8192 | 4.7 + 1.0 GB | 9 + 3.4 GB | 20 + 4.6 GB,超過 |
| 32~64 GiB(A100 40 GiB) | 8 × 8192 | 4.7 + 2.0 GB | 9 + 6.8 GB | 20 + 9.1 GB |
| ≥64 GiB(G4 95.6 GiB) | 16 × 8192 | 4.7 + 4.0 GB | 9 + 13.6 GB | 20 + 18.2 GB |

- 判斷:各級裡權重本來就放得下的模型,加上 KV 之後仍在顯示記憶體內。L4 上的 32B 本來就會被 003 標成「可能無法載入」,不因級距而變;A100 的 `MAX_LOADED_MODELS=2` 能同時放兩個 7B~14B。
- 判斷:SC-001、SC-002 的量法見 spec(分身 D8);實跑需要真的 T4 與 A100,先停下問使用者本人,照 001 testplan 的 P1~P9。

**考慮過的替代方案**:依 GPU 類型名稱寫死一張表:Colab 同一種類型可能分到不同規格,也無法涵蓋之後新增的類型(使用者已決定只看顯示記憶體)。

## R5. 相容端點同時轉發的上限(spec 假設、FR-017)

**決策**:不改相容端點;它現有的上限 100 條連線已高於平行數上限 32。

**理由**:

- 查證(`src/cgb/ollama_compat/__init__.py`):轉發用 `httpx.AsyncClient(timeout=FORWARD_TIMEOUT)`,沒有傳 `limits`,也沒有 semaphore。
- 實測(桌機,專案的 uv 環境,`httpx` 0.28.1):預設的 `AsyncClient()` 連線池 `max_connections` 是 100,`max_keepalive_connections` 是 20。
- 判斷:同時轉發最多 100 條,比 FR-017 的平行數上限 32 高;超過 Ollama 平行數的請求由遠端 Ollama 自己排隊(`OLLAMA_MAX_QUEUE` 預設 512,桌機 log 實測)。

**考慮過的替代方案**:替相容端點加 semaphore 限制同時轉發數:遠端 Ollama 已經會依平行數排隊,多一層限制只會讓排隊發生在兩個地方。

## R6. 在哪裡量硬體(FR-001、NFR-001)

**決策**:在 `start_ollama.py` 與 `restart_ollama.py` 裡、啟動 `ollama serve` 之前量:`nvidia-smi --query-gpu=name,memory.total`(10 秒逾時,和 `probe_resources.py` 同一套)與 `/proc/meminfo` 的 `MemTotal`;結果放進 `CGB-RESULT` 的新欄位,不多一次 `colab exec`。

**理由**:

- 實測(桌機 GTX 1660 Ti):`nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits` 花 0.03 秒。
- 查證(`src/cgb/adapters/scripts/probe_resources.py`):已有同樣的 `nvidia-smi` 讀法,失敗或逾時回 `None`;003 的顯示記憶體快取用的是 `probe_resources`。
- 判斷:另外先呼叫一次 `probe_resources` 要多一次 `colab exec` 來回(數秒),會吃掉 NFR-001 的 5 秒;在同一支腳本裡量只多 0.03 秒。

**考慮過的替代方案**:開啟流程先跑 `probe_resources` 再把結果傳給 `start_ollama`:多一次 `colab exec`。

## R7. 設定怎麼傳到遠端(FR-003、FR-007、邊界情況)

**決策**:

- **後端只傳覆蓋值,級距由遠端腳本算**:每次 `start_ollama` / `restart_ollama` 都帶齊三個 `--env CGB_TUNE_NUM_PARALLEL=<值或空字串>`、`CGB_TUNE_CONTEXT_LENGTH`、`CGB_TUNE_MAX_LOADED_MODELS`;空字串代表自動。
- **腳本組出 `ollama serve` 的環境**:從 `os.environ` 複製一份,先刪掉所有 `OLLAMA_NUM_PARALLEL` 等五個變數,再依「覆蓋值 > 級距 > 不帶」填入;只傳給 `Popen(env=...)`,不改 kernel 的 `os.environ`。
- **級距表**:放在共用的 `cgb/domain/tuning.py`,後端顯示與測試用;遠端腳本是單檔送過去,內嵌同一張表,以單元測試確認兩邊一致。
- **`CGB-RESULT` 回報實際套用的值**(每一項的值與來源),後端以它為準寫進紀錄與 UI。

**理由**:

- 查證(`specs/001-session-model-catalog/contracts/colab-cli.openapi.yaml` § `/exec/start-ollama`):「`--env` 把下列環境變數設進遠端 kernel,腳本啟動的 Ollama 繼承它們」。kernel 的環境會留到下一次 exec。
- 判斷:如果直接用 `--env OLLAMA_NUM_PARALLEL=4`,之後改回自動重啟時,沒帶的變數仍留在 kernel 裡被繼承,會套到舊值;每次帶齊三個 `CGB_TUNE_*`、由腳本自己組 `Popen` 的環境,就不會殘留,也符合邊界情況「同一個變數不得同時出現兩個值」。
- 判斷:級距要用遠端量到的顯示記憶體,在遠端算可以少一次來回(R6)。

**考慮過的替代方案**:後端先量硬體、算好五個值再用 `--env` 傳:要多一次 exec(R6),還有殘留問題。

## R8. 怎麼重新載入模型(FR-012)

**決策**:重啟成功後,依重啟前 `/api/ps` 的順序,對前 N 個(N = 新的同時載入模型數)依序呼叫 001 的預先載入(`remote_ollama.preload`,只有 `model`、`keep_alive: -1`);等全部載入完才回到就緒,沒有重新載入的列在工作階段狀態。

**理由**:

- 查證(`src/cgb/services/catalog.py` `preload`、`src/cgb/services/runtime_switch.py`):001 已有預先載入(背景送只有 `model` 的 generate,`keep_alive: -1`),變更類型時用 `list_loaded_models` 記下已載入的模型。
- 實測(桌機臨時 serve,重啟後):對 `qwen2.5:0.5b` 送 `{"model":..., "keep_alive":-1}` 1.9 秒載入完成。
- 判斷:依序載入避免兩個模型同時爭顯示記憶體;FR-012 要求重啟期間不算就緒,所以載入完才轉就緒。

**考慮過的替代方案**:重啟後全部重新載入讓 Ollama 自己換出,或都不載入:分身 D6 已否決(多一次白費的載入,或把等待移到第一個請求)。

## R9. 覆蓋值與每次套用的紀錄怎麼存(FR-005、FR-016、FR-018)

**決策**:沿用 SQLite 與 `PRAGMA user_version` 遷移(1 → 2):

- 新表 `runtime_type_tuning`:每種 GPU 類型一列,三個可為 NULL 的欄位與更新時間。
- 新表 `session_tunings`:每次開啟或套用一列(工作階段、時間、觸發、五項值與來源、結果、顯示記憶體與系統記憶體)。
- 表與欄位細節由 system-analysis 的 data-plan 定。

**理由**:

- 查證(`src/cgb/db/schema.py`):004 已用 `PRAGMA user_version` 從 0 遷到 1,`sessions.runtime_type_gpu` 的 CHECK 列出五種類型。
- 判斷:只是加表,不改既有表,不需要重建;沿用同一套遷移方式不新增套件。

**考慮過的替代方案**:把覆蓋值存成 JSON 放進既有的 `settings` 表:要查某一種類型的值得整份解析,每次套用的紀錄也還是要另一張表。

## R10. 忙碌判斷與重啟期間的閒置倒數(FR-011、邊界情況)

**決策**:

- **進行中的請求**:用 `IdleMonitor.active_requests > 0`。
- **下載中**:下載佇列有狀態為下載中的項目。
- **重啟期間**:工作階段狀態加一個 step(例如 `restarting_ollama`、`reloading_models`),相容端點與對話照 001「未就緒」回錯誤;閒置倒數在非就緒時不計,回到就緒時重設。

**理由**:

- 查證(`src/cgb/services/idle_monitor.py`、`src/cgb/ollama_compat/idle_hook.py`、`src/cgb/api/chat.py`):相容端點(`IdleHook`)與 UI 對話(`chat.py` 第 201、210 行)都會呼叫 `request_started()` / `request_finished()`,`active_requests` 已涵蓋兩者。
- 判斷:沿用現成的計數就能符合分身 D3,不需要另外追蹤。

**考慮過的替代方案**:另外追蹤 UI 對話與相容端點的請求清單:`active_requests` 已經涵蓋兩者,多一份清單只會和它不同步。

## R11. UI 做法(FR-004、FR-006、FR-010、FR-015)

**決策**:沿用原生 HTML / CSS / JS:開啟畫面的類型選單下加一個可展開的「Ollama 設定」區塊(三個數字欄位、「留空 = 自動」、「全部改回自動」);工作階段頁加一張「Ollama 設定」卡,顯示量到的硬體與三項設定的來源,就緒時可以修改並「套用並重啟 Ollama」。畫面細節由 system-analysis 的 ui-plan 做原型。

**理由**:

- 查證(`src/cgb/static/js/session.js`、`view.js`):開啟與變更類型共用 `renderPicker`,`RUNTIME_TYPES` 已有每種類型的顯示記憶體;頁面都是原生 JS,沒有框架。
- 判斷:對照的同類產品(本次未重新查文件)中,LM Studio 載入模型時的進階設定是「預設收起、展開才看到數字欄位」,一般使用者不用碰;本系統照同樣的做法,預設全部自動。

**考慮過的替代方案**:另開一個「Ollama 設定」頁:設定只對目前的工作階段與開啟畫面有意義,放在這兩個地方使用者不用切頁。

## 待驗證

| 來源 | 待驗證 | 驗證方式 / 時機 | 擋計畫? |
|---|---|---|---|
| R2 | Colab 上安裝的最新版 Ollama 仍讀同樣的五個環境變數 | 實跑 SC-001 時讀遠端 log 的 `server config`、`n_seq_max`;實跑前先問使用者 | 否 |
| R3 | T4 上 flash attention 與 KV `q8_0` 生效(桌機 1660 Ti 同架構已實測) | 實跑 SC-002 時讀遠端 log | 否 |
| R4 | 級距能讓 A100 達 SC-001、T4 達 SC-002,模型全部在 GPU | 實跑 SC-001、SC-002;實跑前先問使用者 | 否 |
| R1 | Colab 上重啟(含 `colab exec` 來回)在 SC-004 的 90 秒內 | 實跑 SC-004 | 否 |

## 修訂紀錄

無(2026-11-15 初版,尚未修訂)。
