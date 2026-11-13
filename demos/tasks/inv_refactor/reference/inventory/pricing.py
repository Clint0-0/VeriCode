from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .repository import InMemoryRepository

VAT_RATE = Decimal("0.19")
CENT = Decimal("0.01")


def apply_bulk_discount_and_vat(subtotal: Decimal, quantity: int) -> Decimal:
    """Bulk discount by quantity tier, then VAT, rounded to cents."""
    if quantity >= 100:
        subtotal = subtotal * Decimal("0.85")
    elif quantity >= 20:
        subtotal = subtotal * Decimal("0.93")
    return (subtotal * (1 + VAT_RATE)).quantize(CENT, rounding=ROUND_HALF_UP)


def quote_line(repo: InMemoryRepository, sku: str, quantity: int) -> Decimal:
    """Gross price for one order line: bulk discount, then VAT, rounded to cents."""
    return apply_bulk_discount_and_vat(repo.product(sku).unit_price * quantity, quantity)


def quote_order(repo: InMemoryRepository, lines: dict[str, int]) -> Decimal:
    """Gross price for a whole order; the bulk discount uses the TOTAL quantity across lines."""
    subtotal = sum((repo.product(sku).unit_price * qty for sku, qty in lines.items()), Decimal("0"))
    return apply_bulk_discount_and_vat(subtotal, sum(lines.values()))
