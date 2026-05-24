"""Explainable confidence scoring."""

from __future__ import annotations

from .models import ConfidenceScore, MarketFeatures, StrategyPerformance


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class AIConfidenceEngine:
    """Score strategy confidence using auditable market and performance factors."""

    WEIGHTS = {
        "volatility_quality": 0.14,
        "liquidity_quality": 0.12,
        "spread_quality": 0.10,
        "btc_alignment": 0.10,
        "trend_consistency": 0.13,
        "historical_performance": 0.17,
        "recent_behavior": 0.12,
        "market_structure": 0.07,
        "session_behavior": 0.05,
    }

    def score(
        self,
        features: MarketFeatures,
        performance: StrategyPerformance,
    ) -> ConfidenceScore:
        components = {
            "volatility_quality": _clamp(features.volatility_quality),
            "liquidity_quality": _clamp(features.liquidity_quality),
            "spread_quality": _clamp(features.spread_quality),
            "btc_alignment": _clamp(features.btc_alignment),
            "trend_consistency": _clamp(features.trend_consistency),
            "historical_performance": _clamp(performance.historical_performance),
            "recent_behavior": _clamp(performance.recent_behavior),
            "market_structure": _clamp(features.market_structure),
            "session_behavior": _clamp(performance.session_compatibility),
        }
        final_score = _clamp(
            sum(components[name] * weight for name, weight in self.WEIGHTS.items())
        )
        min_threshold = 0.72 if features.regime == "chaos" else 0.6
        priority_multiplier = _clamp(0.5 + final_score * 0.9, 0.25, 1.35)

        return ConfidenceScore(
            strategy_name=performance.strategy_name,
            final_score=final_score,
            components=components,
            min_confidence_threshold=min_threshold,
            priority_multiplier=priority_multiplier,
            rationale=(
                "Confidence calculated from market quality, BTC alignment, "
                "strategy performance, recent behavior, and session compatibility."
            ),
        )

