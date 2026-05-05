# Change Sample ID on Existing Experiment (with Calculation Re-trigger)

## Summary

Add the ability to reassign the rock sample linked to an existing experiment from the Experiment Detail view. When the sample ID changes, the backend must explicitly re-run the full calculation chain — conditions first (to recompute `total_ferrous_iron_g`), then all scalar result entries (to recompute `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct`) — because those yields depend on FeO characterization data resolved via `sample_id`.

---

## Background

`Experiment.sample_id` is used by the calculation engine to look up the rock's FeO wt% from `ExternalAnalysis → ElementalAnalysis → Analyte` and derive `total_ferrous_iron_g` on `ExperimentalConditions`. That value then feeds the ferrous iron yield calculations on every `ScalarResults` row.

Currently there is no UI path to change `sample_id` on an experiment after creation. This surfaced as a concrete problem with `HPHT_112`: a bulk upload created duplicate `SampleInfo` entries for `Tamarack` under different casings, leaving the experiment pointing to a variant with no FeO data. With no way to re-point the experiment via the UI, the ferrous iron yield fields are stuck at `NULL`.

The fix for HPHT_112 is a side-effect of this feature, but the feature itself is genuinely needed — experiment sample assignments occasionally need to be corrected, and there is currently no path to do that without direct database access.

---

## Proposed Solution

### Backend

#### Endpoint

Extend the existing `PATCH /api/experiments/{experiment_id}` to accept a `sample_id` field in the request body, or add a dedicated route if the general PATCH schema is too constrained:

```
PATCH /api/experiments/{experiment_id}
Body: { "sample_id": "Tamarack" }
```

#### Service method

In the experiment update service (likely `backend/services/experiments.py` or the router directly):

```python
def update_experiment_sample_id(experiment_id: str, new_sample_id: str, db: Session):
    # 1. Validate the new sample exists
    sample = db.get(SampleInfo, new_sample_id)
    if not sample:
        raise HTTPException(status_code=404, detail=f"Sample '{new_sample_id}' not found")

    # 2. Update the experiment
    exp = db.query(Experiments).filter_by(experiment_id=experiment_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    exp.sample_id = new_sample_id
    db.flush()

    # 3. Re-run conditions calculations (recomputes total_ferrous_iron_g)
    if exp.conditions:
        registry.recalculate(exp.conditions, db)
        db.flush()

    # 4. Re-run scalar result calculations (recomputes ferrous_iron_yield_*_pct)
    for result in exp.scalar_results:
        registry.recalculate(result, db)

    db.commit()
```

**Why steps 3 and 4 are both required:** `registry.recalculate` on `ExperimentalConditions` only updates `total_ferrous_iron_g`. The yield fields (`ferrous_iron_yield_h2_pct`, `ferrous_iron_yield_nh3_pct`) live on `ScalarResults` and will not update unless recalculation is also triggered on each result row. Both must fire in order: conditions first, scalar results second, since the yield calculations read `total_ferrous_iron_g` from conditions.

**Important:** Verify the exact relationship attribute names (`exp.conditions`, `exp.scalar_results`) against the actual SQLAlchemy models before implementing. The names above reflect the documented traversal path in `CALCULATIONS.md`.

#### Response

Return the updated experiment object (same shape as `GET /api/experiments/{experiment_id}`), so the frontend can invalidate and re-fetch in one round trip.

---

### Frontend

#### Location

`ExperimentDetail.tsx` — the Overview section of the experiment detail page, where other mutable fields (status, notes, etc.) are displayed and edited.

#### Behavior

- Display the current sample ID as a read-only label with an **Edit** button (or pencil icon) next to it, consistent with how other inline edits work in this view.
- Clicking Edit replaces the label with the existing `SampleSelector` component (already used in `NewExperiment/Step1BasicInfo.tsx`). Reuse it directly rather than building a new one.
- On selection, call a `useMutation` that hits `PATCH /api/experiments/{experiment_id}` with `{ sample_id: newId }`.
- On success: invalidate `['experiments', id]` and show a toast confirming the update and that calculations have been re-run.
- On error: show a toast with the error message; revert the selector to the previous value.
- On cancel (Escape or clicking away without selecting): revert to read-only display with no change.

#### API layer

Add a method to `src/api/experiments.ts`:

```ts
patchSampleId: (experimentId: string, sampleId: string) =>
  apiClient.patch(`/experiments/${experimentId}`, { sample_id: sampleId })
    .then(r => r.data),
```

---

## Acceptance Criteria

- [ ] A user can change the sample ID on an existing experiment from the Experiment Detail view without leaving the page.
- [ ] The `SampleSelector` component is reused; no new search/autocomplete widget is built.
- [ ] After a successful save, `total_ferrous_iron_g` on `ExperimentalConditions` reflects the new sample's FeO data.
- [ ] After a successful save, `ferrous_iron_yield_h2_pct` and `ferrous_iron_yield_nh3_pct` on all `ScalarResults` rows for the experiment reflect the updated conditions.
- [ ] If the new `sample_id` does not exist in `SampleInfo`, the backend returns 404 and no change is committed.
- [ ] A sample with no FeO data (or no `ExternalAnalysis` of type `Elemental`/`Bulk Elemental Composition`) leaves `total_ferrous_iron_g` as `NULL` — not an error, just a NULL propagation. The yield fields also become `NULL`.
- [ ] Changing the sample ID is reflected in the audit log (`ModificationsLog` or equivalent) if one is written for experiment updates.
- [ ] `HPHT_112` can be re-pointed to the correct `Tamarack` variant via this UI, after which ferrous iron yield fields populate correctly.

---

## Out of Scope

- Merging or deduplicating `SampleInfo` rows (covered by the fuzzy-matching issue).
- Changing `sample_id` in bulk across multiple experiments.
- Any changes to `enums.py`.

---

## Affected Files

| File | Change |
|------|--------|
| `backend/routers/experiments.py` | Add `sample_id` to the PATCH schema / handler |
| `backend/services/experiments.py` | Service method with recalculation chain |
| `frontend/src/pages/ExperimentDetail.tsx` | Inline sample ID editor |
| `frontend/src/api/experiments.ts` | `patchSampleId` method |

---

## Test Plan

**Unit (backend)**
- `update_experiment_sample_id` with a valid new sample ID: assert `exp.sample_id` updated, `registry.recalculate` called on both conditions and each scalar result (mock the registry).
- `update_experiment_sample_id` with a non-existent sample ID: assert 404 raised, no DB writes committed.
- `update_experiment_sample_id` on an experiment with no conditions or no scalar results: assert no crash, conditions/results blocks are no-ops.

**Integration (backend)**
- `PATCH /api/experiments/HPHT_112` with `{ "sample_id": "Tamarack" }` (the correct variant): assert `total_ferrous_iron_g` is non-NULL and `ferrous_iron_yield_h2_pct` / `ferrous_iron_yield_nh3_pct` update on the real test DB.
- `PATCH /api/experiments/HPHT_112` with `{ "sample_id": "DoesNotExist" }`: assert 404.

**E2E (manual)**
- Open HPHT_112 in the UI. Observe ferrous iron yield fields show `—`.
- Click Edit on the sample ID field. Select the correct `Tamarack` variant.
- Save. Verify toast appears and yield fields now show a numeric value.

---

## Embedded Claude Code CLI Prompt

```
Read backend/routers/experiments.py and backend/services/experiments.py (or wherever
the experiment PATCH logic lives). Then read backend/services/calculations/__init__.py
to confirm the registry.recalculate signature and how it's called.

Implement the following:

1. Extend the PATCH /api/experiments/{experiment_id} endpoint to accept an optional
   `sample_id: str` field. If provided:
   a. Validate the sample exists in SampleInfo (404 if not).
   b. Update Experiment.sample_id.
   c. Call registry.recalculate on ExperimentalConditions (flush first).
   d. Call registry.recalculate on each ScalarResults row for the experiment.
   e. Commit.
   Verify the exact relationship attribute names (conditions, scalar_results) against
   the actual SQLAlchemy model before using them.

2. In frontend/src/api/experiments.ts, add a patchSampleId method that calls
   PATCH /api/experiments/{experimentId} with { sample_id }.

3. In frontend/src/pages/ExperimentDetail.tsx, add an inline sample ID editor to the
   Overview section. Reuse the SampleSelector component from NewExperiment/Step1BasicInfo.tsx.
   On save, call patchSampleId, invalidate ['experiments', id], and show a success toast
   that mentions calculations were re-run. On error, show an error toast.

Do not modify enums.py. Do not modify any Alembic migration files. Scope changes to
the four files listed above plus any existing test files for experiment endpoints.

After implementing, run the existing experiment endpoint tests to confirm no regressions.
```

---

## Labels

`enhancement`, `backend`, `frontend`, `calculations`, `data-integrity`

## Priority

High — blocks accurate ferrous iron yield reporting for HPHT_112 and any future experiment with a mis-assigned sample.
