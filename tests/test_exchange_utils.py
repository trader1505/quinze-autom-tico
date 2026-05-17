from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from laps_bot.exchange import ExchangeGateway


class ExchangeUtilsTests(unittest.TestCase):
    def test_extract_leverage_bounds_parses_exchange_error(self) -> None:
        exc = RuntimeError("binanceusdm leverage should be between 1 and 125")
        self.assertEqual(ExchangeGateway._extract_leverage_bounds(exc), (1, 125))

    def test_extract_leverage_bounds_returns_none_when_pattern_missing(self) -> None:
        exc = RuntimeError("some unrelated network error")
        self.assertIsNone(ExchangeGateway._extract_leverage_bounds(exc))


if __name__ == "__main__":
    unittest.main()
