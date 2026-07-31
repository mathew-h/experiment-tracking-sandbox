# Issue #114 — Master Results residual #111 gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close four of the residual gaps #111 left behind in the Master Results parser — error-list ordering, an invisible GC-precedence decision, carryover gas geometry persisted without a reading, and three dead entry points — without changing any schema.

**Architecture:** Every code change lands in one file, `backend/services/bulk_uploads/master_bulk_upload.py`, plus one deletion in `backend/config/settings.py`. Two changes are additive and observable through `MasterUploadResult.warnings` (already rendered by the existing UI, so there is **no frontend work in this plan**); one is a behavior change inside `_resolve_h2`; one is a deletion of dead API surface with a mechanical test conversion. Tasks 1–4 are independent of each other and each ends with its own passing test; Task 5 runs last because it rewrites call sites in every test the earlier tasks touch.

**Tech Stack:** Python 3.11, pandas (Excel parsing), SQLAlchemy 2.x ORM, pytest. No new dependency, no migration, no `database/models/` change.

## Global Constraints

- **`backend/services/bulk_uploads/` is a locked component** (`.claude/CLAUDE.md` §5). Sign-off for this plan was given by the user on 2026-07-30 for exactly the items below. Do not extend the change to any other parser in that directory.
- **No schema change.** Nothing in this plan touches `database/models/`, `alembic/versions/`, or `database/event_listeners.py`. `ScalarResults` gains no column — item 1 was explicitly decided as a warning, not a persisted field. If a task appears to need a column, stop and escalate.
- **Issue #114 item 2 is out of scope** (a rename that drops the `h2` token, e.g. `FL Hydrogen (ppm)`). Deferred to #113 by user decision on 2026-07-30, because both warnings must share one false-positive design and #113 is still open and unstarted. Task 6 records the deferral; do not build it.
- **Commit format:** `[#114] <imperative description>` under 50 chars, no trailing period, with `- Tests added: yes/no` and `- Docs updated: yes/no` in the body (`.claude/CLAUDE.md` §8).
- **Branch:** `chore/issue-114-master-results-residual-gaps`, already created off `develop`. Any PR uses `--base develop`.
- **Never write to `docs/project_context/`** — a `PostToolUse` hook copies every `docs/` write there automatically. `.claude/rules/MODELS.md` is *not* hook-synced and is edited directly.
- **Test command for this plan:** `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q`. Never run two pytest processes at once — the test DB is shared and an interrupted run leaves a schema `create_all` cannot repair.
- **Known-unstable baseline:** the full backend suite has 3 pre-existing failures in `tests/test_pg_backup_restore.py` and 4 errors in `tests/test_fresh_install_migration.py`, plus an intermittent `tests/test_pxrf_analysis.py::test_create_pxrf_reading`. Do not treat that as a safe baseline and do not claim it as clean; scope verification to the directories this plan touches.
- **Do not restart the uvicorn or Vite servers** (`backend/CLAUDE.md`, `frontend/CLAUDE.md`). No task in this plan requires a running server.

---

## File Structure

| File | Responsibility in this plan |
|------|------------------------------|
| `backend/services/bulk_uploads/master_bulk_upload.py` | All four behavior changes. `_process_bytes` gains row-keyed error collection (Task 1) and a superseded-row tally (Task 2); `_resolve_h2` stops returning carryover geometry (Task 4); `MasterBulkUploadService` loses two static methods and `MasterUploadResult` loses `as_tuple` (Task 5). |
| `backend/config/settings.py` | Task 5 only: delete `master_results_path` and `_default_master_results_path()`, whose sole reader was `sync_from_path`. |
| `tests/services/bulk_uploads/test_master_bulk_upload.py` | New tests for Tasks 1, 2, 4; a strengthened existing test for Task 3; the `_upload` helper and 46 call-site conversions plus two test deletions in Task 5. |
| `tests/integration/test_master_results_sync_endpoint.py` | Task 5 only: two `from_bytes` call sites converted to `from_bytes_ex`. |
| `.claude/rules/MODELS.md` | Task 6: `ScalarResults` → Hydrogen section — the DI-superseded reading is now surfaced as a warning, and geometry is not stored without a concentration. |
| `docs/user_guide/BULK_UPLOADS.md` | Task 6: §1 Master Results Sync — the new warning, the geometry rule, and error ordering. |
| `docs/CALCULATIONS.md` | Task 6: Hydrogen Amount — where the three inputs come from now that geometry requires a concentration. |
| `docs/issues/issue-114-master-results-residual-gaps.md` | Task 6: the local issue doc (repo convention — every worked issue has one), with acceptance criteria and the item-2 deferral. |

---

### Task 1: Errors listed in sheet-row order (issue #114 item 3)

`_process_bytes` is two-phase by necessity: Phase 1 resolves every row's `(experiment_id, timepoint)` identity so duplicate keys can be tallied before anything is written, Phase 2 upserts. Errors are appended in that execution order, so **every** Phase-1 error precedes **every** Phase-2 error — a row 5 bad-Duration error is printed above a row 2 upsert failure. Researchers read the list against the spreadsheet top-down.

The fix collects row-level errors with their row number and sorts them in at the end. Do **not** regex `^Row (\d+)` out of the finished strings — the row number is in hand at every append site, and two of the four sites use a different message prefix (`Row 5: invalid Duration…` vs `Row 5 (SERUM_001a): …`).

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py:371-565` (`_process_bytes`)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: no signature change. `MasterUploadResult.errors` remains `List[str]`; only the order of its row-level entries changes. Later tasks append to `out.warnings` (unaffected) and must **not** append to `out.errors` directly from inside the row loops — use the `row_errors` list introduced here.

- [ ] **Step 1: Write the failing test**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`, immediately after `test_duplicate_vial_and_timepoint_is_an_error`'s block (the "Duplicate vial-timepoint rejection" section near the end of the file):

```python
# ---------------------------------------------------------------------------
# Error ordering (issue #114 item 3)
# ---------------------------------------------------------------------------

def test_errors_are_listed_in_sheet_row_order(db_session: Session):
    """The error list reads top-down against the spreadsheet.

    _process_bytes resolves every row's identity (Phase 1) before upserting any
    row (Phase 2), so appending in execution order put EVERY Phase-1 error above
    EVERY Phase-2 one. Here row 2 fails in Phase 2 (no such experiment) and row 3
    fails in Phase 1 (unparseable Duration); before issue #114 the row 3 message
    came first, which is the opposite of how the sheet reads.

    Nothing is seeded on purpose. create_scalar_result_ex falls back to
    auto_create_treatment_experiment (backend/services/scalar_results_service.py
    :86-95), which needs an existing parent experiment — with an empty table
    there is none, so the not-found ValueError is guaranteed.
    """
    xlsx = _master_excel_v3([
        _v3_row("HPHT_ORD_MISSING", 7.0),   # sheet row 2 — Phase 2: experiment not found
        _v3_row("HPHT_ORD02", "not a day"),  # sheet row 3 — Phase 1: invalid Duration
    ])

    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert len(result.errors) == 2, f"expected one error per row, got: {result.errors}"
    assert result.errors[0].startswith("Row 2 ("), (
        f"the row 2 Phase-2 failure must come first, got: {result.errors}"
    )
    assert result.errors[1].startswith("Row 3:"), (
        f"the row 3 Phase-1 failure must come second, got: {result.errors}"
    )
```

Note the two prefixes differ on purpose: the Phase-2 message is `f"Row {row_num} ({exp_id}): …"` and the Phase-1 Duration message is `f"Row {row_num}: invalid Duration (Days) …"`. Neither experiment is seeded — `HPHT_ORD02` never reaches Phase 2, and `HPHT_ORD_MISSING` is meant to fail there.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py::test_errors_are_listed_in_sheet_row_order -q`

Expected: FAIL on the first assertion — `result.errors[0]` is the row 3 Duration message (`Row 3: invalid Duration (Days) 'not a day'`), because Phase 1 appended it before Phase 2 ran at all.

- [ ] **Step 3: Write minimal implementation**

In `_process_bytes`, just below the existing alias block:

```python
    out = MasterUploadResult()
    errors = out.errors
    warnings = out.warnings
    feedbacks = out.feedbacks
    created = updated = skipped = 0
```

add:

```python
    # Row-level errors carry their sheet row number and are sorted in at the end
    # (issue #114 item 3). This function is two-phase by necessity — identity and
    # duplicate tallying for every row, then the upserts — so appending straight
    # to out.errors listed every Phase-1 error above every Phase-2 one: a row 5
    # Duration error above a row 2 upsert failure, while researchers read this
    # list against the sheet top-down. Sheet-level messages have no row number
    # and belong at the top; every one of them returns immediately, so
    # out.errors is empty by the time the sort runs, and extending rather than
    # assigning keeps them first if a non-returning one is ever added.
    row_errors: List[Tuple[int, str]] = []
```

Convert the four row-level append sites. Phase 1:

```python
        if error is not None:
            row_errors.append((row_num, error))
            continue
```

Phase 2 — the duplicate rejection:

```python
        if key_counts[(exp_id, normalize_timepoint(time_post_reaction))] > 1:
            row_errors.append((row_num, (
                f"Row {row_num} ({exp_id}): duplicate experiment ID and timepoint "
                f"(day {time_post_reaction:g}). Each vial gets one row per timepoint "
                f"— give each vial its own ID (e.g. SERUM_001a-t7, SERUM_001b-t7). "
                f"No row for this vial-day was written."
            )))
            continue
```

Phase 2 — both exception handlers:

```python
        except ValueError as exc:
            savepoint.rollback()
            row_errors.append((row_num, f"Row {row_num} ({exp_id}): {exc}"))
        except Exception as exc:
            savepoint.rollback()
            row_errors.append((row_num, f"Row {row_num} ({exp_id}): unexpected error — {exc}"))
```

Then, immediately before the final assignment:

```python
    # Stable sort — two errors on one row keep the order they were found in.
    out.errors.extend(message for _, message in sorted(row_errors, key=lambda item: item[0]))

    out.created, out.updated, out.skipped = created, updated, skipped
    return out
```

Leave the `errors = out.errors` alias in place: the three sheet-level errors (`Failed to read file`, `File has no sheets`, `missing required columns`) still use it and each returns immediately.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q`

Expected: PASS, including the new test and every pre-existing error-assertion test (`test_duplicate_vial_and_timepoint_is_an_error`, `test_missing_required_columns_returns_error`, and the blank/NaN ID tests). A single-error result is order-insensitive, so nothing else should shift.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "$(cat <<'EOF'
[#114] Sort upload errors by sheet row number

- Row-level errors collected with their row number, sorted before return;
  sheet-level messages stay at the top (they all return early)
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: One warning when a DI reading was superseded (issue #114 item 1)

Phase 2 already computes, per row, whether Full Loop overrode a populated direct-injection cell — `h2_di_superseded` in each feedback record. `feedbacks` reaches the browser and nothing renders it (`frontend/src/api/bulkUploads.ts:9` types it; no non-test consumer exists), and the discarded value is not persisted, so a researcher asking "why is this not the DI number I entered?" has no way to find out from the app.

The decided fix (user, 2026-07-30) is the cheapest one that answers that question: **one file-level warning**, rendered by the warnings panel `BulkUploadRow.tsx:236-252` already draws. No frontend change, no schema change. It is silent unless precedence was actually contested — measured against the live v3 Dashboard on 2026-07-30, **0 of 499 rows** carry a reading in both blocks, so this fires on no sheet in use today.

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py:484-565` (Phase 2 loop and the block after it)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py:1238-1256` (extend `test_feedback_records_which_gc_block_was_used`) and one new test

**Interfaces:**
- Consumes: `_resolve_h2`'s existing 5-tuple return `(h2_ppm, gas_volume_mL, gas_pressure_psi, source, di_ppm)` — unchanged by this task.
- Produces: one additional entry in `MasterUploadResult.warnings`, appended after all per-row warnings. No signature change.

- [ ] **Step 1: Write the failing test**

`test_feedback_records_which_gc_block_was_used` (line 1238) already builds exactly the right fixture — one row where FL supersedes DI, one where DI is used. Extend it rather than duplicating the fixture. Add to the end of that test:

```python
    superseded = [w for w in result.warnings if "instead of direct injection" in w]
    assert len(superseded) == 1, (
        f"exactly one file-level warning, not one per row, got: {result.warnings}"
    )
    assert "1 row" in superseded[0], superseded[0]
    assert "(2)" in superseded[0], (
        f"the warning must name the sheet row so it can be found, got: {superseded[0]}"
    )
```

`HPHT_WARN04` is the first data row, so its sheet row number is 2 (`row_num = idx + 2`); `HPHT_WARN05` (row 3) uses DI and must not be listed.

Then add a new test in the "Warnings and per-row H2 source feedback" section, after `test_feedback_records_which_gc_block_was_used`:

```python
def test_no_supersede_warning_when_precedence_is_uncontested(db_session: Session):
    """The warning fires only when a DI value actually lost.

    A warning that appears on ordinary sheets is a warning researchers learn to
    ignore. FL-only, DI-only and neither-block rows are all the normal case —
    measured on the v3 Dashboard, 0 of 499 rows carry a reading in both blocks.
    """
    _seed_experiment(db_session, "HPHT_SUP01", 8891)
    _seed_experiment(db_session, "HPHT_SUP02", 8892)
    _seed_experiment(db_session, "HPHT_SUP03", 8893)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_SUP01", 7.0, fl_h2=115.0),              # FL only
        _v3_row("HPHT_SUP02", 7.0, di_h2=42.0, di_vol=30.0),  # DI only
        _v3_row("HPHT_SUP03", 7.0, nh4=5.0),                  # neither
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 3
    assert [w for w in result.warnings if "direct injection" in w] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q -k "which_gc_block or uncontested"`

Expected: `test_feedback_records_which_gc_block_was_used` FAILS on `len(superseded) == 1` (the list is empty — nothing produces this warning yet). `test_no_supersede_warning_when_precedence_is_uncontested` PASSES already — it is the false-positive guard, and a test that passes before the change is the point. Note that in the report, and do not "fix" it.

- [ ] **Step 3: Write minimal implementation**

Declare the tally just above the Phase 2 loop (next to `# Phase 2 — upsert what is left.`):

```python
    # Rows where Full Loop overrode a populated direct-injection cell. Reported
    # once, at file level, after the loop (issue #114 item 1).
    superseded_rows: List[int] = []
```

Inside the loop, replace the `feedbacks.append({...})` block with:

```python
            # di_ppm comes from _resolve_h2's own parse — re-reading the cell
            # here would let this flag drift from the precedence decision if the
            # DI branch ever gains filtering.
            di_superseded = h2_source == "full_loop" and di_ppm is not None
            if di_superseded:
                superseded_rows.append(row_num)
            feedbacks.append({
                "row": row_num,
                "experiment_id": exp_id,
                "action": action,
                "h2_source": h2_source,
                "h2_di_superseded": di_superseded,
            })
```

After the loop — place it above the Task 1 error sort so warnings and errors are finalised in a predictable order:

```python
    # The per-row h2_di_superseded flag above reaches the client in `feedbacks`
    # and nothing renders it, so a researcher could not learn from the app why a
    # stored value is not the DI number they entered — and the discarded reading
    # is not persisted either. One file-level warning says it in the panel the UI
    # already draws (issue #114 item 1). Deliberately silent when precedence was
    # never contested: 0 of 499 rows on the v3 Dashboard (2026-07-30) carry a
    # reading in both blocks, and a warning that fires on ordinary sheets is one
    # researchers learn to ignore.
    if superseded_rows:
        shown = ", ".join(str(r) for r in superseded_rows[:10])
        if len(superseded_rows) > 10:
            shown += f", and {len(superseded_rows) - 10} more"
        label = "row" if len(superseded_rows) == 1 else "rows"
        warnings.append(
            f"Full Loop reading used instead of direct injection on "
            f"{len(superseded_rows)} {label} ({shown}). 'DI H2 (ppm)' also held a "
            "value there and Full Loop takes precedence, so the direct-injection "
            "reading was not stored and cannot be recovered from the database."
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q`

Expected: PASS. Two pre-existing tests build both-block rows and must still pass because neither asserts an empty warning list — `test_full_loop_wins_when_both_present` (asserts `errors == []`) and `test_zero_h2_is_a_real_measurement` (`fl_h2=0.0, di_h2=99.0`, so `0` supersedes and the warning fires; it asserts errors and values only). `test_h2s_column_is_not_reported_as_a_dropped_h2_reading:1207` asserts `result.warnings == []` but its row is FL-only, so it stays clean — if that test fails, the new warning is firing when precedence was uncontested and the condition is wrong.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "$(cat <<'EOF'
[#114] Warn when a DI reading is superseded by Full Loop

- One file-level warning naming the affected rows; renders in the existing
  warnings panel, no frontend or schema change
- Silent when precedence is uncontested (0 of 499 rows on the v3 sheet)
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Pin the same-block geometry pairing with measured magnitudes (issue #114 addendum, consequence 1)

The issue's addendum asks for "a regression test pinning this, since the failure would be silent and plausible-looking." **The test already exists** — `test_di_wins_ignores_stray_full_loop_gas_geometry` (line 1005), added in #111's fix wave. Do not add a second one. What is missing is the measured justification: the test uses invented magnitudes (3935 vs 10) and its docstring argues from first principles, so a future reader cannot tell that **all 35 DI-won rows in the live v3 sheet carry populated Full Loop geometry** and that the wrong pairing would compute `h2_micromoles` off a volume 141× too large.

This task is test-strengthening only: no production code changes, and the test must pass both before and after.

**Files:**
- Modify: `tests/services/bulk_uploads/test_master_bulk_upload.py:1005-1036`

**Interfaces:**
- Consumes: `_v3_row(...)`'s existing keyword parameters `fl_vol`, `fl_psi`, `di_vol`, `di_psi`.
- Produces: nothing other tasks depend on. Task 4 changes `_resolve_h2`'s *no-concentration* branch, which this test does not exercise (its row has a DI concentration), so this test must still pass unchanged after Task 4.

- [ ] **Step 1: Retune the test to the measured magnitudes**

Replace the whole of `test_di_wins_ignores_stray_full_loop_gas_geometry` with:

```python
def test_di_wins_ignores_stray_full_loop_gas_geometry(db_session: Session):
    """When DI supplies the concentration, FL gas volume/pressure are ignored.

    Load-bearing, not defensive (issue #114 addendum, 2026-07-30). Measured on
    the live v3 Dashboard: 35 rows resolve to DI, and every one of them also
    carries populated Full Loop geometry left over from a previous run — the GC
    sheets always carry some stale columns. Geometry therefore has to come from
    the block that won the concentration. Had precedence been built as
    "concentration from the winner, geometry from Full Loop", all 35 rows would
    compute h2_micromoles from 4235 mL instead of 30 mL — a 141x overstatement
    that produces a plausible-looking number, with nothing to flag it.

    The mirror of test_full_loop_wins_when_both_present.
    """
    _seed_experiment(db_session, "HPHT_MIX01", 8881)

    xlsx = _master_excel_v3([
        # FL geometry is real carryover magnitude; DI's is a real injection.
        _v3_row("HPHT_MIX01", 7.0,
                fl_h2=None, fl_vol=4235.0, fl_psi=90.0,
                di_h2=42.0, di_vol=30.0, di_psi=14.7),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_MIX01")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(42.0)
    assert scalar.gas_sampling_volume_ml == pytest.approx(30.0), (
        "must be DI's 30 mL injection volume, never FL's 4235 mL carryover"
    )
    assert scalar.gas_sampling_pressure_MPa == pytest.approx(14.7 * _PSI_TO_MPA, rel=1e-3)
```

- [ ] **Step 2: Run the test — it must PASS**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py::test_di_wins_ignores_stray_full_loop_gas_geometry -q`

Expected: PASS. This is the one task in the plan with no red phase — the behavior is already correct and this pins it with the real numbers. If it fails, stop: the pairing is broken and that is a bug report, not a test to adjust.

- [ ] **Step 3: Prove the test can still fail**

Temporarily break the DI branch of `_resolve_h2` (`master_bulk_upload.py:241-248`) by reading `"FL Gas Volume (mL)"` instead of `"DI gas volume (mL)"`, re-run the command from Step 2, and confirm it FAILS with `4235.0 != 30.0`. Then revert the edit with `git checkout -- backend/services/bulk_uploads/master_bulk_upload.py` and re-run to confirm PASS. A guard test nobody has seen fail is not yet a guard.

Do not commit the temporary break. Verify `git status` shows only the test file modified before Step 4.

- [ ] **Step 4: Commit**

```bash
git add tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "$(cat <<'EOF'
[#114] Pin geometry pairing with measured GC magnitudes

- Retunes the existing DI-wins guard to the live sheet's 4235 mL carryover
  vs 30 mL injection; records that 35 DI-won rows depend on it
- Tests added: no (strengthens an existing test)
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Stop storing gas geometry with no concentration (issue #114 addendum, consequence 2)

`_resolve_h2`'s final branch — neither block has an `H2 (ppm)` value — still returns the Full Loop gas columns, with this rationale (`master_bulk_upload.py:250-251`): *"Keep reading the Full Loop gas columns so a row recording only the sampling geometry behaves as it did pre-#111."*

That held when a blank gas cell meant no data. Per Mat (2026-07-30) carryover is now a permanent condition of the GC sheets, and the field of record is `H2 (ppm)` on either sheet. Measured: 207 FL rows and 464 DI rows carry gas geometry with no concentration attached. Nothing computes wrong — `_calculate_hydrogen` requires a concentration, so the derived fields stay `None` — but up to 207 rows per upload write `gas_sampling_volume_ml=4235` into `ScalarResults`, where a later reader cannot distinguish it from a real measurement.

Verified before writing this plan: **no test relies on geometry-only rows.** Only five tests pass FL geometry (lines 804, 899, 957, 1016, 1049) and every one carries a concentration in one block or the other. `test_superseded_di_flag_comes_from_the_resolver:1235` asserts `_resolve_h2(neither)[3:] == (None, None)`, slicing from index 3, so it does not read the geometry slots.

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py:207-258` (`_resolve_h2` docstring and final branch), and the module docstring at `:17-19`
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_resolve_h2` keeps its exact signature — `Tuple[Optional[float], Optional[float], Optional[float], Optional[str], Optional[float]]` returning `(h2_ppm, gas_volume_mL, gas_pressure_psi, source, di_ppm)`. Only the values in slots 1 and 2 of the no-concentration branch change, from the FL columns to `None`.

- [ ] **Step 1: Write the failing tests**

Add both to the "Warnings and per-row H2 source feedback" section, after `test_no_gc_reading_leaves_h2_unset` (line 1099) — they belong beside it:

```python
def test_geometry_without_a_concentration_is_not_stored(db_session: Session):
    """Carryover gas columns with no reading attached are dropped.

    The GC sheets always carry stale values in some columns (Mat, 2026-07-30) and
    the field of record is 'H2 (ppm)'. Measured on the v3 Dashboard, 207 rows
    carry FL geometry with no FL concentration; storing it would put 4235 mL into
    ScalarResults where no later reader could tell it from a real measurement.
    Nothing is computed from it either way — _calculate_hydrogen requires a
    concentration.
    """
    _seed_experiment(db_session, "HPHT_GEO01", 8895)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_GEO01", 7.0, nh4=5.0,
                fl_h2=None, fl_vol=4235.0, fl_psi=90.0,
                di_h2=None, di_vol=30.0, di_psi=14.7),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 1, "the row must still upload — NH4 is real data"

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_GEO01")
        .one()
    ).scalar_data
    assert scalar.gross_ammonium_concentration_mM == pytest.approx(5.0)
    assert scalar.h2_concentration is None
    assert scalar.gas_sampling_volume_ml is None, "carryover volume must not be stored"
    assert scalar.gas_sampling_pressure_MPa is None, "carryover pressure must not be stored"


def test_overwrite_clears_stale_geometry_when_the_reading_goes_away(db_session: Session):
    """OVERWRITE on a concentration-less row clears geometry instead of rewriting carryover.

    gas_sampling_volume_ml and gas_sampling_pressure_MPa are both in
    SCALAR_UPDATABLE_FIELDS (backend/services/scalar_results_service.py:17), so
    with overwrite=True every field absent from the row is set to None. Dropping
    the carryover geometry therefore also stops a re-upload from re-asserting a
    volume the second sheet no longer claims a reading for.
    """
    _seed_experiment(db_session, "HPHT_GEO02", 8896)

    first = _master_excel_v3([
        _v3_row("HPHT_GEO02", 7.0, fl_h2=115.0, fl_vol=4235.0, fl_psi=90.0),
    ])
    MasterBulkUploadService.from_bytes_ex(db_session, first)

    second = _master_excel_v3([
        _v3_row("HPHT_GEO02", 7.0, fl_h2=None, fl_vol=4235.0, fl_psi=90.0, overwrite=1.0),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, second)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.updated == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_GEO02")
        .one()
    ).scalar_data
    assert scalar.h2_concentration is None
    assert scalar.gas_sampling_volume_ml is None
    assert scalar.gas_sampling_pressure_MPa is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q -k "geometry_without or overwrite_clears_stale"`

Expected: both FAIL on the `gas_sampling_volume_ml is None` assertion, reporting `4235.0`.

- [ ] **Step 3: Write minimal implementation**

Replace the final branch of `_resolve_h2` (`master_bulk_upload.py:250-258`):

```python
    # No concentration in either block, so no geometry either (issue #114). The
    # pre-#111 allowance here kept the Full Loop gas columns so a row recording
    # only sampling geometry behaved as it always had. That assumed a blank gas
    # cell meant no data; carryover is now a permanent condition of the GC sheets
    # and 'H2 (ppm)' is the field of record (Mat, 2026-07-30), so those columns
    # hold a previous run's values on 207 of 499 rows. Nothing was computed from
    # them — _calculate_hydrogen needs a concentration — but persisting them put
    # a 4235 mL volume in ScalarResults that no later reader could tell from a
    # real measurement.
    return (None, None, None, None, di_ppm)
```

Also amend the `_resolve_h2` docstring's return description so it stays true. Change:

```
    Returns (h2_ppm, gas_volume_mL, gas_pressure_psi, source, di_ppm), where
    source is 'full_loop', 'di', or None when neither block has a
    concentration.
```

to:

```
    Returns (h2_ppm, gas_volume_mL, gas_pressure_psi, source, di_ppm), where
    source is 'full_loop', 'di', or None when neither block has a
    concentration — in which case the geometry is None too, since the gas
    columns carry the previous run's values.
```

And extend the module docstring's hydrogen paragraph (`:17-19`) with one sentence:

```
Hydrogen: Full Loop wins; 'DI H2 (ppm)' is used only when the Full Loop cell is
blank, and gas volume/pressure come from the same block. A value of 0 is a real
reading, not a blank. A row with no reading in either block stores no gas
geometry either — those columns carry stale values from previous runs.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q`

Expected: PASS, all of them. The five geometry-bearing tests all carry a concentration and take the FL or DI branch, so none is affected; `test_superseded_di_flag_comes_from_the_resolver` slices from index 3 and is untouched.

Then confirm no other suite reads this: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/ tests/integration/test_master_results_sync_endpoint.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "$(cat <<'EOF'
[#114] Drop carryover gas geometry with no GC reading

- _resolve_h2's no-concentration branch returns no geometry; carryover is
  permanent on the GC sheets and 207 of 499 rows were importing it
- Tests added: yes
- Docs updated: no (Task 6 covers MODELS.md/CALCULATIONS.md)

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Delete the dead entry points (issue #114 item 4)

`MasterBulkUploadService.from_bytes` and `sync_from_path` have no production callers — `backend/api/routers/bulk_uploads.py:394` uses `from_bytes_ex` exclusively. Both return `MasterUploadResult.as_tuple()`, which drops `warnings` by construction, so wiring anything to either would silently regress #111's acceptance criterion 3.

`sync_from_path` is deader than "no callers": issue #74 removed path-based sync, deleting both `/master-results/config` endpoints and the sync button (`docs/specs/master_results_sync.md:115`, `docs/milestones/M6_bulk_uploads.md:146`), and the tracker file it probes was moved to `99_Archive/` on 2026-07-30 with no `master_results_path` row in `AppConfig` — so it returns "file not found" unconditionally, advising the user to configure a path through a UI that no longer exists.

Three things therefore go, not two: both methods **and** `as_tuple`, which is the actual loaded gun and has no other caller. `settings.master_results_path` goes with them (user decision, 2026-07-30) — its only reader was `sync_from_path`, and its default runs `_default_master_results_path()` at import time, scanning `C:\Users\` for the archived file. Removal is safe for the lab PC: `SettingsConfigDict(extra="ignore")` (`backend/config/settings.py:52`) means a leftover `MASTER_RESULTS_PATH=` in `.env` is ignored, not an error. Neither `.env.example` nor `docs/ENVIRONMENT.md` mentions the variable — verified, nothing to update there.

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py:95-114` (`as_tuple` + docstring) and `:568-614` (`MasterBulkUploadService`)
- Modify: `backend/config/settings.py:1-67` (delete `_default_master_results_path`, the `master_results_path` field and its comment, and the now-unused `pathlib.Path` import)
- Modify: `tests/services/bulk_uploads/test_master_bulk_upload.py` (add `_upload` helper, convert 46 call sites, delete 2 tests)
- Modify: `tests/integration/test_master_results_sync_endpoint.py:64,90` (2 call sites)

**Interfaces:**
- Consumes: `MasterBulkUploadService.from_bytes_ex(db: Session, file_bytes: bytes) -> MasterUploadResult`, the only surviving entry point, unchanged by this task.
- Produces: `_upload(db: Session, xlsx: bytes) -> tuple` — module-local test helper in `test_master_bulk_upload.py` returning `(created, updated, skipped, errors, feedbacks)`. Nothing in `backend/` may import it.

- [ ] **Step 1: Add the test helper**

In `tests/services/bulk_uploads/test_master_bulk_upload.py`, directly below `_seed_experiment` in the Helpers section:

```python
def _upload(db: Session, xlsx: bytes) -> tuple:
    """(created, updated, skipped, errors, feedbacks) for the positional tests.

    Deliberately local to the tests. The parser no longer offers a return shape
    that drops `warnings` — MasterUploadResult.as_tuple and the two entry points
    that called it were deleted by issue #114 item 4, because anything wired to
    them would compute warnings and throw them away. Tests that assert on
    warnings use from_bytes_ex directly.
    """
    r = MasterBulkUploadService.from_bytes_ex(db, xlsx)
    return r.created, r.updated, r.skipped, r.errors, r.feedbacks
```

- [ ] **Step 2: Convert the call sites mechanically**

One scripted replacement — do not hand-edit 46 sites:

```powershell
$p = "tests/services/bulk_uploads/test_master_bulk_upload.py"
$content = [System.IO.File]::ReadAllText($p, [System.Text.Encoding]::UTF8)
$content = $content.Replace("MasterBulkUploadService.from_bytes(", "_upload(")
[System.IO.File]::WriteAllText($p, $content, (New-Object System.Text.UTF8Encoding $false))
```

`Get-Content -Raw | Set-Content -Encoding utf8` mojibake-corrupts em dashes and
other non-ASCII characters under PowerShell 5.1 — it did on this file when
Task 5's implementer ran it, and it had to be reverted and redone with an
explicit UTF-8 read/write as above.

`from_bytes_ex(` does not match — the trailing `(` in the search string prevents it. Verify: `Select-String -Path $p -Pattern "MasterBulkUploadService\.from_bytes\("` must return nothing, and `Select-String -Path $p -Pattern "from_bytes_ex"` must still return its 8 hits.

Calls stay wrapped across two lines (`_upload(\n        db_session, xlsx\n    )`). That is valid and keeps the diff purely mechanical — **do not** reflow them.

- [ ] **Step 3: Delete the two tests that only covered deleted surface**

Delete `test_sync_from_path_file_not_found_returns_error` (line 124, and its now-unused `import os` inside the function body). It asserts an error string that names "Bulk Uploads → Master Results Sync → Settings" — a UI removed by #74 — on a code path reachable from nothing. It also mutates `os.environ["MASTER_RESULTS_PATH"]` and clears the `get_settings` cache, which no longer resolves to anything after Step 5.

Delete `test_from_bytes_tuple_shape_unchanged` (line 1259). It asserts `len(out) == 5` on `from_bytes` — precisely the contract being removed.

- [ ] **Step 4: Convert the integration test**

`tests/integration/test_master_results_sync_endpoint.py:64` and `:90` each unpack the 5-tuple. Two sites, so use attribute access rather than a second helper:

```python
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)
```

and update the assertions in each test to read `result.created`, `result.errors`, and so on. Read the surrounding test bodies first and rename only what those two calls feed. Leave the file's name alone — it predates #74's removal of the sync endpoint and renaming it is out of scope.

- [ ] **Step 5: Delete the production surface**

In `backend/services/bulk_uploads/master_bulk_upload.py`, delete `as_tuple` from `MasterUploadResult` and rewrite the class docstring, which currently describes the tuple as still returned:

```python
@dataclass
class MasterUploadResult:
    """Master Results upload outcome.

    The one return shape. Issue #111 introduced it beside a legacy 5-tuple that
    had no slot for `warnings`; issue #114 deleted the tuple and the two entry
    points that produced it, since anything wired to them would compute warnings
    and drop them on the floor.
    """

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    feedbacks: List[Dict[str, Any]] = field(default_factory=list)
```

Then reduce `MasterBulkUploadService` to its one live method — delete `sync_from_path` and `from_bytes` entirely:

```python
class MasterBulkUploadService:
    @staticmethod
    def from_bytes_ex(db: Session, file_bytes: bytes) -> MasterUploadResult:
        """Parse an uploaded Master Results file.

        The only entry point. `POST /api/bulk-uploads/master-results` requires a
        multipart file (issue #74 removed path-based sync along with the
        /master-results/config endpoints and the sync button), so there is no
        second way in.
        """
        return _process_bytes(db, file_bytes)
```

`Tuple` is still used in `_resolve_h2`, `_resolve_row_identity` and Task 1's `row_errors` annotation, so leave the `typing` import list alone. Confirm with `Select-String -Path backend/services/bulk_uploads/master_bulk_upload.py -Pattern "Tuple"`.

In `backend/config/settings.py`, delete `_default_master_results_path()` (lines 8-45), the two-line comment and field at lines 65-67, and the now-unused `from pathlib import Path` at line 3. `Path` appears nowhere else in that file — verify with `Select-String -Path backend/config/settings.py -Pattern "Path"` returning nothing afterwards.

- [ ] **Step 6: Run the tests**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/ tests/integration/test_master_results_sync_endpoint.py tests/api/test_bulk_uploads.py -q`

Expected: PASS. `tests/api/test_bulk_uploads.py` is included because it mocks `from_bytes_ex` at lines 327, 342 and 369 — those mocks are unaffected, and this run proves the router still resolves.

Then prove nothing else referenced the deleted names:

```powershell
Select-String -Path . -Include *.py -Pattern "sync_from_path|as_tuple|master_results_path" -Recurse |
  Where-Object { $_.Path -notlike "*\legacy\*" }
```

Expected: no hits under `backend/`, `database/`, `scripts/` or `tests/`. Hits inside `docs/superpowers/plans/` and `docs/superpowers/specs/` are dated records and stay as they are, matching how issue #104 handled historical plan documents. If a hit appears in live code, stop and report it — this plan asserts there are none.

- [ ] **Step 7: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py backend/config/settings.py tests/services/bulk_uploads/test_master_bulk_upload.py tests/integration/test_master_results_sync_endpoint.py
git commit -m "$(cat <<'EOF'
[#114] Delete dead Master Results entry points

- sync_from_path, from_bytes and as_tuple removed; as_tuple was the only
  return shape that dropped warnings, and #74 removed path-based sync
- settings.master_results_path deleted with its sole reader
- 46 test call sites moved to a local _upload helper; 2 tests covering only
  the deleted surface removed
- Tests added: no (converted; net -2)
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Documentation and the issue record

Three documentation surfaces make statements this branch falsifies, and the repo convention is that every worked issue has a local doc in `docs/issues/` with its acceptance criteria ticked.

**Files:**
- Modify: `.claude/rules/MODELS.md` — `ScalarResults` → Hydrogen (the "GC source precedence (issue #111)" and "One row per vial (issue #111)" bullets)
- Modify: `docs/user_guide/BULK_UPLOADS.md` — §1 Master Results Sync
- Modify: `docs/CALCULATIONS.md` — Hydrogen Amount
- Create: `docs/issues/issue-114-master-results-residual-gaps.md`

**Interfaces:**
- Consumes: the behavior established by Tasks 1, 2 and 4, and the deletions from Task 5.
- Produces: nothing code depends on.

- [ ] **Step 1: Correct the MODELS.md hydrogen bullets**

`.claude/rules/MODELS.md` currently says of the discarded DI reading that it "is not currently surfaced in the UI — the frontend types `feedbacks` (`frontend/src/api/bulkUploads.ts`) but nothing renders it, so a researcher cannot see this from the app today." That is now half-true: the per-row record is still unrendered, but the fact is reported. Replace that sentence with:

```
    On a Master Results upload the parser picks Full Loop over direct
    injection and writes only the winner. The upload's `warnings` name the
    affected rows ("Full Loop reading used instead of direct injection on
    3 rows (2, 5, 9)"), which the bulk-upload panel already renders, so a
    researcher can see that a DI reading was discarded (issue #114 item 1).
    The per-row `h2_source` / `h2_di_superseded` records in the response's
    `feedbacks` are still not rendered anywhere. Neither the source nor the
    discarded value is persisted — making that a stored provenance field
    would be an additive `ScalarResults` column and a schema-checklist run.
```

Add one bullet under the same Hydrogen block for Task 4:

```
  - **Geometry requires a reading (issue #114):** a Master Results row with no
    `H2 (ppm)` in either GC block stores no `gas_sampling_volume_ml` or
    `gas_sampling_pressure_MPa` either. Those sheet columns carry the previous
    run's values (207 of 499 rows on the v3 Dashboard, 2026-07-30), and nothing
    was ever computed from them without a concentration — but persisted, they
    were indistinguishable from a real measurement.
```

**Do not** edit `docs/project_context/MODELS.md` — that file does not exist; `.claude/rules/MODELS.md` is not hook-synced and is the only copy.

- [ ] **Step 2: Update the user guide**

In `docs/user_guide/BULK_UPLOADS.md` §1 (Master Results Sync), replace the two paragraphs under **Hydrogen columns** — from "**Hydrogen columns.** `FL H2 (ppm)`…" through "…than being ignored." — with:

```markdown
**Hydrogen columns.** `FL H2 (ppm)` (Full Loop) is used whenever it has a value;
`DI H2 (ppm)` is used only when the Full Loop cell is blank. Gas volume and
pressure are taken from whichever block supplied the concentration, so do not
mix them by hand. A `0` is treated as a real reading of zero — leave the cell
**empty** if there was no measurement.

If a row has a reading in **both** blocks, Full Loop wins and the
direct-injection value is not stored anywhere. The upload names those rows under
**Warnings** so you can see it happened — the discarded reading cannot be
recovered from the database afterwards.

**Gas volume and pressure need a reading to go with them.** A row with no
`H2 (ppm)` in either block imports no gas volume or pressure either, even when
those cells are filled in. The GC sheets carry values forward from previous runs,
so geometry with no concentration beside it is stale rather than measured, and
nothing is computed from it in any case.

If you rename a Dashboard column, the upload now tells you: any unmatched column
whose name mentions H2 appears under **Warnings** in the result panel rather
than being ignored.

**Errors are listed in sheet order.** Row errors appear in the same order as the
rows in the spreadsheet, so you can work down the list against the file. A
problem with the file as a whole — a missing required column — comes first,
since it has no row number. (The deprecated wide `DI a/b/c H2 (ppm)` columns
are reported under **Warnings**, not Errors — the rest of the file still
uploads.)
```

Two of those paragraphs are unchanged (the first and the rename one) — they are repeated here so the replacement is a single contiguous block rather than three interleaved edits.

**Correction (post-review, 2026-07-30):** the last sentence originally listed the
deprecated wide `DI a/b/c H2 (ppm)` columns alongside missing required columns as
a file-level *error*. That message is `warnings.append(...)`, not an error — the
sentence has been corrected above to match what actually shipped in
`docs/user_guide/BULK_UPLOADS.md`.

- [ ] **Step 3: Update CALCULATIONS.md**

In `docs/CALCULATIONS.md`, replace the "Where the inputs come from on a Master Results upload (issue #111)" paragraph at lines 130-137 with:

```markdown
**Where the inputs come from on a Master Results upload (issue #111):** all
three inputs are read from a single GC block. Full Loop (`FL H2 (ppm)`,
`FL Gas Volume (mL)`, `FL Gas Pressure (psi)`) takes precedence; direct
injection (`DI H2 (ppm)`, `DI gas volume (mL)`, `DI gas pressure (psi)`) is
used only when the Full Loop concentration cell is blank. The blocks are never
mixed — pairing a Full Loop concentration with a DI sampling volume would
compute micromoles for an injection that never happened. A concentration of `0`
is a real measurement and is stored as such. Volume and pressure are read **only
when a concentration resolved** (issue #114): a row with no `H2 (ppm)` in either
block stores none of the three, because the sheet's gas columns carry the
previous run's values and were never computable without a concentration anyway.
```

Do not restate or alter the formula block or the bullet above it — `_calculate_hydrogen`'s guard (volume and pressure present and `> 0`, concentration present and non-negative, `0` valid) is documented correctly at line 128 and is unchanged by this branch.

- [ ] **Step 4: Write the issue doc**

Create `docs/issues/issue-114-master-results-residual-gaps.md`, following the shape of `docs/issues/issue-dead-add-result-modal.md`: a `> **Status YYYY-MM-DD — …**` blockquote, `**Type:** chore` / `**Area:** backend/services/bulk_uploads/` / `**Priority:**`, then Problem / Fix / Acceptance criteria / Notes.

It must record, explicitly:

1. Items 1, 3, 4 and both addendum consequences shipped; **item 2 deferred to #113** with the reason (both warnings need one shared false-positive design, and #113 is unstarted).
2. That addendum consequence 1 needed **no new test** — `test_di_wins_ignores_stray_full_loop_gas_geometry` already existed from #111's fix wave and was strengthened to the measured magnitudes instead. Do not claim a test was added where one was retuned.
3. That item 1 was decided as a warning, not a schema column, because 0 of 499 rows on the current sheet contest precedence — so the persisted-provenance option was measured as zero-impact, not merely deprioritised.
4. That `settings.master_results_path` was deleted alongside `sync_from_path`, and why that is safe on the lab PC (`extra="ignore"`).
5. Use `[~]`, not `[x]`, for any acceptance criterion that cannot pass as literally written — the repo precedent is `docs/issues/issue-bulk-upload-dry-run.md:255`. Ticking a criterion whose annotation says it cannot pass reads as a false pass claim.

- [ ] **Step 5: Verify the docs hook fired**

The `PostToolUse` hook copies `docs/` writes into `docs/project_context/`. Confirm, do not assume:

```powershell
git status --short docs/project_context/
```

Expected: modified copies of `BULK_UPLOADS.md` and `CALCULATIONS.md`, plus a new `issue-114-master-results-residual-gaps.md`. If they are missing, the hook did not run — report it rather than hand-copying, since a hand-written copy diverges silently.

- [ ] **Step 6: Commit**

```bash
git add .claude/rules/MODELS.md docs/user_guide/BULK_UPLOADS.md docs/CALCULATIONS.md docs/issues/issue-114-master-results-residual-gaps.md docs/project_context/
git commit -m "$(cat <<'EOF'
[#114] Document warning, geometry rule and error order

- MODELS.md hydrogen bullets, BULK_UPLOADS.md §1, CALCULATIONS.md
- Issue doc records item 2 deferred to #113 and C1 needing no new test
- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Verification before calling this done

- [ ] `.venv/Scripts/python -m pytest tests/services/bulk_uploads/ tests/integration/test_master_results_sync_endpoint.py tests/api/test_bulk_uploads.py -q` — paste the actual summary line. The pre-#114 count for `tests/services/bulk_uploads/` was 244 passed; expect 244 + 4 new − 2 deleted = 246 in that directory, and reconcile the number if it differs rather than accepting it. **Correction (post-review, 2026-07-30):** the measured baseline is 264 on `develop` and 266 on this branch, not 244/246 as originally estimated here.
- [ ] `git diff develop --stat -- database/models/ alembic/ database/event_listeners.py` returns empty — this branch changes no schema.
- [ ] `Select-String -Path frontend -Include *.ts,*.tsx -Pattern "feedbacks" -Recurse` shows no new consumer — item 1 was built with zero frontend change, and a stray edit there means the wrong option was implemented.
- [ ] No new warning fires on an ordinary sheet: `test_no_supersede_warning_when_precedence_is_uncontested` and `test_h2s_column_is_not_reported_as_a_dropped_h2_reading` both pass.
- [ ] Post a comment on GitHub issue #114 recording what shipped and that item 2 moved to #113, so the issue and the repo agree.
- [ ] `docs/working/issue-log.md` entry written as part of `/complete-task`, not here.
