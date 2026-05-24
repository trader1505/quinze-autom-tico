from __future__ import annotations

import asyncio
import unittest

from backend.laps_hybrid.execution_exchange import (
    Exchange,
    ExecutionExchangeEngine,
    ExecutionFailsafeEngine,
    ExecutionPriority,
    ExchangePosition,
    Fill,
    InMemoryExecutionAuditSink,
    InMemoryExecutionEventBus,
    LocalPosition,
    MarketDepth,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperExchangeConnector,
    PositionReconciler,
    PositionSide,
    ReconciliationSeverity,
    SmartExecutionPlanner,
    WebsocketManager,
    WebsocketStreamState,
)
from backend.laps_hybrid.execution_exchange.models import ExchangeOrderUpdate
from backend.laps_hybrid.execution_exchange.validation import ExecutionValidator


class ExecutionExchangeTest(unittest.TestCase):
    def test_smart_planner_splits_large_non_hedge_order(self) -> None:
        request = OrderRequest(
            exchange=Exchange.BINANCE_FUTURES,
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100.0,
        )
        depth = MarketDepth(
            symbol="BTC/USDT",
            mid_price=100_000.0,
            spread_bps=5.0,
            bid_depth=200.0,
            ask_depth=200.0,
            volatility=0.03,
        )

        plan = SmartExecutionPlanner(max_child_depth_fraction=0.1).plan(request, depth)

        self.assertGreater(len(plan.child_orders), 1)
        self.assertAlmostEqual(sum(child.quantity for child in plan.child_orders), 100.0)

    def test_hedge_order_is_not_split_and_uses_fast_validation(self) -> None:
        request = OrderRequest(
            exchange=Exchange.BINANCE_FUTURES,
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=100.0,
            priority=ExecutionPriority.HEDGE,
            reduce_only=True,
        )
        depth = MarketDepth(
            symbol="BTC/USDT",
            mid_price=100_000.0,
            spread_bps=30.0,
            bid_depth=50.0,
            ask_depth=50.0,
            volatility=0.08,
        )

        plan = SmartExecutionPlanner(max_child_depth_fraction=0.1).plan(request, depth)

        self.assertEqual(len(plan.child_orders), 1)
        self.assertEqual(plan.validation_timeout_ms, 750)
        self.assertEqual(plan.fallback_action, "poll_immediately")

    def test_validator_rejects_overfilled_order_and_tracks_duplicate_fills(self) -> None:
        validator = ExecutionValidator()
        accepted = validator.validate_order_update(
            ExchangeOrderUpdate(
                exchange=Exchange.BINANCE_FUTURES,
                symbol="BTC/USDT",
                client_order_id="order-1",
                status=OrderStatus.PARTIALLY_FILLED,
                requested_quantity=2.0,
                filled_quantity=1.0,
                fills=(Fill(fill_id="fill-1", price=100_000.0, quantity=1.0),),
            )
        )
        duplicate = validator.validate_order_update(
            ExchangeOrderUpdate(
                exchange=Exchange.BINANCE_FUTURES,
                symbol="BTC/USDT",
                client_order_id="order-1",
                status=OrderStatus.PARTIALLY_FILLED,
                requested_quantity=2.0,
                filled_quantity=1.0,
                fills=(Fill(fill_id="fill-1", price=100_000.0, quantity=1.0),),
            )
        )
        overfilled = validator.validate_order_update(
            ExchangeOrderUpdate(
                exchange=Exchange.BINANCE_FUTURES,
                symbol="BTC/USDT",
                client_order_id="order-2",
                status=OrderStatus.FILLED,
                requested_quantity=1.0,
                filled_quantity=2.0,
            )
        )

        self.assertTrue(accepted.valid)
        self.assertEqual(duplicate.duplicate_fill_ids, ("fill-1",))
        self.assertFalse(overfilled.valid)

    def test_reconciler_detects_quantity_and_ghost_position(self) -> None:
        issues = PositionReconciler().reconcile(
            local_positions=(
                LocalPosition(
                    exchange=Exchange.BINANCE_FUTURES,
                    symbol="ETH/USDT",
                    quantity=2.0,
                    leverage=2.0,
                    side=PositionSide.LONG,
                ),
            ),
            exchange_positions=(
                ExchangePosition(
                    exchange=Exchange.BINANCE_FUTURES,
                    symbol="ETH/USDT",
                    quantity=1.5,
                    leverage=2.0,
                    side=PositionSide.LONG,
                ),
                ExchangePosition(
                    exchange=Exchange.BINANCE_FUTURES,
                    symbol="SOL/USDT",
                    quantity=10.0,
                    leverage=1.0,
                    side=PositionSide.LONG,
                ),
            ),
        )

        issue_types = {issue.issue_type for issue in issues}
        self.assertIn("quantity_mismatch", issue_types)
        self.assertIn("ghost_exchange_position", issue_types)
        self.assertTrue(
            any(issue.severity == ReconciliationSeverity.SEVERE for issue in issues)
        )

    def test_websocket_staleness_triggers_reconnect(self) -> None:
        decision = WebsocketManager().evaluate(
            WebsocketStreamState(
                exchange=Exchange.BITGET_FUTURES,
                stream_name="private_orders",
                connected=True,
                last_message_age_ms=4_000,
                heartbeat_age_ms=500,
                reconnect_attempts=1,
                latency_ms=50,
            )
        )

        self.assertFalse(decision.healthy)
        self.assertTrue(decision.reconnect)
        self.assertTrue(decision.stale)

    def test_failsafe_pauses_on_stale_stream_and_reconciliation_issue(self) -> None:
        ws_decision = WebsocketManager().evaluate(
            WebsocketStreamState(
                exchange=Exchange.BINANCE_FUTURES,
                stream_name="private_positions",
                connected=False,
                last_message_age_ms=10_000,
                heartbeat_age_ms=10_000,
                reconnect_attempts=2,
                latency_ms=0,
            )
        )
        issue = PositionReconciler().reconcile(
            local_positions=(
                LocalPosition(
                    exchange=Exchange.BINANCE_FUTURES,
                    symbol="BTC/USDT",
                    quantity=1.0,
                    leverage=2.0,
                    side=PositionSide.LONG,
                ),
            ),
            exchange_positions=(),
        )[0]

        decision = ExecutionFailsafeEngine().evaluate(
            websocket_decisions=(ws_decision,),
            reconciliation_issues=(issue,),
        )

        self.assertTrue(decision.pause_new_orders)
        self.assertTrue(decision.allow_reduce_only)
        self.assertTrue(decision.require_reconciliation)
        self.assertFalse(decision.lockdown)

    def test_execution_engine_publishes_and_audits_order_lifecycle(self) -> None:
        async def scenario() -> None:
            event_bus = InMemoryExecutionEventBus()
            audit_sink = InMemoryExecutionAuditSink()
            engine = ExecutionExchangeEngine(
                connectors={Exchange.BINANCE_FUTURES: PaperExchangeConnector()},
                event_publisher=event_bus,
                audit_sink=audit_sink,
            )

            updates = await engine.execute(
                OrderRequest(
                    exchange=Exchange.BINANCE_FUTURES,
                    symbol="BTC/USDT",
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    quantity=0.2,
                    price=100_000.0,
                ),
                MarketDepth(
                    symbol="BTC/USDT",
                    mid_price=100_000.0,
                    spread_bps=3.0,
                    bid_depth=100.0,
                    ask_depth=100.0,
                    volatility=0.02,
                ),
            )

            self.assertEqual(len(updates), 1)
            self.assertEqual(updates[0].status, OrderStatus.ACCEPTED)
            self.assertGreaterEqual(len(event_bus.snapshot()), 2)
            self.assertGreaterEqual(len(audit_sink.snapshot()), 2)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()

