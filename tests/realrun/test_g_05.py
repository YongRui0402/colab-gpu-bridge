"""G-05(tasks.md T298):整批實跑的日誌、資料夾與錄下的回應裡都沒有 OAuth token(NFR-010)。

整批結束、P3 與 G-07 之後;`<暫存目錄>/data/colab-cli/token.json` 仍在。
- 從 token.json 取出 access token 與 refresh token 寫進 `<暫存目錄>` 裡 0600 的 pattern 檔,不印出;用完立即刪除。
- 每個來源只印 `grep -c -F -f <pattern 檔>` 的次數:
  P3 之前與 G-07 之後的 `docker compose logs`、`<暫存目錄>/data` 底下 token.json 與 sessions.json 以外的每個檔、
  實跑錄下的 UI API 回應與 SSE 事件(`<暫存目錄>/g05/`)、`<暫存目錄>/raw/` 的原始輸出。
- `<暫存目錄>/data` 底下有容器以 root 寫的 0600 檔(主機讀不到),這一部分在容器裡 grep;pattern 以 stdin 傳進去,不寫進容器。
- 先以已知的假 token 驗過兩條 grep(主機、容器)真的數得到。
不開執行環境,0 compute units,約 2 分鐘。判定者:腳本(次數 0)。
"""

import json
import os
import subprocess
from pathlib import Path

from realrun.helpers_container import CONTAINER, get_stack, private_file, verdict

FAKE_TOKEN = "cgb-test-fake-token-G05-0001"
# 容器裡:pattern 從 stdin 讀進變數,逐檔 grep(-a:sqlite 等二進位檔也照文字數)
CONTAINER_GREP = r"""
p=$(cat)
find /data -xdev -type f ! -name token.json ! -name sessions.json | sort | while read -r f; do
  n=$(printf '%s\n' "$p" | grep -a -c -F -f - "$f")
  printf '%s\t%s\n' "${n:-0}" "$f"
done
"""


def host_count(pattern: Path, target: Path) -> int:
    result = subprocess.run(["grep", "-a", "-c", "-F", "-f", str(pattern), str(target)], capture_output=True, text=True)
    return int(result.stdout.strip() or 0)


def container_counts(stack, patterns: str, root: str = "/data") -> dict[str, int]:
    script = CONTAINER_GREP if root == "/data" else CONTAINER_GREP.replace("/data -xdev", f"{root} -xdev")
    result = stack.docker_exec("sh", "-c", script, stdin=patterns, timeout=120)
    counts = {}
    for line in result.stdout.splitlines():
        n, _, path = line.partition("\t")
        if path:
            counts[path] = int(n or 0)
    return counts


def test_g_05(realrun):
    stack = get_stack(realrun)
    token_path = realrun.data / "colab-cli" / "token.json"
    pattern = realrun.root / "g05-patterns.txt"
    fake_pattern = realrun.root / "g05-fake-patterns.txt"
    fake_target = realrun.root / "g05-fake-target.txt"
    extra: list[str] = []
    try:
        # 先驗 grep 真的數得到(主機與容器各一次)
        for path, text in ((fake_pattern, FAKE_TOKEN + "\n"), (fake_target, f"x {FAKE_TOKEN} y\nz\n")):
            private_file(path).write_text(text, encoding="utf-8")
        host_ok = host_count(fake_pattern, fake_target) == 1
        stack.docker_exec("sh", "-c", f"mkdir -p /tmp/g05 && printf 'x {FAKE_TOKEN} y\\n' > /tmp/g05/f")
        container_ok = container_counts(stack, FAKE_TOKEN, "/tmp/g05").get("/tmp/g05/f") == 1
        stack.docker_exec("rm", "-rf", "/tmp/g05")
        assert host_ok and container_ok, f"grep 的自我檢查沒過(主機 {host_ok}、容器 {container_ok}),不能判定"

        try:
            raw_token = token_path.read_text(encoding="utf-8")
        except PermissionError:
            # 容器以 root 改寫過、主機讀不到時,從容器裡讀(只進記憶體,不印出)
            raw_token = stack.docker_exec("cat", "/data/colab-cli/token.json").stdout
            extra.append("token.json 主機讀不到,改由容器讀取")
        data = json.loads(raw_token)
        secrets = [data.get(k) for k in ("token", "access_token", "refresh_token") if isinstance(data.get(k), str) and data.get(k)]
        assert len(secrets) >= 2, f"token.json 裡找得到的 token 只有 {len(secrets)} 個(只檢查欄位,不印內容)"
        private_file(pattern).write_text("".join(s + "\n" for s in secrets), encoding="utf-8")
        patterns_text = pattern.read_text(encoding="utf-8")

        counts: dict[str, int] = {}
        stack.save_compose_logs("logs-after-g07.txt")
        for source in sorted(stack.g05.iterdir()) + sorted(realrun.raw_dir.iterdir()):
            if source.is_file():
                counts[f"主機 {source.relative_to(realrun.root)}"] = host_count(pattern, source)
        for path, n in container_counts(stack, patterns_text).items():
            counts[f"容器 {path}"] = n
        inspect = subprocess.run(["docker", "inspect", "-f", "{{json .Config.Env}}", CONTAINER], capture_output=True, text=True)
        env_count = subprocess.run(
            ["grep", "-c", "-F", "-f", str(pattern)], input=inspect.stdout, capture_output=True, text=True
        ).stdout.strip()
    finally:
        for path in (pattern, fake_pattern, fake_target):
            path.unlink(missing_ok=True)

    log = realrun.data / "colab-cli" / "colab.log"
    log_ok = log.is_symlink() and os.readlink(log) == os.devnull
    nonzero = {k: v for k, v in counts.items() if v}
    checks = {"則1": not nonzero, "則2": log_ok, "則3": env_count == "0"}
    if nonzero:
        extra.append(f"次數不是 0 的來源:{nonzero}")
    numbers = (
        f"掃了 {len(counts)} 個來源,次數不是 0 的 {len(nonzero)} 個;"
        f"docker inspect 環境變數 {env_count} 次;colab.log → /dev/null {log_ok}"
    )
    verdict("G-05", "T298", checks, numbers, "則1 每個來源 0 次;則2 colab.log 指向 /dev/null;則3 docker inspect 沒有 token", extra)
