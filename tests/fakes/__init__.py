"""轉接層的替身與假 Ollama HTTP 伺服器(plan.md Q96)。"""

from .adapters import (
    Call,
    FakeColabControl,
    FakeGoogleOAuth,
    FakeMethod,
    FakeModelLibrary,
    FakeNotConfigured,
    FakeRemoteOllama,
    FakeTunnel,
)
from .gate import Gate
from .ollama_server import (
    DisconnectReply,
    FakeOllamaServer,
    HangReply,
    JsonReply,
    NdjsonReply,
    RecordedRequest,
)

__all__ = [
    "Call",
    "DisconnectReply",
    "FakeColabControl",
    "FakeGoogleOAuth",
    "FakeMethod",
    "FakeModelLibrary",
    "FakeNotConfigured",
    "FakeOllamaServer",
    "FakeRemoteOllama",
    "FakeTunnel",
    "Gate",
    "HangReply",
    "JsonReply",
    "NdjsonReply",
    "RecordedRequest",
]
