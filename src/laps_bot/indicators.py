from __future__ import annotations

from laps_bot.models import Trend


def ema_series(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        raise ValueError(f"Not enough values for period {period}.")
    multiplier = 2.0 / (period + 1.0)
    ema_values: list[float] = [values[0]]
    for price in values[1:]:
        ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def ema(values: list[float], period: int) -> float:
    return ema_series(values, period)[-1]


def trend_from_closes(closes: list[float], fast_period: int, slow_period: int) -> Trend:
    fast = ema(closes, fast_period)
    slow = ema(closes, slow_period)
    if fast > slow:
        return Trend.LONG
    if fast < slow:
        return Trend.SHORT
    return Trend.FLAT


def crossover_from_closes(closes: list[float], fast_period: int, slow_period: int) -> Trend | None:
    if len(closes) < max(fast_period, slow_period) + 1:
        return None

    fast_values = ema_series(closes, fast_period)
    slow_values = ema_series(closes, slow_period)
    prev_fast = fast_values[-2]
    prev_slow = slow_values[-2]
    curr_fast = fast_values[-1]
    curr_slow = slow_values[-1]

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return Trend.LONG
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return Trend.SHORT
    return None
