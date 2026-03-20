# Developer Guide: Adding a New Bulk Upload Type

Follow these steps to add a new upload card to the Bulk Uploads page.
Each card requires a parser service, a backend endpoint, and a frontend row component.

---

## Overview of the stack

```
Frontend UploadRow  →  API client function  →  FastAPI endpoint  →  Parser service  →  DB
                                                     ↓
                                              UploadResponse
                                         (created, updated, skipped,
                                          errors, warnings, feedbacks)
```

---

## Step 1 — Write or identify the parser service

Parser services live in `backend/services/bulk_uploads/`.

**Return signature convention — pick the matching tuple:**

| Upload type | Return tuple |
|-------------|-------------|
| Simple upsert | `(created, updated, skipped, errors)` |
| With warnings | `(created, updated, skipped, errors, warnings)` |
| With feedbacks | `(created, updated, skipped, errors, feedbacks)` |
| With all | `(created, updated, skipped, errors, warnings, feedbacks)` |
| Rock inventory | `(created, updated, images_attached, skipped, errors, warnings)` |

**Parser checklist:**
- [ ] Accept `db: Session` and `file_bytes: bytes` as first two parameters
- [ ] Return `(0, 0, 0, [error_message])` for unreadable files; never raise uncaught exceptions
- [ ] Validate required column names early and return a clear error if missing
- [ ] Skip blank/empty key-column rows (increment `skipped`, do not add to `errors`)
- [ ] Do NOT modify locked parsers in this directory without explicit instruction
- [ ] If the parser imports `frontend.config.variable_config`, it **must** be lazy-imported
  (see Step 2 below)

**Template generation (optional):**

If your upload type should have a downloadable template, add a static method:
```python
@staticmethod
def generate_template_bytes() -> bytes:
    """Return openpyxl workbook bytes for the download template."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template"
    ws.append(["column_one", "column_two", ...])
    # Optionally: add an INSTRUCTIONS sheet, highlight required headers
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

---

## Step 2 — Add the FastAPI endpoint

**File:** `backend/api/routers/bulk_uploads.py`

### 2a — Add the route

```python
@router.post("/your-upload-type", response_model=UploadResponse)
async def upload_your_type(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: FirebaseUser = Depends(verify_firebase_token),
):
    file_bytes = await file.read()
    try:
        # IMPORTANT: use a lazy import to avoid startup failures
        from backend.services.bulk_uploads.your_parser import YourService  # noqa: PLC0415

        created, updated, skipped, errors = YourService.bulk_upsert_from_excel(db, file_bytes)
        db.commit()
    except Exception as e:
        db.rollback()
        return UploadResponse(created=0, updated=0, skipped=0, errors=[str(e)])

    return UploadResponse(
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
        message=f"Processed: {created} created, {updated} updated, {skipped} skipped.",
    )
```

**Rules:**
- Always use `lazy imports` (import inside the function body) — some parsers import
  `frontend.config.variable_config` at module load time, which doesn't exist at startup
- Always wrap in `try/except`; call `db.rollback()` on exception
- Call `registry.recalculate(instance, db)` for each `ScalarResults` instance created/updated
  before `db.commit()` if your upload affects calculated fields

### 2b — Add a template route entry

If your parser has `generate_template_bytes()`, add its type key to the `TEMPLATE_MAP`
dict near the top of `bulk_uploads.py`:

```python
TEMPLATE_MAP = {
    ...
    "your-upload-type": ("YourService", "your_parser"),
}
```

The `GET /api/bulk-uploads/templates/{upload_type}` route reads this map and calls
`generate_template_bytes()` dynamically. Types not in the map return 404.

---

## Step 3 — Extend the Pydantic schema (if needed)

**File:** `backend/api/schemas/bulk_upload.py`

`UploadResponse` already has `created`, `updated`, `skipped`, `errors`, `warnings`,
`feedbacks`, and `message`. You should not need to add fields unless your upload type
returns genuinely novel data.

---

## Step 4 — Add the API client function

**File:** `frontend/src/api/bulkUploads.ts`

```typescript
export async function uploadYourType(file: File): Promise<BulkUploadResult> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await apiClient.post<BulkUploadResult>(
    "/api/bulk-uploads/your-upload-type",
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
}
```

The `BulkUploadResult` interface (same file) already contains all standard fields.
Do not add a new interface unless your endpoint returns an entirely different shape.

---

## Step 5 — Add the accordion row to the page

**File:** `frontend/src/pages/BulkUploads/index.tsx`

Add one `<BulkUploadRow>` to the ordered list:

```tsx
<BulkUploadRow
  id="your-upload-type"
  title="Your Upload Title"
  description="One-sentence description shown in the collapsed header."
  accept=".xlsx,.xls,.csv"
  uploadFn={uploadYourType}
  templateType="your-upload-type"   // omit if no template
/>
```

**Props reference:**

| Prop | Type | Required | Notes |
|------|------|----------|-------|
| `id` | `string` | ✓ | Unique; used as accordion key and aria-id |
| `title` | `string` | ✓ | Displayed in header |
| `description` | `string` | ✓ | One-liner shown when collapsed |
| `accept` | `string` | ✓ | File picker filter, e.g. `".xlsx,.csv"` |
| `uploadFn` | `(file: File) => Promise<BulkUploadResult>` | ✓ | |
| `templateType` | `string` | | If set, shows download button; calls `downloadTemplate(type)` |
| `syncFn` | `() => Promise<BulkUploadResult>` | | If set, shows "Sync" button (Master Results only) |
| `helpText` | `string` | | Override the default help paragraph |
| `children` | `ReactNode` | | Extra content in expanded area (e.g. Next-ID chips) |

---

## Step 6 — Write tests

**Service tests:** `tests/services/bulk_uploads/test_your_upload_type.py`

Minimum coverage:
- [ ] Valid file creates expected DB rows (assert created count + field values)
- [ ] Missing required column returns error, zero rows written
- [ ] Blank key-column row is skipped (not errored)
- [ ] Overwrite behaviour (if applicable)
- [ ] Invalid file bytes return a file-read error

**API tests:** add to `tests/api/test_bulk_uploads.py`

Add these parametrised entries:
1. `test_upload_endpoint_requires_auth` — add your endpoint path to the list
2. `test_upload_requires_file` — add your endpoint path
3. `test_*_returns_upload_response_shape` — one test verifying `UploadResponse` shape

Use the pattern already established in `test_bulk_uploads.py` (mock the parser via
`sys.modules` patching in `conftest.py`).

---

## Step 7 — Update documentation

- [ ] Add a section to `docs/user_guide/BULK_UPLOADS.md`
- [ ] Add the endpoint to `docs/api/API_REFERENCE.md` under Bulk Uploads
- [ ] If the parser changes the DB schema, update `docs/MODELS.md`
- [ ] Update `docs/milestones/M6_bulk_uploads.md` upload card table

---

## Common pitfalls

| Pitfall | Resolution |
|---------|-----------|
| Parser imported at module level crashes startup | Use lazy import inside the endpoint function |
| `UploadResponse` fields mismatch frontend `BulkUploadResult` | Both use `created/updated/skipped/errors`; add `message` field |
| `autoflush=True` in test session causes IntegrityError mid-test | Call `db_session.flush()` before assertions that query the DB |
| Empty string cell `""` in Excel becomes `NaN` in pandas | Use `"   "` (spaces) in test fixtures; the service strips and checks `if not value` |
| Sample/experiment ID normalisation | `rock_inventory.py` normalises IDs — test fixtures must match normalised form |
| `molecular_weight` vs `molecular_weight_g_mol` | `chemical_inventory.py` has a known attribute name mismatch — do not add `molecular_weight` column to test fixtures |
