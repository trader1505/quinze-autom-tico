"""Failsafe incident classification and action mapping."""

from __future__ import annotations

from .models import (
    BreakerSeverity,
    ExchangeRisk,
    FailsafeIncident,
    FailsafeIncidentType,
    SafeMode,
)


class FailsafeEngine:
    """Convert operational failures into concrete survival actions."""

    def evaluate(self, exchange: ExchangeRisk) -> tuple[FailsafeIncident, ...]:
        incidents: list[FailsafeIncident] = []

        if exchange.api_error_rate >= 0.25:
            incidents.append(
                FailsafeIncident(
                    incident_type=FailsafeIncidentType.API_FAILURE,
                    severity=BreakerSeverity.SEVERE,
                    target_mode=SafeMode.SURVIVAL,
                    affected_service="exchange_api",
                    action="Throttle requests, block new entries, and retry health probes.",
                    reason="Exchange API error rate exceeds safe threshold.",
                )
            )

        if exchange.websocket_staleness_ms >= 5_000 or exchange.websocket_disconnects >= 3:
            incidents.append(
                FailsafeIncident(
                    incident_type=FailsafeIncidentType.WEBSOCKET_DISCONNECT,
                    severity=BreakerSeverity.SEVERE,
                    target_mode=SafeMode.SURVIVAL,
                    affected_service="exchange_websocket",
                    action="Resubscribe feeds and reject stale market-data signals.",
                    reason="Exchange websocket feed is stale or repeatedly disconnected.",
                )
            )

        if exchange.execution_mismatch:
            incidents.append(
                FailsafeIncident(
                    incident_type=FailsafeIncidentType.EXECUTION_MISMATCH,
                    severity=BreakerSeverity.CRITICAL,
                    target_mode=SafeMode.LOCKDOWN,
                    affected_service="execution_worker",
                    action="Stop new orders, fetch exchange state, and reconcile positions.",
                    reason="Internal execution state does not match exchange state.",
                )
            )

        if exchange.exchange_desync:
            incidents.append(
                FailsafeIncident(
                    incident_type=FailsafeIncidentType.EXCHANGE_DESYNC,
                    severity=BreakerSeverity.CRITICAL,
                    target_mode=SafeMode.LOCKDOWN,
                    affected_service="exchange_account",
                    action="Cancel unknown orders and keep lockdown until resolved.",
                    reason="Exchange account desync detected.",
                )
            )

        if exchange.order_rejection_rate >= 0.2:
            incidents.append(
                FailsafeIncident(
                    incident_type=FailsafeIncidentType.ORDER_REJECTION,
                    severity=BreakerSeverity.WARNING,
                    target_mode=SafeMode.DEFENSIVE,
                    affected_service="order_router",
                    action="Reduce execution frequency and inspect rejection causes.",
                    reason="Order rejection rate is elevated.",
                )
            )

        if exchange.execution_latency_ms >= 2_500:
            incidents.append(
                FailsafeIncident(
                    incident_type=FailsafeIncidentType.DELAYED_EXECUTION,
                    severity=BreakerSeverity.WARNING,
                    target_mode=SafeMode.DEFENSIVE,
                    affected_service="execution_gateway",
                    action="Disable latency-sensitive strategies.",
                    reason="Execution latency exceeds safe routing limits.",
                )
            )

        return tuple(incidents)

