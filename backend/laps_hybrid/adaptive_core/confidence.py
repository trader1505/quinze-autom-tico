"""Dynamic confidence scoring for strategy competition."""

from __future__ import annotations

from .models import ConfidenceBreakdown, MarketSnapshot, RegimeAssessment, StrategyEvaluation


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class ConfidenceEngine:
    """Score strategy evaluations using auditable components.

    The scoring model is intentionally transparent for early production. The
    same component contract can be backed by Bayesian or ML models later.
    """

    def score(
        self,
        evaluation: StrategyEvaluation,
        snapshot: MarketSnapshot,
        regime: RegimeAssessment,
    ) -> ConfidenceBreakdown:
        """Return a normalized final confidence score and component details."""

        market_alignment = self._market_alignment(evaluation, regime)
        volatility_quality = self._volatility_quality(snapshot)
        liquidity_quality = self._liquidity_quality(snapshot)
        btc_correlation_quality = self._btc_correlation_quality(snapshot)
        spread_quality = self._spread_quality(snapshot)
        strategy_performance = self._strategy_performance(evaluation)
        recent_behavior = self._recent_behavior(evaluation)

        final_score = _clamp(
            market_alignment * 0.25
            + volatility_quality * 0.15
            + liquidity_quality * 0.15
            + btc_correlation_quality * 0.10
            + spread_quality * 0.10
            + strategy_performance * 0.15
            + recent_behavior * 0.10
        )

        return ConfidenceBreakdown(
            market_alignment=market_alignment,
            volatility_quality=volatility_quality,
            liquidity_quality=liquidity_quality,
            btc_correlation_quality=btc_correlation_quality,
            spread_quality=spread_quality,
            strategy_performance=strategy_performance,
            recent_behavior=recent_behavior,
            final_score=final_score,
        )

    def _market_alignment(
        self,
        evaluation: StrategyEvaluation,
        regime: RegimeAssessment,
    ) -> float:
        family_allowed = evaluation.strategy_family in regime.allowed_strategy_families
        family_score = 1.0 if family_allowed else 0.25
        return _clamp(
            evaluation.regime_alignment * 0.65
            + regime.confidence * 0.2
            + family_score * 0.15
        )

    def _volatility_quality(self, snapshot: MarketSnapshot) -> float:
        if snapshot.volatility <= 0:
            return 0.0
        target_midpoint = 0.045
        tolerance = 0.075
        distance = abs(snapshot.volatility - target_midpoint)
        return _clamp(1.0 - distance / tolerance)

    def _liquidity_quality(self, snapshot: MarketSnapshot) -> float:
        return _clamp(snapshot.volume / 5_000_000.0)

    def _btc_correlation_quality(self, snapshot: MarketSnapshot) -> float:
        dominance_stress = abs(snapshot.btc_dominance - 0.52)
        return _clamp(1.0 - dominance_stress / 0.25)

    def _spread_quality(self, snapshot: MarketSnapshot) -> float:
        return _clamp(1.0 - snapshot.spread_bps / 25.0)

    def _strategy_performance(self, evaluation: StrategyEvaluation) -> float:
        metrics = evaluation.metrics
        drawdown_quality = 1.0 - _clamp(metrics.drawdown / 0.2)
        efficiency = _clamp((metrics.sharpe_like + 1.0) / 3.0)
        profit_factor = _clamp(metrics.profit_factor / 2.0)
        return _clamp(drawdown_quality * 0.35 + efficiency * 0.4 + profit_factor * 0.25)

    def _recent_behavior(self, evaluation: StrategyEvaluation) -> float:
        metrics = evaluation.metrics
        sample_confidence = _clamp(metrics.sample_size / 50.0)
        win_rate_quality = _clamp(metrics.recent_win_rate)
        return _clamp(win_rate_quality * 0.75 + sample_confidence * 0.25)

