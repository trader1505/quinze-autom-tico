"""Shadow AI lab metrics and promotion readiness."""

from __future__ import annotations

from collections import defaultdict

from .models import ShadowObservation


class ShadowAILab:
    """Collect shadow observations and evaluate promotion readiness."""

    def __init__(self) -> None:
        self._observations: list[ShadowObservation] = []

    def record(self, observation: ShadowObservation) -> None:
        self._observations.append(observation)

    def observations(self) -> tuple[ShadowObservation, ...]:
        return tuple(self._observations)

    def promotion_candidates(
        self,
        *,
        min_samples: int = 30,
        min_average_pnl: float = 0.0,
        max_drawdown: float = 0.08,
    ) -> tuple[str, ...]:
        grouped: dict[str, list[ShadowObservation]] = defaultdict(list)
        for observation in self._observations:
            grouped[observation.strategy_name].append(observation)

        candidates: list[str] = []
        for strategy_name, observations in grouped.items():
            if len(observations) < min_samples:
                continue
            average_pnl = sum(item.simulated_pnl for item in observations) / len(observations)
            worst_drawdown = max(item.simulated_drawdown for item in observations)
            average_confidence = sum(item.confidence for item in observations) / len(observations)
            if (
                average_pnl > min_average_pnl
                and worst_drawdown <= max_drawdown
                and average_confidence >= 0.62
            ):
                candidates.append(strategy_name)
        return tuple(candidates)

