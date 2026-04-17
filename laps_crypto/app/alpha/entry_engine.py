"""Entry engine coordinating signal and sizing decisions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.models import OrderRequest, OrderResult, Signal
from ..exchange.order_executor import OrderExecutor


@dataclass
class EntryEngine:
    """Executes validated entry opportunities."""

    order_executor: OrderExecutor

    def try_open(
        self,
        *,
        signal: Signal,
        quantity: Decimal,
        mark_price: Decimal,
    ) -> OrderResult:
        if quantity <= 0:
            return OrderResult(
                accepted=False,
                message_pt_br="Abertura ignorada: quantidade inválida.",
            )
        order = OrderRequest(symbol=signal.symbol, side=signal.side, quantity=quantity, reduce_only=False)
        return self.order_executor.execute_open(order)
