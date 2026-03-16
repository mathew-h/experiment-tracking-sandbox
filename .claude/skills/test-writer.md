# Skill: test-writer

## When Claude Loads This Skill
Load this file when the task involves: writing tests, reviewing coverage,
running pytest or vitest, or completing the post-feature test pass.

## Role Definition
- Generates automated tests for every new feature and code change
- Produces: test plan document + implemented test files
- Triggered: after every feature branch is complete, before any merge
- Coverage target: 80% minimum on all new code
- Tools: pytest + pytest-asyncio (backend), Vitest + React Testing Library (frontend)

## Testing Standards
- Backend: pytest, pytest-asyncio, httpx `TestClient`; frontend: Vitest, React Testing Library, MSW
- Test file location mirrors source structure
- Every test is independent — no shared mutable state
- Fixtures for DB setup/teardown — never use production DB in tests
- Calculation engine tests: every formula must have a test with known numeric inputs/outputs taken from existing Streamlit-computed values

## Playwright E2E Tests
Use Playwright MCP for all Milestone 8 user journey tests and for repeatable test scenarios.

| Test type | Milestone |
|---|---|
| Component smoke tests (login, protected routes) | Milestone 4 |
| Experiment creation round-trip | Milestone 5 |
| Bulk upload file drag-and-drop flow | Milestone 6 |
| Dashboard auto-refresh and filter combinations | Milestone 7 |
| All 6 E2E user journeys | Milestone 8 |

## E2E User Journeys (Milestone 8)
1. Login → create experiment → add conditions → add chemical additives → verify derived fields on detail page
2. Login → bulk upload new experiments → verify all appear in list
3. Login → upload ICP CSV → verify data links to correct experiment and timepoint
4. Login → update experiment status → verify dashboard reflects change within one refresh cycle
5. Login → upload XRD report → verify mineral phases in Analysis tab
6. Login → edit `rock_mass_g` on existing experiment → verify `water_to_rock_ratio` recalculated in DB
