"""Exchange connector contracts and safe placeholder adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    Exchange,
    ExchangeOrderUpdate,
    ExchangePosition,
    OrderRequest,
    OrderStatus,
)


@runtime_checkable
class ExchangeConnector(Protocol):
    """Protocol every futures exchange connector must implement."""

    exchange: Exchange

    async def place_order(self, request: OrderRequest) -> ExchangeOrderUpdate:
        """Place an order and return a normalized exchange update."""

    async def cancel_order(
        self,
        exchange_order_id: str,
        symbol: str,
    ) -> ExchangeOrderUpdate:
        """Cancel an order and return the normalized final state."""

    async def fetch_order(
        self,
        exchange_order_id: str,
        symbol: str,
    ) -> ExchangeOrderUpdate:
        """Fetch one order from the exchange."""

    async def fetch_positions(self) -> tuple[ExchangePosition, ...]:
        """Fetch current futures positions."""

    async def fetch_balances(self) -> dict[str, float]:
        """Fetch normalized account balances."""


class UnsupportedExchangeOperation(RuntimeError):
    """Raised by placeholder adapters until real REST clients are wired."""


class BaseFuturesConnector:
    """Base class for futures connectors.

    Concrete implementations should wrap native REST/websocket clients and
    normalize all responses into execution_exchange models.
    """

    exchange: Exchange

    def __init__(self, exchange: Exchange) -> None:
        self.exchange = exchange

    async def place_order(self, request: OrderRequest) -> ExchangeOrderUpdate:
        raise UnsupportedExchangeOperation(f"{self.exchange} place_order not configured")

    async def cancel_order(
        self,
        exchange_order_id: str,
        symbol: str,
    ) -> ExchangeOrderUpdate:
        raise UnsupportedExchangeOperation(f"{self.exchange} cancel_order not configured")

    async def fetch_order(
        self,
        exchange_order_id: str,
        symbol: str,
    ) -> ExchangeOrderUpdate:
        raise UnsupportedExchangeOperation(f"{self.exchange} fetch_order not configured")

    async def fetch_positions(self) -> tuple[ExchangePosition, ...]:
        raise UnsupportedExchangeOperation(f"{self.exchange} fetch_positions not configured")

    async def fetch_balances(self) -> dict[str, float]:
        raise UnsupportedExchangeOperation(f"{self.exchange} fetch_balances not configured")


class BinanceFuturesConnector(BaseFuturesConnector):
    """Binance Futures connector boundary."""

    def __init__(self) -> None:
        super().__init__(Exchange.BINANCE_FUTURES)


class BitgetFuturesConnector(BaseFuturesConnector):
    """Bitget Futures connector boundary."""

    def __init__(self) -> None:
        super().__init__(Exchange.BITGET_FUTURES)


class PaperExchangeConnector:
    """Deterministic connector for tests and paper execution."""

    def __init__(self, exchange: Exchange = Exchange.BINANCE_FUTURES) -> None:
        self.exchange = exchange
        self.orders: dict[str, ExchangeOrderUpdate] = {}
        self.positions: tuple[ExchangePosition, ...] = ()

    async def place_order(self, request: OrderRequest) -> ExchangeOrderUpdate:
        update = ExchangeOrderUpdate(
            exchange=self.exchange,
            symbol=request.symbol,
            client_order_id=request.client_order_id,
            exchange_order_id=f"paper-{request.client_order_id}",
            status=OrderStatus.ACCEPTED,
            requested_quantity=request.quantity,
            filled_quantity=0.0,
            latency_ms=1,
            raw={"paper": True},
        )
        self.orders[request.client_order_id] = update
        return update

    async def cancel_order(
        self,
        exchange_order_id: str,
        symbol: str,
    ) -> ExchangeOrderUpdate:
        for update in self.orders.values():
            if update.exchange_order_id == exchange_order_id and update.symbol == symbol:
                canceled = ExchangeOrderUpdate(
                    exchange=update.exchange,
                    symbol=update.symbol,
                    client_order_id=update.client_order_id,
                    exchange_order_id=update.exchange_order_id,
                    status=OrderStatus.CANCELED,
                    requested_quantity=update.requested_quantity,
                    filled_quantity=update.filled_quantity,
                    latency_ms=1,
                    raw={"paper": True},
                )
                self.orders[update.client_order_id] = canceled
                return canceled
        raise KeyError(f"Unknown paper order {exchange_order_id}")

    async def fetch_order(
        self,
        exchange_order_id: str,
        symbol: str,
    ) -> ExchangeOrderUpdate:
        for update in self.orders.values():
            if update.exchange_order_id == exchange_order_id and update.symbol == symbol:
                return update
        raise KeyError(f"Unknown paper order {exchange_order_id}")

    async def fetch_positions(self) -> tuple[ExchangePosition, ...]:
        return self.positions

    async def fetch_balances(self) -> dict[str, float]:
        return {"USDT": 100_000.0}

