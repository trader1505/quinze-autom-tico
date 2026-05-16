from laps1505_bot.indicators import detect_trend, ema
from laps1505_bot.models import Side


def test_ema_returns_expected_value():
    values = [10, 11, 12, 13, 14, 15, 16]
    result = ema(values, 3)
    assert round(result, 4) == 15.0


def test_detect_trend_long_confirmed():
    prices = list(range(100, 145))
    signal = detect_trend(prices, short_period=12, long_period=26)
    assert signal.side == Side.LONG
    assert signal.confirmed is True


def test_detect_trend_short_confirmed():
    prices = list(range(145, 100, -1))
    signal = detect_trend(prices, short_period=12, long_period=26)
    assert signal.side == Side.SHORT
    assert signal.confirmed is True
