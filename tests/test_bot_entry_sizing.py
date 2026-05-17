from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laps_bot.bot import LapsBot
from laps_bot.config import BotConfig
from laps_bot.models import Trend
from laps_bot.strategy import TrendSignal


class _ExchangeEntryStub:
    def __init__(self, free_futures: float) -> None:
        self._free_futures = free_futures
        self.choose_calls: list[tuple[tuple[str, ...], float, int]] = []
        self.created_orders = 0

    def free_futures_usdt(self) -> float:
        return self._free_futures

    def choose_symbol_and_amount_for_exact_margin(
        self, symbols: list[str], target_margin_usdt: float, leverage: int
    ) -> tuple[str, float, float, float]:
        self.choose_calls.append((tuple(symbols), target_margin_usdt, leverage))
        symbol = symbols[0]
        return symbol, 1.0, 1.0, target_margin_usdt

    def create_market_position(self, symbol: str, trend: Trend, amount: float, reduce_only: bool = False) -> dict:
        self.created_orders += 1
        return {"id": "order"}

    def active_leverage(self, symbol: str) -> int:
        return 50


def _signal_long() -> TrendSignal:
    return TrendSignal(
        trend=Trend.LONG,
        crossover=None,
        latest_crossover=None,
        previous_crossover=None,
        fast_ema=1.0,
        slow_ema=0.9,
    )


def _make_config(fixed_entry_margin_usdt: float) -> BotConfig:
    return BotConfig(
        api_key="k",
        api_secret="s",
        sandbox=True,
        symbols=("ADA/USDT:USDT",),
        scan_all_symbols=False,
        max_scan_symbols=300,
        symbol_universe_refresh_seconds=900,
        timeframe="15m",
        fast_ma=12,
        slow_ma=26,
        max_positions=30,
        balance_risk_pct=1.0,
        fixed_entry_margin_usdt=fixed_entry_margin_usdt,
        leverage=125,
        use_max_leverage_per_symbol=True,
        target_roi_pct=100.0,
        add_margin_trigger_pct=-60.0,
        margin_ratio_trigger_pct=60.0,
        margin_match_tolerance_pct=0.25,
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


class EntrySizingTests(unittest.TestCase):
    def test_fixed_entry_margin_is_used_for_new_orders(self) -> None:
        bot = LapsBot.__new__(LapsBot)
        bot.config = _make_config(0.10)
        bot.exchange = _ExchangeEntryStub(15.0)
        bot.position_states = {}
        bot._emit = lambda *args, **kwargs: None  # type: ignore[method-assign]
        bot._signal_for_symbol = lambda symbol, emit_event=True: _signal_long()  # type: ignore[method-assign]

        opened = bot._open_new_position(set(), ["ADA/USDT:USDT"])
        self.assertTrue(opened)
        self.assertEqual(bot.exchange.choose_calls[0][1], 0.10)  # type: ignore[attr-defined]

    def test_fixed_entry_margin_skips_when_free_balance_is_insufficient(self) -> None:
        bot = LapsBot.__new__(LapsBot)
        bot.config = _make_config(0.10)
        bot.exchange = _ExchangeEntryStub(0.05)
        bot.position_states = {}
        emitted: list[str] = []

        def _capture(event_type: str, message: str, payload=None, severity: str = "info") -> None:
            emitted.append(event_type)

        bot._emit = _capture  # type: ignore[method-assign]
        bot._signal_for_symbol = lambda symbol, emit_event=True: _signal_long()  # type: ignore[method-assign]

        opened = bot._open_new_position(set(), ["ADA/USDT:USDT"])
        self.assertFalse(opened)
        self.assertEqual(bot.exchange.choose_calls, [])  # type: ignore[attr-defined]
        self.assertIn("entry_skipped", emitted)


if __name__ == "__main__":
    unittest.main()
