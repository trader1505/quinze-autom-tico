from laps1505_bot.config import BotSettings
from laps1505_bot.models import BalanceSnapshot, BotState, Position, Side, TrendSignal
from laps1505_bot.strategy import StrategyEngine


def test_initial_entry_uses_1_percent_of_free_futures():
    settings = BotSettings(min_notional_usdt=1.0, entry_fraction_of_free_futures=0.01)
    strategy = StrategyEngine(settings)
    balances = BalanceSnapshot(spot_usdt=80, futures_wallet_usdt=20, futures_free_usdt=20, margin_ratio=0.2)
    position = Position(side=Side.FLAT, quantity=0, entry_price=0, mark_price=100)
    signal = TrendSignal(side=Side.LONG, ema_short=101, ema_long=100, confirmed=True)

    result = strategy.evaluate(signal, balances, position, BotState())

    assert len(result.orders) == 1
    assert result.orders[0].side == Side.LONG
    assert result.orders[0].notional_usdt == 1.0  # max(20*1%, min_notional=1)
    assert result.state.open_operations == 0


def test_tp_100_percent_closes_position():
    settings = BotSettings(tp_roi_target=1.0)
    strategy = StrategyEngine(settings)
    balances = BalanceSnapshot(spot_usdt=80, futures_wallet_usdt=20, futures_free_usdt=20, margin_ratio=0.2)
    position = Position(side=Side.LONG, quantity=0.01, entry_price=100, mark_price=200)
    signal = TrendSignal(side=Side.LONG, ema_short=101, ema_long=100, confirmed=True)

    result = strategy.evaluate(signal, balances, position, BotState())

    assert len(result.orders) == 1
    assert result.orders[0].reduce_only is True
    assert result.orders[0].reason == "tp_100_roi"
    assert any(event.type == "tp_hit" for event in result.events)


def test_recovery_3x_after_opposite_then_return():
    settings = BotSettings(recovery_multiplier=3.0, min_notional_usdt=1.0)
    strategy = StrategyEngine(settings)
    balances = BalanceSnapshot(spot_usdt=80, futures_wallet_usdt=20, futures_free_usdt=20, margin_ratio=0.2)
    position = Position(side=Side.LONG, quantity=0.04, entry_price=100, mark_price=80)
    state = BotState(recovery_anchor_side=Side.LONG, recovery_base_notional=4.0, pending_3x=False)

    opposite_signal = TrendSignal(side=Side.SHORT, ema_short=90, ema_long=100, confirmed=True)
    armed = strategy.evaluate(opposite_signal, balances, position, state)
    assert armed.state.pending_3x is True
    assert len(armed.orders) == 0

    return_signal = TrendSignal(side=Side.LONG, ema_short=101, ema_long=100, confirmed=True)
    fired = strategy.evaluate(return_signal, balances, position, armed.state)
    assert len(fired.orders) == 1
    assert fired.orders[0].reason == "recovery_3x"
    assert fired.orders[0].notional_usdt == 12.0
    assert any(event.type == "recovery_fired" for event in fired.events)


def test_recovery_armed_event_emitted_once_while_pending():
    settings = BotSettings(recovery_multiplier=3.0, min_notional_usdt=1.0)
    strategy = StrategyEngine(settings)
    balances = BalanceSnapshot(spot_usdt=80, futures_wallet_usdt=20, futures_free_usdt=20, margin_ratio=0.2)
    position = Position(side=Side.LONG, quantity=0.04, entry_price=100, mark_price=80)
    state = BotState(recovery_anchor_side=Side.LONG, recovery_base_notional=4.0, pending_3x=False)
    opposite_signal = TrendSignal(side=Side.SHORT, ema_short=90, ema_long=100, confirmed=True)

    first = strategy.evaluate(opposite_signal, balances, position, state)
    second = strategy.evaluate(opposite_signal, balances, position, first.state)

    assert any(event.type == "recovery_armed" for event in first.events)
    assert not any(event.type == "recovery_armed" for event in second.events)


def test_slot_scale_entry_up_to_max_operations():
    settings = BotSettings(max_concurrent_operations=30, min_notional_usdt=1.0, entry_fraction_of_free_futures=0.01)
    strategy = StrategyEngine(settings)
    balances = BalanceSnapshot(spot_usdt=80, futures_wallet_usdt=20, futures_free_usdt=20, margin_ratio=0.2)
    position = Position(side=Side.LONG, quantity=0.04, entry_price=100, mark_price=100)
    signal = TrendSignal(side=Side.LONG, ema_short=101, ema_long=100, confirmed=True)
    state = BotState(recovery_anchor_side=Side.LONG, recovery_base_notional=4.0, pending_3x=False, open_operations=29)

    result = strategy.evaluate(signal, balances, position, state)
    assert len(result.orders) == 1
    assert result.orders[0].reason == "slot_scale_entry"
    assert result.state.open_operations == 29
    assert any(event.type == "slot_opened" for event in result.events)

    result.state.open_operations = 30
    second = strategy.evaluate(signal, balances, position, result.state)
    assert len(second.orders) == 0
    assert second.state.open_operations == 30
