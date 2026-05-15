"""Portfolio risk controls for leverage and exposure."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from ..core.config import TradingConfig
from ..core.models import PortfolioSnapshot, Position


@dataclass
class PortfolioRiskEngine:
    """Validates exposure against deterministic portfolio limits."""

    config: TradingConfig

    def current_exposure_pct(self, *, equity: Decimal, positions: Iterable[Position]) -> Decimal:
        """Returns portfolio exposure percentage."""
        if equity <= 0:
            return Decimal("999")
        exposure_notional = sum((p.entry_notional for p in positions), Decimal("0"))
        return (exposure_notional / equity) * Decimal("100")

    def within_limit(self, snapshot: PortfolioSnapshot) -> bool:
        if snapshot.equity <= 0:
            return False
        return (
            (snapshot.total_exposure_notional / snapshot.equity) * Decimal("100")
            <= self.config.max_portfolio_exposure_pct
        )

