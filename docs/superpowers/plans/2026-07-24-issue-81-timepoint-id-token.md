# Issue #81 — Replicate Timepoints (`-t<days>` ID token) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support destructively-sampled replicate timepoints as first-class experiments via a `-t<days>` ID token (e.g. `SERUM_001a-t7`): parse it, persist it as `Experiment.id_timepoint_days`, make the ID canonical for the result timepoint (auto-fill blank Time, block conflicting Time), and let the existing `v_results_scalar_rollup` aggregate `a/b/c` per day bucket with zero view changes.

**Architecture:** One new pre-strip helper `split_timepoint_token()` in the canonical parser module peels the token before BOTH pinned parsers run, so their grammar bodies stay byte-identical on every existing ID shape. The day value persists on `Experiment.id_timepoint_days` (one additive nullable column, mirroring `replicate_label`, written by `update_experiment_lineage` in the existing `before_flush` flow). Enforcement is layered: a single pure helper `apply_id_timepoint()` (fill-blank / reject-conflict, using the existing bucket tolerance) is called (1) string-level in the two live bulk parsers for good per-row errors, (2) DB-level in `ScalarResultsService.create_scalar_result_ex` (choke point for ALL bulk paths — defense in depth), and (3) in `POST /api/results` (the frontend Add Results path). The frontend mirrors the token regex in a small util for display/locking.

**Tech Stack:** Python 3 / SQLAlchemy / Alembic / FastAPI / pytest; React 18 + TypeScript / vitest. No new packages.

## Global Constraints

- **Locked decisions from issue #81 (do not relitigate):** `-t<days>` = actual days, decimals allowed, lowercase `t`, token anchored at string end (`-t(\d+(?:\.\d+)?)$`); parsed day flows to `time_post_reaction_days` and reuses `v_results_scalar_rollup` (no new view, no view change); the ID is canonical for the timepoint (auto-fills Time, blocks conflicts); one additive nullable column `id_timepoint_days` mirroring `replicate_label`; scope is parse + validate + docs (no grid-creation helper).
- **Byte-identity of the pinned parsers on existing shapes:** `parse_lineage_fields` gains only a pre-strip line; `extract_lineage_info`'s body is FROZEN (issue #70 P5) and is never edited — it is fed a pre-stripped stem by its callers. `CF-015`, `HPHT_MH_001-2`, `HPHT_MH_001_Desorption`, `SERUM_001a` must parse exactly as today with `timepoint_days = None`. No existing test assertion may change; the pinned classes in `tests/services/test_experiment_validation_replicates.py`, `tests/test_experiment_id_parser.py`, `tests/test_replicate_lineage.py`, `tests/test_lineage_migration.py` all pass unchanged.
- **Locked files, issue-authorized edits only:** `backend/services/bulk_uploads/scalar_results.py` and `master_bulk_upload.py` get the tightly-scoped additive blocks shown in Task 4 (mirroring the issue #70 P3 `combine_replicate_id` insertion pattern) and nothing else. **Zero edits** to `backend/services/bulk_uploads/new_experiments.py` and `long_format.py` (Decision Points 8 and 9). `database/data_migrations/establish_experiment_lineage_006.py` stays frozen.
- **Bucket tolerance source (open question 5 — RESOLVED):** `backend/services/result_merge_utils.py` — `TIMEPOINT_TOLERANCE_DAYS = 0.0001`, `normalize_timepoint() = round(value, 4)`. All conflict comparisons in this plan use `TIMEPOINT_TOLERANCE_DAYS` from that module; never hardcode a new tolerance.
- **Migration:** additive, single model, reversible, `down_revision = '98b849b9f08b'` (current head). Mirror `fe48608cabb7_add_replicate_label_to_experiments.py` (Pattern A: `add_column` + index / `drop_index` + `drop_column`). No view SQL changes in the migration or `database/event_listeners.py`.
- **Commit format:** `[#81] <imperative, ≤50 chars>` with `- Tests added: yes/no` / `- Docs updated: yes/no` detail lines.
- **Test command:** `.venv/Scripts/python -m pytest <path> -q` from repo root. Full-suite runs show exactly 3 pre-existing failures in `tests/test_pg_backup_restore.py` (local pg_dump toolchain gap) and 4 skips; any other failure is a defect of this branch. Frontend: `cd frontend && npx vitest run` / `npx tsc --noEmit`.
- **No writes to `docs/project_context/`** — the PostToolUse hook syncs `docs/` files automatically.
- Branch: `feat/issue-81-timepoint-id-token` (already created from `develop`).
- Never start/stop/restart the uvicorn server (backend/CLAUDE.md).

## Decision Points (resolve before executing the affected task)

The issue left 5 open questions; research resolved one and surfaced 5 more. Each row states the plan's default — **the plan as written implements the Default column**. Overriding any default requires a plan amendment before the affected task runs.

| # | Question | Default implemented by this plan | Affected task |
|---|----------|----------------------------------|---------------|
| 1 | (Issue OQ1) Bare `SERUM_001a` coexisting with `-t<days>` siblings — disallow untimed results once timed siblings exist? | **Document only, do not block** in this release. A DB-level sibling scan on every result write is real complexity for a rule the team may not want yet; the rollup pollution risk is documented in REPLICATES.md (Task 6) with a recommendation to file a follow-up issue if it bites. | Task 6 (docs) |
| 2 | (Issue OQ2) Treatment combined with timepoint (`SERUM_001a-t7_Desorption`) | **Defer.** The token is anchored at string end, so it does not fire when `_Desorption` trails; the ID parses with the token glued to the stem, `timepoint_days = None`, no crash. Pinned by an explicit test (Task 1). Real treatment+timepoint combos get their own issue. | Task 1 (pin test) |
| 3 | (Issue OQ3) Units | **Days only, decimals for sub-day** (`-t0.5`), per locked decision 1. No hours encoding. No code impact. | — |
| 4 | (Issue OQ4) Persist vs re-parse | **Persist** `id_timepoint_days` — locked by issue design decision 4. | Task 2 |
| 5 | (Issue OQ5) Bucket tolerance for the match check | **RESOLVED by research:** `TIMEPOINT_TOLERANCE_DAYS = 0.0001` / `normalize_timepoint()` in `backend/services/result_merge_utils.py`. `-t7` vs entered `7.0` can never spuriously conflict (`round(7.0, 4) == 7.0`, diff 0). | Task 3 |
| 6 | (NEW) The issue assumed the New Experiment form has a Time (days) field. **It does not** — the wizard (`Step1BasicInfo` → `Step4Review`) collects no results/timepoints at creation; results enter via the Add Results modal and bulk uploads. | "Auto-fill + lock on create" is reinterpreted as: create form **displays** the parsed day and documents the lock; the actual fill/lock lands in `AddResultsModal` (Task 5) and bulk upload (Task 4). No Time field is added to the wizard. | Task 5 |
| 7 | (NEW) Letterless timepoint vial (`SERUM_001-t7`) classification: after the pre-strip it parses as a bare stem, so `update_experiment_lineage` classifies it as a **group-parent-like row** (base = stem, `parent_experiment_fk = NULL`). | **Keep classification untouched** (minimal change; verified harmless — `update_orphaned_derivations` resolves parents by exact bare/`-0`/`-1` spelling, so a `-t` vial can never steal orphans, and the rollup groups by `base_experiment_id` either way). Pinned by a test; documented. If member-semantics (parent → group parent) are preferred, Task 2 needs an amendment. | Task 2 |
| 8 | (NEW) `new_experiments.py` (locked) calls `extract_lineage_info` directly in `find_parent_for_copy`; with a raw `-t` ID that returns the full ID as base, so bulk-created `-t` vials **do not get parent-conditions copy**. | **Zero-edit** `new_experiments.py`. Lineage + `id_timepoint_days` still persist correctly via the `before_flush` listener on insert; only the conditions-copy convenience is skipped for `-t` IDs. Documented as a known limitation (Task 6). | Task 4 (verify), Task 6 (doc) |
| 9 | (NEW) `long_format.py` (locked, legacy tier, no FastAPI endpoint — same posture as issue #70 P3, which left it untouched) | **Zero-edit.** Its upserts flow through `create_scalar_result_ex`, so the Task 3 service guard already rejects conflicting times with a per-group error; blank-Time fill is not added (Time is a required column there). | Task 3 covers it |
| 10 | (NEW) `frontend/src/components/experiments/AddResultModal.tsx` is dead code — not rendered by any page (only its own test references it). The live modal is `frontend/src/pages/ExperimentDetail/AddResultsModal.tsx`. | **Skip the dead component.** The backend guard (Task 3) covers any future caller. Noted in the issue log at completion. | Task 5 |

## Logged, not fixed (pre-existing, surfaced by research — do NOT fix in this branch)

1. `POST /api/results` never computes `time_post_reaction_bucket_days` (the frontend modal sends only `time_post_reaction_days`), so modal-created results have `NULL` buckets and are invisible to `v_results_scalar_rollup`. Pre-existing behavior; the Task 3 guard fills/validates `time_post_reaction_days` only and deliberately does not start computing buckets in this path.
2. `v_results_scalar.cumulative_ferrous_iron_yield_h2_pct` partitions per `experiment_id`; for single-timepoint `-t` vials the "cumulative" equals the single row. Correct for destructive sampling — documented in Task 6, no code change (issue's "Known implication").
3. The bare-sibling coexistence risk (Decision Point 1) — documented, not enforced.

## File Structure

- **Modify:** `database/experiment_id_parser.py` — `split_timepoint_token` + `_TIMEPOINT_TOKEN_RE`; pre-strip line in `parse_lineage_fields`; `ParsedExperimentID.timepoint_days`; `parse_experiment_id_full` wiring.
- **Modify:** `backend/services/experiment_validation.py` — `parse_experiment_id` pre-strips before the frozen `extract_lineage_info`; surfaces `timepoint_days`.
- **Modify:** `database/models/experiments.py` — `id_timepoint_days` column (locked model, issue-authorized single additive change).
- **Create:** `alembic/versions/<generated>_add_id_timepoint_days_to_experiments.py`.
- **Modify:** `database/lineage_utils.py` — `update_experiment_lineage` persists `id_timepoint_days`.
- **Modify:** `backend/services/result_merge_utils.py` — new pure helper `apply_id_timepoint`.
- **Modify:** `backend/services/scalar_results_service.py` — service-level guard in `create_scalar_result_ex`.
- **Modify:** `backend/api/routers/results.py` — guard in `create_result`.
- **Modify:** `backend/api/schemas/experiments.py` — `id_timepoint_days` on `ExperimentResponse` + `ExperimentListItem`.
- **Modify (locked, issue-authorized):** `backend/services/bulk_uploads/scalar_results.py`, `backend/services/bulk_uploads/master_bulk_upload.py` — additive timepoint blocks.
- **Create:** `frontend/src/utils/experimentId.ts` (+ test) — TS mirror of the token regex.
- **Modify:** `frontend/src/api/experiments.ts`, `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx`, `frontend/src/pages/NewExperiment/Step4Review.tsx`, `frontend/src/pages/ExperimentDetail/{index.tsx,ResultsTab.tsx,AddResultsModal.tsx}`.
- **Modify (P2):** `frontend/src/pages/BulkUploads.tsx`, `frontend/src/pages/ExperimentList.tsx`, docs (`.claude/rules/MODELS.md`, `docs/user_guide/REPLICATES.md`, `docs/api/API_REFERENCE.md`, `docs/upload_templates/scalar_results.md`, `docs/upload_templates/master_bulk_upload.md`).
- **Tests — create:** `tests/services/test_timepoint_guard.py`, `tests/services/bulk_uploads/test_scalar_results_timepoints.py`, `tests/models/test_id_timepoint_days_column.py`, `frontend/src/utils/__tests__/experimentId.test.ts`, `frontend/src/pages/ExperimentDetail/__tests__/AddResultsModal.timepoint.test.tsx`.
- **Tests — extend (new classes/cases only, no existing line changes):** `tests/test_experiment_id_parser.py`, `tests/services/test_experiment_validation_replicates.py`, `tests/test_replicate_lineage.py`, `tests/views/test_v_results_scalar_rollup.py`, `tests/services/bulk_uploads/test_master_bulk_upload.py`, `tests/api/test_results.py`, `tests/api/test_experiments.py`.
- **Zero-edit (verify only):** `backend/services/bulk_uploads/new_experiments.py`, `backend/services/bulk_uploads/long_format.py`, `backend/services/bulk_uploads/replicate_routing.py`, `database/event_listeners.py`, `database/data_migrations/establish_experiment_lineage_006.py`, `frontend/src/components/experiments/AddResultModal.tsx`.

## Acceptance-Criteria → Test Traceability

| Issue AC checkbox | Concrete test(s) |
|---|---|
| `split_timepoint_token` peels `-t<days>` (int + decimal), no token → `(id, None)` | `tests/test_experiment_id_parser.py::TestSplitTimepointToken` (Task 1) |
| `parse_lineage_fields("SERUM_001a-t7") == ("SERUM_001", None, None, "a")`; `parse_experiment_id_full` exposes `timepoint_days=7.0`, `replicate_label="a"`, `base_id="SERUM_001"` | `TestTimepointGrammar::test_lineage_fields_strip_timepoint`, `test_full_parse_timepoint` (Task 1) |
| `-t0.5` → `0.5`; `SERUM_001-t7` (no letter) → `7.0`, label `None`; `SERUM_001a-2-t0` → base `SERUM_001`, seq 2, rep a, tp 0.0 | `TestTimepointGrammar::test_decimal_days`, `test_letterless_timepoint`, `test_combined_sequential_timepoint` (Task 1) |
| Existing IDs unchanged (`CF-015`, `HPHT_MH_001-2`, `HPHT_MH_001_Desorption`, `SERUM_001a`) with `timepoint_days=None`; pinned `extract_lineage_info` divergences intact | `TestTimepointGrammar::test_existing_ids_byte_identical` + entire pre-existing suite passing unchanged (`TestLegacyLineageDivergencesPinned` untouched) + `tests/services/test_experiment_validation_replicates.py::TestTimepointOnValidationSurface` (Task 1) |
| Creating `SERUM_001a-t7` persists `base_experiment_id=SERUM_001`, `replicate_label=a`, `id_timepoint_days=7.0` | `tests/test_replicate_lineage.py::TestTimepointPersistence` (Task 2) |
| `-t<days>` auto-fills Time on create/bulk; conflicting Time blocked with clear message; blank Time filled from ID | Backend: `tests/services/test_timepoint_guard.py`, `tests/services/bulk_uploads/test_scalar_results_timepoints.py`, `test_master_bulk_upload.py` additions, `tests/api/test_results.py` additions (Tasks 3–4). Frontend: `AddResultsModal.timepoint.test.tsx` (Task 5) |
| Rollup aggregates a/b/c per day bucket (n, mean, median, stddev_samp); lone vial n=1, sd NULL | `tests/views/test_v_results_scalar_rollup.py::TestRollupTimepointVials` (Task 2) |
| Migration additive, single-model, reversible; no calc-engine/schema regression | `tests/models/test_id_timepoint_days_column.py` + alembic round-trip step (Task 2) + full-suite run |

---

### Task 1: Parser — `split_timepoint_token` + wiring both parse surfaces

**Files:**
- Modify: `database/experiment_id_parser.py` (regexes near lines 66–67; `ParsedExperimentID` lines 51–63; `parse_lineage_fields` lines 87–182; `parse_experiment_id_full` lines 258–296)
- Modify: `backend/services/experiment_validation.py` (`parse_experiment_id` lines 164–233 only; `extract_lineage_info` body untouched)
- Test: `tests/test_experiment_id_parser.py` (append new classes), `tests/services/test_experiment_validation_replicates.py` (append new class)

**Interfaces:**
- Consumes: existing `parse_lineage_fields`, `classify_base_id`, `extract_lineage_info` (frozen).
- Produces (later tasks rely on these exact names):
  - `database.experiment_id_parser.split_timepoint_token(experiment_id: str) -> Tuple[str, Optional[float]]`
  - `database.experiment_id_parser.ParsedExperimentID.timepoint_days: Optional[float] = None`
  - `parse_experiment_id_full(...)` / `backend.services.experiment_validation.parse_experiment_id(...)` both populate `timepoint_days`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_experiment_id_parser.py` (import `split_timepoint_token` in the existing import block from `database.experiment_id_parser`):

```python
class TestSplitTimepointToken:
    """Issue #81: '-t<days>' pre-strip helper."""

    def test_integer_days(self):
        assert split_timepoint_token("SERUM_001a-t7") == ("SERUM_001a", 7.0)
        assert split_timepoint_token("SERUM_001a-t0") == ("SERUM_001a", 0.0)

    def test_decimal_days(self):
        assert split_timepoint_token("SERUM_001a-t0.5") == ("SERUM_001a", 0.5)
        assert split_timepoint_token("Serum_MH_101a-t14") == ("Serum_MH_101a", 14.0)

    def test_no_token_passthrough(self):
        assert split_timepoint_token("SERUM_001a") == ("SERUM_001a", None)
        assert split_timepoint_token("CF-015") == ("CF-015", None)
        assert split_timepoint_token("HPHT_MH_001-2") == ("HPHT_MH_001-2", None)
        assert split_timepoint_token("HPHT_MH_001_Desorption") == ("HPHT_MH_001_Desorption", None)

    def test_token_not_at_end_does_not_fire(self):
        # Decision Point 2: treatment outside the token — deferred, must not crash.
        assert split_timepoint_token("SERUM_001a-t7_Desorption") == ("SERUM_001a-t7_Desorption", None)

    def test_case_sensitive_lowercase_t_only(self):
        assert split_timepoint_token("SERUM_001a-T7") == ("SERUM_001a-T7", None)

    def test_malformed_tokens_do_not_fire(self):
        assert split_timepoint_token("SERUM_001a-t") == ("SERUM_001a-t", None)
        assert split_timepoint_token("SERUM_001a-t7.") == ("SERUM_001a-t7.", None)
        assert split_timepoint_token("SERUM_001a-tx") == ("SERUM_001a-tx", None)

    def test_non_string_and_empty(self):
        assert split_timepoint_token("") == ("", None)
        assert split_timepoint_token(None) == (None, None)


class TestTimepointGrammar:
    """Issue #81: timepoint token through the canonical parse surfaces."""

    def test_lineage_fields_strip_timepoint(self):
        assert parse_lineage_fields("SERUM_001a-t7") == ("SERUM_001", None, None, "a")
        assert parse_lineage_fields("SERUM_001a-t0") == ("SERUM_001", None, None, "a")

    def test_letterless_timepoint(self):
        assert parse_lineage_fields("SERUM_001-t7") == ("SERUM_001", None, None, None)
        parsed = parse_experiment_id_full("SERUM_001-t7")
        assert parsed.timepoint_days == 7.0
        assert parsed.replicate_label is None
        assert parsed.base_id == "SERUM_001"

    def test_combined_sequential_timepoint(self):
        assert parse_lineage_fields("SERUM_001a-2-t0") == ("SERUM_001", 2, None, "a")
        parsed = parse_experiment_id_full("SERUM_001a-2-t0")
        assert parsed.timepoint_days == 0.0
        assert parsed.sequential_number == 2
        assert parsed.replicate_label == "a"

    def test_full_parse_timepoint(self):
        parsed = parse_experiment_id_full("SERUM_001a-t7")
        assert parsed.timepoint_days == 7.0
        assert parsed.replicate_label == "a"
        assert parsed.base_id == "SERUM_001"
        assert parsed.original_id == "SERUM_001a-t7"

    def test_decimal_days(self):
        assert parse_experiment_id_full("SERUM_001a-t0.5").timepoint_days == 0.5

    def test_timepoint_never_read_as_sequential(self):
        # 't7' is not all-digits, so the sequential step could never fire on it;
        # pin it anyway per the AC.
        base, seq, treat, rep = parse_lineage_fields("SERUM_001-t7")
        assert seq is None

    def test_existing_ids_byte_identical(self):
        assert parse_lineage_fields("CF-015") == ("CF-015", None, None, None)
        assert parse_lineage_fields("HPHT_MH_001-2") == ("HPHT_MH_001", 2, None, None)
        assert parse_lineage_fields("HPHT_MH_001_Desorption") == ("HPHT_MH_001", None, "Desorption", None)
        assert parse_lineage_fields("SERUM_001a") == ("SERUM_001", None, None, "a")
        for exp_id in ("CF-015", "HPHT_MH_001-2", "HPHT_MH_001_Desorption", "SERUM_001a"):
            assert parse_experiment_id_full(exp_id).timepoint_days is None

    def test_treatment_after_token_no_crash(self):
        # Deferred combo (Decision Point 2): token glued to stem, no timepoint.
        parsed = parse_experiment_id_full("SERUM_001a-t7_Desorption")
        assert parsed.timepoint_days is None
        assert parsed.treatment_variant == "Desorption"
```

Append to `tests/services/test_experiment_validation_replicates.py` (new class only; imports at top of file already pull `parse_experiment_id` — add `extract_lineage_info` if not present):

```python
class TestTimepointOnValidationSurface:
    """Issue #81: the validation surface pre-strips '-t<days>' before the
    FROZEN extract_lineage_info, so legacy lineage semantics apply to the stem."""

    def test_timepoint_surfaced(self):
        parsed = parse_experiment_id("SERUM_001a-t7")
        assert parsed.timepoint_days == 7.0
        assert parsed.replicate_label == "a"
        assert parsed.base_id == "SERUM_001"
        assert parsed.is_valid is True

    def test_decimal_timepoint_surfaced(self):
        assert parse_experiment_id("SERUM_001a-t0.5").timepoint_days == 0.5

    def test_no_token_means_none(self):
        assert parse_experiment_id("SERUM_001a").timepoint_days is None
        assert parse_experiment_id("CF-015").timepoint_days is None

    def test_legacy_divergences_apply_to_stem(self):
        # CF-015-t3: strip token -> 'CF-015' -> legacy naive rule still fires
        # exactly as pinned for the bare shape.
        parsed = parse_experiment_id("CF-015-t3")
        assert parsed.timepoint_days == 3.0
        assert parsed.base_id == "CF"
        assert parsed.sequential_number == 15

    def test_frozen_function_untouched_by_token(self):
        # extract_lineage_info itself never sees/strips tokens (frozen body).
        assert extract_lineage_info("SERUM_001a-t7") == ("SERUM_001a-t7", None, None, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_experiment_id_parser.py -q` and `.venv/Scripts/python -m pytest tests/services/test_experiment_validation_replicates.py -q`
Expected: new tests FAIL (`ImportError: cannot import name 'split_timepoint_token'` / `AttributeError: ... no attribute 'timepoint_days'`); all pre-existing tests still pass.

- [ ] **Step 3: Implement**

In `database/experiment_id_parser.py`:

(a) After `_REPLICATE_GUARD_RE` (line 67), add:

```python
_TIMEPOINT_TOKEN_RE = re.compile(r'-t(\d+(?:\.\d+)?)$')


def split_timepoint_token(experiment_id: str) -> Tuple[str, Optional[float]]:
    """
    Peel a trailing '-t<days>' timepoint token (issue #81).

    '-t<days>' encodes a destructively-sampled vial's time post-reaction in
    DAYS (decimals allowed), e.g. SERUM_001a-t7 or SERUM_001a-t0.5. Lowercase
    't' only; the token must be the final characters of the ID (a trailing
    treatment suffix suppresses it — deferred combo, issue #81 open question 2).

    Returns (stem_without_token, timepoint_days):
        'SERUM_001a-t7'   -> ('SERUM_001a', 7.0)
        'SERUM_001a-t0.5' -> ('SERUM_001a', 0.5)
        'SERUM_001a'      -> ('SERUM_001a', None)
    """
    if not experiment_id or not isinstance(experiment_id, str):
        return experiment_id, None
    match = _TIMEPOINT_TOKEN_RE.search(experiment_id)
    if not match:
        return experiment_id, None
    return experiment_id[:match.start()], float(match.group(1))
```

(b) In `ParsedExperimentID` (after `replicate_label`, line 63), add:

```python
    timepoint_days: Optional[float] = None  # from '-t<days>' token; None = not encoded in ID
```

(c) In `parse_lineage_fields`, immediately after the existing strip/empty guard (after line 139 `return None, None, None, None`), insert the pre-strip so the pinned treatment → sequential → replicate steps below run on a timepoint-free stem:

```python
    # Step 0 (issue #81): peel a trailing '-t<days>' timepoint token first.
    # The day value is not a lineage field and is discarded here; callers that
    # need it use split_timepoint_token / parse_experiment_id_full.
    experiment_id, _timepoint_days = split_timepoint_token(experiment_id)
    if not experiment_id:
        return None, None, None, None
```

No other line of `parse_lineage_fields` changes. Update its docstring Examples with two additions (`SERUM_001a-t7` → `("SERUM_001", None, None, "a")`, `SERUM_001a-2-t0` → `("SERUM_001", 2, None, "a")`) and mention Step 0 in the delimiter list.

(d) In `parse_experiment_id_full`, replace line 282:

```python
    base_id, sequential_number, treatment_variant, replicate_label = parse_lineage_fields(original_id)
```

with:

```python
    stem, timepoint_days = split_timepoint_token(original_id)
    base_id, sequential_number, treatment_variant, replicate_label = parse_lineage_fields(stem)
```

and add `timepoint_days=timepoint_days,` to the returned `ParsedExperimentID(...)` kwargs.

In `backend/services/experiment_validation.py`:

(e) Extend the canonical-module import (lines 24–29) with `split_timepoint_token`.

(f) In `parse_experiment_id`, replace line 216:

```python
    base_id, sequential_number, treatment_variant, replicate_label = extract_lineage_info(original_id)
```

with:

```python
    # Issue #81: peel the '-t<days>' timepoint token BEFORE the frozen legacy
    # extraction so extract_lineage_info's pinned algorithm never sees it.
    stem, timepoint_days = split_timepoint_token(original_id)
    base_id, sequential_number, treatment_variant, replicate_label = extract_lineage_info(stem)
```

and add `timepoint_days=timepoint_days,` to the returned `ParsedExperimentID(...)` kwargs. Do NOT touch `extract_lineage_info` (frozen body — its docstring already says so).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_experiment_id_parser.py tests/services/test_experiment_validation_replicates.py tests/test_replicate_lineage.py tests/test_lineage_migration.py -q`
Expected: ALL PASS (new + every pre-existing pin).

- [ ] **Step 5: Commit**

```bash
git add database/experiment_id_parser.py backend/services/experiment_validation.py tests/test_experiment_id_parser.py tests/services/test_experiment_validation_replicates.py
git commit -m "[#81] Add -t<days> timepoint token to ID parsers

- split_timepoint_token pre-strip; both pinned parsers byte-identical on existing shapes
- Tests added: yes
- Docs updated: no"
```

---

### Task 2: Schema — `id_timepoint_days` column, migration, lineage persistence, rollup proof

**Files:**
- Modify: `database/models/experiments.py` (after `is_outlier`, line 25 — locked model, issue-authorized single additive change)
- Create: `alembic/versions/<generated>_add_id_timepoint_days_to_experiments.py`
- Modify: `database/lineage_utils.py` (`update_experiment_lineage`, lines 209–286)
- Test: `tests/models/test_id_timepoint_days_column.py` (new), `tests/test_replicate_lineage.py` (append class), `tests/views/test_v_results_scalar_rollup.py` (append class)

**Interfaces:**
- Consumes: `split_timepoint_token` (Task 1).
- Produces: `Experiment.id_timepoint_days: Column(Float, nullable=True, index=True)` — read by Tasks 3–5.

- [ ] **Step 1: Corpus safety check (no existing ID matches the token)**

Run against the dev DB:

```bash
.venv/Scripts/python -c "from database.database import SessionLocal; from database.models import Experiment; from database.experiment_id_parser import split_timepoint_token; db=SessionLocal(); hits=[e for (e,) in db.query(Experiment.experiment_id).all() if split_timepoint_token(e)[1] is not None]; print('token-shaped existing IDs:', hits)"
```

Expected: `token-shaped existing IDs: []`. If non-empty, STOP and report — those rows would be silently reinterpreted and need a user decision (no backfill is planned because none should exist).

- [ ] **Step 2: Write the failing tests**

Create `tests/models/test_id_timepoint_days_column.py` (mirror `tests/models/test_is_outlier_column.py`'s fixture/session pattern):

```python
"""Issue #81: Experiment.id_timepoint_days column contract."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from sqlalchemy import Float
from database.models import Experiment


class TestIdTimepointDaysColumn:
    def test_column_exists_nullable_float(self):
        col = Experiment.__table__.columns['id_timepoint_days']
        assert isinstance(col.type, Float)
        assert col.nullable is True
        assert col.index is True

    def test_default_is_null(self):
        exp = Experiment(experiment_id="SERUM_900", experiment_number=90001)
        assert exp.id_timepoint_days is None
```

Append to `tests/test_replicate_lineage.py` (uses the existing `sqlite_session` fixture and `_make_exp` helper):

```python
class TestTimepointPersistence:
    """Issue #81: '-t<days>' persists as Experiment.id_timepoint_days."""

    def test_timepoint_vials_share_base_and_persist_day(self, sqlite_session):
        _make_exp(sqlite_session, "SERUM_001", 1)
        t0 = _make_exp(sqlite_session, "SERUM_001a-t0", 2)
        t7 = _make_exp(sqlite_session, "SERUM_001a-t7", 3)
        sqlite_session.flush()
        assert t0.base_experiment_id == "SERUM_001"
        assert t7.base_experiment_id == "SERUM_001"
        assert t0.replicate_label == "a"
        assert t7.replicate_label == "a"
        assert t0.id_timepoint_days == 0.0
        assert t7.id_timepoint_days == 7.0

    def test_decimal_timepoint_persists(self, sqlite_session):
        half = _make_exp(sqlite_session, "SERUM_002a-t0.5", 4)
        sqlite_session.flush()
        assert half.id_timepoint_days == 0.5

    def test_untimed_ids_stay_null(self, sqlite_session):
        plain = _make_exp(sqlite_session, "SERUM_003a", 5)
        base = _make_exp(sqlite_session, "SERUM_004", 6)
        sqlite_session.flush()
        assert plain.id_timepoint_days is None
        assert base.id_timepoint_days is None

    def test_letterless_timepoint_vial_classification_pinned(self, sqlite_session):
        # Decision Point 7: SERUM_005-t7 stays a parent-like row (base = stem,
        # parent NULL) with the day persisted. Change requires a plan amendment.
        vial = _make_exp(sqlite_session, "SERUM_005-t7", 7)
        sqlite_session.flush()
        assert vial.id_timepoint_days == 7.0
        assert vial.base_experiment_id == "SERUM_005"
        assert vial.replicate_label is None
        assert vial.parent_experiment_fk is None

    def test_timepoint_vial_links_to_group_parent(self, sqlite_session):
        parent = _make_exp(sqlite_session, "SERUM_006", 8)
        vial = _make_exp(sqlite_session, "SERUM_006a-t7", 9)
        sqlite_session.flush()
        assert vial.parent_experiment_fk == parent.id
```

Append to `tests/views/test_v_results_scalar_rollup.py` (uses existing `view_db` fixture and `_make_experiment` / `_make_result` / `_make_scalar` seeders):

```python
class TestRollupTimepointVials:
    """Issue #81: '-t<days>' vials aggregate under the shared base per day
    bucket with NO view change (reuses base + time_post_reaction_bucket_days)."""

    def test_three_vials_roll_up_at_their_day(self, view_db):
        for i, (exp_id, nh4) in enumerate([
            ("SERUM_050a-t7", 1.0), ("SERUM_050b-t7", 2.0), ("SERUM_050c-t7", 3.0),
        ]):
            exp = _make_experiment(view_db, exp_id, 5000 + i)
            result = _make_result(view_db, exp, bucket_days=7.0)
            _make_scalar(view_db, result, gross_nh4=nh4)
        view_db.commit()
        row = view_db.execute(text(
            "SELECT n_replicates, mean_gross_ammonium_mM, median_gross_ammonium_mM, "
            "sd_gross_ammonium_mM FROM v_results_scalar_rollup "
            "WHERE base_experiment_id = 'SERUM_050' "
            "AND time_post_reaction_bucket_days = 7.0"
        )).fetchone()
        assert row is not None
        assert row[0] == 3
        assert row[1] == 2.0
        assert row[2] == 2.0
        assert abs(row[3] - 1.0) < 1e-9

    def test_t0_set_forms_separate_bucket(self, view_db):
        for i, exp_id in enumerate(["SERUM_051a-t0", "SERUM_051b-t0"]):
            exp = _make_experiment(view_db, exp_id, 5100 + i)
            result = _make_result(view_db, exp, bucket_days=0.0)
            _make_scalar(view_db, result, gross_nh4=1.5)
        exp7 = _make_experiment(view_db, "SERUM_051a-t7", 5102)
        result7 = _make_result(view_db, exp7, bucket_days=7.0)
        _make_scalar(view_db, result7, gross_nh4=4.0)
        view_db.commit()
        buckets = view_db.execute(text(
            "SELECT time_post_reaction_bucket_days, n_replicates "
            "FROM v_results_scalar_rollup WHERE base_experiment_id = 'SERUM_051' "
            "ORDER BY time_post_reaction_bucket_days"
        )).fetchall()
        assert [(b[0], b[1]) for b in buckets] == [(0.0, 2), (7.0, 1)]

    def test_lone_vial_n1_sd_null(self, view_db):
        exp = _make_experiment(view_db, "SERUM_052a-t14", 5200)
        result = _make_result(view_db, exp, bucket_days=14.0)
        _make_scalar(view_db, result, gross_nh4=2.5)
        view_db.commit()
        row = view_db.execute(text(
            "SELECT n_replicates, sd_gross_ammonium_mM FROM v_results_scalar_rollup "
            "WHERE base_experiment_id = 'SERUM_052'"
        )).fetchone()
        assert row[0] == 1
        assert row[1] is None
```

(Adjust helper keyword names to the file's actual `_make_result(db, experiment, bucket_days)` / `_make_scalar(db, result, gross_nh4)` signatures — they exist at lines 67/81; use positional args if the helpers take them positionally. Add `from sqlalchemy import text` only if the file doesn't already import it.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/models/test_id_timepoint_days_column.py tests/test_replicate_lineage.py tests/views/test_v_results_scalar_rollup.py -q`
Expected: new tests FAIL (`KeyError: 'id_timepoint_days'` / attribute errors); pre-existing tests pass.

- [ ] **Step 4: Implement — model column**

In `database/models/experiments.py`, after the `is_outlier` line (25):

```python
    id_timepoint_days = Column(Float, nullable=True, index=True)  # day value parsed from '-t<days>' ID token (issue #81); NULL = timepoint not encoded in ID. Drives result-time auto-fill/validation; grouping still uses base_experiment_id + bucket
```

Add `Float` to the existing `sqlalchemy` import on line 1.

- [ ] **Step 5: Implement — lineage persistence**

In `database/lineage_utils.py`:

(a) Line 20, extend the import:

```python
from .experiment_id_parser import parse_lineage_fields, split_timepoint_token
```

(b) In `update_experiment_lineage`, directly after the `replicate_label` sync block (lines 243–245) and BEFORE the `is_parent_row` computation (so it also runs for parent-like rows such as letterless `-t` vials):

```python
    _, timepoint_days = split_timepoint_token(experiment.experiment_id)
    if experiment.id_timepoint_days != timepoint_days:
        experiment.id_timepoint_days = timepoint_days
        updated = True
```

(c) Update the function docstring's first line to mention `id_timepoint_days` alongside the other fields it sets.

- [ ] **Step 6: Create the migration**

```bash
.venv/Scripts/alembic revision -m "add id_timepoint_days to experiments"
```

Fill the generated file (keep its generated `revision` id; `down_revision` must be `'98b849b9f08b'`):

```python
"""add id_timepoint_days to experiments

Issue #81: day value parsed from the '-t<days>' experiment ID token.
Additive, single model, reversible. No view changes.
"""
from alembic import op
import sqlalchemy as sa

revision = '<generated>'
down_revision = '98b849b9f08b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('experiments', sa.Column('id_timepoint_days', sa.Float(), nullable=True))
    op.create_index(op.f('ix_experiments_id_timepoint_days'), 'experiments', ['id_timepoint_days'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_experiments_id_timepoint_days'), table_name='experiments')
    op.drop_column('experiments', 'id_timepoint_days')
```

- [ ] **Step 7: Migration round-trip**

```bash
.venv/Scripts/alembic upgrade head
.venv/Scripts/alembic downgrade -1
.venv/Scripts/alembic upgrade head
```

Expected: all three succeed cleanly (transient caught-and-logged view-recreation messages are known-benign per issue #70 P4).

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/models/ tests/test_replicate_lineage.py tests/views/test_v_results_scalar_rollup.py -q`
Expected: ALL PASS.

- [ ] **Step 9: Commit**

```bash
git add database/models/experiments.py database/lineage_utils.py alembic/versions/ tests/models/test_id_timepoint_days_column.py tests/test_replicate_lineage.py tests/views/test_v_results_scalar_rollup.py
git commit -m "[#81] Persist id_timepoint_days on Experiment

- Additive nullable Float column + reversible migration; set by update_experiment_lineage
- Rollup aggregates -t vials with zero view changes (proven by tests)
- Tests added: yes
- Docs updated: no"
```

---

### Task 3: Backend guards — `apply_id_timepoint` helper, service choke point, API endpoint, response schemas

**Files:**
- Modify: `backend/services/result_merge_utils.py` (new helper next to `normalize_timepoint`, after line 18)
- Modify: `backend/services/scalar_results_service.py` (`create_scalar_result_ex`, insert after experiment resolution ~line 94, replacing the flow into the required-time check at 96–102)
- Modify: `backend/api/routers/results.py` (`create_result`, lines 74–95)
- Modify: `backend/api/schemas/experiments.py` (`ExperimentResponse` ~line 93, `ExperimentListItem` ~line 56)
- Test: `tests/services/test_timepoint_guard.py` (new), `tests/api/test_results.py` (append), `tests/api/test_experiments.py` (append)

**Interfaces:**
- Consumes: `Experiment.id_timepoint_days` (Task 2), `TIMEPOINT_TOLERANCE_DAYS` (existing).
- Produces (Task 4 relies on these):
  - `backend.services.result_merge_utils.apply_id_timepoint(id_timepoint_days: Optional[float], time_post_reaction: Optional[float]) -> Optional[float]` — returns the effective time (fills a missing value from the ID; raises `ValueError` on conflict beyond `TIMEPOINT_TOLERANCE_DAYS`; passes through unchanged when `id_timepoint_days is None`).
  - `create_scalar_result_ex` enforces the guard for every bulk path (scalar, master, long_format) — conflicting rows raise `ValueError` into the existing per-row error surfaces.
  - `POST /api/results` returns 422 on conflict; fills `time_post_reaction_days` when omitted.
  - `ExperimentResponse.id_timepoint_days` / `ExperimentListItem.id_timepoint_days` (`Optional[float] = None`) — consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/test_timepoint_guard.py`:

```python
"""Issue #81: ID-encoded timepoint is canonical for result times.

apply_id_timepoint unit table + the create_scalar_result_ex service guard
(the choke point for scalar, master, and long-format bulk paths).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.services.result_merge_utils import apply_id_timepoint
from backend.services.scalar_results_service import ScalarResultsService


class TestApplyIdTimepoint:
    def test_no_id_timepoint_passthrough(self):
        assert apply_id_timepoint(None, 3.0) == 3.0
        assert apply_id_timepoint(None, None) is None

    def test_blank_time_filled_from_id(self):
        assert apply_id_timepoint(7.0, None) == 7.0

    def test_matching_time_accepted(self):
        assert apply_id_timepoint(7.0, 7.0) == 7.0
        assert apply_id_timepoint(7.0, 7.00005) == 7.00005  # inside 0.0001 tolerance

    def test_conflicting_time_rejected(self):
        with pytest.raises(ValueError) as exc:
            apply_id_timepoint(7.0, 3.0)
        assert "-t7" in str(exc.value)
        assert "canonical" in str(exc.value)

    def test_decimal_day_conflict(self):
        with pytest.raises(ValueError):
            apply_id_timepoint(0.5, 1.0)


class TestServiceGuard:
    """create_scalar_result_ex fills/validates against Experiment.id_timepoint_days."""

    def _seed_vial(self, db, exp_id="SERUM_060a-t7", number=6000):
        from database.models import Experiment
        exp = Experiment(experiment_id=exp_id, experiment_number=number)
        db.add(exp)
        db.flush()
        return exp

    def test_blank_time_filled_from_id_column(self, db_session):
        self._seed_vial(db_session)
        upsert = ScalarResultsService.create_scalar_result_ex(
            db_session, "SERUM_060a-t7",
            {"description": "day 7 vial", "gross_ammonium_concentration_mM": 2.0},
        )
        assert upsert.experimental_result.time_post_reaction_days == 7.0
        assert upsert.experimental_result.time_post_reaction_bucket_days == 7.0

    def test_matching_time_accepted(self, db_session):
        self._seed_vial(db_session, "SERUM_061a-t7", 6100)
        upsert = ScalarResultsService.create_scalar_result_ex(
            db_session, "SERUM_061a-t7",
            {"time_post_reaction": 7.0, "description": "ok"},
        )
        assert upsert.experimental_result.time_post_reaction_days == 7.0

    def test_conflicting_time_rejected(self, db_session):
        self._seed_vial(db_session, "SERUM_062a-t7", 6200)
        with pytest.raises(ValueError, match="canonical"):
            ScalarResultsService.create_scalar_result_ex(
                db_session, "SERUM_062a-t7",
                {"time_post_reaction": 3.0, "description": "wrong day"},
            )

    def test_untimed_experiment_unaffected(self, db_session):
        self._seed_vial(db_session, "SERUM_063a", 6300)
        upsert = ScalarResultsService.create_scalar_result_ex(
            db_session, "SERUM_063a",
            {"time_post_reaction": 3.0, "description": "free timepoint"},
        )
        assert upsert.experimental_result.time_post_reaction_days == 3.0
```

(Use the repo's existing DB-session fixture name for service tests — `tests/services/bulk_uploads/test_scalar_results_replicates.py` shows the pattern; reuse its `db_session`/equivalent fixture import or conftest wiring verbatim.)

Append to `tests/api/test_results.py` (the file uses flat test functions with `client, db_session` fixtures and inline `Experiment` seeding — see its `_seed()` helper at the top; `ResultCreate` is strict-mode Pydantic, so day values must be JSON floats like `7.0`, never `7`):

```python
# ── Issue #81: '-t<days>' ID timepoint is canonical on POST /api/results ─────


def _seed_timepoint_exp(db, experiment_id, number):
    exp = Experiment(experiment_id=experiment_id, experiment_number=number, status=ExperimentStatus.ONGOING)
    db.add(exp)
    db.commit()  # commit fires before_flush -> id_timepoint_days is populated
    db.refresh(exp)
    return exp


def test_create_result_omitted_time_filled_from_id(client, db_session):
    exp = _seed_timepoint_exp(db_session, "SERUM_070a-t7", 6070)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "auto-filled",
        "is_primary_timepoint_result": True,
    })
    assert resp.status_code == 201
    assert resp.json()["time_post_reaction_days"] == 7.0


def test_create_result_matching_time_accepted(client, db_session):
    exp = _seed_timepoint_exp(db_session, "SERUM_071a-t7", 6071)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "match",
        "time_post_reaction_days": 7.0,
        "is_primary_timepoint_result": True,
    })
    assert resp.status_code == 201


def test_create_result_conflicting_time_422(client, db_session):
    exp = _seed_timepoint_exp(db_session, "SERUM_072a-t7", 6072)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "conflict",
        "time_post_reaction_days": 3.0,
        "is_primary_timepoint_result": True,
    })
    assert resp.status_code == 422
    assert "canonical" in resp.json()["detail"]


def test_create_result_untimed_experiment_unaffected(client, db_session):
    exp = _seed_timepoint_exp(db_session, "SERUM_073a", 6073)
    resp = client.post("/api/results", json={
        "experiment_fk": exp.id,
        "description": "free",
        "time_post_reaction_days": 3.0,
        "is_primary_timepoint_result": True,
    })
    assert resp.status_code == 201
```

Append to `tests/api/test_experiments.py` (mirroring the `is_outlier` response-field tests added in #70 P4 — seed inline with the file's `Experiment` import and fixtures):

```python
def test_id_timepoint_days_in_responses(client, db_session):
    exp = Experiment(experiment_id="SERUM_074a-t7", experiment_number=6074, status=ExperimentStatus.ONGOING)
    db_session.add(exp)
    db_session.commit()  # before_flush sets id_timepoint_days = 7.0
    detail = client.get(f"/api/experiments/{exp.experiment_id}")
    assert detail.status_code == 200
    assert detail.json()["id_timepoint_days"] == 7.0
    listing = client.get("/api/experiments")
    item = next(i for i in listing.json()["items"] if i["experiment_id"] == "SERUM_074a-t7")
    assert item["id_timepoint_days"] == 7.0
```

(Adjust the two seeding snippets to the exact imports/fixtures each API test file already has — both files already import `Experiment` and `ExperimentStatus`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/services/test_timepoint_guard.py tests/api/test_results.py tests/api/test_experiments.py -q`
Expected: new tests FAIL (`ImportError: cannot import name 'apply_id_timepoint'`, missing response fields, no 422).

- [ ] **Step 3: Implement — the helper**

In `backend/services/result_merge_utils.py`, after `normalize_timepoint` (line 18):

```python
def apply_id_timepoint(id_timepoint_days, time_post_reaction):
    """
    Resolve a result's time against an ID-encoded timepoint (issue #81).

    The '-t<days>' token in an experiment ID is canonical for that vial's
    timepoint: a missing time is filled from it; a conflicting time (beyond
    the bucket tolerance) is rejected so one vial never holds result rows at
    a different day.

    Returns the effective time_post_reaction value.
    Raises ValueError when the supplied time conflicts with the ID.
    """
    if id_timepoint_days is None:
        return time_post_reaction
    if time_post_reaction is None:
        return id_timepoint_days
    if abs(float(time_post_reaction) - float(id_timepoint_days)) > TIMEPOINT_TOLERANCE_DAYS:
        raise ValueError(
            f"Time (days) {time_post_reaction} conflicts with the timepoint encoded "
            f"in the experiment ID (-t{id_timepoint_days:g} = day {id_timepoint_days:g}). "
            "The ID is canonical: leave Time blank to use the ID's day, or fix the ID."
        )
    return time_post_reaction
```

- [ ] **Step 4: Implement — service guard**

In `backend/services/scalar_results_service.py`, extend the existing `result_merge_utils` import (the file already imports `normalize_timepoint` / `ensure_primary_result_for_timepoint` around line 370 area and/or the module header — add `apply_id_timepoint` to the same import). Then in `create_scalar_result_ex`, replace lines 96–102:

```python
        # Validate time_post_reaction is provided (required for proper merge with ICP data)
        time_post_reaction = result_data.get('time_post_reaction')
        if time_post_reaction is None:
            raise ValueError(
                "time_post_reaction (Time (days)) is required for scalar results. "
                "Use 0 for pre-reaction baselines."
            )
```

with:

```python
        # Issue #81: the '-t<days>' token in the experiment ID is canonical for
        # this vial's timepoint — fill a missing time from it, reject a conflict.
        # Defense in depth: the live bulk parsers also check string-level, but
        # every upload path (scalar, master, long-format) funnels through here.
        time_post_reaction = apply_id_timepoint(
            experiment.id_timepoint_days, result_data.get('time_post_reaction'),
        )
        result_data['time_post_reaction'] = time_post_reaction
        if time_post_reaction is None:
            raise ValueError(
                "time_post_reaction (Time (days)) is required for scalar results. "
                "Use 0 for pre-reaction baselines."
            )
```

(Note `result_data['time_post_reaction']` must be written back so the later `ensure_primary_result_for_timepoint(..., time_post_reaction=result_data.get('time_post_reaction'))` call at line ~206 sees the filled value.)

- [ ] **Step 5: Implement — API guard + schemas**

In `backend/api/routers/results.py`, import the helper (top of file, with the other backend.services imports):

```python
from backend.services.result_merge_utils import apply_id_timepoint
```

In `create_result`, replace line 90 (`result = ExperimentalResults(**payload.model_dump())`):

```python
    data = payload.model_dump()
    try:
        # Issue #81: '-t<days>' in the experiment ID is canonical for the timepoint.
        data["time_post_reaction_days"] = apply_id_timepoint(
            exp.id_timepoint_days, data.get("time_post_reaction_days"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result = ExperimentalResults(**data)
```

In `backend/api/schemas/experiments.py`, add to BOTH `ExperimentListItem` (next to `replicate_label`/`is_outlier`, ~line 56) and `ExperimentResponse` (~line 93):

```python
    id_timepoint_days: Optional[float] = None
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/test_timepoint_guard.py tests/api/test_results.py tests/api/test_experiments.py tests/services/ -q`
Expected: ALL PASS (including every pre-existing service test — the replaced required-time error message is byte-identical for the `id_timepoint_days is None` path).

- [ ] **Step 7: Commit**

```bash
git add backend/services/result_merge_utils.py backend/services/scalar_results_service.py backend/api/routers/results.py backend/api/schemas/experiments.py tests/services/test_timepoint_guard.py tests/api/test_results.py tests/api/test_experiments.py
git commit -m "[#81] Enforce ID timepoint on result creation

- apply_id_timepoint helper (bucket tolerance); guards in create_scalar_result_ex + POST /api/results
- id_timepoint_days exposed on experiment responses
- Tests added: yes
- Docs updated: no"
```

---

### Task 4: Bulk-upload parser hooks (locked files — issue-authorized, tightly scoped)

**Files:**
- Modify (locked, issue-authorized): `backend/services/bulk_uploads/scalar_results.py` (import block + one additive block after the replicate-routing block, lines 176–194)
- Modify (locked, issue-authorized): `backend/services/bulk_uploads/master_bulk_upload.py` (import block + restructure of the Duration parse, lines 152–160)
- Test: `tests/services/bulk_uploads/test_scalar_results_timepoints.py` (new), `tests/services/bulk_uploads/test_master_bulk_upload.py` (append)
- Zero-edit (verify): `backend/services/bulk_uploads/new_experiments.py`, `long_format.py`, `replicate_routing.py`

**Interfaces:**
- Consumes: `split_timepoint_token` (Task 1), `apply_id_timepoint` (Task 3).
- Produces: Solution Chemistry rows with a `-t` ID get blank Time filled / conflicting Time as a per-row error (`errors` + `parse_feedbacks`, dry-run visible); Master Results rows likewise (blank `Duration (Days)` no longer skips the row when the ID carries a token).

**Why string-level hooks in addition to the Task 3 service guard:** both parsers reject/skip blank-Time rows BEFORE reaching the service (`scalar_results.py:217–233` requires Time; `master_bulk_upload.py:152–155` skips blank Duration), so fill-from-ID must happen in the row loop; doing the conflict check there too gives per-row messages in dry-run previews. The service guard stays as the backstop for every other path.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/bulk_uploads/test_scalar_results_timepoints.py`, mirroring `test_scalar_results_replicates.py`'s helpers verbatim (`_seed_experiment`, `_upload(db, headers, rows)`, `_gross_for(db, experiment_id, time_days)`; copy them into the new file and keep the same conftest `variable_config` stub reliance):

```python
"""Issue #81: '-t<days>' timepoint resolution in the Solution Chemistry upload."""
# ... copy the imports + _seed_experiment/_upload/_gross_for helpers from
# tests/services/bulk_uploads/test_scalar_results_replicates.py ...


def test_blank_time_filled_from_id(db_session):
    _seed_experiment(db_session, "SERUM_080a-t7")
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        headers=["Experiment ID", "Time (days)", "NH4+ (mM)"],
        rows=[["SERUM_080a-t7", None, 2.0]],
    )
    assert errors == []
    assert created == 1
    assert _gross_for(db_session, "SERUM_080a-t7", 7.0) == 2.0


def test_conflicting_time_errors_row(db_session):
    _seed_experiment(db_session, "SERUM_081a-t7")
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        headers=["Experiment ID", "Time (days)", "NH4+ (mM)"],
        rows=[["SERUM_081a-t7", 3.0, 2.0]],
    )
    assert created == 0
    assert len(errors) == 1
    assert "canonical" in errors[0]
    error_fb = [f for f in feedbacks if f["status"] == "error"]
    assert len(error_fb) == 1


def test_matching_time_accepted(db_session):
    _seed_experiment(db_session, "SERUM_082a-t7")
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        headers=["Experiment ID", "Time (days)", "NH4+ (mM)"],
        rows=[["SERUM_082a-t7", 7.0, 2.0]],
    )
    assert errors == []
    assert created == 1


def test_error_row_does_not_abort_batch(db_session):
    _seed_experiment(db_session, "SERUM_083a-t7")
    _seed_experiment(db_session, "SERUM_084")
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        headers=["Experiment ID", "Time (days)", "NH4+ (mM)"],
        rows=[["SERUM_083a-t7", 3.0, 2.0], ["SERUM_084", 5.0, 1.0]],
    )
    assert created == 1  # the good row lands
    assert len(errors) == 1


def test_untokened_sheet_unchanged(db_session):
    _seed_experiment(db_session, "SERUM_085")
    created, updated, skipped, errors, feedbacks = _upload(
        db_session,
        headers=["Experiment ID", "Time (days)", "NH4+ (mM)"],
        rows=[["SERUM_085", 5.0, 1.0]],
    )
    assert errors == []
    assert created == 1
```

(Adapt the exact `_upload` return unpacking and NH4 header alias to whatever `test_scalar_results_replicates.py` actually uses — copy its conventions exactly; the intent of each test is fixed.)

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py` (the file's helpers: `_seed_experiment(db, experiment_id, exp_num)` and `_master_excel(rows)` whose 15 columns are `Experiment ID, Duration (Days), Description, Sample Date, NMR Run Date, ICP Run Date, GC Run Date, NH4 (mM), H2 (ppm), Gas Volume (mL), Gas Pressure (psi), Sample pH, Sample Conductivity (mS/cm), Modification, Overwrite`):

```python
# ---------------------------------------------------------------------------
# ID-encoded timepoints (issue #81)
# ---------------------------------------------------------------------------

def test_master_blank_duration_filled_from_id(db_session: Session):
    """A -t7 ID with an empty Duration (Days) cell is no longer skipped —
    the result lands at day 7."""
    _seed_experiment(db_session, "SERUM_090a-t7", 8190)

    xlsx = _master_excel([
        ["SERUM_090a-t7", None, "vial day 7", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1
    assert skipped == 0

    result = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_090a-t7")
        .one()
    )
    assert result.time_post_reaction_days == 7.0


def test_master_conflicting_duration_errors_row(db_session: Session):
    """A -t7 ID with Duration = 3.0 is a per-row error; nothing is created."""
    _seed_experiment(db_session, "SERUM_091a-t7", 8191)

    xlsx = _master_excel([
        ["SERUM_091a-t7", 3.0, "wrong day", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 0
    assert len(errors) == 1
    assert "canonical" in errors[0]


def test_master_matching_duration_accepted(db_session: Session):
    """Duration matching the -t token uploads normally."""
    _seed_experiment(db_session, "SERUM_092a-t7", 8192)

    xlsx = _master_excel([
        ["SERUM_092a-t7", 7.0, "right day", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1


def test_master_blank_duration_without_token_still_skipped(db_session: Session):
    """Regression: untokened IDs with blank Duration keep the pre-#81 skip."""
    _seed_experiment(db_session, "SERUM_093", 8193)

    xlsx = _master_excel([
        ["SERUM_093", None, "no duration", None, None, None, None,
         2.0, None, None, None, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == []
    assert created == 0
    assert skipped == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/test_scalar_results_timepoints.py tests/services/bulk_uploads/test_master_bulk_upload.py -q`
Expected: new tests FAIL — blank-Time row errors with "'Time (days)' is required" (scalar) / row skipped (master); conflict rows currently succeed at the wrong day or die at the service guard with a batch-level error instead of a per-row one. Pre-existing tests pass.

- [ ] **Step 3: Implement — scalar_results.py (additive block only)**

Add to the import block (next to the `combine_replicate_id` import, line 13):

```python
from backend.services.bulk_uploads.replicate_routing import combine_replicate_id
from backend.services.result_merge_utils import apply_id_timepoint
from database.experiment_id_parser import split_timepoint_token
```

Insert AFTER the replicate-routing block (after line 194's `continue`) and BEFORE the `measurement_date` block (line 196):

```python
            # Issue #81: '-t<days>' in the experiment ID is canonical for the
            # timepoint — fill a blank Time (days) from it, error a conflict.
            # A non-float-coercible Time cell is left untouched so the existing
            # "'Time (days)' must be a number" row error below still fires.
            _, id_timepoint = split_timepoint_token(str(clean.get("experiment_id") or ""))
            if id_timepoint is not None:
                raw_time = clean.get("time_post_reaction")
                coercible = True
                if raw_time is not None:
                    try:
                        raw_time = float(raw_time)
                    except (TypeError, ValueError):
                        coercible = False
                if coercible:
                    try:
                        clean["time_post_reaction"] = apply_id_timepoint(id_timepoint, raw_time)
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

No other line of this locked file changes. (The block runs before the required-Time check at line 217, so a blank cell is filled before that check can reject it; a filled/matching value then passes the existing float-coercion at lines 234–250 unchanged.)

- [ ] **Step 4: Implement — master_bulk_upload.py (tightly scoped restructure of lines 152–160)**

Add imports (next to the `combine_replicate_id` import, line 19):

```python
from backend.services.result_merge_utils import apply_id_timepoint
from database.experiment_id_parser import split_timepoint_token
```

Replace lines 152–160:

```python
        duration_raw = row.get("Duration (Days)")
        if duration_raw is None or (isinstance(duration_raw, float) and pd.isna(duration_raw)):
            skipped += 1
            continue

        time_post_reaction = _parse_float(duration_raw)
        if time_post_reaction is None:
            errors.append(f"Row {row_num}: invalid Duration (Days) '{duration_raw}'")
            continue
```

with:

```python
        # Issue #81: '-t<days>' in the experiment ID is canonical for the
        # timepoint — fill a blank Duration from it, error a conflict.
        _, id_timepoint = split_timepoint_token(exp_id)

        duration_raw = row.get("Duration (Days)")
        if duration_raw is None or (isinstance(duration_raw, float) and pd.isna(duration_raw)):
            if id_timepoint is None:
                skipped += 1
                continue
            time_post_reaction = id_timepoint
        else:
            time_post_reaction = _parse_float(duration_raw)
            if time_post_reaction is None:
                errors.append(f"Row {row_num}: invalid Duration (Days) '{duration_raw}'")
                continue
            try:
                time_post_reaction = apply_id_timepoint(id_timepoint, time_post_reaction)
            except ValueError as exc:
                errors.append(f"Row {row_num} ({exp_id}): {exc}")
                continue
```

No other line of this locked file changes.

- [ ] **Step 5: Zero-edit verification**

Run: `git diff --stat backend/services/bulk_uploads/`
Expected: exactly `scalar_results.py` and `master_bulk_upload.py` changed; `new_experiments.py`, `long_format.py`, `replicate_routing.py`, `quick_upload.py` untouched. If any task step seemed to require touching them, STOP and report (Decision Points 8–9).

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/services/bulk_uploads/ -q`
Expected: ALL PASS (new + all pre-existing replicate/master tests).

- [ ] **Step 7: Commit**

```bash
git add backend/services/bulk_uploads/scalar_results.py backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_scalar_results_timepoints.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "[#81] Resolve -t timepoint in bulk uploads

- Blank Time filled from ID; conflicting Time is a per-row error (scalar + master)
- Issue-authorized additive edits to locked parsers, P3 insertion pattern
- Tests added: yes
- Docs updated: no"
```

---

### Task 5: Frontend P1 — token util, create-form display, Add Results lock

**Files:**
- Create: `frontend/src/utils/experimentId.ts`, `frontend/src/utils/__tests__/experimentId.test.ts`
- Modify: `frontend/src/api/experiments.ts` (`ExperimentListItem` ~line 20, `ExperimentDetail` ~line 43)
- Modify: `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx` (hint + parsed-day info line)
- Modify: `frontend/src/pages/NewExperiment/Step4Review.tsx` (line 40 regex)
- Modify: `frontend/src/pages/ExperimentDetail/index.tsx` (pass-through), `frontend/src/pages/ExperimentDetail/ResultsTab.tsx` (prop plumbing), `frontend/src/pages/ExperimentDetail/AddResultsModal.tsx` (lock behavior)
- Test: `frontend/src/pages/ExperimentDetail/__tests__/AddResultsModal.timepoint.test.tsx` (new)
- Zero-edit: `frontend/src/components/experiments/AddResultModal.tsx` (dead component — Decision Point 10)

**Interfaces:**
- Consumes: `id_timepoint_days` on `ExperimentResponse`/`ExperimentListItem` (Task 3).
- Produces: `splitTimepointToken(id: string): { stem: string; timepointDays: number | null }`; `AddResultsModal` prop `idTimepointDays?: number | null`.

- [ ] **Step 1: Write the failing util test**

Create `frontend/src/utils/__tests__/experimentId.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'
import { splitTimepointToken } from '../experimentId'

describe('splitTimepointToken', () => {
  it('peels integer and decimal day tokens', () => {
    expect(splitTimepointToken('SERUM_001a-t7')).toEqual({ stem: 'SERUM_001a', timepointDays: 7 })
    expect(splitTimepointToken('SERUM_001a-t0')).toEqual({ stem: 'SERUM_001a', timepointDays: 0 })
    expect(splitTimepointToken('SERUM_001a-t0.5')).toEqual({ stem: 'SERUM_001a', timepointDays: 0.5 })
  })

  it('passes through IDs without a token', () => {
    for (const id of ['SERUM_001a', 'CF-015', 'HPHT_MH_001-2', 'HPHT_MH_001_Desorption']) {
      expect(splitTimepointToken(id)).toEqual({ stem: id, timepointDays: null })
    }
  })

  it('is case-sensitive and end-anchored', () => {
    expect(splitTimepointToken('SERUM_001a-T7').timepointDays).toBeNull()
    expect(splitTimepointToken('SERUM_001a-t7_Desorption').timepointDays).toBeNull()
    expect(splitTimepointToken('SERUM_001a-t').timepointDays).toBeNull()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/utils/__tests__/experimentId.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the util**

Create `frontend/src/utils/experimentId.ts`:

```typescript
// Mirror of database/experiment_id_parser.py::split_timepoint_token (issue #81).
// '-t<days>' at the end of an experiment ID encodes the vial's time
// post-reaction in days (decimals allowed). Lowercase 't' only.
const TIMEPOINT_TOKEN_RE = /-t(\d+(?:\.\d+)?)$/

export function splitTimepointToken(experimentId: string): {
  stem: string
  timepointDays: number | null
} {
  const match = TIMEPOINT_TOKEN_RE.exec(experimentId)
  if (!match) return { stem: experimentId, timepointDays: null }
  return {
    stem: experimentId.slice(0, match.index),
    timepointDays: parseFloat(match[1]),
  }
}
```

Run the util test again: PASS.

- [ ] **Step 4: API types**

In `frontend/src/api/experiments.ts`, add to BOTH `ExperimentListItem` (next to `is_outlier`, ~line 21) and `ExperimentDetail` (~line 44):

```typescript
  id_timepoint_days: number | null
```

Run: `cd frontend && npx tsc --noEmit` — fix any fixture objects in existing tests that now miss the field by adding `id_timepoint_days: null` (additive fixture edits only, same as the `is_outlier` rollout in #70 P4).

- [ ] **Step 5: New Experiment form (display only — Decision Point 6)**

In `frontend/src/pages/NewExperiment/Step1BasicInfo.tsx`:

(a) Import the util: `import { splitTimepointToken } from '../../utils/experimentId'` (match the file's existing relative-import style).

(b) Below the `idValidation` line (~53), add:

```typescript
  const { timepointDays } = splitTimepointToken(data.experimentId.trim())
```

(c) Extend the ID field's `hint` string (lines 85–89) by appending:

```
 Encode a destructively-sampled timepoint with -t<days>: SERUM_001a-t7 = replicate a sampled at day 7 (decimals allowed, e.g. -t0.5). The day is locked to the ID for all results.
```

(d) Directly under the `<Input>` (and outside its `hint`, so it shows even while the availability check renders), add:

```tsx
      {timepointDays !== null && (
        <p className="text-xs text-ink-muted">
          Timepoint from ID: day {timepointDays}. Result times for this experiment will be locked to it.
        </p>
      )}
```

(Match the file's actual muted-text utility classes — copy whatever class string the existing hint paragraph in `Input.tsx` uses.)

In `frontend/src/pages/NewExperiment/Step4Review.tsx`, replace line 40:

```typescript
  const isLetteredId = /\d+[a-z]$/.test(step1.experimentId.trim())
```

with:

```typescript
  const { stem, timepointDays } = splitTimepointToken(step1.experimentId.trim())
  // A -t<days> vial is a single destructively-sampled timepoint — creating
  // lettered replicates of it would drop the token, so hide the control.
  const isLetteredId = /\d+[a-z]$/.test(stem) || timepointDays !== null
```

(add the util import at the top).

- [ ] **Step 6: Add Results modal lock — failing test first**

Create `frontend/src/pages/ExperimentDetail/__tests__/AddResultsModal.timepoint.test.tsx` (mirror the render/provider scaffolding of the nearest existing test in that folder, e.g. `GroupedResultsView.test.tsx` / `OutlierToggle.test.tsx` — QueryClientProvider with retry:false, `vi.mock` of the results API module):

```tsx
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
// ... QueryClientProvider wrapper + vi.mock('@/api/results') per folder convention ...
import AddResultsModal from '../AddResultsModal'

describe('AddResultsModal — ID-encoded timepoint (issue #81)', () => {
  it('defaults and locks the time field when idTimepointDays is set', () => {
    render(
      <Wrapper>
        <AddResultsModal open onClose={() => {}} experimentFk={1} experimentId="SERUM_001a-t7" idTimepointDays={7} />
      </Wrapper>,
    )
    const input = screen.getByLabelText(/time post reaction/i) as HTMLInputElement
    expect(input.value).toBe('7')
    expect(input).toBeDisabled()
    expect(screen.getByText(/locked to day 7 from the experiment id/i)).toBeInTheDocument()
  })

  it('leaves the field editable when idTimepointDays is null', () => {
    render(
      <Wrapper>
        <AddResultsModal open onClose={() => {}} experimentFk={1} experimentId="SERUM_001a" idTimepointDays={null} />
      </Wrapper>,
    )
    const input = screen.getByLabelText(/time post reaction/i) as HTMLInputElement
    expect(input.value).toBe('')
    expect(input).not.toBeDisabled()
  })
})
```

Run: `cd frontend && npx vitest run src/pages/ExperimentDetail/__tests__/AddResultsModal.timepoint.test.tsx` — FAIL (unknown prop / no default / not disabled).

- [ ] **Step 7: Implement the lock + plumbing**

In `frontend/src/pages/ExperimentDetail/AddResultsModal.tsx`:

(a) Add `idTimepointDays?: number | null` to the props interface (lines 20–25) and destructure it.

(b) Initialize the form's time field from it — where the initial `FormState` is built (line 42) and wherever the form resets on open, use:

```typescript
  time_post_reaction_days: idTimepointDays != null ? String(idTimepointDays) : '',
```

(If the initial state is a module-level constant, switch to an initializer function that takes `idTimepointDays`; keep every other field's default identical. If the modal stays mounted across opens, also sync via the existing open-reset effect or add `useEffect(..., [open, idTimepointDays])` following the file's conventions.)

(c) On the time `<input>` (lines 172–184): add `disabled={idTimepointDays != null}`; ensure the label/`id`+`htmlFor` pairing supports `getByLabelText` (add `id`/`htmlFor` if the label isn't associated yet). Below the input, when locked:

```tsx
              {idTimepointDays != null && (
                <p className="text-xs text-ink-muted">
                  Locked to day {idTimepointDays} from the experiment ID (-t{idTimepointDays}).
                </p>
              )}
```

(d) Defensive validate() addition (first line of `validate`, lines 53–66) — belt-and-braces in case state is ever mutated another way:

```typescript
  if (idTimepointDays != null && f.time_post_reaction_days.trim() !== '' &&
      Math.abs(parseFloat(f.time_post_reaction_days) - idTimepointDays) > 0.0001) {
    return `Time is locked to day ${idTimepointDays} by the experiment ID token; remove the -t token from the ID to log a different day.`
  }
```

In `frontend/src/pages/ExperimentDetail/ResultsTab.tsx`: add `idTimepointDays?: number | null` to its props, pass it through to `<AddResultsModal ... idTimepointDays={idTimepointDays} />` (line ~278).

In `frontend/src/pages/ExperimentDetail/index.tsx`: at the `ResultsTab` render site (where `experimentFk={experiment.id}` is passed, ~line 390), add `idTimepointDays={experiment.id_timepoint_days}`.

- [ ] **Step 8: Run all frontend checks**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build`
Expected: all tests pass (new + existing), tsc clean, build clean. eslint: only the 5 known pre-existing errors in untouched files.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/utils/experimentId.ts frontend/src/utils/__tests__/experimentId.test.ts frontend/src/api/experiments.ts frontend/src/pages/NewExperiment/Step1BasicInfo.tsx frontend/src/pages/NewExperiment/Step4Review.tsx frontend/src/pages/ExperimentDetail/index.tsx frontend/src/pages/ExperimentDetail/ResultsTab.tsx frontend/src/pages/ExperimentDetail/AddResultsModal.tsx frontend/src/pages/ExperimentDetail/__tests__/AddResultsModal.timepoint.test.tsx
git commit -m "[#81] Lock result time to ID timepoint in UI

- splitTimepointToken util; create-form day display; Add Results field locked
- Tests added: yes
- Docs updated: no"
```

---

### Task 6 (P2): Help text, list day chip, docs

**Files:**
- Modify: `frontend/src/pages/BulkUploads.tsx` (helpText strings: New Experiments tile ~line 262, Master Results tile ~lines 201–205, Solution Chemistry tile ~line 312)
- Modify: `frontend/src/pages/ExperimentList.tsx` (`ExperimentRow` ID cell, lines 303–309)
- Modify: `.claude/rules/MODELS.md`, `docs/user_guide/REPLICATES.md`, `docs/api/API_REFERENCE.md`, `docs/upload_templates/scalar_results.md`, `docs/upload_templates/master_bulk_upload.md`
- Test: `frontend/src/pages/__tests__/BulkUploads.test.tsx` (append 1 assertion), `frontend/src/pages/__tests__/ExperimentList.test.tsx` (append 1 test)

**Interfaces:**
- Consumes: `ExperimentListItem.id_timepoint_days` (Tasks 3/5).
- Produces: user-facing documentation; no new code surface.

- [ ] **Step 1: Bulk-upload help text**

Append to the three helpText strings (exact copy, adapted to each tile's existing sentence flow):

- New Experiments tile: `Replicate timepoints are separate vials: encode the sample day in the ID with -t<days> (SERUM_001a-t0, SERUM_001a-t7, decimals allowed like -t0.5). The day is locked to the ID for all results.`
- Master Results tile: `If the Experiment ID carries -t<days>, a blank Duration (Days) is filled from the ID; a different Duration errors the row.`
- Solution Chemistry tile: `If the Experiment ID carries -t<days>, a blank Time (days) is filled from the ID; a different Time errors the row.`

Append one assertion to the existing master-copy test in `frontend/src/pages/__tests__/BulkUploads.test.tsx` checking the New Experiments tile renders text matching `/-t<days>/`.

- [ ] **Step 2: Experiments list day chip**

In `frontend/src/pages/ExperimentList.tsx`, in `ExperimentRow`'s ID cell (next to the `↳ {exp.replicate_label}` / `groupBadge` rendering, lines 303–309), add:

```tsx
              {exp.id_timepoint_days != null && (
                <span className="ml-1 rounded bg-surface-muted px-1 text-[10px] text-ink-muted">
                  day {exp.id_timepoint_days}
                </span>
              )}
```

(Match the exact badge/chip classes already used by `groupBadge` in this file — copy its class string.) Append a test to `ExperimentList.test.tsx`: a fixture row with `id_timepoint_days: 7` renders text `day 7`; a row with `null` doesn't.

- [ ] **Step 3: Docs**

1. `.claude/rules/MODELS.md` — in the `Experiment` Lineage Tracking section, add the `id_timepoint_days` bullet:
   `- `id_timepoint_days` (Float, nullable, indexed): day value parsed from a trailing `-t<days>` ID token (e.g. `SERUM_001a-t7` → 7.0; decimals allowed). NULL = not encoded. The ID is canonical for the vial's timepoint: result creation fills a blank time from it and rejects a conflicting one (guards in `create_scalar_result_ex` and `POST /api/results`; string-level checks in the scalar/master bulk parsers). Set by `update_experiment_lineage` via `split_timepoint_token`; the token is stripped before lineage grouping, so `SERUM_001a-t7` groups under base `SERUM_001` with `replicate_label = a` and rolls up per day bucket with no view changes. A letterless `-t` vial (`SERUM_001-t7`) stays a parent-like row (base = stem, parent NULL).`
   Also note under `v_results_scalar`'s cumulative caveat: for single-timepoint `-t` vials the per-experiment cumulative equals the single row — read time courses at the base/rollup grain.
2. `docs/user_guide/REPLICATES.md` — new section "Replicate timepoints (`-t<days>`)": the grammar with examples (`-t0`, `-t7`, `-t0.5`, letterless allowed), one-vial-one-timepoint rule, auto-fill/lock behavior on the Add Results modal and both uploads, how the rollup aggregates each day bucket, the cumulative caveat, and two documented limitations: (a) untimed bare siblings are not blocked — keep result days consistent manually (Decision Point 1); (b) bulk New Experiments upload does not copy parent conditions for `-t` IDs (Decision Point 8).
3. `docs/api/API_REFERENCE.md` — `id_timepoint_days` on the experiment response/list schemas; `POST /api/results` 422 conflict behavior + auto-fill note; the two bulk-upload behaviors.
4. `docs/upload_templates/scalar_results.md` + `docs/upload_templates/master_bulk_upload.md` — the fill/conflict rule sentence per tile copy above.

(The PostToolUse hook syncs `docs/` copies to `docs/project_context/` automatically — do not write there.)

- [ ] **Step 4: Run checks**

Run: `cd frontend && npx vitest run && npx tsc --noEmit` and `.venv/Scripts/python -m pytest tests/ -q -x --ignore=tests/test_pg_backup_restore.py`
Expected: frontend green; backend full suite green (minus the 3 known pg_dump failures if not ignored, 4 skips).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/BulkUploads.tsx frontend/src/pages/ExperimentList.tsx frontend/src/pages/__tests__/BulkUploads.test.tsx frontend/src/pages/__tests__/ExperimentList.test.tsx .claude/rules/MODELS.md docs/user_guide/REPLICATES.md docs/api/API_REFERENCE.md docs/upload_templates/scalar_results.md docs/upload_templates/master_bulk_upload.md docs/project_context/
git commit -m "[#81] Document -t timepoint grammar and behaviors

- Help text on 3 upload tiles; day chip on experiments list; user + API docs
- Tests added: yes
- Docs updated: yes"
```

---

## Final verification (after Task 6)

- [ ] Full backend suite: `.venv/Scripts/python -m pytest tests/ -q` — expect only the 3 known `test_pg_backup_restore.py` failures + 4 skips.
- [ ] Frontend: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build && npx eslint src` — only the 5 known pre-existing eslint errors in untouched files.
- [ ] Alembic round-trip once more at HEAD: `.venv/Scripts/alembic downgrade -1 && .venv/Scripts/alembic upgrade head`.
- [ ] `git diff develop --stat` — confirm zero-edit files (`new_experiments.py`, `long_format.py`, `replicate_routing.py`, `event_listeners.py`, `establish_experiment_lineage_006.py`, `components/experiments/AddResultModal.tsx`) are absent from the diff.
- [ ] Append the issue-log entry to `docs/working/issue-log.md` per the established format (files changed, tests added, decisions logged, scope notes incl. Decision Points 1/2/6–10 outcomes).
