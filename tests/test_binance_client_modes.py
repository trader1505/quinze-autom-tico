"""Tests for paper/live behavior in Binance client."""

from decimal import Decimal

import pytest

from laps_crypto.app.core.models import OrderRequest, Side
from laps_crypto.app.exchange.binance_client import BinanceApiError, BinanceClient


def test_live_mode_requires_credentials_before_order_submission() -> None:
    client = BinanceClient(
        execution_mode="live",
        use_testnet=True,
        api_key="",
        api_secret="",
    )
    with pytest.raises(BinanceApiError):
        client.submit_order(
            OrderRequest(
                symbol="BTCUSDT",
                side=Side.LONG,
                quantity=Decimal("0.001"),
                reduce_only=False,
            )
        )


def test_paper_mode_updates_position_locally() -> None:
    client = BinanceClient(
        execution_mode="paper",
        prices={"BTCUSDT": Decimal("50000")},
    )
    client.submit_order(
        OrderRequest(
            symbol="BTCUSDT",
            side=Side.LONG,
            quantity=Decimal("0.010"),
            reduce_only=False,
        )
    )
    position = client.get_position("BTCUSDT")
    assert position is not None
    assert position.quantity == Decimal("0.010")

