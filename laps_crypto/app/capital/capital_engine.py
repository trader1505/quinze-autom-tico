"""Capital overview engine."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..core.models import AccountSnapshot
from ..exchange.binance_client import BinanceClient


@dataclass
class CapitalEngine:
    """Builds account-level capital snapshots."""

    realized_pnl: Decimal = Decimal("0")

    def register_realized_pnl(self, amount: Decimal) -> None:
        self.realized_pnl += amount

    def build_snapshot(self, client: BinanceClient, base_asset: str) -> AccountSnapshot:
        return client.get_account_snapshot(base_asset=base_asset)
