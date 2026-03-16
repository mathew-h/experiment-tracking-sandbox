# Pre-Milestone: Infrastructure Setup

**Owner:** db-architect
**Branch:** `infra/lab-pc-server-setup`

**Objective:** Transform the lab PC from a Streamlit host into a proper application server before any code migration begins.

**Tasks:**
1. Install PostgreSQL for Windows as a system service (auto-start on boot)
2. Create the `experiments` database and application user with least-privilege permissions
3. Install NSSM to run uvicorn as a Windows service
4. Configure Windows Firewall to allow inbound TCP on port 8000 from LAN only
5. Write `scripts/install_services.bat` — idempotent setup script for the lab PC
6. Write `scripts/deploy.bat` — replaces `auto_update.bat`:
   - Pull latest from `main`, install/update dependencies, run `alembic upgrade head`, restart uvicorn
   - On failure: rollback git, restore last backup, restart old service
7. Write `scripts/backup.bat` — replaces `database_backup.py`:
   - `pg_dump` to timestamped file, 30-day retention, separate read-only dump for Power BI on 12-hour schedule

**Acceptance criteria:** PostgreSQL auto-starts on boot; FastAPI skeleton accessible from LAN at port 8000; `deploy.bat` and `backup.bat` work end-to-end.

**Documentation Agent:** `docs/deployment/LAB_PC_SETUP.md` — step-by-step Windows setup guide.
