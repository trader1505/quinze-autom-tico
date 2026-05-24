"""Failsafe decisions for execution instability."""

from __future__ import annotations

from .models import (
    ExecutionFailsafeDecision,
    ReconciliationIssue,
    ReconciliationSeverity,
    WebsocketHealthDecision,
)


class ExecutionFailsafeEngine:
    """Map execution anomalies to safe operational responses."""

    def evaluate(
        self,
        *,
        websocket_decisions: tuple[WebsocketHealthDecision, ...] = (),
        reconciliation_issues: tuple[ReconciliationIssue, ...] = (),
        rejected_order_count: int = 0,
        unknown_order_count: int = 0,
        average_slippage_bps: float = 0.0,
    ) -> ExecutionFailsafeDecision:
        critical_reconciliation = any(
            issue.severity == ReconciliationSeverity.CRITICAL
            for issue in reconciliation_issues
        )
        severe_reconciliation = any(
            issue.severity == ReconciliationSeverity.SEVERE
            for issue in reconciliation_issues
        )
        stale_private_stream = any(decision.stale for decision in websocket_decisions)

        if critical_reconciliation or unknown_order_count >= 3:
            return ExecutionFailsafeDecision(
                pause_new_orders=True,
                allow_reduce_only=True,
                require_reconciliation=True,
                cancel_stale_orders=True,
                escalate_safe_mode=True,
                lockdown=True,
                reason="Critical execution uncertainty requires lockdown.",
            )

        if severe_reconciliation or stale_private_stream:
            return ExecutionFailsafeDecision(
                pause_new_orders=True,
                allow_reduce_only=True,
                require_reconciliation=True,
                cancel_stale_orders=True,
                escalate_safe_mode=True,
                lockdown=False,
                reason="Execution state is unsafe until reconciliation completes.",
            )

        if rejected_order_count >= 3 or average_slippage_bps >= 35:
            return ExecutionFailsafeDecision(
                pause_new_orders=True,
                allow_reduce_only=True,
                require_reconciliation=False,
                cancel_stale_orders=False,
                escalate_safe_mode=True,
                lockdown=False,
                reason="Execution quality degraded; throttle new entries.",
            )

        return ExecutionFailsafeDecision(
            pause_new_orders=False,
            allow_reduce_only=False,
            require_reconciliation=False,
            cancel_stale_orders=False,
            escalate_safe_mode=False,
            lockdown=False,
            reason="Execution state is healthy.",
        )

