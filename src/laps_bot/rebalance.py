from __future__ import annotations

import logging

from laps_bot.config import BotConfig
from laps_bot.exchange import ExchangeGateway
from laps_bot.risk import split_8020

LOG = logging.getLogger(__name__)


def rebalance_80_20(exchange: ExchangeGateway, config: BotConfig) -> None:
    spot_total = exchange.total_spot_usdt()
    futures_total = exchange.total_futures_usdt()
    combined = spot_total + futures_total
    if combined <= 0:
        LOG.warning("Skipping rebalance because total capital is zero.")
        return

    target_spot, target_futures = split_8020(combined, config.spot_target_pct, config.futures_target_pct)
    spot_delta = target_spot - spot_total
    futures_delta = target_futures - futures_total

    if abs(spot_delta) < 0.0000001 and abs(futures_delta) < 0.0000001:
        LOG.info("80/20 rebalance not required.")
        return

    if spot_delta > 0:
        # move from futures to spot
        amount = min(spot_delta, exchange.free_futures_usdt())
        if amount > 0:
            exchange.transfer_usdt(amount, "future", "spot")
            LOG.info("Rebalanced %.8f USDT from futures to spot.", amount)
        return

    # move from spot to futures
    amount = min(abs(spot_delta), exchange.free_spot_usdt())
    if amount > 0:
        exchange.transfer_usdt(amount, "spot", "future")
        LOG.info("Rebalanced %.8f USDT from spot to futures.", amount)
