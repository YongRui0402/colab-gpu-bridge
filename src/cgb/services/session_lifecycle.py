"""開啟與結束工作階段的用例(FR-001、FR-003)。"""

import asyncio
import secrets
from dataclasses import dataclass
from typing import Any

from cgb.adapters.errors import AdapterError
from cgb.domain.errors import ApiError, reason_message
from cgb.domain.session_state import ACTIVE_STATES, TERMINAL_STATES, iso, listed_names, release_warning_fields, session_payload
from cgb.repos.sessions import ActiveSessionExists, SessionsRepo
from cgb.repos.tunings import TuningsRepo, machine_of, tuning_of
from cgb.services.auth import AuthService

# 本機轉發的 port(contracts/tunnel.openapi.yaml § OpenTunnelInput.localPort 預設)
TUNNEL_LOCAL_PORT = 11435


# 工作階段被結束(使用者結束、變更執行階段類型)時進入的狀態;進行中的轉送要隨之中斷(FR-013)
_ENDED_STATES = frozenset({"ending", "ended"})

# 三個覆蓋值都是自動(contracts/ui.openapi.yaml § TuningOverrides 的 null)
AUTO_OVERRIDES: dict[str, int | None] = {"numParallel": None, "contextLength": None, "maxLoadedModels": None}

# 開啟流程裡 `starting_ollama` 之後的步驟(contracts/ui.openapi.yaml § OpeningStep)
_AFTER_STARTING_OLLAMA = frozenset({"connecting", "verifying"})

# contracts/ui.openapi.yaml § Session.balanceMayBeDepleted:重連中或失聯時才判斷
_MAY_BE_DEPLETED_STATES = frozenset({"reconnecting", "lost"})


@dataclass(frozen=True)
class ForwardTarget:
    """Ollama 相容端點這次要轉送到的地方。`ended` 在這個工作階段被結束時設定。"""

    base_url: str
    ended: asyncio.Event


class SessionLifecycle:
    def __init__(self, state: Any, repo: SessionsRepo, auth: AuthService, key_path: str, tunings: TuningsRepo) -> None:
        self._state = state
        self._auth = auth
        self._repo = repo
        # 每一次開啟的 Ollama 設定(contracts/store.dbml § Table session_tunings)
        self._tunings = tunings
        self._key_path = key_path
        self._tasks: set[asyncio.Task[None]] = set()
        self._open_tasks: dict[str, asyncio.Task[None]] = {}
        # 進行中的 `colab new`:不中途終止(Q63),結束時等它跑完再釋放
        self._creating: dict[str, asyncio.Future[Any]] = {}
        # 目前通道的遠端 Ollama base URL(contracts/tunnel.openapi.yaml § Tunnel.baseUrl);只在後端內部使用
        self.base_url: str | None = None
        # 進行中的轉送等著的「工作階段被結束」事件(名稱 → 事件);repo 一有變更就檢查
        self._ended_events: dict[str, asyncio.Event] = {}
        repo.listeners.append(self._signal_ended)
        # 工作階段變成就緒時呼叫,收到轉發位址(開啟、重啟接回、重連都算;下載佇列自動繼續)
        self.ready_listeners: list[Any] = []
        self._was_ready = False
        repo.listeners.append(self._notify_ready)
        # 閒置倒數的來源(`IdleMonitor`);組裝時設定,沒設定時沿用 `session_payload` 的預設時限
        self.idle: Any = None
        # 最後讀到的用量(`UsageService`);重連中或失聯時提示餘額可能已經歸零(spec 邊界情況)
        self.usage: Any = None
        # 後端重新啟動後正在接回的工作階段名稱(`Recovery` 設定);UI 依此顯示「接回中」(Q117、Q167;合約沒有這個欄位)
        self.resuming: str | None = None

    def current(self) -> dict[str, Any]:
        row = self._repo.latest()
        payload = session_payload(row, self._repo.unmanaged_runtimes)
        if row is not None:
            payload["ollama"] = self._ollama_status(row["name"])
        if row is not None and row["name"] == self.resuming and row["state"] in ACTIVE_STATES:
            payload["resuming"] = True
        if row is not None and payload.get("idle") is not None and self.idle is not None:
            payload["idle"] = self.idle.countdown(row)
        if row is not None and row["state"] in _MAY_BE_DEPLETED_STATES and self.usage is not None:
            payload["balanceMayBeDepleted"] = self.usage.balance_may_be_depleted()
        return payload

    def _ollama_status(self, name: str) -> dict[str, Any]:
        """`Session.ollama`(contracts/ui.openapi.yaml § OllamaStatus):照紀錄裡 `startOllama` 回報的硬體與設定,不重算。"""
        record = self._tunings.latest(name)
        if record is None:
            # 沒有紀錄:還沒走完 `starting_ollama` 是 `pending`;已經走過(005 之前開、升級後接回)是 `unknown`
            status = "unknown" if self._passed_starting_ollama(name) else "pending"
            return {"status": status, "machine": None, "tuning": None, "lastApply": None}
        tuning = tuning_of(record)
        # 遠端 Ollama 在執行、但讀不到它套用的設定(OllamaStatus.status 的 `unknown`)
        status = "applied" if tuning is not None else "unknown"
        return {"status": status, "machine": machine_of(record), "tuning": tuning, "lastApply": None}

    def _passed_starting_ollama(self, name: str) -> bool:
        return any(t["state"] == "ready" or t["step"] in _AFTER_STARTING_OLLAMA for t in self._repo.transitions(name))

    def ready_base_url(self) -> str | None:
        """工作階段就緒時的轉發位址;開啟中、重連中、結束後都是 None(不去連轉發位址)。"""
        if self.current()["state"] != "ready":
            return None
        return self.base_url

    def require_ready_base_url(self) -> str:
        """同 `ready_base_url`,沒有就緒的工作階段時回 503 `NO_READY_SESSION`。"""
        base_url = self.ready_base_url()
        if base_url is None:
            raise ApiError(503, "NO_READY_SESSION")
        return base_url

    def forward_target(self) -> ForwardTarget | None:
        """Ollama 相容端點此刻該轉送到的地方;沒有可轉送的工作階段時是 None(FR-013)。"""
        latest = self._repo.latest()
        # 只有「就緒」才轉送:開啟中、重連中、結束中、變更類型的過程中都不排隊等(FR-013)
        if latest is None or latest["state"] != "ready" or self.base_url is None:
            return None
        ended = self._ended_events.setdefault(latest["name"], asyncio.Event())
        return ForwardTarget(base_url=self.base_url, ended=ended)

    async def open_tunnel(self, name: str, *, key_path: str | None = None) -> dict[str, Any]:
        """建立通道並記下轉發位址;首次開啟、重啟接回與重連都走這裡,Ollama 相容端點才轉送得出去(Q170)。

        先準備通道金鑰(tunnel 合約 openTunnel 的前置 (1));已存在就不覆寫,全新部署才有金鑰可用。
        """
        key = key_path if key_path is not None else self._key_path
        await self._state.tunnel.ensure_key(key_path=key)
        opened = await self._state.tunnel.open_tunnel(session_name=name, key_path=key, local_port=TUNNEL_LOCAL_PORT)
        self.base_url = opened["baseUrl"]
        return opened

    def _notify_ready(self) -> None:
        ready = self.ready_base_url() is not None
        if ready and not self._was_ready:
            for listener in list(self.ready_listeners):
                listener(self.base_url)
        self._was_ready = ready

    def _signal_ended(self) -> None:
        for name in list(self._ended_events):
            row = self._repo.get(name)
            if row is None or row["state"] in _ENDED_STATES:
                self._ended_events.pop(name).set()

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
        colab, remote = self._state.colab, self._state.remote_ollama
        # Q63:記下開啟前沒有名稱的執行環境,`colab new` 逾時後比對
        progress["unnamed_before"] = (await colab.list_sessions())["unnamed"]
        creating = asyncio.ensure_future(
            colab.create_session(name=name, gpu=runtime_type["gpu"], high_mem=runtime_type["highMem"])
        )
        self._creating[name] = creating
        await asyncio.shield(creating)
        progress["allocated"] = True
        self._repo.update(name, step="starting_ollama")
        started = await colab.start_ollama(name=name, overrides=AUTO_OVERRIDES)
        self._tunings.insert_open(
            session_name=name, at=iso(self._state.clock.now()), requested=AUTO_OVERRIDES, started=started
        )
        self._repo.update(name, step="connecting")
        # Q64:`colab ssh --proxy-mode` 找不到名稱會自己開一台新的,建立通道前一定先確認名稱在列
        listed = await colab.list_sessions()
        if name not in listed_names(listed):
            raise AdapterError("COLAB_NOT_FOUND", "colab sessions 沒有列出這個工作階段")
        opened = await self.open_tunnel(name)
        self._repo.update(name, step="verifying")
        await remote.get_version(base_url=opened["baseUrl"])
        self._repo.update(name, state="ready", step=None, ready_at=iso(self._state.clock.now()))

    async def end(self, end_reason: str = "USER_ENDED") -> dict[str, Any]:
        latest = self._repo.latest()
        if latest is None or (latest["state"] in TERMINAL_STATES and latest["release_warning_message"] is None):
            raise ApiError(409, "NO_ACTIVE_SESSION")
        name = latest["name"]
        self._repo.update(name, state="ending", active_slot=None, step=None)
        self.spawn(self._run_end(name, end_reason))
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

    async def _run_end(self, name: str, end_reason: str) -> None:
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
                end_reason=end_reason,
                ended_at=now,
                **release_warning_fields(error.code, now),
            )
            return
        self._repo.update(
            name,
            state="ended",
            end_reason=end_reason,
            ended_at=now,
            **release_warning_fields(None, None),
        )

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
