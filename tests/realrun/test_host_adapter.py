"""主機階段:同一台 `cgb-test-<YYYYmmddHHMM>-adapter` 依序做 US1-CLI-21、US2-RO-03、US1-TUN-10,最後 stop(P9)。

tasks.md 把三個案例寫成三個檔(T077 `test_us1_cli_21.py`、T174 `test_us2_ro_03.py`、T109 `test_us1_tun_10.py`),
這裡合成一個檔:三個案例共用一台執行環境,US1-CLI-21 的 stop 又要在另外兩個案例之後,
放在同一個模組才能由一個 module-scope fixture 開一台、模組結束一定收掉(不拖到容器階段才 stop)。

測試照定義順序執行:
1. `test_us1_cli_21_open`:version、usage、sessions、new、sessions、exec 啟動 Ollama、exec 讀資源、stop 不存在的名稱
2. `test_us2_ro_03`:經 `Tunnel.open_tunnel` 的本機轉發呼叫真的遠端 Ollama
3. `test_us1_tun_10`:建立通道、殺掉 ssh、重新建立、關閉
4. `test_us1_cli_21_stop`:stop 這台、60 秒內回讀不再列出;替身劇本與真輸出的欄位比對

`host` fixture 的收尾不論成敗都做:關通道 → 這台還在就 stop 並回讀 → P3(`realrun.p3_cleanup()`)→ 再回讀一次
`colab sessions` 確認沒有這台;有問題就讓收尾失敗(訊息列出要使用者處理的事)。

子行程的環境:`realrun.colab()` 自己帶 `realrun.env()`;轉接層(`Tunnel` 的 ssh 與 ProxyCommand)繼承 `os.environ`,
所以 fixture 在整個模組期間把 `os.environ` 的 HOME、PATH、`COLAB_CLI_REQUEST_TIMEOUT` 換成 `realrun.env()` 的值。
不呼叫本系統後端。GPU 只用 T4(P2,由 `realrun.colab()` 強制)。
"""

import asyncio
import contextlib
import json
import os
import re
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime
from importlib.resources import files
from typing import Any

import httpx
import pytest
from integration.test_colab_cli import (
    NEW_READY,
    NO_SESSIONS,
    PROBE_OK,
    SESSIONS_WITH_0001,
    START_OLLAMA_OK,
    STOP_TERMINATED,
    USAGE_NEGATIVE_BALANCE_WITH_NOTICE,
)
from integration.test_remote_ollama import PS_ONE_MODEL, PULL_LAYER_50, TAGS_TWO_MODELS

from cgb.adapters.colab_cli import (
    CONNECTION_LOST,
    RESULT_PREFIX,
    SESSION_LINE,
    SESSION_READY,
    START_OLLAMA_ENV as OLLAMA_ENV,
    USAGE_LINES,
    VERSION_LINE,
    stop_output_of,
)
from cgb.adapters.errors import AdapterError
from cgb.adapters.remote_ollama import RemoteOllama
from cgb.adapters.tunnel import STDERR_IGNORE, STDERR_PATTERNS, Tunnel, mask_secrets
from realrun.conftest import (
    ALLOWED_GPU,
    TEST_PREFIX,
    GuardViolation,
    adapter_session_name,
    check_model,
    mask_urls,
    parse_session_names,
    residual_ssh_pids,
    write_measurement,
)
from realrun.helpers import RecordingTransport, field_names, free_loopback_port, ndjson, port_listening, run

SCRIPTS = files("cgb.adapters.scripts")
SMALL, LARGE, MISSING = "qwen2.5:0.5b", "qwen2.5:7b", "qwen2.5:cgb-test-nonexistent"
for _model in (SMALL, LARGE, MISSING):
    check_model(_model)

COLAB_CALL_TIMEOUT = 90
NEW_TIMEOUT = 300
START_OLLAMA_TIMEOUT = 300
# 和轉接層的 start_ollama 同一個命令列:005 起每次都帶齊三個 CGB_TUNE_*,自動時是空字串(Q63)
START_OLLAMA_ENV = (
    *OLLAMA_ENV,
    "--env", "CGB_TUNE_NUM_PARALLEL=",
    "--env", "CGB_TUNE_CONTEXT_LENGTH=",
    "--env", "CGB_TUNE_MAX_LOADED_MODELS=",
)  # fmt: skip
PROBE_TIMEOUT = 90
STOP_GONE_DEADLINE = 60
POLL = 5
REOPEN_DEADLINE = 120
REOPEN_INTERVAL = 2
# 讓 US2-RO-03 載入的 qwen2.5:0.5b 留到 US1-TUN-10 查 /api/ps(Ollama 預設 5 分鐘就卸載)
KEEP_LOADED = "30m"
LAN_ORIGIN = "http://192.168.0.50:3000"
CREATING_LINE = re.compile(r"^\[colab\] Creating session '[^']*'\.\.\.$")
# 替身(`tests/integration/test_colab_cli.py` 的 US1-CLI-15)寫的「不存在」輸出
FAKE_STOP_NOT_FOUND = "[colab] Session 'cgb-test-0001' not found.\n"
# 替身(`tests/integration/test_remote_ollama.py`)寫的 generate 串流行與錯誤本文
FAKE_GENERATE_LINE = {"model": "x", "created_at": "2026-11-10T09:00:00Z", "response": "a", "done": False}
FAKE_GENERATE_404 = {"error": "model 'x' not found"}
FAKE_PULL_ERROR = {"error": "pull model manifest: file does not exist"}
PULL_FIELD_TYPES = {"status": str, "digest": str, "total": int, "completed": int, "error": str}


# ---------------------------------------------------------------- 共用狀態


@dataclass
class Host:
    name: str
    none_name: str
    key_path: str
    tunnel: Tunnel = field(default_factory=Tunnel)
    created: bool = False
    ollama_started: bool = False
    stopped_by_case: bool = False
    tunnel_open: bool = False
    connection_lost: int = 0
    outputs: dict[str, str] = field(default_factory=dict)
    small_loaded_by_ro03: bool = False


def call(realrun, label: str, *args: str, timeout: float = COLAB_CALL_TIMEOUT):
    """`realrun.colab()`,逾時當成一次失敗的結果(exit None),原始輸出遮蔽後錄下。"""
    started = time.monotonic()
    try:
        result = realrun.colab(*args, timeout=timeout)
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
    except GuardViolation:
        raise
    except Exception as error:  # noqa: BLE001 - subprocess.TimeoutExpired 等,一律當成失敗留下紀錄
        stdout, stderr, code = "", f"{type(error).__name__}\n", None
    elapsed = time.monotonic() - started
    realrun.record_raw("host_adapter", f"$ colab {' '.join(args)} (exit {code}, {elapsed:.1f} 秒) [{label}]\n{stdout}{stderr}\n")
    return stdout, stderr, code, elapsed


def listed_names(realrun, label: str) -> list[str] | None:
    stdout, _, code, _ = call(realrun, label, "sessions")
    return parse_session_names(stdout) if code == 0 else None


def session_fields(stdout: str) -> dict[str, Any]:
    """`colab sessions` 用轉接層的 regex 解析:每台的欄位,與格式不符的行。"""
    rows, bad, blank = [], [], 0
    for line in stdout.splitlines():
        if not line.strip():
            blank += 1
            continue
        if line.startswith("[colab] "):
            continue
        m = SESSION_LINE.match(line)
        if m:
            rows.append(dict(zip(("name", "endpoint", "hardware", "shape", "variant"), m.groups(), strict=True)))
        else:
            bad.append(mask_urls(line)[:120])
    return {"rows": rows, "bad": bad, "blank": blank}


def last_result(stdout: str) -> dict[str, Any] | None:
    lines = [line for line in stdout.splitlines() if line.startswith(RESULT_PREFIX)]
    if not lines:
        return None
    try:
        value = json.loads(lines[-1][len(RESULT_PREFIX) :])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def cli_fields(kind: str, stdout: str) -> list[str]:
    """則8:轉接層會從這種輸出取出的欄位名稱。"""
    if kind == "version":
        return ["version"] if any(VERSION_LINE.match(line) for line in stdout.splitlines()) else []
    if kind == "usage":
        return sorted(k for k, p in USAGE_LINES.items() if any(p.match(line) for line in stdout.splitlines()))
    if kind.startswith("sessions"):
        parsed = session_fields(stdout)
        kinds = {"session:" + f for row in parsed["rows"] for f in row}
        if any(line.startswith("[colab] ") for line in stdout.splitlines()):
            kinds.add("notice")
        if parsed["bad"]:
            kinds.add("格式不符")
        return sorted(kinds)
    if kind == "new":
        lines = stdout.splitlines()
        return sorted({"creating" for line in lines if CREATING_LINE.match(line)} | ({"ready"} if SESSION_READY in stdout else set()))
    if kind.startswith("exec"):
        return sorted(last_result(stdout) or {})
    if kind.startswith("stop"):
        return [stop_output_of(stdout)]
    raise AssertionError(kind)


def exec_script(realrun, host: Host, label: str, script: str, remote_timeout: str, extra: tuple[str, ...], timeout: float):
    """`colab exec -f`,和轉接層同一個命令列;`Connection was lost` 時重跑一次(共用約定 6),並記下次數。"""
    args = ("exec", "-s", host.name, "-f", str(SCRIPTS / script), "--timeout", remote_timeout, *extra)
    stdout, stderr, code, elapsed = call(realrun, label, *args, timeout=timeout)
    total = elapsed
    if CONNECTION_LOST in stderr:
        host.connection_lost += 1
        stdout, stderr, code, elapsed = call(realrun, label + "(重跑)", *args, timeout=timeout)
        total += elapsed
        if CONNECTION_LOST in stderr:
            host.connection_lost += 1
    return stdout, stderr, code, total


# ---------------------------------------------------------------- fixture


@pytest.fixture(scope="module")
def host(realrun):
    name = adapter_session_name()
    assert name.startswith(TEST_PREFIX) and name.endswith("-adapter")
    state = Host(
        name=name,
        none_name=name.removesuffix("-adapter") + "-none",
        key_path=str(realrun.data / "ssh" / "id_ed25519"),
    )
    child_env = realrun.env()
    with pytest.MonkeyPatch.context() as mp:
        for key in ("HOME", "PATH", "COLAB_CLI_REQUEST_TIMEOUT"):
            mp.setenv(key, child_env[key])
        for key in ("CGB_FAKE_SCRIPT", "CGB_FAKE_LOG"):
            mp.delenv(key, raising=False)
        try:
            yield state
        finally:
            problems = teardown(realrun, state)
    if problems:
        pytest.fail("主機階段收尾有需要處理的事:" + ";".join(problems), pytrace=False)


def teardown(realrun, state: Host) -> list[str]:
    """不論成敗:關通道 → 這台還在就 stop 並回讀 → P3 → 再回讀一次確認沒有這台。"""
    problems: list[str] = []
    try:
        run(state.tunnel.close_tunnel(state.name))
    except Exception as error:  # noqa: BLE001
        problems.append(f"關通道失敗:{type(error).__name__}")
    names = listed_names(realrun, "收尾")
    # 讀不到清單時照樣 stop 一次:對不存在的名稱 stop 是安全的(只回 not found),讀不到卻不 stop 會留下殭屍
    if names is None or state.name in names:
        call(realrun, "收尾", "stop", "-s", state.name)
        deadline = time.monotonic() + STOP_GONE_DEADLINE
        while time.monotonic() < deadline:
            names = listed_names(realrun, "收尾回讀")
            if names is not None and state.name not in names:
                break
            time.sleep(POLL)
    problems += realrun.p3_cleanup()
    final = listed_names(realrun, "收尾確認")
    if final is None:
        problems.append(f"收尾後 colab sessions 失敗,無法確認 {state.name} 已結束,請到 Colab 網頁確認")
    elif any(n.startswith(TEST_PREFIX) for n in final):
        problems.append(f"收尾後 colab sessions 仍有 cgb-test- 執行環境:{[n for n in final if n.startswith(TEST_PREFIX)]}")
    return problems


def code_or_type(error: Exception) -> str:
    return error.code if isinstance(error, AdapterError) else type(error).__name__


def need(host: Host, *flags: str) -> None:
    missing = [f for f in flags if not getattr(host, f)]
    if missing:
        pytest.skip(f"前置沒成立({'、'.join(missing)}),列為未驗證")


def verdict(case: str, task: str, checks: dict[str, bool], numbers: str, threshold: str, extra: list[str]) -> None:
    failed = [k for k, ok in checks.items() if not ok]
    note = ";".join((["沒過:" + "、".join(failed)] if failed else []) + extra)
    write_measurement(case, task, numbers, threshold, not failed, note)
    assert not failed, note


# ---------------------------------------------------------------- US1-CLI-21(T077)開啟段


def test_us1_cli_21_open(realrun, host):
    out = host.outputs
    checks: dict[str, bool] = {}
    extra: list[str] = []

    # version
    stdout, _, _, _ = call(realrun, "則1", "version")
    out["version"] = stdout
    checks["則1"] = stdout.strip() == "Version: 0.7.5"

    # usage
    stdout, _, _, _ = call(realrun, "則2", "usage")
    out["usage"] = stdout
    checks["則2"] = all(any(p.match(line) for line in stdout.splitlines()) for p in USAGE_LINES.values())

    # sessions(開之前)
    stdout, _, code, _ = call(realrun, "則3", "sessions")
    out["sessions_before"] = stdout
    before = session_fields(stdout)
    if before["blank"]:
        extra.append(f"開之前的 sessions 有 {before['blank']} 個空行(轉接層略過)")
    if host.name in [r["name"] for r in before["rows"]]:
        pytest.fail(f"開之前 colab sessions 已經有 {host.name},不在這台上做量測", pytrace=False)

    # new
    stdout, stderr, code, new_elapsed = call(realrun, "則4", "new", "-s", host.name, "--gpu", ALLOWED_GPU, timeout=NEW_TIMEOUT)
    out["new"] = stdout
    host.created = True  # 不論輸出如何都當成可能已開,讓收尾去回讀
    ready_printed = SESSION_READY in stdout
    if "--high-mem ignored" in stderr:
        extra.append("new 的 stderr 有 --high-mem ignored(沒帶 --high-mem,不該出現)")

    # sessions(開之後)
    stdout, _, _, _ = call(realrun, "則4", "sessions")
    out["sessions_after"] = stdout
    after = session_fields(stdout)
    mine = [r for r in after["rows"] if r["name"] == host.name]
    checks["則3"] = not before["bad"] and not after["bad"]
    if before["bad"] or after["bad"]:
        extra.append(f"sessions 格式不符的行:{(before['bad'] + after['bad'])[:3]}")
    checks["則4"] = ready_printed and len(mine) == 1 and mine[0]["hardware"] == ALLOWED_GPU
    host.created = bool(mine) or host.created

    # 清單裡沒有這台就不執行 exec:CLI 對不認得的名稱可能自己另開一台(Q64 的同類風險)
    start_result: dict[str, Any] | None = None
    probe: dict[str, Any] | None = None
    start_elapsed = probe_elapsed = 0.0
    if mine:
        # exec 啟動 Ollama(和轉接層 start_ollama 同一個命令列)
        stdout, stderr, _, start_elapsed = exec_script(
            realrun, host, "則5 啟動 Ollama", "start_ollama.py", "240", START_OLLAMA_ENV, START_OLLAMA_TIMEOUT
        )
        out["exec_start"] = stdout
        start_result = last_result(stdout)
        host.ollama_started = isinstance(start_result, dict) and start_result.get("ok") is True
        if start_result is None and stderr.strip():
            extra.append(f"啟動 Ollama 沒有結果行,stderr 最後一行:{mask_urls(stderr.strip().splitlines()[-1])[:160]}")

        # exec 讀資源(和轉接層 probe_resources 同一個命令列)
        stdout, _, _, probe_elapsed = exec_script(realrun, host, "則5 讀資源", "probe_resources.py", "30", (), PROBE_TIMEOUT)
        out["exec_probe"] = stdout
        probe = last_result(stdout)
    else:
        extra.append("sessions 沒有列出這台,不執行 exec")
    vram = probe.get("vramTotalBytes") if isinstance(probe, dict) else None
    checks["則5"] = (
        isinstance(start_result, dict) and start_result.get("ok") is True
        and isinstance(probe, dict) and probe.get("ok") is True
        and isinstance(vram, int) and vram > 0
    )  # fmt: skip

    # stop 不存在的名稱
    stdout, stderr, code, _ = call(realrun, "則6", "stop", "-s", host.none_name)
    out["stop_none"] = stdout
    checks["則6"] = "not found" in stdout and code == 0
    if "not found" in stderr and "not found" not in stdout:
        extra.append("not found 印在 stderr,不是 stdout")

    extra.append(f"Connection was lost {host.connection_lost} 次")
    numbers = (
        f"new {new_elapsed:.1f} 秒;啟動 Ollama {start_elapsed:.1f} 秒"
        f"(ollamaVersion {start_result.get('ollamaVersion') if start_result else None}、"
        f"alreadyRunning {start_result.get('alreadyRunning') if start_result else None}"
        # 失敗時留下 stage 與 detail(write_measurement 會先遮蔽網址);原始輸出隨暫存目錄刪除,這裡是唯一的線索
        f"、stage {start_result.get('stage') if start_result else None}"
        f"、detail {str(start_result.get('detail'))[:200] if start_result else None});"
        f"讀資源 {probe_elapsed:.1f} 秒(vramTotalBytes {vram}、gpuName {probe.get('gpuName') if probe else None});"
        f"stop 不存在的名稱 exit {code}、stopOutput {stop_output_of(out['stop_none'])}"
    )
    verdict(
        "US1-CLI-21(開啟段)", "T077", checks, numbers,
        "則1 Version: 0.7.5;則2 usage 三行;則3 sessions 每行合格式;則4 READY 且列出 T4;則5 ok 且 vram>0;則6 not found 且 exit 0",
        extra,
    )  # fmt: skip


# ---------------------------------------------------------------- US2-RO-03(T174)


async def ro03_measure(host: Host, port: int) -> dict[str, Any]:
    got: dict[str, Any] = {}
    await host.tunnel.ensure_key(host.key_path)
    opened = await host.tunnel.open_tunnel(host.name, host.key_path, port)
    host.tunnel_open = True
    base = opened["baseUrl"]
    got["tunnel_ms"] = opened["elapsedMs"]
    transport = RecordingTransport()
    remote = RemoteOllama(transport=transport)
    try:
        got["version"] = await remote.get_version(base)
        got["tags_before"] = await remote.list_local_models(base_url=base)

        started = time.monotonic()
        got["pull_small"] = [line async for line in await remote.pull_model(base_url=base, model=SMALL)]
        got["pull_small_s"] = time.monotonic() - started
        got["pull_small_raw"] = ndjson(bytes(transport.last("POST", "/api/pull").body))

        try:
            [line async for line in await remote.pull_model(base_url=base, model=MISSING)]
            got["pull_missing"] = "沒有丟錯誤"
        except AdapterError as error:
            got["pull_missing"] = error.code
            got["pull_missing_message"] = error.message
        missing_exchange = transport.last("POST", "/api/pull")
        got["pull_missing_status"] = missing_exchange.status
        got["pull_missing_raw"] = ndjson(bytes(missing_exchange.body))

        body = {"model": SMALL, "prompt": "你好", "keep_alive": KEEP_LOADED, "options": {"num_predict": 8}}
        started = time.monotonic()
        got["gen_plain"] = [line async for line in await remote.generate(base, {**body, "stream": False})]
        got["gen_plain_s"] = time.monotonic() - started
        started = time.monotonic()
        got["gen_stream"] = [line async for line in await remote.generate(base, {**body, "stream": True})]
        got["gen_stream_s"] = time.monotonic() - started
        got["gen_stream_raw"] = ndjson(bytes(transport.last("POST", "/api/generate").body))

        got["ps"] = await remote.list_loaded_models(base_url=base)

        async with httpx.AsyncClient(base_url=base, transport=transport, timeout=120) as client:
            chat = await client.post(
                "/api/chat",
                json={"model": SMALL, "messages": [{"role": "user", "content": "你好"}], "stream": False,
                      "keep_alive": KEEP_LOADED, "options": {"num_predict": 8}},
                headers={"Origin": LAN_ORIGIN},
            )  # fmt: skip
        got["chat_status"] = chat.status_code
        got["chat_acao"] = chat.headers.get("access-control-allow-origin")

        try:
            await remote.generate(base, {"model": LARGE, "prompt": "你好", "stream": False, "options": {"num_predict": 8}})
            got["gen_large"] = "沒有丟錯誤"
        except AdapterError as error:
            got["gen_large"] = error.code
        large_exchange = transport.last("POST", "/api/generate")
        got["gen_large_status"] = large_exchange.status
        got["gen_large_body"] = large_exchange.json() if large_exchange.body else {}
        got["tags_after"] = await remote.list_local_models(base_url=base)
    finally:
        await transport.close_inner()
        await host.tunnel.close_tunnel(host.name)
        host.tunnel_open = False
    return got


def pull_line_problems(lines: list[Any]) -> list[str]:
    problems = []
    for i, line in enumerate(lines, 1):
        if not isinstance(line, dict):
            problems.append(f"第 {i} 行不是物件")
            continue
        for key, kind in PULL_FIELD_TYPES.items():
            if key in line and not isinstance(line[key], kind):
                problems.append(f"第 {i} 行的 {key} 型別不符")
            if kind is int and isinstance(line.get(key), int) and line[key] < 0:
                problems.append(f"第 {i} 行的 {key} 小於 0")
    return problems


def model_names(listing: dict[str, Any]) -> list[str]:
    return [m.get("name") for m in listing.get("models", [])]


def test_us2_ro_03(realrun, host):
    need(host, "ollama_started")
    port = free_loopback_port()
    try:
        got = run(ro03_measure(host, port))
    except (AdapterError, httpx.HTTPError) as error:
        write_measurement("US2-RO-03", "T174", "—", "—", None, f"量測中斷:{code_or_type(error)}")
        pytest.fail(f"US2-RO-03 量測中斷:{code_or_type(error)}", pytrace=False)
    realrun.record_raw("us2_ro_03", json.dumps({k: v for k, v in got.items() if not k.endswith("_raw")}, ensure_ascii=False, default=str))
    extra: list[str] = []

    c1 = isinstance(got["version"].get("version"), str)
    raw = got["pull_small_raw"]
    problems = pull_line_problems(raw)
    unknown = sorted({k for line in raw if isinstance(line, dict) for k in line} - PULL_FIELD_TYPES.keys())
    if unknown:
        extra.append(f"pull 行有 PullProgress 沒列的欄位:{unknown}")
    c2 = not problems and bool(raw) and raw[-1] == {"status": "success"}
    if problems:
        extra.append("pull 行不符:" + "、".join(problems[:5]))

    missing_errors = [line["error"] for line in got["pull_missing_raw"] if isinstance(line, dict) and "error" in line]
    c3 = (
        got["pull_missing_status"] == 200
        and any("file does not exist" in e for e in missing_errors)
        and got["pull_missing"] == "OLLAMA_NOT_FOUND"
    )
    if not c3:
        extra.append(f"不存在的模型:HTTP {got['pull_missing_status']}、error {missing_errors[:1]}、轉接層 {got['pull_missing']}")

    c4 = (
        len(got["gen_plain"]) == 1 and got["gen_plain"][0].get("done") is True
        and bool(got["gen_stream"]) and got["gen_stream"][-1].get("done") is True
    )  # fmt: skip
    c5 = SMALL in model_names(got["ps"])
    host.small_loaded_by_ro03 = c5
    c6 = got["chat_status"] == 200
    c7 = got["gen_large_status"] == 404 and got["gen_large"] == "OLLAMA_NOT_FOUND" and LARGE not in model_names(got["tags_after"])

    # 則8:替身劇本的欄位都出現在真的回應裡(真的回應多出的欄位只記錄)
    stream_lines = [line for line in got["gen_stream_raw"] if isinstance(line, dict)]
    pairs = {
        "version": (["version"], field_names([got["version"]])),
        "pull 進度行": (field_names([PULL_LAYER_50]), field_names([line for line in raw if isinstance(line, dict) and "total" in line])),
        "pull error 行": (
            field_names([FAKE_PULL_ERROR]),
            field_names([line for line in got["pull_missing_raw"] if isinstance(line, dict) and "error" in line]),
        ),
        "generate 串流行": (field_names([FAKE_GENERATE_LINE]), field_names(stream_lines[:-1] or stream_lines)),
        "generate 404": (field_names([FAKE_GENERATE_404]), field_names([got["gen_large_body"]])),
        "tags 的模型": (field_names(TAGS_TWO_MODELS["models"]), field_names(got["tags_after"].get("models", []))),
        "ps 的模型": (field_names(PS_ONE_MODEL["models"]), field_names(got["ps"].get("models", []))),
        "details": (
            field_names([m["details"] for m in TAGS_TWO_MODELS["models"]]),
            field_names([m.get("details", {}) for m in got["tags_after"].get("models", [])]),
        ),
    }
    missing_fields = {k: sorted(set(fake) - set(live)) for k, (fake, live) in pairs.items() if set(fake) - set(live)}
    surplus = {k: sorted(set(live) - set(fake)) for k, (fake, live) in pairs.items() if set(live) - set(fake)}
    c8 = not missing_fields
    if missing_fields:
        extra.append(f"替身有、真的沒有的欄位:{missing_fields}")
    if surplus:
        extra.append(f"真的多出的欄位(只記錄):{surplus}")
    extra.append(f"帶 Origin 的 chat:Access-Control-Allow-Origin {got['chat_acao']!r}")

    numbers = (
        f"通道就緒 {got['tunnel_ms']} ms;遠端 Ollama {got['version'].get('version')};"
        f"pull {SMALL} {got['pull_small_s']:.1f} 秒、{len(raw)} 行;generate 非串流 {got['gen_plain_s']:.2f} 秒、"
        f"串流 {got['gen_stream_s']:.2f} 秒 {len(got['gen_stream'])} 行;chat HTTP {got['chat_status']};"
        f"{LARGE} generate HTTP {got['gen_large_status']} → {got['gen_large']}"
    )
    verdict(
        "US2-RO-03", "T174",
        {"則1": c1, "則2": c2, "則3": c3, "則4": c4, "則5": c5, "則6": c6, "則7": c7, "則8": c8},
        numbers,
        "則2 每行合 PullProgress、最後 success;則3 HTTP 200 + file does not exist + OLLAMA_NOT_FOUND;"
        "則6 chat 200;則7 404 + OLLAMA_NOT_FOUND;則8 替身欄位都在",
        extra,
    )  # fmt: skip


# ---------------------------------------------------------------- US1-TUN-10(T109)


def own_zombies() -> list[int]:
    """這個 pytest 行程底下已結束、還沒被回收的子行程。"""
    me, found = os.getpid(), []
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        try:
            with open(f"/proc/{entry.name}/stat", encoding="utf-8", errors="replace") as f:
                fields = f.read().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if fields[0] == "Z" and int(fields[1]) == me:
            found.append(int(entry.name))
    return found


def cmdline_of(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return ""


async def tun10_measure(host: Host, port: int) -> dict[str, Any]:
    tunnel, got = host.tunnel, {"codes": [], "forwards": []}

    def keep_forward() -> None:
        forward = tunnel._forwards.get(host.name)  # 只為了讀 stderr(則7);不改它
        if forward is not None and all(forward is not f for f in got["forwards"]):
            got["forwards"].append(forward)

    await tunnel.ensure_key(host.key_path)
    started = time.monotonic()
    try:
        opened = await tunnel.open_tunnel(host.name, host.key_path, port)
        got["first_ms"] = opened["elapsedMs"]
    except AdapterError as error:
        got["first_error"] = error.code
        got["first_ms"] = int((time.monotonic() - started) * 1000)
        keep_forward()
        return got
    keep_forward()
    host.tunnel_open = True
    base = opened["baseUrl"]

    got["health"] = []
    for _ in range(3):
        try:
            got["health"].append((await tunnel.check_health(host.name))["latencyMs"])
        except AdapterError as error:
            got["health"].append(error.code)
    got["ps_before"] = model_names(await RemoteOllama().list_loaded_models(base_url=base))

    targets = [pid for pid in residual_ssh_pids() if host.name in cmdline_of(pid)]
    got["killed"] = len(targets)
    for pid in targets:
        os.kill(pid, signal.SIGKILL)
    killed_at = time.monotonic()

    try:
        result = await tunnel.check_health(host.name)
        got["after_kill"] = "healthy" if result.get("healthy") else repr(result)
    except AdapterError as error:
        got["after_kill"] = error.code

    deadline = killed_at + REOPEN_DEADLINE
    got["reopened"] = False
    while time.monotonic() < deadline:
        try:
            await tunnel.open_tunnel(host.name, host.key_path, port)
            keep_forward()
            got["reopened"] = True
            break
        except AdapterError as error:
            keep_forward()
            got["codes"].append(error.code)
        await asyncio.sleep(REOPEN_INTERVAL)
    got["reopen_s"] = time.monotonic() - killed_at

    if got["reopened"]:
        got["ps_after"] = model_names(await RemoteOllama().list_loaded_models(base_url=base))
    closed = await tunnel.close_tunnel(host.name)
    host.tunnel_open = False
    got["closed"] = closed
    got["port_listening"] = port_listening(port)
    got["zombies"] = own_zombies()
    # 量測之後才做:被殺掉的那條 ssh 留下的 ProxyCommand(同一個 process group)若還在,一併結束並回收
    got["leftover_groups"] = sum(reap_group(f.process) for f in got["forwards"])
    return got


def reap_group(process) -> int:
    """對已結束的 ssh 的 process group 送 SIGKILL 並回收 ssh;group 裡還有行程時回 1。"""
    try:
        os.killpg(process.pid, signal.SIGKILL)
        found = 1
    except ProcessLookupError:
        found = 0
    with contextlib.suppress(Exception):
        process.wait(timeout=2)
    return found


def classify_lines(lines: list[str]) -> list[str]:
    """則7:比對不到 `x-stderr-patterns` 任何一條、也不是 `x-stderr-ignore` 的行(遮蔽後)。"""
    unknown = []
    for line in lines:
        if not line.strip() or line.startswith(STDERR_IGNORE):
            continue
        if not any(pattern in line for pattern, _ in STDERR_PATTERNS):
            unknown.append(mask_urls(mask_secrets(line))[:160])
    return unknown


def test_us1_tun_10(realrun, host):
    need(host, "ollama_started")
    port = free_loopback_port()
    got = run(tun10_measure(host, port))
    lines = [line for forward in got["forwards"] for line in list(forward.stderr_lines)]
    realrun.record_raw("us1_tun_10", "\n".join(mask_urls(mask_secrets(line)) for line in lines) + "\n")
    names = listed_names(realrun, "US1-TUN-10 則6")
    extra: list[str] = []

    if "first_error" in got:
        numbers = f"第一次建立失敗 {got['first_error']}({got['first_ms']} ms)"
        write_measurement("US1-TUN-10", "T109", numbers, "則1 30 秒", False, "其餘未驗證")
        pytest.fail(f"第一次建立通道失敗:{got['first_error']}", pytrace=False)

    c1 = got["first_ms"] <= 30_000
    c2 = got["after_kill"] != "healthy"
    c3 = got["reopened"] and got["reopen_s"] <= REOPEN_DEADLINE
    c4 = got["reopened"] and SMALL in got.get("ps_after", [])
    if SMALL not in got["ps_before"]:
        extra.append(f"殺掉之前 /api/ps 就沒有 {SMALL}(US2-RO-03 {'有' if host.small_loaded_by_ro03 else '沒有'}載入)")
    c5 = not got["port_listening"] and not got["zombies"]
    c6 = names is not None and host.name in names
    unknown = classify_lines(lines)
    c7 = not unknown
    if unknown:
        extra.append(f"比對不到的 stderr 行:{unknown[:5]}")
    if got["killed"] != 1:
        extra.append(f"殺掉的 ssh 行程數是 {got['killed']}")

    numbers = (
        f"第一次建立 {got['first_ms']} ms;健康檢查 {got['health']};殺掉後健康檢查 {got['after_kill']};"
        f"重新建立 {'成功' if got['reopened'] else '沒成功'},等了 {got['reopen_s']:.1f} 秒,中間代碼 {got['codes'] or '無'};"
        f"關閉 {got['closed']};port 仍在聽 {got['port_listening']};defunct {got['zombies']};stderr {len(lines)} 行;"
        f"量測後另外收掉的殘留 group {got.get('leftover_groups', 0)} 個"
    )
    verdict(
        "US1-TUN-10", "T109",
        {"則1": c1, "則2": c2, "則3": c3, "則4": c4, "則5": c5, "則6": c6, "則7": c7},
        numbers,
        "則1 ≤ 30 秒;則2 不是健康;則3 ≤ 120 秒;則4 /api/ps 有 qwen2.5:0.5b;則5 port 不聽、無 defunct;則6 仍列出;則7 stderr 都認得",
        extra,
    )  # fmt: skip


# ---------------------------------------------------------------- US1-CLI-21(T077)結束段


def test_us1_cli_21_stop(realrun, host):
    need(host, "created")
    out = host.outputs
    checks: dict[str, bool] = {}
    extra: list[str] = []

    stopped_at = datetime.now()
    stdout, _, code, stop_elapsed = call(realrun, "則7", "stop", "-s", host.name)
    out["stop"] = stdout
    started = time.monotonic()
    gone_after: float | None = None
    last_sessions = ""
    while time.monotonic() - started <= STOP_GONE_DEADLINE:
        s_out, _, s_code, _ = call(realrun, "則7 回讀", "sessions")
        if s_code == 0:
            last_sessions = s_out
            if host.name not in parse_session_names(s_out):
                gone_after = time.monotonic() - started
                break
        time.sleep(POLL)
    out["sessions_end"] = last_sessions
    host.stopped_by_case = gone_after is not None
    checks["則7"] = gone_after is not None
    end_bad = session_fields(last_sessions)["bad"]
    if end_bad:
        extra.append(f"結束後的 sessions 有格式不符的行:{end_bad[:3]}")

    # 則8:替身劇本與真輸出,轉接層取出的欄位名稱
    fakes = {
        "version": "Version: 0.7.5\n",
        "usage": USAGE_NEGATIVE_BALANCE_WITH_NOTICE,
        "sessions_after": SESSIONS_WITH_0001["stdout"],
        "new": NEW_READY["stdout"],
        "exec_start": START_OLLAMA_OK,
        "exec_probe": PROBE_OK,
        "stop_none": FAKE_STOP_NOT_FOUND,
        "stop": STOP_TERMINATED["stdout"],
    }
    if not session_fields(last_sessions)["rows"]:
        fakes["sessions_end"] = NO_SESSIONS["stdout"]
    diffs = []
    for kind, fake in fakes.items():
        if kind not in out:
            diffs.append(f"{kind}:這次沒有錄到")
            continue
        fake_fields, live_fields = cli_fields(kind, fake), cli_fields(kind, out[kind])
        if kind.startswith("sessions"):
            # 真的清單可能另有使用者自己的執行環境或 [colab] 訊息;只比替身寫到的那幾種
            live_fields = [f for f in live_fields if f in fake_fields or f == "格式不符"]
        if fake_fields != live_fields:
            diffs.append(f"{kind}:替身 {fake_fields},真的 {live_fields}")
    checks["則8"] = not diffs
    extra += diffs

    numbers = (
        f"{stopped_at:%H:%M:%S} stop(exit {code},{stop_elapsed:.1f} 秒,stopOutput {stop_output_of(stdout)});"
        f"回讀不再列出:{f'{gone_after:.1f} 秒' if gone_after is not None else f'{STOP_GONE_DEADLINE} 秒內仍列出'};"
        f"Connection was lost 共 {host.connection_lost} 次"
    )
    verdict(
        "US1-CLI-21(結束段)", "T077", checks, numbers,
        "則7 stop 後 60 秒內 sessions 不再列出(SC-003);則8 替身與真輸出的欄位名稱相同",
        extra,
    )  # fmt: skip
