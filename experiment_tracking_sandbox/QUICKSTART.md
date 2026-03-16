# Quick Start — 3 Minutes to Development

## Prerequisites
- Docker Desktop installed
- Git
- The experiments.db file (already uploaded ✅)

## Go

```bash
# 1. Navigate to the sandbox
cd experiment_tracking_sandbox

# 2. Run setup script (creates directories)
bash setup.sh

# 3. Copy project files from parent repo
# You'll need to copy:
#   - database/        (models, connection setup)
#   - backend/         (api skeleton, services)
#   - frontend/        (package.json, vite.config, src stub)
#   - alembic/         (migrations, env.py)
#   - requirements.txt
#   - tests/           (test stubs)

# 4. Start Docker
docker-compose up --build

# ✅ Done. The container will:
#   - Initialize PostgreSQL
#   - Run Alembic migrations
#   - Migrate experiments.db (SQLite → PostgreSQL)
#   - Start FastAPI (http://localhost:8000/api/docs)
#   - Start React dev server (http://localhost:5173)
```

## What's Inside

| File | Purpose |
|---|---|
| `Dockerfile` | Full-stack: Python 3.11 + Node.js + dev tools |
| `docker-compose.yml` | Orchestrates PostgreSQL, FastAPI, React |
| `scripts/dev-entrypoint.sh` | Container startup (migrations, view creation) |
| `scripts/migrate-sqlite-to-postgres.py` | Data migration utility |
| `.claude/MEMORY.md` | Compact schema reference |
| `.claude/rules/schema-checklist.md` | Before-you-code checklist |
| `README_DEV_SETUP.md` | Detailed development guide |

## First-Time Commands (Inside Container)

```bash
# If you need to enter the container:
docker exec -it experiment_tracking_app bash

# Inside:
alembic current                              # Check migration status
pytest tests/ -v                             # Run tests
python scripts/migrate-sqlite-to-postgres.py # Manual migration
```

## Key Ports

| Port | Service |
|---|---|
| 8000 | FastAPI (Swagger: /api/docs) |
| 5173 | React dev server |
| 5432 | PostgreSQL (connect from host) |

## References

- **Schema authority:** `MODELS.md` (in parent repo)
- **Dev workflow:** `README_DEV_SETUP.md`
- **Before schema changes:** `.claude/rules/schema-checklist.md`
- **Quick reference:** `.claude/MEMORY.md`

## Troubleshooting

**Container won't start?**
```bash
docker-compose down -v
docker-compose up --build
docker-compose logs -f app
```

**Need to rebuild migrations?**
```bash
docker-compose down -v  # Wipes DB
docker-compose up
```

**Want to connect to PostgreSQL from host?**
```bash
psql postgresql://experiments_user:experiments_dev_password@localhost:5432/experiments
```

---

You're ready. Start the container and begin building.
