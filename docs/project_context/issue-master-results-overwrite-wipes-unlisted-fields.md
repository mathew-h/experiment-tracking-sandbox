# bug: Master Results `Overwrite=TRUE` nulls eight fields the sheet never carries

> **Status 2026-08-01 — SHIPPED on `fix/issue-116-overwrite-wipes-unlisted-fields`.**
> The reproduction test the ticket asked for was written first and confirmed all
> eight fields wiped against the real code path. Fixed by bounding the overwrite
> branch to the fields the calling source declares it has columns for. Scoped to
> Master Results by user decision; `scalar_results.py` and `quick_upload.py`
> share the bug class and are unchanged — see Follow-up below.
>
> **Scoped out of #115 by user decision, 2026-07-31.** Raised while
> investigating the Dashboard's GC Measurements KPI reading 0 (issue #115).
> Confirmed **not** the cause of that symptom (see Negative evidence below),
> so it was split into its own ticket rather than riding along on that fix.
> First flagged in `issue-results-api-missing-run-dates.md` §3, which asked
> for a reproduction test before fixing it — that test has still not been
> written. Writing it is the first task for whoever picks this up.

## Summary

A Master Results upload with `Overwrite=TRUE` nulls any `scalar_results` field
the sheet does not carry a column for, even when the intent of the upload was
to correct a single unrelated value (e.g. an ammonium concentration). Eight
fields are affected, one of which (`background_ammonium_concentration_mM`)
silently changes a previously-computed net ammonium yield when it is cleared.

The mechanism is real and present in the code today. It has not been observed
in the data: 0 wipes across 9,615 audited `scalar_results` updates from
February–May 2026. This is a **latent** bug, not an active one — it has not
fired yet, most likely because `Overwrite=TRUE` uploads are rare in practice,
not because the code guards against it.

## Mechanism

`backend/services/bulk_uploads/master_bulk_upload.py:548-549` strips every
`None`-valued key out of the row's `result_data` dict before handing it to the
service layer — this is deliberate and correct for the *non-overwrite* path,
where an absent key must mean "leave this field alone":

```python
# Remove None-valued optional fields so the service skips them
result_data = {k: v for k, v in result_data.items() if v is not None or k == "_overwrite"}
```

But `backend/services/scalar_results_service.py:129-131` iterates the full
`SCALAR_UPDATABLE_FIELDS` list on the overwrite branch, not the keys actually
present in `result_data`:

```python
            if overwrite:
                for field in SCALAR_UPDATABLE_FIELDS:
                    setattr(scalar_data, field, result_data.get(field))
```

For any field in `SCALAR_UPDATABLE_FIELDS` that the Master Results sheet has
no column for, `result_data.get(field)` returns `None` — indistinguishable
from "the sheet explicitly cleared this field" — and the existing stored
value is overwritten with `NULL`. The non-overwrite branch three lines below
(`scalar_results_service.py:132-135`) is correct: it guards with
`if field in result_data`, so an absent key really does mean "leave alone"
there.

## The eight affected fields

The Master Results sheet's columns map into `result_data` with:
`gross_ammonium_concentration_mM`, `h2_concentration`,
`h2_concentration_unit`, `gas_sampling_volume_ml`, `gas_sampling_pressure_MPa`,
`final_ph`, `final_conductivity_mS_cm`, `sampling_volume_mL`,
`measurement_date`, `nmr_run_date`, `icp_run_date`, `gc_run_date`,
`xrd_run_date` (see `master_bulk_upload.py` rows ~530–547). Every other entry
in `SCALAR_UPDATABLE_FIELDS` (`backend/services/scalar_results_service.py:14-21`)
has no sheet column and is therefore nulled on every `Overwrite=TRUE` row:

1. `background_ammonium_concentration_mM`
2. `ammonium_quant_method`
3. `final_nitrate_concentration_mM`
4. `final_alkalinity_mg_L`
5. `co2_partial_pressure_MPa`
6. `final_dissolved_oxygen_mg_L`
7. `background_experiment_id`
8. `ferrous_iron_yield`

## Why `background_ammonium_concentration_mM` is the one that actually matters

The other seven are informational fields whose loss is a data-quality problem
but not a silent calculation change. `background_ammonium_concentration_mM`
is different: it feeds net ammonium directly (`docs/CALCULATIONS.md`):

```
net_concentration_mM = max(0, gross_ammonium_concentration_mM − background_ammonium_concentration_mM)
```

`background_ammonium_concentration_mM` **defaults to 0.2 mM when not set**
(`docs/CALCULATIONS.md`, Ammonium Yield section). So an `Overwrite=TRUE` row
that clears a previously-recorded, sample-specific background value does not
merely lose a number — it silently substitutes the 0.2 mM default into every
downstream `grams_per_ton_yield` calculation for that row, with no error and
no visible sign that the substitution happened.

## Negative evidence

Query run against the local dev DB (9,615 audited `scalar_results` updates,
Feb–May 2026, 6,510 in April alone): grouping every field that went from a
non-null value to `NULL` on an `'updated'`-type `modifications_log` row shows
exactly one field affected, and it is not on this list —
`gross_ammonium_concentration_mM` ×3, and nothing else. **Zero of the eight
fields above show a single wipe in that window.** The mechanism is real in
code and has not fired in the data this environment can see.

The same production-confirmation caveat as #115 applies here: this DB's real
data ends in May 2026. `issue-115-gc-run-date-visibility.md`'s Q2 (the
`modifications_log` JSONB query) answers this for any table and field,
including these eight, and should be re-run against the live database as part
of confirming this ticket's priority — a non-empty result for any of the
eight fields listed above means this is no longer latent.

## Recommended fix (not yet implemented)

Per `issue-results-api-missing-run-dates.md` §3: make the overwrite branch
distinguish "the sheet explicitly supplied a blank value, clear it" from "the
sheet has no column for this field at all, leave it alone." The likely shape
is not stripping `None`s at `master_bulk_upload.py:548-549` and instead
threading a sentinel (or the full fixed set of sheet-supplied keys) through to
the service layer, since `Overwrite=TRUE` legitimately needs to be able to
clear a field the sheet *does* carry and leaves blank.

**Write the reproduction test first**, per the original ask in
`issue-results-api-missing-run-dates.md` §3: create a scalar row with
`background_ammonium_concentration_mM` (or another of the eight) set, run an
`Overwrite=TRUE` upload whose sheet has no column for that field, and assert
whether the value survives. That test does not exist yet in
`tests/services/bulk_uploads/test_master_bulk_upload.py` — confirming the
mechanism against the actual code path, not just by inspection, is the first
step for whoever picks this up.

Note: `issue-new-experiments-overwrite-field-updates-lost.md` is a *different*
bug despite the similar name (`db.expire_all()` discarding unflushed ORM
changes in the New Experiments uploader). It shares only the word "overwrite"
and its fix does not transfer here.

## Verification

- New test: scalar row seeded with one of the eight fields set; `Overwrite=TRUE`
  upload with no column/value for that field; assert the pre-fix behavior
  (nulled) to lock in the reproduction, then assert the post-fix behavior
  (preserved) once the fix lands.
- `ScalarUpsertResult.fields_updated` / `fields_preserved`
  (`scalar_results_service.py:137-147`) should report the eight-field case
  honestly once fixed — that change-tracking block exists precisely so an
  upload's response can be audited for exactly this kind of silent clear.
- Re-run `issue-115-gc-run-date-visibility.md`'s Q2 against production; a
  non-empty result for any of the eight fields reprioritises this ticket.

## What shipped

**The reproduction, first.** `test_overwrite_preserves_background_ammonium_the_sheet_never_carries`
and `test_overwrite_preserves_every_field_absent_from_the_sheet_schema` were
written before any fix and watched fail. The second named all eight fields in its
failure output, so the mechanism is now confirmed against the code path rather
than by inspection — closing the ask left open since
`issue-results-api-missing-run-dates.md` §3.

**The constraint the ticket did not know about.** #114 shipped
`test_overwrite_clears_stale_geometry_when_the_reading_goes_away`
(`test_master_bulk_upload.py:1161`), which *depends* on overwrite nulling fields
absent from `result_data` — that is how stale GC carryover geometry is removed
when a row's H2 reading disappears. The "only write keys present in the dict"
fix the ticket floated would have broken it and re-introduced #114's problem. So
the rule could not be presence-based; it had to distinguish *unmapped* from
*mapped-but-blank*.

**The fix.** `create_scalar_result_ex` pops an optional `_sheet_fields` from
`result_data` and, on the overwrite branch, writes only fields inside that set:

```python
for field in SCALAR_UPDATABLE_FIELDS:
    if sheet_fields is None or field in sheet_fields:
        setattr(scalar_data, field, result_data.get(field))
```

`sheet_fields is None` preserves the previous behavior exactly, so the two
callers not opted in are untouched. `master_bulk_upload.py` declares its set as
`frozenset(result_data)` taken *before* the `None`-strip — derived from the dict
literal rather than restated beside it, so a future sheet column cannot silently
land outside the declared set. The strip's guard widened from `k == "_overwrite"`
to `k.startswith("_")` so control keys survive it regardless of value.

- **Files:** `backend/services/scalar_results_service.py`,
  `backend/services/bulk_uploads/master_bulk_upload.py` (LOCKED — additive only,
  per explicit user authorization 2026-08-01, matching the #115 precedent: no
  parse or write logic touched),
  `tests/services/bulk_uploads/test_master_bulk_upload.py`,
  `.claude/rules/MODELS.md`, `docs/user_guide/BULK_UPLOADS.md`,
  `docs/upload_templates/master_bulk_upload.md`.
- **Tests:** 3 added. `tests/services/bulk_uploads/` 269 → 272, all passing.
  Full backend suite 1308 passed / 3 failed — the 3 are the documented
  `tests/test_pg_backup_restore.py` baseline, **verified identical on `develop`
  in this session** rather than assumed (the #114 entry noted that check was
  skipped last time).
- **Two stale claims fixed in `docs/upload_templates/master_bulk_upload.md`**,
  both found while editing it: it credited the flow to
  `bulk_create_scalar_results_ex` (this parser calls `create_scalar_result_ex`
  per row, inside a SAVEPOINT each), and its Output section still described the
  tuple return that #114 item 4 deleted.

## Follow-up

`scalar_results.py:304` and `quick_upload.py:304` feed the same overwrite branch
and declare no `_sheet_fields`, so an overwrite upload through either still nulls
every `SCALAR_UPDATABLE_FIELDS` entry their file has no column for. Deliberately
out of scope (user decision, 2026-08-01): their sheets have no fixed schema, so
the declared set would have to be derived per-file from the columns actually
present, across two more locked parsers. The service-side mechanism is already
general — opting them in is one added key each once that derivation is settled.

## Labels

`bug`, `data-integrity`, `bulk-upload`
