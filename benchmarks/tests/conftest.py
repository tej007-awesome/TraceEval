import json
from pathlib import Path

import pytest

from benchmarks.models import Scenario

SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"


def _load(name: str) -> Scenario:
    path = SCENARIOS_DIR / "refunds" / name
    return Scenario.model_validate(json.loads(path.read_text(encoding="utf-8")))


@pytest.fixture
def in_order_scenario() -> Scenario:
    return _load("refund_001_in_order_subset_regex.json")


@pytest.fixture
def any_order_scenario() -> Scenario:
    return _load("refund_002_any_order.json")
