"""Position sizing engine with deterministic Decimal math."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from ..core.config import TradingConfig


@dataclass
class SizingEngine:
    """Computes safe order size based on account risk budget."""

    config: TradingConfig

    def compute_position_size(
        self,
        *,
        equity: Decimal,
        mark_price: Decimal,
        signal_strength: Decimal,
    ) -> Decimal:
        if equity <= 0 or mark_price <= 0 or signal_strength <= 0:
            return Decimal("0")

        risk_budget = equity * (self.config.per_trade_risk_pct / Decimal("100"))
        conviction_boost = min(signal_strength, Decimal("1.0"))
        notional = risk_budget * (Decimal("0.5") + conviction_boost)
        quantity = notional / mark_price
        return quantity.quantize(self.config.quantity_precision, rounding=ROUND_DOWN)
