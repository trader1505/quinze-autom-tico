"""Main orchestrator for strategy, risk and execution motors."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone

from .config import BotSettings
from .gateway import Gateway
from .indicators import detect_trend
from .models import BotState, EngineEvent, Position, Side
from .risk import RiskEngine
from .strategy import StrategyEngine


class TradingEngine:
    def __init__(self, settings: BotSettings, gateway: Gateway):
        self.settings = settings
        self.gateway = gateway
        self.strategy = StrategyEngine(settings)
        self.risk = RiskEngine(settings)
        self.state = BotState()
        self.events: list[EngineEvent] = []
        self.running = False
        self._loop_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.last_cycle_at: datetime | None = None
        self.last_error: str | None = None
        self.last_strategy_bucket_at: datetime | None = None

    def _interval_seconds(self) -> int:
        interval = self.settings.interval.strip().lower()
        if len(interval) < 2:
            raise ValueError(f"Invalid interval: {self.settings.interval}")
        value = int(interval[:-1])
        unit = interval[-1]
        if value <= 0:
            raise ValueError(f"Invalid interval: {self.settings.interval}")
        if unit == "m":
            return value * 60
        if unit == "h":
            return value * 3600
        if unit == "d":
            return value * 86400
        raise ValueError(f"Unsupported interval unit: {self.settings.interval}")

    def _current_interval_bucket(self, now_utc: datetime) -> datetime:
        seconds = self._interval_seconds()
        bucket_epoch = int(now_utc.timestamp() // seconds * seconds)
        return datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)

    def _append_event(self, event: EngineEvent) -> None:
        with self._lock:
            self.events.append(event)
            self.state.last_event = event
            self.events = self.events[-200:]

    @staticmethod
    def _safe_float(value: object, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _reset_managed_operations(self) -> None:
        self.state.managed_operations = []
        self.state.open_operations = 0
        self.state.next_operation_id = 1

    def _register_synced_operation(self, position: Position) -> None:
        if position.side == Side.FLAT:
            self._reset_managed_operations()
            return
        if self.state.managed_operations:
            return
        notional = max(position.notional, self.settings.min_notional_usdt)
        quantity = position.quantity if position.quantity > 0 else (notional / position.entry_price if position.entry_price > 0 else 0.0)
        self.state.managed_operations.append(
            {
                "id": self.state.next_operation_id,
                "side": position.side.value,
                "entry_price": position.entry_price,
                "quantity": quantity,
                "notional_usdt": notional,
                "reason": "synced_existing_position",
                "opened_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.state.next_operation_id += 1
        self.state.open_operations = len(self.state.managed_operations)

    def _extract_execution_metrics(self, responses: list[dict], fallback_price: float, fallback_notional: float) -> tuple[float, float, float]:
        total_qty = 0.0
        total_quote = 0.0
        avg_prices: list[float] = []
        for response in responses:
            qty = self._safe_float(response.get("executedQty"))
            quote = self._safe_float(response.get("cumQuote"))
            avg_price = self._safe_float(response.get("avgPrice"))
            if qty > 0:
                total_qty += qty
            if quote > 0:
                total_quote += quote
            if avg_price > 0:
                avg_prices.append(avg_price)

        price = fallback_price if fallback_price > 0 else 1.0
        if total_qty > 0 and total_quote > 0:
            price = total_quote / total_qty
        elif avg_prices:
            price = sum(avg_prices) / len(avg_prices)

        notional = total_quote if total_quote > 0 else fallback_notional
        quantity = total_qty if total_qty > 0 else (notional / price if price > 0 else 0.0)
        return price, quantity, notional

    def _register_operation_from_order(self, intent, responses: list[dict], mark_price: float) -> None:
        if intent.reduce_only:
            if intent.reason == "tp_100_roi":
                self._reset_managed_operations()
            return

        if intent.reason not in {"initial_entry", "slot_scale_entry", "recovery_3x"}:
            return

        entry_price, quantity, notional = self._extract_execution_metrics(
            responses=responses,
            fallback_price=mark_price,
            fallback_notional=intent.notional_usdt,
        )
        self.state.managed_operations.append(
            {
                "id": self.state.next_operation_id,
                "side": intent.side.value,
                "entry_price": entry_price,
                "quantity": quantity,
                "notional_usdt": notional,
                "reason": intent.reason,
                "opened_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.state.next_operation_id += 1
        self.state.open_operations = len(self.state.managed_operations)

    def _operation_snapshot(self, mark_price: float) -> list[dict]:
        snapshots: list[dict] = []
        for operation in self.state.managed_operations:
            side_value = str(operation.get("side", "FLAT"))
            entry_price = self._safe_float(operation.get("entry_price"))
            quantity = self._safe_float(operation.get("quantity"))
            notional = self._safe_float(operation.get("notional_usdt"))
            if quantity <= 0 and entry_price > 0 and notional > 0:
                quantity = notional / entry_price

            if side_value == Side.LONG.value:
                pnl_usdt = (mark_price - entry_price) * quantity
                direction_color = "green"
            elif side_value == Side.SHORT.value:
                pnl_usdt = (entry_price - mark_price) * quantity
                direction_color = "red"
            else:
                pnl_usdt = 0.0
                direction_color = "neutral"

            pnl_pct = (pnl_usdt / notional) if notional > 0 else 0.0
            pnl_color = "green" if pnl_usdt > 0 else "red" if pnl_usdt < 0 else "neutral"
            snapshots.append(
                {
                    **operation,
                    "mark_price": mark_price,
                    "pnl_usdt": pnl_usdt,
                    "pnl_pct": pnl_pct,
                    "direction_color": direction_color,
                    "pnl_color": pnl_color,
                }
            )
        return snapshots

    def _pending_operations_snapshot(self, base_notional: float, planned_side: Side) -> list[dict]:
        pending: list[dict] = []
        for slot in range(self.state.open_operations + 1, self.settings.max_concurrent_operations + 1):
            pending.append(
                {
                    "slot": slot,
                    "side": planned_side.value,
                    "estimated_notional_usdt": base_notional,
                    "status": "PENDENTE",
                }
            )
        return pending

    def _sync_state_with_open_position(self, position: Position) -> None:
        if position.side == Side.FLAT:
            if (
                self.state.pending_3x
                or self.state.recovery_anchor_side != Side.FLAT
                or self.state.recovery_base_notional > 0
                or self.state.open_operations > 0
            ):
                self.state.pending_3x = False
                self.state.recovery_anchor_side = Side.FLAT
                self.state.recovery_base_notional = 0.0
                self._reset_managed_operations()
                self._append_event(
                    EngineEvent(
                        type="position_state_reset",
                        message="Posição zerada detectada, estado interno normalizado",
                    )
                )
            return

        open_notional = max(position.notional, self.settings.min_notional_usdt)
        if self.state.recovery_anchor_side == Side.FLAT:
            self.state.recovery_anchor_side = position.side
            self.state.recovery_base_notional = open_notional
            self.state.pending_3x = False
            self._register_synced_operation(position)
            self._append_event(
                EngineEvent(
                    type="position_synced",
                    message="Posição aberta detectada e sincronizada para gerenciamento",
                    payload={
                        "side": position.side.value,
                        "notional": open_notional,
                        "open_operations": self.state.open_operations,
                    },
                )
            )
            return

        if self.state.recovery_anchor_side != position.side and not self.state.pending_3x:
            self.state.recovery_anchor_side = position.side
            self.state.recovery_base_notional = open_notional
            self._reset_managed_operations()
            self._register_synced_operation(position)
            self._append_event(
                EngineEvent(
                    type="position_reanchored",
                    message="Mudança externa de posição detectada, âncora atualizada",
                    payload={
                        "side": position.side.value,
                        "notional": open_notional,
                        "open_operations": self.state.open_operations,
                    },
                )
            )
            return

        if self.state.recovery_base_notional <= 0:
            self.state.recovery_base_notional = open_notional
        if self.state.open_operations <= 0 or not self.state.managed_operations:
            self._register_synced_operation(position)

    def cycle_once(self) -> None:
        try:
            closes = self.gateway.get_recent_closes(
                symbol=self.settings.symbol,
                interval=self.settings.interval,
                limit=max(self.settings.ema_long_period + 5, 60),
            )
            if len(closes) < self.settings.ema_long_period + 2:
                raise ValueError("Not enough candles to process closed-candle strategy")
            closed_closes = closes[:-1]
            balances = self.gateway.get_balances()
            position = self.gateway.get_position(self.settings.symbol)
            position.mark_price = closes[-1]
            self._sync_state_with_open_position(position)

            now_utc = datetime.now(timezone.utc)
            current_bucket = self._current_interval_bucket(now_utc)
            signal = detect_trend(
                closed_closes,
                self.settings.ema_short_period,
                self.settings.ema_long_period,
            )
            strategy_result = self.strategy.evaluate(signal, balances, position, self.state)
            self.state = strategy_result.state
            for order in strategy_result.orders:
                responses = self.gateway.place_order(order)
                self._register_operation_from_order(order, responses, position.mark_price)
            self.state.open_operations = len(self.state.managed_operations)
            for event in strategy_result.events:
                self._append_event(event)
            self.last_strategy_bucket_at = current_bucket

            risk_result = self.risk.evaluate(balances)
            for transfer in risk_result.transfers:
                self.gateway.transfer(transfer)
            for event in risk_result.events:
                self._append_event(event)

            self.last_cycle_at = datetime.now(timezone.utc)
            self.last_error = None
        except Exception as exc:  # pragma: no cover - defensive runtime path
            self.last_error = str(exc)
            self._append_event(
                EngineEvent(
                    type="error",
                    message="Falha no ciclo do motor",
                    payload={"error": str(exc)},
                )
            )

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()

    def stop(self) -> None:
        self.running = False
        if self._loop_thread and self._loop_thread.is_alive():
            self._loop_thread.join(timeout=2)

    def _run_loop(self) -> None:
        while self.running:
            self.cycle_once()
            time.sleep(self.settings.poll_seconds)

    def status(self) -> dict:
        balances = self.gateway.get_balances()
        position = self.gateway.get_position(self.settings.symbol)
        mark_price = position.mark_price if position.mark_price > 0 else position.entry_price
        if mark_price <= 0:
            mark_price = 0.0
        operations = self._operation_snapshot(mark_price=mark_price)
        base_notional = max(
            balances.futures_free_usdt * self.settings.entry_fraction_of_free_futures,
            self.settings.min_notional_usdt,
        )
        planned_side = position.side if position.side != Side.FLAT else self.state.recovery_anchor_side
        pending_operations = self._pending_operations_snapshot(
            base_notional=base_notional,
            planned_side=planned_side,
        )
        with self._lock:
            recent_events = [asdict(event) for event in self.events[-20:]]
        return {
            "running": self.running,
            "symbol": self.settings.symbol,
            "interval": self.settings.interval,
            "dry_run": self.settings.dry_run,
            "last_cycle_at": self.last_cycle_at.isoformat() if self.last_cycle_at else None,
            "last_strategy_bucket_at": self.last_strategy_bucket_at.isoformat() if self.last_strategy_bucket_at else None,
            "last_error": self.last_error,
            "balances": asdict(balances),
            "position": asdict(position),
            "state": {
                "pending_3x": self.state.pending_3x,
                "recovery_anchor_side": self.state.recovery_anchor_side.value,
                "recovery_base_notional": self.state.recovery_base_notional,
                "open_operations": len(self.state.managed_operations),
                "max_concurrent_operations": self.settings.max_concurrent_operations,
            },
            "operations": operations,
            "pending_operations": pending_operations,
            "events": recent_events,
        }
