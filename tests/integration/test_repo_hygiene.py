"""全域:機密與資料不進版本控制、也不送進映像的 build context(testplan.md § G-03;spec.md § NFR-010)。

testplan 寫的 `deploy/Dockerfile.dockerignore` 依 plan.md Q85、Q118 搬到 repo 根目錄的 `Dockerfile.dockerignore`。
`.gitignore` 的排除與否交給 git 自己判定(`git check-ignore --no-index`,在暫存的空 repo 裡只放這份 `.gitignore`);
dockerignore 照 Docker 的規則判定:每一行依序比對路徑本身或它的上層目錄,`!` 開頭是放行,最後比對到的那一行決定。
"""

import fnmatch
import subprocess
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[2]
DOCKERIGNORE = REPO / "Dockerfile.dockerignore"

FORBIDDEN_NAMES = ("token.json", "sessions.json", ".env")


def tracked_files() -> list[str]:
    result = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True)
    return result.stdout.splitlines()


def forbidden(path: str) -> bool:
    name = PurePosixPath(path).name
    return name in FORBIDDEN_NAMES or name.startswith("id_ed25519") or name.endswith(".sqlite3")


def git_ignores(gitignore: Path, paths: list[str], workdir: Path) -> dict[str, bool]:
    """在只有這份 `.gitignore` 的暫存 repo 裡,問 git 每個路徑是否被排除。"""
    subprocess.run(["git", "init", "-q", str(workdir)], check=True)
    (workdir / ".gitignore").write_text(gitignore.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"], cwd=workdir, input="\n".join(paths), capture_output=True, text=True
    )
    ignored = set(result.stdout.splitlines())
    return {path: path in ignored for path in paths}


def docker_ignores(dockerignore: Path, path: str) -> bool:
    excluded = False
    parts = PurePosixPath(path).parts
    candidates = ["/".join(parts[: i + 1]) for i in range(len(parts))]
    for raw in dockerignore.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        pattern = line.removeprefix("!").strip("/")
        if any(fnmatch.fnmatchcase(candidate, pattern) for candidate in candidates):
            excluded = not negate
    return excluded


def test_追蹤的檔案沒有授權_金鑰_env_與資料庫() -> None:
    # Act
    files = tracked_files()

    # Assert(則1)
    assert files, "git ls-files 沒有列出任何檔案"
    assert [path for path in files if forbidden(path)] == []


def test_gitignore_排除_env_資料夾與資料庫(tmp_path: Path) -> None:
    # Arrange
    paths = [".env", "data/cgb.sqlite3", "data/colab-cli/token.json", "cgb.sqlite3", "tests/x/cgb.sqlite3"]

    # Act
    ignored = git_ignores(REPO / ".gitignore", paths, tmp_path / "probe")

    # Assert(則2)
    assert ignored == dict.fromkeys(paths, True)


def test_dockerignore_排除_env_與資料夾() -> None:
    # Act
    ignored = {path: docker_ignores(DOCKERIGNORE, path) for path in (".env", "data", "data/cgb.sqlite3", "data/colab-cli/token.json")}

    # Assert(則3);對照:Dockerfile 要 COPY 的檔沒有被排除,確認判定不是一律回「排除」
    assert ignored == dict.fromkeys(ignored, True)
    assert not docker_ignores(DOCKERIGNORE, "src/cgb/app.py") and not docker_ignores(DOCKERIGNORE, "pyproject.toml")
