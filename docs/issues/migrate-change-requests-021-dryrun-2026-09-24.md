# 021 dry run — `reactor_change_requests` → dated `modification` notes (2026-09-24)

Issue #122, PR-B (`feat/reactor-mods-as-notes`). Script:
`database/data_migrations/migrate_reactor_change_requests_021.py` (committed `43ca929`).
**Dry run only. `--apply` has not been run anywhere.** This is the audit input the phase-2
spec's hard gate (§2) requires before the mirror apply; production follows only after the
mirror numbers are confirmed.

## What the script does (rules, in id order)

1. `experiment_id IS NULL` → **orphaned**, reported, never converted. The column is a
   foreign key to `experiments.experiment_id` with `ON DELETE SET NULL`
   (`reactor_change_requests_experiment_id_fkey`), so NULL means the experiment was deleted
   after the row was written, or the Notion import never matched one. There is no string
   to resolve; guessing from the reactor label would attribute a modification to whoever
   holds the slot today.
2. A non-NULL `experiment_id` resolves **exactly**; the FK guarantees the match. No fuzzy
   matching.
3. Blank `requested_change` → reported, not converted.
4. Otherwise one note via `backend/services/notes.py::add_note`: `note_type='modification'`,
   `event_date=sync_date`, `result_id NULL`, text stripped, `created_by='migrate_change_requests_021'`,
   `created_at=row.created_at`. Dashboard-typed and Notion-imported rows convert alike.
   `reactor_label` is **not** carried onto the note (decision 2); the whole original row goes
   into one `ModificationsLog` snapshot (`modified_table='reactor_change_requests'`,
   `modification_type='update'`, `old_values`=row, `new_values={'note_id': …}`,
   `experiment_fk` set so the snapshot dies with the experiment).
5. Idempotent on `(experiment_fk, event_date, note_text, created_by=tag)`; two source rows
   sharing `(experiment, date, text)` under different labels collapse to one note and are
   counted.
6. Informational: convertible rows whose `reactor_label` differs from the experiment's
   current `experimental_conditions.reactor_slot`.

Nothing is deleted from `reactor_change_requests`; the table drop is PR-E2, separately
authorized.

## Mirror provenance

| Item | Value |
|---|---|
| Backup restored | `docs/sample_data/experiments_20260923_010002.sql` (pg_dump custom archive, created 2026-09-23 01:00:03, server 18.3) |
| Data horizon | experiments `created_at` max 2026-09-22 16:30; change requests `sync_date` max 2026-09-21 |
| Schema on restore | `00063a5dd6a8` (pre-Titanium, pre-typed-notes) |
| Upgraded to | `c4d8f1a2b6e7` (develop head), then `e5b2d9c7a1f4` (this branch: `event_date`, relaxed `ck_note_scope`, `v_notes.event_date`) |
| 020 rehearsal on this mirror | dry run: 1,429 descriptions to promote, 38 `nan` notes flagged, review queue 1,288. `--apply`: `description_notes 1429, modification_notes 151, observation_notes 1539, review_queue 1288, notes_total 3119`. Production's own 020 run (2026-09-23) reported 1,432 / 151 / 1,288; the three-description gap is the experiments created between the 01:00 backup and the production run. |
| Rollback | the previous 2026-09-04 mirror is saved as `dev_pre_restore_20260924.dump` in the session scratchpad |

Restore followed memory `restoring-prod-backups-to-dev` (terminate connections, drop and
recreate `experiments` owned by `experiments_user`, `pg_restore --no-owner --no-acl` as
`experiments_user`).

## Pre-measurement of `reactor_change_requests` (SQL, independent of the script)

| Measure | 2026-09-04 mirror (spec §1) | 2026-09-23 mirror |
|---|---|---|
| rows | 294 | **333** |
| typed on the dashboard (`notion_page_id IS NULL`) | 161 | **196** |
| imported from Notion | 133 | **137** |
| dated 2026-08-01 or later | 115 | 154 |
| dated after 2026-09-04 | — | 39 |
| `experiment_id IS NULL` | reported as "26 with no matching experiment" | **26** |
| non-NULL `experiment_id` that does not resolve | — | **0** |
| blank `requested_change` | 0 | 0 |
| distinct `reactor_label` | — | 21 |
| distinct experiments among convertible rows | — | 98 |
| `reactor_label` ≠ current `conditions.reactor_slot` | — | 8 |
| duplicate `(experiment_id, sync_date, requested_change)` | — | 0 |
| `carried_forward = true` | — | 106 |
| `created_at` column | — | present, NOT NULL, 2026-04-07 → 2026-09-21 |

**Correction to the spec's framing.** The "26 unresolvable experiment IDs" are 26 rows whose
`experiment_id` is NULL. Because of the FK's `ON DELETE SET NULL`, no non-NULL string can
fail to resolve. Nothing can be recovered for those rows without guessing.

By month and source (convertible | orphaned):

| Month | Dashboard | Notion |
|---|---|---|
| 2026-04 | — | 60 \| 23 |
| 2026-05 | 32 \| 0 | 23 \| 3 |
| 2026-06 | 1 \| 0 | — |
| 2026-07 | 34 \| 0 | 3 \| 0 |
| 2026-08 | 78 \| 0 | 16 \| 0 |
| 2026-09 | 51 \| 0 | 9 \| 0 |

All 26 orphaned rows are Notion imports from 2026-04-07 to 2026-05-01: fifteen are the
autoclave labels `AC01`–`AC03` (five each, "sample Friday" / "heat/sample 4/15" /
"start ammonia degredation exp…"), which never had an experiment row to match; the other
eleven are R03–R09 entries from the first week of the Notion sync whose experiments were
since deleted or never linked.

## Dry-run output (verbatim, `PYTHONIOENCODING=utf-8`)

```
== migrate_reactor_change_requests_021 -- dry-run report ==
reactor_change_requests rows:                    333
  typed on the dashboard (notion_page_id NULL):  196
  imported from Notion:                          137
convertible (-> one 'modification' note each):   307
orphaned (experiment_id NULL; FK ON DELETE SET NULL): 26
    row 1: R04 2026-04-07 notion 'Start background to match Mg conditions Next steps: H2 + Mg…'
    row 2: R08 2026-04-07 notion 'Continue N2 solubility testing Next steps: CaCl2, pH 9, Ni,…'
    row 3: R05 2026-04-07 notion 'Awaiting repairs'
    row 4: R03 2026-04-07 notion 'Clear out reactor Resume HPHT_079 (now HPHT_079-2), fresh b…'
    row 6: R09 2026-04-07 notion 'Start background to prep for Tamarack Magnesium Aluminate e…'
    row 7: R07 2026-04-07 notion 'Reverse NH3 rxn conclusion Desorption with KCl Next steps: …'
    row 8: R06 2026-04-07 notion 'Awaiting repairs'
    row 25: R04 2026-04-09 notion 'Start background to match Mg conditions (HPHT_116) Next ste…'
    row 32: AC03 2026-04-09 notion 'start ammonia degredation exp, NH4Cl 5 mM (0.0160 g), 200C …'
    row 33: AC02 2026-04-09 notion 'start ammonia degredation exp, NH4Cl 5 mM (0.0160 g), 200C …'
    row 34: AC01 2026-04-09 notion 'start ammonia degredation exp, NH4Cl 5 mM (0.0160 g), 200C …'
    row 40: R07 2026-04-10 notion 'Sample KCl for NMR Next steps: HPHT_126'
    row 49: AC03 2026-04-11 notion 'sample Friday'
    row 50: AC02 2026-04-11 notion 'sample Friday'
    row 51: AC01 2026-04-11 notion 'sample Friday'
    row 72: R03 2026-04-14 notion 'Prepare Fe(OH)2 as per SOP in 4/10 Daily Meeting Notes'
    row 102: AC03 2026-04-16 notion 'heat/sample 4/15'
    row 103: AC02 2026-04-16 notion 'heat/sample 4/15'
    row 104: AC01 2026-04-16 notion 'heat/sample 4/15'
    row 107: R05 2026-04-17 notion 'pH adjust via NaOH addition to pH >2. RuCl3 dropped pH to 1…'
    row 122: AC03 2026-04-18 notion 'sample Friday'
    row 123: AC02 2026-04-18 notion 'sample Friday'
    row 124: AC01 2026-04-18 notion 'sample Friday'
    row 244: AC03 2026-05-01 notion 'sample Friday'
    row 245: AC02 2026-05-01 notion 'sample Friday'
    row 246: AC01 2026-05-01 notion 'sample Friday'
blank requested_change:                          0
already converted by a prior run (skipped):      0
collapsed under (experiment, date, text):        0
reactor_label != current conditions.reactor_slot: 8 of 307 (informational)
-- sample of 20 convertible rows --
    row 5: R02 2026-04-07 exp=HPHT_112 notion 'Sampling today:   • RT Gas Sample   • Liquid Sample (NMR, I…'
    row 26: R08 2026-04-09 exp=HPHT_122 notion 'Finishing solubility test. Next step: HPHT_122'
    row 27: R05 2026-04-09 exp=HPHT_117 notion 'Next steps: HPHT_121'
    row 29: R09 2026-04-09 exp=HPHT_124 notion 'Next step: HPHT_124'
    row 31: R06 2026-04-09 exp=HPHT_118 notion 'Next steps: HPHT_120'
    row 35: R04 2026-04-10 exp=HPHT_116 notion 'Next steps: HPHT 113, H2 + Mg Fayalite Experiment'
    row 36: R08 2026-04-10 exp=HPHT_122 notion 'Next step: Sample liquid and gas Monday 4/13'
    row 37: R01 2026-04-10 exp=HPHT_109 notion 'Filter rock in glovebox Save brine in serum vial Sample roc…'
    row 39: R09 2026-04-10 exp=HPHT_124 notion 'Next step: liquid sample Fri, end Mon. Queued: HPHT_125 (Ta…'
    row 42: R04 2026-04-11 exp=HPHT_116 notion 'Sample 24hr liquid today. Next steps: HPHT 113, H2 + Mg Fay…'
    row 45: CF01 2026-04-11 exp=CF-015 notion '2 days no flow, flush 9mL gas and liquid samples today.'
    row 47: R07 2026-04-11 exp=HPHT_126 notion 'Sample liquid'
    row 70: R01 2026-04-14 exp=HPHT_109 notion 'Sample gas and liquid, filter (while saving brine) and dry …'
    row 71: R02 2026-04-14 exp=HPHT_112 notion 'Sample gas and liquid, pH mod if needed'
    row 73: R04 2026-04-14 exp=HPHT_113 notion 'Sample day 4 liquid today. Next steps: HPHT 113, H2 + Mg Fa…'
    row 77: R08 2026-04-14 exp=HPHT_122 notion 'Next step: Sample liquid and gas Thursday 4/16'
    row 78: R09 2026-04-14 exp=HPHT_124 notion 'Queued: HPHT_125 (Tamarack+pH9)'
    row 88: R07 2026-04-15 exp=HPHT_126 notion 'Use syringe pump to add fluid for sampling'
    row 93: R04 2026-04-16 exp=HPHT_113 notion 'Sample liquid for NMR, day 2 sample.'
    row 97: R03 2026-04-16 exp=HPHT_127 notion 'Sample, restart'
before: {'change_request_rows': 333, 'modification_notes': 151, 'dated_modification_notes': 0, 'notes_by_021': 0, 'snapshots_by_021': 0, 'notes_total': 3119}

Dry run — pass --apply to commit changes.
```

## The eight label disagreements

All eight are `reactor_label = R04` on rows for `HPHT_116` (rows 35, 42) and `HPHT_113`
(rows 73, 93, 105, 116, 167, 177), April 2026, whose conditions now read `reactor_slot = R07`.
That is the reactor 4↔7 swap applied later by `database/data_migrations/swap_reactor_4_7_015.py`:
the labels were true when written. Informational only; both experiments convert normally.

## What `--apply` would do on this mirror

- Insert **307** `modification` notes with `event_date` (from 0 dated ones today) and
  **307** `ModificationsLog` snapshots (`modified_table='reactor_change_requests'`).
- `modification_notes` 151 → **458**; `notes_total` 3,119 → **3,426**.
- `reactor_change_requests` stays at 333 rows.
- The script's own after-check compares `notes_by_021` with the plan and exits 2 on mismatch.

Command (mirror; the default `DATABASE_URL` in `.env`):

```
PYTHONPATH=. .venv/Scripts/python.exe database/data_migrations/migrate_reactor_change_requests_021.py --apply
```

A second dry run afterwards must report `already converted by a prior run (skipped): 307`
and `convertible: 0`.

## Questions for Mat

1. **Approve `--apply` on the mirror** with the numbers above? (Production follows the
   normal deploy runbook after the branch merges: `alembic upgrade head`, then this
   script's dry run compared against this report, then `--apply`.)
2. **Decision 2, reactor label.** Default is **not** to carry `reactor_label` onto the note
   text; the full original row is recoverable from each snapshot. If you want the label
   visible in the note, say so and the script gains a `[R05] `-style prefix (one-line
   change, re-dry-run before apply). The 8 disagreements above are the only rows where the
   prefix would say something the experiment's current slot does not.
3. **The 26 orphaned rows** stay in `reactor_change_requests` untouched and are dropped
   with the table in PR-E2. If any should survive as notes on a specific experiment, name
   the row id and the experiment and it can be done by hand through the Notes tab after
   PR-C, not by this script.
