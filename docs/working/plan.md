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
`feature/m3-fastapi-backend` — cut from `feature/m2-calculation-engine` (via `infra/lab-pc-server-setup`)

### Pending
- [ ] Write M3 implementation plan
- [ ] Build dependencies (`get_db`, `verify_firebase_token`)
- [ ] Build Pydantic schemas for all entities
- [ ] Implement 9 routers: experiments, conditions, results, samples, chemicals, analysis, dashboard, bulk_uploads, admin
- [ ] Wire calculation engine on all write endpoints
- [ ] Tests per endpoint
- [ ] `docs/api/API_REFERENCE.md`

---

## Context Restructure (completed 2026-03-16)
The original CLAUDE.md was refactored into a hierarchical context system (27 files). All content preserved. See previous plan entries for details.
