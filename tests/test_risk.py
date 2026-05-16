from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laps_bot.risk import (
    margin_topup_usdt,
    should_add_margin,
    should_rebalance_after_recovery,
    split_8020,
    target_entry_usdt,
)


class RiskTests(unittest.TestCase):
    def test_target_entry(self) -> None:
        self.assertAlmostEqual(target_entry_usdt(100, 1), 1.0)

    def test_topup(self) -> None:
        self.assertAlmostEqual(margin_topup_usdt(50, 20), 10.0)

    def test_margin_trigger(self) -> None:
        self.assertTrue(should_add_margin(-70, -60, 0, 4))
        self.assertFalse(should_add_margin(-50, -60, 0, 4))
        self.assertFalse(should_add_margin(-70, -60, 4, 4))

    def test_recovery(self) -> None:
        self.assertTrue(should_rebalance_after_recovery(-30, -31, 1))
        self.assertFalse(should_rebalance_after_recovery(-40, -31, 1))
        self.assertFalse(should_rebalance_after_recovery(-30, -31, 0))

    def test_split(self) -> None:
        spot, futures = split_8020(100, 80, 20)
        self.assertAlmostEqual(spot, 80.0)
        self.assertAlmostEqual(futures, 20.0)


if __name__ == "__main__":
    unittest.main()
