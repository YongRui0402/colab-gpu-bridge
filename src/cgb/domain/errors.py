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
    # FR-017:寫出那一項的範圍(contracts/ui.openapi.yaml § components.schemas.Error.message)
    "INVALID_NUM_PARALLEL": "平行數要是 1~32 的整數",
    "INVALID_CONTEXT_LENGTH": "context 長度要是 2048~131072 的整數",
    "INVALID_MAX_LOADED_MODELS": "同時載入模型數要是 1~4 的整數",
    "NO_READY_SESSION": "目前沒有就緒的工作階段,請等工作階段就緒後再試。",
    "INVALID_CURATED_DESCRIPTION": "說明最多 200 個字。",
    "INVALID_AUTO_DOWNLOAD": "「開好就自動下載」只能是開或關。",
    "CURATED_DUPLICATE": "精選清單已經有這個模型(沒寫版本視為 latest)。",
    "CURATED_NOT_FOUND": "精選清單裡沒有這一筆,可能已被刪除,請重新整理畫面。",
    "AUTO_DOWNLOAD_RESULT_NOT_FOUND": "目前沒有自動下載的結果可以關閉(可能工作階段已結束),請重新整理畫面。",
    "OLLAMA_NOT_FOUND": "執行環境上沒有這個模型,請先下載。",
    "MODEL_ALREADY_DOWNLOADED": "執行環境上已經有這個模型,不必再下載。",
    "DOWNLOAD_ALREADY_QUEUED": "這個模型已經在下載佇列裡。",
    "DISK_SPACE_INSUFFICIENT": "執行環境的剩餘磁碟空間不夠放下這些模型(含佇列裡還沒下載完的),請少選一些。",
    "DISK_SPACE_UNKNOWN": "讀不到執行環境的剩餘磁碟空間,無法確認放不放得下,請稍後再試。",
    "DOWNLOAD_IN_PROGRESS": "這個模型正在下載,不能取消;請等它下載完成或失敗。",
    "DOWNLOAD_NOT_RETRYABLE": "只有下載失敗的項目可以重新排隊;這一筆是排隊中、下載中或已完成。",
    "DOWNLOAD_NOT_FOUND": "下載佇列裡已經沒有這一筆(工作階段結束時佇列會清空),請重新整理畫面。",
    "LIBRARY_NOT_FOUND": "官方模型庫找不到這個模型或版本,請確認名稱。",
    "LIBRARY_UNREACHABLE": "連不到 Ollama 官方模型庫,請稍後再試;也可以從精選清單挑選或直接輸入名稱。",
    "LIBRARY_SERVER_ERROR": "Ollama 官方模型庫暫時發生錯誤,請稍後再試;也可以從精選清單挑選或直接輸入名稱。",
    "LIBRARY_BAD_RESPONSE": "Ollama 官方模型庫的回應無法解讀(可能改版了);可以從精選清單挑選或直接輸入名稱。",
    "LIBRARY_TIMEOUT": "Ollama 官方模型庫在時限內沒有回應,請稍後再試;也可以從精選清單挑選或直接輸入名稱。",
    "LIBRARY_CLOUD_ONLY": "這個版本只能在 Ollama 雲端執行,不能下載到執行環境。",
    "OLLAMA_UNREACHABLE": "連不到執行環境上的 Ollama,請確認工作階段仍在運作後再試。",
    "OLLAMA_BAD_RESPONSE": "執行環境上的 Ollama 回應無法解讀,請稍後再試。",
    "OLLAMA_TIMEOUT": "執行環境上的 Ollama 在時限內沒有回應,請稍後再試。",
    "INVALID_IDLE_TIMEOUT": "閒置時限要是 1 到 1440 分鐘的整數。",
    "INVALID_BALANCE_THRESHOLD": "餘額警告門檻要是 0 到 10000 之間的數字。",
    "INVALID_MODEL_NAME": "模型名稱的格式不對,請從模型目錄選擇,或輸入官方名稱(小寫,例如 qwen2.5:7b)或 hf.co/<作者>/<模型>。",
    "EMPTY_MODEL_LIST": "沒有要下載的模型,請先選擇或輸入至少一個模型名稱。",
    "EMPTY_CHAT_MESSAGES": "沒有要送出的訊息,請先輸入內容。",
    "OLLAMA_BAD_REQUEST": "執行環境上的 Ollama 不接受這則請求,請稍後再試。",
    "OLLAMA_SERVER_ERROR": "執行環境上的 Ollama 處理時發生錯誤,請稍後再試。",
    "OLLAMA_STREAM_INTERRUPTED": "執行環境上的 Ollama 回應到一半就斷了,請稍後再試。",
    "SESSION_ENDED": "工作階段已結束,這次回應中斷。",
    "INVALID_CHAT_MESSAGE": "對話裡有一則訊息的格式不對(角色只能是 user 或 assistant,內容要是文字)。",
    "INVALID_QUERY": "關鍵字要有 1 到 100 個字(前後的空白不算),請重新輸入。",
    "INVALID_CURSOR": "載入更多的位置標記不正確,請重新搜尋。",
    "INVALID_HF_MODEL_ID": "模型的作者或名稱格式不對(只能用英數字、「.」、「_」、「-」,且要以英數字開頭),請從搜尋結果展開。",
    "HF_UNREACHABLE": "連不到 Hugging Face,請稍後再試;也可以從精選清單挑選、搜尋官方模型庫或直接輸入名稱。",
    "HF_SERVER_ERROR": "Hugging Face 暫時發生錯誤,請稍後再試;也可以從精選清單挑選、搜尋官方模型庫或直接輸入名稱。",
    "HF_BAD_RESPONSE": "Hugging Face 的回應無法解讀(可能改版了);可以從精選清單挑選、搜尋官方模型庫或直接輸入名稱。",
    "HF_AUTH_REQUIRED": "這個模型需要登入、同意條款、是私有的,或根本不存在,這一輪不支援下載;請改選其他模型。",
    "HF_NO_GGUF": "這個模型沒有可以下載的 GGUF 檔,請改選其他模型。",
    "HF_QUANT_UNAVAILABLE": "這個量化版本無法下載(不存在、是分割檔,或這個模型不是 GGUF),請改選其他版本。",
    "HF_TIMEOUT": "Hugging Face 在時限內沒有回應,請稍後再試;也可以從精選清單挑選、搜尋官方模型庫或直接輸入名稱。",
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
    "LIBRARY_CLOUD_ONLY": 422,
    "LIBRARY_UNREACHABLE": 502,
    "LIBRARY_SERVER_ERROR": 502,
    "LIBRARY_BAD_RESPONSE": 502,
    "LIBRARY_TIMEOUT": 504,
}


def library_error(code: str, model: str | None = None) -> ApiError:
    return ApiError(LIBRARY_STATUS.get(code, 502), code, model=model)


# contracts/ui.openapi.yaml § info.x-download-check-order (4):讀執行環境上的模型清單失敗時,依 S1 代碼原樣放在 `code`,沒有 `model`
OLLAMA_STATUS = {"OLLAMA_UNREACHABLE": 502, "OLLAMA_BAD_RESPONSE": 502, "OLLAMA_TIMEOUT": 504}


def ollama_error(code: str) -> ApiError:
    return ApiError(OLLAMA_STATUS.get(code, 502), code)


# contracts/ui.openapi.yaml § info.x-hf-error-status:Hugging Face 的失敗依 S2 代碼原樣放在 `code`(四個操作共用)
HF_STATUS = {
    "HF_UNREACHABLE": 502,
    "HF_SERVER_ERROR": 502,
    "HF_BAD_RESPONSE": 502,
    "HF_TIMEOUT": 504,
    "HF_AUTH_REQUIRED": 422,
    "HF_NO_GGUF": 422,
    "HF_QUANT_UNAVAILABLE": 422,
}


def hf_error(code: str, model: str | None = None) -> ApiError:
    return ApiError(HF_STATUS.get(code, 502), code, model=model)
