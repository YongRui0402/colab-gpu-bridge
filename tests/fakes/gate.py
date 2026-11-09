"""讓替身「等測試放行」的閘門。

替身可能在別的執行緒的事件迴圈裡被呼叫(測試行程內的 uvicorn,Q97、Q99),
所以用 threading 的原語,非同步的等待以短間隔輪詢,不綁定任何一個事件迴圈。
"""

import asyncio
import threading
import time

POLL_SECONDS = 0.005


class Gate:
    """關著時,經過的呼叫停在這裡,直到測試呼叫 `release()`。

    `entered` 是已經走到閘門前的次數,測試可以用 `wait_entered()` 確認呼叫真的到了。
    """

    def __init__(self) -> None:
        self._open = threading.Event()
        self._lock = threading.Lock()
        self._entered = 0

    @property
    def entered(self) -> int:
        with self._lock:
            return self._entered

    @property
    def is_open(self) -> bool:
        return self._open.is_set()

    def release(self) -> None:
        self._open.set()

    def _enter(self) -> None:
        with self._lock:
            self._entered += 1

    async def pass_async(self) -> None:
        self._enter()
        while not self._open.is_set():
            await asyncio.sleep(POLL_SECONDS)

    def pass_sync(self, stop: threading.Event | None = None) -> bool:
        """同步等待放行;`stop` 被設定時提早回 False(假伺服器關閉時用)。"""
        self._enter()
        while not self._open.wait(POLL_SECONDS * 4):
            if stop is not None and stop.is_set():
                return False
        return True

    def wait_entered(self, count: int = 1, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while self.entered < count:
            if time.monotonic() > deadline:
                raise AssertionError(f"等了 {timeout} 秒,只有 {self.entered} 次呼叫走到閘門(預期 {count} 次)")
            time.sleep(POLL_SECONDS)

    async def wait_entered_async(self, count: int = 1, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while self.entered < count:
            if time.monotonic() > deadline:
                raise AssertionError(f"等了 {timeout} 秒,只有 {self.entered} 次呼叫走到閘門(預期 {count} 次)")
            await asyncio.sleep(POLL_SECONDS)
