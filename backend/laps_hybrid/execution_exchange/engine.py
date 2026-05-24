"""Execution orchestration service."""

from __future__ import annotations

from uuid import uuid4

from .audit import ExecutionAuditRecord, ExecutionAuditSink, InMemoryExecutionAuditSink
from .connectors import ExchangeConnector
from .event_bus import ExecutionEventPublisher, InMemoryExecutionEventBus
from .models import (
    Exchange,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionPlan,
    ExchangeOrderUpdate,
    MarketDepth,
    OrderRequest,
    ReconciliationSeverity,
)
from .smart_execution import SmartExecutionPlanner
from .validation import ExecutionValidator


class ExecutionExchangeEngine:
    """Coordinate safe order planning, connector routing, validation, and audit."""

    def __init__(
        self,
        connectors: dict[Exchange, ExchangeConnector],
        *,
        planner: SmartExecutionPlanner | None = None,
        validator: ExecutionValidator | None = None,
        event_publisher: ExecutionEventPublisher | None = None,
        audit_sink: ExecutionAuditSink | None = None,
    ) -> None:
        self.connectors = connectors
        self.planner = planner or SmartExecutionPlanner()
        self.validator = validator or ExecutionValidator()
        self.event_publisher = event_publisher or InMemoryExecutionEventBus()
        self.audit_sink = audit_sink or InMemoryExecutionAuditSink()

    async def execute(self, request: OrderRequest, depth: MarketDepth) -> tuple[ExchangeOrderUpdate, ...]:
        """Plan, submit, validate, publish, and audit a normalized order request."""

        if request.exchange not in self.connectors:
            raise KeyError(f"No connector configured for {request.exchange}")

        correlation_id = uuid4().hex
        plan = self.planner.plan(request, depth)
        await self._publish_plan_created(request, plan, correlation_id)

        updates: list[ExchangeOrderUpdate] = []
        for child in plan.child_orders:
            connector = self.connectors[child.exchange]
            await self._audit(
                request=child,
                action="submit_order",
                correlation_id=correlation_id,
                reason=plan.rationale,
            )
            update = await connector.place_order(child)
            validation = self.validator.validate_order_update(update)
            updates.append(update)

            event_type = (
                ExecutionEventType.ORDER_ACCEPTED
                if validation.valid
                else ExecutionEventType.ORDER_REJECTED
            )
            await self.event_publisher.publish(
                ExecutionEvent(
                    event_type=event_type,
                    exchange=update.exchange,
                    symbol=update.symbol,
                    correlation_id=correlation_id,
                    client_order_id=update.client_order_id,
                    exchange_order_id=update.exchange_order_id,
                    severity=(
                        ReconciliationSeverity.INFO
                        if validation.valid
                        else ReconciliationSeverity.SEVERE
                    ),
                    latency_ms=update.latency_ms,
                    payload={
                        "status": update.status.value,
                        "validation_reason": validation.reason,
                        "duplicate_fill_ids": validation.duplicate_fill_ids,
                    },
                )
            )
            await self.audit_sink.write(
                ExecutionAuditRecord(
                    exchange=update.exchange,
                    symbol=update.symbol,
                    action="validate_order_update",
                    correlation_id=correlation_id,
                    client_order_id=update.client_order_id,
                    exchange_order_id=update.exchange_order_id,
                    status=update.status,
                    latency_ms=update.latency_ms,
                    reason=validation.reason,
                    metadata={"valid": validation.valid},
                )
            )

        return tuple(updates)

    async def _publish_plan_created(
        self,
        request: OrderRequest,
        plan: ExecutionPlan,
        correlation_id: str,
    ) -> None:
        await self.event_publisher.publish(
            ExecutionEvent(
                event_type=ExecutionEventType.ORDER_CREATED,
                exchange=request.exchange,
                symbol=request.symbol,
                correlation_id=correlation_id,
                client_order_id=plan.parent_client_order_id,
                payload={
                    "child_order_count": len(plan.child_orders),
                    "expected_slippage_bps": plan.expected_slippage_bps,
                    "fallback_action": plan.fallback_action,
                    "rationale": plan.rationale,
                },
            )
        )

    async def _audit(
        self,
        request: OrderRequest,
        action: str,
        correlation_id: str,
        reason: str,
    ) -> None:
        await self.audit_sink.write(
            ExecutionAuditRecord(
                exchange=request.exchange,
                symbol=request.symbol,
                action=action,
                correlation_id=correlation_id,
                client_order_id=request.client_order_id,
                reason=reason,
                metadata={
                    "order_type": request.order_type.value,
                    "quantity": request.quantity,
                    "priority": request.priority.value,
                    "reduce_only": request.reduce_only,
                    "post_only": request.post_only,
                },
            )
        )

