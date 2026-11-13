from datetime import date
from decimal import Decimal

import pytest

from ledger.errors import CurrencyError
from ledger.fx import FxTable
from ledger.money import Money


def test_money_rounds_to_minor_units() -> None:
    assert Money.of("1.005", "EUR").amount == Decimal("1.00")  # banker's rounding
    assert Money.of("1.015", "EUR").amount == Decimal("1.02")
    assert Money.of("12.5", "JPY").amount == Decimal("12")
    assert (Money.of("1.10") + Money.of("2.20")).amount == Decimal("3.30")


def test_money_rejects_mixed_and_unknown_currencies() -> None:
    with pytest.raises(CurrencyError):
        Money.of(1, "EUR") + Money.of(1, "USD")
    with pytest.raises(CurrencyError):
        Money.of(1, "XXX")


def test_fx_conversion_through_base() -> None:
    fx = FxTable("EUR")
    fx.set_rate("USD", date(2026, 1, 1), "1.10")
    fx.set_rate("GBP", date(2026, 1, 1), "0.85")
    assert fx.convert(Money.of("110.00", "USD"), "EUR", date(2026, 1, 15)).amount == Decimal("100.00")
    assert fx.convert(Money.of("100.00", "EUR"), "GBP", date(2026, 1, 15)).amount == Decimal("85.00")
    assert fx.convert(Money.of("11.00", "USD"), "GBP", date(2026, 1, 15)).amount == Decimal("8.50")


def test_fx_missing_rate() -> None:
    fx = FxTable("EUR")
    fx.set_rate("USD", date(2026, 3, 1), "1.10")
    with pytest.raises(CurrencyError):
        fx.rate("USD", date(2026, 2, 1))
    with pytest.raises(CurrencyError):
        fx.rate("CHF", date(2026, 3, 1))
