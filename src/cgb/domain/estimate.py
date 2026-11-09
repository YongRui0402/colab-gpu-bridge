"""下載前的試算(FR-022;contracts/ui.openapi.yaml § DownloadEstimate)。"""

from typing import Any

# 預估下載速度 50 MB/s(research.md R5 的估算),UI 標示為估計值
DOWNLOAD_BYTES_PER_SECOND = 50_000_000


def estimate(sized: list[tuple[str, int]], *, pending_queue_bytes: int, free_disk_bytes: int, disk_checked_at: str) -> dict[str, Any]:
    """`sized` 是(名稱含版本, manifest `layers[].size` 的總和)。"""
    total = sum(size for _, size in sized)
    return {
        "items": [{"name": name, "sizeBytes": size} for name, size in sized],
        "totalBytes": total,
        "pendingQueueBytes": pending_queue_bytes,
        "freeDiskBytes": free_disk_bytes,
        "diskCheckedAt": disk_checked_at,
        "fits": total + pending_queue_bytes <= free_disk_bytes,
        "estimatedSeconds": total // DOWNLOAD_BYTES_PER_SECOND,
    }
