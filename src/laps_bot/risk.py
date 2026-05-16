from __future__ import annotations

from laps_bot.config import BotConfig


def target_entry_usdt(free_futures_usdt: float, risk_pct: float) -> float:
    return (free_futures_usdt * risk_pct) / 100.0


def margin_topup_usdt(spot_available_usdt: float, topup_pct: float) -> float:
    return (spot_available_usdt * topup_pct) / 100.0


def should_add_margin(roi_pct: float, trigger_pct: float, topups_used: int, max_topups: int) -> bool:
    return roi_pct <= trigger_pct and topups_used < max_topups


def should_rebalance_after_recovery(roi_pct: float, recovery_pct: float, topups_used: int) -> bool:
    return topups_used > 0 and roi_pct >= recovery_pct


def split_8020(total_usdt: float, spot_pct: float, futures_pct: float) -> tuple[float, float]:
    spot_target = (total_usdt * spot_pct) / 100.0
    futures_target = (total_usdt * futures_pct) / 100.0
    return spot_target, futures_target


def validate_config(config: BotConfig) -> None:
    if config.max_positions != 1:
        raise ValueError("This first live version supports exactly 1 simultaneous position.")
