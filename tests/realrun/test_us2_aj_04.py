"""US2-AJ-04(tasks.md T184):遠端 Ollama 只聽執行環境本機、轉發 port 不發布,區網裝置繞不過本系統(NFR-003)。

沿用 US1-AJ-17 的 T4,約 2 分鐘、約 0.04 compute units。
監聽位址以主機上的 `HOME=<暫存目錄>/home colab exec -s <名稱> -f tests/realrun/scripts/listen_check.py` 讀
(`realrun.colab()`,只讀的腳本;和容器共用 `<暫存目錄>/data/colab-cli`)。判定者:腳本;樣本:一次實跑。
"""

import json
import re
import subprocess

import httpx

from realrun.conftest import REALRUN_DIR, URL_PATTERN, mask_urls
from realrun.helpers_container import CONTAINER, UI, get_stack, verdict

LISTEN_SCRIPT = REALRUN_DIR / "scripts" / "listen_check.py"
DOCKER_PORT_LINE = re.compile(r"^(\d+)/tcp -> ([\d.:\[\]]+):(\d+)$")
RUNTIME_HOST_HINTS = ("colab", "googleusercontent", "/tun/m/")


# Colab 的公開官網(失聯畫面「打開 Colab 網頁」的連結,原型就有)不是執行環境的網址(實跑 US2-AJ-04 第一次誤判)
PUBLIC_COLAB_SITE = "https://colab.research.google.com/"


def runtime_urls(text: str) -> list[str]:
    return [
        u for u in URL_PATTERN.findall(text)
        if u != PUBLIC_COLAB_SITE and any(h in u for h in RUNTIME_HOST_HINTS)
    ]  # fmt: skip


def test_us2_aj_04(realrun):
    stack = get_stack(realrun)
    stack.require("US2-AJ-04", "T184", "main_ready")
    name = stack.state["main"]
    extra: list[str] = []

    result = realrun.colab("exec", "-s", name, "-f", str(LISTEN_SCRIPT), "--timeout", "30", timeout=120)
    realrun.record_raw("us2_aj_04", f"$ colab exec listen_check (exit {result.returncode})\n{result.stdout}{result.stderr}\n")
    lines = [line for line in result.stdout.splitlines() if line.startswith("CGB-LISTEN ")]
    listening = json.loads(lines[-1][len("CGB-LISTEN ") :]) if lines else None
    on_11434 = sorted({addr for addr, port in listening or [] if port == 11434})
    c1 = bool(on_11434) and all(addr in ("127.0.0.1", "::1") for addr in on_11434)
    if listening is None:
        extra.append(f"listen_check 沒有結果行;stderr 最後一行:{mask_urls((result.stderr.strip().splitlines() or [''])[-1])[:160]}")

    port_out = subprocess.run(["docker", "port", CONTAINER], capture_output=True, text=True, timeout=30).stdout
    mapping = {}
    for line in port_out.splitlines():
        m = DOCKER_PORT_LINE.match(line.strip())
        if m:
            mapping.setdefault(int(m.group(1)), set()).add((m.group(2), int(m.group(3))))
    c2 = set(mapping) == {8780, 11434} and {p for _, p in mapping[11434]} == {11436}

    try:
        httpx.get("http://127.0.0.1:11435/api/version", timeout=3)
        c3 = False
        extra.append("主機對 127.0.0.1:11435 連得上")
    except httpx.ConnectError:
        c3 = True
    except httpx.HTTPError as error:
        c3 = False
        extra.append(f"主機對 11435:{type(error).__name__}")

    session_text = stack.ui("GET", "/api/session").text
    home_html = httpx.get(f"{UI}/", timeout=10).text
    leaked = runtime_urls(session_text) + runtime_urls(home_html)
    c4 = not leaked and not URL_PATTERN.search(session_text)
    if leaked:
        extra.append(f"出現執行環境網址 {len(leaked)} 個(內容不記)")

    numbers = f"執行環境 11434 監聽於 {on_11434};docker port {sorted((k, sorted(v)) for k, v in mapping.items())};11435 連不上 {c3}"
    verdict(
        "US2-AJ-04", "T184", {"則1": c1, "則2": c2, "則3": c3, "則4": c4}, numbers,
        "則1 11434 只聽 127.0.0.1;則2 只發布 8780 與 11434→11436;則3 主機連不上 11435;則4 回應與首頁沒有執行環境網址",
        extra,
    )  # fmt: skip
