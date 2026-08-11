# Replicates User Guide

Replicates are lettered "sister" vials of the same experiment setup — e.g. `SERUM_001a`,
`SERUM_001b`, `SERUM_001c` — run side by side so results can be reported as a mean ± std
instead of a single number.

---

## What a replicate ID looks like

- The bare base ID (`SERUM_001`) is **replicate 0**, the group parent. It has no letter
  suffix. An explicit `SERUM_001-0` or `SERUM_001-1` spelling is treated the same way.
- Lettered members (`a`, `b`, `c`, …) are the replicate siblings, each its own full
  `Experiment` row with its own conditions, additives, and results.
- A base experiment can have sequential re-runs (`HPHT_001-2`) that are **not**
  replicates — those stay flat in the list and are never grouped into a replicate set.

### Re-running a single replicate

If one vial of a replicate set is re-run, name it by appending a sequential number to the lettered ID (e.g. `SERUM_001a-2` for the second run of vial `a`). The re-run is linked to the lettered replicate itself (`SERUM_001a`) as its parent, so the lineage chain reads stem → `a` → `a-2`. If the lettered experiment does not exist in the system, the re-run falls back to linking directly to the group parent.

---

## Grouped experiments list

The Experiments list has a **Group replicates** toggle (on by default). When on:

- Lettered sets collapse into a single row for the parent, with a `▸` disclosure arrow.
- Click the arrow to expand and see each lettered member indented underneath.
- Pagination counts collapsed groups as one row, so page size and totals stay stable
  as you expand/collapse — expanding a row never changes what page you're on.
- Turn the toggle off to see every experiment row flat, one per line, as before.

---

## Grouped results (mean ± std)

On an experiment's **Results** tab, if the experiment belongs to a replicate set, a
**Grouped (n=N)** mode appears alongside the normal per-vial view. It shows:

- A chart of the selected metric — **H₂ (ppm)** (the default), **H₂ (µmol)**, **H₂ (g/t)**,
  **Fe²⁺ → H₂ (%)**, or **pH** — with the cross-replicate mean line and error bars (± 1 std)
  per timepoint, plus each individual replicate's series overlaid (toggle-able) so you can
  spot an outlier vial.
- A table with the same mean/median/std/n columns per timepoint.
- Click through from an individual series or table row to that replicate's own
  detail page to inspect its raw data.

Individual series overlays are capped at 4 lines on the chart — in practice replicate
sets are a/b/c, well under that cap.

> **H₂-focused views.** Both the per-vial Results tab and the grouped rollup are
> hydrogen-first: they show only H₂ metrics, Fe²⁺ → H₂ (%), pH, and conductivity. Ammonium
> figures (gross/net NH₄, NH₄ g/t, Fe²⁺ → NH₃ (%)) are **not** deleted — they remain in the
> database, the calculation engine, the `v_results_scalar_rollup` view, and the Power BI
> datasets, and are still recorded through Bulk Uploads and the Add Results form. Only the
> on-screen results and rollup tables dropped the NH₄ columns.

---

## Replicate Group View

Every replicate group — including an orphan lettered set with no parent row — has its
own page at `/experiments/groups/{base}` (e.g. `/experiments/groups/SERUM_001`). Reach
it from the **Group {base}** link in the experiment detail header strip of any member.

It shows:

- A **members table** — one row per replicate (the parent, if one exists, plus every
  lettered member), with status, outlier flag, and result count per row. Any condition
  that differs from the rest of the group (e.g. actual rock mass) is called out per row.
  A set sampled per timepoint with **no letters at all** (`SERUM_pH_002-t1`, `-t3`,
  `-t7`, `-t20`) lists one row per vial here — see "Timepoint vials with no letters"
  below.
- **Shared conditions** — the fields identical across every member, shown once instead
  of repeated per row.
- An **additive summary** — a single summary line if every member's additives agree, or
  a "varies" note if they don't.
- The cross-replicate **rollup chart** (mean ± std per timepoint) — the same data as the
  Grouped (n=N) mode on an individual member's Results tab.

The page is **read-only**: "This is a grouped experiment view — you may only edit
individual replicates." Edit a replicate's conditions, additives, or results from its
own experiment page.

This replaces the old header link to `/experiments/{base}`, which 404'd whenever the
base ID had no parent row — the common case for lettered-only replicate sets.

### Timepoint vials with no letters

An experiment sampled destructively at several timepoints but **not** replicated —
`SERUM_pH_002-t1`, `-t3`, `-t7`, `-t20`, with no `a`/`b`/`c` anywhere — is one
experiment, four vials. It gets a group page like any set:

- On `/experiments` the four vials appear as **one row labelled `SERUM_pH_002`** with a
  **4 vials** chip. Clicking it opens the group page (not the first vial). The status
  dropdown is read-only on that row, because an inline change would reach only one vial.
- The group page header reads **4 vials** rather than "0 replicates", lists every vial
  with its `T+N` timepoint and result count, and links each one to its own page.
- The chart is a **time course**: one point per day, no error bars. Each day comes from a
  single vial, so there is no standard deviation to draw — the table shows the value
  alone rather than "± 0.0". A vial with no results yet (`-t20` above) is listed with a
  result count of 0 and contributes no point.
- The same view is reachable from any vial's Results tab via **Grouped (n=4)**.

Before this, such a set had no group page at all: `/experiments` collapsed the four
vials into one row that opened only the earliest one, and the rollup reported "No
primary results to aggregate yet." even though the data was there (issue #101).

---

## Creating replicates

Two ways to create lettered replicates of an existing experiment:

1. **From the experiment detail page** — on any non-replicate experiment (one that
   isn't itself a lettered member of a set), use the **Create Replicates** button to
   open a modal. Enter how many replicates you want (default 3); the modal previews
   the IDs it will create, continuing the alphabet after any letters already in use.
2. **From the New Experiment wizard** — on the final review step, set a "replicates to
   create" count before submitting. The base experiment is created first regardless of
   what happens next; if replicate creation fails, that failure is **non-fatal** — you'll
   be pointed to the Create Replicates action on the new experiment's detail page to
   retry.

Either way, each new replicate copies the base experiment's sample, researcher, status,
date, reactor conditions, and chemical additives. **Per-vial actuals — anything that
differs vial to vial (e.g. actual rock mass weighed in, actual reactor number, actual
pH) — are not unique per replicate at creation time and must be edited on each
replicate individually afterward.**

A conflicting ID (one that already exists) is skipped with a message rather than
failing the whole batch — check the toast/response for any skipped IDs.

---

## Uploading replicate results

Both the Solution Chemistry upload and the Master Results sync can load one sheet holding all replicates for a timepoint. Two row formats work:

1. **Full replicate IDs** — put the lettered ID (`SERUM_001a`) in the Experiment ID column, exactly as for any other experiment.
2. **Base ID + Replicate column** — put the bare base (`SERUM_001`) in Experiment ID and the letter (`a`, `b`, `c`) in the optional `Replicate` column. `0` or a blank cell means the group parent itself.

Each row lands as its own result on the matching sibling experiment, so the grouped (mean ± std) view aggregates automatically. Rows that cannot be resolved — a letter with no matching replicate experiment, a Replicate value that is not a single letter, or a letter that conflicts with one already in the ID — are skipped with a per-row error message; the rest of the file still uploads.

Replicate experiments must already exist (create them with the **Create replicates** button or the New Experiments upload) — result uploads never auto-create replicate siblings.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| "No parent experiment found" on Create Replicates | The base experiment doesn't exist yet | Create the base experiment first, then create replicates |
| A replicate ID was skipped | An experiment with that exact ID already exists | Check the skipped message; rename or delete the conflicting experiment if it was a mistake |
| Grouped results show `n=1` | This experiment has no lettered siblings yet | Use Create Replicates, or confirm you're not looking at a sequential re-run instead of a lettered set |
| Rollup stats look wrong across a base with re-runs | The base has both lettered replicates and a sequential re-run (e.g. `HPHT_001-2`) sharing the same base ID | Rollup and grouping key don't distinguish the two — verify the group is actually a lettered set before trusting `n_vials` |

---

## Replicate timepoints (`-t<days>`)

A different problem from lettered replicates: sometimes each "replicate" is actually its
own vial sacrificed at a specific day, rather than a sister vial sampled repeatedly over
time. For that pattern, encode the sample day directly in the experiment ID with a
trailing `-t<days>` token.

### Grammar

- `-t<days>` goes at the very end of the ID, after any letter or sequential suffix:
  `SERUM_001a-t0`, `SERUM_001a-t7`, `SERUM_001a-t14`.
- Decimals are allowed: `SERUM_001a-t0.5`.
- The token is letter-optional — a bare stem can carry it too: `SERUM_001-t7`. This stays
  a parent-like row (its `base_experiment_id` is the stem itself, `parent_experiment_fk`
  is `NULL`) rather than becoming a lettered replicate member.
- The token is stripped before lineage grouping, so `SERUM_001a-t7` still groups under
  base `SERUM_001` with `replicate_label = a`, exactly as `SERUM_001a` would without the
  token.
- **The Replicate column (base ID + letter format) cannot be combined with a token ID.**
  A row with `SERUM_001-t7` in Experiment ID and `a` in the Replicate column is rejected
  with a per-row error — encode the letter directly in the ID instead
  (`SERUM_001a-t7`). Blank/`0` Replicate cells are unaffected and upload fine with the
  token intact.

### One vial, one timepoint

The day encoded in the ID is canonical for that vial — every result row on that
experiment must be at that day. This is enforced everywhere a result's time is set:

- **Add Results modal:** the Time (days) field auto-fills from the ID and locks —
  you can't type a conflicting value.
- **Solution Chemistry upload:** a blank Time (days) cell is filled from the ID; a
  different value in that cell errors the row.
- **Master Results Sync:** a blank Duration (Days) cell is filled from the ID; a
  different value errors the row.
- **Direct API calls** (`POST /api/results`, and the scalar-result creation path used by
  all three upload routes above) apply the same fill/reject rule, so there's no way to
  get a `-t` vial's results out of sync with its ID.

### How the rollup reads it

Each `-t<days>` vial groups under its base experiment like any other replicate, and when
the result row has a `time_post_reaction_bucket_days` set, it lands in that day's bucket
in `v_results_scalar_rollup` — so a set like `SERUM_001a-t0`, `SERUM_001b-t0`,
`SERUM_001c-t0` (three vials sacrificed at day 0) rolls up exactly like three same-vial
samples taken at day 0 would. Use `-t<days>` when each timepoint is destructively sampled
from its own vial; use a repeated Add Results entry on one experiment when the same vial
is sampled non-destructively over time.

Results entered via the Add Results modal (`POST /api/results`) set
`time_post_reaction_bucket_days` automatically from the entered (or ID-encoded) time,
so they land in that day's rollup bucket just like bulk-uploaded rows (fixed in issue
#83; rows entered before the fix were backfilled). If you enter the same day twice for
the same experiment, the newest entry becomes that day's primary row and the older one
is kept but excluded from the rollup.

### The group parent counts toward the stats

The bare parent ID ("replicate 0") is part of its own replicate group: if the parent
has results of its own, they are averaged into the group mean ± sd alongside the
lettered replicates. This is intentional — a parent with data is treated as a group
member. If the parent's run should not count (for example, it was a scouting run under
different handling), flag the parent **Mark as outlier** on its experiment page; the
rollup then excludes it, exactly like an outlier replicate.

### Limitations

- **Untimed bare siblings are not blocked.** Nothing stops you from mixing a `-t`-tagged
  vial with an ordinary untimed sibling in the same replicate set — the system does not
  cross-check that every member of a set uses (or doesn't use) the token. Keep result
  days consistent across a replicate set manually.
- **Bulk New Experiments upload does not copy parent conditions for `-t` IDs.** Creating
  a batch of `-t<days>` vials via the New Experiments template creates each experiment
  row and parses its `id_timepoint_days`, but does not copy conditions/additives from a
  parent the way the **Create Replicates** button or `POST /api/experiments/replicates`
  does. Set up each `-t` vial's conditions after upload, or create the vials via the
  replicate-creation paths instead if you want conditions copied automatically.

---

## Flagging an outlier

If one vial in a replicate set goes bad (leak, cracked septum, contamination), you can drop it from the group statistics without deleting any data:

1. Open the replicate's experiment page (e.g. `SERUM_001c`).
2. Click **Mark as outlier** in the quick-actions row. An **Outlier — excluded from group stats** badge appears next to the status.
3. The grouped results view and the Power BI rollup (`v_results_scalar_rollup`) immediately recompute mean/median/std **and `n`** without that replicate. The flagged replicate is annotated "(outlier)" in the grouped view.
4. All of the replicate's own data stays intact and visible on its page and in every per-row reporting view.
5. To undo, click **Include in rollup** on the same page. Every flag change is recorded in the experiment's Entry Logs.

The button appears only on experiments that belong to a replicate set (lettered members and the group parent, which is vial 0).
