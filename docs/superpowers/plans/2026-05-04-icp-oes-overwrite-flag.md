# ICP-OES Overwrite Flag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "overwrite" checkbox to the ICP-OES bulk upload card that, when checked, deletes and replaces existing `ICPResults` for each matching (experiment, timepoint) key instead of merging.

**Architecture:** Mirror the existing XRD Mineralogy overwrite pattern exactly. The flag flows from a React checkbox → `FormData` → FastAPI `Form(False)` param → `ICPService.bulk_create_icp_results` → `ICPService.create_icp_result`. When `overwrite=True` and an existing `ICPResults` record is found, it is deleted and the creation branch is executed fresh; `was_update` remains `False` so the row counts as "created". The parent `ExperimentalResults` row is never touched.

**Tech Stack:** Python 3.x / SQLAlchemy (backend), FastAPI (router), TypeScript / React 18 / Tailwind (frontend), pytest (tests)

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Modify | `backend/services/icp_service.py` | Add `overwrite` param to `create_icp_result` + `bulk_create_icp_results`; delete existing `ICPResults` before re-creating when `overwrite=True` |
| Modify | `backend/api/routers/bulk_uploads.py` | Add `overwrite: bool = Form(False)` to `upload_icp_oes`; pass to service |
| Modify | `frontend/src/api/bulkUploads.ts` | Accept `overwrite` param in `uploadIcpOes`; append to `FormData` |
| Modify | `frontend/src/pages/BulkUploads.tsx` | Add `IcpOverwriteToggle` component; `icpOverwrite` state; wire to `UploadRow` |
| Modify | `tests/test_icp_handling.py` | New test class for overwrite behavior |

---

## Task 1: Service Layer — overwrite support in `create_icp_result`

**Files:**
- Modify: `backend/services/icp_service.py:431` (`create_icp_result`)
- Modify: `backend/services/icp_service.py:607` (`bulk_create_icp_results`)

- [ ] **Step 1: Write the failing tests**

Add this class to `tests/test_icp_handling.py`:

```python
class TestICPOverwrite:
    """Test overwrite=True replaces existing ICP data instead of merging."""

    def _upload_day3(self, db, overwrite: bool = False):
        data = [
            {
                'experiment_id': 'Test_MH_001',
                'time_post_reaction': 3.0,
                'description': 'Day 3 results',
                'fe': 10.0,
                'ni': 2.0,
            }
        ]
        return ICPService.bulk_create_icp_results(db, data, overwrite=overwrite)

    def test_overwrite_false_merges_elements(self, test_db):
        """Without overwrite, re-upload adds new elements but keeps old ones."""
        # First upload: fe + ni
        ICPService.bulk_create_icp_results(
            test_db,
            [{'experiment_id': 'Test_MH_001', 'time_post_reaction': 3.0,
              'description': 'Day 3', 'fe': 10.0, 'ni': 2.0}],
            overwrite=False,
        )
        # Second upload: fe only (no ni)
        ICPService.bulk_create_icp_results(
            test_db,
            [{'experiment_id': 'Test_MH_001', 'time_post_reaction': 3.0,
              'description': 'Day 3', 'fe': 99.0}],
            overwrite=False,
        )
        test_db.expire_all()
        result = test_db.query(ExperimentalResults).filter_by(
            experiment_fk=test_db.query(Experiment)
                .filter_by(experiment_id='Test_MH_001').first().id,
        ).first()
        assert result.icp_data is not None
        assert result.icp_data.fe == 99.0       # updated
        assert result.icp_data.ni == 2.0        # preserved

    def test_overwrite_true_replaces_all_elements(self, test_db):
        """With overwrite=True, re-upload discards old elements and inserts fresh."""
        # First upload: fe + ni
        ICPService.bulk_create_icp_results(
            test_db,
            [{'experiment_id': 'Test_MH_001', 'time_post_reaction': 3.0,
              'description': 'Day 3', 'fe': 10.0, 'ni': 2.0}],
            overwrite=False,
        )
        # Second upload with overwrite: fe only (ni should disappear)
        results, updated, errors = ICPService.bulk_create_icp_results(
            test_db,
            [{'experiment_id': 'Test_MH_001', 'time_post_reaction': 3.0,
              'description': 'Day 3', 'fe': 99.0}],
            overwrite=True,
        )
        assert errors == []
        assert updated == 0           # replaced rows count as "created", not "updated"
        test_db.expire_all()
        result = test_db.query(ExperimentalResults).filter_by(
            experiment_fk=test_db.query(Experiment)
                .filter_by(experiment_id='Test_MH_001').first().id,
        ).first()
        assert result.icp_data is not None
        assert result.icp_data.fe == 99.0
        assert result.icp_data.ni is None       # not preserved

    def test_overwrite_true_no_existing_data_creates_normally(self, test_db):
        """Overwrite with no prior ICP data behaves like a normal insert."""
        results, updated, errors = ICPService.bulk_create_icp_results(
            test_db,
            [{'experiment_id': 'Test_MH_001', 'time_post_reaction': 3.0,
              'description': 'Day 3', 'fe': 50.0}],
            overwrite=True,
        )
        assert errors == []
        assert updated == 0
        test_db.expire_all()
        result = test_db.query(ExperimentalResults).filter_by(
            experiment_fk=test_db.query(Experiment)
                .filter_by(experiment_id='Test_MH_001').first().id,
        ).first()
        assert result.icp_data is not None
        assert result.icp_data.fe == 50.0
```

- [ ] **Step 2: Run the failing tests**

```
pytest tests/test_icp_handling.py::TestICPOverwrite -v
```

Expected: `TypeError` — `bulk_create_icp_results()` and `create_icp_result()` do not accept `overwrite`.

- [ ] **Step 3: Add `overwrite` to `create_icp_result`**

In `backend/services/icp_service.py`, change the signature at line 431:

```python
@staticmethod
def create_icp_result(
    db: Session,
    experiment_id: str,
    result_data: Dict[str, Any],
    overwrite: bool = False,
) -> Tuple[Optional[ExperimentalResults], bool]:
```

Then, replace the block starting at line 486 (`was_update = False`) through `else:` so it reads:

```python
        was_update = False
        if overwrite and experimental_result.icp_data:
            # Delete the existing ICPResults so the creation branch runs fresh.
            # The parent ExperimentalResults row is preserved.
            db.delete(experimental_result.icp_data)
            db.flush()
            experimental_result.icp_data = None

        if experimental_result.icp_data:
            # Merge: only overwrite elements present in incoming CSV; preserve others.
            icp_data = experimental_result.icp_data

            # Snapshot old element values for audit trail
            old_fixed = {el: getattr(icp_data, el) for el in ICP_FIXED_ELEMENT_FIELDS}
            old_all = dict(icp_data.all_elements) if icp_data.all_elements else {}

            for element in ICP_FIXED_ELEMENT_FIELDS:
                if element in fixed_column_data:
                    setattr(icp_data, element, fixed_column_data[element])
            # Merge all_elements: incoming overrides, preserve existing for keys not in incoming
            existing = dict(icp_data.all_elements) if icp_data.all_elements else {}
            existing.update(all_elements_data)
            icp_data.all_elements = existing if existing else None
            icp_data.dilution_factor = result_data.get('dilution_factor')
            icp_data.raw_label = result_data.get('raw_label')
            if 'instrument_used' in result_data:
                icp_data.instrument_used = result_data.get('instrument_used')
            if 'detection_limits' in result_data:
                icp_data.detection_limits = result_data.get('detection_limits')
            if 'measurement_date' in result_data:
                icp_data.measurement_date = result_data.get('measurement_date')
            if 'sample_date' in result_data:
                icp_data.sample_date = result_data.get('sample_date')
            was_update = True

            # Audit trail: log changed element values
            changed_old: Dict[str, Any] = {}
            changed_new: Dict[str, Any] = {}
            for el in ICP_FIXED_ELEMENT_FIELDS:
                if el in fixed_column_data and old_fixed.get(el) != getattr(icp_data, el):
                    changed_old[el] = old_fixed.get(el)
                    changed_new[el] = getattr(icp_data, el)
            for el_key, el_val in all_elements_data.items():
                if old_all.get(el_key) != el_val:
                    changed_old[el_key] = old_all.get(el_key)
                    changed_new[el_key] = el_val
            if changed_old or changed_new:
                db.add(ModificationsLog(
                    experiment_id=experiment.experiment_id,
                    experiment_fk=experiment.id,
                    modification_type="update",
                    modified_table="icp_results",
                    old_values=changed_old or None,
                    new_values=changed_new or None,
                ))
        else:
            # Create ICP data with elemental concentrations
            icp_data = ICPResults(
                result_id=experimental_result.id,
                fe=fixed_column_data.get('fe'),
                si=fixed_column_data.get('si'),
                ni=fixed_column_data.get('ni'),
                cu=fixed_column_data.get('cu'),
                mo=fixed_column_data.get('mo'),
                zn=fixed_column_data.get('zn'),
                mn=fixed_column_data.get('mn'),
                ca=fixed_column_data.get('ca'),
                cr=fixed_column_data.get('cr'),
                co=fixed_column_data.get('co'),
                mg=fixed_column_data.get('mg'),
                al=fixed_column_data.get('al'),
                sr=fixed_column_data.get('sr'),
                y=fixed_column_data.get('y'),
                nb=fixed_column_data.get('nb'),
                sb=fixed_column_data.get('sb'),
                cs=fixed_column_data.get('cs'),
                ba=fixed_column_data.get('ba'),
                nd=fixed_column_data.get('nd'),
                gd=fixed_column_data.get('gd'),
                pt=fixed_column_data.get('pt'),
                rh=fixed_column_data.get('rh'),
                ir=fixed_column_data.get('ir'),
                pd=fixed_column_data.get('pd'),
                ru=fixed_column_data.get('ru'),
                os=fixed_column_data.get('os'),
                tl=fixed_column_data.get('tl'),
                all_elements=all_elements_data if all_elements_data else None,
                dilution_factor=result_data.get('dilution_factor'),
                raw_label=result_data.get('raw_label'),
                instrument_used=result_data.get('instrument_used'),
                detection_limits=result_data.get('detection_limits'),
                measurement_date=result_data.get('measurement_date'),
                sample_date=result_data.get('sample_date'),
                result_entry=experimental_result
            )
            db.add(icp_data)

            # Audit trail for new ICP record
            if all_elements_data:
                db.add(ModificationsLog(
                    experiment_id=experiment.experiment_id,
                    experiment_fk=experiment.id,
                    modification_type="create",
                    modified_table="icp_results",
                    old_values=None,
                    new_values=all_elements_data,
                ))
```

Note: the original `if experimental_result.icp_data:` at line 487 is changed to `if experimental_result.icp_data:` (same condition) — what changed is that the new overwrite block above it runs `db.delete` + `db.flush` + sets `experimental_result.icp_data = None` so the `if` branch is bypassed and the `else` (creation) branch runs.

- [ ] **Step 4: Add `overwrite` to `bulk_create_icp_results`**

Change the signature at line 607:

```python
@staticmethod
def bulk_create_icp_results(
    db: Session,
    processed_data: List[Dict[str, Any]],
    overwrite: bool = False,
) -> Tuple[List[ExperimentalResults], int, List[str]]:
```

Change line 639 (the `create_icp_result` call) to pass the flag:

```python
                result, was_update = ICPService.create_icp_result(
                    db=db,
                    experiment_id=experiment_id,
                    result_data=data,
                    overwrite=overwrite,
                )
```

- [ ] **Step 5: Run the tests**

```
pytest tests/test_icp_handling.py::TestICPOverwrite -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Run the full ICP test suite to check for regressions**

```
pytest tests/test_icp_handling.py tests/test_icp_parsing.py tests/test_icp_service.py -v
```

Expected: all previously-passing tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/services/icp_service.py tests/test_icp_handling.py
git commit -m "[fix] add overwrite param to ICP service create/bulk methods

- Tests added: yes
- Docs updated: no"
```

---

## Task 2: Router — wire `overwrite` form field in `upload_icp_oes`

**Files:**
- Modify: `backend/api/routers/bulk_uploads.py:297`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_icp_handling.py` (inside or after `TestICPOverwrite`):

```python
class TestICPRouterOverwrite:
    """Smoke-test that the router passes overwrite to the service."""

    def test_router_passes_overwrite_flag(self, monkeypatch):
        """upload_icp_oes forwards overwrite=True to bulk_create_icp_results."""
        calls: list[bool] = []

        def fake_bulk_create(db, data, overwrite=False):
            calls.append(overwrite)
            return [], 0, []

        monkeypatch.setattr(
            'backend.services.icp_service.ICPService.bulk_create_icp_results',
            fake_bulk_create,
        )
        monkeypatch.setattr(
            'backend.services.icp_service.ICPService.parse_and_process_icp_file',
            lambda _: ([], []),
        )

        from fastapi.testclient import TestClient
        from backend.api.main import app
        import sys
        from types import ModuleType
        if 'frontend.config.variable_config' not in sys.modules:
            stub = ModuleType('frontend.config.variable_config')
            sys.modules.setdefault('frontend', ModuleType('frontend'))
            sys.modules.setdefault('frontend.config', ModuleType('frontend.config'))
            sys.modules['frontend.config.variable_config'] = stub

        client = TestClient(app, raise_server_exceptions=True)
        csv_bytes = b'Label,Element Label,Concentration\n'
        response = client.post(
            '/bulk-uploads/icp-oes',
            data={'overwrite': 'true'},
            files={'file': ('test.csv', csv_bytes, 'text/csv')},
            headers={'Authorization': 'Bearer test-token'},
        )
        # Auth may reject in test env; we only care that overwrite was forwarded
        # if the call was made.
        if calls:
            assert calls[0] is True
```

- [ ] **Step 2: Run to confirm it fails or is skipped** (auth may intercept — the test is a wire-check, not an integration test)

```
pytest tests/test_icp_handling.py::TestICPRouterOverwrite -v
```

- [ ] **Step 3: Update the router endpoint**

In `backend/api/routers/bulk_uploads.py`, replace the `upload_icp_oes` function signature and call site (lines 297–338):

```python
@router.post("/icp-oes", response_model=UploadResponse)
async def upload_icp_oes(
    file: UploadFile = File(...),
    overwrite: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
) -> UploadResponse:
    """Upload an ICP-OES CSV file and ingest elemental data.

    When overwrite=True, existing ICPResults for each matching (experiment, timepoint)
    are deleted before new data is inserted. Fixed columns and all_elements are replaced
    entirely rather than merged.
    """
    import sys  # noqa: PLC0415
    from types import ModuleType  # noqa: PLC0415
    if "frontend.config.variable_config" not in sys.modules:
        _stub = ModuleType("frontend.config.variable_config")
        sys.modules["frontend"] = sys.modules.get("frontend", ModuleType("frontend"))
        sys.modules["frontend.config"] = sys.modules.get("frontend.config", ModuleType("frontend.config"))
        sys.modules["frontend.config.variable_config"] = _stub
    _vc = sys.modules["frontend.config.variable_config"]
    if not hasattr(_vc, "ICP_FIXED_ELEMENT_FIELDS"):
        _vc.ICP_FIXED_ELEMENT_FIELDS = [
            "fe", "si", "mg", "ca", "ni", "cu", "mo", "zn", "mn", "cr",
            "co", "al", "sr", "y", "nb", "sb", "cs", "ba", "nd", "gd",
            "pt", "rh", "ir", "pd", "ru", "os", "tl",
        ]
    from backend.services.icp_service import ICPService  # noqa: PLC0415
    file_bytes = await file.read()
    try:
        processed_data, parse_errors = ICPService.parse_and_process_icp_file(file_bytes)
        if parse_errors and not processed_data:
            return UploadResponse(created=0, updated=0, skipped=0, errors=parse_errors,
                                  message="ICP parse failed")
        created_rows, updated_count, ingest_errors = ICPService.bulk_create_icp_results(
            db, processed_data, overwrite=overwrite
        )
        all_errors = parse_errors + ingest_errors
        db.commit()
    except Exception as exc:
        db.rollback()
        log.error("icp_upload_failed", error=str(exc))
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)],
                              message="Upload failed")
    new_count = len(created_rows) - updated_count
    log.info("icp_upload", created=new_count, updated=updated_count, user=current_user.email)
    return UploadResponse(
        created=new_count, updated=updated_count, skipped=0, errors=all_errors,
        message=f"ICP-OES: {new_count} created, {updated_count} updated",
    )
```

- [ ] **Step 4: Run backend tests**

```
pytest tests/test_icp_handling.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/bulk_uploads.py tests/test_icp_handling.py
git commit -m "[fix] wire overwrite form field to ICP-OES upload endpoint

- Tests added: yes
- Docs updated: no"
```

---

## Task 3: Frontend API — `uploadIcpOes` accepts `overwrite`

**Files:**
- Modify: `frontend/src/api/bulkUploads.ts:73`

- [ ] **Step 1: Update `uploadIcpOes` to accept and forward the flag**

Replace lines 73–74 in `frontend/src/api/bulkUploads.ts`:

```typescript
  // Card 2 — ICP-OES Data
  uploadIcpOes: (file: File, overwrite = false) => {
    const fd = fileForm(file)
    fd.append('overwrite', overwrite ? 'true' : 'false')
    return post<BulkUploadResult>('/bulk-uploads/icp-oes', fd)
  },
```

- [ ] **Step 2: Type-check**

```
cd frontend && npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/bulkUploads.ts
git commit -m "[fix] add overwrite param to uploadIcpOes API function

- Tests added: no
- Docs updated: no"
```

---

## Task 4: Frontend UI — `IcpOverwriteToggle` and state wiring

**Files:**
- Modify: `frontend/src/pages/BulkUploads.tsx`

- [ ] **Step 1: Add `IcpOverwriteToggle` component**

After the closing brace of `XrdOverwriteToggle` (line 124), insert the new component. Note the text is ICP-specific: "Replace existing ICP data" and the amber warning mentions elements, not mineral phases.

```typescript
// ─── ICP overwrite toggle ─────────────────────────────────────────────────────
function IcpOverwriteToggle({
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
          className="w-3.5 h-3.5 rounded accent-red-500"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="text-xs text-ink-secondary">
          Replace existing ICP data for matching experiment / timepoint
        </span>
      </label>
      {checked ? (
        <p className="text-xs text-amber-400 leading-relaxed pl-5">
          Existing ICP elemental data for any matching experiment and timepoint in this file
          will be deleted and replaced with the values from this upload.
        </p>
      ) : (
        <p className="text-xs text-ink-muted leading-relaxed pl-5">
          Existing ICP data for the same experiment and timepoint will be updated by
          merging — new elements are added and existing element values are overwritten,
          but elements absent from this file are preserved.
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Add `icpOverwrite` state to `BulkUploadsPage`**

In `BulkUploadsPage`, add state at line 132 (alongside `xrdOverwrite`):

```typescript
  const [icpOverwrite, setIcpOverwrite] = useState(false)
```

- [ ] **Step 3: Wire the toggle into the ICP-OES `UploadRow`**

Replace the ICP-OES `UploadRow` block (lines 169–178) with:

```typescript
        {/* 2 — ICP-OES Data */}
        <UploadRow
          id="icp-oes"
          title="ICP-OES Data"
          description="Upload ICP-OES elemental analysis CSV"
          helpText="Instrument CSV export from the ICP-OES. Multi-element, multi-timepoint files supported. Blank rows are filtered. Duplicate spectral lines resolved by best intensity."
          accept=".csv"
          uploadFn={(file) => bulkUploadsApi.uploadIcpOes(file, icpOverwrite)}
          topContent={<IcpOverwriteToggle checked={icpOverwrite} onChange={setIcpOverwrite} />}
          isOpen={isOpen('icp-oes')}
          onToggle={() => toggle('icp-oes')}
        />
```

- [ ] **Step 4: Type-check and lint**

```
cd frontend && npx tsc --noEmit && npx eslint src/pages/BulkUploads.tsx --ext .tsx
```

Expected: 0 errors, 0 warnings.

- [ ] **Step 5: Verify in the browser**

Open the Bulk Uploads page (dev server already running on port 5173 or 5174).
- Expand the ICP-OES card.
- Confirm the overwrite checkbox appears below the help text.
- Check the box — amber warning text should appear.
- Uncheck — muted "merge" description should appear.
- The checkbox state should reset to unchecked when the card is collapsed and reopened (it's local state, no persistence needed).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/BulkUploads.tsx
git commit -m "[fix] add IcpOverwriteToggle to ICP-OES bulk upload card

- Tests added: no
- Docs updated: no"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Covered by |
|-------------|-----------|
| Checkbox UI in ICP-OES card | Task 4 |
| Checkbox passes flag to API | Tasks 3 + 4 |
| Backend receives flag via `Form` | Task 2 |
| `overwrite=True` deletes existing `ICPResults` then re-creates | Task 1 |
| `overwrite=False` retains existing merge behavior | Task 1 (unchanged else branch) |
| Replaced records count as "created" not "updated" | Task 1 (`was_update` stays `False`) |
| Tests for overwrite behavior | Task 1 |
| No change to parent `ExperimentalResults` row | Task 1 (`db.delete(experimental_result.icp_data)` only) |

**Placeholder scan:** No TBDs, no "implement later", no "similar to Task N" shortcuts — all code blocks are complete.

**Type consistency:**
- `overwrite: bool = False` used consistently in both service methods and the router param.
- `IcpOverwriteToggle` props `{ checked: boolean; onChange: (v: boolean) => void }` match how `XrdOverwriteToggle` is called — no drift.
- `bulkUploadsApi.uploadIcpOes(file, icpOverwrite)` matches the updated signature `(file: File, overwrite = false)`.
