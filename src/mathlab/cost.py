from __future__ import annotations


def estimate_model_cost(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """Approximate token spend for a supported configured model.

    This deliberately excludes tool-call fees and any long-context multiplier; the OpenAI dashboard is
    always the billing source of truth.
    """
    prices = {
        "gpt-6-astra": (10, 1, 50),
        "gpt-5.4-mini": (0.75, 0.075, 4.5),
    }
    input_price, cached_price, output_price = prices.get(model, prices["gpt-6-astra"])
    uncached = max(0, input_tokens - cached_tokens)
    return (uncached * input_price + cached_tokens * cached_price + output_tokens * output_price) / 1_000_000


def estimate_astra_cost(input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """Backward-compatible Astra estimate."""
    return estimate_model_cost("gpt-6-astra", input_tokens, cached_tokens, output_tokens)
