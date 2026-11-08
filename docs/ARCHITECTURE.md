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
| C Local Dependency Truth | `pyinspect.py`, `jsinspect.py`, `verify_api.py` | Python: AST over installed source, follows `from x import`, star imports, `_dynamic_imports` maps, base classes; detects `@deprecated`, top-level `warnings.warn(DeprecationWarning)`, and `kwargs.pop('x')` + `raise` (removed kwargs); package-provided migration messages for missing names. Optional runtime introspection in an isolated subprocess (`python -I`, timeout, scrubbed env) only when static resolution fails. JS/TS: **TypeScript compiler API** (`tools/ts-checker/check.cjs`, pinned TS 5.9.3) resolves the module from the project's node_modules (export maps, `types`). It checks named and default exports, class/interface/namespace members, signatures (required/optional/rest, generic constraints) and `@deprecated`, and type-checks the planned call (`args` = TS expressions). The regex `.d.ts` reader is the fallback when the checker is not installed. |
| D Tavily | `tavily.py` | `POST /search` (+ `/extract` for full page text of top results). Missing key, timeout, network, 429 (Retry-After), 5xx, invalid schema, no results → explicit `SearchOutcome.status`; bounded retries; SQLite cache with TTL. |
| E0 Claim decomposition | `claim_parse.py` | Modular steps: subordinate clauses (although/whereas/because; time and conditional clauses stay attached) → non-restrictive relative clauses on the subject → coordinated predicates. Features: hedging, hypotheticals, comparisons, quantities with units, version ranges, temporal markers, qualifiers/exceptions, unresolved pronoun subjects (marked `incomplete`, never verified). Dataset: `backend/tests/data/claim_dataset.json` |
| E1 Source authority | `source_authority.py` | Trusted-domain registry (configurable `trusted_registry`), category rules (`authority_rules`), exact/dot-bounded host matching, impersonation detection (embedded trusted domain, hyphen look-alike, 1-edit typo), publisher/entity matching, primary/secondary/unknown/suspicious tiers with explanations. Suspicious sources are never decisive |
| E Stale-answer detection | `claims.py`, `stale.py` | Span-traceable extraction (compound splitting, negation, conditionals, opinions, ranges; optional LLM extraction). Verification: value check → lexical/negation check → optional quote-validated LLM judge. Configurable authority rules. See formulas below. |
| F Risk engine | `verify_api.py` | Statuses VERIFIED_LOCAL, VERIFIED_LIVE, STALE, INCOMPATIBLE, DEPRECATED, NOT_FOUND, UNCERTAIN, NOT_CHECKED. Separate fields: `api_compatibility`, `evidence_freshness`, `verification_confidence`, `risk_score`. |
| G Surgical context | `agent.build_briefing`, `select_relevant_files` | Briefing lists only problems + one line of verified APIs; coder receives relevant files only; repair rounds receive failure digest + changed files only. |
| H Coding agent | `agent.py` | SEARCH/REPLACE edit protocol; exact-single-match application; refuses blind overwrites; runs in `demos/_runs/<task>` copy; tests via allowlisted commands; bounded repairs; unified diff; `apply` endpoint with hash-based overwrite protection. |
| I Project memory | `memory.py` | Rules only from high-confidence findings verified against installed source; version spec `==installed`; TTL 30 days; deactivated when installed version changes; export to `.agent-rules.md` inside a managed block (user content preserved). |
| K Persistence | `db.py` | Tables: projects, tasks, token_usage, analyses, claims, evidence, rules, cache, benchmarks. Created idempotently on startup (no migration tool needed). |
| M Benchmark | `benchmark.py` | See BENCHMARK.md. Also reports flagged-API usage shipped by each mode. |
| Combined workflow | `local_evidence.py` | Track 1 claims naming an installed package and an API symbol (`@decorator`, `Class.method()`, backticks, "X decorator") are resolved against installed code. Outcome rules: deprecated+recommended → contradict; deprecated+"deprecated" claim → support; exists+"removed" claim → contradict; missing (with migration message)+"exists" claim → contradict; unknown symbol → no evidence. |
| Correction tracking | `agent.api_corrections` | Flagged usage patterns (call, decorator, import, rejected kwarg, exact TS call) are searched in the added lines of the final diff: `corrected` or `still_used`. |

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
`30·max authority + 20·mean relevance + 15·completeness (claim-term coverage) + 10·specificity (value-based=1, else 0.5)
+ 15·corroboration (distinct domains, max 3) + 10·date known − 30·conflict − 10·(decided only lexically or by the LLM judge)`.

**Authority** (in order): preferred domains 0.95 → category primary sources from Settings 0.95 → government 1.0 →
community/blog 0.35 → the claim's own entity site (domain label matches a claim term) 0.9 → registries 0.8 →
docs subdomains 0.8 → encyclopedia 0.6 (secondary) → news 0.7 (secondary) → org/project sites 0.7 → general web 0.5.
Authority is applied only to sources whose content passed the relevance gate.

**Claim status rules**
- Evidence sufficiency (applied before the rules below):
  - only primary or secondary, non-community sources may contradict a claim;
  - a weak side is set aside against a strong side, and disagreement among weak sources only is UNVERIFIED;
  - a lexical match never overrides value, installed-code or judged evidence;
  - for "latest version" claims, an authoritative source naming a newer version contradicts regardless of dates;
  - a value inside a negated sentence is not support.
- Relevance: a source counts only if ≥34 % of the claim's subject terms appear in the best-matching excerpt.
- *support (value)*: the claim's concrete value appears in a statement covering ≥50% of the claim's terms (version, money, person, percent, year). For "latest/current"
  version claims, the source's highest version must equal the claimed one.
- *contradict*: a same-type value differs (e.g. a newer version than the claimed latest, a different price in the same currency).
- Support + contradiction → `CONTRADICTED` if every contradicting source is dated later than every supporting one
  and is not community-grade; otherwise `CONFLICTING_EVIDENCE`.
- Only support → `CURRENT_SUPPORTED`, or `POTENTIALLY_STALE` if the claim asserts a present state and the best
  supporting evidence has freshness < 25. Past-event claims ("introduced in", "was released") do not go stale.
- *support (lexical)*: ≥75% normalised term coverage with the same polarity. *contradict (lexical)*: the same
  coverage with opposite polarity (negation).
- *LLM judge* (real provider, optional, only when nothing was decided by value): structured verdict. Its quotes must
  appear verbatim in the cited excerpt, otherwise the verdict is discarded.
- No support or contradiction → `UNVERIFIED`, with `missing_evidence` (e.g. search unavailable, related sources that
  don't state the claim). Absence of support never becomes `CONTRADICTED`.
- Stable statements → `NOT_APPLICABLE`.

**Corrected answer**: only `CONTRADICTED` claims with a value extracted from evidence are rewritten, each with a
numbered citation. Unresolved claims are marked inline. The original text is always returned alongside.
