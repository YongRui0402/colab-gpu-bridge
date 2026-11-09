"""Colab CLI 轉接層(`contracts/colab-cli.openapi.yaml`,S8)。

每個方法執行一次 `colab` 子行程(必要時再加一次 `colab sessions` 回讀),解析輸出後交出結果;
失敗一律丟 `AdapterError`,代碼照規格檔 `components.schemas.Error`。
"""

import asyncio
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any

from cgb.adapters.errors import AdapterError

SUPPORTED_VERSION = "0.7.5"
VERSION_LINE = re.compile(r"^Version: (\S+)$")
# CLI 0.7.5 `commands/session.py` 的 `_format_session_line`;第 2 組是 endpoint,解析後就丟掉(NFR-010)
SESSION_LINE = re.compile(
    r"^\[([^\]]+)\] (\S+) \| Hardware: ([A-Z0-9]+) \| Shape: (Standard|High-RAM) \| Variant: (DEFAULT|GPU|TPU)$"
)
NOTICE_PREFIX = "[colab] "
UNNAMED = "?"
# CLI 對 Colab 後端的每個 HTTP 請求最多等 60 秒(CLI 預設不設讀取逾時;共用約定 2)
CLI_ENV = {"COLAB_CLI_REQUEST_TIMEOUT": "60"}
HIGH_MEM_IGNORED = "[colab] --high-mem ignored"
# 沒有 token 或 refresh 失敗(CLI 印授權網址後等授權碼,stdin 是 /dev/null 所以立刻 EOFError),或後端回 401
AUTH_MARKERS = ("To authorize colab-cli, visit this URL", ": Unauthorized")
RESULT_PREFIX = "CGB-RESULT "
# `colab exec` 偶發、執行環境仍在(research.md R1);同一個命令列重跑一次(共用約定 6)
CONNECTION_LOST = "Connection was lost"
SCRIPTS = files("cgb.adapters.scripts")
TRACEBACK = "Traceback (most recent call last)"
# 網址一律換成 `<網址>`(網址裡有執行環境的 endpoint,NFR-010);結尾的標點不算網址的一部分
URL = re.compile(r"https?://\S*[^\s:,.;)\]'\"]")
STOP_ATTEMPTS = 2
# CLI 0.7.5 `consumption.py` 的 `format_consumption_status`(數字一律兩位小數)
USAGE_LINES = {
    "balance": re.compile(r"^Current balance: (-?\d+\.\d{2}) compute units$"),
    "ratePerHour": re.compile(r"^Usage rate: (-?\d+\.\d{2})/hr$"),
    "activeAssignments": re.compile(r"^Active assignments: (\d+)$"),
}
# `GpuType`;CLI 對認不得的 GPU 名稱不報錯、直接當成 A100,所以只有這幾個值能放進命令列
GPU_TYPES = frozenset({"T4", "L4", "G4", "A100", "H100"})


@dataclass(frozen=True)
class CliTimeouts:
    """各子行程的時限(秒,`x-timeout`);測試注入縮短的值。"""

    sessions: float = 60.0


class ColabControl:
    def __init__(self, timeouts: CliTimeouts | None = None) -> None:
        self.timeouts = timeouts if timeouts is not None else CliTimeouts()

    async def get_cli_version(self) -> dict[str, Any]:
        stdout, _, _ = await self._run("version")
        for line in stdout.splitlines():
            match = VERSION_LINE.match(line)
            if match:
                version = match.group(1)
                if version != SUPPORTED_VERSION:
                    raise AdapterError(
                        "COLAB_UNSUPPORTED_VERSION",
                        f"Colab CLI 版本不是支援的 {SUPPORTED_VERSION}:{version}",
                    )
                return {"version": version}
        raise AdapterError("COLAB_BAD_RESPONSE", "Colab CLI 的 version 輸出無法解析")

    async def list_sessions(self) -> dict[str, Any]:
        stdout, _, _ = await self._run("sessions", timeout=self.timeouts.sessions)
        named: list[dict[str, str]] = []
        unnamed: list[dict[str, str]] = []
        for line in stdout.splitlines():
            if not line.strip() or line.startswith(NOTICE_PREFIX):
                continue
            match = SESSION_LINE.match(line)
            if not match:
                # 除了 `[colab] ` 訊息與空行,任何對不上格式的行都表示 CLI 的輸出格式變了;略過會讓執行環境「消失」
                raise AdapterError("COLAB_BAD_RESPONSE", "Colab CLI 的 sessions 輸出有一行格式不符")
            name, _endpoint, hardware, shape, variant = match.groups()
            listed = {"hardware": hardware, "shape": shape, "variant": variant}
            if name == UNNAMED:
                unnamed.append(listed)
            else:
                named.append({"name": name, **listed})
        return {"named": named, "unnamed": unnamed}

    async def create_session(self, name: str, gpu: str, high_mem: bool) -> dict[str, Any]:
        if gpu not in GPU_TYPES:
            raise ValueError(f"gpu 必須是 GpuType 之一({', '.join(sorted(GPU_TYPES))}),收到 {gpu!r}")
        args = ["new", "-s", name, "--gpu", gpu]
        if high_mem:
            args.append("--high-mem")
        _, stderr, _ = await self._run(*args)
        # exit code 與 `Session READY.` 都不算數,以回讀為準(共用約定 1)
        listed = await self.list_sessions()
        for session in listed["named"]:
            if session["name"] == name:
                return {
                    "name": name,
                    "hardware": session["hardware"],
                    "shape": session["shape"],
                    "highMemIgnored": HIGH_MEM_IGNORED in stderr,
                }
        raise AdapterError("COLAB_NOT_FOUND", f"Colab 回報配置完成,但執行環境清單裡沒有 {name}")

    async def get_usage(self) -> dict[str, Any]:
        stdout, stderr, returncode = await self._run("usage")
        if any(marker in stderr for marker in AUTH_MARKERS):
            raise AdapterError("AUTH_REQUIRED", "Colab 授權已失效,請重新登入")
        if returncode != 0:
            last = masked_last_line(stderr)
            raise AdapterError("COLAB_FAILED", "讀不到 Colab 用量" + (f":{last}" if last else ""), last)
        values = {}
        for line in stdout.splitlines():
            for key, pattern in USAGE_LINES.items():
                match = pattern.match(line)
                if match:
                    values[key] = match.group(1)
        if values.keys() != USAGE_LINES.keys():
            raise AdapterError("COLAB_BAD_RESPONSE", "Colab CLI 的 usage 輸出無法解析")
        return {
            "balance": float(values["balance"]),
            "ratePerHour": float(values["ratePerHour"]),
            "activeAssignments": int(values["activeAssignments"]),
            "readAt": datetime.now(UTC).isoformat(),
        }

    async def start_ollama(self, name: str) -> dict[str, Any]:
        stdout, stderr = await self._exec_script(
            "-s", name, "-f", str(SCRIPTS / "start_ollama.py"), "--timeout", "240",
            "--env", "OLLAMA_HOST=127.0.0.1:11434", "--env", "OLLAMA_ORIGINS=*",
        )  # fmt: skip
        # 安裝程式等其他輸出一律忽略,取最後一個結果行(共用約定 5)
        result_lines = [line for line in stdout.splitlines() if line.startswith(RESULT_PREFIX)]
        if not result_lines and TRACEBACK in stderr:
            last = masked_last_line(stderr)
            raise AdapterError("COLAB_REMOTE_ERROR", f"執行環境上的初始化腳本發生錯誤:{last}", last)
        result = json.loads(result_lines[-1][len(RESULT_PREFIX) :])
        return {"ollamaVersion": result["ollamaVersion"], "alreadyRunning": result["alreadyRunning"]}

    async def probe_resources(self, name: str) -> dict[str, Any]:
        await self._exec_script("-s", name, "-f", str(SCRIPTS / "probe_resources.py"), "--timeout", "30")
        return {}

    async def stop_session(self, name: str) -> dict[str, Any]:
        # `colab stop` 的 exit code 與輸出都不反映結果(research.md R1),一律以回讀為準
        # 回讀仍看得到就再結束一次、再回讀一次(x-retry)
        for _ in range(STOP_ATTEMPTS):
            stdout, stderr, _ = await self._run("stop", "-s", name)
            listed = await self.list_sessions()
            if all(session["name"] != name for session in listed["named"]):
                return {"name": name, "stopOutput": stop_output_of(stdout)}
        last = masked_last_line(stderr)
        raise AdapterError(
            "COLAB_STOP_UNCONFIRMED",
            f"結束兩次之後 Colab 仍列出 {name},請到 Colab 網頁確認並手動結束" + (f":{last}" if last else ""),
            last,
        )

    async def _run(self, *args: str, timeout: float | None = None) -> tuple[str, str, int]:
        """執行一次 `colab <args>`,stdin 接 /dev/null;交回 stdout、stderr 的文字與 exit code。

        找不到執行檔歸成 COLAB_NOT_INSTALLED;超過 `timeout` 就殺掉子行程並等它結束(不留殭屍),歸成 COLAB_TIMEOUT。
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "colab",
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **CLI_ENV},
            )
        except FileNotFoundError:
            raise AdapterError("COLAB_NOT_INSTALLED", "找不到 Colab CLI(colab 執行檔)") from None
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise AdapterError("COLAB_TIMEOUT", f"Colab CLI 在 {timeout:g} 秒內沒有回應") from None
        return stdout.decode(errors="replace"), stderr.decode(errors="replace"), process.returncode

    async def _exec_script(self, *args: str) -> tuple[str, str]:
        """`colab exec <args>`;遇到 `Connection was lost` 以同一個命令列重跑一次,仍是就歸成 COLAB_UNREACHABLE。"""
        stdout, stderr, _ = await self._run("exec", *args)
        if CONNECTION_LOST in stderr:
            stdout, stderr, _ = await self._run("exec", *args)
            if CONNECTION_LOST in stderr:
                raise AdapterError("COLAB_UNREACHABLE", "與 Colab 執行環境的連線中斷,重試一次後仍中斷")
        return stdout, stderr


def masked_last_line(text: str) -> str | None:
    """最後一個非空行,其中的網址換成 `<網址>`;沒有就是 None。"""
    lines = [line for line in text.splitlines() if line.strip()]
    return URL.sub("<網址>", lines[-1]) if lines else None


def stop_output_of(stdout: str) -> str:
    """`StoppedSession.stopOutput`:最後一次 `colab stop` 的輸出是哪一種。"""
    if "[colab] Session terminated." in stdout:
        return "terminated"
    if "not found." in stdout:
        return "not_found"
    return "error"
