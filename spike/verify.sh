#!/usr/bin/env bash
# 桌機端驗證:從 .env 讀 COLAB_OLLAMA_URL,不印出網址本身
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(stat -c %a .env)" = 600 ] || { echo ".env 權限不是 600"; exit 1; }
URL=$(grep -E '^COLAB_OLLAMA_URL=' .env | head -1 | cut -d= -f2-)
[ -n "$URL" ] || { echo ".env 沒有 COLAB_OLLAMA_URL=... 這一行(或格式不符)"; exit 1; }
echo "網址長度 ${#URL}, sha256 前 8 碼 $(printf %s "$URL" | sha256sum | cut -c1-8)"
echo "== version";  curl -sS -m 15 "$URL/api/version"; echo
echo "== tags";     curl -sS -m 15 "$URL/api/tags" | python3 -c 'import sys,json;print([m["name"] for m in json.load(sys.stdin)["models"]])'
echo "== generate(從桌機)"
curl -sS -m 120 "$URL/api/generate" -d '{"model":"qwen2.5:0.5b","prompt":"Say hi in five words.","stream":false}' \
 | python3 -c 'import sys,json;r=json.load(sys.stdin);print("回應:",r["response"].strip());print("eval tokens/s:",round(r["eval_count"]/r["eval_duration"]*1e9,1));print("total 秒:",round(r["total_duration"]/1e9,2))'
echo "== ps(遠端)"; curl -sS -m 15 "$URL/api/ps" | python3 -c 'import sys,json;[print(m["name"],"size_vram=",m.get("size_vram")) for m in json.load(sys.stdin)["models"]]'
