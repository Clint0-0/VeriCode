from datetime import date

import pytest

from ledger import Account, AccountType, ChartOfAccounts, Ledger
from ledger.journal import simple_entry


@pytest.fixture
def chart() -> ChartOfAccounts:
    return ChartOfAccounts([
        Account(code="1000", name="Bank", type=AccountType.ASSET, is_cash=True),
        Account(code="1100", name="Receivables", type=AccountType.ASSET),
        Account(code="2000", name="Payables", type=AccountType.LIABILITY),
        Account(code="3000", name="Owner equity", type=AccountType.EQUITY),
        Account(code="4000", name="Sales", type=AccountType.INCOME),
        Account(code="5000", name="Rent", type=AccountType.EXPENSE),
        Account(code="5100", name="Software", type=AccountType.EXPENSE),
        Account(code="9999", name="Suspense", type=AccountType.ASSET),
    ])


@pytest.fixture
def ledger(chart: ChartOfAccounts) -> Ledger:
    lg = Ledger(chart)
    lg.post(simple_entry(date(2026, 1, 2), "Owner investment", "1000", "3000", "10000.00"))
    lg.post(simple_entry(date(2026, 1, 5), "January rent", "5000", "1000", "1200.00"))
    lg.post(simple_entry(date(2026, 1, 20), "Invoice 001", "1100", "4000", "3000.00"))
    lg.post(simple_entry(date(2026, 2, 3), "Invoice 001 paid", "1000", "1100", "3000.00"))
    lg.post(simple_entry(date(2026, 2, 5), "February rent", "5000", "1000", "1200.00"))
    lg.post(simple_entry(date(2026, 2, 11), "IDE licence", "5100", "2000", "240.00"))
    return lg
