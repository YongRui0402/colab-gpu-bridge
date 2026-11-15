"""`session_tunings` 與 `runtime_type_tunings` 表的存取(contracts/store.dbml § Table session_tunings、Table runtime_type_tunings)。"""

import sqlite3
from typing import Any

from cgb.domain.session_state import GPU_TYPES

# AppliedTuning 的三項數值:API 的名稱 → 欄位名稱
_INT_ITEMS = (
    ("numParallel", "num_parallel"),
    ("contextLength", "context_length"),
    ("maxLoadedModels", "max_loaded_models"),
)


class TuningsRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_open(self, *, session_name: str, at: str, requested: dict[str, Any], started: dict[str, Any]) -> None:
        """開啟時那一筆(`trigger` 為 `open`、`result` 為 `applied`):`startOllama` 回報的硬體與設定原樣存起來。"""
        columns: dict[str, Any] = {
            "session_name": session_name,
            "at": at,
            "finished_at": at,
            "trigger": "open",
            "result": "applied",
            "requested_num_parallel": requested["numParallel"],
            "requested_context_length": requested["contextLength"],
            "requested_max_loaded_models": requested["maxLoadedModels"],
            # 已在執行而讀不到設定檔時 `tuning` 是 null:設定的欄位都留 NULL
            **_result_columns(started["machine"], started["tuning"]),
        }
        names = ", ".join(columns)
        marks = ", ".join("?" for _ in columns)
        self._conn.execute(f"INSERT INTO session_tunings ({names}) VALUES ({marks})", tuple(columns.values()))

    def insert_apply(self, *, session_name: str, at: str, requested: dict[str, Any]) -> int:
        """套用受理時那一筆(`trigger` 為 `apply`、`attempt` 為 `requested`、`result` 為 `in_progress`),回傳它的 id。"""
        cursor = self._conn.execute(
            "INSERT INTO session_tunings (session_name, at, trigger, attempt, result,"
            " requested_num_parallel, requested_context_length, requested_max_loaded_models)"
            " VALUES (?, ?, 'apply', 'requested', 'in_progress', ?, ?, ?)",
            (session_name, at, requested["numParallel"], requested["contextLength"], requested["maxLoadedModels"]),
        )
        return int(cursor.lastrowid)

    def record_restart(self, record_id: int, *, machine: dict[str, Any], tuning: dict[str, Any] | None) -> None:
        """重啟成功:寫入這次量到的硬體與新設定(`result` 仍是 `in_progress`,analysis A2)。"""
        columns = _result_columns(machine, tuning)
        assignments = ", ".join(f"{column} = ?" for column in columns)
        self._conn.execute(f"UPDATE session_tunings SET {assignments} WHERE id = ?", (*columns.values(), record_id))

    def mark_fallback(self, record_id: int, *, reason_code: str, remote_stage: str | None) -> None:
        """要求的設定重啟失敗、改回自動值再試:`attempt` 改為 `auto_fallback`,記下第一次的失敗。"""
        self._conn.execute(
            "UPDATE session_tunings SET attempt = 'auto_fallback', reason_code = ?, remote_stage = ? WHERE id = ?",
            (reason_code, remote_stage, record_id),
        )

    def fail_apply(
        self, record_id: int, *, finished_at: str, reason_code: str, remote_stage: str | None, message: str, result: str = "failed"
    ) -> None:
        """無法回到就緒:`result`(預設 `failed`;恢復時失敗是 `interrupted`),記下最後一次的失敗(machine 與 tuning 維持 NULL)。"""
        self._conn.execute(
            "UPDATE session_tunings SET result = ?, finished_at = ?, reason_code = ?, remote_stage = ?, message = ? WHERE id = ?",
            (result, finished_at, reason_code, remote_stage, message, record_id),
        )

    def finish_apply(self, record_id: int, *, result: str, finished_at: str, message: str | None = None) -> None:
        """套用結束:寫入結果、完成時間與給使用者看的說明。"""
        self._conn.execute(
            "UPDATE session_tunings SET result = ?, finished_at = ?, message = ? WHERE id = ?",
            (result, finished_at, message, record_id),
        )

    def add_model(
        self, record_id: int, *, position: int, model: str, reason: str | None = None, reason_code: str | None = None
    ) -> None:
        """記下重啟前 `/api/ps` 的第 `position` 個模型:沒有給 `reason` 是已重新載入,有給是沒有重新載入的原因。"""
        self._conn.execute(
            "INSERT INTO session_tuning_models (tuning_id, position, model, reason, reason_code) VALUES (?, ?, ?, ?, ?)",
            (record_id, position, model, reason, reason_code),
        )

    def for_session(self, session_name: str) -> list[dict[str, Any]]:
        """這個工作階段的每一筆,依 `at` 排序。"""
        rows = self._conn.execute(
            "SELECT * FROM session_tunings WHERE session_name = ? ORDER BY at, id", (session_name,)
        ).fetchall()
        return [self._with_models(dict(row)) for row in rows]

    def latest_apply(self, session_name: str) -> dict[str, Any] | None:
        """這個工作階段最近一次套用(`trigger` 為 `apply`)的那一筆,含進行中的。"""
        row = self._conn.execute(
            "SELECT * FROM session_tunings WHERE session_name = ? AND trigger = 'apply' ORDER BY at DESC, id DESC LIMIT 1",
            (session_name,),
        ).fetchone()
        return self._with_models(dict(row)) if row is not None else None

    def effective(self, session_name: str) -> dict[str, Any] | None:
        """目前生效的設定所在的那一筆(`Session.ollama.machine`、`tuning` 取它)。"""
        row = self._conn.execute(
            "SELECT * FROM session_tunings WHERE session_name = ?"
            " AND (result IN ('applied', 'fell_back_to_auto') OR (result IN ('in_progress', 'interrupted') AND probed_at IS NOT NULL))"
            " ORDER BY at DESC, id DESC LIMIT 1",
            (session_name,),
        ).fetchone()
        return dict(row) if row is not None else None

    def _with_models(self, row: dict[str, Any]) -> dict[str, Any]:
        """套用那一筆附上重新載入與沒有重新載入的模型(`session_tuning_models`,依 `position`)。"""
        if row["trigger"] == "apply":
            models = self._conn.execute(
                "SELECT model, reason, reason_code FROM session_tuning_models WHERE tuning_id = ? ORDER BY position",
                (row["id"],),
            ).fetchall()
            row["models"] = [dict(model) for model in models]
        return row

    def put_type_override(self, gpu: str, overrides: dict[str, Any], *, at: str) -> None:
        """以這次的三個值整份取代這種 GPU 類型記住的覆蓋值(contracts/ui.openapi.yaml § info.x-tuning-rule (3))。"""
        if all(value is None for value in overrides.values()):
            # 三個都是 null 就是清除:刪掉那一列(plan.md Q23)
            self._conn.execute("DELETE FROM runtime_type_tunings WHERE gpu = ?", (gpu,))
            return
        self._conn.execute(
            "INSERT OR REPLACE INTO runtime_type_tunings (gpu, num_parallel, context_length, max_loaded_models, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (gpu, overrides["numParallel"], overrides["contextLength"], overrides["maxLoadedModels"], at),
        )

    def type_override(self, gpu: str) -> dict[str, Any]:
        """這種 GPU 類型記住的三個覆蓋值(`TuningOverrides`);沒有記過時三個都是 None。"""
        row = self._conn.execute("SELECT * FROM runtime_type_tunings WHERE gpu = ?", (gpu,)).fetchone()
        return _override_values(row)

    def type_overrides(self) -> list[dict[str, Any]]:
        """五種 GPU 類型各一筆 `RuntimeTypeTuningOverride`,依 `GpuType` 的順序;沒有記過的三個值與 `updatedAt` 都是 None。"""
        rows = {row["gpu"]: row for row in self._conn.execute("SELECT * FROM runtime_type_tunings")}
        return [
            {"gpu": gpu, **_override_values(rows.get(gpu)), "updatedAt": rows[gpu]["updated_at"] if gpu in rows else None}
            for gpu in GPU_TYPES
        ]

    def latest(self, session_name: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM session_tunings WHERE session_name = ? ORDER BY at DESC, id DESC LIMIT 1", (session_name,)
        ).fetchone()
        return dict(row) if row is not None else None


def _result_columns(machine: dict[str, Any], tuning: dict[str, Any] | None) -> dict[str, Any]:
    """重啟(或恢復時 `startOllama`)回報的硬體與設定換成 `session_tunings` 的欄位;`tuning` 為 None(讀不到設定檔)時只有硬體。"""
    columns: dict[str, Any] = {
        "gpu_name": machine["gpuName"],
        "vram_total_bytes": machine["vramTotalBytes"],
        "system_memory_total_bytes": machine["systemMemoryTotalBytes"],
        "probed_at": machine["probedAt"],
    }
    if tuning is None:
        return columns
    for key, column in _INT_ITEMS:
        columns[column] = tuning[key]["value"]
        columns[f"{column}_source"] = tuning[key]["source"]
    flash = tuning["flashAttention"]["value"]
    columns["flash_attention"] = None if flash is None else int(flash)
    columns["flash_attention_source"] = tuning["flashAttention"]["source"]
    columns["kv_cache_type"] = tuning["kvCacheType"]["value"]
    columns["kv_cache_type_source"] = tuning["kvCacheType"]["source"]
    return columns


def _override_values(row: Any) -> dict[str, Any]:
    """`runtime_type_tunings` 的一列換回三個覆蓋值;沒有那一列時三個都是 None。"""
    return {key: row[column] if row is not None else None for key, column in _INT_ITEMS}


def machine_of(row: dict[str, Any]) -> dict[str, Any]:
    """一列換回 `MachineProbe`。"""
    return {
        "gpuName": row["gpu_name"],
        "vramTotalBytes": row["vram_total_bytes"],
        "systemMemoryTotalBytes": row["system_memory_total_bytes"],
        "probedAt": row["probed_at"],
    }


def tuning_of(row: dict[str, Any]) -> dict[str, Any] | None:
    """一列換回 `AppliedTuning`;讀不到設定(來源都是 NULL)時是 None。"""
    if row["num_parallel_source"] is None:
        return None
    tuning = {key: {"value": row[column], "source": row[f"{column}_source"]} for key, column in _INT_ITEMS}
    flash = row["flash_attention"]
    tuning["flashAttention"] = {"value": None if flash is None else bool(flash), "source": row["flash_attention_source"]}
    tuning["kvCacheType"] = {"value": row["kv_cache_type"], "source": row["kv_cache_type_source"]}
    return tuning


def record_of(row: dict[str, Any]) -> dict[str, Any]:
    """一列換回 `TuningRecord`(contracts/ui.openapi.yaml § components.schemas.TuningRecord);開啟那一筆沒有 `attempt`。"""
    record = {
        "at": row["at"],
        "finishedAt": row["finished_at"],
        "trigger": row["trigger"],
        "requested": {
            "numParallel": row["requested_num_parallel"],
            "contextLength": row["requested_context_length"],
            "maxLoadedModels": row["requested_max_loaded_models"],
        },
        # 重啟還沒成功、或失敗時沒有量到硬體(probed_at 為 NULL)
        "machine": machine_of(row) if row["probed_at"] is not None else None,
        "tuning": tuning_of(row),
        "result": row["result"],
        "reasonCode": row["reason_code"],
        "remoteStage": row["remote_stage"],
        "message": row["message"],
    }
    if row["trigger"] == "apply":
        models = row.get("models", [])
        record["attempt"] = row["attempt"]
        record["reloaded"] = [m["model"] for m in models if m["reason"] is None]
        record["notReloaded"] = [
            {"model": m["model"], "reason": m["reason"], "reasonCode": m["reason_code"]} for m in models if m["reason"] is not None
        ]
    return record
