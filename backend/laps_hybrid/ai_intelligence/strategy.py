"""Strategy evaluation and degradation detection."""

from __future__ import annotations

from .models import (
    DegradationSeverity,
    StrategyEvaluation,
    StrategyPerformance,
    StrategyRecommendation,
)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class StrategyEvaluationEngine:
    """Evaluate strategy quality and recommend participation state."""

    def evaluate(self, performance: StrategyPerformance) -> StrategyEvaluation:
        degradation = self.degradation_severity(performance)
        quality = _clamp(
            performance.win_rate * 0.18
            + (1.0 - _clamp(performance.drawdown / 0.2)) * 0.18
            + _clamp((performance.sharpe_like + 1.0) / 3.0) * 0.18
            + _clamp(performance.profit_factor / 2.0) * 0.12
            + performance.regime_compatibility * 0.12
            + performance.volatility_compatibility * 0.1
            + performance.session_compatibility * 0.07
            + performance.recent_behavior * 0.05
        )
        recommendation = self._recommendation(quality, degradation, performance.sample_size)
        return StrategyEvaluation(
            strategy_name=performance.strategy_name,
            quality_score=quality,
            recommendation=recommendation,
            degradation_severity=degradation,
            reason=self._reason(quality, degradation, recommendation),
        )

    def degradation_severity(self, performance: StrategyPerformance) -> DegradationSeverity:
        if (
            performance.drawdown >= 0.16
            or performance.consecutive_losses >= 7
            or performance.slippage_bps >= 50
            or performance.recent_behavior <= 0.2
        ):
            return DegradationSeverity.SEVERE
        if (
            performance.drawdown >= 0.1
            or performance.consecutive_losses >= 5
            or performance.slippage_bps >= 35
            or performance.recent_behavior <= 0.35
        ):
            return DegradationSeverity.WARNING
        if (
            performance.drawdown >= 0.06
            or performance.consecutive_losses >= 3
            or performance.recent_behavior <= 0.5
        ):
            return DegradationSeverity.WATCH
        return DegradationSeverity.NONE

    def _recommendation(
        self,
        quality: float,
        degradation: DegradationSeverity,
        sample_size: int,
    ) -> StrategyRecommendation:
        if degradation == DegradationSeverity.SEVERE:
            return StrategyRecommendation.DISABLE_TEMPORARILY
        if degradation == DegradationSeverity.WARNING:
            return StrategyRecommendation.SHADOW_MODE
        if quality >= 0.72 and sample_size >= 30:
            return StrategyRecommendation.INCREASE_PRIORITY
        if quality < 0.48:
            return StrategyRecommendation.REDUCE_PRIORITY
        return StrategyRecommendation.MAINTAIN_PRIORITY

    def _reason(
        self,
        quality: float,
        degradation: DegradationSeverity,
        recommendation: StrategyRecommendation,
    ) -> str:
        return (
            f"Strategy quality={quality:.3f}, degradation={degradation.value}, "
            f"recommendation={recommendation.value}."
        )

