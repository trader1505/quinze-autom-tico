"""Investor audit event sink."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import InvestorAuditEvent


@runtime_checkable
class InvestorAuditSink(Protocol):
    """Persistence boundary for investor audit events."""

    async def write(self, event: InvestorAuditEvent) -> None:
        """Persist one immutable investor audit event."""


class InMemoryInvestorAuditSink:
    """In-memory audit sink for tests and early integration."""

    def __init__(self) -> None:
        self.events: list[InvestorAuditEvent] = []

    async def write(self, event: InvestorAuditEvent) -> None:
        self.events.append(event)

    def snapshot(self) -> tuple[InvestorAuditEvent, ...]:
        return tuple(self.events)

