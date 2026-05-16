from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from laps_bot.config import BotConfig
from laps_bot.exchange import ExchangeGateway
from laps_bot.models import Trend
from laps_bot.rebalance import rebalance_80_20
from laps_bot.risk import (
    margin_topup_usdt,
    should_add_margin,
    should_rebalance_after_recovery,
    target_entry_usdt,
    validate_config,
)
from laps_bot.strategy import resolve_trend

LOG = logging.getLogger(__name__)


@dataclass
class RuntimeState:
    initial_entry_usdt: float = 0.0
    topups_used: int = 0
    reinforcement_alert: bool = False
    reinforcement_done: bool = False

    def reset(self) -> None:
        self.initial_entry_usdt = 0.0
        self.topups_used = 0
        self.reinforcement_alert = False
        self.reinforcement_done = False


class LapsBot:
    def __init__(self, config: BotConfig) -> None:
        validate_config(config)
        self.config = config
        self.exchange = ExchangeGateway(config)
        self.state = RuntimeState()

    def _signal_for_symbol(self, symbol: str) -> Trend:
        candles_needed = self.config.slow_ma + 5
        closes = self.exchange.fetch_closes(symbol, self.config.timeframe, candles_needed)
        return resolve_trend(closes, self.config)

    def _base_side(self, side: str) -> Trend:
        return Trend.LONG if side == "long" else Trend.SHORT

    def _open_new_position(self) -> None:
        free_usdt = self.exchange.free_futures_usdt()
        target_margin_usdt = target_entry_usdt(free_usdt, self.config.balance_risk_pct)
        try:
            symbol, amount, price, used_margin = self.exchange.choose_symbol_and_amount_for_exact_margin(
                self.config.symbols,
                target_margin_usdt,
                self.config.leverage,
            )
        except RuntimeError as exc:
            LOG.warning("Entry skipped: %s", exc)
            return
        trend = self._signal_for_symbol(symbol)
        if trend == Trend.FLAT:
            LOG.info("Signal is FLAT on %s. Waiting.", symbol)
            return

        self.exchange.create_market_position(symbol, trend, amount, reduce_only=False)
        self.state.initial_entry_usdt = used_margin
        self.state.topups_used = 0
        self.state.reinforcement_alert = False
        self.state.reinforcement_done = False
        LOG.info(
            "Opened %s on %s with %.8f contracts (price %.8f, target margin %.8f USDT, used margin %.8f USDT, leverage %sx).",
            trend.value,
            symbol,
            amount,
            price,
            target_margin_usdt,
            used_margin,
            self.config.leverage,
        )

    def _handle_reinforcement(self, symbol: str, base_trend: Trend) -> None:
        if self.state.initial_entry_usdt <= 0:
            return
        reinforce_margin = self.state.initial_entry_usdt * self.config.reinforcement_multiplier
        try:
            symbol, amount, _, used_margin = self.exchange.choose_symbol_and_amount_for_exact_margin(
                [symbol],
                reinforce_margin,
                self.config.leverage,
            )
        except RuntimeError as exc:
            LOG.warning("3x reinforcement skipped: %s", exc)
            return
        self.exchange.create_market_position(symbol, base_trend, amount, reduce_only=False)
        self.state.reinforcement_alert = False
        self.state.reinforcement_done = True
        LOG.warning(
            "3x reinforcement executed on %s with used margin %.8f USDT (target %.8f USDT).",
            symbol,
            used_margin,
            reinforce_margin,
        )

    def _manage_open_position(self) -> None:
        position = self.exchange.fetch_open_position(self.config.symbols)
        if not position:
            self.state.reset()
            self._open_new_position()
            return

        if self.state.initial_entry_usdt <= 0:
            self.state.initial_entry_usdt = position.initial_margin

        roi = position.roi_pct
        LOG.info("Position %s %s | ROI %.4f%%", position.symbol, position.side, roi)

        if roi >= self.config.target_roi_pct:
            self.exchange.close_position(position)
            rebalance_80_20(self.exchange, self.config)
            self.state.reset()
            LOG.info("Target ROI reached. Position closed and 80/20 rebalanced.")
            return

        if should_add_margin(
            roi,
            self.config.add_margin_trigger_pct,
            self.state.topups_used,
            self.config.max_topups,
        ):
            topup_amount = margin_topup_usdt(self.exchange.free_spot_usdt(), self.config.margin_topup_pct)
            if topup_amount > 0:
                self.exchange.transfer_usdt(topup_amount, "spot", "future")
                self.state.topups_used += 1
                LOG.warning(
                    "Negative ROI trigger reached (%.4f%%). Added %.8f USDT margin. Topups: %s/%s",
                    roi,
                    topup_amount,
                    self.state.topups_used,
                    self.config.max_topups,
                )

        if should_rebalance_after_recovery(roi, self.config.rebalance_recovery_pct, self.state.topups_used):
            rebalance_80_20(self.exchange, self.config)
            self.state.topups_used = 0
            LOG.info("Recovered above %.2f%% ROI. 80/20 rebalance completed.", self.config.rebalance_recovery_pct)

        market_trend = self._signal_for_symbol(position.symbol)
        base_trend = self._base_side(position.side)

        if market_trend != Trend.FLAT and market_trend != base_trend:
            if not self.state.reinforcement_alert:
                LOG.warning(
                    "Trend reversed against open %s on %s. Waiting for same-direction confirmation.",
                    position.side,
                    position.symbol,
                )
            self.state.reinforcement_alert = True
            return

        if self.state.reinforcement_alert and market_trend == base_trend and not self.state.reinforcement_done:
            self._handle_reinforcement(position.symbol, base_trend)
            return

        if self.state.reinforcement_done and roi >= 0:
            self.exchange.close_position(position)
            rebalance_80_20(self.exchange, self.config)
            self.state.reset()
            LOG.info("Reinforced position returned to non-negative ROI. Position closed.")

    def run_forever(self) -> None:
        LOG.info("Starting LAPS bot with symbols=%s timeframe=%s", self.config.symbols, self.config.timeframe)
        while True:
            try:
                self._manage_open_position()
            except Exception:
                LOG.exception("Fatal cycle error.")
            time.sleep(self.config.poll_seconds)
