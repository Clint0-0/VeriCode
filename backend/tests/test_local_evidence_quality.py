"""Local (installed-source) evidence quality: multiple Python and TypeScript packages, import-name resolution,
attribution, workspace selection, version-change invalidation, and no rewriting."""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vericode import jsinspect, security, stale
from vericode.config import ROOT, settings
from vericode.local_evidence import _import_name, candidate_symbols

NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)
TS = ROOT / "demos" / "ts_project"
needs_ts = pytest.mark.skipif(not (jsinspect.ts_checker_available() and (TS / "node_modules").is_dir()), reason="ts demo not installed")


@pytest.fixture
def empty(tmp_path):
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"sources": []}))
    return p


def run(text, ws, fixture):
    return stale.analyze(text, mode="fixture", fixture=fixture, now=NOW, workspace=ws)["claims"]


def test_public_import_name_for_multi_toplevel_dists(sample_project):
    sp = next((sample_project / ".venv" / "lib").glob("python*/site-packages"))
    dist = next(sp.glob("pytest-*.dist-info"))
    assert _import_name(str(dist), "pytest") == "pytest"  # regression: was "_pytest" (first top_level entry)
    assert _import_name(str(next(sp.glob("pydantic-*.dist-info"))), "pydantic") == "pydantic"


@pytest.mark.parametrize("text,status,needle", [
    ("In pytest, the yield_fixture decorator is the recommended way to write fixtures.", "CONTRADICTED", "deprecated"),
    ("Pytest provides the approx helper for floating point comparisons.", "CURRENT_SUPPORTED", "exists"),
    ("In pydantic, the validator decorator is deprecated.", "CURRENT_SUPPORTED", "deprecated"),
    ("Pydantic removed the BaseModel.dict() method.", "CONTRADICTED", "still provides"),
    ("You can import the pydantic BaseSettings class directly from pydantic.", "CONTRADICTED", "pydantic-settings"),
])
def test_python_packages(sample_project, empty, text, status, needle):
    c = run(text, "sample_project", empty)[0]
    assert c["status"] == status, c["explanation"]
    ev = c["evidence"][0]
    assert ev["origin"] == "installed_source" and ev["method"] == "installed_source" and ev["url"].startswith("installed://")
    assert needle in (ev["excerpt"] + ev["relevance_explanation"])
    assert c["correction"] is None  # installed-source evidence never rewrites the answer


@needs_ts
@pytest.mark.parametrize("text,status,pkg", [
    ("In zod, ZodString.nonempty() is the recommended way to require a value.", "CONTRADICTED", "zod@3.23.8"),
    ("In vitest, the describe function is deprecated.", "CONTRADICTED", "vitest@2.1.9"),
    ("The typescript package exports the createProgram function.", "CURRENT_SUPPORTED", "typescript@5.9.3"),
    ("Vitest provides the vi.useFakeTimers helper.", "CURRENT_SUPPORTED", "vitest@2.1.9"),
])
def test_typescript_packages(empty, text, status, pkg):
    c = run(text, "ts_project", empty)[0]
    assert c["status"] == status
    assert c["evidence"][0]["domain"] == pkg and c["evidence"][0]["authority_tier"] == "primary"


def test_installed_source_is_never_labelled_live(sample_project, empty):
    c = run("In pydantic, the validator decorator is deprecated.", "sample_project", empty)[0]
    assert all(e["origin"] != "live_tavily" for e in c["evidence"])
    assert "version-specific" in c["evidence"][0]["source_type"]


def test_unknown_workspace_rejected(empty):
    with pytest.raises(security.SecurityError):
        run("In pydantic, the validator decorator is deprecated.", "../../etc", empty)


def test_claim_without_installed_package_gets_no_local_evidence(sample_project, empty):
    c = run("In Django, the url() function was removed.", "sample_project", empty)[0]
    assert not any(e["origin"] == "installed_source" for e in c["evidence"])


def test_symbol_candidates():
    assert candidate_symbols("use `BaseModel.model_dump()` not @validator") [:2] == ["BaseModel.model_dump", "validator"]
    assert "vi.useFakeTimers" in candidate_symbols("Vitest provides the vi.useFakeTimers helper.")


def test_version_change_invalidates_local_evidence(tmp_path, monkeypatch, empty):
    ws_root = tmp_path / "ws"
    proj = ws_root / "proj"
    sp = proj / ".venv" / "lib" / "python3.12" / "site-packages"
    (sp / "acmelib").mkdir(parents=True)
    (proj / "requirements.txt").write_text("acmelib>=1\n")

    def install(version, deprecated):
        for d in sp.glob("acmelib-*.dist-info"):
            shutil.rmtree(d)
        di = sp / f"acmelib-{version}.dist-info"
        di.mkdir()
        (di / "METADATA").write_text(f"Name: acmelib\nVersion: {version}\n")
        body = ('from typing_extensions import deprecated\n@deprecated("connect() is deprecated; use open_session()")\n'
                if deprecated else "") + "def connect(url): ...\n"
        (sp / "acmelib" / "__init__.py").write_text(body)
    monkeypatch.setattr(settings, "workspaces_root", str(ws_root))
    install("1.0.0", deprecated=False)
    c1 = run("Acmelib provides the connect() function for opening sessions.", "proj", empty)[0]
    assert c1["status"] == "CURRENT_SUPPORTED" and "acmelib@1.0.0" == c1["evidence"][0]["domain"]
    install("2.0.0", deprecated=True)  # dependency upgraded: cached environment must not be reused
    c2 = run("Acmelib provides the connect() function for opening sessions.", "proj", empty)[0]
    assert c2["status"] == "CONTRADICTED" and c2["evidence"][0]["domain"] == "acmelib@2.0.0"
    assert "open_session" in c2["evidence"][0]["excerpt"]
