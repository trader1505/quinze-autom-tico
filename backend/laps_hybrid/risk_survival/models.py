"""Contracts for the LAPS HYBRID Risk & Survival Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class InvestorProfile(StrEnum):
    """Investor DNA profiles."""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class SafeMode(StrEnum):
    """Survival posture enforced by the risk engine."""

    NORMAL = "normal"
    CAUTION = "caution"
    DEFENSIVE = "defensive"
    SURVIVAL = "survival"
    LOCKDOWN = "lockdown"


class RiskLayer(StrEnum):
    """Risk layers evaluated by the survival system."""

    POSITION = "position"
    STRATEGY = "strategy"
    PORTFOLIO = "portfolio"
    EXCHANGE = "exchange"
    SESSION = "session"
    MARKET_REGIME = "market_regime"
    CORRELATION = "correlation"
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    SYSTEMIC_FAILURE = "systemic_failure"


class BreakerSeverity(StrEnum):
    """Circuit breaker severity."""

    INFO = "info"
    WARNING = "warning"
    SEVERE = "severe"
    CRITICAL = "critical"


class FailsafeIncidentType(StrEnum):
    """Operational failure classes."""

    API_FAILURE = "api_failure"
    WEBSOCKET_DISCONNECT = "websocket_disconnect"
    STALE_MARKET_DATA = "stale_market_data"
    EXECUTION_MISMATCH = "execution_mismatch"
    ORDER_REJECTION = "order_rejection"
    DELAYED_EXECUTION = "delayed_execution"
    EXCHANGE_DESYNC = "exchange_desync"


@dataclass(frozen=True, slots=True)
class InvestorDNA:
    """Risk personality that constrains, but never bypasses, global safety."""

    profile: InvestorProfile
    leverage_multiplier: float
    exposure_multiplier: float
    drawdown_tolerance: float
    trade_frequency_multiplier: float
    max_simultaneous_trades: int

    @classmethod
    def from_profile(cls, profile: InvestorProfile) -> "InvestorDNA":
        if profile == InvestorProfile.CONSERVATIVE:
            return cls(
                profile=profile,
                leverage_multiplier=0.45,
                exposure_multiplier=0.45,
                drawdown_tolerance=0.06,
                trade_frequency_multiplier=0.45,
                max_simultaneous_trades=2,
            )
        if profile == InvestorProfile.AGGRESSIVE:
            return cls(
                profile=profile,
                leverage_multiplier=1.0,
                exposure_multiplier=1.0,
                drawdown_tolerance=0.14,
                trade_frequency_multiplier=1.0,
                max_simultaneous_trades=6,
            )
        return cls(
            profile=profile,
            leverage_multiplier=0.7,
            exposure_multiplier=0.7,
            drawdown_tolerance=0.1,
            trade_frequency_multiplier=0.7,
            max_simultaneous_trades=4,
        )


@dataclass(frozen=True, slots=True)
class PositionRisk:
    """Risk telemetry for one open position."""

    symbol: str
    notional: float
    leverage: float
    unrealized_pnl: float
    liquidation_distance: float
    beta_to_btc: float
    sector: str = "general"


@dataclass(frozen=True, slots=True)
class StrategyRisk:
    """Recent health of a strategy."""

    strategy_name: str
    drawdown: float
    consecutive_losses: int
    win_rate: float
    confidence_decay: float
    slippage_bps: float
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class PortfolioRisk:
    """Aggregate account or investor portfolio telemetry."""

    equity: float
    total_exposure: float
    total_leverage: float
    drawdown: float
    drawdown_velocity: float
    open_trade_count: int


@dataclass(frozen=True, slots=True)
class MarketRisk:
    """Current market, volatility, liquidity, and regime stress."""

    regime: str
    volatility: float
    volatility_shock: float
    spread_bps: float
    depth_score: float
    liquidity_score: float
    btc_dominance_change: float
    liquidation_intensity: float


@dataclass(frozen=True, slots=True)
class ExchangeRisk:
    """Exchange API, websocket, and execution-route health."""

    api_error_rate: float
    websocket_staleness_ms: int
    websocket_disconnects: int
    order_rejection_rate: float
    execution_latency_ms: int
    execution_mismatch: bool
    exchange_desync: bool


@dataclass(frozen=True, slots=True)
class SystemRisk:
    """Platform-level process and dependency health."""

    heartbeat_age_ms: int
    queue_backlog: int
    redis_available: bool
    postgres_available: bool
    frozen_processes: int = 0


@dataclass(frozen=True, slots=True)
class RiskTelemetry:
    """Full risk snapshot consumed by the survival engine."""

    investor_dna: InvestorDNA
    portfolio: PortfolioRisk
    market: MarketRisk
    exchange: ExchangeRisk
    system: SystemRisk
    positions: tuple[PositionRisk, ...] = ()
    strategies: tuple[StrategyRisk, ...] = ()
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CircuitBreakerEvent:
    """Deterministic emergency event emitted by breaker evaluation."""

    name: str
    severity: BreakerSeverity
    target_mode: SafeMode
    layer: RiskLayer
    reason: str
    action: str
    trigger_value: float | int | bool
    threshold: float | int | bool


@dataclass(frozen=True, slots=True)
class CorrelationAssessment:
    """Hidden BTC dependency and concentration assessment."""

    btc_equivalent_exposure: float
    hidden_btc_dependency: float
    sector_concentration: float
    correlation_risk_score: float
    recommended_multiplier: float
    dominant_sector: str | None = None


@dataclass(frozen=True, slots=True)
class HedgeRecommendation:
    """BTC defense hedge recommendation."""

    required: bool
    symbol: str
    side: str
    notional: float
    intensity: float
    reason: str


@dataclass(frozen=True, slots=True)
class RiskBudget:
    """Enforceable dynamic constraints exported to execution systems."""

    safe_mode: SafeMode
    risk_score: float
    leverage_multiplier: float
    position_size_multiplier: float
    trade_frequency_multiplier: float
    max_simultaneous_trades: int
    min_confidence: float
    allowed_actions: frozenset[str]
    allowed_strategy_families: frozenset[str]


@dataclass(frozen=True, slots=True)
class SurvivalDecision:
    """Complete output of one risk assessment cycle."""

    budget: RiskBudget
    correlation: CorrelationAssessment
    hedge: HedgeRecommendation
    breakers: tuple[CircuitBreakerEvent, ...]
    reasons: tuple[str, ...]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class FailsafeIncident:
    """Operational incident requiring throttling, safe mode, or lockdown."""

    incident_type: FailsafeIncidentType
    severity: BreakerSeverity
    target_mode: SafeMode
    affected_service: str
    action: str
    reason: str


@dataclass(frozen=True, slots=True)
class WatchdogHeartbeat:
    """Heartbeat from a critical service monitored by the watchdog."""

    service_name: str
    last_seen_ms: int
    queue_backlog: int = 0
    error_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WatchdogDecision:
    """Independent watchdog decision."""

    healthy: bool
    target_mode: SafeMode
    actions: tuple[str, ...]
    reasons: tuple[str, ...]

