from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

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

    def test_discover_symbols_skips_non_coin_underlyings(self) -> None:
        gateway = ExchangeGateway.__new__(ExchangeGateway)
        gateway.config = SimpleNamespace(scan_all_symbols=True)
        gateway.exchange = SimpleNamespace(
            markets={
                "BTC/USDT:USDT": {
                    "active": True,
                    "contract": True,
                    "swap": True,
                    "linear": True,
                    "quote": "USDT",
                    "settle": "USDT",
                    "info": {"underlyingType": "COIN"},
                },
                "AAPL/USDT:USDT": {
                    "active": True,
                    "contract": True,
                    "swap": True,
                    "linear": True,
                    "quote": "USDT",
                    "settle": "USDT",
                    "info": {"underlyingType": "STOCK"},
                },
            },
            fetch_tickers=lambda symbols: {symbol: {"quoteVolume": 1000.0} for symbol in symbols},
        )
        symbols = gateway.discover_tradable_symbols(limit=10, preferred_symbols=())
        self.assertEqual(symbols, ["BTC/USDT:USDT"])


if __name__ == "__main__":
    unittest.main()
