"""Configuration helpers for the LAPS 1505 bot."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv


def _env_float(name: str, default: float) -> float:
    value = getenv(name)
    return float(value) if value is not None else default


def _env_int(name: str, default: int) -> int:
    value = getenv(name)
    return int(value) if value is not None else default


@dataclass(slots=True)
class BotSettings:
    """Runtime settings loaded from env vars."""

    symbol: str = "BTCUSDT"
    interval: str = "15m"
    ema_short_period: int = 12
    ema_long_period: int = 26
    entry_fraction_of_free_futures: float = 0.01
    spot_target_ratio: float = 0.80
    futures_target_ratio: float = 0.20
    tp_roi_target: float = 1.0
    recovery_multiplier: float = 3.0
    order_slices: int = 3
    max_concurrent_operations: int = 30
    margin_stress_threshold: float = 0.60
    margin_recovery_threshold: float = 0.30
    min_notional_usdt: float = 5.0
    poll_seconds: int = 5
    dry_run: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    binance_api_key: str | None = None
    binance_api_secret: str | None = None

    @classmethod
    def from_env(cls) -> "BotSettings":
        return cls(
            symbol=getenv("BOT_SYMBOL", "BTCUSDT"),
            interval=getenv("BOT_INTERVAL", "15m"),
            ema_short_period=_env_int("BOT_EMA_SHORT", 12),
            ema_long_period=_env_int("BOT_EMA_LONG", 26),
            entry_fraction_of_free_futures=_env_float("BOT_ENTRY_FRACTION", 0.01),
            spot_target_ratio=_env_float("BOT_SPOT_TARGET", 0.80),
            futures_target_ratio=_env_float("BOT_FUTURES_TARGET", 0.20),
            tp_roi_target=_env_float("BOT_TP_ROI", 1.0),
            recovery_multiplier=_env_float("BOT_RECOVERY_MULTIPLIER", 3.0),
            order_slices=_env_int("BOT_ORDER_SLICES", 3),
            max_concurrent_operations=_env_int("BOT_MAX_CONCURRENT_OPS", 30),
            margin_stress_threshold=_env_float("BOT_MARGIN_STRESS", 0.60),
            margin_recovery_threshold=_env_float("BOT_MARGIN_RECOVERY", 0.30),
            min_notional_usdt=_env_float("BOT_MIN_NOTIONAL", 5.0),
            poll_seconds=_env_int("BOT_POLL_SECONDS", 5),
            dry_run=getenv("BOT_DRY_RUN", "true").lower() == "true",
            api_host=getenv("BOT_API_HOST", "0.0.0.0"),
            api_port=_env_int("BOT_API_PORT", 8080),
            binance_api_key=getenv("BINANCE_API_KEY"),
            binance_api_secret=getenv("BINANCE_API_SECRET"),
        )
