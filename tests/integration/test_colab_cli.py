"""E5 Colab CLI 轉接層(testplan.md § 2.2;`contracts/colab-cli.openapi.yaml`)。

接縫:`ColabControl` 的方法;`colab` 是 `tests/fixtures/bin/colab` 假執行檔(由 `fake_cli` fixture 放上 `PATH`)。
"""

import asyncio
import json
import os
import shlex
import subprocess
import sys
import time
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
START_OLLAMA_OK = 'CGB-RESULT {"ok": true, "ollamaVersion": "0.40.15", "alreadyRunning": false}\n'
INSTALLER_OUTPUT = "".join(f">>> Installing ollama to /usr/local ... step {i}\n" for i in range(30))


def start_ollama_script(*entries):
    return {"colab": {shlex.join(START_OLLAMA_ARGV): list(entries) if len(entries) > 1 else entries[0]}}


async def test_start_ollama_reads_the_last_result_line(fake_cli):
    # Arrange
    fake_cli.script(start_ollama_script({"stdout": INSTALLER_OUTPUT + START_OLLAMA_OK}))

    # Act
    result = await failure_of_or_result(ColabControl().start_ollama(name="cgb-test-0001"))

    # Assert
    assert isinstance(result, dict) and result.get("ollamaVersion") == "0.40.15"


async def test_start_ollama_waits_up_to_240_seconds_on_the_remote(fake_cli):
    # Arrange
    fake_cli.script(start_ollama_script({"stdout": START_OLLAMA_OK}))

    # Act
    await failure_of(ColabControl().start_ollama(name="cgb-test-0001"))

    # Assert
    argvs = [call["argv"] for call in fake_cli.calls("colab")]
    assert any(argv[i : i + 2] == ["--timeout", "240"] for argv in argvs for i in range(len(argv)))


async def test_start_ollama_passes_ollama_environment_verbatim(fake_cli):
    # Arrange
    fake_cli.script(start_ollama_script({"stdout": START_OLLAMA_OK}))

    # Act
    await failure_of(ColabControl().start_ollama(name="cgb-test-0001"))

    # Assert
    argvs = [call["argv"] for call in fake_cli.calls("colab")]
    assert len(argvs) == 1
    assert "OLLAMA_HOST=127.0.0.1:11434" in argvs[0]
    assert "OLLAMA_ORIGINS=*" in argvs[0]


# ---------------------------------------------------------------- US1-CLI-12

CONNECTION_LOST = {"stderr": "RuntimeError: Connection was lost\n", "exit": 0}


async def test_start_ollama_retries_once_with_same_arguments_after_connection_lost(fake_cli):
    # Arrange
    fake_cli.script(start_ollama_script(CONNECTION_LOST, {"stdout": START_OLLAMA_OK}))

    # Act
    result = await failure_of_or_result(ColabControl().start_ollama(name="cgb-test-0001"))

    # Assert
    assert result == {"ollamaVersion": "0.40.15", "alreadyRunning": False}
    assert [call["argv"] for call in fake_cli.calls("colab")] == [START_OLLAMA_ARGV, START_OLLAMA_ARGV]


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
    error = await failure_of(ColabControl().start_ollama(name="cgb-test-0001"))

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
