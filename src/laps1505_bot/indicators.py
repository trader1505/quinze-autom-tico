"""Indicator and trend detection logic."""

from __future__ import annotations

from .models import Side, TrendSignal


def ema(values: list[float], period: int) -> float:
    if period <= 0:
        raise ValueError("EMA period must be positive")
    if len(values) < period:
        raise ValueError("Not enough values to compute EMA")

    multiplier = 2 / (period + 1)
    seed = sum(values[:period]) / period
    current = seed
    for price in values[period:]:
        current = (price - current) * multiplier + current
    return current


def detect_trend(close_prices: list[float], short_period: int, long_period: int) -> TrendSignal:
    if short_period >= long_period:
        raise ValueError("Short period must be smaller than long period")
    if len(close_prices) < long_period + 1:
        raise ValueError("Not enough candles to detect trend")

    ema_short_now = ema(close_prices, short_period)
    ema_long_now = ema(close_prices, long_period)
    ema_short_prev = ema(close_prices[:-1], short_period)
    ema_long_prev = ema(close_prices[:-1], long_period)

    side = Side.LONG if ema_short_now > ema_long_now else Side.SHORT
    confirmed = (ema_short_now > ema_long_now and ema_short_prev > ema_long_prev) or (
        ema_short_now < ema_long_now and ema_short_prev < ema_long_prev
    )
    return TrendSignal(side=side, ema_short=ema_short_now, ema_long=ema_long_now, confirmed=confirmed)
