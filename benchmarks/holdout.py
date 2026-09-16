"""Deterministic holdout scenario selection: one scenario per domain, chosen by a fixed
seeded RNG, recorded once in the committed benchmarks/holdout.json. Excluded from runs by
default (see run.py's --include-holdout flag), so there's always a fixed set of scenarios
that were never used to tune operators, scenario content, or judge config during
development - a basic defense against overfitting the benchmark to itself.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from benchmarks.models import Scenario

# Fixed and arbitrary (the date this split was created), NOT the --seed CLI flag used for
# operator mutation randomness - those are different concerns. Regenerating the split
# (python -m benchmarks.holdout) with this same constant always reproduces the same file.
HOLDOUT_SEED = 20260916
HOLDOUT_FILE = Path("benchmarks/holdout.json")


def select_holdout(scenarios: List[Scenario], seed: int = HOLDOUT_SEED) -> List[str]:
    """One scenario id per domain, chosen deterministically."""
    by_domain: Dict[str, List[str]] = defaultdict(list)
    for s in scenarios:
        by_domain[s.domain].append(s.id)
    rng = random.Random(seed)
    selected = [rng.choice(sorted(by_domain[domain])) for domain in sorted(by_domain)]
    return sorted(selected)


def load_holdout(path: Path = HOLDOUT_FILE) -> List[str]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("scenario_ids", [])


def write_holdout(scenario_ids: List[str], seed: int = HOLDOUT_SEED, path: Path = HOLDOUT_FILE) -> None:
    payload = {"seed": seed, "scenario_ids": scenario_ids}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main():
    from benchmarks.run import load_scenarios

    scenarios = load_scenarios(Path("benchmarks/scenarios"))
    selected = select_holdout(scenarios)
    write_holdout(selected)
    print(f"Wrote {len(selected)} holdout scenario id(s) to {HOLDOUT_FILE}:")
    for sid in selected:
        print(f"  {sid}")


if __name__ == "__main__":
    main()
