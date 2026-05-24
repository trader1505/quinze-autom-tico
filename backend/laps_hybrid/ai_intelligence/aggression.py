"""Adaptive operational aggression recommendations."""

from __future__ import annotations

from .models import (
    AggressionDecision,
    AggressionState,
    ConfidenceScore,
    FearIndex,
    FearState,
    SessionAssessment,
    StrategyEvaluation,
    StrategyRecommendation,
)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class AdaptiveAggressionEngine:
    """Translate AI intelligence into operational behavior recommendations."""

    def decide(
        self,
        *,
        confidence: ConfidenceScore,
        strategy_evaluation: StrategyEvaluation,
        fear: FearIndex,
        session: SessionAssessment,
    ) -> AggressionDecision:
        degradation_penalty = {
            StrategyRecommendation.INCREASE_PRIORITY: 0.0,
            StrategyRecommendation.MAINTAIN_PRIORITY: 0.05,
            StrategyRecommendation.REDUCE_PRIORITY: 0.25,
            StrategyRecommendation.SHADOW_MODE: 0.45,
            StrategyRecommendation.DISABLE_TEMPORARILY: 0.75,
        }[strategy_evaluation.recommendation]
        fear_penalty = fear.score * 0.55
        aggression_score = _clamp(
            confidence.final_score * 0.45
            + strategy_evaluation.quality_score * 0.3
            + session.aggressiveness_multiplier * 0.25
            - fear_penalty
            - degradation_penalty
        )
        state = self._state(aggression_score, fear)
        mode_multiplier = {
            AggressionState.SUPPRESSED: 0.1,
            AggressionState.DEFENSIVE: 0.35,
            AggressionState.NORMAL: 0.7,
            AggressionState.EXPANDED: 1.0,
        }[state]

        return AggressionDecision(
            state=state,
            aggression_score=aggression_score,
            leverage_multiplier=_clamp(mode_multiplier * fear.leverage_multiplier),
            position_size_multiplier=_clamp(mode_multiplier * fear.exposure_multiplier),
            execution_aggressiveness=_clamp(mode_multiplier * session.aggressiveness_multiplier),
            allowed_strategy_bias=session.preferred_strategy_families,
            reason=(
                f"Aggression {state.value} from confidence={confidence.final_score:.3f}, "
                f"strategy_quality={strategy_evaluation.quality_score:.3f}, "
                f"fear={fear.score:.3f}."
            ),
        )

    def _state(self, aggression_score: float, fear: FearIndex) -> AggressionState:
        if fear.state == FearState.PANIC or aggression_score < 0.22:
            return AggressionState.SUPPRESSED
        if fear.state == FearState.STRESSED or aggression_score < 0.45:
            return AggressionState.DEFENSIVE
        if aggression_score >= 0.72 and fear.state == FearState.CALM:
            return AggressionState.EXPANDED
        return AggressionState.NORMAL

