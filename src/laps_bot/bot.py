from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from laps_bot.config import BotConfig
from laps_bot.exchange import ExchangeGateway
from laps_bot.models import PositionState, Trend
from laps_bot.rebalance import rebalance_80_20
from laps_bot.risk import (
    margin_topup_usdt,
    should_add_margin,
    should_rebalance_after_recovery,
    target_entry_usdt,
    validate_config,
)
from laps_bot.strategy import resolve_trend
from laps_bot.telemetry import TelemetryStore

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
        self.telemetry = TelemetryStore(config.telemetry_dir)

    def _emit(self, event_type: str, message: str, payload: dict[str, Any] | None = None, severity: str = "info") -> None:
        self.telemetry.emit(event_type, message, payload=payload, severity=severity)

    def _sync_state(self, status: str, position: PositionState | None = None, trend: Trend | None = None) -> None:
        if position is None:
            self.telemetry.update_state(
                status=status,
                symbol=None,
                side=None,
                contracts=0.0,
                entry_price=0.0,
                roi_pct=0.0,
                unrealized_pnl=0.0,
                trend=trend.value if trend else None,
                topups_used=self.state.topups_used,
                reinforcement_alert=self.state.reinforcement_alert,
                reinforcement_done=self.state.reinforcement_done,
                initial_entry_usdt=self.state.initial_entry_usdt,
            )
            return
        self.telemetry.update_state(
            status=status,
            symbol=position.symbol,
            side=position.side,
            contracts=position.contracts,
            entry_price=position.entry_price,
            roi_pct=position.roi_pct,
            unrealized_pnl=position.unrealized_pnl,
            trend=trend.value if trend else None,
            topups_used=self.state.topups_used,
            reinforcement_alert=self.state.reinforcement_alert,
            reinforcement_done=self.state.reinforcement_done,
            initial_entry_usdt=self.state.initial_entry_usdt,
        )

    def _signal_for_symbol(self, symbol: str) -> Trend:
        candles_needed = self.config.slow_ma + 5
        closes = self.exchange.fetch_closes(symbol, self.config.timeframe, candles_needed)
        trend = resolve_trend(closes, self.config)
        self._emit(
            "trend_evaluated",
            "Trend evaluated from M15 moving averages.",
            payload={
                "symbol": symbol,
                "timeframe": self.config.timeframe,
                "fast_ma": self.config.fast_ma,
                "slow_ma": self.config.slow_ma,
                "trend": trend.value,
            },
        )
        return trend

    def _base_side(self, side: str) -> Trend:
        return Trend.LONG if side == "long" else Trend.SHORT

    def _open_new_position(self) -> None:
        free_usdt = self.exchange.free_futures_usdt()
        target_margin_usdt = target_entry_usdt(free_usdt, self.config.balance_risk_pct)
        self._emit(
            "entry_attempt",
            "Attempting new entry using configured balance risk.",
            payload={
                "free_futures_usdt": free_usdt,
                "target_margin_usdt": target_margin_usdt,
                "risk_pct": self.config.balance_risk_pct,
                "leverage": self.config.leverage,
            },
        )
        try:
            symbol, amount, price, used_margin = self.exchange.choose_symbol_and_amount_for_exact_margin(
                self.config.symbols,
                target_margin_usdt,
                self.config.leverage,
            )
        except RuntimeError as exc:
            LOG.warning("Entry skipped: %s", exc)
            self._sync_state("waiting_entry")
            self._emit("entry_skipped", str(exc), severity="warning")
            return
        trend = self._signal_for_symbol(symbol)
        if trend == Trend.FLAT:
            LOG.info("Signal is FLAT on %s. Waiting.", symbol)
            self._sync_state("flat_trend_wait", trend=trend)
            self._emit(
                "entry_skipped",
                "Flat trend detected; entry not opened.",
                payload={"symbol": symbol},
                severity="warning",
            )
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
        self._sync_state("position_opened", trend=trend)
        self._emit(
            "position_opened",
            "New market position opened.",
            payload={
                "symbol": symbol,
                "side": trend.value,
                "amount": amount,
                "price": price,
                "target_margin_usdt": target_margin_usdt,
                "used_margin_usdt": used_margin,
                "leverage": self.config.leverage,
            },
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
            self._emit("reinforcement_3x_skipped", str(exc), severity="warning")
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
        self._emit(
            "reinforcement_3x_executed",
            "3x reinforcement executed after trend re-confirmation.",
            payload={
                "symbol": symbol,
                "side": base_trend.value,
                "used_margin_usdt": used_margin,
                "target_margin_usdt": reinforce_margin,
                "multiplier": self.config.reinforcement_multiplier,
            },
            severity="warning",
        )

    def _manage_open_position(self) -> None:
        position = self.exchange.fetch_open_position(self.config.symbols)
        if not position:
            self.state.reset()
            self._sync_state("no_open_position")
            self._open_new_position()
            return

        if self.state.initial_entry_usdt <= 0:
            self.state.initial_entry_usdt = position.initial_margin

        roi = position.roi_pct
        LOG.info("Position %s %s | ROI %.4f%%", position.symbol, position.side, roi)
        self._sync_state("position_active", position=position)
        self._emit(
            "position_update",
            "Position ROI updated.",
            payload={
                "symbol": position.symbol,
                "side": position.side,
                "contracts": position.contracts,
                "entry_price": position.entry_price,
                "roi_pct": roi,
                "unrealized_pnl": position.unrealized_pnl,
            },
        )

        if roi >= self.config.target_roi_pct:
            self.exchange.close_position(position)
            rebalance_80_20(self.exchange, self.config)
            self._emit(
                "tp_hit",
                "Target ROI reached; position closed and capital rebalanced 80/20.",
                payload={
                    "symbol": position.symbol,
                    "side": position.side,
                    "roi_pct": roi,
                    "target_roi_pct": self.config.target_roi_pct,
                },
            )
            self._emit(
                "cash_rebalance",
                "Cash rebalance executed after TP.",
                payload={
                    "spot_target_pct": self.config.spot_target_pct,
                    "futures_target_pct": self.config.futures_target_pct,
                },
            )
            self.state.reset()
            self._sync_state("tp_closed")
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
                self._emit(
                    "margin_topped_up",
                    "Margin topup triggered by negative ROI threshold.",
                    payload={
                        "symbol": position.symbol,
                        "roi_pct": roi,
                        "topup_amount_usdt": topup_amount,
                        "topups_used": self.state.topups_used,
                        "max_topups": self.config.max_topups,
                    },
                    severity="warning",
                )

        if should_rebalance_after_recovery(roi, self.config.rebalance_recovery_pct, self.state.topups_used):
            rebalance_80_20(self.exchange, self.config)
            self.state.topups_used = 0
            self._emit(
                "recovery_rebalanced",
                "ROI recovered; 80/20 rebalance executed.",
                payload={
                    "symbol": position.symbol,
                    "roi_pct": roi,
                    "recovery_threshold_pct": self.config.rebalance_recovery_pct,
                },
            )
            LOG.info("Recovered above %.2f%% ROI. 80/20 rebalance completed.", self.config.rebalance_recovery_pct)

        market_trend = self._signal_for_symbol(position.symbol)
        base_trend = self._base_side(position.side)
        self._sync_state("position_active", position=position, trend=market_trend)

        if market_trend != Trend.FLAT and market_trend != base_trend:
            if not self.state.reinforcement_alert:
                LOG.warning(
                    "Trend reversed against open %s on %s. Waiting for same-direction confirmation.",
                    position.side,
                    position.symbol,
                )
                self._emit(
                    "reinforcement_alert",
                    "Trend reversed against position; waiting for re-confirmation.",
                    payload={
                        "symbol": position.symbol,
                        "position_side": position.side,
                        "trend_now": market_trend.value,
                    },
                    severity="warning",
                )
            self.state.reinforcement_alert = True
            self._sync_state("reinforcement_alert", position=position, trend=market_trend)
            return

        if self.state.reinforcement_alert and market_trend == base_trend and not self.state.reinforcement_done:
            self._handle_reinforcement(position.symbol, base_trend)
            self._sync_state("reinforcement_executed", position=position, trend=market_trend)
            return

        if self.state.reinforcement_done and roi >= 0:
            self.exchange.close_position(position)
            rebalance_80_20(self.exchange, self.config)
            self._emit(
                "reinforcement_recovered_close",
                "3x reinforced position recovered to break-even and was closed.",
                payload={
                    "symbol": position.symbol,
                    "side": position.side,
                    "roi_pct": roi,
                },
            )
            self._emit(
                "cash_rebalance",
                "Cash rebalance executed after 3x recovery close.",
                payload={
                    "spot_target_pct": self.config.spot_target_pct,
                    "futures_target_pct": self.config.futures_target_pct,
                },
            )
            self.state.reset()
            self._sync_state("reinforcement_recovered_closed")
            LOG.info("Reinforced position returned to non-negative ROI. Position closed.")

    def run_forever(self) -> None:
        LOG.info("Starting LAPS bot with symbols=%s timeframe=%s", self.config.symbols, self.config.timeframe)
        self._sync_state("running")
        self._emit(
            "bot_started",
            "LAPS bot started.",
            payload={
                "symbols": list(self.config.symbols),
                "timeframe": self.config.timeframe,
                "risk_pct": self.config.balance_risk_pct,
                "target_roi_pct": self.config.target_roi_pct,
                "leverage": self.config.leverage,
            },
        )
        while True:
            try:
                self._manage_open_position()
            except Exception as exc:
                LOG.exception("Fatal cycle error.")
                self._emit("cycle_error", f"Fatal cycle error: {exc}", severity="error")
                self._sync_state("error")
            time.sleep(self.config.poll_seconds)
