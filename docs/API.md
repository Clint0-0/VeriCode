# API reference (implemented)

Base URL `http://127.0.0.1:8000/api`. Interactive schema: `/docs` (FastAPI OpenAPI). Request bodies over
256 KB → 413. Workspace paths are relative to `VERICODE_WORKSPACES` (default `./demos`); anything outside → 400.

Authentication: open the login URL printed by the server (`/?token=…`), or call `POST /api/auth/login {token}`.
That sets an HttpOnly session cookie and returns `csrf`. Send `X-CSRF-Token: <csrf>` on every non-GET request.
Scripts can instead send `Authorization: Bearer <token>` (no CSRF needed). Unauthenticated → 401 `{"code":"auth"}`.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/auth/login` · GET `/auth/status` · POST `/auth/logout` | `{token}` | session cookie + `{csrf}` |
| GET | `/integrations` | – | LLM provider status (ready, missing env vars, models), Tavily, sandbox (configured/active/docker), TS checker, auth, schema version |
| GET | `/health` | – | provider, tavily_configured, network_isolation |
| GET/PUT | `/settings` | PUT: editable runtime fields (models, provider, limits, half_lives, costs). Keys are rejected (400). | public settings with key *presence* flags only |
| GET | `/workspaces` | – | workspaces under the root |
| POST | `/projects/inspect` | `{path}` | ProjectEnvironment (languages, frameworks, manifests, dependencies with declared/resolved/installed/status, files, test_commands, warnings, fingerprint) |
| POST | `/projects/select-files` | `{path, task}` | `{files:[{path, score, reasons, is_test}]}` |
| POST | `/preflight` | `{path, task, live}` | skeleton, skeleton_errors, findings[], briefing, tokens, tavily_calls, rules_saved, task_id |
| POST | `/verify-api` | `{path, package, ecosystem, import_path, name, type, arguments[], assumed_version?, live}` | one APIFinding (no LLM) |
| GET | `/catalog` | – | bundled demo tasks |
| POST | `/tasks` | `{path?, prompt?, mode: vericode|baseline, max_repairs?, live, catalog_id?}` | `{task_id}` (runs asynchronously); 503 `llm_unavailable` if no provider |
| GET | `/tasks` | `limit` | task summaries |
| GET | `/tasks/{id}` | – | status, events, preflight, result (attempts, checks, diff, tokens, changed_files, sandbox) |
| POST | `/tasks/{id}/apply` | – | copies validated changes into the workspace. 409 if the run was not successful, or `{"code":"conflict","conflicts":[{path,state,user_diff}]}` if files changed since the run |
| POST | `/stale/analyze` | `{answer, question?, urls[≤5], preferred_domains[≤10], mode: live|fixture, llm_extraction?}` | `{id, summary, claims:[{claim{claim_id, claim, span, source_text, category, volatility, temporal_sensitivity, verifiability, evidence_type, negated, conditional, values, extraction}, status, freshness, freshness_note, confidence, confidence_breakdown, explanation, evidence[], correction, missing_evidence, conflict{supporting[], contradicting[], reason}, judge, query, search_status}]}`; summary includes `extraction`, `llm_judge`, `search_credits`, `llm_tokens` |
| GET | `/stale` / `/stale/{id}` | – | list / stored analysis |
| GET | `/stale/demo` | – | Demo 2 fixture (answer + labelled sources) |
| POST | `/stale/{id}/correct` | – | `{original, corrected, changes[], citations[], policy}` |
| GET | `/evidence` | `analysis_id?` | evidence records joined with claim + status |
| GET | `/analytics/tokens` | – | by_stage, by_mode, **by_measurement**, per_task (with measurement label), Tavily `search` usage (requests, cache hits, credits, failures), cost config |
| POST/GET | `/benchmarks` | POST `{task_ids[], runs≤5, max_repairs?, live}` (async) | GET: `{running, error, results[]}` |
| GET | `/dashboard` | – | aggregate counts from stored data only |
| GET | `/rules` · PUT/DELETE `/rules/{id}` · POST `/rules/export {path}` | – | project memory CRUD + export |

APIFinding fields: `package, ecosystem, planned_api, api_type, arguments, installed_version, assumed_version,
status, api_compatibility, verification_confidence, evidence_freshness, risk_score, risk_factors[],
explanation, suggested_correction, verification_method[], local{location, params, deprecated,
rejected_kwargs, migration_hint, resolution_path}, argument_checks[], live{status, query, domains, sources[]}, memory_rule`.

Evidence record fields: `claim_id, original_claim, title, url, domain, source_type, authority, retrieved_at,
published_date, excerpt, relevance, relevance_explanation, outcome (support|contradict|neutral|irrelevant),
origin (live_tavily|user_url|fixture|fixture_synthetic), method (value|lexical|llm_judge|none), freshness, age_days, replacement`.
Task results include `outcome` (succeeded | partial | failed), `backend` (docker | process), checks with `kind` (test | quality) and `required`.
