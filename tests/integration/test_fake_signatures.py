"""全域:替身與真轉接層的簽章一致(testplan.md § G-09;spec.md FR-004、FR-005、FR-007;plan.md Q159、Q160、Q175)。

替身照單全收時,呼叫端少帶參數(例如重連只傳 `session_name` 給 `open_tunnel`)自動化測試全綠、接上真 adapter 才丟 TypeError。
比對範圍照 Q160(a):只比真 adapter 有的公開方法;替身另有的測試控制成員(`method()`、`local_port` 等)不比。
"""

import asyncio
import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Any

import pytest

import cgb.adapters
from cgb.adapters.colab_cli import ColabControl
from cgb.adapters.google_oauth import GoogleOAuth
from cgb.adapters.huggingface import HuggingFaceHub
from cgb.adapters.model_library import ModelLibrary
from cgb.adapters.remote_ollama import RemoteOllama
from cgb.adapters.tunnel import Tunnel
from fakes import FakeColabControl, FakeGoogleOAuth, FakeHuggingFaceHub, FakeModelLibrary, FakeRemoteOllama, FakeTunnel

# 比對清單:真 adapter → 替身。`RemoteOllama`(E7)、`ModelLibrary`(E8)、`HuggingFaceHub`(E12,Q65)的 adapter 已經建立,一併比對(Q160、Q175)
PAIRS: list[tuple[type, type]] = [
    (ColabControl, FakeColabControl),
    (Tunnel, FakeTunnel),
    (GoogleOAuth, FakeGoogleOAuth),
    (RemoteOllama, FakeRemoteOllama),
    (ModelLibrary, FakeModelLibrary),
    (HuggingFaceHub, FakeHuggingFaceHub),
]

UNKNOWN_PARAMETER = "cgb_test_not_a_parameter"


def public_methods(cls: type) -> list[str]:
    return sorted(name for name, _ in inspect.getmembers(cls, inspect.isfunction) if not name.startswith("_"))


def real_parameters(real: type, name: str) -> list[inspect.Parameter]:
    """真方法的參數,不含 `self`。"""
    return list(inspect.signature(getattr(real, name)).parameters.values())[1:]


def shape(parameters: list[inspect.Parameter]) -> list[tuple[str, Any, bool]]:
    """比對用:參數名、種類(位置或關鍵字、只能關鍵字等)與有沒有預設值,依宣告的順序。"""
    return [(p.name, p.kind, p.default is not inspect.Parameter.empty) for p in parameters]


def arguments(parameters: list[inspect.Parameter], *, omit: str | None = None) -> dict[str, Any]:
    """依真方法的參數組一組關鍵字參數:必填的都帶,`omit` 那一個不帶(真方法沒有只能用位置傳的參數)。"""
    return {p.name: f"cgb-test-{p.name}" for p in parameters if p.default is inspect.Parameter.empty and p.name != omit}


def call_fully(fake_method: Any, *args: Any, **kwargs: Any) -> Any:
    """呼叫替身方法;回傳值是 awaitable 時把它跑完(綁定參數的錯誤不論發生在呼叫或等待時都會丟出)。"""
    result = fake_method(*args, **kwargs)
    if inspect.isawaitable(result):
        asyncio.run(_await(result))
    return result


async def _await(awaitable: Any) -> Any:
    return await awaitable


CASES = [
    pytest.param(real, fake, name, id=f"{fake.__name__}.{name}") for real, fake in PAIRS for name in public_methods(real)
]


@pytest.mark.parametrize(("real", "fake_cls"), [pytest.param(r, f, id=f.__name__) for r, f in PAIRS])
def test_真adapter的每個公開方法替身都有同名方法(real: type, fake_cls: type) -> None:
    fake = fake_cls()

    missing = [name for name in public_methods(real) if not callable(getattr(fake, name, None))]

    assert missing == []


@pytest.mark.parametrize(("real", "fake_cls", "name"), CASES)
def test_同名方法的參數名順序與有沒有預設值都和真方法相同(real: type, fake_cls: type, name: str) -> None:
    fake = fake_cls()

    fake_parameters = list(inspect.signature(getattr(fake, name)).parameters.values())

    assert shape(fake_parameters) == shape(real_parameters(real, name))


@pytest.mark.parametrize(("real", "fake_cls", "name"), CASES)
def test_真方法是async時替身的呼叫結果是awaitable_不是時不是(real: type, fake_cls: type, name: str) -> None:
    # Arrange
    fake = fake_cls()
    fake.method(name).returns([] if name in fake.STREAMING else {})
    kwargs = arguments(real_parameters(real, name))

    # Act
    result = getattr(fake, name)(**kwargs)
    awaitable = inspect.isawaitable(result)
    if awaitable:
        asyncio.run(_await(result))

    # Assert
    assert awaitable == inspect.iscoroutinefunction(getattr(real, name))


REQUIRED_CASES = [
    pytest.param(real, fake, name, p.name, id=f"{fake.__name__}.{name}-少帶{p.name}")
    for real, fake in PAIRS
    for name in public_methods(real)
    for p in real_parameters(real, name)
    if p.default is inspect.Parameter.empty
]


@pytest.mark.parametrize(("real", "fake_cls", "name", "omitted"), REQUIRED_CASES)
def test_少帶必填參數時替身丟TypeError(real: type, fake_cls: type, name: str, omitted: str) -> None:
    # Arrange
    fake = fake_cls()
    fake.method(name).returns([] if name in fake.STREAMING else {})
    kwargs = arguments(real_parameters(real, name), omit=omitted)

    # Act、Assert
    with pytest.raises(TypeError):
        call_fully(getattr(fake, name), **kwargs)


@pytest.mark.parametrize(("real", "fake_cls", "name"), CASES)
def test_多帶真方法沒有的參數名時替身丟TypeError(real: type, fake_cls: type, name: str) -> None:
    # Arrange
    fake = fake_cls()
    fake.method(name).returns([] if name in fake.STREAMING else {})
    kwargs = arguments(real_parameters(real, name))

    # Act、Assert
    with pytest.raises(TypeError):
        call_fully(getattr(fake, name), **kwargs, **{UNKNOWN_PARAMETER: "cgb-test"})


def adapter_classes(module: Any) -> list[type]:
    """模組裡定義的轉接層類別:公開、而且至少有一個公開的 async 方法(資料類別與例外不算)。"""
    return [
        cls
        for name, cls in inspect.getmembers(module, inspect.isclass)
        if cls.__module__ == module.__name__
        and not name.startswith("_")
        and any(inspect.iscoroutinefunction(f) for n, f in inspect.getmembers(cls, inspect.isfunction) if not n.startswith("_"))
    ]


def test_adapters裡每個定義了轉接層類別的模組都在比對清單裡() -> None:
    # Arrange
    root = Path(cgb.adapters.__file__).parent
    modules = [importlib.import_module(info.name) for info in pkgutil.walk_packages([str(root)], prefix="cgb.adapters.")]

    # Act
    found = {cls for module in modules for cls in adapter_classes(module)}

    # Assert
    assert found, "src/cgb/adapters/ 裡沒有找到任何轉接層類別,判斷方式可能錯了"
    assert sorted(cls.__name__ for cls in found - {real for real, _ in PAIRS}) == []
