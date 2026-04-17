"""Profit allocation policies for institutional capital governance."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.config import TradingConfig


@dataclass
class ProfitAllocator:
    """Computes reserve amount for each realized positive profit."""

    config: TradingConfig

    def allocate_to_reserve(self, realized_profit: Decimal) -> Decimal:
        if realized_profit <= 0:
            return Decimal("0")
        return realized_profit * self.config.reserve_profit_pct / Decimal("100")

    def allocate(self, realized_profit: Decimal) -> tuple[Decimal, Decimal]:
        reserve = self.allocate_to_reserve(realized_profit)
        return reserve, realized_profit - reserve
