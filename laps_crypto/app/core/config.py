"""Runtime configuration for LAPS Crypto."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import os


def _decimal_from_env(name: str, default: str) -> Decimal:
    return Decimal(os.getenv(name, default).strip())


@dataclass(frozen=True)
class TradingConfig:
    """Immutable runtime configuration."""

    base_asset: str
    quantity_precision: Decimal
    min_close_profit_pct: Decimal
    taker_fee_pct: Decimal
    maker_fee_pct: Decimal
    default_funding_pct: Decimal
    default_slippage_pct: Decimal
    max_portfolio_exposure_pct: Decimal
    per_trade_risk_pct: Decimal
    dust_notional_threshold: Decimal
    hedge_trigger_pct: Decimal
    reserve_profit_pct: Decimal
    signal_min_strength_pct: Decimal
    simulated_fair_price: Decimal


def load_config() -> TradingConfig:
    """Create config from environment values."""
    return TradingConfig(
        base_asset=os.getenv("LAPS_BASE_ASSET", "USDT"),
        quantity_precision=Decimal("0.001"),
        min_close_profit_pct=_decimal_from_env("LAPS_MIN_CLOSE_PROFIT_PCT", "0.1"),
        taker_fee_pct=_decimal_from_env("LAPS_TAKER_FEE_PCT", "0.04"),
        maker_fee_pct=_decimal_from_env("LAPS_MAKER_FEE_PCT", "0.02"),
        default_funding_pct=_decimal_from_env("LAPS_DEFAULT_FUNDING_PCT", "0.01"),
        default_slippage_pct=_decimal_from_env("LAPS_DEFAULT_SLIPPAGE_PCT", "0.03"),
        max_portfolio_exposure_pct=_decimal_from_env("LAPS_MAX_EXPOSURE_PCT", "35"),
        per_trade_risk_pct=_decimal_from_env("LAPS_PER_TRADE_RISK_PCT", "1.2"),
        dust_notional_threshold=_decimal_from_env("LAPS_DUST_THRESHOLD", "10"),
        hedge_trigger_pct=_decimal_from_env("LAPS_HEDGE_TRIGGER_PCT", "20"),
        reserve_profit_pct=_decimal_from_env("LAPS_RESERVE_PROFIT_PCT", "15"),
        signal_min_strength_pct=_decimal_from_env("LAPS_SIGNAL_MIN_STRENGTH_PCT", "0.55"),
        simulated_fair_price=_decimal_from_env("LAPS_FAIR_PRICE", "65150"),
    )
