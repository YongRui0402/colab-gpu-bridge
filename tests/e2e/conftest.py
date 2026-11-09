"""跨端點驗收(Playwright)的 fixture(tasks.md T007;plan.md Q99)。

後端是測試行程內的 uvicorn:UI 127.0.0.1:8781、Ollama 相容端點 127.0.0.1:11437,轉接層用替身,由測試直接操控。
"""

from collections.abc import Callable
from typing import Any

import pytest

from cgb.app import AppPair

E2E_UI_PORT = 8781
E2E_OLLAMA_PORT = 11437


@pytest.fixture(scope="session")
def base_url() -> str:
    """pytest-playwright 的 `base_url`:`page.goto("/")` 開的是測試行程內的 UI。"""
    return f"http://127.0.0.1:{E2E_UI_PORT}"


@pytest.fixture
def e2e_servers(app_pair: AppPair, start_live_servers: Callable[..., Any]) -> Any:
    """UI 在 127.0.0.1:8781、Ollama 相容端點在 127.0.0.1:11437 的 uvicorn。"""
    return start_live_servers(app_pair, ui_port=E2E_UI_PORT, ollama_port=E2E_OLLAMA_PORT)
