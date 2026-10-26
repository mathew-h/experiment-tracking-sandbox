# Zero Note Cells Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the Master Results upload from storing a numeric-0 note cell as the note `'0'`, let an OVERWRITE row clear the parser's own note slots, and delete the 186 existing `'0'` notes with an audited one-off script.

**Architecture:** Fix A is one rule in the parser's `_parse_text` (the only helper the two note columns go through). Fix B opens the already-existing "blank text deletes the caller's slot" branch of `sync_result_note` to OVERWRITE rows, gated on the Master parser's declared `_sheet_fields` so the other parsers are untouched. Fix C is a dry-run-by-default data migration in the 020/021 shape.

**Tech Stack:** Python 3, SQLAlchemy ORM, PostgreSQL, pandas/openpyxl, pytest.

**Spec:** `docs/issues/issue-zero-note-cells.md`

## Global Constraints

- `backend/services/bulk_uploads/master_bulk_upload.py` is LOCKED. Mat Hearl signed off 2026-10-26 on exactly two edits there: the `_parse_text` zero rule (A) and the modification guard `if modification:` → `if modification or overwrite:` (B). Docstring/comment updates describing those two edits are allowed. No other change to any file under `backend/services/bulk_uploads/`.
- Do NOT change `backend/services/notes.py` (`_clean` is shared with the Timepoint Modifications, `scalar_results.py` and `quick_upload.py` parsers).
- No Alembic revision, no model/enum change, no view change, no `docs/CALCULATIONS.md` change.
- Zero rule, verbatim: return None "when the value is a number equal to 0 (int or float, excluding bool) or when the stripped text is exactly `"0"`."
- Observation clear, verbatim: call `sync_result_note(..., None, ...)` "when `overwrite` is true **and** `sheet_fields` is not None and contains `'description'`."
- Cleanup targets, verbatim: `note_type IN ('modification','observation') AND note_text = '0' AND created_by = 'master_bulk_upload'`. Exact match, no `LIKE`.
- Cleanup audit row: `modification_type='delete'`, `modified_table='experiment_notes'`, `modified_by='delete_zero_notes_022'`, `old_values` = `{id, note_text, note_type, result_id, created_by, needs_review}` (the `bulk_delete_notes` shape, `backend/api/routers/experiments.py:686-703`), `new_values=None`.
- Commit format (inline task): `[fix] <imperative, <50 chars, no period>` then `- Tests added: yes/no` / `- Docs updated: yes/no`, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use `git commit -F <file>` for multi-line messages.
- Tests run with `.venv/Scripts/pytest`. Never run two pytest processes at once (shared `experiments_test` DB).

## Review Focus

1. **numpy scalars from pandas.** pandas hands the parser `numpy.int64(0)` / `numpy.float64(0.0)`, and `isinstance(numpy.int64(0), int)` is False. The zero rule must treat them as 0 (use `numbers.Real`). Pinned in Task 1.
2. **Booleans.** `False == 0` in Python. A bool cell must NOT become None; `False` stays `"False"`. Pinned in Task 1.
3. **Padded text.** `" 0 "` is blank; `"0.0"` and `"10"` are real text and survive. Pinned in Task 1.
4. **A stale joined note healed by re-upload.** A stored master note `'0; Liq'` is rewritten to `'Liq'` by a re-upload of the merged `"Liq"` + `0` rows. Pinned in Task 2.
5. **OVERWRITE on a brand-new result.** A blank cell on an OVERWRITE row that creates the result (no slot exists) is a no-op, not an error. Pinned in Task 2.

---

### Task 1: Treat a zero note cell as blank (fix A)

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (`_parse_text`, ~line 561; module docstring ~lines 18-23)
- Modify: `docs/upload_templates/master_bulk_upload.md` (free-text bullet, line 21; row-merge `0` bullet, ~line 44)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py` (add after `test_a_real_modification_is_stored_as_a_modification_note`, ~line 2955)

**Interfaces:**
- Produces: `_parse_text(val: Any) -> Optional[str]` returns None for blank, NaN, a non-bool `numbers.Real` equal to 0, or text whose `.strip()` is exactly `"0"`. Signature unchanged.

- [ ] **Step 1: Write the failing tests** (import `_parse_text` from the module alongside the existing imports, and `numpy as np`)

```python
@pytest.mark.parametrize("cell", [0, 0.0, np.int64(0), np.float64(0.0), "0", " 0 "])
def test_parse_text_treats_a_zero_cell_as_blank(cell):
    assert _parse_text(cell) is None

@pytest.mark.parametrize("cell, expected", [
    (False, "False"), (True, "True"), ("0.0", "0.0"), ("10", "10"), (5, "5"), ("Liq", "Liq"),
])
def test_parse_text_keeps_non_zero_values(cell, expected):
    assert _parse_text(cell) == expected

@pytest.mark.parametrize("cell", [0, 0.0, "0"])
def test_zero_modification_cell_writes_no_note(db_session, cell):
    # seed HPHT_ZERONOTE01 (exp_num 8971); _v3_row(..., nh4=1.0, modification=cell)
    # -> no errors; _notes_for(result, NoteType.modification) == []

@pytest.mark.parametrize("cell", [0, 0.0, "0"])
def test_zero_observation_cell_writes_no_note(db_session, cell):
    # seed HPHT_ZERONOTE02 (8972); _v3_row(..., nh4=1.0, description=cell)
    # -> no errors; _notes_for(result, NoteType.observation) == []

def test_merged_vial_day_of_liq_and_zero_stores_liq(db_session):
    # seed HPHT_ZERONOTE03 (8973); two rows, same day 7.0:
    #   _v3_row(..., description="Liq", ph=7.1)   and   _v3_row(..., description=0, ph=None, nh4=1.0)
    # -> no errors; observation notes == [("Liq", "master_bulk_upload")]
```

Use a distinct experiment ID per parametrized case if the seed would collide (suffix the case index), since `db_session` rolls back per test.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "parse_text or zero" -v`
Expected: the zero cases FAIL (`'0'` returned / note stored); the keep cases pass.

- [ ] **Step 3: Implement the zero rule in `_parse_text`**

Check order: None → NaN → `isinstance(val, numbers.Real) and not isinstance(val, bool) and val == 0` → None → strip → `""` or `"0"` → None. Extend the docstring with one paragraph: the Dashboard fills both note columns with XLOOKUP, which returns the number 0 for an empty source cell, so 0 is a blank here (the `_parse_measurement_float` precedent); only called for the two note columns.

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_master_bulk_upload.py -v`
Expected: all PASS.

- [ ] **Step 5: Docs**

Module docstring "Typed notes" paragraph: add "A cell holding 0 (number or the text '0') is blank: the Dashboard's XLOOKUP returns 0 for an empty source cell." In `docs/upload_templates/master_bulk_upload.md`, add the same zero rule to the free-text bullet (line 21) and extend the "A `0` in the pH, conductivity or gas volume/pressure columns is a blank" bullet to name the two note columns. Edit with the Edit tool so the docs-sync hook fires.

- [ ] **Step 6: Commit**

`[fix] Treat a zero note cell as blank`

---

### Task 2: OVERWRITE clears the Master parser's own note slots (fix B)

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (modification guard ~line 1036 and its comment; module docstring sentence "A blank cell writes NO note and leaves an earlier one in place.")
- Modify: `backend/services/scalar_results_service.py` (`create_scalar_result_ex`, observation mirror ~lines 241-248)
- Modify: `docs/upload_templates/master_bulk_upload.md` (line 21 blank rule; the Overwrite Scope bullet)
- Test: `tests/services/bulk_uploads/test_typed_notes_dual_write.py` (Master section, after `test_master_reupload_updates_note_slot_instead_of_appending`; scalar/quick cases may go here too)

**Interfaces:**
- Consumes: Task 1's `_parse_text`.
- Uses as-is: `sync_result_note(db, result, note_type, note_text: Optional[str], created_by: str)` — blank/None text deletes the `(result.id, note_type, created_by)` slot, no-op when empty. `sheet_fields` in the master parser is `frozenset(result_data)` and already contains `"description"`.
- Produces: in `create_scalar_result_ex`, the mirror calls `sync_result_note` when (`note_source` and text present) OR (`note_source` and `overwrite` and `sheet_fields is not None` and `"description" in sheet_fields`), passing the cleaned text (possibly None).

- [ ] **Step 1: Write the failing tests** (use the file's `_V4_HEADERS`, `_rows`, `_dashboard`, `_notes`; index 2 = Observation Note, 13 = Modification Note, 14 = OVERWRITE)

- `test_master_overwrite_blank_modification_deletes_the_parsers_note` — upload `_rows("TNZ_001")` (FALSE) → day-7 has both notes; re-upload day 7 only with Modification `None`, observation text unchanged, `"TRUE"` → day-7 notes are exactly `[observation "Liquid sample, slightly cloudy"]`.
- `test_master_overwrite_blank_modification_keeps_a_researcher_note` — as above, plus before the re-upload add an `ExperimentNotes(note_type=modification, result_id=<day-7>, note_text="Swapped septum", created_by="researcher@addisenergy.com", experiment_fk=…, experiment_id=…)` → after: the researcher note survives (same id, same text); the master modification note is gone.
- `test_master_overwrite_blank_observation_deletes_the_parsers_note` and `test_master_overwrite_blank_observation_keeps_a_researcher_note` — the same two with the Observation Note blanked and an `observation` researcher note.
- `test_master_non_overwrite_blank_cells_leave_both_slots` — re-upload day 7 with both note cells `None` and `"FALSE"` → both master notes unchanged (same ids, same text).
- `test_master_mixed_overwrite_vial_day_clears_nothing` — after the first upload, re-upload two day-7 rows with both note cells `None`, one `"TRUE"` (NH4 5.2) and one `"FALSE"` (pH 7.1, NH4 `None`) → both master notes unchanged.
- `test_master_overwrite_rewrites_a_joined_zero_note` — seed a master-signed observation `'0; Liq'` on the day-7 result after the first upload; re-upload two day-7 rows, observation `"Liq"` and `0`, both `"TRUE"`, complementary measurements → the slot now reads `"Liq"` (same note id).
- `test_master_overwrite_blank_on_a_new_result_is_a_no_op` — first-ever upload of a day-7 row, both note cells `None`, `"TRUE"` → no errors, `created == 1`, no notes.
- `test_scalar_overwrite_blank_description_leaves_the_note` — `ScalarResultsUploadService.bulk_upsert_from_excel_ex` with headers `["Experiment ID", "Time (days)", "Description", "Gross Ammonium (mM)"]`: first `"first text"`, then a blank Description with `overwrite_all=True` → the `scalar_results` note still reads `"first text"`.
- `test_quick_upload_overwrite_blank_description_leaves_the_note` — `quick_upload_from_excel(..., "hydrogen", overwrite_all=True)` with headers `["Experiment ID*", "Time (days)*", "H2 Conc (ppm)*", "Description"]`, `sheet_name="Data"`: first with text, then blank → the `quick_upload` note survives.

- [ ] **Step 2: Run to verify the right ones fail**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/test_typed_notes_dual_write.py -v`
Expected: the two `..._deletes_the_parsers_note` tests FAIL; the rest pass (they pin behavior that must not change).

- [ ] **Step 3: Implement**

Master parser: guard becomes `if modification or overwrite:`, passing `modification` (possibly None); update the comment to say an OVERWRITE row's blank cell clears this parser's own slot only. Service: widen the mirror condition per the Interfaces block; replace the "blank -> no call, an earlier mirror stays" comment with the rule and why it is gated on the declared `_sheet_fields` (only the Master parser declares them; `scalar_results.py` / `quick_upload.py` keep their behavior on purpose — narrower than #116's `None` means "everything").

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/pytest tests/services/bulk_uploads/ -v`
Expected: all PASS.

- [ ] **Step 5: Docs**

Module docstring: replace "A blank cell writes NO note and leaves an earlier one in place." with: a blank cell writes no note; without OVERWRITE it leaves an earlier one in place, and on an OVERWRITE row (every row of the vial-day TRUE) it deletes this parser's own note for that type — never a note signed by anyone else. Same rule in the template doc's line-21 bullet and one sentence in the Overwrite Scope bullet.

- [ ] **Step 6: Commit**

`[fix] Let OVERWRITE clear the parser's own notes`

---

### Task 3: Cleanup script `delete_zero_notes_022.py` (fix C)

**Files:**
- Create: `database/data_migrations/delete_zero_notes_022.py`
- Create: `tests/data_migrations/test_delete_zero_notes_022.py`
- Modify: `database/data_migrations/README.md` (both quick-reference tables)

**Interfaces:**
- Produces, in `database.data_migrations.delete_zero_notes_022`:
  - `SOURCE_TAG = "delete_zero_notes_022"`, `TARGET_AUTHOR = "master_bulk_upload"`
  - `@dataclass Plan`: `targets`, `joined_zero`, `other_author_zero`, `null_author_zero`, `nan_notes` — each `list[ExperimentNotes]`
  - `build_plan(db: Session) -> Plan` — `targets` is the exact Global-Constraints query ordered by id. Report-only buckets: `joined_zero` = text not exactly `'0'` but with `'0'` as one of its `'; '`-separated parts (e.g. `'0; Liq'`, `'low P gas, cold liquid; 0'`), any author; `other_author_zero` = exact `'0'` with a non-NULL author outside the target set (other author, or `description`/`result_note` types); `null_author_zero` = exact `'0'` with `created_by IS NULL`; `nan_notes` = `lower(trim(note_text)) = 'nan'`.
  - `apply_plan(db: Session, plan: Plan) -> list[int]` — per target, adds the audit row (Global Constraints shape, plus `experiment_id`/`experiment_fk` from the note) then deletes the note; flushes, does NOT commit; returns deleted ids.
  - `print_report(plan: Plan) -> None` — Markdown: one table of bucket counts, then a list per bucket (`id | experiment_id | note_type | result_id | created_by | note_text`), targets broken down by `note_type`.
  - `main(apply: bool) -> None` — `get_db()` session; prints report and before-counts; dry run returns without writing; `--apply` runs `apply_plan`, commits once, re-counts, exits 2 if the deleted count or the after-count disagrees with the plan, rolls back and exits 1 on any exception. CLI: `argparse`, `--apply`. Keep the `sys.path.insert(0, …parents[2])` line so `python database/data_migrations/delete_zero_notes_022.py` works directly.
- Module docstring: background (one paragraph, cite the issue doc), the rules above, why it is not Alembic (deletes rows; `downgrade` could not restore them; the ModificationsLog snapshot is the recovery path), deploy order (A and B first), usage.

- [ ] **Step 1: Write the failing tests** (fixture `migration_session`; seed two experiments, one result each, notes via `ExperimentNotes(...)`)

Seed set: master modification `'0'`, master observation `'0'`, master observation `'0; Liq'`, master modification `'Swapped brine'`, researcher (`a@addisenergy.com`) observation `'0'`, NULL-author description `'0'`, NULL-author observation `'nan'`.

- `test_dry_run_changes_nothing` — `build_plan` + `print_report` (capsys) → note count and `modifications_log` count unchanged; report mentions each bucket.
- `test_build_plan_buckets` — `targets` = exactly the two master `'0'` ids; `joined_zero` = the `'0; Liq'` id; `other_author_zero` contains the researcher id; `null_author_zero` = the description id; `nan_notes` = the `'nan'` id.
- `test_apply_deletes_only_the_targets` — after `apply_plan`: the two target ids are gone; every other seeded note still exists with its text unchanged.
- `test_apply_writes_one_snapshot_per_deleted_note` — `ModificationsLog` rows with `modified_by == SOURCE_TAG` = 2, each `modification_type == "delete"`, `modified_table == "experiment_notes"`, `new_values is None`, `old_values` equal to `{id, note_text: "0", note_type, result_id, created_by: "master_bulk_upload", needs_review}` for its note.
- `test_second_run_is_a_no_op` — apply, then `build_plan` again → `targets == []` and a second `apply_plan` returns `[]` and writes no log row.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/pytest tests/data_migrations/test_delete_zero_notes_022.py -v`
Expected: FAIL (ImportError: module does not exist).

- [ ] **Step 3: Implement the script per the Interfaces block.**

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/Scripts/pytest tests/data_migrations/ -v`
Expected: all PASS.

- [ ] **Step 5: README** — add a row for `delete_zero_notes_022` to both quick-reference tables: purpose "Delete master-signed `'0'` modification/observation notes (XLOOKUP zero cells), with a ModificationsLog snapshot each"; when "Once, after the zero-note-cells parser fix is deployed; dry run first, `--apply` after Mat audits the report".

- [ ] **Step 6: Commit**

`[fix] Add delete_zero_notes_022 cleanup script`

---

### Task 4: Production-mirror verification and dry-run report (controller)

**Gate:** restoring `docs/sample_data/experiments_20261026_010002.sql` replaces the dev DB `experiments`. Requires Mat's explicit OK before Step 1.

- [ ] **Step 1:** Restore the 2026-10-26 backup into the dev DB per memory `restoring-prod-backups-to-dev` (`pg_restore` as `experiments_user`, `--no-owner --no-acl`), then `alembic upgrade head`. Expected: `alembic current` = head; `SELECT count(*) FROM experiment_notes WHERE note_text = '0' AND created_by = 'master_bulk_upload' AND note_type IN ('modification','observation')` = 186.
- [ ] **Step 2:** `python database/data_migrations/delete_zero_notes_022.py` (dry run). Save `docs/issues/delete-zero-notes-022-dryrun-2026-10-26.md`: header (source backup, command, status "AWAITING AUDIT by Mat Hearl; `--apply` NOT run on production"), raw output. Expected counts against the spec table: targets 186 (105 modification + 81 observation), joined 13, NULL-author description 1, `'nan'` 31. Any difference is explained in the report, not hidden.
- [ ] **Step 3:** On the mirror: snapshot all non-`'0'` `master_bulk_upload` notes (id, text); run `--apply`; upload `docs/sample_data/Master_Results_Tracker_v5.xlsx` through `MasterBulkUploadService.from_bytes_ex` and commit. Expected: the zero-count query = 0; `SELECT count(*) FROM modifications_log WHERE modified_by = 'delete_zero_notes_022'` = 186; every snapshotted non-`'0'` note whose result the sheet covers still holds the same text, except HPHT_297 T14's `'low P gas, cold liquid; 0'` → `'low P gas, cold liquid'`. Record the diff in the report.
- [ ] **Step 4:** Run `.venv/Scripts/pytest tests/services/ tests/regression/ tests/api/ tests/data_migrations/ -v` (one process). Expected: 0 failed, apart from failures shown to pre-exist on `develop`.
- [ ] **Step 5:** Chrome DevTools: `/experiments/HPHT_309` Results tab shows no MOD badge and no `0` modification on T+0, T+3, T+7, T+10, T+13 (restart the dev backend on this branch first; check for an orphan worker on port 8000).
- [ ] **Step 6: Commit** the report: `[fix] Add delete_zero_notes_022 dry-run report`

---

### Task 5: Close-out docs

**Files:** `docs/LOCKED_COMPONENTS.md` (footnote ⁶), `docs/working/issue-log.md`, `docs/issues/issue-zero-note-cells.md` (acceptance checkboxes)

- [ ] **Step 1:** Footnote ⁶: append a paragraph — 2026-10-26, Mat Hearl's sign-off on two edits to `master_bulk_upload.py`: a zero note cell is blank (`_parse_text`), and an all-TRUE OVERWRITE vial-day with a blank note cell deletes the parser's own slot for that type (modification in the parser, observation through `create_scalar_result_ex` gated on `_sheet_fields`); other authors' notes are never touched; `scalar_results.py` / `quick_upload.py` unchanged.
- [ ] **Step 2:** Issue-log entry in the house shape (files changed, why, verification with exact counts from Task 4, deploy runbook: deploy → OVERWRITE upload is safe → Mat runs 022 dry run on the lab PC, audits, `--apply`, runs the two count queries, refreshes Power BI; sheet guard D; follow-ups = the spec's two open questions).
- [ ] **Step 3:** Tick the acceptance criteria met; mark the production ones (`--apply` audit and counts) `[ ]` with "lab PC, post-deploy".
- [ ] **Step 4: Commit** `[fix] Document zero note cell fix and runbook`
