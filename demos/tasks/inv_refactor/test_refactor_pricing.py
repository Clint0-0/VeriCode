"""Benchmark acceptance: the bulk-discount + VAT logic lives in one helper used by both quote functions."""
import ast
from decimal import Decimal
from pathlib import Path

from inventory import pricing

SOURCE = Path(pricing.__file__).read_text()
TREE = ast.parse(SOURCE)


def _function(name: str) -> ast.FunctionDef:
    return next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)


def _calls(fn: ast.FunctionDef) -> set[str]:
    return {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def test_helper_exists_and_is_used_by_both() -> None:
    helper = _function("apply_bulk_discount_and_vat")
    assert [a.arg for a in helper.args.args] == ["subtotal", "quantity"]
    assert "apply_bulk_discount_and_vat" in _calls(_function("quote_line"))
    assert "apply_bulk_discount_and_vat" in _calls(_function("quote_order"))


def test_tier_rates_and_vat_written_once() -> None:
    for literal in ('"0.85"', '"0.93"', "VAT_RATE)"):
        assert SOURCE.count(literal) == 1, f"{literal} should appear exactly once after the refactor"


def test_helper_behaviour() -> None:
    f = pricing.apply_bulk_discount_and_vat
    assert f(Decimal("10.00"), 1) == Decimal("11.90")
    assert f(Decimal("10.00"), 20) == Decimal("11.07")
    assert f(Decimal("10.00"), 100) == Decimal("10.12")
    assert f(Decimal("10.00"), 19) == Decimal("11.90")


def test_behaviour_unchanged(repo) -> None:
    assert pricing.quote_line(repo, "BLT-0001", 10) == Decimal("2.38")
    assert pricing.quote_line(repo, "BLT-0001", 100) == Decimal("20.23")
    assert pricing.quote_order(repo, {"BLT-0001": 60, "NUT-0002": 40}) == Decimal("16.18")
    assert pricing.quote_order(repo, {"GEA-0100": 1}) == Decimal("153.51")
