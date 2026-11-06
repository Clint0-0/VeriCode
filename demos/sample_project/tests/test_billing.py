from decimal import Decimal

from taskboard.billing import build_invoice, prorate


def test_invoice_total():
    inv = build_invoice("acme", "team", 3, "IN")
    assert inv.total == Decimal("28.32")


def test_prorate():
    assert prorate(Decimal("30"), 15, 30) == Decimal("15.00")
