from datetime import date
from decimal import Decimal

from ledger.reports import balance_sheet, income_statement, trial_balance
from ledger.reports.balance_sheet import net_worth


def test_trial_balance_balances(ledger) -> None:
    lines, debits, credits = trial_balance(ledger)
    assert debits == credits == Decimal("13240.00")
    assert {l.code for l in lines} == {"1000", "2000", "3000", "4000", "5000", "5100"}


def test_income_statement_for_a_month(ledger) -> None:
    jan = income_statement(ledger, date(2026, 1, 1), date(2026, 1, 31))
    assert jan["total_income"] == Decimal("3000.00")
    assert jan["total_expenses"] == Decimal("1200.00")
    assert jan["net_income"] == Decimal("1800.00")


def test_balance_sheet_balances(ledger) -> None:
    sheet = balance_sheet(ledger, date(2026, 2, 28))
    assert sheet["balanced"] and sheet["difference"] == 0
    assert sheet["retained_earnings"] == Decimal("360.00")
    assert net_worth(ledger, date(2026, 2, 28)) == Decimal("10360.00")
