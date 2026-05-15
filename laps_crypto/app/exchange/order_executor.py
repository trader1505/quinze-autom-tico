"""Deterministic order execution gateway with close guard enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging

from ..core.config import TradingConfig
from ..core.guards import can_close_position
from ..core.models import (
    CloseDecision,
    OrderRequest,
    OrderResult,
    Position,
    PositionStatus,
    PriceEstimate,
)
from .binance_client import BinanceClient


@dataclass
class OrderExecutor:
    """Routes open/close actions while enforcing non-loss close rule."""

    config: TradingConfig
    client: BinanceClient
    logger: logging.Logger

    def execute_open(self, order: OrderRequest, mark_price: Decimal | None = None) -> OrderResult:
        """Executes an opening order with deterministic validation."""
        if order.reduce_only:
            return OrderResult(
                accepted=False,
                message_pt_br="Ordem de abertura inválida: reduce_only deve ser falso.",
                executed_price=None,
            )
        self.client.submit_order(order)
        price = self.client.get_mark_price(order.symbol) if mark_price is None else mark_price
        return OrderResult(
            accepted=True,
            message_pt_br="Ordem de abertura enviada com sucesso.",
            executed_price=price,
        )

    def evaluate_close(
        self,
        *,
        position: Position,
        mark_price: Decimal,
        funding_cost: Decimal,
    ) -> CloseDecision:
        """Evaluates whether close is allowed by the non-loss rule."""
        estimate = PriceEstimate(
            mark_price=mark_price,
            exit_fee_rate_pct=self.config.taker_fee_pct,
            slippage_rate_pct=self.config.default_slippage_pct,
        )
        return can_close_position(
            position=position,
            estimate=estimate,
            funding_cost=funding_cost,
            min_net_profit_pct=self.config.min_close_profit_pct,
        )

    def execute_close_if_safe(
        self,
        *,
        position: Position,
        mark_price: Decimal,
        funding_cost: Decimal,
    ) -> OrderResult:
        """Executes close order only when guard allows it."""
        decision = self.evaluate_close(
            position=position,
            mark_price=mark_price,
            funding_cost=funding_cost,
        )
        if not decision.allowed:
            self.logger.warning(
                "Fechamento negado para %s: lucro_liquido=%.6f%% minimo=%.4f%%",
                position.symbol,
                float(decision.breakdown.net_profit_pct),
                float(decision.min_required_pct),
            )
            return OrderResult(
                accepted=False,
                message_pt_br=decision.reason_pt_br,
                executed_price=None,
                close_decision=decision,
            )

        order = OrderRequest(
            symbol=position.symbol,
            side=position.side.opposite,
            quantity=position.quantity,
            reduce_only=True,
        )
        self.client.submit_order(order)
        position.status = PositionStatus.CLOSED
        position.mark_price = mark_price
        self.logger.info("Fechamento executado para %s com segurança.", position.symbol)
        return OrderResult(
            accepted=True,
            message_pt_br="Fechamento executado com lucro líquido acima do mínimo.",
            executed_price=mark_price,
            close_decision=decision,
        )
