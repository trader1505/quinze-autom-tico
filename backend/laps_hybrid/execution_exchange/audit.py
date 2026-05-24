"""Structured execution audit records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from .models import Exchange, OrderStatus


@dataclass(frozen=True, slots=True)
class ExecutionAuditRecord:
    """Immutable audit record for an execution lifecycle transition."""

    exchange: Exchange
    symbol: str
    action: str
    correlation_id: str
    client_order_id: str | None = None
    exchange_order_id: str | None = None
    status: OrderStatus | None = None
    latency_ms: int = 0
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ExecutionAuditSink(Protocol):
    """Persistence boundary for execution audit records."""

    async def write(self, record: ExecutionAuditRecord) -> None:
        """Persist one execution audit record."""


class InMemoryExecutionAuditSink:
    """In-memory audit sink used for tests and early integration."""

    def __init__(self) -> None:
        self.records: list[ExecutionAuditRecord] = []

    async def write(self, record: ExecutionAuditRecord) -> None:
        self.records.append(record)

    def snapshot(self) -> tuple[ExecutionAuditRecord, ...]:
        return tuple(self.records)

