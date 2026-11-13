from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..ledger import Ledger


@dataclass(frozen=True)
class TrialBalanceLine:
    code: str
    name: str
    debit: Decimal
    credit: Decimal


def trial_balance(ledger: Ledger, as_of: date | None = None) -> tuple[list[TrialBalanceLine], Decimal, Decimal]:
    """Every account with a non-zero balance on its natural side; returns (lines, total debits, total credits)."""
    lines = []
    for acct in ledger.chart:
        bal = ledger.balance(acct.code, as_of)
        if bal == 0:
            continue
        natural_debit = acct.type.debit_normal
        if (bal > 0) == natural_debit:
            lines.append(TrialBalanceLine(acct.code, acct.name, abs(bal), Decimal(0)))
        else:
            lines.append(TrialBalanceLine(acct.code, acct.name, Decimal(0), abs(bal)))
    return lines, sum((l.debit for l in lines), Decimal(0)), sum((l.credit for l in lines), Decimal(0))
