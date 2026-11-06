"""Billing helpers for paid workspaces (unrelated to the demo tasks; adds realistic repo context)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

PLAN_PRICES = {"free": Decimal("0"), "team": Decimal("8.00"), "business": Decimal("15.00")}
TAX_RATES = {"IN": Decimal("0.18"), "DE": Decimal("0.19"), "US": Decimal("0.00")}


@dataclass
class Invoice:
    workspace: str
    plan: str
    seats: int
    country: str
    subtotal: Decimal
    tax: Decimal

    @property
    def total(self) -> Decimal:
        return (self.subtotal + self.tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def seat_price(plan: str) -> Decimal:
    if plan not in PLAN_PRICES:
        raise ValueError(f"unknown plan {plan}")
    return PLAN_PRICES[plan]


def build_invoice(workspace: str, plan: str, seats: int, country: str) -> Invoice:
    if seats < 1:
        raise ValueError("seats must be positive")
    subtotal = seat_price(plan) * seats
    rate = TAX_RATES.get(country, Decimal("0"))
    tax = (subtotal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Invoice(workspace, plan, seats, country, subtotal, tax)


def prorate(amount: Decimal, days_used: int, days_in_period: int) -> Decimal:
    if not 0 <= days_used <= days_in_period:
        raise ValueError("invalid proration window")
    return (amount * Decimal(days_used) / Decimal(days_in_period)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def apply_discount(amount: Decimal, percent: int) -> Decimal:
    if not 0 <= percent <= 100:
        raise ValueError("percent out of range")
    return (amount * (Decimal(100 - percent) / Decimal(100))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
