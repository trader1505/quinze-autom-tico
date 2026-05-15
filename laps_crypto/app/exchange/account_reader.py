"""Account snapshot reader."""

from __future__ import annotations

from ..core.models import AccountSnapshot
from .binance_client import BinanceClient


class AccountReader:
    """Reads normalized account snapshots from exchange adapter."""

    def __init__(self, client: BinanceClient, base_asset: str) -> None:
        self._client = client
        self._base_asset = base_asset

    def read(self) -> AccountSnapshot:
        return self._client.get_account_snapshot(base_asset=self._base_asset)
