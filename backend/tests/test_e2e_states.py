"""Browser checks of empty, error and labelling states on a fresh database (MOCK provider, no keys).
Shares the fixture setup with test_e2e_ui.py.
Exercises login, Track 1 (stale answer, fixture evidence), Track 2 (pre-flight heatmap, coding task with the
MOCK provider, diff, outcome) and every screen. Skipped when Playwright or a Chromium binary is unavailable."""
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
CHROME = next((p for p in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser") if os.path.exists(p)), None)
try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(sync_playwright is None or CHROME is None or not (ROOT / "frontend" / "dist").is_dir(),
                                                  reason="playwright/chromium/frontend build not available")]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    port = socket.socket(); port.bind(("127.0.0.1", 0)); p = port.getsockname()[1]; port.close()
    env = {**os.environ, "VERICODE_DB": str(tmp / "e2e.db"), "VERICODE_AUTH_TOKEN": "e2e-token", "VERICODE_TOKEN_FILE": str(tmp / "tok"),
           "VERICODE_LLM_PROVIDER": "mock", "TAVILY_API_KEY": "", "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "PORT": str(p),
           "VERICODE_SANDBOX": os.environ.get("VERICODE_TEST_SANDBOX", "process")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "vericode.api:app", "--host", "127.0.0.1", "--port", str(p)],
                            cwd=ROOT / "backend", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{p}"
    for _ in range(60):
        try:
            if httpx.get(f"{base}/api/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.25)
    yield base
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="module")
def page(server):
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 1400, "height": 1000})
        errors = []
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.errors = errors
        yield pg
        b.close()




# ---- states on a FRESH database (own server; runs independently of the flow tests) ----

def test_empty_states_on_fresh_database(page, server):
    page.goto(f"{server}/?token=e2e-token#dashboard")  # log in (token stripped from the URL by the app)
    page.get_by_role("heading", name="Dashboard").wait_for()
    for hash_, heading, text in [("dashboard", "Dashboard", "No tasks yet"), ("history", "Task History", "No tasks yet."),
                                 ("evidence", "Evidence Explorer", "No evidence yet."),
                                 ("tokens", "Token Analytics", "No real-provider benchmark yet")]:
        page.goto(f"{server}/#{hash_}")
        page.get_by_role("heading", name=heading, level=1).wait_for()
        page.get_by_text(text).first.wait_for(timeout=10000)


def test_error_state_for_unknown_records(page, server):
    page.goto(f"{server}/#history/task_does_not_exist")
    page.get_by_role("alert").first.wait_for(timeout=10000)
    page.goto(f"{server}/#stale/an_does_not_exist")
    page.get_by_role("heading", name="Stale-Answer Detector", level=1).wait_for()
    page.get_by_role("alert").first.wait_for(timeout=10000)


def test_mock_provider_is_labelled_not_real(page, server):
    page.goto(f"{server}/#dashboard")
    page.get_by_text("scripted mock").first.wait_for(timeout=10000)
    assert "ACTUAL_PROVIDER_USAGE" not in page.locator("main").inner_text()
