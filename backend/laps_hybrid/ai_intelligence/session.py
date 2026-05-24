"""Session intelligence for Asia, Europe, US, and overlap windows."""

from __future__ import annotations

from .models import MarketSession, SessionAssessment


class SessionIntelligenceEngine:
    """Return expected behavior and strategy bias by market session."""

    def assess(self, session: MarketSession) -> SessionAssessment:
        if session == MarketSession.ASIA:
            return SessionAssessment(
                session=session,
                expected_volatility=0.45,
                liquidity_expectation=0.45,
                aggressiveness_multiplier=0.55,
                preferred_strategy_families=frozenset(
                    {"mean_reversion", "funding_capture", "scalping"}
                ),
                reason="Asia session often requires lower liquidity assumptions.",
            )
        if session == MarketSession.EUROPE:
            return SessionAssessment(
                session=session,
                expected_volatility=0.65,
                liquidity_expectation=0.7,
                aggressiveness_multiplier=0.75,
                preferred_strategy_families=frozenset(
                    {"breakout", "momentum", "session_scalping", "trend_following"}
                ),
                reason="Europe session supports controlled volatility expansion.",
            )
        if session == MarketSession.US:
            return SessionAssessment(
                session=session,
                expected_volatility=0.8,
                liquidity_expectation=0.85,
                aggressiveness_multiplier=0.8,
                preferred_strategy_families=frozenset(
                    {"trend_following", "momentum", "breakout", "liquidity_sweep"}
                ),
                reason="US session has higher liquidity but news-shock risk.",
            )
        return SessionAssessment(
            session=session,
            expected_volatility=0.9,
            liquidity_expectation=0.8,
            aggressiveness_multiplier=0.7,
            preferred_strategy_families=frozenset(
                {"momentum", "breakout", "volatility_expansion", "hedge_defense"}
            ),
            reason="Overlap windows increase opportunity and instability simultaneously.",
        )

