"""Correlation and hidden BTC exposure analysis."""

from __future__ import annotations

from collections import defaultdict

from .models import CorrelationAssessment, PositionRisk


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class CorrelationEngine:
    """Estimate hidden BTC dependency and concentration risk."""

    def assess(self, positions: tuple[PositionRisk, ...], equity: float) -> CorrelationAssessment:
        if not positions or equity <= 0:
            return CorrelationAssessment(
                btc_equivalent_exposure=0.0,
                hidden_btc_dependency=0.0,
                sector_concentration=0.0,
                correlation_risk_score=0.0,
                recommended_multiplier=1.0,
            )

        btc_equivalent = sum(
            abs(position.notional) * abs(position.beta_to_btc)
            for position in positions
        )
        total_notional = sum(abs(position.notional) for position in positions)
        sector_exposure: dict[str, float] = defaultdict(float)
        for position in positions:
            sector_exposure[position.sector] += abs(position.notional)

        dominant_sector, dominant_exposure = max(
            sector_exposure.items(),
            key=lambda item: item[1],
        )
        hidden_btc_dependency = _clamp(btc_equivalent / equity)
        sector_concentration = _clamp(dominant_exposure / max(total_notional, 1.0))
        correlation_risk_score = _clamp(
            hidden_btc_dependency * 0.65 + sector_concentration * 0.35
        )
        recommended_multiplier = _clamp(1.0 - correlation_risk_score * 0.7, 0.15, 1.0)

        return CorrelationAssessment(
            btc_equivalent_exposure=btc_equivalent,
            hidden_btc_dependency=hidden_btc_dependency,
            sector_concentration=sector_concentration,
            correlation_risk_score=correlation_risk_score,
            recommended_multiplier=recommended_multiplier,
            dominant_sector=dominant_sector,
        )

