# Direct Database Access with psql (Read-Only)

This guide covers connecting to the production PostgreSQL database from your own laptop
over the lab LAN, using `psql` — a command-line tool for running SQL queries — to pull and
plot your own data. It is a **read-only** alternative to Power BI: no dashboard building,
no saved reports, just a terminal window and whatever query answers the question you have
right now.

This guide does not cover pgAdmin, DBeaver, Python/pandas, or any other database client.
Everything here is `psql` in a terminal, plus one export command (`\copy`).

---

## 1. When to use this vs. Power BI vs. the app

| Need | Use |
|---|---|
| Enter or correct experiment data | **The app** (`http://<lab-pc-hostname>:8000`) — the only place writes are allowed |
| A recurring, shared, polished dashboard | **Power BI** — see `docs/POWERBI_MODEL.md` |
| "I just need these 30 numbers to plot in Excel/Origin/Python right now" | **psql**, this guide |
| Exploring a question nobody's built a dashboard for yet | **psql** |

psql is faster than opening Power BI Desktop for a one-off question, and it exports
straight to CSV. It will never be the right tool for entering or fixing data — see
[Section 9](#9-read-only--why-you-cant-write-from-here) for why.

---

## 2. Getting credentials

Ask **Mat** (mhearl@addisenergy.com) for access. You'll receive:

- The lab PC's hostname or IP address on the LAN
- A read-only username and password
- The database name (`experiments`)

You'll only be able to connect while on the lab network (same WiFi/LAN as the lab PC) —
this database is not reachable from the internet, by design (see `docs/ENVIRONMENT.md`).

**Never share your password over email/Slack in plain text, and never put it in a file
that gets committed to Git.** Treat it like any other login.

---

## 3. Installing psql

You only need the *client* — not a full PostgreSQL server install.

### Windows

1. Download the installer from [postgresql.org/download/windows](https://www.postgresql.org/download/windows/) (the EnterpriseDB installer).
2. Run it, but on the "Select Components" screen, **uncheck** "PostgreSQL Server", "pgAdmin 4", and "Stack Builder" — leave only **"Command Line Tools"** checked.
3. Finish the install, then add the install's `bin` folder (typically `C:\Program Files\PostgreSQL\<version>\bin`) to your PATH if the installer didn't already.
4. Open a new terminal and confirm:
   ```powershell
   psql --version
   ```

### macOS

```bash
brew install libpq
brew link --force libpq
```

`libpq` is the client-library package that includes `psql`; it doesn't install a server.
`brew link --force` is needed because Homebrew doesn't put it on your PATH by default.

Confirm:
```bash
psql --version
```

---

## 4. Connecting

```bash
psql -h <LAB_PC_HOSTNAME> -p 5432 -U <your_readonly_username> -d experiments
```

You'll be prompted for your password. If you'd rather use a single connection string:

```bash
psql "postgresql://<your_readonly_username>@<LAB_PC_HOSTNAME>:5432/experiments"
```

**How to tell you're connected:** the prompt changes to:

```
experiments=>
```

`experiments` is the database name, and `=>` means psql is ready for a command (a
superuser prompt would show `=#` instead — you won't see that with a read-only account).
Everything you type is held until you end it with a semicolon `;` and press Enter.

If the connection hangs or refuses, you're most likely off the lab network, or the
firewall/role hasn't been set up yet for your account — contact Mat.

---

## 5. psql survival guide

A handful of commands (all start with a backslash, and don't need a trailing `;`) get you
around without memorizing SQL:

| Command | What it does |
|---|---|
| `\l` | List all databases on the server |
| `\dt` | List tables (lowercase names, e.g. `experiments`, `scalar_results`) |
| `\dv` | List views (names starting `v_`, e.g. `v_results_scalar`) |
| `\d+ <name>` | Describe a table or view — every column, its type, and whether it can be `NULL` |
| `\x` | Toggle expanded (vertical) output — one field per line instead of a wide table. Very useful for ICP rows with 30+ columns. Run it again to toggle back off, or use `\x auto` to switch automatically only when a row is too wide for your terminal |
| `\timing` | Show how long each query took to run — toggle on/off |
| `\q` | Quit psql |

**Scrolling/paging:** if a query returns more rows than fit on screen, psql pipes the
output through a pager (usually `more` on Windows). Press the spacebar to page down, and
`q` to exit the pager and get your prompt back.

**Cancelling a runaway query:** if you write a query that's taking too long (see the
"forgetting a WHERE clause" gotcha in [Section 10](#10-common-gotchas)), press **Ctrl+C**.
This safely tells the database to stop that one query — it does not close your connection,
and because your account is read-only there's nothing to "undo."

---

## 6. Orientation to our data

Three quick definitions before you look at anything, since none of this assumes prior
database experience:

- **Schema** — the blueprint of the database: which tables exist and what columns each one
  has. Ours is called `public`, which is the default and the only one you'll need to think
  about.
- **View** — a saved query that behaves like a table when you `SELECT` from it, but stores
  nothing itself; it always reflects the current underlying data. Every name starting with
  `v_` in this database is a view, built specifically to make reporting easier (they're
  listed below).
- **Join** — combining rows from two tables (or views) that share a common value — e.g.
  `experiment_id` — so a single query can show an experiment's setup conditions next to its
  results. Section 7 has worked examples.

### Tables that matter

| Table | What it holds |
|---|---|
| `experiments` | One row per experiment — ID, status, researcher, date, sample link |
| `experimental_conditions` | One row per experiment — reactor setup: temperature, rock mass, water volume, feedstock, etc. |
| `experimental_results` | One row per timepoint sampled for an experiment (the parent record; the actual measurements live in the two tables below) |
| `scalar_results` | Solution chemistry per timepoint — pH, ammonium, H2, derived yields |
| `icp_results` | ICP-OES elemental analysis per timepoint |
| `sample_info` | Geological sample metadata (rock type, locality, well/core info) |
| `compounds` | Chemical reagent inventory (name, formula, molecular weight) |
| `chemical_additives` | Which compounds were added to which experiment, and how much |

Full field-by-field detail: `.claude/rules/MODELS.md`.

### Reporting views — start here, not with the raw tables

**Most questions can be answered from a view alone, with no joins at all.** The views
already do the joining described above. Write raw-table joins yourself only when a view
doesn't cover what you need.

| View | One row per... |
|---|---|
| `v_experiments` | experiment, with key setup fields already pulled in |
| `v_experiment_conditions` | experiment, full reactor/setup parameters |
| `v_chemical_additives` | additive per experiment (long format — one row per compound added) |
| `v_experiment_additives_summary` | experiment, additives concatenated as one text field (e.g. "Mg(OH)₂ 5 g; Magnetite 1 g") |
| `v_experiment_additive_names_summary` | experiment, additive names only, comma-separated |
| `v_results_scalar` | primary result timepoint — pH, ammonium (gross + net), yields |
| `v_results_h2` | primary result timepoint with an H2 measurement — ppm, micromoles, g/ton |
| `v_results_icp` | primary result timepoint with ICP data — all elements as `_ppm` columns |
| `v_results_scalar_rollup` | `(base_experiment_id, timepoint)` — mean/median/SD across a replicate set |
| `v_dim_timepoints` | primary result timepoint — the time-axis fields, shared by the three views above |
| `v_sample_info` | geological sample |
| `v_sample_characterization` | external analysis (XRD, titration, etc.) per sample |
| `v_sample_elemental_comp` | external elemental analysis per sample, pivoted wide |

Full column lists for every view: `docs/POWERBI_MODEL.md`.

---

## 7. Sample queries

Every query below has been checked against the live schema (`database/models/` and the
view definitions in `database/event_listeners.py`) — column names are copy-paste accurate
as of this writing. Replace the example `experiment_id`/`sample_id` values with your own.

### Recent experiments with status, researcher, date, and type

```sql
SELECT experiment_id, status, researcher, date, experiment_type
FROM v_experiments
ORDER BY date DESC
LIMIT 20;
```

```
 experiment_id  |  status   | researcher |          date          | experiment_type
----------------+-----------+------------+-------------------------+------------------
 SERUM_001c      | ONGOING   | A. Chen    | 2026-07-24 00:00:00+00 | Serum
 HPHT_001        | COMPLETED | M. Hearl   | 2026-07-20 00:00:00+00 | HPHT
 SERUM_001b      | ONGOING   | A. Chen    | 2026-07-18 00:00:00+00 | Serum
```

### All results for one experiment, ordered by timepoint (gross + net ammonium, final pH)

```sql
SELECT time_post_reaction_days,
       "gross_ammonium_concentration_mM",
       net_ammonium_concentration,
       final_ph
FROM v_results_scalar
WHERE experiment_id = 'SERUM_001a'
ORDER BY time_post_reaction_days;
```

```
 time_post_reaction_days | gross_ammonium_concentration_mM | net_ammonium_concentration | final_ph
--------------------------+----------------------------------+-----------------------------+----------
                        0 |                              0.3 |                         0.1 |     7.20
                        7 |                              2.1 |                         1.9 |     7.45
                       14 |                              3.8 |                         3.6 |     7.51
```

`net_ammonium_concentration` is a view column that already computes
`GREATEST(0, gross − background)` for you — you don't need to subtract background
yourself (see `docs/POWERBI_MODEL.md` Notes).

### The flattened fact table for one experiment (scalar + H2 + ICP together)

> **Note:** `.claude/rules/MODELS.md` still documents a view called
> `v_primary_experiment_results` as "the" flattened fact table. **That view no longer
> exists** — `database/event_listeners.py` explicitly drops it and does not recreate it.
> If you go looking for it in `\dv`, you won't find it. Use the join below instead, which
> covers the same ground across the three views that replaced it.

```sql
SELECT s.experiment_id,
       s.time_post_reaction_days,
       s."gross_ammonium_concentration_mM",
       s.net_ammonium_concentration,
       s.final_ph,
       h.h2_concentration,
       h.h2_micromoles,
       h.h2_grams_per_ton_yield,
       i.fe_ppm,
       i.ni_ppm,
       i.cu_ppm
FROM v_results_scalar s
LEFT JOIN v_results_h2  h ON h.result_id = s.result_id
LEFT JOIN v_results_icp i ON i.result_id = s.result_id
WHERE s.experiment_id = 'SERUM_001a'
ORDER BY s.time_post_reaction_days;
```

```
 experiment_id | time_post_reaction_days | gross_ammonium_concentration_mM | net_ammonium_concentration | final_ph | h2_concentration | h2_micromoles | h2_grams_per_ton_yield | fe_ppm | ni_ppm | cu_ppm
---------------+---------------------------+----------------------------------+-----------------------------+----------+-------------------+----------------+-------------------------+--------+--------+--------
 SERUM_001a    |                         0 |                              0.3 |                         0.1 |     7.20 |               120 |           45.2 |                    0.8  |  980.0 |   12.4 |    3.1
 SERUM_001a    |                         7 |                              2.1 |                         1.9 |     7.45 |               340 |          128.6 |                    2.3  | 1020.0 |   14.1 |    3.4
```

The `LEFT JOIN`s matter here: `v_results_h2` only includes rows with an H2 measurement, and
`v_results_icp` only includes rows with ICP data. An inner join would silently drop
timepoints that have scalar data but no H2 or ICP reading yet.

### Replicate-set statistics: mean ± SD ammonium and H2 across a/b/c

```sql
SELECT time_post_reaction_bucket_days,
       n_replicates,
       "mean_gross_ammonium_mM",
       "sd_gross_ammonium_mM",
       mean_h2_ppm,
       sd_h2_ppm
FROM v_results_scalar_rollup
WHERE base_experiment_id = 'SERUM_001'
ORDER BY time_post_reaction_bucket_days;
```

```
 time_post_reaction_bucket_days | n_replicates | mean_gross_ammonium_mM | sd_gross_ammonium_mM | mean_h2_ppm | sd_h2_ppm
----------------------------------+---------------+--------------------------+------------------------+--------------+------------
                               0 |            3 |                     0.29 |                   0.06 |          115 |         12
                               7 |            3 |                     2.05 |                   0.14 |          335 |         18
```

Semantics to know before you trust this (full detail in `.claude/rules/MODELS.md`):

- `n_replicates` and every mean/SD column **exclude** experiments flagged `is_outlier`
  (a bad vial — leak, cracked septum). A flagged experiment still shows up if you query
  `v_results_scalar` directly for its own `experiment_id`; it just drops out of this rollup.
- The group's un-lettered parent experiment (e.g. `SERUM_001` itself, if it has its own
  results) is counted in these statistics exactly like `SERUM_001a/b/c` — there's no
  separate way to exclude it other than flagging it `is_outlier` too.
- `sd_*` is `NULL` when `n_replicates = 1` (nothing to compute a spread from) — that's
  expected, not missing data.

### H2 results: ppm → micromoles → g/ton

```sql
SELECT experiment_id, time_post_reaction_days, h2_concentration,
       h2_concentration_unit, h2_micromoles, h2_grams_per_ton_yield
FROM v_results_h2
WHERE experiment_id = 'HPHT_001'
ORDER BY time_post_reaction_days;
```

```
 experiment_id | time_post_reaction_days | h2_concentration | h2_concentration_unit | h2_micromoles | h2_grams_per_ton_yield
---------------+---------------------------+-------------------+-------------------------+----------------+-------------------------
 HPHT_001      |                         0 |               210 | ppm                     |           78.4 |                    1.4
 HPHT_001      |                         7 |               560 | ppm                     |          208.9 |                    3.7
```

`h2_concentration` is always stored in ppm (vol/vol) — `h2_concentration_unit` will always
read `'ppm'`, but it's included so a query never has to assume the unit silently.

### ICP elements for one experiment (pulling a subset of columns)

```sql
SELECT experiment_id, time_post_reaction_days, fe_ppm, ni_ppm, cu_ppm, mo_ppm
FROM v_results_icp
WHERE experiment_id = 'HPHT_001'
ORDER BY time_post_reaction_days;
```

```
 experiment_id | time_post_reaction_days | fe_ppm | ni_ppm | cu_ppm | mo_ppm
---------------+---------------------------+--------+--------+--------+--------
 HPHT_001      |                         0 |  980.0 |   12.4 |    3.1 |   0.8
 HPHT_001      |                         7 | 1020.0 |   14.1 |    3.4 |   0.9
```

All 27 element columns follow the same `<symbol>_ppm` naming — `\d+ v_results_icp` will
show you the full list.

### Experiments filtered by condition (temperature range, type, feedstock)

```sql
SELECT e.experiment_id, e.status, e.researcher,
       ec.temperature_c, ec.experiment_type, ec.feedstock
FROM v_experiment_conditions ec
JOIN v_experiments e ON e.experiment_id = ec.experiment_id
WHERE ec.temperature_c BETWEEN 60 AND 90
  AND ec.experiment_type = 'HPHT'
  AND ec.feedstock = 'Nitrate'
ORDER BY ec.temperature_c;
```

```
 experiment_id | status    | researcher | temperature_c | experiment_type | feedstock
---------------+-----------+------------+-----------------+-------------------+-----------
 HPHT_001      | COMPLETED | M. Hearl   |              75 | HPHT              | Nitrate
 HPHT_004      | ONGOING   | A. Chen    |              82 | HPHT              | Nitrate
```

This is the `JOIN` concept from Section 6 in practice: `v_experiment_conditions` doesn't
carry `status`/`researcher`, so we bring those in from `v_experiments` by matching on the
shared `experiment_id`.

### Additives for a set of experiments

```sql
SELECT experiment_id, additive_names
FROM v_experiment_additive_names_summary
WHERE experiment_id IN ('SERUM_001a', 'SERUM_001b', 'SERUM_001c');
```

```
 experiment_id | additive_names
----------------+------------------------------
 SERUM_001a     | Magnetite, Nickel Chloride
 SERUM_001b     | Magnetite, Nickel Chloride
 SERUM_001c     |
```

`SERUM_001c` shows a blank because `additive_names` is `NULL` for experiments with no
additives — that's not a query error.

### Everything for one geological sample

```sql
SELECT si.sample_id, si.rock_classification, si.locality, si.characterized,
       e.experiment_id, e.status, e.date, e.experiment_type
FROM v_sample_info si
JOIN v_experiments e ON e.sample_id = si.sample_id
WHERE si.sample_id = 'TUS-CT3'
ORDER BY e.date;
```

```
 sample_id | rock_classification | locality      | characterized | experiment_id | status    |          date          | experiment_type
-----------+-----------------------+-----------------+------------------+----------------+-----------+-------------------------+------------------
 TUS-CT3   | Serpentinite          | Tuscarora, WV  | t              | HPHT_001      | COMPLETED | 2026-07-20 00:00:00+00 | HPHT
 TUS-CT3   | Serpentinite          | Tuscarora, WV  | t              | HPHT_003      | ONGOING   | 2026-07-25 00:00:00+00 | HPHT
```

(`sample_info` has more fields worth knowing about for core samples on loan — `well_name`,
`core_lender`, `core_interval_ft`, `on_loan_return_date` — see `.claude/rules/MODELS.md`.)

### A replicate group's time-course, at the rollup grain

```sql
SELECT time_post_reaction_bucket_days,
       n_replicates,
       "mean_gross_ammonium_mM",
       mean_h2_ppm
FROM v_results_scalar_rollup
WHERE base_experiment_id = 'SERUM_001'
ORDER BY time_post_reaction_bucket_days;
```

```
 time_post_reaction_bucket_days | n_replicates | mean_gross_ammonium_mM | mean_h2_ppm
----------------------------------+---------------+--------------------------+--------------
                               0 |            3 |                     0.29 |          115
                               7 |            3 |                     2.05 |          335
                              14 |            3 |                     3.71 |          520
```

**Don't build this same time-course by pulling `cumulative_time_post_reaction_days` (or
any cumulative column) off a single lettered replicate**, especially a `-t<days>` vial
like `SERUM_001a-t7`. Per `.claude/rules/MODELS.md`, cumulative columns in `v_results_scalar`
are computed **per experiment_id**, not per replicate group — a `-t` vial typically has
exactly one result row, so its own cumulative value is just that one row, and it never
accumulates across its siblings' timepoints. The rollup view above, grouped by
`base_experiment_id`, is the correct place to read a time course across a replicate set.

---

## 8. Exporting to CSV with `\copy`

You'll usually want a query's result as a file you can open in Excel, Origin, or plot from
Python later. Use `\copy` — not plain SQL `COPY`.

**Why `\copy` and not `COPY`:** `COPY` is a server-side SQL command — it writes the file on
the *database server's* disk (the lab PC), which you don't have filesystem access to and
which wouldn't help you anyway. `\copy` is a **psql** command that runs the query on the
server but streams the result back to psql, which then writes the file on **your own
laptop**. Since everyone here is connecting from their own machine, `\copy` is what you
want essentially every time.

```sql
\copy (SELECT time_post_reaction_days, "gross_ammonium_concentration_mM", net_ammonium_concentration, final_ph FROM v_results_scalar WHERE experiment_id = 'SERUM_001a' ORDER BY time_post_reaction_days) TO 'C:/Users/yourname/Desktop/serum_001a_results.csv' WITH CSV HEADER;
```

On macOS, use a normal Unix-style path instead:

```sql
\copy (SELECT ...) TO '/Users/yourname/Desktop/serum_001a_results.csv' WITH CSV HEADER;
```

Notes:
- `\copy` is one line — the whole thing, including the `SELECT`, goes between the parentheses.
- `WITH CSV HEADER` includes column names as the first row; leave it off and you just get data rows.
- Forward slashes (`C:/Users/...`) work fine in psql on Windows even though the OS also
  accepts backslashes — psql is more predictable with forward slashes, so use them.

---

## 9. Read-only — why you can't write from here

**Every example in this guide is a `SELECT`. That is not a style preference — it is a hard
rule.** `INSERT`, `UPDATE`, `DELETE`, and every DDL statement (`CREATE`, `ALTER`, `DROP`,
`TRUNCATE`, etc.) are forbidden from psql. Your read-only account's database permissions
won't allow them anyway, but the reason goes deeper than permissions:

- Several fields you'll see in these tables — ammonium yield, H2 yield, ferrous iron yield,
  catalyst loadings — are **not** entered by hand. They're computed by the calculation
  engine in `backend/services/calculations/` immediately after every write the *app* makes
  through the ORM, and stored back to the row. A raw SQL `UPDATE` from psql would change
  the input fields but never trigger that recalculation, silently leaving the derived
  fields wrong and out of sync with what you just changed.
- `ModificationsLog` — the audit trail of who changed what — only records changes made
  **through the app**. A raw SQL write from psql leaves no trace there at all.

**Data corrections always go through the app UI**, never psql, so both the derived fields
and the audit trail stay correct. If you spot bad data while exploring here, note the
`experiment_id`/timepoint and fix it in the app (or ask whoever owns that experiment to).

---

## 10. Common gotchas

- **Case-sensitive quoted identifiers.** Most column names here are plain lowercase
  (`experiment_id`, `final_ph`) and need no special handling. But some carry mixed-case
  units in their name — `"gross_ammonium_concentration_mM"`, `"final_dissolved_oxygen_mg_L"`,
  `"co2_partial_pressure_MPa"` — and Postgres **folds unquoted identifiers to lowercase**.
  Typing `gross_ammonium_concentration_mM` without quotes actually looks for
  `gross_ammonium_concentration_mm` and fails with "column does not exist." Whenever a
  column name has an uppercase letter in it, wrap it in double quotes and match the case
  exactly, as every example in Section 7 does.
- **`NULL` is not zero.** A `NULL` H2 or ICP value means that measurement wasn't taken for
  that timepoint, not that it measured as zero. Aggregate functions like `AVG()` already
  skip `NULL`s (which is usually what you want), but don't yourself substitute `0` for a
  blank when eyeballing or exporting data.
- **Forgetting a `WHERE` on a large table.** `SELECT * FROM v_results_icp;` with no filter
  returns every ICP timepoint for every experiment ever run. Always scope to an
  `experiment_id` (or add `LIMIT 20` while you're still figuring out what you want) — see
  [Section 5](#5-psql-survival-guide) for how to cancel it if you forget.
- **`is_outlier` rows behave differently depending on which view you're in.** A flagged
  experiment (bad vial) still appears in every per-row view — `v_results_scalar`,
  `v_results_h2`, `v_results_icp` — and on its own page in the app. It is excluded from
  `v_results_scalar_rollup`'s aggregates, **including `n_replicates`**. Seeing a lower
  `n_replicates` in the rollup than the number of vials you know exist for a group is
  expected in that case, not a bug.

---

## 11. Where to get help

- **Access, credentials, or firewall issues:** ask Mat.
- **Schema or "what does this field mean" questions:** `.claude/rules/MODELS.md` (full
  field reference) and `docs/POWERBI_MODEL.md` (full view/column reference).
- **Derived-field formulas** (how yields, H2 amounts, etc. are calculated): `docs/CALCULATIONS.md`.
- **Data looks wrong:** fix it in the app, not here — see [Section 9](#9-read-only--why-you-cant-write-from-here).

---

## 12. Administrator setup (one time, Mat only)

**Researchers: nothing below this line is for you — skip it.** This section is the setup
Mat runs once, directly on the lab PC, to create the read-only role this whole guide
depends on. No dedicated read-only role currently exists in this repo or on the lab PC —
this is a new role, proposed from scratch to satisfy the "read-only alternative to Power
BI" requirement.

Everything below is documentation and copy-pasteable SQL/config for Mat to run manually.
**Nothing in this section is executed by any script, migration, or agent** — the production
database is not touched by anyone else per `docs/ENVIRONMENT.md`.

Placeholders used below — fill these in yourself, they are never real values in this repo:

- `<READONLY_PASSWORD>` — a password you generate and distribute directly to each
  teammate (Slack DM, in person, a password manager share — never Git, never this file)
- `<LAB_SUBNET>` — the lab's LAN CIDR range, e.g. `192.168.1.0/24`
- `<LAB_PC_HOSTNAME>` / `<LAB_PC_IP>` — the lab PC's own network name/address

### 12.1 Create the role

Connect as a superuser (`psql -U postgres -d experiments`) and run:

```sql
CREATE ROLE reporting_reader WITH LOGIN PASSWORD '<READONLY_PASSWORD>'
    NOSUPERUSER NOCREATEDB NOCREATEROLE;

GRANT CONNECT ON DATABASE experiments TO reporting_reader;
GRANT USAGE ON SCHEMA public TO reporting_reader;

-- Grants every table AND every view in the public schema — in PostgreSQL,
-- "ALL TABLES" already includes views (and materialized views), so this one
-- statement covers both the base tables and every v_* reporting view. No
-- separate grant is needed for views.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO reporting_reader;

-- So a table or view added *after* this point is readable without
-- having to re-run the GRANT above.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO reporting_reader;
```

Rename `reporting_reader` if you'd prefer a different role name — nothing else in this
guide depends on that exact name.

### 12.2 Allow LAN connections

Two separate files, two separate purposes — don't confuse them:

**`postgresql.conf`** controls which network interfaces Postgres listens on at all. It does
**not** accept a subnet/CIDR — only specific IP addresses (or `*` for "every interface").
To accept connections from anywhere but `localhost`, add the lab PC's own LAN IP:

```
listen_addresses = 'localhost,<LAB_PC_IP>'
```

**`pg_hba.conf`** is what actually restricts *who* is allowed to connect from where — this
is where the lab subnet belongs, not `listen_addresses`. Add a line scoped to the lab
subnet only (never `0.0.0.0/0`):

```
host    experiments    reporting_reader    <LAB_SUBNET>    scram-sha-256
```

**Restart vs. reload — they're different:**
- `listen_addresses` only takes effect after a **full PostgreSQL service restart**
  (`services.msc` → restart the PostgreSQL service, or `net stop postgresql-x64-16` /
  `net start postgresql-x64-16`, adjusting the service name for your installed version).
- `pg_hba.conf` only needs a **reload**, which doesn't drop existing connections:
  ```sql
  SELECT pg_reload_conf();
  ```
  (run from any already-connected superuser `psql` session), or restart the service if
  that's easier to remember.

### 12.3 Windows Firewall

Postgres listening on the right address isn't enough — Windows Firewall on the lab PC must
also allow inbound port 5432 from the lab subnet:

```powershell
New-NetFirewallRule -DisplayName "PostgreSQL LAN reporting access" `
    -Direction Inbound -Protocol TCP -LocalPort 5432 `
    -RemoteAddress <LAB_SUBNET> -Action Allow
```

### 12.4 Distributing access

Give each teammate: the lab PC hostname/IP, port `5432`, database name `experiments`,
username `reporting_reader`, and the password — through a channel that isn't Git or a
committed file. Point them at Section 2 onward of this guide for everything after that.
