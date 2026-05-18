from __future__ import annotations

import logging

from laps_bot.config import BotConfig
from laps_bot.exchange import ExchangeGateway
from laps_bot.risk import split_8020

LOG = logging.getLogger(__name__)


def rebalance_80_20(exchange: ExchangeGateway, config: BotConfig) -> dict:
    spot_total = exchange.total_spot_usdt()
    futures_total = exchange.total_futures_usdt()
    combined = spot_total + futures_total
    if combined <= 0:
        LOG.warning("Skipping rebalance because total capital is zero.")
        return {
            "changed": False,
            "reason": "no_capital",
            "moved_amount_usdt": 0.0,
            "direction": "none",
            "spot_total_usdt": spot_total,
            "futures_total_usdt": futures_total,
        }

    target_spot, target_futures = split_8020(combined, config.spot_target_pct, config.futures_target_pct)
    spot_delta = target_spot - spot_total
    futures_delta = target_futures - futures_total

    if abs(spot_delta) < 0.0000001 and abs(futures_delta) < 0.0000001:
        LOG.info("80/20 rebalance not required.")
        return {
            "changed": False,
            "reason": "already_balanced",
            "moved_amount_usdt": 0.0,
            "direction": "none",
            "spot_total_usdt": spot_total,
            "futures_total_usdt": futures_total,
        }

    if spot_delta > 0:
        # move from futures to spot
        amount = min(spot_delta, exchange.free_futures_usdt())
        if amount > 0:
            exchange.transfer_usdt(amount, "future", "spot")
            LOG.info("Rebalanced %.8f USDT from futures to spot.", amount)
            return {
                "changed": True,
                "reason": "drift_to_futures",
                "moved_amount_usdt": amount,
                "direction": "future_to_spot",
                "spot_total_usdt": spot_total,
                "futures_total_usdt": futures_total,
            }
        return {
            "changed": False,
            "reason": "no_free_futures",
            "moved_amount_usdt": 0.0,
            "direction": "future_to_spot",
            "spot_total_usdt": spot_total,
            "futures_total_usdt": futures_total,
        }

    # move from spot to futures
    amount = min(abs(spot_delta), exchange.free_spot_usdt())
    if amount > 0:
        exchange.transfer_usdt(amount, "spot", "future")
        LOG.info("Rebalanced %.8f USDT from spot to futures.", amount)
        return {
            "changed": True,
            "reason": "drift_to_spot",
            "moved_amount_usdt": amount,
            "direction": "spot_to_future",
            "spot_total_usdt": spot_total,
            "futures_total_usdt": futures_total,
        }
    return {
        "changed": False,
        "reason": "no_free_spot",
        "moved_amount_usdt": 0.0,
        "direction": "spot_to_future",
        "spot_total_usdt": spot_total,
        "futures_total_usdt": futures_total,
    }
