from decimal import Decimal

import pytest
from pydantic import ValidationError

from inventory import Product, StockItem, Supplier


def test_product_validates_sku_and_normalises_name() -> None:
    p = Product(sku="ABC-1234", name="  Hex   key ", unit_price=Decimal("1.50"), supplier_id="ACME")
    assert p.name == "Hex key"
    with pytest.raises(ValidationError):
        Product(sku="abc-1", name="x", unit_price=Decimal("1"), supplier_id="ACME")
    with pytest.raises(ValidationError):
        Product(sku="ABC-1234", name="x", unit_price=Decimal("0"), supplier_id="ACME")


def test_supplier_is_frozen() -> None:
    s = Supplier(id="ACME", name="Acme")
    with pytest.raises(ValidationError):
        s.name = "Other"  # type: ignore[misc]


def test_stock_available() -> None:
    assert StockItem(sku="ABC-1234", on_hand=10, reserved=3).available == 7
