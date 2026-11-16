# 量測紀錄:007-catalog-error-chat-keep

由各案例的測試附加(tasks.md T072);護欄見 `testplan.md` § 4.2 各案例的「副作用與護欄」。

## G-01(T072)替身與真的轉接層一致:讀不到目錄時回 502/504、不回 500

- 日期:2026-11-16 19:23;環境:桌機 Ubuntu,本系統測試行程內 uvicorn,替身開工作階段、遠端 Ollama 用真的 `RemoteOllama`(`RecordingTransport(get_only=True)`)
- (1)沒有人在聽的 port `GET /api/models`:502 `OLLAMA_UNREACHABLE`(門檻 502 `OLLAMA_UNREACHABLE`,過)
- (1)沒有人在聽的 port `POST /api/models/preload`:502 `OLLAMA_UNREACHABLE`(門檻 502 `OLLAMA_UNREACHABLE`,過)
- (2)回 200 與 HTML 的 http 伺服器 `GET /api/models`:502 `OLLAMA_BAD_RESPONSE`(門檻 502 `OLLAMA_BAD_RESPONSE`,過)
- (2)回 200 與 HTML 的 http 伺服器 `POST /api/models/preload`:502 `OLLAMA_BAD_RESPONSE`(門檻 502 `OLLAMA_BAD_RESPONSE`,過)
- (3)只 accept、不回位元組的 socket `GET /api/models`:504 `OLLAMA_TIMEOUT`,耗時 10.01 秒(門檻 504 `OLLAMA_TIMEOUT`,過)
- (3)只 accept、不回位元組的 socket `POST /api/models/preload`:504 `OLLAMA_TIMEOUT`,耗時 10.02 秒(門檻 504 `OLLAMA_TIMEOUT`,過)
- (3)`GET /api/models` 送出後 10.01 秒回應(門檻 10~12 秒,過)
- 六次回應裡 500 的次數:0(門檻 0,SC-001,過)
- 轉接層實際送出的請求:`GET /api/tags`、`GET /api/version`;收到回應的往返 3 次(連不上與逾時的沒有回應,不留紀錄)
- **判定:全部過門檻**
- 判定者:腳本;樣本:一次實跑(未用於調整)
- 收尾:P(127.0.0.1 上的臨時 port)收尾後已釋放
