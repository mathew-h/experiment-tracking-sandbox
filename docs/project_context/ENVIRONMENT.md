# Environment and Permissions

## Deployment Reality
- **Server:** One always-on lab PC on a local area network
- **Users:** 2-5 researchers accessing via browser at `http://<lab-pc-hostname>:8000`
- **No cloud, no external hosting, no Docker required in production**
- React app is served as static files by FastAPI — no separate Node server in production
- All users are on the same LAN — no public internet exposure needed
- Docker Compose is used for local development only

## Environment Variables (never hardcode these)
```
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/experiments

# Firebase
FIREBASE_PROJECT_ID=
FIREBASE_PRIVATE_KEY=
FIREBASE_CLIENT_EMAIL=

# App
APP_ENV=development|production
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://<lab-pc-hostname>:8000
LOG_LEVEL=INFO

# Backups
BACKUP_DIR=
PUBLIC_COPY_DIR=
```

## Permitted Operations
- Read and write to this Git repository
- Fetch external documentation via Context7 MCP (`use context7`) for all stack libraries: FastAPI, React, PostgreSQL, SQLAlchemy, Alembic, Firebase, Tailwind, Vite, Vitest, structlog, TanStack Query, Pydantic, psycopg2
- Research full-stack experimental data tracking best practices
- Run tests, linters, formatters, and build tools within the repo
- Run database migrations against the local development database
- Install packages listed in `requirements.txt` or `package.json`
- Use GitHub MCP to create PRs, manage issues, and check CI status
- Use Playwright MCP for E2E test execution (Milestone 8 and `frontend-builder` verification)
- Use Chrome DevTools MCP for the frontend-builder closed-loop (Milestone 4 onward)

## Not Permitted
- Accessing or modifying the production database directly
- Deploying to production without explicit user instruction
- Installing new third-party packages without proposing them to the user first and receiving approval
- Accessing any external service not listed above
- Modifying `.env` files — only read them; never commit secrets
- Committing directly to `main` or `develop`
