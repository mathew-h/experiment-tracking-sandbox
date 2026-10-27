# Master Results upload stores a numeric-0 note cell as the text '0', and OVERWRITE cannot clear it

**Type:** fix
**Area:** `backend/services/bulk_uploads/master_bulk_upload.py`
**Priority:** high
**Related:** issue #118 (typed notes), issue #122 PR-D, issue #116 (OVERWRITE `_sheet_fields`)

---

## Problem

Two defects in the Master Results (Dashboard) upload combine.

**1. A numeric 0 in a note cell becomes the note text `'0'`.** The Dashboard sheet fills both free-text columns with XLOOKUP. XLOOKUP returns the number 0 when the source cell is empty. `_parse_text` (`master_bulk_upload.py:561-575`) catches only None and NaN, then returns `str(val).strip()`, so int 0 becomes `"0"`. `notes._clean` (`backend/services/notes.py:45-52`) filters only blank and `'nan'`, so `sync_result_note` stores the `"0"`. The row-merge join uses the same helper (`master_bulk_upload.py:690-697`), which is how `'0; Liq'` and `'low P gas, cold liquid; 0'` got stored.

The Modification formula in `Master_Results_Tracker_v5.xlsx` now has a `LET(... IF(OR(m="",m=0),"",m))` guard. The Description formula does not. The current sheet still emits int 0 in the Description column on 14 rows (e.g. HPHT_297 T14, HPHT_313 T4, HPHT_307 T14), so every upload still writes `'0'` observation notes.

**2. An OVERWRITE row with a blank note cell never clears the parser's own note.**

```python
# master_bulk_upload.py:1035-1039
# The Modification Note is this parser's own 'modification' slot (inside the vial-day's SAVEPOINT).
if modification:
    sync_result_note(
        db, exp_result, NoteType.modification, modification, created_by=_NOTE_SOURCE,
    )
```

`sync_result_note` already deletes the caller's own slot when the text is blank (`notes.py:127-131`). The `if modification:` guard makes that branch unreachable from this parser. The observation mirror has the same guard (`scalar_results_service.py:241-248`). Issue #116 made an OVERWRITE row clear the sheet's own blank columns through `_sheet_fields`, but only for `SCALAR_UPDATABLE_FIELDS`. The note slots were never included.

The current rule is documented in two places: the module docstring (`master_bulk_upload.py:23`) and `docs/upload_templates/master_bulk_upload.md:21` both say "a blank cell writes no note and leaves an earlier one in place." The Timepoint Modifications parser already does the opposite under overwrite (`test_typed_notes_dual_write.py::test_timepoint_modifications_overwrite_blank_deletes_the_callers_note`).

Net effect: after the sheet was corrected and re-uploaded with OVERWRITE=TRUE on all 380 rows, every `'0'` note survived.

## Impact

**Researchers see false modifications.** The Results tab shows a MODIFICATION note reading `0`. The MOD badge (`ResultsTab.tsx:274`, driven by `has_modification_note` at `experiments.py:761`) flags timepoints where nothing was done to the vial. Power BI shows `0` in `v_dim_timepoints.modification_note` and in `v_notes`. The calculation engine does not read notes, so no derived field is affected.

**Deleting a `'0'` in the UI doesn't stick.** ModificationsLog has 14 manual deletions of `'0'` notes on HPHT_304, HPHT_309 and HPHT_310 between 2026-10-14 and 2026-10-20, and the next upload re-created each one. HPHT_309's were deleted between 11:49 and 12:42 on 10-16 and were back at 13:22.

Data as of the 2026-10-26 01:00 backup:

| Rows | note_type | note_text | created_by |
|---|---|---|---|
| 105 | modification | `'0'` exactly | master_bulk_upload (all result-scoped, 77 experiments, none sharing a result with another modification note) |
| 81 | observation | `'0'` exactly | master_bulk_upload (all result-scoped) |
| 7 | observation | 0 joined into text, e.g. `'0; Liq'` | master_bulk_upload |
| 6 | observation / result_note | 0 joined into text | reclassify_notes_020 |
| 1 | description | `'0'` (CF_020-5_Puddle) | NULL |
| 31 | observation | `'nan'` | NULL |

The 2026-10-26 16:28 upload probably added a few more observation `'0'`s (HPHT_307/308 T17, HPHT_326 T3) after this backup was taken.

**Six notes were overwritten with no record.** Six of the 105 modification notes (ids 8010-8013, 8025, 8034) were created on 2026-10-07 with other text and overwritten to `'0'` on 2026-10-09 13:56. `sync_result_note` writes no ModificationsLog row when it rewrites a note, so the prior text exists only in the nightly backups. Mat confirmed on 2026-10-26 that the prior text is not needed. These six are deleted with the rest.

## Fix

This touches a locked parser. **Mat Hearl signed off on 2026-10-26** on A and B below. Record the sign-off in footnote 6 of `docs/LOCKED_COMPONENTS.md`.

**A. Treat a zero note cell as blank.** In `_parse_text`, return None when the value is a number equal to 0 (int or float, excluding bool) or when the stripped text is exactly `"0"`. This follows the `_parse_measurement_float` precedent (`master_bulk_upload.py:301-310`).

- `_parse_text` is called only for the two note columns (`:693`, `:975`, `:988`), so this one change fixes the single-row path and the merge join and touches nothing else.
- Do not put this in `notes._clean`. It is shared with the Timepoint Modifications parser, `scalar_results.py` and `quick_upload.py`, which don't have the XLOOKUP problem.

**B. An OVERWRITE row clears this parser's own note slots for blank cells.**

- **Modification.** Change the guard at `:1036` to `if modification or overwrite:` and pass `modification` (possibly None) through. `sync_result_note` then deletes only the `(result, 'modification', 'master_bulk_upload')` slot. Notes signed by a researcher, `migrate_change_requests_021` or `reclassify_notes_020` are outside the slot key and are untouched.
- **Observation.** In `create_scalar_result_ex`, also call `sync_result_note(..., None, ...)` when `overwrite` is true **and** `sheet_fields` is not None and contains `'description'`.
  - Gating on the declared `_sheet_fields` limits the change to the Master parser. `scalar_results.py:313` and `quick_upload.py:302` send `_note_source` but no `_sheet_fields`, so their behavior doesn't change.
  - This is narrower than #116's `sheet_fields is None` means "everything" rule, on purpose.
- **Mixed OVERWRITE.** A merged vial-day with OVERWRITE on only some of its rows already resolves to `overwrite=False` (`:699-709`), so it clears nothing. That is consistent.
- **Blast radius on the current v5 sheet.** The first OVERWRITE upload after deploy deletes no real text:
  - All 48 non-`'0'` master-signed modification notes were checked against the sheet. Every one whose timepoint is on the sheet has the same text there.
  - The observation slots that would be cleared all hold `'0'`.
  - HPHT_297 T14's merged `'low P gas, cold liquid; 0'` becomes `'low P gas, cold liquid'`.

**C. Cleanup: `database/data_migrations/delete_zero_notes_022.py`.** Follow the 020/021 pattern: dry run by default, and `--apply` only after Mat has audited the dry-run report.

- **Targets:** `note_type IN ('modification','observation') AND note_text = '0' AND created_by = 'master_bulk_upload'`. Exact match, no `LIKE`. That is 186 rows on the 2026-10-26 backup.
- **Per row:** write a ModificationsLog snapshot in the `bulk_delete_notes` shape (`experiments.py:686-703`): `modification_type='delete'`, `modified_table='experiment_notes'`, `modified_by='delete_zero_notes_022'`, and `old_values` with id, note_text, note_type, result_id, created_by and needs_review. Then delete the note. Run everything in one transaction.
- **Report only, never touched:** the 13 joined-zero notes, the legacy description `'0'` and the 31 `'nan'` observations.
- **Idempotent:** a second `--apply` deletes 0 rows.
- **Report location:** save the dry-run report as `docs/issues/delete-zero-notes-022-dryrun-<date>.md`, matching `reclassify-notes-020-dryrun-2026-09-08.md`.
- **Order:** deploy A and B first. Otherwise the next upload re-creates observation `'0'`s from the 14 zeroed Description cells. The script is still needed after deploy, because the sheet does not cover every affected result.
- **Why not Alembic:** this deletes rows, which breaks the additive-only migration rule, and `downgrade` could not restore them. The ModificationsLog snapshot is the recovery path.

**D. Sheet (no code).** Put the same `LET` guard on the Dashboard's Description formula. With A shipped this is belt-and-braces.

## Acceptance criteria

**Parser (A):**
- [x] A Dashboard row whose Modification or Observation cell is int 0, float 0.0 or text `"0"` writes no note. A merged vial-day of `"Liq"` and `0` stores `"Liq"`. Add tests to `tests/services/bulk_uploads/test_master_bulk_upload.py` next to `test_blank_modification_writes_no_modification_note` (`:2923`).

**OVERWRITE behavior (B):**
- [x] An OVERWRITE row with a blank Modification cell deletes the existing `master_bulk_upload` modification note.
- [x] A researcher-signed modification note on the same result survives that upload.
- [x] The same two checks hold for Observation.
- [x] A non-overwrite row with a blank cell still leaves the slot alone.
- [x] A mixed-OVERWRITE vial-day clears nothing.
- [x] An overwrite with a blank Description through `scalar_results.py` or `quick_upload.py` leaves that parser's observation note unchanged.
- [x] The B tests go in `tests/services/bulk_uploads/test_typed_notes_dual_write.py`.

**Cleanup script (C):**
- [x] New `tests/data_migrations/test_delete_zero_notes_022.py` covers: the dry run changes nothing; `--apply` deletes only exact-`'0'` master-signed modification and observation notes; it skips `'0; Liq'`, NULL-author `'0'` and researcher-signed `'0'`; it writes one ModificationsLog snapshot per deleted note; a second run is a no-op.
- [ ] Mat has audited the dry-run report on production before `--apply`. — lab PC, post-deploy
- [x] After `--apply`, this query returns 0: `SELECT count(*) FROM experiment_notes WHERE note_text = '0' AND created_by = 'master_bulk_upload' AND note_type IN ('modification','observation')`. (mirror; production pending, lab PC post-deploy)
- [x] After `--apply`, `SELECT count(*) FROM modifications_log WHERE modified_by = 'delete_zero_notes_022'` equals the number of rows deleted. (mirror; production pending, lab PC post-deploy)

**End to end:**
- [x] HPHT_309's Results tab shows no MOD badge and no `0` modification on T+0, T+3, T+7, T+10 or T+13. (mirror; production after deploy + 022 `--apply`)
- [x] Re-uploading the current `Master_Results_Tracker_v5.xlsx` after deploy creates no `'0'` notes. (mirror; production after deploy)
- [x] `.venv/Scripts/pytest tests/services/ tests/regression/ tests/api/ tests/data_migrations/ -v` passes.

**Docs:**
- [x] Updated: the module docstring (`master_bulk_upload.py:18-23`), `docs/upload_templates/master_bulk_upload.md` (lines 21 and 44: the blank and zero rules for note columns), footnote 6 of `docs/LOCKED_COMPONENTS.md`, the `database/data_migrations/README.md` quick reference, and a deploy runbook entry in `docs/working/issue-log.md`.

## Open questions

1. **Should `sync_result_note` log rewrites and deletes?** It changes and deletes notes without a ModificationsLog row, which is how the six 2026-10-09 notes lost their text. Logging there would cover every parser that uses it. This was not in the agreed scope. Recommendation: a follow-up issue.
2. **Who protects UI edits to upload-written notes?** `PATCH /experiments/{id}/notes/{note_id}` (`experiments.py:1651-1653`) edits the text but keeps `created_by`. A researcher who fixes a `master_bulk_upload` note in the UI is still in the parser's slot, so the next upload rewrites it, and with B, an OVERWRITE row with a blank cell deletes it. No current master-signed note matches a UI edit, so nothing is at risk today. Options: re-sign the note to the editor on a text change, or document "edit the sheet, not the UI" for notes written by an upload.
   - **Resolved (2026-10-27, branch `fix/ui-edits-leave-upload-note-slot`): re-sign to the editor.** `backend/services/notes.py::release_upload_slot` re-signs a result-scoped note signed `master_bulk_upload`, `scalar_results` or `quick_upload` to the caller when `PATCH /notes/{id}` changes its text or type, or `PATCH /notes/bulk` retypes it; the existing ModificationsLog row records the old and new `created_by`. The next upload neither rewrites nor deletes the edit; if the sheet still holds the old text, it writes a new note beside it. Out of scope: the email-signed Timepoint Modifications slot (an editor's own OVERWRITE Timepoint Modifications upload can still reach an edited `modification` note), other signers, experiment-level notes, UI deletes, backfill.
   - **Production audit:** `docs/issues/audit-queries.sql` Q5 lists parser-signed notes that still carry a pre-fix UI edit. Dev mirror (2026-10-26 backup): 0 rows. A draft without the `n.updated_at >= ml.created_at` condition returned 2 false positives on HPHT_315: a description retype (description → observation → description, 2026-10-20) matched both of the experiment's never-edited master observation notes. Production output, pasted after deploy: _pending_. Empty means done; bring any rows to Mat before acting.

## Notes

- Branch `fix/zero-note-cells` from `develop`; open the PR with `gh pr create --base develop`.
- No Alembic revision, no view change and no `docs/CALCULATIONS.md` change. Power BI reads notes live, so a refresh after `--apply` is enough.
- New Experiments made the opposite overwrite call for `initial_note`: a blank cell with overwrite leaves the notes alone (`issue-blank-initial-note-parses-to-nan.md`). This issue doesn't change that. The description is one note per experiment, not a per-timepoint note owned by a parser.
- The legacy `created_by IS NULL` rows (one description `'0'`, 31 `'nan'` observations) predate this bug. They are listed in the dry run for a separate decision.
