"""Benchmark dataset validity: every task is unsolved at its starting state and solvable.

For each catalog task with a reference solution: (1) pristine project tests pass; (2) with the task's seed files
and acceptance tests added, the checks FAIL (the task is not already done); (3) with the reference solution
applied, every check PASSES (the task is solvable and the acceptance tests are correct). Reference solutions
are only used here, never shown to an agent."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT

TASKS = ROOT / "demos" / "tasks"
CATALOG = json.loads((TASKS / "catalog.json").read_text())
REQUIRED_META = ("language", "repo_size", "category", "api_risk", "expected_changes", "expected_api_findings")


def _checks(root: Path, language: str) -> list[list[str]]:
    if language == "python":
        return [[str(root / ".venv" / "bin" / "python"), "-m", "pytest", "-q", "-p", "no:cacheprovider"]]
    return [[str(root / "node_modules" / ".bin" / "vitest"), "run"], [str(root / "node_modules" / ".bin" / "tsc"), "--noEmit"]]


def _passes(root: Path, language: str) -> bool:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(root), "PYTHONDONTWRITEBYTECODE": "1", "CI": "1"}
    return all(subprocess.run(c, cwd=root, env=env, capture_output=True, timeout=300).returncode == 0 for c in _checks(root, language))


def _copy(project: Path, dst: Path) -> Path:
    shutil.copytree(project, dst, symlinks=True, ignore=shutil.ignore_patterns(".venv", "node_modules", "__pycache__", ".pytest_cache"))
    for heavy in (".venv", "node_modules"):
        if (project / heavy).exists():
            os.symlink(project / heavy, dst / heavy)
    return dst


def _installed(t: dict) -> bool:
    project = ROOT / "demos" / t["project"]
    return (project / ".venv").is_dir() if t["language"] == "python" else (project / "node_modules").is_dir()


def test_catalog_metadata_complete_and_ids_unique() -> None:
    ids = [t["id"] for t in CATALOG]
    assert len(ids) == len(set(ids))
    assert len(CATALOG) >= 12
    for t in CATALOG:
        missing = [k for k in REQUIRED_META if not t.get(k)]
        assert not missing, f"{t['id']}: missing metadata {missing}"
        for rel in list(t.get("acceptance_tests", {}).values()) + list(t.get("seed_files", {}).values()) + list((t.get("reference") or {}).values()):
            assert (TASKS / rel).is_file(), f"{t['id']}: {rel} missing"
    assert {t["language"] for t in CATALOG} == {"python", "typescript"}
    assert {t["repo_size"] for t in CATALOG} >= {"small", "medium", "large"}
    assert {t["category"] for t in CATALOG} >= {"feature", "bugfix", "refactor", "tests", "modification"}
    assert {t["api_risk"] for t in CATALOG} >= {"dependency_api", "none"}


@pytest.mark.parametrize("task", [t for t in CATALOG if t.get("reference")], ids=lambda t: t["id"])
def test_task_is_unsolved_at_start_and_solved_by_reference(task: dict, tmp_path: Path) -> None:
    if not _installed(task):
        pytest.skip(f"{task['project']} dependencies not installed (scripts/setup_benchmark_repos.sh)")
    project = ROOT / "demos" / task["project"]
    pristine = _copy(project, tmp_path / "pristine")
    assert _passes(pristine, task["language"]), "pristine project tests must pass"

    work = _copy(project, tmp_path / "work")
    for dst, src in {**task.get("seed_files", {}), **task.get("acceptance_tests", {})}.items():
        (work / dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TASKS / src, work / dst)
    assert not _passes(work, task["language"]), "the task must not be solved at its starting state"

    for dst, src in task["reference"].items():
        (work / dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TASKS / src, work / dst)
    assert _passes(work, task["language"]), "the reference solution must pass every check"
