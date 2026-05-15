"""Integration-style sanity tests for LAPS Crypto runtime."""

from laps_crypto.app.main import LapsCryptoSystem


def test_system_cycle_runs_without_exception() -> None:
    system = LapsCryptoSystem.bootstrap()
    system.run_cycle()

    orders = system.client.order_history()
    assert len(orders) >= 1
    assert all(order.quantity > 0 for order in orders)
