"""Contracts for the LAPS HYBRID Copy Trading & Investor Ecosystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class InvestorProfile(StrEnum):
    """Investor DNA profile."""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class InvestorStatus(StrEnum):
    """Investor lifecycle status."""

    REGISTERED = "registered"
    FUNDED = "funded"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class CopyOrderStatus(StrEnum):
    """Copy order lifecycle state."""

    CREATED = "created"
    SKIPPED = "skipped"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    FAILED = "failed"
    DESYNC = "desync"


class TradeSide(StrEnum):
    """Trade direction."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class WalletTransactionType(StrEnum):
    """Append-only investor wallet transaction types."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    TRADING_FEE = "trading_fee"
    PLATFORM_FEE = "platform_fee"
    PERFORMANCE_FEE = "performance_fee"
    PROFIT_DISTRIBUTION = "profit_distribution"
    AFFILIATE_COMMISSION = "affiliate_commission"
    COMMISSION_PAYOUT = "commission_payout"
    REVERSAL = "reversal"


class ReferralStatus(StrEnum):
    """Referral attribution status."""

    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class PayoutStatus(StrEnum):
    """Commission or withdrawal payout state."""

    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    FAILED = "failed"
    REVERSED = "reversed"


class SyncSeverity(StrEnum):
    """Subaccount synchronization issue severity."""

    INFO = "info"
    WARNING = "warning"
    SEVERE = "severe"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class InvestorRiskProfile:
    """Investor-specific risk constraints."""

    profile: InvestorProfile
    leverage_multiplier: float
    exposure_multiplier: float
    max_drawdown: float
    trade_frequency_multiplier: float
    max_simultaneous_trades: int
    allowed_strategy_families: frozenset[str]

    @classmethod
    def from_profile(cls, profile: InvestorProfile) -> "InvestorRiskProfile":
        if profile == InvestorProfile.CONSERVATIVE:
            return cls(
                profile=profile,
                leverage_multiplier=0.4,
                exposure_multiplier=0.45,
                max_drawdown=0.06,
                trade_frequency_multiplier=0.45,
                max_simultaneous_trades=2,
                allowed_strategy_families=frozenset(
                    {"funding_capture", "mean_reversion", "scalping", "hedge_defense"}
                ),
            )
        if profile == InvestorProfile.AGGRESSIVE:
            return cls(
                profile=profile,
                leverage_multiplier=1.0,
                exposure_multiplier=1.0,
                max_drawdown=0.14,
                trade_frequency_multiplier=1.0,
                max_simultaneous_trades=6,
                allowed_strategy_families=frozenset(
                    {
                        "trend_following",
                        "momentum",
                        "breakout",
                        "mean_reversion",
                        "scalping",
                        "funding_capture",
                        "arbitrage",
                        "liquidity_sweep",
                        "session_scalping",
                        "volatility_expansion",
                        "hedge_defense",
                    }
                ),
            )
        return cls(
            profile=profile,
            leverage_multiplier=0.7,
            exposure_multiplier=0.7,
            max_drawdown=0.1,
            trade_frequency_multiplier=0.7,
            max_simultaneous_trades=4,
            allowed_strategy_families=frozenset(
                {
                    "trend_following",
                    "momentum",
                    "breakout",
                    "mean_reversion",
                    "scalping",
                    "funding_capture",
                    "session_scalping",
                    "hedge_defense",
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class InvestorAccount:
    """Investor account and subaccount state used by copy execution."""

    investor_id: str
    subaccount_id: str
    status: InvestorStatus
    equity: float
    available_balance: float
    risk_profile: InvestorRiskProfile
    current_drawdown: float = 0.0
    open_trade_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MasterTrade:
    """Validated master trade event eligible for investor replication."""

    master_trade_id: str
    symbol: str
    side: TradeSide
    notional: float
    quantity: float
    master_equity: float
    strategy_family: str
    leverage: float
    fill_ratio: float = 1.0
    correlation_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def risk_fraction(self) -> float:
        if self.master_equity <= 0:
            return 0.0
        return self.notional / self.master_equity


@dataclass(frozen=True, slots=True)
class ScalingDecision:
    """Investor-specific scaling outcome for a master trade."""

    investor_id: str
    approved: bool
    target_notional: float
    target_quantity: float
    leverage: float
    reason: str
    skipped: bool = False


@dataclass(frozen=True, slots=True)
class CopyOrder:
    """Investor-specific copy order created from a master trade."""

    copy_order_id: str
    master_trade_id: str
    investor_id: str
    subaccount_id: str
    symbol: str
    side: TradeSide
    target_notional: float
    target_quantity: float
    leverage: float
    status: CopyOrderStatus
    correlation_id: str
    reason: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class InvestorPosition:
    """Expected or observed investor subaccount position."""

    investor_id: str
    subaccount_id: str
    symbol: str
    quantity: float
    leverage: float
    side: TradeSide
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class SynchronizationIssue:
    """Subaccount synchronization issue."""

    investor_id: str
    subaccount_id: str
    symbol: str
    severity: SyncSeverity
    issue_type: str
    reason: str
    expected_quantity: float = 0.0
    actual_quantity: float = 0.0


@dataclass(frozen=True, slots=True)
class RevenueRule:
    """Versioned configurable revenue distribution rule."""

    rule_id: str
    platform_fee_rate: float
    performance_fee_rate: float
    affiliate_commission_rate: float
    minimum_payout: float = 0.0
    currency: str = "USDT"
    effective_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ProfitDistribution:
    """Calculated profit distribution components."""

    investor_id: str
    gross_profit: float
    platform_fee: float
    performance_fee: float
    affiliate_commission: float
    investor_net_profit: float
    rule_id: str
    currency: str
    correlation_id: str = field(default_factory=lambda: uuid4().hex)


@dataclass(frozen=True, slots=True)
class ReferralAccount:
    """Referral attribution relationship."""

    referral_id: str
    referrer_investor_id: str
    referred_investor_id: str
    referral_code: str
    status: ReferralStatus = ReferralStatus.ACTIVE
    level: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ReferralCommission:
    """Referral commission accrual or payout."""

    commission_id: str
    referral_id: str
    referrer_investor_id: str
    referred_investor_id: str
    amount: float
    currency: str
    source_distribution_id: str
    status: PayoutStatus = PayoutStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class WalletTransaction:
    """Append-only investor wallet ledger entry."""

    transaction_id: str
    investor_id: str
    transaction_type: WalletTransactionType
    amount: float
    currency: str
    correlation_id: str
    reference_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InvestorDashboardSnapshot:
    """Dashboard-ready investor state."""

    investor_id: str
    balance: float
    equity: float
    open_positions: tuple[InvestorPosition, ...]
    realized_pnl: float
    unrealized_pnl: float
    risk_status: str
    market_regime: str
    active_strategies: tuple[str, ...]
    ai_confidence_state: float
    performance_history: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class InvestorAuditEvent:
    """Immutable investor audit event."""

    event_id: str
    actor_id: str
    actor_type: str
    investor_id: str
    action: str
    resource_type: str
    resource_id: str
    correlation_id: str
    reason: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

