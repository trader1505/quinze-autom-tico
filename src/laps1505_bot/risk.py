"""Risk and treasury motor (80/20 rebalance + margin defense)."""

from __future__ import annotations

from dataclasses import dataclass

from .config import BotSettings
from .models import BalanceSnapshot, EngineEvent, TransferIntent


@dataclass(slots=True)
class RiskResult:
    transfers: list[TransferIntent]
    events: list[EngineEvent]


class RiskEngine:
    def __init__(self, settings: BotSettings, tolerance_usdt: float = 0.5):
        self.settings = settings
        self.tolerance_usdt = tolerance_usdt

    def _target_balances(self, balances: BalanceSnapshot) -> tuple[float, float]:
        total = balances.total_equity_usdt
        target_spot = total * self.settings.spot_target_ratio
        target_futures = total * self.settings.futures_target_ratio
        return target_spot, target_futures

    def evaluate(self, balances: BalanceSnapshot) -> RiskResult:
        transfers: list[TransferIntent] = []
        events: list[EngineEvent] = []
        target_spot, target_futures = self._target_balances(balances)

        # Emergency margin support: if usage >= 60%, inject +20% of current equity.
        if balances.margin_ratio >= self.settings.margin_stress_threshold:
            emergency_amount = balances.total_equity_usdt * self.settings.futures_target_ratio
            transfer_amount = min(emergency_amount, balances.spot_usdt)
            if transfer_amount > self.tolerance_usdt:
                transfers.append(
                    TransferIntent(
                        from_wallet="spot",
                        to_wallet="futures",
                        amount_usdt=transfer_amount,
                        reason="margin_stress_topup",
                    )
                )
                events.append(
                    EngineEvent(
                        type="margin_defense",
                        message="Margem em estresse, transferindo +20% para Futures",
                        payload={"amount": transfer_amount, "margin_ratio": balances.margin_ratio},
                    )
                )
            return RiskResult(transfers=transfers, events=events)

        # When margin is normalized (<= 30%), enforce normal 80/20.
        if balances.margin_ratio <= self.settings.margin_recovery_threshold:
            delta_spot = balances.spot_usdt - target_spot
            if delta_spot > self.tolerance_usdt:
                transfers.append(
                    TransferIntent(
                        from_wallet="spot",
                        to_wallet="futures",
                        amount_usdt=delta_spot,
                        reason="rebalance_to_80_20",
                    )
                )
            elif delta_spot < -self.tolerance_usdt:
                transfers.append(
                    TransferIntent(
                        from_wallet="futures",
                        to_wallet="spot",
                        amount_usdt=abs(delta_spot),
                        reason="rebalance_to_80_20",
                    )
                )
            if transfers:
                events.append(
                    EngineEvent(
                        type="rebalance",
                        message="Rebalanceamento 80/20 aplicado",
                        payload={"target_spot": target_spot, "target_futures": target_futures},
                    )
                )
            return RiskResult(transfers=transfers, events=events)

        # In neutral margin zone, still rebalance if a new deposit shifts allocation.
        delta_spot = balances.spot_usdt - target_spot
        if delta_spot > self.tolerance_usdt:
            transfers.append(
                TransferIntent(
                    from_wallet="spot",
                    to_wallet="futures",
                    amount_usdt=delta_spot,
                    reason="deposit_rebalance",
                )
            )
        elif delta_spot < -self.tolerance_usdt:
            transfers.append(
                TransferIntent(
                    from_wallet="futures",
                    to_wallet="spot",
                    amount_usdt=abs(delta_spot),
                    reason="deposit_rebalance",
                )
            )
        if transfers:
            events.append(
                EngineEvent(
                    type="rebalance",
                    message="Alocação ajustada para manter 80% Spot e 20% Futures",
                    payload={"target_spot": target_spot, "target_futures": target_futures},
                )
            )
        return RiskResult(transfers=transfers, events=events)
