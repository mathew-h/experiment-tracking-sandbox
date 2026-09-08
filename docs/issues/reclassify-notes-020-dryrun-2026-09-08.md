# `reclassify_notes_020` dry-run report — dev DB, 2026-09-08

**Issue #118, PR2. Status: AWAITING AUDIT by Mat Hearl. `--apply` has NOT been run.**

Produced by:

```
DATABASE_URL=<dev DB from .env> python database/data_migrations/reclassify_notes_020.py
```

against the local dev DB (`experiments`) after the PR1 migration `b7e2c9a41d05`
was applied. The rules are applied exactly as written in the #118 spec; nothing
was tuned to change the numbers. The **Audit notes** section below is what the
numbers say, including the parts that look wrong.

## Raw output

```
==============================================================================
reclassify_notes_020 -- plan report
==============================================================================
experiments total:                                1009
experiments with ZERO notes:                      88
  sample: , AUTO_MH_001, AUTO_MH_002, AUTO_MH_003, AUTO_MH_004, AUTO_MH_005, AUTO_MH_006, CF-01, CF-02, CF-03, CF-04, HPHT_MH_001, HPHT_MH_002, HPHT_MH_003, MHE-75, MHE-76, MHE-77, nan, SERUM_JW_164, SERUM_MH_007
legacy notes (created_by IS NULL):                1131
PR1-era notes (created_by set, left untouched):   0

-- Rule 1: oldest legacy note per experiment by min(id) -> description
  notes to promote to 'description':              917
  notes set to 'observation' (result_id NULL):    0
  experiments keeping a PR1-era description:      0
  experiments already promoted by a prior run:    0

-- Rule 2: legacy notes reading 'nan' -> needs_review, never promoted
  'nan' legacy notes:                             4
  ...newly flagged needs_review by this run:      4
  experiments whose OLDEST note is 'nan' and therefore end with NO description: 4
  OTHER_JW_002, OTHER_JW_003, OTHER_JW_004, OTHER_JW_001

-- Rule 3: brine_modification_description -> 'modification' note on the result
  notes to insert:                                128
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
  DISCARDED as filler:                            174
  PRESERVED as observation, needs_review=true:    1678
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
       77  'gas, liquid'
       63  'Day 1.0 results'
       43  'Day 2.0 results'
       41  'Day 6.0 results'
       31  'gas, liquid, solid'
       28  't=0'
       26  'Gas and liquid sample'
       25  'End of exp.'
       24  'Day 3.0 results'
       24  'Gas, liquid'
       18  'Day 7.0 results'
       16  'Pre-rxn brine check'
       13  'day 10 nmr'
       13  'Day 14.0 results'
       12  't=1d, liquid'

-- Review queue (needs_review = true after --apply)
  'nan' legacy notes newly flagged:               4
  preserved result descriptions:                  1678
  TOTAL rows landing in the review queue:         1682
==============================================================================
before: {'description_notes': 0, 'experiments_with_description': 0, 'modification_notes': 0, 'observation_notes': 1131, 'review_queue': 0, 'notes_total': 1131}

Dry run — pass --apply to commit changes.
```

## Audit notes (what surprised me, not adjusted for)

1. **The filler pattern catches far fewer rows than the review queue can absorb.**
   It discards 174 of 1961 result descriptions and preserves **1,678** as
   `needs_review` observations — 854 distinct texts. Two families dominate the
   preserved set and are, by inspection, filler the spec did not anticipate:
   - **Code-generated fallbacks from other parsers** — `Day 1.0 results`,
     `Day 7.0 results`, `Analysis results for Day N` — written by
     `scalar_results_service.py` / `scalar_results.py` when no description was
     supplied. **285 rows.** These are the same species as `Master upload — day`
     (which the spec does discard) but come from a different code path.
   - **Multi-fraction sample lists** — `gas, liquid`, `Gas, liquid`,
     `gas, liquid, solid`, `Gas and liquid sample`, `t=1d, liquid`. **216 rows**
     match a comma/and/`+`/`/`-separated list of `gas|liquid|solid`. The spec's
     alternation only accepts a single fraction or the literal `gas + liquid`.

   If Mat agrees these are filler, widening rule 4 to those two families drops the
   review queue from **1,682 to roughly 1,180**. I did not make that change: the
   spec says to report a surprise rather than tune the regex, and "fraction list" is
   arguably information (which phases were sampled) that a `sample_type` enum was
   explicitly ruled out of this task. Decision needed.

2. **Four experiments end with no description at all** — `OTHER_JW_001/002/003/004`,
   the known `"nan"` rows. Rule 2 forbids promoting the `nan` note and nothing is
   promoted in its place. `OTHER_JW_001` has a second, real note; the script does
   not promote it because that would be a guess. If you want the next-oldest
   note promoted when the oldest is `nan`, say so and I'll add it as an explicit
   rule.

3. **88 experiments have zero notes**, so they get no description from this
   backfill. Two of them have broken IDs: experiment row 504 has `experiment_id =
   'nan'` and row 701 has `experiment_id = ''`. Those look like the same
   NaN-stringification class of bug at experiment-creation time and are outside
   this task's rules — flagged for a separate cleanup.

4. **`Master upload — day 46115.0`** (result 1382, experiment 676) is a result
   whose `time_post_reaction_days` is 46115 — an Excel serial date that was read
   as a duration. The description is correctly discarded as filler; the result
   row itself is a data-quality defect unrelated to this task.

5. **Nothing has been dual-written yet** on the dev DB (`PR1-era notes: 0`), so
   the "already mirrored" counters are all zero here. On the lab PC they will be
   non-zero for any upload run between deploying PR1 and applying PR2; the script
   handles that idempotently and reports the counts.

## Expected state after `--apply` (for definition-of-done item 6)

| Metric | Before | Expected after |
|---|---|---|
| `note_type = 'description'` rows | 0 | 917 |
| experiments with a description | 0 | 917 |
| `note_type = 'modification'` rows | 0 | 128 |
| `note_type = 'observation'` rows | 1,131 | 214 legacy + 1,678 preserved = 1,892 |
| `needs_review = true` (the review queue) | 0 | **1,682** |
| notes total | 1,131 | 2,937 |

The script exits non-zero if the post-apply review-queue count differs from the
plan.
