# Security

| Control | Implementation | Tested by |
|---|---|---|
| Authentication | One-time access token (random per start, or `VERICODE_AUTH_TOKEN`), printed as a login URL and stored in `.vericode_token` (mode 600). `POST /api/auth/login` exchanges it for an **HttpOnly, SameSite=Strict** session cookie (12 h, hashed in SQLite) and a CSRF token. All `/api/*` except health/auth require a session or `Authorization: Bearer <token>` | `test_auth_required_and_csrf_enforced` |
| CSRF | Cookie sessions must send `X-CSRF-Token` on every non-GET request | same |
| Network exposure | Host-header allowlist (loopback only) blocks DNS rebinding. The app and `scripts/run.sh` refuse non-loopback binds unless `VERICODE_ALLOW_REMOTE=1` | `test_dns_rebinding_host_header_blocked`, `test_refuses_remote_bind_without_opt_in` |
| Credentials | Env/.env only, never stored in SQLite, never returned (`*_configured` flags only). PUT `/settings` rejects key fields. `.env` and `.vericode_token` are git-ignored | `test_settings_never_expose_secrets` |
| Secret redaction | `redact()` on every LLM prompt, command output, Tavily error and evidence excerpt | `test_redaction` |
| Workspace boundary | Projects must resolve inside `VERICODE_WORKSPACES`. `safe_join` rejects absolute paths, `..`, NUL, symlink escapes and `.git/.venv/node_modules/.env` | `test_safe_join_rejects_traversal` |
| Overwrite protection | Edits happen in a disposable copy. SEARCH must match exactly once, and an empty SEARCH cannot overwrite. `apply` refuses changed files (SHA-1) and returns a conflict report with the user's diff. Copies content only (keeps permissions), then deletes the sandbox | `test_conflict_report_contains_user_diff`, `test_apply_changes_with_overwrite_protection` |
| Command allowlist | No shell. argv allowlist (`pytest`, `python -m pytest/py_compile/mypy/ruff`, `npm test/run test/run lint/run typecheck`, `npx tsc --noEmit/vitest run`). Metacharacters rejected | `test_command_allowlist` |
| **Docker sandbox: two modes** | (a) *Self-contained image* (`docker/sandbox.Dockerfile`, built once with `scripts/build_sandbox_image.sh`, used automatically when `VERICODE_SANDBOX_IMAGE` exists locally): host `/usr` is **not** mounted. Portable to Docker Desktop on macOS and Windows. The project's site-packages are mounted read-only and run with the image's Python (same minor version required). (b) *Host-toolchain mode* (default, no registry needed): empty local image plus host `/usr` read-only. A venv interpreter or node toolchain outside `/usr` (pyenv, setup-python, `/opt/node`) has its prefix mounted read-only too. Same controls in both modes (row below) | `test_sandbox_portability.py` (command construction for both modes, prefix mounts) |
| **Docker sandbox controls** (default when the daemon is reachable) | Local base image created with `docker import` (no registry pull). `--network none`, `--read-only` rootfs, host `/usr` mounted **read-only**, only the workspace copy (`/work`) writable, dependency dirs read-only, `--user 65534`, `--cap-drop ALL`, `no-new-privileges`, `--memory/--memory-swap`, `--cpus`, `--pids-limit 256`, `--ipc private`, `--ulimit nofile=1024`, `--rm` plus forced `docker rm -f` on timeout, tmpfs `/tmp` and tool caches, scrubbed env, timeout followed by `docker kill` | `test_docker_sandbox_enforces_isolation` (inside the container: network connect fails, uid is 65534, `/etc` and `/usr` are not writable, no `*_API_KEY` in env), `test_docker_timeout_kills_container` |
| Process sandbox (fallback) | Scrubbed env, RLIMIT_CPU/FSIZE, new session, timeout. **No network only when `unshare -rn` works** (reported per run). Otherwise the label reads "network NOT restricted". An explicit `VERICODE_SANDBOX=docker` never downgrades silently | `test_process_sandbox_labels_network`, `test_explicit_docker_request_never_downgrades` |
| Runtime introspection | Used only when static analysis fails: separate `python -I` process, scrubbed env, 10 s timeout | – |
| TypeScript checker | VeriCode's own pinned TypeScript in a node subprocess (scrubbed env, timeout). The user project is never modified | `test_ts_*` |
| SSRF (user URLs) | http(s) only, no URL credentials, every resolved IP public (blocks loopback, private, link-local incl. 169.254.169.254, reserved, multicast). Each redirect re-validated (max 3). **Connected peer address re-checked after connect** (DNS rebinding). 500 KB cap | `test_ssrf_guard`, `test_ssrf_blocked_for_user_urls` |
| Untrusted content | Repository files and retrieved pages are wrapped in `<untrusted>`. Statuses are computed by code. LLM judge verdicts count only with verbatim quotes from the source | `test_llm_judge_rejects_unquoted_verdicts` |
| Limits & headers | Body ≤ 256 KB, answer ≤ 20 000 chars, ≤ 5 URLs. `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` | `test_api_end_to_end` |

**Malicious-input tests:** symlink escapes from the workspace, shell-metacharacter argv, non-allowlisted binaries
(`docker`, `python -c`, `npm exec`), NUL and traversal in workspace paths, a fork bomb (stopped by the pids limit), writes
to `/usr`, `/etc` and the read-only dependency mounts, host paths and host-file symlinks invisible inside the container,
and containers removed after timeouts.

**Residual risks.**
- **Shared kernel:** Docker containers share the host kernel. A kernel exploit could escape. This is not VM-level isolation.
  For hostile repositories use a VM, or gVisor/Kata as the Docker runtime.
- Host-toolchain mode exposes host `/usr` read-only (binaries and libraries, normally no secrets). Use the self-contained image to avoid this.
- The process fallback runs on the host filesystem.
- There is a single access token, with no multi-user roles.
- For untrusted repositories, run VeriCode as a dedicated user with Docker available.
