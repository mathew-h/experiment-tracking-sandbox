# User Manual

The Experiment Tracking System is a web application for the Addis Energy geochemistry team to log and manage lab experiments, track samples and chemicals, upload bulk analytical data, and monitor reactor status. It runs on the lab PC and is accessible from any browser on the local network.

For detailed guides on specific features, see the sub-guides linked in the navigation below.

---

## Sub-Guides

- [Bulk Uploads Guide](BULK_UPLOADS.md) — All 12 upload types, templates, and field mappings
- [Dashboard Guide](DASHBOARD.md) — Reactor grid, status changes, and experiment cards

---

## Getting Started

1. Open a browser and navigate to `http://<lab-pc-hostname>:8000`
2. Log in with your `@addisenergy.com` Google or email account.
3. If you do not have an account, click **Register** and fill in your details. Your account must be approved by an administrator before you can log in. Contact the lab admin after registering.

---

## Main Pages

| Page | What it does |
|------|--------------|
| **Dashboard** (`/dashboard`) | Reactor grid showing all ONGOING experiments. Click a status badge to change an experiment's status (Ongoing → Completed or Cancelled). |
| **Experiments** (`/experiments`) | List all experiments. Click an experiment to open its detail view with Conditions, Results, Notes, and XRD tabs. |
| **Core Floods** (`/core-floods`) | One row per core flood run, with a run page for samples and cleanup. See [Core Floods](#core-floods) below. |
| **New Experiment** (`/experiments/new`) | 4-step guided form to create a new experiment: basic info, conditions, chemical additives, and confirmation. |
| **Bulk Uploads** (`/bulk-uploads`) | Accordion panel for uploading analytical data in bulk (solution chemistry, ICP-OES, XRD, pXRF, and more). See the [Bulk Uploads Guide](BULK_UPLOADS.md). |
| **Samples** (`/samples`) | Browse and manage geological sample inventory. |
| **Chemicals** (`/chemicals`) | Browse the reagent/compound inventory used in experiment conditions. |
| **Data Export** (`/data-export`) | Filter experiments (status, type, ID, sample, reactor, description, additive, researcher, dates), tick any number, and download one Excel workbook for all of them. |
| **Notes review** (`/notes/review`) | Global queue of notes flagged for review after the typed-notes migration. Filter by researcher, experiment, type or text; select rows (or every row reading the same text) and mark reviewed, retype, or delete them in one audited action. |

---

## Core Floods

A core flood run is split across `-N` segment experiments (`CF_020`, `CF_020-2`, ...). The **Core Floods** page treats the whole run as one record.

**List.** One row per run: rig, segment count, sample count, last sample date, cumulative H₂ (g/t) and a warnings badge. It opens on **Active** (runs with an ONGOING segment); **All** shows every run. Type in the search box to filter by run ID.

**Run page.** Click a run to open it. The header shows the rig, the ONGOING segment, cumulative H₂ and pore volumes to date. Below it:

- **Segments:** one row per segment, with a link to its experiment page, an editable status, an inline description and **Rename**. Pore volume is set from **Data checks** or on each experiment's Conditions tab.
- **Samples:** every sample across all segments in time order. **Cum. day** is the cumulative day since the run started. A flow rate of 0 shows a **HOLD** badge. Blanks and bypass samples sit in a separate **Side samples** section with no cumulative columns. Click a row to edit it.
- **Cleanup:** one line per data problem the run has (several roots, several ONGOING segments, missing pore volume or description, samples with no flow rate), each with its fix. The segment's ID sits beside each per-segment control. **Set pore volume for all segments** writes one value to every segment that lacks it.
- **ICP over time:** ICP ppm against cumulative day for the run's main-line samples, with a dashed marker where each segment starts. It works the same way as on the Results tab (see "Plot ICP concentrations over time" below).

**Export.** **Export all** in the run header downloads one Excel workbook for the whole run: every segment and side sample, with a Core Flood tab of flow, pressures and cumulative values.

**Add a sample.** Click **+ Add sample**. With one ONGOING segment it is used automatically; otherwise pick a segment. Day here is the number of days since the chosen segment started (not the cumulative day shown in the table); it is filled from the sample date and the segment's start, and you can change it (a segment with no start date needs a Day typed in). If that segment already has a sample on the same day, a warning appears and the button becomes **Replace existing sample**: saving replaces that sample in the run. Enter a fractional day (for example 11.5) to keep both. The GC run date follows the sample date until you edit it, and flow rate, N₂ flow, inlet pressure and outlet pressure are filled from the previous sample. Flow rate is the rate since the previous sample: **enter 0 for a hold**. Enter gas pressure in **psi**; it is stored in MPa. When editing, only the fields you change are saved, and Day cannot be changed.

---

## Experiment Lifecycle

Experiments move through a defined lifecycle from creation to completion:

1. **Create** — Use the New Experiment form (`/experiments/new`) to record the basic metadata: experiment ID, researcher, date, and the associated sample.
2. **Add Conditions** — Open the experiment's detail view and complete the Conditions tab: temperature, pH, reactor number, rock mass, water volume, and chemical additives.
3. **Add Results** — Upload analytical data via Bulk Uploads (preferred for multiple experiments at once) or enter results manually on the Results tab of the experiment detail view. The Results tab and the grouped rollup **display** hydrogen metrics (H₂ ppm/µmol/g/t, Fe²⁺ → H₂ %, pH, conductivity); ammonium fields are still recorded and stored — they remain in the database and Power BI datasets — but are no longer shown in these two on-screen tables. See `REPLICATES.md` for details.
4. **Analyze** — Use the XRD tab (called Analysis before November 2026) to attach external analyses (XRD, pXRF, SEM, elemental) or view Aeris XRD time-series data.
5. **Complete** — When the experiment is finished, change the status to **Completed** from the Dashboard or the experiment detail header. Cancelled experiments can be marked **Cancelled**.

---

## Common Tasks

| Task | How |
|------|-----|
| Create an experiment | Navigate to **New Experiment**, fill the 4-step form |
| Upload solution chemistry results | **Bulk Uploads** → Solution Chemistry → download template → fill in values → upload |
| Update experiment status | **Dashboard** → click the status badge on a reactor card → select new status |
| Check Water:Rock Ratio | Open an experiment → **Conditions** tab |
| Upload ICP data | **Bulk Uploads** → ICP-OES Data → upload the instrument CSV |
| View all results for an experiment | Open an experiment → **Results** tab |
| Plot ICP concentrations over time | Open any experiment with ICP data → **Results** tab → **ICP over time**, below the results table (not shown when the series has no ICP). It plots ppm against cumulative day for the experiment's whole series: every segment, side sample and timepoint vial sharing its base ID. Dashed vertical lines mark where each chained segment starts. Click element chips to add or remove lines; **All** toggles every element; **Log scale** switches the y axis. Ca, Si, Fe, Ni, Mg, Mn and Al are on by default (Cu is off). The first four lines are solid; from the fifth on, lines reuse the four colours with a dash pattern, and the legend shows each line's colour and dash. The core flood run page has the same chart |
| Add or fix an experiment's description | Fill in "Experiment Description" in step 1 of **New Experiment**; it is saved as the experiment's Description note and shows on the reactor card and detail header. Later, open the experiment and click the description under its ID to edit it in place — or click **Add description** if it has none. Only one Description is allowed per experiment |
| Read or write notes on an experiment | Open an experiment → **Notes** tab. Every note — experiment-level and timepoint-scoped — is one timeline, newest first, each with a type badge, a `T+N` chip (on a timepoint) or a date chip (a dated modification), and its author. Filter by type or "Review queue only". To add one, pick a type: an Observation may name a timepoint; a Result note must; a Modification needs a timepoint **or** a date (defaults to today); a Description has neither |
| Change a note's type | Open an experiment → **Notes** tab → use the type dropdown on the note. Experiment-level notes can be Observation or Description; notes on a timepoint can be Observation, Modification or Result note; a dated note can be Observation, Modification or Description. Only one Description is allowed per experiment |
| Export an experiment's data to Excel | Open an experiment (or a run on **Core Floods**) → **Export all** in the header. One workbook downloads with Results, Conditions, Additives, Notes and Summary tabs (plus Core Flood for core flood runs), covering the experiment and every segment and side sample in its series. Values are the same as the Power BI report |
| Export several experiments to one Excel workbook | **Data Export** → set filters (for example an Additive or a Researcher) → tick the experiments (**Select all shown** ticks every row listed; ticks survive changing the filters) → leave **Include whole series** on to bring each experiment's whole series, or untick it for just the ticked ones and their timepoint vials → **Export**. The page lists up to 500 matches; narrow the filters if it says "Showing N of M". An export is limited to 500 experiments after series expansion |
| Attach an external analysis file | Open an experiment → **XRD** tab → Add Analysis |
| Search for a sample | Navigate to **Samples**, use the search bar |
| Add a new user (admin only) | Run `python scripts/manage_users.py create <email> <password> <display_name>` on the lab PC, then `approve <request_id>` |
