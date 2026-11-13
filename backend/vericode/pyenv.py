"""Python environment discovery for a workspace (Windows, Linux, macOS).

Only environments that belong to the workspace, or that the user configured for it, are considered; VeriCode's own
interpreter and unrelated global installs are never used. Candidates, in priority order:

1. configured  - interpreter the user chose for this workspace (Pre-Flight page), stored in the settings table
2. in-project  - .venv / venv / env containing pyvenv.cfg, conda-meta or a site-packages dir
                 (also what uv, Poetry with in-project venvs and PIPENV_VENV_IN_PROJECT create)
3. VIRTUAL_ENV - only when it points inside the workspace
4. Poetry      - {cache}/virtualenvs/<name>-<hash>-py*, hash derived from the workspace path (Poetry's own scheme)
5. Pipenv      - $WORKON_HOME or ~/.local/share/virtualenvs/<dir>-<hash> (Pipenv's own scheme)
6. Conda       - environment.yml `name:` under the conda envs directories

Each candidate is validated: the interpreter is launched in isolated mode with a timeout and reports its version and
site-packages. Statuses: AVAILABLE, UNAVAILABLE (nothing found), AMBIGUOUS (several valid; the highest-priority one is
used and the others listed), CONFIGURATION_ERROR (found, but the interpreter is missing or cannot run).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .security import child_env

IN_PROJECT = (".venv", "venv", "env")
_PROBE = ("import json, sys, sysconfig; "
          "print(json.dumps({'version': sys.version.split()[0], 'prefix': sys.prefix, 'purelib': sysconfig.get_paths()['purelib']}))")
_PROBE_CACHE: dict[tuple[str, int], dict] = {}


@dataclass
class PythonEnv:
    status: str = "UNAVAILABLE"  # AVAILABLE | UNAVAILABLE | AMBIGUOUS | CONFIGURATION_ERROR
    interpreter: str | None = None
    site_packages: str | None = None
    source: str | None = None
    version: str | None = None
    detail: str = ""
    candidates: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def interpreter_in(env_dir: Path) -> Path | None:
    for cand in (env_dir / "Scripts" / "python.exe", env_dir / "python.exe", env_dir / "bin" / "python", env_dir / "bin" / "python3"):
        if cand.is_file():
            return cand
    return None


def static_site_packages(env_dir: Path) -> Path | None:
    for sp in sorted(env_dir.glob("lib/python*/site-packages")):
        return sp
    sp = env_dir / "Lib" / "site-packages"
    return sp if sp.is_dir() else None


def _looks_like_env(d: Path) -> bool:
    return d.is_dir() and ((d / "pyvenv.cfg").is_file() or (d / "conda-meta").is_dir() or static_site_packages(d) is not None)


def _project_name(root: Path) -> str:
    try:
        import tomllib
        data = tomllib.loads((root / "pyproject.toml").read_text())
        return data.get("tool", {}).get("poetry", {}).get("name") or data.get("project", {}).get("name") or root.name
    except (OSError, ValueError):
        return root.name


def poetry_env_prefix(root: Path) -> str:
    """Poetry's env name prefix: <sanitized name>-<first 8 chars of urlsafe-b64(sha256(path))>."""
    name = re.sub(r'[ $`!*@"\\\r\n\t]', "_", _project_name(root).lower())[:42]
    h = base64.urlsafe_b64encode(hashlib.sha256(os.path.normcase(os.path.realpath(root)).encode()).digest()).decode()[:8]
    return f"{name}-{h}"


def pipenv_env_name(root: Path) -> str:
    """Pipenv's env dir name: <sanitized dir name>-<first 8 chars of urlsafe-b64(sha256(path))>."""
    name = re.sub(r'[ &$`!*@"()\[\]\\\r\n\t]', "_", root.name)[:42]
    h = base64.urlsafe_b64encode(hashlib.sha256(str(root).encode()).digest()[:6]).decode()
    return f"{name}-{h}"


def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or Path.home())


def _poetry_dirs() -> list[Path]:
    if os.environ.get("POETRY_VIRTUALENVS_PATH"):
        return [Path(os.environ["POETRY_VIRTUALENVS_PATH"])]
    if os.environ.get("POETRY_CACHE_DIR"):
        return [Path(os.environ["POETRY_CACHE_DIR"]) / "virtualenvs"]
    h = _home()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or h / "AppData" / "Local")
        return [base / "pypoetry" / "Cache" / "virtualenvs"]
    if sys.platform == "darwin":
        return [h / "Library" / "Caches" / "pypoetry" / "virtualenvs"]
    return [Path(os.environ.get("XDG_CACHE_HOME") or h / ".cache") / "pypoetry" / "virtualenvs"]


def _pipenv_dirs() -> list[Path]:
    if os.environ.get("WORKON_HOME"):
        return [Path(os.environ["WORKON_HOME"])]
    h = _home()
    return [h / ".virtualenvs"] if os.name == "nt" else [Path(os.environ.get("XDG_DATA_HOME") or h / ".local" / "share") / "virtualenvs"]


def _conda_dirs() -> list[Path]:
    out = [Path(p) for p in os.environ.get("CONDA_ENVS_PATH", "").split(os.pathsep) if p]
    if os.environ.get("CONDA_PREFIX"):
        cp = Path(os.environ["CONDA_PREFIX"])
        out.append((cp.parent if cp.parent.name == "envs" else cp / "envs"))
    h = _home()
    out += [h / d / "envs" for d in (".conda", "miniconda3", "anaconda3", "miniforge3", "mambaforge")]
    return out


def _conda_env_name(root: Path) -> str | None:
    for fn in ("environment.yml", "environment.yaml"):
        try:
            m = re.search(r"^name:\s*['\"]?([\w.\-]+)", (root / fn).read_text(), re.M)
        except OSError:
            continue
        if m:
            return m.group(1)
    return None


def find_candidates(root: Path, configured: str | None = None) -> list[dict]:
    """Static discovery (no process launched): environment dirs that belong to, or were configured for, the workspace."""
    root = root.resolve()
    out: list[dict] = []

    def add(source: str, env_dir: Path | None, interp: Path | None = None) -> None:
        interp = interp or (interpreter_in(env_dir) if env_dir else None)
        key = str((env_dir or interp).resolve()) if (env_dir or interp) else None
        if key and any(c["key"] == key for c in out):
            return
        out.append({"source": source, "key": key, "env_dir": str(env_dir) if env_dir else None,
                    "interpreter": str(interp) if interp else None,
                    "site_packages": str(sp) if env_dir and (sp := static_site_packages(env_dir)) else None})

    if configured:
        p = Path(configured)
        env_dir = p.parent.parent if p.parent.name in ("bin", "Scripts") else p.parent
        add("configured", env_dir if _looks_like_env(env_dir) else None, p)
    for name in IN_PROJECT:
        d = root / name
        if _looks_like_env(d):
            add(f"in-project ({name})", d)
    ve = os.environ.get("VIRTUAL_ENV")
    if ve:
        vd = Path(ve).resolve()
        if vd == root or root in vd.parents:
            add("VIRTUAL_ENV", vd)
    if (root / "poetry.lock").is_file() or "[tool.poetry]" in _read(root / "pyproject.toml"):
        prefix = poetry_env_prefix(root)
        for base in _poetry_dirs():
            for d in sorted(base.glob(f"{prefix}-py*")) if base.is_dir() else []:
                if _looks_like_env(d):
                    add("poetry", d)
    if (root / "Pipfile").is_file():
        for base in _pipenv_dirs():
            d = base / pipenv_env_name(root)
            if _looks_like_env(d):
                add("pipenv", d)
    cname = _conda_env_name(root)
    if cname:
        for base in _conda_dirs():
            d = base / cname
            if (d / "conda-meta").is_dir():
                add(f"conda ({cname})", d)
    return out


def _read(p: Path) -> str:
    try:
        return p.read_text()
    except OSError:
        return ""


def probe_interpreter(interp: str, timeout: int = 10) -> dict:
    """Launch the interpreter isolated (-I, scrubbed env, timeout); returns version/prefix/purelib or an error."""
    try:
        st = os.stat(interp)
    except OSError as e:
        return {"ok": False, "error": f"interpreter not found: {e.strerror or e}"}
    key = (interp, st.st_mtime_ns)
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    try:
        from .security import _limits, network_isolation_available
        # the interpreter belongs to the workspace (possibly an untrusted clone): no network where `unshare -rn`
        # works, rlimits, new session, scrubbed env, timeout - same containment as runtime introspection
        prefix = ["unshare", "-rn"] if network_isolation_available() else []
        p = subprocess.run(prefix + [interp, "-I", "-c", _PROBE], capture_output=True, text=True, timeout=timeout, env=child_env(),
                           cwd=os.path.dirname(interp) or None, preexec_fn=_limits if os.name != "nt" else None)
        data = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 and p.stdout.strip() else None
        res = {"ok": True, **data} if data else {"ok": False, "error": f"exit {p.returncode}: {(p.stderr or '').strip()[-300:]}"}
    except subprocess.TimeoutExpired:
        res = {"ok": False, "error": f"interpreter did not answer within {timeout}s"}
    except (OSError, ValueError) as e:
        res = {"ok": False, "error": f"cannot launch interpreter: {type(e).__name__}: {e}"}
    _PROBE_CACHE[key] = res
    return res


def discover(root: Path, configured: str | None = None) -> PythonEnv:
    cands = find_candidates(root, configured)
    if not cands:
        return PythonEnv("UNAVAILABLE", detail="No Python environment found for this workspace (looked for .venv, venv, env, "
                                               "VIRTUAL_ENV inside the workspace, Poetry, Pipenv and Conda environments).")
    valid = []
    for c in cands:
        if c["interpreter"]:
            pr = probe_interpreter(c["interpreter"])
            c["probe"] = pr
            if pr["ok"]:
                c["version"] = pr["version"]
                c["site_packages"] = pr["purelib"] if Path(pr["purelib"]).is_dir() else c["site_packages"]
                valid.append(c)
                continue
            c["error"] = pr["error"]
        elif c["site_packages"]:
            c["note"] = "no interpreter found: installed versions read from package metadata only, runtime checks disabled"
            valid.append(c)
        else:
            c["error"] = "no interpreter and no site-packages"
    public = [{k: v for k, v in c.items() if k not in ("key", "probe")} for c in cands]
    if cands[0]["source"] == "configured" and cands[0] not in valid:
        return PythonEnv("CONFIGURATION_ERROR", interpreter=cands[0]["interpreter"], source="configured",
                         site_packages=cands[0]["site_packages"], candidates=public,
                         detail=f"Configured interpreter is not usable: {cands[0].get('error')}")
    if not valid:
        c = cands[0]
        return PythonEnv("CONFIGURATION_ERROR", interpreter=c["interpreter"], source=c["source"], site_packages=c["site_packages"],
                         candidates=public, detail=f"Environment found ({c['source']}) but its interpreter is not usable: {c.get('error')}")
    best = valid[0]
    status = "AMBIGUOUS" if len(valid) > 1 else "AVAILABLE"
    detail = best.get("note", "")
    if status == "AMBIGUOUS":
        detail = (f"{len(valid)} environments found; using {best['source']}. Choose one explicitly on the Pre-Flight page "
                  "if that is not the project's environment. " + detail).strip()
    return PythonEnv(status, interpreter=best["interpreter"], site_packages=best["site_packages"], source=best["source"],
                     version=best.get("version"), detail=detail, candidates=public)


# --- per-workspace interpreter choice (explicit user action) -------------------------------------------------
def configured_interpreter(root: Path) -> str | None:
    from . import db
    r = db.row("SELECT value FROM settings WHERE key=?", (f"pyinterp:{root.resolve()}",))
    return db.loads(r["value"]) if r else None


def set_configured_interpreter(root: Path, interpreter: str | None) -> dict:
    """Validate and store (or clear) the interpreter for a workspace. Must be an absolute path to a runnable Python."""
    from . import db
    key = f"pyinterp:{root.resolve()}"
    if not interpreter:
        with db.tx() as c:
            c.execute("DELETE FROM settings WHERE key=?", (key,))
        return {"cleared": True}
    p = Path(interpreter)
    if not p.is_absolute():
        raise ValueError("interpreter must be an absolute path")
    if not p.is_file() or not re.match(r"python(\d+(\.\d+)?)?(\.exe)?$", p.name, re.I):
        raise ValueError("interpreter must be an existing python executable (python, python3, python.exe)")
    pr = probe_interpreter(str(p))
    if not pr["ok"]:
        raise ValueError(f"interpreter cannot run: {pr['error']}")
    with db.tx() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES(?,?,strftime('%s','now'))", (key, db.dumps(str(p))))
    return {"interpreter": str(p), "version": pr["version"], "site_packages": pr["purelib"]}
