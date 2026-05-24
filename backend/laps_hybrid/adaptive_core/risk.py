"""Risk gatekeeper for the Adaptive Core Engine."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .models import (
    ExecutionIntent,
    MarketRegime,
    MarketSnapshot,
    PositionSnapshot,
    RiskDecision,
    RiskDecisionType,
    SignalSide,
)


@dataclass(frozen=True, slots=True)
class RiskLimits:
    """Hard portfolio safety constraints.

    These limits should be tightened by investor profile, copy-trading account,
    and exchange health. They should never be loosened by a strategy.
    """

    max_portfolio_exposure: float = 1_000_000.0
    max_symbol_exposure: float = 250_000.0
    max_notional_per_order: float = 100_000.0
    max_leverage: float = 5.0
    max_drawdown: float = 0.12
    max_spread_bps: float = 30.0
    max_data_freshness_ms: int = 2_500
    min_exchange_health: float = 0.75
    min_confidence: float = 0.58
    chaos_max_notional: float = 25_000.0


class RiskEngine:
    """Validate every execution intent before it can reach an exchange."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def evaluate(
        self,
        intent: ExecutionIntent,
        snapshot: MarketSnapshot,
        positions: tuple[PositionSnapshot, ...],
    ) -> RiskDecision:
        """Approve, reduce, deny, or escalate an execution intent."""

        if intent.side == SignalSide.FLAT:
            return RiskDecision(
                decision=RiskDecisionType.DENIED,
                reason="Flat signals do not create execution intents.",
            )

        if snapshot.data_freshness_ms > self.limits.max_data_freshness_ms:
            return RiskDecision(
                decision=RiskDecisionType.SAFE_MODE,
                reason="Market data is stale; engine must enter safe mode.",
            )

        if snapshot.exchange_health < self.limits.min_exchange_health:
            return RiskDecision(
                decision=RiskDecisionType.SAFE_MODE,
                reason="Exchange health below safety threshold.",
            )

        if snapshot.spread_bps > self.limits.max_spread_bps:
            return RiskDecision(
                decision=RiskDecisionType.DENIED,
                reason="Spread is too wide for safe execution.",
            )

        if intent.confidence < self.limits.min_confidence:
            return RiskDecision(
                decision=RiskDecisionType.DENIED,
                reason="Confidence below minimum risk threshold.",
            )

        portfolio_drawdown = max((position.drawdown for position in positions), default=0.0)
        if portfolio_drawdown >= self.limits.max_drawdown:
            return RiskDecision(
                decision=RiskDecisionType.SHUTDOWN,
                reason="Maximum drawdown reached; emergency shutdown required.",
            )

        if intent.leverage > self.limits.max_leverage:
            intent = replace(intent, leverage=self.limits.max_leverage)

        symbol_exposure = sum(
            abs(position.net_notional)
            for position in positions
            if position.symbol == intent.symbol
        )
        portfolio_exposure = sum(abs(position.net_notional) for position in positions)

        remaining_symbol = self.limits.max_symbol_exposure - symbol_exposure
        remaining_portfolio = self.limits.max_portfolio_exposure - portfolio_exposure
        allowed_notional = min(
            self.limits.max_notional_per_order,
            remaining_symbol,
            remaining_portfolio,
        )

        if intent.regime == MarketRegime.CHAOS:
            allowed_notional = min(allowed_notional, self.limits.chaos_max_notional)

        if allowed_notional <= 0:
            return RiskDecision(
                decision=RiskDecisionType.DENIED,
                reason="No remaining risk budget for symbol or portfolio.",
            )

        if intent.notional > allowed_notional:
            reduced_intent = replace(intent, notional=allowed_notional)
            return RiskDecision(
                decision=RiskDecisionType.REDUCED,
                reason="Intent reduced to remaining risk budget.",
                intent=reduced_intent,
                approved_notional=allowed_notional,
                approved_leverage=reduced_intent.leverage,
            )

        return RiskDecision(
            decision=RiskDecisionType.APPROVED,
            reason="Intent satisfies current risk limits.",
            intent=intent,
            approved_notional=intent.notional,
            approved_leverage=intent.leverage,
        )

