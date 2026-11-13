from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SKU_PATTERN = r"^[A-Z]{3}-\d{4}$"


class Supplier(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=2, max_length=16)
    name: str
    lead_time_days: int = Field(default=7, ge=0, le=120)


class Product(BaseModel):
    sku: str = Field(pattern=SKU_PATTERN)
    name: str = Field(min_length=1, max_length=80)
    unit_price: Decimal = Field(gt=0, decimal_places=2)
    supplier_id: str
    active: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return " ".join(v.split())


class StockItem(BaseModel):
    sku: str = Field(pattern=SKU_PATTERN)
    on_hand: int = Field(default=0, ge=0)
    reserved: int = Field(default=0, ge=0)
    reorder_level: int = Field(default=5, ge=0)

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved
