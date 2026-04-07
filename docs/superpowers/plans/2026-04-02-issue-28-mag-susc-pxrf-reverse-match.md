# Issue #28 — Rock Inventory mag susc + pXRF Reverse-Match Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `magnetic_susceptibility` column to the Rock Inventory bulk upload parser + template, and trigger `evaluate_characterized` re-evaluation for affected samples after a pXRF bulk upload.

**Architecture:** Two independent backend changes: (1) `rock_inventory.py` parser gains mag-susc alias detection using the same EA create/overwrite pattern as pxrf_reading_no, and the template endpoint gains an INSTRUCTIONS sheet; (2) the `upload_pxrf` router endpoint extracts reading_no values from the file bytes using a lightweight pandas parse, then queries `ExternalAnalysis` post-ingest to re-evaluate and log `characterized` status changes. No schema or migration changes needed — `ExternalAnalysis.magnetic_susceptibility` already exists.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.x, pandas, openpyxl, pytest, PostgreSQL (test DB at `postgresql://experiments_user:password@localhost:5432/experiments_test`)

---

## File Map

| File | Change |
|------|--------|
| `backend/services/bulk_uploads/rock_inventory.py` | Add mag-susc alias detection + EA create/overwrite (Part 1 parser) |
| `backend/api/routers/bulk_uploads.py` | (a) rock-inventory template: add pxrf_reading_no, magnetic_susceptibility, overwrite, INSTRUCTIONS sheet; (b) upload_pxrf: add reading_no extraction + reverse-match post-processing |
| `tests/services/bulk_uploads/test_rock_inventory.py` | Add 6 tests for mag-susc behavior |
| `tests/api/test_bulk_uploads.py` | Add 3 tests for pXRF reverse-match |

**Tasks 1–3 (parser + template) and Tasks 4–5 (reverse-match) are independent and can be parallelized.**

---

## Task 1: Write failing tests for mag-susc parser behavior

**Files:**
- Modify: `tests/services/bulk_uploads/test_rock_inventory.py`

- [ ] **Step 1: Append the 6 failing tests to `test_rock_inventory.py`**

Add these tests at the end of `tests/services/bulk_uploads/test_rock_inventory.py`:

```python
# ---------------------------------------------------------------------------
# magnetic_susceptibility tests (Issue #28)
# ---------------------------------------------------------------------------

def test_mag_susc_creates_external_analysis(db_session: Session):
    """magnetic_susceptibility column creates ExternalAnalysis of type 'Magnetic Susceptibility'."""
    from database.models.analysis import ExternalAnalysis

    xlsx = make_excel(
        ["sample_id", "magnetic_susceptibility"],
        [["S_MAG001", 2.5]],
    )
    created, updated, _images, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )

    assert errors == [], errors
    assert created == 1
    db_session.flush()

    # Service normalizes "S_MAG001" → "SMAG001"
    ea = (
        db_session.query(ExternalAnalysis)
        .filter(
            ExternalAnalysis.sample_id == "SMAG001",
            ExternalAnalysis.analysis_type == "Magnetic Susceptibility",
        )
        .first()
    )
    assert ea is not None
    assert ea.magnetic_susceptibility == pytest.approx(2.5)


def test_mag_susc_aliases_recognized(db_session: Session):
    """All four alias column names for mag susc are accepted."""
    from database.models.analysis import ExternalAnalysis

    aliases = ["magnetic susceptibility", "mag_susc", "mag susc"]
    for alias in aliases:
        # Produce a unique sample_id per alias to avoid cross-contamination
        safe_alias = alias.replace(" ", "X").replace("_", "Y").upper()
        xlsx = make_excel(
            ["sample_id", alias],
            [[f"S_{safe_alias}", 3.7]],
        )
        created, updated, _images, skipped, errors, warnings = (
            RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
        )
        assert errors == [], f"Alias '{alias}' produced errors: {errors}"
        db_session.flush()
        expected_sid = f"S{safe_alias}"  # normalization: uppercase, no underscores
        ea = (
            db_session.query(ExternalAnalysis)
            .filter(
                ExternalAnalysis.sample_id == expected_sid,
                ExternalAnalysis.analysis_type == "Magnetic Susceptibility",
            )
            .first()
        )
        assert ea is not None, f"No EA created for alias '{alias}'"


def test_mag_susc_blank_skipped(db_session: Session):
    """Blank magnetic_susceptibility cell does not create an ExternalAnalysis."""
    from database.models.analysis import ExternalAnalysis

    xlsx = make_excel(
        ["sample_id", "magnetic_susceptibility"],
        [["S_BLANK001", ""]],
    )
    RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    db_session.flush()

    ea = (
        db_session.query(ExternalAnalysis)
        .filter(
            ExternalAnalysis.sample_id == "SBLANK001",
            ExternalAnalysis.analysis_type == "Magnetic Susceptibility",
        )
        .first()
    )
    assert ea is None


def test_mag_susc_non_numeric_skipped(db_session: Session):
    """Non-numeric mag susc value does not create an EA and produces no error."""
    from database.models.analysis import ExternalAnalysis

    xlsx = make_excel(
        ["sample_id", "magnetic_susceptibility"],
        [["S_NAN001", "not-a-number"]],
    )
    created, updated, _images, skipped, errors, warnings = (
        RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    )
    assert errors == [], errors
    db_session.flush()

    ea = (
        db_session.query(ExternalAnalysis)
        .filter(
            ExternalAnalysis.sample_id == "SNAN001",
            ExternalAnalysis.analysis_type == "Magnetic Susceptibility",
        )
        .first()
    )
    assert ea is None


def test_mag_susc_skip_without_overwrite(db_session: Session):
    """Re-upload with a different value and no overwrite flag leaves the existing EA unchanged."""
    from database.models.analysis import ExternalAnalysis
    from database.models.samples import SampleInfo

    sample = SampleInfo(sample_id="SOVER001")
    db_session.add(sample)
    db_session.flush()
    ea = ExternalAnalysis(
        sample_id="SOVER001",
        analysis_type="Magnetic Susceptibility",
        magnetic_susceptibility=1.0,
    )
    db_session.add(ea)
    db_session.flush()

    xlsx = make_excel(
        ["sample_id", "magnetic_susceptibility"],
        [["SOVER001", 99.9]],
    )
    RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    db_session.flush()
    db_session.refresh(ea)

    assert ea.magnetic_susceptibility == pytest.approx(1.0)  # unchanged


def test_mag_susc_update_with_overwrite(db_session: Session):
    """Re-upload with overwrite=TRUE updates the existing EA's magnetic_susceptibility value."""
    from database.models.analysis import ExternalAnalysis
    from database.models.samples import SampleInfo

    sample = SampleInfo(sample_id="SOVER002")
    db_session.add(sample)
    db_session.flush()
    ea = ExternalAnalysis(
        sample_id="SOVER002",
        analysis_type="Magnetic Susceptibility",
        magnetic_susceptibility=1.0,
    )
    db_session.add(ea)
    db_session.flush()

    xlsx = make_excel(
        ["sample_id", "magnetic_susceptibility", "overwrite"],
        [["SOVER002", 99.9, "TRUE"]],
    )
    RockInventoryService.bulk_upsert_samples(db_session, xlsx, [])
    db_session.flush()
    db_session.refresh(ea)

    assert ea.magnetic_susceptibility == pytest.approx(99.9)
```

- [ ] **Step 2: Run the failing tests to confirm they fail for the right reason**

```bash
cd C:\Users\MathewHearl\Documents\0x_Software\database_sandbox\experiment_tracking_sandbox
.venv/Scripts/pytest tests/services/bulk_uploads/test_rock_inventory.py -k "mag_susc" -v 2>&1 | tail -30
```

Expected: all 6 tests FAIL because the mag-susc logic doesn't exist yet. Some will fail with `AttributeError` or `AssertionError: ea is None`.

---

## Task 2: Implement magnetic_susceptibility handling in rock_inventory.py

**Files:**
- Modify: `backend/services/bulk_uploads/rock_inventory.py`

- [ ] **Step 1: Add alias resolution and per-row mag-susc handling**

In `backend/services/bulk_uploads/rock_inventory.py`, make two edits:

**Edit A** — Add alias resolution constant and column detection right before the `seen_samples = {}` line (before the `for idx, row in df.iterrows():` loop):

Find:
```python
        # Track samples in this batch by normalized ID to prevent duplicates
        seen_samples = {}
```

Replace with:
```python
        # Resolve magnetic_susceptibility column from accepted aliases (all lowercased by header normalization)
        _MAG_SUSC_ALIASES = {"magnetic_susceptibility", "magnetic susceptibility", "mag_susc", "mag susc"}
        _mag_susc_col = next((c for c in df.columns if c in _MAG_SUSC_ALIASES), None)

        # Track samples in this batch by normalized ID to prevent duplicates
        seen_samples = {}
```

**Edit B** — Add mag-susc EA block inside the row loop, right after the existing `pxrf_reading_no` block (after `except Exception as e: errors.append(f"Row {idx+2} ...pXRF link...")`) and before `if is_new: created += 1`:

Find:
```python
                    except Exception as e:
                        errors.append(f"Row {idx+2} ({sample.sample_id}): failed to create pXRF link — {e}")

                if is_new:
                    created += 1
```

Replace with:
```python
                    except Exception as e:
                        errors.append(f"Row {idx+2} ({sample.sample_id}): failed to create pXRF link — {e}")

                # Create/update ExternalAnalysis for magnetic_susceptibility if column present
                if _mag_susc_col is not None:
                    try:
                        mag_val_raw = row.get(_mag_susc_col)
                        mag_float: Optional[float] = None
                        if mag_val_raw is not None and not (
                            isinstance(mag_val_raw, float) and pd.isna(mag_val_raw)
                        ):
                            try:
                                mag_float = float(str(mag_val_raw).strip())
                            except (ValueError, TypeError):
                                mag_float = None

                        if mag_float is not None:
                            existing_mag = (
                                db.query(ExternalAnalysis)
                                .filter(
                                    ExternalAnalysis.sample_id == sample.sample_id,
                                    ExternalAnalysis.analysis_type == "Magnetic Susceptibility",
                                )
                                .first()
                            )
                            if existing_mag is None:
                                db.add(ExternalAnalysis(
                                    sample_id=sample.sample_id,
                                    analysis_type="Magnetic Susceptibility",
                                    magnetic_susceptibility=mag_float,
                                ))
                            elif overwrite_mode:
                                existing_mag.magnetic_susceptibility = mag_float
                    except Exception as e:
                        errors.append(
                            f"Row {idx+2} ({sample.sample_id}): failed to create mag susc record — {e}"
                        )

                if is_new:
                    created += 1
```

- [ ] **Step 2: Run the mag-susc tests to confirm they pass**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_rock_inventory.py -k "mag_susc" -v 2>&1 | tail -20
```

Expected: all 6 tests PASS.

- [ ] **Step 3: Run the full rock_inventory test suite to confirm no regressions**

```bash
.venv/Scripts/pytest tests/services/bulk_uploads/test_rock_inventory.py -v 2>&1 | tail -20
```

Expected: all existing tests still PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/services/bulk_uploads/rock_inventory.py tests/services/bulk_uploads/test_rock_inventory.py
git commit -m "[#28] add magnetic_susceptibility to rock inventory parser

- detect alias columns (magnetic_susceptibility, magnetic susceptibility,
  mag_susc, mag susc) after header normalization
- find-or-create ExternalAnalysis type 'Magnetic Susceptibility' per row
- respect overwrite flag: skip existing if false, update if true
- blank/non-numeric values silently skipped (no error)
- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Update rock-inventory template in bulk_uploads.py

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py` (the `_get_template_bytes` function, rock-inventory case)

- [ ] **Step 1: Replace the rock-inventory template case in `_get_template_bytes`**

In `backend/api/routers/bulk_uploads.py`, find this block:

```python
    if upload_type == "rock-inventory":
        return _simple_template(
            headers=["sample_id", "rock_classification", "state", "country",
                     "locality", "latitude", "longitude", "description", "characterized"],
            required={"sample_id"},
            example_row=["S001", "Basalt", "BC", "Canada", "Vancouver Island",
                         49.5, -125.0, "Fresh olivine basalt", "FALSE"],
        )
```

Replace with:

```python
    if upload_type == "rock-inventory":
        import openpyxl  # noqa: PLC0415
        from openpyxl.styles import PatternFill, Font, Alignment  # noqa: PLC0415

        headers = [
            "sample_id", "rock_classification", "state", "country",
            "locality", "latitude", "longitude", "description",
            "characterized", "pxrf_reading_no", "magnetic_susceptibility", "overwrite",
        ]
        required = {"sample_id"}
        example_row = [
            "S001", "Basalt", "BC", "Canada", "Vancouver Island",
            49.5, -125.0, "Fresh olivine basalt", "FALSE", "", "", "FALSE",
        ]
        req_fill = PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid")
        opt_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Template"
        for col, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = Font(bold=True)
            cell.fill = req_fill if h in required else opt_fill
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[cell.column_letter].width = max(len(h) + 4, 16)
        for col, val in enumerate(example_row, start=1):
            ws.cell(row=2, column=col, value=val)

        ws_inst = wb.create_sheet("INSTRUCTIONS")
        ws_inst.column_dimensions["A"].width = 30
        ws_inst.column_dimensions["B"].width = 70
        instructions = [
            ("Column", "Notes"),
            ("sample_id", "REQUIRED. Unique sample identifier (e.g. S001, SROCK-042)."),
            ("rock_classification", "Rock type (e.g. Basalt, Dunite, Serpentinite)."),
            ("state", "Province or state."),
            ("country", "Country of origin."),
            ("locality", "Locality or formation name."),
            ("latitude", "Decimal degrees (e.g. 49.5)."),
            ("longitude", "Decimal degrees (e.g. -125.0)."),
            ("description", "Free-text sample description."),
            ("characterized", "TRUE or FALSE (default FALSE)."),
            (
                "pxrf_reading_no",
                "Comma-separated pXRF reading numbers. Creates ExternalAnalysis type 'pXRF' per reading.",
            ),
            (
                "magnetic_susceptibility",
                "Magnetic susceptibility value (units: 1x10\u207b\u00b3 SI). Leave blank if not measured.",
            ),
            ("overwrite", "TRUE clears and rewrites all optional fields for existing samples (default FALSE)."),
        ]
        for r_idx, (col_name, note) in enumerate(instructions, start=1):
            name_cell = ws_inst.cell(row=r_idx, column=1, value=col_name)
            note_cell = ws_inst.cell(row=r_idx, column=2, value=note)
            if r_idx == 1:
                name_cell.font = Font(bold=True)
                note_cell.font = Font(bold=True)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
```

- [ ] **Step 2: Verify template endpoint returns 200 and a valid xlsx**

```bash
.venv/Scripts/pytest tests/api/test_bulk_uploads.py -k "template" -v 2>&1 | tail -20
```

Expected: existing template tests still PASS (the rock-inventory template test should return 200).

- [ ] **Step 3: Commit**

```bash
git add backend/api/routers/bulk_uploads.py
git commit -m "[#28] update rock-inventory template with new columns + INSTRUCTIONS

- add pxrf_reading_no, magnetic_susceptibility, overwrite to headers
- add INSTRUCTIONS sheet with per-column notes
- magnetic_susceptibility note: 'units 1x10^-3 SI, leave blank if not measured'
- Tests added: no
- Docs updated: no"
```

---

## Task 4: Write failing tests for pXRF reverse-match

**Files:**
- Modify: `tests/api/test_bulk_uploads.py`

- [ ] **Step 1: Append 3 failing tests to `test_bulk_uploads.py`**

Add these tests at the end of `tests/api/test_bulk_uploads.py`:

```python
# ---------------------------------------------------------------------------
# pXRF reverse-match tests (Issue #28)
# ---------------------------------------------------------------------------

def _make_pxrf_excel_bytes(reading_nos: list) -> bytes:
    """Minimal pXRF Excel file with 'Reading No' column for reverse-match extraction."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Reading No", "Fe", "Mg", "Ni", "Cu", "Si", "Co", "Mo", "Al", "Ca", "K", "Au"])
    for rno in reading_nos:
        ws.append([rno, 10.0, 1.0, 0.1, 0.1, 45.0, 0.1, 0.01, 8.0, 9.0, 1.0, 0.0])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_pxrf_upload_reevaluates_characterized_status(client, db_session):
    """After pXRF upload, a sample whose EA pxrf_reading_no matches the import becomes characterized."""
    from database import SampleInfo
    from database.models.analysis import ExternalAnalysis, PXRFReading

    # Sample is NOT characterized; has an EA pointing to reading_no "99"
    sample = SampleInfo(sample_id="REVTEST001", characterized=False)
    db_session.add(sample)
    db_session.flush()
    ea = ExternalAnalysis(
        sample_id="REVTEST001",
        analysis_type="pXRF",
        pxrf_reading_no="99",
    )
    db_session.add(ea)
    # The PXRFReading now "exists" (simulate what the upload would create)
    reading = PXRFReading(
        reading_no="99",
        fe=10.0, mg=1.0, ni=0.1, cu=0.1, si=45.0,
        co=0.1, mo=0.01, al=8.0, ca=9.0, k=1.0, au=0.0,
    )
    db_session.add(reading)
    db_session.flush()

    file_bytes = _make_pxrf_excel_bytes(["99"])
    fake_mod = MagicMock()
    fake_mod.PXRFUploadService.ingest_from_bytes.return_value = (1, 0, 0, [])

    with patch.dict(sys.modules, {
        "frontend": MagicMock(),
        "frontend.config": MagicMock(),
        "frontend.config.variable_config": MagicMock(),
        "backend.services.bulk_uploads.pxrf_data": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/pxrf",
            files={"file": ("test.xlsx", io.BytesIO(file_bytes), "application/vnd.ms-excel")},
        )

    assert resp.status_code == 200
    db_session.refresh(sample)
    assert sample.characterized is True


def test_pxrf_upload_creates_modifications_log_entry(client, db_session):
    """ModificationsLog entry is created when characterized status changes after pXRF upload."""
    from database import SampleInfo
    from database.models.analysis import ExternalAnalysis, PXRFReading
    from database.models.experiments import ModificationsLog

    sample = SampleInfo(sample_id="REVTEST002", characterized=False)
    db_session.add(sample)
    db_session.flush()
    ea = ExternalAnalysis(
        sample_id="REVTEST002",
        analysis_type="pXRF",
        pxrf_reading_no="88",
    )
    db_session.add(ea)
    reading = PXRFReading(
        reading_no="88",
        fe=5.0, mg=2.0, ni=0.2, cu=0.2, si=40.0,
        co=0.2, mo=0.02, al=7.0, ca=8.0, k=2.0, au=0.0,
    )
    db_session.add(reading)
    db_session.flush()

    file_bytes = _make_pxrf_excel_bytes(["88"])
    fake_mod = MagicMock()
    fake_mod.PXRFUploadService.ingest_from_bytes.return_value = (1, 0, 0, [])

    with patch.dict(sys.modules, {
        "frontend": MagicMock(),
        "frontend.config": MagicMock(),
        "frontend.config.variable_config": MagicMock(),
        "backend.services.bulk_uploads.pxrf_data": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/pxrf",
            files={"file": ("test.xlsx", io.BytesIO(file_bytes), "application/vnd.ms-excel")},
        )

    assert resp.status_code == 200
    log_entry = (
        db_session.query(ModificationsLog)
        .filter(ModificationsLog.sample_id == "REVTEST002")
        .first()
    )
    assert log_entry is not None
    assert log_entry.new_values.get("characterized") is True
    assert log_entry.old_values.get("characterized") is False


def test_pxrf_upload_message_includes_reevaluated_count(client, db_session):
    """Upload response message includes count of re-evaluated samples when > 0."""
    from database import SampleInfo
    from database.models.analysis import ExternalAnalysis, PXRFReading

    sample = SampleInfo(sample_id="REVTEST003", characterized=False)
    db_session.add(sample)
    db_session.flush()
    ea = ExternalAnalysis(
        sample_id="REVTEST003",
        analysis_type="pXRF",
        pxrf_reading_no="77",
    )
    db_session.add(ea)
    reading = PXRFReading(
        reading_no="77",
        fe=3.0, mg=3.0, ni=0.3, cu=0.3, si=35.0,
        co=0.3, mo=0.03, al=6.0, ca=7.0, k=3.0, au=0.0,
    )
    db_session.add(reading)
    db_session.flush()

    file_bytes = _make_pxrf_excel_bytes(["77"])
    fake_mod = MagicMock()
    fake_mod.PXRFUploadService.ingest_from_bytes.return_value = (1, 0, 0, [])

    with patch.dict(sys.modules, {
        "frontend": MagicMock(),
        "frontend.config": MagicMock(),
        "frontend.config.variable_config": MagicMock(),
        "backend.services.bulk_uploads.pxrf_data": fake_mod,
    }):
        resp = client.post(
            "/api/bulk-uploads/pxrf",
            files={"file": ("test.xlsx", io.BytesIO(file_bytes), "application/vnd.ms-excel")},
        )

    assert resp.status_code == 200
    body = resp.json()
    # Message must mention re-evaluation
    assert "re-evaluated" in body["message"].lower() or "1 sample" in body["message"]
```

- [ ] **Step 2: Run the failing tests to confirm they fail for the right reason**

```bash
.venv/Scripts/pytest tests/api/test_bulk_uploads.py -k "reevaluat or modifications_log or reevaluated_count" -v 2>&1 | tail -30
```

Expected: all 3 tests FAIL (reverse-match logic doesn't exist yet — characterized stays False, no log entry, message doesn't mention re-evaluation).

---

## Task 5: Implement pXRF reverse-match in upload_pxrf endpoint

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py` (the `upload_pxrf` function)

- [ ] **Step 1: Replace the `upload_pxrf` function body**

Find the current `upload_pxrf` function in `backend/api/routers/bulk_uploads.py`:

```python
@router.post("/pxrf", response_model=UploadResponse)
async def upload_pxrf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload a pXRF CSV/Excel file."""
    import sys  # noqa: PLC0415
    from types import ModuleType  # noqa: PLC0415
    if "frontend.config.variable_config" not in sys.modules:
        _stub = ModuleType("frontend.config.variable_config")
        sys.modules["frontend"] = sys.modules.get("frontend", ModuleType("frontend"))
        sys.modules["frontend.config"] = sys.modules.get("frontend.config", ModuleType("frontend.config"))
        sys.modules["frontend.config.variable_config"] = _stub
    _vc = sys.modules["frontend.config.variable_config"]
    if not hasattr(_vc, "PXRF_REQUIRED_COLUMNS"):
        _vc.PXRF_REQUIRED_COLUMNS = {"Reading No", "Fe", "Mg", "Si", "Ni", "Cu", "Mo", "Co", "Al", "Ca", "K", "Au"}
    from backend.services.bulk_uploads.pxrf_data import PXRFUploadService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        created, updated, skipped, errors = PXRFUploadService.ingest_from_bytes(db, file_bytes)
        db.commit()
    except Exception as exc:
        db.rollback()
        log.error("pxrf_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(created=created, updated=updated, skipped=skipped, errors=errors,
                          message=f"pXRF: {created} created, {updated} updated")
```

Replace the entire function with:

```python
@router.post("/pxrf", response_model=UploadResponse)
async def upload_pxrf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload a pXRF CSV/Excel file and re-evaluate characterized status for affected samples."""
    import sys  # noqa: PLC0415
    from types import ModuleType  # noqa: PLC0415
    if "frontend.config.variable_config" not in sys.modules:
        _stub = ModuleType("frontend.config.variable_config")
        sys.modules["frontend"] = sys.modules.get("frontend", ModuleType("frontend"))
        sys.modules["frontend.config"] = sys.modules.get("frontend.config", ModuleType("frontend.config"))
        sys.modules["frontend.config.variable_config"] = _stub
    _vc = sys.modules["frontend.config.variable_config"]
    if not hasattr(_vc, "PXRF_REQUIRED_COLUMNS"):
        _vc.PXRF_REQUIRED_COLUMNS = {"Reading No", "Fe", "Mg", "Si", "Ni", "Cu", "Mo", "Co", "Al", "Ca", "K", "Au"}
    from backend.services.bulk_uploads.pxrf_data import PXRFUploadService  # noqa: PLC0415
    file_bytes = await file.read()

    # Lightweight extraction of reading_no values for post-upload reverse-match.
    # Mirrors the normalization in PXRFUploadService._clean_dataframe.
    _imported_reading_nos: set[str] = set()
    try:
        _rn_df = __import__("pandas").read_excel(
            __import__("io").BytesIO(file_bytes), usecols=["Reading No"], engine="openpyxl"
        )
        for _v in _rn_df["Reading No"].dropna():
            _s = str(_v).strip()
            if _s:
                _s_clean = _s.replace(".", "", 1).replace("-", "", 1)
                if _s_clean.isdigit():
                    try:
                        _s = str(int(float(_s)))
                    except (ValueError, OverflowError):
                        pass
                _imported_reading_nos.add(_s)
    except Exception:
        pass  # extraction is best-effort; parser will report any real file errors

    try:
        created, updated, skipped, errors = PXRFUploadService.ingest_from_bytes(db, file_bytes)

        # Reverse-match: re-evaluate characterized for samples whose EA pxrf_reading_no
        # overlaps with the just-ingested readings.
        reevaluated_count = 0
        if _imported_reading_nos:
            from sqlalchemy import or_ as _or  # noqa: PLC0415
            from database.models.analysis import ExternalAnalysis as _EA  # noqa: PLC0415
            from database.models.samples import SampleInfo as _SI  # noqa: PLC0415
            from backend.services.samples import (  # noqa: PLC0415
                evaluate_characterized as _eval_char,
                log_sample_modification as _log_mod,
            )

            # Build LIKE conditions matching the comma-separated pxrf_reading_no field.
            # Pattern mirrors v_pxrf_characterization view in database/event_listeners.py.
            _like_conds = []
            for _rno in _imported_reading_nos:
                _like_conds.append(
                    _or(
                        _EA.pxrf_reading_no == _rno,
                        _EA.pxrf_reading_no.like(_rno + ",%"),
                        _EA.pxrf_reading_no.like("%," + _rno + ",%"),
                        _EA.pxrf_reading_no.like("%," + _rno),
                    )
                )

            affected_eas = db.query(_EA).filter(
                _EA.analysis_type == "pXRF",
                _EA.sample_id.isnot(None),
                _or(*_like_conds),
            ).all()

            for _sid in {ea.sample_id for ea in affected_eas if ea.sample_id}:
                _sample = db.query(_SI).filter(_SI.sample_id == _sid).first()
                if _sample is None:
                    continue
                _old = _sample.characterized
                _new = _eval_char(db, _sid)
                if _old != _new:
                    _sample.characterized = _new
                    _log_mod(
                        db,
                        sample_id=_sid,
                        modified_by=current_user.email,
                        modification_type="update",
                        modified_table="sample_info",
                        old_values={"characterized": _old},
                        new_values={
                            "characterized": _new,
                            "reason": "Triggered by pXRF bulk upload reverse-match",
                        },
                    )
                    reevaluated_count += 1

        db.commit()
    except Exception as exc:
        db.rollback()
        log.error("pxrf_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")

    base_msg = f"pXRF: {created} created, {updated} updated"
    message = (
        f"{base_msg}. Re-evaluated characterized status for {reevaluated_count} sample{'s' if reevaluated_count != 1 else ''}."
        if reevaluated_count > 0
        else base_msg
    )
    log.info("pxrf_upload", created=created, updated=updated, reevaluated=reevaluated_count, user=current_user.email)
    return UploadResponse(created=created, updated=updated, skipped=skipped, errors=errors,
                          message=message)
```

- [ ] **Step 2: Run the reverse-match tests to confirm they pass**

```bash
.venv/Scripts/pytest tests/api/test_bulk_uploads.py -k "reevaluat or modifications_log or reevaluated_count" -v 2>&1 | tail -20
```

Expected: all 3 tests PASS.

- [ ] **Step 3: Run the full bulk-uploads API test suite to confirm no regressions**

```bash
.venv/Scripts/pytest tests/api/test_bulk_uploads.py -v 2>&1 | tail -30
```

Expected: all existing tests PASS.

- [ ] **Step 4: Run the full test suite**

```bash
.venv/Scripts/pytest tests/ -v --tb=short 2>&1 | tail -40
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/bulk_uploads.py tests/api/test_bulk_uploads.py
git commit -m "[#28] add pXRF reverse-match to re-evaluate characterized status

- lightweight pandas parse extracts reading_no values from file bytes
- LIKE-based query matches comma-separated pxrf_reading_no in ExternalAnalysis
- calls evaluate_characterized for each affected sample
- logs to ModificationsLog when characterized status changes
- response message includes re-evaluated sample count
- Tests added: yes
- Docs updated: no"
```

---

## Self-Review

### Spec coverage check

| Acceptance criterion | Covered by task |
|---|---|
| Rock Inventory template includes magnetic_susceptibility column and INSTRUCTIONS note | Task 3 |
| Upload creates ExternalAnalysis type "Magnetic Susceptibility" with correct float | Task 1 test + Task 2 impl |
| Re-upload without overwrite skips existing mag susc records | Task 1 test + Task 2 impl |
| Re-upload with overwrite=TRUE updates existing EA | Task 1 test + Task 2 impl |
| Blank/non-numeric values do not error | Task 1 test + Task 2 impl |
| After pXRF upload, samples with matching EA pxrf_reading_no have characterized re-evaluated | Task 4 test + Task 5 impl |
| Previously-uncharacterized samples become characterized | Task 4 test + Task 5 impl |
| pXRF response message includes re-evaluated sample count | Task 4 test + Task 5 impl |
| ModificationsLog entries created for changed samples | Task 4 test + Task 5 impl |
| v_sample_characterization still surfaces mag susc correctly | No view changes needed — EA already has magnetic_susceptibility field; view reads it |
| Existing Rock Inventory behavior unaffected | Task 2 Step 3 regression run |

### Placeholder scan

No TBDs, TODOs, or "similar to" references. All code blocks contain complete, runnable code.

### Type consistency check

- `_mag_susc_col` (str | None) used consistently in both Tasks 2
- `_imported_reading_nos` (set[str]) produced in Task 5 before the try block, consumed inside it
- `evaluate_characterized(db, sample_id: str) -> bool` — matches `backend/services/samples.py:45`
- `log_sample_modification(db, *, sample_id, modified_by, modification_type, modified_table, old_values, new_values)` — matches `backend/services/samples.py:93`
- `PXRFUploadService.ingest_from_bytes(db, file_bytes) -> (int, int, int, list[str])` — matches `pxrf_data.py:94`
- `RockInventoryService.bulk_upsert_samples(db, file_bytes, []) -> (created, updated, images, skipped, errors, warnings)` — matches `rock_inventory.py:31`
