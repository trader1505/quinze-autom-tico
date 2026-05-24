"""Circuit breakers for immediate survival escalation."""

from __future__ import annotations

from .models import (
    BreakerSeverity,
    CircuitBreakerEvent,
    RiskLayer,
    RiskTelemetry,
    SafeMode,
)


class CircuitBreakerEngine:
    """Evaluate deterministic emergency shutdown and safe-mode rules."""

    def evaluate(self, telemetry: RiskTelemetry) -> tuple[CircuitBreakerEvent, ...]:
        events: list[CircuitBreakerEvent] = []
        events.extend(self._volatility_breakers(telemetry))
        events.extend(self._exchange_breakers(telemetry))
        events.extend(self._drawdown_breakers(telemetry))
        events.extend(self._liquidity_breakers(telemetry))
        events.extend(self._strategy_breakers(telemetry))
        events.extend(self._system_breakers(telemetry))
        return tuple(events)

    def _volatility_breakers(
        self,
        telemetry: RiskTelemetry,
    ) -> list[CircuitBreakerEvent]:
        market = telemetry.market
        events: list[CircuitBreakerEvent] = []
        if market.volatility >= 0.16 or market.volatility_shock >= 0.1:
            events.append(
                CircuitBreakerEvent(
                    name="abnormal_volatility",
                    severity=BreakerSeverity.SEVERE,
                    target_mode=SafeMode.SURVIVAL,
                    layer=RiskLayer.VOLATILITY,
                    reason="Volatility shock exceeds survival threshold.",
                    action="Block speculative entries and allow hedge/reduce actions.",
                    trigger_value=max(market.volatility, market.volatility_shock),
                    threshold=0.16,
                )
            )
        elif market.volatility >= 0.1 or market.volatility_shock >= 0.06:
            events.append(
                CircuitBreakerEvent(
                    name="volatility_expansion",
                    severity=BreakerSeverity.WARNING,
                    target_mode=SafeMode.DEFENSIVE,
                    layer=RiskLayer.VOLATILITY,
                    reason="Volatility expansion requires defensive sizing.",
                    action="Reduce leverage and require higher confidence.",
                    trigger_value=max(market.volatility, market.volatility_shock),
                    threshold=0.1,
                )
            )
        return events

    def _exchange_breakers(
        self,
        telemetry: RiskTelemetry,
    ) -> list[CircuitBreakerEvent]:
        exchange = telemetry.exchange
        events: list[CircuitBreakerEvent] = []
        if exchange.execution_mismatch or exchange.exchange_desync:
            events.append(
                CircuitBreakerEvent(
                    name="execution_desync",
                    severity=BreakerSeverity.CRITICAL,
                    target_mode=SafeMode.LOCKDOWN,
                    layer=RiskLayer.SYSTEMIC_FAILURE,
                    reason="Execution state mismatch or exchange desync detected.",
                    action="Stop new orders and reconcile exchange state.",
                    trigger_value=True,
                    threshold=True,
                )
            )
        if exchange.api_error_rate >= 0.25:
            events.append(
                CircuitBreakerEvent(
                    name="exchange_api_instability",
                    severity=BreakerSeverity.SEVERE,
                    target_mode=SafeMode.SURVIVAL,
                    layer=RiskLayer.EXCHANGE,
                    reason="Exchange API error rate is unsafe.",
                    action="Throttle execution and prefer reduce-only operations.",
                    trigger_value=exchange.api_error_rate,
                    threshold=0.25,
                )
            )
        if exchange.websocket_staleness_ms >= 5_000 or exchange.websocket_disconnects >= 3:
            events.append(
                CircuitBreakerEvent(
                    name="websocket_failure",
                    severity=BreakerSeverity.SEVERE,
                    target_mode=SafeMode.SURVIVAL,
                    layer=RiskLayer.EXCHANGE,
                    reason="Websocket feed is stale or unstable.",
                    action="Block new entries until market data recovers.",
                    trigger_value=max(
                        exchange.websocket_staleness_ms,
                        exchange.websocket_disconnects,
                    ),
                    threshold=5_000,
                )
            )
        return events

    def _drawdown_breakers(
        self,
        telemetry: RiskTelemetry,
    ) -> list[CircuitBreakerEvent]:
        portfolio = telemetry.portfolio
        tolerance = telemetry.investor_dna.drawdown_tolerance
        events: list[CircuitBreakerEvent] = []
        if portfolio.drawdown >= tolerance:
            events.append(
                CircuitBreakerEvent(
                    name="max_drawdown",
                    severity=BreakerSeverity.CRITICAL,
                    target_mode=SafeMode.LOCKDOWN,
                    layer=RiskLayer.PORTFOLIO,
                    reason="Investor drawdown tolerance breached.",
                    action="Stop new trades and protect remaining capital.",
                    trigger_value=portfolio.drawdown,
                    threshold=tolerance,
                )
            )
        elif portfolio.drawdown_velocity >= 0.035:
            events.append(
                CircuitBreakerEvent(
                    name="rapid_drawdown",
                    severity=BreakerSeverity.SEVERE,
                    target_mode=SafeMode.SURVIVAL,
                    layer=RiskLayer.PORTFOLIO,
                    reason="Drawdown velocity is accelerating.",
                    action="Cut risk budget and evaluate hedge defense.",
                    trigger_value=portfolio.drawdown_velocity,
                    threshold=0.035,
                )
            )
        return events

    def _liquidity_breakers(
        self,
        telemetry: RiskTelemetry,
    ) -> list[CircuitBreakerEvent]:
        market = telemetry.market
        events: list[CircuitBreakerEvent] = []
        if market.depth_score <= 0.2 or market.liquidity_score <= 0.2:
            events.append(
                CircuitBreakerEvent(
                    name="liquidity_collapse",
                    severity=BreakerSeverity.SEVERE,
                    target_mode=SafeMode.SURVIVAL,
                    layer=RiskLayer.LIQUIDITY,
                    reason="Order-book depth or liquidity quality collapsed.",
                    action="Disable new entries and reduce slippage-sensitive exposure.",
                    trigger_value=min(market.depth_score, market.liquidity_score),
                    threshold=0.2,
                )
            )
        if market.spread_bps >= 45:
            events.append(
                CircuitBreakerEvent(
                    name="abnormal_spread_expansion",
                    severity=BreakerSeverity.SEVERE,
                    target_mode=SafeMode.SURVIVAL,
                    layer=RiskLayer.LIQUIDITY,
                    reason="Spread expansion is unsafe for execution.",
                    action="Block marketable orders except emergency reduction.",
                    trigger_value=market.spread_bps,
                    threshold=45,
                )
            )
        elif market.spread_bps >= 25:
            events.append(
                CircuitBreakerEvent(
                    name="spread_expansion",
                    severity=BreakerSeverity.WARNING,
                    target_mode=SafeMode.DEFENSIVE,
                    layer=RiskLayer.LIQUIDITY,
                    reason="Spread deterioration requires defensive execution.",
                    action="Reduce frequency and require better liquidity.",
                    trigger_value=market.spread_bps,
                    threshold=25,
                )
            )
        return events

    def _strategy_breakers(
        self,
        telemetry: RiskTelemetry,
    ) -> list[CircuitBreakerEvent]:
        events: list[CircuitBreakerEvent] = []
        for strategy in telemetry.strategies:
            if strategy.consecutive_losses >= 5:
                events.append(
                    CircuitBreakerEvent(
                        name="consecutive_strategy_losses",
                        severity=BreakerSeverity.WARNING,
                        target_mode=SafeMode.DEFENSIVE,
                        layer=RiskLayer.STRATEGY,
                        reason=f"{strategy.strategy_name} has degraded loss behavior.",
                        action="Throttle or disable degraded strategy.",
                        trigger_value=strategy.consecutive_losses,
                        threshold=5,
                    )
                )
            if strategy.slippage_bps >= 35:
                events.append(
                    CircuitBreakerEvent(
                        name="excessive_slippage",
                        severity=BreakerSeverity.WARNING,
                        target_mode=SafeMode.DEFENSIVE,
                        layer=RiskLayer.STRATEGY,
                        reason=f"{strategy.strategy_name} slippage exceeds model tolerance.",
                        action="Reduce or pause slippage-sensitive strategy.",
                        trigger_value=strategy.slippage_bps,
                        threshold=35,
                    )
                )
        return events

    def _system_breakers(
        self,
        telemetry: RiskTelemetry,
    ) -> list[CircuitBreakerEvent]:
        system = telemetry.system
        events: list[CircuitBreakerEvent] = []
        if not system.redis_available or not system.postgres_available:
            events.append(
                CircuitBreakerEvent(
                    name="critical_dependency_unavailable",
                    severity=BreakerSeverity.CRITICAL,
                    target_mode=SafeMode.LOCKDOWN,
                    layer=RiskLayer.SYSTEMIC_FAILURE,
                    reason="Redis or PostgreSQL dependency is unavailable.",
                    action="Stop new trading until persistence and state buses recover.",
                    trigger_value=False,
                    threshold=True,
                )
            )
        if system.heartbeat_age_ms >= 10_000 or system.frozen_processes > 0:
            events.append(
                CircuitBreakerEvent(
                    name="frozen_process_detected",
                    severity=BreakerSeverity.SEVERE,
                    target_mode=SafeMode.SURVIVAL,
                    layer=RiskLayer.SYSTEMIC_FAILURE,
                    reason="Critical process heartbeat is stale or frozen.",
                    action="Trigger watchdog restart and safe mode.",
                    trigger_value=max(system.heartbeat_age_ms, system.frozen_processes),
                    threshold=10_000,
                )
            )
        return events

