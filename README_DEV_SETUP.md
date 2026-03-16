# Experiment Tracking System — Docker Development Setup

## Quick Start

```bash
# 1. Clone/setup the repo
cd experiment_tracking_sandbox

# 2. Start the Docker environment
docker-compose up --build

# 3. Access the app
# FastAPI docs: http://localhost:8000/api/docs
# React dev: http://localhost:5173
```

That's it. The container handles:
- PostgreSQL initialization
- Alembic migrations
- SQLite → PostgreSQL data migration (first run)
- React dev server hot-reload
- FastAPI hot-reload with Uvicorn

---

## Development Workflow

### In the Container

Everything runs inside the container. Your files are volume-mounted, so changes reflect immediately.

```bash
# If you need to run commands manually:
docker exec -it experiment_tracking_app bash

# Then inside the container:
alembic revision --autogenerate -m "add new field"  # Generate migration
pytest tests/ -v                                     # Run tests
python scripts/migrate-sqlite-to-postgres.py        # Manual SQLite migration
```

### Backend (FastAPI)

- **Location:** `backend/api/`
- **Entry point:** `backend/api/main.py`
- **Port:** 8000
- **Hot-reload:** ✅ Enabled (changes auto-restart Uvicorn)

Create new endpoints:
```python
# backend/api/routers/experiments.py
@router.get("/experiments/{experiment_id}")
async def get_experiment(experiment_id: str, db: Session = Depends(get_db)):
    """Retrieve single experiment."""
    ...
```

### Frontend (React + Vite)

- **Location:** `frontend/src/`
- **Entry point:** `frontend/src/App.tsx`
- **Port:** 5173
- **Hot-reload:** ✅ Enabled (HMR works in container)

Create new pages:
```tsx
// frontend/src/pages/Experiments.tsx
export function ExperimentsPage() {
  return <div>Experiments list</div>;
}
```

### Database (PostgreSQL)

- **Host:** postgres (inside container) or localhost:5432 (from host)
- **User:** experiments_user
- **Password:** experiments_dev_password
- **Database:** experiments

Connect from host:
```bash
psql postgresql://experiments_user:experiments_dev_password@localhost:5432/experiments
```

---

## Project Structure

```
experiment_tracking_sandbox/
├── backend/
│   ├── api/
│   │   ├── main.py                    # FastAPI app
│   │   ├── dependencies.py            # DB session, auth
│   │   ├── routers/                   # One per domain
│   │   └── schemas/                   # Pydantic request/response
│   ├── auth/                          # Firebase integration
│   └── services/
│       └── bulk_uploads/              # Existing parsers (read-only)
│
├── database/
│   ├── models/                        # SQLAlchemy ORM (read-only, locked)
│   ├── connection.py                  # Engine + session factory
│   └── event_listeners.py             # View creation
│
├── frontend/
│   ├── src/
│   │   ├── api/                       # Axios client
│   │   ├── components/                # React components
│   │   ├── pages/                     # Route pages
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
│
├── alembic/                           # Database migrations
│   └── versions/                      # Never delete!
│
├── tests/
│   ├── api/                           # Endpoint tests
│   ├── models/                        # Model integrity
│   └── fixtures/                      # Test data
│
├── scripts/
│   ├── dev-entrypoint.sh              # Container startup
│   ├── migrate-sqlite-to-postgres.py  # Data migration
│   └── init-db.sql                    # PostgreSQL setup
│
├── docs/
│   └── sample_data/
│       └── experiments.db             # Current production data
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Database Migrations

Migrations run automatically on container start. To create a new one:

```bash
# Inside container
alembic revision --autogenerate -m "add reactor_name field"

# Review generated file (alembic/versions/xxx.py)
# Then container restart applies it

# To downgrade locally:
alembic downgrade -1
```

**Important:** Always test both upgrade and downgrade.

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs -f app

# Rebuild from scratch
docker-compose down -v
docker-compose up --build
```

### PostgreSQL connection refused

Wait a few seconds — the service healthcheck ensures readiness. If still failing:

```bash
docker-compose logs postgres
# Check for errors in initialization
```

### React dev server not accessible

The dev server runs inside the container on port 5173. Make sure `docker-compose.yml` exposes it and your firewall allows it.

```bash
curl http://localhost:5173
```

### Migration errors

Check the Alembic logs:

```bash
docker-compose logs app | grep alembic
```

If a migration fails, investigate, fix, and re-run:

```bash
docker exec -it experiment_tracking_app alembic current
docker exec -it experiment_tracking_app alembic downgrade -1
# Fix the migration file
docker exec -it experiment_tracking_app alembic upgrade head
```

---

## Before Touching the Schema

**Always follow:** `.claude/rules/schema-checklist.md`

Quick checklist:
1. Read `MODELS.md` (authoritative reference)
2. Read `.claude/MEMORY.md` (Key Design Decisions — do NOT rewrite these)
3. Ask user if your change affects locked models or requires destructive operations
4. Create Alembic migration
5. Test upgrade + downgrade
6. Run tests

---

## Environment Variables

Copy `.env.example` to `.env`:

```bash
# Database (configured by docker-compose.yml)
DATABASE_URL=postgresql://experiments_user:experiments_dev_password@postgres:5432/experiments

# Firebase (add your credentials if testing auth)
FIREBASE_PROJECT_ID=
FIREBASE_PRIVATE_KEY=
FIREBASE_CLIENT_EMAIL=

# App
APP_ENV=development
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:8000
```

---

## Next Steps

1. **Milestone 1:** SQLite → PostgreSQL migration (data integrity tests)
2. **Milestone 2:** FastAPI endpoints wrapping bulk upload parsers
3. **Milestone 3:** React shell with authentication
4. **Milestone 4:** Experiment management pages
5. **Milestone 5:** Bulk upload UI
6. **Milestone 6:** Reactor dashboard

See `CLAUDE.md` Section 6 for complete milestone breakdown.
