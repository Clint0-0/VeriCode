"""Module I - Version-aware project memory. Only findings backed by verified evidence become rules."""
from __future__ import annotations

import time
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from . import db

DEFAULT_TTL = 30 * 86400
VERIFIED_STATUSES = {"DEPRECATED", "INCOMPATIBLE", "NOT_FOUND"}


def _matches(version: str | None, spec: str) -> bool:
    if not version:
        return False
    try:
        return Version(version) in SpecifierSet(spec)
    except (InvalidSpecifier, InvalidVersion):
        return version == spec


def find_rule(package: str, version: str | None, api_name: str) -> dict | None:
    now = time.time()
    for r in db.rows("SELECT * FROM rules WHERE active=1 AND lower(package)=lower(?) AND api LIKE ?", (package, f"%{api_name}")):
        if r["expires_at"] and r["expires_at"] < now:
            continue  # needs revalidation
        if _matches(version, r["version_spec"]):
            return r
    return None


def save_from_finding(f: dict) -> dict | None:
    """Persist a rule only when the finding was verified against installed source (or official live docs)
    and carries a concrete correction. Unverified LLM suggestions are never stored."""
    if f["status"] not in VERIFIED_STATUSES or not f.get("suggested_correction") or f.get("verification_confidence") != "high":
        return None
    local = f.get("local") or {}
    evidence = local.get("location") or (local.get("migration_hint") or "")[:200]
    if not evidence:
        return None
    spec = f"=={f['installed_version']}"
    existing = db.row("SELECT id FROM rules WHERE package=? AND api=? AND version_spec=?", (f["package"], f["planned_api"], spec))
    now = time.time()
    with db.tx() as c:
        if existing:
            c.execute("UPDATE rules SET last_verified=?, expires_at=?, correction=?, active=1 WHERE id=?",
                      (now, now + DEFAULT_TTL, f["suggested_correction"], existing["id"]))
            rid = existing["id"]
        else:
            rid = db.new_id("rule_")
            c.execute("INSERT INTO rules VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (rid, f["package"], spec, f["planned_api"], f["explanation"][:500], f["suggested_correction"][:500],
                       f"installed source: {evidence}", now, now, now + DEFAULT_TTL, 1))
    return db.row("SELECT * FROM rules WHERE id=?", (rid,))


def invalidate_for_versions(installed: dict[str, str]) -> int:
    """Deactivate rules whose version spec no longer matches the installed version."""
    n = 0
    for r in db.rows("SELECT * FROM rules WHERE active=1"):
        v = installed.get(r["package"].lower())
        if v is not None and not _matches(v, r["version_spec"]):
            with db.tx() as c:
                c.execute("UPDATE rules SET active=0 WHERE id=?", (r["id"],))
            n += 1
    return n


def list_rules() -> list[dict]:
    return db.rows("SELECT * FROM rules ORDER BY created_at DESC")


def update_rule(rid: str, data: dict) -> dict | None:
    allowed = {k: v for k, v in data.items() if k in ("correction", "issue", "active", "version_spec")}
    if not allowed:
        return db.row("SELECT * FROM rules WHERE id=?", (rid,))
    with db.tx() as c:
        for k, v in allowed.items():
            c.execute(f"UPDATE rules SET {k}=? WHERE id=?", (v, rid))
    return db.row("SELECT * FROM rules WHERE id=?", (rid,))


def delete_rule(rid: str) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM rules WHERE id=?", (rid,))


START, END = "<!-- vericode:rules:start -->", "<!-- vericode:rules:end -->"


def export_rules(project_root: Path) -> Path:
    """Write verified rules into .agent-rules.md inside a managed block; user content is preserved."""
    target = project_root / ".agent-rules.md"
    lines = [START, "## VeriCode verified compatibility rules (auto-generated; edit outside this block)"]
    for r in db.rows("SELECT * FROM rules WHERE active=1 ORDER BY package, api"):
        lines.append(f"- **{r['package']} {r['version_spec']}** `{r['api']}`: {r['correction']}  \n  _evidence: {r['evidence_source']}_")
    lines.append(END)
    block = "\n".join(lines)
    existing = target.read_text() if target.exists() else ""
    if START in existing and END in existing:
        pre, rest = existing.split(START, 1)
        post = rest.split(END, 1)[1]
        new = pre + block + post
    else:
        new = (existing.rstrip() + "\n\n" if existing.strip() else "") + block + "\n"
    target.write_text(new)
    return target
