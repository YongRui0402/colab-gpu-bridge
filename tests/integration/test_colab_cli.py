"""E5 Colab CLI 轉接層(testplan.md § 2.2;`contracts/colab-cli.openapi.yaml`)。

接縫:`ColabControl` 的方法;`colab` 是 `tests/fixtures/bin/colab` 假執行檔(由 `fake_cli` fixture 放上 `PATH`)。
"""

import asyncio
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import pytest

from cgb.adapters.colab_cli import CliTimeouts, ColabControl
from cgb.adapters.errors import AdapterError


async def failure_of(call):
    """執行呼叫並交回它丟出的例外(沒有丟就是 None),讓「丟了別的例外」也成為斷言失敗而不是測試錯誤。"""
    try:
        await call
    except Exception as error:  # noqa: BLE001 - 要看到的就是任何例外
        return error
    return None


async def failure_of_or_result(call):
    """執行呼叫並交回結果;丟出例外時交回那個例外,讓「回了錯誤」也成為斷言失敗。"""
    try:
        return await call
    except Exception as error:  # noqa: BLE001
        return error


@pytest.fixture(autouse=True)
def kill_leftover_fake_children(fake_cli):
    """測試結束後,把假 `colab` 分出、仍活著的子行程清掉(紅燈時被測程式沒清,也不讓它留在桌機上)。"""
    yield
    for call in fake_cli.calls("colab"):
        for pid in (call.get("child_pid"), call["pid"]):
            if pid is not None:
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass


def code_of(error):
    return error.code if isinstance(error, AdapterError) else repr(error)


# ---------------------------------------------------------------- US1-CLI-01


async def test_supported_cli_version_is_reported(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"version": {"stdout": "Version: 0.7.5\n"}}})

    # Act
    result = await ColabControl().get_cli_version()

    # Assert
    assert result == {"version": "0.7.5"}


async def test_other_cli_version_is_unsupported(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"version": {"stdout": "Version: 0.7.6\n"}}})

    # Act
    with pytest.raises(AdapterError) as caught:
        await ColabControl().get_cli_version()

    # Assert
    assert caught.value.code == "COLAB_UNSUPPORTED_VERSION"


# ---------------------------------------------------------------- US1-CLI-02


async def test_missing_cli_is_reported_as_not_installed(fake_cli, tmp_path, monkeypatch):
    # Arrange
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    # Act
    error = await failure_of(ColabControl().get_cli_version())

    # Assert
    assert code_of(error) == "COLAB_NOT_INSTALLED"


# ---------------------------------------------------------------- US1-CLI-03

FAKE_ENDPOINT = "https://cgb-test-fake-endpoint.example"
SESSIONS_WITH_NOTICES = (
    "[colab] A new version of colab-cli is available: 0.7.6 (you have 0.7.5).\n"
    "\n"
    "[colab] Pruned 1 stale local session(s).\n"
    f"[cgb-test-0001] {FAKE_ENDPOINT} | Hardware: T4 | Shape: Standard | Variant: GPU\n"
    f"[?] {FAKE_ENDPOINT} | Hardware: T4 | Shape: High-RAM | Variant: GPU\n"
)


async def test_session_list_skips_colab_notices_and_blank_lines(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"sessions": {"stdout": SESSIONS_WITH_NOTICES}}})

    # Act
    result = await ColabControl().list_sessions()

    # Assert
    assert [(s["name"], s["hardware"], s["shape"]) for s in result["named"]] == [("cgb-test-0001", "T4", "Standard")]
    assert [s["hardware"] for s in result["unnamed"]] == ["T4"]


async def test_session_list_does_not_contain_endpoint(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"sessions": {"stdout": SESSIONS_WITH_NOTICES}}})

    # Act
    result = await ColabControl().list_sessions()

    # Assert
    assert "cgb-test-fake-endpoint" not in repr(result)


# ---------------------------------------------------------------- US1-CLI-04


async def test_no_active_sessions_is_an_empty_list(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"sessions": {"stdout": "[colab] No active sessions found on server.\n"}}})

    # Act
    result = await failure_of_or_result(ColabControl().list_sessions())

    # Assert
    assert result == {"named": [], "unnamed": []}


# ---------------------------------------------------------------- US1-CLI-05


async def test_session_line_in_unknown_format_is_bad_response(fake_cli):
    # Arrange
    stdout = (
        f"[cgb-test-0001] {FAKE_ENDPOINT} | Hardware: T4 | Shape: Standard | Variant: GPU\n"
        "[cgb-test-0001] x Hardware T4\n"
    )
    fake_cli.script({"colab": {"sessions": {"stdout": stdout}}})

    # Act
    error = await failure_of(ColabControl().list_sessions())

    # Assert
    assert code_of(error) == "COLAB_BAD_RESPONSE"


# ---------------------------------------------------------------- US1-CLI-06

NEW_READY = {"stdout": "[colab] Creating session 'cgb-test-0001'...\n[colab] Session READY.\n"}
SESSIONS_WITH_0001 = {
    "stdout": f"[cgb-test-0001] {FAKE_ENDPOINT} | Hardware: T4 | Shape: Standard | Variant: GPU\n"
}
CREATE_SCRIPT = {
    "colab": {
        "new -s cgb-test-0001 --gpu T4": NEW_READY,
        "new -s cgb-test-0001 --gpu T4 --high-mem": NEW_READY,
        "sessions": SESSIONS_WITH_0001,
    }
}


async def create_0001_twice(fake_cli):
    """以 `high_mem=false` 與 `high_mem=true` 各開一次 `cgb-test-0001`,交回兩次 `colab new` 的紀錄。"""
    fake_cli.script(CREATE_SCRIPT)
    colab = ColabControl()
    await failure_of(colab.create_session(name="cgb-test-0001", gpu="T4", high_mem=False))
    await failure_of(colab.create_session(name="cgb-test-0001", gpu="T4", high_mem=True))
    return [call for call in fake_cli.calls("colab") if call["argv"][:1] == ["new"]]


async def test_create_session_command_line_is_verbatim(fake_cli):
    # Act
    new_calls = await create_0001_twice(fake_cli)

    # Assert
    assert [call["argv"] for call in new_calls][:1] == [["new", "-s", "cgb-test-0001", "--gpu", "T4"]]


async def test_create_session_with_high_mem_ends_with_high_mem_flag(fake_cli):
    # Act
    new_calls = await create_0001_twice(fake_cli)

    # Assert
    assert [call["argv"][-1] for call in new_calls][1:2] == ["--high-mem"]


async def test_create_session_stdin_is_at_eof(fake_cli):
    # Act
    new_calls = await create_0001_twice(fake_cli)

    # Assert
    assert len(new_calls) == 2
    assert all(call["stdin_eof"] for call in new_calls)


async def test_create_session_sets_cli_request_timeout(fake_cli):
    # Act
    new_calls = await create_0001_twice(fake_cli)

    # Assert
    assert len(new_calls) == 2
    assert [call["env"].get("COLAB_CLI_REQUEST_TIMEOUT") for call in new_calls] == ["60", "60"]


REAL_COLAB = Path(sys.executable).parent / "colab"
ARGUMENT_ERRORS = ("No such option", "Usage:", "Invalid value")


def run_real_colab_without_auth(argv, home: Path) -> subprocess.CompletedProcess:
    """以真的 `colab` 0.7.5 解讀參數(Q115):空的暫存 HOME、沒有授權檔、stdin 接 /dev/null、不檢查更新;
    任何 HTTP 請求都導到 127.0.0.1:9(關閉的 port),保證不連網、不會配置執行環境。"""
    config_dir = home / ".config" / "colab-cli"
    config_dir.mkdir(parents=True)
    (config_dir / "settings.json").write_text(json.dumps({"enable_update_check": False}), encoding="utf-8")
    blackhole = "http://127.0.0.1:9"
    env = {
        "PATH": os.defpath,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "LANG": "C.UTF-8",
        "HTTP_PROXY": blackhole,
        "HTTPS_PROXY": blackhole,
        "http_proxy": blackhole,
        "https_proxy": blackhole,
        "NO_PROXY": "",
    }
    return subprocess.run(
        [str(REAL_COLAB), *argv],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


async def test_create_session_command_line_is_accepted_by_real_cli(fake_cli, tmp_path):
    # Arrange
    new_calls = await create_0001_twice(fake_cli)
    argvs = [call["argv"] for call in new_calls]

    # Act
    results = [run_real_colab_without_auth(argv, tmp_path / f"real-home-{i}") for i, argv in enumerate(argvs)]

    # Assert
    assert len(argvs) == 2
    assert [[marker for marker in ARGUMENT_ERRORS if marker in r.stderr] for r in results] == [[], []]
    assert all("To authorize colab-cli, visit this URL" in r.stderr for r in results)


# ---------------------------------------------------------------- US1-CLI-07


async def test_created_session_missing_from_session_list_is_not_found(fake_cli):
    # Arrange
    fake_cli.script(
        {
            "colab": {
                "new -s cgb-test-0001 --gpu T4": NEW_READY,
                "sessions": {"stdout": "[colab] No active sessions found on server.\n"},
            }
        }
    )

    # Act
    error = await failure_of(ColabControl().create_session(name="cgb-test-0001", gpu="T4", high_mem=False))

    # Assert
    assert code_of(error) == "COLAB_NOT_FOUND"


# ---------------------------------------------------------------- US1-CLI-08


async def test_gpu_outside_gpu_type_is_rejected_before_running_cli(fake_cli):
    # Arrange
    colab = ColabControl()

    # Act
    errors = [
        await failure_of(colab.create_session(name="cgb-test-0001", gpu=gpu, high_mem=False)) for gpu in ("t4", "TPU")
    ]

    # Assert
    assert all(error is not None for error in errors)
    assert fake_cli.calls("colab") == []


# ---------------------------------------------------------------- US1-CLI-09


async def test_high_mem_ignored_by_cli_is_reported_as_success(fake_cli):
    # Arrange
    fake_cli.script(
        {
            "colab": {
                "new -s cgb-test-0001 --gpu L4 --high-mem": {
                    **NEW_READY,
                    "stderr": "[colab] --high-mem ignored: this accelerator only offers one machine shape.\n",
                },
                "sessions": {
                    "stdout": f"[cgb-test-0001] {FAKE_ENDPOINT} | Hardware: L4 | Shape: Standard | Variant: GPU\n"
                },
            }
        }
    )

    # Act
    result = await failure_of_or_result(ColabControl().create_session(name="cgb-test-0001", gpu="L4", high_mem=True))

    # Assert
    assert isinstance(result, dict) and result.get("highMemIgnored") is True


# ---------------------------------------------------------------- US1-CLI-10

AUTH_PROMPT_THEN_EOF = {
    "stderr": (
        "\nTo authorize colab-cli, visit this URL in any browser:\n\n"
        "  https://accounts.google.com/o/oauth2/auth?client_id=cgb-test-fake\n\n"
        "After approving, Google will display an authorization code.\n"
        "Enter the authorization code: Traceback (most recent call last):\n"
        '  File "/usr/lib/python3/colab_cli/auth.py", line 91, in _run_remote_flow\n'
        "EOFError: EOF when reading a line\n"
    ),
    "exit": 1,
}


async def test_usage_without_valid_authorization_is_auth_required_quickly(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"usage": AUTH_PROMPT_THEN_EOF}})

    # Act
    error = await failure_of(asyncio.wait_for(ColabControl().get_usage(), timeout=2))

    # Assert
    assert code_of(error) == "AUTH_REQUIRED"


# ---------------------------------------------------------------- US1-CLI-11

# 本系統提供的遠端腳本放在套件裡;`colab exec -f` 帶的是它在本機上的路徑
START_OLLAMA_SCRIPT = str(files("cgb.adapters.scripts") / "start_ollama.py")
START_OLLAMA_ARGV = [
    "exec", "-s", "cgb-test-0001", "-f", START_OLLAMA_SCRIPT, "--timeout", "240",
    "--env", "OLLAMA_HOST=127.0.0.1:11434", "--env", "OLLAMA_ORIGINS=*",
]  # fmt: skip
INSTALLER_OUTPUT = "".join(f">>> Installing ollama to /usr/local ... step {i}\n" for i in range(30))

# 三個覆蓋值都是自動(null);命令列代入空字串(合約共用約定 11)
AUTO = {"numParallel": None, "contextLength": None, "maxLoadedModels": None}


def start_argv(np="", cl="", ml=""):
    """001 的 `START_OLLAMA_ARGV` 後面接三個 `--env CGB_TUNE_*`(合約 § `paths./exec/start-ollama.post` 的 `x-argv`)。"""
    return [
        *START_OLLAMA_ARGV,
        "--env", f"CGB_TUNE_NUM_PARALLEL={np}",
        "--env", f"CGB_TUNE_CONTEXT_LENGTH={cl}",
        "--env", f"CGB_TUNE_MAX_LOADED_MODELS={ml}",
    ]  # fmt: skip


def result(**fields):
    """遠端腳本印出的一行結果(`CGB-RESULT <JSON>`)。"""
    return f"CGB-RESULT {json.dumps(fields)}\n"


# 40 GiB 的自動值:8/8192/2,flash attention 與 KV cache 固定開啟,五項來源都是 auto
TUNING_AUTO_40G = {
    "numParallel": {"value": 8, "source": "auto"},
    "contextLength": {"value": 8192, "source": "auto"},
    "maxLoadedModels": {"value": 2, "source": "auto"},
    "flashAttention": {"value": True, "source": "auto"},
    "kvCacheType": {"value": "q8_0", "source": "auto"},
}
# 讀不到顯示記憶體也沒有覆蓋值:五項都不帶,用 Ollama 自己的預設值
TUNING_DEFAULT = {
    key: {"value": None, "source": "ollama_default"}
    for key in ("numParallel", "contextLength", "maxLoadedModels", "flashAttention", "kvCacheType")
}
STARTED_A100 = result(
    ok=True,
    ollamaVersion="0.40.15",
    alreadyRunning=False,
    gpuName="NVIDIA A100-SXM4-40GB",
    vramTotalBytes=42949672960,
    systemMemoryTotalBytes=89632571392,
    tuning=TUNING_AUTO_40G,
)
# 001 的測試只看命令列與分類,結果行改成 005 的(含量到的硬體與設定)
START_OLLAMA_OK = STARTED_A100


def start_ollama_script(*entries):
    return {"colab": {shlex.join(start_argv()): list(entries) if len(entries) > 1 else entries[0]}}


async def test_start_ollama_waits_up_to_240_seconds_on_the_remote(fake_cli):
    # Arrange
    fake_cli.script(start_ollama_script({"stdout": START_OLLAMA_OK}))

    # Act
    await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))

    # Assert
    argvs = [call["argv"] for call in fake_cli.calls("colab")]
    assert any(argv[i : i + 2] == ["--timeout", "240"] for argv in argvs for i in range(len(argv)))


async def test_start_ollama_passes_ollama_environment_verbatim(fake_cli):
    # Arrange
    fake_cli.script(start_ollama_script({"stdout": START_OLLAMA_OK}))

    # Act
    await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))

    # Assert
    argvs = [call["argv"] for call in fake_cli.calls("colab")]
    assert len(argvs) == 1
    assert "OLLAMA_HOST=127.0.0.1:11434" in argvs[0]
    assert "OLLAMA_ORIGINS=*" in argvs[0]


# ---------------------------------------------------------------- US1-CLI-12

CONNECTION_LOST = {"stderr": "RuntimeError: Connection was lost\n", "exit": 0}


# ---------------------------------------------------------------- US1-CLI-13

PROBE_SCRIPT = str(files("cgb.adapters.scripts") / "probe_resources.py")
PROBE_ARGV = ["exec", "-s", "cgb-test-0001", "-f", PROBE_SCRIPT, "--timeout", "30"]


async def test_probe_resources_gives_up_as_unreachable_after_one_retry(fake_cli):
    # Arrange
    fake_cli.script({"colab": {shlex.join(PROBE_ARGV): CONNECTION_LOST}})

    # Act
    error = await failure_of(ColabControl().probe_resources(name="cgb-test-0001"))

    # Assert
    assert code_of(error) == "COLAB_UNREACHABLE"
    assert len(fake_cli.calls("colab")) == 2


# ---------------------------------------------------------------- US1-CLI-14


async def test_remote_traceback_without_result_is_remote_error_with_masked_url(fake_cli):
    # Arrange
    traceback = {
        "stderr": (
            "Traceback (most recent call last):\n"
            f"ValueError: see {FAKE_ENDPOINT}/x\n"
        ),
        "exit": 0,
    }
    fake_cli.script(start_ollama_script(traceback))

    # Act
    error = await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))

    # Assert
    assert code_of(error) == "COLAB_REMOTE_ERROR"
    assert error.stderr_last_line == "ValueError: see <網址>"


# ---------------------------------------------------------------- US1-CLI-15

STOP_ARGV = "stop -s cgb-test-0001"
NO_SESSIONS = {"stdout": "[colab] No active sessions found on server.\n"}


def calls_of(fake_cli, subcommand):
    return [call for call in fake_cli.calls("colab") if call["argv"][:1] == [subcommand]]


async def test_stopping_unknown_session_succeeds_after_session_list_confirms(fake_cli):
    # Arrange
    fake_cli.script(
        {
            "colab": {
                STOP_ARGV: {"stdout": "[colab] Session 'cgb-test-0001' not found.\n", "exit": 0},
                "sessions": NO_SESSIONS,
            }
        }
    )

    # Act
    result = await failure_of_or_result(ColabControl().stop_session(name="cgb-test-0001"))

    # Assert
    assert isinstance(result, dict) and result.get("name") == "cgb-test-0001"
    assert len(calls_of(fake_cli, "sessions")) == 1


# ---------------------------------------------------------------- US1-CLI-16

STOP_TERMINATED = {"stdout": "[colab] Stopping session 'cgb-test-0001'...\n[colab] Session terminated.\n", "exit": 0}


async def test_session_still_listed_after_two_stops_is_stop_unconfirmed(fake_cli):
    # Arrange
    fake_cli.script({"colab": {STOP_ARGV: STOP_TERMINATED, "sessions": SESSIONS_WITH_0001}})

    # Act
    error = await failure_of(ColabControl().stop_session(name="cgb-test-0001"))

    # Assert
    assert code_of(error) == "COLAB_STOP_UNCONFIRMED"
    assert len(calls_of(fake_cli, "stop")) == 2
    assert len(calls_of(fake_cli, "sessions")) == 2


# ---------------------------------------------------------------- US1-CLI-17


async def test_session_gone_after_second_stop_succeeds(fake_cli):
    # Arrange
    fake_cli.script({"colab": {STOP_ARGV: STOP_TERMINATED, "sessions": [SESSIONS_WITH_0001, NO_SESSIONS]}})

    # Act
    result = await failure_of_or_result(ColabControl().stop_session(name="cgb-test-0001"))

    # Assert
    assert isinstance(result, dict) and result.get("name") == "cgb-test-0001"
    assert len(calls_of(fake_cli, "stop")) == 2


# ---------------------------------------------------------------- US1-CLI-18


async def test_stop_unconfirmed_reports_stderr_with_endpoint_masked(fake_cli):
    # Arrange
    failed_stop = {"stderr": f"Failed to issue request POST {FAKE_ENDPOINT}/unassign/abc: 500\n", "exit": 1}
    fake_cli.script({"colab": {STOP_ARGV: failed_stop, "sessions": SESSIONS_WITH_0001}})

    # Act
    error = await failure_of(ColabControl().stop_session(name="cgb-test-0001"))

    # Assert
    assert code_of(error) == "COLAB_STOP_UNCONFIRMED"
    assert error.stderr_last_line == "Failed to issue request POST <網址>: 500"


# ---------------------------------------------------------------- US1-CLI-19


async def test_usage_reports_balance_rate_and_active_assignments(fake_cli):
    # Arrange
    stdout = "Current balance: 381.66 compute units\nUsage rate: 1.15/hr\nActive assignments: 1\n"
    fake_cli.script({"colab": {"usage": {"stdout": stdout}}})

    # Act
    result = await failure_of_or_result(ColabControl().get_usage())

    # Assert
    assert isinstance(result, dict)
    assert (result.get("balance"), result.get("ratePerHour"), result.get("activeAssignments")) == (381.66, 1.15, 1)


async def test_usage_fetch_failure_is_not_reported_as_auth_required(fake_cli):
    # Arrange
    failed = {"stderr": "[colab] Warning: failed to fetch compute-unit info: timeout\n", "exit": 1}
    fake_cli.script({"colab": {"usage": failed}})

    # Act
    error = await failure_of(ColabControl().get_usage())

    # Assert
    assert isinstance(error, AdapterError)
    assert error.code != "AUTH_REQUIRED"


# ---------------------------------------------------------------- US1-CLI-20


async def test_session_list_times_out_and_leaves_no_process_behind(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"sessions": {"sleep": 10, "stdout": "[colab] No active sessions found on server.\n"}}})
    colab = ColabControl(timeouts=CliTimeouts(sessions=0.5))
    started = time.monotonic()

    # Act
    error = await failure_of(colab.list_sessions())
    elapsed = time.monotonic() - started

    # Assert
    assert code_of(error) == "COLAB_TIMEOUT"
    assert 0.5 <= elapsed <= 1.5
    pids = [str(call["pid"]) for call in fake_cli.calls("colab")]
    assert len(pids) == 1
    ps = subprocess.run(["ps", "-o", "pid=,stat=", "-p", ",".join(pids)], capture_output=True, text=True, check=False)
    assert ps.stdout.strip() == ""


# ---------------------------------------------------------------- US1-CLI-22~41(Q134 補充案例)

# 先分出一個常駐的子行程(同一個 process group,模擬 `sleep 30 &`),自己再睡 30 秒
HANGS_WITH_CHILD = {"spawn_child": True, "sleep": 30}
SHORT = 0.5


def processes_still_present(pids):
    """`ps` 還看得到的行程(含 defunct);空清單表示都已結束並被回收。"""
    pids = [str(pid) for pid in pids if pid is not None]
    if not pids:
        return []
    ps = subprocess.run(["ps", "-o", "pid=,stat=", "-p", ",".join(pids)], capture_output=True, text=True, check=False)
    return ps.stdout.split("\n")[:-1] if ps.stdout.strip() else []


def fake_and_child_pids(fake_cli):
    calls = fake_cli.calls("colab")
    return [call["pid"] for call in calls] + [call.get("child_pid") for call in calls]


async def timed(call):
    started = time.monotonic()
    error = await failure_of(call)
    return error, time.monotonic() - started


# ---------------------------------------------------------------- US1-CLI-22


async def test_cli_version_times_out_and_ends_cli_with_its_children(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"version": HANGS_WITH_CHILD}})
    colab = ColabControl(timeouts=CliTimeouts(version=SHORT))

    # Act
    error, elapsed = await timed(colab.get_cli_version())

    # Assert
    assert code_of(error) == "COLAB_TIMEOUT"
    assert SHORT <= elapsed <= 1.5
    assert len(fake_cli.calls("colab")) == 1
    assert processes_still_present(fake_and_child_pids(fake_cli)) == []


# ---------------------------------------------------------------- US1-CLI-23


async def test_create_session_times_out_and_ends_cli_with_its_children(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"new -s cgb-test-0001 --gpu T4": HANGS_WITH_CHILD}})
    colab = ColabControl(timeouts=CliTimeouts(new=SHORT))

    # Act
    error, elapsed = await timed(colab.create_session(name="cgb-test-0001", gpu="T4", high_mem=False))

    # Assert
    assert code_of(error) == "COLAB_TIMEOUT"
    assert SHORT <= elapsed <= 1.5
    assert processes_still_present(fake_and_child_pids(fake_cli)) == []


# ---------------------------------------------------------------- US1-CLI-24


@pytest.mark.parametrize(
    ("method", "argv"),
    [("start_ollama", start_argv()), ("probe_resources", PROBE_ARGV)],
)
async def test_exec_times_out_without_retry_and_ends_cli_with_its_children(fake_cli, method, argv):
    # Arrange
    extra = {"overrides": AUTO} if method == "start_ollama" else {}
    fake_cli.script({"colab": {shlex.join(argv): HANGS_WITH_CHILD}})
    colab = ColabControl(timeouts=CliTimeouts(start_ollama=SHORT, probe_resources=SHORT))

    # Act
    error, elapsed = await timed(getattr(colab, method)(name="cgb-test-0001", **extra))

    # Assert
    assert code_of(error) == "COLAB_TIMEOUT"
    assert SHORT <= elapsed <= 1.5
    assert processes_still_present(fake_and_child_pids(fake_cli)) == []
    assert len(fake_cli.calls("colab")) == 1


# ---------------------------------------------------------------- US1-CLI-25


async def test_stop_that_times_out_is_still_judged_by_session_list(fake_cli):
    # Arrange
    fake_cli.script({"colab": {STOP_ARGV: {"sleep": 30}, "sessions": NO_SESSIONS}})
    colab = ColabControl(timeouts=CliTimeouts(stop=SHORT))
    started = time.monotonic()

    # Act
    result = await failure_of_or_result(colab.stop_session(name="cgb-test-0001"))
    elapsed = time.monotonic() - started

    # Assert
    assert isinstance(result, dict) and result.get("name") == "cgb-test-0001"
    # 要抓的錯是「colab stop 沒有時限」:沒有時限時要等滿 30 秒
    assert elapsed <= 10  # 沒有時限時要等滿 30 秒;10 秒以內就分得出來,不受機器負載影響(Q198)
    stop_calls, sessions_calls = calls_of(fake_cli, "stop"), calls_of(fake_cli, "sessions")
    assert len(stop_calls) == 1 and len(sessions_calls) == 1
    # 兩個時間戳由假 colab 子行程各自記下,高負載時 Python 啟動變慢會讓 stop 那筆晚記幾 ms;留 50ms 餘裕(Q201)。
    # 錯的實作(不等時限就查 sessions)差距是 0,仍分得出來
    assert sessions_calls[0]["time"] >= stop_calls[0]["time"] + SHORT - 0.05
    assert processes_still_present([stop_calls[0]["pid"]]) == []


# ---------------------------------------------------------------- US1-CLI-26


async def test_stop_whose_session_list_times_out_is_timeout(fake_cli):
    # Arrange
    fake_cli.script({"colab": {STOP_ARGV: STOP_TERMINATED, "sessions": {"sleep": 30}}})
    colab = ColabControl(timeouts=CliTimeouts(sessions=SHORT, stop=SHORT))

    # Act
    error = await failure_of(colab.stop_session(name="cgb-test-0001"))

    # Assert
    assert code_of(error) == "COLAB_TIMEOUT"
    assert processes_still_present([call["pid"] for call in calls_of(fake_cli, "sessions")]) == []


# ---------------------------------------------------------------- US1-CLI-27


async def test_usage_times_out_and_ends_cli_with_its_children(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"usage": HANGS_WITH_CHILD}})
    colab = ColabControl(timeouts=CliTimeouts(usage=SHORT))

    # Act
    error, elapsed = await timed(colab.get_usage())

    # Assert
    assert code_of(error) == "COLAB_TIMEOUT"
    assert SHORT <= elapsed <= 1.5
    assert processes_still_present(fake_and_child_pids(fake_cli)) == []


# ---------------------------------------------------------------- US1-CLI-28


@pytest.mark.parametrize(
    ("last_line", "expected"),
    [
        ("requests.exceptions.ConnectionError: x", "COLAB_UNREACHABLE"),
        ("Max retries exceeded with url: /tun/m", "COLAB_UNREACHABLE"),
        ("NameResolutionError: x", "COLAB_UNREACHABLE"),
        ("Temporary failure in name resolution", "COLAB_UNREACHABLE"),
        ("requests.exceptions.ReadTimeout: x", "COLAB_TIMEOUT"),
        ("Read timed out.", "COLAB_TIMEOUT"),
    ],
)
async def test_session_list_network_failures_are_told_apart(fake_cli, last_line, expected):
    # Arrange
    fake_cli.script({"colab": {"sessions": {"stderr": f"Traceback (most recent call last):\n{last_line}\n", "exit": 1}}})

    # Act
    error = await failure_of(ColabControl().list_sessions())

    # Assert
    assert code_of(error) == expected


# ---------------------------------------------------------------- US1-CLI-29

NETWORK_MARKERS = [
    ("ConnectionError", "COLAB_UNREACHABLE"),
    ("Max retries exceeded", "COLAB_UNREACHABLE"),
    ("NameResolutionError", "COLAB_UNREACHABLE"),
    ("Temporary failure in name resolution", "COLAB_UNREACHABLE"),
    ("ReadTimeout", "COLAB_TIMEOUT"),
    ("timed out", "COLAB_TIMEOUT"),
]


@pytest.mark.parametrize(("marker", "expected"), NETWORK_MARKERS)
async def test_create_session_network_failures_are_told_apart(fake_cli, marker, expected):
    # Arrange
    fake_cli.script({"colab": {"new -s cgb-test-0001 --gpu T4": {"stderr": f"error: {marker}\n", "exit": 1}}})

    # Act
    error = await failure_of(ColabControl().create_session(name="cgb-test-0001", gpu="T4", high_mem=False))

    # Assert
    assert code_of(error) == expected


# ---------------------------------------------------------------- US1-CLI-30


@pytest.mark.parametrize(("marker", "expected"), [*NETWORK_MARKERS[:4], ("TimeoutError", "COLAB_TIMEOUT"), *NETWORK_MARKERS[4:]])
async def test_start_ollama_network_failures_are_told_apart_without_retry(fake_cli, marker, expected):
    # Arrange
    fake_cli.script(start_ollama_script({"stderr": f"error: {marker}\n", "exit": 1}))

    # Act
    error = await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))

    # Assert
    assert code_of(error) == expected
    assert len(fake_cli.calls("colab")) == 1


# ---------------------------------------------------------------- US1-CLI-31


@pytest.mark.parametrize(("marker", "expected"), NETWORK_MARKERS)
async def test_usage_network_failures_are_told_apart(fake_cli, marker, expected):
    # Arrange
    fake_cli.script({"colab": {"usage": {"stderr": f"[colab] Warning: failed to fetch compute-unit info: {marker}\n", "exit": 1}}})

    # Act
    error = await failure_of(ColabControl().get_usage())

    # Assert
    assert code_of(error) == expected


# ---------------------------------------------------------------- US1-CLI-32

AUTH_FAILURES = {
    "authorize-url": "To authorize colab-cli, visit this URL: https://accounts.google.com/o/oauth2/auth?x=1\n",
    "http-401": f"requests.exceptions.HTTPError: 401 Client Error: Unauthorized for url: {FAKE_ENDPOINT}/x\n",
}


@pytest.mark.parametrize("stderr", AUTH_FAILURES.values(), ids=AUTH_FAILURES.keys())
async def test_session_list_without_valid_authorization_is_auth_required(fake_cli, stderr):
    # Arrange
    fake_cli.script({"colab": {"sessions": {"stderr": stderr, "exit": 1}}})

    # Act
    error = await failure_of(ColabControl().list_sessions())

    # Assert
    assert code_of(error) == "AUTH_REQUIRED"


# ---------------------------------------------------------------- US1-CLI-33


@pytest.mark.parametrize("stderr", AUTH_FAILURES.values(), ids=AUTH_FAILURES.keys())
async def test_create_session_without_valid_authorization_is_auth_required(fake_cli, stderr):
    # Arrange
    fake_cli.script({"colab": {"new -s cgb-test-0001 --gpu T4": {"stderr": stderr, "exit": 1}}})

    # Act
    error = await failure_of(ColabControl().create_session(name="cgb-test-0001", gpu="T4", high_mem=False))

    # Assert
    assert code_of(error) == "AUTH_REQUIRED"


# ---------------------------------------------------------------- US1-CLI-34


@pytest.mark.parametrize("stderr", AUTH_FAILURES.values(), ids=AUTH_FAILURES.keys())
async def test_start_ollama_without_valid_authorization_is_auth_required_without_retry(fake_cli, stderr):
    # Arrange
    fake_cli.script(start_ollama_script({"stderr": stderr, "exit": 1}))

    # Act
    error = await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))

    # Assert
    assert code_of(error) == "AUTH_REQUIRED"
    assert len(fake_cli.calls("colab")) == 1


# ---------------------------------------------------------------- US1-CLI-35


async def test_stop_without_valid_authorization_is_auth_required_without_session_list(fake_cli):
    # Arrange
    fake_cli.script({"colab": {STOP_ARGV: {"stderr": AUTH_FAILURES["authorize-url"], "exit": 1}}})

    # Act
    error = await failure_of(ColabControl().stop_session(name="cgb-test-0001"))

    # Assert
    assert code_of(error) == "AUTH_REQUIRED"
    assert calls_of(fake_cli, "sessions") == []


# ---------------------------------------------------------------- US1-CLI-36


@pytest.mark.parametrize(
    ("gpu", "stderr", "expected"),
    [
        ("T4", "[colab] Allocation refused (precondition failed).\n", "COLAB_ALLOCATION_REFUSED"),
        ("L4", "[colab] Backend rejected accelerator 'L4' for this account.\n", "COLAB_ACCELERATOR_REJECTED"),
    ],
    ids=["allocation-refused", "accelerator-rejected"],
)
async def test_create_session_tells_refused_allocation_from_rejected_accelerator(fake_cli, gpu, stderr, expected):
    # Arrange
    fake_cli.script({"colab": {f"new -s cgb-test-0001 --gpu {gpu}": {"stderr": stderr, "exit": 1}}})

    # Act
    error = await failure_of(ColabControl().create_session(name="cgb-test-0001", gpu=gpu, high_mem=False))

    # Assert
    assert code_of(error) == expected


# ---------------------------------------------------------------- US1-CLI-37

CRASH = {
    "stderr": f"Traceback (most recent call last):\n  File x\nRuntimeError: boom at {FAKE_ENDPOINT}/x\n\n",
    "exit": 2,
}
CALLS_THAT_CRASH = {
    "get_cli_version": ("version", lambda colab: colab.get_cli_version()),
    "list_sessions": ("sessions", lambda colab: colab.list_sessions()),
    "create_session": (
        "new -s cgb-test-0001 --gpu T4",
        lambda colab: colab.create_session(name="cgb-test-0001", gpu="T4", high_mem=False),
    ),
    "start_ollama": (shlex.join(start_argv()), lambda colab: colab.start_ollama(name="cgb-test-0001", overrides=AUTO)),
}


@pytest.mark.parametrize("method", CALLS_THAT_CRASH.keys())
async def test_cli_exiting_non_zero_is_failed_with_last_non_blank_stderr_line_masked(fake_cli, method):
    # Arrange
    key, call = CALLS_THAT_CRASH[method]
    fake_cli.script({"colab": {key: CRASH}})

    # Act
    error = await failure_of(call(ColabControl()))

    # Assert
    assert code_of(error) == "COLAB_FAILED"
    assert error.stderr_last_line == "RuntimeError: boom at <網址>"


# ---------------------------------------------------------------- US1-CLI-38


async def test_create_session_without_session_ready_is_bad_response(fake_cli):
    # Arrange
    fake_cli.script(
        {
            "colab": {
                "new -s cgb-test-0001 --gpu T4": {"stdout": "[colab] Creating session 'cgb-test-0001'...\n", "exit": 0},
                "sessions": SESSIONS_WITH_0001,
            }
        }
    )

    # Act
    error = await failure_of(ColabControl().create_session(name="cgb-test-0001", gpu="T4", high_mem=False))

    # Assert
    assert code_of(error) == "COLAB_BAD_RESPONSE"


# ---------------------------------------------------------------- US1-CLI-39


@pytest.mark.parametrize(
    "stdout",
    ["[colab] Session 'cgb-test-0001' not found.\n", "[colab] Runtime appears to be lost (404/401).\n"],
    ids=["not-found", "lost"],
)
async def test_start_ollama_on_runtime_that_is_gone_is_not_found_without_retry(fake_cli, stdout):
    # Arrange
    fake_cli.script(start_ollama_script({"stdout": stdout, "exit": 0}))

    # Act
    error = await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))

    # Assert
    assert code_of(error) == "COLAB_NOT_FOUND"
    assert len(fake_cli.calls("colab")) == 1


# ---------------------------------------------------------------- US1-CLI-40


async def test_start_ollama_result_not_ok_is_remote_error_with_stage_and_detail(fake_cli):
    # Arrange
    result = 'CGB-RESULT {"ok": false, "stage": "install", "detail": "curl: (22) error 503"}\n'
    fake_cli.script(start_ollama_script({"stdout": INSTALLER_OUTPUT + result, "exit": 0}))

    # Act
    error = await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))

    # Assert
    assert code_of(error) == "COLAB_REMOTE_ERROR"
    assert "install" in error.message
    assert "curl: (22) error 503" in error.message


# ---------------------------------------------------------------- US1-CLI-41


@pytest.mark.parametrize(
    "stdout",
    [INSTALLER_OUTPUT, INSTALLER_OUTPUT + "CGB-RESULT {ok: true\n"],
    ids=["no-result-line", "invalid-json"],
)
async def test_probe_resources_without_a_valid_result_line_is_bad_response(fake_cli, stdout):
    # Arrange
    fake_cli.script({"colab": {shlex.join(PROBE_ARGV): {"stdout": stdout, "exit": 0}}})

    # Act
    error = await failure_of(ColabControl().probe_resources(name="cgb-test-0001"))

    # Assert
    assert code_of(error) == "COLAB_BAD_RESPONSE"


# ---------------------------------------------------------------- US2-CLI-01 遠端 Ollama 只聽執行環境本機(NFR-003)

PUBLIC_EXPOSURE_WORDS = ("0.0.0.0", "cloudflared", "ngrok", "localtunnel")


def env_values(argv, name):
    """argv 裡每個 `--env <name>=<值>` 的值。"""
    prefix = f"{name}="
    return [
        argv[i + 1].removeprefix(prefix)
        for i in range(len(argv) - 1)
        if argv[i] == "--env" and argv[i + 1].startswith(prefix)
    ]


def uploaded_script_of(argv):
    """`colab exec -f <路徑>` 送出的那份初始化腳本的內容(以本系統實際帶的路徑讀,不另外指定)。"""
    paths = [argv[i + 1] for i in range(len(argv) - 1) if argv[i] == "-f"]
    assert len(paths) == 1, f"argv 裡 `-f` 應該剛好一個:{argv}"
    return Path(paths[0]).read_text(encoding="utf-8")


async def start_ollama_argv(fake_cli):
    fake_cli.script(start_ollama_script({"stdout": START_OLLAMA_OK}))
    await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))
    calls = fake_cli.calls("colab")
    assert len(calls) == 1
    return calls[0]["argv"]


async def test_start_ollama_binds_remote_ollama_to_runtime_loopback_only(fake_cli):
    # Act
    argv = await start_ollama_argv(fake_cli)

    # Assert
    assert env_values(argv, "OLLAMA_HOST") == ["127.0.0.1:11434"]


async def test_start_ollama_script_neither_binds_all_interfaces_nor_opens_a_public_tunnel(fake_cli):
    # Arrange
    argv = await start_ollama_argv(fake_cli)

    # Act
    script = uploaded_script_of(argv).lower()

    # Assert
    assert [word for word in PUBLIC_EXPOSURE_WORDS if word in script] == []


# ---------------------------------------------------------------- US3-CLI-01

PROBE_OK = (
    'CGB-RESULT {"ok": true, "diskFreeBytes": 225485783040, "diskTotalBytes": 253338115072, '
    '"gpuName": "Tesla T4", "vramTotalBytes": 16106127360, "vramFreeBytes": 15727591424}\n'
)


async def test_probe_resources_reports_free_disk_and_total_vram(fake_cli):
    # Arrange
    fake_cli.script({"colab": {shlex.join(PROBE_ARGV): {"stdout": PROBE_OK}}})

    # Act
    result = await failure_of_or_result(ColabControl().probe_resources(name="cgb-test-0001"))

    # Assert
    assert isinstance(result, dict), f"回了錯誤:{result!r}"
    assert result.get("diskFreeBytes") == 225485783040
    assert result.get("vramTotalBytes") == 16106127360
    argvs = [call["argv"] for call in fake_cli.calls("colab")]
    assert any(argv[i : i + 2] == ["--timeout", "30"] for argv in argvs for i in range(len(argv)))


# ---------------------------------------------------------------- US3-CLI-02

PROBE_NO_GPU = (
    'CGB-RESULT {"ok": true, "diskFreeBytes": 225485783040, "diskTotalBytes": 253338115072, '
    '"gpuName": null, "vramTotalBytes": null, "vramFreeBytes": null}\n'
)
PROBE_DISK_FAILED = 'CGB-RESULT {"ok": false, "detail": "disk_usage(/root) failed: [Errno 5] Input/output error"}\n'


async def test_probe_resources_without_gpu_still_reports_free_disk(fake_cli):
    # Arrange
    fake_cli.script({"colab": {shlex.join(PROBE_ARGV): {"stdout": PROBE_NO_GPU}}})

    # Act
    result = await failure_of_or_result(ColabControl().probe_resources(name="cgb-test-0001"))

    # Assert
    assert isinstance(result, dict), f"回了錯誤:{result!r}"
    assert result.get("diskFreeBytes") == 225485783040
    assert "vramTotalBytes" in result and result["vramTotalBytes"] is None


async def test_probe_resources_that_cannot_read_disk_is_remote_error(fake_cli):
    # Arrange
    fake_cli.script({"colab": {shlex.join(PROBE_ARGV): {"stdout": PROBE_DISK_FAILED}}})

    # Act
    error = await failure_of(ColabControl().probe_resources(name="cgb-test-0001"))

    # Assert
    assert code_of(error) == "COLAB_REMOTE_ERROR"


# ---------------------------------------------------------------- US4-CLI-01

USAGE_NEGATIVE_BALANCE_WITH_NOTICE = (
    "[colab] A new version of colab-cli is available: 0.7.6 (you have 0.7.5).\n"
    "Current balance: -0.50 compute units\n"
    "Usage rate: 0.00/hr\n"
    "Active assignments: 0\n"
)


async def test_usage_after_balance_runs_out_reports_negative_balance(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"usage": {"stdout": USAGE_NEGATIVE_BALANCE_WITH_NOTICE}}})

    # Act
    result = await failure_of_or_result(ColabControl().get_usage())

    # Assert
    assert isinstance(result, dict), f"回了錯誤:{result!r}"
    assert result.get("balance") == -0.5
    assert result.get("ratePerHour") == 0
    assert result.get("activeAssignments") == 0


# ---------------------------------------------------------------- US4-CLI-02

USAGE_ONE_DECIMAL_BALANCE = "Current balance: 381.7 compute units\nUsage rate: 1.15/hr\nActive assignments: 1\n"


async def test_usage_in_unexpected_number_format_is_bad_response(fake_cli):
    # Arrange
    fake_cli.script({"colab": {"usage": {"stdout": USAGE_ONE_DECIMAL_BALANCE}}})

    # Act
    error = await failure_of(ColabControl().get_usage())

    # Assert
    assert code_of(error) == "COLAB_BAD_RESPONSE"


# ================================================================ 005 依機器配置調整遠端 Ollama(testplan.md § 2.1)

def start_script_for(argv, *entries):
    return {"colab": {shlex.join(argv): list(entries) if len(entries) > 1 else entries[0]}}


# ---- 005 US1-CLI-01


async def test_沒有覆蓋值時啟動_Ollama_的命令列仍帶齊三個_CGB_TUNE_且值為空字串(fake_cli):
    # Arrange
    fake_cli.script(start_script_for(start_argv(), {"stdout": STARTED_A100}))

    # Act
    await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))

    # Assert
    calls = fake_cli.calls("colab")
    assert len(calls) == 1
    assert calls[0]["argv"] == start_argv()


async def test_啟動_Ollama_的命令列真的_colab_解讀得了(tmp_path):
    """Q56:`--env CGB_TUNE_*=` 帶空值是新的寫法,讓真的 `colab` 0.7.5 解讀一次;會在本機執行 `colab`(快速層排除,執行前先問本人)。"""
    # Act
    real = run_real_colab_without_auth(start_argv(), tmp_path / "real-home")

    # Assert
    assert [marker for marker in ARGUMENT_ERRORS if marker in real.stderr + real.stdout] == []
    # 參數解讀完之後,`colab exec` 先查工作階段(空的 HOME 裡沒有),再要求授權;兩種都代表參數已被接受
    # (2026-11-15 實跑:stdout「[colab] Session 'cgb-test-0001' not found.」,和 001 `colab new` 停在授權不同)
    assert "not found" in real.stdout or "To authorize colab-cli, visit this URL" in real.stderr


# ---- 005 US1-CLI-05

REMOTE_FAILURES = [
    {"stdout": result(ok=False, stage="install", detail="curl: (6) Could not resolve host: ollama.com"), "exit": 0},
    {"stdout": result(ok=False, stage="start", detail="[Errno 2] No such file or directory: 'ollama'"), "exit": 0},
    {"stdout": result(ok=False, stage="verify", detail="no response from /api/version within 60 seconds"), "exit": 0},
    {
        "stderr": f'Traceback (most recent call last):\n  File "<x>"\nValueError: see {FAKE_ENDPOINT}/x\n',
        "exit": 0,
    },
]


def remote_stage_of(error):
    return getattr(error, "remote_stage", "<AdapterError 沒有 remote_stage>")


async def test_遠端腳本回報失敗時帶出失敗的階段_丟出例外時階段是_None(fake_cli):
    # Arrange
    fake_cli.script(start_script_for(start_argv(), *REMOTE_FAILURES))
    colab = ColabControl()

    # Act
    install, start, verify, traceback = [
        await failure_of(colab.start_ollama(name="cgb-test-0001", overrides=AUTO)) for _ in REMOTE_FAILURES
    ]

    # Assert
    assert (code_of(install), remote_stage_of(install)) == ("COLAB_REMOTE_ERROR", "install")
    assert (code_of(start), remote_stage_of(start)) == ("COLAB_REMOTE_ERROR", "start")
    assert (code_of(verify), remote_stage_of(verify)) == ("COLAB_REMOTE_ERROR", "verify")
    assert "verify" in verify.message and "no response from /api/version within 60 seconds" in verify.message
    assert (code_of(traceback), remote_stage_of(traceback)) == ("COLAB_REMOTE_ERROR", None)
    assert traceback.stderr_last_line == "ValueError: see <網址>"


# ---- 005 US1-CLI-02


async def test_啟動_Ollama_交出量到的硬體與腳本回報的設定(fake_cli):
    # Arrange
    fake_cli.script(start_script_for(start_argv(), {"stdout": STARTED_A100}))
    before = datetime.now(UTC)

    # Act
    started = await failure_of_or_result(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))
    after = datetime.now(UTC)

    # Assert
    assert isinstance(started, dict), f"回了錯誤:{started!r}"
    machine = started.get("machine") or {}
    assert (started.get("ollamaVersion"), started.get("alreadyRunning")) == ("0.40.15", False)
    assert machine.get("gpuName") == "NVIDIA A100-SXM4-40GB"
    assert machine.get("vramTotalBytes") == 42949672960
    assert machine.get("systemMemoryTotalBytes") == 89632571392
    probed_at = datetime.fromisoformat(machine.get("probedAt") or "1970-01-01")
    assert probed_at.tzinfo is not None and before <= probed_at <= after
    assert started.get("tuning") == TUNING_AUTO_40G


# ---- 005 US1-CLI-03


async def test_讀不到顯示記憶體時照樣啟動_硬體是_None_設定是_Ollama_預設值(fake_cli):
    # Arrange
    no_gpu = result(
        ok=True,
        ollamaVersion="0.40.15",
        alreadyRunning=False,
        gpuName=None,
        vramTotalBytes=None,
        systemMemoryTotalBytes=13605855232,
        tuning=TUNING_DEFAULT,
    )
    fake_cli.script(start_script_for(start_argv(), {"stdout": no_gpu}))

    # Act
    started = await failure_of_or_result(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))

    # Assert
    assert isinstance(started, dict), f"回了錯誤:{started!r}"
    assert started["machine"]["vramTotalBytes"] is None
    assert started["machine"]["gpuName"] is None
    assert started["tuning"] == TUNING_DEFAULT


# ---- 005 US1-CLI-04


async def test_已在執行而讀不到設定檔時照樣接受_設定是_None_不拿這次的覆蓋值補(fake_cli):
    # Arrange
    before_005 = result(
        ok=True,
        ollamaVersion="0.40.15",
        alreadyRunning=True,
        gpuName="Tesla T4",
        vramTotalBytes=16106127360,
        systemMemoryTotalBytes=13605855232,
        tuning=None,
    )
    fake_cli.script(start_script_for(start_argv(np="4"), {"stdout": before_005}))
    overrides = {"numParallel": 4, "contextLength": None, "maxLoadedModels": None}

    # Act
    started = await failure_of_or_result(ColabControl().start_ollama(name="cgb-test-0001", overrides=overrides))

    # Assert
    assert isinstance(started, dict), f"回了錯誤:{started!r}"
    assert started["alreadyRunning"] is True
    assert started["tuning"] is None
    assert started["machine"]["vramTotalBytes"] == 16106127360


# ---- 005 US1-CLI-06

STARTED_FIELDS = {
    "ok": True,
    "ollamaVersion": "0.40.15",
    "alreadyRunning": False,
    "gpuName": "NVIDIA A100-SXM4-40GB",
    "vramTotalBytes": 42949672960,
    "systemMemoryTotalBytes": 89632571392,
    "tuning": TUNING_AUTO_40G,
}
BAD_RESULTS = {
    "a-no-result-line": INSTALLER_OUTPUT,
    "b-not-json": INSTALLER_OUTPUT + "CGB-RESULT not json\n",
    "c-missing-vram": result(**{k: v for k, v in STARTED_FIELDS.items() if k != "vramTotalBytes"}),
    "d-unknown-source": result(
        **{**STARTED_FIELDS, "tuning": {**TUNING_AUTO_40G, "numParallel": {"value": 8, "source": "magic"}}}
    ),
    "e-new-start-without-tuning": result(**{**STARTED_FIELDS, "tuning": None}),
}


async def test_結果行缺鍵_型別不符或新啟動卻沒有設定時都是_COLAB_BAD_RESPONSE(fake_cli):
    # Arrange
    entries = [{"stdout": stdout, "exit": 0} for stdout in BAD_RESULTS.values()]
    fake_cli.script(start_script_for(start_argv(), *entries))
    colab = ColabControl()

    # Act
    errors = [await failure_of(colab.start_ollama(name="cgb-test-0001", overrides=AUTO)) for _ in entries]

    # Assert
    assert dict(zip(BAD_RESULTS, map(code_of, errors), strict=True)) == dict.fromkeys(BAD_RESULTS, "COLAB_BAD_RESPONSE")
    assert [e for e in errors if isinstance(e, (KeyError, TypeError, ValueError))] == []


# ---- 005 US1-CLI-07

RUNTIME_GONE = {"stdout": "[colab] Session 'cgb-test-0001' not found.\n", "exit": 0}
AUTH_PROMPT = {
    "stderr": "To authorize colab-cli, visit this URL: https://accounts.google.com/o/oauth2/auth?x=1\n",
    "exit": 1,
}
CLI_FAILURES = {
    "c-not-found": (RUNTIME_GONE, "COLAB_NOT_FOUND"),
    "d-auth": (AUTH_PROMPT, "AUTH_REQUIRED"),
    "e-connection-error": ({"stderr": "error: ConnectionError\n", "exit": 1}, "COLAB_UNREACHABLE"),
    "f-read-timeout": ({"stderr": "error: ReadTimeout\n", "exit": 1}, "COLAB_TIMEOUT"),
    "g-crash": ({"stderr": f"boom at {FAKE_ENDPOINT}/y\n", "exit": 3}, "COLAB_FAILED"),
}


async def test_帶覆蓋值的啟動照樣有_001_的失敗分類_逾時整組終止與斷線重跑一次(fake_cli, tmp_path, monkeypatch):
    # Arrange
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    short = ColabControl(timeouts=CliTimeouts(start_ollama=SHORT))

    # Act
    with monkeypatch.context() as no_colab:
        no_colab.setenv("PATH", str(empty_bin))
        not_installed = await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))
    fake_cli.script(start_script_for(start_argv(), HANGS_WITH_CHILD))
    hang, hang_elapsed = await timed(short.start_ollama(name="cgb-test-0001", overrides=AUTO))
    hang_left = processes_still_present(fake_and_child_pids(fake_cli))
    failures = {}
    for case, (entry, _) in CLI_FAILURES.items():
        fake_cli.script(start_script_for(start_argv(), entry))
        before = len(fake_cli.calls("colab"))
        error = await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))
        failures[case] = (error, len(fake_cli.calls("colab")) - before)
    fake_cli.script(start_script_for(start_argv(), CONNECTION_LOST, {"stdout": STARTED_A100}))
    before = len(fake_cli.calls("colab"))
    retried = await failure_of_or_result(ColabControl().start_ollama(name="cgb-test-0001", overrides=AUTO))
    retried_argvs = [call["argv"] for call in fake_cli.calls("colab")[before:]]

    # Assert
    assert code_of(not_installed) == "COLAB_NOT_INSTALLED"
    assert code_of(hang) == "COLAB_TIMEOUT" and SHORT <= hang_elapsed <= 1.5
    assert hang_left == []
    assert {case: code_of(error) for case, (error, _) in failures.items()} == {
        case: code for case, (_, code) in CLI_FAILURES.items()
    }
    assert failures["c-not-found"][1] == 1
    assert failures["g-crash"][0].stderr_last_line == "boom at <網址>"
    assert isinstance(retried, dict), f"回了錯誤:{retried!r}"
    assert retried_argvs == [start_argv(), start_argv()]


# ---- 005 US2-CLI-01

NUM_PARALLEL_4 = {"numParallel": 4, "contextLength": None, "maxLoadedModels": None}


async def test_只覆蓋平行數時命令列帶它的十進位數字_沒填的兩項仍是空字串_設定照腳本回報(fake_cli):
    # Arrange
    manual_4 = {**TUNING_AUTO_40G, "numParallel": {"value": 4, "source": "manual"}}
    fake_cli.script(start_script_for(start_argv(np="4"), {"stdout": result(**{**STARTED_FIELDS, "tuning": manual_4})}))

    # Act
    started = await failure_of_or_result(ColabControl().start_ollama(name="cgb-test-0001", overrides=NUM_PARALLEL_4))

    # Assert
    assert [call["argv"] for call in fake_cli.calls("colab")] == [start_argv(np="4")]
    assert isinstance(started, dict), f"回了錯誤:{started!r}"
    assert started["tuning"]["numParallel"] == {"value": 4, "source": "manual"}


# ---- 005 US2-CLI-02


async def test_覆蓋值剛好是上限或下限時照樣帶進命令列(fake_cli):
    # Arrange
    upper = start_argv(np="32", cl="131072", ml="4")
    lower = start_argv(np="1", cl="2048", ml="1")
    fake_cli.script({"colab": {shlex.join(argv): {"stdout": STARTED_A100} for argv in (upper, lower)}})
    colab = ColabControl()

    # Act
    at_upper = await failure_of(
        colab.start_ollama(name="cgb-test-0001", overrides={"numParallel": 32, "contextLength": 131072, "maxLoadedModels": 4})
    )
    at_lower = await failure_of(
        colab.start_ollama(name="cgb-test-0001", overrides={"numParallel": 1, "contextLength": 2048, "maxLoadedModels": 1})
    )

    # Assert
    argvs = [call["argv"] for call in fake_cli.calls("colab")]
    assert (at_upper, argvs[:1]) == (None, [upper])
    assert (at_lower, argvs[1:]) == (None, [lower])


# ---- 005 US2-CLI-03

OUT_OF_RANGE = {
    "numParallel-0": {"numParallel": 0},
    "numParallel-33": {"numParallel": 33},
    "contextLength-2047": {"contextLength": 2047},
    "contextLength-131073": {"contextLength": 131073},
    "maxLoadedModels-0": {"maxLoadedModels": 0},
    "maxLoadedModels-5": {"maxLoadedModels": 5},
    "numParallel-4.5": {"numParallel": 4.5},
    "numParallel-str-4": {"numParallel": "4"},
    "numParallel-True": {"numParallel": True},
}


@pytest.mark.parametrize("override", OUT_OF_RANGE.values(), ids=OUT_OF_RANGE.keys())
async def test_覆蓋值超出範圍或不是整數時是_COLAB_INVALID_TUNING_不執行_colab(fake_cli, override):
    # Arrange
    fake_cli.script({"colab": {shlex.join(argv): {"stdout": STARTED_A100} for argv in (start_argv(), start_argv(np="1"))}})

    # Act
    error = await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides={**AUTO, **override}))

    # Assert
    assert code_of(error) == "COLAB_INVALID_TUNING"
    assert fake_cli.calls("colab") == []


# ---- 005 US2-CLI-04


async def test_遠端腳本回報覆蓋值不符時是_COLAB_INVALID_TUNING_沒有遠端階段(fake_cli):
    # Arrange
    rejected = result(ok=False, stage="input", detail="CGB_TUNE_NUM_PARALLEL must be an integer between 1 and 32")
    fake_cli.script(start_script_for(start_argv(np="4"), {"stdout": rejected, "exit": 0}))

    # Act
    error = await failure_of(ColabControl().start_ollama(name="cgb-test-0001", overrides=NUM_PARALLEL_4))

    # Assert
    assert code_of(error) == "COLAB_INVALID_TUNING"
    assert remote_stage_of(error) is None
