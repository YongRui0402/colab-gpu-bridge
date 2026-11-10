"""US2-AJ-04 送到 Colab 執行環境的只讀腳本(tasks.md T184):印出 TCP 監聽位址,不安裝、不寫入任何東西。

有 `ss` 就印 `ss -ltn` 的原文;沒有就讀 `/proc/net/tcp`、`/proc/net/tcp6` 的 LISTEN(狀態 0A)列。
最後一行是 `CGB-LISTEN <JSON>`:`[[位址, port], ...]`,給量測腳本解析。
"""

import json
import shutil
import subprocess

listening = []
if shutil.which("ss"):
    out = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=10).stdout
    print(out)
    for line in out.splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 4 and ":" in cols[3]:
            addr, _, port = cols[3].rpartition(":")
            listening.append([addr.strip("[]"), int(port)])
else:
    for path, v6 in (("/proc/net/tcp", False), ("/proc/net/tcp6", True)):
        try:
            with open(path) as f:
                rows = f.read().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            cols = row.split()
            if len(cols) < 4 or cols[3] != "0A":
                continue
            hex_addr, hex_port = cols[1].split(":")
            if v6:
                addr = "::1" if hex_addr == "00000000000000000000000001000000" else ("::" if set(hex_addr) == {"0"} else hex_addr)
            else:
                addr = ".".join(str(int(hex_addr[i : i + 2], 16)) for i in (6, 4, 2, 0))
            listening.append([addr, int(hex_port, 16)])
print("CGB-LISTEN " + json.dumps(listening))
