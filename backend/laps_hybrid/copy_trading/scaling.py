"""Proportional scaling logic for investor copy trading."""

from __future__ import annotations

from .models import InvestorAccount, MasterTrade, ScalingDecision


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class ProportionalScalingEngine:
    """Scale master trades into investor-equivalent exposure."""

    def __init__(
        self,
        *,
        max_notional_per_trade_fraction: float = 0.25,
        safe_mode_exposure_multiplier: float = 1.0,
    ) -> None:
        self.max_notional_per_trade_fraction = max_notional_per_trade_fraction
        self.safe_mode_exposure_multiplier = safe_mode_exposure_multiplier

    def scale(self, master_trade: MasterTrade, investor: InvestorAccount) -> ScalingDecision:
        """Return investor-specific exposure for a master trade."""

        if investor.equity <= 0 or investor.available_balance <= 0:
            return self._skip(investor, "Investor has no available equity.")

        if master_trade.master_equity <= 0 or master_trade.notional <= 0:
            return self._skip(investor, "Master trade has invalid risk basis.")

        if master_trade.strategy_family not in investor.risk_profile.allowed_strategy_families:
            return self._skip(investor, "Investor profile does not allow strategy family.")

        if investor.current_drawdown >= investor.risk_profile.max_drawdown:
            return self._skip(investor, "Investor drawdown limit reached.")

        if investor.open_trade_count >= investor.risk_profile.max_simultaneous_trades:
            return self._skip(investor, "Investor simultaneous trade limit reached.")

        drawdown_multiplier = _clamp(
            1.0 - investor.current_drawdown / max(investor.risk_profile.max_drawdown, 0.01),
            0.05,
            1.0,
        )
        base_notional = (
            investor.equity
            * master_trade.risk_fraction
            * investor.risk_profile.exposure_multiplier
            * self.safe_mode_exposure_multiplier
            * drawdown_multiplier
        )
        max_notional = min(
            investor.equity * self.max_notional_per_trade_fraction,
            investor.available_balance * max(investor.risk_profile.leverage_multiplier, 0.0),
        )
        target_notional = min(base_notional, max_notional)

        if target_notional <= 0:
            return self._skip(investor, "Investor target notional is zero after caps.")

        leverage = max(0.0, master_trade.leverage * investor.risk_profile.leverage_multiplier)
        target_quantity = (
            master_trade.quantity
            * (target_notional / master_trade.notional)
            * _clamp(master_trade.fill_ratio)
        )

        return ScalingDecision(
            investor_id=investor.investor_id,
            approved=True,
            target_notional=target_notional,
            target_quantity=target_quantity,
            leverage=leverage,
            reason="Investor copy exposure approved after proportional risk scaling.",
        )

    def _skip(self, investor: InvestorAccount, reason: str) -> ScalingDecision:
        return ScalingDecision(
            investor_id=investor.investor_id,
            approved=False,
            target_notional=0.0,
            target_quantity=0.0,
            leverage=0.0,
            reason=reason,
            skipped=True,
        )

