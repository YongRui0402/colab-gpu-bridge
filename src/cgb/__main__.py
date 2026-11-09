"""`python -m cgb`:組出真的轉接層,在同一個行程起 UI 與 Ollama 相容端點(plan.md Q87、Q93、Q113)。

環境變數(deploy/compose.yaml 的 environment,預設值與 Dockerfile 相同):
`CGB_LISTEN_HOST`、`CGB_UI_PORT`、`CGB_OLLAMA_PORT`、`CGB_TUNNEL_LOCAL_PORT`、`CGB_DB_PATH`、
`CGB_COLAB_CONFIG_DIR`、`CGB_SSH_IDENTITY_PATH`。
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from cgb.adapters.colab_cli import ColabControl
from cgb.adapters.google_oauth import GoogleOAuth
from cgb.adapters.tunnel import Tunnel
from cgb.app import create_app
from cgb.server import serve


@dataclass(frozen=True)
class Settings:
    listen_host: str
    ui_port: int
    ollama_port: int
    tunnel_local_port: int
    db_path: str
    colab_config_dir: str
    ssh_identity_path: str


def read_settings(env: Mapping[str, str] = os.environ) -> Settings:
    return Settings(
        listen_host=env.get("CGB_LISTEN_HOST", "0.0.0.0"),
        ui_port=int(env.get("CGB_UI_PORT", "8780")),
        ollama_port=int(env.get("CGB_OLLAMA_PORT", "11434")),
        tunnel_local_port=int(env.get("CGB_TUNNEL_LOCAL_PORT", "11435")),
        db_path=env.get("CGB_DB_PATH", "/data/cgb.sqlite3"),
        colab_config_dir=env.get("CGB_COLAB_CONFIG_DIR", "/data/colab-cli"),
        ssh_identity_path=env.get("CGB_SSH_IDENTITY_PATH", "/data/ssh/id_ed25519"),
    )


def main() -> None:
    settings = read_settings()
    # 授權檔的位置與 SSH 私鑰由轉接層與 UI API 從環境變數讀取(Q87);沒設時補上預設值,讓兩邊讀到同一個路徑
    os.environ.setdefault("CGB_COLAB_CONFIG_DIR", settings.colab_config_dir)
    os.environ.setdefault("CGB_SSH_IDENTITY_PATH", settings.ssh_identity_path)
    pair = create_app(
        db_path=settings.db_path,
        tunnel_local_port=settings.tunnel_local_port,
        colab=ColabControl(),
        tunnel=Tunnel(),
        # 遠端 Ollama 與官方模型庫的轉接層屬故事 2、3(remote_ollama.py、model_library.py),還沒有實作
        remote_ollama=None,
        model_library=None,
        google_oauth=GoogleOAuth(),
    )
    serve(pair, host=settings.listen_host, ui_port=settings.ui_port, ollama_port=settings.ollama_port)


if __name__ == "__main__":
    main()
