"""開啟與結束工作階段的用例(FR-001、FR-003)。"""

import asyncio
import secrets
from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.errors import ApiError, reason_message
from cgb.domain.session_state import TERMINAL_STATES, iso, listed_names, release_warning_fields, session_payload
from cgb.repos.sessions import ActiveSessionExists, SessionsRepo
from cgb.services.auth import AuthService

# 本機轉發的 port(contracts/tunnel.openapi.yaml § OpenTunnelInput.localPort 預設)
TUNNEL_LOCAL_PORT = 11435


class SessionLifecycle:
    def __init__(self, state: Any, repo: SessionsRepo, auth: AuthService, key_path: str) -> None:
        self._state = state
        self._auth = auth
        self._repo = repo
        self._key_path = key_path
        self._tasks: set[asyncio.Task[None]] = set()
        self._open_tasks: dict[str, asyncio.Task[None]] = {}
        # 進行中的 `colab new`:不中途終止(Q63),結束時等它跑完再釋放
        self._creating: dict[str, asyncio.Future[Any]] = {}
        # 目前通道的遠端 Ollama base URL(contracts/tunnel.openapi.yaml § Tunnel.baseUrl);只在後端內部使用
        self.base_url: str | None = None

    def current(self) -> dict[str, Any]:
        return session_payload(self._repo.latest(), self._repo.unmanaged_runtimes)

    def _new_name(self) -> str:
        # contracts/colab-cli.openapi.yaml § SessionName 建議的 <前綴><yyyymmdd>-<hhmmss>-<4 碼十六進位>
        now = self._state.clock.now()
        return f"{self._state.name_prefix}{now:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"

    def spawn(self, coro: Any) -> asyncio.Task[None]:
        """背景工作;關機時一起取消。"""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def open(self, runtime_type: dict[str, Any]) -> dict[str, Any]:
        latest = self._repo.latest()
        if latest is not None and latest["state"] == "ending":
            # ending 不占位(store.dbml active_slot),但不能和正在結束的那台重疊
            raise ApiError(409, "SESSION_ENDING")
        # FR-008:先確認授權,不讓 `colab new` 卡在等授權碼
        if (await self._auth.check())["state"] == "logged_out":
            raise ApiError(409, "AUTH_REQUIRED")
        name = self.reserve(runtime_type, step="allocating")
        self.start_open(name, runtime_type)
        return self.current()

    def reserve(self, runtime_type: dict[str, Any], *, step: str) -> str:
        """寫入一筆開啟中的工作階段,回傳它的名稱。"""
        name = self._new_name()
        try:
            # 寫入本身就是檢查:active_slot 的 unique 讓同時送來的第二個開啟寫不進去(不先查再寫)
            self._repo.insert_opening(
                name=name,
                gpu=runtime_type["gpu"],
                high_mem=runtime_type["highMem"],
                opened_at=iso(self._state.clock.now()),
                step=step,
            )
        except ActiveSessionExists:
            raise ApiError(409, "SESSION_ALREADY_ACTIVE") from None
        return name

    def start_open(self, name: str, runtime_type: dict[str, Any]) -> asyncio.Task[None]:
        """在背景跑開啟流程;回傳那個 task。"""
        task = self.spawn(self._run_open(name, runtime_type))
        self._open_tasks[name] = task
        task.add_done_callback(lambda _: self._open_tasks.pop(name, None))
        return task

    async def _run_open(self, name: str, runtime_type: dict[str, Any]) -> None:
        progress: dict[str, Any] = {"allocated": False, "unnamed_before": None}
        try:
            await self._within_open_deadline(self._open_steps(name, runtime_type, progress))
        except TimeoutError:
            # Q58、SC-001:開啟流程的總時限
            await self._fail_open(name, "COLAB_TIMEOUT", allocated=progress["allocated"])
        except AdapterError as error:
            if error.code == "AUTH_REQUIRED":
                # 授權過期不是失聯:開啟失敗,並讓 UI 知道要重新登入(spec 邊界情況、FR-008)
                self._auth.mark_logged_out()
            await self._fail_open(name, error.code, allocated=progress["allocated"], unnamed_before=progress["unnamed_before"])

    async def _within_open_deadline(self, steps: Any) -> None:
        """在注入的時鐘上等開啟流程;總時限先到就取消它並丟 TimeoutError。"""
        steps_task = asyncio.ensure_future(steps)
        deadline = asyncio.ensure_future(self._state.clock.sleep(self._state.timeouts.open_total))
        try:
            await asyncio.wait({steps_task, deadline}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            steps_task.cancel()
            await asyncio.gather(steps_task, return_exceptions=True)
            raise
        finally:
            deadline.cancel()
        if not steps_task.done():
            steps_task.cancel()
            await asyncio.gather(steps_task, return_exceptions=True)
            raise TimeoutError
        steps_task.result()

    async def _fail_open(
        self, name: str, reason_code: str, *, allocated: bool, unnamed_before: list[Any] | None = None
    ) -> None:
        self._repo.update(
            name,
            state="open_failed",
            active_slot=None,
            step=None,
            end_reason="OPEN_FAILED",
            reason_code=reason_code,
            message=reason_message(reason_code),
            ended_at=iso(self._state.clock.now()),
        )
        if allocated:
            # FR-007:已配置的執行環境要釋放(stop_session 自己會回讀確認)
            await self._release(name)
        else:
            # FR-007:回讀 Colab 帳號,確認沒有遺留
            after = await self._state.colab.list_sessions()
            if unnamed_before is not None and len(after["unnamed"]) > len(unnamed_before):
                # Q63:`colab new` 逾時後多出沒有名稱的執行環境,可能是這次的配置生效卻沒記下名稱;不接手、不關閉,只警告
                self._warn_release(name, reason_code)

    def _warn_release(self, name: str, reason_code: str) -> None:
        now = iso(self._state.clock.now())
        self._repo.update(
            name,
            **release_warning_fields(reason_code, now),
        )

    async def _release(self, name: str) -> None:
        try:
            await self._state.colab.stop_session(name=name)
            # FR-006、FR-007:釋放後以 `colab sessions` 確認(含 `colab ssh` 意外開出、已交給 stop 的那台)
            listed = await self._state.colab.list_sessions()
        except AdapterError as error:
            self._warn_release(name, error.code)
            return
        if name in listed_names(listed):
            self._warn_release(name, "COLAB_STOP_UNCONFIRMED")

    async def _open_steps(self, name: str, runtime_type: dict[str, Any], progress: dict[str, bool]) -> None:
        colab, tunnel, remote = self._state.colab, self._state.tunnel, self._state.remote_ollama
        # Q63:記下開啟前沒有名稱的執行環境,`colab new` 逾時後比對
        progress["unnamed_before"] = (await colab.list_sessions())["unnamed"]
        creating = asyncio.ensure_future(
            colab.create_session(name=name, gpu=runtime_type["gpu"], high_mem=runtime_type["highMem"])
        )
        self._creating[name] = creating
        await asyncio.shield(creating)
        progress["allocated"] = True
        self._repo.update(name, step="starting_ollama")
        await colab.start_ollama(name=name)
        self._repo.update(name, step="connecting")
        # Q64:`colab ssh --proxy-mode` 找不到名稱會自己開一台新的,建立通道前一定先確認名稱在列
        listed = await colab.list_sessions()
        if name not in listed_names(listed):
            raise AdapterError("COLAB_NOT_FOUND", "colab sessions 沒有列出這個工作階段")
        opened = await tunnel.open_tunnel(session_name=name, key_path=self._key_path, local_port=TUNNEL_LOCAL_PORT)
        self.base_url = opened["baseUrl"]
        self._repo.update(name, step="verifying")
        await remote.get_version(base_url=opened["baseUrl"])
        self._repo.update(name, state="ready", step=None, ready_at=iso(self._state.clock.now()))

    async def end(self) -> dict[str, Any]:
        latest = self._repo.latest()
        if latest is None or (latest["state"] in TERMINAL_STATES and latest["release_warning_message"] is None):
            raise ApiError(409, "NO_ACTIVE_SESSION")
        name = latest["name"]
        self._repo.update(name, state="ending", active_slot=None, step=None)
        self.spawn(self._run_end(name))
        return self.current()

    async def _stop_opening(self, name: str) -> None:
        """結束時若還在開啟:取消後面的步驟,但等進行中的 `colab new` 自己結束(spec 邊界情況、Q63)。"""
        task = self._open_tasks.get(name)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        creating = self._creating.pop(name, None)
        if creating is not None:
            await asyncio.gather(creating, return_exceptions=True)

    async def _run_end(self, name: str) -> None:
        await self._stop_opening(name)
        # 先關通道再釋放:串流斷掉時不會被當成非預期的斷線
        await self._state.tunnel.close_tunnel(session_name=name)
        now = iso(self._state.clock.now())
        try:
            await self._state.colab.stop_session(name=name)
        except AdapterError as error:
            self._repo.update(
                name,
                state="ended",
                end_reason="USER_ENDED",
                ended_at=now,
                **release_warning_fields(error.code, now),
            )
            return
        self._repo.update(
            name,
            state="ended",
            end_reason="USER_ENDED",
            ended_at=now,
            **release_warning_fields(None, None),
        )

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
