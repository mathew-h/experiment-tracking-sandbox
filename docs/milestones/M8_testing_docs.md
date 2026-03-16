# Milestone 8: Full System Testing and Documentation Pass

**Owner:** Test Writer Agent (primary), Documentation Agent (primary)
**Branch:** `feature/m8-testing-docs`

**E2E user journeys:**
1. Login → create experiment → add conditions → add chemical additives → verify derived fields on detail page
2. Login → bulk upload new experiments → verify all appear in list
3. Login → upload ICP CSV → verify data links to correct experiment and timepoint
4. Login → update experiment status → verify dashboard reflects change within one refresh cycle
5. Login → upload XRD report → verify mineral phases in Analysis tab
6. Login → edit `rock_mass_g` on existing experiment → verify `water_to_rock_ratio` recalculated in DB

**Additional tests:** Load test (5 concurrent users, simultaneous uploads); calculation regression test (all derived fields for known dataset match expected values); backup/restore test; fresh-install migration test.

**Documentation tasks:** Audit all FastAPI docstrings and React JSDoc; final `README.md` rewrite; complete user manual; `CONTRIBUTING.md`; `PRODUCTION_DEPLOYMENT.md`; final `CALCULATIONS.md` and `FIELD_MAPPING.md` audits.

**Acceptance criteria:** All 6 E2E journeys pass; calculation regression test passes; load test clean at 5 concurrent users; all documentation accurate; `README.md` works on a clean machine.
