# Spike 結果:Colab Pro 跑 Ollama + 通道(2026-11-09)

> 對應作品提案「開工前要先驗證」第 1 項。結論:**通過**,題目成立。

## 做法

- Colab Pro,T4 runtime,notebook `spike/colab_ollama_spike.ipynb`(使用者手動開、手動執行)
- Ollama 在 notebook 內背景執行(`OLLAMA_HOST=0.0.0.0:11434`),模型 `qwen2.5:0.5b`
- 通道:cloudflared quick tunnel(`trycloudflare.com`,不需帳號,Colab 主動往外連)
- 桌機以 `spike/verify.sh` 驗證;網址只在 `.env`(0600),輸出只印長度與 sha256 前 8 碼

## 證據(桌機實測)

| 項目 | 結果 |
|---|---|
| `/api/version` | `0.40.15`(本機 Ollama 為 `0.32.15` → 確認打到的是遠端) |
| `/api/tags` | `['qwen2.5:0.5b']`(本機沒有這個模型) |
| 桌機發起 `/api/generate` | 成功;eval 163.7 / 193.1 tokens/s |
| `/api/ps` | `size_vram=483645193`(模型在 GPU 上) |
| 通道往返延遲(`/api/version` ×5) | 平均 0.266 s(0.262–0.272) |

## Compute units(開工前驗證第 3 項,部分)

- Colab「資源」面板:可用量 381.74,使用率約 **1.15 單位/小時**(T4)
- 結束餘額:使用者未提供(runtime 已於 2026-11-09 關閉;桌機實測通道 DNS 已解析不到)

## 尚未處理的風險(交給 technical-research)

- quick tunnel 網址公開、無驗證:任何拿到網址的人都能用這台 Ollama → 正式版要加驗證或換通道
- 條款「connecting to remote proxies」是否涵蓋反向通道:仍模糊
- quick tunnel 網址每次 runtime 都會變;spec 改由後端以 Colab CLI 開啟與連線(見 specs/001-session-model-catalog/spec.md),不再需要 notebook 報到
