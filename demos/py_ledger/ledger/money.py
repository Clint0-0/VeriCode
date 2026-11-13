from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .currency import check, round_amount
from .errors import CurrencyError


@dataclass(frozen=True, order=True)
class Money:
    amount: Decimal
    currency: str = "EUR"

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", check(self.currency))
        object.__setattr__(self, "amount", round_amount(Decimal(self.amount), self.currency))

    @classmethod
    def of(cls, amount: str | int | Decimal, currency: str = "EUR") -> Money:
        return cls(Decimal(str(amount)), currency)

    def _same(self, other: Money) -> None:
        if other.currency != self.currency:
            raise CurrencyError(f"cannot combine {self.currency} and {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def scale(self, factor: Decimal) -> Money:
        return Money(self.amount * factor, self.currency)

    def is_zero(self) -> bool:
        return self.amount == 0

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"
