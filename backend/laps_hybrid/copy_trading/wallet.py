"""Append-only investor wallet ledger."""

from __future__ import annotations

from uuid import uuid4

from .models import WalletTransaction, WalletTransactionType


class WalletLedger:
    """Append-only ledger for investor wallet accounting."""

    def __init__(self) -> None:
        self._transactions: list[WalletTransaction] = []

    def record(
        self,
        *,
        investor_id: str,
        transaction_type: WalletTransactionType,
        amount: float,
        currency: str,
        correlation_id: str,
        reference_id: str | None = None,
    ) -> WalletTransaction:
        """Append one wallet transaction."""

        transaction = WalletTransaction(
            transaction_id=uuid4().hex,
            investor_id=investor_id,
            transaction_type=transaction_type,
            amount=amount,
            currency=currency,
            correlation_id=correlation_id,
            reference_id=reference_id,
        )
        self._transactions.append(transaction)
        return transaction

    def balance(self, investor_id: str, currency: str = "USDT") -> float:
        """Derive current balance from ledger entries."""

        return sum(
            transaction.amount
            for transaction in self._transactions
            if transaction.investor_id == investor_id and transaction.currency == currency
        )

    def transactions(
        self,
        investor_id: str | None = None,
    ) -> tuple[WalletTransaction, ...]:
        """Return ledger transactions, optionally scoped to one investor."""

        if investor_id is None:
            return tuple(self._transactions)
        return tuple(
            transaction
            for transaction in self._transactions
            if transaction.investor_id == investor_id
        )

