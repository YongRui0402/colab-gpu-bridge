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
