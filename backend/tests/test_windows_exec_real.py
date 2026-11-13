"""Real (unmocked) launch of the ts_orders checks through the process sandbox, from a path containing spaces.

Reproduces the Windows Coding Workspace failure: right after the CODER stage, run_checks() runs `npm test`;
on Windows npm is `npm.cmd`, which subprocess (list form, no shell) cannot find -> FileNotFoundError [WinError 2].
Runs on any OS where npm is installed and demos/ts_orders has node_modules (CI: Linux and Windows jobs)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from vericode.security import run_command

DEMO = Path(__file__).resolve().parents[2] / "demos" / "ts_orders"

pytestmark = pytest.mark.skipif(not shutil.which("npm") or not (DEMO / "node_modules" / "vitest").is_dir(),
                                reason="needs npm and `npm ci` in demos/ts_orders")


@pytest.fixture
def workspace(tmp_path):
    dst = tmp_path / "copy with spaces" / "ts_orders"
    shutil.copytree(DEMO, dst, symlinks=True)
    return dst


@pytest.mark.parametrize("argv", [["npm", "test"], ["npm", "run", "typecheck"]])
def test_npm_checks_launch_in_process_sandbox(workspace, argv):
    r = run_command(argv, workspace, backend="process", timeout=240)
    assert r.returncode == 0, (r.stdout[-2000:], r.stderr[-2000:])
