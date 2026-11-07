"""Docker sandbox: command construction for both modes, dependency-dir restrictions, TypeScript checking in the
container, and cleanup. Container tests are skipped when the Docker daemon is unreachable."""
import shutil
import subprocess
from pathlib import Path

import pytest

from vericode import agent, security
from vericode.config import ROOT, settings

needs_docker = pytest.mark.skipif(not security.docker_available(), reason="Docker daemon not reachable")
TS = ROOT / "demos" / "ts_project"


def _flags(cmd):
    j = " ".join(cmd)
    for f in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges", "--user 65534:65534",
              "--pids-limit 256", f"--memory {settings.sandbox_memory}", f"--memory-swap {settings.sandbox_memory}",
              f"--cpus {settings.sandbox_cpus}", "--rm", "--ipc private"):
        assert f in j, f


def test_host_toolchain_mode_command(tmp_path, sample_project):
    cmd, inner, iso = security.docker_command(["python", "-m", "pytest"], tmp_path, {".venv": sample_project / ".venv"}, "vc-x")
    _flags(cmd)
    assert "/usr:/usr:ro" in cmd and f"{(sample_project / '.venv').resolve()}:/work/.venv:ro" in cmd
    assert inner[0] == "/work/.venv/bin/python" and "host /usr read-only" in iso
    assert not any("API_KEY" in c for c in cmd)


def test_self_contained_image_mode_command(tmp_path, sample_project):
    cmd, inner, iso = security.docker_command(["python", "-m", "pytest", "-q"], tmp_path, {".venv": sample_project / ".venv"},
                                              "vc-y", image="vericode-sandbox:full")
    _flags(cmd)
    assert "/usr:/usr:ro" not in cmd  # portable: no host toolchain mount
    assert cmd[-1] == "vericode-sandbox:full" and inner == ["python3", "-m", "pytest", "-q"]
    assert any(c.startswith("PYTHONPATH=/work/.venv/lib/python") and c.endswith("site-packages") for c in cmd)
    assert "self-contained image" in iso


def test_missing_self_contained_image_falls_back_to_host_mode(monkeypatch):
    monkeypatch.setattr(settings, "sandbox_image", "vericode-sandbox:definitely-not-built")
    if not security.docker_available():
        pytest.skip("docker not reachable")
    assert security.self_contained_image() is None


@needs_docker
def test_dependency_dirs_are_read_only_in_container(tmp_path, sample_project):
    (tmp_path / "test_ro.py").write_text(
        "import pytest\n"
        "def test_venv_readonly():\n    with pytest.raises(OSError):\n        open('/work/.venv/pwned', 'w')\n"
        "def test_workspace_writable():\n    open('/work/ok.txt', 'w').write('x')\n")
    r = security.run_command(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], tmp_path, backend="docker",
                             ro_mounts={".venv": sample_project / ".venv"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (sample_project / ".venv" / "pwned").exists()


@needs_docker
def test_typescript_check_inside_container(tmp_path):
    if not (TS / "node_modules").is_dir():
        pytest.skip("ts demo not installed")
    sb = agent.make_sandbox(TS, "ts_docker_check", link_heavy=False)
    try:
        ok = security.run_command(["npx", "tsc", "--noEmit"], sb, backend="docker", ro_mounts=agent.heavy_mounts(TS))
        assert ok.returncode == 0, ok.stdout + ok.stderr
        (sb / "src" / "bad.ts").write_text("const n: number = 'not a number'\nexport default n\n")
        bad = security.run_command(["npx", "tsc", "--noEmit"], sb, backend="docker", ro_mounts=agent.heavy_mounts(TS))
        assert bad.returncode != 0 and "TS2322" in bad.stdout + bad.stderr
    finally:
        shutil.rmtree(sb, ignore_errors=True)


@needs_docker
def test_containers_are_cleaned_up(tmp_path, sample_project):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    security.run_command(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], tmp_path, backend="docker",
                         ro_mounts={".venv": sample_project / ".venv"})
    (tmp_path / "test_ok.py").write_text("import time\ndef test_slow():\n    time.sleep(30)\n")
    security.run_command(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"], tmp_path, backend="docker", timeout=4,
                         ro_mounts={".venv": sample_project / ".venv"})
    left = subprocess.run(["docker", "ps", "-a", "--filter", "name=vc-", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.strip()
    assert left == ""


@needs_docker
def test_malicious_commands_never_reach_docker(tmp_path):
    for argv in (["docker", "run", "alpine"], ["python", "-c", "import os; os.system('id')"], ["npm", "exec", "rimraf", "/"]):
        with pytest.raises(security.SecurityError):
            security.run_command(argv, tmp_path, backend="docker")


def test_venv_interpreter_outside_usr_is_mounted(tmp_path):
    prefix = tmp_path / "toolcache" / "Python" / "3.13.1"
    (prefix / "bin").mkdir(parents=True)
    venv = tmp_path / "proj" / ".venv"
    venv.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text(f"home = {prefix / 'bin'}\ninclude-system-site-packages = false\nversion = 3.13.1\n")
    cmd, _, _ = security.docker_command(["python", "-m", "pytest"], tmp_path, {".venv": venv}, "vc-z")
    assert f"{prefix.resolve()}:{prefix.resolve()}:ro" in cmd
