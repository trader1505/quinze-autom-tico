"""Exchange gateways (Binance live + simulation)."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import requests

from .models import BalanceSnapshot, OrderIntent, Position, Side, TransferIntent


class Gateway(Protocol):
    def get_recent_closes(self, symbol: str, interval: str, limit: int = 100) -> list[float]:
        ...

    def get_balances(self) -> BalanceSnapshot:
        ...

    def get_position(self, symbol: str) -> Position:
        ...

    def place_order(self, intent: OrderIntent) -> list[dict]:
        ...

    def transfer(self, intent: TransferIntent) -> dict:
        ...


class BinanceGateway:
    def __init__(self, api_key: str, api_secret: str, recv_window: int = 5_000):
        self.api_key = api_key
        self.api_secret = api_secret.encode("utf-8")
        self.recv_window = recv_window
        self._quantity_precision_cache: dict[str, int] = {}

    def _sign(self, params: dict[str, str | int | float]) -> str:
        query = urlencode(params, doseq=True)
        return hmac.new(self.api_secret, query.encode("utf-8"), hashlib.sha256).hexdigest()

    def _request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, str | int | float] | None = None,
        signed: bool = False,
        market: str = "futures",
    ) -> dict | list:
        params = params or {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = self.recv_window
            params["signature"] = self._sign(params)

        if market == "futures":
            base_url = "https://fapi.binance.com"
        else:
            base_url = "https://api.binance.com"

        headers = {"X-MBX-APIKEY": self.api_key}
        response = requests.request(
            method=method,
            url=f"{base_url}{path}",
            params=params,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def get_recent_closes(self, symbol: str, interval: str, limit: int = 100) -> list[float]:
        data = self._request(
            method="GET",
            path="/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            signed=False,
        )
        return [float(item[4]) for item in data]

    def get_balances(self) -> BalanceSnapshot:
        futures = self._request(
            method="GET",
            path="/fapi/v2/account",
            signed=True,
            market="futures",
        )
        spot = self._request(
            method="GET",
            path="/api/v3/account",
            signed=True,
            market="spot",
        )
        spot_usdt = 0.0
        for bal in spot["balances"]:
            if bal["asset"] == "USDT":
                spot_usdt = float(bal["free"])
                break

        futures_wallet = float(futures["totalWalletBalance"])
        futures_free = float(futures["availableBalance"])
        margin_balance = float(futures["totalMarginBalance"])
        maint_margin = float(futures["totalMaintMargin"])
        margin_ratio = (maint_margin / margin_balance) if margin_balance > 0 else 0.0

        return BalanceSnapshot(
            spot_usdt=spot_usdt,
            futures_wallet_usdt=futures_wallet,
            futures_free_usdt=futures_free,
            margin_ratio=margin_ratio,
        )

    def get_position(self, symbol: str) -> Position:
        positions = self._request(
            method="GET",
            path="/fapi/v2/positionRisk",
            signed=True,
            market="futures",
        )
        for item in positions:
            if item["symbol"] != symbol:
                continue
            qty = float(item["positionAmt"])
            if abs(qty) < 1e-12:
                continue
            side = Side.LONG if qty > 0 else Side.SHORT
            return Position(
                side=side,
                quantity=abs(qty),
                entry_price=float(item["entryPrice"]),
                mark_price=float(item["markPrice"]),
            )
        mark_price = self._get_mark_price(symbol)
        return Position(side=Side.FLAT, quantity=0.0, entry_price=0.0, mark_price=mark_price)

    def _get_mark_price(self, symbol: str) -> float:
        data = self._request(
            method="GET",
            path="/fapi/v1/ticker/price",
            params={"symbol": symbol},
            signed=False,
        )
        return float(data["price"])

    def _get_quantity_precision(self, symbol: str) -> int:
        if symbol in self._quantity_precision_cache:
            return self._quantity_precision_cache[symbol]
        info = self._request(method="GET", path="/fapi/v1/exchangeInfo", signed=False)
        for data in info["symbols"]:
            if data["symbol"] == symbol:
                precision = int(data["quantityPrecision"])
                self._quantity_precision_cache[symbol] = precision
                return precision
        raise ValueError(f"Symbol not found on Binance futures: {symbol}")

    def _round_quantity(self, symbol: str, notional_usdt: float) -> float:
        mark_price = self._get_mark_price(symbol)
        if mark_price <= 0:
            raise ValueError("Invalid mark price")
        precision = self._get_quantity_precision(symbol)
        qty = notional_usdt / mark_price
        return round(qty, precision)

    def place_order(self, intent: OrderIntent) -> list[dict]:
        side = "BUY" if intent.side == Side.LONG else "SELL"
        slices = max(intent.slices, 1)
        one_slice_notional = intent.notional_usdt / slices
        responses: list[dict] = []
        for _ in range(slices):
            qty = self._round_quantity(intent.symbol, one_slice_notional)
            if qty <= 0:
                continue
            response = self._request(
                method="POST",
                path="/fapi/v1/order",
                params={
                    "symbol": intent.symbol,
                    "side": side,
                    "type": "MARKET",
                    "quantity": qty,
                    "reduceOnly": "true" if intent.reduce_only else "false",
                    "newOrderRespType": "RESULT",
                },
                signed=True,
                market="futures",
            )
            responses.append(response)
            time.sleep(0.1)
        return responses

    def transfer(self, intent: TransferIntent) -> dict:
        transfer_type = 1 if intent.from_wallet == "spot" else 2
        return self._request(
            method="POST",
            path="/sapi/v1/futures/transfer",
            params={
                "asset": "USDT",
                "amount": intent.amount_usdt,
                "type": transfer_type,
            },
            signed=True,
            market="spot",
        )


@dataclass
class SimulationGateway:
    close_prices: list[float]
    balances: BalanceSnapshot
    position: Position

    def get_recent_closes(self, symbol: str, interval: str, limit: int = 100) -> list[float]:
        _ = symbol, interval
        return self.close_prices[-limit:]

    def get_balances(self) -> BalanceSnapshot:
        return self.balances

    def get_position(self, symbol: str) -> Position:
        _ = symbol
        return self.position

    def place_order(self, intent: OrderIntent) -> list[dict]:
        mark = self.position.mark_price if self.position.mark_price > 0 else self.close_prices[-1]
        qty = intent.notional_usdt / mark if mark > 0 else 0.0
        if intent.reduce_only:
            if self.position.side != Side.FLAT and self.position.side != intent.side:
                self.position.quantity = max(0.0, self.position.quantity - qty)
                if self.position.quantity == 0:
                    self.position.side = Side.FLAT
                    self.position.entry_price = 0.0
            return [{"status": "FILLED", "reduceOnly": True, "simulated": True}]

        if self.position.side == Side.FLAT:
            self.position.side = intent.side
            self.position.quantity = qty
            self.position.entry_price = mark
        elif self.position.side == intent.side:
            old_notional = self.position.quantity * self.position.entry_price
            add_notional = qty * mark
            total_qty = self.position.quantity + qty
            if total_qty > 0:
                self.position.entry_price = (old_notional + add_notional) / total_qty
            self.position.quantity = total_qty
        return [{"status": "FILLED", "reduceOnly": False, "simulated": True}]

    def transfer(self, intent: TransferIntent) -> dict:
        amount = min(intent.amount_usdt, self.balances.spot_usdt if intent.from_wallet == "spot" else self.balances.futures_wallet_usdt)
        if amount <= 0:
            return {"success": False, "reason": "insufficient_balance", "simulated": True}

        if intent.from_wallet == "spot":
            self.balances.spot_usdt -= amount
            self.balances.futures_wallet_usdt += amount
            self.balances.futures_free_usdt += amount
        else:
            self.balances.spot_usdt += amount
            self.balances.futures_wallet_usdt -= amount
            self.balances.futures_free_usdt = max(0.0, self.balances.futures_free_usdt - amount)
        return {"success": True, "amount": amount, "simulated": True}
