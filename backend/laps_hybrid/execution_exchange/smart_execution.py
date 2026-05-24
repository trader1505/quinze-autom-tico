"""Smart execution planner for spread, slippage, and liquidity constraints."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from .models import (
    ExecutionPlan,
    ExecutionPriority,
    MarketDepth,
    OrderRequest,
    OrderType,
)


class SmartExecutionPlanner:
    """Convert approved orders into exchange-safe child order plans."""

    def __init__(
        self,
        *,
        max_spread_bps: float = 25.0,
        max_child_depth_fraction: float = 0.15,
        max_market_slippage_bps: float = 18.0,
    ) -> None:
        self.max_spread_bps = max_spread_bps
        self.max_child_depth_fraction = max_child_depth_fraction
        self.max_market_slippage_bps = max_market_slippage_bps

    def plan(self, request: OrderRequest, depth: MarketDepth) -> ExecutionPlan:
        """Create a smart execution plan for one normalized order request."""

        parent_id = request.client_order_id
        hedge_like = request.priority in {
            ExecutionPriority.HEDGE,
            ExecutionPriority.LIQUIDATION_DEFENSE,
        }
        spread_too_wide = depth.spread_bps > self.max_spread_bps
        child_capacity = max(depth.available_depth * self.max_child_depth_fraction, 0.0)

        if not hedge_like and spread_too_wide and request.order_type == OrderType.MARKET:
            request = replace(
                request,
                order_type=OrderType.LIMIT,
                price=depth.mid_price,
                metadata={**request.metadata, "converted_from_market": True},
            )

        expected_slippage = self._expected_slippage_bps(request, depth)
        if request.quantity <= child_capacity or hedge_like or child_capacity <= 0:
            child_orders = (request,)
        else:
            child_orders = self._split_order(request, child_capacity)

        fallback_action = (
            "poll_immediately"
            if hedge_like
            else "cancel_or_reprice_if_not_accepted"
            if spread_too_wide
            else "poll_then_reconcile"
        )

        return ExecutionPlan(
            parent_client_order_id=parent_id,
            child_orders=child_orders,
            expected_slippage_bps=expected_slippage,
            validation_timeout_ms=750 if hedge_like else 2_500,
            fallback_action=fallback_action,
            rationale=self._rationale(request, depth, child_orders, hedge_like),
        )

    def _split_order(
        self,
        request: OrderRequest,
        child_capacity: float,
    ) -> tuple[OrderRequest, ...]:
        children: list[OrderRequest] = []
        remaining = request.quantity
        index = 1
        while remaining > 0:
            quantity = min(remaining, child_capacity)
            children.append(
                replace(
                    request,
                    quantity=quantity,
                    client_order_id=f"{request.client_order_id}-{index}-{uuid4().hex[:8]}",
                    metadata={**request.metadata, "parent_client_order_id": request.client_order_id},
                )
            )
            remaining -= quantity
            index += 1
        return tuple(children)

    def _expected_slippage_bps(self, request: OrderRequest, depth: MarketDepth) -> float:
        depth_pressure = request.quantity / max(depth.available_depth, 1.0)
        volatility_pressure = depth.volatility * 100.0
        return min(
            self.max_market_slippage_bps * 2.0,
            depth.spread_bps * 0.5 + depth_pressure * 10.0 + volatility_pressure,
        )

    def _rationale(
        self,
        request: OrderRequest,
        depth: MarketDepth,
        child_orders: tuple[OrderRequest, ...],
        hedge_like: bool,
    ) -> str:
        if hedge_like:
            return "Hedge or liquidation-defense execution prioritized with immediate validation."
        if len(child_orders) > 1:
            return "Order split to reduce liquidity impact and slippage."
        if depth.spread_bps > self.max_spread_bps:
            return "Wide spread requires passive or repriced execution."
        return "Market depth and spread permit single child execution."

