"""Defense actions for stressed scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DefenseDecision:
    """Decision output for defensive controls."""

    block_new_entries: bool
    raise_hedge: bool
    reason_pt_br: str


class DefenseEngine:
    """Simple deterministic defense policy."""

    def can_open_new_position(self, *, exposure_pct: Decimal, max_exposure_pct: Decimal) -> bool:
        """Hard gate for new entries based on exposure limits."""
        return exposure_pct <= max_exposure_pct

    def evaluate(self, drawdown_pct: Decimal) -> DefenseDecision:
        if drawdown_pct >= Decimal("25"):
            return DefenseDecision(
                block_new_entries=True,
                raise_hedge=True,
                reason_pt_br="Modo defesa máxima ativado por drawdown elevado.",
            )
        if drawdown_pct >= Decimal("15"):
            return DefenseDecision(
                block_new_entries=False,
                raise_hedge=True,
                reason_pt_br="Aumentar hedge por drawdown moderado.",
            )
        return DefenseDecision(
            block_new_entries=False,
            raise_hedge=False,
            reason_pt_br="Condições de risco sob controle.",
        )
