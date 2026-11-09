"""對外的錯誤代碼與給使用者看的繁體中文訊息(contracts/ui.openapi.yaml § components.schemas.Error)。"""

from typing import Any

MESSAGES: dict[str, str] = {
    "INVALID_REQUEST_BODY": "請求的內容格式不對。",
    "SESSION_ALREADY_ACTIVE": "已有工作階段正在開啟、就緒或重連中,同一時間只能有一個工作階段。",
    "SESSION_ENDING": "目前的工作階段正在結束,請等它結束後再開啟。",
    "AUTH_REQUIRED": "Colab 帳號尚未登入或授權已過期,請先登入 Colab。",
    "NO_ACTIVE_SESSION": "目前沒有可以結束的工作階段。",
    "AUTH_LINK_EXPIRED": "授權連結已失效,請重新取得授權連結。",
    "OAUTH_INVALID_GRANT": "授權碼錯誤、已用過或已過期,請用同一個連結重新取得授權碼後再送出,或重新取得授權連結。",
    "OAUTH_SCOPE_NOT_GRANTED": "沒有勾選 Colab 的權限,請重新授權並勾選全部權限。",
    "OAUTH_TIMEOUT": "Google 在時限內沒有回應,請稍後再試。",
    "OAUTH_UNREACHABLE": "連不到 Google,請確認網路後再試。",
    "OAUTH_SERVER_ERROR": "Google 暫時發生錯誤,請稍後再試。",
    "OAUTH_BAD_RESPONSE": "Google 的回應無法使用,請重新取得授權連結再試一次。",
    "OAUTH_INVALID_REQUEST": "登入設定有誤,無法向 Google 換得授權。",
    "OAUTH_INVALID_CLIENT": "登入設定有誤,無法向 Google 換得授權。",
    "OAUTH_UNAUTHORIZED_CLIENT": "登入設定有誤,無法向 Google 換得授權。",
    "OAUTH_UNSUPPORTED_GRANT_TYPE": "登入設定有誤,無法向 Google 換得授權。",
    "OAUTH_INVALID_SCOPE": "登入設定有誤,無法向 Google 換得授權。",
    "SESSION_NOT_FOUND": "沒有這個工作階段的紀錄。",
    "INVALID_RUNTIME_TYPE": "不支援這種執行階段類型,請從清單選擇 T4、L4、G4、A100 或 H100。",
}


# 非同步失敗的 `reasonCode`(轉接層代碼)對應給使用者看的說明;只用這張表,不把轉接層的原始訊息交給 UI(NFR-010)
REASON_MESSAGES: dict[str, str] = {
    "COLAB_ALLOCATION_REFUSED": "Colab 暫時拒絕配置執行環境(可能同時開太多,或這種類型暫時沒有容量),請稍後再試或換一種類型。",
}
REASON_FALLBACK_MESSAGE = "開啟執行環境失敗,請稍後再試。"


def reason_message(code: str) -> str:
    return REASON_MESSAGES.get(code, REASON_FALLBACK_MESSAGE)


# FR-007:釋放不了時在 UI 明確警告(Session.releaseWarning.message)
RELEASE_WARNING_MESSAGE = "無法確認 Colab 已釋放這個執行環境,它可能仍在扣 compute units;請再按一次「結束」,或到 Colab 網頁手動結束。"


class ApiError(Exception):
    """以 HTTP 錯誤回給 UI 的情況;`code` 是 `Error.code`。"""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code

    def body(self) -> dict[str, Any]:
        return {"code": self.code, "message": MESSAGES[self.code]}


# contracts/ui.openapi.yaml § submitAuthorizationCode:Google 的失敗依 S3 代碼原樣放在 `code`
_OAUTH_STATUS = {"OAUTH_INVALID_GRANT": 400, "OAUTH_SCOPE_NOT_GRANTED": 400, "OAUTH_TIMEOUT": 504}


def oauth_error(code: str) -> ApiError:
    return ApiError(_OAUTH_STATUS.get(code, 502), code)
