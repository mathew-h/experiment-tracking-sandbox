# Technology Stack

## Current State
| Layer | Technology | Location |
|---|---|---|
| Frontend | React 18 + TypeScript (Vite) + Tailwind CSS | `frontend/` |
| API | FastAPI + uvicorn | `backend/api/` |
| ORM | SQLAlchemy 2.0 | `database/models/` |
| Migrations | Alembic | `alembic/` |
| Calculation Engine | Python service layer | `backend/services/calculations/` |
| Logging | structlog (structured JSON) | `backend/core/logging.py` |
| Database | PostgreSQL (on lab PC, always-on) | lab PC service |
| Auth | Firebase Authentication | `backend/auth/` |
| Deployment | Windows Service (NSSM) on lab PC, LAN accessible | lab PC |
| Reporting | Read-only PostgreSQL connection for Power BI | Power BI Desktop |

## Legacy (superseded, reference only)
| Layer | Technology | Location |
|---|---|---|
| Frontend | Streamlit | `legacy/streamlit_frontend/` |
| Database | SQLite file (`experiments.db`) | superseded by PostgreSQL |

The Streamlit → React/FastAPI/PostgreSQL migration completed at Milestone 8 (`docs/milestones/MILESTONE_INDEX.md`). Do not build new features against the legacy Streamlit code.

## Canonical Repository
`https://github.com/mathew-h/experiment-tracking-sandbox.git`
