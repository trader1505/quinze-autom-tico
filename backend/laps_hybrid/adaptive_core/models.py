"""Shared contracts for the Adaptive Core Engine.

These models intentionally avoid exchange-specific fields. Native websocket,
CCXT, PostgreSQL, Redis, and FastAPI adapters should translate their own data
into these contracts before interacting with the core engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class MarketRegime(StrEnum):
    """Operational market personalities supported by LAPS HYBRID."""

    TREND = "trend"
    RANGE = "range"
    CHAOS = "chaos"
    DEAD = "dead"


class OperationalMode(StrEnum):
    """Engine-level operating posture."""

    NORMAL = "normal"
    AGGRESSIVE = "aggressive"
    DEFENSIVE = "defensive"
    SAFE = "safe"
    SHUTDOWN = "shutdown"


class StrategyMode(StrEnum):
    """Whether a strategy can place capital at risk."""

    LIVE = "live"
    SHADOW = "shadow"
    DISABLED = "disabled"


class SignalSide(StrEnum):
    """Strategy signal direction."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"
    HEDGE = "hedge"


class RiskDecisionType(StrEnum):
    """Possible risk outcomes for an execution intent."""

    APPROVED = "approved"
    REDUCED = "reduced"
    DENIED = "denied"
    SAFE_MODE = "safe_mode"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Normalized market condition snapshot for one decision tick."""

    symbol: str
    timestamp: datetime
    price: float
    volatility: float
    volume: float
    spread_bps: float
    btc_dominance: float
    momentum: float
    funding_rate: float
    liquidation_intensity: float
    open_interest: float = 0.0
    exchange_health: float = 1.0
    data_freshness_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RegimeAssessment:
    """Market regime classification and operating modifiers."""

    regime: MarketRegime
    confidence: float
    operational_mode: OperationalMode
    leverage_multiplier: float
    aggressiveness_multiplier: float
    trade_frequency_multiplier: float
    position_size_multiplier: float
    allowed_strategy_families: frozenset[str]
    explanation: str


@dataclass(frozen=True, slots=True)
class StrategyMetrics:
    """Recent strategy quality metrics used by competition and scoring."""

    recent_win_rate: float
    drawdown: float
    sharpe_like: float
    profit_factor: float = 1.0
    sample_size: int = 0


@dataclass(frozen=True, slots=True)
class StrategyEvaluation:
    """Output of a strategy evaluation for a single market snapshot."""

    strategy_name: str
    strategy_family: str
    mode: StrategyMode
    signal: SignalSide
    raw_confidence: float
    metrics: StrategyMetrics
    regime_alignment: float
    suggested_notional: float
    suggested_leverage: float
    rationale: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfidenceBreakdown:
    """Auditable confidence score components."""

    market_alignment: float
    volatility_quality: float
    liquidity_quality: float
    btc_correlation_quality: float
    spread_quality: float
    strategy_performance: float
    recent_behavior: float
    final_score: float


@dataclass(frozen=True, slots=True)
class ExecutionIntent:
    """Capital-at-risk request produced after strategy competition."""

    strategy_name: str
    symbol: str
    side: SignalSide
    notional: float
    leverage: float
    confidence: float
    regime: MarketRegime
    idempotency_key: str = field(default_factory=lambda: uuid4().hex)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """Current portfolio state needed for risk decisions."""

    symbol: str
    net_notional: float
    unrealized_pnl: float
    leverage: float
    portfolio_exposure: float
    drawdown: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """Risk engine response for a proposed execution intent."""

    decision: RiskDecisionType
    reason: str
    intent: ExecutionIntent | None = None
    approved_notional: float = 0.0
    approved_leverage: float = 0.0

    @property
    def executable(self) -> bool:
        """Return whether the decision permits an exchange order."""

        return self.decision in {
            RiskDecisionType.APPROVED,
            RiskDecisionType.REDUCED,
        } and self.intent is not None


@dataclass(frozen=True, slots=True)
class EngineState:
    """State snapshot published to APIs, websockets, and audit logs."""

    timestamp: datetime
    regime: RegimeAssessment
    evaluations: tuple[StrategyEvaluation, ...]
    confidence_scores: dict[str, ConfidenceBreakdown]
    risk_decisions: tuple[RiskDecision, ...]
    executed_intents: tuple[ExecutionIntent, ...]
    shadow_evaluations: tuple[StrategyEvaluation, ...]
    operational_mode: OperationalMode

