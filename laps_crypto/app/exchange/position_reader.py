"""Position reader abstraction."""

from __future__ import annotations

from typing import List

from ..core.models import Position
from .binance_client import BinanceClient


class PositionReader:
    """Reads normalized open positions from exchange adapter."""

    def __init__(self, client: BinanceClient) -> None:
        self._client = client

    def get_open_position(self, symbol: str) -> Position | None:
        return self._client.get_position(symbol)

    def list_open_positions(self) -> List[Position]:
        return self._client.list_positions()

    def total_exposure_notional(self) -> float:
        total = 0.0
        for position in self._client.list_positions():
            total += float(position.entry_notional)
        return total
