"""Ollama 相容端點的路由(contracts/ollama-compat.openapi.yaml § paths)。

白名單只看路徑,不看方法:白名單路徑用錯方法也照轉送,回遠端 Ollama 自己的 405(plan.md Q18)。
"""

from fastapi import APIRouter, Request
from fastapi.responses import Response

from cgb.ollama_compat.forward import V1_PREFIX, forward, ollama_error, openai_error

# FR-011 點名的推論與查詢路徑(contracts/ollama-compat.openapi.yaml § paths 的白名單)
WHITELIST = frozenset(
    {"/", "/api/version", "/api/tags", "/api/ps", "/api/show", "/api/generate", "/api/chat", "/api/embed", "/api/embeddings"}
)

# FR-009 開放的 OpenAI 相容路徑(contracts/ollama-compat.openapi.yaml § paths./v1/*);`/v1/` 底下不在這裡的路徑一律 404
V1_WHITELIST = frozenset({"/v1/chat/completions", "/v1/models"})

# FR-012 管理模型的操作 → 這類操作的名稱(給 403 的說明用);`/api/blobs/{digest}` 屬於建立(plan.md Q21)
MANAGED_PATHS = {
    "/api/pull": "下載模型",
    "/api/push": "推送模型",
    "/api/create": "建立模型",
    "/api/copy": "複製模型",
    "/api/delete": "刪除模型",
}
BLOBS_PREFIX = "/api/blobs/"

# FR-013:沒有就緒的工作階段時的說明,括號裡的狀態依當下而定(代碼 NO_READY_SESSION 不出現在本文裡)
NO_READY_SESSION_MESSAGE = "目前沒有可用的工作階段:{},請稍後再試,或到 UI 查看狀態"
_STATE_DESCRIPTIONS = {
    "none": "尚未開啟工作階段",
    "opening": "工作階段開啟中",
    "reconnecting": "工作階段重連中",
    "ending": "工作階段結束中",
    "ended": "工作階段已結束",
    "open_failed": "工作階段開啟失敗",
    "lost": "工作階段已失聯",
}

ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

router = APIRouter()


def managed_operation(path: str) -> str | None:
    """管理模型的操作回它的名稱,其他路徑回 None。"""
    if path.startswith(BLOBS_PREFIX):
        return MANAGED_PATHS["/api/create"]
    return MANAGED_PATHS.get(path)


def managed_message(operation: str) -> str:
    return f"{operation}請到 UI 操作;Ollama 相容端點不執行這個操作"


def no_ready_session_message(state: str) -> str:
    return NO_READY_SESSION_MESSAGE.format(_STATE_DESCRIPTIONS.get(state, "工作階段尚未就緒"))


def unlisted_message(path: str) -> str:
    return f"Ollama 相容端點不提供 {path};只開放 Ollama 的推論與查詢 API(/api/generate、/api/chat、/api/embed、/api/tags 等)"


def unlisted_v1_message(path: str) -> str:
    return f"Ollama 相容端點不提供 {path};/v1 只開放 /v1/chat/completions 與 /v1/models"


@router.api_route("/{path:path}", methods=ALL_METHODS)
async def ollama_endpoint(request: Request) -> Response:
    managed = managed_operation(request.url.path)
    if managed is not None:
        # 不論方法與工作階段狀態,不轉送、不讀本文(contracts/ollama-compat.openapi.yaml 處理順序 (1))
        return ollama_error(managed_message(managed), 403)
    if request.url.path.startswith(V1_PREFIX) and request.url.path not in V1_WHITELIST:
        # `/v1/` 底下沒開放的路徑:OpenAI 格式的 404(FR-011),不轉送、不讀本文
        return openai_error(unlisted_v1_message(request.url.path), 404, "unsupported_path", "invalid_request_error")
    if request.url.path not in WHITELIST and request.url.path not in V1_WHITELIST:
        # 白名單外不轉送、不讀本文(x-unlisted-paths;`/v1/` 底下沒開放的路徑已在上面用 OpenAI 格式回 404)
        return ollama_error(unlisted_message(request.url.path), 404)
    services = request.app.state.services_of()
    target = services.lifecycle.forward_target()
    if target is None:
        # 不排隊、不轉送,立即回(FR-013、SC-007)
        message = no_ready_session_message(services.lifecycle.current()["state"])
        if request.url.path.startswith(V1_PREFIX):
            return openai_error(message, 503, "no_ready_session", "service_unavailable")
        return ollama_error(message, 503)
    # 串流中途斷線:不等下一個排程,立刻做健康檢查(斷了就進入重連,FR-004)
    return await forward(request.app.state.forward_client, request, target, on_interrupted=services.monitor.check_now)
