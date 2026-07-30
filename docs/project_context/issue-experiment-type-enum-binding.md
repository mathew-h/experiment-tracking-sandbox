# bug: `experiment_type` is an unenforced free-form string — a typo silently deletes an experiment from the dashboard

> **Verified against** `OneDrive - Addis Energy/Documents/01_Software/database_sandbox/experiment_tracking_sandbox`, branch `feat/issue-85-dashboard-kpi-cards` @ `49e5f8f`. `dashboard.py` and `schemas/dashboard.py` citations are **post-#85**; every other file cited is identical on `develop`.

## Summary

`ExperimentType` exists as an enum in `database/models/enums.py` but is not bound to anything. The column is a plain `Column(String)`, all three Pydantic conditions schemas type it `Optional[str]`, and no layer validates the value.

`experiment_type` is load-bearing: it decides whether an experiment appears in the reactor grid, whether it counts toward reactor occupancy, and (after `issue-reactor-slot-identity-and-occupancy-uniqueness.md`) which physical slot it maps to. All of those comparisons are exact string equality. A value of `"Core flood"`, `"core_flood"`, or `"HPHT "` drops the experiment out of the dashboard entirely, with no error raised anywhere and nothing in the logs. It simply ceases to exist as far as the dashboard is concerned.

**This ticket cannot be scoped without first running one query against prod.** See Prerequisite below. That query decides whether this is a fifteen-minute constraint addition or a normalizing data migration, and there is no point designing the migration blind.

---

## Background

`database/models/enums.py:12-18`

```python
class ExperimentType(enum.Enum):
    """Type of experimental setup"""
    SERUM = "Serum"
    AUTOCLAVE = "Autoclave"
    HPHT = "HPHT"
    CF = "Core Flood"
    OTHER = "Other"
```

Note it is a bare `enum.Enum`, **not** a `str` mixin. That matters for §2 below.

`database/models/conditions.py:17`

```python
    experiment_type = Column(String)
```

Nullable by default, no `Enum` type, no CHECK constraint, no default.

Pydantic, all `Optional[str] = None`:

| Schema | File | Line |
|---|---|---|
| `ConditionsCreate.experiment_type` | `backend/api/schemas/conditions.py` | 14 |
| `ConditionsUpdate.experiment_type` | `backend/api/schemas/conditions.py` | 40 |
| `ConditionsResponse.experiment_type` | `backend/api/schemas/conditions.py` | 72 |
| `ExperimentListItem.experiment_type` | `backend/api/schemas/experiments.py` | 60-61 |
| `ReactorStatusResponse.experiment_type` | `backend/api/schemas/dashboard.py` | 16 |
| `ReactorCardData.experiment_type` | `backend/api/schemas/dashboard.py` | 49 |
| `GanttEntry.experiment_type` | `backend/api/schemas/dashboard.py` | 66 |

Seven sites in total.

## Where the exact string match matters

- `backend/api/routers/dashboard.py:114` — reactor cards: `.where(ExperimentalConditions.experiment_type.in_(["HPHT", "Core Flood"]))`
- `backend/api/routers/dashboard.py:330` — same filter in `GET /reactor-status`
- `backend/api/routers/dashboard.py:212` — **new in #85**: `.where(ExperimentalConditions.experiment_type == "Serum")`, the Serum Vials Started KPI
- `backend/api/routers/dashboard.py:136`, `:347` — `is_cf = exp_type == "Core Flood"`, which picks `R01` vs `CF01`
- `backend/services/notion_sync/export.py:40` — `_reactor_label_for`, same comparison
- `backend/services/notion_sync/import_.py:49,52` — `== "Core Flood"` / `!= "Core Flood"`
- `backend/api/routers/conditions.py:16` — `_REACTOR_ALLOWED_TYPES = {"HPHT", "Core Flood"}`, the 422 gate on setting `reactor_number`
- `database/reactor_slot.py` — `_SERIES_BY_TYPE` (module-level dict) and `normalize_experiment_type` / `is_occupancy_type`. **Updated 2026-07-29:** this replaces the bullet that used to point at `experiment_status.py:17-28` (`_OCCUPANCY_TYPES`, `_normalize_type`, `_is_eligible_for_occupancy`) — issue #97 deleted all three from `experiment_status.py` and centralized the type-normalization/occupancy-eligibility logic in `database/reactor_slot.py` instead. If you pick this ticket up, that module (not `experiment_status.py`) is where the case/whitespace normalization and the occupancy-type allowlist now live.

Note the inconsistency: as originally written, `experiment_status.py` was the only site that normalized case and whitespace before comparing (its now-deleted `_normalize_type` docstring explicitly anticipated `'HPHT '` and `'Core  Flood'` arriving), while every other module assumed dirty data wasn't possible. **Updated 2026-07-29:** issue #97 moved that normalization into `database/reactor_slot.py::normalize_experiment_type`, which is now the one module that tolerates dirty data — but every *other* site listed above (`dashboard.py`, `notion_sync/export.py`, `notion_sync/import_.py`, `conditions.py`) is still a bare string comparison with no normalization. The disagreement this ticket exists to fix hasn't gone away; it just moved to a different file.

Consequence of a near-miss value like `"Core flood"`:
- Excluded by the `in_([...])` filter → no reactor card, no `/reactor-status` entry
- Excluded from the frontend's slot occupancy → the slot renders as *empty*, not as *unknown*
- Excluded from #85's `_occupancy()` counts, since those derive from `reactor_cards`, which the filter already emptied. The slot bar will show the rig as free while an experiment is running in it.
- `database/reactor_slot.py::is_occupancy_type` (formerly `_is_eligible_for_occupancy`) *does* match it (it normalizes), so it participates in demotion while being invisible in the UI. That combination is the nastiest one: an experiment that can auto-complete other experiments but that nobody can see.

**#85 raised the stakes here.** The new Serum KPI at `dashboard.py:212` is a bare `== "Serum"` with no normalization, so a vial typed `"serum"` or `"Serum "` is silently absent from `serum_vials_started_7wd` and `serum_experiments_7wd`. That is a *count on a dashboard card* that reads low with no indication anything was skipped — a quieter failure than a missing reactor card, because there is no empty slot to notice. Every KPI added on top of this column inherits the same exposure, which is the argument for binding the column now rather than after the next one ships.

## Why it hasn't bitten yet

Every UI write path uses a dropdown constrained to the five canonical values, and `backend/services/bulk_uploads/new_experiments.py:594-597` writes the enum's `.value`:

```python
                        if not conditions.experiment_type or conditions.experiment_type == '':
                            parsed = parse_exp_id_validation(exp_id)
                            if parsed.experiment_type:
                                conditions.experiment_type = parsed.experiment_type.value
```

The exposure is: bulk upload paths where the column is supplied directly rather than derived, direct DB edits, the `database/data_migrations/` scripts, and anything written by the Notion sync.

## The dead defensive code this has already generated

`backend/api/routers/dashboard.py` contains this block three times — lines 130-135, 249-254, and 339-344:

```python
        exp_type = (
            row.experiment_type.value
            if hasattr(row.experiment_type, "value")
            else str(row.experiment_type)
            if row.experiment_type else None
        )
```

There is a fourth copy at `backend/services/notion_sync/export.py:39`.

All four are dead. The column is a `String`, so `.value` never exists and the `hasattr` branch is never taken. They were written because the reader genuinely could not tell whether the attribute held a string or an enum — which is the real cost of the unbound column, and the clearest argument for fixing it. Note that binding the column to a SQLAlchemy `Enum` type would make the *first* branch the live one and the rest dead; either way, all four collapse to a plain attribute read once the type is knowable.

---

## Prerequisite — run this before scoping anything

```sql
SELECT experiment_type, count(*) AS n
FROM experimental_conditions
GROUP BY 1
ORDER BY n DESC;
```

And the narrower version that decides urgency:

```sql
-- Values that would be invisible on the dashboard.
SELECT experiment_type, count(*) AS n,
       count(reactor_number) AS with_reactor_number
FROM experimental_conditions
WHERE experiment_type IS NULL
   OR experiment_type NOT IN ('Serum', 'Autoclave', 'HPHT', 'Core Flood', 'Other')
GROUP BY 1
ORDER BY n DESC;
```

**Do not write the migration before seeing these results.** Three possible outcomes, three different tickets:

- **All values canonical, no NULLs** → add the constraint, tighten the schemas, delete the dead code. Small PR, no data migration.
- **A handful of near-misses** (`'Core flood'`, trailing whitespace) → same, plus a normalizing `UPDATE` in the migration. Still small, but the mapping needs a human to confirm each one.
- **NULLs with non-null `reactor_number`, or values outside the enum entirely** → needs a team decision on what those rows *are* before anything is enforced. Possibly a sixth enum value. This is no longer a small PR.

Paste the output into this ticket before starting implementation.

---

## Proposed Changes (assuming outcome 1 or 2)

### 1. Bind the column

Prefer a `VARCHAR` + CHECK constraint over a native Postgres `ENUM` type. Native enums require `ALTER TYPE` to add a value, which is awkward and, in older Postgres, can't run inside a transaction with other DDL. The lab will plausibly add a sixth experiment type. A CHECK constraint is a one-line migration to widen.

```python
experiment_type = Column(
    String,
    nullable=False,           # see §3 — only if the audit shows no NULLs
    server_default="Other",   # decide with the team; see below
)
# plus, in __table_args__:
CheckConstraint(
    "experiment_type IN ('Serum','Autoclave','HPHT','Core Flood','Other')",
    name="ck_experimental_conditions_experiment_type",
)
```

If you'd rather use SQLAlchemy's `Enum(ExperimentType, native_enum=False, validate_strings=True)`, that generates an equivalent CHECK and gives ORM-level validation too — a reasonable alternative, and it makes `.value` the live branch in the code cited above. Either is fine; pick one and be consistent.

### 2. Tighten the Pydantic schemas

Change all seven `Optional[str]` sites listed in the Background table to `Optional[ExperimentType]`. This gives a 422 at the API boundary instead of a silent write.

**Serialization caveat — this is the trap in this ticket.** `ExperimentType` is a bare `enum.Enum`, not a `str` subclass (`enums.py:12`). Pydantic v2 serializes enum members to their `.value` in `model_dump(mode="json")` and in FastAPI responses, so JSON output should be unchanged — but the Python-side type changes, and any code doing `if conditions.experiment_type == "HPHT"` against a schema object rather than an ORM object will start silently returning `False`.

Two options: add the `str` mixin (`class ExperimentType(str, enum.Enum)`), which makes equality-against-string keep working everywhere and is the lower-risk change; or leave it a plain `Enum` and audit every comparison. **Recommend adding the `str` mixin** — it's a one-line change to `enums.py` and it makes the whole ticket much less likely to break something subtly. Check the other enums in that file for consistency while you're there.

Either way, verify against `tests/api/test_conditions.py` and `tests/api/test_dashboard.py` rather than assuming, and grep the frontend types in `frontend/src/` for any place that compares the raw string.

### 3. Decide nullability — needs a team call

Making the column `NOT NULL` is the stronger fix, but only if the audit shows zero NULLs. If there are NULLs, the options are: backfill them to `"Other"`, backfill by parsing the experiment ID prefix (the machinery already exists — `backend.services.experiment_validation.parse_experiment_id`, imported as `parse_exp_id_validation` at `new_experiments.py:22` and used at `:595`), or leave the column nullable and accept that NULL means "not recorded." My recommendation is ID-prefix backfill where it resolves unambiguously and `"Other"` for the remainder, then `NOT NULL` — but this depends entirely on the counts, so it's a decision for after the audit, not before.

### 4. Delete the dead defensive code

Four sites: `dashboard.py:130-135`, `:249-254`, `:339-344`, `export.py:39`. Collapse each to a direct read. Do this **last**, after the constraint is in place, so the diff is obviously safe.

---

## Verification

- Audit queries above return only canonical values (and, if §3 lands, no NULLs).
- New test: `POST /api/experiments/{id}/conditions` with `experiment_type: "Core flood"` → 422. Same for PATCH. Add to `tests/api/test_conditions.py`, next to the existing `reactor_number` validation suite at lines 134-216.
- New test: raw ORM write of a non-canonical value → `IntegrityError`. This is the one that proves the *database* is enforcing it, not just Pydantic.
- New test: a Serum experiment written with `experiment_type = "serum"` is rejected at the boundary, rather than silently missing from `serum_vials_started_7wd`. This is the #85-specific regression.
- New test: bulk upload with a non-canonical `Experiment Type` cell → row-level error in the preview, not a silent accept. Check how `master_bulk_upload.py` surfaces per-row errors and match that pattern.
- Existing suites that must stay green: `tests/api/test_dashboard.py` (all the label/dedup/spec tests), `tests/services/bulk_uploads/test_experiment_status.py:302` (`test_preview_serum_ongoing_with_reactor_no_demotion`), `tests/services/test_notion_sync_export.py:139` (`test_export_cf_slots_mapped_correctly`).

---

## Data Model Notes

| Field | Change |
|---|---|
| `experimental_conditions.experiment_type` | Gains a CHECK constraint restricting to the five `ExperimentType` values. Nullability decided post-audit. |
| Seven Pydantic fields | `Optional[str]` → `Optional[ExperimentType]` |
| `ExperimentType` (`enums.py:12`) | Add the `str` mixin — see §2. |

Alembic head: `daae92e908f1`.

## Sequencing

Independent of `issue-reactor-slot-identity-and-occupancy-uniqueness.md`, but **run that ticket's second audit query at the same time as this one's** — they answer overlapping questions, and the slot backfill rule depends on what non-canonical `experiment_type` values exist. If the two tickets land in either order, the later one should re-check the audit.

Landing this before `issue-reactors-table-entity.md` is worth it: a clean, constrained `experiment_type` makes the reactor-series mapping in that ticket a total function instead of one with a fallback branch.

## Labels

`bug`, `data-integrity`, `database`, `tech-debt`, `needs-prod-audit`

## Notes

The `needs-prod-audit` label is doing real work here — please don't estimate or start this ticket until the `SELECT DISTINCT` output is pasted in above. It's a one-minute query that changes the scope by an order of magnitude.
