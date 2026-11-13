from __future__ import annotations

from .errors import UnknownSkuError
from .models import Product, StockItem, Supplier


class InMemoryRepository:
    """Stores products, stock and suppliers in dictionaries keyed by SKU / supplier id."""

    def __init__(self) -> None:
        self.products: dict[str, Product] = {}
        self.stock: dict[str, StockItem] = {}
        self.suppliers: dict[str, Supplier] = {}

    def add_supplier(self, supplier: Supplier) -> None:
        self.suppliers[supplier.id] = supplier

    def add_product(self, product: Product, on_hand: int = 0, reorder_level: int = 5) -> None:
        if product.supplier_id not in self.suppliers:
            raise ValueError(f"unknown supplier {product.supplier_id}")
        self.products[product.sku] = product
        self.stock[product.sku] = StockItem(sku=product.sku, on_hand=on_hand, reorder_level=reorder_level)

    def product(self, sku: str) -> Product:
        try:
            return self.products[sku]
        except KeyError:
            raise UnknownSkuError(sku) from None

    def stock_item(self, sku: str) -> StockItem:
        try:
            return self.stock[sku]
        except KeyError:
            raise UnknownSkuError(sku) from None

    def save_stock(self, item: StockItem) -> None:
        self.stock[item.sku] = item
