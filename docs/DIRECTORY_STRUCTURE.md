# Directory Structure

```
experiment_tracking_sandbox/
├── README.md                          ← start here: stack, quick start, key docs
├── CONTRIBUTING.md                    ← contributor setup, branch/PR rules
├── PROJECT_STRUCTURE.md               ← deprecated, points here
├── .env / .env.example
├── requirements.txt
├── alembic.ini                        ← script_location = alembic/ (canonical migration history)
│
├── .claude/
│   ├── CLAUDE.md                      ← root instructions, read first
│   ├── MEMORY.md
│   ├── rules/                         ← MODELS.md, AUTH.md, schema-checklist.md
│   ├── skills/                        ← agent skill files (conductor, db-architect, ...)
│   └── commands/                      ← slash commands (start-task, complete-task, ...)
│
├── backend/
│   ├── CLAUDE.md
│   ├── config/settings.py             ← pydantic-settings
│   ├── api/
│   │   ├── main.py                    ← FastAPI entry point
│   │   ├── dependencies/              ← DB session, auth
│   │   ├── routers/                   ← one file per domain
│   │   └── schemas/                   ← Pydantic v2, one file per domain
│   ├── auth/firebase_auth.py          ← current Firebase token verification
│   └── services/
│       ├── calculations/              ← calculation engine
│       ├── bulk_uploads/              ← locked parsers, do not modify logic
│       ├── database/                  ← query helpers
│       └── notion_sync/
│
├── database/
│   ├── CLAUDE.md
│   ├── models/                        ← SQLAlchemy models, locked, storage-only
│   ├── database.py, event_listeners.py (Power BI view creation)
│   └── data_migrations/               ← one-off backfill scripts, not Alembic
│
├── alembic/versions/                  ← never delete existing files
│
├── frontend/
│   ├── CLAUDE.md
│   ├── src/{api,auth,components,layouts,pages,hooks,styles}/
│   ├── dist/                          ← build output, served by FastAPI in production
│   └── package.json
│
├── tests/
│   ├── api/, models/, services/, integration/, regression/, views/
│   └── fixtures/
│
├── docs/
│   ├── STACK.md, GIT_WORKFLOW.md, CODE_STANDARDS.md, CALCULATIONS.md
│   ├── LOCKED_COMPONENTS.md, ENVIRONMENT.md, AGENT_SYSTEM.md, DESIGN.md
│   ├── PSQL_ACCESS.md                 ← read-only psql access + query guide for the team
│   ├── DIRECTORY_STRUCTURE.md         ← this file
│   ├── api/API_REFERENCE.md
│   ├── frontend/                      ← ARCHITECTURE.md, DESIGN_SYSTEM.md, ADDING_A_PAGE.md
│   ├── developer/                     ← ADDING_UPLOAD_TYPE.md, SAMPLE_CHARACTERIZED_LOGIC.md
│   ├── deployment/                    ← STARTUP_GUIDE.md, PRODUCTION_DEPLOYMENT.md
│   ├── user_guide/                    ← USER_MANUAL.md, ONBOARDING.md, BULK_UPLOADS.md, ...
│   ├── milestones/                    ← M0–M9 + MILESTONE_INDEX.md
│   ├── specs/, upload_templates/      ← per-parser specs and templates
│   ├── working/                       ← plan.md, decisions.md, issue-log.md (session state)
│   ├── project_context/               ← auto-synced mirror for the wider team, do not edit directly
│   └── sample_data/
│
├── legacy/streamlit_frontend/         ← old Streamlit UI, reference only
│
├── scripts/                           ← manage_users.py, migrate-sqlite-to-postgres.py
│
├── setup.ps1 / update.ps1 / backup.ps1   ← lab PC install & nightly update, see docs/deployment/STARTUP_GUIDE.md
│
└── logs/
```

## Known cruft, not yet cleaned up

- Root `app.py` and the root `auth/` module are the old Streamlit entry point; `requirements.txt` still lists `streamlit`. The real app is `backend/api/main.py` + `frontend/`.
- `Dockerfile` / `docker-compose.yml` / `scripts/dev-entrypoint.sh` supported a Docker dev workflow superseded by the native venv + npm setup in `README.md`.
