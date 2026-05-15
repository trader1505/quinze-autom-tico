"""Binance client with paper/live execution modes."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import hmac
import json
from typing import Any, Dict, List
import urllib.error
import urllib.parse
import urllib.request
import time

from ..core.config import TradingConfig
from ..core.models import AccountSnapshot, OrderRequest, Position, Side


class BinanceApiError(RuntimeError):
    """Raised when Binance API returns an error."""


@dataclass
class BinanceClient:
    """Exchange adapter supporting deterministic paper mode and Binance live mode."""

    execution_mode: str = "paper"
    use_testnet: bool = True
    api_key: str = ""
    api_secret: str = ""
    recv_window_ms: int = 5000
    taker_fee_pct: Decimal = Decimal("0.04")
    balances: Dict[str, Decimal] = field(default_factory=dict)
    prices: Dict[str, Decimal] = field(default_factory=dict)
    _positions: Dict[str, Position] = field(default_factory=dict)
    _orders: List[OrderRequest] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.execution_mode = self.execution_mode.lower().strip()
        if self.execution_mode not in {"paper", "live"}:
            raise ValueError("execution_mode deve ser 'paper' ou 'live'.")
        self.balances = {k: Decimal(str(v)) for k, v in self.balances.items()}
        self.prices = {k: Decimal(str(v)) for k, v in self.prices.items()}

    @classmethod
    def from_config(cls, config: TradingConfig) -> "BinanceClient":
        return cls(
            execution_mode=config.execution_mode,
            use_testnet=config.use_binance_testnet,
            api_key=config.binance_api_key,
            api_secret=config.binance_api_secret,
            recv_window_ms=config.binance_recv_window_ms,
            taker_fee_pct=config.taker_fee_pct,
            balances={config.base_asset: Decimal("100000")},
            prices={config.default_symbol: Decimal("65000")},
        )

    @property
    def is_live(self) -> bool:
        return self.execution_mode == "live"

    def get_balance(self, asset: str) -> Decimal:
        if not self.is_live:
            return self.balances.get(asset, Decimal("0"))

        balances = self._request_signed("GET", "/fapi/v2/balance")
        for item in balances:
            if item.get("asset", "").upper() == asset.upper():
                return Decimal(str(item.get("availableBalance", "0")))
        return Decimal("0")

    def set_balance(self, asset: str, value: Decimal) -> None:
        if self.is_live:
            raise RuntimeError("Alteração manual de saldo não é permitida em modo live.")
        self.balances[asset] = Decimal(value)

    def get_mark_price(self, symbol: str) -> Decimal:
        if not self.is_live:
            return Decimal(self.prices[symbol])

        payload = self._request_public("GET", "/fapi/v1/premiumIndex", {"symbol": symbol})
        return Decimal(str(payload["markPrice"]))

    def set_mark_price(self, symbol: str, value: Decimal) -> None:
        if self.is_live:
            raise RuntimeError("Alteração manual de preço não é permitida em modo live.")
        mark = Decimal(value)
        self.prices[symbol] = mark
        if symbol in self._positions:
            self._positions[symbol].mark_price = mark

    def get_position(self, symbol: str) -> Position | None:
        if not self.is_live:
            return self._positions.get(symbol)

        for position in self.list_positions():
            if position.symbol == symbol:
                return position
        return None

    def list_positions(self) -> List[Position]:
        if not self.is_live:
            return [self._positions[symbol] for symbol in sorted(self._positions.keys())]

        rows = self._request_signed("GET", "/fapi/v2/positionRisk")
        results: List[Position] = []
        for row in rows:
            quantity_signed = Decimal(str(row.get("positionAmt", "0")))
            if quantity_signed == 0:
                continue
            side = Side.LONG if quantity_signed > 0 else Side.SHORT
            results.append(
                Position(
                    symbol=str(row["symbol"]),
                    side=side,
                    quantity=abs(quantity_signed),
                    entry_price=Decimal(str(row.get("entryPrice", "0"))),
                    mark_price=Decimal(str(row.get("markPrice", "0"))),
                    entry_fee_rate_pct=self.taker_fee_pct,
                )
            )
        return results

    def get_account_snapshot(self, base_asset: str = "USDT") -> AccountSnapshot:
        if not self.is_live:
            equity = self.get_balance(base_asset)
            used_collateral = Decimal("0")
            for position in self._positions.values():
                used_collateral += position.entry_notional
                equity += position.gross_pnl
            return AccountSnapshot(
                equity=equity,
                free_collateral=equity - used_collateral,
                used_collateral=used_collateral,
            )

        account = self._request_signed("GET", "/fapi/v2/account")
        equity = Decimal(str(account.get("totalMarginBalance", "0")))
        free_collateral = Decimal(str(account.get("availableBalance", "0")))
        used_collateral = Decimal(str(account.get("totalPositionInitialMargin", "0"))) + Decimal(
            str(account.get("totalOpenOrderInitialMargin", "0"))
        )
        if used_collateral == 0 and equity > free_collateral:
            used_collateral = equity - free_collateral
        return AccountSnapshot(
            equity=equity,
            free_collateral=free_collateral,
            used_collateral=used_collateral,
        )

    def submit_order(self, order: OrderRequest, entry_fee_rate_pct: Decimal = Decimal("0.04")) -> None:
        self._orders.append(order)
        if self.is_live:
            self._submit_order_live(order)
            return

        price = self.get_mark_price(order.symbol)
        existing = self._positions.get(order.symbol)

        if order.reduce_only:
            if existing is None:
                raise ValueError("Reduce-only rejeitado: não existe posição aberta.")
            if order.side != existing.side.opposite:
                raise ValueError("Reduce-only rejeitado: lado inválido para fechamento.")
            if order.quantity >= existing.quantity:
                self._positions.pop(order.symbol, None)
            else:
                existing.quantity -= order.quantity
                existing.mark_price = price
            return

        if existing is None:
            self._positions[order.symbol] = Position(
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                entry_price=price,
                mark_price=price,
                entry_fee_rate_pct=entry_fee_rate_pct,
            )
            return

        if existing.side == order.side:
            total_qty = existing.quantity + order.quantity
            weighted_entry = (
                (existing.entry_price * existing.quantity) + (price * order.quantity)
            ) / total_qty
            existing.quantity = total_qty
            existing.entry_price = weighted_entry
            existing.mark_price = price
            return

        if order.quantity < existing.quantity:
            existing.quantity -= order.quantity
            existing.mark_price = price
            return

        if order.quantity == existing.quantity:
            self._positions.pop(order.symbol, None)
            return

        flipped_qty = order.quantity - existing.quantity
        self._positions[order.symbol] = Position(
            symbol=order.symbol,
            side=order.side,
            quantity=flipped_qty,
            entry_price=price,
            mark_price=price,
            entry_fee_rate_pct=entry_fee_rate_pct,
        )

    def order_history(self) -> List[OrderRequest]:
        """Returns immutable-like view of submitted orders."""
        return list(self._orders)

    def _submit_order_live(self, order: OrderRequest) -> None:
        self._assert_live_credentials()
        params = {
            "symbol": order.symbol,
            "side": "BUY" if order.side == Side.LONG else "SELL",
            "type": "MARKET",
            "quantity": self._format_decimal(order.quantity),
            "reduceOnly": "true" if order.reduce_only else "false",
            "newOrderRespType": "RESULT",
        }
        self._request_signed("POST", "/fapi/v1/order", params)

    def _request_public(self, method: str, path: str, params: Dict[str, Any] | None = None) -> Any:
        return self._request(method=method, path=path, params=params or {}, signed=False)

    def _request_signed(self, method: str, path: str, params: Dict[str, Any] | None = None) -> Any:
        return self._request(method=method, path=path, params=params or {}, signed=True)

    def _request(self, *, method: str, path: str, params: Dict[str, Any], signed: bool) -> Any:
        if signed:
            self._assert_live_credentials()
            params = dict(params)
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = self.recv_window_ms
            query = urllib.parse.urlencode(params, doseq=True)
            signature = hmac.new(
                self.api_secret.encode("utf-8"),
                query.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            params["signature"] = signature

        query_string = urllib.parse.urlencode(params, doseq=True)
        base_url = "https://testnet.binancefuture.com" if self.use_testnet else "https://fapi.binance.com"
        url = f"{base_url}{path}"
        data: bytes | None = None
        if method in {"GET", "DELETE"}:
            if query_string:
                url = f"{url}?{query_string}"
        else:
            data = query_string.encode("utf-8")

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if signed:
            headers["X-MBX-APIKEY"] = self.api_key

        request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise BinanceApiError(f"Erro HTTP Binance ({exc.code}): {body}") from exc
        except urllib.error.URLError as exc:
            raise BinanceApiError(f"Falha de rede ao chamar Binance: {exc.reason}") from exc

    def _assert_live_credentials(self) -> None:
        if not self.api_key or not self.api_secret:
            raise BinanceApiError(
                "Credenciais Binance ausentes. Defina BINANCE_API_KEY e BINANCE_API_SECRET."
            )

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        normalized = value.normalize()
        as_string = format(normalized, "f")
        return as_string.rstrip("0").rstrip(".") if "." in as_string else as_string
