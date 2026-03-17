# Project Working Memory

## Current Status
**Active Milestone:** M3 — FastAPI Backend
**Branch:** `feature/m3-fastapi-backend`
**Last Updated:** 2026-03-16

---

## M0 — Infrastructure Setup: COMPLETE

### What Was Done
- Configured GitHub remote: `https://github.com/mathew-h/experiment-tracking-sandbox.git`
- PAT authentication via `GITHUB_PAT` Windows env var; `GITHUB_PERSONAL_ACCESS_TOKEN` needed separately for GitHub MCP plugin
- PostgreSQL 18 installed on dev PC at `C:\Program Files\PostgreSQL\18`
- Created `experiments` database and `experiments_user` with password `password`
- Updated `.env` `DATABASE_URL` from SQLite to `postgresql://experiments_user:password@localhost:5432/experiments`
- Created `.venv` and installed all requirements from `requirements.txt`
- Created all tables via `Base.metadata.create_all()` (initial Alembic migration was empty — written against existing SQLite DB)
- Stamped Alembic at `head` (`4efd20d110e8`)
- FastAPI skeleton confirmed running: `GET /health → {"status":"ok","service":"experiment_tracking_api"}`

### Decisions Made
- **SQLite→PostgreSQL bootstrap pattern:** Initial migration chain was written against an existing SQLite DB (the `b1fc58c4119d` initial migration is empty). On a fresh PostgreSQL DB, use `Base.metadata.create_all()` + `alembic stamp head` rather than running the migration chain. This is the standard approach for bootstrapping.
- **Deployment deferred to lab PC phase:** `scripts/install_services.bat`, `scripts/deploy.bat`, `scripts/backup.bat`, and `docs/deployment/LAB_PC_SETUP.md` are not yet written. These will be addressed when setting up the lab PC. NSSM not yet installed.
- **Running on dev PC for now:** User will use their personal PC as the application host until lab PC setup is revisited.

### Deferred M0 Items (lab PC phase)
- [ ] `scripts/install_services.bat` — idempotent setup (PostgreSQL service, NSSM, firewall)
- [ ] `scripts/deploy.bat` — replaces `auto_update.bat`
- [ ] `scripts/backup.bat` — pg_dump with 30-day retention + Power BI dump
- [ ] `docs/deployment/LAB_PC_SETUP.md`
- [ ] NSSM install + uvicorn Windows service registration

### Known Pre-existing Test Issues (not M0-related)
- `tests/test_icp_service.py` — calls `sys.exit(1)` on import; legacy broken file
- `tests/test_time_field_guardrails.py` and others — import `frontend.config.variable_config` which doesn't exist until M4
- These will be addressed in M8 (Testing and Docs)

---

## M1 — PostgreSQL Migration: COMPLETE

### Objective
Migrate existing SQLite data (`docs/sample_data/experiments.db`) to PostgreSQL with full integrity verification.

### What Was Done
- Integrated Alembic with PostgreSQL
- Migrated all schema and data to PostgreSQL
- Created M1 milestone documentation

---

## M2 — Calculation Engine: COMPLETE

### Objective
Extract all derived-field calculation logic from SQLAlchemy model methods into `backend/services/calculations/`.

### Branch
`feature/m2-calculation-engine` — cut from `feature/m1-postgres-migration`

### What Was Done
- Registry pattern: `backend/services/calculations/registry.py` — dispatch dict + `recalculate(instance, session)`
- `conditions_calcs.py` — water_to_rock_ratio
- `additive_calcs.py` — unit conversions, moles, concentration, catalyst fields, format_additives()
- `scalar_calcs.py` — H2 PV=nRT at 20°C, ammonium yield, h2_grams_per_ton_yield
- Deleted calculation methods from `chemicals.py`, `conditions.py`, `results.py` (models now pure storage)
- 29 unit tests passing, no DB required
- `docs/CALCULATIONS.md` created

### Decisions Made
- **Clean break:** Model calculation methods deleted (not wrapped). No dead code.
- **Simple registry:** dispatch dict keyed on `type(instance)` — exact type match, no subclass matching.
- **Background default:** 0.3 mM default for background_ammonium_concentration_mM when not set.

### Sign-off
- [x] User sign-off received 2026-03-16 — proceed to M3

---

## M3 — FastAPI Backend: IN PROGRESS

### Objective
Build the complete API layer. All business logic lives here. The React app never touches the database directly.

### Branch
`feature/m3-fastapi-backend` — cut from `infra/lab-pc-server-setup` (after M2 merge)

### Implementation Plan
`docs/superpowers/plans/2026-03-16-m3-fastapi-backend.md` — 18 tasks, 6 chunks. **Read this before starting any M3 work.**

### Key Decisions Made
- **Firebase auth:** `auth/firebase_config.py` imports `streamlit` at module load — cannot be imported from FastAPI. `backend/auth/firebase_auth.py` initializes Firebase Admin SDK directly via `pydantic-settings`. Never import `auth.firebase_config` from the backend.
- **Calc engine API:** `docs/CODE_STANDARDS.md` example snippet uses `get_affected_fields()`/`calculation_service.run()` — these do **not exist**. Actual API is `registry.recalculate(instance, session)` from `backend/services/calculations/registry.py`.
- **Bulk upload parsers are locked:** `backend/services/bulk_uploads/` must not be modified. M3 wraps them only.
- **Route order matters:** In `results.py`, static routes (`/scalar/`, `/icp/`) must be registered before `/{experiment_id}` to avoid path shadowing.
- **Test DB:** Use `experiments_test` PostgreSQL DB. Create once: `psql -U postgres -c "CREATE DATABASE experiments_test OWNER experiments_user;"`. Tests use rollback fixtures, not mocks.

### Completed
- [x] Chunk 1: Settings, `get_db`, Firebase auth, test conftest (Tasks 1–4) — 2026-03-16
  - `backend/config/settings.py` — pydantic-settings, CORS list, Firebase cred dict
  - `backend/api/dependencies/db.py` — module-level engine + `get_db` generator
  - `backend/auth/firebase_auth.py` — `FirebaseUser`, `_decode_token`, `verify_firebase_token`
  - `tests/api/conftest.py` — test DB session, client fixture, auth override
  - `httpx==0.28.1` added to `requirements.txt` (required by FastAPI TestClient)
  - `experiments_test` DB created (postgres superuser password: "password")
- [x] Chunk 2: All Pydantic schemas (Tasks 5–7) — 2026-03-16
  - experiments.py, conditions.py, results.py, chemicals.py, samples.py, analysis.py, dashboard.py, bulk_upload.py + __init__.py
  - 5 schema tests passing
- [x] Chunk 3: Read routers — experiments, samples, chemicals, analysis (Tasks 8–11) — 2026-03-16
  - experiments.py: GET /api/experiments (list + filters), GET /api/experiments/{id}
  - samples.py: GET/POST /api/samples, GET/PATCH /api/samples/{id}
  - chemicals.py: GET/POST /api/chemicals/compounds, GET /api/chemicals/compounds/{id}, GET/POST /api/chemicals/additives/{conditions_id}
  - analysis.py: GET /api/analysis/xrd/{experiment_id}, GET /api/analysis/pxrf, GET /api/analysis/external/{experiment_id}
  - 15 tests passing

### Pending
- [ ] Chunk 4: Write routers — experiments write, conditions, results (Tasks 12–13)
- [ ] Chunk 5: Dashboard, admin, bulk uploads, wire main.py (Tasks 14–17)
- [ ] Chunk 6: `docs/api/API_REFERENCE.md` + final verification (Task 18)

---

## Context Restructure (completed 2026-03-16)
The original CLAUDE.md was refactored into a hierarchical context system (27 files). All content preserved. See previous plan entries for details.
