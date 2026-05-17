from __future__ import annotations

import logging
from dataclasses import dataclass

from laps_bot.config import BotConfig
from laps_bot.indicators import crossover_from_closes, crossover_history_from_closes, ema, trend_from_closes
from laps_bot.models import Trend

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrendSignal:
    trend: Trend
    crossover: Trend | None
    latest_crossover: Trend | None
    previous_crossover: Trend | None
    fast_ema: float
    slow_ema: float


def resolve_trend(closes: list[float], config: BotConfig) -> TrendSignal:
    trend = trend_from_closes(closes, config.fast_ma, config.slow_ma)
    crossover = crossover_from_closes(closes, config.fast_ma, config.slow_ma)
    history = crossover_history_from_closes(closes, config.fast_ma, config.slow_ma)
    latest_crossover = history[-1] if history else None
    previous_crossover = history[-2] if len(history) > 1 else None
    fast_ema = ema(closes, config.fast_ma)
    slow_ema = ema(closes, config.slow_ma)
    if crossover is None:
        LOG.info(
            "Trend EMA(%s/%s): %s | fast=%.8f slow=%.8f",
            config.fast_ma,
            config.slow_ma,
            trend.value,
            fast_ema,
            slow_ema,
        )
    else:
        LOG.info(
            "Trend EMA(%s/%s): %s | crossover=%s | fast=%.8f slow=%.8f",
            config.fast_ma,
            config.slow_ma,
            trend.value,
            crossover.value,
            fast_ema,
            slow_ema,
        )
    return TrendSignal(
        trend=trend,
        crossover=crossover,
        latest_crossover=latest_crossover,
        previous_crossover=previous_crossover,
        fast_ema=fast_ema,
        slow_ema=slow_ema,
    )
