# Flexible Elemental Composition Importer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `FlexibleElementalCompositionService` that accepts user-prepared wide-format Excel files with loose headers, plus a live DB-driven downloadable template — wired to a new POST endpoint and a new bulk-upload card.

**Architecture:** New `_elemental_helpers.py` holds the shared write helper currently locked in `actlabs_titration_data.py`. New `elemental_composition.py` holds `FlexibleElementalCompositionService` and `build_flexible_composition_template_bytes`. The unified `/templates/{type}` endpoint gains a `db` dependency and a branch for the new type; the existing static-template path is untouched.

**Tech Stack:** Python 3.11, SQLAlchemy 2.x, pandas, openpyxl, FastAPI, structlog, pytest (PostgreSQL test DB), React 18, TypeScript.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/services/bulk_uploads/_elemental_helpers.py` | **Create** | Shared `_write_elemental_record` helper |
| `backend/services/bulk_uploads/actlabs_titration_data.py` | **Modify** (1 line) | Replace function def with import from `_elemental_helpers` |
| `backend/services/bulk_uploads/elemental_composition.py` | **Create** | `FlexibleElementalCompositionService` + `build_flexible_composition_template_bytes` |
| `backend/api/routers/bulk_uploads.py` | **Modify** | Add POST endpoint; add `db` dep + branch to template endpoint |
| `frontend/src/api/bulkUploads.ts` | **Modify** | New `TemplateType` value + `uploadFlexibleElementalComposition` |
| `frontend/src/pages/BulkUploads.tsx` | **Modify** | New `UploadRow` card |
| `tests/services/bulk_uploads/test_flexible_elemental.py` | **Create** | All service + template unit tests |
| `tests/api/test_bulk_uploads_flexible.py` | **Create** | API integration tests |
| `docs/upload_templates/elemental_composition_flexible.md` | **Create** | Upload format documentation |

---

## Task 1 — Extract `_write_elemental_record` to shared helper

**Files:**
- Create: `backend/services/bulk_uploads/_elemental_helpers.py`
- Modify: `backend/services/bulk_uploads/actlabs_titration_data.py` (lines 14–47)

> No new tests needed — the existing `tests/services/bulk_uploads/test_elemental_composition.py` covers this helper indirectly. Run them to confirm nothing breaks after the move.

- [ ] **Step 1: Create `_elemental_helpers.py`**

```python
# backend/services/bulk_uploads/_elemental_helpers.py
from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from sqlalchemy.orm import Session

from database import Analyte, ElementalAnalysis

if TYPE_CHECKING:
    pass


def _write_elemental_record(
    db: Session,
    ext_analysis_id: int,
    sample_id: str,
    analyte: "Analyte",
    value: float,
    overwrite: bool,
) -> "Tuple[int, int]":
    """Write a single ElementalAnalysis record. Returns (created_delta, updated_delta).

    When overwrite=False, any existing record is preserved and (0, 0) is returned.
    When overwrite=True, any existing record is updated and (0, 1) is returned.
    Null/blank values must never be passed to this function.
    """
    existing = (
        db.query(ElementalAnalysis)
        .filter(
            ElementalAnalysis.external_analysis_id == ext_analysis_id,
            ElementalAnalysis.analyte_id == analyte.id,
        )
        .first()
    )
    if existing:
        if overwrite:
            existing.analyte_composition = value
            return 0, 1
        return 0, 0
    db.add(ElementalAnalysis(
        external_analysis_id=ext_analysis_id,
        sample_id=sample_id,
        analyte_id=analyte.id,
        analyte_composition=value,
    ))
    return 1, 0
```

- [ ] **Step 2: Replace definition in `actlabs_titration_data.py` with import**

Lines 14–47 are the entire `_write_elemental_record` function. Delete them and insert the import at that same location (after the existing stdlib/third-party imports that end at line 12):

```python
from ._elemental_helpers import _write_elemental_record  # noqa: F401
```

Do not move it above line 14 — the lines above it (1–12) are the existing `from __future__` and third-party imports that must stay first.

- [ ] **Step 3: Run existing elemental tests**

```bash
pytest tests/services/bulk_uploads/test_elemental_composition.py -v
```

Expected: all tests pass (same count as before).

- [ ] **Step 4: Commit**

```bash
git add backend/services/bulk_uploads/_elemental_helpers.py backend/services/bulk_uploads/actlabs_titration_data.py
git commit -m "[#4] Extract _write_elemental_record to _elemental_helpers"
```

---

## Task 2 — Service skeleton + pure-function unit tests

**Files:**
- Create: `backend/services/bulk_uploads/elemental_composition.py` (skeleton)
- Create: `tests/services/bulk_uploads/test_flexible_elemental.py` (pure-function section)

These tests cover `_parse_header`, `_normalize_sample_id`, and `_coerce_numeric` — no DB needed.

- [ ] **Step 1: Create service skeleton with helper functions**

```python
# backend/services/bulk_uploads/elemental_composition.py
from __future__ import annotations

import io
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd
import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import Analyte, ElementalAnalysis, SampleInfo
from database.models.analysis import ExternalAnalysis

from ._elemental_helpers import _write_elemental_record

log = structlog.get_logger(__name__)

# Matches: "Symbol (unit)", "Symbol [unit]", or bare "Symbol"
_HEADER_RE = re.compile(r'^(?P<symbol>[^\(\[\]]+?)\s*(?:[\(\[](?P<unit>[^\)\]]+)[\)\]])?$')
_NULL_STRINGS = {"nd", "na", "n/a", ""}


def _parse_header(header: str) -> Tuple[str, Optional[str]]:
    """Parse a column header into (symbol, unit).

    Examples:
        "Fe (%)"    → ("Fe", "%")
        "SiO2 [ppm]" → ("SiO2", "ppm")
        "MgO"       → ("MgO", None)
    """
    m = _HEADER_RE.match(header.strip())
    if m:
        return m.group("symbol").strip(), m.group("unit")
    return header.strip(), None


def _normalize_sample_id(sid: str) -> str:
    """Strip hyphens, underscores, spaces and lowercase for fuzzy matching."""
    return "".join(ch for ch in sid.lower() if ch not in ("-", "_", " "))


def _coerce_numeric(val) -> Optional[float]:
    """Coerce a cell value to float; return None for nulls, nd, n/a, or unparseable text.

    Leading < or > characters are stripped before parsing (detection-limit notation).
    """
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    s = str(val).strip()
    if s.lower() in _NULL_STRINGS:
        return None
    s = s.lstrip("<>").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None
```

- [ ] **Step 2: Write failing tests for the pure helpers**

```python
# tests/services/bulk_uploads/test_flexible_elemental.py
"""Tests for FlexibleElementalCompositionService and build_flexible_composition_template_bytes."""
from __future__ import annotations

import io

import openpyxl
import pytest
from sqlalchemy.orm import Session

from database import Analyte, ElementalAnalysis, SampleInfo
from database.models.analysis import ExternalAnalysis
from backend.services.bulk_uploads.elemental_composition import (
    FlexibleElementalCompositionService,
    _coerce_numeric,
    _normalize_sample_id,
    _parse_header,
    build_flexible_composition_template_bytes,
)

from .excel_helpers import make_excel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_sample(db: Session, sample_id: str) -> SampleInfo:
    s = SampleInfo(sample_id=sample_id)
    db.add(s)
    db.flush()
    return s


def _seed_analyte(db: Session, symbol: str, unit: str = "wt%") -> Analyte:
    a = Analyte(analyte_symbol=symbol, unit=unit)
    db.add(a)
    db.flush()
    return a


# ---------------------------------------------------------------------------
# _parse_header
# ---------------------------------------------------------------------------

def test_parse_header_symbol_with_parens():
    assert _parse_header("Fe (%)") == ("Fe", "%")

def test_parse_header_symbol_with_brackets():
    assert _parse_header("SiO2 [ppm]") == ("SiO2", "ppm")

def test_parse_header_bare_symbol():
    symbol, unit = _parse_header("MgO")
    assert symbol == "MgO"
    assert unit is None

def test_parse_header_strips_whitespace():
    symbol, _ = _parse_header("  Al2O3  ")
    assert symbol == "Al2O3"


# ---------------------------------------------------------------------------
# _normalize_sample_id
# ---------------------------------------------------------------------------

def test_normalize_strips_hyphens():
    assert _normalize_sample_id("DUNE-001") == "dune001"

def test_normalize_strips_underscores():
    assert _normalize_sample_id("DUNE_001") == "dune001"

def test_normalize_strips_spaces():
    assert _normalize_sample_id("DUNE 001") == "dune001"

def test_normalize_lowercases():
    assert _normalize_sample_id("ABC") == "abc"


# ---------------------------------------------------------------------------
# _coerce_numeric
# ---------------------------------------------------------------------------

def test_coerce_strips_less_than():
    assert _coerce_numeric("<0.01") == pytest.approx(0.01)

def test_coerce_strips_greater_than():
    assert _coerce_numeric(">100") == pytest.approx(100.0)

def test_coerce_nd_returns_none():
    assert _coerce_numeric("nd") is None

def test_coerce_na_returns_none():
    assert _coerce_numeric("n/a") is None

def test_coerce_blank_returns_none():
    assert _coerce_numeric("") is None

def test_coerce_nan_returns_none():
    import math
    assert _coerce_numeric(float("nan")) is None

def test_coerce_normal_float():
    assert _coerce_numeric("47.2") == pytest.approx(47.2)
```

- [ ] **Step 3: Run tests — expect ImportError (FlexibleElementalCompositionService not yet defined)**

```bash
pytest tests/services/bulk_uploads/test_flexible_elemental.py::test_parse_header_symbol_with_parens -v
```

Expected: ImportError or similar — the class doesn't exist yet.

- [ ] **Step 4: The pure-helper tests pass already since the functions are defined**

```bash
pytest tests/services/bulk_uploads/test_flexible_elemental.py -k "parse_header or normalize or coerce" -v
```

Expected: all helper tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/elemental_composition.py tests/services/bulk_uploads/test_flexible_elemental.py
git commit -m "[#4] Add elemental_composition.py skeleton and pure-helper tests"
```

---

## Task 3 — `FlexibleElementalCompositionService` implementation + tests

**Files:**
- Modify: `backend/services/bulk_uploads/elemental_composition.py` (add service class)
- Modify: `tests/services/bulk_uploads/test_flexible_elemental.py` (add DB tests)

- [ ] **Step 1: Add the remaining service tests (DB tests)**

Append to `tests/services/bulk_uploads/test_flexible_elemental.py`:

```python
# ---------------------------------------------------------------------------
# FlexibleElementalCompositionService — sample column detection
# ---------------------------------------------------------------------------

def test_detects_sample_column_named_Sample(db_session: Session):
    _seed_sample(db_session, "S001")
    _seed_analyte(db_session, "Fe")
    xlsx = make_excel(["Sample", "Fe"], [["S001", 10.5]])
    created, _, _, errors, _ = FlexibleElementalCompositionService.bulk_upsert_from_excel(
        db_session, xlsx
    )
    assert errors == []
    assert created == 1


def test_detects_sample_column_named_Sample_ID(db_session: Session):
    _seed_sample(db_session, "S001")
    _seed_analyte(db_session, "Fe")
    xlsx = make_excel(["Sample ID", "Fe"], [["S001", 10.5]])
    created, _, _, errors, _ = FlexibleElementalCompositionService.bulk_upsert_from_excel(
        db_session, xlsx
    )
    assert errors == []
    assert created == 1


def test_detects_sample_column_named_sample_id(db_session: Session):
    _seed_sample(db_session, "S001")
    _seed_analyte(db_session, "Fe")
    xlsx = make_excel(["sample_id", "Fe"], [["S001", 10.5]])
    created, _, _, errors, _ = FlexibleElementalCompositionService.bulk_upsert_from_excel(
        db_session, xlsx
    )
    assert errors == []
    assert created == 1


def test_no_sample_column_returns_error(db_session: Session):
    xlsx = make_excel(["Code", "Fe"], [["S001", 10.5]])
    created, _, _, errors, _ = FlexibleElementalCompositionService.bulk_upsert_from_excel(
        db_session, xlsx
    )
    assert created == 0
    assert any("sample" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# FlexibleElementalCompositionService — header parsing + analyte matching
# ---------------------------------------------------------------------------

def test_header_with_unit_suffix_matched_to_analyte(db_session: Session):
    """'Fe (%)' header should match the 'Fe' analyte."""
    _seed_sample(db_session, "S001")
    _seed_analyte(db_session, "Fe", unit="%")
    xlsx = make_excel(["sample_id", "Fe (%)"], [["S001", 12.3]])
    created, _, _, errors, _ = FlexibleElementalCompositionService.bulk_upsert_from_excel(
        db_session, xlsx
    )
    assert errors == []
    assert created == 1


def test_analyte_lookup_is_case_insensitive(db_session: Session):
    _seed_sample(db_session, "S001")
    _seed_analyte(db_session, "SiO2")
    xlsx = make_excel(["sample_id", "sio2"], [["S001", 47.2]])
    created, _, _, errors, _ = FlexibleElementalCompositionService.bulk_upsert_from_excel(
        db_session, xlsx
    )
    assert errors == []
    assert created == 1


def test_unknown_analyte_skipped_in_strict_mode(db_session: Session):
    _seed_sample(db_session, "S001")
    # No 'Zr' analyte seeded
    xlsx = make_excel(["sample_id", "Zr"], [["S001", 5.0]])
    created, _, _, errors, warnings = FlexibleElementalCompositionService.bulk_upsert_from_excel(
        db_session, xlsx
    )
    assert created == 0
    assert errors == []
    assert any("Zr" in w for w in warnings)  # unknown analyte surfaces as a warning, not an error


def test_unknown_analyte_created_in_auto_create_mode(db_session: Session):
    _seed_sample(db_session, "S001")
    xlsx = make_excel(["sample_id", "Zr (ppm)"], [["S001", 5.0]])
    created, _, _, errors, _ = FlexibleElementalCompositionService.bulk_upsert_from_excel(
        db_session, xlsx, auto_create=True, default_unit="ppm"
    )
    assert errors == []
    assert created == 1
    analyte = db_session.query(Analyte).filter_by(analyte_symbol="Zr").first()
    assert analyte is not None


# ---------------------------------------------------------------------------
# FlexibleElementalCompositionService — fuzzy sample lookup
# ---------------------------------------------------------------------------

def test_fuzzy_sample_match_hyphen_vs_underscore(db_session: Session):
    """DUNE-001 in the DB should be found when the file contains DUNE_001."""
    _seed_sample(db_session, "DUNE-001")
    _seed_analyte(db_session, "Fe")
    xlsx = make_excel(["sample_id", "Fe"], [["DUNE_001", 8.5]])
    created, _, _, errors, _ = FlexibleElementalCompositionService.bulk_upsert_from_excel(
        db_session, xlsx
    )
    assert errors == []
    assert created == 1


def test_unknown_sample_records_error(db_session: Session):
    _seed_analyte(db_session, "Fe")
    xlsx = make_excel(["sample_id", "Fe"], [["NOTEXIST", 8.5]])
    _, _, _, errors, _ = FlexibleElementalCompositionService.bulk_upsert_from_excel(
        db_session, xlsx
    )
    assert any("NOTEXIST" in e for e in errors)


# ---------------------------------------------------------------------------
# FlexibleElementalCompositionService — ExternalAnalysis linkage
# ---------------------------------------------------------------------------

def test_external_analysis_id_set_on_created_row(db_session: Session):
    """Every ElementalAnalysis row must have a non-null external_analysis_id."""
    _seed_sample(db_session, "S001")
    _seed_analyte(db_session, "Fe")
    xlsx = make_excel(["sample_id", "Fe"], [["S001", 10.0]])
    FlexibleElementalCompositionService.bulk_upsert_from_excel(db_session, xlsx)
    db_session.flush()
    row = db_session.query(ElementalAnalysis).first()
    assert row is not None
    assert row.external_analysis_id is not None


def test_shares_external_analysis_stub_with_strict_service(db_session: Session):
    """Flexible and strict services writing for the same sample share one ExternalAnalysis stub."""
    from backend.services.bulk_uploads.actlabs_titration_data import ElementalCompositionService

    _seed_sample(db_session, "S001")
    _seed_analyte(db_session, "Fe")
    _seed_analyte(db_session, "SiO2")

    # Strict service writes first
    strict_xlsx = make_excel(["sample_id", "SiO2"], [["S001", 47.2]])
    ElementalCompositionService.bulk_upsert_wide_from_excel(db_session, strict_xlsx)
    db_session.flush()

    # Flexible service writes second
    flex_xlsx = make_excel(["sample_id", "Fe (%)"], [["S001", 10.5]])
    FlexibleElementalCompositionService.bulk_upsert_from_excel(db_session, flex_xlsx)
    db_session.flush()

    stubs = (
        db_session.query(ExternalAnalysis)
        .filter_by(sample_id="S001", analysis_type="Bulk Elemental Composition")
        .all()
    )
    assert len(stubs) == 1, "Both services should share one ExternalAnalysis stub"


# ---------------------------------------------------------------------------
# FlexibleElementalCompositionService — overwrite behaviour
# ---------------------------------------------------------------------------

def test_overwrite_false_preserves_existing_value(db_session: Session):
    _seed_sample(db_session, "S001")
    analyte = _seed_analyte(db_session, "Fe")
    xlsx = make_excel(["sample_id", "Fe"], [["S001", 10.0]])
    FlexibleElementalCompositionService.bulk_upsert_from_excel(db_session, xlsx)
    db_session.flush()

    xlsx2 = make_excel(["sample_id", "Fe"], [["S001", 99.0]])
    FlexibleElementalCompositionService.bulk_upsert_from_excel(db_session, xlsx2, overwrite=False)
    db_session.flush()

    row = db_session.query(ElementalAnalysis).filter_by(analyte_id=analyte.id).first()
    assert row.analyte_composition == pytest.approx(10.0)


def test_overwrite_true_updates_existing_value(db_session: Session):
    _seed_sample(db_session, "S001")
    analyte = _seed_analyte(db_session, "Fe")
    xlsx = make_excel(["sample_id", "Fe"], [["S001", 10.0]])
    FlexibleElementalCompositionService.bulk_upsert_from_excel(db_session, xlsx)
    db_session.flush()

    xlsx2 = make_excel(["sample_id", "Fe"], [["S001", 99.0]])
    _, updated, _, errors, _ = FlexibleElementalCompositionService.bulk_upsert_from_excel(
        db_session, xlsx2, overwrite=True
    )
    db_session.flush()
    assert errors == []
    assert updated == 1
    row = db_session.query(ElementalAnalysis).filter_by(analyte_id=analyte.id).first()
    assert row.analyte_composition == pytest.approx(99.0)
```

- [ ] **Step 2: Run tests — expect failures (class not implemented)**

```bash
pytest tests/services/bulk_uploads/test_flexible_elemental.py -k "not parse_header and not normalize and not coerce and not template" -v
```

Expected: ImportError or AttributeError on `FlexibleElementalCompositionService`.

- [ ] **Step 3: Implement `FlexibleElementalCompositionService` in `elemental_composition.py`**

Append to `backend/services/bulk_uploads/elemental_composition.py`:

```python
class FlexibleElementalCompositionService:
    """Importer for user-prepared wide-format elemental composition files.

    Unlike ElementalCompositionService, this class:
    - Detects any column containing 'sample' as the sample ID column.
    - Parses headers of the form 'Symbol (unit)', 'Symbol [unit]', or bare 'Symbol'.
    - Uses fuzzy/delimiter-insensitive SampleInfo lookup.
    - Skips unknown analytes by default (strict mode); auto-creates when auto_create=True.

    NOTE: diagnose() is internal only. A future enhancement could expose it as a
    POST /diagnose endpoint to power a UI preview-before-commit flow.
    """

    @classmethod
    def bulk_upsert_from_excel(
        cls,
        db: Session,
        file_bytes: bytes,
        overwrite: bool = False,
        auto_create: bool = False,
        default_unit: Optional[str] = None,
    ) -> Tuple[int, int, int, List[str], List[str]]:
        """Upsert ElementalAnalysis from a flexible wide-format Excel file.

        Returns (created, updated, skipped_rows, errors, warnings).
        warnings contains one entry per unknown analyte column (strict mode only).
        """
        errors: List[str] = []
        warnings: List[str] = []
        created = updated = skipped = 0

        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return 0, 0, 0, [f"Failed to read Excel: {e}"]

        df.columns = [str(c).strip() for c in df.columns]

        # Detect sample column — first header containing 'sample' (case-insensitive)
        sample_col: Optional[str] = None
        for c in df.columns:
            if "sample" in c.lower():
                sample_col = c
                break
        if sample_col is None:
            return 0, 0, 0, ["No sample column detected. Column header must contain 'sample'."]

        analyte_cols = [c for c in df.columns if c != sample_col]
        if not analyte_cols:
            return 0, 0, 0, ["No analyte columns detected."]

        # Parse headers → {col_name: (symbol, unit)}
        parsed: Dict[str, Tuple[str, Optional[str]]] = {
            col: _parse_header(col) for col in analyte_cols
        }

        # Load known analytes
        all_analytes = db.query(Analyte).all()
        symbol_map: Dict[str, Analyte] = {a.analyte_symbol.lower(): a for a in all_analytes}

        if auto_create:
            for col, (symbol, unit) in parsed.items():
                if symbol.lower() not in symbol_map:
                    effective_unit = unit or default_unit or ""
                    new_a = Analyte(analyte_symbol=symbol, unit=effective_unit)
                    db.add(new_a)
                    db.flush()
                    symbol_map[symbol.lower()] = new_a
        else:
            for col, (symbol, _unit) in parsed.items():
                if symbol.lower() not in symbol_map:
                    log.warning("flexible_elemental_unknown_analyte", symbol=symbol)
                    warnings.append(f"Unknown analyte '{symbol}' skipped (not in database).")

        # ExternalAnalysis stub cache per resolved sample_id
        ext_cache: Dict[str, int] = {}

        def _get_ext_id(resolved_sid: str) -> int:
            if resolved_sid in ext_cache:
                return ext_cache[resolved_sid]
            stub = (
                db.query(ExternalAnalysis)
                .filter_by(sample_id=resolved_sid, analysis_type="Bulk Elemental Composition")
                .first()
            )
            if not stub:
                stub = ExternalAnalysis(
                    sample_id=resolved_sid, analysis_type="Bulk Elemental Composition"
                )
                db.add(stub)
                db.flush()
            ext_cache[resolved_sid] = stub.id
            return stub.id

        for idx, row in df.iterrows():
            try:
                raw_sid = str(row.get(sample_col) or "").strip()
                if not raw_sid:
                    skipped += 1
                    continue

                sid_norm = _normalize_sample_id(raw_sid)
                sample = db.query(SampleInfo).filter(
                    func.lower(
                        func.replace(
                            func.replace(
                                func.replace(SampleInfo.sample_id, "-", ""),
                                "_", "",
                            ),
                            " ", "",
                        )
                    ) == sid_norm
                ).first()
                if not sample:
                    errors.append(f"Row {idx + 2}: sample '{raw_sid}' not found")
                    continue

                ext_id = _get_ext_id(sample.sample_id)

                for col, (symbol, _unit) in parsed.items():
                    analyte = symbol_map.get(symbol.lower())
                    if not analyte:
                        continue
                    fval = _coerce_numeric(row.get(col))
                    if fval is None:
                        continue
                    dc, du = _write_elemental_record(
                        db, ext_id, sample.sample_id, analyte, fval, overwrite
                    )
                    created += dc
                    updated += du
            except Exception as e:
                errors.append(f"Row {idx + 2}: {e}")

        return created, updated, skipped, errors, warnings

    @classmethod
    def diagnose(cls, db: Session, file_bytes: bytes) -> Dict[str, object]:
        """Preview file structure without writing to the database.

        Returns a dict with keys:
            detected_sample_col: str | None
            parsed_analytes: list[{col, symbol, unit}]
            unrecognised_cols: list[str]   (symbol not in Analyte table)
            row_count: int
            sample_match_rate: float       (0.0–1.0)

        NOTE (future): Expose as POST /api/bulk-uploads/elemental-composition-flexible/diagnose
        to power a UI preview-before-commit step.
        """
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e:
            return {"error": str(e)}

        df.columns = [str(c).strip() for c in df.columns]

        sample_col: Optional[str] = next(
            (c for c in df.columns if "sample" in c.lower()), None
        )
        analyte_cols = [c for c in df.columns if c != sample_col] if sample_col else []

        all_analytes = db.query(Analyte).all()
        symbol_map = {a.analyte_symbol.lower(): a for a in all_analytes}

        parsed_analytes = []
        unrecognised = []
        for col in analyte_cols:
            symbol, unit = _parse_header(col)
            entry = {"col": col, "symbol": symbol, "unit": unit}
            parsed_analytes.append(entry)
            if symbol.lower() not in symbol_map:
                unrecognised.append(col)

        # Sample match rate (first 100 rows)
        matched = total = 0
        if sample_col is not None:
            for val in df[sample_col].head(100):
                raw = str(val or "").strip()
                if not raw:
                    continue
                total += 1
                sid_norm = _normalize_sample_id(raw)
                hit = db.query(SampleInfo).filter(
                    func.lower(
                        func.replace(
                            func.replace(
                                func.replace(SampleInfo.sample_id, "-", ""),
                                "_", "",
                            ),
                            " ", "",
                        )
                    ) == sid_norm
                ).first()
                if hit:
                    matched += 1

        return {
            "detected_sample_col": sample_col,
            "parsed_analytes": parsed_analytes,
            "unrecognised_cols": unrecognised,
            "row_count": len(df),
            "sample_match_rate": (matched / total) if total else 0.0,
        }
```

- [ ] **Step 4: Run service tests**

```bash
pytest tests/services/bulk_uploads/test_flexible_elemental.py -k "not template" -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/elemental_composition.py tests/services/bulk_uploads/test_flexible_elemental.py
git commit -m "[#4] Add FlexibleElementalCompositionService with tests"
```

---

## Task 4 — Template builder tests + implementation

**Files:**
- Modify: `backend/services/bulk_uploads/elemental_composition.py` (add `build_flexible_composition_template_bytes`)
- Modify: `tests/services/bulk_uploads/test_flexible_elemental.py` (add template tests)

- [ ] **Step 1: Add template tests**

Append to `tests/services/bulk_uploads/test_flexible_elemental.py`:

```python
# ---------------------------------------------------------------------------
# build_flexible_composition_template_bytes
# ---------------------------------------------------------------------------

def test_template_with_no_analytes_has_sample_id_only(db_session: Session):
    """Empty analyte catalogue → single-column file with sample_id."""
    xlsx_bytes = build_flexible_composition_template_bytes(db_session)
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb["Template"]
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert headers == ["sample_id"]


def test_template_with_no_analytes_has_instructions_sheet(db_session: Session):
    wb = openpyxl.load_workbook(io.BytesIO(build_flexible_composition_template_bytes(db_session)))
    assert "INSTRUCTIONS" in wb.sheetnames


def test_template_columns_are_alphabetical(db_session: Session):
    _seed_analyte(db_session, "SiO2", "wt%")
    _seed_analyte(db_session, "Al2O3", "wt%")
    _seed_analyte(db_session, "Fe", "%")
    wb = openpyxl.load_workbook(io.BytesIO(build_flexible_composition_template_bytes(db_session)))
    ws = wb["Template"]
    headers = [ws.cell(row=1, column=c).value for c in range(2, ws.max_column + 1)]
    assert headers == sorted(headers)


def test_template_header_format_is_symbol_unit(db_session: Session):
    _seed_analyte(db_session, "Fe", "%")
    wb = openpyxl.load_workbook(io.BytesIO(build_flexible_composition_template_bytes(db_session)))
    ws = wb["Template"]
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert "Fe (%)" in headers


def test_template_sio2_roundtrips_as_symbol(db_session: Session):
    """SiO2 symbol with special chars round-trips through the template header format."""
    _seed_analyte(db_session, "SiO2", "wt%")
    wb = openpyxl.load_workbook(io.BytesIO(build_flexible_composition_template_bytes(db_session)))
    ws = wb["Template"]
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert "SiO2 (wt%)" in headers
    # Verify _parse_header can extract the symbol back
    symbol, unit = _parse_header("SiO2 (wt%)")
    assert symbol == "SiO2"
    assert unit == "wt%"
```

- [ ] **Step 2: Run template tests — expect failure**

```bash
pytest tests/services/bulk_uploads/test_flexible_elemental.py -k "template" -v
```

Expected: ImportError on `build_flexible_composition_template_bytes`.

- [ ] **Step 3: Implement `build_flexible_composition_template_bytes`**

Append to `backend/services/bulk_uploads/elemental_composition.py`:

```python
def build_flexible_composition_template_bytes(db: Session) -> bytes:
    """Generate a downloadable Excel template from live analyte data.

    Column A: sample_id
    Remaining columns: one per Analyte ordered alphabetically, header = "Symbol (unit)"

    If no analytes exist in the database, returns a single-column file plus an
    INSTRUCTIONS sheet explaining that analytes must be defined first.
    """
    import openpyxl
    from openpyxl.styles import Font

    analytes = db.query(Analyte).order_by(Analyte.analyte_symbol).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template"

    headers = ["sample_id"] + [f"{a.analyte_symbol} ({a.unit})" for a in analytes]
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True)

    if not analytes:
        instr = wb.create_sheet("INSTRUCTIONS")
        instr["A1"] = "No analytes are defined in the system."
        instr["A2"] = (
            "Use the 'Analyte Definitions' bulk upload to add analytes first, "
            "then re-download this template to get the correct columns."
        )
        instr["A1"].font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Run all template tests**

```bash
pytest tests/services/bulk_uploads/test_flexible_elemental.py -k "template" -v
```

Expected: all PASS.

- [ ] **Step 5: Run full test file**

```bash
pytest tests/services/bulk_uploads/test_flexible_elemental.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/bulk_uploads/elemental_composition.py tests/services/bulk_uploads/test_flexible_elemental.py
git commit -m "[#4] Add build_flexible_composition_template_bytes with tests"
```

---

## Task 5 — POST endpoint + API integration test

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py`
- Create: `tests/api/test_bulk_uploads_flexible.py`

- [ ] **Step 1: Write failing API test**

```python
# tests/api/test_bulk_uploads_flexible.py
"""API integration tests for the flexible elemental composition endpoints.

Uses the shared `client` and `db_session` fixtures from tests/api/conftest.py.
No local fixture overrides needed.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from database import Analyte, SampleInfo

from tests.services.bulk_uploads.excel_helpers import make_excel


def _seed_sample(db: Session, sample_id: str) -> SampleInfo:
    s = SampleInfo(sample_id=sample_id)
    db.add(s)
    db.flush()
    return s


def _seed_analyte(db: Session, symbol: str, unit: str = "wt%") -> Analyte:
    a = Analyte(analyte_symbol=symbol, unit=unit)
    db.add(a)
    db.flush()
    return a


def test_post_flexible_elemental_returns_200_with_created_count(
    client: TestClient, db_session: Session
):
    _seed_sample(db_session, "S001")
    _seed_analyte(db_session, "Fe")
    xlsx = make_excel(["sample_id", "Fe (%)"], [["S001", 12.3]])
    response = client.post(
        "/api/bulk-uploads/elemental-composition-flexible",
        files={"file": ("test.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == 1
    assert data["errors"] == []


def test_post_flexible_elemental_malformed_file_returns_errors(
    client: TestClient, db_session: Session
):
    response = client.post(
        "/api/bulk-uploads/elemental-composition-flexible",
        files={"file": ("bad.xlsx", b"not an excel file", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == 0
    assert len(data["errors"]) > 0
```

- [ ] **Step 2: Run test — expect 404 (endpoint not yet defined)**

```bash
pytest tests/api/test_bulk_uploads_flexible.py::test_post_flexible_elemental_returns_200_with_created_count -v
```

Expected: FAIL with 404 or connection error.

- [ ] **Step 3: Add the POST endpoint to `bulk_uploads.py`**

Add after the existing `/elemental-composition` endpoint (around line 370):

```python
@router.post("/elemental-composition-flexible", response_model=UploadResponse)
async def upload_flexible_elemental_composition(
    file: UploadFile = File(...),
    overwrite: bool = Query(False, description="Overwrite existing values"),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload flexible elemental composition (wide-format Excel with loose headers).

    Accepts any column header containing 'sample' as the sample ID column.
    Analyte headers may be bare symbols ('Fe') or 'Symbol (unit)' / 'Symbol [unit]'.
    Unknown analytes are skipped with a warning; pass overwrite=true to replace existing values.
    """
    from backend.services.bulk_uploads.elemental_composition import FlexibleElementalCompositionService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        created, updated, skipped, errors, warnings = FlexibleElementalCompositionService.bulk_upsert_from_excel(
            db, file_bytes, overwrite=overwrite
        )
        if not errors:
            db.commit()
        else:
            db.rollback()
    except Exception as exc:
        db.rollback()
        log.error("flexible_elemental_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        warnings=warnings,
        message=f"Flexible Elemental: {created} created, {updated} updated",
    )
```

- [ ] **Step 4: Run API tests**

```bash
pytest tests/api/test_bulk_uploads_flexible.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/bulk_uploads.py tests/api/test_bulk_uploads_flexible.py
git commit -m "[#4] Add POST /elemental-composition-flexible endpoint with tests"
```

---

## Task 6 — Dynamic template via unified `/templates/{type}` endpoint

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py` (template endpoint + `_get_template_bytes`)
- Modify: `tests/api/test_bulk_uploads_flexible.py` (add template download test)

- [ ] **Step 1: Add template download test**

Append to `tests/api/test_bulk_uploads_flexible.py`:

```python
def test_get_flexible_template_returns_xlsx(client: TestClient, db_session: Session):
    _seed_analyte(db_session, "Fe", "%")
    response = client.get("/api/bulk-uploads/templates/elemental-composition-flexible")
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]


def test_get_flexible_template_empty_analytes_returns_xlsx(
    client: TestClient, db_session: Session
):
    """No analytes → still returns a valid xlsx (not a 500)."""
    response = client.get("/api/bulk-uploads/templates/elemental-composition-flexible")
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]
```

- [ ] **Step 2: Run tests — expect 404**

```bash
pytest tests/api/test_bulk_uploads_flexible.py -k "template" -v
```

Expected: FAIL with 404.

- [ ] **Step 3: Add `db` dependency to `download_template` endpoint and branch for the new type**

In `backend/api/routers/bulk_uploads.py`, modify the `download_template` endpoint:

```python
@router.get("/templates/{upload_type}")
async def download_template(
    upload_type: str,
    mode: Optional[str] = Query(None, description="Template mode (e.g. 'experiment' for XRD)"),
    db: Session = Depends(get_db),                          # ADD THIS
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> StreamingResponse:
    """Download an Excel upload template for the specified upload type."""
    if upload_type in _NO_TEMPLATE:
        raise HTTPException(
            status_code=404,
            detail=f"No template available for '{upload_type}'. "
                   "This upload type uses instrument exports or fixed-format files.",
        )

    # DB-driven template — handled before the static generator
    if upload_type == "elemental-composition-flexible":
        from backend.services.bulk_uploads.elemental_composition import build_flexible_composition_template_bytes  # noqa: PLC0415
        try:
            template_bytes = build_flexible_composition_template_bytes(db)
        except Exception as exc:
            log.error("flexible_template_generation_failed", error=str(exc))
            raise HTTPException(status_code=500, detail=f"Failed to generate template: {exc}")
        return StreamingResponse(
            io.BytesIO(template_bytes),
            media_type=_XLSX_MIME,
            headers={"Content-Disposition": 'attachment; filename="elemental-composition-flexible-template.xlsx"'},
        )

    try:
        template_bytes = _get_template_bytes(upload_type, mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.error("template_generation_failed", upload_type=upload_type, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to generate template: {exc}")

    filename = f"{upload_type}-template.xlsx"
    return StreamingResponse(
        io.BytesIO(template_bytes),
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Run all API tests**

```bash
pytest tests/api/test_bulk_uploads_flexible.py -v
```

Expected: all PASS.

- [ ] **Step 5: Verify existing template routes still work**

```bash
pytest tests/api/ -v -k "template"
```

Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/bulk_uploads.py tests/api/test_bulk_uploads_flexible.py
git commit -m "[#4] Add elemental-composition-flexible to template endpoint"
```

---

## Task 7 — Frontend: API client + upload card

**Files:**
- Modify: `frontend/src/api/bulkUploads.ts`
- Modify: `frontend/src/pages/BulkUploads.tsx`

No automated tests for this task — verify visually by running the dev server.

- [ ] **Step 1: Add `TemplateType` value and upload function in `bulkUploads.ts`**

In `frontend/src/api/bulkUploads.ts`:

1. Add `'elemental-composition-flexible'` to the `TemplateType` union:

```typescript
export type TemplateType =
  // ... existing values ...
  | 'elemental-composition'
  | 'elemental-composition-flexible'   // ADD THIS
  // ... rest
```

2. Add the upload function alongside `uploadElementalComposition`:

```typescript
uploadFlexibleElementalComposition: (file: File, overwrite = false) => {
  const fd = new FormData()
  fd.append('file', file)
  return post<BulkUploadResult>(
    `/bulk-uploads/elemental-composition-flexible?overwrite=${overwrite}`,
    fd,
  )
},
```

- [ ] **Step 2: Add the upload card in `BulkUploads.tsx`**

After the `{/* 9 — Sample Chemical Composition */}` card block, add:

```tsx
{/* 10 — Elemental Composition (Flexible) */}
<UploadRow
  id="elemental-composition-flexible"
  title="Elemental Composition (Flexible)"
  description="Wide-format Excel with flexible header parsing"
  helpText="Columns after the sample column must match analytes defined in the system. Headers can be bare symbols ('Fe') or 'Symbol (unit)' format ('Fe (%)'). Add missing analytes via the Analyte Definitions upload before downloading if you need extra columns."
  accept=".xlsx"
  uploadFn={(file) => bulkUploadsApi.uploadFlexibleElementalComposition(file)}
  templateType="elemental-composition-flexible"
  isOpen={isOpen('elemental-composition-flexible')}
  onToggle={() => toggle('elemental-composition-flexible')}
/>
```

> Renumber the subsequent cards' comments (10 → 11 → 12 etc.) to stay consistent.

- [ ] **Step 3: Build and verify**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/bulkUploads.ts frontend/src/pages/BulkUploads.tsx
git commit -m "[#4] Add Flexible Elemental Composition upload card"
```

---

## Task 8 — Documentation

**Files:**
- Create: `docs/upload_templates/elemental_composition_flexible.md`

- [ ] **Step 1: Write upload format doc**

```markdown
# Flexible Elemental Composition Upload

**Endpoint:** `POST /api/bulk-uploads/elemental-composition-flexible`
**Template:** `GET /api/bulk-uploads/templates/elemental-composition-flexible`

## Overview

Imports rock or sample elemental composition data from a user-prepared wide-format Excel file.
Unlike the strict `elemental-composition` upload, this format tolerates common header variations.

## File Format

| Column | Requirement | Example |
|---|---|---|
| Sample column | Any header containing "sample" (first match wins) | `sample_id`, `Sample`, `Sample ID` |
| Analyte columns | One per analyte; bare symbol or `Symbol (unit)` | `Fe`, `Fe (%)`, `SiO2 [wt%]` |
| Cell values | Numeric. `<0.01` stripped to `0.01`. `nd`, `n/a`, blank → skipped | `47.2`, `<0.01`, `nd` |

## Column Header Rules

- `Fe` — bare symbol; matches analyte `Fe` regardless of unit
- `Fe (%)` or `Fe [%]` — symbol + unit in parens or brackets; symbol is matched, unit is informational
- Matching is **case-insensitive**: `sio2` matches `SiO2`
- Unknown analytes are **silently skipped** (strict mode). They do not cause an error.

## Sample Matching

Sample IDs are matched **fuzzy**: hyphens, underscores, and spaces are ignored and comparison is case-insensitive.
`DUNE-001`, `dune_001`, and `DUNE 001` all resolve to the same sample.

## Query Parameters

| Parameter | Default | Description |
|---|---|---|
| `overwrite` | `false` | When `true`, replaces existing `ElementalAnalysis` values for matched (sample, analyte) pairs |

## Template Download

The template is generated live from the current analyte catalogue.
Download it after adding all required analytes via the **Analyte Definitions** upload.
Headers are in `Symbol (unit)` format and sorted alphabetically.

If no analytes exist, the download returns a single-column file with an `INSTRUCTIONS` sheet.

## ExternalAnalysis Linkage

Each imported row creates or reuses a `Bulk Elemental Composition` `ExternalAnalysis` stub per sample.
This stub is shared with the strict `elemental-composition` upload — both services write to the same parent record.

## Future Enhancement

A `diagnose()` method is implemented on `FlexibleElementalCompositionService` (internal only).
A future issue could expose `POST /diagnose` to show a preview (detected columns, unrecognised analytes,
sample match rate) before the user commits the upload.
```

- [ ] **Step 2: Commit**

```bash
git add docs/upload_templates/elemental_composition_flexible.md
git commit -m "[#4] Add elemental_composition_flexible upload format doc"
```

---

## Task 9 — Full regression run

- [ ] **Step 1: Run all backend service tests**

```bash
pytest tests/services/ -v
```

Expected: all PASS, no regressions in existing elemental / actlabs tests.

- [ ] **Step 2: Run all API tests**

```bash
pytest tests/api/ -v
```

Expected: all PASS.

- [ ] **Step 3: Frontend build**

```bash
cd frontend && npm run build 2>&1 | tail -5
```

Expected: exit 0, no TypeScript errors.
