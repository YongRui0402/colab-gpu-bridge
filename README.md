# colab-gpu-bridge

把 Google Colab 的 GPU 執行環境當成區網裡的一台 Ollama 來用:網頁 UI 負責 Google 登入、開關工作階段與下載模型,
區網程式照平常連 Ollama 的方式連本系統的 Ollama 相容端點,請求經 SSH 通道轉到 Colab 上的 Ollama。

| 入口 | port |
|---|---|
| UI | 8780 |
| Ollama 相容端點 | 11434 |

## 本機執行

```bash
cp .env.example .env    # 可全部留空;主機已有 Ollama 佔 11434 時改 CGB_HOST_OLLAMA_PORT
docker compose up -d --build
```

瀏覽器開 `http://<主機>:8780/` 做 Google 登入。**登入要一次做完,期間不要重建或重啟容器**:授權流程的暫存只在記憶體,重啟就要重來。
資料(授權、SSH 金鑰、SQLite)在 named volume `cgb-data`,或 `.env` 的 `CGB_HOST_DATA`。

## 測試

```bash
uv sync
uv run pytest tests/integration -q    # 快速層;CI 另外排除單支超過 1 秒的,清單見 specs/003-download-dedup-model-cache/testplan.md 的測試指令表
uv run pytest -q                      # 全部(含 tests/e2e,要先 uv run playwright install chromium)
```

打真實 Colab 的實跑案例標 `realrun`,預設不跑,會花 compute units,要明確帶 `-m realrun`。
