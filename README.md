# colab-gpu-bridge

把 Google Colab 的 GPU 執行環境當成區網裡的一台 Ollama 來用:網頁 UI 負責 Google 登入、開關工作階段與下載模型,
區網程式照平常連 Ollama 的方式連本系統的 Ollama 相容端點,請求經 SSH 通道轉到 Colab 上的 Ollama。

| 入口 | 本機(`compose.yaml`) | Tower(`deploy/compose.yml`) |
|---|---|---|
| UI | 8780 | 8912 |
| Ollama 相容端點 | 11434 | 8911 |

## 本機執行

```bash
cp .env.example .env    # 可全部留空;主機已有 Ollama 佔 11434 時改 CGB_HOST_OLLAMA_PORT
docker compose up -d --build
```

瀏覽器開 `http://<主機>:8780/`。資料(授權、SSH 金鑰、SQLite)在 named volume `cgb-data`,或 `.env` 的 `CGB_HOST_DATA`。

## 部署到 Tower

映像由 CI 在 main 建好推到 `<內網 registry>/apps/colab-gpu-bridge`。**第一次**照下面做,之後每次合併進 main,CI 會自動更新:

1. 圖示 `deploy/icon.png` 已合併進 `apps/icons`(網址寫在 `deploy/tower.override.yml`)。
2. 在 Tower 建 Compose Manager 專案 `colab-gpu-bridge`:`deploy/compose.yml` 當 `docker-compose.yml`,
   `deploy/tower.override.yml` 當 `docker-compose.override.yml`;建好資料夾 `/mnt/nvme_data/appdata/colab-gpu-bridge/data`(擁有者 `0:0`)。
3. 照 `deploy/tower.env.example` 填專案的 `.env`(只有 `CGB_WEBUI_URL` 必填,沒有機密)。
4. Unraid GUI 按 **Compose Up**,開 **Autostart**。
5. 開 UI 做 Google 登入。**登入要一次做完,期間不要重建或重啟容器**:授權流程的暫存只在記憶體,重啟就要重來。

## 測試

```bash
uv sync
uv run pytest tests/integration -q    # 快速層;CI 另外排除單支超過 1 秒的,清單見 .gitlab-ci.yml
uv run pytest -q                      # 全部(含 tests/e2e,要先 uv run playwright install chromium)
```

打真實 Colab 的實跑案例標 `realrun`,預設不跑,會花 compute units,要明確帶 `-m realrun`。
