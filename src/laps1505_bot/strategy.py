"""Trading strategy motor (EMA + 3x recovery + TP)."""

from __future__ import annotations

from dataclasses import dataclass

from .config import BotSettings
from .models import BalanceSnapshot, BotState, EngineEvent, OrderIntent, Position, Side, TrendSignal


@dataclass(slots=True)
class StrategyResult:
    orders: list[OrderIntent]
    state: BotState
    events: list[EngineEvent]


class StrategyEngine:
    def __init__(self, settings: BotSettings):
        self.settings = settings

    def _base_entry_notional(self, balances: BalanceSnapshot) -> float:
        notional = balances.futures_free_usdt * self.settings.entry_fraction_of_free_futures
        return max(notional, self.settings.min_notional_usdt)

    def evaluate(
        self,
        signal: TrendSignal,
        balances: BalanceSnapshot,
        position: Position,
        state: BotState,
    ) -> StrategyResult:
        orders: list[OrderIntent] = []
        events: list[EngineEvent] = []

        # ROI 100% => close all position and realize full trade.
        if position.side != Side.FLAT and position.roi >= self.settings.tp_roi_target:
            orders.append(
                OrderIntent(
                    symbol=self.settings.symbol,
                    side=position.side.opposite,
                    notional_usdt=position.notional,
                    reduce_only=True,
                    slices=self.settings.order_slices,
                    reason="tp_100_roi",
                )
            )
            events.append(
                EngineEvent(
                    type="tp_hit",
                    message="TP atingido em 100% ROI, posição encerrada",
                    payload={"roi": position.roi, "notional": position.notional},
                )
            )
            state.pending_3x = False
            state.recovery_anchor_side = Side.FLAT
            state.recovery_base_notional = 0.0
            return StrategyResult(orders=orders, state=state, events=events)

        # Initial entry when flat and trend is confirmed.
        if position.side == Side.FLAT and signal.confirmed:
            entry_notional = self._base_entry_notional(balances)
            orders.append(
                OrderIntent(
                    symbol=self.settings.symbol,
                    side=signal.side,
                    notional_usdt=entry_notional,
                    reduce_only=False,
                    slices=self.settings.order_slices,
                    reason="initial_entry",
                )
            )
            state.recovery_anchor_side = signal.side
            state.recovery_base_notional = entry_notional
            state.pending_3x = False
            events.append(
                EngineEvent(
                    type="entry",
                    message=f"Entrada inicial {signal.side.value}",
                    payload={"notional": entry_notional},
                )
            )
            return StrategyResult(orders=orders, state=state, events=events)

        if position.side == Side.FLAT:
            return StrategyResult(orders=orders, state=state, events=events)

        # Opposite confirmed trend arms the 3x recovery (no immediate reverse).
        if signal.confirmed and signal.side != position.side:
            should_emit_arm_event = not state.pending_3x or state.recovery_anchor_side != position.side
            state.pending_3x = True
            if state.recovery_base_notional <= 0:
                state.recovery_base_notional = max(position.notional, self.settings.min_notional_usdt)
            state.recovery_anchor_side = position.side
            if should_emit_arm_event:
                events.append(
                    EngineEvent(
                        type="recovery_armed",
                        message="Tendência oposta detectada, aguardando reconfirmação para 3x",
                        payload={"anchor_side": position.side.value, "base_notional": state.recovery_base_notional},
                    )
                )

        # If trend returns to original side, add 3x notional for recovery.
        if signal.confirmed and state.pending_3x and signal.side == state.recovery_anchor_side:
            recovery_notional = state.recovery_base_notional * self.settings.recovery_multiplier
            orders.append(
                OrderIntent(
                    symbol=self.settings.symbol,
                    side=signal.side,
                    notional_usdt=recovery_notional,
                    reduce_only=False,
                    slices=self.settings.order_slices,
                    reason="recovery_3x",
                )
            )
            state.pending_3x = False
            events.append(
                EngineEvent(
                    type="recovery_fired",
                    message="Ordem 3x de recuperação executada",
                    payload={"notional": recovery_notional},
                )
            )

        return StrategyResult(orders=orders, state=state, events=events)
