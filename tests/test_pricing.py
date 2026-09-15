import json

import pytest

from traceeval.loaders.otel import TokenUsage
from traceeval.pricing import DEFAULT_PRICING, ModelPrice, compute_cost, load_pricing


def test_compute_cost_known_tokens():
    usage = [
        TokenUsage(model="gpt-4o-mini", input_tokens=150, output_tokens=30),
        TokenUsage(model="gpt-4o-mini", input_tokens=220, output_tokens=35),
    ]
    result = compute_cost(usage, DEFAULT_PRICING)

    expected = (150 / 1_000_000) * 0.15 + (30 / 1_000_000) * 0.60
    expected += (220 / 1_000_000) * 0.15 + (35 / 1_000_000) * 0.60

    assert result.total_usd == expected
    assert result.unknown_models == []


def test_compute_cost_unknown_model():
    usage = [TokenUsage(model="some-mystery-model", input_tokens=100, output_tokens=100)]
    result = compute_cost(usage, DEFAULT_PRICING)

    assert result.total_usd == 0.0
    assert result.unknown_models == ["some-mystery-model"]


def test_load_pricing_overrides_default_and_adds_new_model(tmp_path):
    override_file = tmp_path / "pricing.json"
    override_file.write_text(
        json.dumps(
            {
                "gpt-4o-mini": {"input_per_1m_usd": 1.0, "output_per_1m_usd": 2.0},
                "custom-model": {"input_per_1m_usd": 5.0, "output_per_1m_usd": 10.0},
            }
        )
    )

    pricing = load_pricing(override_file)

    assert pricing["gpt-4o-mini"] == ModelPrice(input_per_1m_usd=1.0, output_per_1m_usd=2.0)
    assert pricing["custom-model"] == ModelPrice(input_per_1m_usd=5.0, output_per_1m_usd=10.0)
    # Defaults not present in the override file are preserved.
    assert set(pricing.keys()) >= set(DEFAULT_PRICING.keys()) | {"custom-model"}


def test_load_pricing_missing_file_raises(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        load_pricing(missing)
