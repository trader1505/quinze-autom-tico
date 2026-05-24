"""Contracts for the LAPS HYBRID AI Intelligence & Learning System."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class MarketSession(StrEnum):
    """Trading sessions used by session intelligence."""

    ASIA = "asia"
    EUROPE = "europe"
    US = "us"
    OVERLAP = "overlap"


class FearState(StrEnum):
    """Internal market fear states."""

    CALM = "calm"
    ELEVATED = "elevated"
    STRESSED = "stressed"
    PANIC = "panic"


class StrategyRecommendation(StrEnum):
    """AI recommendation for strategy participation."""

    INCREASE_PRIORITY = "increase_priority"
    MAINTAIN_PRIORITY = "maintain_priority"
    REDUCE_PRIORITY = "reduce_priority"
    SHADOW_MODE = "shadow_mode"
    DISABLE_TEMPORARILY = "disable_temporarily"


class AggressionState(StrEnum):
    """Operational aggression posture."""

    SUPPRESSED = "suppressed"
    DEFENSIVE = "defensive"
    NORMAL = "normal"
    EXPANDED = "expanded"


class DegradationSeverity(StrEnum):
    """Strategy degradation severity."""

    NONE = "none"
    WATCH = "watch"
    WARNING = "warning"
    SEVERE = "severe"


@dataclass(frozen=True, slots=True)
class MarketFeatures:
    """Normalized AI feature snapshot."""

    symbol: str
    volatility_quality: float
    liquidity_quality: float
    spread_quality: float
    btc_alignment: float
    trend_consistency: float
    market_structure: float
    liquidation_intensity: float
    funding_instability: float
    orderflow_aggression: float
    btc_dominance_shock: float
    session: MarketSession
    regime: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyPerformance:
    """Strategy performance and compatibility metrics."""

    strategy_name: str
    strategy_family: str
    win_rate: float
    drawdown: float
    sharpe_like: float
    profit_factor: float
    consecutive_losses: int
    slippage_bps: float
    historical_performance: float
    recent_behavior: float
    regime_compatibility: float
    volatility_compatibility: float
    session_compatibility: float
    sample_size: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConfidenceScore:
    """Explainable strategy confidence score."""

    strategy_name: str
    final_score: float
    components: dict[str, float]
    min_confidence_threshold: float
    priority_multiplier: float
    rationale: str
    model_version: str = "deterministic-v1"
    score_id: str = field(default_factory=lambda: uuid4().hex)


@dataclass(frozen=True, slots=True)
class StrategyEvaluation:
    """AI strategy quality and recommendation output."""

    strategy_name: str
    quality_score: float
    recommendation: StrategyRecommendation
    degradation_severity: DegradationSeverity
    reason: str


@dataclass(frozen=True, slots=True)
class FearIndex:
    """Internal market fear/stress index."""

    symbol: str
    score: float
    state: FearState
    components: dict[str, float]
    exposure_multiplier: float
    leverage_multiplier: float
    safe_mode_signal: bool
    reason: str


@dataclass(frozen=True, slots=True)
class SessionAssessment:
    """Session intelligence output."""

    session: MarketSession
    expected_volatility: float
    liquidity_expectation: float
    aggressiveness_multiplier: float
    preferred_strategy_families: frozenset[str]
    reason: str


@dataclass(frozen=True, slots=True)
class AggressionDecision:
    """Adaptive operational aggression recommendation."""

    state: AggressionState
    aggression_score: float
    leverage_multiplier: float
    position_size_multiplier: float
    execution_aggressiveness: float
    allowed_strategy_bias: frozenset[str]
    reason: str


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    """Shadow strategy metric sample."""

    strategy_name: str
    symbol: str
    regime: str
    session: MarketSession
    confidence: float
    simulated_pnl: float
    simulated_drawdown: float
    slippage_bps: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class LearningDecision:
    """Persistable AI decision record."""

    decision_type: str
    target: str
    recommendation: str
    confidence: float
    reason: str
    model_version: str = "deterministic-v1"
    decision_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

