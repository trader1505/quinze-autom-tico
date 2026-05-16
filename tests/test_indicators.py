from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laps_bot.indicators import trend_from_closes
from laps_bot.models import Trend


class IndicatorTests(unittest.TestCase):
    def test_long_trend(self) -> None:
        closes = list(range(1, 40))
        self.assertEqual(trend_from_closes(closes, 12, 26), Trend.LONG)

    def test_short_trend(self) -> None:
        closes = list(range(40, 0, -1))
        self.assertEqual(trend_from_closes(closes, 12, 26), Trend.SHORT)


if __name__ == "__main__":
    unittest.main()
