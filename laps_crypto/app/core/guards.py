"""Safety guards for trading actions."""

from __future__ import annotations

from decimal import Decimal

from .models import CloseDecision, Position, PriceEstimate, ProfitabilityBreakdown, Side


def _to_notional(position: Position, price: Decimal) -> Decimal:
    return position.quantity * price


def calculate_profitability(
    *,
    position: Position,
    estimate: PriceEstimate,
    funding_cost: Decimal,
) -> ProfitabilityBreakdown:
    """Deterministic PnL calculator with explicit cost components."""
    entry_notional = _to_notional(position, position.entry_price)
    exit_notional = _to_notional(position, estimate.mark_price)

    if position.side == Side.LONG:
        gross_pnl = exit_notional - entry_notional
    else:
        gross_pnl = entry_notional - exit_notional

    entry_fee = entry_notional * position.entry_fee_rate_pct / Decimal("100")
    exit_fee = exit_notional * estimate.exit_fee_rate_pct / Decimal("100")
    slippage_cost = exit_notional * estimate.slippage_rate_pct / Decimal("100")

    total_costs = entry_fee + exit_fee + funding_cost + slippage_cost
    net_pnl = gross_pnl - total_costs

    if entry_notional == 0:
        net_profit_pct = Decimal("0")
    else:
        net_profit_pct = (net_pnl / entry_notional) * Decimal("100")

    return ProfitabilityBreakdown(
        gross_pnl=gross_pnl,
        entry_fee=entry_fee,
        exit_fee=exit_fee,
        funding_cost=funding_cost,
        slippage_cost=slippage_cost,
        net_pnl=net_pnl,
        net_profit_pct=net_profit_pct,
    )


def can_close_position(
    *,
    position: Position,
    estimate: PriceEstimate,
    funding_cost: Decimal,
    min_net_profit_pct: Decimal,
) -> CloseDecision:
    """
    Core non-negotiable rule:
    closing is allowed only when NET_PROFIT >= +0.1% (or configured threshold).
    """
    breakdown = calculate_profitability(
        position=position,
        estimate=estimate,
        funding_cost=funding_cost,
    )
    allowed = breakdown.net_profit_pct >= min_net_profit_pct

    if allowed:
        reason = "Fechamento autorizado: lucro líquido mínimo atingido."
    else:
        reason = "Fechamento bloqueado: lucro líquido abaixo do mínimo configurado."

    return CloseDecision(
        allowed=allowed,
        reason_pt_br=reason,
        breakdown=breakdown,
        min_required_pct=min_net_profit_pct,
    )
