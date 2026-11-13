from __future__ import annotations

from dataclasses import dataclass

from .repository import InMemoryRepository


@dataclass(frozen=True)
class LowStockLine:
    sku: str
    name: str
    available: int
    reorder_level: int
    shortfall: int
    supplier: str


def low_stock_report(repo: InMemoryRepository) -> list[LowStockLine]:
    """Active products whose available stock is at or below the reorder level, largest shortfall first
    (ties broken by SKU)."""
    out = []
    for sku, item in repo.stock.items():
        product = repo.products.get(sku)
        if product is None or not product.active:
            continue
        if item.available <= item.reorder_level:
            supplier = repo.suppliers[product.supplier_id].name
            out.append(LowStockLine(sku, product.name, item.available, item.reorder_level,
                                    item.reorder_level - item.available, supplier))
    return sorted(out, key=lambda line: (-line.shortfall, line.sku))


def stock_value(repo: InMemoryRepository) -> dict[str, str]:
    """Net value of on-hand stock per supplier, as strings with two decimals."""
    totals: dict[str, object] = {}
    for sku, item in repo.stock.items():
        p = repo.products[sku]
        totals[p.supplier_id] = totals.get(p.supplier_id, 0) + p.unit_price * item.on_hand
    return {k: f"{v:.2f}" for k, v in sorted(totals.items())}
