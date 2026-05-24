"""Investor subaccount synchronization checks."""

from __future__ import annotations

from .models import InvestorPosition, SyncSeverity, SynchronizationIssue


class SubaccountSynchronizer:
    """Compare expected investor positions with observed exchange positions."""

    def __init__(self, *, quantity_tolerance: float = 1e-8) -> None:
        self.quantity_tolerance = quantity_tolerance

    def compare(
        self,
        expected: tuple[InvestorPosition, ...],
        actual: tuple[InvestorPosition, ...],
    ) -> tuple[SynchronizationIssue, ...]:
        issues: list[SynchronizationIssue] = []
        expected_index = {
            self._key(position): position
            for position in expected
        }
        actual_index = {
            self._key(position): position
            for position in actual
        }

        for key, expected_position in expected_index.items():
            actual_position = actual_index.get(key)
            if actual_position is None:
                issues.append(
                    SynchronizationIssue(
                        investor_id=expected_position.investor_id,
                        subaccount_id=expected_position.subaccount_id,
                        symbol=expected_position.symbol,
                        severity=SyncSeverity.SEVERE,
                        issue_type="missing_subaccount_position",
                        reason="Expected investor position is missing at exchange.",
                        expected_quantity=expected_position.quantity,
                        actual_quantity=0.0,
                    )
                )
                continue
            issues.extend(self._compare_position(expected_position, actual_position))

        for key, actual_position in actual_index.items():
            if key not in expected_index:
                issues.append(
                    SynchronizationIssue(
                        investor_id=actual_position.investor_id,
                        subaccount_id=actual_position.subaccount_id,
                        symbol=actual_position.symbol,
                        severity=SyncSeverity.SEVERE,
                        issue_type="ghost_subaccount_position",
                        reason="Exchange has investor position not expected locally.",
                        expected_quantity=0.0,
                        actual_quantity=actual_position.quantity,
                    )
                )

        return tuple(issues)

    def _compare_position(
        self,
        expected: InvestorPosition,
        actual: InvestorPosition,
    ) -> tuple[SynchronizationIssue, ...]:
        issues: list[SynchronizationIssue] = []
        if abs(expected.quantity - actual.quantity) > self.quantity_tolerance:
            issues.append(
                SynchronizationIssue(
                    investor_id=expected.investor_id,
                    subaccount_id=expected.subaccount_id,
                    symbol=expected.symbol,
                    severity=SyncSeverity.SEVERE,
                    issue_type="quantity_mismatch",
                    reason="Investor expected and actual quantities diverge.",
                    expected_quantity=expected.quantity,
                    actual_quantity=actual.quantity,
                )
            )
        if abs(expected.leverage - actual.leverage) > 1e-8:
            issues.append(
                SynchronizationIssue(
                    investor_id=expected.investor_id,
                    subaccount_id=expected.subaccount_id,
                    symbol=expected.symbol,
                    severity=SyncSeverity.WARNING,
                    issue_type="leverage_mismatch",
                    reason="Investor expected and actual leverage diverge.",
                    expected_quantity=expected.leverage,
                    actual_quantity=actual.leverage,
                )
            )
        if expected.side != actual.side:
            issues.append(
                SynchronizationIssue(
                    investor_id=expected.investor_id,
                    subaccount_id=expected.subaccount_id,
                    symbol=expected.symbol,
                    severity=SyncSeverity.SEVERE,
                    issue_type="hedge_side_mismatch",
                    reason="Investor expected and actual hedge sides diverge.",
                    expected_quantity=expected.quantity,
                    actual_quantity=actual.quantity,
                )
            )
        return tuple(issues)

    def _key(self, position: InvestorPosition) -> tuple[str, str, str, str]:
        return (
            position.investor_id,
            position.subaccount_id,
            position.symbol,
            position.side.value,
        )

