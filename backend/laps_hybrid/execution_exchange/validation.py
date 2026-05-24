"""Order lifecycle validation and duplicate fill protection."""

from __future__ import annotations

from .models import ExchangeOrderUpdate, OrderStatus, OrderValidationResult


class ExecutionValidator:
    """Validate exchange responses before they affect local state."""

    TERMINAL_STATUSES = {
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.REJECTED,
        OrderStatus.STALE,
    }

    def __init__(self) -> None:
        self._seen_client_order_ids: set[str] = set()
        self._seen_fill_ids: set[str] = set()

    def validate_order_update(
        self,
        update: ExchangeOrderUpdate,
    ) -> OrderValidationResult:
        """Validate one normalized order update."""

        if update.requested_quantity <= 0:
            return OrderValidationResult(
                valid=False,
                status=OrderStatus.REJECTED,
                reason="Requested quantity must be positive.",
            )

        if update.filled_quantity < 0:
            return OrderValidationResult(
                valid=False,
                status=OrderStatus.REJECTED,
                reason="Filled quantity cannot be negative.",
            )

        if update.filled_quantity > update.requested_quantity:
            return OrderValidationResult(
                valid=False,
                status=OrderStatus.UNKNOWN,
                reason="Filled quantity exceeds requested quantity.",
            )

        duplicate_fills: list[str] = []
        accepted_fills: list[str] = []
        for fill in update.fills:
            if fill.fill_id in self._seen_fill_ids:
                duplicate_fills.append(fill.fill_id)
            else:
                self._seen_fill_ids.add(fill.fill_id)
                accepted_fills.append(fill.fill_id)

        if update.status == OrderStatus.FILLED and update.filled_quantity != update.requested_quantity:
            return OrderValidationResult(
                valid=False,
                status=OrderStatus.UNKNOWN,
                reason="Filled status quantity does not match requested quantity.",
                duplicate_fill_ids=tuple(duplicate_fills),
                accepted_fill_ids=tuple(accepted_fills),
            )

        if update.status == OrderStatus.PARTIALLY_FILLED and update.filled_quantity <= 0:
            return OrderValidationResult(
                valid=False,
                status=OrderStatus.UNKNOWN,
                reason="Partially filled status requires positive filled quantity.",
                duplicate_fill_ids=tuple(duplicate_fills),
                accepted_fill_ids=tuple(accepted_fills),
            )

        self._seen_client_order_ids.add(update.client_order_id)
        return OrderValidationResult(
            valid=True,
            status=update.status,
            reason="Order update validated.",
            duplicate_fill_ids=tuple(duplicate_fills),
            accepted_fill_ids=tuple(accepted_fills),
        )

    def is_duplicate_client_order_id(self, client_order_id: str) -> bool:
        """Return whether the client order ID has already been observed."""

        return client_order_id in self._seen_client_order_ids

