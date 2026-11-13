from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class BankLine:
    date: date
    payee: str
    amount: Decimal  # positive = money in, negative = money out
    reference: str = ""


class CsvFormatError(ValueError):
    def __init__(self, line_no: int, message: str) -> None:
        super().__init__(f"line {line_no}: {message}")
        self.line_no = line_no


def _amount(raw: str) -> Decimal:
    """Accepts '1,234.56', '-12.00', '(12.00)' (accounting negative) and '12,50' (decimal comma)."""
    s = raw.strip().replace(" ", "")
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    s = s.replace(",", "")
    value = Decimal(s)
    return -value if negative else value


def parse_bank_csv(text: str, date_format: str = "%Y-%m-%d") -> list[BankLine]:
    """Columns (header required): date, payee, amount[, reference]. Blank lines are skipped."""
    reader = csv.DictReader(io.StringIO(text.strip()))
    missing = {"date", "payee", "amount"} - set(reader.fieldnames or [])
    if missing:
        raise CsvFormatError(1, f"missing columns: {sorted(missing)}")
    out = []
    for i, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        try:
            d = datetime.strptime(row["date"].strip(), date_format).date()
        except ValueError:
            raise CsvFormatError(i, f"bad date {row['date']!r}") from None
        try:
            amt = _amount(row["amount"])
        except (InvalidOperation, ValueError):
            raise CsvFormatError(i, f"bad amount {row['amount']!r}") from None
        out.append(BankLine(d, row["payee"].strip(), amt, (row.get("reference") or "").strip()))
    return out
