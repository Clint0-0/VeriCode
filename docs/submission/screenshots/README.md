# Screenshots

Captured from the real application (`scripts/run.sh` build) on 2026-11-08 with **offline data**: Track 1 uses the
labelled fixture `demos/stale_fixtures/demo2.json` (FIXTURE), and Track 2 uses the scripted mock provider (MOCK).
The app shows these labels on screen itself ("Evidence below comes from the offline fixture", "Scripted mock
provider"). They are not live results. Live results are documented in [../../LIVE_VALIDATION.md](../../LIVE_VALIDATION.md)
and were checked in the browser by `backend/tests/test_e2e_live.py` in GitHub Actions.

| File | Screen | Data |
|---|---|---|
| `01-dashboard-offline-mock.png` | Dashboard | MOCK |
| `02-stale-detector-offline-fixture.png` | Stale-Answer Detector (claims, spans, statuses, freshness vs confidence) | FIXTURE |
| `03-evidence-explorer-offline-fixture.png` | Evidence Explorer | FIXTURE |
| `04-task-preflight-heatmap-offline-mock.png` | Task detail: pre-flight report and heatmap against installed pydantic 2.9.2 | MOCK planner, real installed-source verification |
| `05-token-analytics-offline-mock.png` | Token Analytics | MOCK |
