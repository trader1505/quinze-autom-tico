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
from laps_bot.models import PositionState


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


class _ExchangeHardStopStub(_ExchangeMarginStub):
    def __init__(self, spot_free: float, positions: list[PositionState]) -> None:
        super().__init__(spot_free)
        self.positions = list(positions)
        self.closed_symbols: list[str] = []

    def close_position(self, position: PositionState) -> dict:
        self.closed_symbols.append(position.symbol)
        self.positions = [item for item in self.positions if item.symbol != position.symbol]
        return {"id": "close"}

    def fetch_open_positions(self, symbols: list[str]) -> list[PositionState]:
        return list(self.positions)


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
        margin_ratio_emergency_pct=70.0,
        margin_emergency_topup_pct=100.0,
        margin_ratio_hard_stop_pct=78.0,
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
        bot._account_margin_last_topup_ts = 0.0
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

    @patch("laps_bot.bot.rebalance_80_20", return_value={"changed": True})
    def test_topup_repeats_after_cooldown_if_margin_stays_high(self, _rebalance_mock: object) -> None:
        bot, exchange, emitted = self._make_bot(10.0)
        bot._manage_account_margin_ratio(65.0)
        self.assertEqual(len(exchange.transfers), 1)

        # still above trigger, but before cooldown no new transfer should occur
        bot._manage_account_margin_ratio(65.0)
        self.assertEqual(len(exchange.transfers), 1)
        self.assertIn("margin_topped_up_skipped", emitted)

        # after cooldown, transfer should happen again if still above trigger
        bot._account_margin_last_topup_ts -= (bot.ACCOUNT_MARGIN_TOPUP_COOLDOWN_SECONDS + 1)
        bot._manage_account_margin_ratio(65.0)
        self.assertEqual(len(exchange.transfers), 2)

    @patch("laps_bot.bot.rebalance_80_20", return_value={"changed": True})
    def test_emergency_topup_bypasses_cooldown(self, _rebalance_mock: object) -> None:
        bot, exchange, emitted = self._make_bot(10.0)
        bot._manage_account_margin_ratio(65.0)
        self.assertEqual(exchange.transfers, [2.0])

        # Above emergency threshold should bypass cooldown and top up remaining balance.
        bot._manage_account_margin_ratio(72.0)
        self.assertEqual(len(exchange.transfers), 2)
        self.assertAlmostEqual(exchange.transfers[1], 8.0)
        self.assertIn("margin_topup_emergency_bypass", emitted)

    def test_hard_stop_closes_highest_margin_pressure_position(self) -> None:
        first = PositionState(
            symbol="ADA/USDT:USDT",
            side="long",
            contracts=1.0,
            entry_price=1.0,
            unrealized_pnl=-0.3,
            initial_margin=1.0,
            mark_price=0.8,
            liquidation_price=0.7,
            margin_ratio_pct=76.0,
        )
        second = PositionState(
            symbol="DOGE/USDT:USDT",
            side="short",
            contracts=2.0,
            entry_price=0.2,
            unrealized_pnl=-0.6,
            initial_margin=1.0,
            mark_price=0.25,
            liquidation_price=0.3,
            margin_ratio_pct=82.0,
        )
        bot = LapsBot.__new__(LapsBot)
        bot.config = _make_config()
        bot.exchange = _ExchangeHardStopStub(spot_free=0.0, positions=[first, second])
        bot.position_states = {first.symbol: object(), second.symbol: object()}
        emitted: list[str] = []
        bot._emit = lambda event_type, message, payload=None, severity="info": emitted.append(event_type)  # type: ignore[method-assign]

        remaining = bot._apply_hard_stop_if_needed(79.0, [first, second], ["ADA/USDT:USDT", "DOGE/USDT:USDT"])
        self.assertEqual(bot.exchange.closed_symbols, ["DOGE/USDT:USDT"])  # type: ignore[attr-defined]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].symbol, "ADA/USDT:USDT")
        self.assertIn("hard_risk_reduce", emitted)


if __name__ == "__main__":
    unittest.main()
