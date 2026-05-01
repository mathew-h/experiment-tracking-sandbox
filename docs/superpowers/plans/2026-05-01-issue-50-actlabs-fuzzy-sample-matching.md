# Issue #50 — ActLabs Fuzzy Sample ID Matching & Duplicate Warning

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fuzzy similarity matching and a blocking two-phase upload flow to the ActLabs rock analysis bulk uploader so near-duplicate sample IDs produce a user-resolvable warning instead of silent errors or duplicate records.

**Architecture:** Phase 1 — POST `/actlabs-rock` with no `resolutions` param parses the file, runs a rapidfuzz similarity check against existing samples, and returns `{status: "warnings", conflicts: [...]}` without writing anything. Phase 2 — same endpoint with a `resolutions` JSON Form field containing the user's per-conflict decisions (`"link:<existing_id>"` or `"create"`) executes the import. Exact normalized matches are auto-resolved silently (logged via structlog).

**Tech Stack:** Python `rapidfuzz>=3.0.0` (WRatio scorer), pydantic-settings for configurable threshold, FastAPI multipart Form field for resolutions, React + Tanstack Query for two-phase UI flow, existing `Modal` component from `frontend/src/components/ui/Modal.tsx`.

---

## Current State (read before touching any file)

- `backend/services/bulk_uploads/_id_match.py` — shared normalize + exact-scan helpers; used by XRD uploader but NOT by the titration service
- `backend/services/bulk_uploads/actlabs_titration_data.py` — has its own local `_normalize_sample_id` / `_fuzzy_find_sample` that do exact-normalized match only; no rapidfuzz; used by both `ElementalCompositionService` and `ActlabsRockTitrationService`
- `backend/api/schemas/bulk_upload.py` — only `UploadResponse` defined
- `backend/config/settings.py` — `pydantic-settings` `Settings` class; `get_settings()` cached singleton
- `backend/api/routers/bulk_uploads.py:491` — `POST /actlabs-rock` endpoint; `response_model=UploadResponse`
- `frontend/src/api/bulkUploads.ts:90` — `uploadActlabsRock(file)` → `post<BulkUploadResult>(...)`
- `frontend/src/pages/BulkUploads.tsx:291` — `UploadRow` for actlabs-rock, `uploadFn` is `bulkUploadsApi.uploadActlabsRock`
- `frontend/src/pages/BulkUploadRow.tsx` — generic upload row; `uploadFn: (file) => Promise<BulkUploadResult>`
- `frontend/src/components/ui/Modal.tsx` — `Modal` component; props: `open`, `onClose`, `title`, `description`, `children`, `footer`, `size`

**Note:** `rapidfuzz` is a new third-party package. CLAUDE.md §9 requires stopping to ask when adding packages. The issue spec explicitly names it — this plan treats that as user approval. Confirm with the user before running the `requirements.txt` step if you have any doubt.

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Modify | `requirements.txt` | Add `rapidfuzz>=3.0.0` |
| Modify | `backend/config/settings.py` | Add `actlabs_similarity_threshold: float = 0.90` |
| Modify | `backend/services/bulk_uploads/_id_match.py` | Add `SimilarSampleMatch` TypedDict + `find_similar_samples()` |
| Modify | `backend/api/schemas/bulk_upload.py` | Add `SampleConflictMatch`, `SampleConflict`, `ConflictCheckResponse` |
| Modify | `backend/services/bulk_uploads/actlabs_titration_data.py` | Migrate local fns to `_id_match`; add `_resolve_sample()`; add `preflight_check()`; update `import_excel()` signature |
| Modify | `backend/api/routers/bulk_uploads.py` | Update `/actlabs-rock` — add `resolutions` Form field, two-phase logic |
| Modify | `tests/services/bulk_uploads/test_id_match.py` | Add `find_similar_samples` tests |
| Create | `tests/services/bulk_uploads/test_actlabs_conflicts.py` | Preflight + resolution tests |
| Modify | `tests/api/test_bulk_uploads.py` | Conflict response + resolution roundtrip tests |
| Modify | `frontend/src/api/bulkUploads.ts` | Add `SampleConflict`, `ConflictCheckResult` types; update `uploadActlabsRock` |
| Create | `frontend/src/components/SampleConflictModal.tsx` | Per-conflict resolution modal |
| Create | `frontend/src/pages/ActlabsUploadRow.tsx` | Upload row with two-phase conflict handling |
| Modify | `frontend/src/pages/BulkUploads.tsx` | Swap `UploadRow` → `ActlabsUploadRow` for actlabs-rock card |

---

## Task 1: Library, settings, `_id_match` extension, schemas

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/config/settings.py`
- Modify: `backend/services/bulk_uploads/_id_match.py`
- Modify: `backend/api/schemas/bulk_upload.py`
- Modify: `tests/services/bulk_uploads/test_id_match.py`

- [ ] **Step 1: Write failing tests for `find_similar_samples`**

Open `tests/services/bulk_uploads/test_id_match.py` and append (do not remove existing `test_normalize_id` tests):

```python
# ── find_similar_samples ──────────────────────────────────────────────────────

from unittest.mock import MagicMock
from backend.services.bulk_uploads._id_match import find_similar_samples, SimilarSampleMatch
from database import SampleInfo


def _make_db(sample_ids: list[str]):
    """Build a mock Session whose query().all() returns SampleInfo stubs."""
    samples = [SampleInfo(sample_id=sid) for sid in sample_ids]
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # no exact match
    db.query.return_value.all.return_value = samples
    return db


def test_find_similar_no_near_matches():
    """Returns empty dict when no sample is similar enough."""
    db = _make_db(["Granite", "Basalt"])
    result = find_similar_samples(db, ["QRTZ9999"], threshold=0.90)
    assert result == {}


def test_find_similar_exact_normalized_excluded():
    """Exact normalized match (auto-resolved) must NOT appear in conflicts."""
    # 'TAMARACK' normalizes same as 'Tamarack' → fuzzy_find_sample returns it
    from unittest.mock import patch
    db = _make_db(["Tamarack"])
    with patch("backend.services.bulk_uploads._id_match.fuzzy_find_sample") as mock_ffm:
        mock_ffm.return_value = SampleInfo(sample_id="Tamarack")
        result = find_similar_samples(db, ["TAMARACK"], threshold=0.90)
    assert "TAMARACK" not in result


def test_find_similar_near_match_returned():
    """Near-match above threshold is returned when no exact normalized match exists."""
    from unittest.mock import patch
    db = _make_db(["Tamarack"])
    with patch("backend.services.bulk_uploads._id_match.fuzzy_find_sample") as mock_ffm:
        mock_ffm.return_value = None  # no exact normalized match
        result = find_similar_samples(db, ["Tamarrack"], threshold=0.85)
    assert "Tamarrack" in result
    assert len(result["Tamarrack"]) == 1
    match = result["Tamarrack"][0]
    assert match["sample_id"] == "Tamarack"
    assert match["similarity"] >= 0.85


def test_find_similar_sorted_by_similarity_desc():
    """Candidates are sorted best-first."""
    from unittest.mock import patch
    db = _make_db(["Tamarack", "Tamaraack"])
    with patch("backend.services.bulk_uploads._id_match.fuzzy_find_sample") as mock_ffm:
        mock_ffm.return_value = None
        result = find_similar_samples(db, ["Tamarrack"], threshold=0.80)
    if "Tamarrack" in result:
        sims = [m["similarity"] for m in result["Tamarrack"]]
        assert sims == sorted(sims, reverse=True)


def test_find_similar_below_threshold_excluded():
    """Candidates below threshold are excluded."""
    from unittest.mock import patch
    db = _make_db(["ZZZ999"])
    with patch("backend.services.bulk_uploads._id_match.fuzzy_find_sample") as mock_ffm:
        mock_ffm.return_value = None
        result = find_similar_samples(db, ["Tamarack"], threshold=0.90)
    assert "Tamarack" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/services/bulk_uploads/test_id_match.py -k "find_similar" -v
```

Expected: `ImportError` or `AttributeError` — `find_similar_samples` not yet defined.

- [ ] **Step 3: Add `rapidfuzz` to `requirements.txt`**

Append to `requirements.txt`:
```
rapidfuzz>=3.0.0
```

Install in the project virtualenv:
```
pip install rapidfuzz>=3.0.0
```

- [ ] **Step 4: Add threshold to `Settings`**

In `backend/config/settings.py`, add one line inside the `Settings` class after `cors_origins`:
```python
    # ActLabs sample ID fuzzy matching threshold (0.0–1.0, default 0.90)
    actlabs_similarity_threshold: float = 0.90
```

- [ ] **Step 5: Add `SimilarSampleMatch` and `find_similar_samples` to `_id_match.py`**

At the top of `backend/services/bulk_uploads/_id_match.py`, add the `TypedDict` import and the new type:

```python
from typing import Optional, TypedDict
```

(Replace `from typing import Optional` if it already exists.)

At the end of the file, after `fuzzy_find_experiment`, add:

```python
class SimilarSampleMatch(TypedDict):
    sample_id: str
    similarity: float  # 0.0–1.0


def find_similar_samples(
    db: Session,
    incoming_ids: list[str],
    threshold: float = 0.90,
) -> dict[str, list[SimilarSampleMatch]]:
    """For each incoming_id with NO exact normalized match, return existing
    SampleInfo records whose normalized IDs score >= threshold via rapidfuzz WRatio.

    IDs that resolve via fuzzy_find_sample (exact normalized match) are silently
    excluded — they are auto-resolved by the caller, not conflicts.

    Returns dict mapping incoming_id -> sorted-desc list of SimilarSampleMatch.
    Only IDs with >= 1 candidate are included.
    """
    from rapidfuzz.fuzz import WRatio  # noqa: PLC0415

    all_samples = db.query(SampleInfo).all()
    conflicts: dict[str, list[SimilarSampleMatch]] = {}

    for raw in incoming_ids:
        if fuzzy_find_sample(db, raw) is not None:
            continue  # exact normalized match — auto-resolved, not a conflict

        target = normalize_id(raw)
        candidates: list[SimilarSampleMatch] = []
        for s in all_samples:
            score = WRatio(target, normalize_id(s.sample_id)) / 100.0
            if score >= threshold:
                candidates.append(SimilarSampleMatch(sample_id=s.sample_id, similarity=round(score, 4)))

        if candidates:
            conflicts[raw] = sorted(candidates, key=lambda c: c["similarity"], reverse=True)

    return conflicts
```

- [ ] **Step 6: Add conflict schemas to `backend/api/schemas/bulk_upload.py`**

Append after `UploadResponse`:

```python
from typing import Literal


class SampleConflictMatch(BaseModel):
    sample_id: str
    similarity: float


class SampleConflict(BaseModel):
    incoming_id: str
    normalized: str
    candidate_matches: list[SampleConflictMatch]


class ConflictCheckResponse(BaseModel):
    status: Literal["warnings"]
    conflicts: list[SampleConflict]
    message: str
```

Also add `Literal` to the existing import if not present:
```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel
```

- [ ] **Step 7: Run failing tests to verify they now pass**

```
pytest tests/services/bulk_uploads/test_id_match.py -k "find_similar" -v
```

Expected: all 5 tests PASS.

- [ ] **Step 8: Run full test suite to check for regressions**

```
pytest tests/ -x -q
```

Expected: all tests pass (same count as before this task).

- [ ] **Step 9: Commit**

```bash
git add requirements.txt backend/config/settings.py backend/services/bulk_uploads/_id_match.py backend/api/schemas/bulk_upload.py tests/services/bulk_uploads/test_id_match.py
git commit -m "[#50] add rapidfuzz, similarity threshold, find_similar_samples, conflict schemas

- Tests added: yes
- Docs updated: no"
```

---

## Task 2: Preflight and resolution logic in `actlabs_titration_data.py`

**Files:**
- Modify: `backend/services/bulk_uploads/actlabs_titration_data.py`
- Create: `tests/services/bulk_uploads/test_actlabs_conflicts.py`

- [ ] **Step 1: Write failing tests**

Create `tests/services/bulk_uploads/test_actlabs_conflicts.py`:

```python
"""Tests for ActlabsRockTitrationService preflight and resolution logic."""
from __future__ import annotations

import io
import pandas as pd
import pytest

from database import SampleInfo
from backend.services.bulk_uploads.actlabs_titration_data import ActlabsRockTitrationService


def _make_csv(sample_ids: list[str]) -> bytes:
    """Build a minimal ActLabs-like CSV with the given sample IDs."""
    rows = [
        ["Report Number", "", ""],
        ["Report Date", "", ""],
        ["Sample ID", "FeO", "SiO2"],
        ["", "%", "%"],
        ["Detection Limit", "0.01", "0.01"],
        ["Analysis Method: titration", "", ""],
        *[[sid, 10.0, 40.0] for sid in sample_ids],
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, header=False, index=False)
    buf.seek(0)
    return buf.getvalue()


# ── preflight_check ───────────────────────────────────────────────────────────

def test_preflight_no_conflicts(test_db):
    """Exact match → no conflicts returned."""
    test_db.add(SampleInfo(sample_id="Granite"))
    test_db.commit()
    conflicts, auto_log = ActlabsRockTitrationService.preflight_check(
        test_db, _make_csv(["Granite"])
    )
    assert conflicts == []


def test_preflight_exact_case_auto_resolved(test_db):
    """Case-only difference is auto-resolved; not returned as conflict."""
    test_db.add(SampleInfo(sample_id="Tamarack"))
    test_db.commit()
    conflicts, auto_log = ActlabsRockTitrationService.preflight_check(
        test_db, _make_csv(["TAMARACK"])
    )
    assert conflicts == []
    assert any("TAMARACK" in entry for entry in auto_log)


def test_preflight_near_match_returned_as_conflict(test_db):
    """Near-match (typo) above default threshold produces a conflict entry."""
    test_db.add(SampleInfo(sample_id="Tamarack"))
    test_db.commit()
    conflicts, _ = ActlabsRockTitrationService.preflight_check(
        test_db, _make_csv(["Tamarrack"]), threshold=0.85
    )
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["incoming_id"] == "Tamarrack"
    assert len(c["candidate_matches"]) >= 1
    assert c["candidate_matches"][0]["sample_id"] == "Tamarack"


def test_preflight_no_existing_samples_no_conflicts(test_db):
    """No existing samples → no conflicts (sample not found, but not a conflict)."""
    conflicts, auto_log = ActlabsRockTitrationService.preflight_check(
        test_db, _make_csv(["NewSample"])
    )
    assert conflicts == []


# ── import_excel with resolutions ────────────────────────────────────────────

def test_import_link_resolution(test_db):
    """Resolution 'link:<id>' maps incoming ID to an existing sample."""
    test_db.add(SampleInfo(sample_id="Tamarack"))
    test_db.commit()

    resolutions = {"Tamarrack": "link:Tamarack"}
    created, updated, skipped, errors = ActlabsRockTitrationService.import_excel(
        test_db, _make_csv(["Tamarrack"]), resolutions=resolutions
    )
    assert errors == []
    assert created + updated > 0


def test_import_create_resolution(test_db):
    """Resolution 'create' creates a new SampleInfo record and imports results."""
    resolutions = {"BrandNew": "create"}
    created, updated, skipped, errors = ActlabsRockTitrationService.import_excel(
        test_db, _make_csv(["BrandNew"]), resolutions=resolutions
    )
    assert errors == []
    from database import SampleInfo
    new_sample = test_db.query(SampleInfo).filter(SampleInfo.sample_id == "BrandNew").first()
    assert new_sample is not None


def test_import_no_resolution_still_errors(test_db):
    """No resolution for an unmatched ID → error row (existing behavior preserved)."""
    resolutions = {}
    _, _, _, errors = ActlabsRockTitrationService.import_excel(
        test_db, _make_csv(["NoMatch999"]), resolutions=resolutions
    )
    assert any("NoMatch999" in e for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/services/bulk_uploads/test_actlabs_conflicts.py -v
```

Expected: `ImportError` or `TypeError` — `preflight_check` / `resolutions` param not yet defined.

- [ ] **Step 3: Migrate local fns and add `_resolve_sample` to `actlabs_titration_data.py`**

At the top of `backend/services/bulk_uploads/actlabs_titration_data.py`, **replace** the two module-level private functions (`_normalize_sample_id` and `_fuzzy_find_sample`) with an import from `_id_match`:

```python
# Remove these two functions entirely:
# def _normalize_sample_id(sample_id: str) -> str: ...
# def _fuzzy_find_sample(db: Session, raw_sample_id: str) -> Optional[SampleInfo]: ...

# Add this import alongside the existing imports at the top:
from backend.services.bulk_uploads._id_match import fuzzy_find_sample as _fuzzy_find_sample, normalize_id as _normalize_sample_id_fn
```

> Note: the two existing call sites already use `_fuzzy_find_sample(db, sample_id)` — the import alias preserves that name so no other call sites change.

Also add `structlog` import:
```python
import structlog
log = structlog.get_logger(__name__)
```

After the imports (module level), add `_resolve_sample`:

```python
def _resolve_sample(
    db: "Session",
    sample_id: str,
    resolutions: "Optional[dict[str, str]]",
) -> "Optional[SampleInfo]":
    """Resolve an incoming sample_id to a SampleInfo using an optional resolutions map.

    Resolution values:
      "link:<existing_sample_id>" — use the named existing sample
      "create"                    — create a new SampleInfo with this sample_id

    Falls back to fuzzy_find_sample when no resolution is present.
    """
    action = (resolutions or {}).get(sample_id)
    if action and action.startswith("link:"):
        existing_id = action[len("link:"):]
        return db.query(SampleInfo).filter(SampleInfo.sample_id == existing_id).first()
    if action == "create":
        new_sample = SampleInfo(sample_id=sample_id)
        db.add(new_sample)
        db.flush()
        log.info("actlabs_sample_created_from_resolution", sample_id=sample_id)
        return new_sample
    return _fuzzy_find_sample(db, sample_id)
```

- [ ] **Step 4: Add `preflight_check` class method to `ActlabsRockTitrationService`**

Add after `diagnose` and before `import_excel` inside `ActlabsRockTitrationService`:

```python
    @classmethod
    def preflight_check(
        cls,
        db: Session,
        file_bytes: bytes,
        threshold: float = 0.90,
    ) -> "Tuple[List[dict], List[str]]":
        """Parse sample IDs from the file without any DB writes.

        Returns (conflicts, auto_resolved_log) where:
        - conflicts: list of dicts with keys incoming_id, normalized, candidate_matches
        - auto_resolved_log: human-readable strings for exact-normalized auto-resolutions

        A conflict means: no exact normalized match exists, but >= 1 existing sample
        scores above ``threshold`` via rapidfuzz WRatio.
        """
        from backend.services.bulk_uploads._id_match import (  # noqa: PLC0415
            find_similar_samples, fuzzy_find_sample, normalize_id,
        )

        df_raw, read_err = cls._read_table(file_bytes)
        if read_err or df_raw.empty:
            return [], []

        sample_id_col = cls._detect_sample_id_col(df_raw)
        data_start = cls._find_data_start_index(df_raw)
        data = df_raw.iloc[data_start:, :].reset_index(drop=True)

        seen: set[str] = set()
        unique_ids: list[str] = []
        for i in range(len(data)):
            raw = data.iat[i, sample_id_col]
            if not isinstance(raw, str) and not isinstance(raw, (int, float)):
                continue
            sid = str(raw).strip() if raw is not None else ""
            try:
                import pandas as pd  # noqa: PLC0415
                if not sid or pd.isna(raw):
                    continue
            except Exception:
                pass
            if sid and sid not in seen:
                seen.add(sid)
                unique_ids.append(sid)

        # Auto-resolved: exact normalized match exists
        auto_log: list[str] = []
        for sid in unique_ids:
            match = fuzzy_find_sample(db, sid)
            if match and match.sample_id != sid:
                msg = f"auto-resolved '{sid}' → '{match.sample_id}'"
                auto_log.append(msg)
                log.info("actlabs_sample_auto_resolved", incoming=sid, resolved_to=match.sample_id)

        # Conflicts: near-match but no exact normalized match
        similar = find_similar_samples(db, unique_ids, threshold=threshold)
        conflicts: list[dict] = []
        for incoming_id, candidates in similar.items():
            conflicts.append({
                "incoming_id": incoming_id,
                "normalized": normalize_id(incoming_id),
                "candidate_matches": [
                    {"sample_id": c["sample_id"], "similarity": c["similarity"]}
                    for c in candidates
                ],
            })

        return conflicts, auto_log
```

- [ ] **Step 5: Update `import_excel` signature to accept `resolutions`**

Change the `import_excel` class method signature from:

```python
    @classmethod
    def import_excel(cls, db: Session, file_bytes: bytes, overwrite: bool = False) -> Tuple[int, int, int, List[str]]:
```

to:

```python
    @classmethod
    def import_excel(
        cls,
        db: Session,
        file_bytes: bytes,
        overwrite: bool = False,
        resolutions: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, int, int, List[str]]:
```

Inside `import_excel`, find the existing block that calls `_fuzzy_find_sample`:

```python
            # ensure sample exists (fuzzy: case-insensitive, symbols stripped)
            sample = _fuzzy_find_sample(db, sample_id)
            if not sample:
                errors.append(f"Row {i+5}: sample_id '{sample_id}' not found")
                continue
            canonical_id = sample.sample_id
```

Replace with:

```python
            # Resolve sample — uses resolutions map if provided, falls back to fuzzy match
            sample = _resolve_sample(db, sample_id, resolutions)
            if not sample:
                errors.append(f"Row {i+5}: sample_id '{sample_id}' not found")
                continue
            canonical_id = sample.sample_id
```

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/services/bulk_uploads/test_actlabs_conflicts.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 7: Run full suite for regressions**

```
pytest tests/ -x -q
```

Expected: all tests pass (same count plus 7 new).

- [ ] **Step 8: Commit**

```bash
git add backend/services/bulk_uploads/actlabs_titration_data.py tests/services/bulk_uploads/test_actlabs_conflicts.py
git commit -m "[#50] add preflight_check and resolution support to ActlabsRockTitrationService

- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Update `/actlabs-rock` router endpoint

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py`
- Modify: `tests/api/test_bulk_uploads.py`

- [ ] **Step 1: Write failing API tests**

Open `tests/api/test_bulk_uploads.py` and append:

```python
# ── Issue #50: ActLabs conflict response ─────────────────────────────────────

import json
from unittest.mock import patch

def _actlabs_csv_bytes():
    import io, pandas as pd
    rows = [
        ["Report Number", "", ""], ["Report Date", "", ""],
        ["Sample ID", "FeO", "SiO2"], ["", "%", "%"],
        ["Detection Limit", "0.01", "0.01"],
        ["Analysis Method: titration", "", ""],
        ["Tamarrack", 10.0, 40.0],
    ]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, header=False, index=False)
    buf.seek(0)
    return buf.getvalue()


def test_actlabs_rock_returns_conflict_warning(client, test_db):
    """When conflicts exist and no resolutions provided, returns 200 with status='warnings'."""
    conflict_payload = [{"incoming_id": "Tamarrack", "normalized": "tamarrack",
                         "candidate_matches": [{"sample_id": "Tamarack", "similarity": 0.95}]}]
    with patch(
        "backend.api.routers.bulk_uploads.ActlabsRockTitrationService.preflight_check",
        return_value=(conflict_payload, []),
    ):
        resp = client.post(
            "/bulk-uploads/actlabs-rock",
            files={"file": ("test.csv", _actlabs_csv_bytes(), "text/csv")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "warnings"
    assert len(body["conflicts"]) == 1
    assert body["conflicts"][0]["incoming_id"] == "Tamarrack"


def test_actlabs_rock_no_conflicts_proceeds_normally(client, test_db):
    """When no conflicts, the upload executes and returns UploadResponse."""
    with patch(
        "backend.api.routers.bulk_uploads.ActlabsRockTitrationService.preflight_check",
        return_value=([], []),
    ), patch(
        "backend.api.routers.bulk_uploads.ActlabsRockTitrationService.import_excel",
        return_value=(2, 0, 0, []),
    ):
        resp = client.post(
            "/bulk-uploads/actlabs-rock",
            files={"file": ("test.csv", _actlabs_csv_bytes(), "text/csv")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "created" in body
    assert body["created"] == 2


def test_actlabs_rock_with_resolutions_proceeds(client, test_db):
    """When resolutions are provided, import_excel is called with them (no preflight check)."""
    resolutions = {"Tamarrack": "link:Tamarack"}
    with patch(
        "backend.api.routers.bulk_uploads.ActlabsRockTitrationService.import_excel",
        return_value=(1, 0, 0, []),
    ) as mock_import:
        resp = client.post(
            "/bulk-uploads/actlabs-rock",
            files={"file": ("test.csv", _actlabs_csv_bytes(), "text/csv")},
            data={"resolutions": json.dumps(resolutions)},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "created" in body
    call_kwargs = mock_import.call_args
    assert call_kwargs.kwargs.get("resolutions") == resolutions or (
        len(call_kwargs.args) >= 4 and call_kwargs.args[3] == resolutions
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/api/test_bulk_uploads.py -k "actlabs_rock_returns_conflict or actlabs_rock_no_conflict or actlabs_rock_with_res" -v
```

Expected: FAIL (endpoint hasn't changed yet).

- [ ] **Step 3: Update the endpoint**

In `backend/api/routers/bulk_uploads.py`, find the `upload_actlabs_rock` function (around line 491). Replace it entirely with:

```python
@router.post("/actlabs-rock", response_model=None)
async def upload_actlabs_rock(
    file: UploadFile = File(...),
    resolutions: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
):
    """Upload an ActLabs Rock Analysis file.

    Phase 1 (no resolutions): runs preflight; if conflicts found, returns
    ConflictCheckResponse without writing anything.

    Phase 2 (resolutions provided as JSON string): executes import with
    caller-supplied conflict resolutions.
    """
    from backend.services.bulk_uploads.actlabs_titration_data import ActlabsRockTitrationService  # noqa: PLC0415
    from backend.api.schemas.bulk_upload import ConflictCheckResponse, SampleConflict, SampleConflictMatch  # noqa: PLC0415
    from backend.config.settings import get_settings  # noqa: PLC0415

    file_bytes = await file.read()

    # Phase 2: caller has already resolved conflicts
    if resolutions is not None:
        try:
            resolution_map: dict[str, str] = json.loads(resolutions)
        except (json.JSONDecodeError, ValueError) as exc:
            return UploadResponse(created=0, updated=0, skipped=0, errors=[f"Invalid resolutions JSON: {exc}"], message="Upload failed")
        try:
            created, updated, skipped, errors = ActlabsRockTitrationService.import_excel(
                db, file_bytes, resolutions=resolution_map
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            log.error("actlabs_rock_upload_failed", error=str(exc))
            return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)], message="Upload failed")
        return UploadResponse(
            created=created, updated=updated, skipped=skipped, errors=errors,
            message=f"ActLabs Rock: {created} created, {updated} updated",
        )

    # Phase 1: preflight conflict check
    settings = get_settings()
    try:
        conflicts_raw, auto_log = ActlabsRockTitrationService.preflight_check(
            db, file_bytes, threshold=settings.actlabs_similarity_threshold
        )
    except Exception as exc:
        log.error("actlabs_rock_preflight_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)], message="Preflight failed")

    if conflicts_raw:
        response_conflicts = [
            SampleConflict(
                incoming_id=c["incoming_id"],
                normalized=c["normalized"],
                candidate_matches=[
                    SampleConflictMatch(sample_id=m["sample_id"], similarity=m["similarity"])
                    for m in c["candidate_matches"]
                ],
            )
            for c in conflicts_raw
        ]
        return ConflictCheckResponse(
            status="warnings",
            conflicts=response_conflicts,
            message=f"{len(response_conflicts)} incoming sample ID(s) closely match existing samples. Review before confirming.",
        )

    # No conflicts — proceed with import
    try:
        created, updated, skipped, errors = ActlabsRockTitrationService.import_excel(db, file_bytes)
        db.commit()
    except Exception as exc:
        db.rollback()
        log.error("actlabs_rock_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)], message="Upload failed")
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=errors,
        message=f"ActLabs Rock: {created} created, {updated} updated",
    )
```

Also add at the top of the router file (after existing imports):
```python
import json
from typing import Optional
```

(If `json` and `Optional` are already imported, skip.)

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/api/test_bulk_uploads.py -k "actlabs_rock_returns_conflict or actlabs_rock_no_conflict or actlabs_rock_with_res" -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run full suite**

```
pytest tests/ -x -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/bulk_uploads.py tests/api/test_bulk_uploads.py
git commit -m "[#50] update /actlabs-rock for two-phase conflict-check upload flow

- Tests added: yes
- Docs updated: no"
```

---

## Task 4: Frontend types and API client

**Files:**
- Modify: `frontend/src/api/bulkUploads.ts`

- [ ] **Step 1: Add conflict types and update `uploadActlabsRock`**

Open `frontend/src/api/bulkUploads.ts`. After the `BulkUploadResult` interface, add:

```typescript
export interface SampleConflictMatch {
  sample_id: string
  similarity: number
}

export interface SampleConflict {
  incoming_id: string
  normalized: string
  candidate_matches: SampleConflictMatch[]
}

export interface ConflictCheckResult {
  status: 'warnings'
  conflicts: SampleConflict[]
  message: string
}
```

Replace the existing `uploadActlabsRock` line:

```typescript
  uploadActlabsRock: (file: File) =>
    post<BulkUploadResult>('/bulk-uploads/actlabs-rock', fileForm(file)),
```

with:

```typescript
  uploadActlabsRock: (file: File, resolutions?: Record<string, string>) => {
    const fd = fileForm(file)
    if (resolutions) fd.append('resolutions', JSON.stringify(resolutions))
    return post<BulkUploadResult | ConflictCheckResult>('/bulk-uploads/actlabs-rock', fd)
  },
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/bulkUploads.ts
git commit -m "[#50] add ConflictCheckResult types and update uploadActlabsRock API client

- Tests added: no
- Docs updated: no"
```

---

## Task 5: `SampleConflictModal` component

**Files:**
- Create: `frontend/src/components/SampleConflictModal.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/SampleConflictModal.tsx`:

```tsx
import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { Button } from '@/components/ui'
import type { SampleConflict } from '@/api/bulkUploads'

export type ConflictResolution =
  | { action: 'link'; existingSampleId: string }
  | { action: 'create' }

export interface SampleConflictModalProps {
  open: boolean
  conflicts: SampleConflict[]
  onConfirm: (resolutions: Record<string, string>) => void
  onCancel: () => void
}

/** Blocking modal shown when the ActLabs upload finds near-duplicate sample IDs.
 *  The user must resolve every conflict before the upload can proceed.
 */
export function SampleConflictModal({ open, conflicts, onConfirm, onCancel }: SampleConflictModalProps) {
  const [choices, setChoices] = useState<Record<string, string>>({})

  const setChoice = (incomingId: string, value: string) =>
    setChoices((prev) => ({ ...prev, [incomingId]: value }))

  const allResolved = conflicts.every((c) => choices[c.incoming_id] !== undefined)

  const handleConfirm = () => {
    onConfirm(choices)
    setChoices({})
  }

  const handleCancel = () => {
    setChoices({})
    onCancel()
  }

  return (
    <Modal
      open={open}
      onClose={handleCancel}
      title="Sample ID Conflicts Detected"
      description="The following incoming sample IDs closely match existing samples. Choose how to handle each one before the upload can proceed."
      size="lg"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={handleCancel}>Cancel Upload</Button>
          <Button variant="primary" onClick={handleConfirm} disabled={!allResolved}>
            Confirm &amp; Upload
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {conflicts.map((conflict) => (
          <div
            key={conflict.incoming_id}
            className="rounded border border-surface-border p-3 space-y-2"
          >
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-ink-primary">Incoming:</span>
              <code className="text-sm font-mono bg-surface-secondary px-1 rounded text-amber-400">
                {conflict.incoming_id}
              </code>
            </div>

            <p className="text-xs text-ink-muted">Close matches in database:</p>
            <div className="space-y-1 pl-2">
              {conflict.candidate_matches.map((m) => (
                <label
                  key={m.sample_id}
                  className="flex items-center gap-2 cursor-pointer text-sm text-ink-primary"
                >
                  <input
                    type="radio"
                    name={`conflict-${conflict.incoming_id}`}
                    value={`link:${m.sample_id}`}
                    checked={choices[conflict.incoming_id] === `link:${m.sample_id}`}
                    onChange={() => setChoice(conflict.incoming_id, `link:${m.sample_id}`)}
                    className="accent-brand-primary"
                  />
                  <span>
                    Link to <code className="font-mono text-xs bg-surface-secondary px-1 rounded">{m.sample_id}</code>
                  </span>
                  <span className="text-xs text-ink-muted ml-auto">
                    {Math.round(m.similarity * 100)}% match
                  </span>
                </label>
              ))}
            </div>

            <label className="flex items-center gap-2 cursor-pointer text-sm text-ink-primary pl-2">
              <input
                type="radio"
                name={`conflict-${conflict.incoming_id}`}
                value="create"
                checked={choices[conflict.incoming_id] === 'create'}
                onChange={() => setChoice(conflict.incoming_id, 'create')}
                className="accent-brand-primary"
              />
              <span>Create as new sample</span>
            </label>
          </div>
        ))}
      </div>
    </Modal>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SampleConflictModal.tsx
git commit -m "[#50] add SampleConflictModal component for conflict resolution UI

- Tests added: no
- Docs updated: no"
```

---

## Task 6: `ActlabsUploadRow` + wire up `BulkUploads.tsx`

**Files:**
- Create: `frontend/src/pages/ActlabsUploadRow.tsx`
- Modify: `frontend/src/pages/BulkUploads.tsx`

- [ ] **Step 1: Create `ActlabsUploadRow`**

Create `frontend/src/pages/ActlabsUploadRow.tsx`:

```tsx
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { UploadRow } from './BulkUploadRow'
import { SampleConflictModal } from '@/components/SampleConflictModal'
import { bulkUploadsApi, ConflictCheckResult, BulkUploadResult } from '@/api/bulkUploads'
import { useToast } from '@/components/ui'

interface ActlabsUploadRowProps {
  isOpen: boolean
  onToggle: () => void
}

function isConflictCheckResult(r: BulkUploadResult | ConflictCheckResult): r is ConflictCheckResult {
  return (r as ConflictCheckResult).status === 'warnings'
}

/** UploadRow for ActLabs Rock Analysis — handles two-phase conflict-check flow. */
export function ActlabsUploadRow({ isOpen, onToggle }: ActlabsUploadRowProps) {
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [conflicts, setConflicts] = useState<ConflictCheckResult['conflicts'] | null>(null)
  const { error: toastError } = useToast()

  const confirmMutation = useMutation({
    mutationFn: ({ file, resolutions }: { file: File; resolutions: Record<string, string> }) =>
      bulkUploadsApi.uploadActlabsRock(file, resolutions) as Promise<BulkUploadResult>,
  })

  const uploadFn = async (file: File): Promise<BulkUploadResult> => {
    const result = await bulkUploadsApi.uploadActlabsRock(file)
    if (isConflictCheckResult(result)) {
      setPendingFile(file)
      setConflicts(result.conflicts)
      // Throw so BulkUploadRow treats this as "not complete" — we handle result ourselves
      throw new Error('__conflicts__')
    }
    return result as BulkUploadResult
  }

  const handleConflictConfirm = async (resolutions: Record<string, string>) => {
    if (!pendingFile) return
    setConflicts(null)
    try {
      await confirmMutation.mutateAsync({ file: pendingFile, resolutions })
    } catch (err) {
      toastError('Upload failed', (err as Error).message)
    }
    setPendingFile(null)
  }

  const handleConflictCancel = () => {
    setConflicts(null)
    setPendingFile(null)
  }

  return (
    <>
      <UploadRow
        id="actlabs-rock"
        title="ActLabs Rock Analysis"
        description="Import ActLabs titration report (Excel or CSV)"
        helpText="Accepts ActLabs standard report format. Row 3 = analyte symbols, Row 4 = units. Values like '<0.01', 'nd', 'na' are handled. Analytes are auto-created from file headers."
        accept=".xlsx,.xls,.csv"
        uploadFn={uploadFn}
        isOpen={isOpen}
        onToggle={onToggle}
      />
      <SampleConflictModal
        open={conflicts !== null}
        conflicts={conflicts ?? []}
        onConfirm={handleConflictConfirm}
        onCancel={handleConflictCancel}
      />
    </>
  )
}
```

- [ ] **Step 2: Update `BulkUploads.tsx` to use `ActlabsUploadRow`**

At the top of `frontend/src/pages/BulkUploads.tsx`, add the import:

```typescript
import { ActlabsUploadRow } from './ActlabsUploadRow'
```

Find the existing ActLabs UploadRow block (around line 290-301):

```tsx
        {/* 10 — ActLabs Rock Analysis */}
        <UploadRow
          id="actlabs-rock"
          title="ActLabs Rock Analysis"
          description="Import ActLabs titration report (Excel or CSV)"
          helpText="Accepts ActLabs standard report format. Row 3 = analyte symbols, Row 4 = units. Values like '<0.01', 'nd', 'na' are handled. Analytes are auto-created from file headers."
          accept=".xlsx,.xls,.csv"
          uploadFn={(file) => bulkUploadsApi.uploadActlabsRock(file)}
          isOpen={isOpen('actlabs-rock')}
          onToggle={() => toggle('actlabs-rock')}
        />
```

Replace with:

```tsx
        {/* 10 — ActLabs Rock Analysis */}
        <ActlabsUploadRow
          isOpen={isOpen('actlabs-rock')}
          onToggle={() => toggle('actlabs-rock')}
        />
```

- [ ] **Step 3: Verify TypeScript compiles**

```
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 4: Manual smoke test**

With both the backend and frontend dev server running:

1. Open the Bulk Uploads page and expand the ActLabs Rock Analysis row.
2. Upload any CSV/XLS file where the sample IDs exactly match existing ones → should upload normally with no modal.
3. Upload a file containing `TAMARACK` when a sample `Tamarack` exists → verify the modal appears with one conflict, "Link to Tamarack" as a radio option, and a similarity percentage.
4. Select "Link to Tamarack", click "Confirm & Upload" → verify upload succeeds and no duplicate sample is created.
5. Upload same file with a clear near-typo (e.g. `Tamarrack`) → verify modal appears, select "Create as new", confirm → verify a new SampleInfo record appears.
6. Click "Cancel Upload" → verify nothing is written and the modal closes cleanly.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ActlabsUploadRow.tsx frontend/src/pages/BulkUploads.tsx
git commit -m "[#50] add ActlabsUploadRow with two-phase conflict modal flow

- Tests added: no
- Docs updated: no"
```

---

## Self-Review

### Spec Coverage Check

| Requirement | Task |
|-------------|------|
| Normalize before lookup (case, whitespace) | Task 1 — `_id_match` already handles this; Task 2 migrates local fns |
| Fuzzy similarity check with rapidfuzz WRatio ≥ 0.90 | Task 1 `find_similar_samples` |
| Pre-commit warning payload `{status: "warnings", conflicts: [...]}` | Task 3 router |
| Frontend blocking modal with incoming ID, match name, similarity | Task 5 `SampleConflictModal` |
| "Link to existing" — associate with matched sample, no new record | Task 2 `_resolve_sample`, Task 6 confirm flow |
| "Create as new" — new SampleInfo record created | Task 2 `_resolve_sample` |
| "Cancel upload" — nothing written | Task 6 `handleConflictCancel` |
| Exact normalized matches auto-resolved silently + logged | Task 2 `preflight_check` auto_log + structlog |
| Similarity threshold configurable via env var (default 0.90) | Task 1 `Settings.actlabs_similarity_threshold` |
| No regression when no near-matches | Task 3 test `test_actlabs_rock_no_conflicts_proceeds_normally` |

### Placeholder Scan

None found — all steps contain complete code.

### Type Consistency

- `SimilarSampleMatch` (TypedDict in `_id_match.py`) has keys `sample_id: str`, `similarity: float` — consistent with all usages in `find_similar_samples`, `preflight_check`, and router.
- `ConflictCheckResult` (TS interface) mirrors `ConflictCheckResponse` (Pydantic) exactly.
- `uploadActlabsRock(file, resolutions?)` returns `Promise<BulkUploadResult | ConflictCheckResult>` — consistent with both response branches in router.
- `_resolve_sample(db, sample_id, resolutions)` — called in `import_excel` at existing `_fuzzy_find_sample` call site; signature matches.
