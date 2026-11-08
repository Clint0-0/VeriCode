# Problem statements and solution rationale

> **Official documents missing (external blocker).** The official hackathon documents for **Track 1, Problem
> Statement 1** and **Track 2, Problem Statement 1** are not in this repository or in any material supplied to the
> build. No official link is recorded anywhere in the project. The descriptions below are **our own summaries**, not
> official wording. To close this, add the originals unchanged as `docs/problem-statements/track1-ps1.pdf` and
> `docs/problem-statements/track2-ps1.pdf` and link them here. Requirement-by-requirement mapping with evidence:
> [submission/TRACK_MAPPING.md](submission/TRACK_MAPPING.md).

## Our selection (own summaries)
**Track 1, Problem Statement 1 — stale-answer detection.** LLM answers can contain information that was true once
but is outdated now: versions, prices, laws, leadership, specifications, deadlines. The task is a layer that breaks an
answer into claims, finds the time-sensitive ones, checks them against current, trustworthy evidence and explains
the result with sources.

**Track 2, Problem Statement 1 — token-efficient coding agent.** Build a coding agent that completes real coding tasks
in an existing repository correctly, using as few tokens as possible, and measures that consumption.

## Why combine them
Both fail the same way: **a model trusts knowledge that no longer matches reality.** In Track 1 that reality is
the current state of the world. In Track 2 it is the exact dependency versions installed in the repository. VeriCode
applies one principle to both, *verify before you trust or generate*, with shared machinery:

| Need | Track 1 | Track 2 |
|---|---|---|
| Decide what needs checking | claim extraction, volatility, temporal sensitivity | speculative API skeleton (planner) |
| Ground truth | live web evidence (Tavily), user URLs, **installed packages** | **installed package source** first, official docs (Tavily) as fallback |
| Explainable verdict | status, freshness, confidence, authority, sources | VERIFIED / DEPRECATED / INCOMPATIBLE / NOT_FOUND, risk factors, signatures |
| Act on it | cited corrected answer (never invented) | surgical briefing injected before code generation |

## Workflows
**Track 1:** answer → span-traceable claims (with clause decomposition, negation, hedging, qualifiers) → only volatile,
verifiable claims are searched → relevance gate → value / lexical / optional LLM-judge comparison → authority tiers →
status + freshness (from the publication date only) + confidence (separate scores) → corrected answer with citations.

**Track 2:** task → repository inspection (declared vs installed versions) → planner lists intended APIs (validated
JSON) → each API checked against installed code (Python AST, TypeScript compiler API) → Tavily docs only when local
checking is insufficient → compact briefing with only the corrections → code generated in a sandbox copy → allowlisted
tests, typecheck and lint → bounded repair → diff, review, safe apply → every token counted (ACTUAL / ESTIMATED / MOCK).

**Combined:** Track 1 claims about libraries installed in a chosen workspace ("use pydantic's `@validator`") are checked
against that installed code. **Why local inspection is valid evidence for stale API claims:** many API claims are
version-dependent ("X is the way to do Y"). The installed source is the authoritative definition of the API *for that
version*. Its `@deprecated` markers, warnings and migration messages are the maintainers' own statements. Web
pages may describe other versions or be outdated themselves. VeriCode labels such evidence `installed_source` and
version-specific (it does not claim to describe the *latest* release), and never rewrites an answer from it.

## Main technical innovation
**Local-first pre-flight verification.** Before generating code, VeriCode checks the planned API surface against the
package code actually installed. It does this deterministically and without executing user code, using the
TypeScript compiler for JS/TS. Only the resulting corrections go to the coding model. The same verifiers double as
version-specific evidence for factual claims.

## Differentiators
- Declared ranges are never confused with installed versions; lockfile transitive entries are excluded.
- Deterministic first (AST, compiler, value and lexical checks). LLM judgments must quote the source verbatim.
- Missing evidence never becomes a contradiction. Opinions, hypotheticals and unresolved-subject claims are not verified.
- Freshness, confidence and authority are separate and explained. Impersonation-like domains are never decisive.
- Honest measurement: ACTUAL / ESTIMATED / MOCK labels, savings only for comparable successful runs, negative results kept.
- Security: Docker sandbox (no network, read-only, non-root, limits), local auth with CSRF, SSRF guards.

## Known limitations
See README "Known limitations". In short: live Tavily and LLM paths have not been exercised in this environment
(credentials pending). Deterministic extraction is heuristic for complex rhetoric. The Docker sandbox shares the host
kernel.
