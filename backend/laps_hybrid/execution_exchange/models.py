"""Contracts for the LAPS HYBRID Execution & Exchange Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class Exchange(StrEnum):
    """Supported and planned futures exchanges."""

    BINANCE_FUTURES = "binance_futures"
    BITGET_FUTURES = "bitget_futures"
    BYBIT = "bybit"
    OKX = "okx"
    KUCOIN_FUTURES = "kucoin_futures"


class OrderType(StrEnum):
    """Normalized order types supported by the execution layer."""

    MARKET = "market"
    LIMIT = "limit"
    POST_ONLY = "post_only"
    REDUCE_ONLY = "reduce_only"
    STOP_MARKET = "stop_market"
    TAKE_PROFIT = "take_profit"


class OrderSide(StrEnum):
    """Order direction."""

    BUY = "buy"
    SELL = "sell"


class PositionSide(StrEnum):
    """Position side for one-way or hedge-mode accounts."""

    LONG = "long"
    SHORT = "short"
    BOTH = "both"


class OrderStatus(StrEnum):
    """Normalized lifecycle status."""

    CREATED = "created"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    STALE = "stale"
    UNKNOWN = "unknown"


class ExecutionPriority(StrEnum):
    """Execution urgency classes."""

    NORMAL = "normal"
    URGENT = "urgent"
    HEDGE = "hedge"
    LIQUIDATION_DEFENSE = "liquidation_defense"


class ExecutionEventType(StrEnum):
    """Event types emitted by execution services."""

    ORDER_CREATED = "order.created"
    ORDER_SUBMITTED = "order.submitted"
    ORDER_ACCEPTED = "order.accepted"
    ORDER_PARTIALLY_FILLED = "order.partially_filled"
    ORDER_FILLED = "order.filled"
    ORDER_REJECTED = "order.rejected"
    ORDER_CANCELED = "order.canceled"
    ORDER_STALE = "order.stale"
    POSITION_UPDATED = "position.updated"
    FUNDING_UPDATED = "funding.updated"
    LIQUIDATION_ALERT = "liquidation.alert"
    RECONCILIATION_ALERT = "reconciliation.alert"
    WEBSOCKET_STALE = "websocket.stale"
    WEBSOCKET_RECOVERED = "websocket.recovered"
    EXECUTION_FAILSAFE_TRIGGERED = "execution.failsafe_triggered"


class ReconciliationSeverity(StrEnum):
    """Severity of local-vs-exchange mismatch."""

    NONE = "none"
    INFO = "info"
    WARNING = "warning"
    SEVERE = "severe"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """Normalized order request sent to an exchange connector."""

    exchange: Exchange
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    client_order_id: str = field(default_factory=lambda: uuid4().hex)
    price: float | None = None
    stop_price: float | None = None
    reduce_only: bool = False
    post_only: bool = False
    priority: ExecutionPriority = ExecutionPriority.NORMAL
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Fill:
    """Normalized fill event."""

    fill_id: str
    price: float
    quantity: float
    fee: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ExchangeOrderUpdate:
    """Normalized exchange order response or websocket update."""

    exchange: Exchange
    symbol: str
    client_order_id: str
    status: OrderStatus
    requested_quantity: float
    filled_quantity: float = 0.0
    exchange_order_id: str | None = None
    average_price: float | None = None
    fills: tuple[Fill, ...] = ()
    latency_ms: int = 0
    reason: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Smart-execution plan containing one or more child orders."""

    parent_client_order_id: str
    child_orders: tuple[OrderRequest, ...]
    expected_slippage_bps: float
    validation_timeout_ms: int
    fallback_action: str
    rationale: str


@dataclass(frozen=True, slots=True)
class MarketDepth:
    """Orderbook and liquidity state used by smart execution."""

    symbol: str
    mid_price: float
    spread_bps: float
    bid_depth: float
    ask_depth: float
    volatility: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def available_depth(self) -> float:
        return min(self.bid_depth, self.ask_depth)


@dataclass(frozen=True, slots=True)
class LocalPosition:
    """Internal expected position state."""

    exchange: Exchange
    symbol: str
    quantity: float
    leverage: float
    side: PositionSide
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ExchangePosition:
    """Position state fetched or streamed from the exchange."""

    exchange: Exchange
    symbol: str
    quantity: float
    leverage: float
    side: PositionSide
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class OrderValidationResult:
    """Result of validating a lifecycle update."""

    valid: bool
    status: OrderStatus
    reason: str
    duplicate_fill_ids: tuple[str, ...] = ()
    accepted_fill_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReconciliationIssue:
    """Detected mismatch between local and exchange position state."""

    symbol: str
    severity: ReconciliationSeverity
    issue_type: str
    reason: str
    local_quantity: float = 0.0
    exchange_quantity: float = 0.0


@dataclass(frozen=True, slots=True)
class WebsocketStreamState:
    """Health state for a public or private exchange stream."""

    exchange: Exchange
    stream_name: str
    connected: bool
    last_message_age_ms: int
    heartbeat_age_ms: int
    reconnect_attempts: int
    latency_ms: int
    sequence_gap_detected: bool = False


@dataclass(frozen=True, slots=True)
class WebsocketHealthDecision:
    """Decision produced by websocket manager health checks."""

    healthy: bool
    reconnect: bool
    stale: bool
    reason: str
    target_action: str


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """Immutable execution event for audit and subscribers."""

    event_type: ExecutionEventType
    exchange: Exchange
    symbol: str
    correlation_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    client_order_id: str | None = None
    exchange_order_id: str | None = None
    severity: ReconciliationSeverity = ReconciliationSeverity.INFO
    latency_ms: int = 0
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExecutionFailsafeDecision:
    """Failsafe decision when execution safety degrades."""

    pause_new_orders: bool
    allow_reduce_only: bool
    require_reconciliation: bool
    cancel_stale_orders: bool
    escalate_safe_mode: bool
    lockdown: bool
    reason: str

