# Skill: db-architect

## When Claude Loads This Skill
Load this file when the task involves: database schema changes, Alembic migrations,
PostgreSQL queries, the calculation engine trigger registry, or any model file in
`database/models/`.

## Role Definition
- Handles all database schema changes, Alembic migrations, PostgreSQL queries
- Owns the calculation engine trigger registry (`backend/services/calculations/registry.py`)
- Produces: migration files, updated `docs/SCHEMA.md`, model integrity tests
- Triggered: any time a schema change, migration, or calculation trigger rule is needed
- Must read `docs/SCHEMA.md` and `MODELS.md` before any action

## Must Read Before Acting
- `MODELS.md` — locked schema reference
- `docs/SCHEMA.md` — PostgreSQL-specific notes
- `docs/CALCULATIONS.md` — derived field rules
- `docs/LOCKED_COMPONENTS.md` — full locked models table and constraints

## Key Constraints
- Models are storage-only — no `@property` or `hybrid_property` for calculated fields
- All derived fields are written at create/update time by the calculation engine
- Never delete, rewrite, or squash existing Alembic migration files — all migrations must be additive
- Every migration file must implement both `upgrade` and `downgrade`
- JSON fields in `ICPResults` (`all_elements`, `detection_limits`) and `XRDAnalysis` (`mineral_phases`) become `JSONB` in PostgreSQL — do not flatten without explicit user instruction
- All enums in `enums.py` are locked — changing them breaks existing data

## Escalation
Stop and ask the user if:
- A schema change affects more than one model
- A migration cannot be written as purely additive (requires dropping or renaming a column)
