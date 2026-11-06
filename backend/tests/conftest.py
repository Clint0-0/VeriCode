import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


os.environ.setdefault("VERICODE_TOKEN_FILE", "/tmp/vericode_test_token")
LIVE = os.environ.get("VERICODE_LIVE_TESTS") == "1"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch, request):
    import copy
    from vericode import db
    from vericode.config import settings
    snapshot = copy.deepcopy(settings.__dict__)
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    if "live" not in request.keywords:
        monkeypatch.setattr(settings, "llm_provider", "mock")
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(settings, "sandbox_backend", os.environ.get("VERICODE_TEST_SANDBOX", "process"))
    db._conn = None
    db.init_db()
    yield
    db._conn = None
    settings.__dict__.clear()
    settings.__dict__.update(snapshot)


@pytest.fixture
def client():
    """Authenticated TestClient (cookie session + CSRF header)."""
    from fastapi.testclient import TestClient
    from vericode import auth
    from vericode.api import app
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"token": auth.access_token()})
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


@pytest.fixture
def sample_project():
    p = ROOT / "demos" / "sample_project"
    if not (p / ".venv").exists():
        pytest.skip("demo venv missing: run scripts/setup_demo.sh")
    return p


@pytest.fixture
def fake_py_project(tmp_path):
    """A tiny project with a hand-made site-packages so API checks don't depend on real installs."""
    root = tmp_path / "proj"
    sp = root / ".venv" / "lib" / "python3.12" / "site-packages"
    pkg = sp / "fakelib"
    (pkg / "sub").mkdir(parents=True)
    (sp / "fakelib-2.1.0.dist-info").mkdir()
    (sp / "fakelib-2.1.0.dist-info" / "METADATA").write_text("Metadata-Version: 2.1\nName: fakelib\nVersion: 2.1.0\nProject-URL: Documentation, https://docs.fakelib.dev\n")
    (pkg / "__init__.py").write_text("from .core import Client, connect\nfrom .sub import *\n__all__=['Client','connect']\n")
    (pkg / "core.py").write_text('''
from typing_extensions import deprecated
import warnings

class Base:
    def close(self): ...

class Client(Base):
    def __init__(self, url: str, *, timeout: float = 5.0, **kwargs):
        retries = kwargs.pop("retries", None)
        if retries is not None:
            raise TypeError("`retries` was removed, use `max_retries`")

    def send(self, data, *, compress=False): ...

    @deprecated("`fetch` is deprecated; use `send` instead.")
    def fetch(self, data): ...

def connect(url, timeout=1.0): ...

def old_connect(url):
    warnings.warn("old_connect is deprecated, use connect", DeprecationWarning)
''')
    (pkg / "sub" / "__init__.py").write_text("def helper(x, y=1): ...\n")
    (root / "requirements.txt").write_text("fakelib>=1.0\nmissinglib==3.0\n")
    (root / "app.py").write_text("import fakelib\n\ndef run():\n    return fakelib.connect('x')\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_app.py").write_text("def test_ok():\n    assert True\n")
    return root
