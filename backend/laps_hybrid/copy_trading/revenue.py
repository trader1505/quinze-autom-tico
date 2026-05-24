"""Configurable revenue distribution."""

from __future__ import annotations

from uuid import uuid4

from .models import ProfitDistribution, RevenueRule


class RevenueDistributionEngine:
    """Calculate platform, performance, affiliate, and investor profit shares."""

    def distribute(
        self,
        *,
        investor_id: str,
        gross_profit: float,
        rule: RevenueRule,
    ) -> ProfitDistribution:
        """Return a distribution using configurable rule rates."""

        if gross_profit <= 0:
            return ProfitDistribution(
                investor_id=investor_id,
                gross_profit=gross_profit,
                platform_fee=0.0,
                performance_fee=0.0,
                affiliate_commission=0.0,
                investor_net_profit=gross_profit,
                rule_id=rule.rule_id,
                currency=rule.currency,
                correlation_id=uuid4().hex,
            )

        platform_fee = gross_profit * rule.platform_fee_rate
        performance_fee = gross_profit * rule.performance_fee_rate
        affiliate_commission = gross_profit * rule.affiliate_commission_rate
        investor_net_profit = gross_profit - platform_fee - performance_fee - affiliate_commission

        return ProfitDistribution(
            investor_id=investor_id,
            gross_profit=gross_profit,
            platform_fee=platform_fee,
            performance_fee=performance_fee,
            affiliate_commission=affiliate_commission,
            investor_net_profit=investor_net_profit,
            rule_id=rule.rule_id,
            currency=rule.currency,
            correlation_id=uuid4().hex,
        )

