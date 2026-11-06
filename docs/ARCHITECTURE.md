# Architecture

```
frontend/ (React 19 + TS + Tailwind v4, Vite)  ──REST──►  backend/vericode/api.py (FastAPI)
                                                              │
   ┌──────────────────────────────────────────────────────────┼─────────────────────────────┐
   │ Track 2: coding agent (agent.py)                          │ Track 1: stale answers       │
   │  repo_intel ─► skeleton (planner LLM, strict JSON)        │  claims (deterministic)      │
   │     │             │                                       │     │                        │
   │     ▼             ▼                                       │     ▼                        │
   │  verify_api ◄─ pyinspect / jsinspect (installed source)   │  stale: tavily / user URLs / │
   │     │  └─ tavily (live docs, domains from pkg metadata)   │         fixture evidence     │
   │     ▼                                                     │     │ compare, freshness,    │
   │  memory (verified rules) ─► briefing ─► coder LLM         │     ▼ confidence, correction │
   │     ─► apply edits (sandbox copy) ─► run_checks ─► repair │                              │
   └──────────────────────────────────────────────────────────┴─────────────────────────────┘
                     db.py (SQLite)  ·  llm.py (anthropic | openai-compatible | mock)  ·  security.py
```

| Module (spec) | File | Notes |
|---|---|---|
| A Repository Intelligence | `repo_intel.py` | requirements/pyproject/poetry.lock/uv.lock/package.json/package-lock/pnpm/yarn; installed versions from `.venv/**/site-packages/*.dist-info/METADATA` and `node_modules/*/package.json` (metadata only, nothing imported). Fingerprint = hash of manifests + sources + installed dist names → env cache keyed by fingerprint (auto-invalidates). Relevant-file scoring: path/symbol/import term overlap with IDF filtering + exact identifiers; reasons returned. |
| B Speculative API Skeleton | `skeleton.py` | Planner prompt asks for JSON only; validated by Pydantic schema; up to 3 attempts with the validation error fed back. |
| C Local Dependency Truth | `pyinspect.py`, `jsinspect.py`, `verify_api.py` | Python: AST over installed source, follows `from x import`, star imports, `_dynamic_imports` maps, base classes; detects `@deprecated`, top-level `warnings.warn(DeprecationWarning)`, and `kwargs.pop('x')` + `raise` (removed kwargs); package-provided migration messages for missing names. Optional runtime introspection in an isolated subprocess (`python -I`, timeout, scrubbed env) only when static resolution fails. JS: `exports`/`types`, `export * from`, `export {a as b} from`, `@deprecated` JSDoc, members of classes/interfaces; TS compiler API check when project has `typescript`. |
| D Tavily | `tavily.py` | `POST /search` (+ `/extract` for full page text of top results). Missing key, timeout, network, 429 (Retry-After), 5xx, invalid schema, no results → explicit `SearchOutcome.status`; bounded retries; SQLite cache with TTL. |
| E Stale-answer detection | `claims.py`, `stale.py` | See formulas below. |
| F Risk engine | `verify_api.py` | Statuses VERIFIED_LOCAL, VERIFIED_LIVE, STALE, INCOMPATIBLE, DEPRECATED, NOT_FOUND, UNCERTAIN, NOT_CHECKED. Separate fields: `api_compatibility`, `evidence_freshness`, `verification_confidence`, `risk_score`. |
| G Surgical context | `agent.build_briefing`, `select_relevant_files` | Briefing lists only problems + one line of verified APIs; coder receives relevant files only; repair rounds receive failure digest + changed files only. |
| H Coding agent | `agent.py` | SEARCH/REPLACE edit protocol; exact-single-match application; refuses blind overwrites; runs in `demos/_runs/<task>` copy; tests via allowlisted commands; bounded repairs; unified diff; `apply` endpoint with hash-based overwrite protection. |
| I Project memory | `memory.py` | Rules only from high-confidence findings verified against installed source; version spec `==installed`; TTL 30 days; deactivated when installed version changes; export to `.agent-rules.md` inside a managed block (user content preserved). |
| K Persistence | `db.py` | Tables: projects, tasks, token_usage, analyses, claims, evidence, rules, cache, benchmarks. Created idempotently on startup (no migration tool needed). |
| M Benchmark | `benchmark.py` | See BENCHMARK.md. |

## Scoring

**API risk score** (0–100, additive, explainable, *not a probability*): not_found 60, package_missing 60,
rejected_argument 50, unsupported_argument 40, deprecated 30, unverifiable 25, assumed_major_mismatch 20,
live_conflict 15, uncertain_argument 8. Each applied factor is listed with its detail.

**Evidence freshness** = `100 × 2^(−age_days / half_life[category])`, computed from the source's
*published/updated* date only. If no date is available it is reported as `unknown` (never derived from
retrieval time). Half-lives (days, configurable in Settings / `config.DEFAULT_HALF_LIVES`):
software_version 90, api_documentation 180, pricing 60, leadership 365, law_regulation 365, product_spec 180,
release_date 365, deadline 30, current_events 14, other_volatile 180.

**Verification confidence** (0–100 evidence-strength index, *not calibrated*) over decisive sources =
`35·max authority + 25·mean relevance + 15·specificity + 15·corroboration(distinct domains, max 3) + 10·date known − 30·conflict`.

**Claim status rules**
- Relevance: a source counts only if ≥34 % of the claim's subject terms appear in the best-matching excerpt.
- *support*: the claim's concrete value appears (version, money, person, percent, year). For "latest/current"
  version claims, the source's highest version must equal the claimed one.
- *contradict*: a same-type value differs (e.g. a newer version than the claimed latest, a different price in the same currency).
- Support + contradiction → `CONTRADICTED` if every contradicting source is dated later than every supporting one
  and is not community-grade; otherwise `CONFLICTING_EVIDENCE`.
- Only support → `CURRENT_SUPPORTED`, or `POTENTIALLY_STALE` if the claim asserts a present state and the best
  supporting evidence has freshness < 25. Past-event claims ("introduced in", "was released") do not go stale.
- No support or contradiction → `UNVERIFIED` (with the reason, e.g. search unavailable).
- Stable statements → `NOT_APPLICABLE`.

**Corrected answer**: only `CONTRADICTED` claims with a value extracted from evidence are rewritten, each with a
numbered citation. Unresolved claims are marked inline. The original text is always returned alongside.
