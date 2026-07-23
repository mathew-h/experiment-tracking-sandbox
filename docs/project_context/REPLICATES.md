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

- A chart of the selected metric (gross/net NH₄, NH₄ or H₂ g/t, H₂ µmol, Fe²⁺ yield, pH)
  with the cross-replicate mean line and error bars (± 1 std) per timepoint, plus each
  individual replicate's series overlaid (toggle-able) so you can spot an outlier vial.
- A table with the same mean/median/std/n columns per timepoint.
- Click through from an individual series or table row to that replicate's own
  detail page to inspect its raw data.

Individual series overlays are capped at 4 lines on the chart — in practice replicate
sets are a/b/c, well under that cap.

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
| Rollup stats look wrong across a base with re-runs | The base has both lettered replicates and a sequential re-run (e.g. `HPHT_001-2`) sharing the same base ID | Rollup and grouping key don't distinguish the two — verify the group is actually a lettered set before trusting `n_replicates` |

---

## Flagging an outlier

If one vial in a replicate set goes bad (leak, cracked septum, contamination), you can drop it from the group statistics without deleting any data:

1. Open the replicate's experiment page (e.g. `SERUM_001c`).
2. Click **Mark as outlier** in the quick-actions row. An **Outlier — excluded from group stats** badge appears next to the status.
3. The grouped results view and the Power BI rollup (`v_results_scalar_rollup`) immediately recompute mean/median/std **and `n`** without that replicate. The flagged replicate is annotated "(outlier)" in the grouped view.
4. All of the replicate's own data stays intact and visible on its page and in every per-row reporting view.
5. To undo, click **Include in rollup** on the same page. Every flag change is recorded in the experiment's Entry Logs.

The button appears only on experiments that belong to a replicate set (lettered members and the group parent, which is vial 0).
