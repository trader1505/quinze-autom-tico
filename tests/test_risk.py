from laps1505_bot.config import BotSettings
from laps1505_bot.models import BalanceSnapshot
from laps1505_bot.risk import RiskEngine


def test_deposit_rebalance_keeps_80_20():
    settings = BotSettings()
    risk = RiskEngine(settings)
    balances = BalanceSnapshot(
        spot_usdt=100.0,
        futures_wallet_usdt=20.0,
        futures_free_usdt=20.0,
        margin_ratio=0.4,
    )

    result = risk.evaluate(balances)

    assert len(result.transfers) == 1
    transfer = result.transfers[0]
    assert transfer.from_wallet == "spot"
    assert transfer.to_wallet == "futures"
    assert round(transfer.amount_usdt, 2) == 4.0  # target spot=96 on total=120


def test_margin_stress_adds_20_percent_to_futures():
    settings = BotSettings(margin_stress_threshold=0.60)
    risk = RiskEngine(settings)
    balances = BalanceSnapshot(
        spot_usdt=80.0,
        futures_wallet_usdt=20.0,
        futures_free_usdt=5.0,
        margin_ratio=0.65,
    )

    result = risk.evaluate(balances)

    assert len(result.transfers) == 1
    assert result.transfers[0].reason == "margin_stress_topup"
    assert round(result.transfers[0].amount_usdt, 2) == 20.0


def test_margin_recovery_rebalances_back():
    settings = BotSettings(margin_recovery_threshold=0.30)
    risk = RiskEngine(settings)
    balances = BalanceSnapshot(
        spot_usdt=70.0,
        futures_wallet_usdt=30.0,
        futures_free_usdt=20.0,
        margin_ratio=0.20,
    )

    result = risk.evaluate(balances)

    assert len(result.transfers) == 1
    assert result.transfers[0].from_wallet == "futures"
    assert result.transfers[0].to_wallet == "spot"
    assert round(result.transfers[0].amount_usdt, 2) == 10.0
