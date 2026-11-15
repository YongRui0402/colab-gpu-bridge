"""組裝後端的注入點(plan.md Q95、Q96、Q109、Q112)。

`create_app` 只建立 UI 與 Ollama 相容端點兩個還沒有任何路由的 FastAPI app 與兩者共用的 `AppState`;
路由、服務與資料表都由各案例的綠燈任務加上。
時鐘、時限與名稱前綴可由測試注入縮短的值,預設值就是正式值,不開放給使用者設定。
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from cgb.adapters.huggingface import HuggingFaceHub

# Q109:S5 `Session.name` 的 pattern 是 `^cgb-`,注入的前綴必須以它開頭(實跑用 `cgb-test-`)
REQUIRED_NAME_PREFIX = "cgb-"

# E1 前端 UI 的靜態檔(原生 HTML/CSS/JS),和 `/api` 同一個來源
STATIC_DIR = Path(__file__).resolve().parent / "static"

# 本機轉發的 port 預設值(contracts/tunnel.openapi.yaml § OpenTunnelInput.localPort;CGB_TUNNEL_LOCAL_PORT)
DEFAULT_TUNNEL_LOCAL_PORT = 11435

# 相容端點在容器內的 port 預設值(CGB_OLLAMA_PORT;plan.md Q21)
DEFAULT_OLLAMA_PORT = 11434


class Clock(Protocol):
    """後端取得時間與等待的唯一來源;測試注入可推進的假時鐘。"""

    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    """正式的時鐘:真實的 UTC 時間與真的等待。"""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


@dataclass(frozen=True)
class Timeouts:
    """各時限與節奏(秒)。預設值是正式值。

    - open_total:開啟流程的總時限 5 分鐘(Q58、SC-001)
    - health_interval:健康檢查間隔 15 秒(research.md R3)
    - health_timeout:健康檢查打 `/api/version` 的逾時 5 秒(S9 checkHealth)
    - reconnect_limit:重連時限固定 5 分鐘(Q67)
    - reconnect_backoff:重連前幾輪的等待:立即、5、10、20 秒(Q67)
    - reconnect_interval:之後每輪的間隔 30 秒(Q67)
    - tunnel_ready:通道建立後等 `/api/version` 就緒的期限 30 秒(Q68)
    - chat_connect:對話轉送到遠端 Ollama 的連線時限 10 秒(004 Q44)
    - chat_read:對話轉送收到回應標頭之前與兩段之間的逾時 300 秒(004 Q44)
    - hf_expand_deadline:展開 Hugging Face 模型時,Hugging Face 這一段與讀模型清單各自從收到請求起算的期限 10 秒(004 Q44、Q67)
    """

    open_total: float = 300.0
    health_interval: float = 15.0
    health_timeout: float = 5.0
    reconnect_limit: float = 300.0
    reconnect_backoff: tuple[float, ...] = (0.0, 5.0, 10.0, 20.0)
    reconnect_interval: float = 30.0
    tunnel_ready: float = 30.0
    chat_connect: float = 10.0
    chat_read: float = 300.0
    hf_expand_deadline: float = 10.0


@dataclass
class AppState:
    """兩個 app 共用的狀態:工作階段、閒置計時與下載佇列都要放在同一份記憶體裡(compose.yaml 的 x-ports)。"""

    db_path: Path
    clock: Clock
    name_prefix: str
    timeouts: Timeouts
    colab: Any
    tunnel: Any
    remote_ollama: Any
    model_library: Any
    google_oauth: Any
    # Hugging Face Hub 轉接層(plan.md Q65):`create_app` 沒給時用正式的 `HuggingFaceHub()`
    huggingface: Any = None
    tunnel_local_port: int = DEFAULT_TUNNEL_LOCAL_PORT
    # 相容端點在容器內的 port,與它在主機上對外的 port(連線設定頁用,plan.md Q21)
    ollama_port: int = DEFAULT_OLLAMA_PORT
    public_ollama_port: int | None = None


@dataclass(frozen=True)
class AppPair:
    """UI(前端、`/api`)與 Ollama 相容端點兩個 app,以及它們共用的狀態。"""

    ui: FastAPI
    ollama: FastAPI
    state: AppState


def _empty_app(title: str, state: AppState) -> FastAPI:
    # 不開 FastAPI 內建的 /docs、/redoc、/openapi.json:Ollama 相容端點白名單外的路徑都必須是 404
    app = FastAPI(title=title, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cgb = state
    return app


def create_app(
    *,
    db_path: str | Path,
    clock: Clock | None = None,
    name_prefix: str = REQUIRED_NAME_PREFIX,
    timeouts: Timeouts | None = None,
    colab: Any,
    tunnel: Any,
    remote_ollama: Any,
    model_library: Any,
    google_oauth: Any,
    huggingface: Any = None,
    tunnel_local_port: int = DEFAULT_TUNNEL_LOCAL_PORT,
    ollama_port: int = DEFAULT_OLLAMA_PORT,
    public_ollama_port: int | None = None,
) -> AppPair:
    """建立兩個空的 app 與共用狀態;五個轉接層(Q96)由呼叫端注入。"""
    if not name_prefix.startswith(REQUIRED_NAME_PREFIX):
        raise ValueError(f"name_prefix 必須以 {REQUIRED_NAME_PREFIX!r} 開頭(Q109),收到 {name_prefix!r}")

    state = AppState(
        db_path=Path(db_path),
        clock=clock if clock is not None else SystemClock(),
        name_prefix=name_prefix,
        timeouts=timeouts if timeouts is not None else Timeouts(),
        colab=colab,
        tunnel=tunnel,
        remote_ollama=remote_ollama,
        model_library=model_library,
        google_oauth=google_oauth,
        huggingface=huggingface if huggingface is not None else HuggingFaceHub(),
        tunnel_local_port=tunnel_local_port,
        ollama_port=ollama_port,
        public_ollama_port=public_ollama_port if public_ollama_port is not None else ollama_port,
    )
    ui = _empty_app("colab-gpu-bridge UI", state)
    # 延後匯入:cgb.api 往下依賴 services 與 db,app.py 只負責組裝
    from cgb.api import install as install_ui_api

    install_ui_api(ui)
    # 掛在 `/api` 的路由之後:沒有對應路由的路徑才交給靜態檔
    ui.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    ollama = _empty_app("colab-gpu-bridge Ollama 相容端點", state)
    from cgb.ollama_compat import install as install_ollama_compat

    install_ollama_compat(ollama, ui)
    return AppPair(ui=ui, ollama=ollama, state=state)
