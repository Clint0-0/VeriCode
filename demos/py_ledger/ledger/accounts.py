from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import UnknownAccountError


class AccountType(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"

    @property
    def debit_normal(self) -> bool:
        """Assets and expenses increase with debits; the others with credits."""
        return self in (AccountType.ASSET, AccountType.EXPENSE)


class Account(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(pattern=r"^\d{4}$")
    name: str = Field(min_length=1, max_length=60)
    type: AccountType
    currency: str = "EUR"
    is_cash: bool = False
    parent: str | None = None

    @field_validator("currency")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()


class ChartOfAccounts:
    def __init__(self, accounts: list[Account] | None = None) -> None:
        self._by_code: dict[str, Account] = {}
        for a in accounts or []:
            self.add(a)

    def add(self, account: Account) -> None:
        if account.parent and account.parent not in self._by_code:
            raise UnknownAccountError(account.parent)
        self._by_code[account.code] = account

    def get(self, code: str) -> Account:
        try:
            return self._by_code[code]
        except KeyError:
            raise UnknownAccountError(code) from None

    def of_type(self, kind: AccountType) -> list[Account]:
        return sorted((a for a in self._by_code.values() if a.type is kind), key=lambda a: a.code)

    def children(self, code: str) -> list[Account]:
        return sorted((a for a in self._by_code.values() if a.parent == code), key=lambda a: a.code)

    def __iter__(self):
        return iter(sorted(self._by_code.values(), key=lambda a: a.code))

    def __contains__(self, code: str) -> bool:
        return code in self._by_code
