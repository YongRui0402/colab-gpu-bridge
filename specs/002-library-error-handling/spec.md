# 功能規格:官方模型庫的錯誤處理

**功能分支**:`002-library-error-handling`

**建立日期**:2026-11-13

**狀態**:草稿

**輸入**:使用者描述:「開第二個迭代 002,建立在 001-session-model-catalog 之上。範圍只有 E8 Ollama 官方模型庫的錯誤處理:`searchLibrary`、`listModelTags`、`getManifest` 遇到連不到、逾時、5xx、回應格式不符、找不到時,要照 001 的合約 `contracts/model-library.openapi.yaml` 回對應的錯誤代碼,不能把原生例外往上拋、讓 UI API 回 500。這是 001 完成報告與觀察紀錄 #33 記下的缺口(Q178 的模型庫部分)。不新增功能、不改 UI。這一輪要小,目標一小時內走完整個迭代。」

## 使用者情境與測試 *(必填)*

### 使用者故事 1 - 搜尋與看版本時模型庫出問題也知道原因(優先順序:P1)

使用者在「下載模型」頁搜尋 Ollama 官方模型庫或點開一個模型看版本時,ollama.com 可能連不到、太慢、回 5xx,或頁面改版解析不出來。這時 UI 要拿到合約定好的錯誤代碼與繁體中文說明,照 001 已經做好的畫面退回精選清單與「輸入名稱」,而不是收到 500、畫面停在讀取中或顯示英文的例外。

**為何是這個優先順序**:搜尋是使用者第一個碰到模型庫的地方;001 實測 ollama.com 連不到時搜尋回 500(Q178),版本清單完全沒接錯誤。只做完這個故事,下載模型頁在模型庫出問題時就不會壞掉。

**獨立測試**:以替身讓 ollama.com 依序表現為連不到、逾時、回 503、回改版後的 HTML、版本頁回 404 → 分別呼叫 UI API 的搜尋與版本清單 → 確認每一次的狀態碼與 `code` 都照 001 的 `ui.openapi.yaml`,`message` 是繁體中文,沒有任何一次是 500。

**驗收情境**:

1. **假如**ollama.com 連不到(DNS 失敗、連線被拒或 TLS 失敗),**當**使用者搜尋關鍵字,**則**UI API 回 502、`code` 為 `LIBRARY_UNREACHABLE`,畫面照 001 的 `library-down` 退回精選清單與「輸入名稱」。
2. **假如**ollama.com 在逾時內沒有回應,**當**使用者搜尋或點開版本,**則**UI API 在逾時到期後回 504、`code` 為 `LIBRARY_TIMEOUT`,`message` 是繁體中文。
3. **假如**ollama.com 回 5xx,**當**使用者搜尋或點開版本,**則**UI API 回 502、`code` 為 `LIBRARY_SERVER_ERROR`。
4. **假如**ollama.com 回 200 但搜尋頁找不到結果區塊,或第 2 頁起內容不是空白卻解析不出任何一筆,**當**使用者搜尋或按「顯示更多」,**則**UI API 回 502、`code` 為 `LIBRARY_BAD_RESPONSE`。
5. **假如**使用者點開的模型在官方模型庫不存在(版本頁回 404),**當**讀取版本清單,**則**UI API 回 404、`code` 為 `LIBRARY_NOT_FOUND`。
6. **假如**版本頁回 200 但一個 `/library/<名稱>:<版本>` 連結都解析不出來,或回了 404 與 5xx 以外的非預期狀態碼,**當**讀取版本清單,**則**UI API 回 502、`code` 為 `LIBRARY_BAD_RESPONSE`。
7. **假如**關鍵字在官方模型庫沒有符合的模型(200 且沒有 `/library/` 連結),**當**使用者搜尋,**則**照 001 回 200 與空的 `items`,不當成錯誤。

**功能需求**:

- **FR-001**:搜尋官方模型庫時,系統必須把 ollama.com 搜尋頁的失敗照 `model-library.openapi.yaml` 的 `searchLibrary` 歸成 `LIBRARY_UNREACHABLE`、`LIBRARY_TIMEOUT`、`LIBRARY_SERVER_ERROR` 或 `LIBRARY_BAD_RESPONSE`;沒有符合的模型與超過最後一頁仍是 0 筆的正常結果。
- **FR-002**:讀取一個模型的版本清單時,系統必須把 ollama.com 版本頁的失敗照 `listModelTags` 歸成 `LIBRARY_NOT_FOUND`(404)、`LIBRARY_UNREACHABLE`、`LIBRARY_TIMEOUT`、`LIBRARY_SERVER_ERROR` 或 `LIBRARY_BAD_RESPONSE`。
- **FR-003**:UI API 的搜尋與版本清單必須把上述代碼照 `ui.openapi.yaml` 的 `searchLibrary`、`listLibraryTags` 回對應的狀態碼:`LIBRARY_NOT_FOUND` 回 404,`LIBRARY_UNREACHABLE`、`LIBRARY_SERVER_ERROR`、`LIBRARY_BAD_RESPONSE` 回 502,`LIBRARY_TIMEOUT` 回 504。

**非功能需求**:

- 無

---

### 使用者故事 2 - 試算與加入下載時取不到模型大小也知道原因(優先順序:P1)

使用者勾好模型按「加入下載」,系統要向 registry 取每個模型的 manifest 算精確大小。registry 連不到、逾時、回 5xx、回的不是 manifest,或模型與版本不存在時,UI 要拿到合約定好的錯誤代碼、說明與是哪一個模型出問題,整批不加入佇列,而不是收到 500。

**為何是這個優先順序**:001 的試算與加入下載只認得 `LIBRARY_NOT_FOUND` 與 `LIBRARY_CLOUD_ONLY` 兩個代碼,其他失敗一律回 500(Q203);這是使用者真的要下載模型時會卡住的地方,和故事 1 一樣重要。

**獨立測試**:工作階段就緒(替身)→ 以替身讓 registry 依序表現為連不到、逾時、回 503、回不是 JSON 的內容、回 404 → 分別呼叫 UI API 的試算與加入下載 → 確認狀態碼、`code` 與 `model` 都照 `ui.openapi.yaml`,下載佇列沒有多出任何一筆,沒有任何一次是 500。

**驗收情境**:

1. **假如**工作階段就緒且 registry 連不到,**當**使用者按「加入下載」試算,**則**UI API 回 502、`code` 為 `LIBRARY_UNREACHABLE`,`model` 指出取不到的那一個。
2. **假如**registry 在逾時內沒有回應,**當**試算或確認加入下載,**則**UI API 回 504、`code` 為 `LIBRARY_TIMEOUT`,佇列不變。
3. **假如**registry 回 5xx,**當**試算或確認加入下載,**則**UI API 回 502、`code` 為 `LIBRARY_SERVER_ERROR`,佇列不變。
4. **假如**registry 回 200 但內容不是 manifest 的格式,或回了 404 與 5xx 以外的非預期狀態碼,**當**試算或確認加入下載,**則**UI API 回 502、`code` 為 `LIBRARY_BAD_RESPONSE`,佇列不變。
5. **假如**勾選了三個模型、第二個在 registry 不存在,**當**確認加入下載,**則**UI API 回 404、`code` 為 `LIBRARY_NOT_FOUND`、`model` 是第二個,三個都沒有加入佇列。

**功能需求**:

- **FR-004**:取一個版本的 manifest 時,系統必須把 registry 的失敗照 `getManifest` 歸成 `LIBRARY_NOT_FOUND`(404)、`LIBRARY_UNREACHABLE`、`LIBRARY_TIMEOUT`、`LIBRARY_SERVER_ERROR`、`LIBRARY_BAD_RESPONSE`,200 但 `layers` 是空陣列時歸成 `LIBRARY_CLOUD_ONLY`。
- **FR-005**:UI API 的試算與加入下載必須把上述代碼照 `ui.openapi.yaml` 的 `estimateDownloads`、`enqueueDownloads` 回對應的狀態碼(`LIBRARY_NOT_FOUND` 回 404、`LIBRARY_CLOUD_ONLY` 回 422、`LIBRARY_UNREACHABLE`、`LIBRARY_SERVER_ERROR`、`LIBRARY_BAD_RESPONSE` 回 502、`LIBRARY_TIMEOUT` 回 504),並以 `model` 指出取不到的那一個;任何一個失敗時整批不加入佇列。

**非功能需求**:

- 無

---

### 邊界情況

- 搜尋第 2 頁起 ollama.com 回 303 導回第 1 頁:是非預期的狀態碼,歸 `LIBRARY_BAD_RESPONSE`,不跟著導向去讀第 1 頁。
- 搜尋頁碼超過最後一頁:ollama.com 回 200 與只有空白的內容,是 0 筆的正常結果,不是格式不符。
- 搜尋第 2 頁起只有社群模型:過濾後官方模型是 0 筆,但頁面有結果,是正常結果,不是格式不符(technical-research R3)。
- registry 對「沒有這個模型」與「沒有這個版本」回的 404 內容相同:兩種都歸 `LIBRARY_NOT_FOUND`,不必分辨。
- 連上了但讀回應到一半連線中斷:沒有完整的 HTTP 回應,和連不到同樣歸 `LIBRARY_UNREACHABLE`;讀到一半逾時歸 `LIBRARY_TIMEOUT`。
- 版本頁解析出部分版本、部分欄位(例如大小)解析不出來:只要有至少一個版本連結就不算格式不符,解析不出的欄位照 001 留空。
- 模型庫失敗時,執行環境上已下載的模型、正在下載的項目與精選清單都不受影響。

## 全域需求 *(必填)*

### 功能需求

- **FR-006**(適用:使用者故事 1、2):三個模型庫操作都必須以同一套規則歸類傳輸層的失敗:DNS 失敗、連線被拒、TLS 失敗與讀回應時連線中斷歸 `LIBRARY_UNREACHABLE`,連線或讀取逾時歸 `LIBRARY_TIMEOUT`;任何底層程式庫的例外都不得越過轉接層往上拋。

### 非功能需求

- **NFR-001**(適用:使用者故事 1、2):每一個對 ollama.com 或 registry 的請求逾時為 10 秒(沿用 001 `ui.openapi.yaml` 的 `x-timeout`,Q12);試算與加入下載依序取多個 manifest 時,逾時對每個請求各自計算。
- **NFR-002**(適用:使用者故事 1、2):回給 UI 的每一個 `LIBRARY_*` 錯誤都必須帶繁體中文的 `message`,取自後端固定的訊息表;不得把底層例外的文字、traceback 或對方的網址放進回應。

## 關鍵實體

- **模型庫錯誤(LibraryError)**:轉接層把官方模型庫的一次失敗歸成的原因。屬性:代碼(`LIBRARY_UNREACHABLE`、`LIBRARY_TIMEOUT`、`LIBRARY_SERVER_ERROR`、`LIBRARY_BAD_RESPONSE`、`LIBRARY_NOT_FOUND`、`LIBRARY_CLOUD_ONLY`)、給人讀的說明。UI API 依操作把它對應到狀態碼,試算與加入下載另外帶出是哪一個模型。

## 成功標準 *(必填)*

### 可衡量成果

- **SC-001**:`model-library.openapi.yaml` 三個操作列出的每一種失敗(連不到、逾時、5xx、格式不符或非預期狀態碼、找不到、只能在雲端執行),經 UI API 對應的四個操作(搜尋、版本清單、試算、加入下載)回出的狀態碼與 `code` 100% 符合 `ui.openapi.yaml`,沒有任何一個組合回 500。
- **SC-002**:模型庫在逾時內沒有回應時,搜尋、版本清單與只勾一個模型的試算,從送出到收到 504 `LIBRARY_TIMEOUT` 都在 11 秒內(10 秒逾時加 1 秒餘裕);勾多個模型時不另設總時限,由 NFR-001 的每請求 10 秒保證。
- **SC-003**:對真的 ollama.com 與 registry 唯讀實跑一次:搜尋 `qwen2.5` 至少有一筆官方模型、`qwen2.5` 的版本清單每個版本都有大小、`qwen2.5:7b` 的 manifest 大小大於 0,和 001 的結果一致(正常路徑沒有退化)。

## 假設

- 錯誤代碼、HTTP 狀態碼與歸類條件全部沿用 001 的 `contracts/model-library.openapi.yaml` 與 `contracts/ui.openapi.yaml`,這一輪不改合約;UI 已經依 `code` 與 `message` 顯示失敗(`library-down`、`cloud-only` 等),這一輪不改 UI。
- 失敗時不自動重試;使用者可以再按一次搜尋或加入下載。
- 模型庫失敗時不另外寫後端日誌;維護的人靠 UI API 回的 `code` 與重現請求查原因,日誌沿用 001 的規則(只記請求的時間、模型、耗時與狀態碼)。
- 錯誤情境以注入替身驗收(ollama.com 無法配合壞掉);正常路徑另以唯讀實跑確認,不開 Colab、不花 compute units。
- 不在範圍內:UI API 的 400 輸入驗證(`INVALID_QUERY`、`INVALID_PAGE`、`INVALID_MODEL_NAME`、`EMPTY_MODEL_LIST`)、`DOWNLOAD_NOT_FOUND`、`CURATED_NOT_FOUND`、精選清單 PUT 重複名稱回 500、遠端 Ollama 與 Colab CLI 轉接層的錯誤處理、下載過程中(pull)的失敗,以及 001 完成報告列的其他 Q178、Q203 項目;留到之後的迭代。
- 「顯示更多」第 2 頁載入空的(001 Q208)、模型目錄太慢(Q179)、預先載入無效不在這一輪範圍。

## 釐清紀錄

### 2026-11-13 釐清

- 問:範圍只修轉接層,還是連 UI API 呼叫它的四個操作一起修?(A 轉接層加 UI API 四個操作的 `LIBRARY_*` 轉接(建議);B 只修轉接層;C A 再加 400 輸入驗證) → 答:A(kevin-twin 代為決定,理由見 `分身決策紀錄.md` D1)
- 問:驗收只用替身,還是加對真的 ollama.com 的實跑?(A 錯誤用替身、正常路徑唯讀實跑一次(建議);B 只用替身;C 對真的服務製造錯誤) → 答:A(kevin-twin 代為決定,理由見 `分身決策紀錄.md` D2)
- 問:模型庫失敗時,維護的人在後端日誌看得到什麼?(A 不另外加,沿用 001 的日誌規則(建議);B 記一行含操作、代碼與對方狀態碼的 warning;C 記完整例外與 traceback) → 答:A(kevin-twin 代為決定,理由見 `分身決策紀錄.md` D4)
- 問:SC-002 的 11 秒怎麼量?(A 以單一請求量,多個模型不另設總時限(建議);B 多個模型時總時限 N×10+1 秒) → 答:A(kevin-twin 代為決定,理由見 `分身決策紀錄.md` D5)
