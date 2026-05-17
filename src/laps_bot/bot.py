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
    ACCOUNT_MARGIN_TOPUP_COOLDOWN_SECONDS = 60

    def __init__(self, config: BotConfig) -> None:
        validate_config(config)
        self.config = config
        self.exchange = ExchangeGateway(config)
        self.position_states: dict[str, PositionRuntimeState] = {}
        self.telemetry = TelemetryStore(config.telemetry_dir)
        self._symbol_universe_cache: list[str] = list(config.symbols)
        self._symbol_universe_cached_at: float = 0.0
        self._account_margin_topup_active = False
        self._account_margin_last_topup_ts = 0.0
        self._restore_runtime_state()

    def _restore_runtime_state(self) -> None:
        snapshot = self.telemetry.read_state()
        self._account_margin_topup_active = bool(snapshot.get("account_margin_topup_active", False))
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
        account_margin_ratio_pct = self.exchange.account_margin_ratio_pct()
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
            "account_margin_ratio_pct": account_margin_ratio_pct if account_margin_ratio_pct is not None else 0.0,
        }

    def _estimate_taker_fee_usdt(self, notional_usdt: float) -> float:
        if notional_usdt <= 0:
            return 0.0
        return notional_usdt * self.config.taker_fee_rate

    def _symbol_universe(self) -> list[str]:
        if not self.config.scan_all_symbols:
            return list(self.config.symbols)

        now = time.time()
        if (
            self._symbol_universe_cache
            and now - self._symbol_universe_cached_at < self.config.symbol_universe_refresh_seconds
        ):
            return list(self._symbol_universe_cache)

        try:
            symbols = self.exchange.discover_tradable_symbols(
                limit=self.config.max_scan_symbols,
                preferred_symbols=self.config.symbols,
            )
        except Exception as exc:
            LOG.warning("Failed to refresh symbol universe: %s", exc)
            self._emit(
                "symbol_universe_refresh_failed",
                "Failed to refresh futures symbol universe; using previous cache.",
                payload={"error": str(exc), "cached_symbols": len(self._symbol_universe_cache)},
                severity="warning",
            )
            return list(self._symbol_universe_cache)

        if not symbols:
            return list(self._symbol_universe_cache)

        self._symbol_universe_cache = symbols
        self._symbol_universe_cached_at = now
        self._emit(
            "symbol_universe_refreshed",
            "Tradable futures universe refreshed.",
            payload={
                "scan_all_symbols": self.config.scan_all_symbols,
                "symbols_count": len(symbols),
                "symbols_preview": symbols[:15],
            },
        )
        return list(self._symbol_universe_cache)

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
            "account_margin_ratio_pct": 0.0,
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
                account_margin_topup_active=self._account_margin_topup_active,
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
            account_margin_topup_active=self._account_margin_topup_active,
            open_positions_count=len(positions),
            positions=position_payload,
            **capital,
        )

    def _manage_account_margin_ratio(self, account_margin_ratio_pct: float | None) -> None:
        if not hasattr(self, "_account_margin_topup_active"):
            self._account_margin_topup_active = False
        if not hasattr(self, "_account_margin_last_topup_ts"):
            self._account_margin_last_topup_ts = 0.0
        if account_margin_ratio_pct is None:
            return

        trigger = self.config.margin_ratio_trigger_pct
        recovery = self.config.margin_ratio_rebalance_pct

        if account_margin_ratio_pct >= trigger:
            self._account_margin_topup_active = True
            now_ts = time.time()
            cooldown_remaining = self.ACCOUNT_MARGIN_TOPUP_COOLDOWN_SECONDS - (
                now_ts - self._account_margin_last_topup_ts
            )
            if cooldown_remaining > 0:
                self._emit(
                    "margin_topped_up_skipped",
                    "Topup skipped because account margin guard cooldown is still active.",
                    payload={
                        "account_margin_ratio_pct": account_margin_ratio_pct,
                        "margin_ratio_trigger_pct": trigger,
                        "cooldown_remaining_seconds": round(cooldown_remaining, 2),
                    },
                    severity="warning",
                )
                return
            spot_free = self.exchange.free_spot_usdt()
            topup_amount = margin_topup_usdt(spot_free, self.config.margin_topup_pct)
            if topup_amount <= 0:
                self._emit(
                    "margin_topped_up_skipped",
                    "Topup skipped because spot free balance is zero.",
                    payload={
                        "account_margin_ratio_pct": account_margin_ratio_pct,
                        "margin_ratio_trigger_pct": trigger,
                        "spot_free_usdt": spot_free,
                    },
                    severity="warning",
                )
                return
            try:
                self.exchange.transfer_usdt(topup_amount, "spot", "future")
            except Exception as exc:
                self._emit(
                    "margin_topup_failed",
                    "Margin topup transfer failed.",
                    payload={
                        "account_margin_ratio_pct": account_margin_ratio_pct,
                        "margin_ratio_trigger_pct": trigger,
                        "topup_amount_usdt": topup_amount,
                        "error": str(exc),
                    },
                    severity="error",
                )
                return
            self._account_margin_last_topup_ts = now_ts
            self._emit(
                "margin_topped_up",
                "Account margin ratio reached trigger; transferred spot to futures.",
                payload={
                    "account_margin_ratio_pct": account_margin_ratio_pct,
                    "margin_ratio_trigger_pct": trigger,
                    "topup_amount_usdt": topup_amount,
                    "margin_topup_pct": self.config.margin_topup_pct,
                },
                severity="warning",
            )
            return

        if self._account_margin_topup_active and account_margin_ratio_pct <= recovery:
            try:
                rebalance_80_20(self.exchange, self.config)
            except Exception as exc:
                self._emit(
                    "cash_rebalance_failed",
                    "Cash rebalance failed after account margin ratio recovery.",
                    payload={
                        "account_margin_ratio_pct": account_margin_ratio_pct,
                        "margin_ratio_rebalance_pct": recovery,
                        "error": str(exc),
                    },
                    severity="error",
                )
                return
            self._account_margin_topup_active = False
            self._account_margin_last_topup_ts = 0.0
            self._emit(
                "cash_rebalance",
                "Cash rebalance executed after account margin ratio recovered.",
                payload={
                    "account_margin_ratio_pct": account_margin_ratio_pct,
                    "margin_ratio_rebalance_pct": recovery,
                },
            )

    def _signal_for_symbol(self, symbol: str, emit_event: bool = True) -> TrendSignal:
        candles_needed = self.config.slow_ma + 50
        closes = self.exchange.fetch_closes(symbol, self.config.timeframe, candles_needed + 1)
        # Ignore current forming candle to avoid premature crossover triggers.
        if len(closes) > candles_needed:
            closes = closes[:-1]
        signal = resolve_trend(closes, self.config)
        if emit_event:
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

    def _open_new_position(self, blocked_symbols: set[str], symbol_universe: list[str]) -> bool:
        available_symbols = [symbol for symbol in symbol_universe if symbol not in blocked_symbols]
        if not available_symbols:
            self._emit(
                "entry_skipped",
                "No symbols available for new slot because all scanned symbols already have positions.",
                severity="warning",
            )
            return False

        free_usdt = self.exchange.free_futures_usdt()
        if self.config.fixed_entry_margin_usdt > 0:
            target_margin_usdt = self.config.fixed_entry_margin_usdt
            entry_mode = "fixed"
        else:
            target_margin_usdt = target_entry_usdt(free_usdt, self.config.balance_risk_pct)
            entry_mode = "risk_pct"
        if target_margin_usdt <= 0:
            self._emit(
                "entry_skipped",
                "Entry skipped because free futures balance is zero.",
                payload={"free_futures_usdt": free_usdt},
                severity="warning",
            )
            return False
        if free_usdt < target_margin_usdt:
            self._emit(
                "entry_skipped",
                "Entry skipped because free futures balance is below configured entry margin.",
                payload={
                    "free_futures_usdt": free_usdt,
                    "target_margin_usdt": target_margin_usdt,
                    "entry_mode": entry_mode,
                },
                severity="warning",
            )
            return False
        self._emit(
            "entry_attempt",
            "Attempting new entry using configured sizing mode.",
            payload={
                "free_futures_usdt": free_usdt,
                "target_margin_usdt": target_margin_usdt,
                "risk_pct": self.config.balance_risk_pct,
                "fixed_entry_margin_usdt": self.config.fixed_entry_margin_usdt,
                "entry_mode": entry_mode,
                "leverage": self.config.leverage,
                "available_symbols_count": len(available_symbols),
                "scan_batch_size": self.config.entry_scan_batch,
            },
        )
        attempt_symbols = available_symbols[: self.config.entry_scan_batch]
        last_error: str | None = None

        for symbol in attempt_symbols:
            try:
                _, amount, price, used_margin = self.exchange.choose_symbol_and_amount_for_exact_margin(
                    [symbol],
                    target_margin_usdt,
                    self.config.leverage,
                )
            except Exception as exc:
                last_error = str(exc)
                continue

            try:
                trend_signal = self._signal_for_symbol(symbol, emit_event=False)
            except Exception as exc:
                last_error = str(exc)
                continue
            trend = trend_signal.trend
            if trend == Trend.FLAT:
                continue

            try:
                self.exchange.create_market_position(symbol, trend, amount, reduce_only=False)
            except Exception as exc:
                last_error = str(exc)
                self._emit(
                    "entry_skipped",
                    "Order rejected on candidate symbol; continuing scan.",
                    payload={
                        "symbol": symbol,
                        "target_margin_usdt": target_margin_usdt,
                        "entry_mode": entry_mode,
                        "error": str(exc),
                    },
                    severity="warning",
                )
                continue
            used_leverage = self.exchange.active_leverage(symbol)
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
                used_leverage,
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
                    "leverage": used_leverage,
                    "entry_mode": entry_mode,
                },
            )
            return True

        payload: dict[str, Any] = {
            "attempted_symbols": len(attempt_symbols),
            "scan_batch_size": self.config.entry_scan_batch,
            "target_margin_usdt": target_margin_usdt,
        }
        if last_error:
            payload["last_error"] = last_error
        self._emit(
            "entry_skipped",
            "Entry skipped after scanning candidate symbols without executable non-flat setup.",
            payload=payload,
            severity="warning",
        )
        return False

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
        used_leverage = self.exchange.active_leverage(symbol)
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
                "leverage": used_leverage,
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

        # Do not arm 3x from historical crossover sequence alone.
        # Otherwise a fresh position may instantly trigger 3x from an old
        # opposite->return pattern that happened before this entry.

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

    def _fill_open_slots(self, open_symbols: set[str], symbol_universe: list[str]) -> bool:
        opened_any = False
        available_slots = self.config.max_positions - len(open_symbols)
        if available_slots <= 0:
            return opened_any
        for _ in range(available_slots):
            opened = self._open_new_position(open_symbols, symbol_universe)
            if not opened:
                break
            opened_any = True
        return opened_any

    def _manage_open_positions(self) -> None:
        symbol_universe = self._symbol_universe()
        account_margin_ratio_pct = self.exchange.account_margin_ratio_pct()
        self._manage_account_margin_ratio(account_margin_ratio_pct)
        positions = self.exchange.fetch_open_positions(symbol_universe)
        open_symbols = {position.symbol for position in positions}
        self._drop_closed_states(open_symbols)

        if len(open_symbols) < self.config.max_positions:
            opened_any = self._fill_open_slots(open_symbols, symbol_universe)
            if opened_any:
                positions = self.exchange.fetch_open_positions(symbol_universe)
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

        refreshed_positions = self.exchange.fetch_open_positions(symbol_universe)
        refreshed_symbols = {position.symbol for position in refreshed_positions}
        self._drop_closed_states(refreshed_symbols)

        if len(refreshed_symbols) < self.config.max_positions:
            opened_after_closes = self._fill_open_slots(refreshed_symbols, symbol_universe)
            if opened_after_closes:
                refreshed_positions = self.exchange.fetch_open_positions(symbol_universe)
                refreshed_symbols = {position.symbol for position in refreshed_positions}
                self._drop_closed_states(refreshed_symbols)

        capital = self._capital_snapshot()
        if refreshed_positions:
            self._sync_state("positions_active", positions=refreshed_positions, trends=trends, capital=capital)
        else:
            self._sync_state("no_open_position", capital=capital)

    def run_forever(self) -> None:
        LOG.info(
            "Starting LAPS bot with symbols=%s timeframe=%s max_positions=%s scan_all=%s max_scan_symbols=%s",
            self.config.symbols,
            self.config.timeframe,
            self.config.max_positions,
            self.config.scan_all_symbols,
            self.config.max_scan_symbols,
        )
        self._sync_state("running", capital=self._capital_snapshot())
        self._emit(
            "bot_started",
            "LAPS bot started.",
            payload={
                "symbols": list(self.config.symbols),
                "scan_all_symbols": self.config.scan_all_symbols,
                "max_scan_symbols": self.config.max_scan_symbols,
                "timeframe": self.config.timeframe,
                "risk_pct": self.config.balance_risk_pct,
                "fixed_entry_margin_usdt": self.config.fixed_entry_margin_usdt,
                "target_roi_pct": self.config.target_roi_pct,
                "leverage": self.config.leverage,
                "use_max_leverage_per_symbol": self.config.use_max_leverage_per_symbol,
                "margin_ratio_trigger_pct": self.config.margin_ratio_trigger_pct,
                "margin_ratio_rebalance_pct": self.config.margin_ratio_rebalance_pct,
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
