from laps1505_bot.config import BotSettings
from laps1505_bot.engine import TradingEngine
from laps1505_bot.gateway import SimulationGateway
from laps1505_bot.models import BalanceSnapshot, Position, Side


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
