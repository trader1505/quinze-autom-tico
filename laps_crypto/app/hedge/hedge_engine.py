"""Hedge decision engine for exposure control."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.config import TradingConfig
from ..core.models import HedgePlan, Position


@dataclass
class HedgeEngine:
    """Determines when a protective hedge is needed."""

    config: TradingConfig

    def build_plan(self, *, position: Position, exposure_pct: Decimal) -> HedgePlan:
        if exposure_pct < self.config.hedge_trigger_pct:
            return HedgePlan(
                required=False,
                side=None,
                quantity=Decimal("0"),
                reason_pt_br="Hedge não necessário: exposição abaixo do gatilho.",
            )

        hedge_qty = position.quantity / Decimal("2")
        return HedgePlan(
            required=True,
            side=position.side.opposite,
            quantity=hedge_qty,
            reason_pt_br="Hedge parcial recomendado para reduzir exposição.",
        )
