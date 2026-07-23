# Issue #70 P3 — Bulk-Upload Replicate Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one uploaded results sheet hold all replicates for a timepoint — rows carrying a base experiment ID plus a separate `Replicate` column are routed to the correct lettered sibling experiment before upsert, with per-row non-fatal errors for unresolved or conflicting rows.

**Architecture:** A new pure helper `combine_replicate_id(experiment_id, replicate)` (no DB access) converts `("SERUM_001", "b")` into `"SERUM_001b"` at parse time, using the P1 parser `database/lineage_utils.py::parse_experiment_id` for grammar-correct combination and conflict detection. The two **live** results-upload parsers (`scalar_results.py` for the Solution Chemistry template, `master_bulk_upload.py` for Master Results) call it per row before delegating to `ScalarResultsService`. Everything downstream is untouched: fuzzy ID lookup, upsert, per-row savepoints, and the "not found" per-row error for missing siblings already exist in `ScalarResultsService.create_scalar_result_ex` (its auto-create path only fires for treatment variants — `auto_create_treatment_experiment` returns `None` when `treatment_variant is None` — so a missing lettered sibling already produces a clear per-row `ValueError`, never a silent creation).

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy / pandas / openpyxl; pytest against the real `experiments_test` PostgreSQL DB.

## Global Constraints

- **Locked-component authorization:** `backend/services/bulk_uploads/` parser logic is locked (CLAUDE.md §5), but issue #70 P3 explicitly directs this work and the user authorized proceeding on 2026-07-23. Only `scalar_results.py`, `master_bulk_upload.py`, and the new `replicate_routing.py` may be touched inside that directory. No other locked files.
- **No schema changes, no migrations, no new packages** in P3.
- **Locked decisions (issue #70, do not revisit):** replicate marker is a single lowercase `[a-z]` after the numeric index; bare base is replicate 0 and the group parent (`S-0`/`S-1` are explicit parent spellings); conflicts on routing produce a clear non-fatal per-row message — no crash, no silent overwrite.
- **Product rules for the `Replicate` column (decided for P3, consistent with locked decisions):**
  - Blank/`NaN` → row behaves exactly as today (byte-identical pass-through).
  - `0` (int, float, or `"0"`) → routes to the bare base itself (replicate 0 = group parent).
  - Single letter `a`–`z`, any case → combined with the base ID.
  - The Experiment ID may already carry the *same* letter (redundant, allowed). A *different* letter, a derivation suffix (`-2`), a treatment suffix (`_Desorption`), a parent-alias spelling (`-0`/`-1`), or an ID shape that cannot carry a letter under the P1 grammar (e.g. `CF-015`) → per-row `ValueError`, row skipped, upload continues.
  - Result uploads **never auto-create** replicate siblings — unresolved combined IDs get the existing per-row "not found" error.
- **Out of scope:** `quick_upload.py` and `long_format.py` (legacy-Streamlit-only, no FastAPI endpoint — full replicate IDs already work there via the shared service); ICP uploads; new-experiments upload; outlier flag (P4); parser consolidation (P5).
- **Test commands:** targeted `.venv/Scripts/python -m pytest tests/services/bulk_uploads/ -q`; full suite `.venv/Scripts/python -m pytest tests/ -q`. Known pre-existing failures: 3 in `tests/test_pg_backup_restore.py` (local pg_dump toolchain gap) — not caused by this branch.
- **Commit format:** `[#70] <imperative, ≤50 chars>` with `- Tests added:` / `- Docs updated:` trailer lines (CLAUDE.md §8).
- **Docs sync:** write docs under `docs/` normally — a PostToolUse hook copies them to `docs/project_context/`. Never write `docs/project_context/` directly.
- **Never start/stop the uvicorn or Vite servers** (backend/frontend CLAUDE.md).
- `structlog` only; no `print()`. Frontend: no hardcoded hex, Tailwind only.
- Branch: `feat/issue-70-replicate-p3-bulk-upload` (already created from `develop`). PRs use `--base develop`.

---

### Task 1: `combine_replicate_id` helper

**Files:**
- Create: `backend/services/bulk_uploads/replicate_routing.py`
- Test: `tests/services/bulk_uploads/test_replicate_routing.py`

**Interfaces:**
- Consumes: `database.lineage_utils.parse_experiment_id(experiment_id: str) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]` — returns `(base_experiment_id, derivation_number, treatment_variant, replicate_label)` (exists since P1).
- Produces: `combine_replicate_id(experiment_id: Any, replicate: Any) -> Any` — returns the effective experiment ID string (or the untouched original input when the replicate value is blank/0); raises `ValueError` with a user-facing message on any malformed or conflicting combination. Tasks 2 and 3 import it as `from backend.services.bulk_uploads.replicate_routing import combine_replicate_id`.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/bulk_uploads/test_replicate_routing.py`:

```python
"""Unit tests for combine_replicate_id (issue #70 P3). Pure — no DB."""
from __future__ import annotations

import pytest

from backend.services.bulk_uploads.replicate_routing import combine_replicate_id


def test_blank_values_pass_through():
    assert combine_replicate_id("SERUM_001", None) == "SERUM_001"
    assert combine_replicate_id("SERUM_001", float("nan")) == "SERUM_001"
    assert combine_replicate_id("SERUM_001", "") == "SERUM_001"
    assert combine_replicate_id("SERUM_001", "  ") == "SERUM_001"


def test_zero_means_group_parent():
    assert combine_replicate_id("SERUM_001", 0) == "SERUM_001"
    assert combine_replicate_id("SERUM_001", 0.0) == "SERUM_001"
    assert combine_replicate_id("SERUM_001", "0") == "SERUM_001"


def test_letter_appends_to_numeric_index():
    assert combine_replicate_id("SERUM_001", "a") == "SERUM_001a"
    assert combine_replicate_id("SERUM_001", "B") == "SERUM_001b"
    assert combine_replicate_id(" SERUM_001 ", " c ") == "SERUM_001c"
    assert combine_replicate_id("Serum_MH_101", "a") == "Serum_MH_101a"


def test_same_letter_in_id_is_noop():
    assert combine_replicate_id("SERUM_001a", "a") == "SERUM_001a"


def test_conflicting_letter_raises():
    with pytest.raises(ValueError, match="conflicts"):
        combine_replicate_id("SERUM_001a", "b")


def test_derivation_or_treatment_suffix_raises():
    with pytest.raises(ValueError, match="derivation or treatment"):
        combine_replicate_id("SERUM_001-2", "b")
    with pytest.raises(ValueError, match="derivation or treatment"):
        combine_replicate_id("HPHT_MH_001_Desorption", "b")
    # Explicit parent spellings parse as derivation 0/1 — same strict rule.
    with pytest.raises(ValueError, match="derivation or treatment"):
        combine_replicate_id("SERUM_001-0", "b")


def test_id_without_numeric_index_raises():
    # "CF-015" has no underscore-delimited numeric index; "CF-015b" would not
    # round-trip through parse_experiment_id as a replicate.
    with pytest.raises(ValueError, match="cannot take a replicate letter"):
        combine_replicate_id("CF-015", "b")


def test_malformed_replicate_values_raise():
    for bad in ("ab", "2", 2.0, "b2", True):
        with pytest.raises(ValueError, match="single letter"):
            combine_replicate_id("SERUM_001", bad)


def test_replicate_without_experiment_id_raises():
    with pytest.raises(ValueError, match="without an Experiment ID"):
        combine_replicate_id(None, "a")
    with pytest.raises(ValueError, match="without an Experiment ID"):
        combine_replicate_id("   ", "a")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_replicate_routing.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.bulk_uploads.replicate_routing'`

- [ ] **Step 3: Write the implementation**

Create `backend/services/bulk_uploads/replicate_routing.py`:

```python
"""Replicate-column routing for bulk uploads (issue #70 P3).

Rows in results uploads may carry a base experiment ID (e.g. "SERUM_001") plus
a separate replicate column ("a", "b", ...). This module combines the two into
the full lettered sibling ID ("SERUM_001a") at parse time, so every downstream
step (fuzzy lookup, upsert, rollup) behaves exactly as if the row had carried
the full replicate ID. Pure string-level: no DB access — existence checks and
fuzzy matching stay in ScalarResultsService.
"""
from __future__ import annotations

import math
from typing import Any

from database.lineage_utils import parse_experiment_id


def combine_replicate_id(experiment_id: Any, replicate: Any) -> Any:
    """Return the effective experiment ID for a row's (experiment_id, replicate) pair.

    Rules (issue #70 locked decisions 1-2):
      - blank replicate (None/NaN/"") -> experiment_id returned unchanged
      - 0 (int, float, or "0") -> experiment_id unchanged (bare base = replicate 0)
      - single letter a-z (any case) -> appended to the ID's numeric index
      - the ID may already carry the same letter (no-op); a different letter,
        a derivation suffix (-2), a treatment suffix (_Desorption), or an ID
        shape that cannot carry a letter (e.g. CF-015) raises ValueError

    Raises:
        ValueError: with a user-facing, per-row message on any malformed or
            conflicting combination.
    """
    # Blank / replicate-0 spellings: pass the ID through untouched so rows
    # without a usable replicate value keep byte-identical behavior.
    if replicate is None:
        return experiment_id
    if isinstance(replicate, float) and math.isnan(replicate):
        return experiment_id
    if (
        isinstance(replicate, (int, float))
        and not isinstance(replicate, bool)
        and replicate == 0
    ):
        return experiment_id

    rep = str(replicate).strip().lower()
    if rep in ("", "0", "0.0"):
        return experiment_id

    if len(rep) != 1 or not ("a" <= rep <= "z"):
        raise ValueError(
            f"Replicate must be a single letter a-z (or 0 for the group parent), "
            f"got '{replicate}'."
        )

    if experiment_id is None or str(experiment_id).strip() == "":
        raise ValueError("Replicate letter given without an Experiment ID.")

    exp_id = str(experiment_id).strip()
    base_id, derivation_num, treatment_variant, replicate_label = parse_experiment_id(exp_id)

    if replicate_label == rep:
        return exp_id
    if replicate_label is not None:
        raise ValueError(
            f"Replicate column '{rep}' conflicts with the replicate letter "
            f"already in '{exp_id}'."
        )
    if derivation_num is not None or treatment_variant is not None:
        raise ValueError(
            f"Replicate column cannot be combined with a derivation or treatment "
            f"suffix ('{exp_id}') - put the full replicate ID in the Experiment ID "
            f"column instead."
        )

    candidate = f"{base_id}{rep}"
    # Round-trip guard: some ID shapes (e.g. "CF-015", whose index is not an
    # underscore-delimited numeric segment) cannot carry a replicate letter
    # under the P1 grammar. Refuse rather than write an ID the lineage
    # listener would misclassify.
    if parse_experiment_id(candidate) != (base_id, None, None, rep):
        raise ValueError(
            f"'{exp_id}' cannot take a replicate letter - only IDs ending in a "
            f"numeric index (e.g. SERUM_001) support the replicate column."
        )
    return candidate
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_replicate_routing.py -q`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/replicate_routing.py tests/services/bulk_uploads/test_replicate_routing.py
git commit -m "[#70] Add replicate-column ID combiner

- Pure string-level base+letter combination with P1-grammar round-trip guard
- Tests added: yes
- Docs updated: no"
```

---

### Task 2: Solution Chemistry path — parser routing, router stub, template

**Files:**
- Modify: `backend/services/bulk_uploads/scalar_results.py` (top imports ~line 11; `LEGACY_ALIASES` ~line 127; cleaning loop after ~line 171)
- Modify: `backend/api/routers/bulk_uploads.py` (stub dict ~line 44; `_get_template_bytes` scalar branch ~line 736)
- Test: `tests/services/bulk_uploads/test_scalar_results_replicates.py` (new)
- Test: `tests/api/test_bulk_uploads.py` (template header assertion, in the "Template download tests" section ~line 463)

**Interfaces:**
- Consumes: `combine_replicate_id(experiment_id, replicate)` from Task 1 (raises `ValueError`); `ScalarResultsUploadService.bulk_upsert_from_excel_ex(db, file_bytes, overwrite_all=False, dry_run=False) -> (created, updated, skipped, errors, row_feedbacks)` (unchanged signature).
- Produces: the Solution Chemistry upload accepts an optional `Replicate` column (header aliases: `Replicate`, `Replicate Letter`, case-insensitive); the downloadable `scalar-results` template contains the column. No signature changes — Tasks 3–4 don't depend on this task's code, only on the same helper.

- [ ] **Step 1: Write the failing service-level tests**

Create `tests/services/bulk_uploads/test_scalar_results_replicates.py`:

```python
"""End-to-end replicate routing through the Solution Chemistry upload (issue #70 P3)."""
from __future__ import annotations

import sys
from types import ModuleType

# scalar_results.py imports frontend.config.variable_config at module load time.
# The real module only exists in the legacy Streamlit app, so stub it exactly as
# backend/api/routers/bulk_uploads.py::upload_scalar_results does.
if "frontend.config.variable_config" not in sys.modules:
    _stub = ModuleType("frontend.config.variable_config")
    sys.modules.setdefault("frontend", ModuleType("frontend"))
    sys.modules.setdefault("frontend.config", ModuleType("frontend.config"))
    sys.modules["frontend.config.variable_config"] = _stub
_vc = sys.modules["frontend.config.variable_config"]
if not hasattr(_vc, "SCALAR_RESULTS_TEMPLATE_HEADERS"):
    _vc.SCALAR_RESULTS_TEMPLATE_HEADERS = {
        "measurement_date": "Date",
        "experiment_id": "Experiment ID",
        "replicate": "Replicate",
        "time_post_reaction": "Time (days)",
        "description": "Description",
        "gross_ammonium_concentration_mM": "Gross Ammonium (mM)",
    }

from sqlalchemy.orm import Session

from database import Experiment, ExperimentalResults
from database.models.enums import ExperimentStatus

from .excel_helpers import make_excel


def _seed_experiment(db: Session, experiment_id: str, exp_num: int) -> Experiment:
    exp = Experiment(
        experiment_id=experiment_id,
        experiment_number=exp_num,
        status=ExperimentStatus.ONGOING,
    )
    db.add(exp)
    db.flush()  # before_flush listener wires base_experiment_id / replicate_label
    return exp


def _seed_replicate_set(db: Session, base: str, start_num: int, letters: str = "ab"):
    _seed_experiment(db, base, start_num)
    for i, letter in enumerate(letters, start=1):
        _seed_experiment(db, f"{base}{letter}", start_num + i)


def _upload(db: Session, headers, rows):
    from backend.services.bulk_uploads.scalar_results import ScalarResultsUploadService

    xlsx = make_excel(headers, rows)
    return ScalarResultsUploadService.bulk_upsert_from_excel_ex(db, xlsx)


def _gross_for(db: Session, experiment_id: str, time_days: float):
    result = (
        db.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(
            Experiment.experiment_id == experiment_id,
            ExperimentalResults.time_post_reaction_days == time_days,
        )
        .one()
    )
    assert result.scalar_data is not None
    return result.scalar_data.gross_ammonium_concentration_mM


_HEADERS = ["Experiment ID", "Replicate", "Time (days)", "Gross Ammonium (mM)"]


def test_base_plus_replicate_column_routes_to_siblings(db_session):
    _seed_replicate_set(db_session, "P3SCAL_701", 7801)
    created, updated, skipped, errors, feedbacks = _upload(db_session, _HEADERS, [
        ["P3SCAL_701", "a", 7, 5.0],
        ["P3SCAL_701", "b", 7, 6.0],
        ["P3SCAL_701", 0, 7, 4.0],  # 0 = group parent
    ])
    assert errors == []
    assert created == 3
    assert _gross_for(db_session, "P3SCAL_701a", 7.0) == 5.0
    assert _gross_for(db_session, "P3SCAL_701b", 7.0) == 6.0
    assert _gross_for(db_session, "P3SCAL_701", 7.0) == 4.0


def test_unresolved_sibling_errors_without_aborting(db_session):
    _seed_replicate_set(db_session, "P3SCAL_702", 7811, letters="a")
    created, updated, skipped, errors, feedbacks = _upload(db_session, _HEADERS, [
        ["P3SCAL_702", "a", 7, 5.0],
        ["P3SCAL_702", "c", 7, 6.0],  # no 'c' sibling exists
    ])
    assert created == 1
    assert any("P3SCAL_702c" in e and "not found" in e for e in errors)
    error_rows = [fb for fb in feedbacks if fb["status"] == "error"]
    assert len(error_rows) == 1
    assert _gross_for(db_session, "P3SCAL_702a", 7.0) == 5.0


def test_conflicting_letter_errors_without_aborting(db_session):
    _seed_replicate_set(db_session, "P3SCAL_703", 7821)
    created, updated, skipped, errors, feedbacks = _upload(db_session, _HEADERS, [
        ["P3SCAL_703a", "b", 7, 5.0],  # ID letter and column letter disagree
        ["P3SCAL_703b", "b", 7, 6.0],  # redundant but consistent -> OK
    ])
    assert created == 1
    assert any("conflicts" in e for e in errors)
    assert _gross_for(db_session, "P3SCAL_703b", 7.0) == 6.0


def test_full_replicate_ids_route_without_column(db_session):
    """Pins today's behavior: full lettered IDs route with no Replicate column."""
    _seed_replicate_set(db_session, "P3SCAL_704", 7831)
    headers = ["Experiment ID", "Time (days)", "Gross Ammonium (mM)"]
    created, updated, skipped, errors, _ = _upload(db_session, headers, [
        ["P3SCAL_704a", 7, 5.0],
        ["P3SCAL_704b", 7, 6.0],
    ])
    assert errors == []
    assert created == 2
    assert _gross_for(db_session, "P3SCAL_704a", 7.0) == 5.0
    assert _gross_for(db_session, "P3SCAL_704b", 7.0) == 6.0


def test_sheet_without_replicate_column_is_unchanged(db_session):
    """Regression: files that never had the column behave exactly as before."""
    _seed_experiment(db_session, "P3SCAL_705", 7841)
    headers = ["Experiment ID", "Time (days)", "Gross Ammonium (mM)"]
    created, updated, skipped, errors, _ = _upload(db_session, headers, [
        ["P3SCAL_705", 7, 5.0],
    ])
    assert errors == []
    assert created == 1
    assert _gross_for(db_session, "P3SCAL_705", 7.0) == 5.0
```

Note the test IDs use a **pure-numeric last underscore segment** (`P3SCAL_701`), because the P1 replicate grammar binds the letter to an `_NNN` index — `SERUM_P3RT001a` would *not* parse as a replicate.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_scalar_results_replicates.py -q`
Expected: the three replicate-column tests FAIL (rows with the unmapped `Replicate` column route to the base experiment or error); the two no-column regression tests PASS.

- [ ] **Step 3: Implement parser routing in `scalar_results.py`**

Three edits (this file is a locked parser — this change is authorized by issue #70 P3; keep every edit minimal and additive):

Edit A — add the import after the existing imports (below `from frontend.config.variable_config import SCALAR_RESULTS_TEMPLATE_HEADERS`):

```python
from backend.services.bulk_uploads.replicate_routing import combine_replicate_id
```

Edit B — in `LEGACY_ALIASES`, immediately after the `"overwrite": "overwrite",` entry, add:

```python
            "replicate":                    "replicate",
            "replicate letter":             "replicate",
```

(The case-insensitive `ci_header_map` built from these makes the `Replicate` template header resolve too.)

Edit C — in the cleaning loop of `bulk_upsert_from_excel_ex`, immediately after the empty-row guard:

```python
            if not clean:
                continue

            if "replicate" in clean:
                rep_val = clean.pop("replicate")
                try:
                    clean["experiment_id"] = combine_replicate_id(
                        clean.get("experiment_id"), rep_val,
                    )
                except ValueError as exc:
                    errors.append(f"Row {row_num}: {exc}")
                    parse_feedbacks.append({
                        "row": row_num,
                        "experiment_id": str(clean.get("experiment_id", "")),
                        "time_post_reaction": None,
                        "status": "error",
                        "fields_updated": [], "fields_preserved": [],
                        "old_values": {}, "new_values": {},
                        "warnings": [],
                        "errors": [str(exc)],
                    })
                    continue
```

(Blank replicate cells never reach this branch — NaN/empty values are stripped before `clean` is built — and `combine_replicate_id` also passes blanks through, so no-column and blank-cell files stay byte-identical. Popping `replicate` before the dry-run branch keeps `data_fields` clean and makes dry-run previews show the resolved ID.)

- [ ] **Step 4: Run the service tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_scalar_results_replicates.py tests/services/bulk_uploads/test_replicate_routing.py -q`
Expected: all PASS

- [ ] **Step 5: Write the failing template test**

In `tests/api/test_bulk_uploads.py`, add to the "Template download tests" section (after the `_NO_TEMPLATE_TYPES` block and its tests):

```python
def test_scalar_template_includes_replicate_column():
    """Issue #70 P3: the Solution Chemistry template carries an optional Replicate column."""
    import openpyxl  # noqa: PLC0415

    from backend.api.routers.bulk_uploads import _get_template_bytes  # noqa: PLC0415

    wb = openpyxl.load_workbook(io.BytesIO(_get_template_bytes("scalar-results")))
    headers = [c.value for c in wb.active[1]]
    assert "Replicate" in headers
    assert headers.index("Replicate") == headers.index("Experiment ID") + 1
```

Run: `.venv/Scripts/python -m pytest tests/api/test_bulk_uploads.py::test_scalar_template_includes_replicate_column -q`
Expected: FAIL — `"Replicate" not in headers`

- [ ] **Step 6: Update the router stub and template**

In `backend/api/routers/bulk_uploads.py`:

Edit A — in `upload_scalar_results`'s stub dict, after `"experiment_id": "Experiment ID",` add:

```python
            "replicate": "Replicate",
```

Edit B — in `_get_template_bytes`, replace the `scalar-results` branch's `headers` and `example_row` with:

```python
    if upload_type == "scalar-results":
        return _simple_template(
            headers=[
                "Experiment ID", "Replicate", "Time (days)", "Description", "Date",
                "Gross Ammonium (mM)", "Sampling Vol (mL)", "Bkg Ammonium (mM)", "Bkg Exp ID",
                "H2 Conc (ppm)", "Gas Sample Vol (mL)", "Gas Pressure (MPa)",
                "Final pH", "Fe2+ Yield (%)", "Final DO (mg/L)",
                "Conductivity (mS/cm)", "Overwrite",
            ],
            required={"Experiment ID", "Time (days)"},
            example_row=["HPHT_001", None, 7.0, "Day 7 sample", None, 5.2, 2.0, 0.3, None,
                         120.0, 5.0, 0.5, 7.2, None, None, 12.5, "FALSE"],
        )
```

- [ ] **Step 7: Run the API bulk-uploads tests**

Run: `.venv/Scripts/python -m pytest tests/api/test_bulk_uploads.py -q`
Expected: all PASS (the new template test plus every pre-existing test)

- [ ] **Step 8: Commit**

```bash
git add backend/services/bulk_uploads/scalar_results.py backend/api/routers/bulk_uploads.py tests/services/bulk_uploads/test_scalar_results_replicates.py tests/api/test_bulk_uploads.py
git commit -m "[#70] Route Replicate column in scalar upload

- Optional Replicate column resolves base+letter to sibling before upsert
- Per-row non-fatal errors for conflicts and unresolved siblings
- Template and router header stub updated
- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Master Results path routing

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (top imports ~line 17; header normalization ~line 110; row loop ~line 127)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py` (extend)

**Interfaces:**
- Consumes: `combine_replicate_id(experiment_id, replicate)` from Task 1; `MasterBulkUploadService.from_bytes(db, file_bytes) -> (created, updated, skipped, errors, feedbacks)` (unchanged signature).
- Produces: the Master Results Dashboard sheet accepts an optional `Replicate` column (case-insensitive header). Feedback dicts carry the *resolved* experiment ID.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
# ---------------------------------------------------------------------------
# Replicate routing (issue #70 P3)
# ---------------------------------------------------------------------------

def _master_excel_with_replicate(rows: list[list]) -> bytes:
    headers = [
        "Experiment ID", "Replicate", "Duration (Days)", "Description", "Sample Date",
        "NMR Run Date", "ICP Run Date", "GC Run Date",
        "NH4 (mM)", "H2 (ppm)", "Gas Volume (mL)", "Gas Pressure (psi)",
        "Sample pH", "Sample Conductivity (mS/cm)", "Modification", "Overwrite",
    ]
    return make_excel_multisheet({"Dashboard": (headers, rows)})


def test_replicate_column_routes_to_sibling(db_session: Session):
    """A base ID + Replicate letter lands the row on the lettered sibling."""
    _seed_experiment(db_session, "P3MAST_701", 7901)
    _seed_experiment(db_session, "P3MAST_701a", 7902)

    xlsx = _master_excel_with_replicate([
        ["P3MAST_701", "a", 7.0, "Day 7", None, None, None, None,
         5.2, None, None, None, 7.1, None, None, "FALSE"],
        ["P3MAST_701", None, 7.0, "Day 7 parent", None, None, None, None,
         4.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 2
    assert feedbacks[0]["experiment_id"] == "P3MAST_701a"

    sibling_result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "P3MAST_701a")
        .one()
    )
    assert sibling_result.scalar_data.gross_ammonium_concentration_mM == 5.2

    parent_result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "P3MAST_701")
        .one()
    )
    assert parent_result.scalar_data.gross_ammonium_concentration_mM == 4.0


def test_invalid_replicate_is_per_row_error(db_session: Session):
    """A malformed Replicate value skips that row only; the rest still upload."""
    _seed_experiment(db_session, "P3MAST_702", 7911)
    _seed_experiment(db_session, "P3MAST_702a", 7912)

    xlsx = _master_excel_with_replicate([
        ["P3MAST_702", "ab", 7.0, "bad", None, None, None, None,
         5.0, None, None, None, None, None, None, "FALSE"],
        ["P3MAST_702", "a", 7.0, "good", None, None, None, None,
         6.0, None, None, None, None, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 1
    assert any("single letter" in e for e in errors)
    assert feedbacks[0]["experiment_id"] == "P3MAST_702a"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q`
Expected: the two new tests FAIL (rows route to the base experiment / no per-row error); all pre-existing tests PASS.

- [ ] **Step 3: Implement routing in `master_bulk_upload.py`**

Three edits (locked parser — authorized by issue #70 P3):

Edit A — add the import after `from sqlalchemy.orm import Session`:

```python
from backend.services.bulk_uploads.replicate_routing import combine_replicate_id
```

Edit B — after the existing volume-column normalization (`"Sampled Solution Volume (mL)" if ...`), add:

```python
    # Normalise the optional replicate column header to canonical casing.
    df.columns = [
        "Replicate" if c.lower() == "replicate" else c
        for c in df.columns
    ]
```

Edit C — in the row loop, immediately after the calibration-standard skip (`if "standard" in exp_id.lower(): ...`), add:

```python
        # Optional replicate column: resolve base + letter to the sibling ID
        # before anything downstream sees exp_id (issue #70 P3).
        try:
            exp_id = combine_replicate_id(exp_id, row.get("Replicate"))
        except ValueError as exc:
            errors.append(f"Row {row_num} ({exp_id}): {exc}")
            continue
```

(`row.get("Replicate")` returns `None` when the column is absent and `NaN` when blank — both pass through `combine_replicate_id` untouched, so existing files keep byte-identical behavior.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "[#70] Route Replicate column in master upload

- Optional Replicate column on the Dashboard sheet resolves to siblings
- Malformed values skip the row with a per-row error
- Tests added: yes
- Docs updated: no"
```

---

### Task 4: Documentation, frontend help text, full verification

**Files:**
- Modify: `frontend/src/pages/BulkUploads.tsx` (scalar tile `helpText`, ~line 252)
- Modify: `docs/user_guide/REPLICATES.md` (new section before `## Troubleshooting`)
- Modify: `docs/user_guide/BULK_UPLOADS.md` (Solution Chemistry + Master Results sections)
- Modify: `docs/upload_templates/scalar_results.md` (optional columns + new section)
- Modify: `docs/upload_templates/master_bulk_upload.md` (column spec note)
- Modify: `docs/api/API_REFERENCE.md` (scalar-results + master-results endpoint notes)

**Interfaces:**
- Consumes: the behavior shipped in Tasks 1–3 (nothing programmatic).
- Produces: user-facing and API documentation of the `Replicate` column. The `docs/` writes are auto-copied to `docs/project_context/` by the PostToolUse hook — do not write that folder directly.

- [ ] **Step 1: Update the frontend help text**

In `frontend/src/pages/BulkUploads.tsx`, replace the Solution Chemistry tile's `helpText` value (currently `"Required columns: Experiment ID, Time (days). All other fields are optional. Set Overwrite=TRUE to replace existing values."`) with:

```
"Required columns: Experiment ID, Time (days). All other fields are optional. Set Overwrite=TRUE to replace existing values. Replicates: either write the full lettered ID (SERUM_001a) in Experiment ID, or put the base ID there and the letter (a, b, c) in the optional Replicate column — 0 or blank means the group parent."
```

Before editing, grep the frontend tests for the old string (`Set Overwrite=TRUE`) — if any test asserts it, update that assertion in the same edit.

- [ ] **Step 2: Update `docs/user_guide/REPLICATES.md`**

Insert this section immediately before `## Troubleshooting`:

```markdown
## Uploading replicate results

Both the Solution Chemistry upload and the Master Results sync can load one sheet holding all replicates for a timepoint. Two row formats work:

1. **Full replicate IDs** — put the lettered ID (`SERUM_001a`) in the Experiment ID column, exactly as for any other experiment.
2. **Base ID + Replicate column** — put the bare base (`SERUM_001`) in Experiment ID and the letter (`a`, `b`, `c`) in the optional `Replicate` column. `0` or a blank cell means the group parent itself.

Each row lands as its own result on the matching sibling experiment, so the grouped (mean ± std) view aggregates automatically. Rows that cannot be resolved — a letter with no matching replicate experiment, a Replicate value that is not a single letter, or a letter that conflicts with one already in the ID — are skipped with a per-row error message; the rest of the file still uploads.

Replicate experiments must already exist (create them with the **Create replicates** button or the New Experiments upload) — result uploads never auto-create replicate siblings.
```

- [ ] **Step 3: Update `docs/user_guide/BULK_UPLOADS.md`**

Read the file first. At the end of the Solution Chemistry section, add:

```markdown
**Replicates:** rows may carry either a full lettered ID (`SERUM_001a`) in Experiment ID, or the bare base ID plus the optional `Replicate` column (`a`–`z`; `0` or blank = the group parent). Base + letter is resolved to the sibling experiment before upsert. Unresolved or conflicting rows are skipped with a per-row error — the rest of the file still uploads. See the [Replicates guide](REPLICATES.md#uploading-replicate-results).
```

Add the same block (verbatim) at the end of the Master Results section.

- [ ] **Step 4: Update the template and API reference docs**

`docs/upload_templates/scalar_results.md` — add `Replicate` to the Optional Columns list, and append this section after "Parsing Logic":

```markdown
## Replicate Routing (Issue #70 P3)
- An optional `Replicate` column (aliases: `Replicate`, `Replicate Letter`, case-insensitive) routes rows carrying a base ID to lettered sibling experiments: `SERUM_001` + `b` upserts to `SERUM_001b`.
- `0` or a blank cell routes to the base experiment itself (replicate 0 = group parent).
- Combination happens at parse time via `backend/services/bulk_uploads/replicate_routing.py::combine_replicate_id`; conflicting or malformed combinations (different letter than the ID already carries, derivation/treatment suffixes, IDs without a numeric index, multi-character values) produce a per-row error and the row is skipped without aborting the upload.
- Missing siblings are **not** auto-created; the row errors with the standard "not found" message.
```

`docs/upload_templates/master_bulk_upload.md` — read the file, then add a note to its column spec:

```markdown
- `Replicate` (optional, issue #70 P3): single letter `a`–`z` routing the row to the lettered sibling of the base Experiment ID (`0`/blank = the base itself). Malformed or conflicting values skip that row with a per-row error.
```

`docs/api/API_REFERENCE.md` — read the scalar-results and master-results endpoint sections, then add to each:

```markdown
Rows may carry either a full replicate ID (`SERUM_001a`) or a base ID plus an optional `Replicate` column (letter `a`–`z`, or `0`/blank for the group parent). Base + letter is resolved to the sibling experiment before upsert; unresolved or conflicting rows produce per-row errors in `errors`/`feedbacks` without aborting the upload. Replicate siblings are never auto-created by result uploads.
```

- [ ] **Step 5: Verify — full backend suite, frontend checks**

```bash
.venv/Scripts/python -m pytest tests/ -q
```
Expected: green except the 3 known pre-existing `tests/test_pg_backup_restore.py` failures.

```bash
cd frontend && npx eslint src/pages/BulkUploads.tsx && npx vitest run src
```
Expected: eslint clean; all frontend tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/BulkUploads.tsx docs/user_guide/REPLICATES.md docs/user_guide/BULK_UPLOADS.md docs/upload_templates/scalar_results.md docs/upload_templates/master_bulk_upload.md docs/api/API_REFERENCE.md docs/project_context/
git commit -m "[#70] Document replicate upload routing

- Replicate column documented in user guide, templates, API reference
- Solution Chemistry tile help text updated
- Tests added: no
- Docs updated: yes"
```

(`docs/project_context/` copies are produced by the sync hook — include them in the commit but never edit them by hand.)

---

## Acceptance mapping (issue #70 P3)

| Acceptance criterion | Covered by |
|---|---|
| Rows with full replicate IDs route as today | Task 2 `test_full_replicate_ids_route_without_column` (pins existing behavior) |
| Base ID + replicate column resolves `base + letter → experiment_id` before upsert | Task 1 helper; Task 2/3 routing tests |
| Each replicate's measurement lands as its own `ExperimentalResults` (+ `ScalarResults`) under its own experiment | Task 2 `test_base_plus_replicate_column_routes_to_siblings`, Task 3 `test_replicate_column_routes_to_sibling` |
| Rollup aggregates automatically | No code needed — `v_results_scalar_rollup` groups by `COALESCE(base_experiment_id, experiment_id)`; rows land on siblings whose lineage P1 already wires |
| Unresolved/conflicting rows: clear per-row message, skipped, not fatal | Task 1 error tests; Task 2 unresolved/conflict tests; Task 3 invalid-value test |
| Full pytest suite green | Task 4 Step 5 |
