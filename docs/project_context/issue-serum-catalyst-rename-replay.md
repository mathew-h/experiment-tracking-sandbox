# Replay the 2026-07-28 SERUM_Catalyst rename at incident scale as a regression test

**Type:** test
**Area:** `tests/services/bulk_uploads/`, `tests/api/`, `scripts/`
**Priority:** medium
**GitHub issue:** #108
**Split from:** #100 (`issue-bulk-upload-dry-run.md`), acceptance criterion 6, which that issue closed without meeting

---

## Problem

#100's last unmet criterion was:

> Replaying the two 2026-07-28 SERUM_Catalyst workbooks against a snapshot of the
> pre-incident database yields a plan of 80 renames and 0 creates.

Everything the criterion tests now exists — the conflict branch, `dry_run`, the
structured plan, file-level rejection, the plan hash, and the preview UI. What is
missing is proof that it holds at the **scale and shape of the real incident** rather
than on the 1–3 row fixtures the shipped tests use. 80 renames across 10 base IDs with
a/b/c replicates and four `-t` timepoints exercises row ordering, chain-rename
collisions and the timepoint token together, in a way a small fixture does not.

## Why the criterion cannot be met literally

Checked on 2026-07-29 while closing #100:

- **Both workbooks are absent.** `20260728_SERUM_catalyst_001_006_renamed.xlsx` and
  `20260728_SERUM_catalyst_007_010.xlsx` are in neither the repo nor
  `docs/sample_data/` (`.gitignore:13` excludes `*.xlsx` there, so they were never
  committed and are not on any clean checkout).
- **No pre-incident snapshot exists.** The only dump on disk is
  `docs/sample_data/experiments_20260511_010002.sql`, from 2026-05-11 — months before
  the 80 originals were created. There is no `backups/` directory in the repo.
- **The old→new mapping is recorded nowhere.** No script, migration, doc or test holds
  the `old_experiment_id` → `experiment_id` pairs the workbooks carried.

The criterion is therefore permanently unmeetable as worded. What follows is
reconstructable instead.

## What *is* recoverable

The two ID **sets** survive in full, which is most of the way there:

- **The 80 intended (new-scheme) IDs**, with expected `status`, `initial_ph`,
  `rock_mass_g`, `temperature_c`, `water_mL`, compound and `amount_mg` — transcribed
  verbatim from the workbooks into the `expected` temp table in
  `scripts/sql/verify_serum_catalyst_target_state.sql` (80 rows, confirmed by count).
- **The 69 old-scheme leftover IDs** — `scripts/serum_catalyst_leftovers.txt`
  (`SERUM_Catalyst_002a-t3` … `SERUM_Catalyst_040-t20`).
- **The 11 IDs common to both schemes** — enumerated in Section 5 of the same SQL
  script (`001a/b/c-t1`, `003a/b/c-t7`, `006-t3`, `008-t20`, `009a/b/c-t1`), with which
  arm each should describe.

69 + 11 = 80, matching the script's own `80 keep / 69 delete / 149 total` inventory in
Section 7. So the old-scheme ID set is complete.

**What must be inferred, not recovered:** which old ID mapped to which new ID. Both
schemes use the same `a/b/c` × `-t1/-t3/-t7/-t20` structure over sequential indices
(old `001`–`040`, new `001`–`010`), so the mapping is very likely ordinal, but this is
an inference and the reconstructed test must say so in a comment rather than imply it
replays the real files.

## Proposal

1. **Build the fixture in code, not from a workbook.** A helper that writes an
   in-memory `.xlsx` (openpyxl, already a dependency) from the 80 old→new pairs — the
   pairs live in the test as an explicit table, derived from the two sources above with
   the ordinal-mapping assumption commented. Do not add a binary fixture to
   `docs/sample_data/`; it would be gitignored and absent on a clean checkout, which is
   exactly why the E2E spec `02-bulk-upload-experiments.spec.ts` cannot run today.
2. **Seed the 80 old-scheme rows** with the pre-incident conditions (pH, rock mass,
   temperature, water volume and additive per arm are all in the `expected` table).
3. **Assert the three cases, all through `dry_run=true`:**
   - `overwrite=TRUE`, correct row order → `counts.renames == 80`, `counts.creates == 0`,
     `counts.conflicts == 0`, and the DB byte-identical after (row count and
     `max(updated_at)` before/after, the check the criterion names).
   - `overwrite` blank → 80 conflicts, 0 creates, whole file refused, each conflict
     naming both IDs. **This is the actual 2026-07-28 failure mode**; pre-fix it
     returned 80 creates and reported success.
   - Row order that puts a rename target on top of a not-yet-renamed row → the
     `CHAIN RENAME CONFLICT` the plan should surface at preview time. Covers the 11
     collision IDs, the expensive part of the incident.
4. **Add a commit-path assertion for the happy case** so the test proves the renames
   apply, not just that they were planned — with the cleanup fixture the API conftest
   requires (see Notes).
5. **Record the reconstruction in this file** — where each ID set came from and that the
   mapping is ordinal-by-inference — so a future reader does not mistake it for a replay
   of the original workbooks.

## Acceptance criteria

- [ ] A test seeds 80 old-scheme experiments and previews an 80-row rename workbook generated in code
- [ ] `overwrite=TRUE` in correct order yields `renames == 80`, `creates == 0`, `conflicts == 0`
- [ ] The preview leaves the database byte-identical, verified by row count and `max(updated_at)` before/after
- [ ] `overwrite` blank yields 80 conflicts, 0 creates, and the whole file refused
- [ ] A collision-inducing row order surfaces `CHAIN RENAME CONFLICT` at preview time
- [ ] The committed run actually renames all 80 and creates nothing
- [ ] No `.xlsx` fixture is added under `docs/sample_data/` (generated in code instead)
- [ ] The test file states which parts of the scenario are reconstructed and which are verbatim
- [ ] Full backend suite green with no edits to pre-existing assertions

## Notes

- **Test-only — no locked component need be touched.** The parsers already emit
  everything being asserted. If a real defect surfaces at 80-row scale, that is its own
  issue with its own `CLAUDE.md` §5 sign-off, not a silent fix inside this one.
- **`tests/api/conftest.py` trap:** the fixture session sits on a connection with an
  outer transaction already open. A router `db.rollback()` discards the test's own seed
  rows (so "the originals survived the rejection" is not observable through that
  session — assert `commit` was never called instead), and a router `db.commit()`
  consumes the fixture transaction so teardown no-ops and rows **really persist** in
  `experiments_test`. An 80-row commit test without a cleanup fixture will break other
  files. Pattern: `tests/api/test_bulk_uploads_plan_gate.py`.
- **ID-grammar footgun:** experiment IDs in tests get parsed. A 3-part
  `Type_Initials_Index` ID makes the parser read the middle token as researcher initials
  and auto-populate a `researcher` field change — this broke two tests during #100 item
  2. `SERUM_Catalyst_NNN` is 3-part, so `Catalyst` will be read as initials. Expect it
  and assert around it rather than renaming the fixture, since the real IDs are the
  point of this test.
- `scripts/sql/verify_serum_catalyst_target_state.sql` is read-only and safe to run
  against the read-only psql role (`docs/PSQL_ACCESS.md`). Section 4 flags a known
  defect in the original workbook worth reproducing or explicitly excluding.
- Related: `issue-bulk-rename-circular-dependency.md` — the row-ordering problem case 3
  above will surface but does not fix.
- Also still unmet from #100: #107 / `issue-upload-plan-all-endpoints.md` (criterion 1 in
  full).
