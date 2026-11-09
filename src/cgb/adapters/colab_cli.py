"""Colab CLI 轉接層(`contracts/colab-cli.openapi.yaml`,S8)。

每個方法執行一次 `colab` 子行程(必要時再加一次 `colab sessions` 回讀),解析輸出後交出結果;
失敗一律丟 `AdapterError`,代碼照規格檔 `components.schemas.Error`。
"""

import asyncio
import json
import os
import re
import signal
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
SESSION_READY = "[colab] Session READY."
ALLOCATION_REFUSED = "[colab] Allocation refused (precondition failed)."
ACCELERATOR_REJECTED = "[colab] Backend rejected accelerator"
HIGH_MEM_IGNORED = "[colab] --high-mem ignored"
# 沒有 token 或 refresh 失敗(CLI 印授權網址後等授權碼,stdin 是 /dev/null 所以立刻 EOFError),或後端回 401
AUTH_MARKERS = ("To authorize colab-cli, visit this URL", ": Unauthorized")
SESSION_NOT_FOUND = re.compile(r"^\[colab\] Session '[^']*' not found\.$", re.MULTILINE)
RUNTIME_LOST = "appears to be lost (404/401)"
RESULT_PREFIX = "CGB-RESULT "
# `colab exec` 偶發、執行環境仍在(research.md R1);同一個命令列重跑一次(共用約定 6)
CONNECTION_LOST = "Connection was lost"
SCRIPTS = files("cgb.adapters.scripts")
# 遠端 Ollama 只聽執行環境本機(NFR-003,SSH 轉發接到這個位址);`OLLAMA_ORIGINS=*` 見 Q18、Q20
START_OLLAMA_ENV = ("--env", "OLLAMA_HOST=127.0.0.1:11434", "--env", "OLLAMA_ORIGINS=*")
TRACEBACK = "Traceback (most recent call last)"
# 網址一律換成 `<網址>`(網址裡有執行環境的 endpoint,NFR-010);結尾的標點不算網址的一部分
URL = re.compile(r"https?://\S*[^\s:,.;)\]'\"]")
# 依 stderr 字樣認出的網路問題(x-failure-rules 的 COLAB_UNREACHABLE、COLAB_TIMEOUT,先比對連不到)
UNREACHABLE_MARKERS = ("ConnectionError", "Max retries exceeded", "NameResolutionError", "Temporary failure in name resolution")
TIMEOUT_MARKERS = ("ReadTimeout", "timed out")
# `colab exec` 另有 CLI `--timeout` 到了的 TimeoutError
EXEC_TIMEOUT_MARKERS = ("TimeoutError", *TIMEOUT_MARKERS)
STOP_ATTEMPTS = 2
# 逾時終止 process group 時,SIGTERM 之後等多久再 SIGKILL(共用約定 8)
KILL_GRACE_SECONDS = 5.0
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
    version: float = 10.0
    new: float = 300.0
    start_ollama: float = 300.0
    probe_resources: float = 90.0
    stop: float = 60.0
    usage: float = 60.0


class ColabControl:
    def __init__(self, timeouts: CliTimeouts | None = None) -> None:
        self.timeouts = timeouts if timeouts is not None else CliTimeouts()

    async def get_cli_version(self) -> dict[str, Any]:
        stdout, stderr, returncode = await self._run("version", timeout=self.timeouts.version)
        raise_failed(returncode, stderr)
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
        stdout, stderr, returncode = await self._run("sessions", timeout=self.timeouts.sessions)
        raise_auth_required(stderr)
        raise_network_failure(stderr)
        raise_failed(returncode, stderr)
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
        # 逾時被終止時不回讀:呼叫者要自己以 listSessions 檢查遺留(x-failure-rules)
        stdout, stderr, returncode = await self._run(*args, timeout=self.timeouts.new)
        raise_auth_required(stderr)
        if ALLOCATION_REFUSED in stderr:
            raise AdapterError(
                "COLAB_ALLOCATION_REFUSED", "Colab 拒絕配置(同時開的執行環境太多,或這種類型暫時沒有容量),請稍後再試或換類型"
            )
        if ACCELERATOR_REJECTED in stderr:
            raise AdapterError("COLAB_ACCELERATOR_REJECTED", "這個 Colab 帳號沒有這種 GPU 的額度或權限")
        raise_network_failure(stderr)
        raise_failed(returncode, stderr)
        if SESSION_READY not in stdout:
            raise AdapterError("COLAB_BAD_RESPONSE", "Colab CLI 沒有回報配置完成(缺 Session READY.)")
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
        stdout, stderr, returncode = await self._run("usage", timeout=self.timeouts.usage)
        raise_auth_required(stderr)
        raise_network_failure(stderr)
        raise_failed(returncode, stderr, "讀不到 Colab 用量")
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
            self.timeouts.start_ollama,
            "-s", name, "-f", str(SCRIPTS / "start_ollama.py"), "--timeout", "240", *START_OLLAMA_ENV,
        )  # fmt: skip
        # 安裝程式等其他輸出一律忽略,取最後一個結果行(共用約定 5)
        if not any(line.startswith(RESULT_PREFIX) for line in stdout.splitlines()) and TRACEBACK in stderr:
            last = masked_last_line(stderr)
            raise AdapterError("COLAB_REMOTE_ERROR", f"執行環境上的初始化腳本發生錯誤:{last}", last)
        result = result_line(stdout)
        if result.get("ok") is not True:
            raise AdapterError(
                "COLAB_REMOTE_ERROR",
                f"在執行環境上啟動 Ollama 失敗(階段 {result.get('stage')}):{result.get('detail')}",
            )
        return {"ollamaVersion": result["ollamaVersion"], "alreadyRunning": result["alreadyRunning"]}

    async def probe_resources(self, name: str) -> dict[str, Any]:
        stdout, _ = await self._exec_script(
            self.timeouts.probe_resources, "-s", name, "-f", str(SCRIPTS / "probe_resources.py"), "--timeout", "30"
        )
        result_line(stdout)
        return {}

    async def stop_session(self, name: str) -> dict[str, Any]:
        # `colab stop` 的 exit code 與輸出都不反映結果(research.md R1),一律以回讀為準
        # 回讀仍看得到就再結束一次、再回讀一次(x-retry)
        for _ in range(STOP_ATTEMPTS):
            try:
                stdout, stderr, _ = await self._run("stop", "-s", name, timeout=self.timeouts.stop)
            except AdapterError as error:
                if error.code != "COLAB_TIMEOUT":
                    raise
                # `colab stop` 本身逾時:已終止整個 group,照常回讀、以回讀為準(Q139)
                stdout, stderr = "", ""
            raise_auth_required(stderr)
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
                start_new_session=True,
            )
        except FileNotFoundError:
            raise AdapterError("COLAB_NOT_INSTALLED", "找不到 Colab CLI(colab 執行檔)") from None
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
        except TimeoutError:
            await terminate_group(process)
            raise AdapterError("COLAB_TIMEOUT", f"Colab CLI 在 {timeout:g} 秒內沒有回應") from None
        return stdout.decode(errors="replace"), stderr.decode(errors="replace"), process.returncode

    async def _exec_script(self, timeout: float, *args: str) -> tuple[str, str]:
        """`colab exec <args>`;遇到 `Connection was lost` 以同一個命令列重跑一次,仍是就歸成 COLAB_UNREACHABLE。"""
        stdout, stderr, returncode = await self._run("exec", *args, timeout=timeout)
        # 執行環境已不在(本機沒有這個名稱,或已被收回);這時不重試。lost 字樣 stdout、stderr 都看(Q140)
        if SESSION_NOT_FOUND.search(stdout) or RUNTIME_LOST in stdout + stderr:
            raise AdapterError("COLAB_NOT_FOUND", "Colab 執行環境已經不在")
        raise_auth_required(stderr)
        if CONNECTION_LOST in stderr:
            stdout, stderr, returncode = await self._run("exec", *args, timeout=timeout)
            if CONNECTION_LOST in stderr:
                raise AdapterError("COLAB_UNREACHABLE", "與 Colab 執行環境的連線中斷,重試一次後仍中斷")
        raise_network_failure(stderr, EXEC_TIMEOUT_MARKERS)
        raise_failed(returncode, stderr)
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


async def terminate_group(process: asyncio.subprocess.Process) -> None:
    """對子行程整個 process group 先送 SIGTERM,等不到再送 SIGKILL,並回收子行程(共用約定 8、Q138)。"""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(process.wait(), KILL_GRACE_SECONDS)
    except TimeoutError:
        pass
    # 帶頭的行程結束了,它分出、還留在同一個 group 的子行程也不能留下
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await process.wait()


def raise_network_failure(stderr: str, timeout_markers: tuple[str, ...] = TIMEOUT_MARKERS) -> None:
    """stderr 有連不到或逾時的字樣時丟出對應的錯誤。"""
    if any(marker in stderr for marker in UNREACHABLE_MARKERS):
        raise AdapterError("COLAB_UNREACHABLE", "連不到 Colab")
    if any(marker in stderr for marker in timeout_markers):
        raise AdapterError("COLAB_TIMEOUT", "Colab 沒有在時限內回應")


def raise_auth_required(stderr: str) -> None:
    """CLI 要求授權或 Colab 後端回 401 時丟 AUTH_REQUIRED(Q26:不另造 COLAB_ 代碼)。"""
    if any(marker in stderr for marker in AUTH_MARKERS):
        raise AdapterError("AUTH_REQUIRED", "Colab 授權已失效,請重新登入")


def raise_failed(returncode: int, stderr: str, message: str = "Colab CLI 執行失敗") -> None:
    """沒有被其他規則認出、但以非 0 結束時丟 COLAB_FAILED,附 stderr 最後一個非空行(網址已遮蔽)。"""
    if returncode != 0:
        last = masked_last_line(stderr)
        raise AdapterError("COLAB_FAILED", message + (f":{last}" if last else ""), last)


def result_line(stdout: str) -> dict[str, Any]:
    """stdout 最後一個 `CGB-RESULT ` 行的 JSON(共用約定 5);沒有或不是 JSON 物件就是 COLAB_BAD_RESPONSE。"""
    lines = [line for line in stdout.splitlines() if line.startswith(RESULT_PREFIX)]
    if not lines:
        raise AdapterError("COLAB_BAD_RESPONSE", "執行環境上的腳本沒有回報結果")
    try:
        result = json.loads(lines[-1][len(RESULT_PREFIX) :])
    except ValueError:
        raise AdapterError("COLAB_BAD_RESPONSE", "執行環境上的腳本回報的結果無法解析") from None
    if not isinstance(result, dict):
        raise AdapterError("COLAB_BAD_RESPONSE", "執行環境上的腳本回報的結果無法解析")
    return result
