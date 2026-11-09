#!/bin/sh
# E10 檔案系統:容器的 ENTRYPOINT。啟動前整理 /data 的目錄、權限與 Colab CLI 的兩個檔,再 exec 後端。
# 只看檔案的類型、權限與 settings.json 的一個欄位;不印出任何檔案的內容。
# 用法:cgb-prepare-data <後端指令...>   啟動前整理
#       cgb-prepare-data --check          健康檢查:/data 的配置仍然成立就 exit 0
set -eu

DATA=${CGB_DATA_DIR:-/data}
CLI=${CGB_COLAB_CONFIG_DIR:-$DATA/colab-cli}
SSH_DIR=$(dirname "${CGB_SSH_IDENTITY_PATH:-$DATA/ssh/id_ed25519}")

log_is_null() {
	[ -L "$CLI/colab.log" ] && [ "$(readlink "$CLI/colab.log")" = /dev/null ]
}

update_check_off() {
	python3 - "$CLI/settings.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
except (OSError, ValueError):
    sys.exit(1)
sys.exit(0 if isinstance(data, dict) and data.get("enable_update_check") is False else 1)
PY
}

mode_700() {
	[ "$(stat -c %a "$1")" = 700 ]
}

if [ "${1:-}" = "--check" ]; then
	for dir in "$DATA" "$CLI" "$SSH_DIR"; do
		[ -d "$dir" ] && [ -w "$dir" ] && mode_700 "$dir" || { echo "目錄不存在、不可寫或權限不是 0700:$dir" >&2; exit 1; }
	done
	log_is_null || { echo "$CLI/colab.log 不是指向 /dev/null 的符號連結" >&2; exit 1; }
	update_check_off || { echo "$CLI/settings.json 的 enable_update_check 不是 false" >&2; exit 1; }
	exit 0
fi

umask 077
mkdir -p "$DATA" "$CLI" "$CLI/history" "$SSH_DIR"

# Q59:CLI 以 DEBUG 等級寫 colab.log,內容含 Authorization token;一律導向 /dev/null。
# 原本若是一般檔(例如從桌機複製過來的),直接刪除,不保留含 token 的舊紀錄。
if ! log_is_null; then
	rm -f "$CLI/colab.log"
	ln -s /dev/null "$CLI/colab.log"
fi

# Q59:關掉 CLI 的更新檢查;settings.json 其他欄位保留,讀不懂的內容 CLI 本來就會當成預設值,直接改寫。
python3 - "$CLI/settings.json" <<'PY'
import json, sys
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = {}
except (OSError, ValueError):
    data = {}
data["enable_update_check"] = False
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY

# 權限:目錄 0700,其餘去掉 group 與 other 的權限;不跟隨符號連結(colab.log 指向 /dev/null),
# -xdev 不進 tmpfs 的 history/。
chmod 700 "$DATA" "$CLI" "$SSH_DIR"
find "$DATA" -xdev ! -type l -exec chmod go-rwx {} +

exec "$@"
