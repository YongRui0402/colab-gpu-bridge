"""全域:啟動前整理資料夾(testplan.md § G-04;spec.md § NFR-010、NFR-012;compose.yaml § services.cgb.volumes、tmpfs)。

接縫:以子行程跑 `deploy/prepare-data.sh`(容器的 ENTRYPOINT `cgb-prepare-data`),暫存資料夾當 `CGB_DATA_DIR`。
"""

import json
import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "deploy" / "prepare-data.sh"
FAKE_TOKEN = "cgb-test-fake-token-0123456789"


def run_script(data: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # 不沿用測試行程的 CGB_* 環境變數:路徑全部由 CGB_DATA_DIR 推導
    env = {key: value for key, value in os.environ.items() if not key.startswith("CGB_")}
    env["CGB_DATA_DIR"] = str(data)
    return subprocess.run(["sh", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=30)


def files_containing(root: Path, needle: str) -> list[Path]:
    """root 底下含 needle 的一般檔(符號連結不跟隨,colab.log 指向 /dev/null)。"""
    found = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        if needle.encode() in path.read_bytes():
            found.append(path)
    return found


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_啟動前整理後_colab_log_指向_dev_null_設定只改更新檢查_權限_0700(tmp_path: Path) -> None:
    # Arrange:colab.log 是含假 token 的一般檔;settings.json 有其他欄位
    data = tmp_path / "data"
    cli = data / "colab-cli"
    cli.mkdir(parents=True)
    (cli / "colab.log").write_text(f"DEBUG Authorization: Bearer {FAKE_TOKEN}\n", encoding="utf-8")
    (cli / "settings.json").write_text(json.dumps({"enable_update_check": True, "x": 1}), encoding="utf-8")

    # Act
    prepared = run_script(data, "true")
    checked = run_script(data, "--check")

    # Assert
    log = cli / "colab.log"
    assert prepared.returncode == 0, prepared.stderr
    assert log.is_symlink() and os.readlink(log) == "/dev/null"  # 則1
    assert files_containing(tmp_path, FAKE_TOKEN) == []  # 則2
    assert json.loads((cli / "settings.json").read_text(encoding="utf-8")) == {"enable_update_check": False, "x": 1}  # 則3
    assert {p.name: oct(mode(p)) for p in (data, cli, data / "ssh")} == dict.fromkeys(("data", "colab-cli", "ssh"), "0o700")  # 則4
    assert checked.returncode == 0, checked.stderr  # 則5
