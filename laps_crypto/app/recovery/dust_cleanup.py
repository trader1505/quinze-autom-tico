"""Utility for cleaning negligible balances (dust)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.config import TradingConfig
from ..exchange.binance_client import BinanceClient


@dataclass
class DustCleanup:
    """Consolidates balances below configured threshold."""

    config: TradingConfig

    def cleanup(self, client: BinanceClient) -> Decimal:
        total_cleaned = Decimal("0")
        for asset, balance in list(client.balances.items()):
            if asset == self.config.base_asset:
                continue
            if balance <= 0:
                continue
            if balance < self.config.dust_notional_threshold:
                total_cleaned += balance
                client.balances[asset] = Decimal("0")
                client.balances[self.config.base_asset] = (
                    client.balances.get(self.config.base_asset, Decimal("0")) + balance
                )
        return total_cleaned
