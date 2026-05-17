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
    target_entry_usdt,
    validate_config,
)
from laps_bot.strategy import TrendSignal, resolve_trend
from laps_bot.telemetry import TelemetryStore

LOG = logging.getLogger(__name__)


@dataclass
class PositionRuntimeState:
    initial_entry_usdt: float = 0.0
    estimated_open_fees_usdt: float = 0.0
    topups_used: int = 0
    reinforcement_alert: bool = False
    reinforcement_done: bool = False
    reinforcement_funding_bucket: int | None = None
    reinforcement_exit_bucket: int | None = None

    def reset(self) -> None:
        self.initial_entry_usdt = 0.0
        self.estimated_open_fees_usdt = 0.0
        self.topups_used = 0
        self.reinforcement_alert = False
        self.reinforcement_done = False
        self.reinforcement_funding_bucket = None
        self.reinforcement_exit_bucket = None


class LapsBot:
    def __init__(self, config: BotConfig) -> None:
        validate_config(config)
        self.config = config
        self.exchange = ExchangeGateway(config)
        self.position_states: dict[str, PositionRuntimeState] = {}
        self.telemetry = TelemetryStore(config.telemetry_dir)
        self._restore_runtime_state()

    def _restore_runtime_state(self) -> None:
        snapshot = self.telemetry.read_state()
        for item in snapshot.get("positions", []) or []:
            symbol = item.get("symbol")
            if not symbol:
                continue
            state = self._state_for_symbol(str(symbol))
            state.topups_used = int(item.get("topups_used", 0) or 0)
            state.reinforcement_alert = bool(item.get("reinforcement_alert", False))
            state.reinforcement_done = bool(item.get("reinforcement_done", False))
            state.initial_entry_usdt = float(item.get("initial_entry_usdt", 0.0) or 0.0)
            state.estimated_open_fees_usdt = float(item.get("estimated_open_fees_usdt", 0.0) or 0.0)
            funding_bucket_raw = item.get("reinforcement_funding_bucket")
            if funding_bucket_raw is None:
                state.reinforcement_funding_bucket = None
            else:
                try:
                    state.reinforcement_funding_bucket = int(funding_bucket_raw)
                except (TypeError, ValueError):
                    state.reinforcement_funding_bucket = None
            exit_bucket_raw = item.get("reinforcement_exit_bucket")
            if exit_bucket_raw is None:
                state.reinforcement_exit_bucket = None
            else:
                try:
                    state.reinforcement_exit_bucket = int(exit_bucket_raw)
                except (TypeError, ValueError):
                    state.reinforcement_exit_bucket = None

    def _emit(self, event_type: str, message: str, payload: dict[str, Any] | None = None, severity: str = "info") -> None:
        self.telemetry.emit(event_type, message, payload=payload, severity=severity)

    def _state_for_symbol(self, symbol: str) -> PositionRuntimeState:
        state = self.position_states.get(symbol)
        if state is not None:
            return state
        state = PositionRuntimeState()
        self.position_states[symbol] = state
        return state

    def _drop_closed_states(self, open_symbols: set[str]) -> None:
        for symbol in list(self.position_states.keys()):
            if symbol not in open_symbols:
                del self.position_states[symbol]

    def _capital_snapshot(self) -> dict[str, float]:
        spot_total = self.exchange.total_spot_usdt()
        futures_total = self.exchange.total_futures_usdt()
        spot_free = self.exchange.free_spot_usdt()
        futures_free = self.exchange.free_futures_usdt()
        total = spot_total + futures_total
        if total <= 0:
            spot_pct = 0.0
            futures_pct = 0.0
        else:
            spot_pct = (spot_total / total) * 100
            futures_pct = (futures_total / total) * 100
        return {
            "spot_total_usdt": spot_total,
            "futures_total_usdt": futures_total,
            "spot_free_usdt": spot_free,
            "futures_free_usdt": futures_free,
            "capital_total_usdt": total,
            "spot_pct_actual": spot_pct,
            "futures_pct_actual": futures_pct,
            "spot_target_pct": self.config.spot_target_pct,
            "futures_target_pct": self.config.futures_target_pct,
        }

    def _estimate_taker_fee_usdt(self, notional_usdt: float) -> float:
        if notional_usdt <= 0:
            return 0.0
        return notional_usdt * self.config.taker_fee_rate

    def _sync_state(
        self,
        status: str,
        positions: list[PositionState] | None = None,
        trends: dict[str, Trend] | None = None,
        capital: dict[str, float] | None = None,
    ) -> None:
        positions = positions or []
        trends = trends or {}
        capital = capital or {
            "spot_total_usdt": 0.0,
            "futures_total_usdt": 0.0,
            "spot_free_usdt": 0.0,
            "futures_free_usdt": 0.0,
            "capital_total_usdt": 0.0,
            "spot_pct_actual": 0.0,
            "futures_pct_actual": 0.0,
            "spot_target_pct": self.config.spot_target_pct,
            "futures_target_pct": self.config.futures_target_pct,
        }
        if not positions:
            self.telemetry.update_state(
                status=status,
                symbol=None,
                side=None,
                contracts=0.0,
                entry_price=0.0,
                roi_pct=0.0,
                unrealized_pnl=0.0,
                trend=None,
                topups_used=0,
                reinforcement_alert=False,
                reinforcement_done=False,
                initial_entry_usdt=0.0,
                open_positions_count=0,
                positions=[],
                **capital,
            )
            return

        lead = max(positions, key=lambda item: abs(item.roi_pct))
        lead_state = self.position_states.get(lead.symbol, PositionRuntimeState())
        position_payload = [
            {
                "symbol": p.symbol,
                "side": p.side,
                "contracts": p.contracts,
                "entry_price": p.entry_price,
                "roi_pct": p.roi_pct,
                "unrealized_pnl": p.unrealized_pnl,
                "mark_price": p.mark_price,
                "liquidation_price": p.liquidation_price,
                "margin_ratio_pct": p.margin_ratio_pct,
                "trend": trends.get(p.symbol).value if trends.get(p.symbol) else None,
                "topups_used": self.position_states.get(p.symbol, PositionRuntimeState()).topups_used,
                "reinforcement_alert": self.position_states.get(p.symbol, PositionRuntimeState()).reinforcement_alert,
                "reinforcement_done": self.position_states.get(p.symbol, PositionRuntimeState()).reinforcement_done,
                "initial_entry_usdt": self.position_states.get(p.symbol, PositionRuntimeState()).initial_entry_usdt,
                "estimated_open_fees_usdt": self.position_states.get(
                    p.symbol, PositionRuntimeState()
                ).estimated_open_fees_usdt,
                "reinforcement_funding_bucket": self.position_states.get(
                    p.symbol, PositionRuntimeState()
                ).reinforcement_funding_bucket,
                "reinforcement_exit_bucket": self.position_states.get(
                    p.symbol, PositionRuntimeState()
                ).reinforcement_exit_bucket,
            }
            for p in positions
        ]

        self.telemetry.update_state(
            status=status,
            symbol=lead.symbol,
            side=lead.side,
            contracts=lead.contracts,
            entry_price=lead.entry_price,
            roi_pct=lead.roi_pct,
            unrealized_pnl=lead.unrealized_pnl,
            trend=trends.get(lead.symbol).value if trends.get(lead.symbol) else None,
            topups_used=lead_state.topups_used,
            reinforcement_alert=lead_state.reinforcement_alert,
            reinforcement_done=lead_state.reinforcement_done,
            initial_entry_usdt=lead_state.initial_entry_usdt,
            open_positions_count=len(positions),
            positions=position_payload,
            **capital,
        )

    def _signal_for_symbol(self, symbol: str) -> TrendSignal:
        candles_needed = self.config.slow_ma + 50
        closes = self.exchange.fetch_closes(symbol, self.config.timeframe, candles_needed + 1)
        # Ignore current forming candle to avoid premature crossover triggers.
        if len(closes) > candles_needed:
            closes = closes[:-1]
        signal = resolve_trend(closes, self.config)
        self._emit(
            "trend_evaluated",
            "Trend evaluated from M15 EMA crossover model.",
            payload={
                "symbol": symbol,
                "timeframe": self.config.timeframe,
                "fast_ema_period": self.config.fast_ma,
                "slow_ema_period": self.config.slow_ma,
                "trend": signal.trend.value,
                "crossover": signal.crossover.value if signal.crossover else None,
                "latest_crossover": signal.latest_crossover.value if signal.latest_crossover else None,
                "previous_crossover": signal.previous_crossover.value if signal.previous_crossover else None,
                "fast_ema": signal.fast_ema,
                "slow_ema": signal.slow_ema,
            },
        )
        return signal

    def _base_side(self, side: str) -> Trend:
        return Trend.LONG if side == "long" else Trend.SHORT

    @staticmethod
    def _timeframe_to_seconds(timeframe: str) -> int:
        unit = timeframe[-1]
        try:
            value = int(timeframe[:-1])
        except ValueError:
            return 60
        if unit == "m":
            return value * 60
        if unit == "h":
            return value * 3600
        if unit == "d":
            return value * 86400
        return max(value, 1)

    def _ensure_reinforcement_funding(self, symbol: str, required_margin: float, state: PositionRuntimeState) -> bool:
        free_futures = self.exchange.free_futures_usdt()
        if free_futures >= required_margin:
            return True

        timeframe_seconds = self._timeframe_to_seconds(self.config.timeframe)
        bucket = int(time.time()) // timeframe_seconds
        if state.reinforcement_funding_bucket == bucket:
            self._emit(
                "reinforcement_3x_skipped",
                "3x funding transfer cooldown active for current candle.",
                payload={
                    "symbol": symbol,
                    "required_margin_usdt": required_margin,
                    "free_futures_usdt": free_futures,
                    "timeframe": self.config.timeframe,
                },
                severity="warning",
            )
            return False

        missing_margin = required_margin - free_futures
        buffer = max(required_margin * 0.005, 0.0001)
        transfer_needed = missing_margin + buffer
        spot_free = self.exchange.free_spot_usdt()
        if spot_free < transfer_needed:
            self._emit(
                "reinforcement_3x_skipped",
                "3x reinforcement skipped: insufficient spot free balance for funding transfer.",
                payload={
                    "symbol": symbol,
                    "required_margin_usdt": required_margin,
                    "missing_margin_usdt": missing_margin,
                    "requested_transfer_usdt": transfer_needed,
                    "spot_free_usdt": spot_free,
                },
                severity="warning",
            )
            state.reinforcement_funding_bucket = bucket
            return False

        try:
            self.exchange.transfer_usdt(transfer_needed, "spot", "future")
        except Exception as exc:
            self._emit(
                "reinforcement_3x_skipped",
                "3x reinforcement skipped: transfer spot->future failed.",
                payload={
                    "symbol": symbol,
                    "required_margin_usdt": required_margin,
                    "requested_transfer_usdt": transfer_needed,
                    "error": str(exc),
                },
                severity="error",
            )
            state.reinforcement_funding_bucket = bucket
            return False

        state.reinforcement_funding_bucket = bucket
        free_after = self.exchange.free_futures_usdt()
        self._emit(
            "reinforcement_funding_transfer",
            "Transferred spot to futures to fund 3x reinforcement.",
            payload={
                "symbol": symbol,
                "requested_transfer_usdt": transfer_needed,
                "required_margin_usdt": required_margin,
                "free_futures_before_usdt": free_futures,
                "free_futures_after_usdt": free_after,
            },
            severity="warning",
        )
        return free_after >= required_margin

    def _open_new_position(self, blocked_symbols: set[str]) -> bool:
        available_symbols = [symbol for symbol in self.config.symbols if symbol not in blocked_symbols]
        if not available_symbols:
            self._emit(
                "entry_skipped",
                "No symbols available for new slot because all configured symbols already have positions.",
                severity="warning",
            )
            return False

        free_usdt = self.exchange.free_futures_usdt()
        target_margin_usdt = target_entry_usdt(free_usdt, self.config.balance_risk_pct)
        if target_margin_usdt <= 0:
            self._emit(
                "entry_skipped",
                "Entry skipped because free futures balance is zero.",
                payload={"free_futures_usdt": free_usdt},
                severity="warning",
            )
            return False
        self._emit(
            "entry_attempt",
            "Attempting new entry using configured balance risk.",
            payload={
                "free_futures_usdt": free_usdt,
                "target_margin_usdt": target_margin_usdt,
                "risk_pct": self.config.balance_risk_pct,
                "leverage": self.config.leverage,
                "available_symbols": available_symbols,
            },
        )
        try:
            symbol, amount, price, used_margin = self.exchange.choose_symbol_and_amount_for_exact_margin(
                available_symbols,
                target_margin_usdt,
                self.config.leverage,
            )
        except RuntimeError as exc:
            LOG.warning("Entry skipped: %s", exc)
            self._emit("entry_skipped", str(exc), severity="warning")
            return False
        trend_signal = self._signal_for_symbol(symbol)
        trend = trend_signal.trend
        if trend == Trend.FLAT:
            LOG.info("Signal is FLAT on %s. Waiting.", symbol)
            self._emit(
                "entry_skipped",
                "Flat trend detected; entry not opened.",
                payload={"symbol": symbol},
                severity="warning",
            )
            return False

        self.exchange.create_market_position(symbol, trend, amount, reduce_only=False)
        state = self._state_for_symbol(symbol)
        state.initial_entry_usdt = used_margin
        open_notional = amount * price
        state.estimated_open_fees_usdt = self._estimate_taker_fee_usdt(open_notional)
        state.topups_used = 0
        state.reinforcement_alert = False
        state.reinforcement_done = False
        blocked_symbols.add(symbol)
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
                "estimated_open_fees_usdt": state.estimated_open_fees_usdt,
                "leverage": self.config.leverage,
            },
        )
        return True

    def _handle_reinforcement(self, symbol: str, base_trend: Trend, state: PositionRuntimeState) -> None:
        if state.initial_entry_usdt <= 0:
            return
        reinforce_margin = state.initial_entry_usdt * self.config.reinforcement_multiplier
        if not self._ensure_reinforcement_funding(symbol, reinforce_margin, state):
            return
        try:
            symbol, amount, price, used_margin = self.exchange.choose_symbol_and_amount_for_exact_margin(
                [symbol],
                reinforce_margin,
                self.config.leverage,
            )
        except RuntimeError as exc:
            LOG.warning("3x reinforcement skipped: %s", exc)
            self._emit("reinforcement_3x_skipped", str(exc), severity="warning")
            return
        self.exchange.create_market_position(symbol, base_trend, amount, reduce_only=False)
        state.reinforcement_alert = False
        state.reinforcement_done = True
        reinforcement_notional = amount * price
        state.estimated_open_fees_usdt += self._estimate_taker_fee_usdt(reinforcement_notional)
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
                "estimated_open_fees_usdt": state.estimated_open_fees_usdt,
                "multiplier": self.config.reinforcement_multiplier,
            },
            severity="warning",
        )

    def _manage_single_position(self, position: PositionState) -> Trend | None:
        state = self._state_for_symbol(position.symbol)
        if state.initial_entry_usdt <= 0:
            state.initial_entry_usdt = position.initial_margin
        roi = position.roi_pct
        LOG.info("Position %s %s | ROI %.4f%%", position.symbol, position.side, roi)
        self._emit(
            "position_update",
            "Position ROI updated.",
            payload={
                "symbol": position.symbol,
                "side": position.side,
                "contracts": position.contracts,
                "entry_price": position.entry_price,
                "mark_price": position.mark_price,
                "liquidation_price": position.liquidation_price,
                "margin_ratio_pct": position.margin_ratio_pct,
                "roi_pct": roi,
                "unrealized_pnl": position.unrealized_pnl,
            },
        )

        if roi >= self.config.target_roi_pct:
            self.exchange.close_position(position)
            try:
                rebalance_80_20(self.exchange, self.config)
            except Exception as exc:
                LOG.warning("Rebalance after TP failed on %s: %s", position.symbol, exc)
                self._emit(
                    "cash_rebalance_failed",
                    "Cash rebalance failed after TP close.",
                    payload={"symbol": position.symbol, "error": str(exc)},
                    severity="error",
                )
            capital_after = self._capital_snapshot()
            self._emit(
                "tp_hit",
                "Target ROI reached; position closed and capital rebalanced 80/20.",
                payload={
                    "symbol": position.symbol,
                    "side": position.side,
                    "roi_pct": roi,
                    "target_roi_pct": self.config.target_roi_pct,
                    "estimated_realized_pnl_usdt": position.unrealized_pnl,
                    "position_margin_usdt": position.initial_margin,
                    "close_reason": "tp_target",
                    **capital_after,
                },
            )
            self._emit(
                "cash_rebalance",
                "Cash rebalance executed after TP.",
                payload={
                    **capital_after,
                },
            )
            self.position_states.pop(position.symbol, None)
            LOG.info("Target ROI reached. Position closed and 80/20 rebalanced.")
            return None

        if should_add_margin(
            roi,
            self.config.add_margin_trigger_pct,
            position.margin_ratio_pct,
            self.config.margin_ratio_trigger_pct,
            state.topups_used,
            self.config.max_topups,
        ):
            topup_amount = margin_topup_usdt(self.exchange.free_spot_usdt(), self.config.margin_topup_pct)
            if topup_amount > 0:
                try:
                    self.exchange.transfer_usdt(topup_amount, "spot", "future")
                    state.topups_used += 1
                    LOG.warning(
                        "Margin trigger reached on %s (ROI %.4f%%, margin ratio %.4f%%). Added %.8f USDT. Topups: %s/%s",
                        position.symbol,
                        roi,
                        position.margin_ratio_pct if position.margin_ratio_pct is not None else -1.0,
                        topup_amount,
                        state.topups_used,
                        self.config.max_topups,
                    )
                    self._emit(
                        "margin_topped_up",
                        "Margin topup triggered by negative ROI threshold.",
                        payload={
                            "symbol": position.symbol,
                            "roi_pct": roi,
                            "margin_ratio_pct": position.margin_ratio_pct,
                            "margin_ratio_trigger_pct": self.config.margin_ratio_trigger_pct,
                            "topup_amount_usdt": topup_amount,
                            "topups_used": state.topups_used,
                            "max_topups": self.config.max_topups,
                        },
                        severity="warning",
                    )
                except Exception as exc:
                    LOG.warning("Margin topup transfer failed on %s: %s", position.symbol, exc)
                    self._emit(
                        "margin_topup_failed",
                        "Margin topup transfer failed.",
                        payload={
                            "symbol": position.symbol,
                            "roi_pct": roi,
                            "margin_ratio_pct": position.margin_ratio_pct,
                            "margin_ratio_trigger_pct": self.config.margin_ratio_trigger_pct,
                            "topup_amount_usdt": topup_amount,
                            "error": str(exc),
                        },
                        severity="error",
                    )
        elif roi <= self.config.add_margin_trigger_pct and (
            position.margin_ratio_pct is None or position.margin_ratio_pct < self.config.margin_ratio_trigger_pct
        ):
            self._emit(
                "margin_topped_up_skipped",
                "Topup skipped because margin ratio trigger was not reached.",
                payload={
                    "symbol": position.symbol,
                    "roi_pct": roi,
                    "roi_trigger_pct": self.config.add_margin_trigger_pct,
                    "margin_ratio_pct": position.margin_ratio_pct,
                    "margin_ratio_trigger_pct": self.config.margin_ratio_trigger_pct,
                },
            )

        trend_signal = self._signal_for_symbol(position.symbol)
        market_trend = trend_signal.trend
        crossover = trend_signal.crossover
        base_trend = self._base_side(position.side)
        opposite_trend = Trend.SHORT if base_trend == Trend.LONG else Trend.LONG
        sequence_ready = (
            trend_signal.latest_crossover == base_trend and trend_signal.previous_crossover == opposite_trend
        )

        # If bot restarts while trend is already opposite, recover alert state.
        if (
            not state.reinforcement_alert
            and not state.reinforcement_done
            and market_trend != Trend.FLAT
            and market_trend != base_trend
        ):
            state.reinforcement_alert = True
            self._emit(
                "reinforcement_alert",
                "Opposite trend active; 3x alert state recovered while waiting return crossover.",
                payload={
                    "symbol": position.symbol,
                    "position_side": position.side,
                    "trend_now": market_trend.value,
                    "crossover": crossover.value if crossover else None,
                    "entry_side": base_trend.value,
                },
                severity="warning",
            )

        # If crossovers already formed opposite -> return while bot was offline,
        # recover and execute 3x once to match strategy intent.
        if not state.reinforcement_done and sequence_ready and not state.reinforcement_alert:
            state.reinforcement_alert = True
            self._emit(
                "reinforcement_alert",
                "Recovered opposite->return EMA crossover sequence from history.",
                payload={
                    "symbol": position.symbol,
                    "position_side": position.side,
                    "latest_crossover": trend_signal.latest_crossover.value if trend_signal.latest_crossover else None,
                    "previous_crossover": trend_signal.previous_crossover.value if trend_signal.previous_crossover else None,
                    "entry_side": base_trend.value,
                },
                severity="warning",
            )

        if crossover is not None and crossover != base_trend:
            if not state.reinforcement_alert:
                LOG.warning(
                    "Opposite EMA crossover detected against %s on %s. Waiting for same-direction crossover before 3x.",
                    position.side,
                    position.symbol,
                )
                self._emit(
                    "reinforcement_alert",
                    "Opposite EMA crossover detected; waiting return crossover in entry direction.",
                    payload={
                        "symbol": position.symbol,
                        "position_side": position.side,
                        "trend_now": market_trend.value,
                        "crossover": crossover.value,
                        "entry_side": base_trend.value,
                    },
                    severity="warning",
                )
            state.reinforcement_alert = True
            return market_trend

        if state.reinforcement_alert and not state.reinforcement_done and (crossover == base_trend or sequence_ready):
            self._emit(
                "reinforcement_crossover_confirmed",
                "Entry-direction EMA crossover confirmed; executing 3x reinforcement.",
                payload={
                    "symbol": position.symbol,
                    "position_side": position.side,
                    "crossover": crossover.value if crossover else None,
                    "latest_crossover": trend_signal.latest_crossover.value if trend_signal.latest_crossover else None,
                    "previous_crossover": trend_signal.previous_crossover.value if trend_signal.previous_crossover else None,
                    "entry_side": base_trend.value,
                },
                severity="warning",
            )
            self._handle_reinforcement(position.symbol, base_trend, state)
            return market_trend

        if state.reinforcement_done:
            close_reference_price = position.mark_price if position.mark_price > 0 else position.entry_price
            close_notional = position.contracts * close_reference_price
            estimated_close_fee_usdt = self._estimate_taker_fee_usdt(close_notional)
            estimated_open_fees_usdt = state.estimated_open_fees_usdt
            if estimated_open_fees_usdt <= 0:
                # Fallback for positions opened before fee tracking existed.
                estimated_open_fees_usdt = self._estimate_taker_fee_usdt(close_notional)
            estimated_total_fees_usdt = estimated_open_fees_usdt + estimated_close_fee_usdt
            estimated_net_after_fees_usdt = position.unrealized_pnl - estimated_total_fees_usdt

            if estimated_net_after_fees_usdt < 0:
                now_bucket = int(time.time()) // self._timeframe_to_seconds(self.config.timeframe)
                if state.reinforcement_exit_bucket != now_bucket:
                    self._emit(
                        "reinforcement_wait_fee_recovery",
                        "Reinforced position is still negative after estimated fees; waiting before close.",
                        payload={
                            "symbol": position.symbol,
                            "side": position.side,
                            "roi_pct": roi,
                            "unrealized_pnl_usdt": position.unrealized_pnl,
                            "estimated_open_fees_usdt": estimated_open_fees_usdt,
                            "estimated_close_fee_usdt": estimated_close_fee_usdt,
                            "estimated_net_after_fees_usdt": estimated_net_after_fees_usdt,
                        },
                        severity="warning",
                    )
                    state.reinforcement_exit_bucket = now_bucket
                return market_trend

            state.reinforcement_exit_bucket = None
            self.exchange.close_position(position)
            try:
                rebalance_80_20(self.exchange, self.config)
            except Exception as exc:
                LOG.warning("Rebalance after 3x recovery failed on %s: %s", position.symbol, exc)
                self._emit(
                    "cash_rebalance_failed",
                    "Cash rebalance failed after 3x recovery close.",
                    payload={"symbol": position.symbol, "error": str(exc)},
                    severity="error",
                )
            capital_after = self._capital_snapshot()
            self._emit(
                "reinforcement_recovered_close",
                "3x reinforced position recovered to break-even and was closed.",
                payload={
                    "symbol": position.symbol,
                    "side": position.side,
                    "roi_pct": roi,
                    "estimated_realized_pnl_usdt": position.unrealized_pnl,
                    "estimated_total_fees_usdt": estimated_total_fees_usdt,
                    "estimated_net_after_fees_usdt": estimated_net_after_fees_usdt,
                    "position_margin_usdt": position.initial_margin,
                    "close_reason": "reinforcement_break_even_recovered",
                    **capital_after,
                },
            )
            self._emit(
                "cash_rebalance",
                "Cash rebalance executed after 3x recovery close.",
                payload={
                    **capital_after,
                },
            )
            self.position_states.pop(position.symbol, None)
            LOG.info("Reinforced position recovered above estimated fee-adjusted break-even. Position closed.")
            return market_trend
        return market_trend

    def _fill_open_slots(self, open_symbols: set[str]) -> bool:
        opened_any = False
        available_slots = self.config.max_positions - len(open_symbols)
        if available_slots <= 0:
            return opened_any
        for _ in range(available_slots):
            opened = self._open_new_position(open_symbols)
            if not opened:
                break
            opened_any = True
        return opened_any

    def _manage_open_positions(self) -> None:
        positions = self.exchange.fetch_open_positions(self.config.symbols)
        open_symbols = {position.symbol for position in positions}
        self._drop_closed_states(open_symbols)

        if len(open_symbols) < self.config.max_positions:
            opened_any = self._fill_open_slots(open_symbols)
            if opened_any:
                positions = self.exchange.fetch_open_positions(self.config.symbols)
                open_symbols = {position.symbol for position in positions}
                self._drop_closed_states(open_symbols)

        if not positions:
            self._sync_state("waiting_entry", capital=self._capital_snapshot())
            return

        trends: dict[str, Trend] = {}
        for position in positions:
            try:
                trend = self._manage_single_position(position)
                if trend is not None:
                    trends[position.symbol] = trend
            except Exception as exc:
                LOG.exception("Position management error on %s", position.symbol)
                self._emit(
                    "position_management_error",
                    "Position management failed for one symbol but cycle continues.",
                    payload={"symbol": position.symbol, "error": str(exc)},
                    severity="error",
                )
                continue

        refreshed_positions = self.exchange.fetch_open_positions(self.config.symbols)
        refreshed_symbols = {position.symbol for position in refreshed_positions}
        self._drop_closed_states(refreshed_symbols)
        capital = self._capital_snapshot()
        if refreshed_positions:
            self._sync_state("positions_active", positions=refreshed_positions, trends=trends, capital=capital)
        else:
            self._sync_state("no_open_position", capital=capital)

    def run_forever(self) -> None:
        LOG.info(
            "Starting LAPS bot with symbols=%s timeframe=%s max_positions=%s",
            self.config.symbols,
            self.config.timeframe,
            self.config.max_positions,
        )
        self._sync_state("running", capital=self._capital_snapshot())
        self._emit(
            "bot_started",
            "LAPS bot started.",
            payload={
                "symbols": list(self.config.symbols),
                "timeframe": self.config.timeframe,
                "risk_pct": self.config.balance_risk_pct,
                "target_roi_pct": self.config.target_roi_pct,
                "leverage": self.config.leverage,
                "margin_ratio_trigger_pct": self.config.margin_ratio_trigger_pct,
                "max_positions": self.config.max_positions,
            },
        )
        while True:
            try:
                self._manage_open_positions()
            except Exception as exc:
                LOG.exception("Fatal cycle error.")
                self._emit("cycle_error", f"Fatal cycle error: {exc}", severity="error")
                self._sync_state("error", capital=self._capital_snapshot())
            time.sleep(self.config.poll_seconds)
