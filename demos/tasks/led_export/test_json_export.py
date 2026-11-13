"""Benchmark acceptance: JSON export/import of journal entries (pydantic 2.9.2 installed).

Deprecated pydantic APIs (v1 style) raise here: warnings are errors in this module."""
import json
from datetime import date
from decimal import Decimal

import pytest

from ledger import JournalEntry, Posting, UnbalancedEntryError
from ledger.io.json_export import export_entries, import_entries
from ledger.journal import simple_entry

pytestmark = pytest.mark.filterwarnings("error")


def _entries() -> list[JournalEntry]:
    a = simple_entry(date(2026, 1, 5), "January rent", "5000", "1000", "1200.10")
    b = JournalEntry(date=date(2026, 1, 20), description="Split invoice", tags=["Q1"], postings=[
        Posting(account="1100", debit=Decimal("100.05")),
        Posting(account="4000", credit=Decimal("90.00")),
        Posting(account="2000", credit=Decimal("10.05"), memo="VAT")])
    return [a, b]


def test_export_is_a_json_array_with_iso_dates_and_string_amounts() -> None:
    data = json.loads(export_entries(_entries()))
    assert isinstance(data, list) and len(data) == 2
    assert data[0]["date"] == "2026-01-05"
    assert data[1]["postings"][0]["debit"] == "100.05"
    assert data[1]["tags"] == ["q1"]


def test_round_trip_is_exact() -> None:
    original = _entries()
    back = import_entries(export_entries(original))
    assert back == original
    assert back[1].postings[2].credit == Decimal("10.05")


def test_import_rejects_unbalanced_entries() -> None:
    data = json.loads(export_entries(_entries()))
    data[0]["postings"][0]["debit"] = "1200.11"
    with pytest.raises(UnbalancedEntryError):
        import_entries(json.dumps(data))


def test_import_rejects_invalid_data() -> None:
    with pytest.raises(ValueError):  # pydantic.ValidationError is a ValueError
        import_entries(json.dumps([{"date": "not-a-date", "description": "x", "postings": []}]))
    assert import_entries("[]") == []
