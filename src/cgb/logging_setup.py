"""正式啟動時的 logging 設定(plan.md Q199;spec.md § NFR-010)。

`python -m cgb` 在起 uvicorn 之前呼叫 `setup()`:`cgb.*` 的 INFO(含 Ollama 相容端點的請求紀錄)才會輸出,
每一行帶時間與 logger 名稱。uvicorn 自己的 logger 由 uvicorn 設定,不經過這裡。
"""

import logging

FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
# httpx、httpcore 的 INFO 會印出轉送的轉發位址與路徑(Q200)
QUIET_LOGGERS = ("httpx", "httpcore")


def setup() -> None:
    logging.basicConfig(level=logging.INFO, format=FORMAT)
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
