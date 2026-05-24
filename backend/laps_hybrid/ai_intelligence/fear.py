"""Internal market fear and stress index."""

from __future__ import annotations

from .models import FearIndex, FearState, MarketFeatures


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class MarketFearIndexEngine:
    """Estimate systemic danger rather than price direction."""

    WEIGHTS = {
        "liquidations": 0.24,
        "spread_expansion": 0.16,
        "abnormal_volatility": 0.20,
        "orderflow_aggression": 0.12,
        "funding_instability": 0.13,
        "btc_dominance_shock": 0.15,
    }

    def calculate(self, features: MarketFeatures) -> FearIndex:
        components = {
            "liquidations": _clamp(features.liquidation_intensity),
            "spread_expansion": 1.0 - _clamp(features.spread_quality),
            "abnormal_volatility": 1.0 - _clamp(features.volatility_quality),
            "orderflow_aggression": _clamp(features.orderflow_aggression),
            "funding_instability": _clamp(features.funding_instability),
            "btc_dominance_shock": _clamp(features.btc_dominance_shock),
        }
        score = _clamp(
            sum(components[name] * weight for name, weight in self.WEIGHTS.items())
        )
        state = self._state(score)
        return FearIndex(
            symbol=features.symbol,
            score=score,
            state=state,
            components=components,
            exposure_multiplier=_clamp(1.0 - score * 0.8, 0.1, 1.0),
            leverage_multiplier=_clamp(1.0 - score * 0.9, 0.05, 1.0),
            safe_mode_signal=state in {FearState.STRESSED, FearState.PANIC},
            reason=f"Market fear state is {state.value} at score {score:.3f}.",
        )

    def _state(self, score: float) -> FearState:
        if score >= 0.75:
            return FearState.PANIC
        if score >= 0.55:
            return FearState.STRESSED
        if score >= 0.32:
            return FearState.ELEVATED
        return FearState.CALM

