"""Profit segregation engine for resilient capital management."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class PigBankEngine:
    """Stores a protected reserve funded by realized profits."""

    current_balance: Decimal = Decimal("0")

    def deposit(self, amount: Decimal) -> Decimal:
        if amount <= 0:
            return Decimal("0")
        self.current_balance += amount
        return amount
