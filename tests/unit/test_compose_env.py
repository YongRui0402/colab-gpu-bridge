"""E11 部署與網路(006 testplan.md § 2.3;deploy/compose.yaml)。

接縫:讀專案根目錄的 `compose.yaml`;專案沒有 YAML 函式庫,照縮排讀出 `services.cgb` 底下的
`environment` 與 `ports`(plan.md Q29),不執行 `docker compose`。
"""

from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[2] / "compose.yaml"


def service_section(service: str, key: str) -> list[str]:
    """`services.<service>.<key>` 底下的每一行(去掉縮排與註解);只認 compose.yaml 固定的兩格縮排。"""
    lines = COMPOSE.read_text(encoding="utf-8").splitlines()
    start = lines.index("services:")
    in_service = in_key = False
    found: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line.startswith(" "):
            break  # 離開 services
        if line.startswith("  ") and not line.startswith("   "):
            in_service = line.strip() == f"{service}:"
            in_key = False
            continue
        if not in_service:
            continue
        if line.startswith("    ") and not line.startswith("     "):
            in_key = line.strip() == f"{key}:"
            continue
        stripped = line.strip()
        if in_key and stripped and not stripped.startswith("#"):
            found.append(stripped)
    return found


# ---- 006 US1-DEP-01


def test_容器拿得到主機那一側的相容端點_port_對外的_port_不變() -> None:
    # Arrange / Act
    environment = dict(item.split(": ", 1) for item in service_section("cgb", "environment"))
    ports = service_section("cgb", "ports")

    # Assert:則1
    assert environment.get("CGB_PUBLIC_OLLAMA_PORT") == "${CGB_HOST_OLLAMA_PORT:-11434}", environment
    # Assert:則2
    assert '- "${CGB_BIND_ADDR:-0.0.0.0}:${CGB_HOST_OLLAMA_PORT:-11434}:11434"' in ports, ports
