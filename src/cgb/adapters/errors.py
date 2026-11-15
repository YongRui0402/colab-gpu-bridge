"""五個轉接層(Colab CLI、SSH 通道、遠端 Ollama、官方模型庫、Google OAuth)共用的錯誤。

`code` 是各規格檔 `components.schemas.Error` 列出的錯誤代碼;
`stderr_last_line` 只放外部程式 stderr 的最後一行(已遮蔽網址),沒有就是 None。
`remote_stage` 是遠端腳本回報失敗的階段(Colab CLI 的 `Error.remoteStage`),沒有回報就是 None。
"""


class AdapterError(Exception):
    def __init__(
        self, code: str, message: str, stderr_last_line: str | None = None, *, remote_stage: str | None = None
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.stderr_last_line = stderr_last_line
        self.remote_stage = remote_stage
