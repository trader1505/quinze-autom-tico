from pathlib import Path
import sys
import unittest
from decimal import Decimal
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

    def test_account_margin_ratio_prefers_total_maint_and_balance(self) -> None:
        gateway = ExchangeGateway.__new__(ExchangeGateway)
        gateway.fetch_futures_balance = lambda: {  # type: ignore[method-assign]
            "info": {"totalMaintMargin": "57", "totalMarginBalance": "100"}
        }
        self.assertAlmostEqual(gateway.account_margin_ratio_pct() or 0.0, 57.0)

    def test_account_margin_ratio_falls_back_to_assets(self) -> None:
        gateway = ExchangeGateway.__new__(ExchangeGateway)
        gateway.fetch_futures_balance = lambda: {  # type: ignore[method-assign]
            "info": {"assets": [{"maintMargin": "3", "marginBalance": "10"}, {"maintMargin": "1", "marginBalance": "10"}]}
        }
        self.assertAlmostEqual(gateway.account_margin_ratio_pct() or 0.0, 20.0)

    def test_choose_symbol_uses_safeguarded_nearest_fallback_when_exact_is_impossible(self) -> None:
        gateway = ExchangeGateway.__new__(ExchangeGateway)
        gateway.config = SimpleNamespace(leverage=1, margin_match_tolerance_pct=0.25)
        gateway.ensure_leverage = lambda symbol, requested: 1  # type: ignore[method-assign]
        gateway.fetch_last_price = lambda symbol: 0.1  # type: ignore[method-assign]
        gateway._amount_step = lambda symbol: Decimal("1")  # type: ignore[method-assign]
        gateway._validate_limits = lambda symbol, amount, cost: True  # type: ignore[method-assign]
        gateway._minimum_margin_for_symbol = lambda symbol, leverage, price: None  # type: ignore[method-assign]

        symbol, _amount, _price, used_margin = gateway.choose_symbol_and_amount_for_exact_margin(["X/USDT:USDT"], 0.05, 1)
        self.assertEqual(symbol, "X/USDT:USDT")
        self.assertAlmostEqual(used_margin, 0.1)

    def test_choose_symbol_keeps_rejecting_when_nearest_fallback_is_too_far(self) -> None:
        gateway = ExchangeGateway.__new__(ExchangeGateway)
        gateway.config = SimpleNamespace(leverage=1, margin_match_tolerance_pct=0.25)
        gateway.ensure_leverage = lambda symbol, requested: 1  # type: ignore[method-assign]
        gateway.fetch_last_price = lambda symbol: 1.0  # type: ignore[method-assign]
        gateway._amount_step = lambda symbol: Decimal("1")  # type: ignore[method-assign]
        gateway._validate_limits = lambda symbol, amount, cost: True  # type: ignore[method-assign]
        gateway._minimum_margin_for_symbol = lambda symbol, leverage, price: None  # type: ignore[method-assign]

        with self.assertRaises(RuntimeError):
            gateway.choose_symbol_and_amount_for_exact_margin(["X/USDT:USDT"], 0.05, 1)


if __name__ == "__main__":
    unittest.main()
