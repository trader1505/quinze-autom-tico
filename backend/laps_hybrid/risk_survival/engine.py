"""Main Risk & Survival Engine."""

from __future__ import annotations

from .circuit_breakers import CircuitBreakerEngine
from .correlation import CorrelationEngine
from .failsafe import FailsafeEngine
from .hedge import BTCDefenseHedgeEngine
from .models import (
    BreakerSeverity,
    CircuitBreakerEvent,
    CorrelationAssessment,
    FailsafeIncident,
    RiskBudget,
    RiskTelemetry,
    SafeMode,
    SurvivalDecision,
)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class RiskSurvivalEngine:
    """Highest-priority defensive organism for LAPS HYBRID."""

    MODE_ORDER = {
        SafeMode.NORMAL: 0,
        SafeMode.CAUTION: 1,
        SafeMode.DEFENSIVE: 2,
        SafeMode.SURVIVAL: 3,
        SafeMode.LOCKDOWN: 4,
    }

    def __init__(
        self,
        *,
        circuit_breakers: CircuitBreakerEngine | None = None,
        correlation_engine: CorrelationEngine | None = None,
        hedge_engine: BTCDefenseHedgeEngine | None = None,
        failsafe_engine: FailsafeEngine | None = None,
    ) -> None:
        self.circuit_breakers = circuit_breakers or CircuitBreakerEngine()
        self.correlation_engine = correlation_engine or CorrelationEngine()
        self.hedge_engine = hedge_engine or BTCDefenseHedgeEngine()
        self.failsafe_engine = failsafe_engine or FailsafeEngine()

    def assess(self, telemetry: RiskTelemetry) -> SurvivalDecision:
        """Assess current risk and return enforceable survival constraints."""

        correlation = self.correlation_engine.assess(
            telemetry.positions,
            telemetry.portfolio.equity,
        )
        breakers = self.circuit_breakers.evaluate(telemetry)
        failsafe_incidents = self.failsafe_engine.evaluate(telemetry.exchange)
        risk_score = self._risk_score(telemetry, correlation, breakers, failsafe_incidents)
        safe_mode = self._safe_mode_from_score(risk_score)

        for breaker in breakers:
            safe_mode = self._max_mode(safe_mode, breaker.target_mode)
        for incident in failsafe_incidents:
            safe_mode = self._max_mode(safe_mode, incident.target_mode)

        budget = self._build_budget(telemetry, correlation, risk_score, safe_mode)
        hedge = self.hedge_engine.recommend(
            correlation=correlation,
            market=telemetry.market,
            safe_mode=safe_mode,
            risk_score=risk_score,
        )

        return SurvivalDecision(
            budget=budget,
            correlation=correlation,
            hedge=hedge,
            breakers=breakers,
            reasons=self._reasons(telemetry, correlation, breakers, failsafe_incidents),
        )

    def _risk_score(
        self,
        telemetry: RiskTelemetry,
        correlation: CorrelationAssessment,
        breakers: tuple[CircuitBreakerEvent, ...],
        failsafe_incidents: tuple[FailsafeIncident, ...],
    ) -> float:
        portfolio = telemetry.portfolio
        market = telemetry.market
        exchange = telemetry.exchange
        system = telemetry.system
        dna = telemetry.investor_dna

        drawdown_pressure = _clamp(portfolio.drawdown / max(dna.drawdown_tolerance, 0.01))
        leverage_pressure = _clamp(portfolio.total_leverage / 8.0)
        exposure_pressure = _clamp(portfolio.total_exposure / max(portfolio.equity * 3.0, 1.0))
        volatility_pressure = _clamp(max(market.volatility / 0.16, market.volatility_shock / 0.1))
        liquidity_pressure = 1.0 - _clamp((market.depth_score + market.liquidity_score) / 2.0)
        exchange_pressure = _clamp(
            exchange.api_error_rate * 2.0
            + exchange.order_rejection_rate
            + exchange.execution_latency_ms / 5_000.0
            + exchange.websocket_staleness_ms / 10_000.0
        )
        strategy_pressure = self._strategy_pressure(telemetry)
        system_pressure = _clamp(
            system.heartbeat_age_ms / 15_000.0
            + system.queue_backlog / 10_000.0
            + (0.5 if not system.redis_available else 0.0)
            + (0.5 if not system.postgres_available else 0.0)
            + system.frozen_processes * 0.3
        )
        breaker_pressure = self._event_pressure(breakers)
        failsafe_pressure = self._incident_pressure(failsafe_incidents)

        return _clamp(
            drawdown_pressure * 0.17
            + leverage_pressure * 0.1
            + exposure_pressure * 0.09
            + volatility_pressure * 0.13
            + liquidity_pressure * 0.1
            + exchange_pressure * 0.1
            + strategy_pressure * 0.08
            + correlation.correlation_risk_score * 0.1
            + system_pressure * 0.06
            + breaker_pressure * 0.04
            + failsafe_pressure * 0.03
        )

    def _strategy_pressure(self, telemetry: RiskTelemetry) -> float:
        if not telemetry.strategies:
            return 0.0
        pressures = []
        for strategy in telemetry.strategies:
            loss_pressure = _clamp(strategy.consecutive_losses / 7.0)
            drawdown_pressure = _clamp(strategy.drawdown / 0.2)
            decay_pressure = _clamp(strategy.confidence_decay)
            slippage_pressure = _clamp(strategy.slippage_bps / 50.0)
            pressures.append(
                loss_pressure * 0.35
                + drawdown_pressure * 0.3
                + decay_pressure * 0.2
                + slippage_pressure * 0.15
            )
        return max(pressures)

    def _event_pressure(self, events: tuple[CircuitBreakerEvent, ...]) -> float:
        severity_pressure = {
            BreakerSeverity.INFO: 0.15,
            BreakerSeverity.WARNING: 0.35,
            BreakerSeverity.SEVERE: 0.75,
            BreakerSeverity.CRITICAL: 1.0,
        }
        return max((severity_pressure[event.severity] for event in events), default=0.0)

    def _incident_pressure(self, incidents: tuple[FailsafeIncident, ...]) -> float:
        severity_pressure = {
            BreakerSeverity.INFO: 0.15,
            BreakerSeverity.WARNING: 0.35,
            BreakerSeverity.SEVERE: 0.75,
            BreakerSeverity.CRITICAL: 1.0,
        }
        return max((severity_pressure[incident.severity] for incident in incidents), default=0.0)

    def _safe_mode_from_score(self, risk_score: float) -> SafeMode:
        if risk_score >= 0.85:
            return SafeMode.LOCKDOWN
        if risk_score >= 0.68:
            return SafeMode.SURVIVAL
        if risk_score >= 0.48:
            return SafeMode.DEFENSIVE
        if risk_score >= 0.28:
            return SafeMode.CAUTION
        return SafeMode.NORMAL

    def _build_budget(
        self,
        telemetry: RiskTelemetry,
        correlation: CorrelationAssessment,
        risk_score: float,
        safe_mode: SafeMode,
    ) -> RiskBudget:
        dna = telemetry.investor_dna
        mode_config = {
            SafeMode.NORMAL: (1.0, 1.0, 1.0, 0.55, {"open", "close", "reduce", "hedge"}),
            SafeMode.CAUTION: (0.7, 0.65, 0.65, 0.62, {"open", "close", "reduce", "hedge"}),
            SafeMode.DEFENSIVE: (0.4, 0.35, 0.35, 0.72, {"open", "close", "reduce", "hedge"}),
            SafeMode.SURVIVAL: (0.15, 0.15, 0.1, 0.82, {"close", "reduce", "hedge"}),
            SafeMode.LOCKDOWN: (0.0, 0.0, 0.0, 1.0, {"close", "reduce", "reconcile"}),
        }[safe_mode]
        leverage_mode, size_mode, frequency_mode, min_confidence, allowed_actions = mode_config

        correlation_multiplier = correlation.recommended_multiplier
        drawdown_multiplier = _clamp(
            1.0
            - telemetry.portfolio.drawdown
            / max(telemetry.investor_dna.drawdown_tolerance, 0.01),
            0.05,
            1.0,
        )
        liquidity_multiplier = _clamp(
            (telemetry.market.depth_score + telemetry.market.liquidity_score) / 2.0,
            0.05,
            1.0,
        )
        exchange_multiplier = _clamp(1.0 - telemetry.exchange.api_error_rate * 1.5, 0.05, 1.0)

        if safe_mode == SafeMode.LOCKDOWN:
            allowed_families: frozenset[str] = frozenset()
        elif safe_mode == SafeMode.SURVIVAL:
            allowed_families = frozenset({"hedge_defense", "risk_reduction"})
        elif safe_mode == SafeMode.DEFENSIVE:
            allowed_families = frozenset(
                {"hedge_defense", "risk_reduction", "funding_capture", "scalping"}
            )
        else:
            allowed_families = frozenset(
                {
                    "trend_following",
                    "momentum",
                    "breakout",
                    "mean_reversion",
                    "scalping",
                    "funding_capture",
                    "arbitrage",
                    "liquidity_sweep",
                    "session_scalping",
                    "volatility_expansion",
                    "hedge_defense",
                }
            )

        max_trades = min(
            dna.max_simultaneous_trades,
            {
                SafeMode.NORMAL: dna.max_simultaneous_trades,
                SafeMode.CAUTION: max(1, dna.max_simultaneous_trades - 1),
                SafeMode.DEFENSIVE: 2,
                SafeMode.SURVIVAL: 1,
                SafeMode.LOCKDOWN: 0,
            }[safe_mode],
        )

        return RiskBudget(
            safe_mode=safe_mode,
            risk_score=risk_score,
            leverage_multiplier=_clamp(
                dna.leverage_multiplier
                * leverage_mode
                * drawdown_multiplier
                * exchange_multiplier,
                0.0,
                1.0,
            ),
            position_size_multiplier=_clamp(
                dna.exposure_multiplier
                * size_mode
                * drawdown_multiplier
                * liquidity_multiplier
                * correlation_multiplier,
                0.0,
                1.0,
            ),
            trade_frequency_multiplier=_clamp(
                dna.trade_frequency_multiplier * frequency_mode * (1.0 - risk_score),
                0.0,
                1.0,
            ),
            max_simultaneous_trades=max_trades,
            min_confidence=min_confidence,
            allowed_actions=frozenset(allowed_actions),
            allowed_strategy_families=allowed_families,
        )

    def _reasons(
        self,
        telemetry: RiskTelemetry,
        correlation: CorrelationAssessment,
        breakers: tuple[CircuitBreakerEvent, ...],
        failsafe_incidents: tuple[FailsafeIncident, ...],
    ) -> tuple[str, ...]:
        reasons = [
            f"portfolio_drawdown={telemetry.portfolio.drawdown:.4f}",
            f"total_leverage={telemetry.portfolio.total_leverage:.4f}",
            f"volatility={telemetry.market.volatility:.4f}",
            f"spread_bps={telemetry.market.spread_bps:.2f}",
            f"correlation_risk={correlation.correlation_risk_score:.4f}",
        ]
        reasons.extend(event.reason for event in breakers)
        reasons.extend(incident.reason for incident in failsafe_incidents)
        return tuple(dict.fromkeys(reasons))

    def _max_mode(self, left: SafeMode, right: SafeMode) -> SafeMode:
        return left if self.MODE_ORDER[left] >= self.MODE_ORDER[right] else right

