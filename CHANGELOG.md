# Changelog

## 2.3.2 — final completion round
- **LIVE**: a chained-call TypeScript task passed first try (2,811 tokens), with 8 chained zod/vitest APIs resolved
  by pre-flight through call return types.
- Pre-flight false alarms found live and fixed (LOCAL · CI):
  - identifiers the task asks to create (`RegistrationSchema.parse`) are UNCERTAIN, not NOT_FOUND;
  - instance members of classes inside a namespace (`z.ZodSchema.parse`);
  - planner names that repeat the module (`vitest.expect.toThrow`).
- Live harness:
  - `coding_typescript_chain` section;
  - quota-stopped runs and benchmarks are BLOCKED, not FAILED;
  - the live workflow waits out resets up to 180 s.
- Security: runtime introspection, which imports installed package code on the host, now runs without network
  (`unshare -rn`) where supported. History secret scan, `npm audit` and `pip-audit` are clean.
- Browser: new tests for empty states, error states and mock labelling, run in CI.
- Fix: claim explanations no longer run two sentences together.
- Docs:
  - `docs/submission/`: overview, Mermaid diagrams, track mapping, demo script, results and limitations, checklist,
    labelled offline screenshots;
  - README tech stack and differentiators;
  - `signup` benchmark marked BLOCKED.

## 2.3.1 — final live round (`feat/vericode-live-final`)
**Confirmed live (Groq + Tavily)**: model_dump import-path fix, truncation detection + bounded retry, new Python and
TypeScript tasks, Demo C, Track 1 B/D improvements, Demo E, browser pass over persisted live results (6/6).

**Track 1**
- Evidence sufficiency: only primary/secondary, non-community sources may contradict a claim. A weak side is set
  aside against a strong side, and disagreement between weak sources only is UNVERIFIED.
- A lexical match never overrides value, installed-code or judged evidence.
- Version monotonicity: an authoritative source naming a newer version contradicts a "latest version" claim
  regardless of dates. An undated page with an equal or older value cannot override dated evidence.
- A value inside a negated sentence is no longer support.
- Product -> publisher aliases (ChatGPT -> openai, Claude -> anthropic, ...).

**Pre-flight (false alarms found live)**
- Python: positional values for `*args` APIs (`field_serializer('due')`).
- TypeScript:
  - namespace-object members and member paths (`z.object`, `z.coerce.number`);
  - chained call results (`z.coerce.number().int()`, `expect().toThrow()`), with the chained call type-checked;
  - no zero-argument check when no arguments were planned;
  - planner-side identifiers count as uncertain, not INCOMPATIBLE.

**Providers**
- Rate limits: `retry-after` wins; short resets are waited out (bounded), long ones stop immediately with the
  provider's limits.
- Remaining quota is recorded.
- Optional structured-stage `reasoning_effort`, dropped automatically if the model rejects it.

**Tokens**: compact planner output contract. Actual benchmark (3 runs per mode): `users` 79.6% savings, `summary`
49.6% savings, `signup` not computable (one VeriCode run rate-limited; the completed pairs were about −130%). That is
three small tasks and not a general savings claim.

**Live completion round (`18b9c81`)**: new TypeScript task passed first try (3,026 tokens, 7/7 APIs VERIFIED_LOCAL).
Chained-call pre-flight is verified by regression tests only. Anthropic is still not live-tested.

**Tooling**: harness quota gate, live truncation probe, `--bench-tasks`; `test_e2e_live.py` (Playwright over live data).

## 2.3.0 — live validation (`feat/vericode-live-validation`)
**Live (Groq via OpenAI-compatible adapter + Tavily, run in GitHub Actions; details in docs/LIVE_VALIDATION.md)**
- New `vericode.live_validation` harness: config/model availability, text, structured planner, API skeleton,
  streaming usage, error handling, evidence judge with quote verification, Tavily search/extract/persistence,
  Track 1 scenarios A-D, Demo E, new Python + TypeScript + arbitrary coding tasks, actual-token benchmark, and a
  check of the API data behind every screen. No MOCK/fixture fallback; refuses to write a report containing a key.
- `.github/workflows/live.yml`: manual workflow reading keys from repo secrets, model/endpoint from repo variables.

**Fixes found by the live run**
- Pre-flight: a class written into the import path (`pydantic.BaseModel` + `model_dump`) was reported NOT_FOUND;
  trailing path segments are now retried as attributes. The false finding had made the coder add a bogus fallback.
- Providers: output truncation (`finish_reason=length` / `max_tokens`) is detected; the truncated call's usage is
  recorded and the call is retried once with double the budget (cap 8192). Empty output at the limit is a clear
  error. HTTP 429 after retries now says it is a rate limit and passes on `retry-after`.
- Optional `VERICODE_REASONING_EFFORT` (sent only when set).
- Offline tests no longer pick up a developer `.env` endpoint.

**Measured**: first ACTUAL_PROVIDER_USAGE benchmark - VeriCode 9/9 successes vs baseline 6/9, but -250.3% token
savings on the one task where both always succeeded. Historical MOCK numbers kept separately.

## 2.2.0 — offline hardening (`feat/vericode-offline-hardening`)
**Track 1**
- New `claim_parse.py`: modular deterministic decomposition.
  - Subordinate clauses are split (although/whereas/because). Time and conditional clauses stay attached.
  - Non-restrictive relative clauses on the subject are split out. Coordinated predicates are split as before.
  - Exact sub-spans (`fragment_span`) whenever a claim is verbatim; `derived` flags carried-over subjects.
  - Features: hedging, hypotheticals (never verified), comparisons, quantities with units, version ranges,
    temporal markers (`previously` means a past state), qualifiers/exceptions.
  - Unresolved pronoun subjects are marked `incomplete`: kept, never searched, never verified.
- New `source_authority.py`: a configurable trusted-domain registry (government, standards, official software docs,
  package registries, research, news, encyclopedia, community), plus:
  - category rules and exact/dot-bounded host matching;
  - **impersonation detection** (embedded trusted domain, hyphen look-alike, one-character typo);
  - publisher/entity matching based on proper nouns in the claim, so a `.com` is not official by default;
  - primary/secondary/unknown/suspicious tiers with explanations.
- Suspicious sources are never decisive. Newer evidence supersedes older only at comparable authority, and never from community sources.

**Local evidence (combined workflow)**
- **Fix:** packages whose `top_level.txt` lists a private module first (pytest: `_pytest`) resolved the wrong import
  name, so their claims were silently unverifiable.
- **Fix:** the AST cache was keyed by path only, so a long-running server kept serving the pre-upgrade source after a
  dependency upgrade. It is now keyed by (path, mtime, size).
- Dotted (`vi.useFakeTimers`) and lowerCamelCase (`createProgram`) symbol detection. The symbol name is shown in the evidence title.
- Regression tests across pydantic, pytest, zod, vitest and typescript, plus a version-upgrade invalidation test.

**Providers**
- **Fix:** empty model content is now an error, not a silent "success".
- **Fix:** streams without a completion event (`message_stop` / `finish_reason`) are rejected as incomplete.
- **Fix:** malformed or negative usage metadata becomes ESTIMATED instead of crashing.
- **Fix:** non-numeric Tavily `usage.credits` no longer breaks parsing.
- `MOCK_PROVIDER_NO_SCRIPT` now lists the supported demo tasks and the exact environment variables needed.
- 31 provider/Tavily **contract** tests (fake transports; not live).

**Sandbox**
- `docker_command()` refactor.
- Optional **self-contained image** mode (`docker/sandbox.Dockerfile`, `scripts/build_sandbox_image.sh`), with no host `/usr` mount.
- In host mode, a venv interpreter prefix outside `/usr` (pyenv, setup-python) is mounted read-only.
- Added `--ipc private`, `--ulimit nofile`, and forced container removal on timeout.
- **Fix (found by CI):** running a container directly on a fresh host failed because the local base image was never
  created. It is now created on first use.
- **Fix (found by CI, non-root hosts):** dockerd created root-owned mount points inside the workspace copy, so later
  runs failed with EPERM. Mount points are now pre-created as the current user, and foreign-owned entries are tolerated.
- Providers fail fast on a missing API key, before any network or TLS setup.
- New tests: read-only dependency dirs, TypeScript check inside the container, cleanup, malicious commands.

**Offline and repository**
- `scripts/demo.sh offline` runs A/B/D/E and the benchmark, each with an expected-outcome check (non-zero exit on UNEXPECTED).
- New docs: `docs/OFFLINE_DEMO.md`, `docs/SETUP_WINDOWS.md` (WSL2), `docs/PROBLEM_STATEMENTS.md` plus a placeholder for the official documents.
- `.gitattributes` enforces LF.
- Key-free GitHub Actions CI.
- UI: authority tier and explanation badges, claim derivation and linguistic feature badges.

**Tests:**
- Backend 120 → 228 passed, including 6 browser e2e, plus 2 opt-in live tests that skip without keys.
- Frontend 8 → 9.

## 2.1.0 — final validation (`feat/vericode-final-validation`)
- **Combined workflow** (`local_evidence.py`, Demo E): Track 1 claims about libraries installed in a selected
  workspace are checked against the installed source. Python uses the AST resolver; TypeScript uses the compiler API.
  The checks cover existence, deprecation and package migration messages, and distinguish "deprecated" claims
  from "removed" claims. Evidence is labelled `installed_source` and is version-specific. It can flag a claim but
  never rewrites it.
- **Auto-correction tracking:** after a VeriCode run, every flagged API is checked against the added lines of the
  final diff and reported as `corrected` or `still_used`. Benchmarks also report how many flagged APIs the
  baseline shipped. In the TS demo the baseline ships the deprecated `nonempty()`.
- **Confidence heatmap** in the Pre-Flight Inspector and task reports: rows are libraries, cells are planned APIs, coloured by status, with correction outcomes.
- **Streaming** for coder/repair calls: Anthropic SSE (`message_start` / `message_delta` usage) and OpenAI
  (`stream_options.include_usage`). Missing stream usage is labelled ESTIMATED. Toggle: `VERICODE_LLM_STREAM`.
- **Per-model pricing** (`model_prices` setting). Analytics show cost per provider/model with the cost basis. MOCK is never priced.
- Demo CLI: `a`/`b`/`c`/`d`/`e` aliases.
  - Demo C runs a non-bundled task. It needs a real provider; with MOCK it reports the blocker explicitly.
  - Demo E shows the combined workflow.
- **Fix:** a NUL byte in a workspace path raised an unhandled `ValueError` (HTTP 500). It now raises `SecurityError` (400).
- **Tests:**
  - Backend 91 → 114, plus 6 browser e2e (real uvicorn + Chromium).
  - Frontend 6 → 8.
  - New security tests: symlink escapes, command-injection argv, workspace path attacks, a docker host-file
    isolation probe, and a fork bomb contained by the pids limit.

## 2.0.0 — completion phase (`feat/vericode-completion`)

### Track 1 — stale-answer detection
- Claim extraction rewritten. Paragraphs, bullets and lists are segmented with character spans back into the
  original answer. Compound sentences are split on coordinated predicates with subject carry-over. Negation,
  conditional, opinion and date-range detection added.
- New classification fields: temporal sensitivity, verifiability, required evidence type. Opinions and stable facts trigger no search.
- Optional LLM claim extraction (planner model, schema-validated). Every claim must map to an exact span or it is dropped.
- Semantic verification:
  - Value matches now also require ≥50% statement coverage, so a version mentioned anywhere no longer counts as support.
  - Lexical support and negation contradiction added.
  - Optional LLM evidence judge with structured output. Its quotes must appear verbatim in the source.
- Absence of support never yields CONTRADICTED. Unresolved claims carry a `missing_evidence` explanation.
- Conflicting evidence lists both sides with dates, authority and the reason no conclusion is possible.
- Configurable source-authority rules per claim category (persisted). Entity-site detection added. Secondary sources are labelled.
- The corrected answer is built from the original text via spans, so structure is preserved. Only cited
  replacements are applied; unresolved claims are qualified inline.
- Confidence formula extended: completeness, specificity, and a method penalty for lexical/LLM-only decisions.

### Track 2 — pre-flight gatekeeper and coding agent
- TypeScript compiler-API checker (`tools/ts-checker`, pinned TypeScript 5.9.3, never installed into user projects):
  - module resolution and export maps;
  - named and default exports, class/interface/namespace members;
  - signatures with required, optional and rest params and generic constraints;
  - `@deprecated`;
  - real type-check of the planned call (TS2345 / TS2554 …).
- New TypeScript demo project (`demos/ts_project`, zod 3.23.8) and catalog task `signup`.
- Lockfile transitive packages are no longer reported as project dependencies.
- Agent:
  - project conventions injected into the prompt;
  - lint/typecheck run as regression checks (they block only if they passed before the change);
  - `partial` outcome when no tests exist (never counted as success);
  - stops repairing when there is nothing to validate against.
- Apply step: structured conflict report with the user's diff (HTTP 409). Content-only copy keeps workspace
  permissions. The sandbox is deleted after apply, and old run copies are cleaned up.

### Providers, measurement and benchmarks
- Provider layer aligned with current APIs:
  - Anthropic Messages (`anthropic-version`, cache token fields);
  - OpenAI Chat Completions (`max_completion_tokens` for api.openai.com).
- Added explicit timeouts, Retry-After handling, structured-output helper (`complete_json`) and `provider_status()`
  listing missing env vars. A failing real provider raises an error and never falls back to mock.
- Every LLM call is labelled `ACTUAL_PROVIDER_USAGE`, `ESTIMATED` or `MOCK`. The dashboard and benchmarks keep real and mock apart.
- Benchmarks add:
  - average savings across comparable tasks, with spread;
  - per-run paired savings;
  - verification-overhead tokens;
  - model ids.
- Tavily client aligned with the official OpenAPI spec:
  - request fields `include_published_date`, `include_usage`, `include_domains_mode=prefer`;
  - `/extract` with query reranking and `failed_results`;
  - error codes 432/433/434/422;
  - per-request usage and credits recorded in `search_usage`; extract results cached.

### Security
- Docker sandbox: local base image built without a registry pull, `--network none`, read-only rootfs, host `/usr`
  read-only, only the workspace copy writable, uid 65534, `--cap-drop ALL`, `no-new-privileges`, memory/CPU/pids
  limits, tmpfs for caches, forced kill on timeout. An explicit `docker` request never silently downgrades.
- Removed `RLIMIT_AS` from the process sandbox (it broke V8/WASM). Network status is labelled truthfully.
- Authentication:
  - one-time token, exchanged for an HttpOnly SameSite=Strict session cookie plus a CSRF token on every write;
  - Bearer token for CLI use;
  - Host-header allowlist (DNS rebinding);
  - refuses non-loopback bind without `VERICODE_ALLOW_REMOTE=1`;
  - security headers.
- SSRF: the connected peer address is re-checked after connect, and the body size is capped.

### Persistence
- Versioned SQLite migrations (`schema_version`).
- Settings persisted in the `settings` table: models, sandbox, judge, search depth, authority rules, freshness
  windows, limits, costs. Secrets stay environment-only.

### Frontend
- Login screen (token URL or paste) and CSRF-aware client.
- Integration status panel (missing env vars shown).
- Original answer shown with claim spans highlighted by status (click to open the claim).
- Supporting and contradicting evidence columns, conflict panel, missing evidence, judge verdicts.
- TypeScript signatures and type-check diagnostics in findings.
- Partial and conflict handling in tasks.
- Measurement-class views and separation of real vs mock benchmarks; Tavily usage panel.
- Persisted settings including sandbox, judge and authority rules.
- Responsive sidebar.

### Tests
- Backend: 57 → 91 passing (2.0.0), plus 2 opt-in live tests (skipped without credentials). Frontend: 5 → 6.

## 1.0.0 — initial build (`feat/vericode-main`)
First end-to-end implementation: see git history.
