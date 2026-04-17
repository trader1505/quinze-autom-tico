"""Dynamic recovery sizing rules."""

from __future__ import annotations

from decimal import Decimal


class DynamicRecovery:
    """Scales recovery effort based on retry attempt."""

    def multiplier_for_attempt(self, attempt: int) -> Decimal:
        if attempt <= 1:
            return Decimal("1")
        if attempt == 2:
            return Decimal("1.5")
        return Decimal("2")
