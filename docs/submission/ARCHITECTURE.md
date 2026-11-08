# VeriCode architecture (submission view)

Detailed module notes and formulas: [../ARCHITECTURE.md](../ARCHITECTURE.md). These diagrams match the modules in
`backend/vericode/`.

## System overview

```mermaid
flowchart LR
  UI["Frontend (React 19 + TS + Tailwind)<br/>Dashboard · Workspace · Pre-flight · Stale detector<br/>Evidence explorer · Token analytics · History · Settings"]
  API["FastAPI api.py<br/>token→session + CSRF, Host allowlist"]
  UI -- REST --> API
  subgraph T1["Track 1 — Stale-Answer Detector"]
    C[claims.py / claim_parse.py]
    S[stale.py]
    A[source_authority.py]
    LE[local_evidence.py]
  end
  subgraph T2["Track 2 — Pre-Flight Gatekeeper + coding agent"]
    R[repo_intel.py]
    K[skeleton.py planner]
    V[verify_api.py]
    PI[pyinspect.py AST]
    JI[jsinspect.py + tools/ts-checker TS compiler API]
    AG[agent.py briefing · coder · repair]
    SB[security.py sandbox]
  end
  API --> T1
  API --> T2
  subgraph SH["Shared"]
    L["llm.py<br/>OpenAI-compatible (Groq, LIVE) · Anthropic (MOCK-tested) · mock"]
    TV["tavily.py search + extract"]
    DB[("db.py SQLite<br/>tasks · token_usage · analyses · claims · evidence · benchmarks")]
    TA["token accounting<br/>ACTUAL_PROVIDER_USAGE / ESTIMATED / MOCK"]
  end
  S --> TV
  S --> L
  V --> TV
  K --> L
  AG --> L
  L --> TA --> DB
  S --> DB
  AG --> DB
  LE --> PI
  LE --> JI
  S --> LE
```

## Track 1 workflow

```mermaid
flowchart TD
  IN[LLM answer] --> EX["Claim extraction<br/>atomic claims with character spans<br/>negation · hedging · conditionals · hypotheticals"]
  EX --> CL["Classification<br/>category · volatility · temporal sensitivity · verifiability"]
  CL -->|not time-sensitive / opinion / incomplete| NA[NOT_APPLICABLE or UNVERIFIED, no search]
  CL -->|volatile & verifiable| RET["Evidence retrieval<br/>Tavily search + extract · user URLs<br/>installed packages for library claims"]
  RET --> REL[Relevance gate]
  REL --> AUTH["Source authority<br/>primary · secondary · unknown · suspicious"]
  AUTH --> VER["Verification<br/>value comparison (negation-aware) → lexical → LLM judge with verbatim-quote check"]
  VER --> SUF["Evidence sufficiency<br/>weak sources never contradict · lexical never overrides stronger evidence<br/>version monotonicity · undated never overrides dated"]
  SUF --> ST["Status + evidence freshness + verification confidence<br/>CURRENT_SUPPORTED · POTENTIALLY_STALE · CONTRADICTED<br/>UNVERIFIED · CONFLICTING_EVIDENCE · NOT_APPLICABLE"]
  ST --> CO["Corrected answer<br/>cited; never invents a fix"]
  ST --> DB[(Persisted analysis + evidence)]
```

## Track 2 workflow

```mermaid
flowchart TD
  REPO[Repository] --> DEP["Dependency inspection<br/>manifests · lockfiles · exact installed versions"]
  DEP --> PL["Planner (LLM, strict JSON)<br/>API skeleton: packages + planned APIs + arguments"]
  PL --> VF["Installed-package verification<br/>Python: AST over site-packages<br/>TS/JS: TypeScript compiler API over node_modules<br/>exports · namespace members · chained calls · signatures · @deprecated · call type-check"]
  VF -->|uncertain only| DOC[Tavily documentation fallback]
  DOC --> VF
  VF --> BR["Correction briefing<br/>only problems + one line of verified APIs"]
  BR --> CD["Coding model<br/>relevant files + conventions only"]
  CD --> SB["Sandbox copy<br/>Docker --network none, read-only rootfs<br/>(labelled process fallback)"]
  SB --> TS["Allowlisted checks<br/>pytest · vitest · tsc · lint"]
  TS -->|fail, within budget| RP["Bounded repair<br/>failure digest + changed files only"]
  RP --> SB
  TS -->|pass or budget spent| OUT["Final output<br/>diff · test results · API corrections · tokens by stage"]
  OUT --> DB[(Persisted task + token usage)]
```

## Combined workflow (why one product)
Track 2's installed-package verifiers are also evidence sources for Track 1. A claim such as "use `@validator` in
Pydantic" is checked against the pydantic version actually installed in the workspace (Demo E), not only against the
web.
