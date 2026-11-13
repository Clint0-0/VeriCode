from decimal import Decimal

from inventory.pricing import quote_line, quote_order


def test_quote_line_tiers(repo) -> None:
    assert quote_line(repo, "BLT-0001", 10) == Decimal("2.38")
    assert quote_line(repo, "BLT-0001", 20) == Decimal("4.43")
    assert quote_line(repo, "BLT-0001", 100) == Decimal("20.23")


def test_quote_order_uses_total_quantity(repo) -> None:
    assert quote_order(repo, {"BLT-0001": 10, "NUT-0002": 10}) == Decimal("3.32")
    assert quote_order(repo, {"BLT-0001": 60, "NUT-0002": 40}) == Decimal("16.18")
