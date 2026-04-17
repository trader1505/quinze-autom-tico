"""Alpha signal generation logic."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.models import Side, Signal


@dataclass
class SignalEngine:
    """Deterministic momentum bias signal model."""

    min_strength_pct: Decimal = Decimal("0.20")

    def generate_signal(self, symbol: str, current_price: Decimal) -> Signal:
        if current_price <= 0:
            return Signal(
                symbol=symbol,
                side=Side.LONG,
                strength=Decimal("0"),
                reason_en="Invalid price input.",
            )

        # Simple deterministic proxy: classify based on the first decimal digit.
        anchor = (current_price % Decimal("10")) / Decimal("10")
        if anchor >= Decimal("0.5"):
            side = Side.SHORT
            strength = Decimal("0.70")
            reason = "Price is over local anchor; fade move."
        else:
            side = Side.LONG
            strength = Decimal("0.70")
            reason = "Price is below local anchor; mean-revert up."

        if (strength * Decimal("100")) < self.min_strength_pct:
            strength = Decimal("0")

        return Signal(symbol=symbol, side=side, strength=strength, reason_en=reason)
