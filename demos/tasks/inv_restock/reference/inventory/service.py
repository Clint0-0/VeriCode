from __future__ import annotations

from .errors import OutOfStockError
from .models import RestockRequest, StockItem
from .repository import InMemoryRepository


class InventoryService:
    def __init__(self, repo: InMemoryRepository) -> None:
        self.repo = repo

    def receive(self, sku: str, quantity: int) -> StockItem:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        item = self.repo.stock_item(sku)
        updated = item.model_copy(update={"on_hand": item.on_hand + quantity})
        self.repo.save_stock(updated)
        return updated

    def reserve(self, sku: str, quantity: int) -> StockItem:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.repo.product(sku)
        item = self.repo.stock_item(sku)
        if item.available < quantity:
            raise OutOfStockError(sku, quantity, item.available)
        updated = item.model_copy(update={"reserved": item.reserved + quantity})
        self.repo.save_stock(updated)
        return updated

    def release(self, sku: str, quantity: int) -> StockItem:
        item = self.repo.stock_item(sku)
        updated = item.model_copy(update={"reserved": max(0, item.reserved - quantity)})
        self.repo.save_stock(updated)
        return updated

    def ship(self, sku: str, quantity: int) -> StockItem:
        item = self.repo.stock_item(sku)
        if quantity > item.reserved:
            raise ValueError(f"cannot ship {quantity}: only {item.reserved} reserved")
        updated = item.model_copy(update={"reserved": item.reserved - quantity, "on_hand": item.on_hand - quantity})
        self.repo.save_stock(updated)
        return updated

    def request_restock(self, sku: str, quantity: int, note: str | None = None) -> RestockRequest:
        product = self.repo.product(sku)
        if not product.active:
            raise ValueError(f"{sku} is inactive")
        return RestockRequest(sku=sku, quantity=quantity, supplier_id=product.supplier_id, note=note)
