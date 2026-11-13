from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ledger import JournalEntry, LedgerError, PeriodClosedError, Posting, UnbalancedEntryError, UnknownAccountError
from ledger.journal import simple_entry


def test_posting_needs_exactly_one_side() -> None:
    with pytest.raises(ValidationError):
        Posting(account="1000", debit=Decimal("1"), credit=Decimal("1"))
    with pytest.raises(ValidationError):
        Posting(account="1000")


def test_unbalanced_entry_rejected(ledger) -> None:
    e = JournalEntry(date=date(2026, 3, 1), description="bad", postings=[
        Posting(account="1000", debit=Decimal("10")), Posting(account="4000", credit=Decimal("9"))])
    with pytest.raises(UnbalancedEntryError):
        ledger.post(e)


def test_balances_follow_normal_side(ledger) -> None:
    assert ledger.balance("1000") == Decimal("10600.00")
    assert ledger.balance("4000") == Decimal("3000.00")
    assert ledger.balance("2000") == Decimal("240.00")
    assert ledger.balance("1000", as_of=date(2026, 1, 31)) == Decimal("8800.00")


def test_closed_period_and_unknown_account(ledger) -> None:
    ledger.periods.close(2026, 1)
    with pytest.raises(PeriodClosedError):
        ledger.post(simple_entry(date(2026, 1, 30), "late", "5000", "1000", "1"))
    with pytest.raises(UnknownAccountError):
        ledger.post(simple_entry(date(2026, 3, 1), "x", "1234", "1000", "1"))


def test_duplicate_ids_and_currency_mismatch(ledger) -> None:
    e = ledger.entries[0]
    with pytest.raises(LedgerError):
        ledger.post(e)
    with pytest.raises(LedgerError):
        ledger.post(simple_entry(date(2026, 3, 1), "usd", "1000", "4000", "5", currency="USD"))


def test_tags_are_normalised() -> None:
    e = simple_entry(date(2026, 3, 1), "x", "1000", "4000", "5").model_copy(update={"tags": []})
    assert JournalEntry(**{**e.model_dump(), "tags": [" Travel", "travel", "", "Q1"]}).tags == ["q1", "travel"]
