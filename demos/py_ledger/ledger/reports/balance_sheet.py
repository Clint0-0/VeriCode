from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..accounts import AccountType
from ..ledger import Ledger


def balance_sheet(ledger: Ledger, as_of: date) -> dict:
    """Assets = liabilities + equity + retained earnings (income - expenses to date)."""
    assets = ledger.total_of_type(AccountType.ASSET, as_of)
    liabilities = ledger.total_of_type(AccountType.LIABILITY, as_of)
    equity = ledger.total_of_type(AccountType.EQUITY, as_of)
    retained = ledger.total_of_type(AccountType.INCOME, as_of) - ledger.total_of_type(AccountType.EXPENSE, as_of)
    return {"assets": assets, "liabilities": liabilities, "equity": equity, "retained_earnings": retained,
            "balanced": assets == liabilities + equity + retained, "difference": assets - (liabilities + equity + retained)}


def net_worth(ledger: Ledger, as_of: date) -> Decimal:
    sheet = balance_sheet(ledger, as_of)
    return sheet["assets"] - sheet["liabilities"]
