"""Strategy contracts for live and shadow competition."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from .models import (
    MarketRegime,
    MarketSnapshot,
    RegimeAssessment,
    StrategyEvaluation,
    StrategyMode,
)


@runtime_checkable
class Strategy(Protocol):
    """Protocol every live or shadow strategy must implement."""

    name: str
    family: str
    mode: StrategyMode
    allowed_regimes: frozenset[MarketRegime]

    async def evaluate(
        self,
        snapshot: MarketSnapshot,
        regime: RegimeAssessment,
    ) -> StrategyEvaluation:
        """Evaluate current market state and return a strategy signal."""


class BaseStrategy(ABC):
    """Base class for production strategies.

    Strategies should contain signal logic only. Execution, copy trading,
    risk approval, and persistence belong outside the strategy boundary.
    """

    name: str
    family: str
    mode: StrategyMode
    allowed_regimes: frozenset[MarketRegime]

    def __init__(
        self,
        name: str,
        family: str,
        mode: StrategyMode,
        allowed_regimes: frozenset[MarketRegime],
    ) -> None:
        self.name = name
        self.family = family
        self.mode = mode
        self.allowed_regimes = allowed_regimes

    def is_allowed(self, regime: MarketRegime) -> bool:
        """Return whether the strategy is compatible with the regime."""

        return self.mode != StrategyMode.DISABLED and regime in self.allowed_regimes

    @abstractmethod
    async def evaluate(
        self,
        snapshot: MarketSnapshot,
        regime: RegimeAssessment,
    ) -> StrategyEvaluation:
        """Evaluate the strategy against the latest market state."""

