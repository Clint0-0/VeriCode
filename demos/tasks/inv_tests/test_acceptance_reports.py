"""Benchmark acceptance for a test-writing task: tests/test_reports.py must exist, pass on the real code and
fail on deliberately broken versions of inventory/reports.py (mutation check)."""
import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "tests" / "test_reports.py"
REPORTS = ROOT / "inventory" / "reports.py"
MUTANTS = {
    "inactive products not excluded": ("if product is None or not product.active:", "if product is None:"),
    "threshold exclusive": ("item.available <= item.reorder_level", "item.available < item.reorder_level"),
    "wrong order": ("key=lambda line: (-line.shortfall, line.sku)", "key=lambda line: (line.shortfall, line.sku)"),
    "value not two decimals": ('f"{v:.2f}"', 'f"{v}"'),
}


def _run(root: Path) -> int:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_reports.py"],
                          cwd=root, env=env, capture_output=True, timeout=120).returncode


def test_generated_tests_exist_and_cover_both_functions() -> None:
    assert GENERATED.is_file(), "tests/test_reports.py was not written"
    tree = ast.parse(GENERATED.read_text())
    tests = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    assert len(tests) >= 5, f"expected at least 5 test functions, found {len(tests)}"
    text = GENERATED.read_text()
    assert "low_stock_report" in text and "stock_value" in text


def test_generated_tests_pass_on_real_code() -> None:
    assert _run(ROOT) == 0


@pytest.mark.parametrize("name", list(MUTANTS))
def test_generated_tests_catch_mutant(name: str, tmp_path: Path) -> None:
    old, new = MUTANTS[name]
    src = REPORTS.read_text()
    assert old in src, "reports.py was changed; this task must not modify it"
    copy = tmp_path / "proj"
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache"))
    (copy / "inventory" / "reports.py").write_text(src.replace(old, new))
    assert _run(copy) != 0, f"the generated tests did not detect the mutant: {name}"
