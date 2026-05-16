"""Core domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"

    @property
    def opposite(self) -> "Side":
        if self == Side.LONG:
            return Side.SHORT
        if self == Side.SHORT:
            return Side.LONG
        return Side.FLAT


@dataclass(slots=True)
class BalanceSnapshot:
    spot_usdt: float
    futures_wallet_usdt: float
    futures_free_usdt: float
    margin_ratio: float

    @property
    def total_equity_usdt(self) -> float:
        return self.spot_usdt + self.futures_wallet_usdt


@dataclass(slots=True)
class Position:
    side: Side = Side.FLAT
    quantity: float = 0.0
    entry_price: float = 0.0
    mark_price: float = 0.0

    @property
    def notional(self) -> float:
        return abs(self.quantity * self.mark_price)

    @property
    def roi(self) -> float:
        if self.side == Side.FLAT or self.entry_price <= 0:
            return 0.0
        delta = (self.mark_price - self.entry_price) / self.entry_price
        if self.side == Side.SHORT:
            delta *= -1
        return delta


@dataclass(slots=True)
class TrendSignal:
    side: Side
    ema_short: float
    ema_long: float
    confirmed: bool


@dataclass(slots=True)
class OrderIntent:
    symbol: str
    side: Side
    notional_usdt: float
    reduce_only: bool = False
    slices: int = 1
    reason: str = ""


@dataclass(slots=True)
class TransferIntent:
    from_wallet: str
    to_wallet: str
    amount_usdt: float
    reason: str


@dataclass(slots=True)
class EngineEvent:
    type: str
    message: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, float | str] = field(default_factory=dict)


@dataclass(slots=True)
class BotState:
    last_signal: Side = Side.FLAT
    recovery_anchor_side: Side = Side.FLAT
    recovery_base_notional: float = 0.0
    pending_3x: bool = False
    last_event: EngineEvent | None = None
