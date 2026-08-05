# bug: `normalize_id` conflated real experiments, and the finders resolved it by guessing

> **Status 2026-08-05 — FIXED.** Branch `fix/id-match-ambiguity`. Found during
> the issue #109 investigation and recorded there as out of scope; this is the
> follow-through.

## Root cause

`backend/services/bulk_uploads/_id_match.py::normalize_id` deleted every
non-alphanumeric character **and** stripped leading zeros from numeric
segments, so a sequential re-run collapsed onto an unrelated experiment:
`SERUM_JW_010-2` and `SERUM_JW_102` both became `serumjw102`.
`fuzzy_find_experiment` then returned `.first()` of the normalized scan — an
arbitrary one of the two, with nothing logged. A bulk upload could attach
results to the wrong experiment silently.

Measured against the dev DB, 2026-08-05:

- **13 experiment pairs** collided (1009 experiments): `SERUM_JW_092/009-2`,
  `102/010-2`, `112/011-2`, `122/012_2`, `123/012_3`, `132/013_2`, `133/013-3`,
  `142/014_2`, `143/014-3`, `152/015_2`, `153/015-3`, `162/016_2`, `163/016-3`.
- **3 sample pairs** collided (680 samples), via the same key through
  `fuzzy_find_sample`: `23UM042/23UM004.2`, `23UM052/23UM005.2`,
  `202505255?/20250525_5`. Not previously recorded anywhere.

## What shipped

1. **Run-delimited `normalize_id`.** Split into maximal alpha/digit runs, strip
   leading zeros inside each digit run, join with `_`. `SERUM_JW_010-2` ->
   `serum_jw_10_2`, `SERUM_JW_102` -> `serum_jw_102`.
   This is a **strict refinement**: equal new keys imply identical run
   sequences, which imply equal old keys, so it can only split an old
   equivalence class, never merge two. Collision count on the dev DB is now
   **0 for experiments and 0 for samples**.
   Every equivalence the finders rely on survives, including the missing
   separator: `HPHT001`, `HPHT_001`, `HPHT-001`, `HPHT_1` all -> `hpht_1`.
2. **The finders no longer guess.** `find_experiment_matches` /
   `find_sample_matches` return **all** matches; `fuzzy_find_experiment` /
   `fuzzy_find_sample` return `None` on 0 **or** >1 and log a structlog
   warning (`ambiguous_experiment_id` / `ambiguous_sample_id`) naming the
   candidates. Signatures unchanged, so no caller broke.
3. **`ScalarResultsService._find_experiment` raises
   `AmbiguousExperimentIdError`** (a `ValueError`) instead of returning `None`.
   This one is load-bearing: `create_scalar_result_ex` treats `None` as "not
   found" and falls through to `auto_create_treatment_experiment`, so a silent
   `None` would have **fabricated an experiment row**.
   `get_scalar_results_for_experiment` (a read helper behind a GET) catches it
   and returns `[]` rather than 500ing, logging
   `ambiguous_experiment_id_on_read` — the raising path in `_id_match` does not
   log, only the `fuzzy_find_*` wrappers do.
4. **`timepoint_modifications.py` reports both candidates** in its row error
   instead of "not found".

## Accepted leniency losses

Two documented equivalences are gone on purpose, both cases where the old key
was guessing:

- `HPHT_0014B` (`hpht_14_b`) no longer matches `HPHT_001_4B` (`hpht_1_4_b`).
- The 13 experiment pairs and 3 sample pairs above.

A workbook ID that no longer matches gets the existing "not found" row error,
which a researcher fixes by using the exact ID. A clean failure beats a silent
wrong attachment.

## Out of scope — recorded, not fixed

**Three sibling finders still end in `.first()`.**
`backend/services/icp_service.py:757`,
`backend/services/bulk_uploads/aeris_xrd.py:46` and
`backend/services/bulk_uploads/xrd_upload.py:63` each hand-roll their own
delimiter-stripping SQL lookup. None of them strips leading zeros, so **none
has the 13-pair defect** — a collision check on a delimiter-only key across all
1009 dev experiment IDs returns **0 groups** (verified 2026-08-05). They keep
the latent habit: a future ID pair differing only in separators would resolve
arbitrarily. Consolidating them onto `find_experiment_matches` would touch two
more locked parsers and their suites, so it needs its own `/start-task`.
