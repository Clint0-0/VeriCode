from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .errors import PeriodClosedError


@dataclass(frozen=True)
class Period:
    year: int
    month: int

    @classmethod
    def of(cls, d: date) -> Period:
        return cls(d.year, d.month)

    def __str__(self) -> str:
        return f"{self.year}-{self.month:02d}"


@dataclass
class PeriodRegistry:
    """Tracks closed months. Postings into a closed month are refused."""

    closed: set[Period] = field(default_factory=set)

    def close(self, year: int, month: int) -> None:
        self.closed.add(Period(year, month))

    def reopen(self, year: int, month: int) -> None:
        self.closed.discard(Period(year, month))

    def is_closed(self, d: date) -> bool:
        return Period.of(d) in self.closed

    def ensure_open(self, d: date) -> None:
        if self.is_closed(d):
            raise PeriodClosedError(d)
