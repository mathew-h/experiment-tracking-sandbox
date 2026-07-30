# Database Context

## Must Read Before Any Database Task
- `MODELS.md` — locked schema reference
- `docs/SCHEMA.md` — PostgreSQL-specific notes and migration history
- `docs/LOCKED_COMPONENTS.md` — complete locked models table

## Quick Commands

```bash
# Create a new migration (use venv prefix — bare 'alembic' not on PATH)
.venv/Scripts/alembic revision --autogenerate -m "descriptive message"

# Apply migrations
.venv/Scripts/alembic upgrade head

# Test downgrade (always verify before merging)
.venv/Scripts/alembic downgrade -1 && .venv/Scripts/alembic upgrade head

# Fresh DB bootstrap (use instead of migration chain on a new PostgreSQL DB)
.venv/Scripts/python -c "from database import Base, engine; Base.metadata.create_all(engine)"
.venv/Scripts/alembic stamp head

# After loading a new experiments.db via migrate-sqlite-to-postgres.py, always follow with:
.venv/Scripts/alembic upgrade head   # applies additive columns added since last migration
```

**Warning — `alembic upgrade head` does NOT backfill `reactor_slot` after this loader runs.**
`scripts/migrate-sqlite-to-postgres.py` builds its `INSERT INTO "{table}" (...)` statements
and executes them as raw Core `INSERT`s via `conn.execute(text(sql), values)`. That bypasses
the ORM entirely, so no mapper events fire — every migrated `experimental_conditions` row
lands with `reactor_slot = NULL`. Running `alembic upgrade head` afterward is a no-op for
this: the DB is already stamped at `1c1ef9b555e0` (the migration that added and backfilled
`reactor_slot`), so that migration does not re-run. Consequences, all silent: the reactor
grid renders empty (`dashboard.py:119` filters `reactor_slot IS NOT NULL`), every occupancy
demotion no-ops (`experiment_status.py:407-410` returns `(0, [])`), the `PATCH /status` 409
gate never fires, and the Notion export clears every reactor page to idle. **The slot column
must be backfilled manually before the app is trusted after a fresh load** — re-execute the
`BACKFILL` statement from `alembic/versions/1c1ef9b555e0_add_reactor_slot_to_conditions.py`.

## Connection Strings
Dev DB: `postgresql://experiments_user:password@localhost:5432/experiments`
Test DB: `postgresql://experiments_user:password@localhost:5432/experiments_test`

Create test DB once: `psql -U postgres -c "CREATE DATABASE experiments_test OWNER experiments_user;"`

## Key Rules (Non-Negotiable)
- Never delete, rewrite, or squash existing Alembic migration files
- All migrations must be additive
- Every migration file must implement both `upgrade` and `downgrade`
- JSON fields in ICPResults and XRDAnalysis become JSONB in PostgreSQL — do not flatten them
- Models are storage definitions only — no @property or hybrid_property for calculated fields

## Schema Change Escalation
If a change affects more than one model, stop and ask the user before proceeding.
If a migration cannot be written as purely additive, stop and ask the user.
