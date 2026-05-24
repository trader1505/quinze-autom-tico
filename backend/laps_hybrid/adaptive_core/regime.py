"""Market regime detection for the Adaptive Core Engine."""

from __future__ import annotations

from .models import MarketRegime, MarketSnapshot, OperationalMode, RegimeAssessment


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class MarketRegimeEngine:
    """Classify market state into an operational personality.

    The initial implementation is deterministic and auditable. It is designed
    so ML classifiers can later replace or augment the scoring functions while
    preserving the same public contract.
    """

    TREND_FAMILIES = frozenset(
        {"trend_following", "momentum", "breakout", "volatility_expansion"}
    )
    RANGE_FAMILIES = frozenset({"mean_reversion", "scalping", "session_scalping"})
    CHAOS_FAMILIES = frozenset({"hedge_defense", "volatility_expansion"})
    DEAD_FAMILIES = frozenset({"funding_capture", "selective_scalping"})

    def assess(self, snapshot: MarketSnapshot) -> RegimeAssessment:
        """Return the current market regime and operating modifiers."""

        chaos_score = self._chaos_score(snapshot)
        dead_score = self._dead_score(snapshot)
        trend_score = self._trend_score(snapshot)
        range_score = self._range_score(snapshot)

        scores = {
            MarketRegime.CHAOS: chaos_score,
            MarketRegime.DEAD: dead_score,
            MarketRegime.TREND: trend_score,
            MarketRegime.RANGE: range_score,
        }
        regime = max(scores, key=scores.get)
        confidence = scores[regime]

        if regime == MarketRegime.CHAOS:
            return RegimeAssessment(
                regime=regime,
                confidence=confidence,
                operational_mode=OperationalMode.DEFENSIVE,
                leverage_multiplier=0.25,
                aggressiveness_multiplier=0.2,
                trade_frequency_multiplier=0.35,
                position_size_multiplier=0.3,
                allowed_strategy_families=self.CHAOS_FAMILIES,
                explanation="Elevated volatility, liquidation, spread, or exchange stress.",
            )

        if regime == MarketRegime.DEAD:
            return RegimeAssessment(
                regime=regime,
                confidence=confidence,
                operational_mode=OperationalMode.SAFE,
                leverage_multiplier=0.15,
                aggressiveness_multiplier=0.1,
                trade_frequency_multiplier=0.15,
                position_size_multiplier=0.2,
                allowed_strategy_families=self.DEAD_FAMILIES,
                explanation="Low activity conditions with insufficient opportunity quality.",
            )

        if regime == MarketRegime.TREND:
            return RegimeAssessment(
                regime=regime,
                confidence=confidence,
                operational_mode=OperationalMode.AGGRESSIVE,
                leverage_multiplier=0.85,
                aggressiveness_multiplier=0.8,
                trade_frequency_multiplier=0.7,
                position_size_multiplier=0.75,
                allowed_strategy_families=self.TREND_FAMILIES,
                explanation="Momentum and participation support directional continuation.",
            )

        return RegimeAssessment(
            regime=MarketRegime.RANGE,
            confidence=confidence,
            operational_mode=OperationalMode.NORMAL,
            leverage_multiplier=0.45,
            aggressiveness_multiplier=0.4,
            trade_frequency_multiplier=0.55,
            position_size_multiplier=0.45,
            allowed_strategy_families=self.RANGE_FAMILIES,
            explanation="Contained volatility with weak directional momentum.",
        )

    def _chaos_score(self, snapshot: MarketSnapshot) -> float:
        volatility = _clamp(snapshot.volatility / 0.12)
        spread = _clamp(snapshot.spread_bps / 40.0)
        liquidations = _clamp(snapshot.liquidation_intensity / 1.0)
        exchange_stress = 1.0 - _clamp(snapshot.exchange_health)
        return _clamp(
            volatility * 0.35
            + spread * 0.2
            + liquidations * 0.3
            + exchange_stress * 0.15
        )

    def _dead_score(self, snapshot: MarketSnapshot) -> float:
        low_volume = 1.0 - _clamp(snapshot.volume / 1_000_000.0)
        low_volatility = 1.0 - _clamp(snapshot.volatility / 0.025)
        weak_momentum = 1.0 - _clamp(abs(snapshot.momentum) / 0.01)
        wide_spread_penalty = _clamp(snapshot.spread_bps / 25.0) * 0.2
        return _clamp(
            low_volume * 0.35
            + low_volatility * 0.3
            + weak_momentum * 0.25
            + wide_spread_penalty
        )

    def _trend_score(self, snapshot: MarketSnapshot) -> float:
        momentum = _clamp(abs(snapshot.momentum) / 0.035)
        volume = _clamp(snapshot.volume / 5_000_000.0)
        spread_quality = 1.0 - _clamp(snapshot.spread_bps / 20.0)
        liquidation_penalty = 1.0 - _clamp(snapshot.liquidation_intensity / 0.8)
        return _clamp(
            momentum * 0.4
            + volume * 0.25
            + spread_quality * 0.2
            + liquidation_penalty * 0.15
        )

    def _range_score(self, snapshot: MarketSnapshot) -> float:
        moderate_volatility = 1.0 - abs(_clamp(snapshot.volatility / 0.06) - 0.5)
        weak_momentum = 1.0 - _clamp(abs(snapshot.momentum) / 0.025)
        liquidity = _clamp(snapshot.volume / 3_000_000.0)
        spread_quality = 1.0 - _clamp(snapshot.spread_bps / 18.0)
        return _clamp(
            moderate_volatility * 0.25
            + weak_momentum * 0.3
            + liquidity * 0.25
            + spread_quality * 0.2
        )

