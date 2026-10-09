"""Estimate EDU credits from measured Codex usage; never infer an account balance."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any


RATE_CARD = json.loads(Path(__file__).with_name("credit_rates.json").read_text(encoding="utf-8"))
SPEED_MULTIPLIERS = {"standard": 1, "fast": 2, "ultrafast": 6}


class CreditLedger:
    """Accumulate costs per model/speed without rounding individual responses."""

    def __init__(self, fallback_speed: str = "standard") -> None:
        """Start an empty ledger with an explicit speed assumption."""
        self.fallback_speed = fallback_speed
        self.cost = Decimal(0)
        self.priced_tokens = 0
        self.unpriced_tokens = 0
        self.free_tokens = 0
        self.assumed_speed_tokens = 0
        self.models: dict[str, Decimal] = {}

    def add(self, counts: dict[str, int], context: dict[str, Any], *, free: bool = False) -> None:
        """Price one response, excluding free safety checks and cache writes."""
        tokens = counts["input_tokens"] + counts["output_tokens"]
        if free:
            self.free_tokens += tokens
            return
        model = context.get("model")
        speed = context.get("speed") or context.get("service_tier")
        assumed = speed is None
        speed = self.fallback_speed if assumed else speed
        speed = "standard" if speed in ("default", "auto") else speed
        rates = RATE_CARD["rates"].get(model)
        supported_speed = (
            speed == "standard"
            or (speed == "fast" and model in {"gpt-6.1-sol", "gpt-6-astra", "gpt-6-sol", "gpt-6-luna"})
            or (speed == "ultrafast" and model in {"gpt-6.1-sol", "gpt-6-astra"})
        )
        if rates is None or not supported_speed:
            self.unpriced_tokens += tokens
            return
        if assumed:
            self.assumed_speed_tokens += tokens
        uncached = counts["input_tokens"] - counts["cached_input_tokens"] - counts["cache_write_input_tokens"]
        cost = (
            sum(
                Decimal(count) * Decimal(str(rate))
                for count, rate in zip(
                    (uncached, counts["cached_input_tokens"], counts["output_tokens"]), rates, strict=True
                )
            )
            * SPEED_MULTIPLIERS[speed]
            / 1_000_000
        )
        self.cost += cost
        self.priced_tokens += tokens
        key = f"{model} ({speed})"
        self.models[key] = self.models.get(key, Decimal(0)) + cost

    def report(self, *, available: bool, missing: int) -> dict[str, Any]:
        """Return numerical coverage and a versioned rate-card reference."""
        known = available and (self.priced_tokens > 0 or self.free_tokens > 0 or self.unpriced_tokens == 0)
        return {
            "estimatedCredits": float(round(self.cost, 8)) if known else None,
            "creditStatus": ("partial" if missing or self.unpriced_tokens else "available")
            if known
            else "unavailable",
            "pricedTokens": self.priced_tokens,
            "unpricedTokens": self.unpriced_tokens,
            "freeSafetyTokens": self.free_tokens,
            "assumedSpeedTokens": self.assumed_speed_tokens,
            "fallbackSpeed": self.fallback_speed,
            "modelCredits": [
                {"model": model, "credits": float(round(cost, 8))} for model, cost in sorted(self.models.items())
            ],
            "rateCardDate": RATE_CARD["checked_at"],
            "rateCardUrl": RATE_CARD["source"],
        }
