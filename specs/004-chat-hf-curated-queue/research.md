# Phase 0 Research: 佇列隨工作階段清空、測試對話框、Hugging Face 模型來源與可編輯的精選清單

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-11-14

使用者指定的技術方向:

- 後端:沿用 001~003 的堆疊(Python 3.12、FastAPI 0.162.2、httpx 0.28.1、SQLite,見 003 的 techstack.md),這一輪不引入新套件。
- 前端:沿用 001 的原生 HTML / CSS / JS,不加框架與建置工具。
- 限制:不開 Colab、不跑 `colab` 指令、0 compute units;不對桌機 127.0.0.1:11434 送請求;需要真的 Ollama 時另起臨時的 `ollama serve`(別的 port、暫存的 `HOME` 與 `OLLAMA_MODELS`,用完結束並刪除)。對 huggingface.co 只發不帶 token 的唯讀請求。

每個「理由」都標出證據類型:**實測**(附量測環境)、**估算**(附依據)、**查證**(附來源)、**判斷**(推論)。探針放在 session 暫存區,不進 repo,需要留存的結論寫在各研究項:`test_probe_queue_baseline.py` 以 `tests/conftest.py` 的 fixture 與替身量改之前的佇列行為;`hf_quants.py`、`hf_match.py` 跑 R3 的量化版本規則;`chat_relay.py` 以既有的 `cgb.ollama_compat.forward.forward` 轉送 `/api/chat`;`migrate.py` 跑 R7 的遷移草稿。實測環境都是桌機(Ubuntu,Python 3.12,專案 `.venv`);Ollama 的實測用臨時 `ollama serve` 0.32.15(port 11447,CPU,模型 `hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M` 約 105 MB),實測完行程已結束、暫存資料夾已刪除。遠端 Colab 上的 Ollama 是安裝時取最新版(001 實測 0.40.15),和本機版本不同的部分列進待驗證。

H100 的隱藏(FR-017)只是 UI 選單的常數,沒有技術未知數,不列研究項。

樣本用途(分配表在暫存區 `樣本分配表.md`,打開任何回應之前只憑 repo 名稱寫):

| 樣本(Hugging Face repo) | 用途 |
|---|---|
| `Qwen/Qwen2.5-0.5B-Instruct-GGUF` | 調整用(R3 規則) |
| `bartowski/Llama-3.2-1B-Instruct-GGUF` | 調整用(R3 規則) |
| `bartowski/SmolLM2-135M-Instruct-GGUF` | 調整用(R3 規則、R4 拉取實測;分配後追加) |
| `google/gemma-3-1b-it-qat-q4_0-gguf` | 調整用(需要同意條款的情況) |
| `unsloth/Qwen3-0.6B-GGUF` | 驗收用(R3 規則定案後才打開) |
| `bartowski/Meta-Llama-3.1-70B-Instruct-GGUF` | 驗收用(含分割檔,R3 規則定案後才打開) |

---

## R1. 佇列隨工作階段清空的觸發點(FR-001、FR-002、FR-003、NFR-001、SC-001)

**決策**:下載項目記下所屬的工作階段,在工作階段狀態的寫入處統一清除。

- **歸屬**:`download_jobs` 加 `session_name`(R7);加入下載、自動下載、重新載入時都寫入當下(或新)工作階段的名稱。
- **觸發**:`DownloadsService` 掛在 `SessionsRepo.listeners`(和 `SessionLifecycle._signal_ended` 同一個掛法),每次寫入後檢查:某個工作階段的狀態是 `ending`、`ended`、`open_failed` 或 `lost`,而佇列裡還有屬於它的項目,就:
  1. 取消背景下載的 worker(`interrupt()` 現有的那段)。
  2. 刪除屬於它的所有項目(含 `session_name` 為 NULL 的舊資料),每一筆推 `download.removed`。
  - 不再把下載中的那筆標成失敗(反正要刪);`end_listeners` 不再用來清佇列。
- **變更執行階段類型**(FR-002):`RuntimeSwitch.restart` 改順序:先讀已載入的模型與大小 → 把舊的改成 `ending`(此時清掉舊的所有項目)→ `reserve` 新的 → 以新的名稱 `enqueue_restore`。
- **就緒**:`resume()` 不再接續上一台的項目;就緒時只開始屬於這個工作階段的排隊中項目(重新載入的那幾筆),再跑 R6 的自動下載。
- **後端重新啟動**(FR-003):`Recovery._run` 在判定之前先刪除 `session_name` 不等於「上一個行程留下、未結束的那筆」名稱的項目;接回時(同一個工作階段)保留並照現有的 `requeue_interrupted` 重下;被收回時照上面的觸發清掉。

**理由**:

- 實測(`test_probe_queue_baseline.py`,改之前,替身的 pull 停在閘門):加入 3 筆,1 筆下載中、2 筆排隊中 → `DELETE /api/session` 回 202 → 結束後立即查佇列:下載中那筆變 `failed`、2 筆仍 `queued` → 再開到就緒,那 2 筆被自動下載成 `completed`,pull 共 3 次。這就是使用者說的「舊紀錄」與「不知道下載了沒」。
- 查證(`src/cgb/services/session_lifecycle.py:end`、`_fail_open`;`src/cgb/services/health_monitor.py:_reconnect`、`_mark_reclaimed`;`src/cgb/services/recovery.py:_reattach`;`src/cgb/services/runtime_switch.py:restart`):只有 `end()` 會呼叫 `end_listeners`(使用者結束與 `IdleMonitor._check` 的閒置結束都走它);開啟失敗(`open_failed`)、重連逾時(`lost`)、被收回(`reclaimed_fields`)、後端重啟時被收回、變更類型(舊的改 `ending`)都只呼叫 `self._repo.update`,不會清佇列。
- 查證(`src/cgb/repos/sessions.py:update`、`_changed`):每次寫入只要前後不同就呼叫所有 `listeners`;上面五條路徑全部經過這裡,所以掛一個 listener 就涵蓋 spec 列的每一種結束方式,而且是同步清除,SC-001 的 5 秒內沒有問題。
- 查證(`src/cgb/services/runtime_switch.py:restart`):現在先 `enqueue_restore` 再把舊的改 `ending`;若照舊順序,清除會把剛排入的重新載入項目一起刪掉,所以要改順序並以新名稱寫入。
- 判斷:用名稱歸屬而不是「清掉除了 origin=restore 以外的」,是因為上一次變更類型留下的、已完成的 restore 項目也屬於舊工作階段,只看 origin 會留下它。

**考慮過的替代方案**:

- 在每一條結束路徑各自呼叫清除(5 處以上):漏掉一處就留下舊紀錄,現在 `end_listeners` 就是這樣漏掉 4 條路徑。
- 把清除掛在 `end_listeners` 並補呼叫:`end_listeners` 的語意是「使用者結束」,失聯與開啟失敗也去呼叫它,會讓其他掛在上面的東西誤以為是使用者結束。
- 只清完成與失敗、保留排隊中:使用者已決定全部清除(分身決策紀錄 D7)。

## R2. Hugging Face 搜尋 API(FR-013、FR-016、NFR-005、SC-004)

**決策**:新增 Hugging Face 轉接層,搜尋打 `GET https://huggingface.co/api/models`。

- **參數**:`search=<關鍵字>&filter=gguf&gated=false&sort=downloads&limit=20&expand[]=downloads&expand[]=gated`;不帶任何 token 與 Cookie。
- **分頁**:回應標頭 `Link: <...&cursor=...>; rel="next"` 有值就表示還有下一頁;轉接層取出 `cursor` 交給 UI API,下一次原樣帶回(不是頁碼);合約怎麼放由系統分析決定。
- **逾時與失敗**:沿用 `adapters/model_library.py` 的寫法,每個請求 `asyncio.timeout(10)` 加 `httpx.Timeout(10)`、不跟著導向;逾時 → `HF_TIMEOUT`、連不到 → `HF_UNREACHABLE`、5xx → `HF_SERVER_ERROR`、其他非 200 或不是 JSON 陣列 → `HF_BAD_RESPONSE`;只影響 Hugging Face 的搜尋區(FR-016)。
- **結果**:每筆取 `id`(`<作者>/<模型>`)與 `downloads`;空陣列就是找不到(驗收情境 5)。

**理由**:

- 實測(桌機 curl,huggingface.co 公開 API,2026-11-14):`search=qwen2.5-0.5b&filter=gguf` 回 JSON 陣列,每筆有 `id`、`private: false`、`downloads`、`tags` 含 `gguf`;回應標頭有 `Link ... rel="next"` 的 cursor。
- 實測(同上):`search=gemma-3-1b&filter=gguf&expand[]=gated` 第一筆是 `google/gemma-3-1b-it-qat-q4_0-gguf`,`gated: "manual"`;加 `gated=false` 後它不再出現,其餘 5 筆都是 `gated: false`,所以需要同意條款的模型可以在伺服器端就濾掉(FR-013「不需登入即可下載」)。
- 實測(同上):`search=zzzqqqnonexist&filter=gguf` 回 200、本文 `[]`,0.21 秒;`search=qwen&filter=gguf&gated=false&limit=20` 連打 3 次 0.385–0.405 秒,遠低於 10 秒逾時。
- 查證(`src/cgb/adapters/model_library.py:ModelLibrary._get`):官方模型庫的逾時、不跟著導向與例外歸類寫法可以照搬,SC-004 的「10 秒逾時加 1 秒」沿用 002 的做法。
- 判斷:不帶 token 的請求本來就看不到私有模型,不用另外濾 `private`。

**考慮過的替代方案**:

- 抓 huggingface.co 的搜尋網頁再解析 HTML:有公開 JSON API 就不用像 001 解析 ollama.com 那樣冒改版的風險。
- 只濾 `filter=gguf`、讓需要同意條款的模型也列出來再在展開時擋:使用者會先看到一堆點不進去的模型;`gated=false` 一個參數就濾掉。

## R3. 量化版本與大小的列表規則(FR-014、FR-015)

**決策**:檔案清單取候選、Hugging Face 給 Ollama 的 manifest 端點驗證並給大小。

1. `GET https://huggingface.co/api/models/<作者>/<模型>/tree/main?recursive=true`,取 `type` 為 `file`、路徑以 `.gguf` 結尾(不分大小寫)的項目。
2. 檔名(路徑最後一段)含 `mmproj`(不分大小寫)的略過。
3. 去掉 `.gguf`,再去掉結尾的分割編號 `-\d{5}-of-\d{5}`。
4. 以 `-` 或 `.` 切開,取最後一段當量化名稱(例:`qwen2.5-0.5b-instruct-q4_k_m` → `q4_k_m`、`llama-2-7b.Q4_K_M` → `Q4_K_M`)。
5. 依檔案清單的順序去重(不分大小寫,留第一個出現的寫法)。
6. 每個量化名稱打 `GET https://huggingface.co/v2/<作者>/<模型>/manifests/<量化名稱>`(標頭 `Accept: application/vnd.docker.distribution.manifest.v2+json`),同時最多 4 個,每個 10 秒逾時:
   - 200:列出,大小 = `layers[].size` 的總和(不含 `config`,和 001 官方模型庫的算法相同);200 但 `layers` 是空的或沒有,歸 `HF_BAD_RESPONSE`、不列出(plan.md Q5,D19)。
   - 400:不列(HF 不認的量化名稱、分割檔、不是 llama.cpp 相容的 GGUF)。
   - 401:整個模型視為需要登入、同意條款、私有或不存在,展開回 FR-015 的錯誤。
   - 其他失敗:照 R2 的代碼回錯誤,整個展開失敗(FR-016)。
7. 一個都沒有列出時,回「沒有可下載的 GGUF 檔」(FR-015)。
8. 整體期限(plan.md Q4,D18):從送出第 1 步的 tree 起,tree 加上第 6 步所有 manifest 共用一個 10 秒期限,每個請求自己的 10 秒仍在;期限到時還沒完成的請求一律取消,整個展開回 `HF_TIMEOUT`,讓 SC-004 的 11 秒成立。試算、加入下載與自動下載替 `hf.co/` 名稱取大小時,每個 manifest 各自計時,不套用這個整體期限。

**理由**:

- 實測(桌機 curl,調整用 `Qwen/Qwen2.5-0.5B-Instruct-GGUF`、`bartowski/Llama-3.2-1B-Instruct-GGUF`):tree API 回每個檔案的 `path` 與 `size`;檔名有全小寫(`q4_k_m`)也有大寫(`Q4_K_M`、`f16`)。
- 實測(調整用 `bartowski/SmolLM2-135M-Instruct-GGUF` 的 23 個量化名稱逐一打 manifest):21 個回 200,`Q4_K_L`、`Q5_K_L` 回 400 `The specified tag is not a valid quantization scheme`;只看檔名列表會列出兩個拉不下來的版本,所以要用 manifest 驗證。
- 實測(調整用 `bartowski/Llama-3.2-1B-Instruct-GGUF`):`Q3_K_XL`、`Q3_K_L`、`Q6_K_L`、`Q6_K`、`Q4_K_M`、`Q4_K_S`、`F16`、`f16` 的 manifest 模型層大小都等於同名檔案的大小,`Q5_K_L` 回 400;大小寫不同的 `F16`、`f16` 回同一個大小。
- 實測(驗收用,規則定案後才打開,`hf_quants.py` 照上面 1~7 跑):

| 樣本 | 候選 | 列出(200) | 不列(400)與原因 | `latest` |
|---|---|---|---|---|
| `unsloth/Qwen3-0.6B-GGUF` | 26 | 26 | 0 | 200,等於 `Q4_K_M` 的 396,707,132 |
| `bartowski/Meta-Llama-3.1-70B-Instruct-GGUF` | 23 | 17 | `Q4_K_L`、`Q5_K_L` 不認;`Q5_K_M`、`Q6_K`、`Q6_K_L`、`Q8_0` 是分割檔(`This tag is a sharded GGUF`) | 200,等於 `Q4_K_M` 的 42,520,399,946 |

- 實測(驗收用,`hf_match.py`):列出的版本中,manifest 的模型層大小和同名檔案大小相符 43/43,不符 0。
- 實測(調整用 `google/gemma-3-1b-it-qat-q4_0-gguf`,需要同意條款):tree API 回 200,manifest 回 401;不存在的 repo 的 tree 與 manifest 也都回 401 `Invalid username or password.`,兩者分不出來,所以合成一個原因。
- 查證(Hugging Face 文件〈Use Ollama with any GGUF Model on Hugging Face Hub〉):沒寫量化版本時用 `Q4_K_M`,沒有就挑一個;量化名稱不分大小寫。
- 估算(驗收樣本 26 個版本 × 每次約 0.23 秒 ÷ 4 個同時):展開一個模型約 1.5 秒,單一請求的 10 秒逾時不變;但只靠單一請求的逾時,26 個候選每批 4 個、每批最壞 10 秒,最壞要約 70 秒,超過 SC-004 的 11 秒,所以要第 8 步的整體期限。
- 判斷:manifest 200 卻沒有模型層(plan.md Q5,D19),拉下來不是能用的模型,列出只會讓使用者下載完才發現;這次的樣本沒有遇到,歸成格式不符。
- 判斷:`mmproj` 是多模態的投影檔,不是可以單獨拉的模型;這一輪的樣本沒有出現,規則先略過,列進待驗證。

**考慮過的替代方案**:

- 只看檔名、大小用 tree 的檔案大小、不打 manifest:驗收樣本會多列 6 個拉不下來的版本,要到試算或下載才失敗。
- 照 `@huggingface/gguf` 的量化型別清單自己寫正規式判斷:HF 接受 `Q2_K_L`、`Q3_K_XL` 卻不接受 `Q4_K_L`,規則不在任何公開清單裡;以 HF 自己的 manifest 回應為準最不會錯。
- 用模型資訊 `GET /api/models/<repo>` 的 `gated` 判斷要不要登入:多一個請求,而 manifest 的 401 已經涵蓋需要同意條款、私有與不存在。

## R4. hf.co 名稱、Ollama 拉取與試算取大小(FR-018、FR-014、FR-015)

**決策**:

- **名稱格式**:`hf.co/<作者>/<模型>[:<量化版本>]`;作者與模型為 `[A-Za-z0-9][A-Za-z0-9._-]*`,量化版本沿用 001 版本的字元規則。`huggingface.co/` 前綴不接受(Ollama 把它當成另一個名稱)。合約 `ModelName` 怎麼放寬由系統分析決定。
- **補版本**:沿用 003 的 `with_version()`:不含 `:` 就接 `:latest`(`hf.co/` 本身不含 `:`)。
- **重複判定比對不分大小寫**(分身決策紀錄 D11):已下載、已在佇列、同一批合併、精選清單重複,一律把兩邊補過版本的名稱轉小寫(`str.casefold()`)後比對;顯示與送給 Ollama 的名稱照使用者輸入的原樣。官方名稱也適用,修訂 003 R1 的「不轉大小寫」。
- **試算取大小**:`DownloadsService._sized` 依前綴分流:`hf.co/` 開頭的用 Hugging Face 轉接層打 R3 第 6 步的 manifest(量化版本就是補過版本的那一段,`latest` 也照送),其他照舊打 registry.ollama.ai;400 → 阻止加入並說明「這個量化版本無法下載(不存在、分割檔或不是 GGUF)」,401 → 「需要登入、同意條款、私有或不存在」,其他照 R2 的代碼。Hugging Face 的英文原文不交給 UI(001 NFR-010)。
- **下載**:照 001 的佇列,`POST /api/pull` 帶 `hf.co/...` 名稱;進度與完成的判讀不變。

**理由**:

- 實測(臨時 Ollama 0.32.15,`POST /api/pull` `hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M`):16.5 秒完成;NDJSON 依序是 `pulling manifest`、帶 `digest` 與 `total` 的進度行、`verifying sha256 digest`、`writing manifest`、`success`,和官方模型庫的格式相同,既有的 `remote_ollama._pull_progress` 不用改。
- 實測(同上,`GET /api/tags`):`name` 與 `model` 都是 `hf.co/bartowski/SmolLM2-135M-Instruct-GGUF:Q4_K_M`,`size` 105,455,694;HF manifest 的 `layers` 總和 105,455,145 加 `config` 549 正好相等,所以試算用 `layers` 總和和官方模型庫一樣只少 config 那幾百位元組。
- 實測(同上,`POST /api/show`):`:q4_k_m` 回 200;沒寫量化版本的 `hf.co/bartowski/SmolLM2-135M-Instruct-GGUF`(= `:latest`)回 404、`huggingface.co/...:Q4_K_M` 回 404。所以 `latest` 與 `Q4_K_M` 在 Ollama 是兩個名稱,`huggingface.co/` 也是另一個名稱。
- 實測(同上,以 `:q4_k_m` 與 `hf.co/Bartowski/smollm2-135M-Instruct-GGUF:Q4_K_M` 再拉):都回 `success`,`/api/tags` 仍只有一筆、名稱維持第一次的寫法,模型資料夾 101 MB 沒有增加。Ollama 的名稱比對不分大小寫,所以本系統照原樣比對會把同一個模型當成沒下載、試算多算一份空間。
- 實測(同上,拉取失敗的情況):`:Q4_K_L` 的 error 行是 `pull model manifest: 400: ... not a valid quantization scheme`;需要同意條款的 `google/gemma-3-1b-it-qat-q4_0-gguf` 與不存在的 repo 都是 `realm host "huggingface.co" does not match original host "hf.co"`,看不出原因;不是 GGUF 的 `Qwen/Qwen2.5-0.5B-Instruct` 是 `400: Repository is not GGUF`。都不含 `file does not exist`,現有程式會歸成 `OLLAMA_PULL_FAILED`。所以要在試算與加入時先用 HF manifest 擋下,不能等拉取失敗才說明(FR-015)。
- 查證(`src/cgb/services/downloads.py:_sized`):以 `model.split(":", 1)` 拆名稱與版本後打 `get_manifest(name=..., tag=...)`,`hf.co/...` 會被送到 registry.ollama.ai 的 `/v2/library/hf.co/...`,所以一定要分流。
- 查證(`src/cgb/domain/model_name.py:with_version`):規則是 `name if ":" in name else f"{name}:latest"`,`hf.co/` 名稱不含 `:`,補版本不用改。
- 判斷:`hf.co/x/y`(latest)與 `hf.co/x/y:Q4_K_M` 在 Ollama 是不同名稱,照 FR-018 不視為重複;兩個都下載時 Ollama 共用同一份檔案,試算會多算一份空間,但不會多佔磁碟。這一輪不特別處理,列進待驗證。

**考慮過的替代方案**:

- 維持 003 照原樣比對:和 Ollama 的行為不一致(實測),分身決策紀錄 D11 否決。
- 只有 hf.co 名稱不分大小寫:兩套規則,沒有多換到什麼(D11)。
- 試算不查 HF、直接讓 Ollama 拉,失敗再說明:需要同意條款與不存在的錯誤訊息看不出原因(實測),而且已經佔了佇列與時間。
- 接受 `huggingface.co/` 前綴並轉成 `hf.co/`:spec 只要求 `hf.co/`;多一條轉換規則沒有實際好處。

## R5. 對話頁的轉送(FR-004、FR-005、FR-006、FR-007、FR-008、NFR-002、NFR-003、SC-002)

同類產品:Open WebUI —— 對照它的對話是從瀏覽器直連 Ollama,還是經後端轉送 `/api/chat` 串流。

**決策**:UI API 新增 `POST /api/chat`(在 UI 的 8780,不是 Ollama 相容端點),後端轉送到目前工作階段的遠端 Ollama `/api/chat`,NDJSON 原樣串流回瀏覽器。

- **請求**:瀏覽器只送 `model` 與 `messages`(每則 `role` 為 `user` 或 `assistant`、`content` 為字串);後端組成 `{"model", "messages", "stream": true}` 再送,不接受其他參數(spec 假設:不做 system prompt 與 temperature)。keep_alive 依 plan.md Q9(D23)改為帶 -1。
- **轉送**:取 `lifecycle.forward_target()`(沒有就緒回 503 `NO_READY_SESSION`),以 `httpx` 的 `client.send(..., stream=True)` 送出,逐段轉送沿用 `ollama_compat/forward.py` 的 `_relay`(不新增 `RemoteOllama.chat`,plan.md Q35);逾時從 `cgb.app.Timeouts` 的 `chat_connect`(10 秒)、`chat_read`(300 秒,收到第一段之前與兩段之間)注入,不直接用 `FORWARD_TIMEOUT`(plan.md Q44,D58;秒數相同,測試才能縮短)。
- **串流開始後的失敗**(plan.md Q11,D25):最後一行是本系統補的物件 `{"error": {"code", "message"}}`(合約 `ChatStreamFailure`),不是相容端點那種 `{"error": "<字串>"}`;前端以 `code` 分辨原因,代碼是 `OLLAMA_TIMEOUT`、`OLLAMA_STREAM_INTERRUPTED`、`OLLAMA_SERVER_ERROR`(遠端自己送了帶 `error` 的一行,不原樣轉送)、`OLLAMA_BAD_RESPONSE`、`SESSION_ENDED`。`_relay` 產生最後一行的方式改成由呼叫端傳入,相容端點照舊用字串,介面不變。
- **工作階段結束或失聯**(plan.md Q60,D74):對話路由傳給 `_relay` 的結束事件,在工作階段 `ending`、`ended` 之外,判定失聯(`lost`)時也設,補 `SESSION_ENDED` 的最後一行後結束轉送;Ollama 相容端點照舊只在 `ending`、`ended` 結束,不在這一輪改。
- **串流開始前的錯誤**:連不到 → 502 `OLLAMA_UNREACHABLE`;遠端回 404(模型不存在)、400、500 → 對應的 `OLLAMA_*` 代碼,UI API 的錯誤本文照 001 的 `{code, message}`;不回 500(NFR-006)。具體代碼由系統分析補進合約。
- **閒置倒數**(FR-007):轉送期間呼叫 `IdleMonitor.request_started()`,串流結束(含中斷)時 `request_finished()`,和 `ollama_compat/idle_hook.py` 相同。
- **停止**(FR-006):瀏覽器以 `fetch` + `AbortController` 讀串流,按「停止」就 `abort()`;連線斷開後 Starlette 停止迭代、關閉上游回應,遠端 Ollama 隨之取消產生。
- **耗時與每秒 token 數**(FR-005):瀏覽器自己計時(送出到收到 `done: true` 的時間)當耗時;每秒 token 數 = 最後一行的 `eval_count ÷ (eval_duration ÷ 10⁹)`。
- **正在載入**(驗收情境 6):送出前看模型目錄的已載入狀態,選的模型沒載入就在收到第一段之前顯示「正在載入模型」。
- **不寫日誌**(NFR-002):這個路由不讀出本文內容寫進任何 logger;UI 的 uvicorn access log 只記路徑與狀態碼。另外要修 `_relay` 在呼叫端中斷時留下的 `Task exception was never retrieved`(見理由),否則每按一次「停止」就多一段例外 log。

**理由**:

- 實測(`chat_relay.py`,桌機,uvicorn 起既有的 `forward()` 與一個每 0.1 秒吐一段、共 20 段的替身):直連替身第一段 0.114 秒、經 `forward()` 第一段 0.104 秒,兩者都是 21 行、總長約 2.02 秒;轉送沒有多等,SC-002 的 0.5 秒門檻有很大的餘裕。
- 實測(臨時 Ollama 0.32.15,`POST /api/chat` 三則訊息的多輪對話,`num_predict` 30):`Content-Type: application/x-ndjson`,每行 `{"message": {"role": "assistant", "content": "..."}, "done": false}`,共 31 行;最後一行 `done: true`,有 `total_duration`、`load_duration`、`eval_count` 30、`eval_duration` 762,323,000,算出約 39.4 tokens/s。
- 實測(同上,curl 直連,2 秒後斷開):Ollama 的 log 記這個請求 2.00 秒結束,並有 `srv stop: cancel task`,斷開就停止產生。
- 實測(`chat_relay.py`,經 `forward()` 轉送,讀了 58 行、2.25 秒時呼叫端斷開):Ollama 的 log 記 2.23 秒結束並 `cancel task`,停止可以穿過本系統的轉送;同時 Python 印出 `Task exception was never retrieved ... httpx.ReadError`,來自 `_relay` 裡被丟下的 `next_chunk` future。
- 查證(`src/cgb/ollama_compat/forward.py:forward`、`_relay`):已處理串流、工作階段結束補行、非預期斷線與 hop-by-hop 標頭,對話頁沿用就不必再寫一套。
- 查證(`src/cgb/services/idle_monitor.py:request_started`、`request_finished`、`_reset`;`src/cgb/ollama_compat/idle_hook.py`):重設倒數是寫 `sessions.last_request_at`,UI 路由直接呼叫同兩個方法就和 Ollama 相容端點一致。
- 查證(Open WebUI `backend/open_webui/routers/ollama.py` 的 `generate_chat_completion`,GitHub main 分支):`POST /api/chat` 由後端以 aiohttp 送到 Ollama 的 `/api/chat`,`stream` 預設 true,以 `StreamingResponse` 傳回 NDJSON;和這裡「後端轉送、不讓瀏覽器直連」是同一個做法。

**考慮過的替代方案**:

- 瀏覽器直接打 Ollama 相容端點(11436):不同 port 要處理 CORS,而且 spec 要對話走 UI 的後端;另外相容端點的白名單與 403 規則是給區網程式的。
- 以 SSE 包一層再送瀏覽器:Ollama 本來就是逐行的 NDJSON,`fetch` 讀串流就能逐段顯示,也才能用 `AbortController` 斷開;SSE 的 `EventSource` 不能送 POST 本文。
- 用 `total_duration` 當耗時:不含轉送與網路的時間,和使用者感受的「這則花了多久」不同。

## R6. 自動下載的觸發點與判定(FR-010、FR-011、FR-012、SC-003)

**決策**:就緒時檢查「這個工作階段做過自動下載沒有」,沒做過才做,結果存表。

- **觸發**:掛在 `SessionLifecycle.ready_listeners`(開啟、重連接回、後端重啟接回都會觸發);以 `auto_download_results` 表(R7)有沒有這個工作階段名稱的那一列判斷是不是第一次就緒。開始時先寫入那一列(標記執行中),所以重連或後端重啟接回時不會重排(驗收情境 8、邊界情況)。
- **判定順序**(精選清單 `auto_download = 1` 的項目,依清單順序,名稱照 R4 補版本、比對不分大小寫):
  1. 在執行環境上(`list_local_models`)或已在佇列中(含重新載入排入的)→ 不排、也不列為跳過(驗收情境 5)。
  2. 取大小(R4 的分流);失敗 → 跳過,原因「取不到大小」。
  3. 大小 > 顯示記憶體總量(沿用 003 `Catalog._vram_total` 的快取;讀不到就不檢查)→ 跳過,原因「這台可能無法載入」(和 `mayNotFit` 同一個比較 `size > vram`)。
  4. 已決定排入的大小 + 佇列中尚未完成的大小 + 這一項 > 剩餘磁碟空間(`probe_resources` 讀一次)→ 跳過,原因「空間不足」;後面較小的仍照順序判斷。
  5. 其餘排入。
  - 取大小同時最多 4 個,每個 10 秒逾時。
  - 讀不到剩餘空間時(plan.md Q52,D66;spec FR-012):第 2、3 步已判定跳過的項目保留原本的原因(「取不到大小」「這台可能無法載入」),其餘還沒判定的都跳過,原因「讀不到剩餘空間」(`DISK_SPACE_UNKNOWN`,plan.md Q17),沒有任何一項排入(沿用 001 不把讀不到當成夠用)。
- **寫入**:排入的一次 `enqueue_many(..., origin="auto")`,寫入當下工作階段名稱,再 `kick()`;結果(排入數量、每個跳過的名稱與原因)寫回那一列並推送事件,`dismissed` 預設否。
- **讀取與清除**:模型頁下載佇列上方的提示區讀 UI API 取得這個工作階段的結果(plan.md Q29,D43;重新整理仍在);按關閉寫 `dismissed`;工作階段結束時照 R1 一併刪除那一列。

**理由**:

- 查證(`src/cgb/services/session_lifecycle.py:_notify_ready`):`ready_listeners` 在每次「不是就緒 → 就緒」時呼叫,重連成功(`health_monitor._reconnect` 把狀態改回 `ready`)與後端重啟接回(`Recovery._run`)也會觸發;只靠 listener 分不出第一次就緒,所以要另外記。
- 查證(`src/cgb/services/session_lifecycle.py:_new_name`、`src/cgb/services/health_monitor.py:_reconnect`):每次開啟與變更類型都產生新名稱,重連沿用原名稱,所以「這個名稱做過沒有」就等於「這個工作階段做過沒有」(003 R3 同一個依據)。
- 查證(`src/cgb/services/catalog.py:list`、`_vram_total`):`mayNotFit` 是 `m["size"] > vram`,讀不到時是 null;自動下載用同一個比較與同一份快取,符合 FR-012「和模型目錄同一個判斷」。
- 查證(`src/cgb/services/downloads.py:_estimate`、`src/cgb/domain/estimate.py:estimate`):剩餘空間比較是 `total + pending_queue_bytes <= free_disk_bytes`,讀不到剩餘空間回 503 `DISK_SPACE_UNKNOWN`;自動下載照這個算法逐項累加。
- 估算(R2、R3 實測每個 manifest 約 0.23 秒;最壞情況每個 10 秒逾時,4 個同時):精選清單 8 項全部逾時約 20 秒,加上 `probe_resources` 一次 `colab exec`,仍在 SC-003 的 30 秒內;清單更長時每多 4 項最壞多 10 秒,列進待驗證。
- 判斷:存表而不是只放記憶體,是因為 spec 要求後端重新啟動接回時不重排、提示仍讀得到。

**考慮過的替代方案**:

- 在 `sessions` 表加一個「已自動下載」欄位:結果(跳過的名稱與原因、已關閉)還是要另外存,不如一張表一起放。
- 只在 `SessionLifecycle._open_steps` 結尾觸發(只有開啟會走):後端重啟時正在開啟的工作階段由 `Recovery` 接回就緒,會漏掉;以表判斷不管哪條路徑都一致。
- 一次排入全部、讓下載失敗再說:違反 FR-012 的空間與顯示記憶體判斷。

## R7. 既有資料庫的遷移(NFR-004、FR-010、FR-001)

**決策**:`create_schema` 之後依 `PRAGMA user_version` 跑遷移,版本 0 → 1 在一個交易裡做完。

- `curated_models`:`ALTER TABLE ... ADD COLUMN auto_download INTEGER NOT NULL DEFAULT 0 CHECK (auto_download IN (0, 1))`;先以 `PRAGMA table_info` 確認欄位不存在才加。排列順序沿用 `id`(新增的順序,修改不變)。
- `download_jobs`:因為 `origin` 的 CHECK 要加 `'auto'`(SQLite 不能改 CHECK),建 `download_jobs_new`(原欄位 + `origin IN ('user','restore','auto')` + `session_name TEXT REFERENCES sessions (name)`)→ 複製原資料 → 刪舊表 → 改名 → 重建 `idx_download_jobs_state`。
- 新表 `auto_download_results`(R6):`session_name` 主鍵、狀態、排入數量、`dismissed`;排入與跳過的明細改存子表 `auto_download_items`(plan.md Q26),欄位細節以 `contracts/store.dbml` 為準。
- 不分大小寫的比對(R4、plan.md Q25):`curated_models` 加 `lower(name)`、`download_jobs` 加 `lower(pending_model)` 的唯一索引,在遷移完成之後才建(plan.md Q28)。
- 建索引前先去重(plan.md Q40,D54):001 的名稱其實不全是小寫(版本允許大寫,`api/curated.py` 沒有驗格式),舊庫可能同時有 `qwen2.5:latest` 與 `qwen2.5:Latest`;所以在同一個交易裡,兩張表各以 `lower(name)`、`lower(pending_model)` 分組,每組只留 `id` 最小的那一筆、其他刪掉,刪掉的名稱逐筆寫進日誌(warning),再建唯一索引。任何一步失敗整個交易 rollback,資料庫維持遷移前的樣子。
- 全新資料庫:`create_schema` 直接建新版的表,並設 `user_version = 1`。
- 下載項目的來源(官方或 Hugging Face)由名稱前綴 `hf.co/` 判斷,不另存欄位。

**理由**:

- 查證(`src/cgb/db/schema.py:create_schema`):全部是 `CREATE TABLE IF NOT EXISTS`,沒有任何遷移;已經有資料庫的使用者升級後,新欄位不會出現。
- 實測(`migrate.py`,桌機 SQLite 3.53.1,以現行 `create_schema` 建庫並寫入 2 筆精選、1 筆下載後跑遷移草稿):精選的 2 筆保留,`auto_download` 都是 0,建議類型 H100 的那筆照常是 H100;下載的 1 筆保留,`origin` 仍是 `user`、`session_name` 是 NULL;寫入 `origin = 'auto'` 成功;同名 `pending_model` 仍被 `UNIQUE constraint failed` 擋下;再跑一次 `create_schema` 不出錯,`user_version` 是 1。
- 判斷:舊資料的 `session_name` 是 NULL,照 R1 在後端啟動與第一次結束時清掉,不影響之後的行為。
- 查證(`src/cgb/api/curated.py`、001 `ui.openapi.yaml` 的版本字元規則):名稱的版本可以有大寫,新增精選時沒有驗格式,所以「001 的名稱只收小寫、不會撞到」不成立;不去重的話,舊庫有只差大小寫的兩筆時建索引失敗、遷移 rollback,之後每次啟動都失敗(plan.md Q40 的 Context)。
- 判斷:只差大小寫的兩筆(D54)在 Ollama 是同一個模型(R4 實測),留一筆不會少任何東西;排隊中的舊項目照 R1 開機時本來也會清掉。

**考慮過的替代方案**:

- 直接刪掉 `download_jobs` 重建、不複製:升級時若剛好有接回中的工作階段,它的佇列會消失。
- 引入 Alembic 之類的遷移工具:這一輪不新增套件,而且只有一次遷移。
- `origin` 改成不設 CHECK:就不用重建表,但少了 001 合約要求的限制。
- 有衝突就不建唯一索引、只靠程式檢查,或把重複的改名:前者兩套行為看資料庫而定,後者留下使用者沒取過的名稱;分身決策紀錄 D54 否決。

## 待驗證

| 來源 | 待驗證 | 驗證方式 / 時機 | 擋計畫? |
|---|---|---|---|
| R4 | 遠端 Colab 上的 Ollama(安裝時取最新,001 實測 0.40.15)拉 hf.co 模型的進度格式、名稱比對不分大小寫,和本機 0.32.15 相同 | testplan 停下來問使用者要不要實跑;這一輪不開 Colab | 否 |
| R3 | 含 `mmproj` 的多模態 repo 與 TheBloke 式 `<模型>.<量化>.gguf` 檔名(這次的樣本都沒有) | 實作時以 tree API 的替身各放一筆;之後遇到再補 | 否 |
| R4 | `hf.co/x/y`(latest)與 `:Q4_K_M` 同時下載時,試算多算一份空間 | 範圍外(FR-018 不視為重複),留給之後 | 否 |
| R5 | 真的工作階段上,經 SSH 轉發與 UI 轉送的第一段延遲 | testplan 決定要不要實跑;替身已量到轉送不多等 | 否 |
| R6 | 精選清單超過 8 個自動下載項目且 HF 全部逾時時,能否在 30 秒內給出結果 | 實作時以延遲替身量 | 否 |

## 修訂紀錄

- R5:2026-11-14 system-analysis 依 plan.md Q9(D23),對話請求改為帶 `keep_alive: -1`。
- R7:2026-11-14 system-analysis 依 plan.md Q25、Q26、Q28(D39、D40、D42),跳過明細改存子表、加不分大小寫的唯一索引並排在遷移之後。
- R3:2026-11-14 analyze 第 1 輪回修,依 plan.md Q4、Q5(D18、D19),補展開版本的整體 10 秒期限(第 8 步),以及 manifest 200 但沒有模型層時歸 `HF_BAD_RESPONSE`、不列出。原因:research 寫在這兩個決定之前,只有單一請求的逾時,最壞約 70 秒不符 SC-004(analysis.md A38 (a))。連帶:無。
- R5:2026-11-14 analyze 第 1 輪回修,依 plan.md Q11、Q60、Q44(D25、D74、D58),串流開始後的最後一行從字串改成 `{"error": {"code","message"}}` 物件,失聯時對話頁也結束轉送(相容端點不變),逾時從沿用 `FORWARD_TIMEOUT` 改成 `Timeouts.chat_connect`、`chat_read` 注入。原因:照舊寫法前端分不出原因,和合約 `ChatStreamFailure` 不符(analysis.md A6、A26)。連帶:無。
- R6:2026-11-14 analyze 第 1 輪回修,依 plan.md Q52、Q29(D66、D43)與 spec FR-012(D82),讀不到剩餘空間時從「全部跳過、原因都改成讀不到剩餘空間」改成保留已判定的原因、只有還沒判定的標 `DISK_SPACE_UNKNOWN`;提示區從下載頁改成模型頁下載佇列上方。原因:舊寫法會把已跳過的項目改標(analysis.md A5、A13)。連帶:無。
- R7:2026-11-14 analyze 第 1 輪回修,依 plan.md Q40(D54),建不分大小寫的唯一索引前,在同一個交易裡每組留 `id` 最小的一筆、其他刪掉並寫進日誌。原因:001 的名稱不全是小寫,不去重時遷移 rollback、後端起不來(analysis.md A2)。連帶:R4 的不分大小寫比對不變。
