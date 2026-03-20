# Backend Context

## Must Read Before Any Backend Task
- `docs/LOCKED_COMPONENTS.md` — what cannot be modified
- `docs/CODE_STANDARDS.md` — Python standards and patterns
- The active milestone file from `docs/milestones/`

## Skills to Load
- For schema/migration work: read `.claude/skills/db-architect.md`
- For API/service work: read `.claude/skills/api-developer.md`

## Quick Commands

```bash
# Start the API server (from project root — use venv prefix)
.venv/Scripts/uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# Run backend tests
pytest tests/services/ -v

# Run calculation engine tests only
pytest tests/services/calculations/ -v

# Run API tests (M3+)
pytest tests/api/ -v
```

## Key Rules (Non-Negotiable)
- No business logic inside `database/models/` files — models are storage only
- All derived fields are written at create/update time by the calculation engine
- Never modify bulk upload parsers in `backend/services/bulk_uploads/` without explicit user instruction
- All write endpoints call `registry.recalculate(instance, session)` after every write (never `get_affected_fields` — does not exist)
- Use `structlog` — never `print()` or `logging.basicConfig()`
- Use `pydantic-settings` for all config — never `os.environ.get()` with hardcoded fallbacks

## Calculation Engine
All formula modules live in `backend/services/calculations/`.
Read `docs/CALCULATIONS.md` before touching any derived field logic.

## M3 Firebase Rule
`backend/auth/firebase_auth.py` initializes Firebase Admin SDK directly.
Never import `auth.firebase_config` from backend code — it imports `streamlit` at load time and crashes the API.

## M3 Bulk Upload Constraint (Learned)
`backend/services/bulk_uploads/scalar_results.py` and `pxrf_data.py` import `frontend.config.variable_config`
at module load time. This module does not exist until M4 (React frontend build).
**Always use lazy imports** (inside endpoint functions) when wrapping these parsers in the API.
Tests that exercise these endpoints must use `sys.modules` patching to stub `frontend.config.variable_config`.

## Server Management (Non-Negotiable)
Never start, stop, or restart the uvicorn server. Assume it is already running
on port 8000. If an endpoint is unreachable, report the error to the user --
do not attempt to restart the process.

## API Reference
Full endpoint reference: `docs/api/API_REFERENCE.md`
Interactive docs when server is running: `http://localhost:8000/docs`
