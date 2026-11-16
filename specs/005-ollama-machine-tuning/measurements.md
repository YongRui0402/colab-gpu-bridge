# 量測紀錄:005-ollama-machine-tuning

## US1-CLI-18(T020)讀真的 `nvidia-smi` 多花的時間

- 日期:2026-11-15;環境:桌機 GTX 1660 Ti,`start_ollama.py` 子行程接臨時 `ollama serve`(`realrun_local`,不開 Colab)
- 真的 `nvidia-smi` 第一行:`NVIDIA GeForce GTX 1660 Ti, 6144`
- A(有真的 `nvidia-smi`)5 次:0.0482、0.0483、0.0483、0.0480、0.0482 秒,中位數 0.0482
- B(沒有 `nvidia-smi`)5 次:0.0290、0.0292、0.0294、0.0295、0.0291 秒,中位數 0.0292
- **A − B 中位數 0.019 秒,門檻 ≤ 5 秒(NFR-001、SC-003):過**
- A 每次回報 `vramTotalBytes` 6442450944(= 6144 × 1048576)、`gpuName` `NVIDIA GeForce GTX 1660 Ti`,與真的輸出一致:過
- 判定者:腳本;樣本:一次實跑,A、B 各 5 次;收尾後只剩使用者自己的 `ollama serve`,沒有碰它

## T002a 真的 `colab` 解讀新的命令列(使用者 2026-11-15 同意)

- 環境:桌機 `colab` 0.7.5,空的暫存 `HOME` 與 `XDG_CONFIG_HOME`、未授權、stdin 接 `/dev/null`,不花 compute units
- 結果:沒有參數錯誤;`colab exec` 停在 stdout「[colab] Session 'cgb-test-0001' not found.」(exec 先查工作階段再要求授權,和 001 `colab new` 停在授權不同,測試斷言照實跑結果修正)
- 對照組:同一條命令列多帶 `--bogus-flag`,命中 `No such option`、`Usage:`,檢查有效

## G-03(T172)與 G-02(T171)真的 Colab T4

- 日期:2026-11-15 23:24;總時間 1.3 分,用掉 0.0 compute units;P3 之後 cgb-test- 的行 []
- 自動值:開啟 68.8 秒;設定 None;來源 None;3 輪 None 秒,中位數 None
- 平行數 1:開啟 None 秒;設定 None;3 輪 None 秒,中位數 None
- `/api/ps`(size, size_vram):自動 None;平行 1 None
- **G-03 開啟 68.8 秒,門檻 ≤ 004 的 56.7 + 5.0 秒:沒過**
- **G-02 自動值 / 平行 1 = None,門檻 ≤ 0.85;size_vram = size False;flash attention False;KV q8_0 False:沒過**
- 其他:{'error': 'auto 沒有就緒:TUNNEL_TIMEOUT 開啟執行環境失敗,請稍後再試。'}

## G-03(T172)與 G-02(T171)真的 Colab T4

- 日期:2026-11-15 23:28;總時間 1.2 分,用掉 0.0 compute units;P3 之後 cgb-test- 的行 []
- 自動值:開啟 64.7 秒;設定 None;來源 None;3 輪 None 秒,中位數 None
- 平行數 1:開啟 None 秒;設定 None;3 輪 None 秒,中位數 None
- `/api/ps`(size, size_vram):自動 None;平行 1 None
- **G-03 開啟 64.7 秒,門檻 ≤ 004 的 56.7 + 5.0 秒:沒過**
- **G-02 自動值 / 平行 1 = None,門檻 ≤ 0.85;size_vram = size False;flash attention False;KV q8_0 False:沒過**
- 其他:{'error': '下載 qwen2.5:7b 回 403'}

## G-03(T172)與 G-02(T171)真的 Colab T4

- 日期:2026-11-15 23:42;總時間 12.6 分,用掉 1.26 compute units;P3 之後 cgb-test- 的行 []
- 自動值:開啟 48.5 秒;設定 {'numParallel': 2, 'contextLength': 4096, 'maxLoadedModels': 1, 'flashAttention': True, 'kvCacheType': 'q8_0'};來源 {'numParallel': 'auto', 'contextLength': 'auto', 'maxLoadedModels': 'auto', 'flashAttention': 'auto', 'kvCacheType': 'auto'};3 輪 [33.6, 40.0, 36.2] 秒,中位數 36.20115826599067
- 平行數 1:開啟 48.5 秒;設定 {'numParallel': 1, 'contextLength': 4096, 'maxLoadedModels': 1, 'flashAttention': True, 'kvCacheType': 'q8_0'};3 輪 [57.5, 61.0, 61.5] 秒,中位數 61.03380162600661
- `/api/ps`(size, size_vram):自動 [('qwen2.5:7b', 4922340801, 4922340801)];平行 1 [('qwen2.5:7b', 4647592917, 4647592917)]
- **G-03 開啟 48.5 秒,門檻 ≤ 004 的 56.7 + 5.0 秒:過**
- **G-02 自動值 / 平行 1 = 0.593,門檻 ≤ 0.85;size_vram = size True;flash attention True;KV q8_0 True:過**
- 其他:{}

## US3-CLI-19(T119)遠端重啟占用的時間

- 日期:2026-11-16;`tests/integration/test_ollama_scripts.py::test_量測_遠端重啟占用的時間_套用在_90_秒內_改回自動值兩步合計在_180_秒內`(`realrun_local`)
- 條件:臨時 `ollama serve`(`free_loopback_port()`、暫存 `HOME` 與 `OLLAMA_MODELS`,不 pull 模型)、假 `nvidia-smi` 量到 15360 MiB、pid 檔指著舊的 serve;`CGB_STOP_SECONDS`、`CGB_VERIFY_SECONDS` 不設(預設 10、60);只含遠端腳本,不含 `colab exec` 來回(由 G-04 量);不執行 `colab`、不花 compute units;不對 127.0.0.1:11434 送請求,停止靠 pid 檔
- 情況 A(`CGB_TUNE_NUM_PARALLEL=4` 連續重啟 5 次):4.1、4.1、4.0、4.1、4.1 秒;`ok` 都是 true
- 情況 B(新設定起不來、等滿 60 秒,再改回自動值):第一步 60.1 秒(`stage` 為 `verify`)、第二步 4.1 秒,合計 64.2 秒
- **則1 A 的 5 次都 ≤ 90 秒:過(最大 4.1 秒);則2 B 合計 ≤ 180 秒:過(64.2 秒);則3 A 的 5 次 `ok` 都是 true:過**
- 判定者:腳本;樣本:一次實跑,A 5 次、B 1 次(未用於調整);收尾 `box` 確認行程與行程群組都已結束

## G-04(T173)真的 Colab T4 套用並重啟

- 日期:2026-11-16 11:02;同一台 T4(context 覆蓋 32768);開啟 {'seconds': 48.4, 'state': 'ready', 'reason': None};下載 加入 201;completed(None),51 秒;整批 4.3 分,用掉 0.03 compute units;P3 之後 cgb-test- 的行 []
- 套用平行數 4:受理 202;重啟完成 9.1 秒、回到就緒 13.2 秒;狀態 ready(None);設定 {'numParallel': 4, 'contextLength': 32768, 'maxLoadedModels': 1, 'flashAttention': True, 'kvCacheType': 'q8_0'}
- `/api/ps` 之前 [('qwen2.5:7b', 7086622636, 7086622636, 32768)];之後 [('qwen2.5:7b', 8704533461, 8704533461, 32768)];遠端 log 的 n_seq_max [2, 4]
- **則1 重啟 90 秒內完成(不含重新載入模型):過;則2 `/api/ps` 列出 qwen2.5:7b:過;則3 n_seq_max = 4:過**
- 其他:{}
