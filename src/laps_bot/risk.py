from __future__ import annotations

from laps_bot.config import BotConfig


def target_entry_usdt(free_futures_usdt: float, risk_pct: float) -> float:
    return (free_futures_usdt * risk_pct) / 100.0


def margin_topup_usdt(spot_available_usdt: float, topup_pct: float) -> float:
    return (spot_available_usdt * topup_pct) / 100.0


def should_add_margin(
    roi_pct: float,
    trigger_pct: float,
    margin_ratio_pct: float | None,
    margin_ratio_trigger_pct: float,
    topups_used: int,
    max_topups: int,
) -> bool:
    if topups_used >= max_topups:
        return False
    if roi_pct > trigger_pct:
        return False
    if margin_ratio_pct is None:
        return False
    return margin_ratio_pct >= margin_ratio_trigger_pct


def should_rebalance_after_recovery(roi_pct: float, recovery_pct: float, topups_used: int) -> bool:
    return topups_used > 0 and roi_pct >= recovery_pct


def split_8020(total_usdt: float, spot_pct: float, futures_pct: float) -> tuple[float, float]:
    spot_target = (total_usdt * spot_pct) / 100.0
    futures_target = (total_usdt * futures_pct) / 100.0
    return spot_target, futures_target


def validate_config(config: BotConfig) -> None:
    if config.max_positions <= 0:
        raise ValueError("LAPS_MAX_POSITIONS must be greater than zero.")
    if config.margin_ratio_trigger_pct <= 0:
        raise ValueError("LAPS_MARGIN_RATIO_TRIGGER_PCT must be positive.")
    if config.margin_ratio_emergency_pct < config.margin_ratio_trigger_pct:
        raise ValueError("LAPS_MARGIN_RATIO_EMERGENCY_PCT must be >= LAPS_MARGIN_RATIO_TRIGGER_PCT.")
    if config.margin_emergency_topup_pct <= 0 or config.margin_emergency_topup_pct > 100:
        raise ValueError("LAPS_MARGIN_EMERGENCY_TOPUP_PCT must be between 0 and 100.")
    if config.margin_ratio_hard_stop_pct <= config.margin_ratio_emergency_pct:
        raise ValueError("LAPS_MARGIN_RATIO_HARD_STOP_PCT must be > LAPS_MARGIN_RATIO_EMERGENCY_PCT.")
    if config.margin_ratio_hard_stop_pct > 100:
        raise ValueError("LAPS_MARGIN_RATIO_HARD_STOP_PCT must be <= 100.")
    if config.margin_ratio_rebalance_pct <= 0:
        raise ValueError("LAPS_MARGIN_RATIO_REBALANCE_PCT must be positive.")
    if config.margin_ratio_rebalance_pct >= config.margin_ratio_trigger_pct:
        raise ValueError("LAPS_MARGIN_RATIO_REBALANCE_PCT must be lower than LAPS_MARGIN_RATIO_TRIGGER_PCT.")
    if config.scan_all_symbols:
        if config.max_positions > config.max_scan_symbols:
            raise ValueError("LAPS_MAX_POSITIONS cannot be greater than LAPS_MAX_SCAN_SYMBOLS.")
        return
    if config.max_positions > len(config.symbols):
        raise ValueError("LAPS_MAX_POSITIONS cannot be greater than the number of configured symbols.")
