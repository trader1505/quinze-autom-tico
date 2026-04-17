"""Tests for LAPS Crypto close-guard non-negotiable rule."""

from decimal import Decimal

from laps_crypto.app.core.guards import can_close_position
from laps_crypto.app.core.models import Position, PriceEstimate, Side


def test_close_blocked_below_minimum_net_profit() -> None:
    position = Position(
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        mark_price=Decimal("100.12"),
        entry_fee_rate_pct=Decimal("0.04"),
    )
    estimate = PriceEstimate(
        mark_price=Decimal("100.12"),
        exit_fee_rate_pct=Decimal("0.04"),
        slippage_rate_pct=Decimal("0.03"),
    )

    decision = can_close_position(
        position=position,
        estimate=estimate,
        funding_cost=Decimal("0.01"),
        min_net_profit_pct=Decimal("0.1"),
    )

    assert decision.allowed is False
    assert decision.breakdown.net_profit_pct < Decimal("0.1")


def test_close_allowed_above_minimum_net_profit() -> None:
    position = Position(
        symbol="BTCUSDT",
        side=Side.LONG,
        quantity=Decimal("1"),
        entry_price=Decimal("100"),
        mark_price=Decimal("100.35"),
        entry_fee_rate_pct=Decimal("0.04"),
    )
    estimate = PriceEstimate(
        mark_price=Decimal("100.35"),
        exit_fee_rate_pct=Decimal("0.04"),
        slippage_rate_pct=Decimal("0.03"),
    )

    decision = can_close_position(
        position=position,
        estimate=estimate,
        funding_cost=Decimal("0.01"),
        min_net_profit_pct=Decimal("0.1"),
    )

    assert decision.allowed is True
    assert decision.breakdown.net_profit_pct >= Decimal("0.1")
