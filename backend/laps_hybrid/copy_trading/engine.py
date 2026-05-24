"""Copy execution orchestration."""

from __future__ import annotations

from uuid import uuid4

from .models import (
    CopyOrder,
    CopyOrderStatus,
    InvestorAccount,
    InvestorStatus,
    MasterTrade,
)
from .scaling import ProportionalScalingEngine


class CopyExecutionEngine:
    """Convert validated master trades into investor-specific copy orders."""

    def __init__(self, scaling_engine: ProportionalScalingEngine | None = None) -> None:
        self.scaling_engine = scaling_engine or ProportionalScalingEngine()

    def create_copy_orders(
        self,
        master_trade: MasterTrade,
        investors: tuple[InvestorAccount, ...],
    ) -> tuple[CopyOrder, ...]:
        """Create copy orders or skipped records for every investor."""

        orders: list[CopyOrder] = []
        for investor in investors:
            if investor.status != InvestorStatus.ACTIVE:
                orders.append(
                    self._skipped_order(
                        master_trade,
                        investor,
                        f"Investor status {investor.status.value} is not active.",
                    )
                )
                continue

            decision = self.scaling_engine.scale(master_trade, investor)
            status = CopyOrderStatus.CREATED if decision.approved else CopyOrderStatus.SKIPPED
            orders.append(
                CopyOrder(
                    copy_order_id=uuid4().hex,
                    master_trade_id=master_trade.master_trade_id,
                    investor_id=investor.investor_id,
                    subaccount_id=investor.subaccount_id,
                    symbol=master_trade.symbol,
                    side=master_trade.side,
                    target_notional=decision.target_notional,
                    target_quantity=decision.target_quantity,
                    leverage=decision.leverage,
                    status=status,
                    correlation_id=master_trade.correlation_id,
                    reason=decision.reason,
                )
            )
        return tuple(orders)

    def _skipped_order(
        self,
        master_trade: MasterTrade,
        investor: InvestorAccount,
        reason: str,
    ) -> CopyOrder:
        return CopyOrder(
            copy_order_id=uuid4().hex,
            master_trade_id=master_trade.master_trade_id,
            investor_id=investor.investor_id,
            subaccount_id=investor.subaccount_id,
            symbol=master_trade.symbol,
            side=master_trade.side,
            target_notional=0.0,
            target_quantity=0.0,
            leverage=0.0,
            status=CopyOrderStatus.SKIPPED,
            correlation_id=master_trade.correlation_id,
            reason=reason,
        )

