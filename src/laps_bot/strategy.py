from __future__ import annotations

import logging

from laps_bot.config import BotConfig
from laps_bot.indicators import trend_from_closes
from laps_bot.models import Trend

LOG = logging.getLogger(__name__)


def resolve_trend(closes: list[float], config: BotConfig) -> Trend:
    trend = trend_from_closes(closes, config.fast_ma, config.slow_ma)
    LOG.info("Trend (%s/%s): %s", config.fast_ma, config.slow_ma, trend.value)
    return trend
