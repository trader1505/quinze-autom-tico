from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime

from backend.laps_hybrid.adaptive_core import (
    AdaptiveCoreEngine,
    BaseStrategy,
    MarketRegime,
    MarketSnapshot,
    NoopExecutionGateway,
    PositionSnapshot,
    RegimeAssessment,
    SignalSide,
    StrategyEvaluation,
    StrategyMetrics,
    StrategyMode,
)


class StaticMarketData:
    async def latest_snapshot(self) -> MarketSnapshot:
        return MarketSnapshot(
            symbol="BTC/USDT",
            timestamp=datetime.now(UTC),
            price=100_000.0,
            volatility=0.04,
            volume=6_000_000.0,
            spread_bps=4.0,
            btc_dominance=0.52,
            momentum=0.03,
            funding_rate=0.0001,
            liquidation_intensity=0.05,
        )


class StaticPortfolio:
    async def latest_positions(self) -> tuple[PositionSnapshot, ...]:
        return (
            PositionSnapshot(
                symbol="BTC/USDT",
                net_notional=10_000.0,
                unrealized_pnl=250.0,
                leverage=1.0,
                portfolio_exposure=10_000.0,
                drawdown=0.01,
            ),
        )


class TrendStrategy(BaseStrategy):
    def __init__(self, mode: StrategyMode = StrategyMode.LIVE) -> None:
        super().__init__(
            name=f"trend-{mode.value}",
            family="trend_following",
            mode=mode,
            allowed_regimes=frozenset({MarketRegime.TREND}),
        )

    async def evaluate(
        self,
        snapshot: MarketSnapshot,
        regime: RegimeAssessment,
    ) -> StrategyEvaluation:
        return StrategyEvaluation(
            strategy_name=self.name,
            strategy_family=self.family,
            mode=self.mode,
            signal=SignalSide.LONG,
            raw_confidence=0.82,
            metrics=StrategyMetrics(
                recent_win_rate=0.62,
                drawdown=0.03,
                sharpe_like=1.4,
                profit_factor=1.5,
                sample_size=80,
            ),
            regime_alignment=0.9,
            suggested_notional=50_000.0,
            suggested_leverage=2.0,
            rationale="Momentum and liquidity aligned.",
        )


class AdaptiveCoreEngineTest(unittest.TestCase):
    def test_tick_executes_live_strategy_and_records_shadow_strategy(self) -> None:
        async def scenario() -> None:
            engine = AdaptiveCoreEngine(
                market_data=StaticMarketData(),
                portfolio=StaticPortfolio(),
                strategies=[
                    TrendStrategy(mode=StrategyMode.LIVE),
                    TrendStrategy(mode=StrategyMode.SHADOW),
                ],
                execution_gateway=NoopExecutionGateway(),
            )

            state = await engine.tick()

            self.assertEqual(state.regime.regime, MarketRegime.TREND)
            self.assertEqual(len(state.executed_intents), 1)
            self.assertEqual(len(state.shadow_evaluations), 1)
            self.assertGreaterEqual(
                state.confidence_scores["trend-live"].final_score,
                engine.min_execution_score,
            )
            self.assertEqual(len(engine.shadow_lab.observations()), 1)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()

