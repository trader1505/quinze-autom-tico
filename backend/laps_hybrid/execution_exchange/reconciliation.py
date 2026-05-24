"""Position reconciliation between local and exchange state."""

from __future__ import annotations

from .models import (
    Exchange,
    ExchangePosition,
    LocalPosition,
    PositionSide,
    ReconciliationIssue,
    ReconciliationSeverity,
)


class PositionReconciler:
    """Compare expected local positions against exchange truth."""

    def __init__(self, *, quantity_tolerance: float = 1e-8) -> None:
        self.quantity_tolerance = quantity_tolerance

    def reconcile(
        self,
        local_positions: tuple[LocalPosition, ...],
        exchange_positions: tuple[ExchangePosition, ...],
    ) -> tuple[ReconciliationIssue, ...]:
        issues: list[ReconciliationIssue] = []
        local_index = {
            self._key(position.exchange, position.symbol, position.side): position
            for position in local_positions
        }
        exchange_index = {
            self._key(position.exchange, position.symbol, position.side): position
            for position in exchange_positions
        }

        for key, local_position in local_index.items():
            exchange_position = exchange_index.get(key)
            if exchange_position is None:
                issues.append(
                    ReconciliationIssue(
                        symbol=local_position.symbol,
                        severity=ReconciliationSeverity.SEVERE,
                        issue_type="missing_exchange_position",
                        reason="Local position exists but exchange position is missing.",
                        local_quantity=local_position.quantity,
                        exchange_quantity=0.0,
                    )
                )
                continue
            issues.extend(self._compare_position(local_position, exchange_position))

        for key, exchange_position in exchange_index.items():
            if key not in local_index:
                issues.append(
                    ReconciliationIssue(
                        symbol=exchange_position.symbol,
                        severity=ReconciliationSeverity.SEVERE,
                        issue_type="ghost_exchange_position",
                        reason="Exchange position exists but local state is missing it.",
                        local_quantity=0.0,
                        exchange_quantity=exchange_position.quantity,
                    )
                )

        return tuple(issues)

    def _compare_position(
        self,
        local_position: LocalPosition,
        exchange_position: ExchangePosition,
    ) -> tuple[ReconciliationIssue, ...]:
        issues: list[ReconciliationIssue] = []
        quantity_delta = abs(local_position.quantity - exchange_position.quantity)
        if quantity_delta > self.quantity_tolerance:
            issues.append(
                ReconciliationIssue(
                    symbol=local_position.symbol,
                    severity=ReconciliationSeverity.SEVERE,
                    issue_type="quantity_mismatch",
                    reason="Local and exchange quantities diverge.",
                    local_quantity=local_position.quantity,
                    exchange_quantity=exchange_position.quantity,
                )
            )

        if abs(local_position.leverage - exchange_position.leverage) > 1e-8:
            issues.append(
                ReconciliationIssue(
                    symbol=local_position.symbol,
                    severity=ReconciliationSeverity.WARNING,
                    issue_type="leverage_mismatch",
                    reason="Local and exchange leverage diverge.",
                    local_quantity=local_position.leverage,
                    exchange_quantity=exchange_position.leverage,
                )
            )

        if local_position.side != exchange_position.side:
            issues.append(
                ReconciliationIssue(
                    symbol=local_position.symbol,
                    severity=ReconciliationSeverity.SEVERE,
                    issue_type="hedge_side_mismatch",
                    reason="Local and exchange hedge sides diverge.",
                    local_quantity=local_position.quantity,
                    exchange_quantity=exchange_position.quantity,
                )
            )

        return tuple(issues)

    def _key(self, exchange: Exchange, symbol: str, side: PositionSide) -> tuple[Exchange, str, PositionSide]:
        return (exchange, symbol, side)

