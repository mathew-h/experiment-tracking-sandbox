# Architectural decisions

Append-only lasting decisions from milestone, issue, or inline work (newest at bottom). Summaries may also appear in `docs/working/plan.md` for milestone tasks; this file holds the durable record.

## 2026-03-24 — Shared write helper for ElementalAnalysis; explicit overwrite contract

**Decision:** Both `ElementalCompositionService` and `ActlabsRockTitrationService` delegate all `ElementalAnalysis` writes to the single module-level function `_write_elemental_record(db, ext_analysis_id, sample_id, analyte, value, overwrite)` in `actlabs_titration_data.py`.

**Contract:**
- `overwrite=False` (default): INSERT if no record exists; SKIP if record already exists
- `overwrite=True`: INSERT if no record exists; UPDATE if record already exists
- Null/blank values must never be passed to this function (callers skip nulls before calling)

**Why:** The two services previously duplicated identical `if existing → update / else → create` blocks with no user-controllable behavior. This created an implicit always-overwrite contract that was unsafe for partial re-uploads. The new default (`overwrite=False`) is the safe choice for first-time and incremental uploads; `overwrite=True` is reserved for deliberate data correction.

**Scope:** Any future parser that writes to `ElementalAnalysis` must use `_write_elemental_record` — do not inline a new upsert block.

## 2026-07-09 — `alembic/` is the sole migration history; `database/migrations/` removed

**Decision:** Deleted `database/migrations/` (a second, independently-scaffolded Alembic environment with 48 frozen files). `alembic/` at repo root — the one `alembic.ini`'s active `script_location` actually points to — is the only migration history.

**Why:** `database/migrations/` was added in the same initial commit as `alembic/` (2026-03-16) and never touched again; every subsequent migration (69 files, through 2026-06-16) landed only in `alembic/`. Nothing in the codebase imported or referenced `database/migrations`. It was dead scaffolding from an early duplicate `alembic init`, not a divergent second chain.

**Scope:** Do not create a second Alembic environment anywhere in this repo. All new migrations go in `alembic/versions/` via `alembic revision --autogenerate`.

## 2026-07-09 — Docker dev workflow deprecated; native venv + npm is the only supported local dev path

**Decision:** Local development runs natively (Python venv + `npm run dev`), matching production (Windows Service via NSSM, no Docker). `Dockerfile` / `docker-compose.yml` / `scripts/dev-entrypoint.sh` still exist in the repo but are no longer the documented or supported dev workflow; `README_DEV_SETUP.md` (the Docker Compose guide) was deleted.

**Why:** `docs/deployment/STARTUP_GUIDE.md` and `docs/deployment/PRODUCTION_DEPLOYMENT.md` — the actively-maintained deployment docs — describe only the native NSSM/venv path, and `README.md`'s Quick Start already dropped Docker. `docs/ENVIRONMENT.md` still claimed "Docker Compose is used for local development only," contradicting both.

**Scope:** Don't resurrect the Docker dev guide or point new contributors at `docker-compose up` without raising it with the user first — the lab-PC deployment model (single Windows host, NSSM services) is the one all setup docs should describe.

## 2026-07-09 — `auth/` module split: `user_management.py` is shared, `firebase_config.py` is legacy-only

**Decision:** `auth/user_management.py` (root) remains the single shared implementation of the Firestore `pending_users` approval queue and Firebase Auth user CRUD — used by both `backend/api/routers/auth.py` (`POST /api/auth/register`) and `scripts/manage_users.py` (admin CLI). `auth/firebase_config.py` (root, imports `streamlit`) is legacy-only, used solely by `legacy/streamlit_frontend/auth_components.py`. New backend code initializes Firebase Admin via `backend/auth/firebase_auth.py`, not `auth/firebase_config.py`.

**Why:** The React/FastAPI rewrite moved login itself to the Firebase Web SDK client-side and moved token verification to `backend/auth/firebase_auth.py`, but never touched the registration/approval plumbing — that logic was reused as-is from the Streamlit era. This left one module (`user_management.py`) genuinely live in both stacks and one (`firebase_config.py`) orphaned to the legacy stack only, which `.claude/rules/AUTH.md` didn't reflect until this pass.

**Scope:** Do not import `auth/firebase_config.py` from new backend or frontend code. If `role`/`approved` custom claims (set at approval time but not currently read anywhere) are wired into an access-control decision, update `.claude/rules/AUTH.md` to document where that check lives.
