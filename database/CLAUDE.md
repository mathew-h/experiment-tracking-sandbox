# Database Context

## Must Read Before Any Database Task
- `MODELS.md` — locked schema reference
- `docs/SCHEMA.md` — PostgreSQL-specific notes and migration history
- `docs/LOCKED_COMPONENTS.md` — complete locked models table

## Key Rules (Non-Negotiable)
- Never delete, rewrite, or squash existing Alembic migration files
- All migrations must be additive
- Every migration file must implement both `upgrade` and `downgrade`
- JSON fields in ICPResults and XRDAnalysis become JSONB in PostgreSQL — do not flatten them
- Models are storage definitions only — no @property or hybrid_property for calculated fields

## Schema Change Escalation
If a change affects more than one model, stop and ask the user before proceeding.
If a migration cannot be written as purely additive, stop and ask the user.
