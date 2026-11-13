from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from .errors import CurrencyError

# ISO 4217 code -> number of minor-unit digits
MINOR_UNITS: dict[str, int] = {"EUR": 2, "USD": 2, "GBP": 2, "CHF": 2, "JPY": 0, "SEK": 2, "KWD": 3}


def check(code: str) -> str:
    code = code.upper()
    if code not in MINOR_UNITS:
        raise CurrencyError(f"unsupported currency {code}")
    return code


def quantum(code: str) -> Decimal:
    return Decimal(1).scaleb(-MINOR_UNITS[check(code)])


def round_amount(amount: Decimal, code: str) -> Decimal:
    """Banker's rounding to the currency's minor unit (accounting convention)."""
    return amount.quantize(quantum(code), rounding=ROUND_HALF_EVEN)
