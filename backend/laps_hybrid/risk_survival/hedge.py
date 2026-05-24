"""BTC defense hedge recommendations."""

from __future__ import annotations

from .models import CorrelationAssessment, HedgeRecommendation, MarketRisk, SafeMode


class BTCDefenseHedgeEngine:
    """Create partial BTC hedge recommendations during systemic stress."""

    def recommend(
        self,
        correlation: CorrelationAssessment,
        market: MarketRisk,
        safe_mode: SafeMode,
        risk_score: float,
    ) -> HedgeRecommendation:
        systemic_stress = (
            safe_mode in {SafeMode.SURVIVAL, SafeMode.LOCKDOWN}
            or market.regime == "chaos"
            or market.liquidation_intensity >= 0.65
            or abs(market.btc_dominance_change) >= 0.04
        )
        if not systemic_stress or correlation.btc_equivalent_exposure <= 0:
            return HedgeRecommendation(
                required=False,
                symbol="BTC/USDT",
                side="short",
                notional=0.0,
                intensity=0.0,
                reason="BTC hedge not required under current systemic conditions.",
            )

        mode_multiplier = {
            SafeMode.NORMAL: 0.0,
            SafeMode.CAUTION: 0.15,
            SafeMode.DEFENSIVE: 0.3,
            SafeMode.SURVIVAL: 0.55,
            SafeMode.LOCKDOWN: 0.8,
        }[safe_mode]
        intensity = min(
            0.85,
            max(
                mode_multiplier,
                correlation.correlation_risk_score * 0.65 + risk_score * 0.35,
            ),
        )
        notional = correlation.btc_equivalent_exposure * intensity

        return HedgeRecommendation(
            required=notional > 0,
            symbol="BTC/USDT",
            side="short",
            notional=notional,
            intensity=intensity,
            reason=(
                "Systemic BTC-linked risk requires partial hedge protection "
                f"at {intensity:.2f} intensity."
            ),
        )

