"""Core recovery orchestration for underwater positions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.config import TradingConfig
from ..core.models import Position


@dataclass
class RecoveryEngine:
    """Provides deterministic recovery metrics and sizing."""

    config: TradingConfig

    def estimate_funding_cost(self, position: Position) -> Decimal:
        return position.entry_notional * self.config.default_funding_pct / Decimal("100")

    def build_recovery_quantity(self, base_qty: Decimal, multiplier: Decimal) -> Decimal:
        if base_qty <= 0 or multiplier <= 0:
            return Decimal("0")
        return (base_qty * multiplier).quantize(self.config.quantity_precision)
