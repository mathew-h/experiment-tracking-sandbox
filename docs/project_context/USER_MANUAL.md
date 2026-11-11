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

The sidebar lists these pages in this order (issue #159): the pages you start from first, then the entry and reference pages.

| Page | What it does |
|------|--------------|
| **Dashboard** (`/`, also `/dashboard`) | Reactor grid showing all ONGOING experiments. Click a status badge to change an experiment's status (Ongoing → Completed or Cancelled). |
| **Experiments** (`/experiments`) | List all experiments. Click an experiment to open its detail view with Conditions, Results, Notes, and XRD tabs. The open tab is part of the address (`/experiments/HPHT_297-2?tab=results`), so a copied link opens the same tab; links from Recent Activity result changes, a group page's Results count and an ICP upload open the Results tab. A row marked **group** opens its replicate group page (click the "replicates" chip instead to list the vials in place). On an HPHT or core flood row, the **Reactor** number links to the run page. The **Experiment start date** and **Last sample date** cards (Begin/End, with Last 7 days / Last 30 days / This month / Last month quick ranges on Last sample date) work as on Data Export; the **Start date** and **Last sample** columns show them, and a group row shows the latest sample date of any of its experiments. |
| **HPHT** (`/hpht`) | One row per HPHT run, with a run page for samples, charts and segments. See [HPHT runs](#hpht-runs) below. |
| **Core Floods** (`/core-floods`) | One row per core flood run, with a run page for samples and cleanup. See [Core Floods](#core-floods) below. |
| **New Experiment** (`/experiments/new`) | 4-step guided form to create a new experiment: basic info, conditions, chemical additives, and confirmation. |
| **Bulk Uploads** (`/bulk-uploads`) | Accordion panel for uploading analytical data in bulk (solution chemistry, ICP-OES, XRD, pXRF, and more). See the [Bulk Uploads Guide](BULK_UPLOADS.md). |
| **Samples** (`/samples`) | Browse and manage geological sample inventory. |
| **Chemicals** (`/chemicals`) | Browse the reagent/compound inventory used in experiment conditions. |
| **Data Export** (`/data-export`) | Filter experiments (status, type, ID, sample, reactor, description, additive, researcher, experiment start date, last sample date), tick any number, and download one Excel workbook for all of them. |
| **Notes review** (`/notes/review`) | Global queue of notes flagged for review after the typed-notes migration. Filter by researcher, experiment, type or text; select rows (or every row reading the same text) and mark reviewed, retype, or delete them in one audited action. |

**A wrong address.** A URL that matches no page shows **Page not found** with the address you tried and links to Dashboard, Experiments, HPHT and Core Floods (it used to send you to the Dashboard without a word). A deleted or mistyped experiment or replicate group shows "not found" with a **Back to Experiments** link.

---

## Core Floods

A core flood run is split across `-N` segment experiments (`CF_020`, `CF_020-2`, ...). The **Core Floods** page treats the whole run as one record.

**List.** One row per run: rig, segment count, sample count, last sample date, cumulative H₂ (g/t) and a warnings badge. It opens on **Active** (runs with an ONGOING segment); **All** shows every run. Type in the search box to filter by run ID.

**Run page.** Click a run to open it. The header shows the rig, the ONGOING segment, cumulative H₂ and pore volumes to date. Below it:

- **Segments:** one row per segment, with a link to its experiment page, an editable status, an inline description, **Rename** and **Delete**. It is open when the run has more than one segment, and its header lists every segment ID as a link. **Delete** asks you to type the segment's ID, like deleting from the experiment page; deleting a run's last segment returns you to the Core Floods list. Pore volume is set from **Data checks** or on each experiment's Conditions tab.
- **Samples:** every sample across all segments, newest first, in the same table as the HPHT run page and the Results tab (see "The samples table" below). After the shared columns comes a **Core flood** group: Flow, Perm. flow, Inlet psi and Outlet psi. A flow rate of 0 shows a **HOLD** badge and a permeability-test rate a **PERM** badge. There is no Fe²⁺ → H₂ column, because core flood samples do not carry one. Blanks and bypass samples sit in a separate **Side samples** section with the same columns minus the running totals. Click a row to edit the sample.
- **Cleanup:** one line per data problem the run has (several roots, several ONGOING segments, missing pore volume or description, samples with no flow rate), each with its fix. The segment's ID sits beside each per-segment control. **Set pore volume for all segments** writes one value to every segment that lacks it.
- **ICP over time** (collapsed, with the sample count): ICP ppm against cumulative day for the run's main-line samples, with a dashed marker where each segment starts. It works the same way as on the Results tab (see "Plot ICP concentrations over time" below).

**From the Results tab.** A core flood segment's Results tab lists its samples (the shared columns only) but has no **+ Add Results**, and clicking a row does nothing: core flood samples record flow and permeability, which only the run page captures. Use **Add or edit samples on the run page** instead.

**The samples table.** The experiment page's Results tab, the HPHT run page and the Core Flood run page show samples in one table, so a sample reads the same wherever you meet it:

- **Columns:** Date, Day, Tube and Result note; then **GC** (H₂ ppm, H₂ µmol, H₂ g/t, and Fe²⁺ → H₂ % except on core floods) and **Solution** (pH, Cond.). The run pages add **Segment** as the first column (click it to open that segment), Cum. H₂ g/t and g/t/day under GC, and Liq mL under Solution. Segment and Date stay in view when the table scrolls sideways (Date alone on the Results tab).
- **Day:** on a run page it is the cumulative day since the run started; on the Results tab it is that segment's own day, and ★ marks the primary result for the timepoint.
- **Flags** sit after the result note. **ICP** (blue) shows the sample's ICP-OES readings, **MOD** (amber) its modification note, and **DETAILS** its instrument run dates (with a warning when an H₂ reading has no GC run date), every note on the timepoint and, on the Results tab, the DO and Fe(II) values. Click a flag to show its section under the sample and again to hide it.
- **Editing:** click anywhere else on a row to edit the sample. On the Results tab only primary results can be edited.

**Export.** **Export all** in the run header downloads one Excel workbook for the whole run: every segment and side sample, with a Core Flood tab of flow, pressures and cumulative values.

**From a segment's experiment page.** The breadcrumb reads **Experiments › Run CF_020 › CF_020-5_Bypass1**, and the strip under the ID lists every segment and side sample of the run (side samples follow their segment). Click **Run CF_020** or any segment in the strip to move around the run.

**Segment IDs in the address.** `/core-floods/CF_020-3` (any segment or side-sample ID) opens run CF_020, and the address changes to `/core-floods/CF_020`. An ID that is not a core flood shows "No core flood run …" with links back to the list and to that experiment's page.

**Add a sample.** Click **+ Add sample**. With one ONGOING segment it is used automatically; otherwise pick a segment. Day here is the number of days since the chosen segment started (not the cumulative day shown in the table); it is filled from the sample date and the segment's start, and you can change it (a segment with no start date needs a Day typed in). If that segment already has a sample on the same day, a warning appears and the button becomes **Replace existing sample**: saving replaces that sample in the run. Enter a fractional day (for example 11.5) to keep both. The GC run date follows the sample date until you edit it, and flow rate, N₂ flow, inlet pressure and outlet pressure are filled from the previous sample. Flow rate is the rate since the previous sample: **enter 0 for a hold**. Enter gas pressure in **psi**; it is stored in MPa. When editing, only the fields you change are saved, and Day cannot be changed.

---

## HPHT runs

An HPHT run is every experiment sharing a base ID: the first segment (`HPHT_297`), later segments (`HPHT_297-2`) and side samples such as `HPHT_068_Acidified`. The **HPHT** page (in the sidebar below Experiments, above Core Floods) treats the whole run as one record. It covers both the R vessels and the Parr vessels (P01–P06).

**List.** One row per run: description, reactor slot (`R07`, `P03`), sample count, last sample date, cumulative H₂ (g/t) and status. It opens on **Active** (runs with an ONGOING segment); **All** shows every run. Type in the search box to filter by run ID or description. A run with no reactor (for example HPHT_Synth_001) shows an empty Reactor cell.

**Run page.** Click a run to open it. From top to bottom:

- **Header:** base ID, description, reactor slot and the ONGOING segment, with **Export all** and **+ Add sample**.
- **Conditions:** temperature, reaction pressure, rock mass, water volume, W:R, catalyst, feedstock, sample ID, start date and additives of the latest segment. This card is read-only; **Edit on Conditions tab** opens that segment's experiment page.
- **Samples:** every sample across all segments, newest first, in the shared samples table (see "The samples table" below). Click a row to edit the sample.
- **Run to date:** three charts against cumulative day: cumulative H₂ (g/t), H₂ per day for each interval, and cumulative Fe²⁺ → H₂ yield (%). A dashed line marks where each later segment starts. Side samples are left out. A gap means that interval has no value (for example two samples on the same day); it is not a zero.
- **Side samples** (collapsed): the run's `_Text` variants with their raw values only, no running totals.
- **ICP over time** (collapsed): the same ICP chart as on the Results tab.
- **Segments** (open when the run has more than one segment): each segment's status, description, **Rename** and **Delete**, as on the Core Flood page. The header lists every segment ID as a link.

Every segment ID on the page (the **Segment** column, the ONGOING badge, the Segments header) links to that experiment's page; clicking one in the Samples table opens the experiment, not the sample editor. `/hpht/HPHT_297-2` opens run HPHT_297 and the address changes to `/hpht/HPHT_297`.
- **Data checks** (only when there is a problem): several roots, several ONGOING segments, a missing description, or a segment whose ID does not follow the run's base ID.

NH₃ is not shown on this page. It stays on the experiment's Results tab and in Power BI.

**Add a sample.** Click **+ Add sample**. It opens the same form as **+ Add Results** on the experiment page, titled **Add sample** (**Edit sample** when editing), with a **Save sample** button. With one ONGOING segment the sample goes there, and the form names it. Otherwise a **Segment** select appears at the top. **Day** counts from the chosen segment's start date, not from the start of the run. Edits work the same way; Day cannot be changed.

**Other ways in.** On any HPHT segment's experiment page, the breadcrumb reads **Experiments › Run HPHT_297 › HPHT_297-2**: click **Run HPHT_297** to open the run. The strip under the ID lists every segment of the run, so a sibling is one click away, and **Reactor R07** in the line below the description also opens the run. On the Dashboard, clicking any occupied reactor (R, P or CF, whatever its status) shows **Open run page** as the main button.

---

## Experiment Lifecycle

Experiments move through a defined lifecycle from creation to completion:

1. **Create** — Use the New Experiment form (`/experiments/new`) to record the basic metadata: experiment ID, researcher, date, and the associated sample.
2. **Add Conditions** — Open the experiment's detail view and complete the Conditions tab: temperature, pH, reactor number, rock mass, water volume, and chemical additives.
3. **Add Results** — Upload analytical data via Bulk Uploads (preferred for multiple experiments at once) or enter results manually on the Results tab of the experiment detail view. The Results tab and the grouped rollup **display** hydrogen metrics (H₂ ppm/µmol/g/t, Fe²⁺ → H₂ %, pH, conductivity); ammonium fields are still recorded and stored — they remain in the database and Power BI datasets — but are no longer shown in these two on-screen tables. See `REPLICATES.md` for details.
4. **Analyze** — Use the XRD tab (called Analysis before November 2026) to attach external analyses (XRD, pXRF, SEM, elemental) or view Aeris XRD time-series data.
5. **Complete** — When the experiment is finished, change the status to **Completed** from the Dashboard, a run page's Segments table, or the status select next to the ID in the experiment detail header. Cancelled experiments can be marked **Cancelled**.

---

## Common Tasks

| Task | How |
|------|-----|
| Create an experiment | Navigate to **New Experiment**, fill the 4-step form |
| Upload solution chemistry results | **Bulk Uploads** → Solution Chemistry → download template → fill in values → upload |
| Update experiment status | **Dashboard** → click the status badge on a reactor card → select new status |
| Check Water:Rock Ratio | Open an experiment → **Conditions** tab |
| Upload ICP data | **Bulk Uploads** → ICP-OES Data → upload the instrument CSV. The row then lists every experiment and day it wrote to; click one to check its Results tab |
| View all results for an experiment | Open an experiment → **Results** tab |
| Plot ICP concentrations over time | Open any experiment with ICP data → **Results** tab → **ICP over time**, below the results table (not shown when the series has no ICP). It opens collapsed, as on both run pages; its header shows how many samples and experiments it covers, and a click opens the chart. It plots ppm against cumulative day for the experiment's whole series: every segment, side sample and timepoint vial sharing its base ID. Dashed vertical lines mark where each chained segment starts. Click element chips to add or remove lines; **All** toggles every element; **Log scale** switches the y axis. Ca, Si, Fe, Ni, Mg, Mn and Al are on by default (Cu is off). The first four lines are solid; from the fifth on, lines reuse the four colours with a dash pattern, and the legend shows each line's colour and dash. The core flood run page has the same chart |
| Add or fix an experiment's description | Fill in "Experiment Description" in step 1 of **New Experiment**; it is saved as the experiment's Description note and shows on the reactor card and detail header. Later, open the experiment and click the description under its ID to edit it in place — or click **Add description** if it has none. Only one Description is allowed per experiment |
| Read or write notes on an experiment | Open an experiment → **Notes** tab. Every note — experiment-level and timepoint-scoped — is one timeline, newest first, each with a type badge, a `T+N` chip (on a timepoint) or a date chip (a dated modification), and its author. Filter by type or "Review queue only". To add one, pick a type: an Observation may name a timepoint; a Result note must; a Modification needs a timepoint **or** a date (defaults to today); a Description has neither |
| Change a note's type | Open an experiment → **Notes** tab → use the type dropdown on the note. Experiment-level notes can be Observation or Description; notes on a timepoint can be Observation, Modification or Result note; a dated note can be Observation, Modification or Description. Only one Description is allowed per experiment |
| Export an experiment's data to Excel | Open an experiment (or a run on **Core Floods**) → **Export all** in the header. One workbook downloads with Results, Conditions, Additives, Notes and Summary tabs (plus Core Flood for core flood runs, **XRD** when any experiment has post-reaction XRD, and **Rock XRD** when its rock sample has XRD), covering the experiment and every segment and side sample in its series. Values are the same as the Power BI report |
| Export several experiments to one Excel workbook | **Data Export** → set filters (for example an Additive or a Researcher; the **Experiment start date** card filters by when the run began and the **Last sample date** card by the date of its most recent dated result, each with **Begin** and **End** (inclusive calendar days in lab time; leave either blank for an open range). **Last 7 days**, **Last 30 days**, **This month** and **Last month** under Last sample date fill both bounds in one click, so "which experiments have data from last month" is one click on **Last month**. **Clear** resets a card. The list shows a **Start date** and a **Last sample** column; a row standing for several vials shows its latest vial's sample date) → tick the experiments (**Select all shown** ticks every row listed; ticks survive changing the filters) → leave **Include whole series** on to bring each experiment's whole series, or untick it for just the ticked ones and their timepoint vials → **Export**. The page lists up to 500 matches; narrow the filters if it says "Showing N of M". There is no limit on how many experiments an export holds; it is refused only if a tab would have more rows than an Excel sheet allows (about a million). The workbook has the same tabs as **Export all**, including **XRD** (one row per experiment and day, one column per mineral in %, with Rwp) and **Rock XRD** (one row per analysis of a starting-rock sample, with the experiments that use it under **Used by**) when there is XRD to show |
| Attach an external analysis file | Open an experiment → **XRD** tab → Add Analysis |
| Search for a sample | Navigate to **Samples**, use the search bar |
| Add a new user (admin only) | Run `python scripts/manage_users.py create <email> <password> <display_name>` on the lab PC, then `approve <request_id>` |
