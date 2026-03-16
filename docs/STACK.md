# Technology Stack

## Current State (Legacy — being replaced)
| Layer | Technology | Location |
|---|---|---|
| Frontend | Streamlit | `frontend/components/` |
| Backend | SQLAlchemy ORM called directly from Streamlit | `database/` |
| Database | SQLite file (`experiments.db`) | repo root |
| Auth | Firebase Authentication | `app.py` |
| Migrations | Alembic | `alembic/` |
| Deployment | Single lab PC, auto-updater via `auto_update.bat` | lab PC |

## Target State (what we are building)
| Layer | Technology | Location |
|---|---|---|
| Frontend | React 18 + TypeScript (Vite) + Tailwind CSS | `frontend/` |
| API | FastAPI + uvicorn | `backend/api/` |
| ORM | SQLAlchemy 2.0 | `database/models/` |
| Migrations | Alembic (extended, not replaced) | `alembic/` |
| Calculation Engine | Python service layer | `backend/services/calculations/` |
| Logging | structlog (structured JSON) | `backend/core/logging.py` |
| Database | PostgreSQL (on lab PC, always-on) | lab PC service |
| Auth | Firebase Authentication (preserved) | `backend/auth/` |
| Deployment | Windows Services on lab PC, LAN accessible | lab PC |
| Reporting | Read-only PostgreSQL replica dump for Power BI | scheduled task |

## Canonical Repository
`https://github.com/mathew-h/experiment-tracking-sandbox.git`
