"""SQLite persistence (stdlib sqlite3). Schema is created idempotently by init_db()."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, path TEXT UNIQUE, name TEXT, fingerprint TEXT,
  environment_json TEXT, inspected_at REAL
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, project_path TEXT, prompt TEXT, mode TEXT, status TEXT,
  created_at REAL, finished_at REAL, success INTEGER, provider TEXT,
  preflight_json TEXT, result_json TEXT, events_json TEXT, benchmark_id TEXT
);
CREATE TABLE IF NOT EXISTS token_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, stage TEXT, provider TEXT, model TEXT,
  input_tokens INTEGER, output_tokens INTEGER, estimated INTEGER, cached INTEGER, created_at REAL
);
CREATE TABLE IF NOT EXISTS analyses (
  id TEXT PRIMARY KEY, answer TEXT, question TEXT, evidence_mode TEXT, created_at REAL,
  summary_json TEXT, corrected_json TEXT
);
CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY, analysis_id TEXT, claim_id TEXT, claim TEXT, category TEXT,
  volatility TEXT, requires_verification INTEGER, status TEXT, freshness REAL,
  confidence REAL, explanation TEXT, detail_json TEXT
);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, analysis_id TEXT, claim_id TEXT, title TEXT, url TEXT, domain TEXT,
  source_type TEXT, authority REAL, retrieved_at TEXT, published_date TEXT, excerpt TEXT,
  relevance TEXT, outcome TEXT, origin TEXT
);
CREATE TABLE IF NOT EXISTS rules (
  id TEXT PRIMARY KEY, package TEXT, version_spec TEXT, api TEXT, issue TEXT, correction TEXT,
  evidence_source TEXT, created_at REAL, last_verified REAL, expires_at REAL, active INTEGER
);
CREATE TABLE IF NOT EXISTS cache (
  key TEXT PRIMARY KEY, value TEXT, created_at REAL, expires_at REAL
);
CREATE TABLE IF NOT EXISTS benchmarks (
  id TEXT PRIMARY KEY, created_at REAL, task_prompt TEXT, project_path TEXT, runs INTEGER,
  result_json TEXT
);
"""

# Ordered, append-only migrations. Version 1 == the base SCHEMA above.
MIGRATIONS: list[tuple[int, str]] = [
    (2, "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, updated_at REAL)"),
    (3, "ALTER TABLE tasks ADD COLUMN outcome TEXT"),
    (4, "ALTER TABLE token_usage ADD COLUMN measurement TEXT"),
    (5, "CREATE TABLE IF NOT EXISTS search_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, analysis_id TEXT, "
        "endpoint TEXT, query TEXT, status TEXT, credits REAL, cached INTEGER, created_at REAL)"),
    (6, "ALTER TABLE benchmarks ADD COLUMN measurement TEXT"),
    (7, "CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, csrf TEXT, created_at REAL, expires_at REAL)"),
]


def _migrate(c: sqlite3.Connection) -> None:
    c.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at REAL)")
    cur = c.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0
    if cur == 0:
        c.execute("INSERT INTO schema_version VALUES (1, ?)", (time.time(),))
        cur = 1
    for version, sql in MIGRATIONS:
        if version > cur:
            try:
                c.execute(sql)
            except sqlite3.OperationalError as e:  # column already exists (idempotent re-run)
                if "duplicate column" not in str(e):
                    raise
            c.execute("INSERT INTO schema_version VALUES (?, ?)", (version, time.time()))
    c.commit()


def schema_version() -> int:
    return connect().execute("SELECT MAX(version) FROM schema_version").fetchone()[0]


_lock = threading.RLock()
_conn: sqlite3.Connection | None = None
_conn_path: str | None = None


def connect() -> sqlite3.Connection:
    global _conn, _conn_path
    with _lock:
        if _conn is None or _conn_path != settings.db_path:
            _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.executescript(SCHEMA)
            _migrate(_conn)
            _conn_path = settings.db_path
        return _conn


def init_db() -> None:
    connect()


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    with _lock:
        c = connect()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def dumps(o: Any) -> str:
    return json.dumps(o, default=str)


def loads(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    return json.loads(s)


def rows(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in connect().execute(sql, params).fetchall()]


def row(sql: str, params: tuple = ()) -> dict | None:
    r = rows(sql, params)
    return r[0] if r else None


# --- generic cache ---------------------------------------------------------
def cache_get(key: str) -> Any:
    r = row("SELECT value, expires_at FROM cache WHERE key=?", (key,))
    if not r:
        return None
    if r["expires_at"] and r["expires_at"] < time.time():
        with tx() as c:
            c.execute("DELETE FROM cache WHERE key=?", (key,))
        return None
    return loads(r["value"])


def cache_set(key: str, value: Any, ttl: int | None = None) -> None:
    now = time.time()
    with tx() as c:
        c.execute(
            "INSERT OR REPLACE INTO cache(key,value,created_at,expires_at) VALUES(?,?,?,?)",
            (key, dumps(value), now, now + ttl if ttl else None),
        )
