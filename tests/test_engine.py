from laps1505_bot.config import BotSettings
from laps1505_bot.engine import TradingEngine
from laps1505_bot.gateway import SimulationGateway
from laps1505_bot.models import BalanceSnapshot, Position, Side
from laps1505_bot.strategy import StrategyResult


def test_engine_processes_strategy_on_each_poll_cycle():
    settings = BotSettings(dry_run=True)
    gateway = SimulationGateway(
        close_prices=list(range(100, 170)),
        balances=BalanceSnapshot(
            spot_usdt=80.0,
            futures_wallet_usdt=20.0,
            futures_free_usdt=20.0,
            margin_ratio=0.2,
        ),
        position=Position(side=Side.FLAT, quantity=0, entry_price=0, mark_price=160),
    )
    engine = TradingEngine(settings, gateway)
    call_counter = {"count": 0}

    def fake_evaluate(*args, **kwargs):
        _ = args, kwargs
        call_counter["count"] += 1
        return StrategyResult(orders=[], state=engine.state, events=[])

    engine.strategy.evaluate = fake_evaluate  # type: ignore[assignment]

    engine.cycle_once()
    engine.cycle_once()

    assert call_counter["count"] == 2


def test_engine_syncs_existing_open_position_on_first_cycle():
    settings = BotSettings(dry_run=True, min_notional_usdt=1.0)
    gateway = SimulationGateway(
        close_prices=list(range(100, 170)),
        balances=BalanceSnapshot(
            spot_usdt=80.0,
            futures_wallet_usdt=20.0,
            futures_free_usdt=20.0,
            margin_ratio=0.2,
        ),
        position=Position(side=Side.LONG, quantity=10, entry_price=150, mark_price=160),
    )
    engine = TradingEngine(settings, gateway)

    engine.cycle_once()

    assert engine.state.recovery_anchor_side == Side.LONG
    assert engine.state.recovery_base_notional > 0
    assert len(engine.state.managed_operations) >= 1
    assert engine.state.managed_operations[0]["reason"] in {"synced_existing_position", "simulation_position"}
    assert any(event.type == "position_synced" for event in engine.events)


def test_engine_cycle_generates_entry_event():
    settings = BotSettings(dry_run=True, min_notional_usdt=1.0)
    gateway = SimulationGateway(
        close_prices=list(range(100, 170)),
        balances=BalanceSnapshot(
            spot_usdt=80.0,
            futures_wallet_usdt=20.0,
            futures_free_usdt=20.0,
            margin_ratio=0.2,
        ),
        position=Position(side=Side.FLAT, quantity=0, entry_price=0, mark_price=160),
    )
    engine = TradingEngine(settings, gateway)

    engine.cycle_once()

    assert engine.last_error is None
    assert any(event.type == "entry" for event in engine.events)


def test_engine_does_not_count_unfilled_orders_as_open_operations():
    settings = BotSettings(dry_run=True, min_notional_usdt=1.0)
    gateway = SimulationGateway(
        close_prices=list(range(100, 170)),
        balances=BalanceSnapshot(
            spot_usdt=80.0,
            futures_wallet_usdt=20.0,
            futures_free_usdt=20.0,
            margin_ratio=0.2,
        ),
        position=Position(side=Side.FLAT, quantity=0, entry_price=0, mark_price=160),
    )
    gateway.place_order = lambda intent: []  # type: ignore[assignment]
    engine = TradingEngine(settings, gateway)

    engine.cycle_once()

    assert engine.state.open_operations == 0
    assert len(engine.state.managed_operations) == 0
    assert any(event.type == "order_not_filled" for event in engine.events)


def test_engine_closes_individual_operations_when_slot_roi_hits_100_percent():
    settings = BotSettings(
        dry_run=True,
        min_notional_usdt=1.0,
        tp_roi_target=1.0,
        max_concurrent_operations=0,
    )
    gateway = SimulationGateway(
        close_prices=list(range(100, 200)),
        balances=BalanceSnapshot(
            spot_usdt=80.0,
            futures_wallet_usdt=20.0,
            futures_free_usdt=20.0,
            margin_ratio=0.2,
        ),
        position=Position(side=Side.LONG, quantity=1.0, entry_price=80.0, mark_price=199.0),
    )
    engine = TradingEngine(settings, gateway)
    engine.state.recovery_anchor_side = Side.LONG
    engine.state.recovery_base_notional = 10.0
    engine.state.managed_operations = [
        {
            "id": 1,
            "side": "LONG",
            "entry_price": 80.0,
            "quantity": 0.5,
            "notional_usdt": 40.0,
            "reason": "slot_scale_entry",
            "opened_at": "2026-01-01T00:00:00+00:00",
        }
    ]
    engine.state.open_operations = 1

    engine.cycle_once()

    assert len(engine.state.managed_operations) == 0
    assert engine.state.open_operations == 0
    assert any(event.type == "tp_slot_hit" for event in engine.events)


def test_engine_status_contains_expected_sections():
    settings = BotSettings(dry_run=True)
    gateway = SimulationGateway(
        close_prices=list(range(100, 170)),
        balances=BalanceSnapshot(
            spot_usdt=80.0,
            futures_wallet_usdt=20.0,
            futures_free_usdt=20.0,
            margin_ratio=0.2,
        ),
        position=Position(side=Side.FLAT, quantity=0, entry_price=0, mark_price=160),
    )
    engine = TradingEngine(settings, gateway)
    payload = engine.status()

    assert "balances" in payload
    assert "position" in payload
    assert "state" in payload
    assert "operations" in payload
    assert "pending_operations" in payload
