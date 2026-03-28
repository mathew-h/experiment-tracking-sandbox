# XRD Stale Phases + Overwrite UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix stale XRDPhase rows on re-upload when overwrite=True, and add a visible overwrite toggle with contextual messaging to the XRD Mineralogy upload card.

**Architecture:** Add `overwrite: bool = False` through all three XRD parsers (experiment-timepoint, Aeris, ActLabs). When True, delete all XRDPhase rows for the batch key (experiment+timepoint or sample) before inserting the new set — keeping the delete inside the existing transaction. Wire the flag through the router Form field, then surface it in the frontend via a checkbox that closes over the state in the `uploadFn` lambda.

**Tech Stack:** Python 3.12, FastAPI Form fields, SQLAlchemy 2.x `.delete()`, React 18, TypeScript strict, TanStack Query v5, Tailwind CSS v3.

**Branch:** `fix/issue-18-xrd-stale-phases`

**Issue:** https://github.com/mathew-h/experiment-tracking-sandbox/issues/18

---

## File Map

| File | Change |
|------|--------|
| `backend/services/bulk_uploads/xrd_upload.py` | Add `overwrite` param to `_parse_experiment_timepoint` and `XRDAutoDetectService.upload`; delete-before-insert when True |
| `backend/services/bulk_uploads/aeris_xrd.py` | Add `overwrite` param to `AerisXRDUploadService.bulk_upsert_from_excel`; delete-before-insert when True |
| `backend/services/bulk_uploads/actlabs_xrd_report.py` | Add `overwrite` param to `XRDUploadService.bulk_upsert_from_excel`; delete-before-insert for sample-based XRDPhase rows when True |
| `backend/api/routers/bulk_uploads.py` | Add `overwrite: bool = Form(False)` to `upload_xrd_mineralogy`; pass to service |
| `tests/services/bulk_uploads/test_xrd_upload.py` | Add stale-phase tests (overwrite=True removes absent phases; overwrite=False leaves them) |
| `frontend/src/api/bulkUploads.ts` | Update `uploadXrdMineralogy(file, overwrite)` to append form field |
| `frontend/src/pages/BulkUploads.tsx` | Add `xrdOverwrite` state + `XrdOverwriteToggle` component; wire to `uploadFn`; dynamic help text |
| `frontend/src/pages/BulkUploadRow.tsx` | Add optional `skippedMessage?: string` prop; render in result area when `result.skipped > 0` |

---

## Task 1: Failing test — experiment-timepoint stale phases

**Files:**
- Test: `tests/services/bulk_uploads/test_xrd_upload.py`

- [ ] **Step 1: Write the two failing stale-phase tests**

Append to `tests/services/bulk_uploads/test_xrd_upload.py`:

```python
def test_stale_phases_deleted_when_overwrite_true(db_session: Session):
    """Upload A (2 phases), then upload B (1 phase, same key, overwrite=True).
    Only B's phase survives — A's absent phase is deleted."""
    exp = _seed_experiment(db_session, "HPHT_STALE001", 9901)

    # Upload A — Quartz + Calcite
    xlsx_a = make_excel(
        ["Experiment ID", "Time (days)", "Quartz", "Calcite"],
        [["HPHT_STALE001", 14.0, 50.0, 50.0]],
    )
    XRDAutoDetectService.upload(db_session, xlsx_a)
    assert db_session.query(XRDPhase).filter(
        XRDPhase.experiment_id == "HPHT_STALE001",
        XRDPhase.time_post_reaction_days == 14.0,
    ).count() == 2

    # Upload B — Quartz only, overwrite=True
    xlsx_b = make_excel(
        ["Experiment ID", "Time (days)", "Quartz"],
        [["HPHT_STALE001", 14.0, 100.0]],
    )
    created, updated, skipped, errors = XRDAutoDetectService.upload(
        db_session, xlsx_b, overwrite=True
    )

    assert errors == [], f"Unexpected errors: {errors}"
    phases = (
        db_session.query(XRDPhase)
        .filter(
            XRDPhase.experiment_id == "HPHT_STALE001",
            XRDPhase.time_post_reaction_days == 14.0,
        )
        .all()
    )
    assert len(phases) == 1, f"Expected 1 phase, got {len(phases)}: {[p.mineral_name for p in phases]}"
    assert phases[0].mineral_name == "Quartz"
    assert phases[0].amount == pytest.approx(100.0)


def test_stale_phases_preserved_when_overwrite_false(db_session: Session):
    """Without overwrite, absent phases from the new file are left untouched."""
    exp = _seed_experiment(db_session, "HPHT_STALE002", 9902)

    # Upload A — Quartz + Calcite
    xlsx_a = make_excel(
        ["Experiment ID", "Time (days)", "Quartz", "Calcite"],
        [["HPHT_STALE002", 7.0, 40.0, 60.0]],
    )
    XRDAutoDetectService.upload(db_session, xlsx_a)

    # Upload B — Quartz only, overwrite=False (default)
    xlsx_b = make_excel(
        ["Experiment ID", "Time (days)", "Quartz"],
        [["HPHT_STALE002", 7.0, 80.0]],
    )
    XRDAutoDetectService.upload(db_session, xlsx_b, overwrite=False)

    # Both phases must still exist
    phases = (
        db_session.query(XRDPhase)
        .filter(
            XRDPhase.experiment_id == "HPHT_STALE002",
            XRDPhase.time_post_reaction_days == 7.0,
        )
        .all()
    )
    assert len(phases) == 2
    quartz = next(p for p in phases if p.mineral_name == "Quartz")
    assert quartz.amount == pytest.approx(80.0)  # value updated
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd C:/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox
.venv/Scripts/pytest tests/services/bulk_uploads/test_xrd_upload.py::test_stale_phases_deleted_when_overwrite_true tests/services/bulk_uploads/test_xrd_upload.py::test_stale_phases_preserved_when_overwrite_false -v
```

Expected: `FAILED` — `TypeError: upload() got an unexpected keyword argument 'overwrite'`

---

## Task 2: Fix `_parse_experiment_timepoint` and wire through `XRDAutoDetectService.upload`

**Files:**
- Modify: `backend/services/bulk_uploads/xrd_upload.py`

- [ ] **Step 1: Update `_parse_experiment_timepoint` signature and add delete-before-insert logic**

Replace the function signature and the per-row mineral loop in `xrd_upload.py`. The change:
1. Adds `overwrite: bool = False` param.
2. Tracks which `(experiment_id, time_days)` pairs have already been cleared (avoids double-deletes when same key appears in multiple rows of the same file).
3. When `overwrite=True`, deletes all existing phases for that key before writing, then always inserts. When `overwrite=False`, keeps the existing upsert behaviour.

```python
def _parse_experiment_timepoint(
    db: Session, file_bytes: bytes, overwrite: bool = False
) -> Tuple[int, int, int, List[str]]:
    """
    Parse a wide-format XRD file with explicit Experiment ID + Time (days) columns.

    Each row is one experiment at one timepoint; all remaining columns are mineral phases.
    When overwrite=False: upserts XRDPhase rows keyed on (experiment_id, time_post_reaction_days, mineral_name).
    When overwrite=True: deletes ALL existing XRDPhase rows for each (experiment_id, time_post_reaction_days)
    key before inserting the new set, so only the uploaded phases survive.

    Returns (created, updated, skipped, errors).
    """
    created = updated = skipped = 0
    errors: List[str] = []

    try:
        df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes))
        except Exception as e:
            return 0, 0, 0, [f"Failed to read file: {e}"]

    cols_normalized = [str(c).strip() for c in df.columns]
    df.columns = cols_normalized
    cols_lower = [c.lower() for c in cols_normalized]

    exp_col = next(
        (cols_normalized[i] for i, c in enumerate(cols_lower) if c in _EXP_COL_VARIANTS),
        None,
    )
    if not exp_col:
        return 0, 0, 0, ["No 'Experiment ID' column found."]

    time_col = next(
        (cols_normalized[i] for i, c in enumerate(cols_lower) if c in _TIME_COL_VARIANTS),
        None,
    )
    if not time_col:
        return 0, 0, 0, ["No 'Time (days)' column found."]

    date_col = next(
        (cols_normalized[i] for i, c in enumerate(cols_lower) if c in _DATE_COL_VARIANTS),
        None,
    )

    identity_cols = {exp_col.lower(), time_col.lower()}
    if date_col:
        identity_cols.add(date_col.lower())
    mineral_cols = [c for c in cols_normalized if c.lower() not in identity_cols]
    if not mineral_cols:
        return 0, 0, 0, ["No mineral phase columns detected."]

    exp_cache: dict[str, Optional[object]] = {}
    cleared_keys: set[tuple[str, float]] = set()

    for idx, row in df.iterrows():
        row_num = idx + 2
        exp_id_raw = str(row.get(exp_col) or "").strip()
        if not exp_id_raw:
            skipped += 1
            continue

        time_raw = row.get(time_col)
        if time_raw is None or (isinstance(time_raw, float) and pd.isna(time_raw)):
            skipped += 1
            continue

        try:
            time_days = float(time_raw)
        except (ValueError, TypeError):
            errors.append(f"Row {row_num}: invalid Time (days) '{time_raw}'")
            continue

        if exp_id_raw not in exp_cache:
            exp_cache[exp_id_raw] = _find_experiment(db, exp_id_raw)
        experiment = exp_cache[exp_id_raw]

        if experiment is None:
            errors.append(f"Row {row_num}: experiment '{exp_id_raw}' not found.")
            continue

        measurement_date = None
        if date_col:
            date_raw = row.get(date_col)
            if date_raw is not None and not (isinstance(date_raw, float) and pd.isna(date_raw)):
                import datetime  # noqa: PLC0415
                if isinstance(date_raw, (datetime.date, datetime.datetime)):
                    measurement_date = date_raw
                else:
                    try:
                        measurement_date = datetime.datetime.strptime(str(date_raw).strip(), "%Y-%m-%d")
                    except ValueError:
                        pass  # Unrecognised format — leave as None

        # When overwrite=True, delete all existing phases for this (experiment, timepoint)
        # once per unique key within this file before inserting the new set.
        if overwrite:
            clear_key = (experiment.experiment_id, time_days)
            if clear_key not in cleared_keys:
                (
                    db.query(XRDPhase)
                    .filter(
                        XRDPhase.experiment_id == experiment.experiment_id,
                        XRDPhase.time_post_reaction_days == time_days,
                    )
                    .delete(synchronize_session=False)
                )
                db.flush()
                cleared_keys.add(clear_key)

        for mcol in mineral_cols:
            raw_val = row.get(mcol)
            if raw_val is None or (isinstance(raw_val, float) and pd.isna(raw_val)):
                continue
            try:
                amount_val = float(raw_val)
            except (ValueError, TypeError):
                continue

            mineral_name = _clean_mineral_name(mcol)

            if overwrite:
                # After clearing, always insert fresh
                db.add(XRDPhase(
                    experiment_fk=experiment.id,
                    experiment_id=experiment.experiment_id,
                    time_post_reaction_days=time_days,
                    mineral_name=mineral_name,
                    amount=amount_val,
                    measurement_date=measurement_date,
                ))
                created += 1
            else:
                phase = (
                    db.query(XRDPhase)
                    .filter(
                        XRDPhase.experiment_id == experiment.experiment_id,
                        XRDPhase.time_post_reaction_days == time_days,
                        XRDPhase.mineral_name == mineral_name,
                    )
                    .first()
                )

                if phase:
                    phase.amount = amount_val
                    phase.experiment_fk = experiment.id
                    if measurement_date is not None:
                        phase.measurement_date = measurement_date
                    updated += 1
                else:
                    db.add(XRDPhase(
                        experiment_fk=experiment.id,
                        experiment_id=experiment.experiment_id,
                        time_post_reaction_days=time_days,
                        mineral_name=mineral_name,
                        amount=amount_val,
                        measurement_date=measurement_date,
                    ))
                    created += 1

    return created, updated, skipped, errors
```

- [ ] **Step 2: Update `XRDAutoDetectService.upload` to accept and pass `overwrite`**

Replace the `upload` staticmethod in `XRDAutoDetectService`:

```python
@staticmethod
def upload(db: Session, file_bytes: bytes, overwrite: bool = False) -> Tuple[int, int, int, List[str]]:
    """
    Auto-detect XRD file format and delegate to the appropriate parser.

    Formats supported:
    - experiment-timepoint: 'Experiment ID' + 'Time (days)' columns (user-created)
    - aeris:   Aeris instrument export (Sample ID values like 20260218_HPHT070-d19_02)
    - actlabs: ActLabs report (plain sample_id column)

    When overwrite=True, all existing XRDPhase rows for each batch key (experiment+timepoint
    or sample) are deleted before the new set is inserted.

    Returns (created, updated, skipped, errors).
    """
    fmt = _detect_format(file_bytes)

    if fmt == "experiment-timepoint":
        return _parse_experiment_timepoint(db, file_bytes, overwrite=overwrite)

    if fmt == "aeris":
        from backend.services.bulk_uploads.aeris_xrd import AerisXRDUploadService  # noqa: PLC0415
        return AerisXRDUploadService.bulk_upsert_from_excel(db, file_bytes, overwrite=overwrite)

    if fmt == "actlabs":
        from backend.services.bulk_uploads.actlabs_xrd_report import XRDUploadService  # noqa: PLC0415
        (
            created_ext, updated_ext,
            created_json, updated_json,
            created_phase, updated_phase,
            skipped, errors,
        ) = XRDUploadService.bulk_upsert_from_excel(db, file_bytes, overwrite=overwrite)
        created = created_phase + created_ext
        updated = updated_phase + updated_ext
        return created, updated, skipped, errors

    return 0, 0, 0, [
        "Unable to detect XRD file format. Expected one of:\n"
        "  (1) Experiment+Timepoint: columns 'Experiment ID' and 'Time (days)'\n"
        "  (2) Aeris instrument export: 'Sample ID' values like '20260218_HPHT070-d19_02'\n"
        "  (3) ActLabs format: 'sample_id' column with plain sample identifiers"
    ]
```

- [ ] **Step 3: Run the two stale-phase tests to confirm they pass**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_xrd_upload.py::test_stale_phases_deleted_when_overwrite_true tests/services/bulk_uploads/test_xrd_upload.py::test_stale_phases_preserved_when_overwrite_false -v
```

Expected: both `PASSED`

- [ ] **Step 4: Run the full XRD test suite to check no regressions**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_xrd_upload.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/xrd_upload.py tests/services/bulk_uploads/test_xrd_upload.py
git commit -m "[#18] delete stale XRD phases on overwrite in experiment-timepoint parser

- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Fix Aeris XRD stale phases

**Files:**
- Modify: `backend/services/bulk_uploads/aeris_xrd.py`
- Test: `tests/services/bulk_uploads/test_xrd_upload.py`

- [ ] **Step 1: Write a failing Aeris stale-phase test**

Append to `tests/services/bulk_uploads/test_xrd_upload.py`:

```python
def test_aeris_stale_phases_deleted_when_overwrite_true(db_session: Session):
    """Aeris format: upload A (2 phases), re-upload B (1 phase, overwrite=True).
    Only B's phase survives."""
    exp = _seed_experiment(db_session, "HPHT_AERIS001", 9903)

    # Upload A — Quartz + Magnetite via Aeris format
    xlsx_a = make_excel(
        ["Sample ID", "Rwp", "Quartz", "Magnetite"],
        [["20260101_HPHTAERIS001-d14_01", 5.2, 60.0, 40.0]],
    )
    XRDAutoDetectService.upload(db_session, xlsx_a)
    assert db_session.query(XRDPhase).filter(
        XRDPhase.experiment_id == "HPHT_AERIS001",
        XRDPhase.time_post_reaction_days == 14.0,
    ).count() == 2

    # Upload B — Quartz only, overwrite=True
    xlsx_b = make_excel(
        ["Sample ID", "Rwp", "Quartz"],
        [["20260101_HPHTAERIS001-d14_01", 4.8, 100.0]],
    )
    created, updated, skipped, errors = XRDAutoDetectService.upload(
        db_session, xlsx_b, overwrite=True
    )

    assert errors == [], f"Unexpected errors: {errors}"
    phases = (
        db_session.query(XRDPhase)
        .filter(
            XRDPhase.experiment_id == "HPHT_AERIS001",
            XRDPhase.time_post_reaction_days == 14.0,
        )
        .all()
    )
    assert len(phases) == 1, f"Expected 1 phase, got {len(phases)}: {[p.mineral_name for p in phases]}"
    assert phases[0].mineral_name == "Quartz"
```

> **Note on Aeris sample ID format:** `20260101_HPHTAERIS001-d14_01`
> - `20260101` = date (8 digits)
> - `HPHTAERIS001` = experiment ID (matched via delimiter-insensitive lookup against `HPHT_AERIS001`)
> - `d14` = days = 14.0
> - `_01` = scan number

- [ ] **Step 2: Run to confirm it fails**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_xrd_upload.py::test_aeris_stale_phases_deleted_when_overwrite_true -v
```

Expected: `FAILED` — `TypeError: bulk_upsert_from_excel() got an unexpected keyword argument 'overwrite'`

- [ ] **Step 3: Add `overwrite` param and delete-before-insert to `aeris_xrd.py`**

In `backend/services/bulk_uploads/aeris_xrd.py`, replace the `bulk_upsert_from_excel` signature and add the cleared-keys pattern. The full method becomes:

```python
@staticmethod
def bulk_upsert_from_excel(
    db: Session, file_bytes: bytes, overwrite: bool = False
) -> Tuple[int, int, int, List[str]]:
    """
    Parse an Aeris XRD Excel file and upsert ``XRDPhase`` rows keyed by
    (experiment_id, time_post_reaction_days, mineral_name).

    When overwrite=True, all existing XRDPhase rows for each
    (experiment_id, time_post_reaction_days) key are deleted before the new
    set is inserted, ensuring no stale phases survive.

    Returns (created, updated, skipped, errors).
    """
    created = updated = skipped = 0
    errors: List[str] = []

    try:
        df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as e:
        return 0, 0, 0, [f"Failed to read Excel: {e}"]

    if df.shape[1] < 4:
        return 0, 0, 0, [
            "Excel must contain at least Scan Number, Sample ID, Rwp, "
            "and one mineral column."
        ]

    cols = [str(c).strip() for c in df.columns]
    df.columns = cols

    col_lower = {c.lower(): c for c in cols}
    sample_col = col_lower.get("sample id") or col_lower.get("sample_id")
    rwp_col = col_lower.get("rwp")

    if not sample_col:
        return 0, 0, 0, ["Could not find a 'Sample ID' column."]

    skip_cols = {
        (sample_col or "").lower(),
        (rwp_col or "").lower(),
        "scan number",
        "scan_number",
    }
    mineral_cols = [c for c in cols if c.lower() not in skip_cols]
    if not mineral_cols:
        return 0, 0, 0, ["No mineral-phase columns detected."]

    exp_cache: dict[str, Optional[Experiment]] = {}
    cleared_keys: set[tuple[str, float]] = set()

    for idx, row in df.iterrows():
        row_num = idx + 2
        raw_sample = str(row.get(sample_col, "")).strip()
        if not raw_sample:
            skipped += 1
            continue

        parsed = _parse_aeris_sample_id(raw_sample)
        if parsed is None:
            errors.append(
                f"Row {row_num}: Sample ID '{raw_sample}' does not match "
                f"expected format DATE_ExperimentID-dDAYS_SCAN "
                f"(e.g. 20260218_HPHT070-d19_02)."
            )
            continue

        measurement_date, exp_id_raw, days = parsed

        if exp_id_raw not in exp_cache:
            exp_cache[exp_id_raw] = _find_experiment(db, exp_id_raw)
        experiment = exp_cache[exp_id_raw]

        if experiment is None:
            errors.append(
                f"Row {row_num}: Experiment '{exp_id_raw}' not found in "
                f"database (tried delimiter-insensitive match)."
            )
            continue

        exp_id_db = experiment.experiment_id
        exp_fk = experiment.id

        rwp_val: Optional[float] = None
        if rwp_col:
            raw_rwp = row.get(rwp_col)
            try:
                if raw_rwp is not None and not (
                    isinstance(raw_rwp, float) and pd.isna(raw_rwp)
                ):
                    rwp_val = float(raw_rwp)
            except (ValueError, TypeError):
                pass

        # When overwrite=True, delete existing phases for this key once per file.
        if overwrite:
            clear_key = (exp_id_db, days)
            if clear_key not in cleared_keys:
                (
                    db.query(XRDPhase)
                    .filter(
                        XRDPhase.experiment_id == exp_id_db,
                        XRDPhase.time_post_reaction_days == days,
                    )
                    .delete(synchronize_session=False)
                )
                db.flush()
                cleared_keys.add(clear_key)

        for mcol in mineral_cols:
            raw_val = row.get(mcol)
            try:
                if raw_val is None or (
                    isinstance(raw_val, float) and pd.isna(raw_val)
                ):
                    continue
                amount_val = float(raw_val)
            except (ValueError, TypeError):
                continue

            mineral_name = _clean_mineral_name(mcol)

            if overwrite:
                db.add(XRDPhase(
                    experiment_fk=exp_fk,
                    experiment_id=exp_id_db,
                    time_post_reaction_days=days,
                    mineral_name=mineral_name,
                    amount=amount_val,
                    rwp=rwp_val,
                    measurement_date=measurement_date,
                ))
                created += 1
            else:
                phase = (
                    db.query(XRDPhase)
                    .filter(
                        XRDPhase.experiment_id == exp_id_db,
                        XRDPhase.time_post_reaction_days == days,
                        XRDPhase.mineral_name == mineral_name,
                    )
                    .first()
                )

                if phase:
                    phase.amount = amount_val
                    phase.rwp = rwp_val
                    phase.measurement_date = measurement_date
                    phase.experiment_fk = exp_fk
                    updated += 1
                else:
                    db.add(XRDPhase(
                        experiment_fk=exp_fk,
                        experiment_id=exp_id_db,
                        time_post_reaction_days=days,
                        mineral_name=mineral_name,
                        amount=amount_val,
                        rwp=rwp_val,
                        measurement_date=measurement_date,
                    ))
                    created += 1

    return created, updated, skipped, errors
```

> **Note:** You need to read the full current body of `aeris_xrd.py` before editing to ensure you capture lines not shown here (imports, `_parse_aeris_sample_id`, `_find_experiment`, `_clean_mineral_name` helpers). The above replaces only the `bulk_upsert_from_excel` method body. The helpers and class definition remain unchanged.

- [ ] **Step 4: Run the Aeris test to confirm it passes**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_xrd_upload.py::test_aeris_stale_phases_deleted_when_overwrite_true -v
```

Expected: `PASSED`

- [ ] **Step 5: Run the full XRD test suite**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_xrd_upload.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add backend/services/bulk_uploads/aeris_xrd.py tests/services/bulk_uploads/test_xrd_upload.py
git commit -m "[#18] delete stale XRD phases on overwrite in Aeris parser

- Tests added: yes
- Docs updated: no"
```

---

## Task 4: Fix ActLabs XRD stale phases

**Files:**
- Modify: `backend/services/bulk_uploads/actlabs_xrd_report.py`
- Test: `tests/services/bulk_uploads/test_xrd_upload.py`

- [ ] **Step 1: Write a failing ActLabs stale-phase test**

Append to `tests/services/bulk_uploads/test_xrd_upload.py`. ActLabs format uses `sample_id` column; you need a `SampleInfo` record, not an `Experiment`.

```python
from database.models import SampleInfo  # add to imports at top of file


def test_actlabs_stale_phases_deleted_when_overwrite_true(db_session: Session):
    """ActLabs format: upload A (2 phases for a sample), re-upload B (1 phase, overwrite=True).
    Only B's phase survives."""
    sample = SampleInfo(sample_id="S_STALE001")
    db_session.add(sample)
    db_session.flush()

    # Upload A — Quartz + Calcite
    xlsx_a = make_excel(
        ["sample_id", "Quartz", "Calcite"],
        [["S_STALE001", 55.0, 45.0]],
    )
    XRDAutoDetectService.upload(db_session, xlsx_a)
    assert db_session.query(XRDPhase).filter(
        XRDPhase.sample_id == "S_STALE001"
    ).count() == 2

    # Upload B — Quartz only, overwrite=True
    xlsx_b = make_excel(
        ["sample_id", "Quartz"],
        [["S_STALE001", 100.0]],
    )
    created, updated, skipped, errors = XRDAutoDetectService.upload(
        db_session, xlsx_b, overwrite=True
    )

    assert errors == [], f"Unexpected errors: {errors}"
    phases = db_session.query(XRDPhase).filter(
        XRDPhase.sample_id == "S_STALE001"
    ).all()
    assert len(phases) == 1, f"Expected 1 phase, got {len(phases)}: {[p.mineral_name for p in phases]}"
    assert phases[0].mineral_name == "Quartz"
    assert phases[0].amount == pytest.approx(100.0)
```

- [ ] **Step 2: Run to confirm it fails**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_xrd_upload.py::test_actlabs_stale_phases_deleted_when_overwrite_true -v
```

Expected: `FAILED` — `TypeError: bulk_upsert_from_excel() got an unexpected keyword argument 'overwrite'`

- [ ] **Step 3: Add `overwrite` param and delete logic to `actlabs_xrd_report.py`**

In `backend/services/bulk_uploads/actlabs_xrd_report.py`, replace the `bulk_upsert_from_excel` method signature and add the delete step inside the per-sample loop. The full method becomes:

```python
@staticmethod
def bulk_upsert_from_excel(
    db: Session, file_bytes: bytes, overwrite: bool = False
) -> Tuple[int, int, int, int, int, int, int, List[str]]:
    """
    Upsert XRD mineralogy per sample from an Excel file.

    When overwrite=True, all existing XRDPhase rows for the sample are deleted
    before inserting the new set so no stale phases survive. The XRDAnalysis.mineral_phases
    JSON is always replaced (existing behavior).

    Returns (
      created_ext, updated_ext, created_json, updated_json, created_phase, updated_phase, skipped_rows, errors
    ).
    """
    created_ext = updated_ext = created_json = updated_json = created_phase = updated_phase = skipped = 0
    errors: List[str] = []

    try:
        df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as e:
        return 0, 0, 0, 0, 0, 0, 0, [f"Failed to read Excel: {e}"]

    if df.shape[1] < 2:
        return 0, 0, 0, 0, 0, 0, 0, ["Template must include 'sample_id' and at least one mineral column."]

    normalized = [str(c).strip() for c in df.columns]
    df.columns = normalized

    sample_col = None
    for c in df.columns:
        if c.lower() == "sample_id":
            sample_col = c
            break
    if not sample_col:
        return 0, 0, 0, 0, 0, 0, 0, ["First column must be 'sample_id'."]

    mineral_cols = [c for c in df.columns if c != sample_col]
    if not mineral_cols:
        return 0, 0, 0, 0, 0, 0, 0, ["No mineral columns detected."]

    for idx, row in df.iterrows():
        try:
            sample_id = str(row.get(sample_col) or '').strip()
            if not sample_id:
                skipped += 1
                continue

            sample = fuzzy_find_sample(db, sample_id)
            if not sample:
                errors.append(f"Row {idx+2}: sample_id '{sample_id}' not found")
                continue
            canonical_id = sample.sample_id

            mineral_data = {}
            for mcol in mineral_cols:
                val = row.get(mcol)
                try:
                    if val is None or (isinstance(val, float) and pd.isna(val)):
                        continue
                    fval = float(val)
                except Exception:
                    continue
                mineral_data[mcol.strip().lower()] = fval

            # Find or create ExternalAnalysis for this sample/type
            ext = (
                db.query(ExternalAnalysis)
                .filter(
                    ExternalAnalysis.sample_id == canonical_id,
                    ExternalAnalysis.analysis_type == "XRD",
                )
                .first()
            )
            if not ext:
                ext = ExternalAnalysis(sample_id=canonical_id, analysis_type="XRD")
                db.add(ext)
                db.flush()
                created_ext += 1
            else:
                updated_ext += 1

            # Upsert JSON model (always replace — existing behaviour)
            xrd = db.query(XRDAnalysis).filter(XRDAnalysis.external_analysis_id == ext.id).first()
            if xrd:
                xrd.mineral_phases = mineral_data or None
                updated_json += 1
            else:
                xrd = XRDAnalysis(external_analysis_id=ext.id, mineral_phases=mineral_data or None)
                db.add(xrd)
                created_json += 1

            # When overwrite=True, clear all existing XRDPhase rows for this sample
            # so no stale phases from a previous upload survive.
            if overwrite:
                (
                    db.query(XRDPhase)
                    .filter(XRDPhase.sample_id == canonical_id)
                    .delete(synchronize_session=False)
                )
                db.flush()

            # Insert or upsert normalized phases per mineral
            for mcol in mineral_cols:
                display_name = str(mcol).strip()
                key = display_name.lower()
                if key not in mineral_data:
                    continue
                amount_val = mineral_data[key]

                if overwrite:
                    db.add(XRDPhase(
                        sample_id=canonical_id,
                        external_analysis_id=ext.id,
                        mineral_name=display_name,
                        amount=amount_val,
                    ))
                    created_phase += 1
                else:
                    phase = (
                        db.query(XRDPhase)
                        .filter(
                            XRDPhase.sample_id == canonical_id,
                            XRDPhase.mineral_name == display_name,
                        )
                        .first()
                    )
                    if phase:
                        phase.amount = amount_val
                        if phase.external_analysis_id is None:
                            phase.external_analysis_id = ext.id
                        updated_phase += 1
                    else:
                        phase = XRDPhase(
                            sample_id=canonical_id,
                            external_analysis_id=ext.id,
                            mineral_name=display_name,
                            amount=amount_val,
                        )
                        db.add(phase)
                        created_phase += 1

        except Exception as e:
            errors.append(f"Row {idx+2}: {e}")

    return created_ext, updated_ext, created_json, updated_json, created_phase, updated_phase, skipped, errors
```

- [ ] **Step 4: Run the ActLabs test to confirm it passes**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_xrd_upload.py::test_actlabs_stale_phases_deleted_when_overwrite_true -v
```

Expected: `PASSED`

- [ ] **Step 5: Run the full XRD test suite**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_xrd_upload.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add backend/services/bulk_uploads/actlabs_xrd_report.py tests/services/bulk_uploads/test_xrd_upload.py
git commit -m "[#18] delete stale XRD phases on overwrite in ActLabs parser

- Tests added: yes
- Docs updated: no"
```

---

## Task 5: Wire `overwrite` through the FastAPI router

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py`

- [ ] **Step 1: Update the `upload_xrd_mineralogy` endpoint**

In `backend/api/routers/bulk_uploads.py`, find the `upload_xrd_mineralogy` function (currently at ~line 239) and replace it with:

```python
@router.post("/xrd-mineralogy", response_model=UploadResponse)
async def upload_xrd_mineralogy(
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload an XRD file — auto-detects Aeris, ActLabs, or Experiment+Timepoint format.

    When overwrite=True, all existing XRDPhase rows for each matching key
    (experiment+timepoint or sample) are deleted before the new phases are inserted.
    """
    from backend.services.bulk_uploads.xrd_upload import XRDAutoDetectService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        created, updated, skipped, errors = XRDAutoDetectService.upload(
            db, file_bytes, overwrite=overwrite
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        log.error("xrd_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        message=f"XRD: {created} created, {updated} updated",
    )
```

- [ ] **Step 2: Run the full XRD test suite (no new failures expected)**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_xrd_upload.py -v
```

Expected: all tests `PASSED` (router change is wiring only; parsers already tested)

- [ ] **Step 3: Commit**

```bash
git add backend/api/routers/bulk_uploads.py
git commit -m "[#18] add overwrite Form param to xrd-mineralogy router endpoint

- Tests added: no
- Docs updated: no"
```

---

## Task 6: Frontend API — pass overwrite flag

**Files:**
- Modify: `frontend/src/api/bulkUploads.ts`

- [ ] **Step 1: Update `uploadXrdMineralogy` to accept and send `overwrite`**

In `frontend/src/api/bulkUploads.ts`, replace the XRD mineralogy line:

```typescript
// Card 3 — XRD Mineralogy (auto-detects Aeris, ActLabs, or Experiment+Timepoint)
uploadXrdMineralogy: (file: File, overwrite = false) => {
  const fd = fileForm(file)
  fd.append('overwrite', overwrite ? 'true' : 'false')
  return post<BulkUploadResult>('/bulk-uploads/xrd-mineralogy', fd)
},
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/bulkUploads.ts
git commit -m "[#18] pass overwrite flag to xrd-mineralogy API endpoint

- Tests added: no
- Docs updated: no"
```

---

## Task 7: Frontend — add `skippedMessage` prop to `UploadRow`

**Files:**
- Modify: `frontend/src/pages/BulkUploadRow.tsx`

This task adds a general-purpose `skippedMessage` prop that the XRD card (Task 8) will use to surface the "enable overwrite" hint when phases are skipped.

- [ ] **Step 1: Add `skippedMessage` prop to `UploadRowProps` and render it**

In `frontend/src/pages/BulkUploadRow.tsx`:

1. Add to the `UploadRowProps` interface (after `syncFn`):

```typescript
/** If provided, shown below the skipped badge when result.skipped > 0 */
skippedMessage?: string
```

2. Add `skippedMessage` to the destructured props in the `UploadRow` function signature (after `syncFn`):

```typescript
export function UploadRow({
  title,
  description,
  helpText,
  accept,
  uploadFn,
  templateType,
  templateMode,
  syncFn,
  skippedMessage,
  topContent,
  isOpen,
  onToggle,
}: UploadRowProps) {
```

3. In the result summary section, after the badges `<div className="flex flex-wrap gap-2">`, add the skipped hint. Find the closing `</div>` of the badges block and insert after it:

```tsx
{result.skipped > 0 && skippedMessage && (
  <p className="text-xs text-amber-400 leading-relaxed">{skippedMessage}</p>
)}
```

The full result section after this change looks like:

```tsx
{result && !isPending && (
  <div className="space-y-2">
    <div className="flex flex-wrap gap-2">
      <Badge variant="success">Created: {result.created}</Badge>
      <Badge variant="default">Updated: {result.updated}</Badge>
      <Badge variant="warning">Skipped: {result.skipped}</Badge>
      {result.errors.length > 0 && (
        <Badge variant="error">Errors: {result.errors.length}</Badge>
      )}
      {result.warnings.length > 0 && (
        <Badge variant="warning">Warnings: {result.warnings.length}</Badge>
      )}
    </div>

    {result.skipped > 0 && skippedMessage && (
      <p className="text-xs text-amber-400 leading-relaxed">{skippedMessage}</p>
    )}

    {/* Error list */}
    {result.errors.length > 0 && (
      // ... existing error list unchanged
    )}
    {/* Warnings list */}
    {result.warnings.length > 0 && (
      // ... existing warnings list unchanged
    )}
  </div>
)}
```

- [ ] **Step 2: Verify TypeScript compiles with no errors**

```bash
cd C:/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox/frontend
npx tsc --noEmit
```

Expected: no output (zero errors)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/BulkUploadRow.tsx
git commit -m "[#18] add skippedMessage prop to UploadRow for contextual skipped hints

- Tests added: no
- Docs updated: no"
```

---

## Task 8: Frontend — overwrite toggle in XRD Mineralogy card

**Files:**
- Modify: `frontend/src/pages/BulkUploads.tsx`

- [ ] **Step 1: Add `xrdOverwrite` state and the `XrdOverwriteToggle` component**

In `frontend/src/pages/BulkUploads.tsx`, after the `XrdModeToggle` component definition (~line 87) and before `// ─── Page ─────────────────────────────────────────────────────────────────────`, insert:

```tsx
// ─── XRD overwrite toggle ─────────────────────────────────────────────────────
function XrdOverwriteToggle({
  checked,
  onChange,
}: {
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          className="w-3.5 h-3.5 rounded accent-coral-500"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="text-xs text-ink-secondary">
          Replace existing results for matching experiment / timepoint
        </span>
      </label>
      {checked ? (
        <p className="text-xs text-amber-400 leading-relaxed pl-5">
          All existing mineral phases for any matching experiment and timepoint in this file
          will be deleted and replaced with the values from this upload.
        </p>
      ) : (
        <p className="text-xs text-ink-muted leading-relaxed pl-5">
          Existing mineral phases for the same experiment and timepoint will be left
          unchanged. Only new phases will be added.
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Add `xrdOverwrite` state to `BulkUploadsPage`**

In the `BulkUploadsPage` function body, add alongside the other state declarations:

```tsx
const [xrdOverwrite, setXrdOverwrite] = useState(false)
```

- [ ] **Step 3: Update the XRD Mineralogy `UploadRow` entry**

Replace the XRD Mineralogy `UploadRow` block (lines ~142–159 in BulkUploads.tsx):

```tsx
{/* 3 — XRD Mineralogy */}
<UploadRow
  id="xrd-mineralogy"
  title="XRD Mineralogy"
  description="Upload XRD mineral phase data — auto-detects format from column names"
  helpText={
    xrdMode === 'experiment'
      ? "Experiment+Timepoint format: include 'Experiment ID' and 'Time (days)' columns plus one column per mineral phase. The format is auto-detected on upload."
      : "Sample-based format: include a 'sample_id' column plus one column per mineral phase. Aeris instrument exports (sample IDs like '20260218_HPHT070-d19_02') are also accepted."
  }
  accept=".xlsx,.xls,.csv"
  uploadFn={(file) => bulkUploadsApi.uploadXrdMineralogy(file, xrdOverwrite)}
  templateType="xrd-mineralogy"
  templateMode={xrdMode}
  topContent={
    <>
      <XrdModeToggle mode={xrdMode} onChange={setXrdMode} />
      <XrdOverwriteToggle checked={xrdOverwrite} onChange={setXrdOverwrite} />
    </>
  }
  skippedMessage={
    !xrdOverwrite
      ? "Some rows were skipped because data already exists for these timepoints. Enable 'Replace existing results' to overwrite."
      : undefined
  }
  isOpen={isOpen('xrd-mineralogy')}
  onToggle={() => toggle('xrd-mineralogy')}
/>
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: no output

- [ ] **Step 5: Verify ESLint is clean**

```bash
npx eslint src/pages/BulkUploads.tsx src/pages/BulkUploadRow.tsx --ext .tsx
```

Expected: no warnings or errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/BulkUploads.tsx
git commit -m "[#18] add overwrite toggle and contextual messaging to XRD upload card

- Tests added: no
- Docs updated: no"
```

---

## Task 9: Final verification and PR

- [ ] **Step 1: Run the full backend test suite**

```bash
cd C:/Users/MathewHearl/Documents/0x_Software/database_sandbox/experiment_tracking_sandbox
.venv/Scripts/pytest tests/services/bulk_uploads/ -v
```

Expected: all tests `PASSED`

- [ ] **Step 2: Run frontend build to catch any type or import errors**

```bash
cd frontend
npm run build
```

Expected: `✓ built in` — zero errors

- [ ] **Step 3: Create PR**

```bash
gh pr create \
  --base develop \
  --title "[#18] Fix XRD stale phases on re-upload + add overwrite UX" \
  --body "$(cat <<'EOF'
## Summary

- **Bug fix (all 3 parsers):** When `overwrite=True`, delete all existing `XRDPhase` rows for the matching key (experiment+timepoint or sample) before inserting the new set. Prevents stale phases from prior uploads surviving a re-upload.
- **Router:** Added `overwrite: bool = Form(False)` to `POST /api/bulk-uploads/xrd-mineralogy` and wired it through `XRDAutoDetectService.upload`.
- **Frontend:** Added `XrdOverwriteToggle` checkbox to the XRD Mineralogy upload card with conditional helper/warning text; passes flag to API. Added `skippedMessage` prop to `UploadRow` so the "enable overwrite" hint surfaces when rows are skipped.

## Parsers fixed
- `backend/services/bulk_uploads/xrd_upload.py` — experiment-timepoint parser
- `backend/services/bulk_uploads/aeris_xrd.py` — Aeris instrument export parser
- `backend/services/bulk_uploads/actlabs_xrd_report.py` — ActLabs sample-based parser

## Test plan
- [ ] Upload an Experiment+Timepoint XRD file (2 minerals) → verify 2 phases in DB
- [ ] Upload a second file for the same experiment+timepoint (1 mineral) with overwrite=True → verify only 1 phase remains, phases sum to ≤ 100 %
- [ ] Repeat with overwrite=False → verify 2 phases still exist (original skipped, new one updated)
- [ ] Verify the overwrite toggle checkbox and helper/warning text render correctly in the XRD Mineralogy card
- [ ] Verify skipped-rows message appears in result banner after a no-overwrite re-upload

Closes #18

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

### Spec coverage check

| Requirement | Task |
|-------------|------|
| Delete stale XRDPhase rows (experiment-timepoint) when overwrite=True | Task 2 |
| Delete stale XRDPhase rows (Aeris) when overwrite=True | Task 3 |
| Delete stale XRDPhase rows (ActLabs sample-based) when overwrite=True | Task 4 |
| XRDAnalysis.mineral_phases JSON kept in sync | Already replaced on each upsert (existing behaviour, no new task needed) |
| Delete-before-insert inside same transaction (rollback safety) | `db.flush()` before insert; commit in router — transaction intact |
| Router accepts `overwrite` Form field | Task 5 |
| Frontend: overwrite checkbox on XRD card | Task 8 |
| Frontend: helper text when unchecked | Task 8 |
| Frontend: warning text when checked | Task 8 |
| Frontend: skipped-rows message with "enable overwrite" hint | Tasks 7 + 8 |
| Test: upload A (N phases) → upload B (strict subset, overwrite=True) → only B survives | Tasks 1, 3, 4 |

### Placeholder scan

No TBDs, no "add appropriate error handling" stubs. All code blocks are complete.

### Type consistency

- `XRDAutoDetectService.upload(db, file_bytes, overwrite=overwrite)` — matches updated signature in Task 2.
- `AerisXRDUploadService.bulk_upsert_from_excel(db, file_bytes, overwrite=overwrite)` — matches Task 3.
- `XRDUploadService.bulk_upsert_from_excel(db, file_bytes, overwrite=overwrite)` — matches Task 4.
- `bulkUploadsApi.uploadXrdMineralogy(file, xrdOverwrite)` — matches Task 6.
- `skippedMessage` prop — added to interface in Task 7, consumed in Task 8. ✓
