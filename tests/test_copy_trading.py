from __future__ import annotations

import unittest

from backend.laps_hybrid.copy_trading import (
    CopyExecutionEngine,
    CopyOrderStatus,
    InvestorAccount,
    InvestorPosition,
    InvestorProfile,
    InvestorRiskProfile,
    InvestorStatus,
    MasterTrade,
    ProportionalScalingEngine,
    ReferralAccount,
    ReferralEngine,
    RevenueDistributionEngine,
    RevenueRule,
    SubaccountSynchronizer,
    SyncSeverity,
    TradeSide,
    WalletLedger,
    WalletTransactionType,
)


def master_trade() -> MasterTrade:
    return MasterTrade(
        master_trade_id="master-1",
        symbol="BTC/USDT",
        side=TradeSide.LONG,
        notional=20_000.0,
        quantity=0.2,
        master_equity=1_000_000.0,
        strategy_family="trend_following",
        leverage=2.0,
    )


def investor(
    investor_id: str = "investor-1",
    profile: InvestorProfile = InvestorProfile.BALANCED,
) -> InvestorAccount:
    return InvestorAccount(
        investor_id=investor_id,
        subaccount_id=f"sub-{investor_id}",
        status=InvestorStatus.ACTIVE,
        equity=50_000.0,
        available_balance=10_000.0,
        risk_profile=InvestorRiskProfile.from_profile(profile),
    )


class CopyTradingTest(unittest.TestCase):
    def test_scaling_uses_master_risk_fraction_and_investor_profile(self) -> None:
        decision = ProportionalScalingEngine().scale(master_trade(), investor())

        self.assertTrue(decision.approved)
        self.assertAlmostEqual(decision.target_notional, 700.0)
        self.assertAlmostEqual(decision.leverage, 1.4)
        self.assertGreater(decision.target_quantity, 0.0)

    def test_conservative_profile_skips_unallowed_strategy(self) -> None:
        decision = ProportionalScalingEngine().scale(
            master_trade(),
            investor(profile=InvestorProfile.CONSERVATIVE),
        )

        self.assertFalse(decision.approved)
        self.assertTrue(decision.skipped)
        self.assertIn("strategy", decision.reason)

    def test_copy_engine_creates_created_and_skipped_orders(self) -> None:
        active = investor("active")
        suspended = InvestorAccount(
            investor_id="suspended",
            subaccount_id="sub-suspended",
            status=InvestorStatus.SUSPENDED,
            equity=50_000.0,
            available_balance=10_000.0,
            risk_profile=InvestorRiskProfile.from_profile(InvestorProfile.BALANCED),
        )

        orders = CopyExecutionEngine().create_copy_orders(master_trade(), (active, suspended))

        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[0].status, CopyOrderStatus.CREATED)
        self.assertEqual(orders[1].status, CopyOrderStatus.SKIPPED)

    def test_revenue_distribution_uses_configurable_rule(self) -> None:
        rule = RevenueRule(
            rule_id="rule-1",
            platform_fee_rate=0.02,
            performance_fee_rate=0.10,
            affiliate_commission_rate=0.05,
        )

        distribution = RevenueDistributionEngine().distribute(
            investor_id="investor-1",
            gross_profit=1_000.0,
            rule=rule,
        )

        self.assertAlmostEqual(distribution.platform_fee, 20.0)
        self.assertAlmostEqual(distribution.performance_fee, 100.0)
        self.assertAlmostEqual(distribution.affiliate_commission, 50.0)
        self.assertAlmostEqual(distribution.investor_net_profit, 830.0)

    def test_referral_commission_accrues_from_distribution(self) -> None:
        referral_engine = ReferralEngine()
        referral_engine.register(
            ReferralAccount(
                referral_id="ref-1",
                referrer_investor_id="referrer",
                referred_investor_id="investor-1",
                referral_code="ABC123",
            )
        )
        distribution = RevenueDistributionEngine().distribute(
            investor_id="investor-1",
            gross_profit=1_000.0,
            rule=RevenueRule(
                rule_id="rule-1",
                platform_fee_rate=0.0,
                performance_fee_rate=0.0,
                affiliate_commission_rate=0.05,
            ),
        )

        commission = referral_engine.accrue_commission(distribution)

        self.assertIsNotNone(commission)
        assert commission is not None
        self.assertEqual(commission.referrer_investor_id, "referrer")
        self.assertAlmostEqual(commission.amount, 50.0)
        self.assertEqual(len(referral_engine.commissions()), 1)

    def test_wallet_ledger_derives_balance_from_append_only_entries(self) -> None:
        ledger = WalletLedger()
        ledger.record(
            investor_id="investor-1",
            transaction_type=WalletTransactionType.DEPOSIT,
            amount=1_000.0,
            currency="USDT",
            correlation_id="corr-1",
        )
        ledger.record(
            investor_id="investor-1",
            transaction_type=WalletTransactionType.WITHDRAWAL,
            amount=-250.0,
            currency="USDT",
            correlation_id="corr-2",
        )

        self.assertAlmostEqual(ledger.balance("investor-1"), 750.0)
        self.assertEqual(len(ledger.transactions("investor-1")), 2)

    def test_subaccount_synchronizer_detects_desync(self) -> None:
        issues = SubaccountSynchronizer().compare(
            expected=(
                InvestorPosition(
                    investor_id="investor-1",
                    subaccount_id="sub-1",
                    symbol="BTC/USDT",
                    quantity=0.1,
                    leverage=2.0,
                    side=TradeSide.LONG,
                ),
            ),
            actual=(
                InvestorPosition(
                    investor_id="investor-1",
                    subaccount_id="sub-1",
                    symbol="BTC/USDT",
                    quantity=0.08,
                    leverage=3.0,
                    side=TradeSide.LONG,
                ),
            ),
        )

        issue_types = {issue.issue_type for issue in issues}
        self.assertIn("quantity_mismatch", issue_types)
        self.assertIn("leverage_mismatch", issue_types)
        self.assertTrue(any(issue.severity == SyncSeverity.SEVERE for issue in issues))


if __name__ == "__main__":
    unittest.main()

