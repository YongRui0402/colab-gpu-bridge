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
        machine, tuning = started["machine"], started["tuning"]
        columns: dict[str, Any] = {
            "session_name": session_name,
            "at": at,
            "finished_at": at,
            "trigger": "open",
            "result": "applied",
            "requested_num_parallel": requested["numParallel"],
            "requested_context_length": requested["contextLength"],
            "requested_max_loaded_models": requested["maxLoadedModels"],
            "gpu_name": machine["gpuName"],
            "vram_total_bytes": machine["vramTotalBytes"],
            "system_memory_total_bytes": machine["systemMemoryTotalBytes"],
            "probed_at": machine["probedAt"],
        }
        # 已在執行而讀不到設定檔時 `tuning` 是 null:設定的欄位都留 NULL
        if tuning is not None:
            for key, column in _INT_ITEMS:
                columns[column] = tuning[key]["value"]
                columns[f"{column}_source"] = tuning[key]["source"]
            flash = tuning["flashAttention"]["value"]
            columns["flash_attention"] = None if flash is None else int(flash)
            columns["flash_attention_source"] = tuning["flashAttention"]["source"]
            columns["kv_cache_type"] = tuning["kvCacheType"]["value"]
            columns["kv_cache_type_source"] = tuning["kvCacheType"]["source"]
        names = ", ".join(columns)
        marks = ", ".join("?" for _ in columns)
        self._conn.execute(f"INSERT INTO session_tunings ({names}) VALUES ({marks})", tuple(columns.values()))

    def for_session(self, session_name: str) -> list[dict[str, Any]]:
        """這個工作階段的每一筆,依 `at` 排序。"""
        rows = self._conn.execute(
            "SELECT * FROM session_tunings WHERE session_name = ? ORDER BY at, id", (session_name,)
        ).fetchall()
        return [dict(row) for row in rows]

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
    return {
        "at": row["at"],
        "finishedAt": row["finished_at"],
        "trigger": row["trigger"],
        "requested": {
            "numParallel": row["requested_num_parallel"],
            "contextLength": row["requested_context_length"],
            "maxLoadedModels": row["requested_max_loaded_models"],
        },
        "machine": machine_of(row),
        "tuning": tuning_of(row),
        "result": row["result"],
        "reasonCode": row["reason_code"],
        "remoteStage": row["remote_stage"],
        "message": row["message"],
    }
