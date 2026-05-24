from __future__ import annotations

import unittest

from backend.laps_hybrid.ai_intelligence import (
    AIConfidenceEngine,
    AdaptiveAggressionEngine,
    AggressionState,
    DegradationSeverity,
    FearState,
    MarketFearIndexEngine,
    MarketFeatures,
    MarketSession,
    SessionIntelligenceEngine,
    ShadowAILab,
    ShadowObservation,
    StrategyEvaluationEngine,
    StrategyPerformance,
    StrategyRecommendation,
)


def healthy_features() -> MarketFeatures:
    return MarketFeatures(
        symbol="BTC/USDT",
        volatility_quality=0.82,
        liquidity_quality=0.9,
        spread_quality=0.88,
        btc_alignment=0.8,
        trend_consistency=0.86,
        market_structure=0.78,
        liquidation_intensity=0.08,
        funding_instability=0.05,
        orderflow_aggression=0.2,
        btc_dominance_shock=0.04,
        session=MarketSession.US,
        regime="trend",
    )


def healthy_performance() -> StrategyPerformance:
    return StrategyPerformance(
        strategy_name="trend-alpha",
        strategy_family="trend_following",
        win_rate=0.64,
        drawdown=0.03,
        sharpe_like=1.45,
        profit_factor=1.6,
        consecutive_losses=1,
        slippage_bps=4.0,
        historical_performance=0.78,
        recent_behavior=0.72,
        regime_compatibility=0.86,
        volatility_compatibility=0.8,
        session_compatibility=0.82,
        sample_size=80,
    )


class AIIntelligenceTest(unittest.TestCase):
    def test_confidence_score_uses_explainable_components(self) -> None:
        score = AIConfidenceEngine().score(healthy_features(), healthy_performance())

        self.assertGreater(score.final_score, 0.7)
        self.assertIn("volatility_quality", score.components)
        self.assertIn("historical_performance", score.components)
        self.assertGreater(score.priority_multiplier, 1.0)

    def test_strategy_degradation_moves_strategy_to_shadow(self) -> None:
        degraded = StrategyPerformance(
            strategy_name="scalper",
            strategy_family="scalping",
            win_rate=0.4,
            drawdown=0.12,
            sharpe_like=-0.2,
            profit_factor=0.8,
            consecutive_losses=5,
            slippage_bps=36.0,
            historical_performance=0.35,
            recent_behavior=0.3,
            regime_compatibility=0.4,
            volatility_compatibility=0.4,
            session_compatibility=0.35,
            sample_size=50,
        )

        evaluation = StrategyEvaluationEngine().evaluate(degraded)

        self.assertEqual(evaluation.degradation_severity, DegradationSeverity.WARNING)
        self.assertEqual(evaluation.recommendation, StrategyRecommendation.SHADOW_MODE)

    def test_market_fear_index_reduces_exposure_under_stress(self) -> None:
        stressed = MarketFeatures(
            symbol="BTC/USDT",
            volatility_quality=0.15,
            liquidity_quality=0.25,
            spread_quality=0.2,
            btc_alignment=0.3,
            trend_consistency=0.25,
            market_structure=0.25,
            liquidation_intensity=0.9,
            funding_instability=0.8,
            orderflow_aggression=0.85,
            btc_dominance_shock=0.7,
            session=MarketSession.OVERLAP,
            regime="chaos",
        )

        fear = MarketFearIndexEngine().calculate(stressed)

        self.assertIn(fear.state, {FearState.STRESSED, FearState.PANIC})
        self.assertTrue(fear.safe_mode_signal)
        self.assertLess(fear.exposure_multiplier, 0.6)
        self.assertLess(fear.leverage_multiplier, 0.5)

    def test_session_intelligence_biases_asia_to_lower_aggression(self) -> None:
        session = SessionIntelligenceEngine().assess(MarketSession.ASIA)

        self.assertLess(session.aggressiveness_multiplier, 0.7)
        self.assertIn("funding_capture", session.preferred_strategy_families)

    def test_adaptive_aggression_expands_only_in_healthy_low_fear_conditions(self) -> None:
        features = healthy_features()
        performance = healthy_performance()
        confidence = AIConfidenceEngine().score(features, performance)
        strategy_eval = StrategyEvaluationEngine().evaluate(performance)
        fear = MarketFearIndexEngine().calculate(features)
        session = SessionIntelligenceEngine().assess(MarketSession.US)

        decision = AdaptiveAggressionEngine().decide(
            confidence=confidence,
            strategy_evaluation=strategy_eval,
            fear=fear,
            session=session,
        )

        self.assertIn(decision.state, {AggressionState.NORMAL, AggressionState.EXPANDED})
        self.assertGreater(decision.leverage_multiplier, 0.5)

    def test_adaptive_aggression_suppresses_under_panic_fear(self) -> None:
        features = MarketFeatures(
            symbol="BTC/USDT",
            volatility_quality=0.05,
            liquidity_quality=0.1,
            spread_quality=0.1,
            btc_alignment=0.2,
            trend_consistency=0.1,
            market_structure=0.1,
            liquidation_intensity=1.0,
            funding_instability=0.95,
            orderflow_aggression=0.95,
            btc_dominance_shock=0.9,
            session=MarketSession.OVERLAP,
            regime="chaos",
        )
        performance = healthy_performance()
        confidence = AIConfidenceEngine().score(features, performance)
        strategy_eval = StrategyEvaluationEngine().evaluate(performance)
        fear = MarketFearIndexEngine().calculate(features)
        session = SessionIntelligenceEngine().assess(MarketSession.OVERLAP)

        decision = AdaptiveAggressionEngine().decide(
            confidence=confidence,
            strategy_evaluation=strategy_eval,
            fear=fear,
            session=session,
        )

        self.assertEqual(decision.state, AggressionState.SUPPRESSED)
        self.assertLess(decision.position_size_multiplier, 0.2)

    def test_shadow_lab_promotes_only_sufficient_quality_samples(self) -> None:
        lab = ShadowAILab()
        for _ in range(30):
            lab.record(
                ShadowObservation(
                    strategy_name="shadow-alpha",
                    symbol="BTC/USDT",
                    regime="trend",
                    session=MarketSession.US,
                    confidence=0.7,
                    simulated_pnl=12.0,
                    simulated_drawdown=0.03,
                    slippage_bps=5.0,
                )
            )

        self.assertEqual(lab.promotion_candidates(), ("shadow-alpha",))


if __name__ == "__main__":
    unittest.main()

