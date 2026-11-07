# Windows setup (WSL2 — recommended)

VeriCode's scripts, test runner and Docker sandbox are built for Linux. On Windows, run VeriCode **inside WSL2
(Ubuntu)**.

| Mode | Status |
|---|---|
| **WSL2 Ubuntu + Docker Desktop (WSL integration)** | Supported. Same commands as on Linux |
| Native Windows (PowerShell/cmd, no WSL) | **Not supported and not tested.** The bash scripts, the `unshare`/rlimit process sandbox and the host-toolchain Docker mode all assume Linux |

## 1. Enable WSL2 and install Ubuntu
In **PowerShell as Administrator**:
```powershell
wsl --install -d Ubuntu-24.04
wsl --set-default-version 2
```
Reboot if asked, open "Ubuntu" from the Start menu and create your Linux user. Check that it is WSL **2**:
```powershell
wsl -l -v      # VERSION column must be 2
```

## 2. Docker Desktop with WSL integration
1. Install Docker Desktop for Windows.
2. Settings → General: enable **Use the WSL 2 based engine**.
3. Settings → Resources → WSL integration: enable your Ubuntu distro.
4. In Ubuntu: `docker info` should print a server version. Without Docker, VeriCode uses its process sandbox
   (labelled in the UI).

## 3. Tools inside Ubuntu
```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip build-essential curl util-linux
# Node 22 via nvm (or NodeSource)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 22
python3 --version   # 3.11+ (3.13 tested)
node --version      # 20+ (22 tested)
```

## 4. Clone **inside the Linux filesystem**
Clone into your WSL home (`~/...`), **not** `/mnt/c/...`. On `/mnt/c`, file watching and installs are much slower,
permission bits are lost, and Docker bind mounts of `/usr` and `.venv` behave differently.
```bash
cd ~
git config --global core.autocrlf input     # keep LF line endings
git clone https://github.com/Clint0-0/VeriCode.git
cd VeriCode
git checkout feat/vericode-offline-hardening   # or the default branch once merged
```
The repo's `.gitattributes` forces LF for `*.sh` and `*.py`. If you already cloned with CRLF on the Windows side and
see `/usr/bin/env: 'bash\r': No such file or directory`, re-clone inside WSL or run:
`git rm --cached -r . && git reset --hard`.

## 5. Install and configure
```bash
scripts/setup.sh          # venvs, demo projects, TypeScript checker, frontend build, creates .env (never overwrites)
nano .env                 # optional now: TAVILY_API_KEY, ANTHROPIC_API_KEY / OPENAI_API_KEY, VERICODE_CODER_MODEL
```
Everything in the offline demo suite works without keys (see `docs/OFFLINE_DEMO.md`).

## 6. Run
```bash
scripts/run.sh            # prints:  VeriCode login URL: http://127.0.0.1:8000/?token=...
```
Open that URL in your **Windows** browser. WSL2 forwards `localhost`/`127.0.0.1` to Windows automatically. The token is
also stored in `.vericode_token`.

Frontend hot reload (optional, second Ubuntu terminal):
```bash
cd frontend && npm run dev      # http://localhost:5173, proxies /api to :8000
```

## 7. Tests and demos
```bash
scripts/test.sh                 # backend + frontend
scripts/demo.sh offline         # all key-free demos with OK/UNEXPECTED summary
VERICODE_TEST_SANDBOX=docker .venv/bin/python -m pytest -q backend/tests -k "docker or sandbox"
```

## Troubleshooting
| Symptom | Fix |
|---|---|
| `Address already in use` on 8000/5173 | `PORT=8010 scripts/run.sh`. Find the culprit with `ss -ltnp \| grep 8000`. On Windows, `netstat -ano \| findstr 8000` |
| Browser can't reach `127.0.0.1:8000` | Check `scripts/run.sh` is still running. Run `wsl --shutdown` and reopen Ubuntu. Make sure no VPN is breaking WSL localhost forwarding |
| `Refusing to bind to 0.0.0.0` | Intended. VeriCode binds to loopback unless `VERICODE_ALLOW_REMOTE=1` |
| `permission denied` running `scripts/*.sh` | `chmod +x scripts/*.sh` (common after copying from `/mnt/c`) |
| `bash\r: No such file or directory` | CRLF line endings: see step 4 |
| `Cannot connect to the Docker daemon` | Start Docker Desktop and enable WSL integration for the distro (step 2) |
| Docker tests fail with missing interpreter | The project venv interpreter must be visible to the container. Python under `/usr` or a prefix such as pyenv is handled automatically. Python installed on the Windows side is not |
| `unshare: unshare failed` | Some WSL kernels restrict user namespaces. The process sandbox then reports "network NOT restricted". Use Docker for isolation |
| Very slow `npm ci` / `pip install` | The repo is on `/mnt/c`: move it into `~` |
| Line-ending diffs in `git status` | `git config core.autocrlf input`, then `git add --renormalize .` |
