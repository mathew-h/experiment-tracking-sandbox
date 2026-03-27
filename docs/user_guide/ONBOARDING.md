# Onboarding Guide -- Experiment Tracking System

Welcome to the Experiment Tracking System. This guide covers two things: how to access the web application and how to connect Power BI to the PostgreSQL database for reporting.

---

## Part 1: Connecting to the Web Application

### What you need

- A computer on the lab network (LAN)
- A modern web browser (Chrome, Edge, or Firefox)
- An `@addisenergy.com` email address

### Accessing the app

The Experiment Tracking System runs on a dedicated lab PC and is available to anyone on the local network. Open your browser and navigate to:

```
http://100.97.130.43:8000
```

> **Note:** The app is LAN-only. You must be connected to the lab network to access it. It is not available over the internet.

### Creating an account

1. On the login screen, switch to the **Register** tab.
2. Enter your `@addisenergy.com` email, a password, your display name, and your role.
3. Click **Register**. Your request will be submitted for admin approval.
4. You will not be able to log in until an administrator approves your account. They will let you know when access is ready.

### Logging in

1. Navigate to the app URL.
2. On the **Login** tab, enter your `@addisenergy.com` email and password.
3. Click **Login**. If your account has been approved, you will be taken to the main dashboard.

If you see a "pending approval" message, your account has not yet been approved. Contact your lab administrator.

### Troubleshooting

| Problem | What to check |
|---------|---------------|
| Page does not load | Confirm you are on the lab network. Try pinging `100.97.130.43`. |
| "Connection refused" error | The app service may be stopped. Ask the administrator to check the `ExperimentTracker` Windows Service on the lab PC. |
| "Pending approval" after registering | Your account needs admin approval. Reach out to the lab admin. |
| Forgotten password | Contact the lab admin to reset your password via the management CLI. |

---

## Part 2: Connecting Power BI to PostgreSQL

The database includes several reporting views designed specifically for Power BI dashboards. These views provide flattened, one-row-per-result datasets so you can build dashboards without writing complex joins.

### Prerequisites

- Power BI Desktop installed on your computer
- Your computer is on the lab network
- PostgreSQL connection credentials (ask your lab administrator)

### Connection details

You will need the following information. Your administrator will provide the specific values for your environment.

| Setting | Value |
|---------|-------|
| Server | `100.97.130.43` |
| Port | `5432` |
| Database | `experiments` |
| Username | Provided by your admin |
| Password | Provided by your admin |

### Installing Npgsql (required for PostgreSQL in Power BI)

Power BI does not ship with a PostgreSQL driver. You need to install the Npgsql provider before Power BI can connect.

1. Download **Npgsql v4.0.17** from GitHub: https://github.com/npgsql/npgsql/releases/tag/v4.0.17
2. On the release page, scroll to the **Assets** section and download `Npgsql-4.0.17.msi`.
3. Close Power BI Desktop if it is open.
4. Run the `.msi` installer. When prompted, make sure to check the option **"Install Npgsql for Power BI"** (or "Npgsql GAC Installation"). This registers the driver where Power BI can find it.
5. Complete the installer and restart Power BI Desktop.

> **Why v4.0.17?** Power BI Desktop requires a .NET Framework (non-Core) Npgsql build registered in the GAC. The v4.0.x line is the last series that ships a traditional MSI installer with GAC support. Newer Npgsql versions (v5+) target .NET Core/.NET 5+ and do not include an MSI, so they will not work with Power BI Desktop's built-in PostgreSQL connector.

### Step-by-step: Connect Power BI to PostgreSQL

1. Open **Power BI Desktop**.
2. Click **Get Data** on the Home ribbon (or File > Get Data).
3. In the data source list, search for **PostgreSQL database** and select it. Click **Connect**.
   - If you do not see a PostgreSQL option, you need to install the Npgsql provider first. See the "Installing Npgsql" section below.
4. In the connection dialog:
   - **Server**: enter `100.97.130.43`.
   - **Database**: enter `experiments`.
   - Choose **DirectQuery** if you want the dashboard to pull live data on each refresh, or **Import** if you prefer to load a snapshot into your Power BI file.
5. Click **OK**.
6. When prompted for credentials, select **Database** (not Windows), then enter the PostgreSQL username and password provided by your administrator.
7. Click **Connect**.

### Choosing tables and views

After connecting, the Navigator panel will show all available tables and views. The most useful sources for reporting are the pre-built views:

**`v_primary_experiment_results`** -- This is the main reporting view. It provides one row per experiment per primary timepoint, with scalar measurements (pH, conductivity, ammonium, H2, yields) and ICP elemental data already joined together. Use this as your primary fact table.

**`v_experiment_additives_summary`** -- One row per experiment with a concatenated text summary of all chemical additives (e.g., "Mg(OH)2 5 g; Magnetite 1 g"). Useful for filtering or displaying additive information alongside results.

You can also connect directly to the underlying tables (`experiments`, `experimental_conditions`, `experimental_results`, `scalar_results`, `icp_results`, etc.) if you need more granular control, but the views will cover most reporting needs.

### Setting up scheduled refresh

Since the app runs on a LAN without cloud access, Power BI scheduled refresh through the Power BI Service will not work directly. Instead, you can:

- **Manual refresh**: Open your `.pbix` file and click **Refresh** on the Home ribbon whenever you want updated data.
- **Power BI Gateway** (optional): If your organization sets up an On-premises Data Gateway on a machine that can reach both the lab PC and the Power BI Service, you can configure scheduled refresh through the gateway.

### Tips for building dashboards

- Start with `v_primary_experiment_results` as your base table. It already resolves the primary result per timepoint, so you do not need to filter for `is_primary_timepoint_result` yourself.
- Join `v_experiment_additives_summary` on `experiment_id` to add additive information.
- If you need experimental conditions (temperature, pressure, rock mass, etc.), add the `experimental_conditions` table and relate it through `experiments`.
- For sample metadata (rock classification, locality), add `sample_info` and relate it through `experiments.sample_id`.
- ICP element columns in the view are named with an `icp_` prefix and `_ppm` suffix (e.g., `icp_fe_ppm`, `icp_si_ppm`, `icp_ni_ppm`).

### Troubleshooting Power BI connections

| Problem | What to check |
|---------|---------------|
| "Unable to connect" | Verify that PostgreSQL is running on `100.97.130.43` (port 5432). Check Windows Firewall on the lab PC allows inbound connections on port 5432. |
| "Npgsql not installed" | Install the Npgsql provider (see "Installing Npgsql" section above), then restart Power BI Desktop. |
| Authentication failure | Double-check the username and password. PostgreSQL credentials are separate from your web app login. |
| Views are missing | The views are created at application startup. Ask the administrator to restart the `ExperimentTracker` service, which will recreate the views. |
| Stale data in Import mode | Click **Refresh** in Power BI Desktop to pull the latest data. DirectQuery mode always fetches live data. |

---

## Getting Help

If you run into issues not covered here, contact your lab administrator. They can check service status, reset passwords, and verify network and database connectivity.
