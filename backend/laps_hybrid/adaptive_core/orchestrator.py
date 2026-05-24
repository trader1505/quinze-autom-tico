"""Asynchronous orchestration loop for the Adaptive Core Engine."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Protocol, Sequence, runtime_checkable

from .confidence import ConfidenceEngine
from .execution import ExecutionGateway, NoopExecutionGateway
from .models import (
    ConfidenceBreakdown,
    EngineState,
    ExecutionIntent,
    MarketSnapshot,
    OperationalMode,
    PositionSnapshot,
    RegimeAssessment,
    RiskDecision,
    RiskDecisionType,
    SignalSide,
    StrategyEvaluation,
    StrategyMetrics,
    StrategyMode,
)
from .regime import MarketRegimeEngine
from .risk import RiskEngine
from .shadow import ShadowStrategyLab
from .strategies import Strategy

LOGGER = logging.getLogger(__name__)


@runtime_checkable
class MarketDataProvider(Protocol):
    """Provider for normalized exchange websocket or cached market state."""

    async def latest_snapshot(self) -> MarketSnapshot:
        """Return the latest market snapshot."""


@runtime_checkable
class PortfolioProvider(Protocol):
    """Provider for current portfolio state."""

    async def latest_positions(self) -> tuple[PositionSnapshot, ...]:
        """Return current positions and risk state."""


class AdaptiveCoreEngine:
    """Central asynchronous orchestrator for LAPS HYBRID.

    The engine owns decision sequencing but delegates market data, strategy
    logic, risk policy, and exchange execution to injected services.
    """

    def __init__(
        self,
        market_data: MarketDataProvider,
        portfolio: PortfolioProvider,
        strategies: Sequence[Strategy],
        *,
        regime_engine: MarketRegimeEngine | None = None,
        confidence_engine: ConfidenceEngine | None = None,
        risk_engine: RiskEngine | None = None,
        execution_gateway: ExecutionGateway | None = None,
        shadow_lab: ShadowStrategyLab | None = None,
        tick_interval_seconds: float = 1.0,
        min_execution_score: float = 0.6,
        max_intents_per_tick: int = 3,
    ) -> None:
        self.market_data = market_data
        self.portfolio = portfolio
        self.strategies = tuple(strategies)
        self.regime_engine = regime_engine or MarketRegimeEngine()
        self.confidence_engine = confidence_engine or ConfidenceEngine()
        self.risk_engine = risk_engine or RiskEngine()
        self.execution_gateway = execution_gateway or NoopExecutionGateway()
        self.shadow_lab = shadow_lab or ShadowStrategyLab()
        self.tick_interval_seconds = tick_interval_seconds
        self.min_execution_score = min_execution_score
        self.max_intents_per_tick = max_intents_per_tick
        self.last_state: EngineState | None = None

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        """Run the continuous adaptive orchestration loop."""

        while stop_event is None or not stop_event.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Adaptive core tick failed")

            await asyncio.sleep(self.tick_interval_seconds)

    async def tick(self) -> EngineState:
        """Run one complete decision cycle."""

        snapshot = await self.market_data.latest_snapshot()
        positions = await self.portfolio.latest_positions()
        regime = self.regime_engine.assess(snapshot)

        evaluations = await self._evaluate_strategies(snapshot, regime)
        confidence_scores = {
            evaluation.strategy_name: self.confidence_engine.score(
                evaluation,
                snapshot,
                regime,
            )
            for evaluation in evaluations
        }

        shadow_evaluations = tuple(
            evaluation
            for evaluation in evaluations
            if evaluation.mode == StrategyMode.SHADOW
        )
        for evaluation in shadow_evaluations:
            self.shadow_lab.record(
                evaluation,
                confidence_scores[evaluation.strategy_name],
                snapshot,
            )

        intents = self._build_execution_intents(
            snapshot=snapshot,
            regime=regime,
            evaluations=evaluations,
            confidence_scores=confidence_scores,
        )
        risk_decisions: list[RiskDecision] = []
        executed_intents: list[ExecutionIntent] = []
        operational_mode = regime.operational_mode

        for intent in intents:
            decision = self.risk_engine.evaluate(intent, snapshot, positions)
            risk_decisions.append(decision)

            if decision.decision == RiskDecisionType.SAFE_MODE:
                operational_mode = OperationalMode.SAFE
                continue
            if decision.decision == RiskDecisionType.SHUTDOWN:
                operational_mode = OperationalMode.SHUTDOWN
                continue
            if not decision.executable or decision.intent is None:
                continue

            report = await self.execution_gateway.execute(decision.intent)
            if report.accepted:
                executed_intents.append(decision.intent)
            else:
                LOGGER.warning(
                    "Execution gateway rejected intent %s: %s",
                    decision.intent.idempotency_key,
                    report.reason,
                )

        state = EngineState(
            timestamp=datetime.now(UTC),
            regime=regime,
            evaluations=tuple(evaluations),
            confidence_scores=confidence_scores,
            risk_decisions=tuple(risk_decisions),
            executed_intents=tuple(executed_intents),
            shadow_evaluations=shadow_evaluations,
            operational_mode=operational_mode,
        )
        self.last_state = state
        return state

    async def _evaluate_strategies(
        self,
        snapshot: MarketSnapshot,
        regime: RegimeAssessment,
    ) -> tuple[StrategyEvaluation, ...]:
        tasks = [
            self._evaluate_strategy(strategy, snapshot, regime)
            for strategy in self.strategies
        ]
        return tuple(await asyncio.gather(*tasks))

    async def _evaluate_strategy(
        self,
        strategy: Strategy,
        snapshot: MarketSnapshot,
        regime: RegimeAssessment,
    ) -> StrategyEvaluation:
        if strategy.mode == StrategyMode.DISABLED:
            return self._inactive_evaluation(strategy, "Strategy disabled.")

        if regime.regime not in strategy.allowed_regimes:
            return self._inactive_evaluation(strategy, "Strategy not allowed in regime.")

        try:
            return await strategy.evaluate(snapshot, regime)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.exception("Strategy %s failed during evaluation", strategy.name)
            return self._inactive_evaluation(strategy, f"Strategy error: {exc}")

    def _inactive_evaluation(self, strategy: Strategy, rationale: str) -> StrategyEvaluation:
        return StrategyEvaluation(
            strategy_name=strategy.name,
            strategy_family=strategy.family,
            mode=strategy.mode,
            signal=SignalSide.FLAT,
            raw_confidence=0.0,
            metrics=StrategyMetrics(
                recent_win_rate=0.0,
                drawdown=1.0,
                sharpe_like=-1.0,
                profit_factor=0.0,
                sample_size=0,
            ),
            regime_alignment=0.0,
            suggested_notional=0.0,
            suggested_leverage=0.0,
            rationale=rationale,
        )

    def _build_execution_intents(
        self,
        *,
        snapshot: MarketSnapshot,
        regime: RegimeAssessment,
        evaluations: tuple[StrategyEvaluation, ...],
        confidence_scores: dict[str, ConfidenceBreakdown],
    ) -> tuple[ExecutionIntent, ...]:
        live_candidates = [
            evaluation
            for evaluation in evaluations
            if evaluation.mode == StrategyMode.LIVE
            and evaluation.signal != SignalSide.FLAT
            and evaluation.strategy_family in regime.allowed_strategy_families
            and confidence_scores[evaluation.strategy_name].final_score
            >= self.min_execution_score
        ]
        live_candidates.sort(
            key=lambda item: confidence_scores[item.strategy_name].final_score,
            reverse=True,
        )

        intents: list[ExecutionIntent] = []
        for evaluation in live_candidates[: self.max_intents_per_tick]:
            score = confidence_scores[evaluation.strategy_name].final_score
            intents.append(
                ExecutionIntent(
                    strategy_name=evaluation.strategy_name,
                    symbol=snapshot.symbol,
                    side=evaluation.signal,
                    notional=max(
                        0.0,
                        evaluation.suggested_notional
                        * regime.position_size_multiplier
                        * score,
                    ),
                    leverage=max(
                        0.0,
                        evaluation.suggested_leverage * regime.leverage_multiplier,
                    ),
                    confidence=score,
                    regime=regime.regime,
                    metadata={
                        "raw_confidence": evaluation.raw_confidence,
                        "regime_confidence": regime.confidence,
                        "rationale": evaluation.rationale,
                    },
                )
            )
        return tuple(intents)

