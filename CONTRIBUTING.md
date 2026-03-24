# Contributing Guide

## Prerequisites

- Python 3.11+
- Node 18+
- PostgreSQL 15+
- A Firebase project with credentials (contact the project maintainer)

## Dev Setup

Follow the steps in [README.md](README.md#quick-start-development). In summary:

1. Clone, create `.env`, activate venv, `pip install -r requirements.txt`
2. `alembic upgrade head`
3. `cd frontend && npm install`
4. Start backend (`uvicorn`) and frontend (`npm run dev`) in separate terminals

## Project Layout

```
backend/        FastAPI app, routers, services, calculation logic
database/       SQLAlchemy models, Alembic migrations
frontend/       React 18 + TypeScript + Vite + Tailwind
docs/           Architecture docs, API reference, user guides, milestones
tests/          pytest (backend) and Playwright (E2E)
scripts/        CLI utilities (user management, data migration)
auth/           Firebase auth module
```

## Before Making Changes

1. **Read `.claude/CLAUDE.md`** — project conventions, working memory, agent system.
2. **Check `docs/LOCKED_COMPONENTS.md`** — some models, parsers, and enums must not be modified without explicit sign-off. If your change touches a locked component, stop and get approval first.
3. **Read the active milestone file** listed in `docs/milestones/MILESTONE_INDEX.md` — your change should be in scope.

## Branch Naming

Cut feature branches from the main branch (`infra/lab-pc-server-setup`):

```
feature/m<N>-short-description
```

Example: `feature/m5-bulk-upload-icp`

Do not commit directly to `infra/lab-pc-server-setup`.

## Commit Format

```
[M<number>] <imperative description>

- Detail if needed
- Tests added: yes/no
- Docs updated: yes/no
```

Example:
```
[M5] Add ICP bulk upload parser

- Parses instrument CSV export, maps elements to ICPResults columns
- Tests added: yes
- Docs updated: yes
```

## Running Tests

**Backend:**
```bash
.venv/Scripts/pytest tests/services/ tests/regression/ tests/api/ -v
```

**End-to-end (from `frontend/` directory):**
```bash
cd frontend && npx playwright test
```

All tests must pass before opening a PR.

## Pull Request Checklist

Before requesting review, confirm:

- [ ] All backend and E2E tests pass
- [ ] Affected documentation files updated (models, API reference, calculations, etc.)
- [ ] No locked components modified without explicit approval
- [ ] Migration (if any) is purely additive — no column drops or renames
- [ ] `alembic downgrade -1` works cleanly
- [ ] Commit messages follow the format above

## Adding New Derived Fields

1. Document the formula in `docs/CALCULATIONS.md`.
2. Implement the calculation in `backend/services/calculations/` following the existing pattern.
3. Do not persist a derived value if it can be computed on read from stored inputs.
4. Add tests in `tests/services/`.
5. Update `docs/api/API_REFERENCE.md` if the field appears in any response schema.
