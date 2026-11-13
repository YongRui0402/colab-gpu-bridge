# 實跑量測結果:加入下載的重複判定與模型目錄快取

由 `tests/realrun/conftest.py` 的 `write_measurement` 寫入(tasks.md T068、T069);護欄見 `testplan.md` § 4.2 各案例的「副作用與護欄」。

| 時間 | 案例 | 任務 | 數字 | 門檻 | 結果 | 備註 |
|---|---|---|---|---|---|---|
| 2026-11-14T01:07:59+08:00 | G-01 | T068 | 臨時 ollama serve 版本 0.32.15(127.0.0.1 port 38053);/api/tags 200、最上層物件 是、models 陣列 是、原始 0 筆、回傳 0 筆,丟出 無;/api/ps 200、最上層物件 是、models 陣列 是、原始 0 筆、回傳 0 筆,丟出 無;沒有在聽的 port 41907 丟出 OLLAMA_UNREACHABLE;往返 2 個,方法 ['GET'];收尾:SIGTERM,0.00 秒;行程已結束 是(poll() = 0),行程群組已空 是 | 則1:/api/tags 原始筆數 = list_local_models 回傳筆數;則2:/api/tags、/api/ps 都是 200,最上層是物件、models 是陣列;則3:/api/ps 原始筆數 = list_loaded_models 回傳筆數;則4:沒有在聽的 port 丟 OLLAMA_UNREACHABLE;則5:收尾後行程已結束(poll() 不是 None)、行程群組沒有剩下的行程(killpg(pgid, 0) 丟 ProcessLookupError) | 過 | 只綁 127.0.0.1,只送 GET,不碰 11434;代價:OLLAMA_MODELS 是空的,/api/tags 是空清單,真實模型名稱是否帶版本與每一筆的欄位名稱驗不到;這是桌機 0.32.15,不是 Colab 上的 0.40.x |
| 2026-11-14T01:08:50+08:00 | G-02 | T069 | 10 次之後 call_count 1;第 1 次 3.051 秒;第 2~10 次 0.048, 0.048, 0.047, 0.046, 0.049, 0.049, 0.048, 0.047, 0.048 秒(最大 0.049);10 次的狀態碼 [200]、vramBytes ['16,106,127,360'];變更類型 202,新工作階段 ready(名稱不同);變更類型後那 1 次 200、3.048 秒,之後 call_count 2 | 則1:10 次之後 probe_resources call_count 1;則2:第 2~10 次每次 < 1 秒;則3:10 次的 vramBytes 都是 16,106,127,360;則4:第 1 次 ≥ 3 秒;則5:變更類型後那 1 次之後 call_count 2 | 過 | uvicorn 只綁 127.0.0.1 隨機 port,Colab 與遠端 Ollama 都用替身 |
