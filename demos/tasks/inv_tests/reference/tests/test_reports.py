from decimal import Decimal

from inventory import InMemoryRepository, Product, Supplier
from inventory.reports import low_stock_report, stock_value


def test_low_stock_includes_items_at_or_below_reorder_level(repo) -> None:
    skus = [line.sku for line in low_stock_report(repo)]
    assert "NUT-0002" in skus  # 40 <= 50
    assert "BLT-0001" not in skus  # 500 > 100


def test_threshold_is_inclusive(repo, service) -> None:
    service.reserve("BLT-0001", 400)  # available 100 == reorder level
    assert "BLT-0001" in [line.sku for line in low_stock_report(repo)]


def test_inactive_products_excluded(repo) -> None:
    assert "OLD-0009" not in [line.sku for line in low_stock_report(repo)]


def test_sorted_by_shortfall_then_sku(repo, service) -> None:
    service.reserve("GEA-0100", 3)  # available 0, shortfall 2
    lines = low_stock_report(repo)
    assert [line.sku for line in lines] == ["NUT-0002", "GEA-0100"]
    assert lines[0].shortfall == 10 and lines[0].supplier == "Acme Parts"


def test_empty_repository() -> None:
    assert low_stock_report(InMemoryRepository()) == []
    assert stock_value(InMemoryRepository()) == {}


def test_stock_value_per_supplier(repo) -> None:
    assert stock_value(repo) == {"ACME": "104.00", "GLOBEX": "387.00"}


def test_stock_value_two_decimals() -> None:
    r = InMemoryRepository()
    r.add_supplier(Supplier(id="S1", name="One"))
    r.add_product(Product(sku="AAA-0001", name="a", unit_price=Decimal("2.5"), supplier_id="S1"), on_hand=2)
    assert stock_value(r) == {"S1": "5.00"}
