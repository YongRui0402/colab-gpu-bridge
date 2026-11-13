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
    "NO_READY_SESSION": "目前沒有就緒的工作階段,請等工作階段就緒後再試。",
    "INVALID_CURATED_DESCRIPTION": "說明最多 200 個字。",
    "CURATED_DUPLICATE": "精選清單已經有這個模型(沒寫版本視為 latest)。",
    "OLLAMA_NOT_FOUND": "執行環境上沒有這個模型,請先下載。",
    "MODEL_ALREADY_DOWNLOADED": "執行環境上已經有這個模型,不必再下載。",
    "DOWNLOAD_ALREADY_QUEUED": "這個模型已經在下載佇列裡。",
    "DISK_SPACE_INSUFFICIENT": "執行環境的剩餘磁碟空間不夠放下這些模型(含佇列裡還沒下載完的),請少選一些。",
    "DISK_SPACE_UNKNOWN": "讀不到執行環境的剩餘磁碟空間,無法確認放不放得下,請稍後再試。",
    "DOWNLOAD_IN_PROGRESS": "這個模型正在下載,不能取消;請等它下載完成或失敗。",
    "LIBRARY_NOT_FOUND": "官方模型庫找不到這個模型或版本,請確認名稱。",
    "LIBRARY_UNREACHABLE": "連不到 Ollama 官方模型庫,請稍後再試;也可以從精選清單挑選或直接輸入名稱。",
    "LIBRARY_SERVER_ERROR": "Ollama 官方模型庫暫時發生錯誤,請稍後再試;也可以從精選清單挑選或直接輸入名稱。",
    "LIBRARY_BAD_RESPONSE": "Ollama 官方模型庫的回應無法解讀(可能改版了);可以從精選清單挑選或直接輸入名稱。",
    "LIBRARY_TIMEOUT": "Ollama 官方模型庫在時限內沒有回應,請稍後再試;也可以從精選清單挑選或直接輸入名稱。",
    "LIBRARY_CLOUD_ONLY": "這個版本只能在 Ollama 雲端執行,不能下載到執行環境。",
    "INVALID_IDLE_TIMEOUT": "閒置時限要是 1 到 1440 分鐘的整數。",
    "INVALID_BALANCE_THRESHOLD": "餘額警告門檻要是 0 到 10000 之間的數字。",
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

    def __init__(self, status: int, code: str, *, model: str | None = None, reason_code: str | None = None) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.model = model
        self.reason_code = reason_code

    def body(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": MESSAGES[self.code]}
        if self.model is not None:
            # 下載相關的錯誤指出是哪一個模型(Error.model)
            body["model"] = self.model
        if self.reason_code is not None:
            # `DISK_SPACE_UNKNOWN` 的外部原因(S8 的 `COLAB_` 代碼)
            body["reasonCode"] = self.reason_code
        return body


# contracts/ui.openapi.yaml § submitAuthorizationCode:Google 的失敗依 S3 代碼原樣放在 `code`
_OAUTH_STATUS = {"OAUTH_INVALID_GRANT": 400, "OAUTH_SCOPE_NOT_GRANTED": 400, "OAUTH_TIMEOUT": 504}


def oauth_error(code: str) -> ApiError:
    return ApiError(_OAUTH_STATUS.get(code, 502), code)


# contracts/ui.openapi.yaml § components.schemas.Error:模型庫的失敗依 S2 代碼原樣放在 `code`(002 research.md R4)
LIBRARY_STATUS = {
    "LIBRARY_NOT_FOUND": 404,
    "LIBRARY_UNREACHABLE": 502,
    "LIBRARY_SERVER_ERROR": 502,
    "LIBRARY_BAD_RESPONSE": 502,
    "LIBRARY_TIMEOUT": 504,
}


def library_error(code: str, model: str | None = None) -> ApiError:
    return ApiError(LIBRARY_STATUS.get(code, 502), code, model=model)
