from __future__ import annotations

import unittest

from backend.laps_hybrid.risk_survival import (
    ExchangeRisk,
    InvestorDNA,
    InvestorProfile,
    MarketRisk,
    PortfolioRisk,
    PositionRisk,
    RiskSurvivalEngine,
    RiskTelemetry,
    SafeMode,
    StrategyRisk,
    SystemRisk,
    WatchdogHeartbeat,
    WatchdogService,
)


def base_telemetry() -> RiskTelemetry:
    return RiskTelemetry(
        investor_dna=InvestorDNA.from_profile(InvestorProfile.BALANCED),
        portfolio=PortfolioRisk(
            equity=100_000.0,
            total_exposure=80_000.0,
            total_leverage=1.2,
            drawdown=0.01,
            drawdown_velocity=0.002,
            open_trade_count=2,
        ),
        market=MarketRisk(
            regime="trend",
            volatility=0.04,
            volatility_shock=0.01,
            spread_bps=5.0,
            depth_score=0.85,
            liquidity_score=0.9,
            btc_dominance_change=0.005,
            liquidation_intensity=0.08,
        ),
        exchange=ExchangeRisk(
            api_error_rate=0.01,
            websocket_staleness_ms=250,
            websocket_disconnects=0,
            order_rejection_rate=0.01,
            execution_latency_ms=120,
            execution_mismatch=False,
            exchange_desync=False,
        ),
        system=SystemRisk(
            heartbeat_age_ms=300,
            queue_backlog=20,
            redis_available=True,
            postgres_available=True,
        ),
        positions=(
            PositionRisk(
                symbol="ETH/USDT",
                notional=30_000.0,
                leverage=1.0,
                unrealized_pnl=500.0,
                liquidation_distance=0.45,
                beta_to_btc=0.75,
                sector="layer1",
            ),
        ),
        strategies=(
            StrategyRisk(
                strategy_name="trend-following",
                drawdown=0.02,
                consecutive_losses=1,
                win_rate=0.58,
                confidence_decay=0.05,
                slippage_bps=4.0,
            ),
        ),
    )


class RiskSurvivalEngineTest(unittest.TestCase):
    def test_normal_conditions_keep_controlled_budget(self) -> None:
        decision = RiskSurvivalEngine().assess(base_telemetry())

        self.assertEqual(decision.budget.safe_mode, SafeMode.NORMAL)
        self.assertGreater(decision.budget.leverage_multiplier, 0.4)
        self.assertIn("open", decision.budget.allowed_actions)
        self.assertFalse(decision.hedge.required)

    def test_exchange_desync_forces_lockdown(self) -> None:
        telemetry = base_telemetry()
        telemetry = RiskTelemetry(
            investor_dna=telemetry.investor_dna,
            portfolio=telemetry.portfolio,
            market=telemetry.market,
            exchange=ExchangeRisk(
                api_error_rate=telemetry.exchange.api_error_rate,
                websocket_staleness_ms=telemetry.exchange.websocket_staleness_ms,
                websocket_disconnects=telemetry.exchange.websocket_disconnects,
                order_rejection_rate=telemetry.exchange.order_rejection_rate,
                execution_latency_ms=telemetry.exchange.execution_latency_ms,
                execution_mismatch=True,
                exchange_desync=True,
            ),
            system=telemetry.system,
            positions=telemetry.positions,
            strategies=telemetry.strategies,
        )

        decision = RiskSurvivalEngine().assess(telemetry)

        self.assertEqual(decision.budget.safe_mode, SafeMode.LOCKDOWN)
        self.assertEqual(decision.budget.leverage_multiplier, 0.0)
        self.assertNotIn("open", decision.budget.allowed_actions)
        self.assertTrue(any(event.name == "execution_desync" for event in decision.breakers))

    def test_systemic_btc_risk_recommends_hedge(self) -> None:
        telemetry = base_telemetry()
        telemetry = RiskTelemetry(
            investor_dna=telemetry.investor_dna,
            portfolio=PortfolioRisk(
                equity=100_000.0,
                total_exposure=240_000.0,
                total_leverage=3.5,
                drawdown=0.045,
                drawdown_velocity=0.04,
                open_trade_count=5,
            ),
            market=MarketRisk(
                regime="chaos",
                volatility=0.14,
                volatility_shock=0.08,
                spread_bps=18.0,
                depth_score=0.45,
                liquidity_score=0.5,
                btc_dominance_change=0.05,
                liquidation_intensity=0.75,
            ),
            exchange=telemetry.exchange,
            system=telemetry.system,
            positions=(
                PositionRisk(
                    symbol="SOL/USDT",
                    notional=90_000.0,
                    leverage=2.0,
                    unrealized_pnl=-3_000.0,
                    liquidation_distance=0.25,
                    beta_to_btc=0.85,
                    sector="layer1",
                ),
                PositionRisk(
                    symbol="AVAX/USDT",
                    notional=70_000.0,
                    leverage=2.0,
                    unrealized_pnl=-2_500.0,
                    liquidation_distance=0.28,
                    beta_to_btc=0.8,
                    sector="layer1",
                ),
            ),
            strategies=telemetry.strategies,
        )

        decision = RiskSurvivalEngine().assess(telemetry)

        self.assertIn(decision.budget.safe_mode, {SafeMode.DEFENSIVE, SafeMode.SURVIVAL})
        self.assertTrue(decision.hedge.required)
        self.assertEqual(decision.hedge.symbol, "BTC/USDT")
        self.assertGreater(decision.hedge.notional, 0.0)
        self.assertLess(decision.budget.position_size_multiplier, 0.3)

    def test_watchdog_escalates_stale_critical_service(self) -> None:
        decision = WatchdogService().evaluate(
            (
                WatchdogHeartbeat(
                    service_name="execution-worker",
                    last_seen_ms=20_000,
                ),
            )
        )

        self.assertFalse(decision.healthy)
        self.assertEqual(decision.target_mode, SafeMode.LOCKDOWN)
        self.assertIn("restart:execution-worker", decision.actions)


if __name__ == "__main__":
    unittest.main()

