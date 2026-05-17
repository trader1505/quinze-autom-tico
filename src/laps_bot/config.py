from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _read_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _read_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class BotConfig:
    api_key: str
    api_secret: str
    sandbox: bool
    symbols: tuple[str, ...]
    timeframe: str
    fast_ma: int
    slow_ma: int
    max_positions: int
    balance_risk_pct: float
    leverage: int
    target_roi_pct: float
    add_margin_trigger_pct: float
    margin_ratio_trigger_pct: float
    margin_match_tolerance_pct: float
    taker_fee_rate: float
    reinforcement_multiplier: float
    spot_target_pct: float
    futures_target_pct: float
    margin_topup_pct: float
    max_topups: int
    poll_seconds: int
    log_level: str
    telemetry_dir: str
    panel_host: str
    panel_port: int


def load_config() -> BotConfig:
    load_dotenv()
    symbols = tuple(
        symbol.strip() for symbol in os.getenv("LAPS_SYMBOLS", "BTC/USDT:USDT").split(",") if symbol.strip()
    )
    if not symbols:
        raise ValueError("LAPS_SYMBOLS must provide at least one symbol.")

    cfg = BotConfig(
        api_key=os.getenv("LAPS_API_KEY", ""),
        api_secret=os.getenv("LAPS_API_SECRET", ""),
        sandbox=_read_bool("LAPS_SANDBOX", True),
        symbols=symbols,
        timeframe=os.getenv("LAPS_TIMEFRAME", "15m"),
        fast_ma=_read_int("LAPS_FAST_MA", 12),
        slow_ma=_read_int("LAPS_SLOW_MA", 26),
        max_positions=_read_int("LAPS_MAX_POSITIONS", 1),
        balance_risk_pct=_read_float("LAPS_BALANCE_RISK_PCT", 1.0),
        leverage=_read_int("LAPS_LEVERAGE", 20),
        target_roi_pct=_read_float("LAPS_TARGET_ROI_PCT", 100.0),
        add_margin_trigger_pct=_read_float("LAPS_ADD_MARGIN_TRIGGER_PCT", -60.0),
        margin_ratio_trigger_pct=_read_float("LAPS_MARGIN_RATIO_TRIGGER_PCT", 60.0),
        margin_match_tolerance_pct=_read_float("LAPS_MARGIN_MATCH_TOLERANCE_PCT", 0.25),
        taker_fee_rate=_read_float("LAPS_TAKER_FEE_RATE", 0.0005),
        reinforcement_multiplier=_read_float("LAPS_REINFORCEMENT_MULTIPLIER", 3.0),
        spot_target_pct=_read_float("LAPS_SPOT_TARGET_PCT", 80.0),
        futures_target_pct=_read_float("LAPS_FUTURES_TARGET_PCT", 20.0),
        margin_topup_pct=_read_float("LAPS_MARGIN_TOPUP_PCT", 20.0),
        max_topups=_read_int("LAPS_MAX_TOPUPS", 4),
        poll_seconds=_read_int("LAPS_POLL_SECONDS", 20),
        log_level=os.getenv("LAPS_LOG_LEVEL", "INFO"),
        telemetry_dir=os.getenv("LAPS_TELEMETRY_DIR", "runtime"),
        panel_host=os.getenv("LAPS_PANEL_HOST", "0.0.0.0"),
        panel_port=_read_int("LAPS_PANEL_PORT", 8080),
    )
    if cfg.fast_ma >= cfg.slow_ma:
        raise ValueError("Fast MA must be lower than slow MA.")
    if round(cfg.spot_target_pct + cfg.futures_target_pct, 10) != 100:
        raise ValueError("Spot and futures targets must sum to 100.")
    if cfg.balance_risk_pct <= 0:
        raise ValueError("LAPS_BALANCE_RISK_PCT must be positive.")
    if cfg.leverage <= 0:
        raise ValueError("LAPS_LEVERAGE must be positive.")
    if cfg.margin_ratio_trigger_pct <= 0:
        raise ValueError("LAPS_MARGIN_RATIO_TRIGGER_PCT must be positive.")
    if cfg.margin_match_tolerance_pct < 0:
        raise ValueError("LAPS_MARGIN_MATCH_TOLERANCE_PCT must be non-negative.")
    if cfg.taker_fee_rate < 0:
        raise ValueError("LAPS_TAKER_FEE_RATE must be non-negative.")
    if cfg.panel_port <= 0:
        raise ValueError("LAPS_PANEL_PORT must be positive.")
    return cfg
