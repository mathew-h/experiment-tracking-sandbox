# Bulk experiment deletion via Excel upload (Bulk Uploads page)

**Type:** feat
**Area:** `backend/services/bulk_uploads/`, `backend/api/routers/bulk_uploads.py`, `frontend/src/pages/BulkUploads.tsx`
**Priority:** urgent (Phase 1 only) / medium (Phase 2)
**Related:** `issue-bulk-delete-selected.md` (checkbox-based bulk delete, not yet built), issue #99 (single-experiment deletion, shipped), issue #100 (preview-first upload pattern — deferred to Phase 2 here)

---

## Context

Mat needs to clean up a batch of existing bad experiment entries now. The near-term goal
is a working tool, not a polished one: upload a spreadsheet of `experiment_id`s on the
Bulk Uploads page, delete exactly those experiments, done. Restricted to
**mhearl@addisenergy.com only** — no other user should see or be able to trigger this.

This issue is split into two phases on purpose. **Phase 1 is the urgent scope. Stop and
get sign-off after Phase 1 is built and tested before starting Phase 2** — the form
hardening in Phase 2 is real but not blocking the immediate cleanup.

## Existing groundwork (reuse, don't reimplement)

- `backend/services/experiment_deletion.py::delete_experiment_cascade` already does all
  the cascading/decoupling work correctly (XRD phases, background-ammonium provenance,
  replicate parent-pointer decoupling, `elemental_analysis` purge order, reactor change
  requests, audit row with `experiment_fk=NULL`) and **commits internally** — see
  `MODELS.md`'s `Experiment` deletion section. Call it per row; do not touch its internals.
- `backend/services/bulk_uploads/experiment_status.py` is the template for "spreadsheet of
  experiment IDs, resolve each, report what wasn't found" — reuse its `missing_ids`
  pattern rather than inventing a new one.
- `backend/auth/firebase_auth.py::verify_firebase_token` returns a `FirebaseUser` with
  `.email` already verified — the single-user gate is a one-line check on that.

---

## Phase 1 — Urgent: working deletion tool, mhearl@addisenergy.com only

**Ship this, test it, stop.**

### Backend

1. New endpoint `POST /api/bulk-uploads/experiment-deletion` in
   `backend/api/routers/bulk_uploads.py`. Accepts an Excel/CSV file with a single
   `experiment_id` column.
2. **Access check, first line of the handler:**
   `if current_user.email != "mhearl@addisenergy.com": raise HTTPException(403)`.
   Hardcoded is fine for Phase 1 — this is not the place to build a general role system
   under time pressure.
3. New service function, e.g.
   `backend/services/bulk_uploads/experiment_deletion_bulk.py::delete_experiments_from_file`:
   - Parse the `experiment_id` column (dedupe, ignore blank rows).
   - Resolve each ID to an `Experiment` row. Not-found IDs go into a `missing` list —
     do not fail the whole request over one typo.
   - For each resolved row, call `delete_experiment_cascade` inside a
     `try/except`. One failure must not stop the rest of the batch — collect
     `(experiment_id, error)` into a `failed` list and continue.
   - Return `{deleted: [ids], missing: [ids], failed: [{id, error}]}`.
4. No preview endpoint, no `dry_run`, no `plan_hash` gating in Phase 1 — that's Phase 2.
   `delete_experiment_cascade` commits per row already, which is the right behavior here:
   partial success on a bad batch beats an all-or-nothing rollback.
5. No batch size cap in Phase 1 (single trusted user, known cleanup list). Add in Phase 2
   if needed.

### Frontend

6. One new row on `BulkUploads.tsx`, using the existing plain `UploadRow` component (same
   as most other upload types) — not a custom preview component. Visible/usable
   regardless of who's logged in on the client; the backend 403 is the actual gate, so
   there's no need to build conditional UI rendering for one user in Phase 1.
7. Before calling the upload, a plain `window.confirm("Delete N experiments? This cannot be undone.")`
   using the row count parsed client-side from the file, or just from the filename/row
   count — whatever is fastest to wire up. This is a guardrail against a wrong file, not a
   UX feature.
8. On response, show the three lists (deleted / missing / failed) as plain text or a
   simple list — no need for the `DeleteExperimentModal`-style itemized impact breakdown
   yet.
9. Template download for this upload type: single-column `experiment_id` sheet, using the
   existing `_get_template_bytes` registry — this is a two-minute addition and worth
   including now since Mat will need to build the input file.

### Testing (required before calling Phase 1 done)

- [ ] A user other than `mhearl@addisenergy.com` gets a 403, no deletion occurs
- [ ] Uploading a file with valid IDs deletes exactly those experiments
- [ ] An ID not in the database comes back in `missing`, and the rest of the batch still
      deletes
- [ ] A row that fails to delete (e.g. locked/constraint issue) comes back in `failed` with
      a reason, and does not prevent the rest of the batch from deleting
- [ ] Each deletion produces the `ModificationsLog` audit row (already handled by
      `delete_experiment_cascade` — verify it fires, not that you built it)
- [ ] Template download produces a usable single-column `experiment_id` sheet
- [ ] Confirmed against a real cleanup batch (Mat's actual list of bad entries) end to end

**Stop here. Report back before starting Phase 2.**

---

## Phase 2 — Follow-up: harden the form (not urgent)

Once Phase 1 has been used for the actual cleanup, revisit with these improvements:

1. **Preview-first flow**, matching the issue #100 convention used elsewhere in Bulk
   Uploads: a `dry_run`/plan step that resolves IDs and shows an aggregate
   `collect_delete_impact` before anything is deleted, with a `plan_hash` gate on commit
   so the applied set can't silently drift from what was reviewed.
2. **Itemized impact display**, reusing `DeleteExperimentModal.tsx`'s `IMPACT_ROWS` shape
   summed across the batch, plus decoupling warnings (background-ammonium references,
   replicate siblings) for experiments outside the uploaded set.
3. **Typed confirmation** (the count, not each ID) replacing the `window.confirm` from
   Phase 1, consistent with what `issue-bulk-delete-selected.md` proposes for its checkbox
   flow.
4. **Batch size cap** to bound the blast radius of a bad file.
5. **Batch correlation ID** across the `ModificationsLog` rows from one upload, so a batch
   can be reconstructed from the audit trail.
6. **Cache eviction** for every deleted ID, including base-ID-keyed group queries (depends
   on `issue-replicate-group-detail-cache-eviction.md` landing first).
7. **Generalize the access check** past the hardcoded single email if this needs to be
   usable by more than one person later — a real role/claim check rather than a literal
   string comparison.
8. **Reconcile with `issue-bulk-delete-selected.md`**: both features end up needing
   "resolve N IDs → aggregate impact → per-ID delete outcome." Decide whether to converge
   on one shared backend endpoint once both exist, rather than maintaining two deletion
   code paths (the same divergence that caused the psql script vs. `experiment_deletion.py`
   mismatch before issue #99).

## Notes

`delete_experiment_cascade` is a hard, cascading, irreversible delete regardless of which
phase triggers it — the audit snapshot is a record of what was deleted, not a restore
point (see `MODELS.md`). Phase 1 deliberately trades review/confirmation depth for speed
because the access is restricted to one trusted user cleaning up a known list; that
trade-off stops being acceptable the moment this is exposed more broadly, which is the
whole point of Phase 2.
