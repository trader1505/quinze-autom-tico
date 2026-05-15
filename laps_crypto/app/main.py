"""Main orchestration loop for LAPS Crypto."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .alpha.entry_engine import EntryEngine
from .alpha.signal_engine import SignalEngine
from .alpha.sizing_engine import SizingEngine
from .capital.capital_engine import CapitalEngine
from .capital.profit_allocator import ProfitAllocator
from .core.config import TradingConfig, load_config
from .core.logger import build_logger, log_event
from .core.models import EngineState
from .core.state_machine import BotStateMachine
from .exchange.account_reader import AccountReader
from .exchange.binance_client import BinanceClient
from .exchange.order_executor import OrderExecutor
from .exchange.position_reader import PositionReader
from .hedge.auto_balance_hedge import AutoBalanceHedge
from .hedge.hedge_engine import HedgeEngine
from .recovery.bidirectional_recovery import BidirectionalRecovery
from .recovery.dynamic_recovery import DynamicRecovery
from .recovery.dust_cleanup import DustCleanup
from .recovery.pigbank_engine import PigBankEngine
from .recovery.recovery_engine import RecoveryEngine
from .risk.defense_engine import DefenseEngine
from .risk.portfolio_risk_engine import PortfolioRiskEngine


@dataclass
class LapsCryptoSystem:
    """Composes all modules into a deterministic runtime."""

    config: TradingConfig
    client: BinanceClient

    @classmethod
    def bootstrap(cls) -> "LapsCryptoSystem":
        config = load_config()
        client = BinanceClient.from_config(config)
        return cls(config=config, client=client)

    def run_cycle(self) -> None:
        logger = build_logger()
        machine = BotStateMachine()

        symbol = self.config.default_symbol
        account_reader = AccountReader(self.client, self.config.base_asset)
        position_reader = PositionReader(self.client)
        order_executor = OrderExecutor(config=self.config, client=self.client, logger=logger)
        signal_engine = SignalEngine(min_strength_pct=self.config.signal_min_strength_pct)
        sizing_engine = SizingEngine(self.config)
        entry_engine = EntryEngine(order_executor=order_executor)
        risk_engine = PortfolioRiskEngine(self.config)
        defense_engine = DefenseEngine()
        hedge_engine = HedgeEngine(self.config)
        auto_hedge = AutoBalanceHedge(hedge_engine=hedge_engine)
        recovery_engine = RecoveryEngine(self.config)
        bidirectional = BidirectionalRecovery()
        pigbank = PigBankEngine()
        dynamic_recovery = DynamicRecovery()
        dust_cleanup = DustCleanup(self.config)
        capital_engine = CapitalEngine()
        allocator = ProfitAllocator(self.config)

        machine.transition_to(EngineState.ANALYZING)
        log_event(logger, "Iniciando análise de mercado.")
        log_event(
            logger,
            "Modo de execução configurado.",
            {
                "modo": "live" if self.client.is_live else "paper",
                "testnet": str(self.config.use_binance_testnet),
                "simbolo": symbol,
            },
        )

        account = account_reader.read()
        mark_price = self.client.get_mark_price(symbol)
        signal = signal_engine.generate_signal(symbol, mark_price)
        positions = position_reader.list_open_positions()
        exposure_pct = risk_engine.current_exposure_pct(
            equity=account.equity,
            positions=positions,
        )

        position = position_reader.get_open_position(symbol)
        if position is None:
            allowed_entry = signal.strength > 0 and defense_engine.can_open_new_position(
                exposure_pct=exposure_pct,
                max_exposure_pct=self.config.max_portfolio_exposure_pct,
            )
            if allowed_entry:
                machine.transition_to(EngineState.OPENING)
                quantity = sizing_engine.compute_position_size(
                    equity=account.equity,
                    mark_price=mark_price,
                    signal_strength=signal.strength,
                )
                entry_result = entry_engine.try_open(signal=signal, quantity=quantity, mark_price=mark_price)
                log_event(logger, entry_result.message_pt_br)
            else:
                log_event(logger, "Abertura bloqueada pelo controle de risco ou ausência de sinal.")

        machine.transition_to(EngineState.MANAGING)
        position = position_reader.get_open_position(symbol)
        if position is None:
            log_event(logger, "Nenhuma posição aberta para gerenciamento.")
            machine.transition_to(EngineState.IDLE)
            return

        latest_mark = self.client.get_mark_price(position.symbol)
        position.mark_price = latest_mark
        funding_cost = recovery_engine.estimate_funding_cost(position)
        close_result = order_executor.execute_close_if_safe(
            position=position,
            mark_price=latest_mark,
            funding_cost=funding_cost,
        )
        log_event(logger, close_result.message_pt_br)

        if close_result.accepted and close_result.close_decision is not None:
            net_profit = close_result.close_decision.breakdown.net_pnl
            reserve = allocator.allocate_to_reserve(net_profit)
            reinvest = net_profit - reserve
            pigbank.deposit(reserve)
            capital_engine.register_realized_pnl(reinvest)
            log_event(
                logger,
                "Lucro líquido alocado entre reserva e reinvestimento.",
                {"reserva": str(reserve), "reinvestimento": str(reinvest)},
            )
        else:
            machine.transition_to(EngineState.RECOVERY)
            action = bidirectional.recommend(position.side)
            multiplier = dynamic_recovery.multiplier_for_attempt(1)
            planned = recovery_engine.build_recovery_quantity(position.quantity, multiplier)
            hedge_plan = auto_hedge.plan_auto_balance(position=position, equity=account.equity)
            log_event(
                logger,
                "Plano de recuperação ativado.",
                {
                    "acao": action,
                    "quantidade_planejada": str(planned),
                    "hedge": hedge_plan.reason_pt_br,
                },
            )

        cleaned = dust_cleanup.cleanup(self.client)
        if cleaned > 0:
            log_event(logger, "Saldos residuais consolidados.", {"quantidade": str(cleaned)})

        capital_snapshot = capital_engine.build_snapshot(self.client, self.config.base_asset)
        log_event(
            logger,
            "Ciclo finalizado.",
            {
                "equity": str(capital_snapshot.equity),
                "colateral_livre": str(capital_snapshot.free_collateral),
                "reserva_protecao": str(pigbank.current_balance),
            },
        )
        machine.transition_to(EngineState.IDLE)


def run() -> None:
    """Entry point used by operators and tests."""
    system = LapsCryptoSystem.bootstrap()
    system.run_cycle()


if __name__ == "__main__":
    run()
