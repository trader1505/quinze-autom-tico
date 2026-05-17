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


def _make_config(max_positions: int = 1) -> BotConfig:
    return BotConfig(
        api_key="k",
        api_secret="s",
        sandbox=True,
        symbols=("ADA/USDT:USDT", "DOGE/USDT:USDT"),
        scan_all_symbols=False,
        max_scan_symbols=300,
        symbol_universe_refresh_seconds=900,
        timeframe="15m",
        fast_ma=12,
        slow_ma=26,
        max_positions=max_positions,
        balance_risk_pct=1.0,
        fixed_entry_margin_usdt=0.10,
        leverage=20,
        use_max_leverage_per_symbol=True,
        target_roi_pct=100.0,
        add_margin_trigger_pct=-60.0,
        margin_ratio_trigger_pct=60.0,
        margin_ratio_rebalance_pct=31.0,
        margin_match_tolerance_pct=30.0,
        taker_fee_rate=0.0005,
        reinforcement_multiplier=3.0,
        spot_target_pct=80.0,
        futures_target_pct=20.0,
        margin_topup_pct=20.0,
        max_topups=4,
        poll_seconds=10,
        entry_scan_batch=300,
        log_level="INFO",
        telemetry_dir="runtime",
        panel_host="0.0.0.0",
        panel_port=8090,
    )


class _ExchangeTpStub:
    def __init__(self) -> None:
        self.closed = 0

    def close_position(self, position: PositionState) -> dict:
        self.closed += 1
        return {"id": "close"}

    def total_spot_usdt(self) -> float:
        return 80.0

    def total_futures_usdt(self) -> float:
        return 20.0

    def free_spot_usdt(self) -> float:
        return 30.0

    def free_futures_usdt(self) -> float:
        return 5.0

    def account_margin_ratio_pct(self) -> float:
        return 20.0


class _ExchangeCycleStub(_ExchangeTpStub):
    def __init__(self, first: PositionState, third: PositionState) -> None:
        super().__init__()
        self._first = first
        self._third = third
        self.fetch_calls = 0

    def fetch_open_positions(self, symbols) -> list[PositionState]:
        self.fetch_calls += 1
        if self.fetch_calls == 1:
            return [self._first]
        if self.fetch_calls == 2:
            return []
        return [self._third]


class BotTpAndRefillTests(unittest.TestCase):
    @patch("laps_bot.bot.rebalance_80_20", return_value={"changed": False})
    def test_tp_close_triggers_rebalance_event(self, _rebalance_mock: object) -> None:
        bot = LapsBot.__new__(LapsBot)
        bot.config = _make_config()
        bot.exchange = _ExchangeTpStub()
        bot.position_states = {}
        emitted: list[str] = []
        bot._emit = lambda event_type, message, payload=None, severity="info": emitted.append(event_type)  # type: ignore[method-assign]

        position = PositionState(
            symbol="ADA/USDT:USDT",
            side="long",
            contracts=1.0,
            entry_price=1.0,
            unrealized_pnl=1.1,
            initial_margin=1.0,
            mark_price=1.0,
            liquidation_price=0.5,
            margin_ratio_pct=70.0,
        )
        bot._state_for_symbol(position.symbol).initial_entry_usdt = 0.10
        trend = bot._manage_single_position(position)

        self.assertIsNone(trend)
        self.assertEqual(bot.exchange.closed, 1)  # type: ignore[attr-defined]
        self.assertIn("tp_hit", emitted)
        self.assertIn("cash_rebalance", emitted)
        self.assertNotIn(position.symbol, bot.position_states)

    @patch("laps_bot.bot.rebalance_80_20", return_value={"changed": False})
    def test_manage_open_positions_refills_slot_after_tp_close_same_cycle(self, _rebalance_mock: object) -> None:
        tp_position = PositionState(
            symbol="ADA/USDT:USDT",
            side="long",
            contracts=1.0,
            entry_price=1.0,
            unrealized_pnl=1.2,
            initial_margin=1.0,
            mark_price=1.0,
            liquidation_price=0.5,
            margin_ratio_pct=70.0,
        )
        reopened = PositionState(
            symbol="DOGE/USDT:USDT",
            side="short",
            contracts=2.0,
            entry_price=0.2,
            unrealized_pnl=0.0,
            initial_margin=0.1,
            mark_price=0.2,
            liquidation_price=0.3,
            margin_ratio_pct=65.0,
        )

        bot = LapsBot.__new__(LapsBot)
        bot.config = _make_config(max_positions=1)
        bot.exchange = _ExchangeCycleStub(tp_position, reopened)
        bot.position_states = {}
        bot._emit = lambda *args, **kwargs: None  # type: ignore[method-assign]
        sync_statuses: list[str] = []
        bot._sync_state = lambda status, positions=None, trends=None, capital=None: sync_statuses.append(status)  # type: ignore[method-assign]

        open_calls = {"count": 0}

        def _open_new_position(blocked_symbols: set[str], symbol_universe: list[str]) -> bool:
            open_calls["count"] += 1
            blocked_symbols.add("DOGE/USDT:USDT")
            return True

        bot._open_new_position = _open_new_position  # type: ignore[method-assign]

        bot._manage_open_positions()

        self.assertGreaterEqual(open_calls["count"], 1)
        self.assertIn("positions_active", sync_statuses)


if __name__ == "__main__":
    unittest.main()
