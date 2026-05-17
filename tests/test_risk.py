from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laps_bot.config import BotConfig
from laps_bot.risk import (
    margin_topup_usdt,
    should_add_margin,
    should_rebalance_after_recovery,
    split_8020,
    target_entry_usdt,
    validate_config,
)


class RiskTests(unittest.TestCase):
    def _make_config(self, max_positions: int, symbols: tuple[str, ...]) -> BotConfig:
        return BotConfig(
            api_key="k",
            api_secret="s",
            sandbox=True,
            symbols=symbols,
            timeframe="15m",
            fast_ma=12,
            slow_ma=26,
            max_positions=max_positions,
            balance_risk_pct=1.0,
            leverage=125,
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
            poll_seconds=5,
            log_level="INFO",
            telemetry_dir="runtime",
            panel_host="0.0.0.0",
            panel_port=8090,
        )

    def test_target_entry(self) -> None:
        self.assertAlmostEqual(target_entry_usdt(100, 1), 1.0)

    def test_topup(self) -> None:
        self.assertAlmostEqual(margin_topup_usdt(50, 20), 10.0)

    def test_margin_trigger(self) -> None:
        self.assertTrue(should_add_margin(-70, -60, 65, 60, 0, 4))
        self.assertFalse(should_add_margin(-70, -60, 55, 60, 0, 4))
        self.assertFalse(should_add_margin(-50, -60, 65, 60, 0, 4))
        self.assertFalse(should_add_margin(-70, -60, None, 60, 0, 4))
        self.assertFalse(should_add_margin(-70, -60, 65, 60, 4, 4))

    def test_recovery(self) -> None:
        self.assertTrue(should_rebalance_after_recovery(-30, -31, 1))
        self.assertFalse(should_rebalance_after_recovery(-40, -31, 1))
        self.assertFalse(should_rebalance_after_recovery(-30, -31, 0))

    def test_split(self) -> None:
        spot, futures = split_8020(100, 80, 20)
        self.assertAlmostEqual(spot, 80.0)
        self.assertAlmostEqual(futures, 20.0)

    def test_validate_config_accepts_multi_positions(self) -> None:
        cfg = self._make_config(max_positions=4, symbols=("BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT"))
        validate_config(cfg)

    def test_validate_config_rejects_positions_above_symbol_count(self) -> None:
        cfg = self._make_config(max_positions=3, symbols=("BTC/USDT:USDT", "ETH/USDT:USDT"))
        with self.assertRaises(ValueError):
            validate_config(cfg)


if __name__ == "__main__":
    unittest.main()
