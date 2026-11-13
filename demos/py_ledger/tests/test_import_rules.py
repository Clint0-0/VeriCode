from datetime import date
from decimal import Decimal

import pytest

from ledger.io.csv_import import CsvFormatError, parse_bank_csv
from ledger.rules.categorize import Categorizer, Rule

CSV = """date,payee,amount,reference
2026-03-01,ACME Corp,"1,500.00",INV-17
2026-03-02,Landlord GmbH,(1200.00),March

2026-03-03,JetBrains,-24.00,
2026-03-04,Unknown shop,"12,50",
"""


def test_parse_bank_csv_formats() -> None:
    lines = parse_bank_csv(CSV)
    assert [l.amount for l in lines] == [Decimal("1500.00"), Decimal("-1200.00"), Decimal("-24.00"), Decimal("12.50")]
    assert lines[0].reference == "INV-17" and lines[0].date == date(2026, 3, 1)


def test_parse_errors_report_line_numbers() -> None:
    with pytest.raises(CsvFormatError, match="line 2"):
        parse_bank_csv("date,payee,amount\n2026-13-01,x,1\n")
    with pytest.raises(CsvFormatError, match="missing columns"):
        parse_bank_csv("when,payee,amount\n")


def test_categorizer_posts_balanced_entries(ledger) -> None:
    cat = Categorizer([Rule("acme", "4000", "sales"), Rule(r"landlord", "5000"), Rule("jetbrains|github", "5100")],
                      bank_account="1000", suspense_account="9999")
    entries, unmatched = cat.categorize(parse_bank_csv(CSV))
    assert [u.payee for u in unmatched] == ["Unknown shop"]
    assert entries[0].tags == ["sales"]
    ledger.post_many(entries)
    assert ledger.balance("1000") == Decimal("10888.50")
    assert ledger.balance("9999") == Decimal("-12.50")
