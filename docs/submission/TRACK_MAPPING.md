# Track mapping

> **Official problem-statement documents are not in this repository.** The requirement lists below are the team's
> own reading of the selected problem statements (Track 1 PS1, Track 2 PS1). They are not official wording. See
> [../PROBLEM_STATEMENTS.md](../PROBLEM_STATEMENTS.md) and add the originals to `../problem-statements/`.

Evidence labels: **LOCAL** · **CI** · **LIVE** (real Groq `openai/gpt-oss-120b` + Tavily) · **MOCK** · **BLOCKED**.

## Track 1, PS1 — stale-answer detection (team summary)

| Requirement (team reading) | VeriCode implementation | Evidence |
|---|---|---|
| Split an answer into checkable claims | `claims.py`, `claim_parse.py`: atomic claims with character spans, clause decomposition | LOCAL · CI (26-case dataset) · LIVE (scenarios A–D) |
| Find time-sensitive claims | volatility, temporal sensitivity, verifiability; only volatile claims are searched | LOCAL · CI · LIVE |
| Check against current evidence | Tavily search + extract, user URLs, installed packages | LIVE |
| Judge source trustworthiness | `source_authority.py` tiers, impersonation detection, evidence sufficiency | LOCAL · CI · LIVE |
| Explain the verdict with sources | status, evidence freshness, verification confidence, supporting/contradicting sources, verbatim quotes | LIVE (UI checked over persisted live data) |
| Correct the answer | cited corrected answer, never invented | LOCAL · CI · LIVE (scenario B correction 3.14) |
| Distinguish freshness from truth | separate freshness and confidence scores; old dated pages labelled "correct when published" | LIVE |

## Track 2, PS1 — token-efficient coding agent with dependency awareness (team summary)

| Requirement (team reading) | VeriCode implementation | Evidence |
|---|---|---|
| Work in an existing repository | `repo_intel.py`: manifests, lockfiles, installed versions, conventions, relevant files | LOCAL · CI · LIVE |
| Avoid APIs that don't match installed dependencies | planner skeleton → `verify_api.py` against installed source (Python AST, TS compiler API) before code generation | LOCAL · CI · LIVE (Python + TS tasks; 8 chained TS APIs resolved live) |
| Complete real coding tasks correctly | sandboxed edits, allowlisted tests, bounded repairs | LIVE (new Python, TS, chained-TS tasks; Demo C) |
| Use few tokens and measure them | surgical briefing, relevant files only, targeted repairs; tokens by stage labelled ACTUAL / ESTIMATED / MOCK | LIVE benchmark — see [RESULTS_AND_LIMITATIONS.md](RESULTS_AND_LIMITATIONS.md) |
| Safe execution | Docker `--network none`, read-only rootfs, uid 65534, cap-drop ALL, limits; labelled process fallback | CI (16 Docker tests) |
