"""正式啟動路徑 `python -m cgb` 的組裝(`cgb.__main__.build_pair`)。

實跑容器階段之前讀映像發現:`__main__` 一直傳 `remote_ollama=None`、`model_library=None`(Setup 時的佔位,
故事 2、3 做完後沒有回頭改),所有測試都經 `create_app` 注入替身,沒有一個走正式組裝,574 個全綠、真的容器卻開不起來;
也沒有辦法注入名稱前綴,實跑開出的名稱違反 P1。這裡只建 app,不啟動伺服器、不呼叫任何外部服務。
"""

from pathlib import Path

import pytest

from cgb.__main__ import build_pair, read_settings
from cgb.adapters.colab_cli import ColabControl
from cgb.adapters.google_oauth import GoogleOAuth
from cgb.adapters.model_library import ModelLibrary
from cgb.adapters.remote_ollama import RemoteOllama
from cgb.adapters.tunnel import Tunnel


def settings_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    return {
        "CGB_DB_PATH": str(tmp_path / "cgb.sqlite3"),
        "CGB_COLAB_CONFIG_DIR": str(tmp_path / "colab-cli"),
        "CGB_SSH_IDENTITY_PATH": str(tmp_path / "ssh" / "id_ed25519"),
        **extra,
    }


def test_正式組裝接上五個真的轉接層(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv("CGB_COLAB_CONFIG_DIR", str(tmp_path / "colab-cli"))
    monkeypatch.setenv("CGB_SSH_IDENTITY_PATH", str(tmp_path / "ssh" / "id_ed25519"))

    # Act
    state = build_pair(read_settings(settings_env(tmp_path))).state

    # Assert
    assert {
        "colab": type(state.colab),
        "tunnel": type(state.tunnel),
        "remote_ollama": type(state.remote_ollama),
        "model_library": type(state.model_library),
        "google_oauth": type(state.google_oauth),
    } == {
        "colab": ColabControl,
        "tunnel": Tunnel,
        "remote_ollama": RemoteOllama,
        "model_library": ModelLibrary,
        "google_oauth": GoogleOAuth,
    }


@pytest.mark.parametrize(("env", "expected"), [({}, "cgb-"), ({"CGB_NAME_PREFIX": "cgb-test-"}, "cgb-test-")])
def test_名稱前綴可由_CGB_NAME_PREFIX_設定_預設是_cgb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: dict[str, str], expected: str
) -> None:
    # Arrange
    monkeypatch.setenv("CGB_COLAB_CONFIG_DIR", str(tmp_path / "colab-cli"))
    monkeypatch.setenv("CGB_SSH_IDENTITY_PATH", str(tmp_path / "ssh" / "id_ed25519"))

    # Act
    state = build_pair(read_settings(settings_env(tmp_path, **env))).state

    # Assert
    assert state.name_prefix == expected
