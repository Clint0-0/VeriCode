from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .errors import UnbalancedEntryError


class Posting(BaseModel):
    account: str = Field(pattern=r"^\d{4}$")
    debit: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    credit: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=2)
    memo: str = ""

    @model_validator(mode="after")
    def one_side(self) -> Posting:
        if (self.debit > 0) == (self.credit > 0):
            raise ValueError("a posting needs exactly one of debit or credit")
        return self


class JournalEntry(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    date: date
    description: str = Field(min_length=1, max_length=140)
    postings: list[Posting] = Field(min_length=2)
    currency: str = "EUR"
    tags: list[str] = []

    @field_validator("tags")
    @classmethod
    def normalise_tags(cls, v: list[str]) -> list[str]:
        return sorted({t.strip().lower() for t in v if t.strip()})

    def totals(self) -> tuple[Decimal, Decimal]:
        return sum((p.debit for p in self.postings), Decimal(0)), sum((p.credit for p in self.postings), Decimal(0))

    def check_balanced(self) -> None:
        debits, credits = self.totals()
        if debits != credits:
            raise UnbalancedEntryError(debits, credits)


def simple_entry(on: date, description: str, debit_account: str, credit_account: str, amount: Decimal | str,
                 currency: str = "EUR") -> JournalEntry:
    amt = Decimal(str(amount))
    return JournalEntry(date=on, description=description, currency=currency,
                        postings=[Posting(account=debit_account, debit=amt), Posting(account=credit_account, credit=amt)])
