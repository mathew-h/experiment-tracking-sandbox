# Milestone 3: FastAPI Backend

**Owner:** api-developer (primary)
**Branch:** `feature/m3-fastapi-backend`

**Objective:** Build the complete API layer. All business logic lives here. The React app never touches the database directly.

**Routers:**

| Router | Key Endpoints |
|---|---|
| `experiments.py` | GET list (filterable), GET detail, POST create, PATCH update, DELETE |
| `conditions.py` | GET, POST, PATCH |
| `results.py` | GET by experiment + timepoint, POST scalar, POST ICP |
| `samples.py` | GET list, GET detail, POST, PATCH |
| `chemicals.py` | GET compounds, POST compound, GET additives by experiment |
| `analysis.py` | GET XRD by experiment, GET pXRF by sample, GET elemental |
| `dashboard.py` | GET reactor status summary (single call, no N+1), GET experiment timeline |
| `bulk_uploads.py` | POST per upload type — wraps existing parsers |
| `admin.py` | Recalculation endpoints from Milestone 2 |

Every write endpoint calls the calculation engine after the DB write. Use `registry.get_affected_fields()` to determine which calculations to run.

**FastAPI serves the built React app** as static files from `frontend/dist/`. All non-API routes return `index.html`.

**Acceptance criteria:** All endpoints return correct data; Firebase auth rejects invalid tokens; `/api/docs` complete; write endpoints trigger correct recalculations; bulk uploads process test fixture files successfully.

**Test Writer Agent:** Unit tests per endpoint (happy path + errors), auth tests, bulk upload tests, calculation integration tests.

**Documentation Agent:** `docs/api/API_REFERENCE.md`, developer guide for adding endpoints.
