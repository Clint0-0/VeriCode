"""Benchmark acceptance: a rate applies from its date until the next rate's date."""
from datetime import date
from decimal import Decimal

import pytest

from ledger.errors import CurrencyError
from ledger.fx import FxTable
from ledger.money import Money


@pytest.fixture
def fx() -> FxTable:
    t = FxTable("EUR")
    t.set_rate("USD", date(2026, 1, 1), "1.10")
    t.set_rate("USD", date(2026, 2, 1), "1.20")
    t.set_rate("USD", date(2026, 3, 1), "1.25")
    return t


def test_rate_in_effect_between_changes(fx: FxTable) -> None:
    assert fx.rate("USD", date(2026, 1, 31)) == Decimal("1.10")
    assert fx.rate("USD", date(2026, 2, 15)) == Decimal("1.20")


def test_rate_on_the_change_date(fx: FxTable) -> None:
    assert fx.rate("USD", date(2026, 2, 1)) == Decimal("1.20")
    assert fx.rate("USD", date(2026, 1, 1)) == Decimal("1.10")


def test_rate_after_the_latest_change(fx: FxTable) -> None:
    assert fx.rate("USD", date(2027, 6, 1)) == Decimal("1.25")


def test_before_first_rate_and_conversion(fx: FxTable) -> None:
    with pytest.raises(CurrencyError):
        fx.rate("USD", date(2025, 12, 31))
    assert fx.convert(Money.of("120.00", "USD"), "EUR", date(2026, 2, 28)).amount == Decimal("100.00")
