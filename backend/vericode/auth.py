"""Local-first authentication: one-time access token -> HttpOnly session cookie + CSRF token.

* A random access token is generated at startup (or taken from VERICODE_AUTH_TOKEN), written to
  `.vericode_token` (mode 600) and printed as a login URL, Jupyter-style.
* POST /api/auth/login exchanges it for a session cookie (HttpOnly, SameSite=Strict) and a CSRF token.
* Every /api route except health/auth requires the session (or `Authorization: Bearer <token>` for
  CLI/scripts); state-changing methods with a cookie session also require `X-CSRF-Token`.
* Host-header allowlist blocks DNS-rebinding; non-loopback exposure requires VERICODE_ALLOW_REMOTE=1.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from . import db
from .config import ROOT, settings

SESSION_COOKIE = "vc_session"
CSRF_COOKIE = "vc_csrf"
SESSION_TTL = 12 * 3600
PUBLIC_PATHS = {"/api/health", "/api/auth/login", "/api/auth/status", "/api/auth/logout"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "testserver"}
TOKEN_FILE = Path(os.environ.get("VERICODE_TOKEN_FILE", str(ROOT / ".vericode_token")))

_access_token: str | None = None


def access_token() -> str:
    global _access_token
    if _access_token is None:
        _access_token = os.environ.get("VERICODE_AUTH_TOKEN", "").strip() or secrets.token_urlsafe(24)
        try:
            TOKEN_FILE.write_text(_access_token)
            os.chmod(TOKEN_FILE, 0o600)
        except OSError:
            pass
    return _access_token


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def check_token(token: str) -> bool:
    return bool(token) and hmac.compare_digest(token.encode(), access_token().encode())


def create_session() -> tuple[str, str]:
    sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    now = time.time()
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        c.execute("INSERT INTO sessions VALUES(?,?,?,?)", (_h(sid), csrf, now, now + SESSION_TTL))
    return sid, csrf


def session_csrf(sid: str | None) -> str | None:
    if not sid:
        return None
    r = db.row("SELECT csrf, expires_at FROM sessions WHERE token_hash=?", (_h(sid),))
    if not r or r["expires_at"] < time.time():
        return None
    return r["csrf"]


def delete_session(sid: str | None) -> None:
    if sid:
        with db.tx() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (_h(sid),))


def host_allowed(host_header: str | None) -> bool:
    if settings.allow_remote:
        return True
    host = (host_header or "").rsplit(":", 1)[0] if not (host_header or "").startswith("[") else (host_header or "").split("]")[0] + "]"
    return host in LOOPBACK_HOSTS


def is_loopback_bind(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def authorize(path: str, method: str, cookies: dict, headers: dict) -> tuple[bool, int, str]:
    """Return (allowed, status, reason)."""
    if not path.startswith("/api/") or path in PUBLIC_PATHS:
        return True, 200, ""
    authz = headers.get("authorization", "")
    if authz.lower().startswith("bearer ") and check_token(authz[7:].strip()):
        return True, 200, ""  # non-ambient credential: no CSRF needed
    csrf = session_csrf(cookies.get(SESSION_COOKIE))
    if csrf is None:
        return False, 401, "authentication required: open the login URL printed by the server (or send Authorization: Bearer <token>)"
    if method not in ("GET", "HEAD", "OPTIONS"):
        sent = headers.get("x-csrf-token", "")
        if not sent or not hmac.compare_digest(sent.encode(), csrf.encode()):
            return False, 403, "CSRF token missing or invalid"
    return True, 200, ""


def login_url(port: int = 8000) -> str:
    return f"http://{settings.host}:{port}/?token={access_token()}"


def token_file() -> Path:
    return TOKEN_FILE
