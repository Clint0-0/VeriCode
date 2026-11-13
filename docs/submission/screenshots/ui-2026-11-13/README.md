# UI screenshots (2026-11-13, professional UI redesign)

Captured with Playwright against the real FastAPI backend on a fresh database. The data was created through the
normal API with the **scripted MOCK provider** and **offline FIXTURE evidence** (no API keys), so coding runs,
pre-flight findings and token counts on these screens are MOCK/ESTIMATED — the UI labels them so. The Token
Analytics "Published: 2026-11-13" view shows the committed ACTUAL_PROVIDER_USAGE benchmark summary
(`docs/submission/benchmark-results/2026-11-13`).

| File | Screen |
|---|---|
| 1-dashboard.png | Dashboard |
| 2-workspace.png | Coding Workspace (task form + repository panel) |
| 2b-task-result.png | A finished coding task (diff, validation, run timeline, audit) |
| 3-preflight.png | Pre-Flight Inspector with a run and an expanded finding |
| 4-stale.png | Stale-Answer Detector, claim expanded |
| 5-evidence.png | Evidence Explorer, source expanded |
| 6-tokens.png | Token Analytics |
| 7-history.png | Task History |
| 8-settings.png | Settings |
| m*-mobile.png, t*-tablet.png | 390 px phone and 820 px tablet layouts |

Desktop 1440×900 (full page), phone 390×844, tablet 820×1100. Every capture had 0 px horizontal overflow and no
console errors.
