"""下載佇列(FR-021、FR-010;contracts/ui.openapi.yaml § DownloadQueue)。一次一個,依佇列順序(research.md R5)。"""

from typing import Any

from cgb.domain.session_state import iso
from cgb.repos.downloads import DownloadsRepo


def job_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "model": row["model"],
        "sizeBytes": row["size_bytes"],
        "state": row["state"],
        "progress": None,
        "reasonCode": row["reason_code"],
        "message": row["message"],
        "origin": row["origin"],
        "preloadOnComplete": bool(row["preload_on_complete"]),
        "addedAt": row["added_at"],
        "startedAt": row["started_at"],
        "finishedAt": row["finished_at"],
    }


class DownloadsService:
    def __init__(self, state: Any, repo: DownloadsRepo) -> None:
        self._state = state
        self._repo = repo

    def queue(self, *, paused: bool) -> dict[str, Any]:
        return {"paused": paused, "jobs": [job_payload(row) for row in self._repo.all()]}

    def enqueue_restore(self, model: str, size_bytes: int) -> None:
        """變更類型時為了重新載入原本已載入的模型而加入(FR-010、Q36)。"""
        self._repo.enqueue(
            model=model,
            size_bytes=size_bytes,
            origin="restore",
            preload_on_complete=True,
            added_at=iso(self._state.clock.now()),
        )

    async def run_queue(self, base_url: str) -> None:
        """依序下載排隊中的項目;`preloadOnComplete` 的下載完成後預先載入(keep_alive: -1,Q4)。"""
        remote = self._state.remote_ollama
        while (job := self._repo.next_queued()) is not None:
            self._repo.update(job["id"], state="downloading", started_at=iso(self._state.clock.now()))
            async for _ in await remote.pull_model(base_url=base_url, model=job["model"]):
                pass
            self._repo.update(job["id"], state="completed", pending_model=None, finished_at=iso(self._state.clock.now()))
            if job["preload_on_complete"]:
                await remote.preload(base_url=base_url, model=job["model"])
