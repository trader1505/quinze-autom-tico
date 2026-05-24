"""Referral and affiliate commission support."""

from __future__ import annotations

from uuid import uuid4

from .models import ProfitDistribution, ReferralAccount, ReferralCommission, ReferralStatus


class ReferralEngine:
    """Track referral attribution and recurring commission accruals."""

    def __init__(self) -> None:
        self._referrals_by_referred: dict[str, ReferralAccount] = {}
        self._commissions: list[ReferralCommission] = []

    def register(self, referral: ReferralAccount) -> None:
        """Register immutable referral attribution for an investor."""

        self._referrals_by_referred[referral.referred_investor_id] = referral

    def accrue_commission(
        self,
        distribution: ProfitDistribution,
    ) -> ReferralCommission | None:
        """Accrue a recurring commission from a profit distribution."""

        referral = self._referrals_by_referred.get(distribution.investor_id)
        if referral is None or referral.status != ReferralStatus.ACTIVE:
            return None

        if distribution.affiliate_commission <= 0:
            return None

        commission = ReferralCommission(
            commission_id=uuid4().hex,
            referral_id=referral.referral_id,
            referrer_investor_id=referral.referrer_investor_id,
            referred_investor_id=referral.referred_investor_id,
            amount=distribution.affiliate_commission,
            currency=distribution.currency,
            source_distribution_id=distribution.correlation_id,
        )
        self._commissions.append(commission)
        return commission

    def commissions(self) -> tuple[ReferralCommission, ...]:
        """Return accrued commission history."""

        return tuple(self._commissions)

