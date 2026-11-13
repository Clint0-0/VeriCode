from __future__ import annotations

import bisect
from datetime import date
from decimal import Decimal

from .currency import check
from .errors import CurrencyError
from .money import Money


class FxTable:
    """Exchange rates per currency pair over time. A rate applies from its date until the next rate's date."""

    def __init__(self, base: str = "EUR") -> None:
        self.base = check(base)
        self._rates: dict[str, list[tuple[date, Decimal]]] = {}

    def set_rate(self, currency: str, on: date, units_per_base: Decimal | str) -> None:
        """`units_per_base`: how many units of `currency` one unit of the base currency buys on `on`."""
        currency = check(currency)
        series = self._rates.setdefault(currency, [])
        rate = Decimal(str(units_per_base))
        if rate <= 0:
            raise CurrencyError("rates must be positive")
        idx = bisect.bisect_left(series, (on, Decimal(0)))
        if idx < len(series) and series[idx][0] == on:
            series[idx] = (on, rate)
        else:
            series.insert(idx, (on, rate))

    def rate(self, currency: str, on: date) -> Decimal:
        currency = check(currency)
        if currency == self.base:
            return Decimal(1)
        series = self._rates.get(currency)
        if not series:
            raise CurrencyError(f"no rates for {currency}")
        idx = bisect.bisect_right(series, (on, Decimal("Infinity"))) - 1
        if idx < 0:
            raise CurrencyError(f"no {currency} rate on or before {on.isoformat()}")
        return series[idx][1]

    def convert(self, amount: Money, to: str, on: date) -> Money:
        to = check(to)
        if amount.currency == to:
            return amount
        in_base = amount.amount / self.rate(amount.currency, on)
        return Money(in_base * self.rate(to, on), to)
