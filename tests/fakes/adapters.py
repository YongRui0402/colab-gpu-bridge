"""五個轉接層的替身(plan.md Q96;research.md R12:替身只放在 adapter 這一層)。

方法名照規格檔 operationId 的 snake_case(以 tasks.md T004 列出的名稱為準)。每個方法都是 `FakeMethod`:

- 設定回傳:`fake.list_sessions.returns([...])`;丟錯:`fake.get_usage.raises("AUTH_REQUIRED")`
- 依序回傳(用完才回到預設):`fake.check_health.then(AdapterError("TUNNEL_UNREACHABLE", "…"), {...})`
- 依參數回傳:`fake.get_manifest.when(name="qwen2.5", tag="7b").returns({...})`,或傳入判斷函式
- 等測試放行:`gate = fake.create_session.gate()`;測試呼叫 `gate.release()` 前,呼叫停在記錄參數之後
- 呼叫紀錄:`fake.create_session.calls`(`Call.args`、`Call.kwargs`)、`call_count`

沒有設定任何回傳的方法被呼叫時丟 `FakeNotConfigured`,不會默默回 None 讓測試誤綠。
串流的方法(`pull_model`、`generate`、`chat`)回傳非同步迭代器:設定的 list 逐項產出,
項目是 `Gate` 就等放行,是 `AdapterError` 就在那裡丟出(模擬串流中斷)。
"""

import inspect
import threading
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from cgb.adapters.colab_cli import ColabControl
from cgb.adapters.errors import AdapterError
from cgb.adapters.google_oauth import GoogleOAuth
from cgb.adapters.huggingface import HuggingFaceHub
from cgb.adapters.model_library import ModelLibrary
from cgb.adapters.remote_ollama import RemoteOllama
from cgb.adapters.tunnel import Tunnel

from .gate import Gate

_UNSET = object()


class FakeNotConfigured(AssertionError):
    """測試沒有替這個方法設定回傳值就呼叫了它。"""


@dataclass(frozen=True)
class Call:
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


@dataclass
class _Outcome:
    value: Any = None
    error: AdapterError | None = None
    func: Callable[..., Any] | None = None

    def resolve(self, call: Call) -> Any:
        if self.error is not None:
            raise self.error
        if self.func is not None:
            return self.func(*call.args, **call.kwargs)
        return self.value


def _outcome_of(item: Any) -> _Outcome:
    if isinstance(item, AdapterError):
        return _Outcome(error=item)
    return _Outcome(value=item)


@dataclass
class _Rule:
    matcher: Callable[[Call], bool]
    outcome: _Outcome | None = None


class _When:
    def __init__(self, rule: _Rule) -> None:
        self._rule = rule

    def returns(self, value: Any) -> None:
        self._rule.outcome = _Outcome(value=value)

    def raises(self, code: str, message: str = "", stderr_last_line: str | None = None) -> None:
        self._rule.outcome = _Outcome(error=AdapterError(code, message or code, stderr_last_line))


@dataclass
class FakeMethod:
    name: str
    streaming: bool = False
    calls: list[Call] = field(default_factory=list)
    _default: _Outcome | None = None
    _queue: list[_Outcome] = field(default_factory=list)
    _rules: list[_Rule] = field(default_factory=list)
    _gates: list[Gate] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    # 真 adapter 同名方法的簽章(不含 self);有的話呼叫時照它綁定參數,少帶、多帶都丟 TypeError(testplan § G-09)
    signature: inspect.Signature | None = None

    def __post_init__(self) -> None:
        if self.signature is not None:
            # `inspect.signature(替身方法)` 和真方法相同
            self.__signature__ = self.signature

    # ---- 測試端的設定 ----

    def returns(self, value: Any) -> None:
        with self._lock:
            self._default = _Outcome(value=value)

    def raises(self, code: str, message: str = "", stderr_last_line: str | None = None) -> None:
        with self._lock:
            self._default = _Outcome(error=AdapterError(code, message or code, stderr_last_line))

    def side_effect(self, func: Callable[..., Any]) -> None:
        """以函式決定回傳;函式收到與方法相同的參數,丟出的例外原樣傳出。"""
        with self._lock:
            self._default = _Outcome(func=func)

    def then(self, *items: Any) -> None:
        """排入一次性的結果,依序用掉;`AdapterError` 的項目會被丟出。"""
        with self._lock:
            self._queue.extend(_outcome_of(item) for item in items)

    def when(self, predicate: Callable[[Call], bool] | None = None, /, **kwargs: Any) -> _When:
        """依參數決定回傳:關鍵字參數逐一比對 `Call.kwargs`,或給一個收 `Call` 的判斷函式。"""
        if predicate is None:
            def predicate(call: Call) -> bool:
                return all(call.kwargs.get(k, _UNSET) == v for k, v in kwargs.items())
        rule = _Rule(matcher=predicate)
        with self._lock:
            self._rules.append(rule)
        return _When(rule)

    def gate(self) -> Gate:
        """之後的每一次呼叫都在記錄參數後停住,直到測試放行。"""
        gate = Gate()
        with self._lock:
            self._gates.append(gate)
        return gate

    def reset_calls(self) -> None:
        with self._lock:
            self.calls.clear()

    @property
    def call_count(self) -> int:
        with self._lock:
            return len(self.calls)

    @property
    def last_call(self) -> Call:
        with self._lock:
            if not self.calls:
                raise AssertionError(f"{self.name} 一次都沒被呼叫")
            return self.calls[-1]

    # ---- 被測程式端的呼叫 ----

    def _pick(self, call: Call) -> _Outcome:
        with self._lock:
            for rule in self._rules:
                if rule.outcome is not None and rule.matcher(call):
                    return rule.outcome
            if self._queue:
                return self._queue.pop(0)
            if self._default is not None:
                return self._default
        raise FakeNotConfigured(f"{self.name} 沒有設定回傳值就被呼叫:args={call.args!r} kwargs={call.kwargs!r}")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self.signature is not None:
            # 和呼叫真方法一樣,參數不對在呼叫當下就丟 TypeError
            self.signature.bind(*args, **kwargs)
        return self.invoke(*args, **kwargs)

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        call = Call(args=args, kwargs=dict(kwargs))
        with self._lock:
            self.calls.append(call)
            gates = list(self._gates)
        for gate in gates:
            await gate.pass_async()
        result = self._pick(call).resolve(call)
        if inspect.isawaitable(result):
            # `side_effect` 給的是 async 函式時等它跑完(research.md R4);同步的回傳值、`raises`、`then`、`gate` 行為不變
            result = await result
        if self.streaming:
            return _stream(result)
        return result


async def _stream(items: Any) -> AsyncIterator[Any]:
    for item in items:
        if isinstance(item, Gate):
            await item.pass_async()
        elif isinstance(item, AdapterError):
            raise item
        else:
            yield item


def _real_signature(real: type | None, name: str) -> inspect.Signature | None:
    """真 adapter 同名方法去掉 `self` 的簽章;真 adapter 沒有這個方法時是 None(照單全收,Q160(a))。"""
    method = getattr(real, name, None) if real is not None else None
    if method is None:
        return None
    signature = inspect.signature(method)
    return signature.replace(parameters=list(signature.parameters.values())[1:])


class _FakeAdapter:
    METHODS: tuple[str, ...] = ()
    STREAMING: frozenset[str] = frozenset()
    # 對應的真 adapter(testplan § G-09 的比對清單)
    REAL: type | None = None

    def __init__(self) -> None:
        for name in self.METHODS:
            method = FakeMethod(
                name=f"{type(self).__name__}.{name}",
                streaming=name in self.STREAMING,
                signature=_real_signature(self.REAL, name),
            )
            setattr(self, name, method)

    def method(self, name: str) -> FakeMethod:
        if name not in self.METHODS:
            raise AttributeError(name)
        return getattr(self, name)


class FakeColabControl(_FakeAdapter):
    """`contracts/colab-cli.openapi.yaml` 的 `ColabControl`。"""

    REAL = ColabControl
    METHODS = (
        "get_cli_version",
        "list_sessions",
        "create_session",
        "start_ollama",
        "probe_resources",
        "stop_session",
        "get_usage",
    )


class FakeTunnel(_FakeAdapter):
    """`contracts/tunnel.openapi.yaml` 的 `Tunnel`。

    給了 `server`(假 Ollama 伺服器)時,`open_tunnel` 預設回報的 `baseUrl` 指到它,
    讓 Ollama 相容端點的轉送真的經過 httpx 的網路連線。
    """

    REAL = Tunnel
    METHODS = ("ensure_key", "open_tunnel", "check_health", "close_tunnel", "cleanup_residual")

    def __init__(self, server: Any | None = None, remote_ollama_version: str = "0.40.15") -> None:
        super().__init__()
        self.server = server
        # 開啟、接回與重連都先準備通道金鑰(SessionLifecycle.open_tunnel);預設回「已存在」,測試要看別的結果再覆寫
        self.ensure_key.returns({"keyType": "ssh-ed25519", "fingerprint": "SHA256:cgb-test-fake-fingerprint", "created": False})
        if server is not None:
            def default_open(*args: Any, **kwargs: Any) -> dict[str, Any]:
                name = kwargs.get("session_name", args[0] if args else None)
                return {
                    "sessionName": name,
                    "baseUrl": server.base_url,
                    "remoteOllamaVersion": remote_ollama_version,
                    "connectedAt": None,
                    "elapsedMs": 0,
                }
            self.open_tunnel.side_effect(default_open)

    @property
    def local_port(self) -> int:
        if self.server is None:
            raise AssertionError("FakeTunnel 沒有接假 Ollama 伺服器")
        return self.server.port


class FakeRemoteOllama(_FakeAdapter):
    """`contracts/remote-ollama.openapi.yaml` 的 `RemoteOllama`。

    背後是 `tests/fakes/ollama_server.py` 的假 Ollama 伺服器(`self.server`);
    Ollama 相容端點的原樣轉送直接打那台伺服器,這裡的方法給 services 用,一樣可由測試設定。
    """

    REAL = RemoteOllama
    METHODS = (
        "get_version",
        "list_local_models",
        "list_loaded_models",
        "pull_model",
        "show_model",
        "generate",
        "chat",
        "embed",
        "preload",
    )
    STREAMING = frozenset({"pull_model", "generate", "chat"})

    def __init__(self, server: Any | None = None) -> None:
        super().__init__()
        self.server = server

    @property
    def base_url(self) -> str:
        if self.server is None:
            raise AssertionError("FakeRemoteOllama 沒有接假 Ollama 伺服器")
        return self.server.base_url


class FakeModelLibrary(_FakeAdapter):
    """`contracts/model-library.openapi.yaml` 的 `ModelLibrary`。"""

    REAL = ModelLibrary
    METHODS = ("search_library", "list_model_tags", "get_manifest")


class FakeHuggingFaceHub(_FakeAdapter):
    """`contracts/huggingface.openapi.yaml` 的 `HuggingFaceHub`(plan.md Q49:四個方法一次寫齊)。

    `get_manifest(author=, model=, tag=)` 回 `{"sizeBytes"}`;`list_quants(author=, model=)` 回 `[{"quant", "sizeBytes"}]`。
    """

    REAL = HuggingFaceHub
    METHODS = ("search_models", "list_repo_files", "get_manifest", "list_quants")


class FakeGoogleOAuth(_FakeAdapter):
    """`contracts/google-oauth.openapi.yaml` 的 `GoogleOAuth`。"""

    REAL = GoogleOAuth
    METHODS = ("build_authorization_url", "request_token")
