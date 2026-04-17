"""Bidirectional recovery helpers."""

from __future__ import annotations

from decimal import Decimal

from ..core.models import Position, Side


class BidirectionalRecovery:
    """Computes opposite-side recovery actions."""

    def recommend(self, side: Side) -> str:
        if side is Side.LONG:
            return "Abrir recuperação vendida para neutralizar exposição comprada."
        return "Abrir recuperação comprada para neutralizar exposição vendida."

    def suggest_quantity(self, position: Position, intensity_pct: Decimal) -> Decimal:
        if intensity_pct <= 0:
            return Decimal("0")
        return position.quantity * (intensity_pct / Decimal("100"))
