# Project Structure — Reorganized for FastAPI + React

## Overview

```
experiment_tracking_sandbox/
├── alembic/                        # Database migrations (Alembic)
│   ├── versions/                   # Migration scripts
│   ├── env.py                      # Migration environment config
│   └── script.py.mako              # Migration template
│
├── backend/                        # FastAPI application
│   ├── api/
│   │   ├── main.py                 # FastAPI app entry point
│   │   ├── dependencies/           # Dependency injection (DB session, auth)
│   │   ├── routers/                # API endpoint routers (one per domain)
│   │   │   ├── experiments.py
│   │   │   ├── results.py
│   │   │   ├── bulk_uploads.py
│   │   │   └── ...
│   │   └── schemas/                # Pydantic v2 request/response models
│   │       ├── experiments.py
│   │       ├── results.py
│   │       └── ...
│   ├── auth/                       # Firebase authentication
│   │   └── firebase.py
│   └── services/                   # Business logic layer
│       ├── bulk_uploads/           # Existing parsers (read-only)
│       │   ├── new_experiments.py
│       │   ├── scalar_results.py
│       │   ├── icp_service.py
│       │   └── ...
│       └── database/               # Database utilities
│           └── session.py
│
├── database/                       # SQLAlchemy ORM & database setup
│   ├── models/                     # SQLAlchemy models (locked, read-only)
│   │   ├── experiments.py
│   │   ├── conditions.py
│   │   ├── results.py
│   │   ├── samples.py
│   │   ├── chemicals.py
│   │   ├── analysis.py
│   │   ├── xrd.py
│   │   ├── characterization.py
│   │   ├── enums.py
│   │   └── __init__.py
│   ├── __init__.py
│   ├── connection.py               # SQLAlchemy engine & session factory
│   ├── event_listeners.py          # View creation on engine connect
│   ├── services.py                 # Query helpers & business logic
│   ├── lineage_utils.py            # Experiment lineage helpers
│   ├── init_db.py                  # Database initialization
│   └── ingest_pxrf.py              # pXRF data ingestion logic
│
├── frontend/                       # React + TypeScript application
│   ├── src/
│   │   ├── App.tsx                 # Root component
│   │   ├── main.tsx                # Vite entry point
│   │   ├── api/                    # Axios clients
│   │   │   ├── client.ts           # Base HTTP client
│   │   │   ├── experiments.ts      # Experiments API calls
│   │   │   └── ...
│   │   ├── auth/                   # Firebase authentication
│   │   │   ├── FirebaseProvider.tsx
│   │   │   └── ProtectedRoute.tsx
│   │   ├── components/             # Reusable React components
│   │   │   ├── ui/                 # Base UI library
│   │   │   │   ├── Button.tsx
│   │   │   │   ├── Input.tsx
│   │   │   │   └── ...
│   │   │   └── shared/             # Domain-specific components
│   │   ├── pages/                  # Route pages
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Experiments.tsx
│   │   │   ├── ExperimentDetail.tsx
│   │   │   └── ...
│   │   ├── layouts/                # Layout components
│   │   │   ├── AppLayout.tsx       # Main app shell
│   │   │   └── AuthLayout.tsx      # Login page layout
│   │   ├── hooks/                  # Custom React hooks
│   │   ├── styles/                 # Global styles & tokens
│   │   │   └── tokens.css          # Design system tokens
│   │   ├── utils/                  # Utility functions
│   │   └── types/                  # TypeScript type definitions
│   ├── public/                     # Static assets
│   ├── package.json                # Node.js dependencies
│   ├── vite.config.ts              # Vite configuration
│   ├── tsconfig.json               # TypeScript config
│   └── index.html                  # HTML entry point
│
├── tests/                          # Automated tests
│   ├── api/                        # Endpoint tests
│   │   ├── test_experiments.py
│   │   ├── test_results.py
│   │   └── ...
│   ├── services/                   # Service layer tests
│   │   ├── test_bulk_uploads.py
│   │   └── ...
│   ├── models/                     # Model integrity tests
│   │   ├── test_experiments.py
│   │   └── ...
│   ├── integration/                # End-to-end tests
│   │   └── test_workflows.py
│   └── fixtures/                   # Test data
│       ├── sample_experiments.xlsx
│       ├── sample_icp_data.csv
│       └── ...
│
├── docs/                           # Documentation
│   ├── api/                        # API documentation
│   │   ├── API_REFERENCE.md
│   │   └── ADDING_ENDPOINTS.md
│   ├── frontend/                   # Frontend documentation
│   │   ├── ARCHITECTURE.md
│   │   ├── DESIGN_SYSTEM.md
│   │   └── ADDING_A_PAGE.md
│   ├── developer/                  # Developer guides
│   │   ├── CONTRIBUTING.md
│   │   ├── CODE_STANDARDS.md
│   │   └── SETUP.md
│   ├── user_guide/                 # User-facing guides
│   │   ├── GETTING_STARTED.md
│   │   ├── BULK_UPLOADS.md
│   │   └── DASHBOARD.md
│   ├── deployment/                 # Deployment guides
│   │   ├── LAB_PC_SETUP.md
│   │   ├── PRODUCTION_DEPLOYMENT.md
│   │   └── MIGRATION_TESTING.md
│   └── sample_data/
│       ├── experiments.db          # Current production database
│       ├── representative_sample.xlsx
│       └── FIELD_MAPPING.md        # Column mapping reference
│
├── scripts/                        # Utility scripts
│   ├── dev-entrypoint.sh           # Docker startup script
│   ├── migrate-sqlite-to-postgres.py
│   ├── init-db.sql                 # PostgreSQL initialization
│   ├── install_services.bat        # Windows service setup (production)
│   └── backup.bat                  # Database backup (production)
│
├── legacy/                         # Legacy code (reference only)
│   └── streamlit_frontend/         # Old Streamlit components
│       └── ...
│
├── .claude/                        # Claude Code metadata
│   ├── MEMORY.md                   # Project memory & schema reference
│   └── rules/
│       └── schema-checklist.md     # Schema modification checklist
│
├── .env.example                    # Environment variables template
├── .gitignore                      # Git ignore rules
├── .dockerignore                   # Docker build ignore
├── Dockerfile                      # Docker image definition
├── docker-compose.yml              # Docker Compose orchestration
├── requirements.txt                # Python dependencies
├── alembic.ini                     # Alembic configuration
├── CLAUDE.md                       # Project instructions (locked)
├── MODELS.md                       # Schema reference (locked)
├── README_DEV_SETUP.md             # Development setup guide
├── QUICKSTART.md                   # 3-minute startup guide
├── PROJECT_STRUCTURE.md            # This file
└── setup.sh                        # Repository initialization script
```

---

## Directory Purposes

### `alembic/`
Database schema migrations. Never delete migration files. Use `alembic upgrade head` to apply all pending migrations.

### `backend/api/`
FastAPI application code. Routers handle endpoints, schemas define request/response contracts, dependencies manage injection (DB sessions, auth).

### `backend/services/`
Business logic and external integrations. `bulk_uploads/` contains the existing parsers (read-only per CLAUDE.md). `database/` utilities for query helpers.

### `database/models/`
SQLAlchemy ORM models (locked per CLAUDE.md Section 4). These are the authoritative schema definitions. Changes require Alembic migrations.

### `frontend/src/`
React application source. Organized by functional domain: `api/` for backend communication, `auth/` for Firebase, `components/` for UI, `pages/` for routes.

### `tests/`
Automated test suites. Structure mirrors `backend/` and `frontend/` for easy discovery. `fixtures/` contains test data.

### `docs/`
All documentation. Update before/after major features per CLAUDE.md Section 3 (Documentation Agent).

### `legacy/`
Old Streamlit frontend components. Kept for reference during migration but not used in new app.

---

## Key Files

| File | Purpose | Lock Status |
|---|---|---|
| `CLAUDE.md` | Project instructions & milestones | READ-ONLY |
| `MODELS.md` | Database schema reference | READ-ONLY |
| `requirements.txt` | Python dependencies | Managed |
| `alembic.ini` | Migration config | Managed |
| `docker-compose.yml` | Dev environment | Managed |
| `.env.example` | Environment template | Managed |

---

## Development Workflow

1. **Create feature branch** from `develop`: `git checkout -b feature/m1-postgres-migration`
2. **Write code** in appropriate directories
3. **Add tests** in `tests/` mirroring the source structure
4. **Run tests locally**: `pytest tests/ -v` (inside container)
5. **Update docs** in `docs/` for new features
6. **Commit with [Milestone] prefix**: `[M1] Migrate database schema`
7. **Create PR** to `develop` (requires Code Revision Agent review)
8. **Merge to main** only after user sign-off per CLAUDE.md Section 7

---

## Next Steps

1. ✅ **Structure organized** — files are properly arranged
2. **Start Docker**: `docker-compose up --build`
3. **Alembic runs**: Migrations apply automatically
4. **Begin Milestone 1**: SQLite → PostgreSQL migration
