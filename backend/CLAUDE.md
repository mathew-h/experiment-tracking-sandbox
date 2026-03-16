# Backend Context

## Must Read Before Any Backend Task
- `docs/LOCKED_COMPONENTS.md` — what cannot be modified
- `docs/CODE_STANDARDS.md` — Python standards and patterns
- The active milestone file from `docs/milestones/`

## Skills to Load
- For schema/migration work: read `.claude/skills/db-architect.md`
- For API/service work: read `.claude/skills/api-developer.md`

## Key Rules (Non-Negotiable)
- No business logic inside `database/models/` files — models are storage only
- All derived fields are written at create/update time by the calculation engine
- Never modify bulk upload parsers in `backend/services/bulk_uploads/` without explicit user instruction
- All endpoints call `registry.get_affected_fields()` after every write
- Use `structlog` — never `print()` or `logging.basicConfig()`

## Calculation Engine
All formula modules live in `backend/services/calculations/`.
Read `docs/CALCULATIONS.md` before touching any derived field logic.
