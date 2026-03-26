# Sample Characterized Logic — Developer Reference

This document explains the `evaluate_characterized` function, the three characterization criteria, when the function is called, and how manual overrides interact with automatic evaluation.

---

## Source

`backend/services/samples.py` — `evaluate_characterized(db: Session, sample_id: str) -> bool`

---

## The Three Criteria

A sample is considered **Characterized** (`SampleInfo.characterized = True`) when **at least one** of the following three criteria is satisfied:

### Criterion 1 — Mineralogy (XRD)

```
ExternalAnalysis(sample_id=X, analysis_type="XRD")
  AND
XRDAnalysis linked to that ExternalAnalysis
```

The check uses a correlated subquery:

```python
xrd = db.scalar(
    select(ExternalAnalysis)
    .join(XRDAnalysis, XRDAnalysis.external_analysis_id == ExternalAnalysis.id)
    .where(
        ExternalAnalysis.sample_id == sample_id,
        ExternalAnalysis.analysis_type == AnalysisType.XRD.value,
    )
    .limit(1)
)
```

### Criterion 2 — Bulk Chemistry (Elemental / Titration)

```
ExternalAnalysis(sample_id=X, analysis_type IN ("Elemental", "Titration"))
  AND
At least one ElementalAnalysis row linked to that ExternalAnalysis
```

```python
elemental = db.scalar(
    select(ExternalAnalysis)
    .join(ElementalAnalysis, ElementalAnalysis.external_analysis_id == ExternalAnalysis.id)
    .where(
        ExternalAnalysis.sample_id == sample_id,
        ExternalAnalysis.analysis_type.in_([
            AnalysisType.ELEMENTAL.value,
            AnalysisType.TITRATION.value,
        ]),
    )
    .limit(1)
)
```

### Criterion 3 — Portable XRF (pXRF)

```
ExternalAnalysis(sample_id=X, analysis_type="pXRF", pxrf_reading_no IS NOT NULL)
  AND
PXRFReading(reading_no = normalized(pxrf_reading_no)) EXISTS
```

The `pxrf_reading_no` is normalized before lookup using `normalize_pxrf_reading_no`:
- Strips leading/trailing whitespace
- Converts integer-like floats (`"1.0"` → `"1"`)

```python
pxrf_analyses = db.scalars(
    select(ExternalAnalysis).where(
        ExternalAnalysis.sample_id == sample_id,
        ExternalAnalysis.analysis_type == AnalysisType.PXRF.value,
        ExternalAnalysis.pxrf_reading_no.isnot(None),
    )
).all()
for ea in pxrf_analyses:
    norm = normalize_pxrf_reading_no(ea.pxrf_reading_no)
    if db.get(PXRFReading, norm):
        return True
```

---

## When `evaluate_characterized` Is Called

| Trigger | Code location |
|---------|---------------|
| `POST /api/samples` | `routers/samples.py` — create endpoint, after initial `db.flush()` |
| `PATCH /api/samples/{id}` | `routers/samples.py` — update endpoint, **only if** `characterized` is NOT in the PATCH payload |
| `POST /api/samples/{id}/analyses` | `routers/samples.py` — analysis create endpoint, after analysis is committed |
| `DELETE /api/samples/{id}/analyses/{id}` | `routers/samples.py` — analysis delete endpoint, after deletion |

It is **not** called on:
- Photo upload/delete (photos don't affect characterization)
- Experiment linking/unlinking
- PATCH when `characterized` is explicitly provided in the payload

---

## Manual Override Behaviour

When a `PATCH /api/samples/{id}` request includes `"characterized": true` (or `false`) in the body, the automatic evaluation is **skipped** for that request. The manual value is persisted as-is.

This is controlled by:

```python
updates = payload.model_dump(exclude_unset=True)
manual_characterized = "characterized" in updates

for field, value in updates.items():
    setattr(sample, field, value)

if not manual_characterized:
    sample.characterized = evaluate_characterized(db, sample_id)
```

The next time an analysis is added or deleted, the automatic evaluation runs again and may overwrite the manual override.

---

## pXRF Reading Normalization

`normalize_pxrf_reading_no(raw: str) -> str` in `backend/services/samples.py`:

1. `.strip()` — remove leading/trailing whitespace
2. If the result matches `\d+\.0+` (integer-like float), convert via `str(int(float(v)))`

Examples:
| Input | Output |
|-------|--------|
| `" 42 "` | `"42"` |
| `"1.0"` | `"1"` |
| `"12.00"` | `"12"` |
| `"A001"` | `"A001"` |
| `"3.14"` | `"3.14"` (unchanged — not integer-like) |

---

## Audit Trail

Every create/update/delete operation on `SampleInfo` calls `log_sample_modification()` in the same service file, which writes a `ModificationsLog` row with:
- `sample_id` — the denormalized sample string ID (nullable String column, no FK; added in M9 migration `d275ae3e1994`)
- `modified_by` — passed from the request (defaults to `"system"` if not provided)
- `modification_type` — `"create"`, `"update"`, or `"delete"`
- `modified_table` — `"sample_info"`
- `old_values` / `new_values` — JSON dicts

Note: `ModificationsLog.sample_id` has no foreign key constraint — it's a denormalized string ID that remains after the sample is deleted.

---

## Tests

Unit tests for `evaluate_characterized` and `normalize_pxrf_reading_no` are in:
`tests/services/test_samples_service.py`

Integration tests for all sample endpoints (including characterized auto-evaluation) are in:
`tests/api/test_samples.py`
