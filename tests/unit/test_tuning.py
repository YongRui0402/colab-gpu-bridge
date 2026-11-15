"""E2 `domain/tuning.py` 的級距(testplan.md § 2.2,US1-API-11~16;spec FR-002、FR-003)。

接縫:`domain/tuning.py` 純函式(testplan.md § 接縫的取捨)。1 GiB = 1073741824 位元組。
"""

from cgb.domain import tuning

GIB = 1073741824


# ---- 005 US1-API-11


def test_未滿_12_GiB_的顯示記憶體用第一級():
    # Arrange
    vram = [0, 6 * GIB, 12_000_000_000, 12 * GIB - 1]  # 12_000_000_000 是十進位的 12 GB,約 11.18 GiB

    # Act
    tiers = [tuning.auto_tier(v) for v in vram]

    # Assert
    assert tiers == [(1, 4096, 1)] * 4


# ---- 005 US1-API-12


def test_12_GiB_起到未滿_20_GiB_用第二級():
    # Arrange
    vram = [12 * GIB, 15 * GIB, 20 * GIB - 1]  # 15 GiB 是 T4

    # Act
    tiers = [tuning.auto_tier(v) for v in vram]

    # Assert
    assert tiers == [(2, 4096, 1)] * 3


# ---- 005 US1-API-13


def test_20_GiB_起到未滿_32_GiB_用第三級():
    # Arrange
    vram = [20 * GIB, int(22.5 * GIB), 32 * GIB - 1]  # 22.5 GiB 是 L4

    # Act
    tiers = [tuning.auto_tier(v) for v in vram]

    # Assert
    assert tiers == [(4, 8192, 1)] * 3


# ---- 005 US1-API-14


def test_32_GiB_起到未滿_64_GiB_用第四級():
    # Arrange
    vram = [32 * GIB, 40 * GIB, 64 * GIB - 1]  # 40 GiB 是 A100

    # Act
    tiers = [tuning.auto_tier(v) for v in vram]

    # Assert
    assert tiers == [(8, 8192, 2)] * 3


# ---- 005 US1-API-15


def test_64_GiB_以上用最高一級_沒有上限():
    # Arrange
    vram = [64 * GIB, 80 * GIB, 96 * GIB]  # 80 GiB 是 H100

    # Act
    tiers = [tuning.auto_tier(v) for v in vram]

    # Assert
    assert tiers == [(16, 8192, 3)] * 3


# ---- 005 US1-API-16


def test_讀不到顯示記憶體時沒有自動值():
    # Arrange
    vram = None

    # Act
    tier = tuning.auto_tier(vram)

    # Assert
    assert tier is None
