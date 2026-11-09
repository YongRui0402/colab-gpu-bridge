# Phase 0 Research: Colab GPU 工作階段管理與模型目錄

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-11-09

使用者指定的技術方向:

- 控制 Colab:Google 官方 Colab CLI(spec 假設;使用者在 specify 時提出「colab cli 應該可以處理」)。
- 連線:不得使用公開網址(spec NFR-003)。
- 部署:容器交付,先在 Ubuntu 桌機驗收,最終部署到 Unraid(spec NFR-012)。
- 前端、後端、資料庫:未指定。

每個「理由」都標出證據類型:**實測**(附量測環境)、**估算**(附依據)、**查證**(附來源)、**判斷**(推論)。探針腳本放在 session 暫存區,不進 repo;Colab 端的實測由使用者在場授權(Drive 授權兩次),本次共用掉 1.29 compute units(`colab usage` 381.66 → 380.37)。要在 testplan 的「實跑」案例、真實 Colab Pro 帳號上重測的項目列在「待驗證」。

量測環境代號:

- **桌機**:Ubuntu,i5-9400F,Docker 29.1.3,Ollama 0.32.15,google-colab-cli 0.7.5
- **T4**:Colab Pro,`colab new --gpu T4`,區域 usw4,Tesla T4 15360 MiB,磁碟 236G,Ollama 0.40.15
- **CPU**:Colab Pro,`colab new`(未指定加速器),區域 euw4,2 vCPU、12GB RAM

---

## R1. 以 Colab CLI 控制執行環境(FR-001、FR-002、FR-003、FR-005、FR-006、FR-007、FR-009、FR-024、SC-001、SC-003)

**決策**:後端以子行程呼叫 `colab`(google-colab-cli 0.7.5),每個指令都解析文字輸出、不信任 exit code。

- **開啟**:`colab new -s <名稱> [--gpu <類型>] [--high-mem]`,名稱固定前綴 `cgb-`,由本系統產生並記錄。
- **遠端初始化**:`colab exec -s <名稱> -f <初始化腳本>`,腳本安裝 Ollama 並以 `OLLAMA_HOST=127.0.0.1:11434`、`OLLAMA_ORIGINS=*`(plan.md Q20)、`start_new_session=True` 背景啟動。
- **狀態**:`colab sessions` 每行一台,格式 `[<名稱>] <endpoint> | Hardware: <類型> | Shape: <形狀> | Variant: <變體>`;本機沒紀錄的那台顯示為 `[?]`。
- **用量**:`colab usage` 三行固定格式 `Current balance: <x> compute units` / `Usage rate: <x>/hr` / `Active assignments: <n>`。
- **結束**:`colab stop -s <名稱>` 之後,必須再以 `colab sessions` 確認該名稱已不在,才算結束(FR-007、SC-003)。
- **重試**:`colab exec` 的 WebSocket 會偶發 `Connection was lost`,同一指令重試一次;重試仍失敗才算開啟失敗。

**理由**:

- 實測(桌機 → T4):

| 步驟 | 結果 |
|---|---|
| `colab new -s probe-t4 --gpu T4` | 13.7 秒到 `Session READY` |
| `colab exec` 安裝 Ollama 並啟動 | 43 秒(其中安裝 34.6 秒);只聽 `127.0.0.1:11434` |
| 開啟到 Ollama 可回應 | 約 57 秒,遠低於 SC-001 的 5 分鐘 |
| `colab new -s probe-cpu`(CPU) | 5 秒 |
| `colab usage`(T4 運作中) | `Usage rate: 1.15/hr`,`Active assignments: 1` |
| `colab usage`(T4 + CPU) | `1.23/hr`,即 CPU 約 0.08/hr |
| `colab stop -s probe-cpu` 後 `colab sessions` | 只剩 probe-t4,`Active assignments: 1` |
| `colab stop -s probe-none`(不存在) | 印 `Session 'probe-none' not found.`,**exit 0** |
| `colab drivemount` 掛載失敗 | 印出 `ValueError: mount failed`,**exit 0** |
| `colab exec`(CPU)一次 | `RuntimeError: Connection was lost`,執行環境仍在,重跑成功 |

- 實測(桌機):`uv tool install google-colab-cli` 先裝到快取中的 0.7.1,沒有 `usage` 指令;`uv tool install -U` 後為 0.7.5(PyPI 最新,2026-10-20)才有。版本必須在映像中釘死為 0.7.5。
- 查證(google-colab-cli 0.7.5 `colab_cli/consumption.py`:`format_consumption_status`):`usage` 輸出就是上表三行,來源是 `GET /tun/m/ccu-info` 的 `currentBalance`、`consumptionRateHourly`、`assignmentsCount`。
- 查證(`colab new --help`,0.7.5):`--gpu` 支援 T4、L4、G4、H100、A100,「Availability varies by Colab subscription tier」;`--high-mem` 需 Pro/Pro+,L4 會忽略。
- 判斷:exit code 在 stop、drivemount 兩處都不反映結果,所以 adapter 一律依輸出文字判斷,並以 `sessions` 回讀確認狀態。
- 判斷:CLI 的後端端點是逆向 HAR 而來(README 自述),Google 改後端就可能壞;所有呼叫集中在一個 adapter,測試用替身,另以實跑案例偵測 CLI 壞掉。

**考慮過的替代方案**:

- 直接 import `colab_cli` 的內部類別(`Client`、`ColabRuntime`):少一層子行程,但不是公開 API,版本一升就可能改名;子行程的文字輸出至少有 `--help` 可對照。
- 使用者手動開 notebook、notebook 回報(原提案):spec 已改為一鍵開關。

## R2. 在 UI 內完成 Colab 登入(FR-008、NFR-012)

**決策**:後端直接執行與 CLI 相同的 OAuth 流程(`google_auth_oauthlib.flow.InstalledAppFlow`,用 CLI 內建的 client 設定、`redirect_uri=https://sdk.cloud.google.com/applicationdefaultauthcode.html`、`token_usage=remote`),把授權網址交給 UI,UI 收到使用者貼回的授權碼後換 token,寫入 `~/.config/colab-cli/token.json`(容器內掛載的 volume)。

- 判斷是否已登入:執行 `colab usage`,成功即已登入;失敗訊息含授權相關字樣即「需要登入」。
- token 過期時 CLI 會自己用 refresh token 更新;refresh 失敗才回到 UI 登入。

**理由**:

- 查證(google-colab-cli 0.7.5 `colab_cli/auth.py`:`_run_remote_flow`、`_get_google_auth_credentials`):授權網址印到 stderr,授權碼用 `input()` 從 stdin 讀;token 寫到 `TOKEN_CONFIG_PATH = ~/.config/colab-cli/token.json`(檔案,不是 README 說的 OS keyring);下次啟動先讀檔、過期就 `creds.refresh`。
- 實測(桌機,既有 token.json):`colab usage`、`colab sessions` 不需重新登入即可回應。
- 實測(桌機 Docker,`python:3.12-slim` + CLI 0.7.5,只掛載複製出來的 `token.json` 到 `/root/.config/colab-cli`):容器內 `colab usage` 與 `colab sessions` 都成功。
- 判斷:直接跑同一套 flow 比用 pipe 驅動 `input()` 穩定(不必解析 stderr、不受提示字樣改版影響),產出的 token.json 格式與 CLI 相同,CLI 照樣讀得到。

**考慮過的替代方案**:

- 子行程驅動 CLI 的 `input()`:可行,但要解析 stderr 的網址、等 prompt,改版就壞。
- ADC(`gcloud auth application-default login`):要在主機裝 gcloud,UI 內做不到。

## R3. 不經公開網址的連線(NFR-003、FR-004、FR-011、SC-002、SC-005)

**決策**:後端以 OpenSSH 建立本機轉發 `ssh -N -L 127.0.0.1:<本機port>:127.0.0.1:11434 root@colab-runtime`,`ProxyCommand` 是 CLI 的 `colab ssh --proxy-mode -s <名稱>`(WebSocket 走 Colab 自己的執行環境代理);金鑰用 ed25519。

- ssh 參數:`ServerAliveInterval=15`、`ServerAliveCountMax=3`、`ExitOnForwardFailure=yes`、`StrictHostKeyChecking=no`、`UserKnownHostsFile=/dev/null`。
- **健康檢查**:每 15 秒打一次本機轉發的 `/api/version`;失敗即「重連中」,重新拉起 ssh;重連時限 5 分鐘(spec 假設)內接不回,或 `colab sessions` 已沒有這台,才標「失聯」。
- **token 期限**:已建立的 ssh 連線不受 runtime proxy token 1 小時期限影響,不需要定時重建;只有新建連線時才需要有效 token(CLI 會在剩 5 分鐘內自動換新)。

**理由**:

- 實測(桌機 → T4,通道建立後):`/api/version` 5 次平均 0.321 秒(spike 的 cloudflared quick tunnel 為 0.266 秒);桌機只聽 `127.0.0.1:11435`,runtime 的 Ollama 只聽 `127.0.0.1:11434`,沒有任何公開網址。
- 實測(桌機 → T4):`/api/pull` 的串流 432 行(416 行含進度)完整穿過通道。
- 實測(桌機 → T4,模擬斷線:殺掉 ssh 行程):斷線時 HTTP 000;`colab sessions` 仍列出同一台;重新建立通道 2.33 秒,`/api/ps` 顯示 qwen2.5:7b 仍在記憶體。
- 查證(google-colab-cli 0.7.5 `commands/ssh.py`):目標是 `root@colab-runtime`,公鑰放在 `X-Colab-Ssh-Pubkey` header,伺服器拒絕 RSA;proxy token 只在連線建立時出示,長連線不會中途更新(模組說明)。
- 查證(`client.py` 的 `token_expires_in_seconds`、本機 `sessions.json`):probe-t4 的 `token_expires_at` 為建立後 1 小時(22:17:28)。
- 實測(桌機 → T4,21:28:14 建立的 ssh 轉發,建立時出示的是 22:17:28 到期的 token):每 15 秒檢查一次 `/api/version`,到 22:20:31 從未失敗;22:20:45 對 qwen2.5:7b 推論成功。期間其他 CLI 指令已把 `sessions.json` 的 token 換新為 23:10 到期,但不影響這條既有連線。
- 判斷:健康檢查 15 秒加 ssh keepalive 45 秒,斷線最晚約 1 分鐘內進入「重連中」,符合 SC-002(修訂後)的「斷線 1 分鐘內顯示重連中」。

**考慮過的替代方案**:

- cloudflared quick tunnel(spike 用過):有公開網址,違反 NFR-003。
- Tailscale 裝在 runtime 裡:要多一個帳號與 tailnet,runtime 每次重開都多一台裝置要清;官方 CLI 已提供 SSH,不必再引入。
- 反向 SSH 到家裡的主機:要在家裡開對外的 SSH,碰共用服務。

## R4. Drive 掛載與模型存放(FR-014、FR-015、FR-016、FR-019、NFR-005、SC-004)

**決策**:第一個迭代不使用 Google Drive;模型存在執行環境的本機磁碟(`OLLAMA_MODELS` 用預設的 `/root/.ollama/models`),執行環境結束就消失。使用者依本研究的實測拍板,spec 已修訂(FR-019、FR-023 移除,NFR-005、SC-004 改寫)。

**理由**:

- 實測(T4,第一次 `colab drivemount`):要求授權,印出 Google 授權網址並等待 Enter;使用者同意後「Credentials propagated」,但 `drive.mount` 回 `mount failed`;DriveFS 日誌 `Account context authorization failed`,時間點早於憑證轉送。第二次 `drivemount` 不再要求授權,14 秒 `Mounted at /content/drive`。
- 實測(CPU,新執行環境):**又要求授權一次**;同意後第一次又 `mount failed`,重試 27 秒成功。兩台都重現「授權後第一次必失敗、重試成功」。
- 查證(Colab FAQ「Why does "Mount Drive" sometimes insert code into the notebook?」):「We usually require that users manually grant this access every time they connect to a new runtime」。
- 查證(google-colab-cli 0.7.5 `commands/automation.py`:`run_automation` 的 `drivefs_hook`):先以 `dryrun=true` 問憑證轉送,`success` 為否時印 `unauthorized_redirect_uri`,從 `/dev/tty`(沒有就 stdin)等使用者按 Enter,再正式轉送。
- 查證(同上,授權網址的 scope):包含 `https://www.googleapis.com/auth/drive`,也就是執行環境取得整個 Drive 的存取權,不只模型資料夾。
- 實測(T4):`cp -r` 4.4GB 模型目錄(qwen2.5:7b)到 Drive 39.3 秒。之後立刻第一次載入 qwen2.5:7b 得到 load 87.9 秒、0.1 tokens/s,判為受 Drive 回寫搶 I/O 影響的異常值;暖機後兩次為 40.8、42.5 tokens/s(模型 100% 在 VRAM)。
- 實測(CPU,euw4,同一台機器比較):

| 來源 | 4.68GB(qwen2.5:7b 權重 blob) |
|---|---|
| Drive 冷讀(`cat > /dev/null`) | 88.3 秒,53.0 MB/s |
| Drive 第二次讀(本機快取) | 29.0 秒 |
| 網路下載(`registry.ollama.ai` blob) | 169.5 秒,27.6 MB/s |

- 實測(T4,usw4):Ollama 從網路 `pull` 同一個模型 48.7 秒(約 96 MB/s)。
- 實測(第二台 T4,`colab new` 161 秒,區域 ass1,同一台機器比較,與 CPU 那台是不同區域):

| 來源 | 4.68GB(qwen2.5:7b 權重 blob) |
|---|---|
| Drive 冷讀(授權、第一次 mount failed、重試後掛上) | 145.2 秒,32.3 MB/s |
| Drive 第二次讀(本機快取) | 19.7 秒 |
| 網路下載(`registry.ollama.ai` blob) | 61.9 秒,75.7 MB/s |

- 判斷:GPU 執行環境上網路下載比 Drive 冷讀快 2.3 倍;只有網路慢的 CPU 那台(27.6 MB/s)Drive 才快。原 NFR-005「Drive 載入短於網路下載」在預設的 GPU 類型上不成立。
- 判斷:Drive 每台新的執行環境都要使用者到瀏覽器授權一次、授權後第一次掛載必失敗、拿到的是整個 Drive 的權限;用它換不到速度,反而讓「一鍵開啟」多一個人工步驟。

**考慮過的替代方案**:

- Drive 為主(原 spec):GPU 上較慢且每次要授權,使用者決定拿掉。
- Drive 當可選快取:對 Ollama 官方庫沒有的模型有用,但第一迭代沒有這種需求,留到之後。
- 複製到本機磁碟再載入(Drive → `/root/.ollama`):仍受 Drive 冷讀 32–53 MB/s 限制,不會比網路快。

## R5. 下載模型在哪裡執行(FR-017、FR-020、FR-021、FR-022、NFR-007、SC-004、SC-008)

**決策**:在目前的工作階段上,由後端經通道呼叫遠端 Ollama 的 `POST /api/pull`(串流進度),一次一個依佇列順序執行;進度事件經 SSE 推給 UI。預估下載時間用 manifest 的大小 ÷ 50 MB/s 估算並標示為估計值。

**理由**:

- 實測(桌機 → T4):背景 `pull` llama3.2:3b 期間,`qwen2.5:7b` 產生 16 token 的請求 5 次平均 0.571 秒,沒有下載時 0.572 秒;量測時下載仍在進行。
- 實測(CPU):CPU 執行環境約 0.08 compute units/小時,T4 約 1.15。
- 實測(桌機 → T4,usw4):經通道 `/api/pull` qwen2.5:7b(4.68GB)48.7 秒,串流 432 行;加上推論前的載入,符合 SC-004 的 3 分鐘。
- 估算(本研究三台的網路下載 27.6–96 MB/s,取中間 50 MB/s):4.7GB 約 94 秒,作為 UI 的預估值。
- 判斷:Drive 已拿掉(R4),「另開 CPU 執行環境下載後存 Drive」與「本機下載後上傳 Drive」兩個候選都失去意義;在工作階段上直接 pull 不需要額外的執行環境,也不吃家裡頻寬。

**考慮過的替代方案**:

- 另開一台 CPU 執行環境專門下載到 Drive:Drive 已拿掉;CPU 那台網路只有 27.6 MB/s。
- 本系統所在主機下載後上傳 Drive:Drive 已拿掉;且吃家裡上傳頻寬。
- 由後端直接從 registry 抓 blob 再傳上 runtime:多經家裡一次,沒有好處。

## R6. 官方模型庫的搜尋與版本(FR-020)

**決策**:

- **大小與 digest**:用官方 registry 的 OCI manifest `GET https://registry.ollama.ai/v2/library/<名稱>/manifests/<版本>`(`Accept: application/vnd.docker.distribution.manifest.v2+json`),各層 `size` 相加即模型大小。
- **搜尋與版本清單**:解析 `https://ollama.com/search?q=<關鍵字>` 與 `https://ollama.com/library/<名稱>/tags` 的 HTML;解析失敗時 UI 只顯示精選清單與「輸入名稱」(spec 假設的退路)。
- 精選清單是本系統自己的資料,不依賴 ollama.com。

**理由**:

- 實測(桌機,2026-11-09):

| 介面 | 結果 |
|---|---|
| `ollama.com/api/tags` | JSON,但只有 23 個雲端模型(glm-5.2、kimi-k2.6…),不是完整模型庫 |
| `ollama.com/search?q=qwen2.5` | HTML,`href="/library/<名稱>"` 可解析出 qwen2.5、qwen2.5-coder、qwen2.5vl… |
| `ollama.com/library/qwen2.5/tags` | HTML,解析出 133 個版本,各有大小(例 0.5b 398MB) |
| `registry.ollama.ai/v2/library/qwen2.5/tags/list` | 404 |
| `registry.ollama.ai/v2/library/qwen2.5/manifests/7b` | 200,4 層,合計 4.68 GB |

- 判斷:沒有正式的搜尋 API;HTML 解析是唯一能做到 FR-020 搜尋的方式,但頁面改版就會壞,所以集中在一個 adapter 並有退路。

**考慮過的替代方案**:只用精選清單(放棄搜尋)。使用者已選「官方庫搜尋 + 精選」,且查得到可用的頁面,所以保留搜尋並保留退路。

## R7. 刪除模型時的共用檔(FR-023)

**決策**:不需要實作;FR-023 隨 Drive 一起移除(R4)。若之後的迭代要加回刪除,直接呼叫遠端 Ollama 的 `DELETE /api/delete`,不必自己判斷共用的 blob(下列實測)。

**理由**:

- 實測(桌機,隔離的 Ollama 0.32.15,獨立 `OLLAMA_MODELS` 與 port):qwen2.5:0.5b 加一個 `FROM qwen2.5:0.5b` 的衍生模型共 7 個 blob;刪衍生模型後剩 5 個,基底模型照常推論;再刪基底模型後剩 0 個。Ollama 只刪沒有被其他模型引用的 blob。
- 判斷:Colab 上是 0.40.15;第一迭代不刪除,不必再驗。

**考慮過的替代方案**:自己比對各 manifest 的 digest 決定可刪的 blob:Ollama 已經做了,重寫只會多一個出錯的地方。

## R8. Ollama 相容端點(FR-011、FR-012、FR-013、FR-016、SC-005、SC-007)

**決策**:後端用 FastAPI + httpx,端點以串流原樣轉送(`client.send(..., stream=True)` + `StreamingResponse(r.aiter_raw())`);管理操作(`/api/pull`、`/api/delete`、`/api/create`、`/api/copy`、`/api/push`、`/api/blobs/*`)直接回 403 與繁體中文說明;只轉送 FR-011 點名的推論與查詢路徑(白名單,plan.md Q18),白名單外回 404;沒有就緒的工作階段時 1 秒內回 503(SC-007)。模型自動載入交給遠端 Ollama 本身(它收到指名的模型就會從 `OLLAMA_MODELS` 載入)。

**理由**:

- 實測(桌機,fastapi 0.162.2、uvicorn 0.54.0、httpx 0.28.1,上游為本機 Ollama 0.32.15 的 qwen2.5:3b,非串流 8 token,每組 5 次):直連平均 0.105 / 0.097 秒,經代理 0.101 / 0.104 秒,差距在雜訊內(SC-005 門檻 0.5 秒);串流逐段轉送;`/api/pull` 回 403。
- 查證(Ollama API:`/api/generate` 指名的模型不在記憶體時會先載入):遠端只要 `OLLAMA_MODELS` 指向模型所在,FR-016 不必由本系統實作載入。
- 判斷:同類產品 LiteLLM(功能過多,要轉成 OpenAI 格式)、ollama-proxy-server(加的是金鑰與佇列,不需要);我們只需要原樣轉送加路徑白名單(plan.md Q18),自寫約 30 行。

**考慮過的替代方案**:

- LiteLLM:會改寫成 OpenAI 格式,和「Ollama 相容」相反。
- Nginx 反向代理:擋路徑做得到,但「沒有工作階段就回 503」、閒置計時(FR-026)要寫在應用程式裡,最後還是得有應用程式層。

## R9. 前端做法(使用者故事 1–4 的 UI、NFR-011)

**決策**:原生 HTML / CSS / JS,不用框架與建置工具,由 FastAPI 提供靜態檔;狀態更新用 Server-Sent Events(sse-starlette)。

**理由**:

- 查證(同類產品):Open WebUI 用 SvelteKit SPA(功能是聊天,遠比我們多);Dozzle(容器日誌)用 Vue SPA 但由後端內嵌靜態檔;Uptime Kuma 用 Vue + Socket.IO 推狀態。共通點是「狀態用伺服器推送」,不靠前端輪詢。
- 判斷:畫面規模小(原型最後交出工作階段、登入、模型目錄、下載模型、用量與設定、紀錄 6 頁,加上狀態總覽),沒有複雜互動;ui-plan 交出的原型本身就是原生 HTML/CSS/JS,直接沿用可少一次轉寫。SSE 是單向推送,剛好對應狀態、進度、倒數。

**考慮過的替代方案**:

- React/Vue SPA:要加建置工具與 node 依賴,容器多一個 build 階段;規模不需要。
- WebSocket:要雙向時才需要;UI 的操作用一般 REST 即可。

## R10. 狀態與紀錄的保存(FR-005、FR-028、NFR-012)

**決策**:SQLite(Python 標準函式庫 `sqlite3`,WAL 模式)存工作階段紀錄、下載項目、精選清單與設定;CLI 的 `~/.config/colab-cli/`(token.json、sessions.json)與 SQLite 檔都放在同一個掛載的資料夾。後端啟動時:讀 SQLite 最後一筆未結束的工作階段 → `colab sessions` 確認那個名稱還在 → 重建 ssh 轉發 → 回到「就緒」;不在就標「失聯」。

**理由**:

- 實測(桌機 Docker,`sessions.json` 為空):`colab sessions` 仍列出伺服器上的 T4,但名稱顯示 `[?]`;所以 CLI 的 `sessions.json` 必須持久化,本系統才認得自己開的那台。
- 判斷:`[?]` 正好用來實作邊界情況「不是本系統開的執行環境:不接手、不關閉,只提示」。
- 判斷:單一使用者、資料量小(幾十筆紀錄),SQLite 足夠,不必另起資料庫容器。

**考慮過的替代方案**:JSON 檔(並行寫入要自己鎖)、PostgreSQL(要多一個容器,規模不需要)。

## R11. 容器化(NFR-009、NFR-010、NFR-012)

**決策**:單一映像 `python:3.12-slim` + `openssh-client` + `google-colab-cli==0.7.5` + 本系統;compose 一個服務,port 綁區網介面,資料夾掛到 `/data`(含 `colab-cli/`、`ssh/`、SQLite)。

**理由**:

- 實測(桌機 Docker 29.1.3):上述映像 build 96 秒,131 MB;掛載 token.json 後容器內 `colab usage`、`colab sessions` 成功。
- 判斷:區網開放、不對外(NFR-009)由 compose 的 port 綁定處理,不經 NPM(spec 假設)。

**考慮過的替代方案**:

- 主機直接跑(不用容器):最終要上 Unraid,容器才符合 NFR-012「一份 compose 加一份環境變數檔」。
- 拆成後端與前端兩個容器:前端只是靜態檔,由 FastAPI 一起提供即可。

## R12. 測試框架與替身邊界(全部故事)

**決策**:pytest 9.2.0 + pytest-asyncio;API 層用 httpx 的 ASGI transport 直接打 FastAPI;UI 用 Playwright(Python)。外部依賴全部藏在 adapter 後面:`ColabControl`(CLI 子行程)、`Tunnel`(ssh)、`RemoteOllama`(HTTP)、`ModelLibrary`(ollama.com / registry)。自動化測試以替身取代 adapter;每個 adapter 至少一個打真實服務的實跑案例。

**理由**:

- 判斷:R1 證明 CLI 的 exit code 不可信、R4 證明授權後第一次掛載必失敗;這些行為替身要照實模擬,否則測試全綠也偵測不到。
- 判斷:實跑案例會用掉 compute units、需要使用者登入 Colab,由 testplan 標出花費與「需要本人在場」。

**考慮過的替代方案**:

- 測試時打真的 Colab:每跑一次都花點數、要人在場,不能當成自動化測試。
- 用 `unittest.mock` 在函式層 patch:替身會長在內部模組,違反「替身只在系統邊界」。

## R13. 條款風險(假設)

**決策**:採用官方 CLI 的 SSH 通道,只轉送一個 port 給自己的區網使用;餘額歸零時依 spec 的邊界情況處理(SSH 會被禁止,依失聯處理)。風險照實寫進 README。

**理由**:

- 查證(Colab FAQ「Which activities are restricted in Colab?」,2026-11-09 讀取):所有方案禁止「connecting to remote proxies」與「web service offerings not related to interactive compute with Colab」;免費或餘額非正時另外禁止「remote control such as SSH shells」與「bypassing the notebook UI to interact primarily via a web UI」,並說付費且維持正餘額可解除。
- 查證(Colab ToS,Last Modified 2026-08-13,「Using Colab」):不得「sell, rent, or otherwise provide direct or indirect access to Colab to any third party」。
- 查證(FAQ 與 ToS):都沒有提到 Colab CLI。
- 判斷:SSH 在付費正餘額時被明文允許,且是 Google 自己的 CLI 提供;「web service offerings」與「third party」仍模糊——本系統只給本人在區網用,若家人也用,可能落入「provide access to third party」。

**考慮過的替代方案**:cloudflared 公開網址(spike 用過):比 CLI 的 SSH 更像「remote proxies」與「web service offerings」,而且任何人拿到網址都能用。

## 待驗證

| 來源 | 待驗證 | 驗證方式 / 時機 | 擋計畫? |
|---|---|---|---|
| R1 | L4、A100 等其他類型在本帳號能否開到、每小時耗用 | 實跑案例(開啟後立即結束),implement 階段 | 否 |
| R1 | CLI 0.7.5 以後改版是否改變 `sessions`/`usage` 輸出格式 | 實跑案例每次升版重跑 | 否 |
| R2 | 後端直接跑 InstalledAppFlow 產生的 token.json,CLI 讀得到 | 實跑案例(需使用者登入一次) | 否 |
| R13 | 長時間使用是否被 Colab 判為違規而終止 | 實際使用觀察 | 否 |
| R3 | 通道連續超過 2 小時、或 runtime 被閒置回收時的行為 | 實跑案例(閒置自動結束、失聯偵測) | 否 |
| R1 | `colab new` 開啟時間的分布(本次 13.7 秒與 161 秒,區域不同) | 實跑案例記錄每次耗時,對照 SC-001 | 否 |

## 修訂紀錄

### 2026-11-10

- R8:轉送從「管理操作黑名單」改為「推論與查詢路徑白名單、白名單外回 404」,沒有工作階段時的回應改為「1 秒內回 503」。原因:system-analysis S6 發現黑名單會連帶提供 `/v1/*`(OpenAI 相容),與 spec 假設「不另外提供 OpenAI 相容 API」矛盾(plan.md Q18);SC-007 定下 1 秒門檻。連帶:techstack.md「自寫取代套件」同步改寫;R8 的代理延遲實測不受影響(只換判斷路徑的方式)。
- R1:遠端初始化加上 `OLLAMA_ORIGINS=*`。原因:S6 實測帶非本機 `Origin` 的瀏覽器程式會被遠端 Ollama 回 403(plan.md Q20)。連帶:無。
- R3:說明文字跟上 SC-002 的修訂(斷線 1 分鐘內顯示重連中)。原因:analyze 第 1 輪 A6。連帶:無。
- R9:說明文字跟上原型實際的頁數(6 頁加狀態總覽)。原因:analyze 第 1 輪 A7。連帶:techstack.md「一覽」前端列同步改為 6 頁加狀態總覽(analyze 第 2 輪 A7)。
