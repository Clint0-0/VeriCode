from decimal import Decimal

import pytest

from inventory import InMemoryRepository, InventoryService, Product, Supplier


@pytest.fixture
def repo() -> InMemoryRepository:
    r = InMemoryRepository()
    r.add_supplier(Supplier(id="ACME", name="Acme Parts", lead_time_days=5))
    r.add_supplier(Supplier(id="GLOBEX", name="Globex"))
    r.add_product(Product(sku="BLT-0001", name="Bolt M6", unit_price=Decimal("0.20"), supplier_id="ACME"), on_hand=500, reorder_level=100)
    r.add_product(Product(sku="NUT-0002", name="Nut  M6", unit_price=Decimal("0.10"), supplier_id="ACME"), on_hand=40, reorder_level=50)
    r.add_product(Product(sku="GEA-0100", name="Gearbox", unit_price=Decimal("129.00"), supplier_id="GLOBEX"), on_hand=3, reorder_level=2)
    r.add_product(Product(sku="OLD-0009", name="Legacy pulley", unit_price=Decimal("9.99"), supplier_id="GLOBEX", active=False), on_hand=0)
    return r


@pytest.fixture
def service(repo: InMemoryRepository) -> InventoryService:
    return InventoryService(repo)
