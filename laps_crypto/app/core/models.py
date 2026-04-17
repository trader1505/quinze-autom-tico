"""Typed domain models for LAPS Crypto."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

    @property
    def opposite(self) -> "Side":
        return Side.SHORT if self == Side.LONG else Side.LONG


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class EngineState(str, Enum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    OPENING = "OPENING"
    MANAGING = "MANAGING"
    HEDGING = "HEDGING"
    RECOVERY = "RECOVERY"
    PAUSED = "PAUSED"


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: Side
    strength: Decimal
    reason_en: str


@dataclass
class Position:
    symbol: str
    side: Side
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    entry_fee_rate_pct: Decimal
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: PositionStatus = PositionStatus.OPEN

    @property
    def entry_notional(self) -> Decimal:
        return self.quantity * self.entry_price

    @property
    def mark_notional(self) -> Decimal:
        return self.quantity * self.mark_price

    @property
    def gross_pnl(self) -> Decimal:
        if self.side == Side.LONG:
            return (self.mark_price - self.entry_price) * self.quantity
        return (self.entry_price - self.mark_price) * self.quantity


@dataclass(frozen=True)
class PriceEstimate:
    mark_price: Decimal
    exit_fee_rate_pct: Decimal
    slippage_rate_pct: Decimal


@dataclass(frozen=True)
class ProfitabilityBreakdown:
    gross_pnl: Decimal
    entry_fee: Decimal
    exit_fee: Decimal
    funding_cost: Decimal
    slippage_cost: Decimal
    net_pnl: Decimal
    net_profit_pct: Decimal

    @property
    def total_cost(self) -> Decimal:
        return self.entry_fee + self.exit_fee + self.funding_cost + self.slippage_cost


@dataclass(frozen=True)
class CloseDecision:
    allowed: bool
    reason_pt_br: str
    breakdown: ProfitabilityBreakdown
    min_required_pct: Decimal


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    quantity: Decimal
    reduce_only: bool = False


@dataclass(frozen=True)
class OrderResult:
    accepted: bool
    message_pt_br: str
    executed_price: Decimal | None = None
    close_decision: CloseDecision | None = None


@dataclass(frozen=True)
class AccountSnapshot:
    equity: Decimal
    free_collateral: Decimal
    used_collateral: Decimal


@dataclass(frozen=True)
class PortfolioSnapshot:
    equity: Decimal
    total_exposure_notional: Decimal


@dataclass(frozen=True)
class HedgePlan:
    required: bool
    side: Side | None
    quantity: Decimal
    reason_pt_br: str
