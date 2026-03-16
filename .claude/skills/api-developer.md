# Skill: api-developer

## When Claude Loads This Skill
Load this file when the task involves: FastAPI routers, Pydantic schemas,
calculation engine formula modules, bulk upload service wrappers, or any
file under `backend/api/` or `backend/services/`.

## Role Definition
- Builds FastAPI routers, Pydantic schemas, calculation engine formula modules, bulk upload service wrappers
- Produces: router files, schema files, calculation formula modules, endpoint tests
- Triggered: any time a new endpoint, schema, or service function is needed
- Coverage target: 80% minimum on all new backend code

## Must Read Before Acting
- `docs/CODE_STANDARDS.md` — Python standards and endpoint patterns
- `docs/CALCULATIONS.md` — derived field formulas and trigger rules
- The active milestone file from `docs/milestones/`

## Key Constraints
- Every write endpoint must call the calculation engine after the DB write using `registry.get_affected_fields()`
- All formula functions: accept only primitive inputs (no ORM objects), return `None` on null inputs (log WARNING), are pure and side-effect-free, have full docstrings with units and formula notation
- Use `structlog` — never `print()` or `logging.basicConfig()`
- Use `pydantic-settings` — never `os.environ.get()` with hardcoded fallbacks
- No business logic inside model files — models are storage definitions only
- FastAPI serves the built React app as static files from `frontend/dist/`; all non-API routes return `index.html`

## Bulk Upload Parsers
Existing parsers in `backend/services/bulk_uploads/` are locked. The task is to wrap them in FastAPI endpoints, not replace them. Do not modify parsing logic without explicit user instruction.

## Context7 Usage
Add `use context7` to any prompt involving: FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, structlog.
