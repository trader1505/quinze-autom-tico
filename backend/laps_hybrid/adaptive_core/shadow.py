"""Shadow strategy simulation and learning feed."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .models import ConfidenceBreakdown, MarketSnapshot, StrategyEvaluation


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    """A single non-executed strategy observation for AI learning."""

    strategy_name: str
    symbol: str
    signal: str
    price: float
    confidence: float
    timestamp: datetime
    metadata: dict[str, float | str] = field(default_factory=dict)


class ShadowStrategyLab:
    """Collect shadow evaluations without allowing live execution."""

    def __init__(self) -> None:
        self._observations: list[ShadowObservation] = []

    def record(
        self,
        evaluation: StrategyEvaluation,
        confidence: ConfidenceBreakdown,
        snapshot: MarketSnapshot,
    ) -> ShadowObservation:
        """Store a shadow observation for later simulation and model training."""

        observation = ShadowObservation(
            strategy_name=evaluation.strategy_name,
            symbol=snapshot.symbol,
            signal=evaluation.signal.value,
            price=snapshot.price,
            confidence=confidence.final_score,
            timestamp=datetime.now(UTC),
            metadata={
                "raw_confidence": evaluation.raw_confidence,
                "drawdown": evaluation.metrics.drawdown,
                "sharpe_like": evaluation.metrics.sharpe_like,
            },
        )
        self._observations.append(observation)
        return observation

    def observations(self) -> tuple[ShadowObservation, ...]:
        """Return immutable view of recorded shadow observations."""

        return tuple(self._observations)

