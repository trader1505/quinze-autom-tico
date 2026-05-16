"""Main orchestrator for strategy, risk and execution motors."""

from __future__ import annotations

import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone

from .config import BotSettings
from .gateway import Gateway
from .indicators import detect_trend
from .models import BotState, EngineEvent
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

            now_utc = datetime.now(timezone.utc)
            current_bucket = self._current_interval_bucket(now_utc)
            if self.last_strategy_bucket_at != current_bucket:
                signal = detect_trend(
                    closed_closes,
                    self.settings.ema_short_period,
                    self.settings.ema_long_period,
                )
                strategy_result = self.strategy.evaluate(signal, balances, position, self.state)
                self.state = strategy_result.state
                for order in strategy_result.orders:
                    self.gateway.place_order(order)
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
            },
            "events": recent_events,
        }
