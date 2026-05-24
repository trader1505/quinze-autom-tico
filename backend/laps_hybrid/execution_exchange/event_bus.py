"""Execution event publishing contracts."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import ExecutionEvent


@runtime_checkable
class ExecutionEventPublisher(Protocol):
    """Event publisher interface for Redis, websockets, or tests."""

    async def publish(self, event: ExecutionEvent) -> None:
        """Publish an immutable execution event."""


class InMemoryExecutionEventBus:
    """Simple event sink used for tests and early integration."""

    def __init__(self) -> None:
        self.events: list[ExecutionEvent] = []

    async def publish(self, event: ExecutionEvent) -> None:
        self.events.append(event)

    def snapshot(self) -> tuple[ExecutionEvent, ...]:
        return tuple(self.events)

