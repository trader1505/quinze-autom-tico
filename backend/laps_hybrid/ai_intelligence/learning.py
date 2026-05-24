"""Performance learning and decision history store boundaries."""

from __future__ import annotations

from .models import LearningDecision, StrategyPerformance


class PerformanceLearningEngine:
    """In-memory learning store for early integration and tests."""

    def __init__(self) -> None:
        self._strategy_metrics: dict[str, list[StrategyPerformance]] = {}
        self._decisions: list[LearningDecision] = []

    def record_strategy_performance(self, performance: StrategyPerformance) -> None:
        self._strategy_metrics.setdefault(performance.strategy_name, []).append(performance)

    def latest_strategy_performance(self, strategy_name: str) -> StrategyPerformance | None:
        history = self._strategy_metrics.get(strategy_name, [])
        if not history:
            return None
        return history[-1]

    def record_decision(self, decision: LearningDecision) -> None:
        self._decisions.append(decision)

    def decisions(self) -> tuple[LearningDecision, ...]:
        return tuple(self._decisions)

