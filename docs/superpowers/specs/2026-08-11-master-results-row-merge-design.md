# Master Results: merge multiple rows per vial-day

**Date:** 2026-08-11
**Task mode:** inline
**Branch:** `feat/master-results-row-merge` off `develop`
**Status:** design approved, awaiting spec review

---

## 1. Problem

Gas and liquid/solid sampling for one vial happen on different dates. Researchers
record them as two Dashboard rows sharing an experiment ID and a timepoint —
one carrying the GC reading, the other carrying pH, conductivity and the
liquid/solid sampling date. The Phase-1 duplicate guard (issue #111, footnote ²
in `docs/LOCKED_COMPONENTS.md`) rejects both rows and writes nothing for that
vial-day.

That guard is correct about the risk it was built for — before it, the later row
upserted onto the same `ScalarResults` row and silently overwrote the earlier one.
It is wrong about the diagnosis in this case: two rows describing *different
analyses* of one vial-day are complementary, not competing.

### 1.1 Measured against the team's workbook

`docs/sample_data/Master_Results_Tracker_v3.xlsx`, Dashboard sheet, as of
2026-08-11 09:51:

| Measurement | Value |
|---|---|
| Sheet rows | 499 |
| …carrying a real experiment ID (not the stale `0.0` formula cache) | 268 |
| Distinct `(normalize_id, normalized timepoint)` keys after Phase-1 resolution | 228 |
| …keys holding more than one row | **39** |
| Largest group | 2 rows (every group is a pair) |
| Rows currently rejected by the duplicate guard | 78 |

The dominant shape, `SERUM_pH_003b-t1`:

| | row 7 | row 188 |
|---|---|---|
| DI H2 (ppm) | 87.12 | — |
| DI gas volume / pressure | 30 mL / 14.7 psi | — |
| Sample pH | — | 7.24 |
| Sample Conductivity | — | 1.541 |
| Liquid/Solid Sample Date | 2026-07-22 | 2026-08-05 |
| GC Run Date | 2026-07-22 | 2026-07-22 |
| Description | — | `Highest H2 liquid, solids` |

### 1.2 Why a naive conflict rule fails

Under a rule of *"error when two rows both hold a non-null value for one field"*,
**38 of the 39 groups error**. The fields responsible:

| Field | Groups conflicting |
|---|---|
| `Liquid/Solid Sample Date` | 36 |
| `Description` | 24 |
| `FL`/`DI H2 (ppm)` | 2 |
| `Sample pH`, `Sample Conductivity (mS/cm)` | 1 |
| gas volume | 1 |

The two dominant fields are precisely the ones that *must* differ when gas and
liquid were collected on different days. A conflict rule is therefore a **field
classification problem**, not a merge algorithm problem.

### 1.3 The sheet rename does not fix the date, and breaks something else

`Sample Date` was renamed to `Liquid/Solid Sample Date` on 2026-08-11 (the source
column on the `Sampling` sheet became `Liquid/Solid Date Sampled`). Two
consequences, both verified by running the parser:

**P0 — `measurement_date` ingestion is broken today, independent of this feature.**
`master_bulk_upload.py:595` reads `row.get("Sample Date")` and `_HEADER_ALIASES`
(`:58`) has no date entry, so after `_normalize_headers` no such column exists:

| Expression | Rows parsing to a date |
|---|---|
| `row.get("Sample Date")` | **0** |
| `row.get("Liquid/Solid Sample Date")` | 274 |

On the non-overwrite path `_parse_date` returns `None`, the None-stripping
comprehension (`:642`) drops the key, and `measurement_date` is simply never
written — silently. On an `OVERWRITE=TRUE` row it is worse: `measurement_date` is
a key in the `result_data` literal, so it is in the `sheet_fields` frozenset
(`:635`), so `create_scalar_result_ex`'s overwrite branch
(`scalar_results_service.py:150-152`) **clears the stored value**. Six rows in the
current workbook carry `OVERWRITE=TRUE`.

**The rename alone does not resolve the date conflict.** The column is still
populated on gas-only rows: row 7 above carries `Liquid/Solid Sample Date` =
2026-07-22 with no pH, no conductivity and no NH4 — that is the *gas* day sitting
in a column now labelled for liquid. Read naively, 36 of 39 groups still conflict.

### 1.4 There is no gas sampling date anywhere in the workbook

`GC Full Loop` and `GC DI` carry only `Date Run`; neither the `Sampling` nor the
`Liquid Sampling` sheet has a gas-collection column. `GC Run Date` is the
**instrument run date**, not the collection date — on the 252 rows where both are
present it differs from `Liquid/Solid Sample Date` on **102** (row 18:
liquid/solid 2026-07-24, GC run 2026-07-28). It is already ingested as
`ScalarResults.gc_run_date` and is duplicated identically on both rows of every
pair, so it never conflicts.

Decision (Mat, 2026-08-11): `gc_run_date` plus the ID's `-t` day is sufficient gas
provenance. A true gas-collection date would need a new sheet column **and** an
additive `ScalarResults` column with a schema-checklist run. **Out of scope.**

---

## 2. Decisions taken

| # | Question | Decision |
|---|---|---|
| D-a | Genuine measurement conflict | **Nothing is written for that vial-day**; one error naming every row and both values |
| D-b | Two different `Description` values | **Join distinct values with `'; '`** in sheet order; same for `Modification` |
| D-c | Rows disagree on `OVERWRITE` | **Ignore the directive unless every row is TRUE** — non-destructive merge **plus a warning**, so the ignored directive is reported, not silent |
| D-d | Group holds two spellings of one ID | **Merge**; fuzzy matching already resolves both spellings onto one stored experiment. Informational warning naming the spellings so the typo can be fixed in the sheet |
| D-e | Sampling date on a gas-only row | **Ignored** — the date column is read only from a row carrying a liquid/solid measurement (§3.2) |
| D-f | Float comparison for conflicts | **Exact equality** after the existing parse helpers; no tolerance |

D-f is safe by measurement, not by assumption: across all 39 groups there is no
numeric pair that is near-equal-but-unequal (nothing within 1% that is not
identical). A tolerance would add a second, unexercised notion of "same value"
beside `TIMEPOINT_TOLERANCE_DAYS`.

D-d supersedes the converse risk accepted in footnote ²: two genuinely distinct
experiments whose IDs differ only by case or zero padding would now merge rather
than both be rejected. `_find_experiment` (`scalar_results_service.py:352`) already
resolves both spellings to the one stored experiment through the same
`normalize_id` key, so rejection never protected against that case — it only
declined to act on it. 0 of 1009 dev-DB experiments share a normalized key.

---

## 3. Contract

### 3.1 Merge key and grouping

Unchanged from the current guard: `(normalize_id(exp_id), normalize_timepoint(t))`,
built from `_resolve_row_identity`'s output. Groups of any size N. Every group in
the current workbook is a pair; nothing in the design assumes it.

### 3.2 Field classes

Four classes, declared as module-level frozensets so that adding a Dashboard column
forces an explicit choice rather than defaulting into one.

**Measurement** — `NH4 (mM)`, `FL H2 (ppm)`, `FL Gas Volume (mL)`,
`FL Gas Pressure (psi)`, `DI H2 (ppm)`, `DI gas volume (mL)`,
`DI gas pressure (psi)`, `Sample pH`, `Sample Conductivity (mS/cm)`,
`Sampled Solution Volume (mL)`.

Merge takes the single non-null value. Two non-null values that are unequal are a
**conflict**. Comparison uses the same parse helper the field already uses, so
`_parse_measurement_float`'s "0 means blank" rule for pH and conductivity holds
inside the merge exactly as it does on a single row.

Classification is on the **raw cell**, before `_resolve_h2`. The merge produces a
merged cell view and `_resolve_h2` runs once over it, so Full-Loop-wins precedence,
the gas-geometry-follows-the-winning-block rule (issue #114) and the supersede
warning are unchanged and cannot drift. A group with FL on one row and DI on
another therefore behaves exactly like one row carrying both — FL wins, the
supersede warning fires. No such group exists in the current workbook (verified),
so this path is defined rather than exercised by real data.

**Sampling date, source-gated** — `Liquid/Solid Sample Date` → `measurement_date`.
Read only from a row carrying at least one liquid/solid measurement: `NH4 (mM)`,
`Sample pH`, `Sample Conductivity (mS/cm)`, `Sampled Solution Volume (mL)`.

- A gas-only row's date is ignored and can never conflict.
- If two gated candidates disagree, that is a conflict (measurement-class).
- If no row in the group carries a liquid/solid measurement, no `measurement_date`
  is written at all — the same principle as issue #114's "geometry requires a
  reading": a date with nothing to date is provenance for a measurement that
  isn't there.

Measured outcome over the 39 groups: 34 resolved by the gate, 3 had no date
disagreement anyway, 1 is gas-only on both rows so the date is dropped, and 1
still disagrees — rows 2/185, which errors regardless because it is also the only
group with a genuine pH/conductivity conflict. **The date rule costs zero
additional errors.**

**Provenance** — `NMR Run Date`, `ICP Run Date`, `GC Run Date`, `XRD Run Date`:
first non-null in sheet order wins; a disagreement is a warning, never an error.
None of the four disagrees in any group today. `Description`, `Modification`:
distinct non-empty values joined with `'; '` in sheet order (D-b), so
`row 7` + `row 188` yields `Highest H2 liquid, solids` and a group where both
carry text yields `Gas, liquid; Highest H2 liquid, solids`. Nothing is discarded,
so no warning is needed.

**Directive** — `OVERWRITE`: the merged write is an overwrite only when every row
in the group is TRUE (D-c). Mixed → non-destructive merge plus a warning naming
the rows. One mixed pair exists today: row 154 (`SERUM_Cation_011c-t5`, DI H2
404.19, TRUE) with row 204 (pH 9.03, conductivity 0.204, FALSE).

### 3.3 Single rows

A group of one is passed through untouched. Existing single-row behaviour —
skips, per-row errors, `_resolve_h2`, `_sheet_fields`, every warning — is
unchanged. This is a strict superset of today's behaviour for any sheet with no
duplicate keys.

### 3.4 Expected outcome on the current workbook

**35 groups merge, 4 error:**

| Rows | Experiment | Conflict |
|---|---|---|
| 2, 185 | `SERUM_pH_001a-t1` | pH 5.22 vs 7.27; conductivity 1.286 vs 1.705 |
| 14, 57 | `SERUM_pH_004-t3` | DI H2 33.89 vs 39.01 ppm |
| 264, 268 | `A1 Flow Leak Test` | two H2 readings |
| 222, 272 | `GC B 500 ppm 1 mL` | gas volume |

Plus warnings for the merge summary, the mixed-`OVERWRITE` pair at rows 154/204,
and the case-variant spellings in the `SERUM_cation_*` / `SERUM_Cation_*` groups.

---

## 4. Implementation

All parser work is in `backend/services/bulk_uploads/master_bulk_upload.py`. **No
schema change, no service change, no new dependency, no frontend change.**
`ScalarResultsService.create_scalar_result_ex` and the `_sheet_fields` contract
(issue #116) are untouched.

### 4.1 P0, standalone: restore date ingestion

Add to `_HEADER_ALIASES` (`:58`), following the file's existing convention that the
canonical name is the current v3 spelling and older spellings alias onto it:

```python
"sample date": "Liquid/Solid Sample Date",
"liquid/solid sample date": "Liquid/Solid Sample Date",
```

and change `:595` to read the canonical name. `_normalize_headers`' rule 1 already
prevents the alias from colliding if an archived workbook somehow carries both
spellings — the literal v3 column wins and the aliased one keeps its raw header,
so no duplicate-column Series can reach `_parse_date`.

This is independently correct and independently testable. It should be the first
commit, with its own regression test, so it is bisectable apart from the merge.

### 4.2 `_merge_group`

```python
def _merge_group(
    members: List[Tuple[int, str, Any]],
) -> Tuple[Optional[Dict[str, Any]], List[str], List[str]]:
    """Collapse N Dashboard rows for one vial-day into one merged cell view.

    Returns (merged_row, conflicts, notes). `merged_row` is None when
    `conflicts` is non-empty — nothing is written for a conflicted vial-day.
    """
```

`merged_row` is a plain `dict` keyed by canonical header, so Phase 2's
`row.get(...)` calls work unchanged. A dict rather than a Series is deliberate: it
cannot carry duplicate labels, so the Series-instead-of-scalar hazard
`_normalize_headers` exists to prevent (`:134-149`) cannot be reintroduced here.

`notes` carries per-group warning material (run-date disagreement, mixed
`OVERWRITE`, multiple spellings) for the caller to aggregate into file-level lines.

### 4.3 Control flow in `_process_bytes`

Phase 1 (`:504-516`) is unchanged. The duplicate-rejection block (`:547-569`)
becomes Phase 1.5:

1. Build `dup_groups` as today (`:537-540`), preserving sheet order within each
   group.
2. For each group, `_merge_group`. Size-1 groups short-circuit to the original row.
3. A conflicted group contributes one error anchored at its first row and no
   merged entry, so nothing writes for that vial-day (D-a).
4. Phase 2 (`:589`) iterates merged entries. Each carries `rows: List[int]`
   alongside the anchor row number; the loop body is otherwise untouched.

Anchoring conflict errors at the group's first row keeps the existing
`sorted(row_errors, key=...)` at `:783` producing sheet order, which is the
property footnote ² requires preserved.

### 4.4 Errors and warnings

`warnings` is the only channel the UI renders — `BulkUploadRow.tsx:204-248` draws
`errors` and `warnings` as string lists (first 5, expandable) and
`bulkUploads.ts:8-9` types `feedbacks` as opaque `Record<string, unknown>[]` that
nothing reads. Everything a researcher needs to see goes in `warnings`.

**Conflict error**, one per group:

```
Rows 2, 185 (SERUM_pH_001a-t1): conflicting values for the same vial-day (day 1)
— Sample pH: 5.22 (row 2) vs 7.27 (row 185); Sample Conductivity (mS/cm): 1.286
(row 2) vs 1.705 (row 185). Rows for one vial-day are merged, but a field cannot
hold two values. Nothing was written for this vial-day.
```

**Merge summary**, one line, always emitted when any group merged — this is what
explains why the counts no longer match the sheet row count (§4.5):

```
Merged 70 rows into 35 vial-days. Gas and liquid/solid readings for one vial are
often recorded on separate rows because they were collected on different dates;
those rows are combined field by field.
```

Row lists are named at ≤10 groups, matching the threshold convention the
supersede (`:699`), GC-date (`:733`) and Duration-disagreement (`:766`) warnings
already share.

**Run-date disagreement**, **mixed-`OVERWRITE`** (naming the rows and stating the
directive was not applied), **multiple spellings** (naming the spellings): one
file-level line each, same ≤10 convention.

### 4.5 Counts and existing warnings

A merged group is one write, so one `created` or `updated` — not N. Therefore
`created + updated + skipped` no longer equals the sheet row count, and the merge
summary warning is the explanation. `skipped` keeps its Phase-1 meaning
(blank/`0.0` IDs, `standard` rows, no-timepoint rows) and is unaffected.

`feedbacks` gains an additive `rows: [2, 185]` key beside the existing anchor
`row`. Additive only; nothing renders it.

The GC-date coverage warning (`:733`) and the Duration-vs-token warning (`:766`)
have "rows" denominators tallied in Phase 2 after a successful write. Both now
count **vial-days**, so their wording changes from "rows" to "vial-days" and their
row lists name anchor rows. The property footnote ² requires — that a rejected row
is never named in a warning claiming its reading was recorded — is preserved,
because a conflicted group never reaches Phase 2 and so enters neither numerator
nor denominator.

---

## 5. Out of scope

**A stored gas-collection date.** No such column exists in the workbook (§1.4);
adding one is a sheet change plus an additive `ScalarResults` column and a
schema-checklist run.

**Fixing the Dashboard formula.** Repointing `Liquid/Solid Sample Date` at the
`Liquid Sampling` sheet so it is blank on gas-only rows would be a cleaner source
of truth, but the parser rule in §3.2 is wanted regardless so behaviour does not
depend on sheet discipline. Worth doing separately; not required by this spec.

**The other two callers of the overwrite branch.** `scalar_results.py` and
`quick_upload.py` reach `create_scalar_result_ex`'s overwrite path declaring no
`_sheet_fields`, so they keep the whole-list clearing behaviour and the latent
issue #116 bug. Already tracked separately; untouched here.

**Merging across timepoints.** Two rows for one vial at different days remain two
vial-days. The `-t` token and Duration resolution in `_resolve_row_identity` are
unchanged.

**The 4 conflicted groups' data.** Resolving which of two H2 readings is correct is
a researcher's call. This spec makes the conflict visible and refuses to guess.

---

## 6. Tests

`tests/services/bulk_uploads/test_master_bulk_upload.py` (2056 lines).

**Rewritten, not deleted** — the duplicate-guard block holds eleven tests. Eight
assert the rejection policy and are re-pointed at the merge policy, keeping the
property each was pinning; the last three assert grouping behaviour that the merge
does not change and are confirmed unchanged rather than edited:

| Test | Becomes |
|---|---|
| `test_duplicate_vial_and_timepoint_is_an_error` | complementary rows merge; conflicting rows error |
| `test_duplicate_group_is_one_error_naming_every_row` | one **conflict** error naming every row |
| `test_duplicate_group_names_both_spellings` | spellings named in the informational warning (D-d) |
| `test_duplicate_group_error_sorts_at_its_first_row` | conflict errors still anchor at the first row |
| `test_duplicate_does_not_block_other_rows` | a conflicted vial-day does not block other vial-days |
| `test_case_variant_ids_at_one_timepoint_are_a_duplicate` | case variants **merge** onto one vial-day |
| `test_padding_variant_ids_at_one_timepoint_are_a_duplicate` | padding variants merge |
| `test_duplicate_detected_after_timepoint_token_resolution` | grouping still happens after `-t` resolution |
| `test_blank_nan_experiment_id_is_skipped_not_duplicated` | unchanged in intent |
| `test_same_vial_different_timepoints_is_fine` | unchanged |
| `test_replicate_letters_are_distinct_vials` | unchanged |

**New:**

- P0 date regression: a sheet with `Liquid/Solid Sample Date` writes
  `measurement_date`; a sheet with the legacy `Sample Date` still does; an
  `OVERWRITE=TRUE` row does not clear a stored date it supplied.
- Complementary gas + liquid pair merges into one `ScalarResults` row holding both
  the H2 reading (with its gas geometry) and pH/conductivity.
- Conflicting measurement writes nothing for that vial-day, and the pre-existing
  stored row is left untouched.
- Gas-only row's sampling date is ignored; the liquid row's date is stored.
- No liquid-bearing row in the group → `measurement_date` unset.
- Two gated dates disagreeing → conflict.
- Descriptions join with `'; '`; a blank one contributes nothing.
- Run-date disagreement warns and still writes.
- Mixed `OVERWRITE` warns and clears nothing; all-TRUE `OVERWRITE` clears a
  declared-but-blank field.
- Multiple spellings merge and warn.
- A 3-row group merges.
- A merged group counts as exactly one `created`/`updated`.
- FL-on-one-row + DI-on-another resolves to FL and fires the supersede warning.

**Must stay green:** the whole file, `tests/api/test_bulk_uploads.py`,
`tests/integration/test_master_results_sync_endpoint.py`,
`tests/test_time_field_guardrails.py`.

Per `docs/working/` precedent and the `verifying-master-results-uploads` note,
tests seed their own experiments and roll back rather than relying on dev-DB
contents; sample workbooks are gitignored and OneDrive-synced, so fixtures are
built in-memory with `from_bytes_ex`.

---

## 7. Docs and locks

`backend/services/bulk_uploads/` is **locked** (CLAUDE.md §5,
`docs/LOCKED_COMPONENTS.md:66`). Explicit sign-off given by Mat, 2026-08-11.

| File | Change |
|---|---|
| `docs/LOCKED_COMPONENTS.md` | amend footnote ² — the duplicate guard becomes a merge; add footnote ⁴ recording the merge contract, the field classes and this sign-off |
| `master_bulk_upload.py` docstring | replace "Two rows sharing an ID and timepoint are both rejected" with the merge contract; record the `Liquid/Solid Sample Date` rename |
| `MODELS.md` | `ScalarResults` "One row per vial (issue #111)" paragraph — rows per vial-day are merged, conflicts rejected; note `measurement_date` is the liquid/solid date and `gc_run_date` the GC run date |
| `docs/upload_templates/` | Master Results template doc, if it names `Sample Date` |
| `docs/working/issue-log.md` | entry at completion |

The `PostToolUse` hook syncs each written doc to `docs/project_context/`.

---

## 8. Acceptance criteria

- [ ] `row.get("Liquid/Solid Sample Date")` populates `measurement_date`; the legacy `Sample Date` spelling still parses
- [ ] An `OVERWRITE=TRUE` row no longer clears a stored `measurement_date` it supplied a value for
- [ ] A complementary gas + liquid pair writes **one** `ScalarResults` row holding the H2 reading, its gas geometry, pH and conductivity
- [ ] A gas-only row's sampling date is never stored as `measurement_date`
- [ ] A group with no liquid/solid measurement writes no `measurement_date`
- [ ] A genuine measurement conflict writes **nothing** for that vial-day and leaves any pre-existing stored row untouched
- [ ] A conflict error names every row in the group, the field, and both values, and sorts at the group's first row
- [ ] Other vial-days in the same sheet upload normally alongside a conflicted one
- [ ] Descriptions join with `'; '`; `Modification` likewise
- [ ] A run-date disagreement warns and does not reject
- [ ] Mixed `OVERWRITE` performs a non-destructive merge **and** warns; all-TRUE clears a declared-but-blank field
- [ ] A group holding two spellings of one ID merges and is named in a warning
- [ ] A merged group counts as exactly one `created` or `updated`, and the merge summary warning explains the gap against the sheet row count
- [ ] `_resolve_h2` precedence, the #114 geometry rule and the supersede warning are unchanged for single rows and applied once to a merged view
- [ ] Uploading the current `Master_Results_Tracker_v3.xlsx` merges 35 groups and errors exactly the 4 in §3.4
- [ ] Footnote ² amended and footnote ⁴ added in `docs/LOCKED_COMPONENTS.md`
- [ ] All four suites in §6 pass
