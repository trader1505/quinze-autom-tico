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
from laps_bot.models import PositionState, Trend
from laps_bot.strategy import TrendSignal


class _ExchangeStub:
    def __init__(self) -> None:
        self.closed_symbols: list[str] = []

    def close_position(self, position: PositionState) -> dict:
        self.closed_symbols.append(position.symbol)
        return {"id": "close-order"}

    def total_spot_usdt(self) -> float:
        return 80.0

    def total_futures_usdt(self) -> float:
        return 20.0

    def free_spot_usdt(self) -> float:
        return 10.0

    def free_futures_usdt(self) -> float:
        return 5.0


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
        fixed_entry_margin_usdt=0.0,
        leverage=20,
        use_max_leverage_per_symbol=True,
        target_roi_pct=1000.0,
        add_margin_trigger_pct=-60.0,
        margin_ratio_trigger_pct=60.0,
        margin_match_tolerance_pct=0.25,
        taker_fee_rate=0.0005,
        reinforcement_multiplier=3.0,
        spot_target_pct=80.0,
        futures_target_pct=20.0,
        margin_topup_pct=20.0,
        max_topups=4,
        poll_seconds=20,
        entry_scan_batch=80,
        log_level="INFO",
        telemetry_dir="runtime",
        panel_host="0.0.0.0",
        panel_port=8080,
    )


def _flat_signal() -> TrendSignal:
    return TrendSignal(
        trend=Trend.FLAT,
        crossover=None,
        latest_crossover=None,
        previous_crossover=None,
        fast_ema=0.0,
        slow_ema=0.0,
    )


class ReinforcementCloseFeeTests(unittest.TestCase):
    def _make_bot(self) -> tuple[LapsBot, _ExchangeStub, list[tuple[str, dict]]]:
        bot = LapsBot.__new__(LapsBot)
        bot.config = _make_config()
        exchange = _ExchangeStub()
        bot.exchange = exchange
        bot.position_states = {}
        emitted: list[tuple[str, dict]] = []

        def _capture(event_type: str, message: str, payload: dict | None = None, severity: str = "info") -> None:
            emitted.append((event_type, payload or {}))

        bot._emit = _capture  # type: ignore[method-assign]
        bot._signal_for_symbol = lambda _symbol: _flat_signal()  # type: ignore[method-assign]
        return bot, exchange, emitted

    @patch("laps_bot.bot.rebalance_80_20", return_value={"changed": False, "reason": "already_balanced"})
    def test_reinforcement_close_waits_when_estimated_net_after_fees_is_negative(self, _rebalance_mock: object) -> None:
        bot, exchange, emitted = self._make_bot()
        symbol = "BTC/USDT:USDT"
        state = bot._state_for_symbol(symbol)
        state.initial_entry_usdt = 10.0
        state.reinforcement_done = True
        state.estimated_open_fees_usdt = 0.20

        position = PositionState(
            symbol=symbol,
            side="long",
            contracts=1.0,
            entry_price=100.0,
            unrealized_pnl=0.10,
            initial_margin=10.0,
            mark_price=100.0,
            liquidation_price=80.0,
            margin_ratio_pct=61.0,
        )

        bot._manage_single_position(position)

        self.assertEqual(exchange.closed_symbols, [])
        self.assertTrue(state.reinforcement_done)
        self.assertIsNotNone(state.reinforcement_exit_bucket)
        self.assertTrue(any(event == "reinforcement_wait_fee_recovery" for event, _ in emitted))

    @patch("laps_bot.bot.rebalance_80_20", return_value={"changed": False, "reason": "already_balanced"})
    def test_reinforcement_close_executes_when_estimated_net_after_fees_is_non_negative(self, _rebalance_mock: object) -> None:
        bot, exchange, emitted = self._make_bot()
        symbol = "BTC/USDT:USDT"
        state = bot._state_for_symbol(symbol)
        state.initial_entry_usdt = 10.0
        state.reinforcement_done = True
        state.estimated_open_fees_usdt = 0.01

        position = PositionState(
            symbol=symbol,
            side="long",
            contracts=1.0,
            entry_price=100.0,
            unrealized_pnl=0.20,
            initial_margin=10.0,
            mark_price=100.0,
            liquidation_price=80.0,
            margin_ratio_pct=61.0,
        )

        bot._manage_single_position(position)

        self.assertEqual(exchange.closed_symbols, [symbol])
        self.assertNotIn(symbol, bot.position_states)
        recovered_events = [payload for event, payload in emitted if event == "reinforcement_recovered_close"]
        self.assertEqual(len(recovered_events), 1)
        self.assertGreaterEqual(recovered_events[0]["estimated_net_after_fees_usdt"], 0.0)


if __name__ == "__main__":
    unittest.main()
