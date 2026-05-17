from __future__ import annotations

import logging
import math
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

import ccxt

from laps_bot.config import BotConfig
from laps_bot.models import PositionState, Trend

LOG = logging.getLogger(__name__)


class ExchangeGateway:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self._leverage_cache: dict[str, int] = {}
        self._max_leverage_cache: dict[str, int] = {}
        self.exchange = ccxt.binanceusdm(
            {
                "apiKey": config.api_key,
                "secret": config.api_secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "future",
                },
            }
        )
        self.spot_exchange = ccxt.binance(
            {
                "apiKey": config.api_key,
                "secret": config.api_secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                },
            }
        )
        if config.sandbox:
            self.exchange.set_sandbox_mode(True)
            self.spot_exchange.set_sandbox_mode(True)
        self.exchange.load_markets()
        self.spot_exchange.load_markets()

    def discover_tradable_symbols(self, limit: int, preferred_symbols: Iterable[str] = ()) -> list[str]:
        known_markets = self.exchange.markets
        preferred = [symbol for symbol in preferred_symbols if symbol in known_markets]
        if not self.config.scan_all_symbols:
            return preferred

        symbols: list[str] = []
        for symbol, market in known_markets.items():
            if not bool(market.get("active", True)):
                continue
            if not bool(market.get("contract", False)):
                continue
            if not bool(market.get("swap", False)):
                continue
            if not bool(market.get("linear", False)):
                continue
            underlying_type = str((market.get("info") or {}).get("underlyingType") or "").upper()
            if underlying_type and underlying_type != "COIN":
                # Skip TradFi/stock perps and other non-crypto underlyings that may
                # require additional agreements and can break automated trading.
                continue
            quote = str(market.get("quote") or "")
            settle = str(market.get("settle") or "")
            if quote != "USDT" and settle != "USDT":
                continue
            symbols.append(symbol)

        volumes: dict[str, float] = {}
        try:
            tickers = self.exchange.fetch_tickers(symbols)
            for symbol, ticker in tickers.items():
                quote_volume = ticker.get("quoteVolume")
                if quote_volume is None:
                    quote_volume = ticker.get("baseVolume")
                try:
                    volumes[symbol] = float(quote_volume or 0.0)
                except (TypeError, ValueError):
                    volumes[symbol] = 0.0
        except Exception as exc:
            LOG.warning("Failed to fetch futures tickers for ranking symbols: %s", exc)

        ranked = sorted(symbols, key=lambda item: volumes.get(item, 0.0), reverse=True)
        ordered = preferred + [symbol for symbol in ranked if symbol not in preferred]
        if limit <= 0:
            return ordered
        return ordered[:limit]

    def fetch_closes(self, symbol: str, timeframe: str, limit: int) -> list[float]:
        candles = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return [float(candle[4]) for candle in candles]

    def fetch_last_price(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        return float(ticker["last"])

    def fetch_futures_balance(self) -> dict:
        return self.exchange.fetch_balance({"type": "future"})

    def fetch_spot_balance(self) -> dict:
        # Spot balance must come from spot API to avoid futures-only wallet projection.
        return self.spot_exchange.fetch_balance()

    def free_futures_usdt(self) -> float:
        balance = self.fetch_futures_balance()
        return float(balance["free"].get("USDT", 0.0))

    def total_futures_usdt(self) -> float:
        balance = self.fetch_futures_balance()
        return float(balance["total"].get("USDT", 0.0))

    def total_spot_usdt(self) -> float:
        balance = self.fetch_spot_balance()
        return float(balance["total"].get("USDT", 0.0))

    def free_spot_usdt(self) -> float:
        balance = self.fetch_spot_balance()
        return float(balance["free"].get("USDT", 0.0))

    def account_margin_ratio_pct(self) -> float | None:
        balance = self.fetch_futures_balance()
        info = balance.get("info") or {}

        def _to_float(value: object) -> float | None:
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        total_maint_margin = _to_float(info.get("totalMaintMargin"))
        total_margin_balance = _to_float(info.get("totalMarginBalance"))
        if total_maint_margin is not None and total_margin_balance and total_margin_balance > 0:
            return (total_maint_margin / total_margin_balance) * 100.0

        assets = info.get("assets")
        if isinstance(assets, list):
            maint_sum = 0.0
            balance_sum = 0.0
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                maint = _to_float(asset.get("maintMargin")) or 0.0
                margin_balance = _to_float(asset.get("marginBalance")) or 0.0
                maint_sum += maint
                balance_sum += margin_balance
            if balance_sum > 0:
                return (maint_sum / balance_sum) * 100.0
        return None

    def fetch_open_positions(self, symbols: Iterable[str]) -> list[PositionState]:
        positions = self.exchange.fetch_positions(list(symbols))
        open_positions: list[PositionState] = []
        for item in positions:
            contracts = float(item.get("contracts") or 0.0)
            if contracts <= 0:
                continue
            side = (item.get("side") or "").lower()
            if side not in {"long", "short"}:
                continue
            symbol = item["symbol"]
            leverage_raw = item.get("leverage")
            if leverage_raw is None:
                leverage_raw = (item.get("info") or {}).get("leverage")
            if leverage_raw is not None:
                try:
                    self._leverage_cache[symbol] = int(float(leverage_raw))
                except (TypeError, ValueError):
                    pass
            entry_price = float(item.get("entryPrice") or 0.0)
            unrealized_pnl = float(item.get("unrealizedPnl") or 0.0)
            initial_margin = float(item.get("initialMargin") or 0.0)
            mark_price_raw = item.get("markPrice")
            mark_price = float(mark_price_raw) if mark_price_raw is not None else None
            liquidation_price_raw = item.get("liquidationPrice")
            liquidation_price = float(liquidation_price_raw) if liquidation_price_raw is not None else None
            margin_ratio_raw = item.get("marginRatio")
            if margin_ratio_raw is None:
                margin_ratio_raw = (item.get("info") or {}).get("marginRatio")
            margin_ratio_pct: float | None
            if margin_ratio_raw is None:
                margin_ratio_pct = None
            else:
                raw = float(margin_ratio_raw)
                margin_ratio_pct = raw * 100 if raw <= 1.0 else raw
            open_positions.append(
                PositionState(
                    symbol=symbol,
                    side=side,
                    contracts=contracts,
                    entry_price=entry_price,
                    unrealized_pnl=unrealized_pnl,
                    initial_margin=initial_margin,
                    mark_price=mark_price,
                    liquidation_price=liquidation_price,
                    margin_ratio_pct=margin_ratio_pct,
                )
            )
        open_positions.sort(key=lambda p: p.symbol)
        return open_positions

    def fetch_open_position(self, symbols: Iterable[str]) -> PositionState | None:
        positions = self.fetch_open_positions(symbols)
        if not positions:
            return None
        return positions[0]

    def _amount_step(self, symbol: str) -> Decimal:
        market = self.exchange.market(symbol)
        precision = market.get("precision", {}).get("amount")
        if isinstance(precision, int):
            return Decimal("1").scaleb(-precision)
        min_amount = market.get("limits", {}).get("amount", {}).get("min")
        if min_amount:
            return Decimal(str(min_amount))
        return Decimal("0.000001")

    def _validate_limits(self, symbol: str, amount: float, cost: float) -> bool:
        market = self.exchange.market(symbol)
        amount_limits = market.get("limits", {}).get("amount", {})
        cost_limits = market.get("limits", {}).get("cost", {})
        min_amount = amount_limits.get("min")
        max_amount = amount_limits.get("max")
        min_cost = cost_limits.get("min")
        max_cost = cost_limits.get("max")
        if min_amount is not None and amount < float(min_amount):
            return False
        if max_amount is not None and amount > float(max_amount):
            return False
        if min_cost is not None and cost < float(min_cost):
            return False
        if max_cost is not None and cost > float(max_cost):
            return False
        return True

    def _max_leverage_from_brackets(self, symbol: str) -> int | None:
        market = self.exchange.market(symbol)
        market_id = str(market.get("id") or "").upper()
        try:
            raw = self.exchange.fapiPrivateGetLeverageBracket({"symbol": market_id})
        except Exception as exc:
            LOG.warning("Cannot read leverage bracket for %s: %s", symbol, exc)
            return None

        entries: list[dict] = []
        if isinstance(raw, list):
            entries = [item for item in raw if isinstance(item, dict)]
        elif isinstance(raw, dict):
            entries = [raw]

        brackets: list[dict] = []
        for entry in entries:
            entry_symbol = str(entry.get("symbol") or "").upper()
            if entry_symbol and entry_symbol != market_id:
                continue
            raw_brackets = entry.get("brackets")
            if isinstance(raw_brackets, list):
                brackets.extend(item for item in raw_brackets if isinstance(item, dict))

        max_leverage = 0
        for bracket in brackets:
            try:
                candidate = int(float(bracket.get("initialLeverage") or 0))
            except (TypeError, ValueError):
                continue
            if candidate > max_leverage:
                max_leverage = candidate
        if max_leverage > 0:
            return max_leverage

        market_max = market.get("limits", {}).get("leverage", {}).get("max")
        if market_max is None:
            return None
        try:
            candidate = int(float(market_max))
        except (TypeError, ValueError):
            return None
        return candidate if candidate > 0 else None

    def max_leverage_for_symbol(self, symbol: str) -> int:
        cached = self._max_leverage_cache.get(symbol)
        if cached is not None:
            return cached
        discovered = self._max_leverage_from_brackets(symbol)
        if discovered is None:
            discovered = self.config.leverage
        discovered = max(1, int(discovered))
        discovered = min(discovered, 125)
        self._max_leverage_cache[symbol] = discovered
        return discovered

    @staticmethod
    def _extract_leverage_bounds(error: Exception) -> tuple[int, int] | None:
        message = str(error).lower()
        match = re.search(r"between\s+(\d+)\s+and\s+(\d+)", message)
        if not match:
            return None
        lower = int(match.group(1))
        upper = int(match.group(2))
        if lower > upper:
            return None
        return lower, upper

    def ensure_leverage(self, symbol: str, requested_leverage: int | None = None) -> int:
        target = requested_leverage if requested_leverage is not None else self.config.leverage
        if self.config.use_max_leverage_per_symbol:
            target = self.max_leverage_for_symbol(symbol)
        market_max = self.exchange.market(symbol).get("limits", {}).get("leverage", {}).get("max")
        if market_max is not None:
            try:
                target = min(int(target), int(float(market_max)))
            except (TypeError, ValueError):
                target = int(target)
        target = max(1, int(target))
        cached = self._leverage_cache.get(symbol)
        if cached == target:
            return cached
        try:
            response = self.exchange.set_leverage(target, symbol)
        except Exception as exc:
            bounds = self._extract_leverage_bounds(exc)
            if bounds is not None:
                lower, upper = bounds
                adjusted_target = min(max(target, lower), upper)
                if adjusted_target != target:
                    LOG.warning(
                        "Leverage %s rejected on %s, retrying with %s based on exchange bounds %s-%s.",
                        target,
                        symbol,
                        adjusted_target,
                        lower,
                        upper,
                    )
                    try:
                        response = self.exchange.set_leverage(adjusted_target, symbol)
                    except Exception:
                        response = None
                    else:
                        applied = int(response.get("leverage") or adjusted_target)
                        self._leverage_cache[symbol] = applied
                        return applied
            if cached is not None:
                LOG.warning(
                    "Cannot set leverage on %s (%s). Reusing cached leverage %s.",
                    symbol,
                    exc,
                    cached,
                )
                return cached
            raise
        applied = int(response.get("leverage") or target)
        if applied != target:
            LOG.warning(
                "Requested leverage %s on %s but exchange applied %s.",
                target,
                symbol,
                applied,
            )
        self._leverage_cache[symbol] = applied
        return applied

    def _minimum_margin_for_symbol(self, symbol: str, leverage: Decimal, price: Decimal) -> Decimal | None:
        market = self.exchange.market(symbol)
        amount_limits = market.get("limits", {}).get("amount", {})
        cost_limits = market.get("limits", {}).get("cost", {})
        min_amount = amount_limits.get("min")
        min_cost = cost_limits.get("min")

        candidates: list[Decimal] = []
        if min_cost is not None:
            candidates.append(Decimal(str(min_cost)) / leverage)
        if min_amount is not None:
            candidates.append((Decimal(str(min_amount)) * price) / leverage)
        if not candidates:
            return None
        return max(candidates)

    def choose_symbol_and_amount_for_exact_margin(
        self,
        symbols: Iterable[str],
        target_margin_usdt: float,
        leverage: int | None = None,
    ) -> tuple[str, float, float, float]:
        if target_margin_usdt <= 0:
            raise ValueError("Target size must be positive.")

        target_margin = Decimal(str(target_margin_usdt))
        requested_leverage = leverage if leverage is not None else self.config.leverage
        tolerance_pct = Decimal(str(self.config.margin_match_tolerance_pct))
        min_margin_required: Decimal | None = None
        nearest: tuple[Decimal, str, float, float, float, int] | None = None

        for symbol in symbols:
            try:
                applied_leverage = self.ensure_leverage(symbol, requested_leverage)
            except Exception as exc:
                LOG.warning("Cannot set leverage on %s: %s", symbol, exc)
                continue

            applied_leverage_dec = Decimal(str(applied_leverage))
            target_notional = target_margin * applied_leverage_dec
            price = Decimal(str(self.fetch_last_price(symbol)))
            step = self._amount_step(symbol)
            if step <= 0:
                continue
            symbol_min_margin = self._minimum_margin_for_symbol(symbol, applied_leverage_dec, price)
            if symbol_min_margin is not None:
                if min_margin_required is None or symbol_min_margin < min_margin_required:
                    min_margin_required = symbol_min_margin

            raw_contracts = target_notional / price / step
            rounded_steps = raw_contracts.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            amount = (rounded_steps * step).normalize()
            if amount <= 0:
                continue
            amount_f = float(amount)
            notional = amount * price
            notional_f = float(notional)
            if not self._validate_limits(symbol, amount_f, notional_f):
                continue
            used_margin = notional / applied_leverage_dec
            delta = abs(used_margin - target_margin)
            if nearest is None or delta < nearest[0]:
                nearest = (delta, symbol, amount_f, float(price), float(used_margin), applied_leverage)

            # "Exato": o bot só aceita se o valor de margem estiver no alvo.
            if math.isclose(float(used_margin), target_margin_usdt, rel_tol=0.0, abs_tol=1e-8):
                return symbol, amount_f, float(price), float(used_margin)

        if nearest is not None and target_margin > 0 and tolerance_pct > 0:
            delta, symbol, amount_f, price_f, used_margin_f, applied_leverage = nearest
            drift_pct = (delta / target_margin) * Decimal("100")
            if drift_pct <= tolerance_pct:
                LOG.warning(
                    "Using nearest margin match on %s (requested %.8f, got %.8f, drift %.6f%%, leverage %sx).",
                    symbol,
                    target_margin_usdt,
                    used_margin_f,
                    float(drift_pct),
                    applied_leverage,
                )
                return symbol, amount_f, price_f, used_margin_f

        details = [
            "No symbol can place an order with exactly the configured margin target.",
            f"Requested margin target: {target_margin_usdt:.8f} USDT with requested leverage {requested_leverage}x.",
        ]
        if min_margin_required is not None:
            details.append(f"Minimum margin required (approx.): {float(min_margin_required):.8f} USDT.")
        if nearest is not None:
            _, sym, _, _, nearest_margin, nearest_leverage = nearest
            details.append(
                f"Nearest match found on {sym}: {nearest_margin:.8f} USDT margin (leverage {nearest_leverage}x)."
            )
        details.append(f"Configured margin tolerance: {self.config.margin_match_tolerance_pct:.4f}%.")
        raise RuntimeError(" ".join(details))

    def create_market_position(
        self,
        symbol: str,
        trend: Trend,
        amount: float,
        reduce_only: bool = False,
    ) -> dict:
        self.ensure_leverage(symbol, self.config.leverage)
        side = "buy" if trend == Trend.LONG else "sell"
        params = {"reduceOnly": reduce_only}
        LOG.info("Sending %s order: symbol=%s amount=%s reduceOnly=%s", side, symbol, amount, reduce_only)
        return self.exchange.create_order(symbol, "market", side, amount, None, params)

    def active_leverage(self, symbol: str) -> int:
        cached = self._leverage_cache.get(symbol)
        if cached is not None:
            return cached
        return self.ensure_leverage(symbol, self.config.leverage)

    def close_position(self, position: PositionState) -> dict:
        side = "sell" if position.side == "long" else "buy"
        params = {"reduceOnly": True}
        LOG.info("Closing %s position on %s with %s contracts", position.side, position.symbol, position.contracts)
        return self.exchange.create_order(position.symbol, "market", side, position.contracts, None, params)

    def transfer_usdt(self, amount: float, from_account: str, to_account: str) -> dict:
        if amount <= 0:
            raise ValueError("Transfer amount must be positive.")
        LOG.info("Transfer %.8f USDT from %s to %s", amount, from_account, to_account)
        return self.exchange.transfer("USDT", amount, from_account, to_account)
