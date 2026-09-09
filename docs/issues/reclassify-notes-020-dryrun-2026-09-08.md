# `reclassify_notes_020` dry-run report — production mirror, 2026-09-09

**Issue #118, PR2. Status: AWAITING FINAL SIGN-OFF by Mat Hearl. `--apply` has NOT been run.**

Produced against a **mirror of the lab PC database**: the 2026-09-08 01:00 backup
(`docs/sample_data/experiments_20260908_010003.sql`, data current to 2026-09-04)
restored into the local dev DB, then `alembic upgrade head` (applies PR1's
`b7e2c9a41d05`), then:

```
DATABASE_URL=<dev DB from .env> python database/data_migrations/reclassify_notes_020.py
```

History of this report:

1. 2026-09-08, stale dev DB (data to ~May 2026): 1,009 experiments, review queue 1,682.
2. 2026-09-08, production mirror, spec rules only: review queue **2,220**.
3. 2026-09-09, + rule 4b (GC method / injection tags discarded, Mat): **1,891**.
4. **2026-09-09, + rules 4c/4d/4e** (this version, Mat: "discard all of those
   remaining categories"): code-generated `Day N results` fallbacks, multi-fraction
   lists, and the literal `0` are discarded. Review queue **1,242**.

Rules 1-3 and the spec's rule 4 are applied exactly as written in #118; rules
4b-4e are Mat's audit decisions, each counted and listed separately below.

Mirror size: 1,395 experiments · 1,536 notes · 2,461 results · 153 non-blank
`brine_modification_description` · 14 `'nan'` notes.

## Raw output

```
==============================================================================
reclassify_notes_020 -- plan report
==============================================================================
experiments total:                                1395
experiments with ZERO notes:                      104
  sample: , AUTO_MH_001, AUTO_MH_002, AUTO_MH_003, AUTO_MH_004, AUTO_MH_005, AUTO_MH_006, CF-01, CF-02, CF-03, CF-04, HPHT_MH_001, HPHT_MH_002, HPHT_MH_003, MHE-75, MHE-76, MHE-77, nan, SERUM_CrTi_001a-t3, SERUM_CrTi_001a-t7
legacy notes (created_by IS NULL):                1536
PR1-era notes (created_by set, left untouched):   0

-- Rule 1: oldest legacy note per experiment by min(id) -> description
  notes to promote to 'description':              1277
  notes set to 'observation' (result_id NULL):    0
  experiments keeping a PR1-era description:      0
  experiments already promoted by a prior run:    0

-- Rule 2: legacy notes reading 'nan' -> needs_review, never promoted
  'nan' legacy notes:                             14
  ...newly flagged needs_review by this run:      14
  experiments whose OLDEST note is 'nan' and therefore end with NO description: 14
  OTHER_JW_002, OTHER_JW_003, OTHER_JW_004, OTHER_JW_001, SERUM_Catalyst_001a-t1, SERUM_Catalyst_001b-t1, SERUM_Catalyst_001c-t1, SERUM_Catalyst_003a-t7, SERUM_Catalyst_003b-t7, SERUM_Catalyst_003c-t7, SERUM_Catalyst_006-t3, SERUM_Catalyst_009a-t1, SERUM_Catalyst_009b-t1, SERUM_Catalyst_009c-t1

-- Rule 3: brine_modification_description -> 'modification' note on the result
  notes to insert:                                141
  already mirrored by PR1 dual-write (skipped):   0
    result 825: '4mL 1M KOH Addition'
    result 899: '4mL 1M KOH Addition'
    result 905: '0.5mL HOAc addition.'
    result 906: 'Rock filtered and rinsed with DI'
    result 953: 'Sampled 2.3g rock for XRD.'
    result 963: 'Temp change to 220C from 90C'
    result 964: 'Sampled 1.9g rock for XRD. Added 1M KOH to bring pH to 10.'
    result 977: 'All promoters refreshed.'
    result 978: '4 promoters, nicl2, HOAc addition'
    result 979: 'Added 2g CaO, 0.203g NiCl2*6H2O.'

-- Rule 4: experimental_results.description
  filler pattern:  ^\s*(gas|liquid|solid|aqueous|gas\s*\+\s*liquid)(\s+sample)?\s*$
  or prefix:       'Master upload — day '
  blank (nothing to carry):                       109
  DISCARDED as filler (rule 4):                   146
  DISCARDED by rule 4b GC method tag:               329
  DISCARDED by rule 4c code-generated fallback:     291
  DISCARDED by rule 4d fraction list:               283
  DISCARDED by rule 4e literal 0:                   75
  PRESERVED as observation, needs_review=true:    1228
  already mirrored by PR1 dual-write (skipped):   0

  sample of 20 DISCARDED (result_id: text):
    1286: 'Gas sample'
    1287: 'Liquid sample'
    1295: 'Liquid sample'
    1319: 'Gas sample'
    1320: 'Gas sample'
    1337: 'Gas sample'
    1339: 'Gas sample'
    1341: 'Gas sample'
    1342: 'Gas sample'
    1345: 'Liquid sample'
    1346: 'Liquid sample'
    1351: 'Liquid sample'
    1353: 'Master upload — day 7.0'
    1355: 'Liquid Sample'
    1382: 'Master upload — day 46115.0'
    1386: 'Gas sample'
    1387: 'Liquid sample'
    1390: 'Gas sample'
    1396: 'Liquid sample'
    1397: 'Liquid sample'
  distinct texts discarded by rule 4b GC method tag, by frequency (329 rows):
      120  'DI, GC-B'
       56  'GC-B'
       45  'Gas, GC-A, DI'
       16  'DI, GC-B; Liq'
       12  'DI, GC-A'
        9  'GC-B; liquid'
        8  'DI, GC-B; Liquid'
        6  'Gas, GC-B'
        5  'Full Loop, GC-A'
        5  'GC-A'
        4  'Gas, liquid, GC-A'
        4  'GC-A, liquid, solid'
        4  'DI, GC-B, liq'
        4  'GC-B; Liq'
        4  'GC-B; Liquid'
  distinct texts discarded by rule 4c code-generated fallback, by frequency (291 rows):
       63  'Day 1.0 results'
       44  'Day 2.0 results'
       41  'Day 6.0 results'
       24  'Day 3.0 results'
       18  'Day 7.0 results'
       13  'Day 14.0 results'
        5  'Day 9.0 results'
        5  'Day 13.0 results'
        5  'Day 19.0 results'
        5  'Day 56.0 results'
        5  'Day 10.0 results'
        4  'Day 109.0 results'
        4  'Day 8.0 results'
        4  'Day 36.0 results'
        4  'Day 16.0 results'
  distinct texts discarded by rule 4d fraction list, by frequency (283 rows):
       80  'gas, liquid'
       65  'Gas, liquid'
       31  'gas, liquid, solid'
       26  'Gas and liquid sample'
       14  'Liquid and gas sample'
       12  'Solid, liquid, gas'
        8  'Liquid, gas'
        7  'Gas, liquid sample'
        5  'Gas, liquid, solid'
        4  'Liquid and Gas sample'
        4  'Gas; Liquid'
        3  'Gas and liquid'
        3  'Gas, liquid, solid sample'
        3  'Liquid and gas'
        3  'Liquid, solid'
  distinct texts discarded by rule 4e literal 0, by frequency (75 rows):
       75  '0'
  sample of 20 PRESERVED (result_id: text):
    24: 'F1'
    25: 'N2 Experiment'
    26: 'F1'
    27: 'F2'
    28: 'F3'
    29: 'F4'
    30: 'F5'
    31: 'F6'
    33: 'N2 Experiment'
    34: 'N2 Experiment'
    35: 'Sat for months'
    36: 'Not stirred'
    37: 'Stirred'
    38: 'Stirred'
    39: 'R'
    40: 'R'
    41: 'R'
    77: 'AOS Flush 1'
    87: 'Pre Acidified'
    97: 'AOS Flush 2'
  top 15 PRESERVED texts by frequency (what the pattern did NOT catch):
       30  't=0'
       25  'End of exp.'
       18  'T=0'
       16  'Pre-rxn brine check'
       13  'day 10 nmr'
       12  't=1d, liquid'
       12  't=7d liquid sample'
       12  't=15d liquid sample'
       10  'DAY 14 NMR'
        9  'Day 7'
        8  'Direct Inject'
        7  'Day 14'
        7  'DAY 7 NMR'
        6  'day 30 nmr'
        6  'day 38 nmr'

-- Review queue (needs_review = true after --apply)
  'nan' legacy notes newly flagged:               14
  preserved result descriptions:                  1228
  TOTAL rows landing in the review queue:         1242
==============================================================================
before: {'description_notes': 0, 'experiments_with_description': 0, 'modification_notes': 0, 'observation_notes': 1536, 'review_queue': 0, 'notes_total': 1536}

Dry run — pass --apply to commit changes.
```

## Audit notes

1. **Decided — four filler families are discarded (rules 4b-4e).** Together they
   remove 978 of the 2,206 descriptions the spec pattern alone would have queued:

   | Rule | Family | Rows | Boundary |
   |---|---|---|---|
   | 4b | GC method / injection tags | 329 | only gas/liquid/liq/solid/DI/GC-A/GC-B/FL/Full Loop tokens + separators, with at least one GC token |
   | 4c | Code-generated fallbacks from the other parsers | 291 | `Day N results`, `Analysis results [for Day N]` |
   | 4d | Multi-fraction lists | 283 | two or more of gas/liquid/liq/solid/aqueous, any separator, optional `sample(s)` |
   | 4e | The literal `0` | 75 | `0` or `0.0` only |

   Each rule is deliberately narrow: any extra word keeps a text out
   (`Cold dip tube liquid, GC-A`, `0 rpm`, `t=1d, liquid` are all preserved).
   The distinct texts each rule caught are listed in the raw output so the
   boundary can be checked against real data.

2. **What is left in the queue (1,228 descriptions + 14 `'nan'` notes).** The
   remaining descriptions are the long tail of researcher-typed labels:
   timepoint tags (`t=0`, `T=0`, `Day 7`, `t=7d liquid sample`), instrument
   run labels (`day 10 nmr`, `DAY 14 NMR`, `Direct Inject`), and genuine
   remarks (`End of exp.`, `Pre-rxn brine check`, `Sat for months`, `Not
   stirred`, `AOS Flush 1`). Roughly 100 of them are timepoint tags that
   duplicate `time_post_reaction_days`; they were left in because "t=7d liquid
   sample" is a judgement call, not a pattern, and the queue is where judgement
   calls go.

3. **What happens to the review queue after `--apply`.** Nothing automatic.
   Each preserved row is an `observation` note on its result with
   `needs_review = true`. PR3 makes them visible (Results tab NOTE badge, the
   review endpoint, the Notes tab filter) and a researcher resolves each one:
   keep, retype, edit, or delete. PR4 is gated on the queue being **empty**.
   PR3 also needs a write path to clear `needs_review` (the spec's review
   endpoint is read-only); scoped into PR3.

4. **`'nan'` notes grew from 4 to 14** since the 2026-08-05 measurement in the
   issue doc; the newest was written 2026-08-10. All ten new ones are
   `SERUM_Catalyst_*` replicate vials. **Every one of the 14 experiments holds
   only that single `'nan'` note**, so rule 2's "nothing is promoted in its
   place" has nothing to promote anyway — these 14 experiments end with no
   description and 14 flagged rows. PR1 stops the bleeding.

5. **104 experiments have zero notes.** Two have broken IDs: row 504 is
   `experiment_id = 'nan'`, row 701 is `''`. Same NaN-stringification class at
   experiment creation; outside this task's rules, flagged for a separate
   cleanup. The `SERUM_CrTi_001a-t*` vials in the sample are recent uploads
   with no `initial_note`, which is legitimate.

6. **Result 1382 is at day 46,115** (experiment 676): an Excel serial date read
   as a duration. Its description is correctly discarded; the row is a separate
   data-quality defect.

7. **Nothing has been dual-written yet** (`PR1-era notes: 0`), so every
   "already mirrored" counter is zero here. On the lab PC they will be non-zero
   for any upload run between deploying PR1 and applying PR2; the script skips
   those idempotently and reports the counts.

## Expected state after `--apply` (for definition-of-done item 6)

| Metric | Before | Expected after |
|---|---|---|
| `note_type = 'description'` rows | 0 | 1,277 |
| experiments with a description | 0 | 1,277 (of 1,395; 104 have no notes, 14 hold only `'nan'`) |
| `note_type = 'modification'` rows | 0 | 141 |
| `note_type = 'observation'` rows | 1,536 | 259 legacy + 1,228 preserved = 1,487 |
| `needs_review = true` (the review queue) | 0 | **1,242** |
| notes total | 1,536 | 2,905 |

The script exits non-zero if the post-apply review-queue count differs from the
plan. These figures move with every upload on the lab PC between now and
`--apply`; the lab-PC dry run is the number that has to match, this report is
the rehearsal.

## Rehearsal: `--apply` on the production mirror (2026-09-09)

Mat approved the plan above ("apply"). Run on the dev-DB mirror, with a
`pg_dump -Fc` of the pre-apply state taken first.

```
after:  {'description_notes': 1277, 'experiments_with_description': 1277,
         'modification_notes': 141, 'observation_notes': 1487,
         'review_queue': 1242, 'notes_total': 2905}
Applied. Review queue = 1242 (matches the dry-run plan).
```

Every figure matches the "Expected state" table exactly. Checks run afterwards:

| Check | Result |
|---|---|
| Second dry run (idempotency) | 0 to promote, 0 to insert, 0 newly flagged; 1,277 "already promoted", 141 + 1,228 "already mirrored" |
| Legacy `min(id)` reader vs typed `description`, per experiment | **1,277 agree, 0 disagree** — the app's description text is unchanged for every experiment |
| `v_experiments` (`ORDER BY created_at`) vs typed `description` | **16 disagree.** In every case the view picks a note with a higher id but earlier `created_at` — e.g. `SERUM_JW_051-3` shows `ICP Analysis - SERUM_JW_051-3_Day1_5x` in Power BI while the app shows `SERUM_JW_051 with EDTA and pH 11`. This is the created_at-vs-min(id) defect the spec names; PR3's `WHERE note_type = 'description'` fixes it, and these 16 are the rows whose Power BI description will change. |
| Experiments with notes but no description | 27 = the 14 `'nan'` experiments + 13 experiments whose only notes are the new result-scoped ones |
| `modification` notes vs non-blank `brine_modification_description` | 141 vs 153. The 12 unmirrored rows all hold the literal `'nan'` — the rows `fix_nan_text_fields_019.py` cleans. **019 has not been applied to production either**; run it on the lab PC before or alongside 020 (its dry run on this mirror reports the same 12). Rule 3 skips them correctly. |

Pre-apply snapshot: session scratchpad `dev_mirror_pre_apply.dump` (not committed).
