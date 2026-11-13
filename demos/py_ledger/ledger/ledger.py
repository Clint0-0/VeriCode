from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Iterable

from .accounts import AccountType, ChartOfAccounts
from .errors import LedgerError
from .journal import JournalEntry
from .periods import PeriodRegistry


class Ledger:
    """Posted journal entries plus balance queries. Entries are validated against the chart of accounts,
    must balance, must use the account currency and must not fall into a closed period."""

    def __init__(self, chart: ChartOfAccounts, periods: PeriodRegistry | None = None) -> None:
        self.chart = chart
        self.periods = periods or PeriodRegistry()
        self.entries: list[JournalEntry] = []

    def post(self, entry: JournalEntry) -> JournalEntry:
        entry.check_balanced()
        self.periods.ensure_open(entry.date)
        for p in entry.postings:
            acct = self.chart.get(p.account)
            if acct.currency != entry.currency:
                raise LedgerError(f"account {acct.code} is in {acct.currency}, entry is in {entry.currency}")
        if any(e.id == entry.id for e in self.entries):
            raise LedgerError(f"duplicate entry id {entry.id}")
        self.entries.append(entry)
        return entry

    def post_many(self, entries: Iterable[JournalEntry]) -> int:
        n = 0
        for e in entries:
            self.post(e)
            n += 1
        return n

    def entries_between(self, start: date, end: date) -> list[JournalEntry]:
        return sorted((e for e in self.entries if start <= e.date <= end), key=lambda e: (e.date, e.id))

    def balance(self, code: str, as_of: date | None = None) -> Decimal:
        """Signed balance in the account's normal direction (positive = normal)."""
        acct = self.chart.get(code)
        debit = credit = Decimal(0)
        for e in self.entries:
            if as_of and e.date > as_of:
                continue
            for p in e.postings:
                if p.account == code:
                    debit += p.debit
                    credit += p.credit
        return debit - credit if acct.type.debit_normal else credit - debit

    def balances(self, as_of: date | None = None) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = defaultdict(Decimal)
        for acct in self.chart:
            totals[acct.code] = self.balance(acct.code, as_of)
        return dict(totals)

    def total_of_type(self, kind: AccountType, as_of: date | None = None) -> Decimal:
        return sum((self.balance(a.code, as_of) for a in self.chart.of_type(kind)), Decimal(0))
