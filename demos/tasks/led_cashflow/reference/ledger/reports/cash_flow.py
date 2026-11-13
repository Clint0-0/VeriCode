from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..ledger import Ledger


def _months(start: date, end: date) -> list[str]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def monthly_cash_flow(ledger: Ledger, start: date, end: date) -> list[dict]:
    """Per month in [start, end]: inflow, outflow and net over cash accounts; cash-to-cash transfers ignored."""
    cash = {a.code for a in ledger.chart if a.is_cash}
    rows = {m: {"month": m, "inflow": Decimal("0"), "outflow": Decimal("0")} for m in _months(start, end)}
    for e in ledger.entries_between(start, end):
        if all(p.account in cash for p in e.postings):
            continue
        row = rows[f"{e.date.year}-{e.date.month:02d}"]
        for p in e.postings:
            if p.account in cash:
                row["inflow"] += p.debit
                row["outflow"] += p.credit
    return [{**r, "net": r["inflow"] - r["outflow"]} for r in rows.values()]
