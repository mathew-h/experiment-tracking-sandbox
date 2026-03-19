# Milestone 1: Database Migration — SQLite to PostgreSQL

**Owner:** db-architect (primary), Test Writer Agent
**Branch:** `feature/m1-postgres-migration`

**Objective:** Migrate all data and schema from SQLite to PostgreSQL with zero data loss.

**Tasks:**
1. Audit all models for SQLite-specific patterns (`Boolean` as Integer, `JSON` → `JSONB`, `AUTOINCREMENT` → `SERIAL`/`IDENTITY`)
2. Update `database/models/` for database-agnostic SQLAlchemy types. **No calculated field logic added here.**
3. Write Alembic migration — two-phase: schema first, then data copy via SQLAlchemy Core
4. Update `database/connection.py` to use `DATABASE_URL` env var
5. Update `requirements.txt`: add `psycopg2-binary`, `structlog`, `pydantic-settings`
6. Remove `experiments.db` from version control

**Acceptance criteria:** All rows present post-migration; `alembic upgrade head` and `downgrade -1` both clean; no SQLite paths remain.

**Test Writer Agent:** Row count validation per table, model CRUD tests, FK constraint tests, JSONB field tests.

**Documentation Agent:** Update `README.md` setup section, `docs/deployment/ENV_REFERENCE.md`, `MODELS.md` PostgreSQL type notes.
