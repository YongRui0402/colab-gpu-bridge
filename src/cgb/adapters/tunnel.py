"""E6 SSH 通道的轉接層(`contracts/tunnel.openapi.yaml`)。

方法名照 `tests/fakes/adapters.py` 的 `FakeTunnel`(plan.md Q124):
`ensure_key`、`open_tunnel`、`check_health`、`close_tunnel`、`cleanup_residual`。
失敗一律丟 `AdapterError`,代碼是規格 `Error` 的 `TUNNEL_` 代碼(plan.md Q37、Q65)。
"""

import asyncio
import contextlib
import logging
import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from cgb.adapters.errors import AdapterError

logger = logging.getLogger(__name__)

KEYGEN_TIMEOUT = 10.0  # ensureTunnelKey 的 x-timeout:每個命令 10 秒
ACCEPTED_KEY_TYPE = "ssh-ed25519"
# `ssh-keygen -l -E sha256` 的 stdout:`<位元數> SHA256:<指紋> <註解> (<類型>)`
FINGERPRINT_LINE = re.compile(r"^\d+ (SHA256:[A-Za-z0-9+/]{43}) .*\(\S+\)$")

READY_DEADLINE = 30.0  # openTunnel 的 x-readiness.deadline
READY_INTERVAL = 0.5  # openTunnel 的 x-readiness.interval
PROBE_TIMEOUT = 5.0  # `/api/version` 的逾時(S1 getVersion,plan.md Q5)
LOOPBACK = "127.0.0.1"  # 本機轉發只綁這個位址,不加 `-g`(NFR-003:不經公開網址)
REMOTE_OLLAMA = "127.0.0.1:11434"
ALARM_POLL = 0.02  # 等 `/api/version` 回應時,多久看一次 stderr 有沒有要立即處理的行
# `colab ssh` 找不到名稱、自己開了新的執行環境(Q64):立即關閉,回 TUNNEL_NOT_FOUND
CREATING_RUNTIME = "[colab] Creating runtime '"
REMOTE_REFUSED = "open failed: connect failed"
STDERR_DRAIN = 1.0  # ssh 結束後,等 stderr 讀完的上限
TERM_WAIT = 5.0  # closeTunnel:SIGTERM 後最多等 5 秒
KILL_WAIT = 2.0  # closeTunnel:SIGKILL 後最多等 2 秒
EXIT_POLL = 0.02  # 等行程結束、port 關閉時的輪詢間隔

# `Error.x-stderr-patterns`:由上而下比對,第一個比中的決定代碼(`[colab] ` 行排在 OpenSSH 的字樣前面)
STDERR_PATTERNS: tuple[tuple[str, str], ...] = (
    (CREATING_RUNTIME, "TUNNEL_NOT_FOUND"),
    ("[colab] Endpoint not found (HTTP 404)", "TUNNEL_NOT_FOUND"),
    ("[colab] session '", "TUNNEL_NOT_FOUND"),
    ("[colab] Server rejected", "TUNNEL_KEY_REJECTED"),
    ("[colab] no SSH public key found", "TUNNEL_KEY_REJECTED"),
    ("[colab] --identity ", "TUNNEL_KEY_REJECTED"),
    ("[colab] failed to derive public key", "TUNNEL_KEY_REJECTED"),
    ("Permission denied (publickey", "TUNNEL_KEY_REJECTED"),
    ("[colab] Authentication failed (HTTP 401)", "TUNNEL_TOKEN_REJECTED"),
    ("[colab] Forbidden (HTTP 403)", "TUNNEL_TOKEN_REJECTED"),
    ("[colab] Already-active SSH session (HTTP 429)", "TUNNEL_ALREADY_CONNECTED"),
    ("[colab] Bad gateway (HTTP 502)", "TUNNEL_SERVER_ERROR"),
    ("[colab] WebSocket connection failed", "TUNNEL_UNREACHABLE"),
    ("[colab] WebSocket upgrade failed without an HTTP status", "TUNNEL_UNREACHABLE"),
    ("Could not request local forwarding", "TUNNEL_PORT_IN_USE"),
    ("Timeout, server colab-runtime not responding", "TUNNEL_TIMEOUT"),
    ("open failed: connect failed", "TUNNEL_REMOTE_REFUSED"),
    ("colab: not found", "TUNNEL_NOT_INSTALLED"),
    ("colab: No such file or directory", "TUNNEL_NOT_INSTALLED"),
    ("kex_exchange_identification", "TUNNEL_UNREACHABLE"),
    ("Connection closed by UNKNOWN port 65535", "TUNNEL_UNREACHABLE"),
    ("Broken pipe", "TUNNEL_UNREACHABLE"),
)
# 每次連線都印的 known_hosts 警告;ssh 被殺時 ProxyCommand(`colab ssh`)收尾印的 Python 雜訊(實跑 US1-TUN-10)
STDERR_IGNORE = ("Warning: Permanently added 'colab-runtime'", "Exception ignored in: <_io.TextIOWrapper name='<stdout>'")

FAILURE_MESSAGES = {
    "TUNNEL_NOT_FOUND": "要連的執行環境已經不在",
    "TUNNEL_KEY_REJECTED": "通道金鑰不被接受",
    "TUNNEL_TOKEN_REJECTED": "Colab 不接受連線的憑證,執行環境可能已過期或被收回",
    "TUNNEL_ALREADY_CONNECTED": "這台執行環境已經有另一條連線",
    "TUNNEL_SERVER_ERROR": "執行環境上的 SSH 服務連不到",
    "TUNNEL_UNREACHABLE": "連不到 Colab 執行環境",
    "TUNNEL_PORT_IN_USE": "本機轉發的 port 已被占用",
    "TUNNEL_TIMEOUT": "Colab 執行環境沒有回應",
    "TUNNEL_REMOTE_REFUSED": "執行環境上的模型服務沒有在聽",
    "TUNNEL_NOT_INSTALLED": "找不到 colab 指令",
    "TUNNEL_FAILED": "SSH 通道意外結束",
}


# NFR-010:附在 TUNNEL_FAILED 與日誌裡的 stderr 先遮蔽 runtime proxy token 與網址(info 的機密規則)
PROXY_TOKEN = re.compile(r"(colab-runtime-proxy-token=)[^&\s]*")
URL = re.compile(r"(?:wss?|https?)://\S*")


def mask_secrets(line: str) -> str:
    return URL.sub("<url>", PROXY_TOKEN.sub(r"\1<token>", line))


def _masked_last_line(stderr: str) -> str | None:
    """stderr 遮蔽後的最後一個非空行;stderr 為空時不附(None)。"""
    lines = [line for line in stderr.splitlines() if line.strip()]
    return mask_secrets(lines[-1]) if lines else None


def relevant_lines(lines: list[str]) -> list[str]:
    """略過 `x-stderr-ignore` 的行(每次連線都會印的 known_hosts 警告)。"""
    return [line for line in lines if not line.startswith(STDERR_IGNORE)]


def classify_stderr(lines: list[str]) -> str | None:
    """依 `x-stderr-patterns` 判定代碼;略過 `x-stderr-ignore` 的行;比對不到回 None。"""
    relevant = relevant_lines(lines)
    for pattern, code in STDERR_PATTERNS:
        if any(pattern in line for line in relevant):
            return code
    return None


def base_url_of(local_port: int) -> str:
    """本機轉發的 base URL(S1 遠端 Ollama 的 base URL)。"""
    return f"http://{LOOPBACK}:{local_port}"


def ssh_argv(session_name: str, key_path: str, local_port: int) -> list[str]:
    """openTunnel 的 x-argv,逐字代入;ProxyCommand 不帶 `--gpu`、`--tpu`、`--high-mem`、`--rm`(Q64)。"""
    return [
        "ssh", "-F", "none", "-N", "-i", key_path,
        "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", f"ProxyCommand=colab ssh --proxy-mode -s {session_name} --identity {key_path}",
        "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3", "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-L", f"{LOOPBACK}:{local_port}:{REMOTE_OLLAMA}", "root@colab-runtime",
    ]  # fmt: skip


@dataclass
class _Forward:
    """一條執行中的轉發:ssh 子行程(自成一個 process group)與持續讀進來的 stderr。"""

    process: subprocess.Popen[bytes]
    local_port: int
    stderr_lines: list[str] = field(default_factory=list)
    creating_runtime: threading.Event = field(default_factory=threading.Event)
    stderr_closed: threading.Event = field(default_factory=threading.Event)
    attention: threading.Event = field(default_factory=threading.Event)

    def read_stderr(self) -> None:
        assert self.process.stderr is not None
        for raw in self.process.stderr:
            line = raw.decode(errors="replace").rstrip("\n")
            self.stderr_lines.append(line)
            if CREATING_RUNTIME in line:
                self.creating_runtime.set()
                self.attention.set()
        self.stderr_closed.set()
        self.attention.set()

    def saw_remote_refused(self) -> bool:
        """stderr 有沒有出現過 `open failed: connect failed`(遠端 11434 拒絕了轉發的連線)。"""
        return any(REMOTE_REFUSED in line for line in self.stderr_lines)


async def _run(*argv: str, timeout: float = KEYGEN_TIMEOUT) -> tuple[str, str]:
    """執行一個命令,stdin 接 /dev/null(不讓 ssh-keygen 停下來等密碼),回傳 stdout 與 stderr。"""
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        raise AdapterError("TUNNEL_NOT_INSTALLED", f"找不到 {argv[0]} 指令") from None
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        # 逾時(例如停下來等輸入密碼)視為 TUNNEL_FAILED(Q147);結束並回收子行程,不留殭屍
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        raise AdapterError("TUNNEL_FAILED", f"{argv[0]} 在時限內沒有完成") from None
    return stdout.decode(errors="replace"), stderr.decode(errors="replace")


class Tunnel:
    def __init__(
        self,
        *,
        ready_deadline: float = READY_DEADLINE,
        ready_interval: float = READY_INTERVAL,
        probe_timeout: float = PROBE_TIMEOUT,
        term_wait: float = TERM_WAIT,
        kill_wait: float = KILL_WAIT,
        keygen_timeout: float = KEYGEN_TIMEOUT,
    ) -> None:
        self._ready_deadline = ready_deadline
        self._ready_interval = ready_interval
        self._probe_timeout = probe_timeout
        self._term_wait = term_wait
        self._kill_wait = kill_wait
        self._keygen_timeout = keygen_timeout
        self._forwards: dict[str, _Forward] = {}

    async def ensure_key(self, key_path: str) -> dict[str, Any]:
        """準備通道專用的 ed25519 金鑰(ensureTunnelKey);已存在就不覆寫,只回類型與指紋。"""
        created = False
        if not os.path.exists(key_path):
            _, create_err = await _run(
                "ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "cgb-tunnel", "-f", key_path,
                timeout=self._keygen_timeout,
            )  # fmt: skip
            # `-q` 成功時本來就沒有輸出,所以只看檔案在不在(Q148)
            if not os.path.exists(key_path):
                raise AdapterError("TUNNEL_FAILED", "產生通道金鑰失敗", stderr_last_line=_masked_last_line(create_err))
            created = True

        public_key, _ = await _run("ssh-keygen", "-y", "-P", "", "-f", key_path, timeout=self._keygen_timeout)
        # 只取第一個欄位(類型);公鑰本文不記錄、不回傳
        key_type = public_key.split(maxsplit=1)[0] if public_key.strip() else ""
        if key_type != ACCEPTED_KEY_TYPE:
            raise AdapterError("TUNNEL_KEY_REJECTED", "通道金鑰不是沒有密碼的 ed25519,Colab 不接受")

        fingerprint_out, fingerprint_err = await _run(
            "ssh-keygen", "-l", "-E", "sha256", "-f", key_path, timeout=self._keygen_timeout
        )
        match = FINGERPRINT_LINE.match(fingerprint_out.strip())
        if match is None:
            raise AdapterError(
                "TUNNEL_FAILED", "讀不出通道金鑰的指紋", stderr_last_line=_masked_last_line(fingerprint_err)
            )
        return {"keyType": key_type, "fingerprint": match.group(1), "created": created}

    async def open_tunnel(self, session_name: str, key_path: str, local_port: int) -> dict[str, Any]:
        """建立本機轉發(openTunnel),等到遠端 Ollama 透過它回應 `/api/version` 才回成功。"""
        # 重連時同名的舊轉發可能還在(ssh 被殺、ProxyCommand 還活著占著 stderr):先整組收掉並回收,
        # 否則舊的 ssh 留成 defunct、ProxyCommand 沒人收(實跑 US1-TUN-10)
        previous = self._forwards.pop(session_name, None)
        if previous is not None:
            await self._end_group(previous)
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                ssh_argv(session_name, key_path, local_port),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=True,  # 自成一個 process group,closeTunnel 對整個 group 送訊號
            )
        except FileNotFoundError:
            raise AdapterError("TUNNEL_NOT_INSTALLED", "找不到 ssh 指令") from None
        forward = _Forward(process=process, local_port=local_port)
        threading.Thread(target=forward.read_stderr, name=f"tunnel-stderr-{session_name}", daemon=True).start()
        self._forwards[session_name] = forward

        base_url = base_url_of(local_port)
        deadline = started + self._ready_deadline
        async with httpx.AsyncClient(base_url=base_url, timeout=self._probe_timeout) as client:
            remote_refused = False
            while time.monotonic() < deadline:
                version, closed_without_reply = await _probe_unless(client, forward.attention)
                # 連上了卻沒有任何回應就被關閉,同時 stderr 有 `open failed: connect failed`:遠端 11434 沒有在聽
                remote_refused = closed_without_reply and forward.saw_remote_refused()
                if forward.creating_runtime.is_set():
                    await self._end_group(forward)
                    raise AdapterError("TUNNEL_NOT_FOUND", "要連的執行環境已經不在,Colab 正要另開一台(已停止)")
                if forward.process.poll() is not None or forward.stderr_closed.is_set():
                    raise await self._ended(forward)
                if version is not None:
                    return {
                        "sessionName": session_name,
                        "baseUrl": base_url,
                        "remoteOllamaVersion": version,
                        "connectedAt": datetime.now(UTC).isoformat(),
                        "elapsedMs": int((time.monotonic() - started) * 1000),
                    }
                await asyncio.sleep(self._ready_interval)
        await self._end_group(forward)
        if remote_refused:
            raise AdapterError("TUNNEL_REMOTE_REFUSED", FAILURE_MESSAGES["TUNNEL_REMOTE_REFUSED"])
        raise AdapterError("TUNNEL_TIMEOUT", "通道在期限內沒有就緒")

    async def _ended(self, forward: _Forward) -> AdapterError:
        """ssh 已經結束:對整個 process group 收尾(留下的 ProxyCommand 一起),並依 stderr 判定代碼(exit code 不可信,不看)。"""
        # 真的 ProxyCommand 繼承 ssh 的 stderr,活著時 stderr 不會關;等待改成非同步輪詢,不卡事件迴圈
        drain_until = time.monotonic() + STDERR_DRAIN
        while not forward.stderr_closed.is_set() and time.monotonic() < drain_until:
            await asyncio.sleep(EXIT_POLL)
        await self._end_group(forward)
        code = classify_stderr(forward.stderr_lines)
        if code is None:
            relevant = relevant_lines(forward.stderr_lines)
            masked = mask_secrets(relevant[-1]) if relevant else None
            return AdapterError("TUNNEL_FAILED", FAILURE_MESSAGES["TUNNEL_FAILED"], stderr_last_line=masked)
        return AdapterError(code, FAILURE_MESSAGES[code])

    async def close_tunnel(self, session_name: str) -> dict[str, Any]:
        """關閉轉發(closeTunnel):結束 ssh 的整個 process group(含 ProxyCommand),不結束 Colab 的執行環境。冪等。"""
        forward = self._forwards.pop(session_name, None)
        if forward is None:
            return {"sessionName": session_name, "wasRunning": False, "forced": False}
        was_running = forward.process.poll() is None
        gone, forced = await self._terminate(forward)
        if not gone:
            raise AdapterError("TUNNEL_FAILED", "SSH 通道的行程關不掉")
        if not await _port_closed(forward.local_port, self._kill_wait):
            raise AdapterError("TUNNEL_FAILED", "本機轉發的 port 仍在聽,可能被別的行程占用")
        return {"sessionName": session_name, "wasRunning": was_running, "forced": forced}

    async def cleanup_residual(self, key_path: str) -> dict[str, Any]:
        """清除殘留(closeTunnel 的第四行):結束上一個後端行程留下的本系統轉發;只比對本系統自己的命令列。"""
        pattern = re.compile(
            rf"^ssh -F none -N -i {re.escape(key_path)} .*ProxyCommand=colab ssh --proxy-mode -s cgb-"
        )
        residual = [pid for pid, cmdline in _command_lines() if pattern.search(cmdline)]
        for pid in residual:
            _signal_process(pid, signal.SIGTERM)
        for pid in residual:
            if not await _process_gone(pid, self._term_wait):
                _signal_process(pid, signal.SIGKILL)
                await _process_gone(pid, self._kill_wait)
        return {"killed": len(residual)}

    async def check_health(self, session_name: str) -> dict[str, Any]:
        """健康檢查(checkTunnelHealth):ssh 還在,而且遠端 Ollama 透過轉發回應 `/api/version`。只回報,不重連。"""
        forward = self._forwards.get(session_name)
        if forward is None:
            raise AdapterError("TUNNEL_NOT_FOUND", "本系統沒有這個工作階段的通道")
        if forward.process.poll() is not None:
            raise await self._ended(forward)

        started = time.monotonic()
        base_url = base_url_of(forward.local_port)
        async with httpx.AsyncClient(base_url=base_url, timeout=self._probe_timeout) as client:
            try:
                response = await client.get("/api/version")
            except httpx.TimeoutException:
                raise AdapterError("TUNNEL_TIMEOUT", FAILURE_MESSAGES["TUNNEL_TIMEOUT"]) from None
            except httpx.ConnectError:
                raise AdapterError("TUNNEL_UNREACHABLE", FAILURE_MESSAGES["TUNNEL_UNREACHABLE"]) from None
            except (httpx.RemoteProtocolError, httpx.ReadError):
                if forward.saw_remote_refused():
                    raise AdapterError("TUNNEL_REMOTE_REFUSED", FAILURE_MESSAGES["TUNNEL_REMOTE_REFUSED"]) from None
                raise AdapterError("TUNNEL_UNREACHABLE", FAILURE_MESSAGES["TUNNEL_UNREACHABLE"]) from None
        version = _version_of(response)
        if version is None:
            raise AdapterError("TUNNEL_BAD_RESPONSE", "模型服務的回應無法解析")
        return {
            "sessionName": session_name,
            "healthy": True,
            "remoteOllamaVersion": version,
            "checkedAt": datetime.now(UTC).isoformat(),
            "latencyMs": int((time.monotonic() - started) * 1000),
        }

    async def _end_group(self, forward: _Forward) -> bool:
        """失敗收尾(Q141):和 closeTunnel 同一套流程;收尾失敗不改變回報的代碼,只記一筆日誌。回傳是否已全部結束。"""
        gone, _ = await self._terminate(forward)
        if not gone:
            logger.warning("SSH 通道的行程在 SIGKILL 之後仍在(process group %d)", forward.process.pid)
        return gone

    async def _terminate(self, forward: _Forward) -> tuple[bool, bool]:
        """整個 process group 送 SIGTERM、等待、還在就 SIGKILL、再等待,並回收 ssh;等待都是非同步的。

        回傳(是否已全部結束, 是否動用到 SIGKILL)。
        """
        pgid = forward.process.pid
        _signal_group(pgid, signal.SIGTERM)
        if await _group_gone(forward.process, self._term_wait):
            return True, False
        _signal_group(pgid, signal.SIGKILL)
        return await _group_gone(forward.process, self._kill_wait), True


async def _probe_unless(client: httpx.AsyncClient, alarm: threading.Event) -> tuple[str | None, bool]:
    """打一次 `/api/version`;等回應的期間 `alarm` 被設起來就放棄這次(回沒有版本)。"""
    probe = asyncio.ensure_future(_probe_version(client))
    while not probe.done():
        if alarm.is_set():
            probe.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await probe
            return None, False
        await asyncio.wait({probe}, timeout=ALARM_POLL)
    return probe.result()


async def _probe_version(client: httpx.AsyncClient) -> tuple[str | None, bool]:
    """打一次 `/api/version`。

    回傳(版本, 是否連上了卻沒有任何回應就被關閉);回 200 且本文是含 `version` 字串的 JSON 才有版本。
    """
    try:
        response = await client.get("/api/version")
    except (httpx.RemoteProtocolError, httpx.ReadError):
        return None, True
    except httpx.HTTPError:
        return None, False
    return _version_of(response), False


def _version_of(response: httpx.Response) -> str | None:
    """回 200 且本文是含 `version` 字串的 JSON 才回版本。"""
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    version = body.get("version") if isinstance(body, dict) else None
    return version if isinstance(version, str) else None


def _signal_group(pgid: int, signum: int) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pgid, signum)


async def _group_gone(process: subprocess.Popen[bytes], timeout: float) -> bool:
    """等 ssh 結束並回收(不留殭屍),而且它的 process group 裡已經沒有任何行程;逾時回 False。"""
    deadline = time.monotonic() + timeout
    while True:
        process.poll()  # 回收 ssh
        if process.returncode is not None:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return True
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(EXIT_POLL)


async def _port_closed(port: int, timeout: float) -> bool:
    """等 `127.0.0.1:<port>` 沒有人在聽(試連被拒);逾時回 False。"""
    deadline = time.monotonic() + timeout
    while True:
        try:
            _, writer = await asyncio.open_connection(LOOPBACK, port)
        except OSError:
            return True
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(EXIT_POLL)


def _command_lines() -> list[tuple[int, str]]:
    """主機上每個看得到的行程的命令列(argv 以空白連接),不含自己。"""
    found = []
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            with open(f"/proc/{entry.name}/cmdline", "rb") as f:
                raw = f.read()
        except OSError:
            continue
        argv = raw.rstrip(b"\0").split(b"\0")
        found.append((int(entry.name), " ".join(arg.decode(errors="replace") for arg in argv)))
    return found


def _signal_process(pid: int, signum: int) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signum)


def _is_running(pid: int) -> bool:
    """行程還在而且不是殭屍(殭屍已經結束,只等它的父行程回收)。"""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
            state = f.read().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return False
    return state != "Z"


async def _process_gone(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while _is_running(pid):
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(EXIT_POLL)
    return True
