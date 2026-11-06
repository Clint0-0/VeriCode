# Security

| Control | Implementation | Tested |
|---|---|---|
| Credentials | Read from env/.env only; `/settings` exposes presence flags; PUT rejects `*api_key`; `.env` git-ignored | `test_api_end_to_end` |
| Secrets in prompts/logs | `security.redact()` applied to every LLM prompt, command output and Tavily error; sensitive files (`.env*`, `*.pem`, `id_rsa*`, `credentials*`) are listed but never read into context | `test_redaction` |
| Workspace boundary | Project paths must resolve inside `VERICODE_WORKSPACES`; edits via `safe_join` reject absolute paths, `..`, NUL, symlink escapes and `.git/.venv/node_modules/.env` | `test_safe_join_rejects_traversal`, `test_edit_parsing_and_safety` |
| Overwrite protection | Agent edits a copy (`demos/_runs/<task>`); empty-SEARCH cannot overwrite non-empty files; SEARCH must match exactly once; `apply` refuses if workspace files changed since the run (SHA-1) | `test_apply_changes_with_overwrite_protection` |
| Command execution | No shell; argv allowlist (`pytest`, `python -m pytest|py_compile|mypy|ruff`, `npm test|run test|run lint|run typecheck`, `npx tsc --noEmit|vitest run`); metacharacters rejected; scrubbed env (keys removed); RLIMIT_CPU 300s, AS 4 GB, FSIZE 200 MB; new session; timeout (default 120 s) | `test_command_allowlist`, `test_command_env_scrubbed_and_timeout` |
| Network isolation for tests | `unshare -rn` (user + network namespace) when available; reported per run as `isolation` and in `/health` | available in this environment (`no-network(unshare)`) |
| Runtime API introspection | Only if static analysis fails: separate `python -I` process with scrubbed env and 10 s timeout | – |
| SSRF | User URLs: http/https only, no credentials in URL, every resolved IP must be public (blocks loopback, private, link-local incl. 169.254.169.254, reserved); redirects re-checked (max 3) | `test_ssrf_guard`, `test_ssrf_blocked_for_user_urls` |
| Request limits | Body > 256 KB → 413; answer ≤ 20 000 chars; ≤ 5 URLs; prompt ≤ 8 000 chars | `test_api_end_to_end` |
| Prompt injection | Repository content and retrieved documents are wrapped in `<untrusted>` and the system prompt says they are data. Verification decisions are deterministic code, not LLM judgments, so injected text cannot change a status | – |

**Not implemented / limitations:** no container or seccomp sandbox. Tests run as the server's user on the host
filesystem (inside a workspace copy whose `.venv` is a symlink to the original). Generated test code can
still read files the user can read. Run VeriCode under a dedicated low-privilege user or inside a container for
untrusted repositories. CORS is limited to the Vite dev origin, and there is no authentication: bind to
127.0.0.1 only (the default in `scripts/run.sh`).
