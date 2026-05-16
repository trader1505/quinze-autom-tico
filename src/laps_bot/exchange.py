from __future__ import annotations

import logging
import math
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
        if config.sandbox:
            self.exchange.set_sandbox_mode(True)
        self.exchange.load_markets()

    def fetch_closes(self, symbol: str, timeframe: str, limit: int) -> list[float]:
        candles = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return [float(candle[4]) for candle in candles]

    def fetch_last_price(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        return float(ticker["last"])

    def fetch_futures_balance(self) -> dict:
        return self.exchange.fetch_balance({"type": "future"})

    def fetch_spot_balance(self) -> dict:
        return self.exchange.fetch_balance({"type": "spot"})

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
            entry_price = float(item.get("entryPrice") or 0.0)
            unrealized_pnl = float(item.get("unrealizedPnl") or 0.0)
            initial_margin = float(item.get("initialMargin") or 0.0)
            open_positions.append(
                PositionState(
                    symbol=symbol,
                    side=side,
                    contracts=contracts,
                    entry_price=entry_price,
                    unrealized_pnl=unrealized_pnl,
                    initial_margin=initial_margin,
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

    def ensure_leverage(self, symbol: str, requested_leverage: int) -> int:
        cached = self._leverage_cache.get(symbol)
        if cached == requested_leverage:
            return cached
        response = self.exchange.set_leverage(requested_leverage, symbol)
        applied = int(response.get("leverage") or requested_leverage)
        if applied != requested_leverage:
            LOG.warning(
                "Requested leverage %s on %s but exchange applied %s.",
                requested_leverage,
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
        leverage: int,
    ) -> tuple[str, float, float, float]:
        if target_margin_usdt <= 0:
            raise ValueError("Target size must be positive.")

        target_margin = Decimal(str(target_margin_usdt))
        leverage_dec = Decimal(str(leverage))
        target_notional = target_margin * leverage_dec
        min_margin_required: Decimal | None = None
        nearest: tuple[Decimal, str, float, float, float] | None = None

        for symbol in symbols:
            try:
                applied_leverage = self.ensure_leverage(symbol, leverage)
            except Exception as exc:
                LOG.warning("Cannot set leverage on %s: %s", symbol, exc)
                continue

            applied_leverage_dec = Decimal(str(applied_leverage))
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
                nearest = (delta, symbol, amount_f, float(price), float(used_margin))

            # "Exato": o bot só aceita se o valor de margem estiver no alvo.
            if math.isclose(float(used_margin), target_margin_usdt, rel_tol=0.0, abs_tol=1e-8):
                return symbol, amount_f, float(price), float(used_margin)

        details = [
            "No symbol can place an order with exactly the configured margin target.",
            f"Requested margin target: {target_margin_usdt:.8f} USDT at {leverage}x.",
        ]
        if min_margin_required is not None:
            details.append(f"Minimum margin required (approx.): {float(min_margin_required):.8f} USDT.")
        if nearest is not None:
            _, sym, _, _, nearest_margin = nearest
            details.append(f"Nearest match found on {sym}: {nearest_margin:.8f} USDT margin.")
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
