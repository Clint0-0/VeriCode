"""Browser test over REAL persisted live results (Groq + Tavily), not mock fixtures.

Runs only when VERICODE_LIVE_DB points at a database produced by `python -m vericode.live_validation`. A copy is
served by a real uvicorn process and inspected in Chromium. Expected values (analysis ids, live source domains,
task ids, benchmark ids) are read from that database, then must be visible on the eight screens.
"""
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
CHROME = next((p for p in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser") if os.path.exists(p)), None)
LIVE_DB = os.environ.get("VERICODE_LIVE_DB", "")
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

pytestmark = [pytest.mark.e2e, pytest.mark.live,
              pytest.mark.skipif(not (LIVE_DB and Path(LIVE_DB).is_file()), reason="VERICODE_LIVE_DB not set (needs a live-validation DB)"),
              pytest.mark.skipif(sync_playwright is None or CHROME is None or not (ROOT / "frontend" / "dist").is_dir(),
                                 reason="playwright/chromium/frontend build not available")]
SECRETS = [v for v in (os.environ.get("OPENAI_API_KEY"), os.environ.get("TAVILY_API_KEY"), os.environ.get("ANTHROPIC_API_KEY")) if v and len(v) > 8]


@pytest.fixture(scope="module")
def facts(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("live_e2e")
    db = tmp / "live.db"
    shutil.copy2(LIVE_DB, db)
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    q = lambda sql: [dict(r) for r in c.execute(sql)]
    f = {"db": db, "tmp": tmp,
         "analyses": q("SELECT id, evidence_mode FROM analyses WHERE evidence_mode='live_tavily' ORDER BY created_at DESC"),
         "claims": q("SELECT analysis_id, claim_id, claim, status, confidence FROM claims"),
         "live_domains": [r["domain"] for r in q("SELECT DISTINCT domain FROM evidence WHERE origin='live_tavily' LIMIT 5")],
         "tasks": q("SELECT id, mode, status, success FROM tasks ORDER BY created_at DESC"),
         "benchmarks": q("SELECT id FROM benchmarks ORDER BY created_at DESC")}
    c.close()
    assert f["analyses"] and f["live_domains"] and f["tasks"], "live DB holds no live results"
    return f


@pytest.fixture(scope="module")
def server(facts):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = {**os.environ, "VERICODE_DB": str(facts["db"]), "VERICODE_AUTH_TOKEN": "live-e2e-token",
           "VERICODE_TOKEN_FILE": str(facts["tmp"] / "tok"), "PORT": str(port)}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "vericode.api:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=ROOT / "backend", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            if httpx.get(f"{base}/api/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.25)
    yield base
    proc.terminate()
    out = proc.communicate(timeout=10)[0].decode(errors="replace")
    assert not any(k in out for k in SECRETS), "a configured key appeared in server logs"


@pytest.fixture(scope="module")
def page(server):
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1400, "height": 1000})
        pg.errors = []
        pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
        bodies = []
        pg.on("response", lambda r: bodies.append(r) if "/api/" in r.url else None)
        pg.api_responses = bodies
        pg.goto(f"{server}/?token=live-e2e-token#dashboard")
        pg.get_by_role("heading", name="Dashboard", level=1).wait_for()
        yield pg
        b.close()


def _text(page) -> str:
    page.wait_for_timeout(600)
    return page.locator("main").inner_text() if page.locator("main").count() else page.inner_text("body")


def test_dashboard_shows_actual_usage(page, server):
    page.goto(f"{server}/#dashboard")
    page.get_by_role("heading", name="Dashboard", level=1).wait_for()
    assert "ACTUAL_PROVIDER_USAGE" in _text(page)


def test_stale_detector_shows_live_sources_confidence_and_status(page, server, facts):
    a = facts["analyses"][0]
    claims = [c for c in facts["claims"] if c["analysis_id"] == a["id"]]
    claim = next((c for c in claims if c["confidence"] is not None), claims[0])
    page.goto(f"{server}/#stale/{a['id']}")
    page.get_by_role("heading", name="Stale-Answer Detector", level=1).wait_for()
    page.get_by_text(claim["claim"][:40]).first.wait_for(timeout=15000)
    assert claim["status"] in _text(page) and "live" in _text(page).lower()
    page.locator(f"#claim-{claim['claim_id']}").get_by_text(claim["claim"][:40]).first.click()  # expand the card
    page.get_by_text("Verification confidence (index)").first.wait_for(timeout=10000)
    if claim["confidence"] is not None:
        assert f"{claim['confidence']:g} / 100" in _text(page) or f"{claim['confidence']} / 100" in _text(page)


def test_evidence_explorer_lists_live_tavily_sources(page, server, facts):
    page.goto(f"{server}/#evidence")
    page.get_by_role("heading", name="Evidence Explorer", level=1).wait_for()
    page.locator("table tbody tr").first.wait_for(timeout=15000)
    txt = _text(page)
    assert "live_tavily" in txt
    assert any(d in txt for d in facts["live_domains"]), facts["live_domains"]


def test_task_history_and_preflight_detail(page, server, facts):
    page.goto(f"{server}/#history")
    page.get_by_role("heading", name="Task History", level=1).wait_for()
    page.get_by_text(facts["tasks"][0]["id"]).first.wait_for(timeout=15000)
    vt = next((t for t in facts["tasks"] if t["mode"] == "vericode" and t["success"]), None)
    if vt:
        page.goto(f"{server}/#history/{vt['id']}")
        page.get_by_text(vt["id"]).first.wait_for(timeout=15000)
        assert "ACTUAL_PROVIDER_USAGE" in _text(page)


def test_token_analytics_actual_and_not_mock(page, server, facts):
    page.goto(f"{server}/#tokens")
    page.get_by_role("heading", name="Token Analytics", level=1).wait_for()
    page.get_by_text("Tokens by measurement type").wait_for()
    txt = _text(page)
    assert "ACTUAL_PROVIDER_USAGE" in txt
    if facts["benchmarks"]:
        assert any(b["id"] in txt for b in facts["benchmarks"]) or "openai/gpt-oss" in txt


def test_remaining_screens_render_and_no_secrets(page, server):
    for hash_, heading in [("workspace", "Coding Workspace"), ("preflight", "Pre-Flight Inspector"), ("settings", "Settings & Rules")]:
        page.goto(f"{server}/#{hash_}")
        page.get_by_role("heading", name=heading, level=1).wait_for()
    page.wait_for_timeout(500)
    for r in page.api_responses:
        try:
            body = r.text()
        except Exception:
            continue
        assert not any(k in body for k in SECRETS), f"secret in {r.url}"
    assert not any(k in page.content() for k in SECRETS)
    real = [e for e in page.errors if "401" not in e]
    assert real == [], real
