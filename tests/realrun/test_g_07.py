"""G-07(tasks.md T299):容器重建後授權與紀錄都還在、權限正確、history 是空的 tmpfs(NFR-012、NFR-010)。

整批實跑的最後(P3 之後)。`<暫存目錄>/.env` 只有那四個變數;`down` 之後 `up -d --force-recreate --no-build`(沿用已建好的映像)。
不開執行環境,0 compute units,約 3 分鐘;只操作 `-p cgb-test`,不碰 named volume `cgb-data`;重建後不按「開啟」。
重建前的 `GET /api/sessions` 筆數由 `test_p3.py` 在收尾前記下。
"""

import time

from realrun.helpers_container import get_stack, verdict

PERMISSION_FILES = ("/data/cgb.sqlite3", "/data/colab-cli/token.json", "/data/ssh/id_ed25519")
HEALTHY_DEADLINE = 90


def test_g_07(realrun):
    stack = get_stack(realrun)
    env_keys = sorted(line.split("=", 1)[0] for line in realrun.env_file.read_text().splitlines() if "=" in line)
    extra: list[str] = []
    if env_keys != ["CGB_BIND_ADDR", "CGB_HOST_DATA", "CGB_HOST_OLLAMA_PORT", "CGB_HOST_UI_PORT"]:
        extra.append(f".env 的變數是 {env_keys}")

    down = realrun.compose("down", timeout=180)
    up = realrun.compose("up", "-d", "--force-recreate", "--no-build", timeout=240)
    upped = time.monotonic()
    raw = f"$ down (exit {down.returncode}) / up -d --force-recreate --no-build (exit {up.returncode})\n{up.stderr}\n"
    realrun.record_raw("compose", raw)
    healthy_s = stack.wait_healthy(HEALTHY_DEADLINE + 30)
    if healthy_s is not None:
        healthy_s = time.monotonic() - upped

    auth = stack.ui("GET", "/api/auth").json() if healthy_s is not None else {}
    history = stack.ui("GET", "/api/sessions?limit=100").json() if healthy_s is not None else {}
    count = len(history.get("items", []))
    modes = {}
    for path in PERMISSION_FILES:
        result = stack.docker_exec("stat", "-c", "%a", path)
        modes[path] = result.stdout.strip() if result.returncode == 0 else "不存在"
    fstype = stack.docker_exec("stat", "-f", "-c", "%T", "/data/colab-cli/history").stdout.strip()
    entries = stack.docker_exec("sh", "-c", "ls -A /data/colab-cli/history | wc -l").stdout.strip()

    before = stack.state.get("history_count")
    checks = {
        "則1": healthy_s is not None and healthy_s <= HEALTHY_DEADLINE,
        "則2": auth.get("state") == "logged_in",
        "則3": before is not None and count == before,
        "則4": all(mode == "600" for mode in modes.values()),
        "則5": fstype == "tmpfs" and entries == "0",
    }
    numbers = (
        f"up 到 healthy {f'{healthy_s:.1f} 秒' if healthy_s is not None else '沒有 healthy'};auth {auth.get('state')};"
        f"紀錄 重建前 {before} 筆、重建後 {count} 筆;權限 {modes};history {fstype}、{entries} 個項目"
    )
    if stack.state.get("history_has_more"):
        extra.append("紀錄超過 100 筆,只比第一頁")
    verdict(
        "G-07", "T299", checks, numbers,
        "則1 90 秒內 healthy;則2 logged_in;則3 筆數相同;則4 三個檔 0600;則5 history 是 tmpfs 且是空的",
        extra,
    )  # fmt: skip
