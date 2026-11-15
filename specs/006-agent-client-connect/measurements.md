# 量測紀錄:006-agent-client-connect

由各案例的測試附加(tasks.md T048~T050);護欄見 `testplan.md` § 5.2 各案例的「副作用與護欄」。

## G-01(T048)opencode 照片段接上本系統(本機臨時 `ollama serve`)

- 日期:2026-11-16 04:29;環境:以硬連結複製已下載 `qwen2.5:3b` 的 `OLLAMA_MODELS`(原本那份不動);臨時 `ollama serve` 0.32.15(127.0.0.1 隨機 port,`OLLAMA_CONTEXT_LENGTH=16384`,暫存 `HOME` 與 `OLLAMA_MODELS`);opencode 1.18.31(`env -i` 只留 `PATH`,`HOME` 與四個 `XDG_*` 指到暫存資料夾);本系統:測試行程內的 uvicorn,相容端點 127.0.0.1:60987,Colab 與通道用替身,不開 Colab、不花錢
- `/api/connect`:contextLength 16384、models ['qwen2.5:3b', 'qwen3:4b']、shouldWarn False
- opencode 結束碼 0;總耗時 84.7 秒(上限 300 秒)
- 回答文字(opencode 的 `text` 事件)含 `紫色長頸鹿 42`:是;前 80 字 `'檔案 `secret.txt` 內容如下：\n1: 紫色長頸鹿 42\n\n(檔案內容為1行，總共1行)'`
- 工具呼叫 1 次:['read'];每一步的 input tokens [6423, 6536]
- 臨時 serve 收到的 `POST /v1/chat/completions` 3 個,帶 `tools` 的 2 個(工具數 [10, 10],`stream` [True, True, True])
- 臨時 serve 的 `/api/ps`:qwen2.5:3b size 2721946009 size_vram 2721946009 context 16384
- **則1 結束碼 0、輸出含 `紫色長頸鹿 42`,門檻同左:過**
- **則2 有帶 `tools` 的 `/v1/chat/completions` 與 `read` 工具呼叫,門檻同左:過**
- **則3 總耗時 84.7 秒(只記錄,沒有門檻)**
- 判定者:腳本;樣本:固定的 `secret.txt`(內容 `紫色長頸鹿 42`,沒有用來調整規則),一次實跑
- 收尾:opencode(結束碼 0)行程群組已空;臨時 serve(pid 2170590,行程群組 2170590)SIGTERM,0.16 秒;行程已結束 是(poll() = 0),行程群組已空 是(`killpg(pgid, 0)` 丟 ProcessLookupError),127.0.0.1:52439 已不在聽 是;使用者自己的 `ollama serve`(pid 3585)沒有碰,收尾後仍在

## G-02(T049)pi 照片段接上本系統(本機臨時 `ollama serve`)

- 日期:2026-11-16 04:31;環境:以硬連結複製已下載 `qwen2.5:3b` 的 `OLLAMA_MODELS`(原本那份不動);臨時 `ollama serve` 0.32.15(127.0.0.1 隨機 port,`OLLAMA_CONTEXT_LENGTH=16384`,暫存 `HOME` 與 `OLLAMA_MODELS`);pi(@mariozechner/pi-coding-agent)0.73.1,`npm install --prefix <暫存資料夾> @mariozechner/pi-coding-agent` 12 秒;pi 以 `env -i` 只留 `PATH`,`HOME` 與四個 `XDG_*` 指到暫存資料夾,另加 `PI_OFFLINE=1`;本系統:測試行程內的 uvicorn,相容端點 127.0.0.1:57295,Colab 與通道用替身,不開 Colab、不花錢
- `/api/connect`:contextLength 16384、reserveTokens 4096、settings.json `{"compaction": {"reserveTokens": 4096}}`
- pi 結束碼 0;總耗時 62.7 秒(上限 300 秒)
- 回答文字(assistant 的 `message_end`)含 `紫色長頸鹿 42`:是;前 80 字 `'read complete, here is the content from `secret.txt`:\n\n紫色長頸鹿 42'`
- 工具呼叫 1 次:['read'];每則 assistant 訊息的 input tokens [1306, 1351]
- 壓縮:JSON 事件 [];臨時 serve 收到的 `POST /v1/chat/completions` 2 個,其中壓縮的請求 0 個
- 臨時 serve 的 `/api/ps`:qwen2.5:3b size 2721946009 size_vram 2721946009 context 16384
- **則1 結束碼 0、輸出含 `紫色長頸鹿 42`,門檻同左:過**
- **則2 JSON 事件裡有 `read` 工具呼叫,門檻同左:過**
- **則3 這一回合沒有因為 `threshold` 觸發自動壓縮(沒有壓縮事件、臨時 serve 沒收到壓縮的請求),門檻同左:過**
- **則4 總耗時 62.7 秒(只記錄,沒有門檻)**
- 對照組(檢查器有效):同一套判定(`compaction_start` 事件、請求裡的 `You are a context summarization assistant`)套到 2026-11-16 技術研究探針的 pi 0.73.1 紀錄(context 10240、沒有 `settings.json`),抓到 `compaction_start/threshold` 1 筆、壓縮的請求 1 個(16 個請求中);所以本次的 0 不是檢查器失效
- 判定者:腳本;樣本:固定的 `secret.txt`(內容 `紫色長頸鹿 42`,沒有用來調整規則),一次實跑
- 收尾:npm install(結束碼 0)行程群組已空;pi(結束碼 0)行程群組已空;臨時 serve(pid 2171621,行程群組 2171621)SIGTERM,0.16 秒;行程已結束 是(poll() = 0),行程群組已空 是(`killpg(pgid, 0)` 丟 ProcessLookupError),127.0.0.1:55373 已不在聽 是;使用者自己的 `ollama serve`(pid 3585)沒有碰,收尾後仍在

## G-03(T050)`stream:true` 每一段的延遲(測試行程內的假 Ollama)

- 日期:2026-11-16 04:32;環境:桌機,`tests/integration/test_006_g_03.py`(快速層、不標 `realrun`),測試行程內的 uvicorn(127.0.0.1 隨機 port)經 httpx 轉送到測試行程內的假 Ollama,不開 Colab、不花錢
- 樣本:假 Ollama 的 `SseReply` 每 0.1 秒送一段、共 20 段,同一個請求送 5 次
- 每次的最大延遲(秒):0.0139、0.0557、0.0567、0.0467、0.0463
- 每次的延遲中位數(秒):0.0097、0.0183、0.0178、0.0089、0.0097
- **5 次 × 20 段的最大延遲 0.0567 秒,門檻每一段 ≤ 0.5 秒:過**
- 判定者:腳本;樣本:固定 20 段(延遲以「請求送出 + i × 間隔」當送出時間,是上限)
- 收尾:假伺服器與 uvicorn 由 fixture 停下;沒有起任何外部行程

## G-01(T048)opencode 照片段接上本系統(本機臨時 `ollama serve`)

- 日期:2026-11-16 05:39;環境:以硬連結複製已下載 `qwen2.5:3b` 的 `OLLAMA_MODELS`(原本那份不動);臨時 `ollama serve` 0.32.15(127.0.0.1 隨機 port,`OLLAMA_CONTEXT_LENGTH=16384`,暫存 `HOME` 與 `OLLAMA_MODELS`);opencode 1.18.31(`env -i` 只留 `PATH`,`HOME` 與四個 `XDG_*` 指到暫存資料夾);本系統:測試行程內的 uvicorn,相容端點 127.0.0.1:59687,Colab 與通道用替身,不開 Colab、不花錢
- `/api/connect`:contextLength 16384、models ['qwen2.5:3b', 'qwen3:4b']、shouldWarn False
- opencode 結束碼 0;總耗時 83.1 秒(上限 300 秒)
- 回答文字(opencode 的 `text` 事件)含 `紫色長頸鹿 42`:是;前 80 字 `'檔案 secret.txt 的內容如下：\n\n1: 紫色長頸鹿 42\n\n(End of file - total 1 lines)'`
- 工具呼叫 1 次:['read'];每一步的 input tokens [6423, 6536]
- 臨時 serve 收到的 `POST /v1/chat/completions` 3 個,帶 `tools` 的 2 個(工具數 [10, 10],`stream` [True, True, True])
- 臨時 serve 的 `/api/ps`:qwen2.5:3b size 2721946009 size_vram 2721946009 context 16384
- **則1 結束碼 0、輸出含 `紫色長頸鹿 42`,門檻同左:過**
- **則2 有帶 `tools` 的 `/v1/chat/completions` 與 `read` 工具呼叫,門檻同左:過**
- **則3 總耗時 83.1 秒(只記錄,沒有門檻)**
- 判定者:腳本;樣本:固定的 `secret.txt`(內容 `紫色長頸鹿 42`,沒有用來調整規則),一次實跑
- 收尾:opencode(結束碼 0)行程群組已空;臨時 serve(pid 2231272,行程群組 2231272)SIGTERM,0.21 秒;行程已結束 是(poll() = 0),行程群組已空 是(`killpg(pgid, 0)` 丟 ProcessLookupError),127.0.0.1:38545 已不在聽 是;使用者自己的 `ollama serve`(pid 3585)沒有碰,收尾後仍在

## G-02(T049)pi 照片段接上本系統(本機臨時 `ollama serve`)

- 日期:2026-11-16 05:41;環境:以硬連結複製已下載 `qwen2.5:3b` 的 `OLLAMA_MODELS`(原本那份不動);臨時 `ollama serve` 0.32.15(127.0.0.1 隨機 port,`OLLAMA_CONTEXT_LENGTH=16384`,暫存 `HOME` 與 `OLLAMA_MODELS`);pi(@mariozechner/pi-coding-agent)0.73.1,`npm install --prefix <暫存資料夾> @mariozechner/pi-coding-agent` 13 秒;pi 以 `env -i` 只留 `PATH`,`HOME` 與四個 `XDG_*` 指到暫存資料夾,另加 `PI_OFFLINE=1`;本系統:測試行程內的 uvicorn,相容端點 127.0.0.1:43669,Colab 與通道用替身,不開 Colab、不花錢
- `/api/connect`:contextLength 16384、reserveTokens 4096、settings.json `{"compaction": {"reserveTokens": 4096}}`
- pi 結束碼 0;總耗時 62.0 秒(上限 300 秒)
- 回答文字(assistant 的 `message_end`)含 `紫色長頸鹿 42`:是;前 80 字 `'讀取到的檔案 `secret.txt` 的內容是：\n```\n紫色長頸鹿 42\n```\n请稍候，我正在查找更多信息。'`
- 工具呼叫 1 次:['read'];每則 assistant 訊息的 input tokens [1306, 1351]
- 壓縮:JSON 事件 [];臨時 serve 收到的 `POST /v1/chat/completions` 2 個,其中壓縮的請求 0 個
- 臨時 serve 的 `/api/ps`:qwen2.5:3b size 2721946009 size_vram 2721946009 context 16384
- **則1 結束碼 0、輸出含 `紫色長頸鹿 42`,門檻同左:過**
- **則2 JSON 事件裡有 `read` 工具呼叫,門檻同左:過**
- **則3 這一回合沒有因為 `threshold` 觸發自動壓縮(沒有壓縮事件、臨時 serve 沒收到壓縮的請求),門檻同左:過**
- **則4 總耗時 62.0 秒(只記錄,沒有門檻)**
- 判定者:腳本;樣本:固定的 `secret.txt`(內容 `紫色長頸鹿 42`,沒有用來調整規則),一次實跑
- 收尾:npm install(結束碼 0)行程群組已空;pi(結束碼 0)行程群組已空;臨時 serve(pid 2231650,行程群組 2231650)SIGTERM,0.21 秒;行程已結束 是(poll() = 0),行程群組已空 是(`killpg(pgid, 0)` 丟 ProcessLookupError),127.0.0.1:46747 已不在聽 是;使用者自己的 `ollama serve`(pid 3585)沒有碰,收尾後仍在
