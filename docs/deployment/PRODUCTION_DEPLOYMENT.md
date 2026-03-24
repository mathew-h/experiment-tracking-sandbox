# Production Deployment Guide

This guide covers deploying the Experiment Tracking System on the lab PC as a Windows service accessible to all users on the LAN.

## Prerequisites

Before starting, ensure the following are installed and running on the lab PC:

- **PostgreSQL 16+** — configured as a Windows service, database created
- **Node 18+** — only needed to build the frontend; can be uninstalled after
- **Python 3.11+** — used for the venv and application runtime
- **NSSM** (Non-Sucking Service Manager) — used to register uvicorn as a Windows service; download from [nssm.cc](https://nssm.cc)
- **Firebase project credentials** — `PROJECT_ID`, `PRIVATE_KEY`, `CLIENT_EMAIL`, `API_KEY`, `AUTH_DOMAIN`

---

## One-Time Setup

### 1. Clone the repository

```powershell
git clone https://github.com/mathew-h/experiment-tracking-sandbox.git C:\Apps\experiment-tracking
cd C:\Apps\experiment-tracking
```

### 2. Create `.env` with production values

```powershell
copy .env.example .env
notepad .env
```

Fill in all required values:

```
DATABASE_URL=postgresql://user:password@localhost:5432/experiments
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
FIREBASE_CLIENT_EMAIL=firebase-adminsdk-xxx@your-project.iam.gserviceaccount.com
FIREBASE_API_KEY=your-web-api-key
FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
APP_ENV=production
API_PORT=8000
CORS_ORIGINS=http://localhost:8000,http://<lab-pc-hostname>:8000
LOG_LEVEL=INFO
BACKUP_DIR=C:\Backups\experiments
PUBLIC_COPY_DIR=\\server\shared\experiment-exports
```

### 3. Create venv and install Python dependencies

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 4. Run database migrations

```powershell
.venv\Scripts\alembic upgrade head
```

### 5. Build the frontend

```powershell
cd frontend
npm install
npm run build
cd ..
```

The build output lands in `frontend/dist/`. FastAPI serves these static files at the root URL — no separate Node server is needed in production.

### 6. Register uvicorn as a Windows service using NSSM

Open an elevated command prompt (Run as Administrator):

```powershell
nssm install ExperimentTracker "C:\Apps\experiment-tracking\.venv\Scripts\uvicorn.exe"
nssm set ExperimentTracker AppParameters "backend.api.main:app --host 0.0.0.0 --port 8000"
nssm set ExperimentTracker AppDirectory "C:\Apps\experiment-tracking"
nssm set ExperimentTracker AppEnvironmentExtra "DOTENV_PATH=C:\Apps\experiment-tracking\.env"
nssm set ExperimentTracker AppStdout "C:\Logs\experiment-tracker\stdout.log"
nssm set ExperimentTracker AppStderr "C:\Logs\experiment-tracker\stderr.log"
nssm set ExperimentTracker Start SERVICE_AUTO_START
nssm start ExperimentTracker
```

Verify the service is running:
```powershell
nssm status ExperimentTracker
```

### 7. Open the firewall for LAN access (port 8000)

In an elevated PowerShell session:

```powershell
New-NetFirewallRule -DisplayName "Experiment Tracker" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

This allows access from the local network only. Do not open port 8000 to the public internet.

### 8. Verify access

Users on the LAN can now open:
```
http://<lab-pc-hostname>:8000
```

---

## Updating the App

After merging changes into the main branch:

```powershell
cd C:\Apps\experiment-tracking

# 1. Pull latest code
git pull

# 2. Apply any new migrations
.venv\Scripts\alembic upgrade head

# 3. Rebuild the frontend (only if frontend files changed)
cd frontend
npm run build
cd ..

# 4. Restart the service
nssm restart ExperimentTracker
```

---

## Database Backups

A daily backup is recommended. Until an automated backup script is in place, run this manually or via Windows Task Scheduler:

```powershell
pg_dump -U postgres experiments > "C:\Backups\experiments\experiments_%DATE:~-4,4%%DATE:~-7,2%%DATE:~-10,2%.sql"
```

Store backups on a separate drive or network share. The `BACKUP_DIR` env var is reserved for a future automated backup service.

---

## Adding Users

New users must register at `http://<lab-pc-hostname>:8000` with an `@addisenergy.com` email address. Their account is not active until an admin approves it.

**Create a user directly (admin only):**
```powershell
cd C:\Apps\experiment-tracking
.venv\Scripts\python scripts\manage_users.py create user@addisenergy.com TempPassword123 "Display Name"
```

**List pending registration requests:**
```powershell
.venv\Scripts\python scripts\manage_users.py pending
```

**Approve a registration request:**
```powershell
.venv\Scripts\python scripts\manage_users.py approve <request_id>
```

---

## Configuring the Master Results Path

The master results sync reads from a configurable file path. Set or update it via the Swagger UI:

1. Open `http://localhost:8000/docs` on the lab PC.
2. Find `PATCH /api/bulk-uploads/master-results/config`.
3. Enter the path to the master results file (e.g. `\\server\shared\Master Results.xlsx`).

---

## Troubleshooting

**View application logs:**
```powershell
nssm get ExperimentTracker AppStdout   # shows log file path
type C:\Logs\experiment-tracker\stdout.log | more
```

**Restart the service:**
```powershell
nssm restart ExperimentTracker
```

**Service won't start — check environment:**
```powershell
nssm get ExperimentTracker AppEnvironmentExtra
```

**Database connection errors:**
Verify PostgreSQL is running and `DATABASE_URL` in `.env` is correct:
```powershell
.venv\Scripts\python -c "from database.db import engine; print(engine.connect())"
```

**Frontend not loading (blank page or 404):**
Confirm the build completed and `frontend/dist/index.html` exists. Rebuild if necessary:
```powershell
cd frontend && npm run build
```
