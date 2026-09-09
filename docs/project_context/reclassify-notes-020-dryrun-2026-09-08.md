# `reclassify_notes_020` dry-run report — production mirror, 2026-09-09

**Issue #118, PR2. Status: AWAITING AUDIT by Mat Hearl. `--apply` has NOT been run.**

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
3. **2026-09-09, production mirror + rule 4b** (this version): Mat ruled that GC
   method / injection tags (`DI, GC-B`, `Gas, GC-A, DI`, ...) are not notes — they
   matter to the person running the GC on the results sheet — so they are now
   discarded. Review queue **1,891**.

Everything else is applied exactly as written in the #118 spec. The **Audit notes**
section is what the numbers say, including the parts that look wrong.

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
  DISCARDED as GC method tag (rule 4b):           329
  PRESERVED as observation, needs_review=true:    1877
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
  distinct GC method tags discarded (rule 4b), by frequency:
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
        4  'Gas, GC-A, DI; liquid'
        3  'Gas (GC-A)'
        2  'liquid, gas (GC-A)'
        2  'GC-B; Liq; liquid'
        2  'gas (GC-A), liquid'
        2  'Gas; GC-A'
        2  'Gas, GC-B; liquid'
        1  'Full loop, GC-A, gas and liquid'
        1  'DI, GC-B; Liquid; Solid'
        1  'Full loop, GC-A'
        1  'Gas (GC-A), liquid, solid'
        1  'GC-A, liquid'
        1  'Gas; Gas, GC-A, DI'
        1  'GC-A; Liquid'
        1  'Gas (GC-A), liquid'
        1  'Gas, GC-A. DI'
        1  'Gas, GC-A, DI; solid, liquid'
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
       80  'gas, liquid'
       75  '0'
       65  'Gas, liquid'
       63  'Day 1.0 results'
       44  'Day 2.0 results'
       41  'Day 6.0 results'
       31  'gas, liquid, solid'
       30  't=0'
       26  'Gas and liquid sample'
       25  'End of exp.'
       24  'Day 3.0 results'
       18  'Day 7.0 results'
       18  'T=0'
       16  'Pre-rxn brine check'
       14  'Liquid and gas sample'

-- Review queue (needs_review = true after --apply)
  'nan' legacy notes newly flagged:               14
  preserved result descriptions:                  1877
  TOTAL rows landing in the review queue:         1891
==============================================================================
before: {'description_notes': 0, 'experiments_with_description': 0, 'modification_notes': 0, 'observation_notes': 1536, 'review_queue': 0, 'notes_total': 1536}

Dry run — pass --apply to commit changes.
```

## Audit notes (what surprised me, not adjusted for unless stated)

1. **Decided — rule 4b, GC method tags (329 rows) are discarded.** Mat,
   2026-09-09: these tags say which GC method and injection produced a
   reading, and belong to the researcher running the GC on the results bulk
   upload sheet, not to the experiment's notes. The rule is narrow on purpose:
   only text built from the tokens gas / liquid / liq / solid / DI / GC-A /
   GC-B / FL / Full Loop and separators, containing at least one GC token. The
   32 distinct texts it caught are listed in the raw output above. Texts with
   any other word (`Cold dip tube liquid, GC-A`) and the `0; Gas, GC-A, DI`
   variant are still preserved for review.

2. **Still pending — three more families the filler pattern misses.** They are
   most of what is left in the 1,877 preserved rows:

   | Family | Rows | Examples |
   |---|---|---|
   | Code-generated fallbacks from the *other* parsers | **291** | `Day 1.0 results`, `Day 7.0 results`, `Analysis results for Day N` |
   | Multi-fraction lists (no GC token) | **~250** | `gas, liquid`, `Gas, liquid`, `gas, liquid, solid`, `Gas and liquid sample`, `Liquid and gas sample` |
   | The literal `0` (Excel blank read as zero; all created 2026-07-23 .. 08-31) | **75** | `0` |

   The `Day N results` fallbacks are the same species as `Master upload — day`,
   which the spec does discard, written by `scalar_results_service.py` when no
   description was supplied. The fraction lists and the literal `0` are
   placeholders. Treating all three as filler would drop the review queue from
   **1,891 to roughly 1,270**; the remaining rows are the long tail of real free
   text (`Pre-rxn brine check`, `End of exp.`, `t=0`, `AOS Flush 1`, ...).
   **Not changed** — the spec says to report rather than tune, and whether a
   fraction list is "no information" is a product call. Decision needed per
   family before `--apply`.

3. **What happens to the review queue after `--apply`.** Nothing automatic.
   Each preserved row is an `observation` note on its result with
   `needs_review = true`. PR3 makes them visible (Results tab NOTE badge, the
   review endpoint, the Notes tab filter) and a researcher resolves each one:
   keep, retype, edit, or delete. PR4 is gated on the queue being **empty**, so
   every surviving row must be touched by hand — which is why the filler
   decisions above matter. PR3 also needs a write path to clear `needs_review`
   (the spec's review endpoint is read-only); scoped into PR3.

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
| `note_type = 'observation'` rows | 1,536 | 259 legacy + 1,877 preserved = 2,136 |
| `needs_review = true` (the review queue) | 0 | **1,891** |
| notes total | 1,536 | 3,554 |

The script exits non-zero if the post-apply review-queue count differs from the
plan. These figures move with every upload on the lab PC between now and
`--apply`; the lab-PC dry run is the number that has to match, this report is
the rehearsal.
