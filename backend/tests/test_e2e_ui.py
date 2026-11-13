"""End-to-end UI tests: real server (uvicorn subprocess, temp DB) + real browser (Playwright/Chromium).
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
    from playwright.sync_api import expect, sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = expect = None

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



def choose(page, label: str, value: str) -> None:
    """Pick an option in the custom dropdown the way a user does: open it, click the option."""
    page.get_by_role("button", name=label, exact=True).click()
    page.get_by_role("listbox").locator(f'[role="option"][data-value="{value}"]').click()
    expect(page.get_by_role("listbox")).to_have_count(0)

def test_login_required_then_token_url(page, server):
    page.goto(f"{server}/#dashboard")
    page.get_by_label("Access token").wait_for()
    page.goto(f"{server}/?token=e2e-token#dashboard")
    page.get_by_role("heading", name="Dashboard").wait_for()
    assert "token=" not in page.url  # token stripped from the address bar
    page.get_by_text("mock (scripted offline demo)").wait_for()


def test_track1_stale_answer_flow(page, server):
    page.goto(f"{server}/#stale")
    page.get_by_role("button", name="Load Demo 2 answer").click()
    page.wait_for_function("document.querySelector('textarea').value.length > 50")
    page.get_by_label("Offline fixture (labelled, reproducible)").check()
    page.get_by_role("button", name="Extract & verify claims").click()
    page.get_by_text("Evidence below comes from the").wait_for(timeout=30000)
    page.get_by_title("claim_001: CONTRADICTED").click()
    page.get_by_text("Contradicting evidence (1)").first.wait_for()
    page.get_by_role("button", name="Generate corrected answer").click()
    corrected = page.get_by_text("Python 3.14 is the latest stable version of Python. [1]")
    corrected.first.wait_for()
    page.get_by_role("link", name="Evidence Explorer").first.click()
    page.get_by_role("heading", name="Evidence Explorer").wait_for()
    assert page.locator("table tbody tr").count() >= 4


def test_track1_combined_installed_source(page, server):
    page.goto(f"{server}/#stale")
    page.get_by_label("LLM answer").fill("In Pydantic, use the @validator decorator to validate fields.")
    page.get_by_label("Offline fixture (labelled, reproducible)").check()
    choose(page, "Installed packages workspace", "sample_project")
    page.get_by_role("button", name="Extract & verify claims").click()
    page.get_by_text("installed_source", exact=True).first.wait_for(timeout=30000)
    page.get_by_title("claim_001: CONTRADICTED").wait_for()


def test_track2_preflight_heatmap_and_coding_task(page, server):
    page.goto(f"{server}/#preflight")
    choose(page, "Demo task", "users")
    page.get_by_role("button", name="Run pre-flight").click()
    heat = page.get_by_role("table", name="API confidence heatmap")
    heat.wait_for(timeout=60000)
    assert "INCOMPATIBLE" in heat.inner_text() and "DEPRECATED" in heat.inner_text()
    page.goto(f"{server}/#workspace")
    choose(page, "Demo task", "users")
    page.get_by_role("button", name="Run task").click()
    page.get_by_text("auto-corrected 3/3 flagged APIs").wait_for(timeout=120000)
    page.get_by_role("button", name="Apply to workspace").wait_for()
    assert page.locator("pre").filter(has_text="field_validator").count() >= 1


def test_every_screen_renders_without_console_errors(page, server):
    for hash_, heading in [("dashboard", "Dashboard"), ("workspace", "Coding Workspace"), ("preflight", "Pre-Flight Inspector"),
                           ("stale", "Stale-Answer Detector"), ("evidence", "Evidence Explorer"), ("tokens", "Token Analytics"),
                           ("history", "Task History"), ("settings", "Settings & Rules")]:
        page.goto(f"{server}/#{hash_}")
        page.get_by_role("heading", name=heading, level=1).wait_for()
        page.wait_for_timeout(300)
    page.goto(f"{server}/#tokens")
    page.get_by_text("Tokens by measurement type").wait_for()
    assert page.get_by_text("MOCK").first.is_visible()
    real = [e for e in page.errors if "401" not in e]  # pre-login 401s are expected
    assert real == [], real


def test_mobile_layout(page, server):
    page.set_viewport_size({"width": 400, "height": 850})
    page.goto(f"{server}/#dashboard")
    page.get_by_role("heading", name="Dashboard").wait_for()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    page.set_viewport_size({"width": 1400, "height": 1000})
