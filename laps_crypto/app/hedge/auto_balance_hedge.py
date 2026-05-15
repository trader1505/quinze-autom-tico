"""Auto-balance wrapper for hedge instructions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.models import HedgePlan, Position
from .hedge_engine import HedgeEngine


@dataclass
class AutoBalanceHedge:
    """Builds hedge plan based on current equity context."""

    hedge_engine: HedgeEngine

    def plan_auto_balance(self, position: Position, equity: Decimal) -> HedgePlan:
        if equity <= 0:
            return HedgePlan(
                required=False,
                side=None,
                quantity=Decimal("0"),
                reason_pt_br="Hedge não calculado: patrimônio inválido.",
            )
        exposure_pct = (position.entry_notional / equity) * Decimal("100")
        return self.hedge_engine.build_plan(position=position, exposure_pct=exposure_pct)
