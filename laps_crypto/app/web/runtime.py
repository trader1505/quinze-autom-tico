"""Runtime service layer used by the web dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import threading
from typing import Any, Dict, List

from ..capital.capital_engine import CapitalEngine
from ..core.models import OrderRequest, Position, Side
from ..exchange.account_reader import AccountReader
from ..exchange.binance_client import BinanceApiError, BinanceClient
from ..exchange.order_executor import OrderExecutor
from ..exchange.position_reader import PositionReader
from ..main import LapsCryptoSystem
from ..recovery.dust_cleanup import DustCleanup
from ..recovery.recovery_engine import RecoveryEngine
from ..risk.portfolio_risk_engine import PortfolioRiskEngine
from ..core.logger import build_logger


@dataclass(frozen=True)
class ActionOutcome:
    """Represents a dashboard action result."""

    success: bool
    message_pt_br: str


class DashboardRuntime:
    """Stateful runtime orchestrator for dashboard actions."""

    def __init__(self, system: LapsCryptoSystem) -> None:
        self._system = system
        self._lock = threading.RLock()
        self._events: List[Dict[str, str]] = []
        self._logger = build_logger("laps_crypto_dashboard")
        self._max_events = 120
        self._last_close_breakdown: Dict[str, Dict[str, str]] = {}

    @property
    def config(self):
        return self._system.config

    @property
    def client(self) -> BinanceClient:
        return self._system.client

    @classmethod
    def bootstrap(cls) -> "DashboardRuntime":
        return cls(system=LapsCryptoSystem.bootstrap())

    def run_cycle(self) -> ActionOutcome:
        with self._lock:
            try:
                self._system.run_cycle()
            except Exception as exc:  # noqa: BLE001 - explicit UI resilience
                message = f"Falha ao executar ciclo: {exc}"
                self._append_event(message=message, level="erro")
                return ActionOutcome(success=False, message_pt_br=message)
            message = "Ciclo automático executado com sucesso."
            self._append_event(message=message, level="sucesso")
            return ActionOutcome(success=True, message_pt_br=message)

    def open_order(self, symbol: str, side_raw: str, quantity_raw: str) -> ActionOutcome:
        with self._lock:
            symbol = symbol.strip().upper()
            if not symbol:
                return self._outcome_error("Símbolo inválido.")
            try:
                quantity = Decimal(quantity_raw.strip())
            except (InvalidOperation, AttributeError):
                return self._outcome_error("Quantidade inválida.")
            if quantity <= 0:
                return self._outcome_error("Quantidade deve ser maior que zero.")

            try:
                side = Side(side_raw.strip().upper())
            except Exception:  # noqa: BLE001
                return self._outcome_error("Lado da ordem inválido (use LONG ou SHORT).")

            executor = self._build_executor()
            order = OrderRequest(symbol=symbol, side=side, quantity=quantity, reduce_only=False)
            try:
                result = executor.execute_open(order=order)
            except BinanceApiError as exc:
                return self._outcome_error(f"Erro Binance ao abrir ordem: {exc}")
            except Exception as exc:  # noqa: BLE001
                return self._outcome_error(f"Falha ao abrir ordem: {exc}")

            level = "sucesso" if result.accepted else "aviso"
            self._append_event(message=result.message_pt_br, level=level)
            return ActionOutcome(success=result.accepted, message_pt_br=result.message_pt_br)

    def evaluate_close(self, symbol: str) -> ActionOutcome:
        with self._lock:
            symbol = symbol.strip().upper()
            position = self.client.get_position(symbol)
            if position is None:
                return self._outcome_error("Não existe posição aberta para o símbolo informado.")

            try:
                mark_price = self.client.get_mark_price(symbol)
                position.mark_price = mark_price
                executor = self._build_executor()
                funding_cost = RecoveryEngine(self.config).estimate_funding_cost(position)
                decision = executor.evaluate_close(
                    position=position,
                    mark_price=mark_price,
                    funding_cost=funding_cost,
                )
            except BinanceApiError as exc:
                return self._outcome_error(f"Erro Binance ao avaliar fechamento: {exc}")
            except Exception as exc:  # noqa: BLE001
                return self._outcome_error(f"Falha ao avaliar fechamento: {exc}")

            self._last_close_breakdown[symbol] = {
                "permitido": "SIM" if decision.allowed else "NÃO",
                "lucro_liquido_pct": self._fmt(decision.breakdown.net_profit_pct),
                "lucro_bruto": self._fmt(decision.breakdown.gross_pnl),
                "taxa_entrada": self._fmt(decision.breakdown.entry_fee),
                "taxa_saida": self._fmt(decision.breakdown.exit_fee),
                "funding": self._fmt(decision.breakdown.funding_cost),
                "slippage": self._fmt(decision.breakdown.slippage_cost),
                "custo_total": self._fmt(decision.breakdown.total_cost),
                "lucro_liquido": self._fmt(decision.breakdown.net_pnl),
                "minimo_pct": self._fmt(decision.min_required_pct),
                "motivo": decision.reason_pt_br,
            }
            self._append_event(message=f"Avaliação de fechamento concluída para {symbol}.", level="info")
            return ActionOutcome(success=True, message_pt_br="Avaliação de fechamento atualizada.")

    def close_position_safe(self, symbol: str) -> ActionOutcome:
        with self._lock:
            symbol = symbol.strip().upper()
            position = self.client.get_position(symbol)
            if position is None:
                return self._outcome_error("Não existe posição aberta para o símbolo informado.")

            executor = self._build_executor()
            try:
                mark_price = self.client.get_mark_price(symbol)
                position.mark_price = mark_price
                funding_cost = RecoveryEngine(self.config).estimate_funding_cost(position)
                result = executor.execute_close_if_safe(
                    position=position,
                    mark_price=mark_price,
                    funding_cost=funding_cost,
                )
            except BinanceApiError as exc:
                return self._outcome_error(f"Erro Binance ao fechar posição: {exc}")
            except Exception as exc:  # noqa: BLE001
                return self._outcome_error(f"Falha ao fechar posição: {exc}")

            if result.close_decision is not None:
                self._last_close_breakdown[symbol] = {
                    "permitido": "SIM" if result.close_decision.allowed else "NÃO",
                    "lucro_liquido_pct": self._fmt(result.close_decision.breakdown.net_profit_pct),
                    "lucro_bruto": self._fmt(result.close_decision.breakdown.gross_pnl),
                    "taxa_entrada": self._fmt(result.close_decision.breakdown.entry_fee),
                    "taxa_saida": self._fmt(result.close_decision.breakdown.exit_fee),
                    "funding": self._fmt(result.close_decision.breakdown.funding_cost),
                    "slippage": self._fmt(result.close_decision.breakdown.slippage_cost),
                    "custo_total": self._fmt(result.close_decision.breakdown.total_cost),
                    "lucro_liquido": self._fmt(result.close_decision.breakdown.net_pnl),
                    "minimo_pct": self._fmt(result.close_decision.min_required_pct),
                    "motivo": result.close_decision.reason_pt_br,
                }

            level = "sucesso" if result.accepted else "aviso"
            self._append_event(message=result.message_pt_br, level=level)
            return ActionOutcome(success=result.accepted, message_pt_br=result.message_pt_br)

    def set_mark_price(self, symbol: str, mark_price_raw: str) -> ActionOutcome:
        with self._lock:
            if self.client.is_live:
                return self._outcome_error("Ajuste manual de preço só é permitido em modo paper.")

            symbol = symbol.strip().upper()
            try:
                mark_price = Decimal(mark_price_raw.strip())
            except (InvalidOperation, AttributeError):
                return self._outcome_error("Preço de marca inválido.")

            if mark_price <= 0:
                return self._outcome_error("Preço de marca deve ser maior que zero.")

            try:
                self.client.set_mark_price(symbol, mark_price)
            except Exception as exc:  # noqa: BLE001
                return self._outcome_error(f"Falha ao atualizar preço: {exc}")

            message = f"Preço de marca de {symbol} atualizado para {mark_price}."
            self._append_event(message=message, level="sucesso")
            return ActionOutcome(success=True, message_pt_br=message)

    def cleanup_dust(self) -> ActionOutcome:
        with self._lock:
            try:
                cleaned = DustCleanup(self.config).cleanup(self.client)
            except Exception as exc:  # noqa: BLE001
                return self._outcome_error(f"Falha na limpeza de saldos residuais: {exc}")

            if cleaned > 0:
                message = f"Limpeza de saldos residuais concluída: {cleaned} {self.config.base_asset}."
                self._append_event(message=message, level="sucesso")
                return ActionOutcome(success=True, message_pt_br=message)

            message = "Nenhum saldo residual elegível para limpeza."
            self._append_event(message=message, level="info")
            return ActionOutcome(success=True, message_pt_br=message)

    def save_api_credentials(self, api_key_raw: str, api_secret_raw: str) -> ActionOutcome:
        with self._lock:
            try:
                self.client.set_credentials(api_key=api_key_raw, api_secret=api_secret_raw)
            except ValueError as exc:
                return self._outcome_error(str(exc))
            except Exception as exc:  # noqa: BLE001
                return self._outcome_error(f"Falha ao salvar credenciais: {exc}")

            message = "Credenciais Binance atualizadas com sucesso (somente memória)."
            self._append_event(message=message, level="sucesso")
            return ActionOutcome(success=True, message_pt_br=message)

    def clear_api_credentials(self) -> ActionOutcome:
        with self._lock:
            self.client.clear_credentials()
            message = "Credenciais Binance removidas da memória do painel."
            self._append_event(message=message, level="info")
            return ActionOutcome(success=True, message_pt_br=message)

    def dashboard_data(self) -> Dict[str, Any]:
        with self._lock:
            snapshot = AccountReader(self.client, self.config.base_asset).read()
            positions = PositionReader(self.client).list_open_positions()
            exposure_pct = PortfolioRiskEngine(self.config).current_exposure_pct(
                equity=snapshot.equity,
                positions=positions,
            )
            capital_snapshot = CapitalEngine().build_snapshot(self.client, self.config.base_asset)

            return {
                "config": {
                    "modo_execucao": self.config.execution_mode.upper(),
                    "testnet": "SIM" if self.config.use_binance_testnet else "NÃO",
                    "simbolo_padrao": self.config.default_symbol,
                    "ativo_base": self.config.base_asset,
                    "minimo_fechamento_pct": self._fmt(self.config.min_close_profit_pct),
                    "credenciais_configuradas": "SIM" if self.client.has_credentials else "NÃO",
                    "api_key_mascarada": self.client.masked_api_key or "N/D",
                },
                "conta": {
                    "equity": self._fmt(snapshot.equity),
                    "colateral_livre": self._fmt(snapshot.free_collateral),
                    "colateral_utilizado": self._fmt(snapshot.used_collateral),
                    "exposicao_pct": self._fmt(exposure_pct),
                    "capital_equity": self._fmt(capital_snapshot.equity),
                },
                "posicoes": [self._position_row(position) for position in positions],
                "avaliacoes_fechamento": dict(self._last_close_breakdown),
                "eventos": list(self._events),
                "is_live": self.client.is_live,
            }

    def _position_row(self, position: Position) -> Dict[str, str]:
        return {
            "symbol": position.symbol,
            "side": position.side.value,
            "quantity": self._fmt(position.quantity),
            "entry_price": self._fmt(position.entry_price),
            "mark_price": self._fmt(position.mark_price),
            "entry_notional": self._fmt(position.entry_notional),
            "mark_notional": self._fmt(position.mark_notional),
            "gross_pnl": self._fmt(position.gross_pnl),
        }

    def _outcome_error(self, message: str) -> ActionOutcome:
        self._append_event(message=message, level="erro")
        return ActionOutcome(success=False, message_pt_br=message)

    def _append_event(self, *, message: str, level: str) -> None:
        now = datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M:%S")
        self._events.append({"horario": now, "nivel": level, "mensagem": message})
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events :]
        if level == "erro":
            self._logger.error(message)
        elif level == "aviso":
            self._logger.warning(message)
        else:
            self._logger.info(message)

    @staticmethod
    def _fmt(value: Decimal) -> str:
        text = format(value.normalize(), "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text if text else "0"

    def _build_executor(self) -> OrderExecutor:
        return OrderExecutor(config=self.config, client=self.client, logger=self._logger)

