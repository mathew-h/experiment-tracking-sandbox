# Startup Guide — Experiment Tracker Lab PC Setup

This guide covers everything needed to get the Experiment Tracker running on the lab PC from a fresh clone. Follow each step in order.

---

## Prerequisites

Install all of the following before running setup. Restart your terminal after each installation.

| Software | Version | Download |
|---|---|---|
| Python | 3.11 or higher | https://python.org/downloads |
| Node.js | 18 or higher | https://nodejs.org |
| NSSM | Latest | https://nssm.cc/download — extract and add the `win64/` folder to your PATH |
| Git | Latest | https://git-scm.com/downloads |
| PostgreSQL | 16+ | Already installed on the lab PC — skip if present |

**Verify everything is installed:** open PowerShell and run:

```powershell
python --version; node --version; nssm version; git --version
```

All four commands should print version numbers. If any fail, install the missing tool first.

---

## First-Time Setup

### 1. Clone the repository

Open PowerShell and run:

```powershell
git clone https://github.com/mathew-h/experiment-tracking-sandbox.git C:\Apps\experiment-tracking
cd C:\Apps\experiment-tracking
```

### 2. Run setup.ps1

Right-click `setup.ps1` in File Explorer and choose **Run with PowerShell**.

The script will:
- Check all prerequisites are installed
- Create `.env` and pause for you to fill in credentials (see below)
- Create `frontend/.env.local` and pause for you to fill in Firebase values (see below)
- Install Python and Node dependencies
- Apply database migrations
- Build the React frontend
- Register the app as a Windows service (auto-starts on boot)
- Open the firewall on port 8000
- Register the nightly update task
- Start the service

The script prompts for your **Windows account password** near the end — this is needed so the nightly update task can run when you are not logged in.

### 3. Fill in `.env`

When the script pauses at the `.env` step, open `C:\Apps\experiment-tracking\.env` in Notepad and fill in:

| Field | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string, e.g. `postgresql://user:password@localhost:5432/experiments` |
| `FIREBASE_PROJECT_ID` | From Firebase Console -> Project Settings -> General |
| `FIREBASE_PRIVATE_KEY` | The full `-----BEGIN PRIVATE KEY-----` block from the service account JSON |
| `FIREBASE_CLIENT_EMAIL` | Service account email from Firebase Console |

All other fields (`APP_ENV`, `API_PORT`, etc.) have working defaults and do not need to be changed.

### 4. Fill in `frontend/.env.local`

When the script pauses at the frontend `.env.local` step, open `C:\Apps\experiment-tracking\frontend\.env.local` in Notepad.

Get the values from **Firebase Console -> Project Settings -> Your Apps -> Web App** (the config snippet):

| Field | Where to find it |
|---|---|
| `VITE_FIREBASE_API_KEY` | `apiKey` in the Firebase web config |
| `VITE_FIREBASE_AUTH_DOMAIN` | `authDomain` |
| `VITE_FIREBASE_PROJECT_ID` | `projectId` |
| `VITE_FIREBASE_STORAGE_BUCKET` | `storageBucket` |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | `messagingSenderId` |
| `VITE_FIREBASE_APP_ID` | `appId` |

**Important:** Without these values the app will start but users will not be able to log in.

### 5. Verify

After setup completes, open a browser on any LAN machine and navigate to:

```
http://<lab-pc-hostname>:8000
```

The login page should appear. If it does not, see [Troubleshooting](#troubleshooting) below.

---

## Manual Updates

To update the app at any time, right-click `update.ps1` in File Explorer and choose **Run with PowerShell**.

The script pulls the latest code, runs any new migrations, rebuilds the frontend if needed, and restarts the service. It logs the result to `C:\Logs\experiment-tracker\updates.log`.

---

## Scheduled Updates

`setup.ps1` registers a Windows Task Scheduler job called `ExperimentTrackerUpdate` that runs `update.ps1` every night at 02:00.

### Verify the task is registered

```powershell
Get-ScheduledTask -TaskName "ExperimentTrackerUpdate" | Select-Object TaskName, State
```

Expected output:
```
TaskName                  State
--------                  -----
ExperimentTrackerUpdate   Ready
```

Or open **Task Scheduler** from the Start menu -> **Task Scheduler Library** -> find `ExperimentTrackerUpdate`.

### Check the last update log

```powershell
Get-Content "C:\Logs\experiment-tracker\updates.log" -Tail 10
```

### If you change your Windows password

The scheduled task stores your credentials. If you change your Windows account password, the task will silently stop working. To fix it:

1. Open **Task Scheduler** (Start -> search "Task Scheduler")
2. Click **Task Scheduler Library** in the left panel
3. Double-click **ExperimentTrackerUpdate**
4. Click the **General** tab -> **Properties** -> enter your new password when prompted
5. Click **OK**

### Changing the update time

1. Open `setup.ps1` in Notepad
2. Change the `$UpdateTime = "02:00"` line at the top to your preferred time (24-hour format)
3. Right-click `setup.ps1` -> **Run with PowerShell** — it will re-register the task with the new time

---

## Troubleshooting

**Service won't start:**
```powershell
type "C:\Logs\experiment-tracker\stderr.log"
```
Check for database connection errors (wrong `DATABASE_URL`) or missing `.env` values.

**Port 8000 blocked — can't reach from other PCs:**
```powershell
Get-NetFirewallRule -DisplayName "Experiment Tracker" | Select-Object DisplayName, Enabled, Profile
```
If the rule is missing or shows the wrong profile (must include `Domain` for domain-joined PCs), re-run `setup.ps1`.

**Blank page or "Cannot GET /" at the app URL:**
The React build may be missing. Run:
```powershell
ls C:\Apps\experiment-tracking\frontend\dist\
```
If the directory is empty or missing, rebuild manually:
```powershell
cd C:\Apps\experiment-tracking\frontend
npm run build
nssm restart ExperimentTracker
```

**Update failed — scheduled task error:**
```powershell
Get-Content "C:\Logs\experiment-tracker\updates.log" -Tail 20
```
Look for `FAILED -- step: <step name>` to identify where it broke. Common causes: network outage during `git pull`, migration error (check `DATABASE_URL`), or expired Windows credentials (see [If you change your Windows password](#if-you-change-your-windows-password) above).

**Check service status:**
```powershell
nssm status ExperimentTracker
```

**Restart the service manually:**
```powershell
nssm restart ExperimentTracker
```
