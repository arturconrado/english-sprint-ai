import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = ROOT / "config" / "model-pricing.json"


def estimate_text_cost(
    model: str,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
) -> Decimal:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    rates = catalog["models"].get(model)
    if rates is None:
        raise ValueError(f"No operational price exists for model {model}.")
    cached = min(max(cached_tokens, 0), max(input_tokens, 0))
    uncached = max(input_tokens - cached, 0)
    million = Decimal(1_000_000)
    return (
        Decimal(uncached) * Decimal(rates["input_per_million"])
        + Decimal(cached) * Decimal(rates["cached_input_per_million"])
        + Decimal(max(output_tokens, 0)) * Decimal(rates["output_per_million"])
    ) / million
