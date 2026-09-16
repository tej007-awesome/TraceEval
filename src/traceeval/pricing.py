import json
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Sequence

from pydantic import BaseModel, Field

from traceeval.core.logger import logger

if TYPE_CHECKING:
    from traceeval.loaders.otel import TokenUsage


class ModelPrice(BaseModel):
    input_per_1m_usd: float = Field(ge=0.0)
    output_per_1m_usd: float = Field(ge=0.0)


# Pricing snapshot as of 2026-09-15, from https://openai.com/api/pricing/
# Prices change over time and vary by provider/tier. Do not treat this as
# authoritative for billing; supply your own pricing file via load_pricing().
DEFAULT_PRICING: Dict[str, ModelPrice] = {
    "gpt-4o-mini": ModelPrice(input_per_1m_usd=0.15, output_per_1m_usd=0.60),
    # Verified current (GA, not deprecated) as of 2026-09-16 via developers.openai.com.
    # OpenAI positions this tier explicitly for "efficient, high-volume workloads" -
    # a good fit for a benchmark firing hundreds of small structured-output judge calls.
    # gpt-4o-mini's sibling (gpt-4o) was already retired from the API in Feb 2026, and the
    # gpt-5-nano dated snapshot is on a retirement path with OpenAI recommending migration
    # to the gpt-5.6 family - gpt-5.6-luna is that family's cheapest tier.
    "gpt-5.6-luna": ModelPrice(input_per_1m_usd=0.20, output_per_1m_usd=1.20),
}


class CostResult(BaseModel):
    total_usd: float
    unknown_models: List[str] = Field(default_factory=list)


def load_pricing(path: Path) -> Dict[str, ModelPrice]:
    """Load a JSON file mapping model name -> {input_per_1m_usd, output_per_1m_usd}.

    Returns DEFAULT_PRICING merged with the overrides in the file (file wins).
    """
    if not path.exists():
        raise FileNotFoundError(f"Pricing file not found: {path}")

    logger.info(f"Loading custom pricing from {path}...")
    raw = json.loads(path.read_text(encoding="utf-8"))

    pricing = dict(DEFAULT_PRICING)
    for model_name, price_dict in raw.items():
        pricing[model_name] = ModelPrice.model_validate(price_dict)
    return pricing


def compute_cost(token_usage: "Sequence[TokenUsage]", pricing: Dict[str, ModelPrice]) -> CostResult:
    """Compute total USD cost from a list of TokenUsage entries against a pricing table."""
    total_usd = 0.0
    unknown_models: List[str] = []

    for usage in token_usage:
        price = pricing.get(usage.model)
        if price is None:
            if usage.model not in unknown_models:
                unknown_models.append(usage.model)
            continue
        total_usd += (usage.input_tokens / 1_000_000) * price.input_per_1m_usd
        total_usd += (usage.output_tokens / 1_000_000) * price.output_per_1m_usd

    return CostResult(total_usd=total_usd, unknown_models=unknown_models)
