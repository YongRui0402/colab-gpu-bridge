# 實跑量測結果:官方模型庫的錯誤處理

由 `tests/realrun/conftest.py` 的 `write_measurement` 寫入(tasks.md T087、T088);護欄見 `testplan.md` § 4.2 各案例的「副作用與護欄」。

| 時間 | 案例 | 任務 | 數字 | 門檻 | 結果 | 備註 |
|---|---|---|---|---|---|---|
| 2026-11-13T20:37:18+08:00 | G-01 | T087 | 搜尋 10.05 秒 504 LIBRARY_TIMEOUT;版本清單 10.04 秒 504 LIBRARY_TIMEOUT;試算 10.04 秒 504 LIBRARY_TIMEOUT;慢慢送資料時的搜尋 10.01 秒 504 LIBRARY_TIMEOUT | 則1~則4:送出後 10~11 秒之間收到 504、code 為 LIBRARY_TIMEOUT | 過 | 只連 127.0.0.1;預設 10 秒逾時,沒帶 request_timeout |
| 2026-11-13T20:38:03+08:00 | G-02 | T088 | 第 1 頁官方模型 0 筆(含 qwen2.5:否),丟出 LIBRARY_TIMEOUT;0 筆搜尋 0 筆,丟出 無;第 2 頁 0 筆,丟出 無;版本 133 個(非 cloud 133 個),sizeLabel 為 null 0 個,丟出 無;qwen2.5:7b sizeBytes 4,683,086,845,丟出 無;請求 4 個 | 則1:第 1 頁至少 1 筆且含 qwen2.5;則2:0 筆搜尋回 0 筆、不丟 AdapterError;則3:第 2 頁不丟 LIBRARY_BAD_RESPONSE;則4:非 cloud 版本 sizeLabel 為 null 0 個;則5:qwen2.5:7b sizeBytes 4,600,000,000~4,800,000,000 | 沒過 | 沒過:則1 |
