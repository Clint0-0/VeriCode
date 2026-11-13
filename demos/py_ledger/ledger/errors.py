from __future__ import annotations

from datetime import date
from decimal import Decimal


class LedgerError(Exception):
    """Base class for ledger errors."""


class UnknownAccountError(LedgerError):
    def __init__(self, code: str) -> None:
        super().__init__(f"unknown account {code}")
        self.code = code


class UnbalancedEntryError(LedgerError):
    def __init__(self, debits: Decimal, credits: Decimal) -> None:
        super().__init__(f"entry does not balance: debits {debits} != credits {credits}")
        self.debits, self.credits = debits, credits


class PeriodClosedError(LedgerError):
    def __init__(self, when: date) -> None:
        super().__init__(f"the period containing {when.isoformat()} is closed")
        self.when = when


class CurrencyError(LedgerError):
    """Raised for unsupported currencies or missing exchange rates."""
