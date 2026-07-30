# Issue #111 — Master Results GC Ingestion, v3 One-Row-Per-Vial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Master Results upload ingest the restructured v3 Dashboard — reading GC Full Loop hydrogen, falling back to a single GC DI column, rejecting rows that pack more than one vial's data into one row, and warning instead of silently dropping any H2 column it cannot map.

**Architecture:** Parser-only change confined to `backend/services/bulk_uploads/master_bulk_upload.py` plus two lines in the router. A header-alias table maps v3, v2 and pre-rename spellings onto one canonical set of names. `_resolve_h2()` applies Full Loop > DI precedence, pairing the winning concentration with gas volume and pressure from the same block. Row identity resolution is lifted into `_resolve_row_identity()` so a pre-pass can detect two rows claiming the same vial and timepoint before anything is written. A `MasterUploadResult` dataclass carries warnings; the legacy 5-tuple `from_bytes()` survives as a thin wrapper.

**No new statistics code.** Cross-replicate mean and standard deviation already exist and are unchanged by this work — see "Mean/SD already exists" below.

**Tech Stack:** Python 3.11, pandas, SQLAlchemy 2.x, FastAPI, PostgreSQL, pytest.

## Global Constraints

- **`backend/services/bulk_uploads/` is a LOCKED component** (`.claude/CLAUDE.md` §5, `docs/LOCKED_COMPONENTS.md`). This plan modifies `master_bulk_upload.py` under the explicit sign-off recorded in issue #111 and the user's 2026-07-30 answers. Do not modify any other file in that directory.
- **No schema change.** `database/models/` is not touched. DI is resolved at parse time; only the winning value reaches `ScalarResults`.
- **`0` is a real measurement, not a blank.** The user is rewriting the Excel formulas so an absent peak area leaves the ppm cell empty. Never coerce `0` to `None` for any H2 or gas column. Do not use `_parse_measurement_float` (the pH/conductivity zero-suppressing helper) on GC values.
- **v3 is the reference format**, but older headers must keep parsing. ~20 existing tests in `tests/services/bulk_uploads/test_master_bulk_upload.py` use pre-rename headers and must pass **unmodified**.
- **Two existing API tests DO have to change, and they fail loudly if you forget.** `tests/api/test_bulk_uploads.py:324` and `:339` replace the whole parser module with a `MagicMock` and stub `mock_svc.from_bytes.return_value = (3, 1, 0, [], [])`. Once the router calls `from_bytes_ex`, the mock returns a bare `MagicMock`, so `outcome.created` is not an `int` and `UploadResponse` validation blows up. Task 3 Step 9 updates both. Do not "fix" this by leaving the router on `from_bytes`.
- **Do not change the sync path.** `backend/config/settings.py` and `sync_from_path()` stay as they are. Uploads happen by drag-and-drop.
- **Per-row SAVEPOINT isolation is load-bearing.** The existing `db.begin_nested()` per row must be preserved exactly. It exists so **a failed row does not poison the session** — without it, one row raising leaves the transaction in a state where every subsequent row fails with `PendingRollbackError`, aborting the rest of the batch. Same rationale as the savepoint at `backend/services/scalar_results_service.py:286-287`.
- **Correction, established during execution (2026-07-30).** `create_scalar_result_ex` **flushes; it does not commit** (`scalar_results_service.py:209`). The upload commits exactly once, at the endpoint, via `_finalize_write` (`backend/api/routers/bulk_uploads.py:28-37`) — which is also how `dry_run` works: run the full parse, then roll back. An earlier draft of this plan asserted the service commits per row. That is true of `delete_experiment_cascade` on the bulk-deletion path (issue #109), **not** of the scalar path. Wherever that claim appears — plan prose or code comment — it is wrong and must be corrected. The pre-pass in Task 4 is still required, for a different reason: a collision is only discoverable once the *later* row has been read, by which point the earlier row has already been flushed, counted, and given a feedback record.
- **The worktree has no `.venv` of its own.** Every `.venv/Scripts/python.exe` command below must be run with the interpreter from the main checkout, with the worktree as the working directory: `& "C:\Users\MathewHearl\OneDrive - Addis Energy\Documents\01_Software\database_sandbox\experiment_tracking_sandbox\.venv\Scripts\python.exe" -m pytest ...`
- **Every test a task adds must be green when that task commits.** If a test cannot be satisfied by its own task's code, it belongs in the later task that makes it observable.
- **Never use bare `git stash` / `git stash pop` here.** The stash stack is shared with the main checkout and every other worktree, and other sessions may push or pop concurrently — a bare `pop` can restore someone else's work into this tree. To verify a RED state against pre-fix source, prefer `git stash push -u -m "<unique-tag>"` followed by `git stash apply <sha>` and an explicit drop, or simply `git show HEAD:<path>` / a scratch copy. Never `git commit --amend` either: an earlier round amended a commit that was not its own and the history had to be rebuilt.
- Python style: `flake8 --max-line-length=100` must be clean on the changed file. Do not run `black` on it — the repo is not Black-formatted in practice and it would reformat locked neighbours.
- Commit format: `[#111] <imperative description under 50 chars>` followed by `- Tests added: yes/no` and `- Docs updated: yes/no`.

## Validated facts this plan is built on

Established by reading the real workbooks, not inferred. **`docs/sample_data/Master_Results_Tracker_v3.xlsx` (rewritten 2026-07-30 10:15) is the reference.**

The v3 `Dashboard` sheet has these 20 columns, in this order:

```
Experiment ID | Description | Sample Date | Duration (Days) | NH4 (mM) |
FL H2 (ppm) | FL Gas Volume (mL) | FL Gas Pressure (psi) | Sample pH |
Sample Conductivity (mS/cm) | Modification | NMR Run Date |
Sampled Solution Volume (mL) | ICP Run Date | GC Run Date | XRD Run Date |
OVERWRITE | DI H2 (ppm) | DI gas volume (mL) | DI gas pressure (psi)
```

**What v3 changed relative to v2** (v2 had 24 columns): the wide DI block `DI a H2 (ppm)` / `DI b H2 (ppm)` / `DI c H2 (ppm)` / `DI avg H2 (ppm)` / `DI SD (ppm)` collapsed to a single **`DI H2 (ppm)`**. The `GC DI` source sheet changed the same way — its `a/b/c (peak area)` and `a/b/c (ppm)` columns became one `H2 (peak area)` + `H2 (ppm)`. There is no `Replicate` column in v3.

This is the pivot: **a/b/c were replicate vials, not triplicate injections of one sample.** Each vial now gets its own row under its own unique experiment ID. `SERUM_001` with replicates a/b/c sampled at t1 and t3 is six rows — `SERUM_001a-t1`, `SERUM_001b-t1`, `SERUM_001c-t1`, `SERUM_001a-t3`, `SERUM_001b-t3`, `SERUM_001c-t3` — not two rows with three columns each.

**Four columns were renamed and are silently dropped by the current parser:**

| Parser reads today | Sheet actually has | Consequence |
|---|---|---|
| `H2 (ppm)` | `FL H2 (ppm)` | `h2_concentration` never written |
| `Gas Volume (mL)` | `FL Gas Volume (mL)` | `gas_sampling_volume_ml` never written |
| `Gas Pressure (psi)` | `FL Gas Pressure (psi)` | `gas_sampling_pressure_MPa` never written |
| `Overwrite` | `OVERWRITE` | `_overwrite` is always `False` |

Because `_calculate_hydrogen()` (`backend/services/calculations/scalar_calcs.py:135`) needs ppm *and* volume *and* pressure, `h2_micromoles`, `h2_mass_ug` and `h2_grams_per_ton_yield` have been uncomputable from a master upload since the rename. Fixing the H2 column alone would not restore them — this is why gas volume and pressure are in scope.

**v3 fill state as of 10:15:** 210 rows carry an Experiment ID. `FL H2 (ppm)` and `DI H2 (ppm)` are both empty throughout; `FL Gas Volume (mL)` / `FL Gas Pressure (psi)` are populated on 209; `DI gas volume (mL)` / `DI gas pressure (psi)` on all 499 (including blank rows). The GC columns are mid-repopulation, so **Task 6's real-file run is expected to report zero H2 sources** — that is the current state of the sheet, not a bug in the parser. Do not "fix" the parser to make H2 appear.

### Mean/SD already exists — do not build it

The user confirmed (2026-07-30) that the existing rollup is what they want, now that `DI avg` / `DI SD` are off the sheet. It is already end-to-end:

- **View:** `v_results_scalar_rollup`, defined in `database/event_listeners.py:521`. Groups by `COALESCE(e.base_experiment_id, e.experiment_id)` × `time_post_reaction_bucket_days`. Mean via `AVG`, median via `percentile_cont(0.5)`, SD via `stddev_samp` (n-1, `NULL` when `n_replicates = 1`). Excludes `is_outlier` vials from every aggregate including `n_replicates`. Carries `mean_h2_ppm` / `sd_h2_ppm` (issue #90).
- **API:** `GET /api/experiments/groups/{base_id}/rollup` — `backend/api/routers/experiments.py:561` → `backend/services/replicate_groups.py:292`, typed by `RollupTimepointResponse` (`backend/api/schemas/results.py:203`).
- **UI:** `frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx`.

Under the pivot this populates on its own: `SERUM_001a-t1` parses to `base_experiment_id = SERUM_001`, `replicate_label = a`, bucket `1`, so the three letters at one timepoint aggregate to `n_replicates = 3` with a mean and an n-1 SD. Task 5 proves this with a test; it writes no new calculation.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `backend/services/bulk_uploads/master_bulk_upload.py` | Dashboard parsing, header aliasing, GC precedence, duplicate detection, warnings | Modify |
| `backend/api/routers/bulk_uploads.py:378-407` | Surface `warnings` on `POST /api/bulk-uploads/master-results` | Modify (2 lines) |
| `tests/services/bulk_uploads/test_master_bulk_upload.py` | Service tests | Modify (append) |
| `tests/api/test_bulk_uploads.py` | Two stale mocks + warnings contract test | Modify |
| `tests/views/test_v_results_scalar_rollup.py` | Proof that vial-level IDs roll up | Modify (append) |
| `docs/CALCULATIONS.md` | Hydrogen section — which GC block feeds the inputs | Modify |
| `.claude/rules/MODELS.md` | `ScalarResults` Hydrogen section — precedence + one-row-per-vial rule | Modify |
| `docs/user_guide/BULK_UPLOADS.md` | Master Results columns and the one-row-per-vial rule | Modify |
| `docs/working/issue-log.md` | Session log entry | Append (Task 7) |

---

### Task 1: Header aliases — v3 canonical, older spellings still accepted

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py:113-123` (the two `df.columns = [...]` blocks), `:203-211` (the value reads)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: module-level `_HEADER_ALIASES: Dict[str, str]` and `_normalize_headers(columns) -> List[str]`. Canonical column names after normalisation are exactly: `"FL H2 (ppm)"`, `"FL Gas Volume (mL)"`, `"FL Gas Pressure (psi)"`, `"DI H2 (ppm)"`, `"DI gas volume (mL)"`, `"DI gas pressure (psi)"`, `"Overwrite"`, `"Sampled Solution Volume (mL)"`, `"Replicate"`. Tasks 2-4 read rows by these names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
# ---------------------------------------------------------------------------
# v3 Dashboard headers (issue #111)
# ---------------------------------------------------------------------------

# The v3 Dashboard as of 2026-07-30. One row per unique experiment ID: the
# wide 'DI a/b/c' block collapsed to a single 'DI H2 (ppm)' because a/b/c were
# replicate vials, and each vial now gets its own row.
_V3_HEADERS = [
    "Experiment ID", "Description", "Sample Date", "Duration (Days)", "NH4 (mM)",
    "FL H2 (ppm)", "FL Gas Volume (mL)", "FL Gas Pressure (psi)",
    "Sample pH", "Sample Conductivity (mS/cm)", "Modification", "NMR Run Date",
    "Sampled Solution Volume (mL)", "ICP Run Date", "GC Run Date", "XRD Run Date",
    "OVERWRITE",
    "DI H2 (ppm)", "DI gas volume (mL)", "DI gas pressure (psi)",
]


def _v3_row(
    experiment_id: str,
    duration: float | None = 7.0,
    *,
    description: str = "Day 7",
    nh4: float | None = None,
    fl_h2: float | None = None,
    fl_vol: float | None = None,
    fl_psi: float | None = None,
    ph: float | None = 7.0,
    overwrite=None,
    di_h2: float | None = None,
    di_vol: float | None = None,
    di_psi: float | None = None,
) -> list:
    """Build one Dashboard row in _V3_HEADERS order."""
    return [
        experiment_id, description, None, duration, nh4,
        fl_h2, fl_vol, fl_psi,
        ph, None, None, None,
        None, None, None, None,
        overwrite,
        di_h2, di_vol, di_psi,
    ]


def _master_excel_v3(rows: list[list]) -> bytes:
    return make_excel_multisheet({"Dashboard": (_V3_HEADERS, rows)})


def test_v3_fl_h2_columns_are_ingested(db_session: Session):
    """'FL H2 (ppm)' / 'FL Gas Volume (mL)' / 'FL Gas Pressure (psi)' are read.

    Before #111 these were dropped silently: the parser looked for the pre-rename
    'H2 (ppm)' spelling, found nothing, and the None-filter removed the field.
    """
    _seed_experiment(db_session, "HPHT_FL001", 8801)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_FL001", 7.0, fl_h2=115.04, fl_vol=3935.0, fl_psi=90.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_FL001")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(115.04)
    assert scalar.h2_concentration_unit == "ppm"
    assert scalar.gas_sampling_volume_ml == pytest.approx(3935.0)
    assert scalar.gas_sampling_pressure_MPa == pytest.approx(90.0 * _PSI_TO_MPA, rel=1e-3)


def test_v3_uppercase_overwrite_header_is_honoured(db_session: Session):
    """The sheet spells it 'OVERWRITE'; the parser used to look for 'Overwrite'.

    The difference is only observable on a field the second upload leaves
    BLANK. `create_scalar_result_ex` (backend/services/scalar_results_service.py
    :129-135) writes every SCALAR_UPDATABLE_FIELDS entry when overwrite is True
    — clearing ones absent from the row — but only the fields actually present
    when it is False. A test that repeats the same populated field in both
    uploads passes either way and proves nothing.
    """
    _seed_experiment(db_session, "HPHT_FL002", 8802)

    first = _master_excel_v3([_v3_row("HPHT_FL002", 7.0, nh4=5.0, ph=7.0)])
    MasterBulkUploadService.from_bytes(db_session, first)

    # Repeat NH4 but leave Sample pH blank, with OVERWRITE set.
    second = _master_excel_v3([
        _v3_row("HPHT_FL002", 7.0, description="Day 7 revised",
                nh4=6.5, ph=None, overwrite=1.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, second
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert updated == 1
    assert created == 0

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_FL002")
        .one()
    ).scalar_data
    assert scalar.gross_ammonium_concentration_mM == pytest.approx(6.5)
    assert scalar.final_ph is None, (
        "OVERWRITE=TRUE must clear a field the new row leaves blank; a "
        "surviving 7.0 means the OVERWRITE header was not recognised"
    )


def test_both_spellings_of_one_field_do_not_collide(db_session: Session):
    """A sheet carrying both 'H2 (ppm)' and 'FL H2 (ppm)' must not produce two
    columns with the same name.

    Duplicate column names make pandas hand `row.get()` a Series instead of a
    scalar; `_parse_float` raises on it and its `except Exception` returns None,
    silently dropping the value — the exact failure issue #111 exists to fix.
    The literal v3 column wins; the aliased one keeps its raw header.
    """
    from backend.services.bulk_uploads.master_bulk_upload import _normalize_headers

    for columns, expected in (
        (["H2 (ppm)", "FL H2 (ppm)"], ["H2 (ppm)", "FL H2 (ppm)"]),
        (["FL H2 (ppm)", "H2 (ppm)"], ["FL H2 (ppm)", "H2 (ppm)"]),
        (["DI avg H2 (ppm)", "DI H2 (ppm)"], ["DI avg H2 (ppm)", "DI H2 (ppm)"]),
        # Two aliases of one canonical, neither spelled canonically.
        (["gas volume (ml)", "Gas Volume (mL)"],
         ["FL Gas Volume (mL)", "Gas Volume (mL)"]),
    ):
        result = _normalize_headers(columns)
        assert result == expected, f"{columns} -> {result}"
        assert len(set(result)) == len(result), f"duplicate columns from {columns}"

    # Ordinary single-spelling mapping is unaffected.
    assert _normalize_headers(["H2 (ppm)"]) == ["FL H2 (ppm)"]
    assert _normalize_headers(["OVERWRITE"]) == ["Overwrite"]


def test_both_spellings_end_to_end_keeps_the_v3_value(db_session: Session):
    """The collision case survives a real upload: the v3 column's value lands."""
    _seed_experiment(db_session, "HPHT_FL005", 8805)

    headers = ["H2 (ppm)"] + list(_V3_HEADERS)
    row = [999.0] + _v3_row("HPHT_FL005", 7.0, fl_h2=115.0, fl_vol=3935.0, fl_psi=90.0)
    xlsx = make_excel_multisheet({"Dashboard": (headers, [row])})

    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_FL005")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(115.0), (
        "the literal 'FL H2 (ppm)' column must win, and its value must not be "
        "lost to a duplicate-column Series"
    )


def test_legacy_h2_header_still_parses(db_session: Session):
    """Archived workbooks using the pre-rename 'H2 (ppm)' block keep working."""
    _seed_experiment(db_session, "HPHT_FL004", 8804)

    xlsx = _master_excel([
        ["HPHT_FL004", 7.0, "Day 7", None, None, None, None,
         5.0, 88.0, 500.0, 145.0, 7.0, None, None, "FALSE"],
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_FL004")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(88.0)
    assert scalar.gas_sampling_volume_ml == pytest.approx(500.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "v3_fl_h2 or uppercase_overwrite or legacy_h2_header" -v
```

Expected: `test_v3_fl_h2_columns_are_ingested` FAILS on `h2_concentration` being `None`; `test_v3_uppercase_overwrite_header_is_honoured` FAILS on `final_ph` still being `7.0` (the un-aliased `OVERWRITE` left `_overwrite` False, so the blank pH was preserved instead of cleared); `test_legacy_h2_header_still_parses` PASSES already — it is the regression guard, keep it.

**Every test in this task must be green at commit time.** The `DI avg H2 (ppm)` alias cannot be observed until Task 2 teaches the parser to read a DI column at all, so its test lives in Task 2, not here.

- [ ] **Step 3: Add the alias table**

In `backend/services/bulk_uploads/master_bulk_upload.py`, after `_DASHBOARD_SHEET = "Dashboard"` (line 24):

```python
# Canonical Dashboard headers, keyed by the lowercased sheet header.
#
# Issue #111: the sheet was restructured twice. The single 'H2 (ppm)' block was
# renamed to a Full Loop ('FL ...') block and 'Overwrite' became 'OVERWRITE';
# then the wide DI block ('DI a/b/c H2 (ppm)' + avg + SD) collapsed to one
# 'DI H2 (ppm)' when a/b/c moved to their own rows. Every spelling is accepted
# so archived workbooks keep parsing; the values on the right are the only
# names the row reads below use.
_HEADER_ALIASES: Dict[str, str] = {
    # Full Loop — pre-rename spelling first in each pair
    "h2 (ppm)": "FL H2 (ppm)",
    "fl h2 (ppm)": "FL H2 (ppm)",
    "gas volume (ml)": "FL Gas Volume (mL)",
    "fl gas volume (ml)": "FL Gas Volume (mL)",
    "gas pressure (psi)": "FL Gas Pressure (psi)",
    "fl gas pressure (psi)": "FL Gas Pressure (psi)",
    # GC direct injection — 'DI avg' is the v2 spelling of v3's 'DI H2'
    "di h2 (ppm)": "DI H2 (ppm)",
    "di avg h2 (ppm)": "DI H2 (ppm)",
    "di gas volume (ml)": "DI gas volume (mL)",
    "di gas pressure (psi)": "DI gas pressure (psi)",
    # Casing-only normalisations (previously done inline)
    "overwrite": "Overwrite",
    "sampled solution volume (ml)": "Sampled Solution Volume (mL)",
    "replicate": "Replicate",
}


def _normalize_headers(columns: Any) -> List[str]:
    """Map sheet headers onto canonical names.

    A sheet can carry two spellings of one field — a hand-merged workbook with
    both 'DI avg H2 (ppm)' and 'DI H2 (ppm)', or 'H2 (ppm)' beside its v3
    replacement 'FL H2 (ppm)'. Renaming both to the canonical name would give
    pandas duplicate columns, and `row.get()` would then return a Series rather
    than a scalar; `_parse_float` raises on that and its `except Exception`
    swallows the value — the exact silent loss issue #111 exists to fix.

    Two rules prevent it:
      1. A column never takes a canonical name that another column in the same
         sheet already carries literally. The literal (v3) column wins and the
         aliased one keeps its raw header.
      2. Any remaining collision falls back to the raw header.
    """
    raw = [str(c).strip() for c in columns]
    raw_names = set(raw)
    out: List[str] = []
    seen: set[str] = set()
    for name in raw:
        canonical = _HEADER_ALIASES.get(name.lower(), name)
        if canonical != name and canonical in raw_names:
            canonical = name
        if canonical in seen:
            canonical = name
        out.append(canonical)
        seen.add(canonical)
    return out
```

- [ ] **Step 4: Replace the two inline normalisation blocks**

Delete lines 113-123 (`df.columns = [str(c).strip() ...]` and both `df.columns = [...]` list comprehensions) and put in their place:

```python
    df.columns = _normalize_headers(df.columns)
```

- [ ] **Step 5: Read the renamed columns**

Replace lines 203-204 (`h2_ppm`, `gas_vol_ml`) and the `gas_psi` read so they use canonical names:

```python
        h2_ppm = _parse_float(row.get("FL H2 (ppm)"))
        gas_vol_ml = _parse_float(row.get("FL Gas Volume (mL)"))
        gas_psi = _parse_float(row.get("FL Gas Pressure (psi)"))
```

`overwrite = _parse_bool(row.get("Overwrite"))` needs no edit — `_normalize_headers` now folds `OVERWRITE` onto `Overwrite`.

- [ ] **Step 6: Run the tests**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -v
```

Expected: all PASS, including the ~20 pre-existing tests that use the legacy headers. If any pre-existing test fails, the alias table is wrong — do not edit the old tests to accommodate it.

- [ ] **Step 7: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "$(cat <<'EOF'
[#111] Accept v3 Dashboard GC headers

- FL H2/gas volume/pressure and OVERWRITE were silently dropped
- v2 and pre-rename spellings still parse via one alias table
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Full Loop > DI precedence

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (add `_resolve_h2`, call it in the row loop)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Consumes: canonical column names from Task 1.
- Produces: `_resolve_h2(row) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[str]]` returning `(h2_ppm, gas_volume_mL, gas_pressure_psi, source)` where `source` is `"full_loop"`, `"di"`, or `None`. Task 3 reads that fourth element.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
def test_full_loop_wins_when_both_present(db_session: Session):
    """Full Loop takes precedence over DI (Mat, 2026-07-30).

    Gas volume and pressure come from the SAME block as the winning
    concentration — _calculate_hydrogen() combines all three, so mixing blocks
    would compute micromoles from a volume that injection never used.
    """
    _seed_experiment(db_session, "HPHT_PREC01", 8811)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_PREC01", 7.0,
                fl_h2=115.0, fl_vol=3935.0, fl_psi=90.0,
                di_h2=42.0, di_vol=10.0, di_psi=15.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_PREC01")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(115.0)
    assert scalar.gas_sampling_volume_ml == pytest.approx(3935.0)
    assert scalar.gas_sampling_pressure_MPa == pytest.approx(90.0 * _PSI_TO_MPA, rel=1e-3)


def test_di_used_when_full_loop_absent(db_session: Session):
    """A blank Full Loop cell falls back to 'DI H2 (ppm)' and DI's own gas
    volume and pressure."""
    _seed_experiment(db_session, "HPHT_PREC02", 8812)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_PREC02", 7.0, fl_h2=None, di_h2=42.0, di_vol=10.0, di_psi=15.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_PREC02")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(42.0)
    assert scalar.h2_concentration_unit == "ppm"
    assert scalar.gas_sampling_volume_ml == pytest.approx(10.0)
    assert scalar.gas_sampling_pressure_MPa == pytest.approx(15.0 * _PSI_TO_MPA, rel=1e-3)


def test_zero_h2_is_a_real_measurement(db_session: Session):
    """A Full Loop reading of exactly 0 ppm is stored, not treated as blank.

    Mat is rewriting the Excel formulas so an absent peak area leaves the cell
    empty; a 0 that survives that rewrite means a genuine zero. Do NOT route H2
    through _parse_measurement_float (the pH/conductivity zero-suppressor).
    """
    _seed_experiment(db_session, "HPHT_PREC03", 8813)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_PREC03", 7.0, fl_h2=0.0, fl_vol=3785.0, fl_psi=30.0, di_h2=99.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_PREC03")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == 0.0, "0 ppm must not fall through to DI"
    assert scalar.h2_micromoles == pytest.approx(0.0)


def test_v2_di_avg_header_maps_onto_di_h2(db_session: Session):
    """A v2 workbook's 'DI avg H2 (ppm)' still lands on h2_concentration.

    v2 is not the reference format any more, but an archived workbook must not
    lose its DI reading just because the column was renamed in v3. The alias
    itself is Task 1's, but nothing reads a DI column until _resolve_h2 exists,
    so the test belongs here.
    """
    _seed_experiment(db_session, "HPHT_PREC05", 8815)

    headers = list(_V3_HEADERS)
    headers[headers.index("DI H2 (ppm)")] = "DI avg H2 (ppm)"
    xlsx = make_excel_multisheet({"Dashboard": (headers, [
        _v3_row("HPHT_PREC05", 7.0, di_h2=42.0, di_vol=10.0, di_psi=15.0),
    ])})
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_PREC05")
        .one()
    ).scalar_data
    assert scalar.h2_concentration == pytest.approx(42.0)


def test_no_gc_reading_leaves_h2_unset(db_session: Session):
    """Both GC blocks blank → h2_concentration stays None and the row still lands."""
    _seed_experiment(db_session, "HPHT_PREC04", 8814)

    xlsx = _master_excel_v3([_v3_row("HPHT_PREC04", 7.0, nh4=5.0)])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 1

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_PREC04")
        .one()
    ).scalar_data
    assert scalar.h2_concentration is None
    assert scalar.h2_concentration_unit is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "full_loop_wins or di_used or zero_h2 or no_gc_reading or di_avg_header" -v
```

Expected: `test_di_used_when_full_loop_absent` and `test_v2_di_avg_header_maps_onto_di_h2` both FAIL (`h2_concentration is None`) — nothing reads a DI column before `_resolve_h2` exists. `test_full_loop_wins_when_both_present`, `test_zero_h2_is_a_real_measurement` and `test_no_gc_reading_leaves_h2_unset` PASS after Task 1 — they pin behavior that must not regress when the DI branch is added.

- [ ] **Step 3: Add the resolver**

In `backend/services/bulk_uploads/master_bulk_upload.py`, after `_find_sheet()`:

```python
def _resolve_h2(
    row: Any,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[str], Optional[float]]:
    """Pick the winning GC reading for one Dashboard row (issue #111).

    Full Loop takes precedence over direct injection (Mat, 2026-07-30); DI is
    used only when the Full Loop cell is blank. Gas volume and pressure are
    taken from the same block as the winning concentration, because
    _calculate_hydrogen() combines all three into h2_micromoles — pairing a
    Full Loop ppm with a DI sampling volume would compute a number that
    describes no real injection.

    A value of 0 is a real measurement and wins normally; only a blank cell
    falls through.

    Returns (h2_ppm, gas_volume_mL, gas_pressure_psi, source, di_ppm), where
    source is 'full_loop', 'di', or None when neither block has a
    concentration. `di_ppm` is the parsed DI value whether or not it won, so
    callers can report a superseded DI reading without re-parsing the cell —
    one parse, one source of truth (review finding, Task 3).
    """
    di_ppm = _parse_float(row.get("DI H2 (ppm)"))

    fl_ppm = _parse_float(row.get("FL H2 (ppm)"))
    if fl_ppm is not None:
        return (
            fl_ppm,
            _parse_float(row.get("FL Gas Volume (mL)")),
            _parse_float(row.get("FL Gas Pressure (psi)")),
            "full_loop",
            di_ppm,
        )

    if di_ppm is not None:
        return (
            di_ppm,
            _parse_float(row.get("DI gas volume (mL)")),
            _parse_float(row.get("DI gas pressure (psi)")),
            "di",
            di_ppm,
        )

    # No concentration in either block. Keep reading the Full Loop gas columns
    # so a row recording only the sampling geometry behaves as it did pre-#111.
    return (
        None,
        _parse_float(row.get("FL Gas Volume (mL)")),
        _parse_float(row.get("FL Gas Pressure (psi)")),
        None,
        di_ppm,
    )
```

- [ ] **Step 4: Call it from the row loop**

Replace the three separate reads added in Task 1 Step 5 with:

```python
        h2_ppm, gas_vol_ml, gas_psi, h2_source, di_ppm = _resolve_h2(row)
```

Leave `gas_mpa = gas_psi * _PSI_TO_MPA if gas_psi is not None else None` on the following line exactly as it is.

- [ ] **Step 5: Run the tests**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -v
```

Expected: all PASS. `h2_source` is assigned but unused until Task 3 — `flake8` does not flag unused locals, so this is fine; do not add a `# noqa`.

- [ ] **Step 6: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "$(cat <<'EOF'
[#111] Apply Full Loop over DI GC precedence

- Gas volume and pressure follow the winning block
- 0 ppm is a real reading, only blanks fall through
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Surface warnings instead of dropping data silently

The root cause of #111 was not the rename itself but that an unmatched column produced no signal. This task adds the signal, flags leftover wide-format DI columns, and records which GC block each row used.

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (add `MasterUploadResult`, `from_bytes_ex`, warning generation, per-row `h2_source` feedback)
- Modify: `backend/api/routers/bulk_uploads.py:378-407`
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`, `tests/api/test_bulk_uploads.py`

**Interfaces:**
- Consumes: `_resolve_h2()`'s `source` return value from Task 2.
- Produces:
  - `MasterUploadResult` dataclass with fields `created: int`, `updated: int`, `skipped: int`, `errors: List[str]`, `warnings: List[str]`, `feedbacks: List[Dict[str, Any]]` and method `as_tuple() -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]`.
  - `MasterBulkUploadService.from_bytes_ex(db, file_bytes) -> MasterUploadResult`.
  - `MasterBulkUploadService.from_bytes` and `sync_from_path` keep their existing 5-tuple signatures — the `_ex` + thin-wrapper shape already used in this codebase (`create_scalar_result_ex`), chosen so none of the ~20 existing service tests change.
  - Each feedback dict gains `"h2_source": "full_loop" | "di" | None` and `"h2_di_superseded": bool`.
  - Module-level `_RECOGNIZED_H2_COLUMNS: set[str]` and `_WIDE_DI_COLUMNS: set[str]`. Task 4 does not use these.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
def test_unrecognized_h2_column_warns(db_session: Session):
    """A column mentioning H2 that the parser cannot map is reported.

    This is the guard for the class of bug #111 itself was: a renamed column
    that upserts every other field successfully while the H2 value vanishes.
    """
    _seed_experiment(db_session, "HPHT_WARN01", 8821)

    headers = list(_V3_HEADERS)
    headers[headers.index("FL H2 (ppm)")] = "GC Loop H2 ppm"  # a future rename
    xlsx = make_excel_multisheet({"Dashboard": (headers, [
        _v3_row("HPHT_WARN01", 7.0, fl_h2=115.0),
    ])})

    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.created == 1, "The row must still upload — this is a warning, not a failure"
    assert any("GC Loop H2 ppm" in w for w in result.warnings)


def test_no_h2_column_at_all_warns(db_session: Session):
    """A Dashboard with neither GC block warns once, at file level."""
    _seed_experiment(db_session, "HPHT_WARN02", 8822)

    keep = [h for h in _V3_HEADERS if "H2" not in h]
    row = [v for h, v in zip(_V3_HEADERS, _v3_row("HPHT_WARN02", 7.0, nh4=5.0))
           if "H2" not in h]
    xlsx = make_excel_multisheet({"Dashboard": (keep, [row])})

    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    assert result.created == 1
    assert any("no recognized H2 column" in w for w in result.warnings)


def test_wide_di_columns_warn_about_one_row_per_vial(db_session: Session):
    """A v2 sheet still carrying 'DI a/b/c H2 (ppm)' is told to split the rows.

    v3 collapsed those to one 'DI H2 (ppm)' because a/b/c are replicate vials
    that each get their own experiment ID now. The columns are ignored, not
    guessed at.
    """
    _seed_experiment(db_session, "HPHT_WARN03", 8823)

    headers = list(_V3_HEADERS) + ["DI a H2 (ppm)", "DI b H2 (ppm)", "DI c H2 (ppm)"]
    row = _v3_row("HPHT_WARN03", 7.0, nh4=5.0) + [10.0, 11.0, 12.0]
    xlsx = make_excel_multisheet({"Dashboard": (headers, [row])})

    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    assert result.created == 1
    assert any("one row per experiment ID" in w for w in result.warnings)

    scalar = (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "HPHT_WARN03")
        .one()
    ).scalar_data
    assert scalar.h2_concentration is None, "wide DI values must not be guessed at"


def test_h2s_column_is_not_reported_as_a_dropped_h2_reading(db_session: Session):
    """'H2S (ppm)' must not be flagged as an unrecognized hydrogen column.

    The warning exists so a researcher trusts it when it fires. A substring
    match on 'h2' would also hit H2S and H2O and cry wolf about a hydrogen
    value that was never there.
    """
    _seed_experiment(db_session, "HPHT_WARN07", 8827)

    headers = list(_V3_HEADERS) + ["H2S (ppm)", "H2O (%)"]
    row = _v3_row("HPHT_WARN07", 7.0, fl_h2=115.0) + [12.0, 3.0]
    xlsx = make_excel_multisheet({"Dashboard": (headers, [row])})

    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    assert result.created == 1
    assert result.warnings == [], f"H2S/H2O must not warn, got: {result.warnings}"

    # A genuine rename still warns — the guard narrows, it does not disable.
    renamed = list(_V3_HEADERS)
    renamed[renamed.index("FL H2 (ppm)")] = "GC Loop H2 ppm"
    xlsx2 = make_excel_multisheet({"Dashboard": (renamed, [
        _v3_row("HPHT_WARN07", 8.0, fl_h2=115.0),
    ])})
    result2 = MasterBulkUploadService.from_bytes_ex(db_session, xlsx2)
    assert any("GC Loop H2 ppm" in w for w in result2.warnings)


def test_superseded_di_flag_comes_from_the_resolver(db_session: Session):
    """h2_di_superseded is derived from _resolve_h2's own DI parse.

    Guards against the flag and the precedence decision drifting apart if the
    DI branch later gains unit conversion or a sanity bound.
    """
    from backend.services.bulk_uploads.master_bulk_upload import _resolve_h2

    both = {"FL H2 (ppm)": 115.0, "DI H2 (ppm)": 42.0}
    fl_only = {"FL H2 (ppm)": 115.0, "DI H2 (ppm)": None}
    di_only = {"FL H2 (ppm)": None, "DI H2 (ppm)": 42.0}
    neither = {"FL H2 (ppm)": None, "DI H2 (ppm)": None}

    assert _resolve_h2(both)[3:] == ("full_loop", 42.0)
    assert _resolve_h2(fl_only)[3:] == ("full_loop", None)
    assert _resolve_h2(di_only)[3:] == ("di", 42.0)
    assert _resolve_h2(neither)[3:] == (None, None)


def test_feedback_records_which_gc_block_was_used(db_session: Session):
    """Each row reports its H2 source so a discarded DI reading is visible."""
    _seed_experiment(db_session, "HPHT_WARN04", 8824)
    _seed_experiment(db_session, "HPHT_WARN05", 8825)

    xlsx = _master_excel_v3([
        _v3_row("HPHT_WARN04", 7.0, fl_h2=115.0, di_h2=42.0),   # DI superseded
        _v3_row("HPHT_WARN05", 7.0, fl_h2=None, di_h2=42.0),    # DI used
    ])
    result = MasterBulkUploadService.from_bytes_ex(db_session, xlsx)

    assert result.errors == []
    assert result.created == 2

    by_id = {f["experiment_id"]: f for f in result.feedbacks}
    assert by_id["HPHT_WARN04"]["h2_source"] == "full_loop"
    assert by_id["HPHT_WARN04"]["h2_di_superseded"] is True
    assert by_id["HPHT_WARN05"]["h2_source"] == "di"
    assert by_id["HPHT_WARN05"]["h2_di_superseded"] is False


def test_from_bytes_tuple_shape_unchanged(db_session: Session):
    """from_bytes() still returns the legacy 5-tuple — no caller breaks."""
    _seed_experiment(db_session, "HPHT_WARN06", 8826)

    xlsx = _master_excel_v3([_v3_row("HPHT_WARN06", 7.0, nh4=5.0)])
    out = MasterBulkUploadService.from_bytes(db_session, xlsx)

    assert len(out) == 5
    created, updated, skipped, errors, feedbacks = out
    assert created == 1
    assert isinstance(errors, list) and isinstance(feedbacks, list)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "warn or tuple_shape or which_gc_block" -v
```

Expected: the four `from_bytes_ex` tests FAIL with `AttributeError: type object 'MasterBulkUploadService' has no attribute 'from_bytes_ex'`. `test_from_bytes_tuple_shape_unchanged` PASSES — it is the regression guard.

- [ ] **Step 3: Add the result dataclass and the column sets**

At the top of `backend/services/bulk_uploads/master_bulk_upload.py`, extend the imports:

```python
import re
from dataclasses import dataclass, field
```

After `_HEADER_ALIASES`:

```python
# H2 as a standalone token, so 'H2S (ppm)' and 'H2O' never look like a dropped
# hydrogen column while a real rename ('GC Loop H2 ppm') still does.
_H2_TOKEN = re.compile(r"\bh2\b", re.IGNORECASE)

# Columns whose header mentions H2 and that the parser deliberately handles.
_RECOGNIZED_H2_COLUMNS = {
    "FL H2 (ppm)",
    "DI H2 (ppm)",
}

# v2's wide DI block. Those letters are replicate VIALS, and v3 gives each vial
# its own row, so there is no correct way to fold three values into one result.
# Recognized so they are named in a specific warning rather than a generic one.
_WIDE_DI_COLUMNS = {
    "DI a H2 (ppm)",
    "DI b H2 (ppm)",
    "DI c H2 (ppm)",
    "DI SD (ppm)",
}


@dataclass
class MasterUploadResult:
    """Master Results upload outcome.

    Exists because the legacy 5-tuple has no slot for warnings and ~20 tests
    plus the router unpack it positionally. `from_bytes` keeps returning the
    tuple; `from_bytes_ex` returns this.
    """

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    feedbacks: List[Dict[str, Any]] = field(default_factory=list)

    def as_tuple(self) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
        """Legacy 5-tuple shape. Warnings are dropped — callers that need them
        should use from_bytes_ex()."""
        return self.created, self.updated, self.skipped, self.errors, self.feedbacks
```

- [ ] **Step 4: Convert `_process_bytes` to return `MasterUploadResult`**

Change its signature and every `return`. The early returns become, in order:

```python
def _process_bytes(db: Session, file_bytes: bytes) -> MasterUploadResult:
    """
    Parse the Master Results Excel and upsert scalar results.
    """
    from backend.services.scalar_results_service import ScalarResultsService  # noqa: PLC0415

    out = MasterUploadResult()
    errors = out.errors
    warnings = out.warnings
    feedbacks = out.feedbacks
    created = updated = skipped = 0

    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
    except Exception as exc:
        errors.append(f"Failed to read file: {exc}")
        return out

    sheet_name = _find_sheet(xls)
    if sheet_name is None:
        errors.append("File has no sheets.")
        return out

    try:
        df = xls.parse(sheet_name)
    except Exception as exc:
        errors.append(f"Failed to parse sheet '{sheet_name}': {exc}")
        return out
```

the missing-required-columns branch:

```python
    if missing:
        errors.append(
            f"Sheet '{sheet_name}' is missing required columns: {', '.join(sorted(missing))}. "
            f"Available: {', '.join(df.columns[:10])}"
        )
        return out
```

and the final return:

```python
    out.created, out.updated, out.skipped = created, updated, skipped
    return out
```

Everything between is unchanged — in particular keep the `savepoint = db.begin_nested()` block exactly as it is.

- [ ] **Step 5: Emit the file-level warnings**

Immediately after the `if missing:` block, before the `for idx, row in df.iterrows():` loop:

```python
    # Issue #111: an H2 column the parser cannot map used to vanish silently —
    # every other field upserted fine, so a sync looked healthy while the
    # hydrogen value was lost. Say so instead.
    stale_wide_di = [c for c in df.columns if c in _WIDE_DI_COLUMNS]
    if stale_wide_di:
        warnings.append(
            "Ignoring wide direct-injection column(s): "
            + ", ".join(f"'{c}'" for c in sorted(stale_wide_di))
            + ". Those letters are replicate vials — give each one row per "
              "experiment ID (e.g. SERUM_001a-t1, SERUM_001b-t1) and put its "
              "reading in 'DI H2 (ppm)'."
        )

    # Match H2 only as a standalone token. A substring test would also fire on
    # an H2S or H2O column, telling a researcher a hydrogen reading was dropped
    # when none was — a false alarm in exactly the place this warning is meant
    # to be trustworthy. A genuine rename keeps H2 as its own token
    # ('GC Loop H2 ppm'), so detection is unaffected.
    unmapped_h2 = [
        c for c in df.columns
        if _H2_TOKEN.search(c)
        and c not in _RECOGNIZED_H2_COLUMNS
        and c not in _WIDE_DI_COLUMNS
    ]
    if unmapped_h2:
        warnings.append(
            "Unrecognized H2 column(s) ignored: "
            + ", ".join(f"'{c}'" for c in unmapped_h2)
            + ". No hydrogen value was read from them — check the Dashboard "
              "headers against the parser's expected names."
        )

    if not _RECOGNIZED_H2_COLUMNS & set(df.columns):
        warnings.append(
            f"Sheet '{sheet_name}' has no recognized H2 column "
            "('FL H2 (ppm)' or 'DI H2 (ppm)') — no hydrogen data was ingested."
        )
```

- [ ] **Step 6: Record the H2 source on each row's feedback**

Replace the existing `feedbacks.append(...)` line inside the `try` block with:

```python
            feedbacks.append({
                "row": row_num,
                "experiment_id": exp_id,
                "action": action,
                "h2_source": h2_source,
                # di_ppm comes from _resolve_h2's own parse — re-reading the
                # cell here would let this flag drift from the precedence
                # decision if the DI branch ever gains filtering.
                "h2_di_superseded": h2_source == "full_loop" and di_ppm is not None,
            })
```

This is the per-row note issue #111 asks for. It is deliberately *not* a warning — a sheet where every row carries both readings would otherwise emit hundreds of lines and bury the real ones.

- [ ] **Step 7: Add `from_bytes_ex` and keep the wrappers**

```python
    @staticmethod
    def sync_from_path(db: Session) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
        ...
        # (unchanged body; each early-return error branch keeps its tuple shape)
        return _process_bytes(db, file_bytes).as_tuple()

    @staticmethod
    def from_bytes(
        db: Session, file_bytes: bytes
    ) -> Tuple[int, int, int, List[str], List[Dict[str, Any]]]:
        """Parse a manually uploaded Master Results file.

        Legacy 5-tuple shape, kept for existing callers. Use from_bytes_ex()
        to also receive warnings.
        """
        return _process_bytes(db, file_bytes).as_tuple()

    @staticmethod
    def from_bytes_ex(db: Session, file_bytes: bytes) -> MasterUploadResult:
        """Parse a manually uploaded Master Results file, warnings included."""
        return _process_bytes(db, file_bytes)
```

`sync_from_path`'s own early returns (file not found, permission denied) already build 5-tuples literally — leave them alone.

- [ ] **Step 8: Surface warnings from the endpoint**

In `backend/api/routers/bulk_uploads.py`, in `upload_master_results` (line ~394), replace the unpack:

```python
        file_bytes = await file.read()
        outcome = MasterBulkUploadService.from_bytes_ex(db, file_bytes)
        created, updated, skipped = outcome.created, outcome.updated, outcome.skipped
        _finalize_write(db, dry_run)
```

and the response:

```python
    return UploadResponse(
        created=created, updated=updated, skipped=skipped, errors=outcome.errors,
        warnings=outcome.warnings,
        feedbacks=outcome.feedbacks,
        message=_finalize_message(f"Master Results: {created} created, {updated} updated, {skipped} skipped", dry_run),
        dry_run=dry_run,
    )
```

The `except` branch is unchanged. `UploadResponse.warnings` already exists (`backend/api/schemas/bulk_upload.py:98`) and `BulkUploadRow.tsx:207-248` already renders a warnings badge and list — no frontend change is needed.

- [ ] **Step 9: Update the two stale API mocks and add the warnings contract test**

`tests/api/test_bulk_uploads.py` does **not** use `monkeypatch` or an `auth_headers` fixture — auth is handled by the `client` fixture (`tests/api/conftest.py:41`), and the parser is stubbed by swapping the whole module out of `sys.modules` with a `MagicMock`. Follow that convention exactly.

Import the dataclass at module scope — it must come from the **real** module, before `patch.dict` replaces it:

```python
from backend.services.bulk_uploads.master_bulk_upload import MasterUploadResult
```

In `test_master_results_upload_returns_response_shape` (line 324), replace:

```python
    mock_svc.from_bytes.return_value = (3, 1, 0, [], [])
```

with:

```python
    mock_svc.from_bytes_ex.return_value = MasterUploadResult(created=3, updated=1, skipped=0)
```

Make the identical substitution in `test_master_results_dry_run_rolls_back` (line 339). Leave the rest of both tests alone.

Then append:

```python
def test_master_results_response_includes_warnings(client):
    """The endpoint forwards parser warnings into UploadResponse.warnings.

    Guards the #111 fix end to end: a warning raised in the parser has to reach
    the researcher, since BulkUploadRow.tsx renders result.warnings and nothing
    else would show that a column was ignored.
    """
    mock_svc = MagicMock()
    mock_svc.from_bytes_ex.return_value = MasterUploadResult(
        created=1, updated=0, skipped=0,
        errors=[],
        warnings=["Unrecognized H2 column(s) ignored: 'GC Loop H2 ppm'."],
        feedbacks=[{"row": 2, "experiment_id": "X_1", "action": "created",
                    "h2_source": None, "h2_di_superseded": False}],
    )
    fake_mod = MagicMock()
    fake_mod.MasterBulkUploadService = mock_svc

    with patch.dict(sys.modules, {"backend.services.bulk_uploads.master_bulk_upload": fake_mod}):
        resp = client.post(
            "/api/bulk-uploads/master-results",
            files={"file": ("master.xlsx", io.BytesIO(b"fake"), "application/vnd.ms-excel")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 1
    assert any("GC Loop H2 ppm" in w for w in body["warnings"])
```

- [ ] **Step 10: Run the touched suites**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/ tests/api/test_bulk_uploads.py tests/integration/test_master_results_sync_endpoint.py -v
```

Expected: all PASS. `tests/integration/test_master_results_sync_endpoint.py` uses the legacy headers and must pass untouched — if it fails, the alias table or the tuple wrapper is wrong.

- [ ] **Step 11: Lint**

```bash
.venv/Scripts/python.exe -m flake8 --max-line-length=100 backend/services/bulk_uploads/master_bulk_upload.py backend/api/routers/bulk_uploads.py
```

Expected: no output. Do not run `black`.

- [ ] **Step 12: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py backend/api/routers/bulk_uploads.py tests/
git commit -m "$(cat <<'EOF'
[#111] Warn on unmapped and wide-format H2 columns

- from_bytes_ex returns warnings; from_bytes keeps its 5-tuple
- Per-row feedback records full_loop vs di and superseded DI
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: One row per vial — reject duplicate (experiment ID, timepoint) rows

Enforces the pivot. Two rows claiming the same vial at the same day are two measurements colliding on one timepoint; today the second silently overwrites the first or demotes it to non-primary. Both rows are reported and **neither** is written.

This needs a pre-pass, because by the time the loop reaches the second row the first has already been committed by `create_scalar_result_ex`. Identity resolution is therefore lifted out of the loop into a helper that both phases share — do not copy the resolution logic.

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py` (extract `_resolve_row_identity`, add the pre-pass)
- Test: `tests/services/bulk_uploads/test_master_bulk_upload.py`

**Interfaces:**
- Consumes: canonical column names from Task 1.
- Produces: `_resolve_row_identity(row, row_num) -> Tuple[Optional[str], Optional[float], Optional[str], bool]` returning `(experiment_id, time_post_reaction, error_message, skip)`. `skip` is `True` for rows the parser intentionally passes over (blank ID, calibration standard, blank Duration with no `-t` token) — those must keep counting toward `skipped`, not `errors`. When `error_message` is not `None` the row is a per-row error. Both are `None` and `skip` is `False` for a good row.

- [ ] **Step 1: Write the failing tests**

Append to `tests/services/bulk_uploads/test_master_bulk_upload.py`:

```python
def test_duplicate_vial_and_timepoint_is_an_error(db_session: Session):
    """Two rows for the same vial at the same day are both rejected.

    v3 is one row per unique experiment ID. A repeated (ID, duration) pair is
    the old wide-format habit leaking through, and silently letting the second
    row win would destroy the first reading.
    """
    _seed_experiment(db_session, "SERUM_DUP01a", 8831)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP01a", 7.0, description="first", fl_h2=10.0),
        _v3_row("SERUM_DUP01a", 7.0, description="second", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 0, "neither row may be written"
    assert updated == 0
    assert len(errors) == 2, f"both rows must be reported, got: {errors}"
    assert all("SERUM_DUP01a" in e for e in errors)
    assert any("row 2" in e.lower() for e in errors)
    assert any("row 3" in e.lower() for e in errors)

    assert (
        db_session.query(ExperimentalResults)
        .join(Experiment, Experiment.id == ExperimentalResults.experiment_fk)
        .filter(Experiment.experiment_id == "SERUM_DUP01a")
        .count()
    ) == 0


def test_same_vial_different_timepoints_is_fine(db_session: Session):
    """The same vial at two different days is two legitimate rows."""
    _seed_experiment(db_session, "SERUM_DUP02a", 8832)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP02a", 1.0, description="day 1", fl_h2=10.0),
        _v3_row("SERUM_DUP02a", 3.0, description="day 3", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 2


def test_replicate_letters_are_distinct_vials(db_session: Session):
    """SERUM_001a/b/c at one timepoint are three rows, not a duplicate.

    This is the shape the pivot exists to support: three replicate vials, each
    with its own experiment ID, all at day 1.
    """
    for letter, num in (("a", 8841), ("b", 8842), ("c", 8843)):
        _seed_experiment(db_session, f"SERUM_DUP03{letter}", num)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP03a", 1.0, fl_h2=10.0),
        _v3_row("SERUM_DUP03b", 1.0, fl_h2=20.0),
        _v3_row("SERUM_DUP03c", 1.0, fl_h2=30.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert errors == [], f"Unexpected errors: {errors}"
    assert created == 3


def test_duplicate_detected_after_timepoint_token_resolution(db_session: Session):
    """'SERUM_X-t7' with a blank Duration collides with 'SERUM_X' at day 7.

    Duplicate detection runs on the RESOLVED (id, time) pair, not on the raw
    cells — the -t token fills a blank Duration, so these are the same vial-day.
    """
    _seed_experiment(db_session, "SERUM_DUP04-t7", 8851)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP04-t7", None, description="from token", fl_h2=10.0),
        _v3_row("SERUM_DUP04-t7", 7.0, description="explicit", fl_h2=20.0),
    ])
    created, updated, skipped, errors, _ = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 0
    assert len(errors) == 2


def test_duplicate_does_not_block_other_rows(db_session: Session):
    """A duplicate pair is rejected; unrelated rows in the same file still land."""
    _seed_experiment(db_session, "SERUM_DUP05a", 8861)
    _seed_experiment(db_session, "SERUM_DUP05b", 8862)

    xlsx = _master_excel_v3([
        _v3_row("SERUM_DUP05a", 7.0, description="dup one", fl_h2=10.0),
        _v3_row("SERUM_DUP05a", 7.0, description="dup two", fl_h2=20.0),
        _v3_row("SERUM_DUP05b", 7.0, description="fine", fl_h2=30.0),
    ])
    created, updated, skipped, errors, feedbacks = MasterBulkUploadService.from_bytes(
        db_session, xlsx
    )

    assert created == 1
    assert len(errors) == 2
    assert [f["experiment_id"] for f in feedbacks] == ["SERUM_DUP05b"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -k "duplicate or distinct_vials or same_vial_different" -v
```

Expected: `test_duplicate_vial_and_timepoint_is_an_error`, `test_duplicate_detected_after_timepoint_token_resolution` and `test_duplicate_does_not_block_other_rows` FAIL (the second row currently upserts, so `created` is 1 or 2 and `errors` is empty). `test_same_vial_different_timepoints_is_fine` and `test_replicate_letters_are_distinct_vials` PASS already — they pin behavior the new check must not break.

- [ ] **Step 3: Extract identity resolution**

Move the ID-and-time resolution currently inline in the loop into a helper placed after `_resolve_h2`.

**Match on content, not line numbers.** As of commit `575c51e` the block to move runs from `row_num = idx + 2` down to the end of the Duration `else:` branch (the `apply_id_timepoint` try/except) — currently lines 322-380, immediately above `description = str(row.get("Description") or "").strip() or None`. Tasks 1-3 have already shifted this region twice; verify by reading before you cut.

Move it **verbatim**, comments included. The error strings, the skip-vs-error split, and the order of the three checks (blank ID → calibration standard → replicate combination → Duration) are all pinned by existing tests. The only changes are `continue` / `skipped += 1` / `errors.append(...)` becoming return values.

```python
def _resolve_row_identity(
    row: Any, row_num: int
) -> Tuple[Optional[str], Optional[float], Optional[str], bool]:
    """Resolve one Dashboard row to its (experiment_id, timepoint).

    Extracted from the upsert loop so the duplicate pre-pass and the loop share
    one implementation (issue #111). Behavior is unchanged from the inline
    version — same skips, same error strings.

    Returns (experiment_id, time_post_reaction, error_message, skip):
      * skip=True      — intentionally passed over; count toward `skipped`
      * error_message  — per-row error; count toward `errors`
      * both None/False — a good row
    """
    exp_id = str(row.get("Experiment ID") or "").strip()
    if not exp_id:
        return None, None, None, True

    # Skip calibration-standard rows (Issue #39)
    if "standard" in exp_id.lower():
        return None, None, None, True

    # Split the '-t<days>' token once, up front, so both the replicate
    # combination below and the Duration fill further down share a single
    # split (issue #81 I1/M-fix — do not re-split exp_id later).
    stem, id_timepoint = split_timepoint_token(exp_id)

    # Optional replicate column: resolve base + letter to the sibling ID
    # before anything downstream sees exp_id (issue #70 P3). A token ID
    # ("SERUM_001-t7") combined with a real Replicate letter is rejected —
    # the letter must be encoded in the ID itself (e.g. SERUM_001a-t7).
    try:
        combined = combine_replicate_id(
            stem if id_timepoint is not None else exp_id, row.get("Replicate"),
        )
        if id_timepoint is not None and combined != stem:
            raise ValueError(
                "Replicate column cannot be combined with a -t<days> ID token; "
                "encode the letter in the ID itself (e.g. SERUM_001a-t7)."
            )
        if id_timepoint is None:
            exp_id = combined
    except ValueError as exc:
        return exp_id, None, f"Row {row_num} ({exp_id}): {exc}", False

    # Issue #81: '-t<days>' in the experiment ID is canonical for the
    # timepoint — fill a blank Duration from it, error a conflict.
    duration_raw = row.get("Duration (Days)")
    if duration_raw is None or (isinstance(duration_raw, float) and pd.isna(duration_raw)):
        if id_timepoint is None:
            return exp_id, None, None, True
        return exp_id, id_timepoint, None, False

    time_post_reaction = _parse_float(duration_raw)
    if time_post_reaction is None:
        return exp_id, None, f"Row {row_num}: invalid Duration (Days) '{duration_raw}'", False

    try:
        time_post_reaction = apply_id_timepoint(id_timepoint, time_post_reaction)
    except ValueError as exc:
        return exp_id, None, f"Row {row_num} ({exp_id}): {exc}", False

    return exp_id, time_post_reaction, None, False
```

- [ ] **Step 4: Restructure the loop into pre-pass plus upsert pass**

Replace the head of `for idx, row in df.iterrows():` — everything from `row_num = idx + 2` down to and including the Duration block — with a resolved-rows pre-pass placed *before* the loop.

The pre-pass goes **after** the three file-level warning blocks that Task 3 added (`stale_wide_di`, `unmapped_h2`, and the no-recognized-H2 check) and before the row loop. Those blocks stay exactly where they are; do not move or reorder them.

`errors`, `warnings`, `feedbacks`, `created`, `updated` and `skipped` are already in scope — Task 3 bound the first three to the `MasterUploadResult` fields at the top of `_process_bytes`. Keep using them; do not introduce new accumulators.

```python
    # Phase 1 — resolve every row's identity, then find collisions. v3 is one
    # row per unique experiment ID (issue #111): two rows claiming the same
    # vial at the same day are two readings fighting over one timepoint, and
    # letting the later one win would destroy the earlier silently. Both are
    # rejected. A collision is only discoverable once the LATER row has been
    # read, by which point the earlier row has already been flushed, counted
    # and given a feedback record — hence a pre-pass rather than an in-loop
    # check. (The upload commits once, at the endpoint, via _finalize_write.)
    resolved: List[Tuple[int, str, float, Any]] = []
    for idx, row in df.iterrows():
        row_num = idx + 2
        exp_id, time_post_reaction, error, skip = _resolve_row_identity(row, row_num)
        if skip:
            skipped += 1
            continue
        if error is not None:
            errors.append(error)
            continue
        resolved.append((row_num, exp_id, time_post_reaction, row))

    key_counts: Dict[Tuple[str, float], int] = {}
    for _, exp_id, time_post_reaction, _row in resolved:
        key = (exp_id, time_post_reaction)
        key_counts[key] = key_counts.get(key, 0) + 1

    # Phase 2 — upsert what is left.
    for row_num, exp_id, time_post_reaction, row in resolved:
        if key_counts[(exp_id, time_post_reaction)] > 1:
            errors.append(
                f"Row {row_num} ({exp_id}): duplicate experiment ID and timepoint "
                f"(day {time_post_reaction}). Each vial gets one row per timepoint "
                f"— give replicates their own IDs (e.g. {exp_id}a, {exp_id}b). "
                f"No row for this vial-day was written."
            )
            continue
```

The remainder of the original loop body — from `description = str(row.get("Description") ...)` through the `except Exception` handler — is unchanged and now sits inside Phase 2. Delete the now-duplicated `exp_id`/`row_num`/Duration lines from it.

- [ ] **Step 5: Run the tests**

```bash
.venv/Scripts/python.exe -m pytest tests/services/bulk_uploads/test_master_bulk_upload.py -v
```

Expected: all PASS, including every pre-existing test. Pay particular attention to `test_invalid_replicate_is_per_row_error`, `test_master_token_id_with_replicate_letter_errors_row`, `test_master_blank_duration_without_token_still_skipped` and `test_standard_row_skipped_silently` — they pin the exact skip-vs-error split that `_resolve_row_identity` now owns. If any of them fail, the extraction changed behavior; fix the helper, not the test.

- [ ] **Step 6: Lint and commit**

```bash
.venv/Scripts/python.exe -m flake8 --max-line-length=100 backend/services/bulk_uploads/master_bulk_upload.py
git add backend/services/bulk_uploads/master_bulk_upload.py tests/services/bulk_uploads/test_master_bulk_upload.py
git commit -m "$(cat <<'EOF'
[#111] Reject duplicate vial-timepoint rows

- v3 is one row per unique experiment ID
- Pre-pass detects collisions before any row commits
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Prove vial-level IDs roll up into mean and SD

No new statistics code. This task pins the behavior the pivot depends on, so a future change to the view or the ID parser cannot quietly break it.

**Files:**
- Test: `tests/views/test_v_results_scalar_rollup.py` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks — this exercises `v_results_scalar_rollup` directly.
- Produces: nothing code-facing.

- [ ] **Step 1: Write the test**

Append to `tests/views/test_v_results_scalar_rollup.py`, reusing that file's existing `view_db` fixture and `_make_experiment` / `_make_result` / `_make_scalar` helpers:

```python
class TestRollupVialLevelIds:
    """Issue #111: the Dashboard moved to one row per unique experiment ID, so
    replicate spread must come from the rollup rather than from avg/SD columns
    on the sheet.

    ID form matters here. A replicate letter only binds to a NUMERIC index —
    `_REPLICATE_LETTER_RE = r'^(\\d+)([a-z])$'` in
    database/experiment_id_parser.py matches the final underscore-separated
    segment. 'ROLL_910a' parses to base 'ROLL_910' + label 'a', but an
    alphanumeric index like 'ROLL_R10a' does not parse as a replicate at all
    and each vial would become its own base — silently producing n=1 groups and
    a vacuous test.
    """

    def test_three_vials_at_one_timepoint_give_mean_and_sd(self, view_db):
        """ROLL_910a/b/c-t1 aggregate to n=3 with an n-1 SD.

        The -t token is stripped before lineage grouping, so all three land on
        base 'ROLL_910' at bucket 1.0.
        """
        exp_a = _make_experiment(view_db, "ROLL_910a-t1", 9101)
        exp_b = _make_experiment(view_db, "ROLL_910b-t1", 9102)
        exp_c = _make_experiment(view_db, "ROLL_910c-t1", 9103)

        for exp, h2 in ((exp_a, 10.0), (exp_b, 20.0), (exp_c, 30.0)):
            er = _make_result(view_db, exp, bucket_days=1.0)
            _make_scalar(view_db, er, gross_nh4=1.0, h2_ppm=h2)
        view_db.commit()

        row = view_db.execute(
            text("""
                SELECT n_replicates, mean_h2_ppm, sd_h2_ppm
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_910'
                  AND time_post_reaction_bucket_days = 1.0
            """)
        ).fetchone()

        assert row is not None, "vial-level IDs must group under their base"
        mapping = row._mapping
        assert mapping["n_replicates"] == 3
        assert mapping["mean_h2_ppm"] == pytest.approx(20.0)
        assert mapping["sd_h2_ppm"] == pytest.approx(10.0)

    def test_timepoints_stay_in_separate_buckets(self, view_db):
        """3 letters x 2 timepoints is 6 vials but two independent buckets."""
        for letter, num, h2_t1, h2_t3 in (
            ("a", 9111, 10.0, 100.0),
            ("b", 9112, 20.0, 200.0),
            ("c", 9113, 30.0, 300.0),
        ):
            exp_t1 = _make_experiment(view_db, f"ROLL_920{letter}-t1", num)
            _make_scalar(view_db, _make_result(view_db, exp_t1, bucket_days=1.0),
                         gross_nh4=1.0, h2_ppm=h2_t1)
            exp_t3 = _make_experiment(view_db, f"ROLL_920{letter}-t3", num + 100)
            _make_scalar(view_db, _make_result(view_db, exp_t3, bucket_days=3.0),
                         gross_nh4=1.0, h2_ppm=h2_t3)
        view_db.commit()

        rows = view_db.execute(
            text("""
                SELECT time_post_reaction_bucket_days, n_replicates, mean_h2_ppm
                FROM v_results_scalar_rollup
                WHERE base_experiment_id = 'ROLL_920'
                ORDER BY time_post_reaction_bucket_days
            """)
        ).fetchall()

        assert len(rows) == 2, "each timepoint is its own bucket"
        assert rows[0]._mapping["n_replicates"] == 3
        assert rows[0]._mapping["mean_h2_ppm"] == pytest.approx(20.0)
        assert rows[1]._mapping["n_replicates"] == 3
        assert rows[1]._mapping["mean_h2_ppm"] == pytest.approx(200.0)
```

**Replicate letters bind to a numeric index only.** `ROLL_910a` → base `ROLL_910`, label `a`. An alphanumeric index (`ROLL_R10a`) parses to base `ROLL_R10a` with **no** replicate label, so each vial forms its own group, `n_replicates` is 1 per vial, and the rollup query returns no matching row at all. Verified against the live parser before writing this. Every experiment ID in this repo uses a numeric index (`SERUM_001`, `HPHT_139`, `ROLL_001a`), so this is the parser behaving correctly, not a limitation to work around.

- [ ] **Step 2: Run it**

```bash
.venv/Scripts/python.exe -m pytest tests/views/test_v_results_scalar_rollup.py -v
```

Expected: PASS on the first run — this documents existing behavior rather than driving new code.

If `test_three_vials_at_one_timepoint_give_mean_and_sd` returns `None` for the row, **first check the ID form**: a replicate letter binds only to a numeric index, so an alphanumeric index would produce one base per vial and no matching group (this exact defect was caught during execution — the plan originally used `SERUM_R01a`, which does not parse as a replicate). If the IDs are numeric-indexed and the row is still `None`, the `-t` token is not being stripped during lineage grouping: stop and report it, because that would mean the pivot does not aggregate and the whole approach needs revisiting. Either way, do **not** paper over it by rewriting the test to use letterless IDs — that hides the thing the test exists to detect.

- [ ] **Step 3: Commit**

```bash
git add tests/views/test_v_results_scalar_rollup.py
git commit -m "$(cat <<'EOF'
[#111] Pin rollup stats for vial-level IDs

- Replicate mean/SD now come from the view, not the sheet
- Tests added: yes
- Docs updated: no

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Verify against the real v3 workbook

Tests use synthetic Excel. This runs the actual v3 file through the parser.

**Files:** none committed — a throwaway script under the session scratchpad.

**Interfaces:**
- Consumes: `MasterBulkUploadService.from_bytes_ex` from Task 3.
- Produces: numbers for the Task 7 issue-log entry.

- [ ] **Step 1: Record the row count before**

```bash
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); from database.database import SessionLocal; from database.models.results import ScalarResults; db=SessionLocal(); print('scalar rows:', db.query(ScalarResults).count()); db.close()"
```

- [ ] **Step 2: Parse the real workbook in a rolled-back session**

```python
# scratchpad/verify_111.py
import sys
sys.path.insert(0, ".")
from database.database import SessionLocal
from backend.services.bulk_uploads.master_bulk_upload import MasterBulkUploadService

path = ("C:/Users/MathewHearl/OneDrive - Addis Energy/Documents/01_Software/"
        "database_sandbox/experiment_tracking_sandbox/docs/sample_data/"
        "Master_Results_Tracker_v3.xlsx")

db = SessionLocal()
try:
    with open(path, "rb") as fh:
        out = MasterBulkUploadService.from_bytes_ex(db, fh.read())
    print("created", out.created, "updated", out.updated, "skipped", out.skipped)
    print("errors", len(out.errors), out.errors[:5])
    print("warnings", len(out.warnings), out.warnings[:5])
    srcs = {}
    for f in out.feedbacks:
        srcs[f.get("h2_source")] = srcs.get(f.get("h2_source"), 0) + 1
    print("h2_source counts:", srcs)
    dupes = [e for e in out.errors if "duplicate experiment ID" in e]
    print("duplicate-row errors:", len(dupes), dupes[:5])
finally:
    db.rollback()
    db.close()
```

- [ ] **Step 3: Interpret the output honestly**

Expected from the header survey: `warnings` empty (every H2 column in v3 is recognized) and **`h2_source` counts of `{None: N}`** — both GC columns are empty in the current v3 file while the sheet is being repopulated. That is the sheet's state, not a parser failure. Do not adjust the parser to make hydrogen appear.

The number that matters here is **duplicate-row errors**. If v3 still contains rows sharing an ID and duration, report the count and the first few to the user before proceeding — it means the sheet has not finished migrating to one-row-per-vial and a real upload would reject those rows.

- [ ] **Step 4: Confirm the rollback left nothing behind**

Re-run Step 1's count and confirm it is unchanged. If it moved, `create_scalar_result_ex`'s per-row commits outran the outer rollback — report that to the user before going further; do not attempt a cleanup delete.

- [ ] **Step 5: No commit** — this task produces no tracked files.

---

### Task 7: Documentation

**Files:**
- Modify: `backend/services/bulk_uploads/master_bulk_upload.py:1-9` (module docstring)
- Modify: `docs/CALCULATIONS.md` (Hydrogen Amount section, ~line 112)
- Modify: `.claude/rules/MODELS.md` (`ScalarResults` → Hydrogen bullet)
- Modify: `docs/user_guide/BULK_UPLOADS.md` (§1 Master Results Sync)
- Modify: `docs/working/issue-log.md` (append)

**Interfaces:**
- Consumes: the behavior built in Tasks 1-4 and the counts measured in Task 6.
- Produces: nothing code-facing.

- [ ] **Step 1: Update the module docstring**

Replace lines 1-9 of `master_bulk_upload.py`:

```python
"""
Master Results bulk upload — reads from fixed SharePoint path or uploaded bytes.

Dashboard sheet column spec (v3, issue #111, 2026-07-30):
  Experiment ID | Description | Sample Date | Duration (Days) | NH4 (mM) |
  FL H2 (ppm)   | FL Gas Volume (mL) | FL Gas Pressure (psi) | Sample pH |
  Sample Conductivity (mS/cm) | Modification | NMR Run Date |
  Sampled Solution Volume (mL) | ICP Run Date | GC Run Date | XRD Run Date |
  OVERWRITE | DI H2 (ppm) | DI gas volume (mL) | DI gas pressure (psi)

One row per unique experiment ID. Replicate letters are separate vials, so
SERUM_001a/b/c at days 1 and 3 is six rows (SERUM_001a-t1, SERUM_001b-t1, ...),
not two rows with per-letter columns. Two rows sharing an ID and timepoint are
both rejected. Cross-replicate mean and SD are computed by
v_results_scalar_rollup, not carried on the sheet.

Hydrogen: Full Loop wins; 'DI H2 (ppm)' is used only when the Full Loop cell is
blank, and gas volume/pressure come from the same block. A value of 0 is a real
reading, not a blank.

Older spellings are still accepted — the pre-rename 'H2 (ppm)', 'Gas Volume
(mL)', 'Gas Pressure (psi)', 'Overwrite', and v2's 'DI avg H2 (ppm)'. v2's wide
'DI a/b/c H2 (ppm)' and 'DI SD (ppm)' are ignored with a warning. See
_HEADER_ALIASES.
"""
```

- [ ] **Step 1b: Correct a factually wrong code comment**

`backend/services/bulk_uploads/master_bulk_upload.py`, in the Phase 1 comment above `resolved: List[...]`, currently ends with:

```python
    # rejected, so this has to happen before any row is committed —
    # create_scalar_result_ex commits per row.
```

That claim is **false** and was inherited from an earlier draft of this plan. `create_scalar_result_ex` flushes (`backend/services/scalar_results_service.py:209`); it never commits. The upload commits once, at the endpoint, via `_finalize_write` (`backend/api/routers/bulk_uploads.py:28-37`). Per-row commits are a property of `delete_experiment_cascade` on the bulk-deletion path (issue #109), not this one. Replace those two lines with:

```python
    # rejected. A collision is only discoverable once the LATER row has been
    # read, by which point the earlier row has already been flushed, counted
    # and given a feedback record — hence a pre-pass rather than an in-loop
    # check. (The upload commits once, at the endpoint, via _finalize_write.)
```

Leave the rest of that comment block and all surrounding code untouched. This is a comment-only edit: no test should change behavior, but re-run `tests/services/bulk_uploads/` afterwards to confirm nothing was disturbed.

Do **not** repeat the per-row-commit claim in any documentation you write in the steps below.

- [ ] **Step 2: Update `docs/CALCULATIONS.md`**

In the "Hydrogen Amount (PV = nRT ...)" section, after the inputs list, add:

```markdown
**Where the inputs come from on a Master Results upload (issue #111):** all
three inputs are read from a single GC block. Full Loop (`FL H2 (ppm)`,
`FL Gas Volume (mL)`, `FL Gas Pressure (psi)`) takes precedence; direct
injection (`DI H2 (ppm)`, `DI gas volume (mL)`, `DI gas pressure (psi)`) is
used only when the Full Loop concentration cell is blank. The blocks are never
mixed — pairing a Full Loop concentration with a DI sampling volume would
compute micromoles for an injection that never happened. A concentration of `0`
is a real measurement and is stored as such.

**Replicate spread is not calculated here.** Mean and standard deviation across
replicate vials come from `v_results_scalar_rollup` (`mean_h2_ppm`,
`sd_h2_ppm`, `stddev_samp`, n-1, outlier vials excluded), served by
`GET /api/experiments/groups/{base_id}/rollup`. The Dashboard sheet no longer
carries avg/SD columns — each vial supplies one reading and the view aggregates.
```

- [ ] **Step 3: Update `.claude/rules/MODELS.md`**

In `ScalarResults` → **Hydrogen (H2)**, after the "Inputs:" line, add:

```markdown
  - **GC source precedence (issue #111):** `h2_concentration` holds a single ppm
    value and there is no stored notion of which GC method produced it. On a
    Master Results upload the parser picks Full Loop over direct injection and
    writes only the winner; the discarded DI reading is reported in the upload's
    per-row feedback (`h2_source`, `h2_di_superseded`) and is not persisted.
    Making that a stored provenance field would be an additive `ScalarResults`
    column and a schema-checklist run.
  - **One row per vial (issue #111):** the v3 Dashboard carries one row per
    unique `experiment_id`; replicate letters are separate vials with their own
    IDs, not columns. The upload rejects two rows sharing an ID and timepoint.
    Cross-replicate mean/SD therefore come from `v_results_scalar_rollup`
    (`mean_h2_ppm` / `sd_h2_ppm`), not from the spreadsheet.
```

- [ ] **Step 4: Update `docs/user_guide/BULK_UPLOADS.md`**

In §1 Master Results Sync, after the file path line, add:

```markdown
**One row per vial.** Each unique experiment ID gets its own row. Replicates are
separate vials, so `SERUM_001` with replicates a, b, c sampled at days 1 and 3
is six rows — `SERUM_001a-t1`, `SERUM_001b-t1`, `SERUM_001c-t1`, `SERUM_001a-t3`,
`SERUM_001b-t3`, `SERUM_001c-t3` — not two rows with an a/b/c column each. If two
rows share an experiment ID and Duration, **both are rejected** and listed under
Errors, because there is no safe way to tell which reading you meant to keep.

You no longer put averages or standard deviations on the sheet. Enter each
vial's own reading; the app computes the replicate mean and SD and shows them on
the experiment group page.

**Hydrogen columns.** `FL H2 (ppm)` (Full Loop) is used whenever it has a value;
`DI H2 (ppm)` is used only when the Full Loop cell is blank. Gas volume and
pressure are taken from whichever block supplied the concentration, so do not
mix them by hand. A `0` is treated as a real reading of zero — leave the cell
**empty** if there was no measurement.

If you rename a Dashboard column, the upload now tells you: any unmatched column
whose name mentions H2 appears under **Warnings** in the result panel rather
than being ignored.
```

- [ ] **Step 5: Verify the doc-sync hook fired**

```bash
git status --porcelain docs/project_context/
```

Expected: `docs/project_context/CALCULATIONS.md` and `docs/project_context/BULK_UPLOADS.md` show as modified. The `PostToolUse` hook copies them automatically — do **not** write to `docs/project_context/` by hand. `.claude/rules/MODELS.md` is not synced by the hook.

- [ ] **Step 6: Append the issue-log entry**

Add to `docs/working/issue-log.md`, matching the existing entry format (`## 2026-07-30 | issue #111 — ...`), covering: the four renamed columns and that the loss was wider than the issue's H2-only framing; the v2→v3 collapse of the wide DI block and the one-row-per-vial pivot; the FL > DI rule; that `0` is real per the user's formula rewrite; the duplicate-row rejection and why it needs a pre-pass; that mean/SD were **not** built because `v_results_scalar_rollup` already provides them; the `from_bytes_ex` wrapper choice; that no schema changed; Task 6's measured counts; and what was and was not run.

- [ ] **Step 7: Commit**

```bash
git add backend/services/bulk_uploads/master_bulk_upload.py docs/ .claude/rules/MODELS.md
git commit -m "$(cat <<'EOF'
[#111] Document v3 one-row-per-vial GC ingestion

- Tests added: no
- Docs updated: yes

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Final verification

- [ ] Full backend suite:

```bash
.venv/Scripts/python.exe -m pytest -q
```

Expected: pass, **except** the documented pre-existing failures — 3 in `tests/test_pg_backup_restore.py` and 4 errors in `tests/test_fresh_install_migration.py` (the latter is a worktree artifact: it shells out to a hardcoded relative `.venv\Scripts\alembic.exe`). That baseline is known to be **unstable, not a fixed 3** — `tests/test_pxrf_analysis.py::test_create_pxrf_reading` also fails intermittently from shared-database `drop_all()` interleaving. If you see a failure outside those files, it is yours: investigate before claiming completion.

- [ ] No frontend change was needed — confirm `git status --porcelain frontend/` returns nothing.
- [ ] `database/models/` untouched — `git diff --stat develop -- database/models/` returns nothing.
- [ ] No new calculation code — `git diff --stat develop -- backend/services/calculations/ database/event_listeners.py` returns nothing.

## Open items deliberately not in this plan

- **The archived sync path.** `settings.master_results_path` still probes `…/02_Results/Master Reactor Sampling Tracker.xlsx`, which was moved to `99_Archive/` on 2026-07-30, and no `master_results_path` row exists in `AppConfig`. `sync_from_path()` therefore returns "file not found". The user directed that uploads happen by drag-and-drop, so this is out of scope — but `sync_from_path` remains dead in a way no test would catch. Worth a separate issue.
- **Persisting DI as data.** Decided against (user, 2026-07-30). If provenance is wanted later it is an additive `ScalarResults` column plus a schema-checklist run.
- **Retrofitting existing wide-format data.** Rows already in the database that came from v2's `DI avg`/`a`/`b`/`c` columns are not migrated or re-attributed. Nothing in this plan rewrites history.
- **The other three ingestion paths** (`scalar_results.py`, `metric_groups.py`, `long_format.py`) still assume one H2 column. They use their own templates rather than the Dashboard sheet, so the v3 restructure does not affect them; no change is needed unless those templates gain FL/DI columns too.
- **The `Replicate` column** is retained as an optional alias even though v3 dropped it, because older workbooks and `tests/services/bulk_uploads/test_master_bulk_upload.py` still exercise it. It resolves before duplicate detection, so a letter supplied that way still yields a distinct vial key.
