from pathlib import Path

from benchmarks.holdout import HOLDOUT_SEED, load_holdout, select_holdout, write_holdout
from benchmarks.run import load_scenarios

SCENARIOS = load_scenarios(Path("benchmarks/scenarios"))


def test_select_holdout_picks_exactly_one_per_domain():
    selected = select_holdout(SCENARIOS)
    domains = {s.id: s.domain for s in SCENARIOS}
    selected_domains = [domains[sid] for sid in selected]
    assert sorted(selected_domains) == sorted(set(domains.values()))
    assert len(selected) == len(set(domains.values()))


def test_select_holdout_deterministic_for_same_seed():
    a = select_holdout(SCENARIOS, seed=HOLDOUT_SEED)
    b = select_holdout(SCENARIOS, seed=HOLDOUT_SEED)
    assert a == b


def test_select_holdout_differs_for_different_seed():
    a = select_holdout(SCENARIOS, seed=1)
    b = select_holdout(SCENARIOS, seed=2)
    assert a != b


def test_holdout_json_matches_select_holdout_with_committed_seed():
    # The committed benchmarks/holdout.json must actually be the output of
    # select_holdout(..., HOLDOUT_SEED) over the current scenario set - not hand-edited or
    # stale relative to the scenario corpus.
    committed = load_holdout()
    recomputed = select_holdout(SCENARIOS, seed=HOLDOUT_SEED)
    assert committed == recomputed


def test_write_and_load_holdout_roundtrip(tmp_path):
    path = tmp_path / "holdout.json"
    write_holdout(["a", "b"], seed=1, path=path)
    assert load_holdout(path) == ["a", "b"]


def test_load_holdout_missing_file_returns_empty(tmp_path):
    assert load_holdout(tmp_path / "does_not_exist.json") == []
