"""G-01(tasks.md T233):`HuggingFaceHub` 對真的 huggingface.co 的搜尋、展開與 manifest,和替身的形狀一致(004 testplan.md § 7.2)。

真的 `HuggingFaceHub()` 連 https://huggingface.co,外面包一層錄下每次往返(含送出的標頭)的 transport;依序
`search_models("qwen2.5-0.5b")`(有 cursor 再取一頁)、`list_quants("bartowski","SmolLM2-135M-Instruct-GGUF")`、
`get_manifest(...,"Q4_K_L")`、`get_manifest("google","gemma-3-1b-it-qat-q4_0-gguf","Q4_0")`、`search_models("zzzqqqnonexist")`。

標 `realrun`,預設排除;不放 `tests/realrun/`,不經會執行 `colab usage` 的 `realrun` fixture。
護欄(testplan.md § 7.0):只送不帶 token、不帶 Cookie 的唯讀 GET,同時最多 4 個(轉接層的上限)、不重試,
整次最多 40 個請求(超過就由 transport 擋下);httpx 不讀環境變數與 `~/.netrc`(`trust_env=False`);
錄到的回應只寫 pytest 暫存資料夾;不碰 Colab、不執行 `colab`;約 30 個 GET、約 10 秒;連不到就標無法實跑。
對方改版時樣本會變,失敗先看暫存資料夾裡錄到的回應再判斷。
判定者:腳本;樣本:`bartowski/SmolLM2-135M-Instruct-GGUF`、`google/gemma-3-1b-it-qat-q4_0-gguf`、關鍵字 `qwen2.5-0.5b`。
執行:`uv run pytest -m realrun tests/integration/test_004_g_01.py`
"""

import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from cgb.adapters.errors import AdapterError
from cgb.adapters.huggingface import HuggingFaceHub
from realrun.conftest import REPO_ROOT, GuardViolation, write_measurement

pytestmark = pytest.mark.realrun

CASE, TASK = "G-01", "T233"
MEASUREMENTS = REPO_ROOT / "specs" / "004-chat-hf-curated-queue" / "measurements.md"
MAX_REQUESTS = 40
SMOL = ("bartowski", "SmolLM2-135M-Instruct-GGUF")
GEMMA = ("google", "gemma-3-1b-it-qat-q4_0-gguf")
Q4_K_M_BYTES = 105_455_145
THRESHOLD = (
    "則1:第一頁沒有例外、≥ 1 筆、每筆 id 含 /;則2:有 Link rel=next 時 cursor 非空;則3:Q4_K_M 大小 105,455,145;"
    "則4:沒有列出 Q4_K_L、Q5_K_L;則5:Q4_K_L 的 manifest 丟 HF_QUANT_UNAVAILABLE;則6:gemma 的 manifest 丟 HF_AUTH_REQUIRED;"
    "則7:zzzqqqnonexist 回 0 筆、沒有例外;則8:每個請求都沒有 Authorization、Cookie;則9:請求總數 ≤ 40"
)


def ensure_measurements(path: Path = MEASUREMENTS) -> Path:
    """004 的 measurements.md 還沒有時先寫好標頭;`write_measurement` 自己建的標頭是 001 的標題。"""
    if not path.exists():
        path.write_text(
            "# 實跑量測結果:對話、Hugging Face、精選清單與下載佇列\n\n"
            "由各案例的測試以 `tests/realrun/conftest.py` 的 `write_measurement` 寫入(tasks.md T232~T237);"
            "護欄見 `testplan.md` § 7.0 與 § 7.2 各案例的「副作用與護欄」。\n\n"
            "| 時間 | 案例 | 任務 | 數字 | 門檻 | 結果 | 備註 |\n"
            "|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    return path


@dataclass
class Sent:
    method: str
    path: str
    request_headers: list[str]
    status: int
    link: str | None
    body: bytes = b""


@dataclass
class HeaderRecorder(httpx.AsyncBaseTransport):
    """包住真傳輸:留下每個請求的方法、路徑、送出的標頭名稱與回應;只放行 GET,最多 40 個。"""

    sent: list[Sent] = field(default_factory=list)
    inner: httpx.AsyncHTTPTransport = field(default_factory=lambda: httpx.AsyncHTTPTransport(trust_env=False))

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            raise GuardViolation(f"G-01 只送 GET,收到 {request.method}")
        if len(self.sent) >= MAX_REQUESTS:
            raise GuardViolation(f"G-01 最多送 {MAX_REQUESTS} 個請求")
        record = Sent(request.method, request.url.path, [k.lower() for k in request.headers.keys()], 0, None)
        self.sent.append(record)
        response = await self.inner.handle_async_request(request)
        body = await response.aread()
        record.status, record.link, record.body = response.status_code, response.headers.get("link"), body
        # `aread()` 已經解壓,交回時拿掉壓縮與長度標頭,免得轉接層再解一次
        headers = [(k, v) for k, v in response.headers.multi_items() if k.lower() not in ("content-encoding", "content-length")]
        return httpx.Response(response.status_code, headers=headers, content=body, request=request)

    async def aclose(self) -> None:
        return None


def reachable(host: str = "huggingface.co") -> bool:
    try:
        with socket.create_connection((host, 443), timeout=5):
            return True
    except OSError:
        return False


async def outcome(call: Any) -> tuple[Any, str | None]:
    try:
        return await call, None
    except AdapterError as error:
        return None, error.code


async def test_g_01(tmp_path: Path) -> None:
    if not reachable():
        write_measurement(CASE, TASK, "連不到 huggingface.co:443", THRESHOLD, None, "無法實跑", path=ensure_measurements())
        pytest.skip("無法實跑:連不到 huggingface.co")

    # Arrange
    recorder = HeaderRecorder()
    hub = HuggingFaceHub(transport=recorder)

    # Act
    try:
        first, first_error = await outcome(hub.search_models("qwen2.5-0.5b"))
        first_link = recorder.sent[-1].link if recorder.sent else None
        second, second_error = (None, None)
        if first and first["nextCursor"]:
            second, second_error = await outcome(hub.search_models("qwen2.5-0.5b", cursor=first["nextCursor"]))
        quants, quants_error = await outcome(hub.list_quants(*SMOL))
        _, q4kl_error = await outcome(hub.get_manifest(*SMOL, "Q4_K_L"))
        _, gemma_error = await outcome(hub.get_manifest(*GEMMA, "Q4_0"))
        none, none_error = await outcome(hub.search_models("zzzqqqnonexist"))
    finally:
        await recorder.inner.aclose()
    (tmp_path / "g_01_exchanges.txt").write_text(
        "".join(
            f"{s.method} {s.path} → {s.status} link={s.link!r} 送出標頭={s.request_headers}\n"
            f"{s.body[:2000].decode(errors='replace')}\n"
            for s in recorder.sent
        ),
        encoding="utf-8",
    )

    # 量到的數字
    items = first["items"] if first else []
    has_next = first_link is not None and 'rel="next"' in first_link
    sizes = {q["quant"]: q["sizeBytes"] for q in quants or []}
    leaked = sorted({h for s in recorder.sent for h in s.request_headers if h in ("authorization", "cookie")})
    checks = {
        "則1": first_error is None and len(items) >= 1 and all("/" in item["id"] for item in items),
        "則2": (not has_next) or bool(first and first["nextCursor"]),
        "則3": sizes.get("Q4_K_M") == Q4_K_M_BYTES,
        "則4": quants_error is None and "Q4_K_L" not in sizes and "Q5_K_L" not in sizes,
        "則5": q4kl_error == "HF_QUANT_UNAVAILABLE",
        "則6": gemma_error == "HF_AUTH_REQUIRED",
        "則7": none_error is None and none is not None and none["items"] == [],
        "則8": not leaked,
        "則9": len(recorder.sent) <= MAX_REQUESTS,
    }
    numbers = [
        f"第一頁 {len(items)} 筆(丟出 {first_error or '無'}),id 都含 / {'是' if checks['則1'] else '否'}",
        f"第一頁有 Link rel=next {'是' if has_next else '否'},cursor 非空 {'是' if first and first['nextCursor'] else '否'};"
        f"第二頁 {len(second['items']) if second else '沒取'} 筆(丟出 {second_error or '無'})",
        f"list_quants {len(sizes)} 個版本(丟出 {quants_error or '無'}):{', '.join(f'{k} {v:,}' for k, v in sizes.items())}",
        f"Q4_K_L manifest 丟出 {q4kl_error or '無'};gemma manifest 丟出 {gemma_error or '無'}",
        f"zzzqqqnonexist {len(none['items']) if none else '—'} 筆(丟出 {none_error or '無'})",
        f"請求 {len(recorder.sent)} 個,方法 {sorted({s.method for s in recorder.sent})},"
        f"帶 Authorization/Cookie 的 {len(leaked)} 個",
    ]
    failed = [name for name, ok in checks.items() if not ok]
    note = ("沒過:" + "、".join(failed) + ";" if failed else "") + "只送不帶 token、不帶 Cookie 的唯讀 GET,trust_env=False"
    write_measurement(CASE, TASK, ";".join(numbers), THRESHOLD, not failed, note, path=ensure_measurements())

    # Assert
    assert not failed, ";".join(numbers)
