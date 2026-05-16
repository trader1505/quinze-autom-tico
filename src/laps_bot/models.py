from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Trend(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class PositionState:
    symbol: str
    side: str
    contracts: float
    entry_price: float
    unrealized_pnl: float
    initial_margin: float

    @property
    def roi_pct(self) -> float:
        if self.initial_margin <= 0:
            return 0.0
        return (self.unrealized_pnl / self.initial_margin) * 100
