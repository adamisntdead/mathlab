from __future__ import annotations


def estimate_astra_cost(input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """Approximate GPT-6 Astra token spend using Oct 2026 list pricing.

    This deliberately excludes tool-call fees and any long-context multiplier; the OpenAI dashboard is
    always the billing source of truth.
    """
    uncached = max(0, input_tokens - cached_tokens)
    return uncached * 10 / 1_000_000 + cached_tokens * 1 / 1_000_000 + output_tokens * 50 / 1_000_000
