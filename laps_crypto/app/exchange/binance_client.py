"""Deterministic Binance-like client abstraction used by LAPS Crypto."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List

from ..core.models import AccountSnapshot, OrderRequest, Position, Side


@dataclass
class BinanceClient:
    """In-memory exchange client with deterministic behavior."""

    balances: Dict[str, Decimal] = field(default_factory=dict)
    prices: Dict[str, Decimal] = field(default_factory=dict)
    _positions: Dict[str, Position] = field(default_factory=dict)
    _orders: List[OrderRequest] = field(default_factory=list)

    def get_balance(self, asset: str) -> Decimal:
        return self.balances.get(asset, Decimal("0"))

    def set_balance(self, asset: str, value: Decimal) -> None:
        self.balances[asset] = Decimal(value)

    def get_mark_price(self, symbol: str) -> Decimal:
        return Decimal(self.prices[symbol])

    def set_mark_price(self, symbol: str, value: Decimal) -> None:
        mark = Decimal(value)
        self.prices[symbol] = mark
        if symbol in self._positions:
            self._positions[symbol].mark_price = mark

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def list_positions(self) -> List[Position]:
        return [self._positions[symbol] for symbol in sorted(self._positions.keys())]

    def get_account_snapshot(self, base_asset: str = "USDT") -> AccountSnapshot:
        equity = self.get_balance(base_asset)
        used_collateral = Decimal("0")
        for position in self._positions.values():
            used_collateral += position.entry_notional
            equity += position.gross_pnl
        return AccountSnapshot(
            equity=equity,
            free_collateral=equity - used_collateral,
            used_collateral=used_collateral,
        )

    def submit_order(self, order: OrderRequest, entry_fee_rate_pct: Decimal = Decimal("0.04")) -> None:
        self._orders.append(order)
        price = self.get_mark_price(order.symbol)
        existing = self._positions.get(order.symbol)

        if order.reduce_only:
            if existing is None:
                raise ValueError("Reduce-only rejeitado: não existe posição aberta.")
            if order.side != existing.side.opposite:
                raise ValueError("Reduce-only rejeitado: lado inválido para fechamento.")
            if order.quantity >= existing.quantity:
                self._positions.pop(order.symbol, None)
            else:
                existing.quantity -= order.quantity
                existing.mark_price = price
            return

        if existing is None:
            self._positions[order.symbol] = Position(
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                entry_price=price,
                mark_price=price,
                entry_fee_rate_pct=entry_fee_rate_pct,
            )
            return

        if existing.side == order.side:
            total_qty = existing.quantity + order.quantity
            weighted_entry = (
                (existing.entry_price * existing.quantity) + (price * order.quantity)
            ) / total_qty
            existing.quantity = total_qty
            existing.entry_price = weighted_entry
            existing.mark_price = price
            return

        if order.quantity < existing.quantity:
            existing.quantity -= order.quantity
            existing.mark_price = price
            return

        if order.quantity == existing.quantity:
            self._positions.pop(order.symbol, None)
            return

        flipped_qty = order.quantity - existing.quantity
        self._positions[order.symbol] = Position(
            symbol=order.symbol,
            side=order.side,
            quantity=flipped_qty,
            entry_price=price,
            mark_price=price,
            entry_fee_rate_pct=entry_fee_rate_pct,
        )

    def order_history(self) -> List[OrderRequest]:
        """Returns immutable-like view of submitted orders."""
        return list(self._orders)
