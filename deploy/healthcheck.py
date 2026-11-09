#!/usr/bin/env python3
"""E11 部署與網路:容器的 HTTP 健康檢查(compose 的 healthcheck 在 cgb-prepare-data --check 之後執行)。

- UI 的 port:GET /api/session(S5 getSession)回 200 才算活著;只看狀態碼,不讀、不印回應本文。
- Ollama 相容端點的 port:只確認 TCP 連得上,不送任何 HTTP 請求。
  S6 規定這個 port 收到的任何請求(含白名單外的路徑)都重設閒置計時(FR-026);
  健康檢查若送 HTTP,工作階段永遠不會因閒置而自動結束,compute units 會一直被耗用。

port 讀容器內的 CGB_UI_PORT、CGB_OLLAMA_PORT(compose.yaml 的 environment),與後端 listen 的是同一個值。
"""

import os
import socket
import sys
import urllib.error
import urllib.request

TIMEOUT = 3


def main() -> int:
    ui_port = int(os.environ.get("CGB_UI_PORT", "8780"))
    ollama_port = int(os.environ.get("CGB_OLLAMA_PORT", "11434"))

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{ui_port}/api/session", timeout=TIMEOUT) as response:
            if response.status != 200:
                print(f"UI 的 port {ui_port}:GET /api/session 回 {response.status}", file=sys.stderr)
                return 1
    except urllib.error.HTTPError as error:
        print(f"UI 的 port {ui_port}:GET /api/session 回 {error.code}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"UI 的 port {ui_port}:連不上({type(error).__name__})", file=sys.stderr)
        return 1

    try:
        with socket.create_connection(("127.0.0.1", ollama_port), timeout=TIMEOUT):
            pass
    except OSError as error:
        print(f"Ollama 相容端點的 port {ollama_port}:連不上({type(error).__name__})", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
