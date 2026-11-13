from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from .repository import InMemoryRepository

VAT_RATE = Decimal("0.19")
CENT = Decimal("0.01")


def quote_line(repo: InMemoryRepository, sku: str, quantity: int) -> Decimal:
    """Gross price for one order line: bulk discount, then VAT, rounded to cents."""
    product = repo.product(sku)
    subtotal = product.unit_price * quantity
    if quantity >= 100:
        subtotal = subtotal * Decimal("0.85")
    elif quantity >= 20:
        subtotal = subtotal * Decimal("0.93")
    gross = subtotal * (1 + VAT_RATE)
    return gross.quantize(CENT, rounding=ROUND_HALF_UP)


def quote_order(repo: InMemoryRepository, lines: dict[str, int]) -> Decimal:
    """Gross price for a whole order; the bulk discount uses the TOTAL quantity across lines."""
    total_qty = sum(lines.values())
    subtotal = sum((repo.product(sku).unit_price * qty for sku, qty in lines.items()), Decimal("0"))
    if total_qty >= 100:
        subtotal = subtotal * Decimal("0.85")
    elif total_qty >= 20:
        subtotal = subtotal * Decimal("0.93")
    gross = subtotal * (1 + VAT_RATE)
    return gross.quantize(CENT, rounding=ROUND_HALF_UP)
