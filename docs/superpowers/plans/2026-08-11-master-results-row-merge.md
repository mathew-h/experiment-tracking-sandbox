# Master Results row merge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Master Results upload combine several Dashboard rows describing one vial-day (a GC row plus a later liquid/solid row) into one result, erroring only when two rows genuinely disagree about a measurement.

**Architecture:** One new pure function, `_merge_group`, collapses N sheet rows into a single merged cell dict before the existing upsert loop runs. Every Dashboard column is assigned to one of four merge classes (measurement / collection-date / provenance / directive) by module-level frozenset, so a new column forces an explicit choice. Identity resolution, `_resolve_h2`, and `ScalarResultsService` are untouched; the merge is a layer between Phase 1 (identity) and Phase 2 (write).

**Tech Stack:** Python 3, pandas (Excel parsing), SQLAlchemy ORM, pytest against PostgreSQL (`experiments_test`).

**Spec:** `docs/superpowers/specs/2026-08-11-master-results-row-merge-design.md`

## Global Constraints

- **Locked directory.** `backend/services/bulk_uploads/` is locked (CLAUDE.md §5). Sign-off for this change: Mat, 2026-08-11. Do not touch any other file in that package.
- **No schema change, no migration, no new dependency, no frontend change.** `database/models/` and `backend/services/scalar_results_service.py` are not modified.
- **Everything stays in `master_bulk_upload.py`.** Do NOT extract the merge into a new module. `_merge_group` needs `_parse_float`, `_parse_measurement_float`, `_parse_date` and `_parse_bool`; moving them churns a locked file, and duplicating them would let `_parse_measurement_float`'s "0 means blank" rule drift between two definitions. `_merge_group` is nonetheless written as a **pure function over Mappings** so it is unit-testable with plain dicts and no database.
- **Canonical header name:** `Sample Collection Date`. Accepted aliases (lowercased keys): `sample collection date`, `sample date`, `liquid/solid sample date`, `hpht + liquid/solid date sampled`.
- **Grouping key:** `(normalize_id(exp_id), normalize_timepoint(time))` — exact timepoint, **no tolerance window** (spec D-g).
- **Float conflict test:** exact equality after the field's own parse helper. No tolerance (spec D-f).
- **Warnings are the only channel the UI renders.** `BulkUploadRow.tsx:204-248` draws `errors` and `warnings` as string lists; `feedbacks` is typed `Record<string, unknown>[]` and rendered nowhere. Anything a researcher must see goes in `warnings`.
- **Row-list threshold:** name individual rows only when there are ≤10, matching the existing supersede (`:699`), GC-date (`:733`) and Duration-disagreement (`:766`) warnings.
- **Errors carry a row number and sort by it.** Append to `row_errors` as `(anchor_row, message)`; the existing sort at `:783` produces sheet order. Never append directly to `out.errors` for a row- or group-level message.
- **Commit format** (CLAUDE.md §8, inline mode): `[fix|feat|chore|refactor] <imperative, <50 chars, no trailing period>` then a blank line, detail bullets, `- Tests added: yes/no`, `- Docs updated: yes/no`. Multi-line messages: write the message to a scratch file and use `git commit -F <file>` — PowerShell here-strings break on embedded double quotes.
- **Branch:** `feat/master-results-row-merge`, already created off `develop`. Never commit to `develop` or `main` directly.
- **Test command prefix:** `.venv/Scripts/python.exe -m pytest` from the repo root. Bare `pytest` is not on PATH.
- **Never run two pytest processes at once** — the test DB is shared and an interrupted run leaves a schema `create_all` cannot repair.
- **Do not start, stop or restart uvicorn.** Assume it is running on port 8000.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `backend/services/bulk_uploads/master_bulk_upload.py` | Dashboard parsing, field-class constants, `_merge_group`, Phase 1.5 wiring, all warnings | Modify |
| `tests/services/bulk_uploads/test_master_bulk_upload.py` | Parser tests: new date-column cases, pure `_merge_group` unit tests, rewritten duplicate-guard tests | Modify |
| `docs/LOCKED_COMPONENTS.md` | Amend footnote ²; add footnote ⁴ | Modify |
| `MODELS.md` | `ScalarResults` "One row per vial" paragraph | Modify |
| `docs/working/issue-log.md` | Completion entry; separate `_t1`/`-t1` defect entry | Modify |

`master_bulk_upload.py` grows from 799 to roughly 1,100 lines. That is deliberate — see the Global Constraints note on why the merge is not extracted.

---

## Task 1: Restore collection-date ingestion (P0)

Independent of the merge and shippable alone. `master_bulk_upload.py:595` reads `row.get("Sample Date")`, a column the sheet no longer has, so `measurement_date` is silently never written on 275 dated rows — and on an `OVERWRITE=TRUE` row it is *cleared*, because `measurement_date` is a key in the `result_data` literal and therefore in the `sheet_fields` frozenset that `create_scalar_result_ex` clears from.

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (`_HEADER_ALIASES` at `:58`; new constants after `:48`; `sample_date = ...` at `:595`; new warning near `:490`)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: module constants `_COLLECTION_DATE: str` and `_COLLECTION_DATE_SPELLINGS: tuple[str, ...]`, used by Task 2's field classes and Task 3's warning. Test helper signature change: `_master_excel_v3(rows, date_header: str = "Sample Collection Date")` and `_v3_row(..., collection_date=None, cond=None, solvol=None, nmr_date=None, icp_date=None, xrd_date=None, modification=None)`.

- [ ] **Step 1: Extend the test helpers so a date can be put in a row**

In `tests/services/bulk_uploads/test_master_bulk_upload.py`, replace `_V3_HEADERS`, `_v3_row` and `_master_excel_v3` (currently at `:750-788`) with:

```python
_V3_HEADERS = [
    "Experiment ID", "Description", "Sample Collection Date", "Duration (Days)",
    "NH4 (mM)",
    "FL H2 (ppm)", "FL Gas Volume (mL)", "FL Gas Pressure (psi)",
    "Sample pH", "Sample Conductivity (mS/cm)", "Modification", "NMR Run Date",
    "Sampled Solution Volume (mL)", "ICP Run Date", "GC Run Date", "XRD Run Date",
    "OVERWRITE",
    "DI H2 (ppm)", "DI gas volume (mL)", "DI gas pressure (psi)",
]


def _v3_row(
    experiment_id: str,
    duration: float | None = 7.0,
    *,
    description: str = "Day 7",
    nh4: float | None = None,
    fl_h2: float | None = None,
    fl_vol: float | None = None,
    fl_psi: float | None = None,
    ph: float | None = 7.0,
    cond: float | None = None,
    solvol: float | None = None,
    overwrite=None,
    di_h2: float | None = None,
    di_vol: float | None = None,
    di_psi: float | None = None,
    collection_date: str | None = None,
    nmr_date: str | None = None,
    icp_date: str | None = None,
    gc_date: str | None = None,
    xrd_date: str | None = None,
    modification: str | None = None,
) -> list:
    """Build one Dashboard row in _V3_HEADERS order.

    `ph` defaults to 7.0 because most existing tests rely on it. A row meant to
    stand for a gas-only sampling MUST pass ph=None, or the merge will treat it
    as carrying a liquid measurement.
    """
    return [
        experiment_id, description, collection_date, duration, nh4,
        fl_h2, fl_vol, fl_psi,
        ph, cond, modification, nmr_date,
        solvol, icp_date, gc_date, xrd_date,
        overwrite,
        di_h2, di_vol, di_psi,
    ]


def _master_excel_v3(
    rows: list[list], date_header: str = "Sample Collection Date",
) -> bytes:
    """Build a v3 Dashboard sheet.

    `date_header` lets a test exercise a superseded spelling of the collection
    date column without duplicating the whole header list.
    """
    headers = list(_V3_HEADERS)
    headers[headers.index("Sample Collection Date")] = date_header
    return make_excel_multisheet({"Dashboard": (headers, rows)})
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
# ---------------------------------------------------------------------------
# Sample Collection Date (P0 — the 2026-08-11 renames broke ingestion)
# ---------------------------------------------------------------------------

import datetime as _dt

from database import ScalarResults


def _scalar_for(db: Session, experiment_id: str) -> ScalarResults:
    """The single ScalarResults row belonging to `experiment_id`."""
    return (
        db.query(ScalarResults)
        .join(ExperimentalResults,
              ExperimentalResults.id == ScalarResults.result_id)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == experiment_id)
        .one()
    )


@pytest.mark.parametrize("date_header", [
    "Sample Collection Date",            # canonical
    "Sample collection date",            # casing variant
    "HPHT + Liquid/Solid Date Sampled",  # 2026-08-11, superseded
    "Liquid/Solid Sample Date",          # 2026-08-11, superseded
    "Sample Date",                       # archived workbooks
])
def test_collection_date_spellings_populate_measurement_date(
    db_session: Session, date_header: str,
):
    """Every accepted spelling of the collection-date column is ingested.

    The column was renamed three times on 2026-08-11 while the parser still read
    a literal "Sample Date", so measurement_date was silently dropped on all 275
    dated rows of the team's workbook. Each spelling gets a case so a future
    rename cannot quietly un-fix this.
    """
    _seed_experiment(db_session, "HPHT_CDATE01", 8901)

    xlsx = _master_excel_v3(
        [_v3_row("HPHT_CDATE01", 7.0, collection_date="2026-08-05", nh4=1.0)],
        date_header=date_header,
    )
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"unexpected errors: {result.errors}"
    scalar = _scalar_for(db_session, "HPHT_CDATE01")
    assert scalar.measurement_date == _dt.datetime(2026, 8, 5), (
        f"'{date_header}' was not ingested as measurement_date"
    )


def test_no_recognized_collection_date_column_warns(db_session: Session):
    """A sheet with no date column says so instead of silently ingesting none.

    This is the durable guard against a fourth rename. Everything else on the
    sheet must still upload — a missing date column is a warning, not an error.
    """
    _seed_experiment(db_session, "HPHT_CDATE02", 8902)

    xlsx = _master_excel_v3(
        [_v3_row("HPHT_CDATE02", 7.0, nh4=1.0)],
        date_header="Totally Renamed Date",
    )
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"a missing date column is not an error: {result.errors}"
    assert result.created == 1, "the rest of the row must still upload"
    assert any("collection date" in w.lower() for w in result.warnings), (
        f"expected a missing-date-column warning, got: {result.warnings}"
    )


def test_two_date_spellings_do_not_collide(db_session: Session):
    """A hand-merged workbook with two date spellings keeps one usable column.

    _normalize_headers rule 1: an aliased column never takes a canonical name a
    literal column already holds. Without that, both columns would be renamed to
    the same label, row.get() would return a Series, and _parse_date's
    `except Exception` would swallow the value — the exact silent loss issue #111
    exists to prevent.
    """
    _seed_experiment(db_session, "HPHT_CDATE03", 8903)

    headers = list(_V3_HEADERS) + ["Sample Date"]
    rows = [_v3_row("HPHT_CDATE03", 7.0, collection_date="2026-08-05", nh4=1.0)
            + ["2026-01-01"]]
    xlsx = make_excel_multisheet({"Dashboard": (headers, rows)})

    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"unexpected errors: {result.errors}"
    scalar = _scalar_for(db_session, "HPHT_CDATE03")
    assert scalar.measurement_date == _dt.datetime(2026, 8, 5), (
        "the canonical column must win over the aliased legacy one"
    )


def test_overwrite_row_does_not_clear_the_date_it_supplied(db_session: Session):
    """An OVERWRITE row that carries a date stores it rather than nulling it.

    measurement_date is a key in the result_data literal, so it is in the
    _sheet_fields frozenset that create_scalar_result_ex's overwrite branch
    clears. While the parser read a header that no longer existed, an
    OVERWRITE=TRUE row actively destroyed a stored date. Six rows in the team's
    workbook carry OVERWRITE=TRUE.
    """
    _seed_experiment(db_session, "HPHT_CDATE04", 8904)

    first = _master_excel_v3(
        [_v3_row("HPHT_CDATE04", 7.0, collection_date="2026-07-01", nh4=1.0)]
    )
    MasterBulkUploadService.from_bytes_ex(db_session, first)

    second = _master_excel_v3(
        [_v3_row("HPHT_CDATE04", 7.0, collection_date="2026-08-05", nh4=2.0,
                 overwrite="TRUE")]
    )
    result = MasterBulkUploadService.from_bytes_ex(db_session, second)

    assert result.errors == [], f"unexpected errors: {result.errors}"
    scalar = _scalar_for(db_session, "HPHT_CDATE04")
    assert scalar.measurement_date == _dt.datetime(2026, 8, 5), (
        "the overwrite row's own date must be stored, not cleared"
    )
```

- [ ] **Step 3: Run the tests to verify they fail**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "collection_date or date_spellings or two_date_spellings" -v
```
Expected: FAIL. The parametrized spelling test fails on all five cases with `measurement_date == None` (the code reads a `"Sample Date"` column that `_normalize_headers` no longer produces for four of them, and for the fifth the header list no longer contains it). `test_no_recognized_collection_date_column_warns` fails with no matching warning.

- [ ] **Step 4: Add the constants and aliases**

In `backend/services/bulk_uploads/master_bulk_upload.py`, after `_DASHBOARD_SHEET = "Dashboard"` (`:48`) add:

```python
# The sample collection date column. Renamed three times on 2026-08-11
# ('Sample Date' -> 'Liquid/Solid Sample Date' -> 'HPHT + Liquid/Solid Date
# Sampled' -> this), and each rename silently dropped every date on the sheet
# because the read below used a literal. The name is a constant and every
# spelling is aliased, so a fourth rename is a one-line change here; the
# "no recognized collection date column" warning further down makes it visible
# rather than silent.
_COLLECTION_DATE = "Sample Collection Date"

# Every spelling the parser answers to, for the warning's message.
_COLLECTION_DATE_SPELLINGS = (
    "Sample Collection Date",
    "Sample Date",
    "Liquid/Solid Sample Date",
    "HPHT + Liquid/Solid Date Sampled",
)
```

Then add to `_HEADER_ALIASES` (`:58-75`), in the "Casing-only normalisations" block beside `"overwrite": "Overwrite"`:

```python
    # Sample collection date — canonical spelling included so a casing variant
    # ('Sample collection date') still normalises, same as 'overwrite' above.
    "sample collection date": _COLLECTION_DATE,
    "sample date": _COLLECTION_DATE,
    "liquid/solid sample date": _COLLECTION_DATE,
    "hpht + liquid/solid date sampled": _COLLECTION_DATE,
```

- [ ] **Step 5: Read the canonical column and add the missing-column warning**

Change `:595` from:
```python
        sample_date = _parse_date(row.get("Sample Date"))
```
to:
```python
        sample_date = _parse_date(row.get(_COLLECTION_DATE))
```

Then, immediately after the `if not _RECOGNIZED_H2_COLUMNS & set(df.columns):` warning block (`:490-494`), add:

```python
    # A renamed date column fails silently in both directions: on the normal
    # path the None-stripping comprehension drops measurement_date, and on an
    # OVERWRITE row it is CLEARED, because measurement_date is one of the
    # declared _sheet_fields. Three renames on 2026-08-11 each dropped every
    # date on the sheet with no message at all. Gated on the column being
    # absent entirely, so it never fires on a normal upload.
    if _COLLECTION_DATE not in df.columns:
        warnings.append(
            f"Sheet '{sheet_name}' has no recognized sample collection date "
            "column, so no measurement date was ingested. Accepted names: "
            + ", ".join(f"'{name}'" for name in _COLLECTION_DATE_SPELLINGS)
            + ". Everything else on the sheet was uploaded normally."
        )
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "collection_date or date_spellings or two_date_spellings" -v
```
Expected: PASS, 8 tests (5 parametrized + 3).

- [ ] **Step 7: Run the whole parser suite for regressions**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q
```
Expected: all PASS. `_master_excel` (`:44`) still uses the legacy `"Sample Date"` header and now aliases onto the canonical name, so those tests keep working — that is the archived-workbook path proving itself.

- [ ] **Step 8: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -F <scratch-file>
```
Message:
```
[fix] Restore sample collection date ingestion

The Dashboard date column was renamed three times on 2026-08-11 while the
parser read a literal "Sample Date", so measurement_date was dropped on
all 275 dated rows -- and cleared outright on OVERWRITE rows.

- Alias every spelling onto a _COLLECTION_DATE constant
- Warn when no recognized date column is present
- Tests added: yes
- Docs updated: no
```

---

## Task 2: Field classes and `_merge_group`

Pure function, no database, no Phase 2 changes yet. Nothing calls it after this task; Task 3 wires it in. This split exists so the merge rules can be reviewed and tested against plain dicts, independently of the upload pipeline.

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (new constants after `_WIDE_DI_COLUMNS` at `:95`; new dataclasses and `_merge_group` after `_resolve_row_identity` ends at `:398`)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Consumes: `_COLLECTION_DATE` from Task 1; the existing `_parse_float`, `_parse_measurement_float`, `_parse_date`, `_parse_bool`.
- Produces, for Task 3 and Task 4:
  - `_MEASUREMENT_COLUMNS: tuple[str, ...]`, `_ZERO_BLANK_COLUMNS: frozenset[str]`, `_LIQUID_SOLID_COLUMNS: tuple[str, ...]`, `_RUN_DATE_COLUMNS: tuple[str, ...]`, `_JOINED_TEXT_COLUMNS: tuple[str, ...]`
  - `@dataclass MergeNotes` with fields `run_date_disagreements: List[str]`, `overwrite_mixed: bool`, `spellings: List[str]`, `fallback_date_disagreement: bool`
  - `@dataclass MergedGroup` with fields `cells: Dict[str, Any]`, `overwrite: bool`
  - `_merge_group(members: List[Tuple[int, str, Any]]) -> Tuple[Optional[MergedGroup], List[str], MergeNotes]` — `members` is `(row_num, experiment_id, row_mapping)` in sheet order; returns `(merged, conflicts, notes)` where `merged is None` exactly when `conflicts` is non-empty. Each conflict string is one field clause, e.g. `Sample pH: 5.22 (row 2) vs 7.27 (row 3)`; the caller composes the sentence around it.

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
# ---------------------------------------------------------------------------
# _merge_group — pure merge rules, no database
# ---------------------------------------------------------------------------

from backend.services.bulk_uploads.master_bulk_upload import _merge_group


def _cells(**overrides) -> dict:
    """A Dashboard row as a plain dict, every column blank unless overridden."""
    row = {header: None for header in _V3_HEADERS}
    row["Overwrite"] = None   # canonical spelling after _normalize_headers
    row.pop("OVERWRITE", None)
    row.update(overrides)
    return row


def test_merge_group_combines_complementary_gas_and_liquid():
    """The core case: a GC row and a later liquid row become one cell view."""
    gas = _cells(**{"DI H2 (ppm)": 87.12, "DI gas volume (mL)": 30.0,
                    "DI gas pressure (psi)": 14.7,
                    "Sample Collection Date": "2026-07-22",
                    "GC Run Date": "2026-07-22"})
    liquid = _cells(**{"Sample pH": 7.24, "Sample Conductivity (mS/cm)": 1.541,
                       "Sample Collection Date": "2026-08-05",
                       "Description": "Highest H2 liquid, solids"})

    merged, conflicts, notes = _merge_group([
        (7, "SERUM_M01a-t1", gas), (188, "SERUM_M01a-t1", liquid),
    ])

    assert conflicts == [], f"complementary rows must not conflict: {conflicts}"
    assert merged is not None
    assert merged.cells["DI H2 (ppm)"] == 87.12
    assert merged.cells["DI gas volume (mL)"] == 30.0
    assert merged.cells["Sample pH"] == 7.24
    assert merged.cells["Sample Conductivity (mS/cm)"] == 1.541
    assert merged.cells["Description"] == "Highest H2 liquid, solids"


def test_merge_group_conflicting_measurement_yields_no_merged_row():
    """Two different H2 readings for one vial-day is a conflict, not a merge."""
    a = _cells(**{"DI H2 (ppm)": 33.89})
    b = _cells(**{"DI H2 (ppm)": 39.01})

    merged, conflicts, notes = _merge_group([
        (14, "SERUM_M02-t3", a), (57, "SERUM_M02-t3", b),
    ])

    assert merged is None, "a conflicted vial-day writes nothing"
    assert len(conflicts) == 1, f"one clause for the one bad field: {conflicts}"
    assert "DI H2 (ppm)" in conflicts[0]
    assert "33.89" in conflicts[0] and "39.01" in conflicts[0]
    assert "row 14" in conflicts[0] and "row 57" in conflicts[0]


def test_merge_group_equal_measurements_are_not_a_conflict():
    """Two rows repeating the same value agree. HPHT_229 does exactly this."""
    a = _cells(**{"FL H2 (ppm)": 0.0, "Sample pH": 7.56})
    b = _cells(**{"FL H2 (ppm)": 0.0})

    merged, conflicts, notes = _merge_group([
        (36, "HPHT_M03", a), (43, "HPHT_M03", b),
    ])

    assert conflicts == []
    assert merged.cells["FL H2 (ppm)"] == 0.0, "0 is a real reading, not a blank"
    assert merged.cells["Sample pH"] == 7.56


def test_merge_group_zero_ph_counts_as_blank_not_a_conflict():
    """The template writes 0 for a blank pH cell, so 0 must not fight a real value.

    _parse_measurement_float treats 0 as None for pH and conductivity. The merge
    has to use the same helper or a template-blank 0 would look like a
    disagreement with the liquid row's real reading.
    """
    gas = _cells(**{"DI H2 (ppm)": 50.0, "Sample pH": 0.0,
                    "Sample Conductivity (mS/cm)": 0.0})
    liquid = _cells(**{"Sample pH": 7.24, "Sample Conductivity (mS/cm)": 1.541})

    merged, conflicts, notes = _merge_group([
        (7, "SERUM_M04a-t1", gas), (188, "SERUM_M04a-t1", liquid),
    ])

    assert conflicts == [], f"a template-blank 0 is not a conflict: {conflicts}"
    assert merged.cells["Sample pH"] == 7.24


def test_merge_group_prefers_the_date_from_a_liquid_bearing_row():
    """The liquid row's collection date outranks the gas row's."""
    gas = _cells(**{"DI H2 (ppm)": 87.12,
                    "Sample Collection Date": "2026-07-22"})
    liquid = _cells(**{"Sample pH": 7.24,
                       "Sample Collection Date": "2026-08-05"})

    merged, conflicts, notes = _merge_group([
        (7, "SERUM_M05a-t1", gas), (188, "SERUM_M05a-t1", liquid),
    ])

    assert conflicts == []
    assert merged.cells[_COLLECTION_DATE] == "2026-08-05"


def test_merge_group_falls_back_to_a_gas_only_date():
    """With no liquid row, the date on record is still used, not discarded.

    185 rows in the team's workbook carry a date with no liquid measurement —
    an HPHT vessel's own sampling date. Excluding them would destroy real data.
    """
    a = _cells(**{"DI H2 (ppm)": 33.89, "Sample Collection Date": "2026-07-24"})
    b = _cells(**{"FL Gas Volume (mL)": 30.0,
                  "Sample Collection Date": "2026-07-24"})

    merged, conflicts, notes = _merge_group([
        (14, "SERUM_M06-t3", a), (57, "SERUM_M06-t3", b),
    ])

    assert conflicts == []
    assert merged.cells[_COLLECTION_DATE] == "2026-07-24"
    assert notes.fallback_date_disagreement is False


def test_merge_group_disagreeing_fallback_dates_warn_rather_than_error():
    """No liquid row and two different dates: first wins, reported not rejected."""
    a = _cells(**{"DI H2 (ppm)": 50.0, "Sample Collection Date": "2026-08-06"})
    b = _cells(**{"FL Gas Volume (mL)": 30.0,
                  "Sample Collection Date": "2026-08-10"})

    merged, conflicts, notes = _merge_group([
        (222, "GC_M07", a), (272, "GC_M07", b),
    ])

    assert conflicts == [], "a fallback date is provenance, not a measurement"
    assert merged.cells[_COLLECTION_DATE] == "2026-08-06", "first in sheet order"
    assert notes.fallback_date_disagreement is True


def test_merge_group_disagreeing_preferred_dates_are_a_conflict():
    """Two liquid-bearing rows with different dates cannot both be right."""
    a = _cells(**{"Sample pH": 5.22, "Sample Collection Date": "2026-07-22"})
    b = _cells(**{"Sample Conductivity (mS/cm)": 1.705,
                  "Sample Collection Date": "2026-08-05"})

    merged, conflicts, notes = _merge_group([
        (2, "SERUM_M08a-t1", a), (185, "SERUM_M08a-t1", b),
    ])

    assert merged is None
    assert any(_COLLECTION_DATE in clause for clause in conflicts), conflicts


def test_merge_group_joins_descriptions_and_modifications():
    """Distinct text is joined with '; ' in sheet order; blanks contribute nothing."""
    a = _cells(**{"DI H2 (ppm)": 50.0, "Description": "Gas, liquid",
                  "Modification": "+200ul 1M HCl"})
    b = _cells(**{"Sample pH": 7.24,
                  "Description": "Highest H2 liquid, solids"})

    merged, conflicts, notes = _merge_group([
        (36, "HPHT_M09", a), (43, "HPHT_M09", b),
    ])

    assert conflicts == []
    assert merged.cells["Description"] == "Gas, liquid; Highest H2 liquid, solids"
    assert merged.cells["Modification"] == "+200ul 1M HCl"


def test_merge_group_repeated_description_is_not_duplicated():
    """Identical text on both rows appears once."""
    a = _cells(**{"DI H2 (ppm)": 50.0, "Description": "same"})
    b = _cells(**{"Sample pH": 7.24, "Description": "same"})

    merged, _conflicts, _notes = _merge_group([
        (2, "HPHT_M10", a), (3, "HPHT_M10", b),
    ])

    assert merged.cells["Description"] == "same"


def test_merge_group_run_date_disagreement_is_a_note_not_a_conflict():
    """Run dates are provenance: first non-null wins and the clash is reported."""
    a = _cells(**{"DI H2 (ppm)": 50.0, "GC Run Date": "2026-07-22"})
    b = _cells(**{"Sample pH": 7.24, "GC Run Date": "2026-07-28"})

    merged, conflicts, notes = _merge_group([
        (2, "HPHT_M11", a), (3, "HPHT_M11", b),
    ])

    assert conflicts == []
    assert merged.cells["GC Run Date"] == "2026-07-22", "first in sheet order"
    assert notes.run_date_disagreements == ["GC Run Date"]


def test_merge_group_overwrite_requires_every_row():
    """Mixed OVERWRITE degrades to a non-destructive merge and is reported."""
    a = _cells(**{"DI H2 (ppm)": 404.19, "Overwrite": "TRUE"})
    b = _cells(**{"Sample pH": 9.03, "Overwrite": "FALSE"})

    merged, conflicts, notes = _merge_group([
        (154, "SERUM_M12c-t5", a), (204, "SERUM_M12c-t5", b),
    ])

    assert conflicts == []
    assert merged.overwrite is False, "a destructive directive needs unanimity"
    assert notes.overwrite_mixed is True


def test_merge_group_unanimous_overwrite_is_honoured():
    a = _cells(**{"DI H2 (ppm)": 404.19, "Overwrite": "TRUE"})
    b = _cells(**{"Sample pH": 9.03, "Overwrite": "TRUE"})

    merged, _conflicts, notes = _merge_group([
        (154, "SERUM_M13c-t5", a), (204, "SERUM_M13c-t5", b),
    ])

    assert merged.overwrite is True
    assert notes.overwrite_mixed is False


def test_merge_group_records_distinct_spellings():
    """Two spellings of one ID merge; the note names them so the typo is fixable."""
    a = _cells(**{"DI H2 (ppm)": 50.0})
    b = _cells(**{"Sample pH": 7.24})

    merged, conflicts, notes = _merge_group([
        (29, "SERUM_cation_001c-t5", a), (194, "SERUM_Cation_001c-t5", b),
    ])

    assert conflicts == []
    assert notes.spellings == ["SERUM_cation_001c-t5", "SERUM_Cation_001c-t5"]


def test_merge_group_single_spelling_records_one_entry():
    a = _cells(**{"DI H2 (ppm)": 50.0})
    b = _cells(**{"Sample pH": 7.24})

    _merged, _conflicts, notes = _merge_group([
        (2, "HPHT_M14", a), (3, "HPHT_M14", b),
    ])

    assert notes.spellings == ["HPHT_M14"], "no variant to report"


def test_merge_group_merges_three_rows():
    """Nothing in the rules assumes a pair."""
    a = _cells(**{"DI H2 (ppm)": 50.0})
    b = _cells(**{"Sample pH": 7.24})
    c = _cells(**{"NH4 (mM)": 3.5, "Sampled Solution Volume (mL)": 2.0})

    merged, conflicts, _notes = _merge_group([
        (2, "HPHT_M15", a), (3, "HPHT_M15", b), (4, "HPHT_M15", c),
    ])

    assert conflicts == []
    assert merged.cells["DI H2 (ppm)"] == 50.0
    assert merged.cells["Sample pH"] == 7.24
    assert merged.cells["NH4 (mM)"] == 3.5
    assert merged.cells["Sampled Solution Volume (mL)"] == 2.0


def test_merge_group_reports_every_conflicting_field():
    """A group can disagree on more than one field; all are named."""
    a = _cells(**{"Sample pH": 5.22, "Sample Conductivity (mS/cm)": 1.286})
    b = _cells(**{"Sample pH": 7.27, "Sample Conductivity (mS/cm)": 1.705})

    merged, conflicts, _notes = _merge_group([
        (2, "SERUM_M16a-t1", a), (185, "SERUM_M16a-t1", b),
    ])

    assert merged is None
    assert len(conflicts) == 2, f"one clause per bad field: {conflicts}"
    assert any("Sample pH" in c for c in conflicts)
    assert any("Sample Conductivity (mS/cm)" in c for c in conflicts)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k merge_group -v
```
Expected: collection error — `ImportError: cannot import name '_merge_group'`.

- [ ] **Step 3: Add the field-class constants**

In `master_bulk_upload.py`, after `_WIDE_DI_COLUMNS` (`:95`), add:

```python
# ---------------------------------------------------------------------------
# Merge field classes (spec §3.2)
#
# Several Dashboard rows can describe one vial-day: gas is drawn and run on one
# date, the liquid/solid fraction is collected later, and each gets its own row.
# Merging them needs every column assigned to exactly one class, so adding a
# Dashboard column forces a choice instead of defaulting into one. Classified on
# the RAW CELL, before _resolve_h2, so Full-Loop precedence and the #114
# geometry rule run once over the merged view and cannot drift.
# ---------------------------------------------------------------------------

# Two rows holding different values here cannot both be right -> conflict.
_MEASUREMENT_COLUMNS = (
    "NH4 (mM)",
    "FL H2 (ppm)", "FL Gas Volume (mL)", "FL Gas Pressure (psi)",
    "DI H2 (ppm)", "DI gas volume (mL)", "DI gas pressure (psi)",
    "Sample pH", "Sample Conductivity (mS/cm)",
    "Sampled Solution Volume (mL)",
)

# Columns where the Excel template writes 0 for a blank cell, so 0 must be read
# as absent -- the same rule _parse_measurement_float applies on a single row.
# Using the wrong helper here would make a template-blank 0 look like a
# disagreement with the liquid row's real reading.
_ZERO_BLANK_COLUMNS = frozenset({"Sample pH", "Sample Conductivity (mS/cm)"})

# A row carrying any of these analysed the liquid/solid fraction, so its
# collection date is the authoritative one for the merged vial-day.
_LIQUID_SOLID_COLUMNS = (
    "NH4 (mM)", "Sample pH", "Sample Conductivity (mS/cm)",
    "Sampled Solution Volume (mL)",
)

# Provenance: first non-null in sheet order wins, a clash is a warning. These
# are instrument run dates, duplicated identically across both rows of every
# pair in the team's workbook.
_RUN_DATE_COLUMNS = ("NMR Run Date", "ICP Run Date", "GC Run Date", "XRD Run Date")

# Free text: distinct values joined, nothing discarded, so no warning needed.
_JOINED_TEXT_COLUMNS = ("Description", "Modification")
```

- [ ] **Step 4: Add the dataclasses and `_merge_group`**

In `master_bulk_upload.py`, after `_resolve_row_identity` ends (`:398`), add:

```python
@dataclass
class MergeNotes:
    """Non-fatal observations about one merged group, for file-level warnings.

    Kept separate from `conflicts` because these never stop a write: they are
    things the researcher should know about a row that DID land.
    """

    run_date_disagreements: List[str] = field(default_factory=list)
    overwrite_mixed: bool = False
    spellings: List[str] = field(default_factory=list)
    fallback_date_disagreement: bool = False


@dataclass
class MergedGroup:
    """One vial-day's cells after collapsing N sheet rows.

    `cells` is a plain dict, not a pandas Series: a dict cannot carry duplicate
    labels, so the Series-instead-of-scalar hazard `_normalize_headers` exists to
    prevent cannot be reintroduced downstream. Phase 2 reads it with .get(),
    exactly as it reads a single sheet row.
    """

    cells: Dict[str, Any]
    overwrite: bool


def _cell_parser(column: str):
    """The parse helper that owns `column`'s blank/value distinction."""
    if column in _ZERO_BLANK_COLUMNS:
        return _parse_measurement_float
    return _parse_float


def _format_value(value: Any) -> str:
    """Render a parsed measurement for an error message."""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _merge_group(
    members: List[Tuple[int, str, Any]],
) -> Tuple[Optional[MergedGroup], List[str], MergeNotes]:
    """Collapse N Dashboard rows for one vial-day into one merged cell view.

    `members` is [(row_num, experiment_id, row_mapping)] in sheet order; the
    mapping is anything supporting .get() (a pandas row or a dict).

    Returns (merged, conflicts, notes). `merged` is None exactly when
    `conflicts` is non-empty -- a vial-day whose rows disagree writes nothing
    (spec D-a), because a partial merge would leave a stored row whose state
    depends on which fields happened to clash.

    Each conflict string is ONE field clause; the caller composes the sentence
    around it so the row list and experiment ID are formatted in one place.

    Pure: no database, no session, no I/O.
    """
    notes = MergeNotes()
    conflicts: List[str] = []
    cells: Dict[str, Any] = {}

    # dict.fromkeys keeps sheet order while dropping repeats. One entry means
    # every row spelled the ID the same way and there is nothing to report.
    notes.spellings = list(dict.fromkeys(exp_id for _, exp_id, _ in members))

    # --- Measurement class: one value, or a conflict ---------------------
    for column in _MEASUREMENT_COLUMNS:
        parse = _cell_parser(column)
        seen: List[Tuple[int, Any]] = []
        for row_num, _exp_id, row in members:
            value = parse(row.get(column))
            if value is not None:
                seen.append((row_num, value))
        if not seen:
            continue
        distinct = {value for _, value in seen}
        if len(distinct) > 1:
            conflicts.append(
                f"{column}: "
                + " vs ".join(
                    f"{_format_value(value)} (row {row_num})"
                    for row_num, value in seen
                )
            )
            continue
        # Store the RAW cell, not the parsed value: Phase 2 re-parses with the
        # same helpers, and handing it a parsed float would double-convert.
        for row_num, _exp_id, row in members:
            if parse(row.get(column)) is not None:
                cells[column] = row.get(column)
                break

    # --- Collection date: prefer a liquid/solid-bearing row --------------
    # The column carries the vessel's own sampling date on a gas-only row (185
    # such rows in the team's workbook, 143 of them standalone), so a gas date
    # is outranked, never discarded.
    def _has_liquid(row: Any) -> bool:
        return any(
            _cell_parser(column)(row.get(column)) is not None
            for column in _LIQUID_SOLID_COLUMNS
        )

    preferred = [
        (row_num, row.get(_COLLECTION_DATE))
        for row_num, _exp_id, row in members
        if _parse_date(row.get(_COLLECTION_DATE)) is not None and _has_liquid(row)
    ]
    fallback = [
        (row_num, row.get(_COLLECTION_DATE))
        for row_num, _exp_id, row in members
        if _parse_date(row.get(_COLLECTION_DATE)) is not None
    ]
    candidates = preferred or fallback
    if candidates:
        distinct_dates = {_parse_date(raw) for _, raw in candidates}
        if len(distinct_dates) > 1:
            if preferred:
                # Two rows both analysed liquid and dated it differently. That
                # is a measurement disagreement, not provenance.
                conflicts.append(
                    f"{_COLLECTION_DATE}: "
                    + " vs ".join(
                        f"{_parse_date(raw).date().isoformat()} (row {row_num})"
                        for row_num, raw in candidates
                    )
                )
            else:
                notes.fallback_date_disagreement = True
        cells[_COLLECTION_DATE] = candidates[0][1]

    # --- Provenance: first non-null wins, clash is a note ----------------
    for column in _RUN_DATE_COLUMNS:
        dated = [
            (row_num, row.get(column))
            for row_num, _exp_id, row in members
            if _parse_date(row.get(column)) is not None
        ]
        if not dated:
            continue
        if len({_parse_date(raw) for _, raw in dated}) > 1:
            notes.run_date_disagreements.append(column)
        cells[column] = dated[0][1]

    # --- Free text: join distinct values in sheet order ------------------
    for column in _JOINED_TEXT_COLUMNS:
        texts = [
            str(row.get(column)).strip()
            for _row_num, _exp_id, row in members
            if str(row.get(column) or "").strip()
        ]
        if texts:
            cells[column] = "; ".join(dict.fromkeys(texts))

    # --- Directive: OVERWRITE needs unanimity ----------------------------
    # Clearing is destructive and a merged vial-day is ONE write, so a single
    # TRUE must not extend clearing to fields another row's author owns. The
    # ignored directive is reported rather than silently dropped.
    flags = [_parse_bool(row.get("Overwrite")) for _r, _e, row in members]
    overwrite = all(flags)
    if any(flags) and not overwrite:
        notes.overwrite_mixed = True

    if conflicts:
        return None, conflicts, notes
    return MergedGroup(cells=cells, overwrite=overwrite), conflicts, notes
```

- [ ] **Step 5: Run the unit tests to verify they pass**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k merge_group -v
```
Expected: PASS, 16 tests.

- [ ] **Step 6: Confirm nothing else changed**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q
```
Expected: same result as the end of Task 1 — `_merge_group` has no callers yet, so the duplicate-guard tests still pass unchanged.

- [ ] **Step 7: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -F <scratch-file>
```
Message:
```
[feat] Add field classes and _merge_group

Pure collapse of N Dashboard rows for one vial-day. No caller yet.

- Measurement clash is a conflict; run dates and text are provenance
- Collection date prefers a liquid/solid-bearing row, never discards
- OVERWRITE needs unanimity
- Tests added: yes
- Docs updated: no
```

---

## Task 3: Wire Phase 1.5 into `_process_bytes`

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (`:537-569` duplicate block → Phase 1.5; Phase 2 loop header `:589`; `overwrite` read at `:608`; feedback dict `:676-682`)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Consumes: `_merge_group`, `MergedGroup`, `MergeNotes` from Task 2.
- Produces, for Task 4: a local list `merged_entries: List[Tuple[int, List[int], str, float, Any, TimepointCheck, bool]]` — `(anchor_row, rows, exp_id, time_post_reaction, cells, check, overwrite)` — and a parallel `group_notes: List[Tuple[int, List[int], MergeNotes]]` holding one entry per multi-row group, which Task 4 turns into file-level warnings.

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
# ---------------------------------------------------------------------------
# Phase 1.5 — merged vial-days end to end
# ---------------------------------------------------------------------------

def test_gas_and_liquid_rows_merge_into_one_result(db_session: Session):
    """The motivating case, end to end.

    Gas sampled 2026-07-22 and run the same day; the liquid/solid fraction
    collected 2026-08-05. Both rows name the same -t1 vial, so the ID pins the
    day and they are one vial-day.
    """
    _seed_experiment(db_session, "SERUM_MG01a-t1", 8921)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_MG01a-t1", 1.0, description="", ph=None,
                di_h2=87.12, di_vol=30.0, di_psi=14.7,
                collection_date="2026-07-22", gc_date="2026-07-22"),
        _v3_row("SERUM_MG01a-t1", 1.0, description="Highest H2 liquid, solids",
                ph=7.24, cond=1.541, collection_date="2026-08-05"),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"complementary rows must merge: {result.errors}"
    assert result.created == 1, "one vial-day is one write"
    assert result.updated == 0

    scalar = _scalar_for(db_session, "SERUM_MG01a-t1")
    assert scalar.h2_concentration == pytest.approx(87.12)
    assert scalar.gas_sampling_volume_ml == pytest.approx(30.0)
    assert scalar.gas_sampling_pressure_MPa == pytest.approx(14.7 * _PSI_TO_MPA)
    assert scalar.final_ph == pytest.approx(7.24)
    assert scalar.final_conductivity_mS_cm == pytest.approx(1.541)
    assert scalar.measurement_date == _dt.datetime(2026, 8, 5), (
        "the liquid row's collection date wins"
    )


def test_merged_group_reports_every_row_in_feedbacks(db_session: Session):
    """One feedback per vial-day, naming every sheet row behind it."""
    _seed_experiment(db_session, "SERUM_MG02a-t1", 8922)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_MG02a-t1", 1.0, ph=None, di_h2=87.12),
        _v3_row("SERUM_MG02a-t1", 1.0, ph=7.24),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert len(result.feedbacks) == 1, f"one write, one feedback: {result.feedbacks}"
    assert result.feedbacks[0]["row"] == 2, "anchored at the group's first row"
    assert result.feedbacks[0]["rows"] == [2, 3]


def test_merge_summary_warning_explains_the_count_gap(db_session: Session):
    """created + updated no longer equals the sheet row count; say why."""
    _seed_experiment(db_session, "SERUM_MG03a-t1", 8923)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_MG03a-t1", 1.0, ph=None, di_h2=87.12),
        _v3_row("SERUM_MG03a-t1", 1.0, ph=7.24),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert any("Merged 2 rows into 1 vial-day" in w for w in result.warnings), (
        f"expected a merge summary, got: {result.warnings}"
    )


def test_no_merge_summary_when_nothing_merged(db_session: Session):
    """A sheet with no duplicate keys behaves exactly as before."""
    _seed_experiment(db_session, "HPHT_MG04", 8924)

    xlsx = _master_excel_v3([_v3_row("HPHT_MG04", 7.0, nh4=1.0)])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.created == 1
    assert not any("Merged" in w for w in result.warnings), (
        f"a warning that fires on ordinary sheets is one people ignore: "
        f"{result.warnings}"
    )


def test_conflicted_vial_day_leaves_a_stored_row_untouched(db_session: Session):
    """A conflict must not partially update what is already stored."""
    _seed_experiment(db_session, "SERUM_MG05a-t1", 8925)

    first = _master_excel_v3([
        _v3_row("SERUM_MG05a-t1", 1.0, ph=7.0, di_h2=10.0),
    ])
    MasterBulkUploadService.from_bytes_ex(db_session, first)

    second = _master_excel_v3([
        _v3_row("SERUM_MG05a-t1", 1.0, ph=None, di_h2=33.89),
        _v3_row("SERUM_MG05a-t1", 1.0, ph=None, di_h2=39.01),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, second)

    assert result.created == 0
    assert result.updated == 0
    assert len(result.errors) == 1, f"one error for the group: {result.errors}"

    scalar = _scalar_for(db_session, "SERUM_MG05a-t1")
    assert scalar.h2_concentration == pytest.approx(10.0), (
        "the stored reading must survive a conflicted re-upload"
    )


def test_conflict_error_names_rows_field_and_both_values(db_session: Session):
    _seed_experiment(db_session, "SERUM_MG06a-t1", 8926)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_MG06a-t1", 1.0, ph=None, di_h2=33.89),
        _v3_row("SERUM_MG06a-t1", 1.0, ph=None, di_h2=39.01),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    (message,) = result.errors
    assert "Rows 2, 3" in message, message
    assert "SERUM_MG06a-t1" in message, message
    assert "day 1" in message, message
    assert "DI H2 (ppm)" in message, message
    assert "33.89" in message and "39.01" in message, message
    assert "Nothing was written" in message, message


def test_three_row_group_merges_end_to_end(db_session: Session):
    _seed_experiment(db_session, "HPHT_MG07-t2", 8927)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_MG07-t2", 2.0, ph=None, di_h2=50.0),
        _v3_row("HPHT_MG07-t2", 2.0, ph=7.24),
        _v3_row("HPHT_MG07-t2", 2.0, ph=None, nh4=3.5, solvol=2.0),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"unexpected errors: {result.errors}"
    assert result.created == 1

    scalar = _scalar_for(db_session, "HPHT_MG07-t2")
    assert scalar.h2_concentration == pytest.approx(50.0)
    assert scalar.final_ph == pytest.approx(7.24)
    assert scalar.gross_ammonium_concentration_mM == pytest.approx(3.5)
    assert scalar.sampling_volume_mL == pytest.approx(2.0)


def test_full_loop_on_one_row_beats_di_on_another(db_session: Session):
    """_resolve_h2 runs once over the merged view, so precedence is unchanged."""
    _seed_experiment(db_session, "HPHT_MG08-t2", 8928)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_MG08-t2", 2.0, ph=None, fl_h2=100.0, fl_vol=20.0,
                fl_psi=14.7),
        _v3_row("HPHT_MG08-t2", 2.0, ph=None, di_h2=50.0, di_vol=30.0,
                di_psi=14.7),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"different GC blocks are not a conflict: {result.errors}"
    scalar = _scalar_for(db_session, "HPHT_MG08-t2")
    assert scalar.h2_concentration == pytest.approx(100.0), "Full Loop wins"
    assert scalar.gas_sampling_volume_ml == pytest.approx(20.0), (
        "geometry must come from the winning block"
    )
    assert any("Full Loop reading used instead of direct injection" in w
               for w in result.warnings), result.warnings


def test_duration_still_drives_non_token_ids(db_session: Session):
    """Regression for spec §1.5: no -t token means Duration supplies the day."""
    _seed_experiment(db_session, "HPHT_MG09", 8929)

    xlsx = _master_excel_v3([_v3_row("HPHT_MG09", 11.0, nh4=1.0)])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    row = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_MG09")
        .one()
    )
    assert row.time_post_reaction_days == pytest.approx(11.0)


def test_rows_one_duration_apart_stay_two_vial_days(db_session: Session):
    """Spec D-g: grouping matches the exact timepoint, with no tolerance window.

    HPHT_217 (day 11 gas, day 12 liquid) and six other IDs in the team's
    workbook look like this and genuinely record different sampling days.
    """
    _seed_experiment(db_session, "HPHT_MG10", 8930)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_MG10", 11.0, ph=None, di_h2=50.0),
        _v3_row("HPHT_MG10", 12.0, ph=7.24),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    assert result.created == 2, "two Durations are two vial-days"
    assert not any("Merged" in w for w in result.warnings), result.warnings
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "MG0 or MG1 or merge_summary or conflicted_vial or three_row_group or duration_still" -v
```
Expected: FAIL. The merge tests fail because the duplicate guard still rejects both rows (`created == 0`, one "duplicate experiment ID and timepoint" error). `test_merged_group_reports_every_row_in_feedbacks` fails with `KeyError: 'rows'`. `test_duration_still_drives_non_token_ids` and `test_rows_one_duration_apart_stay_two_vial_days` should already PASS — they are regression guards.

- [ ] **Step 3: Replace the duplicate-rejection block with Phase 1.5**

In `master_bulk_upload.py`, replace the whole block from `duplicate_rows: set[int] = set()` through the end of the `for (_norm_id, day), members in dup_groups.items():` loop (`:547-569`) with:

```python
    # Phase 1.5 -- collapse each vial-day's rows into one merged cell view.
    #
    # Gas is drawn and run on one date; the liquid/solid fraction is collected
    # later and gets its own row. Both name the same vial and the same day, so
    # before this they were rejected as duplicates and NOTHING was written --
    # 80 of 268 real rows in the team's workbook, 2026-08-11. They are
    # complementary, not competing: only a field two rows both fill with
    # DIFFERENT values is a real conflict, and that vial-day is then rejected
    # whole (spec D-a) rather than partially merged.
    #
    # Grouping matches the EXACT timepoint -- no tolerance window (spec D-g).
    # Setting two rows to the same Duration is the researcher's deliberate
    # request to merge them; adjacent days stay separate vial-days.
    merged_entries: List[
        Tuple[int, List[int], str, float, Any, TimepointCheck, bool]
    ] = []
    group_notes: List[Tuple[int, List[int], MergeNotes]] = []
    merged_row_count = 0
    merged_group_count = 0

    for members in dup_groups.values():
        anchor_row, anchor_id, _anchor_cells, _anchor_check = (
            members[0][0], members[0][1], members[0][2], members[0][3],
        )
        rows = [row_num for row_num, _e, _r, _c in members]

        if len(members) == 1:
            row_num, exp_id, row, check = members[0]
            merged_entries.append((
                row_num, [row_num], exp_id, group_times[id(members)], row,
                check, _parse_bool(row.get("Overwrite")),
            ))
            continue

        merged, conflicts, notes = _merge_group(
            [(row_num, exp_id, row) for row_num, exp_id, row, _c in members]
        )
        group_notes.append((anchor_row, rows, notes))

        if conflicts:
            rows_text = ", ".join(str(row_num) for row_num in rows)
            spellings = ", ".join(notes.spellings)
            day = group_times[id(members)]
            row_errors.append((anchor_row, (
                f"Rows {rows_text} ({spellings}): conflicting values for the "
                f"same vial-day (day {day:g}) — {'; '.join(conflicts)}. Rows "
                f"for one vial-day are merged, but a field cannot hold two "
                f"values. Nothing was written for this vial-day."
            )))
            continue

        # A merged group's timepoint check is the union of its rows': any row
        # that could be compared makes the group comparable, and any
        # disagreement is worth reporting.
        check = TimepointCheck(
            compared=any(c.compared for _r, _e, _row, c in members),
            disagrees=any(c.disagrees for _r, _e, _row, c in members),
        )
        merged_entries.append((
            anchor_row, rows, anchor_id, group_times[id(members)],
            merged.cells, check, merged.overwrite,
        ))
        merged_row_count += len(rows)
        merged_group_count += 1
```

This needs `dup_groups` to carry the row payload and the timepoint. Change the group build (`:537-540`) from storing `(row_num, exp_id)` to storing the full tuple, and keep each group's timepoint alongside:

```python
    dup_groups: Dict[Tuple[str, float], List[Tuple[int, str, Any, TimepointCheck]]] = {}
    group_times: Dict[int, float] = {}
    for row_num, exp_id, time_post_reaction, row, check in resolved:
        key = (normalize_id(exp_id), normalize_timepoint(time_post_reaction))
        members = dup_groups.setdefault(key, [])
        members.append((row_num, exp_id, row, check))
        # Keyed by the list's identity so the timepoint travels with the group
        # without widening the member tuple. Every member of a group resolved to
        # the same normalized timepoint by construction.
        group_times[id(members)] = time_post_reaction
```

- [ ] **Step 4: Point Phase 2 at the merged entries**

Change the Phase 2 loop header (`:589`) from:

```python
    for row_num, exp_id, time_post_reaction, row, check in resolved:
        # The error was already emitted once for the whole group above.
        if row_num in duplicate_rows:
            continue
```

to:

```python
    for row_num, rows, exp_id, time_post_reaction, row, check, overwrite in merged_entries:
```

Delete the `overwrite = _parse_bool(row.get("Overwrite"))` line (`:608`) — the flag now arrives from Phase 1.5, which applies the unanimity rule for merged groups and the plain parse for single rows.

Add `rows` to the feedback dict (`:676-682`):

```python
            feedbacks.append({
                "row": row_num,
                "rows": rows,
                "experiment_id": exp_id,
                "action": action,
                "h2_source": h2_source,
                "h2_di_superseded": di_superseded,
            })
```

- [ ] **Step 5: Add the merge summary warning**

In `master_bulk_upload.py`, immediately before the supersede warning block (`:699`), add:

```python
    # created + updated no longer equals the sheet row count once rows merge,
    # so say so plainly rather than leaving the numbers unexplained. Silent
    # when nothing merged: a warning that fires on ordinary sheets is one
    # researchers learn to ignore.
    if merged_group_count:
        day_label = "vial-day" if merged_group_count == 1 else "vial-days"
        warnings.append(
            f"Merged {merged_row_count} rows into {merged_group_count} "
            f"{day_label}. Gas and liquid/solid readings for one vial are often "
            "recorded on separate rows because they were collected on different "
            "dates; those rows are combined field by field."
        )
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "MG0 or MG1 or merge_summary or conflicted_vial or three_row_group or duration_still" -v
```
Expected: PASS.

- [ ] **Step 7: Run the whole file and note expected failures**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q
```
Expected: the new tests PASS; the eight duplicate-guard tests now FAIL because they assert the rejection policy this task replaces. **Do not fix them here** — Task 5 rewrites them deliberately. Record which failed so Task 5 can confirm it covered them all.

- [ ] **Step 8: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -F <scratch-file>
```
Message:
```
[feat] Merge multiple Dashboard rows per vial-day

Phase 1.5 collapses each vial-day's rows before the upsert loop. A
measurement clash rejects that vial-day whole; complementary rows merge.

- One write, one feedback, with every source row named in `rows`
- Merge summary warning explains the count gap
- Eight duplicate-guard tests now fail by design; rewritten next
- Tests added: yes
- Docs updated: no
```

---

## Task 4: Group-level warnings

`_merge_group` already records these in `MergeNotes`; nothing renders them yet.

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (after the merge summary warning added in Task 3)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Consumes: `group_notes: List[Tuple[int, List[int], MergeNotes]]` from Task 3.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
# ---------------------------------------------------------------------------
# Group-level warnings
# ---------------------------------------------------------------------------

def test_mixed_overwrite_warns_and_clears_nothing(db_session: Session):
    """A destructive directive needs unanimity, and the refusal is reported.

    Rows 154/204 of the team's workbook are exactly this: a DI reading marked
    OVERWRITE beside an untouched liquid row.
    """
    _seed_experiment(db_session, "SERUM_MW01c-t5", 8941)

    first = _master_excel_v3([
        _v3_row("SERUM_MW01c-t5", 5.0, ph=7.0, nh4=1.0),
    ])
    MasterBulkUploadService.from_bytes_ex(db_session, first)

    second = _master_excel_v3([
        _v3_row("SERUM_MW01c-t5", 5.0, ph=None, di_h2=404.19, overwrite="TRUE"),
        _v3_row("SERUM_MW01c-t5", 5.0, ph=9.03, cond=0.204, overwrite="FALSE"),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, second)

    assert result.errors == [], f"mixed OVERWRITE is not an error: {result.errors}"
    assert any("OVERWRITE" in w and "154" not in w for w in result.warnings) or \
        any("overwrite" in w.lower() for w in result.warnings), (
            f"the ignored directive must be reported: {result.warnings}"
        )

    scalar = _scalar_for(db_session, "SERUM_MW01c-t5")
    assert scalar.gross_ammonium_concentration_mM == pytest.approx(1.0), (
        "no clearing: the NH4 value this sheet left blank must survive"
    )


def test_unanimous_overwrite_clears_a_declared_blank(db_session: Session):
    """When every row says TRUE, the overwrite happens as before."""
    _seed_experiment(db_session, "SERUM_MW02c-t5", 8942)

    first = _master_excel_v3([
        _v3_row("SERUM_MW02c-t5", 5.0, ph=7.0, nh4=1.0),
    ])
    MasterBulkUploadService.from_bytes_ex(db_session, first)

    second = _master_excel_v3([
        _v3_row("SERUM_MW02c-t5", 5.0, ph=None, di_h2=404.19, overwrite="TRUE"),
        _v3_row("SERUM_MW02c-t5", 5.0, ph=9.03, overwrite="TRUE"),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, second)

    assert result.errors == [], f"unexpected errors: {result.errors}"
    scalar = _scalar_for(db_session, "SERUM_MW02c-t5")
    assert scalar.gross_ammonium_concentration_mM is None, (
        "a declared-but-blank column clears under a unanimous overwrite"
    )


def test_run_date_disagreement_warns_and_still_writes(db_session: Session):
    _seed_experiment(db_session, "SERUM_MW03a-t1", 8943)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_MW03a-t1", 1.0, ph=None, di_h2=50.0,
                gc_date="2026-07-22"),
        _v3_row("SERUM_MW03a-t1", 1.0, ph=7.24, gc_date="2026-07-28"),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"a run date is provenance: {result.errors}"
    assert result.created == 1
    assert any("GC Run Date" in w for w in result.warnings), result.warnings


def test_variant_spellings_merge_and_are_named(db_session: Session):
    """A case typo is not a distinct experiment; merge and name the spellings."""
    _seed_experiment(db_session, "SERUM_MW04c-t5", 8944)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_mw04c-t5", 5.0, ph=None, di_h2=50.0),
        _v3_row("SERUM_MW04C-t5", 5.0, ph=7.24),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"variant spellings must merge: {result.errors}"
    assert result.created == 1
    assert any("SERUM_mw04c-t5" in w and "SERUM_MW04C-t5" in w
               for w in result.warnings), (
        f"both spellings must be named: {result.warnings}"
    )


def test_disagreeing_fallback_dates_warn(db_session: Session):
    """No liquid row in the group: first date wins and the clash is reported."""
    _seed_experiment(db_session, "GC_MW05-t0", 8945)

    xlsx = _master_excel_v3([
        _v3_row("GC_MW05-t0", 0.0, ph=None, di_h2=50.0,
                collection_date="2026-08-06"),
        _v3_row("GC_MW05-t0", 0.0, ph=None, fl_vol=30.0,
                collection_date="2026-08-10"),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"a fallback date must not reject: {result.errors}"
    assert result.created == 1
    assert any("collection date" in w.lower() for w in result.warnings), (
        f"the disagreement must be reported: {result.warnings}"
    )

    scalar = _scalar_for(db_session, "GC_MW05-t0")
    assert scalar.measurement_date == _dt.datetime(2026, 8, 6), "first in sheet order"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "MW0" -v
```
Expected: FAIL — the writes succeed but no warning is emitted for any of the four note types. `test_unanimous_overwrite_clears_a_declared_blank` should already PASS.

- [ ] **Step 3: Render the notes as file-level warnings**

In `master_bulk_upload.py`, immediately after the merge summary warning from Task 3, add:

```python
    # MergeNotes are things a researcher should know about a vial-day that DID
    # land, so they are warnings, never errors. One file-level line per kind,
    # with the row list only at <=10 groups -- the threshold the supersede,
    # GC-date and Duration warnings below already share.
    def _rows_clause(anchors: List[str]) -> str:
        return " (" + ", ".join(anchors) + ")" if len(anchors) <= 10 else ""

    mixed_overwrite = [
        rows for _anchor, rows, notes in group_notes if notes.overwrite_mixed
    ]
    if mixed_overwrite:
        shown = [" and ".join(str(r) for r in rows) for rows in mixed_overwrite]
        warnings.append(
            f"'OVERWRITE' was set on some but not all rows of "
            f"{len(mixed_overwrite)} merged vial-day(s)"
            + _rows_clause(shown)
            + ". Overwrite clears the sheet's own columns that are left blank, "
              "so it was NOT applied: those vial-days were merged without "
              "clearing anything. Tick the box on every row of the vial-day, or "
              "on none."
        )

    date_clashes = [
        rows for _anchor, rows, notes in group_notes
        if notes.fallback_date_disagreement
    ]
    if date_clashes:
        shown = [" and ".join(str(r) for r in rows) for rows in date_clashes]
        warnings.append(
            f"{len(date_clashes)} merged vial-day(s) disagree on "
            f"'{_COLLECTION_DATE}'" + _rows_clause(shown)
            + ", and no row carries a liquid/solid measurement to settle which "
              "date is authoritative. The first date in sheet order was stored."
        )

    run_date_clashes: Dict[str, List[str]] = {}
    for _anchor, rows, notes in group_notes:
        for column in notes.run_date_disagreements:
            run_date_clashes.setdefault(column, []).append(
                " and ".join(str(r) for r in rows)
            )
    for column in _RUN_DATE_COLUMNS:      # stable order, not dict insertion
        clashing = run_date_clashes.get(column)
        if not clashing:
            continue
        warnings.append(
            f"'{column}' differs between the rows of {len(clashing)} merged "
            f"vial-day(s)" + _rows_clause(clashing)
            + ". It is provenance, not a measurement, so the first value in "
              "sheet order was stored and no row was rejected."
        )

    variant_spellings = [
        (rows, notes.spellings)
        for _anchor, rows, notes in group_notes if len(notes.spellings) > 1
    ]
    if variant_spellings:
        shown = [
            " and ".join(str(r) for r in rows) + ": " + ", ".join(spellings)
            for rows, spellings in variant_spellings
        ]
        warnings.append(
            f"{len(variant_spellings)} merged vial-day(s) spell their "
            f"experiment ID more than one way" + _rows_clause(shown)
            + ". The spellings resolve to one stored experiment, so the rows "
              "were merged normally — but the difference is a typo worth fixing "
              "in the sheet."
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "MW0" -v
```
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -F <scratch-file>
```
Message:
```
[feat] Report merge notes as file-level warnings

- Mixed OVERWRITE, disagreeing fallback dates, run-date clashes and
  variant ID spellings each get one line
- Tests added: yes
- Docs updated: no
```

---

## Task 5: Rewrite the duplicate-guard tests

Eight tests assert the rejection policy Task 3 replaced. Each is re-pointed at the merge policy, keeping the property it was pinning. Three neighbours in the same block assert grouping behaviour the merge does not change and must be confirmed still passing, not edited.

**Files:**
- Modify: `tests/services/bulk_uploads/test_master_bulk_upload.py` (`:1372-1400`, `:1496-1543`, `:1544-1660`)

**Interfaces:** none produced or consumed.

- [ ] **Step 1: Re-point `test_duplicate_vial_and_timepoint_is_an_error`**

Replace it (`:1372-1400`) with two tests — the merge case and the conflict case — because the original name conflated them:

```python
def test_repeated_vial_and_timepoint_merges_when_complementary(db_session: Session):
    """Two rows for one vial-day are merged, not rejected.

    Before this, v3 was read as strictly one row per vial-day and a repeat was
    the old wide-format habit leaking through. It is not: gas is drawn and run
    on one date and the liquid/solid fraction is collected later, so the two
    fractions legitimately arrive as two rows.
    """
    _seed_experiment(db_session, "SERUM_DUP01a", 8831)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP01a", 7.0, description="gas", ph=None, fl_h2=10.0),
        _v3_row("SERUM_DUP01a", 7.0, description="liquid", ph=7.4, cond=1.2),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert errors == [], f"complementary rows must merge: {errors}"
    assert created == 1, "one vial-day is one write"
    assert updated == 0

    assert (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_DUP01a")
        .count()
    ) == 1


def test_repeated_vial_and_timepoint_errors_when_conflicting(db_session: Session):
    """Two rows filling the same field with different values reject the vial-day.

    Letting the later row win would destroy the earlier reading silently, which
    is the failure the old duplicate guard existed to prevent. The guard is kept
    for exactly this case and dropped for the complementary one.
    """
    _seed_experiment(db_session, "SERUM_DUP01b", 8832)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP01b", 7.0, description="first", ph=None, fl_h2=10.0),
        _v3_row("SERUM_DUP01b", 7.0, description="second", ph=None, fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert created == 0, "neither row may be written"
    assert updated == 0
    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "SERUM_DUP01b" in errors[0]
    assert "Rows 2, 3" in errors[0], f"both rows must be named: {errors[0]}"

    assert (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_DUP01b")
        .count()
    ) == 0
```

- [ ] **Step 2: Re-point the case- and padding-variant tests**

Replace `test_case_variant_ids_at_one_timepoint_are_a_duplicate` and `test_padding_variant_ids_at_one_timepoint_are_a_duplicate` (`:1496-1543`) with:

```python
def test_case_variant_ids_at_one_timepoint_are_one_vial_day(db_session: Session):
    """Two spellings resolving to ONE experiment are ONE vial-day.

    The pre-pass keys on _id_match.normalize_id, the same key the DB lookup
    uses, so 'SERUM_cation_001c-t5' and 'SERUM_Cation_001c-t5' are one vial and
    their rows merge. Keying on the raw string instead let both rows upsert onto
    the one stored experiment, the second silently overwriting the first. Three
    such pairs are live in Master_Results_Tracker_v3.xlsx (rows 29/194, 32/195,
    35/196). A capital letter is a typo, not a distinct experiment.
    """
    _seed_experiment(db_session, "SERUM_DUP06c-t5", 8866)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_dup06c-t5", 5.0, description="gas", ph=None, fl_h2=10.0),
        _v3_row("SERUM_DUP06C-t5", 5.0, description="liquid", ph=7.4),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert errors == [], f"variant spellings must merge: {errors}"
    assert created == 1

    assert (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_DUP06c-t5")
        .count()
    ) == 1


def test_padding_variant_ids_at_one_timepoint_are_one_vial_day(db_session: Session):
    """Zero-padding differences collapse the same way case differences do.

    normalize_id strips leading zeros per digit run, so 'HPHT_007' and 'HPHT_7'
    are one experiment to the finder and one vial-day to the merge.
    """
    _seed_experiment(db_session, "HPHT_DUP07", 8867)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_DUP07", 7.0, description="gas", ph=None, fl_h2=10.0),
        _v3_row("HPHT_DUP0007", 7.0, description="liquid", ph=7.4),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert errors == [], f"padding variants must merge: {errors}"
    assert created == 1
```

- [ ] **Step 3: Re-point `test_duplicate_group_is_one_error_naming_every_row`**

Replace it (`:1544-1568`) with:

```python
def test_conflict_group_is_one_error_naming_every_row(db_session: Session):
    """One conflicted vial-day produces one error listing all its rows.

    A researcher reads this list against the sheet: 'row 2 conflicts' with no
    sibling row number means opening the file and searching for the partner by
    hand. Same shape as the ambiguous-ID fix in commit de379a1.
    """
    _seed_experiment(db_session, "SERUM_DUP08a", 8868)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP08a", 7.0, description="first", ph=None, fl_h2=10.0),
        _v3_row("SERUM_DUP08a", 7.0, description="second", ph=None, fl_h2=20.0),
        _v3_row("SERUM_DUP08a", 7.0, description="third", ph=None, fl_h2=30.0),
    ])
    created, updated, skipped, errors, _ = _upload(db_session, xlsx)

    assert created == 0
    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "Rows 2, 3, 4" in errors[0], f"every row must be named: {errors[0]}"
    assert "SERUM_DUP08a" in errors[0]
    assert "day 7" in errors[0]
    assert "FL H2 (ppm)" in errors[0], f"the bad field must be named: {errors[0]}"
```

- [ ] **Step 4: Re-point `test_duplicate_group_names_both_spellings`**

Replace it (`:1570-1591`) with:

```python
def test_variant_spellings_are_named_in_a_warning(db_session: Session):
    """When merged rows are spelled differently, the warning says so.

    The rows merge (a capital letter is a typo, not a distinct experiment), but
    the researcher still needs to see that the two cells do not read the same,
    or the sheet keeps drifting. Reported as a warning, not an error, so it
    never blocks an upload.
    """
    _seed_experiment(db_session, "SERUM_DUP09c-t5", 8869)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_dup09c-t5", 5.0, description="gas", ph=None, fl_h2=10.0),
        _v3_row("SERUM_DUP09C-t5", 5.0, description="liquid", ph=7.4),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"a spelling variant is not an error: {result.errors}"
    assert result.created == 1
    variant = [w for w in result.warnings if "SERUM_dup09c-t5" in w]
    assert variant, f"first spelling missing: {result.warnings}"
    assert "SERUM_DUP09C-t5" in variant[0], f"second spelling missing: {variant[0]}"
```

- [ ] **Step 5: Re-point the sort-order and does-not-block tests**

Replace `test_duplicate_group_error_sorts_at_its_first_row` and `test_duplicate_does_not_block_other_rows` (`:1593-1636`) with:

```python
def test_conflict_group_error_sorts_at_its_first_row(db_session: Session):
    """The group error sits where its earliest row sits in sheet order.

    Errors are sorted by row number so the list reads top-down against the
    spreadsheet (issue #114 item 3). A group spanning rows 2 and 4 must appear
    above a single-row failure on row 3, not after it.
    """
    _seed_experiment(db_session, "SERUM_DUP10a", 8870)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP10a", 7.0, description="dup one", ph=None, fl_h2=10.0),
        _v3_row("HPHT_DUP10_MISSING", 7.0, description="no such experiment"),
        _v3_row("SERUM_DUP10a", 7.0, description="dup two", ph=None, fl_h2=20.0),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert len(result.errors) == 2, f"one group + one row error: {result.errors}"
    assert result.errors[0].startswith("Rows 2, 4 ("), (
        f"the group anchored at row 2 must come first: {result.errors}"
    )
    assert result.errors[1].startswith("Row 3 ("), (
        f"the row 3 failure must come second: {result.errors}"
    )


def test_conflict_does_not_block_other_vial_days(db_session: Session):
    """A conflicted vial-day is rejected; unrelated rows still land."""
    _seed_experiment(db_session, "SERUM_DUP05a", 8861)
    _seed_experiment(db_session, "SERUM_DUP05b", 8862)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP05a", 7.0, description="dup one", ph=None, fl_h2=10.0),
        _v3_row("SERUM_DUP05a", 7.0, description="dup two", ph=None, fl_h2=20.0),
        _v3_row("SERUM_DUP05b", 7.0, description="fine", ph=None, fl_h2=30.0),
    ])
    created, updated, skipped, errors, feedbacks = _upload(db_session, xlsx)

    assert created == 1
    assert len(errors) == 1, f"one error for the group, got: {errors}"
    assert "Rows 2, 3" in errors[0]
    assert [f["experiment_id"] for f in feedbacks] == ["SERUM_DUP05b"]
```

- [ ] **Step 6: Rename the `-t`-resolution test for accuracy**

`test_duplicate_detected_after_timepoint_token_resolution` (`:1475`) still asserts a real property — grouping happens after the `-t` token is resolved — but "duplicate detected" is now wrong. Read it, then rename it to `test_grouping_happens_after_timepoint_token_resolution` and change its assertions from "both rejected" to whatever the merge produces for its fixture (merge if the rows are complementary, one error if they share a field). Do not change the fixture's IDs or durations — the token-resolution property is what it exists to pin.

- [ ] **Step 7: Run the whole file**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q
```
Expected: all PASS. Cross-check against the failure list recorded in Task 3 Step 7 — every one must now be accounted for by a rewritten test, not by deletion.

- [ ] **Step 8: Commit**

```bash
git add tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -F <scratch-file>
```
Message:
```
[test] Re-point duplicate-guard tests at the merge

Eight tests asserted the rejection policy. Each keeps the property it
pinned and now asserts the merge outcome instead.

- Case and padding variants merge rather than both being rejected
- Conflict errors still anchor at the group's first row
- Tests added: yes
- Docs updated: no
```

---

## Task 6: Re-word the two coverage warnings for vial-days

The GC-date coverage warning (`:733`) and the Duration-vs-token warning (`:766`) count "rows" in denominators tallied in Phase 2. Phase 2 now iterates vial-days, so those numbers are vial-days and the wording must say so.

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (`:733-753`, `:766-780`, and the comment block at `:578-588`)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:** none produced or consumed.

- [ ] **Step 1: Write the failing test**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
def test_gc_date_coverage_warning_counts_vial_days(db_session: Session):
    """Phase 2 iterates vial-days, so the denominator is vial-days, not rows.

    Two sheet rows merge into one vial-day carrying an H2 reading and no GC Run
    Date. Reporting '1 of 1 rows' would be a lie about what the parser counted.
    """
    _seed_experiment(db_session, "SERUM_MV01a-t1", 8951)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_MV01a-t1", 1.0, ph=None, di_h2=50.0),
        _v3_row("SERUM_MV01a-t1", 1.0, ph=7.24),
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    gc_warning = [w for w in result.warnings if "GC Run Date" in w]
    assert gc_warning, f"expected the GC-date coverage warning: {result.warnings}"
    assert "vial-day" in gc_warning[0], (
        f"the denominator counts vial-days, not rows: {gc_warning[0]}"
    )
```

- [ ] **Step 2: Run it to verify it fails**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k MV01 -v
```
Expected: FAIL — the warning says "row"/"rows".

- [ ] **Step 3: Re-word both warnings**

In the GC-date warning (`:733-753`), rename the local `label` computation and message wording from rows to vial-days:

```python
        label = "vial-day" if total == 1 else "vial-days"
        ...
        warnings.append(
            f"'GC Run Date' is missing or unreadable on {n} of {total} {label} "
            f"carrying an H2 reading{where}. {stored_clause} "
            ...
        )
```

Do the same in the Duration-vs-token warning (`:766-780`):

```python
        label = "vial-day" if comparable_rows == 1 else "vial-days"
        ...
            f"Duration (Days) disagrees with the ID's -t token on {n} of "
            f"{comparable_rows} {label}{where}. The ID is canonical, so each "
            ...
```

Update the comment block at `:578-588` so it describes vial-days rather than rows, and add why the footnote ² property still holds:

```python
    # Denominators for the warnings below. Counted here, after the write
    # succeeds -- not in Phase 1 where the check was computed -- because a
    # vial-day that is rejected (conflicting rows, or no matching experiment)
    # was never written and cannot honestly be described as "recorded at the day
    # its ID encodes". Phase 2 now iterates MERGED vial-days, so these count
    # vial-days, not sheet rows; a conflicted group never reaches this loop and
    # so enters neither numerator nor denominator.
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k MV01 -v
```
Expected: PASS.

- [ ] **Step 5: Run the whole file**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q
```
Expected: all PASS. Existing tests asserting on these two warnings may match on `"row"` — update those assertions to the new wording if they fail.

- [ ] **Step 6: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -F <scratch-file>
```
Message:
```
[fix] Count vial-days in the coverage warnings

Phase 2 iterates merged vial-days, so "n of m rows" was wrong.

- Tests added: yes
- Docs updated: no
```

---

## Task 7: Documentation

**Files:**
- Modify: `docs/LOCKED_COMPONENTS.md`, `MODELS.md`, `backend/services/bulk_uploads/master_bulk_upload.py` (module docstring `:1-27`), `docs/working/issue-log.md`
- Check: `docs/upload_templates/` for any file naming `Sample Date`

**Interfaces:** none.

- [ ] **Step 1: Amend footnote ² in `docs/LOCKED_COMPONENTS.md`**

Footnote ² (at `:70`) currently records the duplicate guard as "both rows rejected" with six properties to preserve. Three survive (normalized-ID keying, first-row anchoring, per-row SAVEPOINT); the rejection does not. Leaving it intact beside a new footnote would leave two footnotes contradicting each other. Edit ² so its opening states that rows for one vial-day are now **merged** (superseded 2026-08-11, see ⁴), keep the paragraph explaining why the key is `normalize_id`-based, and keep the anchoring and SAVEPOINT sentences verbatim.

- [ ] **Step 2: Add footnote ⁴**

Append after footnote ³, following the numbering convention ¹/²/³ already established, and add a `⁴` marker beside `master_bulk_upload.py` in the parsers table (`:66`, which currently carries `²` — it becomes `²⁴`):

```markdown
⁴ **Row-merge contract (changed 2026-08-11 with explicit sign-off).** Several
Dashboard rows may describe one vial-day: gas is drawn and run on one date, the
liquid/solid fraction is collected later, and each gets its own row. Phase 1.5
collapses them into one merged cell view before the upsert loop, superseding the
blanket rejection in ². Load-bearing properties: (a) every Dashboard column
belongs to exactly one merge class -- measurement, collection date, provenance,
directive -- declared as module frozensets, so a new column forces a choice;
(b) classification is on the RAW CELL, before `_resolve_h2`, which runs once over
the merged view so Full-Loop precedence and the #114 geometry rule cannot drift;
(c) a measurement disagreement rejects the vial-day WHOLE, never partially, and
`merged_row is None` exactly when conflicts exist; (d) `Sample Collection Date`
prefers a row carrying a liquid/solid measurement but falls back to any dated row
rather than discarding -- 185 rows carry a date with no liquid measurement, 143 of
them standalone; (e) `OVERWRITE` is honoured only when EVERY row of the group is
TRUE, because clearing is destructive and a merged vial-day is one write;
(f) grouping matches the EXACT timepoint with no tolerance window -- setting two
rows to the same Duration is the researcher's deliberate request to merge, and
seven IDs in the team's workbook sit one day apart while genuinely recording
different sampling days; (g) `_parse_measurement_float`'s "0 means blank" rule is
used inside the merge for pH and conductivity, or a template-blank 0 reads as a
disagreement. Preserve all seven when touching this file.
```

- [ ] **Step 3: Rewrite the module docstring**

In `master_bulk_upload.py`, replace the "One row per unique experiment ID… Two rows sharing an ID and timepoint are both rejected" paragraph (`:11-16`) with:

```
Several rows may describe one vial-day. Gas is drawn and run on one date and the
liquid/solid fraction is collected later, so each fraction gets its own row;
Phase 1.5 collapses rows sharing a (normalize_id, timepoint) key into one merged
cell view. Only a field two rows fill with DIFFERENT values is a conflict, and
that vial-day is then rejected whole. Grouping matches the exact timepoint --
identical Durations are the researcher's request to merge; rows a day apart stay
separate vial-days. Replicate letters remain separate vials with their own IDs.
Cross-replicate mean and SD are computed by v_results_scalar_rollup, not carried
on the sheet.

The sample collection date column is 'Sample Collection Date'; 'Sample Date',
'Liquid/Solid Sample Date' and 'HPHT + Liquid/Solid Date Sampled' are accepted
aliases. See _COLLECTION_DATE and _HEADER_ALIASES.
```

- [ ] **Step 4: Update `MODELS.md`**

In the `ScalarResults` section, in the "**One row per vial (issue #111):**" paragraph, replace the sentence stating that two rows sharing an ID and timepoint are both rejected with: rows sharing a vial-day are **merged** field by field (gas and liquid/solid fractions are collected on different dates), and only a genuine measurement disagreement rejects that vial-day, with the affected rows and values named in the error. Add that `measurement_date` holds the **sample collection date** — preferring a row that carried a liquid/solid measurement — while `gc_run_date` is the GC **instrument run date**, which differs from the collection date on 104 of the 254 rows carrying both.

- [ ] **Step 5: Check the upload template doc**

Run:
```bash
grep -rn "Sample Date" docs/upload_templates/ MODELS.md
```
If any file names `Sample Date` as the Dashboard header, update it to `Sample Collection Date` and note the accepted aliases. If nothing matches, skip.

- [ ] **Step 6: Add the issue-log entries**

Append two entries to `docs/working/issue-log.md`:

1. Completion entry for this work, linking the spec and this plan.
2. A **separate open defect** for the `_t1`-vs-`-t1` grammar gap, which this work does not fix: `_id_match.normalize_id` treats `_t1` and `-t1` as one key, but `split_timepoint_token` accepts lowercase `-t` only. In `Master_Results_Tracker_v3.xlsx` (2026-08-11) row 95 is `SERUM_Catalyst_005a_t1` and row 214 is `SERUM_Catalyst_005a-t1`; both resolve to the same stored experiment, but row 95's token is unrecognised so its Duration of 7.0 is used instead of the day 1 its ID declares — a gas reading filed at the wrong timepoint on a real vial. Needs its own `/start-task` because it changes the canonical ID grammar used by lineage repo-wide. Note that after this change the two rows look like a merge candidate that inexplicably did not merge.

- [ ] **Step 7: Verify the docs hook synced**

Run:
```bash
git status --short
```
Expected: the `PostToolUse` hook has also written the `docs/` copies into `docs/project_context/`. `MODELS.md` at the repo root and `.claude/rules/MODELS.md` are separate files — check whether the rules copy needs the same edit.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -F <scratch-file>
```
Message:
```
[docs] Record the row-merge contract

- Amend LOCKED_COMPONENTS footnote 2; add footnote 4
- Rewrite the parser docstring and the MODELS.md vial paragraph
- Log the _t1 vs -t1 mis-filing as a separate open defect
- Tests added: no
- Docs updated: yes
```

---

## Task 8: Verification against the real workbook

**Files:** none modified unless a defect is found.

**Interfaces:** none.

- [ ] **Step 1: Run the four suites the spec names**

Run:
```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py tests/api/test_bulk_uploads.py tests/integration/test_master_results_sync_endpoint.py tests/test_time_field_guardrails.py -q
```
Expected: all PASS.

- [ ] **Step 2: Run the full suite and separate known failures**

Run:
```bash
.venv/Scripts/python.exe -m pytest -q
```
Expected: three pre-existing `pg_backup_restore` failures caused by test-order interaction — `drop_all()` wipes `experiments_test` — and nothing else. **Confirm they are pre-existing** rather than assuming:
```bash
git stash && .venv/Scripts/python.exe -m pytest -q tests/<the failing file> ; git stash pop
```
Any other failure is a regression from this work and must be fixed before proceeding.

- [ ] **Step 3: Dry-run the real workbook through the parser**

Write this to the scratchpad and run it. It parses without committing, so the dev DB is untouched.

```python
import sys
sys.path.insert(0, '.')
from database import SessionLocal
from backend.services.bulk_uploads.master_bulk_upload import MasterBulkUploadService

with open('docs/sample_data/Master_Results_Tracker_v3.xlsx', 'rb') as handle:
    data = handle.read()

db = SessionLocal()
try:
    result = MasterBulkUploadService.from_bytes_ex(db, data)
    print('created', result.created, 'updated', result.updated,
          'skipped', result.skipped)
    print('errors', len(result.errors))
    for message in result.errors:
        print('  E', message)
    print('warnings', len(result.warnings))
    for message in result.warnings:
        print('  W', message)
finally:
    db.rollback()
    db.close()
```

- [ ] **Step 4: Check the run against the spec's expected outcome**

Expected, per spec §3.4 measured on the 2026-08-11 11:37 revision:
- A merge summary reading **"Merged 72 rows into 36 vial-days"**.
- Exactly **four** conflict errors, for rows 2/185 (`SERUM_pH_001a-t1`: pH 5.22 vs 7.27, conductivity 1.286 vs 1.705, and the preferred-tier collection date), 14/57 (`SERUM_pH_004-t3`: DI H2 33.89 vs 39.01), 264/268 (`A1 Flow Leak Test`: two H2 readings), 222/272 (`GC B 500 ppm 1 mL`: gas volume).
- A mixed-`OVERWRITE` warning naming rows 154 and 204.
- A variant-spellings warning naming three vial-days.

Other errors are expected and are **not** regressions: rows whose experiment does not exist in the dev DB fail lookup, because the dev DB's real data stops around May 2026 and these are July/August experiments. Count them and confirm each is an experiment-not-found message, not a merge failure.

If the four conflict groups do not match, stop and investigate before claiming completion — that list is the spec's acceptance criterion and was measured directly.

- [ ] **Step 5: Walk the acceptance criteria**

Open spec §8 and tick each of its 20 boxes against a specific test name or the Step 3 output. Any box without evidence is unfinished work, not a formality.

- [ ] **Step 6: Commit any fixes and report**

If Steps 1-5 required changes, commit them with an `[fix]` message. Then report: the four suites' results, the full-suite result with the three known failures named, and the real-workbook numbers against §3.4.

---

## Self-Review

**Spec coverage.** §1.3 P0 → Task 1. §3.1 grouping → Task 3 Step 3. §3.2 four field classes → Task 2 Steps 3-4. §3.3 single rows → Task 3 Step 3 (`len(members) == 1` short-circuit), tested by `test_no_merge_summary_when_nothing_merged`. §3.4 expected outcome → Task 8 Step 4. §4.1 → Task 1. §4.2 `_merge_group` → Task 2. §4.3 control flow → Task 3. §4.4 errors and warnings → Task 3 Step 5 and Task 4 Step 3. §4.5 counts, `feedbacks.rows`, vial-day denominators → Task 3 Step 4 and Task 6. §6 test list → Tasks 1, 2, 3, 4, 5, 6. §7 docs → Task 7. §8 acceptance → Task 8 Step 5.

**Two spec defects corrected here.** §4.4's merge-summary example says "Merged 70 rows into 35 vial-days"; the measured figures for the current workbook are 72 rows into 36 vial-days, used in Task 8 Step 4. §7 references a §1.6 that was removed from the spec; the `_t1`/`-t1` evidence it pointed at is carried in full in Task 7 Step 6.

**One deliberate deviation.** The spec calls the merged-row builder `_merge_group` returning `(Optional[Dict], List[str], List[str])`. This plan returns `(Optional[MergedGroup], List[str], MergeNotes)` — the dict is wrapped so the group's resolved `overwrite` flag travels with its cells rather than being recomputed at the call site, and `notes` is typed rather than a bag of strings so Task 4 can group warnings by kind. `merged.cells` is the plain dict the spec requires.

**Interface consistency.** `_merge_group` is declared in Task 2's Interfaces and consumed in Task 3 Step 3 with the same signature. `MergeNotes` field names (`run_date_disagreements`, `overwrite_mixed`, `spellings`, `fallback_date_disagreement`) are identical in Task 2's dataclass, Task 2's tests, and Task 4's warning code. `merged_entries`' seven-tuple shape is declared in Task 3's Interfaces and unpacked identically in Task 3 Step 4. `_COLLECTION_DATE` is created in Task 1 and used in Tasks 2, 4 and 7. Test helpers `_scalar_for` and `_cells` are defined once (Tasks 1 and 2) and reused later.

**Known risk carried into Task 5 Step 6.** `test_duplicate_detected_after_timepoint_token_resolution` is the one test whose rewrite cannot be fully specified without reading its fixture, because whether its two rows are complementary or conflicting depends on cell values not visible in the spec. The step says to read it first and states the property to preserve.
