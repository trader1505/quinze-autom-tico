"""Execution gateway contracts for exchange adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from .models import ExecutionIntent


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """Exchange execution result for an approved intent."""

    idempotency_key: str
    accepted: bool
    status: str
    exchange_order_id: str | None = None
    reason: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ExecutionGateway(Protocol):
    """Protocol implemented by CCXT or native exchange execution adapters."""

    async def execute(self, intent: ExecutionIntent) -> ExecutionReport:
        """Submit an already risk-approved execution intent."""


class NoopExecutionGateway:
    """Safe execution gateway used for tests, dry-runs, and early integration."""

    async def execute(self, intent: ExecutionIntent) -> ExecutionReport:
        """Pretend to accept an order without touching an exchange."""

        return ExecutionReport(
            idempotency_key=intent.idempotency_key,
            accepted=True,
            status="noop_accepted",
            exchange_order_id=None,
            metadata={"strategy_name": intent.strategy_name, "symbol": intent.symbol},
        )

