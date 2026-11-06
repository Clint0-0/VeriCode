"""Security primitives: workspace boundaries, command allowlist, SSRF guard, secret redaction."""
from __future__ import annotations

import ipaddress
import os
import re
import resource
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .config import settings

MAX_FILE_BYTES = 400_000
MAX_REQUEST_CHARS = 60_000


class SecurityError(Exception):
    pass


def workspace_root() -> Path:
    return Path(settings.workspaces_root).resolve()


def resolve_workspace(path: str) -> Path:
    """A project path must live inside the configured workspaces root."""
    p = Path(path)
    if not p.is_absolute():
        p = workspace_root() / p
    p = p.resolve()
    root = workspace_root()
    if p != root and root not in p.parents:
        raise SecurityError(f"path outside workspace root: {path}")
    if not p.is_dir():
        raise SecurityError(f"workspace does not exist: {path}")
    return p


def safe_join(root: Path, rel: str) -> Path:
    """Join a relative path to root, rejecting traversal, absolute paths and symlink escapes."""
    if not rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        raise SecurityError(f"invalid relative path: {rel!r}")
    if "\x00" in rel:
        raise SecurityError("NUL in path")
    target = (root / rel).resolve()
    root = root.resolve()
    if root not in target.parents:
        raise SecurityError(f"path escapes workspace: {rel}")
    protected = {".git", ".venv", "node_modules", ".env"}
    if any(part in protected for part in Path(rel).parts):
        raise SecurityError(f"protected path: {rel}")
    return target


# --- secrets -----------------------------------------------------------------
_SECRET_PATTERNS = [
    re.compile(r"tvly-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?[^\s'\"]{8,}"),
]


def redact(text: str) -> str:
    if not text:
        return text
    for key in (settings.tavily_api_key, settings.anthropic_api_key, settings.openai_api_key):
        if key and len(key) > 6:
            text = text.replace(key, "[REDACTED]")
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


SENSITIVE_FILE_RE = re.compile(r"(^|/)(\.env(\..*)?|.*\.pem|.*\.key|id_rsa.*|credentials.*|secrets?\..*)$", re.I)


def is_sensitive_file(rel: str) -> bool:
    return bool(SENSITIVE_FILE_RE.search(rel)) and not rel.endswith(".env.example")


# --- command execution -------------------------------------------------------
ALLOWED_COMMANDS: dict[str, list[list[str]]] = {
    # first token -> allowed argument prefixes (exact executable resolution done below)
    "pytest": [[]],
    "python": [["-m", "pytest"], ["-m", "py_compile"], ["-m", "mypy"], ["-m", "ruff"]],
    "npm": [["test"], ["run", "test"], ["run", "lint"], ["run", "typecheck"]],
    "npx": [["tsc", "--noEmit"], ["vitest", "run"]],
}


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    isolation: str


def _check_allowed(argv: list[str]) -> None:
    if not argv:
        raise SecurityError("empty command")
    exe = Path(argv[0]).name
    base = "python" if exe.startswith("python") else exe
    if base not in ALLOWED_COMMANDS:
        raise SecurityError(f"command not allowlisted: {exe}")
    rest = argv[1:]
    if not any(rest[: len(p)] == p for p in ALLOWED_COMMANDS[base]):
        raise SecurityError(f"arguments not allowlisted for {exe}: {rest[:3]}")
    for a in argv:
        if any(ch in a for ch in [";", "|", "&", "`", "$(", ">", "<"]):
            raise SecurityError("shell metacharacters rejected")


def _limits() -> None:  # pragma: no cover - runs in child
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
    resource.setrlimit(resource.RLIMIT_AS, (4 * 1024**3, 4 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (200 * 1024**2, 200 * 1024**2))
    os.setsid()


_NET_ISOLATION: bool | None = None


def network_isolation_available() -> bool:
    """True if `unshare -rn` works here (user+net namespace => no network for the child)."""
    global _NET_ISOLATION
    if _NET_ISOLATION is None:
        exe = shutil.which("unshare")
        ok = False
        if exe:
            try:
                ok = subprocess.run([exe, "-rn", "true"], capture_output=True, timeout=5).returncode == 0
            except Exception:
                ok = False
        _NET_ISOLATION = ok
    return _NET_ISOLATION


def run_command(argv: list[str], cwd: Path, timeout: int | None = None) -> CommandResult:
    """Run an allowlisted command without a shell, with scrubbed env, rlimits, timeout and
    (when the kernel allows) no network. This is process-level isolation, not a container."""
    _check_allowed(argv)
    timeout = timeout or settings.command_timeout
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(cwd),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CI": "1",
    }
    venv = cwd / ".venv" / "bin"
    if venv.is_dir():
        env["PATH"] = f"{venv}:{env['PATH']}"
        env["VIRTUAL_ENV"] = str(venv.parent)
        if Path(argv[0]).name in ("python", "pytest"):
            argv = [str(venv / Path(argv[0]).name)] + argv[1:]
    full = argv
    isolation = "rlimits+scrubbed-env"
    if network_isolation_available():
        full = [shutil.which("unshare") or "unshare", "-rn"] + argv
        isolation += "+no-network(unshare)"
    try:
        p = subprocess.run(full, cwd=str(cwd), env=env, capture_output=True, text=True,
                           timeout=timeout, preexec_fn=_limits)
        return CommandResult(argv, p.returncode, redact(p.stdout[-20000:]), redact(p.stderr[-20000:]), False, isolation)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return CommandResult(argv, -1, redact(out[-20000:]), f"timed out after {timeout}s", True, isolation)


# --- SSRF guard --------------------------------------------------------------
def check_public_url(url: str) -> str:
    """Allow only http(s) URLs whose host resolves exclusively to public IPs."""
    u = urlparse(url)
    if u.scheme not in ("http", "https"):
        raise SecurityError("only http/https URLs allowed")
    if not u.hostname:
        raise SecurityError("URL has no host")
    if u.username or u.password:
        raise SecurityError("credentials in URL not allowed")
    host = u.hostname
    try:
        infos = socket.getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80))
    except socket.gaierror as e:
        raise SecurityError(f"cannot resolve host {host}: {e}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            raise SecurityError(f"host {host} resolves to non-public address")
    return url
