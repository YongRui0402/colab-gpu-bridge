"""E6 SSH 通道:`Tunnel` 的整合測試(testplan.md § US1-TUN-01~US1-TUN-09)。

接縫:`Tunnel` 的公開方法;`ssh` 是假的執行檔(`tests/fixtures/bin/ssh`,由 `fake_cli` 放到 PATH 前面),
`ssh-keygen` 是真的;金鑰一律放在測試的暫存資料夾,不碰 `~/.ssh`。
"""

import asyncio
import contextlib
import hashlib
import logging
import os
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Awaitable, Iterator
from pathlib import Path
from typing import Any

import pytest

from cgb.adapters.errors import AdapterError
from cgb.adapters.tunnel import Tunnel
from conftest import FAKE_BIN_DIR, FakeCli
from fakes import DisconnectReply, FakeOllamaServer, Gate, HangReply, JsonReply

NO_ERROR = "沒有失敗"
ED25519_PUBLIC_KEY_PREFIX = "AAAAC3NzaC1lZDI1NTE5"


async def code_of(call: Awaitable[Any]) -> str:
    """執行呼叫,回傳丟出的 `AdapterError` 代碼;沒有丟錯就回 `NO_ERROR`,讓斷言比對值而不是靠例外。"""
    try:
        await call
    except AdapterError as error:
        return error.code
    return NO_ERROR


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_rsa_key(path: Path) -> None:
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "rsa", "-b", "2048", "-N", "", "-C", "cgb-test-rsa", "-f", str(path)],
        check=True,
        stdin=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------- US1-TUN-01 ensure_key


async def test_ensure_key_creates_ed25519_key_readable_only_by_owner(tmp_path: Path) -> None:
    # Arrange
    key_path = tmp_path / "ssh" / "id_ed25519"
    key_path.parent.mkdir()

    # Act
    key = await Tunnel().ensure_key(str(key_path))

    # Assert
    assert key_path.exists()
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert key["keyType"] == "ssh-ed25519"
    assert key["fingerprint"].startswith("SHA256:")
    assert key["created"] is True


async def test_ensure_key_result_does_not_contain_public_key_text(tmp_path: Path) -> None:
    # Arrange
    key_path = tmp_path / "id_ed25519"

    # Act
    key = await Tunnel().ensure_key(str(key_path))

    # Assert:ed25519 公鑰本文的 base64 一律以這串開頭(`ssh-ed25519` 的長度與名稱編碼)
    assert ED25519_PUBLIC_KEY_PREFIX not in repr(key)


async def test_ensure_key_rejects_existing_rsa_key(tmp_path: Path) -> None:
    # Arrange
    key_path = tmp_path / "id_user"
    make_rsa_key(key_path)

    # Act
    code = await code_of(Tunnel().ensure_key(str(key_path)))

    # Assert
    assert code == "TUNNEL_KEY_REJECTED"


async def test_ensure_key_leaves_existing_key_file_untouched(tmp_path: Path) -> None:
    # Arrange
    key_path = tmp_path / "id_user"
    make_rsa_key(key_path)
    before = sha256_of(key_path)

    # Act
    await code_of(Tunnel().ensure_key(str(key_path)))

    # Assert
    assert sha256_of(key_path) == before


# ---------------------------------------------------------------- 假 ssh 的劇本與收尾

SESSION = "cgb-test-0001"
REMOTE_VERSION = "0.40.15"


def spec_ssh_argv(key_path: str, session_name: str, local_port: int) -> list[str]:
    """`contracts/tunnel.openapi.yaml` § `paths./tunnels.post` 的 `x-argv`(去掉程式名),逐字代入。"""
    return [
        "-F", "none", "-N", "-i", key_path,
        "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", f"ProxyCommand=colab ssh --proxy-mode -s {session_name} --identity {key_path}",
        "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3", "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
        "-L", f"127.0.0.1:{local_port}:127.0.0.1:11434", "root@colab-runtime",
    ]  # fmt: skip


def ssh_argv(fake_cli: FakeCli) -> list[str]:
    """假 ssh 第一次被呼叫時收到的 argv;沒有被呼叫就是空的。"""
    calls = fake_cli.calls("ssh")
    return calls[0]["argv"] if calls else []


def option_values(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg == "-o"]


def has_pair(argv: list[str], flag: str, value: str) -> bool:
    return any(argv[i] == flag and argv[i + 1] == value for i in range(len(argv) - 1))


@pytest.fixture
def key_path(tmp_path: Path) -> str:
    """測試用的 ed25519 金鑰(暫存資料夾,真的 ssh-keygen)。"""
    path = tmp_path / "ssh" / "id_ed25519"
    path.parent.mkdir()
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "cgb-test", "-f", str(path)],
        check=True,
        stdin=subprocess.DEVNULL,
    )
    return str(path)


@pytest.fixture
def fake_ssh(fake_cli: FakeCli) -> Iterator[FakeCli]:
    """假 ssh 的劇本;測試結束時殺掉每一個假 ssh 與它分出的子行程(以紀錄裡的 pid,不比對命令列)。"""
    yield fake_cli
    for record in fake_cli.calls("ssh"):
        pids = [record["pid"], record.get("child_pid")]
        if record["pgid"] == record["pid"]:  # 自成一個 process group 時才對整個 group 送;否則可能是 pytest 自己的 group
            with contextlib.suppress(ProcessLookupError):
                os.killpg(record["pgid"], signal.SIGKILL)
        for pid in pids:
            if pid:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)


def script_ssh(fake_cli: FakeCli, argv: list[str], entry: dict[str, Any]) -> None:
    fake_cli.script({"ssh": {shlex.join(argv): entry}})


def _alive(pid: int) -> bool:
    """行程還在而且不是殭屍。"""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return False
    return state != "Z"


class ForwardStandIn:
    """代表本機轉發的另一端:假 ssh 不會真的轉發,所以 `localPort` 就是假 Ollama 伺服器的 port。

    和真的轉發一樣,假 ssh 啟動之前請求停著不回(伺服器在,但還沒有「通」);假 ssh 啟動後才照劇本回;
    假 ssh 結束後伺服器關閉,`localPort` 不再有人聽。
    """

    WATCH_SECONDS = 0.01

    def __init__(self, server: FakeOllamaServer, fake_cli: FakeCli) -> None:
        self.server = server
        self._fake_cli = fake_cli
        self._ssh_started = Gate()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, name="forward-stand-in", daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return self.server.port

    def reply_version(self, reply: Any, times: int | None = None) -> None:
        self.server.add("GET", "/api/version", HangReply(release=self._ssh_started, after=reply), times=times)

    def _watch(self) -> None:
        while not self._stop.wait(self.WATCH_SECONDS):
            calls = self._fake_cli.calls("ssh")
            if not calls:
                continue
            self._ssh_started.release()
            if not _alive(calls[-1]["pid"]):
                self.server.stop()
                return

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


@pytest.fixture
def forward(ollama_server: FakeOllamaServer, fake_ssh: FakeCli) -> Iterator[ForwardStandIn]:
    stand_in = ForwardStandIn(ollama_server, fake_ssh)
    try:
        yield stand_in
    finally:
        stand_in.close()


def real_ssh() -> str:
    """真的 OpenSSH(PATH 去掉假執行檔的資料夾)。"""
    path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if Path(p) != FAKE_BIN_DIR)
    found = shutil.which("ssh", path=path)
    assert found is not None, "主機上找不到真的 ssh"
    return found


# ---------------------------------------------------------------- US1-TUN-02 open_tunnel 的命令列與就緒


async def open_ready_tunnel(fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str) -> dict[str, Any]:
    port = forward.port
    forward.reply_version(JsonReply({"version": REMOTE_VERSION}))
    script_ssh(fake_ssh, spec_ssh_argv(key_path, SESSION, port), {"daemon": True})
    return await Tunnel().open_tunnel(SESSION, key_path, port)


async def test_open_tunnel_runs_ssh_without_config_files_and_never_prompting(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Act
    await code_of(open_ready_tunnel(fake_ssh, forward, key_path))

    # Assert
    argv = ssh_argv(fake_ssh)
    assert has_pair(argv, "-F", "none")
    assert "-N" in argv
    assert {
        "BatchMode=yes",
        "IdentitiesOnly=yes",
        "ExitOnForwardFailure=yes",
        "ServerAliveInterval=15",
        "ServerAliveCountMax=3",
    } <= set(option_values(argv))


async def test_open_tunnel_proxy_command_attaches_to_the_named_session_without_creating_or_removing_it(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Act
    await code_of(open_ready_tunnel(fake_ssh, forward, key_path))

    # Assert
    proxy = [v for v in option_values(ssh_argv(fake_ssh)) if v.startswith("ProxyCommand=")]
    assert proxy == [f"ProxyCommand=colab ssh --proxy-mode -s cgb-test-0001 --identity {key_path}"]
    assert not any(flag in proxy[0].split() for flag in ("--gpu", "--tpu", "--high-mem", "--rm"))


async def test_open_tunnel_forwards_only_on_loopback(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Act
    await code_of(open_ready_tunnel(fake_ssh, forward, key_path))

    # Assert
    argv = ssh_argv(fake_ssh)
    assert has_pair(argv, "-L", f"127.0.0.1:{forward.port}:127.0.0.1:11434")
    assert "-g" not in argv


async def test_open_tunnel_succeeds_only_after_remote_ollama_answers_version(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Act
    tunnel = await open_ready_tunnel(fake_ssh, forward, key_path)

    # Assert
    assert forward.server.requests_to("GET", "/api/version")
    assert tunnel["sessionName"] == "cgb-test-0001"
    assert tunnel["remoteOllamaVersion"] == "0.40.15"
    assert tunnel["baseUrl"] == f"http://127.0.0.1:{forward.port}"


async def test_open_tunnel_arguments_are_understood_by_openssh_as_specified(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Arrange
    await code_of(open_ready_tunnel(fake_ssh, forward, key_path))
    argv = ["-G" if arg == "-N" else arg for arg in ssh_argv(fake_ssh)]

    # Act:`ssh -G` 只印解析後的設定,不連線
    result = subprocess.run(
        [real_ssh(), *argv], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10, check=False
    )

    # Assert
    config = {}
    for line in result.stdout.splitlines():
        name, _, value = line.partition(" ")
        config.setdefault(name, value)
    port = forward.port
    assert {
        "localforward": config.get("localforward"),
        "proxycommand": config.get("proxycommand"),
        "batchmode": config.get("batchmode"),
        "identitiesonly": config.get("identitiesonly"),
        "exitonforwardfailure": config.get("exitonforwardfailure"),
        "serveraliveinterval": config.get("serveraliveinterval"),
        "serveralivecountmax": config.get("serveralivecountmax"),
    } == {
        "localforward": f"[127.0.0.1]:{port} [127.0.0.1]:11434",
        "proxycommand": f"colab ssh --proxy-mode -s cgb-test-0001 --identity {key_path}",
        "batchmode": "yes",
        "identitiesonly": "yes",
        "exitonforwardfailure": "yes",
        "serveraliveinterval": "15",
        "serveralivecountmax": "3",
    }


# ---------------------------------------------------------------- US1-TUN-03 `colab ssh` 意外開新執行環境


def process_group(pgid: int) -> set[int]:
    """process group `pgid` 裡還活著(不是殭屍)的行程。"""
    members = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if fields[0] != "Z" and int(fields[2]) == pgid:
            members.add(int(entry.name))
    return members


def still_running(record: dict[str, Any]) -> set[int]:
    """假 ssh 這次啟動的行程(它自己、它分出的子行程,以及它的 process group)中還活著的。"""
    alive = {pid for pid in (record["pid"], record.get("child_pid")) if pid and _alive(pid)}
    if record["pgid"] == record["pid"]:
        alive |= process_group(record["pgid"])
    return alive


async def wait_until_stopped(record: dict[str, Any], deadline: float) -> set[int]:
    """等到行程都結束或過了 `deadline`(time.time()),回傳那時還活著的。"""
    while (alive := still_running(record)) and time.time() < deadline:
        await asyncio.sleep(0.01)
    return alive


CREATING_RUNTIME = "[colab] Creating runtime 'cgb-test-0001'...\n"


async def open_with_creating_runtime(fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str) -> str:
    # 不替 /api/version 寫劇本:新的一台要好幾分鐘才開好,這段時間轉發的另一端不會回版本
    script_ssh(
        fake_ssh,
        spec_ssh_argv(key_path, SESSION, forward.port),
        {"stderr": CREATING_RUNTIME, "daemon": True, "spawn_child": True},
    )
    return await code_of(Tunnel().open_tunnel(SESSION, key_path, forward.port))


async def test_open_tunnel_reports_not_found_when_colab_ssh_starts_creating_a_runtime(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Act
    code = await open_with_creating_runtime(fake_ssh, forward, key_path)

    # Assert
    assert code == "TUNNEL_NOT_FOUND"


async def test_open_tunnel_ends_whole_ssh_process_group_within_a_second_of_creating_runtime(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Act
    await open_with_creating_runtime(fake_ssh, forward, key_path)

    # Assert:假 ssh 一啟動就印這行,所以從它的啟動時間起算 1 秒
    record = fake_ssh.calls("ssh")[0]
    assert await wait_until_stopped(record, deadline=record["time"] + 1.0) == set()


# ---------------------------------------------------------------- US1-TUN-04 stderr 對應代碼

# 經 ProxyCommand 連線時,`colab ssh` 結束後 OpenSSH 接著印的兩行;排在 `[colab] ` 行的後面,比對要以 `[colab] ` 那一行為準
PROXY_GONE = "kex_exchange_identification: Connection closed by remote host\nConnection closed by UNKNOWN port 65535\n"

# `Error.x-stderr-patterns` 的每一條比對字樣與它對應的代碼(照規格逐條抄寫,不從實作取)
STDERR_CASES = [
    ("[colab] Creating runtime 'cgb-test-0001'...\n", "TUNNEL_NOT_FOUND"),
    ("[colab] Endpoint not found (HTTP 404)\n" + PROXY_GONE, "TUNNEL_NOT_FOUND"),
    ("[colab] session 'cgb-test-0001' not found\n" + PROXY_GONE, "TUNNEL_NOT_FOUND"),
    ("[colab] Server rejected the public key (HTTP 400): unsupported key type\n" + PROXY_GONE, "TUNNEL_KEY_REJECTED"),
    ("[colab] no SSH public key found in ~/.ssh\n" + PROXY_GONE, "TUNNEL_KEY_REJECTED"),
    ("[colab] --identity /data/ssh/id_ed25519 does not exist\n" + PROXY_GONE, "TUNNEL_KEY_REJECTED"),
    ("[colab] failed to derive public key from /data/ssh/id_ed25519\n" + PROXY_GONE, "TUNNEL_KEY_REJECTED"),
    ("root@colab-runtime: Permission denied (publickey).\n", "TUNNEL_KEY_REJECTED"),
    ("[colab] Authentication failed (HTTP 401)\n" + PROXY_GONE, "TUNNEL_TOKEN_REJECTED"),
    ("[colab] Forbidden (HTTP 403)\n" + PROXY_GONE, "TUNNEL_TOKEN_REJECTED"),
    ("[colab] Already-active SSH session (HTTP 429)\n" + PROXY_GONE, "TUNNEL_ALREADY_CONNECTED"),
    ("[colab] Bad gateway (HTTP 502)\n" + PROXY_GONE, "TUNNEL_SERVER_ERROR"),
    ("[colab] WebSocket connection failed: [Errno -3] Temporary failure in name resolution\n" + PROXY_GONE,
     "TUNNEL_UNREACHABLE"),
    ("[colab] WebSocket upgrade failed without an HTTP status\n" + PROXY_GONE, "TUNNEL_UNREACHABLE"),
    ("bind [127.0.0.1]:11435: Address already in use\n"
     "channel_setup_fwd_listener_tcpip: cannot listen to port: 11435\n"
     "Could not request local forwarding.\n", "TUNNEL_PORT_IN_USE"),
    ("Timeout, server colab-runtime not responding.\n", "TUNNEL_TIMEOUT"),
    ("channel 2: open failed: connect failed: Connection refused\n", "TUNNEL_REMOTE_REFUSED"),
    ("/bin/sh: 1: exec: colab: not found\n" + PROXY_GONE, "TUNNEL_NOT_INSTALLED"),
    ("sh: line 1: exec: colab: No such file or directory\n" + PROXY_GONE, "TUNNEL_NOT_INSTALLED"),
    (PROXY_GONE, "TUNNEL_UNREACHABLE"),
    ("Connection closed by UNKNOWN port 65535\n", "TUNNEL_UNREACHABLE"),
    ("client_loop: send disconnect: Broken pipe\n", "TUNNEL_UNREACHABLE"),
]  # fmt: skip
KNOWN_HOSTS_WARNING = "Warning: Permanently added 'colab-runtime' (ED25519) to the list of known hosts.\n"
SHORT_READY_DEADLINE = 3.0  # 斷言的是 ssh 結束後的判定,不必等正式的 30 秒


@pytest.mark.parametrize(
    ("stderr", "expected"),
    STDERR_CASES,
    ids=[f"{i:02d}-{code}" for i, (_, code) in enumerate(STDERR_CASES)],
)
async def test_open_tunnel_reports_the_code_of_the_stderr_pattern_when_ssh_exits(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str, stderr: str, expected: str
) -> None:
    # Arrange
    script_ssh(fake_ssh, spec_ssh_argv(key_path, SESSION, forward.port), {"stderr": stderr, "exit": 255})

    # Act
    code = await code_of(Tunnel(ready_deadline=SHORT_READY_DEADLINE).open_tunnel(SESSION, key_path, forward.port))

    # Assert
    assert code == expected


async def test_open_tunnel_does_not_treat_known_hosts_warning_as_failure(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Arrange
    forward.reply_version(JsonReply({"version": REMOTE_VERSION}))
    script_ssh(fake_ssh, spec_ssh_argv(key_path, SESSION, forward.port), {"stderr": KNOWN_HOSTS_WARNING, "daemon": True})

    # Act
    code = await code_of(Tunnel(ready_deadline=SHORT_READY_DEADLINE).open_tunnel(SESSION, key_path, forward.port))

    # Assert
    assert code == NO_ERROR


# ---------------------------------------------------------------- US1-TUN-05 就緒期限

INJECTED_READY_DEADLINE = 1.0


def free_port() -> int:
    """一個現在沒有人聽的 127.0.0.1 port(連上去會被拒絕)。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def open_timed(fake_ssh: FakeCli, key_path: str, port: int, entry: dict[str, Any]) -> tuple[str, float]:
    script_ssh(fake_ssh, spec_ssh_argv(key_path, SESSION, port), entry)
    started = time.monotonic()
    code = await code_of(Tunnel(ready_deadline=INJECTED_READY_DEADLINE).open_tunnel(SESSION, key_path, port))
    return code, time.monotonic() - started


async def open_while_local_port_refuses(fake_ssh: FakeCli, key_path: str) -> tuple[str, float]:
    """情況 A:假 ssh 常駐,但 `localPort` 一直沒有人聽。"""
    return await open_timed(fake_ssh, key_path, free_port(), {"daemon": True})


async def open_while_remote_ollama_refuses(fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str) -> tuple[str, float]:
    """情況 B:通道是通的,但遠端 11434 拒絕,ssh 印 `open failed` 並立即關掉轉發的那條連線。"""
    forward.reply_version(DisconnectReply())
    return await open_timed(
        fake_ssh,
        key_path,
        forward.port,
        {"stderr": "channel 2: open failed: connect failed: Connection refused\n", "daemon": True},
    )


async def test_open_tunnel_keeps_waiting_until_deadline_then_times_out_when_local_port_refuses(
    fake_ssh: FakeCli, key_path: str
) -> None:
    # Act
    code, elapsed = await open_while_local_port_refuses(fake_ssh, key_path)

    # Assert
    assert code == "TUNNEL_TIMEOUT"
    assert 1.0 <= elapsed <= 1.5


async def test_open_tunnel_keeps_waiting_until_deadline_then_reports_remote_refused(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Act
    code, elapsed = await open_while_remote_ollama_refuses(fake_ssh, forward, key_path)

    # Assert
    assert code == "TUNNEL_REMOTE_REFUSED"
    assert 1.0 <= elapsed <= 1.5


async def test_open_tunnel_stops_ssh_when_deadline_passes_with_local_port_refusing(
    fake_ssh: FakeCli, key_path: str
) -> None:
    # Act
    await open_while_local_port_refuses(fake_ssh, key_path)

    # Assert
    assert still_running(fake_ssh.calls("ssh")[0]) == set()


async def test_open_tunnel_stops_ssh_when_deadline_passes_with_remote_ollama_refusing(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Act
    await open_while_remote_ollama_refuses(fake_ssh, forward, key_path)

    # Assert
    assert still_running(fake_ssh.calls("ssh")[0]) == set()


# ---------------------------------------------------------------- US1-TUN-06 check_health

INJECTED_PROBE_TIMEOUT = 0.3


async def open_then(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str, entry: dict[str, Any], later_reply: Any = None
) -> Tunnel:
    """建立通道(就緒判定那一次回版本),之後的 `/api/version` 改回 `later_reply`(None 表示照樣回版本)。"""
    if later_reply is None:
        forward.reply_version(JsonReply({"version": REMOTE_VERSION}))
    else:
        forward.reply_version(JsonReply({"version": REMOTE_VERSION}), times=1)
        forward.server.add("GET", "/api/version", later_reply)
    script_ssh(fake_ssh, spec_ssh_argv(key_path, SESSION, forward.port), entry)
    tunnel = Tunnel(probe_timeout=INJECTED_PROBE_TIMEOUT)
    await tunnel.open_tunnel(SESSION, key_path, forward.port)
    return tunnel


async def test_check_health_reports_healthy_when_remote_ollama_answers_version(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Arrange
    tunnel = await open_then(fake_ssh, forward, key_path, {"daemon": True})

    # Act
    health = await tunnel.check_health(SESSION)

    # Assert
    assert {key: health.get(key) for key in ("sessionName", "healthy", "remoteOllamaVersion")} == {
        "sessionName": "cgb-test-0001",
        "healthy": True,
        "remoteOllamaVersion": "0.40.15",
    }


async def test_check_health_reports_timeout_after_ssh_keepalive_gave_up(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Arrange
    entry = {"steps": [{"sleep": 0.5}, {"stderr": "Timeout, server colab-runtime not responding.\n"}], "exit": 255}
    tunnel = await open_then(fake_ssh, forward, key_path, entry)
    assert await wait_until_stopped(fake_ssh.calls("ssh")[0], deadline=time.time() + 5) == set()

    # Act
    code = await code_of(tunnel.check_health(SESSION))

    # Assert
    assert code == "TUNNEL_TIMEOUT"


async def test_check_health_reports_timeout_when_remote_ollama_does_not_answer_in_time(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Arrange
    tunnel = await open_then(fake_ssh, forward, key_path, {"daemon": True}, later_reply=HangReply())

    # Act
    code = await code_of(tunnel.check_health(SESSION))

    # Assert
    assert code == "TUNNEL_TIMEOUT"


async def test_check_health_reports_bad_response_when_version_is_not_json(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Arrange
    html = JsonReply(b"<html><body>colab</body></html>", headers={"Content-Type": "text/html"})
    tunnel = await open_then(fake_ssh, forward, key_path, {"daemon": True}, later_reply=html)

    # Act
    code = await code_of(tunnel.check_health(SESSION))

    # Assert
    assert code == "TUNNEL_BAD_RESPONSE"


# ---------------------------------------------------------------- US1-TUN-07 close_tunnel

INJECTED_TERM_WAIT = 0.5


def port_is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


async def open_with_stubborn_proxy_command(fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str) -> Tunnel:
    """建立通道;假 ssh 分出代表 ProxyCommand 的子行程,兩者都忽略 SIGTERM。

    假執行檔沒有「忽略 SIGTERM」的劇本欄位,所以啟動的那一刻讓測試行程暫時忽略 SIGTERM:
    忽略的設定會經 fork 與 exec 繼承給假 ssh 與它的子行程,之後立即還原測試行程自己的設定。
    """
    forward.reply_version(JsonReply({"version": REMOTE_VERSION}))
    script_ssh(fake_ssh, spec_ssh_argv(key_path, SESSION, forward.port), {"daemon": True, "spawn_child": True})
    tunnel = Tunnel(term_wait=INJECTED_TERM_WAIT)
    previous = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        await tunnel.open_tunnel(SESSION, key_path, forward.port)
    finally:
        signal.signal(signal.SIGTERM, previous)
    return tunnel


def leftover_processes(record: dict[str, Any]) -> set[int]:
    """假 ssh 與它的子行程中,還看得到的(含殭屍)。"""
    return {pid for pid in (record["pid"], record["child_pid"]) if Path(f"/proc/{pid}").exists()}


async def wait_for_no_leftovers(record: dict[str, Any], timeout: float) -> set[int]:
    deadline = time.monotonic() + timeout
    while (left := leftover_processes(record)) and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    return left


async def test_close_tunnel_returns_once_local_port_is_no_longer_listening(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Arrange
    tunnel = await open_with_stubborn_proxy_command(fake_ssh, forward, key_path)

    # Act
    closed = await tunnel.close_tunnel(SESSION)

    # Assert
    assert closed.get("sessionName") == "cgb-test-0001"
    assert not port_is_listening(forward.port)


async def test_close_tunnel_leaves_no_ssh_proxy_command_or_defunct_process(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Arrange
    tunnel = await open_with_stubborn_proxy_command(fake_ssh, forward, key_path)

    # Act
    await tunnel.close_tunnel(SESSION)

    # Assert:ssh 由後端回收;子行程被殺後由 init 回收,給它一點時間
    assert await wait_for_no_leftovers(fake_ssh.calls("ssh")[0], timeout=1.0) == set()


async def test_close_tunnel_twice_succeeds_both_times(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Arrange
    tunnel = await open_with_stubborn_proxy_command(fake_ssh, forward, key_path)
    await tunnel.close_tunnel(SESSION)

    # Act
    code = await code_of(tunnel.close_tunnel(SESSION))
    again = await tunnel.close_tunnel(SESSION)

    # Assert
    assert code == NO_ERROR
    assert {key: again.get(key) for key in ("sessionName", "wasRunning")} == {
        "sessionName": "cgb-test-0001",
        "wasRunning": False,
    }


# ---------------------------------------------------------------- US1-TUN-08 cleanup_residual

# 啟動後把自己的命令列(/proc/<pid>/cmdline)改寫成 argv[1] 指定的內容,然後常駐。
# 假 ssh 由 python 直譯器執行,命令列開頭是直譯器與腳本路徑,不是 `ssh`;這裡要的是命令列就是 `ssh …` 的行程
_SET_CMDLINE_AND_STAY = r"""
import sys, time
target = sys.argv[1].replace("\x01", "\0").encode()
fields = open("/proc/self/stat").read().rsplit(")", 1)[1].split()
start, end = int(fields[45]), int(fields[46])
with open("/proc/self/mem", "r+b", buffering=0) as mem:
    mem.seek(start)
    mem.write(target + b"\0" * (end - start - len(target)))
print("ready", flush=True)
while True:
    time.sleep(3600)
"""


@pytest.fixture
def process_with_cmdline() -> Iterator[Any]:
    """啟動命令列就是指定 argv 的常駐假行程;測試結束時以 pid 殺掉並回收。"""
    started: list[subprocess.Popen[str]] = []

    def start(argv: list[str]) -> subprocess.Popen[str]:
        target = "\x01".join(argv)
        process = subprocess.Popen(
            [sys.executable, "-c", _SET_CMDLINE_AND_STAY, target, "x" * (len(target) + 16)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            text=True,
        )
        started.append(process)
        assert process.stdout is not None and process.stdout.readline().strip() == "ready"
        cmdline = Path(f"/proc/{process.pid}/cmdline").read_bytes().rstrip(b"\0").split(b"\0")
        assert [part.decode() for part in cmdline] == argv
        return process

    yield start
    for process in started:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        process.wait(timeout=5)


async def test_cleanup_residual_ends_leftover_tunnel_ssh_but_not_other_ssh(
    process_with_cmdline: Any, key_path: str
) -> None:
    # Arrange
    leftover = process_with_cmdline(["ssh", *spec_ssh_argv(key_path, SESSION, 11435)])
    users_own = process_with_cmdline(["ssh", "-N", "user@example"])

    # Act
    await Tunnel().cleanup_residual(key_path)

    # Assert
    assert {"leftover": _alive(leftover.pid), "users_own": _alive(users_own.pid)} == {
        "leftover": False,
        "users_own": True,
    }


# ---------------------------------------------------------------- US1-TUN-09 機密:stderr 遮蔽

FAKE_TOKEN = "cgb-test-fake-token"
FAKE_ENDPOINT = "cgb-test-fake-endpoint"
UNCLASSIFIABLE = (
    "ws error wss://cgb-test-fake-endpoint.example/x?colab-runtime-proxy-token=cgb-test-fake-token&a=1 refused\n"
)


async def open_with_unclassifiable_stderr(fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str) -> AdapterError:
    script_ssh(fake_ssh, spec_ssh_argv(key_path, SESSION, forward.port), {"stderr": UNCLASSIFIABLE, "exit": 255})
    try:
        await Tunnel(ready_deadline=SHORT_READY_DEADLINE).open_tunnel(SESSION, key_path, forward.port)
    except AdapterError as error:
        return error
    return AdapterError(NO_ERROR, NO_ERROR)


async def test_open_tunnel_reports_failed_for_unclassifiable_stderr(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Act
    error = await open_with_unclassifiable_stderr(fake_ssh, forward, key_path)

    # Assert
    assert error.code == "TUNNEL_FAILED"


async def test_open_tunnel_failure_stderr_line_hides_proxy_token(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Act
    error = await open_with_unclassifiable_stderr(fake_ssh, forward, key_path)

    # Assert
    assert error.stderr_last_line is not None
    assert FAKE_TOKEN not in error.stderr_last_line


async def test_open_tunnel_failure_stderr_line_hides_runtime_endpoint(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str
) -> None:
    # Act
    error = await open_with_unclassifiable_stderr(fake_ssh, forward, key_path)

    # Assert
    assert error.stderr_last_line is not None
    assert FAKE_ENDPOINT not in error.stderr_last_line


async def test_open_tunnel_failure_logs_never_contain_proxy_token(
    fake_ssh: FakeCli, forward: ForwardStandIn, key_path: str, caplog: pytest.LogCaptureFixture
) -> None:
    # Arrange
    caplog.set_level(logging.DEBUG)

    # Act
    await open_with_unclassifiable_stderr(fake_ssh, forward, key_path)

    # Assert
    assert FAKE_TOKEN not in caplog.text
