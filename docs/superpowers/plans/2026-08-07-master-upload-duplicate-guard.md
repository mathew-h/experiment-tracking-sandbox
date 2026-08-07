# Master Results Upload — Duplicate Guard and Message Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the hole that lets two Master Results rows with case- or padding-variant experiment IDs silently overwrite each other, and cut the upload panel's error/warning noise by grouping duplicate reports and aggregating the ID-vs-Duration warning.

**Architecture:** All three changes live inside `_process_bytes` in one parser file. Phase 1 already resolves every row's `(experiment_id, timepoint)` before Phase 2 upserts anything; we re-key its duplicate tally on the canonical fuzzy-match key (`_id_match.normalize_id`) instead of the raw ID string, convert the per-row duplicate error into one error per collision group, and convert the per-row Duration-disagreement warning into one file-level coverage warning matching the shapes issues #114 and #115 already established in this file.

**Tech Stack:** Python 3.11, pandas, SQLAlchemy 2.x, pytest. No new dependencies.

## Global Constraints

- **`backend/services/bulk_uploads/master_bulk_upload.py` is a LOCKED component** (`docs/LOCKED_COMPONENTS.md` §Bulk Upload Python Parsers). It is unlocked for exactly the three changes in this plan by explicit user instruction (Mat, 2026-08-07). Do not refactor anything else in the file. Do not modify any other file under `backend/services/bulk_uploads/` — `_id_match.py` is **imported from, never edited**.
- Black line length 88; type hints on all signatures; no `Any` without a comment.
- `structlog` only — never `print()` or `logging.basicConfig()`.
- No new third-party packages.
- **Never run two pytest processes at once.** The test DB is shared; a concurrent or interrupted run leaves a stale schema that `create_all` cannot repair. Run tasks strictly sequentially.
- Run tests with the venv interpreter: `.venv/Scripts/python.exe -m pytest ...` from the project root.
- Never start, stop, or restart the uvicorn server.
- A full `pytest -q` has **3 pre-existing failures** in `tests/test_pg_backup_restore.py` (documented baseline, not a regression). Scope test runs to `tests/services/bulk_uploads/test_master_bulk_upload.py` unless verifying the whole suite.
- Commit format (inline task): `[fix] <imperative under 50 chars>` followed by a blank line, then `- Detail`, `- Tests added: yes/no`, `- Docs updated: yes/no`.
- Branch is already created and checked out: `fix/master-upload-duplicate-guard`.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `backend/services/bulk_uploads/master_bulk_upload.py` | Master Results Dashboard parser | Modify — Phase 1 duplicate key, duplicate error emission, `_resolve_row_identity` return shape, warning tail |
| `tests/services/bulk_uploads/test_master_bulk_upload.py` | Parser tests (1778 lines, 62 tests) | Modify — 3 existing duplicate tests change their error count; add 5 new tests |
| `docs/LOCKED_COMPONENTS.md` | Lock register | Modify — footnote recording the authorized behavior change |
| `.claude/rules/MODELS.md` | Schema + contract reference | Modify — duplicate-rejection contract under `ScalarResults` |
| `docs/working/issue-log.md` | Session log | Modify — final entry |

Everything the parser needs already exists: `normalize_id` in `backend/services/bulk_uploads/_id_match.py:57`, `normalize_timepoint` in `backend/services/result_merge_utils.py` (already imported).

---

### Task 1: Key the duplicate pre-pass on the normalized ID

Two rows whose IDs differ only by case or zero-padding (`SERUM_cation_001c-t5` vs `SERUM_Cation_001c-t5`) currently produce two different keys, both pass the duplicate guard, and both upsert onto the **one** experiment `_id_match.fuzzy_find_experiment` resolves them to — the second silently overwrites the first. Three such pairs are live in `Master_Results_Tracker_v3.xlsx` (rows 29/194, 32/195, 35/196).

**Accepted trade-off (Mat, 2026-08-07):** keying on the normalized ID means two *genuinely different* stored experiments whose IDs differ only by case/padding, each named by its own sheet row, would now both be rejected. Measured 2026-08-07: **0 of 1009** experiments in the dev DB share a normalized key, so this is unreachable on current data, and the failure mode is a loud stop rather than silent data loss.

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py:38` (imports), `:487-496` (the `key_counts` block), `:508` (the Phase-2 lookup)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Consumes: `normalize_id(raw: str) -> str` from `backend.services.bulk_uploads._id_match`
- Produces: nothing new for later tasks; Task 2 rewrites the block this task edits

- [ ] **Step 1: Write the failing test**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`, immediately after `test_duplicate_detected_after_timepoint_token_resolution` (which ends at line 1494):

```python
def test_case_variant_ids_at_one_timepoint_are_a_duplicate(db_session: Session):
    """Two spellings that resolve to ONE experiment are a duplicate, not two rows.

    The pre-pass used to key on the raw ID string while the DB lookup keys on
    _id_match.normalize_id, so 'SERUM_cation_001c-t5' and 'SERUM_Cation_001c-t5'
    produced two different keys, both passed the guard, and both upserted onto
    the single stored experiment — the second reading silently overwriting the
    first with no error and no warning. Three such pairs are live in
    Master_Results_Tracker_v3.xlsx (sheet rows 29/194, 32/195, 35/196).
    """
    _seed_experiment(db_session, "SERUM_DUP06c-t5", 8866)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_dup06c-t5", 5.0, description="first", fl_h2=10.0),
        _v3_row("SERUM_DUP06C-t5", 5.0, description="second", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert created == 0, "neither row may be written"
    assert updated == 0
    assert errors, "the collision must be reported"

    assert (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_DUP06c-t5")
        .count()
    ) == 0


def test_padding_variant_ids_at_one_timepoint_are_a_duplicate(db_session: Session):
    """Zero-padding differences collapse the same way case differences do.

    normalize_id strips leading zeros per digit run, so 'HPHT_007' and 'HPHT_7'
    are one experiment to the finder and must be one row to the guard.
    """
    _seed_experiment(db_session, "HPHT_DUP07", 8867)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_DUP07", 7.0, description="unpadded", fl_h2=10.0),
        _v3_row("HPHT_DUP0007", 7.0, description="padded", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert created == 0
    assert errors, "the collision must be reported"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest "tests/services/bulk_uploads/test_master_bulk_upload.py::test_case_variant_ids_at_one_timepoint_are_a_duplicate" "tests/services/bulk_uploads/test_master_bulk_upload.py::test_padding_variant_ids_at_one_timepoint_are_a_duplicate" -v
```

Expected: both FAIL. The case-variant test fails on `assert created == 0` with `created == 1` (the two rows resolve to one experiment, so the first creates and the second updates — `created == 1, updated == 1`). The padding test fails the same way. This failure IS the bug: two readings, one stored row, no error.

- [ ] **Step 3: Add the import**

In `backend/services/bulk_uploads/master_bulk_upload.py`, the existing import block at line 38 reads:

```python
from backend.services.bulk_uploads.replicate_routing import combine_replicate_id
```

Add directly above it (isort orders `_id_match` before `replicate_routing`):

```python
from backend.services.bulk_uploads._id_match import normalize_id
from backend.services.bulk_uploads.replicate_routing import combine_replicate_id
```

- [ ] **Step 4: Re-key the tally**

Replace the comment and block currently at lines 487-496:

```python
    # Keyed on the normalized (rounded) timepoint so 7.0 and 7.00005 — which
    # `find_timepoint_candidates` would merge into the same result row anyway
    # — collide here too. This narrows the gap but does not close it:
    # normalization only rounds to 4 decimals, so two values on opposite sides
    # of a rounding boundary (e.g. 7.00004 and 7.00006) still key differently
    # even though they fall within the ±1e-4 tolerance of each other.
    key_counts: Dict[Tuple[str, float], int] = {}
    for _, exp_id, time_post_reaction, _row in resolved:
        key = (exp_id, normalize_timepoint(time_post_reaction))
        key_counts[key] = key_counts.get(key, 0) + 1
```

with:

```python
    # Keyed on the normalized ID, not the raw string: `_id_match.normalize_id`
    # is what the DB lookup resolves through, so two spellings that differ only
    # by case or zero padding ('SERUM_cation_001c-t5' vs 'SERUM_Cation_001c-t5')
    # name ONE stored experiment. Keying on the raw string let both rows pass
    # this guard and both upsert onto that one experiment — the later row
    # silently overwriting the earlier, which is precisely what the guard
    # exists to prevent. Three such pairs were live in the team's v3 workbook
    # (2026-08-07). The converse risk — two genuinely different experiments
    # whose IDs differ only by case/padding, each with its own sheet row, now
    # being rejected as a false duplicate — was accepted (Mat, 2026-08-07):
    # 0 of 1009 dev-DB experiments share a normalized key, and a loud stop
    # beats the silent overwrite it replaces.
    #
    # Keyed on the normalized (rounded) timepoint so 7.0 and 7.00005 — which
    # `find_timepoint_candidates` would merge into the same result row anyway
    # — collide here too. This narrows the gap but does not close it:
    # normalization only rounds to 4 decimals, so two values on opposite sides
    # of a rounding boundary (e.g. 7.00004 and 7.00006) still key differently
    # even though they fall within the ±1e-4 tolerance of each other.
    key_counts: Dict[Tuple[str, float], int] = {}
    for _, exp_id, time_post_reaction, _row in resolved:
        key = (normalize_id(exp_id), normalize_timepoint(time_post_reaction))
        key_counts[key] = key_counts.get(key, 0) + 1
```

- [ ] **Step 5: Update the Phase-2 lookup to use the same key**

Line 508 currently reads:

```python
        if key_counts[(exp_id, normalize_timepoint(time_post_reaction))] > 1:
```

Replace with:

```python
        if key_counts[(normalize_id(exp_id), normalize_timepoint(time_post_reaction))] > 1:
```

That line is 92 characters — over the 88 limit. Wrap it:

```python
        dup_key = (normalize_id(exp_id), normalize_timepoint(time_post_reaction))
        if key_counts[dup_key] > 1:
```

- [ ] **Step 6: Run the new tests to verify they pass**

```bash
.venv/Scripts/python.exe -m pytest "tests/services/bulk_uploads/test_master_bulk_upload.py::test_case_variant_ids_at_one_timepoint_are_a_duplicate" "tests/services/bulk_uploads/test_master_bulk_upload.py::test_padding_variant_ids_at_one_timepoint_are_a_duplicate" -v
```

Expected: 2 passed.

- [ ] **Step 7: Run the whole parser suite for regressions**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q
```

Expected: all pass (64 tests). If `test_from_bytes_matches_experiment_with_leading_zeros`, `..._with_dot_separator` or `..._with_leading_zeros_and_symbols` fail, STOP and report — those are single-row files that must not be affected by a duplicate key change, and a failure there means the key is being applied somewhere it shouldn't be.

- [ ] **Step 8: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "$(cat <<'EOF'
[fix] Key upload duplicate guard on normalized ID

- Case/padding-variant IDs resolve to one experiment and now collide
- Closes a silent overwrite: both rows passed, the later one won
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 2: Report one error per duplicate group, naming every row

Today each duplicate row gets its own error and none of them says which other row it collides with. Your workbook produces 52 near-identical lines for 26 collisions. This mirrors the fix already shipped for ambiguous IDs in commit `de379a1` ("Name both candidates on an ambiguous upload row").

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` — the `key_counts` block from Task 1 and the Phase-2 guard at the top of the upsert loop
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Consumes: `normalize_id` (imported in Task 1); `row_errors: List[Tuple[int, str]]`, already declared at line 396 and sorted by row number at line 675
- Produces: duplicate errors formatted `Rows {n}, {m} ({id}[, {id2}]): duplicate experiment ID and timepoint (day {d:g}). …`, anchored in `row_errors` at the group's FIRST row number so the existing sort places them correctly. Single-row errors keep their `Row {n} ({id}): …` prefix — `test_errors_are_listed_in_sheet_row_order` asserts on it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`, after the two tests added in Task 1:

```python
def test_duplicate_group_is_one_error_naming_every_row(db_session: Session):
    """One collision produces one error listing all its rows, not one per row.

    A researcher reads this list against the sheet: 'row 2 is a duplicate' with
    no sibling row number means opening the file and searching for the partner
    by hand. The team's v3 workbook had 26 collisions reported as 52 lines.
    Same shape as the ambiguous-ID fix in commit de379a1.
    """
    _seed_experiment(db_session, "SERUM_DUP08a", 8868)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP08a", 7.0, description="first", fl_h2=10.0),
        _v3_row("SERUM_DUP08a", 7.0, description="second", fl_h2=20.0),
        _v3_row("SERUM_DUP08a", 7.0, description="third", fl_h2=30.0),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert created == 0
    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "Rows 2, 3, 4" in errors[0], f"every row must be named: {errors[0]}"
    assert "SERUM_DUP08a" in errors[0]
    assert "day 7" in errors[0]


def test_duplicate_group_names_both_spellings(db_session: Session):
    """When the colliding rows are spelled differently, the message says so.

    'Rows 29, 194 (SERUM_pH_001a-t1)' would look like a plain repeat; the
    researcher needs to see that the two cells do not read the same, or they
    will search the sheet for a string that is only in one of them.
    """
    _seed_experiment(db_session, "SERUM_DUP09c-t5", 8869)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_dup09c-t5", 5.0, description="first", fl_h2=10.0),
        _v3_row("SERUM_DUP09C-t5", 5.0, description="second", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "SERUM_dup09c-t5" in errors[0], f"first spelling missing: {errors[0]}"
    assert "SERUM_DUP09C-t5" in errors[0], f"second spelling missing: {errors[0]}"
    assert "resolve to one experiment" in errors[0], (
        f"the message must explain why differing spellings collided: {errors[0]}"
    )


def test_duplicate_group_error_sorts_at_its_first_row(db_session: Session):
    """The group error sits where its earliest row sits in the sheet order.

    Errors are sorted by row number so the list reads top-down against the
    spreadsheet (issue #114 item 3). A group spanning rows 2 and 4 must appear
    above a single-row failure on row 3, not after it.
    """
    _seed_experiment(db_session, "SERUM_DUP10a", 8870)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP10a", 7.0, description="dup one", fl_h2=10.0),
        _v3_row("HPHT_DUP10_MISSING", 7.0, description="no such experiment"),
        _v3_row("SERUM_DUP10a", 7.0, description="dup two", fl_h2=20.0),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert len(result.errors) == 2, f"one group + one row error: {result.errors}"
    assert result.errors[0].startswith("Rows 2, 4 ("), (
        f"the group anchored at row 2 must come first: {result.errors}"
    )
    assert result.errors[1].startswith("Row 3 ("), (
        f"the row 3 failure must come second: {result.errors}"
    )
```

- [ ] **Step 2: Run them to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q -k "duplicate_group"
```

Expected: 3 failed — `len(errors) == 1` gets 3, 2, and 3 respectively (one error per row today).

- [ ] **Step 3: Replace the tally with a group map and emit the group errors**

In `backend/services/bulk_uploads/master_bulk_upload.py`, replace the whole `key_counts` block Task 1 produced (the comment plus the three-line loop) with:

```python
    # Keyed on the normalized ID, not the raw string: `_id_match.normalize_id`
    # is what the DB lookup resolves through, so two spellings that differ only
    # by case or zero padding ('SERUM_cation_001c-t5' vs 'SERUM_Cation_001c-t5')
    # name ONE stored experiment. Keying on the raw string let both rows pass
    # this guard and both upsert onto that one experiment — the later row
    # silently overwriting the earlier, which is precisely what the guard
    # exists to prevent. Three such pairs were live in the team's v3 workbook
    # (2026-08-07). The converse risk — two genuinely different experiments
    # whose IDs differ only by case/padding, each with its own sheet row, now
    # being rejected as a false duplicate — was accepted (Mat, 2026-08-07):
    # 0 of 1009 dev-DB experiments share a normalized key, and a loud stop
    # beats the silent overwrite it replaces.
    #
    # Keyed on the normalized (rounded) timepoint so 7.0 and 7.00005 — which
    # `find_timepoint_candidates` would merge into the same result row anyway
    # — collide here too. This narrows the gap but does not close it:
    # normalization only rounds to 4 decimals, so two values on opposite sides
    # of a rounding boundary (e.g. 7.00004 and 7.00006) still key differently
    # even though they fall within the ±1e-4 tolerance of each other.
    dup_groups: Dict[Tuple[str, float], List[Tuple[int, str]]] = {}
    for row_num, exp_id, time_post_reaction, _row in resolved:
        key = (normalize_id(exp_id), normalize_timepoint(time_post_reaction))
        dup_groups.setdefault(key, []).append((row_num, exp_id))

    # One error per collision, not per row. Each names every row in the group,
    # so a researcher reading this list against the sheet is told where the
    # partner reading is instead of having to search for it — the same reason
    # an ambiguous ID names both candidates. Anchored at the group's first row
    # so the sort at the end of this function keeps the list in sheet order.
    duplicate_rows: set[int] = set()
    for (_norm_id, day), members in dup_groups.items():
        if len(members) < 2:
            continue
        duplicate_rows.update(row_num for row_num, _ in members)
        rows_text = ", ".join(str(row_num) for row_num, _ in members)
        # dict.fromkeys keeps sheet order while dropping repeats.
        spellings = list(dict.fromkeys(exp_id for _, exp_id in members))
        # Differing spellings collided on the normalized key, which is not
        # visible from the cells themselves — say so, or the researcher
        # searches the sheet for a string only one of the rows contains.
        variant_clause = (
            " These spellings differ but resolve to one experiment, so one "
            "reading would have silently overwritten the other."
            if len(spellings) > 1 else ""
        )
        row_errors.append((members[0][0], (
            f"Rows {rows_text} ({', '.join(spellings)}): duplicate experiment "
            f"ID and timepoint (day {day:g}).{variant_clause} Each vial gets "
            f"one row per timepoint — give each vial its own ID (e.g. "
            f"SERUM_001a-t7, SERUM_001b-t7). No row for this vial-day was "
            f"written."
        )))
```

- [ ] **Step 4: Replace the Phase-2 guard**

The Phase-2 loop currently opens with the Task 1 version of the guard, which appends a per-row error. Replace:

```python
        dup_key = (normalize_id(exp_id), normalize_timepoint(time_post_reaction))
        if key_counts[dup_key] > 1:
            row_errors.append((row_num, (
                f"Row {row_num} ({exp_id}): duplicate experiment ID and timepoint "
                f"(day {time_post_reaction:g}). Each vial gets one row per timepoint "
                f"— give each vial its own ID (e.g. SERUM_001a-t7, SERUM_001b-t7). "
                f"No row for this vial-day was written."
            )))
            continue
```

with:

```python
        # The error was already emitted once for the whole group above.
        if row_num in duplicate_rows:
            continue
```

- [ ] **Step 5: Fix the three existing duplicate tests**

These assert one error per row and must now assert one per group. Make exactly these edits — do not weaken any other assertion.

In `test_duplicate_vial_and_timepoint_is_an_error` (around line 1391), replace:

```python
    assert len(errors) == 2, f"both rows must be reported, got: {errors}"
    assert all("SERUM_DUP01a" in e for e in errors)
    assert any("row 2" in e.lower() for e in errors)
    assert any("row 3" in e.lower() for e in errors)
```

with:

```python
    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "SERUM_DUP01a" in errors[0]
    assert "Rows 2, 3" in errors[0], f"both rows must be named: {errors[0]}"
```

In `test_duplicate_detected_after_timepoint_token_resolution` (around line 1493), replace:

```python
    assert len(errors) == 2
```

with:

```python
    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "Rows 2, 3" in errors[0]
```

In `test_duplicate_does_not_block_other_rows` (around line 1511), replace:

```python
    assert len(errors) == 2
```

with:

```python
    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "Rows 2, 3" in errors[0]
```

- [ ] **Step 6: Run the new tests, then the whole parser suite**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q -k "duplicate_group"
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q
```

Expected: 3 passed, then all 67 pass. If `test_errors_are_listed_in_sheet_row_order` fails, the single-row `Row N (id):` prefix was changed — revert that; only duplicate groups use the `Rows` plural form.

- [ ] **Step 7: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "$(cat <<'EOF'
[fix] Report one error per duplicate group

- Names every colliding row and every distinct spelling
- Anchored at the group's first row so sheet order is kept
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 3: Aggregate the ID-vs-Duration warnings into one file-level line

The Dashboard's `Duration (Days)` column is a formula derived from sampling dates and has drifted from the `-t<days>` tokens: 109 of 202 resolvable rows in the team's v3 workbook disagree. Each emits its own warning, so the upload panel shows 5 of 109 near-identical lines behind a "show all" toggle. The file already has the right shape for this — `superseded_rows` (#114 item 1) and `missing_gc_date_rows` (#115) both report coverage with a row list only at ≤10.

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` — new `TimepointCheck` dataclass, `_resolve_row_identity` signature/docstring/returns, the Phase-1 warning append, the row-warning ordering comment at `:386-395`, and the warning tail after the GC-date block
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Produces: `TimepointCheck(compared: bool, disagrees: bool)` — a frozen dataclass returned as the 5th element of `_resolve_row_identity`, replacing the `Optional[str]` warning. `compared=False` means no comparison was possible (no `-t` token, or a blank Duration). No other module calls `_resolve_row_identity`; it is module-private.

- [ ] **Step 1: Confirm nothing else consumes the per-row warning string**

```bash
grep -rn "disagrees with the ID" --include=*.py --include=*.tsx --include=*.ts .
```

Expected: hits only in `backend/services/bulk_uploads/master_bulk_upload.py` and `tests/services/bulk_uploads/test_master_bulk_upload.py`. If anything else matches, STOP and report before changing the format.

- [ ] **Step 2: Write the failing tests**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`, at the end of the file:

```python
# ---------------------------------------------------------------------------
# Aggregated Duration-vs-ID disagreement warning
# ---------------------------------------------------------------------------

def test_duration_disagreements_are_one_aggregated_warning(db_session: Session):
    """Many disagreeing rows produce ONE warning, not one per row.

    The Dashboard's Duration column is a formula off the Sampling sheet and has
    drifted from the '-t<days>' tokens wholesale: 109 of 202 resolvable rows in
    the team's v3 workbook disagreed (2026-08-07). One line per row buries the
    other warnings, so this follows the coverage form the DI-supersede (#114)
    and GC-run-date (#115) warnings already use.
    """
    rows = []
    for i in range(3):
        exp_id = f"SERUM_DIS{i:02d}a-t7"
        _seed_experiment(db_session, exp_id, 8940 + i)
        rows.append(_v3_row(exp_id, 3.0, nh4=1.0))

    xlsx = _master_excel_v3(rows)
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"a disagreement must not reject a row: {result.errors}"
    assert result.created == 3

    disagreements = [w for w in result.warnings if "-t token" in w]
    assert len(disagreements) == 1, (
        f"exactly one file-level warning, not one per row: {result.warnings}"
    )
    assert "3 of 3" in disagreements[0], (
        f"the denominator must count comparable rows: {disagreements[0]}"
    )
    assert "(2, 3, 4)" in disagreements[0], (
        f"at or below the 10-row threshold the rows must be named: {disagreements[0]}"
    )


def test_duration_disagreement_denominator_counts_comparable_rows_only(
    db_session: Session,
):
    """The denominator is rows where a comparison was possible, not all rows.

    A row with no '-t' token, or with a blank Duration cell, has nothing to
    disagree with and must not inflate the denominator — the same reasoning
    that makes the GC-date warning count only H2-bearing rows.
    """
    _seed_experiment(db_session, "SERUM_DIS10a-t7", 8950)   # token + duration: comparable
    _seed_experiment(db_session, "SERUM_DIS11a-t7", 8951)   # token + duration: comparable
    _seed_experiment(db_session, "SERUM_DIS12", 8952)       # no token: not comparable
    _seed_experiment(db_session, "SERUM_DIS13a-t7", 8953)   # blank duration: not comparable

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DIS10a-t7", 3.0, nh4=1.0),    # disagrees
        _v3_row("SERUM_DIS11a-t7", 7.0, nh4=2.0),    # agrees
        _v3_row("SERUM_DIS12", 5.0, nh4=3.0),        # no token
        _v3_row("SERUM_DIS13a-t7", None, nh4=4.0),   # blank duration, ID supplies day 7
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 4

    disagreements = [w for w in result.warnings if "-t token" in w]
    assert len(disagreements) == 1, f"got: {result.warnings}"
    assert "1 of 2" in disagreements[0], (
        f"only the two token+duration rows are comparable: {disagreements[0]}"
    )
    assert "(2)" in disagreements[0], f"only row 2 disagreed: {disagreements[0]}"


def test_no_disagreement_warning_when_every_row_agrees(db_session: Session):
    """A sheet whose Durations match its tokens says nothing.

    A warning that fires on ordinary sheets is one researchers learn to ignore
    — the same rule the DI-supersede warning follows.
    """
    _seed_experiment(db_session, "SERUM_DIS20a-t7", 8960)

    xlsx = _master_excel_v3([_v3_row("SERUM_DIS20a-t7", 7.0, nh4=1.0)])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    assert result.created == 1
    assert [w for w in result.warnings if "-t token" in w] == []


def test_disagreement_warning_drops_the_row_list_above_ten(db_session: Session):
    """Above 10 disagreeing rows the warning reports a ratio and no row list.

    Matches the <=10 threshold the supersede and GC-date warnings use. The real
    workbook disagrees on 109 rows; enumerating them is exactly the noise this
    change removes.
    """
    rows = []
    for i in range(11):
        exp_id = f"SERUM_DIS3{i:02d}a-t7"
        _seed_experiment(db_session, exp_id, 8970 + i)
        rows.append(_v3_row(exp_id, 3.0, nh4=1.0))

    xlsx = _master_excel_v3(rows)
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    disagreements = [w for w in result.warnings if "-t token" in w]
    assert len(disagreements) == 1, f"got: {result.warnings}"
    assert "11 of 11" in disagreements[0]
    assert "(" not in disagreements[0].split("rows")[1][:5], (
        f"no row list above the threshold: {disagreements[0]}"
    )
```

- [ ] **Step 3: Run them to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q -k "disagreement or disagreements"
```

Expected: 3 failed, 1 passed. The three aggregation tests fail because today each disagreeing row emits its own warning (`len(disagreements) == 3`, `11`, etc.); `test_no_disagreement_warning_when_every_row_agrees` already passes and is a regression guard.

- [ ] **Step 4: Add the `TimepointCheck` dataclass**

In `backend/services/bulk_uploads/master_bulk_upload.py`, insert immediately above the `MasterUploadResult` dataclass (currently at line 96):

```python
@dataclass(frozen=True)
class TimepointCheck:
    """Outcome of comparing a row's Duration cell against its ID's -t token.

    `compared` is False when no comparison was possible — the ID carries no
    '-t<days>' token, or the Duration cell is blank (in which case the token
    simply supplies the day). It is the denominator of the file-level
    disagreement warning, which must count rows that could disagree rather
    than every row in the sheet.
    """

    compared: bool
    disagrees: bool


_NO_TIMEPOINT_CHECK = TimepointCheck(compared=False, disagrees=False)
```

- [ ] **Step 5: Change `_resolve_row_identity` to return the check**

Replace the signature and docstring return block (lines 285-299). The current annotation is a 4-tuple while the function returns 5 values — fix that too:

```python
def _resolve_row_identity(
    row: Any, row_num: int
) -> Tuple[Optional[str], Optional[float], Optional[str], bool, TimepointCheck]:
    """Resolve one Dashboard row to its (experiment_id, timepoint).

    Extracted from the upsert loop so the duplicate pre-pass and the loop share
    one implementation (issue #111).

    Returns (experiment_id, time_post_reaction, error_message, skip, check):
      * skip=True      — intentionally passed over; count toward `skipped`
      * error_message  — per-row error; count toward `errors`
      * check          — whether this row's Duration could be compared against
                         a '-t<days>' token and whether it disagreed. The row
                         still uploads either way; the caller aggregates these
                         into one file-level warning.
      * error None / skip False — a good row
    """
```

Then replace every `return` in the function body so the 5th element is a `TimepointCheck`:

- The four early returns that currently end in `, None` — the two blank/empty-ID skips, the `"standard"` skip, and the `combine_replicate_id` `ValueError` return — become `, _NO_TIMEPOINT_CHECK`.
- The blank-Duration branch (currently lines 342-345):

```python
    duration_raw = row.get("Duration (Days)")
    if _is_blank_duration(duration_raw):
        if id_timepoint is None:
            return exp_id, None, None, True, _NO_TIMEPOINT_CHECK
        return exp_id, id_timepoint, None, False, _NO_TIMEPOINT_CHECK
```

- The invalid-Duration return:

```python
    time_post_reaction = _parse_float(duration_raw)
    if time_post_reaction is None:
        return (
            exp_id, None,
            f"Row {row_num}: invalid Duration (Days) '{duration_raw}'",
            False, _NO_TIMEPOINT_CHECK,
        )
```

- The comparison block at the end (currently lines 358-368) becomes:

```python
    check = _NO_TIMEPOINT_CHECK
    if id_timepoint is not None:
        check = TimepointCheck(
            compared=True,
            disagrees=abs(time_post_reaction - id_timepoint) > TIMEPOINT_TOLERANCE_DAYS,
        )
        time_post_reaction = id_timepoint

    return exp_id, time_post_reaction, None, False, check
```

Keep the existing explanatory comment above that block (the one beginning "The '-t<days>' token defines the vial's elapsed days") unchanged — it still describes why the ID wins.

- [ ] **Step 6: Collect the checks in Phase 1 instead of appending warnings**

Replace the Phase-1 loop (lines 474-485):

```python
    resolved: List[Tuple[int, str, float, Any]] = []
    # Denominators for the file-level disagreement warning below. Counted here
    # rather than warned per row: the Duration column is a formula off the
    # Sampling sheet and drifts wholesale, so 109 of 202 rows disagreed on the
    # team's v3 workbook (2026-08-07) — one line each buried every other
    # warning in the upload panel.
    comparable_rows = 0
    disagreement_rows: List[int] = []
    for idx, row in df.iterrows():
        row_num = idx + 2
        exp_id, time_post_reaction, error, skip, check = _resolve_row_identity(row, row_num)
        if check.compared:
            comparable_rows += 1
            if check.disagrees:
                disagreement_rows.append(row_num)
        if skip:
            skipped += 1
            continue
        if error is not None:
            row_errors.append((row_num, error))
            continue
        resolved.append((row_num, exp_id, time_post_reaction, row))
```

- [ ] **Step 7: Emit the aggregated warning**

Insert after the `missing_gc_date_rows` warning block (which ends at line 672, just before the `# Stable sort` comment):

```python
    # One line, not 109. The Dashboard's Duration column is a formula derived
    # from sampling dates and has drifted from the '-t<days>' tokens wholesale
    # -- 109 of 202 comparable rows disagreed on the team's v3 workbook
    # (2026-08-07). The ID wins either way (Mat, 2026-07-30) so no row is
    # rejected, which is exactly why this must stay visible without drowning
    # the other warnings. Row list only at <=10, matching the supersede and
    # GC-date warnings above.
    if disagreement_rows:
        n = len(disagreement_rows)
        label = "row" if comparable_rows == 1 else "rows"
        where = (
            " (" + ", ".join(str(r) for r in disagreement_rows) + ")"
            if n <= 10 else ""
        )
        warnings.append(
            f"Duration (Days) disagrees with the ID's -t token on {n} of "
            f"{comparable_rows} {label}{where}. The ID is canonical, so each "
            "reading was recorded at the day its ID encodes and the Duration "
            "value was not used. That column is a formula derived from sampling "
            "dates -- a disagreement on many rows means the formula no longer "
            "tracks the vials' intended days."
        )
```

- [ ] **Step 8: Correct the now-stale ordering comment**

The comment at lines 386-395 ends with a paragraph about row-level warnings having no ordering guarantee. After this task there are no row-level warnings at all. Replace its final sentence — from "Row-level warnings have no equivalent ordering guarantee" through "would need this same treatment." — with:

```python
    # Every warning is now file-level: the per-row Duration-vs-token warning was
    # aggregated into a single coverage line at the end of this function, so the
    # ordering hazard that applied to row-level warnings no longer exists. A
    # future per-row warning would need the same row-number sorting the errors
    # get below.
```

- [ ] **Step 9: Run the new tests, then the whole parser suite**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q -k "disagreement or disagreements"
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q
```

Expected: 4 passed, then all 71 pass. `test_master_conflicting_duration_warns_and_the_id_wins` asserts `len(result.warnings) == 1` and the substring `"disagrees with the ID's -t token"` — both still hold, since its single row produces `"… on 1 of 1 row (2)."`. If it fails on the substring, the message wording drifted from the spec above; restore it.

- [ ] **Step 10: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "$(cat <<'EOF'
[fix] Aggregate Duration-vs-token warnings

- One coverage line replaces one warning per disagreeing row
- Denominator counts rows where a comparison was possible
- Tests added: yes
- Docs updated: no
EOF
)"
```

---

### Task 4: Record the contract and verify against the real workbook

**Files:**
- Modify: `docs/LOCKED_COMPONENTS.md`, `.claude/rules/MODELS.md`, `docs/working/issue-log.md`

**Interfaces:**
- Consumes: the finished behavior from Tasks 1-3. Nothing produces onward.

- [ ] **Step 1: Verify against the real workbook (read-only, no commit)**

The team's workbook lives outside the repo and is OneDrive-synced. **Read it, never write it.** Write this to the scratchpad directory (not the repo) and run it:

```python
"""READ-ONLY verification against the real v3 Dashboard."""
import sys, collections
sys.path.insert(0, r"C:\Users\MathewHearl\OneDrive - Addis Energy\Documents\01_Software\database_sandbox\experiment_tracking_sandbox")
import pandas as pd
from backend.services.bulk_uploads.master_bulk_upload import (
    _normalize_headers, _resolve_row_identity,
)
from backend.services.bulk_uploads._id_match import normalize_id
from backend.services.result_merge_utils import normalize_timepoint

PATH = r"C:\Users\MathewHearl\Addis Energy\All Company - Addis Energy\01_R&D\02_Results\Master_Results_Tracker_v3.xlsx"
df = pd.ExcelFile(PATH).parse("Dashboard")
df.columns = _normalize_headers(df.columns)

resolved, comparable, disagreed = [], 0, 0
for idx, row in df.iterrows():
    exp_id, tpr, err, skip, check = _resolve_row_identity(row, idx + 2)
    if check.compared:
        comparable += 1
        disagreed += bool(check.disagrees)
    if skip or err:
        continue
    resolved.append((idx + 2, exp_id, tpr))

groups = collections.defaultdict(list)
for rn, e, t in resolved:
    groups[(normalize_id(e), normalize_timepoint(t))].append(rn)
dupe_groups = {k: v for k, v in groups.items() if len(v) > 1}
print("duplicate GROUPS (was 52 row-errors):", len(dupe_groups))
print("rows rejected:", sum(len(v) for v in dupe_groups.values()))
print(f"disagreement warning: 1 line, '{disagreed} of {comparable} rows'")
```

Expected: **29 duplicate groups** covering 58 rows — 26 groups from the raw-string key plus the 3 case-variant pairs (rows 29/194, 32/195, 35/196) the old key missed — and one warning line reading `109 of 202 rows`. If the group count is 26, Task 1 did not take effect; if it is not 29, report the actual number rather than adjusting the plan to match.

- [ ] **Step 2: Add the footnote to `docs/LOCKED_COMPONENTS.md`**

The `master_bulk_upload.py` row of the parser table (line 66) reads:

```markdown
| `master_bulk_upload.py` | Dispatcher routing uploads to the correct parser |
```

Change it to carry a footnote marker and correct the stale description — this file parses the Dashboard sheet, it does not dispatch:

```markdown
| `master_bulk_upload.py` | Master Results Dashboard sheet parser |²
```

Then append below the existing `¹` footnote:

```markdown
² **Duplicate-guard contract (changed 2026-08-07 with explicit sign-off).** The Phase-1
duplicate pre-pass keys on `_id_match.normalize_id(experiment_id)` plus the normalized
timepoint — **not** the raw ID string. Keying on the raw string let two spellings that
differ only by case or zero padding both pass the guard and both upsert onto the one
experiment the DB lookup resolves them to, so the later row silently overwrote the
earlier; three such pairs were live in the team's v3 workbook. The accepted converse is
that two genuinely different experiments whose IDs differ only by case/padding would now
both be rejected (0 of 1009 dev-DB experiments share a normalized key, measured
2026-08-07). One error is emitted per collision group, naming every row and every
distinct spelling, anchored at the group's first row so the sheet-order sort holds.
The per-row Duration-vs-`-t`-token warning was aggregated into one file-level coverage
line. Preserve all four properties when touching this file.
```

- [ ] **Step 3: Update the contract note in `.claude/rules/MODELS.md`**

Under `### ScalarResults`, the bullet beginning **"One row per vial (issue #111):"** ends with "The upload rejects two rows sharing an ID and timepoint." Replace that sentence with:

```markdown
    The upload rejects two rows sharing an ID and timepoint, matched on the
    `_id_match.normalize_id` key rather than the raw string — so
    `SERUM_cation_001c-t5` and `SERUM_Cation_001c-t5` are one vial-day and are
    both rejected, where before 2026-08-07 both passed and the later row
    silently overwrote the earlier. The rejection is reported once per
    collision group, naming every sheet row and every distinct spelling.
```

- [ ] **Step 4: Append the session entry to `docs/working/issue-log.md`**

Follow the existing entry format (`**Shipped:**`, `**Tests added:**`, `**Verification:**`, `**Scope notes:**`). Record: the three changes; the measured before/after against the real workbook from Step 1; that `master_bulk_upload.py` is locked and was changed under explicit sign-off from Mat on 2026-08-07; and under scope notes, the two findings from the same investigation that were deliberately **not** fixed —

1. `database/experiment_id_parser.py::split_timepoint_token` accepts only `-t<days>`, while `normalize_id` treats `_t1` and `-t1` as the same key. So `SERUM_Catalyst_005a_t1` resolves to the right stored experiment but then hard-errors on the timepoint conflict, where the hyphen spelling would have uploaded with a warning. Needs its own `/start-task`: it changes the canonical ID grammar used by lineage repo-wide.
2. Missing `-t` vials are not auto-created (`auto_create_treatment_experiment` handles only `_`-delimited treatment variants with an existing parent). Deliberately left alone — auto-creating them would have fabricated `SERUM_Catayst_002-t3`, a typo, as a real experiment.

- [ ] **Step 5: Confirm the docs hook synced `docs/` files to `project_context/`**

```bash
git status --short docs/project_context/
```

Expected: `docs/project_context/LOCKED_COMPONENTS.md` shows as modified (the `PostToolUse` hook copies it automatically). `.claude/rules/MODELS.md` and `docs/working/issue-log.md` are outside the synced set and will not appear. If `LOCKED_COMPONENTS.md` did not sync, do **not** hand-copy it — report that the hook did not fire.

- [ ] **Step 6: Run the full backend suite**

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: 3 failed, ~1345 passed. The 3 failures must be exactly the documented `tests/test_pg_backup_restore.py` baseline. Any other failure blocks the commit — report it.

- [ ] **Step 7: Commit**

```bash
git add docs/LOCKED_COMPONENTS.md docs/project_context/LOCKED_COMPONENTS.md .claude/rules/MODELS.md docs/working/issue-log.md
git commit -m "$(cat <<'EOF'
[fix] Record the upload duplicate-guard contract

- Locked-file footnote, MODELS.md contract, session log
- Tests added: no
- Docs updated: yes
EOF
)"
```

---

## Self-Review

**Spec coverage.** Item 1 (normalized key) → Task 1. Item 2 (grouped duplicate messages naming the colliding rows) → Task 2. Item 3 (aggregated Duration warning) → Task 3. The locked-component sign-off and the two deliberately-unfixed findings → Task 4. No requirement is unassigned.

**Placeholder scan.** Every code step carries the literal code to write. Every test step carries the full test body. Every run step carries the exact command and its expected output. No "TBD", no "similar to Task N", no "add error handling".

**Type consistency.** `normalize_id(raw: str) -> str` is used identically in Tasks 1, 2 and the Task 4 verification script. `TimepointCheck(compared, disagrees)` is defined in Task 3 Step 4 and consumed in Steps 5 and 6 under those exact field names. `dup_groups` maps `Tuple[str, float] -> List[Tuple[int, str]]` in Task 2 and is read as `(row_num, exp_id)` pairs in the same task. `row_errors: List[Tuple[int, str]]` matches the existing declaration at line 396 and the existing sort at line 675.

**Known interaction.** Task 2 rewrites the block Task 1 creates. That is deliberate: Task 1 changes *which rows are caught* and Task 2 changes *how they are reported*, and a reviewer can reject either independently. Do not merge them to save an edit.
