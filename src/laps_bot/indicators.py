from __future__ import annotations

from statistics import mean

from laps_bot.models import Trend


def sma(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError(f"Not enough values for period {period}.")
    return mean(values[-period:])


def trend_from_closes(closes: list[float], fast_period: int, slow_period: int) -> Trend:
    fast = sma(closes, fast_period)
    slow = sma(closes, slow_period)
    if fast > slow:
        return Trend.LONG
    if fast < slow:
        return Trend.SHORT
    return Trend.FLAT
