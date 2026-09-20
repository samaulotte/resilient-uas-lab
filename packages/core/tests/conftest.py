from __future__ import annotations

from pathlib import Path

import pytest
from core_support import SCENARIOS_DIR


@pytest.fixture
def scenarios_dir() -> Path:
    return SCENARIOS_DIR
