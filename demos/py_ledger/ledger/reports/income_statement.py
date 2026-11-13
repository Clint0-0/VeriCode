from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..accounts import AccountType
from ..ledger import Ledger


def _movement(ledger: Ledger, code: str, start: date, end: date) -> Decimal:
    acct = ledger.chart.get(code)
    debit = credit = Decimal(0)
    for e in ledger.entries_between(start, end):
        for p in e.postings:
            if p.account == code:
                debit += p.debit
                credit += p.credit
    return debit - credit if acct.type.debit_normal else credit - debit


def income_statement(ledger: Ledger, start: date, end: date) -> dict:
    income = {a.code: _movement(ledger, a.code, start, end) for a in ledger.chart.of_type(AccountType.INCOME)}
    expenses = {a.code: _movement(ledger, a.code, start, end) for a in ledger.chart.of_type(AccountType.EXPENSE)}
    total_income = sum(income.values(), Decimal(0))
    total_expenses = sum(expenses.values(), Decimal(0))
    return {"income": income, "expenses": expenses, "total_income": total_income, "total_expenses": total_expenses,
            "net_income": total_income - total_expenses}
