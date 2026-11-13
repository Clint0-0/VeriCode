"""Security primitives: workspace boundaries, command allowlist, SSRF guard, secret redaction."""
from __future__ import annotations

import ipaddress
import os
import re
try:
    import resource
except ImportError:
    resource = None
import shutil
import socket
import subprocess
import time
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
    if not path or "\x00" in path or len(path) > 1000:
        raise SecurityError("invalid workspace path")
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
    if resource is not None:
        resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
        # no RLIMIT_AS: V8/WebAssembly reserve large virtual ranges; real memory caps come from the docker backend
        resource.setrlimit(resource.RLIMIT_FSIZE, (200 * 1024**2, 200 * 1024**2))
    if hasattr(os, "setsid"):
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


SANDBOX_IMAGE = "vericode-sandbox:base"
_DOCKER_OK: bool | None = None


def docker_available() -> bool:
    """Docker CLI present and daemon reachable (cached)."""
    global _DOCKER_OK
    if _DOCKER_OK is None:
        exe = shutil.which("docker")
        ok = False
        if exe:
            try:
                ok = subprocess.run([exe, "info", "--format", "{{.ServerVersion}}"], capture_output=True, timeout=10).returncode == 0
            except Exception:
                ok = False
        _DOCKER_OK = ok
    return _DOCKER_OK


def ensure_sandbox_image() -> None:
    """Create a tiny local base image (no registry pull): empty usr-merged rootfs; host /usr is mounted read-only."""
    if subprocess.run(["docker", "image", "inspect", SANDBOX_IMAGE], capture_output=True).returncode == 0:
        return
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for d in ("work", "tmp", "proc", "dev", "etc", "usr", "home"):
            ti = tarfile.TarInfo(d)
            ti.type, ti.mode = tarfile.DIRTYPE, 0o755 if d != "tmp" else 0o1777
            tar.addfile(ti)
        for link, target in (("bin", "usr/bin"), ("lib", "usr/lib"), ("lib64", "usr/lib64"), ("sbin", "usr/sbin")):
            ti = tarfile.TarInfo(link)
            ti.type, ti.linkname = tarfile.SYMTYPE, target
            tar.addfile(ti)
        data = b"nobody:x:65534:65534:nobody:/tmp:/usr/sbin/nologin\n"
        ti = tarfile.TarInfo("etc/passwd")
        ti.size = len(data)
        tar.addfile(ti, io.BytesIO(data))
    p = subprocess.run(["docker", "import", "-", SANDBOX_IMAGE], input=buf.getvalue(), capture_output=True, timeout=60)
    if p.returncode != 0:
        raise SecurityError(f"could not create sandbox image: {p.stderr.decode()[:300]}")


def sandbox_backend() -> str:
    """Resolve the configured backend. An explicit 'docker' request never silently downgrades."""
    want = settings.sandbox_backend
    if want == "process":
        return "process"
    if docker_available():
        try:
            ensure_sandbox_image()
            return "docker"
        except SecurityError:
            if want == "docker":
                raise
            return "process"
    if want == "docker":
        raise SecurityError("sandbox_backend=docker but the Docker daemon is not reachable")
    return "process"


def run_command(argv: list[str], cwd: Path, timeout: int | None = None, backend: str | None = None,
                ro_mounts: dict[str, Path] | None = None) -> CommandResult:
    """Run an allowlisted command (no shell) in the selected sandbox.

    docker : container with --network none, read-only rootfs, host /usr read-only, only the workspace copy
             writable (/work), dependency dirs read-only, non-root uid 65534, all capabilities dropped,
             no-new-privileges, memory/CPU/pids limits, tmpfs /tmp, timeout + forced kill.
    process: scrubbed env, rlimits, new session, timeout, and no network via `unshare -rn` when available.
    """
    _check_allowed(argv)
    timeout = timeout or settings.command_timeout
    backend = backend or sandbox_backend()
    if backend == "docker":
        return _run_docker(argv, cwd, timeout, ro_mounts or {})
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(cwd),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CI": "1",
    }
    venv = cwd / ".venv" / "bin"
    if not venv.is_dir() and (cwd / ".venv" / "Scripts").is_dir():
        venv = cwd / ".venv" / "Scripts"
    if venv.is_dir():
        env["PATH"] = f"{venv}{os.pathsep}{env['PATH']}"
        env["VIRTUAL_ENV"] = str(venv.parent)
        if Path(argv[0]).name in ("python", "pytest"):
            exe = venv / Path(argv[0]).name
            if not exe.exists() and (venv / f"{Path(argv[0]).name}.exe").exists():
                exe = venv / f"{Path(argv[0]).name}.exe"
            argv = [str(exe)] + argv[1:]
    full = argv
    isolation = "process: rlimits+scrubbed-env+timeout"
    if network_isolation_available():
        full = [shutil.which("unshare") or "unshare", "-rn"] + argv
        isolation += "+no-network(unshare -rn)"
    else:
        isolation += " (network NOT restricted)"
    try:
        p = subprocess.run(full, cwd=str(cwd), env=env, capture_output=True, text=True,
                           timeout=timeout, preexec_fn=_limits if os.name != "nt" else None)
        return CommandResult(argv, p.returncode, redact(p.stdout[-20000:]), redact(p.stderr[-20000:]), False, isolation)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return CommandResult(argv, -1, redact(out[-20000:]), f"timed out after {timeout}s", True, isolation)


def _prepare_writable(cwd: Path, skip: set[str] = frozenset()) -> None:
    """Let uid 65534 write into the disposable workspace copy (and nothing else). Mount points of read-only
    dependency dirs are skipped; entries we don't own (e.g. created by a previous container) are left as-is."""
    for root, dirs, files in os.walk(cwd):
        if Path(root) == cwd:
            dirs[:] = [d for d in dirs if d not in skip]
        for d in dirs:
            p = Path(root) / d
            if not p.is_symlink():
                try:
                    p.chmod(0o777)
                except PermissionError:
                    pass
        for f in files:
            p = Path(root) / f
            if not p.is_symlink():
                try:
                    p.chmod(p.stat().st_mode | 0o666)
                except PermissionError:
                    pass
    cwd.chmod(0o777)


def self_contained_image() -> str | None:
    """A locally available self-contained sandbox image (VERICODE_SANDBOX_IMAGE, built from docker/sandbox.Dockerfile).
    When present, the host /usr is NOT mounted (portable to Docker Desktop on macOS/Windows)."""
    img = settings.sandbox_image
    if not img:
        return None
    try:
        ok = subprocess.run(["docker", "image", "inspect", img], capture_output=True, timeout=10).returncode == 0
    except Exception:
        ok = False
    return img if ok else None


def docker_command(argv: list[str], cwd: Path, ro_mounts: dict[str, Path], name: str,
                   image: str | None = None) -> tuple[list[str], list[str], str]:
    """Build the `docker run` command. Returns (docker_args, inner_argv, isolation_label)."""
    cmd = ["docker", "run", "--rm", "--name", name, "--network", "none", "--ipc", "private",
           "--memory", settings.sandbox_memory, "--memory-swap", settings.sandbox_memory, "--cpus", settings.sandbox_cpus,
           "--pids-limit", "256", "--ulimit", "nofile=1024:1024", "--read-only", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges", "--user", "65534:65534", "--tmpfs", "/tmp:size=128m,mode=1777"]
    if not image:
        cmd += ["-v", "/usr:/usr:ro"]  # host-toolchain mode: empty local base image + host /usr read-only
    cmd += ["-v", f"{cwd}:/work:rw"]
    for rel, host in ro_mounts.items():
        if host.exists():
            cmd += ["-v", f"{host.resolve()}:/work/{rel}:ro"]
            if rel == "node_modules":  # tools write caches under node_modules/.vite etc: give them a tmpfs
                for cache in (".vite", ".cache"):
                    try:
                        (host / cache).mkdir(exist_ok=True)
                        cmd += ["--tmpfs", f"/work/node_modules/{cache}:size=64m,mode=1777"]
                    except OSError:
                        pass
    extra_path = ""
    env = ["-e", "HOME=/tmp", "-e", "CI=1", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "LANG=C.UTF-8"]
    inner = list(argv)
    if image:
        # self-contained image: use the image's interpreter; the project's installed packages come from the
        # read-only mounted venv's site-packages (same Python minor version required, see docs/SECURITY.md)
        site = next((p for p in sorted((ro_mounts.get(".venv") or Path("/nonexistent")).glob("lib/python*/site-packages"))), None)
        if site is not None:
            env += ["-e", f"PYTHONPATH=/work/.venv/{site.relative_to(ro_mounts['.venv'])}"]
        if Path(inner[0]).name in ("python", "pytest"):
            inner = ["python3"] + (["-m", "pytest"] + inner[1:] if Path(inner[0]).name == "pytest" else inner[1:])
        env += ["-e", "PATH=/work/node_modules/.bin:/usr/local/bin:/usr/bin:/bin"]
        label = f"docker(self-contained image {image})"
    else:
        venv = ro_mounts.get(".venv")
        cfg = venv / "pyvenv.cfg" if venv else None
        if cfg and cfg.is_file():  # venv interpreter outside /usr (pyenv, setup-python, conda): mount its prefix read-only
            home = next((l.split("=", 1)[1].strip() for l in cfg.read_text().splitlines() if l.strip().startswith("home")), "")
            if home:
                prefix = Path(home).resolve().parent
                if not str(prefix).startswith("/usr") and prefix != Path("/") and prefix.is_dir():
                    cmd += ["-v", f"{prefix}:{prefix}:ro"]
        node = shutil.which("node")
        if node:
            node_root = Path(node).resolve().parents[1]
            if not str(node_root).startswith("/usr"):
                cmd += ["-v", f"{node_root}:{node_root}:ro"]  # node toolchain outside /usr (e.g. /opt/node22)
                extra_path = f"{node_root}/bin:"
        env += ["-e", f"PATH=/work/.venv/bin:/work/node_modules/.bin:{extra_path}/usr/local/bin:/usr/bin:/bin"]
        if Path(inner[0]).name in ("python", "pytest") and ".venv" in ro_mounts:
            inner[0] = f"/work/.venv/bin/{Path(inner[0]).name}"
        label = "docker(host /usr read-only)"
    cmd += ["-w", "/work"] + env + [image or SANDBOX_IMAGE]
    isolation = (f"docker: --network none, read-only rootfs, uid 65534, cap-drop ALL, memory {settings.sandbox_memory}, "
                 f"cpus {settings.sandbox_cpus}, pids 256, only workspace copy writable; {label}")
    return cmd, inner, isolation


def _remove_container(name: str, wait_s: float = 15.0) -> bool:
    """Kill and remove a container, then wait until it is really gone: with `--rm`, Docker's own removal can still
    be in progress (and `rm -f` can fail with 'removal already in progress') right after the kill."""
    subprocess.run(["docker", "kill", name], capture_output=True, timeout=30)
    deadline = time.time() + wait_s
    while True:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30)
        left = subprocess.run(["docker", "ps", "-aq", "--filter", f"name=^{name}$"], capture_output=True, text=True, timeout=30).stdout.strip()
        if not left:
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.5)


def _run_docker(argv: list[str], cwd: Path, timeout: int, ro_mounts: dict[str, Path]) -> CommandResult:
    import uuid
    name = f"vc-{uuid.uuid4().hex[:10]}"
    for rel, host in ro_mounts.items():  # pre-create mount points as the current user (dockerd would create them as root)
        mp = cwd / rel
        if host.exists() and not mp.exists() and not mp.is_symlink():
            mp.mkdir(parents=True, exist_ok=True)
    _prepare_writable(cwd, skip=set(ro_mounts))
    image = self_contained_image()
    if not image:
        ensure_sandbox_image()  # host-toolchain base image is created locally on first use (no registry pull)
    cmd, inner, isolation = docker_command(argv, cwd, ro_mounts, name, image)
    try:
        p = subprocess.run(cmd + inner, capture_output=True, text=True, timeout=timeout)
        return CommandResult(argv, p.returncode, redact(p.stdout[-20000:]), redact(p.stderr[-20000:]), False, isolation)
    except subprocess.TimeoutExpired as e:
        _remove_container(name)
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return CommandResult(argv, -1, redact(out[-20000:]), f"timed out after {timeout}s (container killed)", True, isolation)


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
