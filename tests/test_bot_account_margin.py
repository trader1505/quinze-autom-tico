from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laps_bot.bot import LapsBot
from laps_bot.config import BotConfig


class _ExchangeMarginStub:
    def __init__(self, spot_free: float) -> None:
        self._spot_free = spot_free
        self.transfers: list[float] = []

    def free_spot_usdt(self) -> float:
        return self._spot_free

    def transfer_usdt(self, amount: float, from_account: str, to_account: str) -> dict:
        self.transfers.append(amount)
        self._spot_free = max(0.0, self._spot_free - amount)
        return {"id": "transfer"}


def _make_config() -> BotConfig:
    return BotConfig(
        api_key="k",
        api_secret="s",
        sandbox=True,
        symbols=("BTC/USDT:USDT",),
        scan_all_symbols=False,
        max_scan_symbols=300,
        symbol_universe_refresh_seconds=900,
        timeframe="15m",
        fast_ma=12,
        slow_ma=26,
        max_positions=1,
        balance_risk_pct=1.0,
        fixed_entry_margin_usdt=0.10,
        leverage=20,
        use_max_leverage_per_symbol=True,
        target_roi_pct=100.0,
        add_margin_trigger_pct=-60.0,
        margin_ratio_trigger_pct=60.0,
        margin_ratio_rebalance_pct=31.0,
        margin_match_tolerance_pct=0.25,
        taker_fee_rate=0.0005,
        reinforcement_multiplier=3.0,
        spot_target_pct=80.0,
        futures_target_pct=20.0,
        margin_topup_pct=20.0,
        max_topups=4,
        poll_seconds=20,
        entry_scan_batch=300,
        log_level="INFO",
        telemetry_dir="runtime",
        panel_host="0.0.0.0",
        panel_port=8090,
    )


class AccountMarginGuardTests(unittest.TestCase):
    def _make_bot(self, spot_free: float) -> tuple[LapsBot, _ExchangeMarginStub, list[str]]:
        bot = LapsBot.__new__(LapsBot)
        bot.config = _make_config()
        exchange = _ExchangeMarginStub(spot_free)
        bot.exchange = exchange
        bot._account_margin_topup_active = False
        emitted: list[str] = []
        bot._emit = lambda event_type, message, payload=None, severity="info": emitted.append(event_type)  # type: ignore[method-assign]
        return bot, exchange, emitted

    @patch("laps_bot.bot.rebalance_80_20", return_value={"changed": True})
    def test_topup_transfers_when_account_margin_hits_trigger(self, _rebalance_mock: object) -> None:
        bot, exchange, emitted = self._make_bot(10.0)
        bot._manage_account_margin_ratio(60.5)
        self.assertEqual(len(exchange.transfers), 1)
        self.assertAlmostEqual(exchange.transfers[0], 2.0)
        self.assertTrue(bot._account_margin_topup_active)
        self.assertIn("margin_topped_up", emitted)

    @patch("laps_bot.bot.rebalance_80_20", return_value={"changed": True})
    def test_rebalance_runs_when_account_margin_recovers(self, _rebalance_mock: object) -> None:
        bot, exchange, emitted = self._make_bot(10.0)
        bot._account_margin_topup_active = True
        bot._manage_account_margin_ratio(30.5)
        self.assertFalse(bot._account_margin_topup_active)
        self.assertEqual(exchange.transfers, [])
        self.assertIn("cash_rebalance", emitted)


if __name__ == "__main__":
    unittest.main()
