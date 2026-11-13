"""Benchmark acceptance: monthly cash flow over cash accounts."""
from datetime import date
from decimal import Decimal

from ledger import Account, AccountType
from ledger.journal import simple_entry
from ledger.reports.cash_flow import monthly_cash_flow


def test_monthly_inflow_outflow_net(ledger) -> None:
    rows = monthly_cash_flow(ledger, date(2026, 1, 1), date(2026, 2, 28))
    assert [r["month"] for r in rows] == ["2026-01", "2026-02"]
    jan, feb = rows
    assert (jan["inflow"], jan["outflow"], jan["net"]) == (Decimal("10000.00"), Decimal("1200.00"), Decimal("8800.00"))
    assert (feb["inflow"], feb["outflow"], feb["net"]) == (Decimal("3000.00"), Decimal("1200.00"), Decimal("1800.00"))


def test_months_without_movement_are_listed_with_zeros(ledger) -> None:
    rows = monthly_cash_flow(ledger, date(2025, 12, 1), date(2026, 3, 31))
    assert [r["month"] for r in rows] == ["2025-12", "2026-01", "2026-02", "2026-03"]
    assert rows[0]["net"] == 0 and rows[-1]["inflow"] == 0 and rows[-1]["outflow"] == 0


def test_range_is_inclusive_and_partial_months_count(ledger) -> None:
    rows = monthly_cash_flow(ledger, date(2026, 2, 4), date(2026, 2, 5))
    assert rows == [{"month": "2026-02", "inflow": Decimal("0"), "outflow": Decimal("1200.00"), "net": Decimal("-1200.00")}]


def test_transfers_between_cash_accounts_are_ignored(ledger) -> None:
    ledger.chart.add(Account(code="1010", name="Savings", type=AccountType.ASSET, is_cash=True))
    ledger.post(simple_entry(date(2026, 2, 20), "To savings", "1010", "1000", "5000.00"))
    feb = monthly_cash_flow(ledger, date(2026, 2, 1), date(2026, 2, 28))[0]
    assert (feb["inflow"], feb["outflow"]) == (Decimal("3000.00"), Decimal("1200.00"))


def test_non_cash_movements_are_ignored(ledger) -> None:
    # the IDE licence (expense against payables) never touches cash
    feb = monthly_cash_flow(ledger, date(2026, 2, 10), date(2026, 2, 12))[0]
    assert feb["inflow"] == feb["outflow"] == 0
