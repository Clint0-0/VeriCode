from __future__ import annotations


class InventoryError(Exception):
    """Base class for inventory errors."""


class UnknownSkuError(InventoryError):
    def __init__(self, sku: str) -> None:
        super().__init__(f"unknown SKU {sku}")
        self.sku = sku


class OutOfStockError(InventoryError):
    def __init__(self, sku: str, requested: int, available: int) -> None:
        super().__init__(f"{sku}: requested {requested}, only {available} available")
        self.sku, self.requested, self.available = sku, requested, available
