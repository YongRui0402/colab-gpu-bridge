"""要使用者本人在場的實跑案例(US1-OA-06、G-01;plan.md Q101、Q108)。

這兩個案例都不開 Colab 執行環境(0 compute units),也不沿用 P9 複製來的授權,
所以覆蓋上層 `tests/realrun/conftest.py` 的 autouse 預算檢查:不建立 `realrun` fixture、不複製 token.json。
仍然只在 `-m realrun` 時執行。
"""

import pytest

from realrun.conftest import realrun_selected


@pytest.fixture(autouse=True)
def _p2_budget_gate(request: pytest.FixtureRequest) -> None:
    if not realrun_selected(request.config):
        pytest.skip("實跑只在 -m realrun 時執行")
