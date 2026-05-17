from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laps_bot.bot import LapsBot
from laps_bot.config import BotConfig
from laps_bot.models import PositionState, Trend
from laps_bot.strategy import TrendSignal


class _ExchangeNoop:
    def close_position(self, position: PositionState) -> dict:
        return {"id": "close-order"}

    def free_spot_usdt(self) -> float:
        return 0.0

    def total_spot_usdt(self) -> float:
        return 80.0

    def total_futures_usdt(self) -> float:
        return 20.0

    def free_futures_usdt(self) -> float:
        return 5.0


def _make_config() -> BotConfig:
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
        max_positions=1,
        balance_risk_pct=1.0,
        fixed_entry_margin_usdt=0.0,
        leverage=20,
        use_max_leverage_per_symbol=True,
        target_roi_pct=1000.0,
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
        entry_scan_batch=80,
        log_level="INFO",
        telemetry_dir="runtime",
        panel_host="0.0.0.0",
        panel_port=8080,
    )


def _signal(
    *,
    trend: Trend,
    crossover: Trend | None,
    latest_crossover: Trend | None,
    previous_crossover: Trend | None,
) -> TrendSignal:
    return TrendSignal(
        trend=trend,
        crossover=crossover,
        latest_crossover=latest_crossover,
        previous_crossover=previous_crossover,
        fast_ema=1.0,
        slow_ema=1.0,
    )


class ReinforcementTriggerTests(unittest.TestCase):
    def _make_bot(self) -> tuple[LapsBot, list[str]]:
        bot = LapsBot.__new__(LapsBot)
        bot.config = _make_config()
        bot.exchange = _ExchangeNoop()
        bot.position_states = {}
        bot._emit = lambda *args, **kwargs: None  # type: ignore[method-assign]
        executed: list[str] = []
        bot._handle_reinforcement = lambda symbol, base_trend, state: executed.append(symbol)  # type: ignore[method-assign]
        return bot, executed

    def test_sequence_history_alone_does_not_trigger_3x(self) -> None:
        bot, executed = self._make_bot()
        symbol = "ADA/USDT:USDT"
        state = bot._state_for_symbol(symbol)
        state.initial_entry_usdt = 10.0
        state.reinforcement_alert = False
        state.reinforcement_done = False
        bot._signal_for_symbol = lambda _symbol: _signal(  # type: ignore[method-assign]
            trend=Trend.LONG,
            crossover=None,
            latest_crossover=Trend.LONG,
            previous_crossover=Trend.SHORT,
        )

        position = PositionState(
            symbol=symbol,
            side="long",
            contracts=1.0,
            entry_price=1.0,
            unrealized_pnl=0.05,
            initial_margin=10.0,
            mark_price=1.0,
            liquidation_price=0.5,
            margin_ratio_pct=80.0,
        )
        bot._manage_single_position(position)

        self.assertEqual(executed, [])
        self.assertFalse(state.reinforcement_alert)

    def test_sequence_history_with_existing_alert_triggers_3x(self) -> None:
        bot, executed = self._make_bot()
        symbol = "ADA/USDT:USDT"
        state = bot._state_for_symbol(symbol)
        state.initial_entry_usdt = 10.0
        state.reinforcement_alert = True
        state.reinforcement_done = False
        bot._signal_for_symbol = lambda _symbol: _signal(  # type: ignore[method-assign]
            trend=Trend.LONG,
            crossover=None,
            latest_crossover=Trend.LONG,
            previous_crossover=Trend.SHORT,
        )

        position = PositionState(
            symbol=symbol,
            side="long",
            contracts=1.0,
            entry_price=1.0,
            unrealized_pnl=0.05,
            initial_margin=10.0,
            mark_price=1.0,
            liquidation_price=0.5,
            margin_ratio_pct=80.0,
        )
        bot._manage_single_position(position)

        self.assertEqual(executed, [symbol])


if __name__ == "__main__":
    unittest.main()
