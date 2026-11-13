# Backend sweep findings: issue #167 Phase 1

**Date:** 2026-11-11 · **Branch:** `chore/issue-167-backend-sweep-findings` (cut from `develop` @ 036c31f)
**Scope:** `backend/` (`api/`, `services/` incl. `calculations/` and `bulk_uploads/`, `config/`, `auth/`): 84 tracked `.py` files, 21,084 lines.
**Method:** Four read-only auditors covered (1) API routers/schemas/config/auth, (2) the calculation engine and its callers, (3) bulk-upload parsers plus their router, and (4) the other services. The controller then re-checked the highest-risk claims against the code. Each finding is marked **Verified** (the controller re-read the code or ran the grep) or **Reported** (one auditor's reading, not independently re-checked). No code was changed. The only test run was the Notion check below.
**Model note:** the issue asks for Fable. Mat chose to run this phase on Opus 5.5 (2026-11-11).

## How to read this

- **Reference labels:** **LIVE** means reached from `backend/`, `database/`, `scripts/`, `alembic/` or live `frontend/src` code. **TEST** means referenced only under `tests/` or a frontend `__tests__` file. **LEGACY** means `legacy/`, `.worktrees/` (empty today), `docs/`, `__pycache__/` or `Claude outputs/`. LEGACY references do not count as live.
- **Staleness rule:** no LIVE refs **and** unchanged for ≥ 60 days, where the cutoff is **2026-09-12**. The rule is applied at **block level** (newest `git blame` date of the dead lines), with the file-level `git log -1` date shown alongside. The reason: several dead blocks sit in files with recent unrelated edits; `dashboard.py` was last touched 2026-11-10, but the `reactor-status` lines were last touched 2026-07-30. If you want strict file-level application, every item where the two dates straddle the cutoff moves to **Needs human call**.
- **Derived-column path:** "yes" means the code writes or feeds a stored derived column (`water_to_rock_ratio`, `total_ferrous_iron_g`, scalar `h2_*` and yield fields, `ChemicalAdditive` calc fields, `cumulative_time_post_reaction_days`). Phase 2 PRs touching these must pass the derived-column diff.
- **Approval:** tick `[x]` to approve for Phase 2. Locked items (their own section) also need explicit per-item sign-off **in conversation**. Ticking the box is not enough.

## Notion residue check

**Clean.** `grep -rniI notion backend requirements*.txt .env.example` returns no matches. `.venv/Scripts/python -m pytest tests/api/test_notion_removed.py -q` reports **5 passed** (2026-11-11).

## Seed items from the issue

| Seed item | Outcome |
|---|---|
| `backend/api/routes.py` and `backend/services/database/__init__.py` empty and unimported | **Confirmed.** Both 0 bytes; no import anywhere. See S-01, S-02. |
| `GET /api/dashboard/reactor-status` is legacy | **Confirmed.** The wrapper has no live caller; only tests and a frontend test mock reference it. Its comment points to `/api/dashboard/reactor-cards`, which does not exist. See S-05. The sibling `GET /api/dashboard/timeline/{id}` is also dead (S-06). |
| `experiment_additives.py` has no route | **Confirmed.** LEGACY and TEST refs only. Locked, see L-S1. |
| `legacy/streamlit_frontend/` imports `backend` | **Confirmed.** It is the only caller of S-04, S-09 and L-S1/L-S2/L-S6/L-S8. Its imports also pin ICP's 2-tuple arity (LOCKED_COMPONENTS footnote 3(d)). Retiring `legacy/` would unlock several locked deletions in one move (see Needs human call H-01). |
| Registry called from 14 files / 72 sites | **Ruled out as stated.** The true count is **30 LIVE call sites in 16 files**, **46 TEST in 6 files**, **0 LEGACY**. A plain `git grep -c "recalculate("` gives 53 lines in 22 files because it includes comments and docstrings. |
| Caller recalculates conditions then scalars again | **Confirmed once on a live path:** `PATCH /api/experiments/{id}` with a sample change (E-08). Migration 012 does the same thing harmlessly (no action). The additive path computes three times, but those explicit calls are **load-bearing** (H-06). |
| `_parse_float` helper vs inline parsing | **Confirmed, but do not unify.** The roughly 13 parsing variants differ in meaningful ways (zero-as-blank, LOD-as-0, `<0.5`→0.5). Inventory in L-D2. The inventory surfaced three real NaN bugs (X-01 to X-03). |

---

## Stale (S)

### S-01: `backend/api/routes.py` is an empty file · **Verified**
- **Evidence:** `backend/api/routes.py`, 0 bytes. Only commit: b69b24f (M0).
- **Inbound refs:** none (LIVE 0 / TEST 0 / LEGACY 0).
- **Last change:** 2026-03-16 · **Locked:** no · **Derived path:** no
- **Action:** delete. **Risk:** low. **Proof:** `python -c "import backend.api.main"`; `git grep "api.routes"` is empty.
- [x] Approved — shipped in PR #193 (issue #189)

### S-02: `backend/services/database/` package holds only an empty `__init__.py` · **Verified**
- **Evidence:** `backend/services/database/__init__.py`, 0 bytes; the directory has no other file.
- **Inbound refs:** none for `services.database` / `services/database` anywhere, docs included.
- **Last change:** 2026-03-16 · **Locked:** no · **Derived path:** no
- **Action:** delete the package. **Risk:** low. **Proof:** `python -c "import backend.services"`, plus the six-dir pytest.
- [x] Approved — shipped in PR #193 (issue #189)

### S-03: `backend/api/schemas/__init__.py` re-exports nothing anyone imports · Reported
- **Evidence:** `backend/api/schemas/__init__.py:1-13` re-exports schema classes (including `ReactorStatusResponse`, S-05). No `from backend.api.schemas import …` or `import backend.api.schemas` exists in `backend`, `database`, `scripts`, `tests`, `alembic` or `app.py`. Its only effect is to import every schema module whenever any one is imported.
- **Inbound refs:** none.
- **Last change:** 2026-03-16 · **Locked:** no · **Derived path:** no
- **Action:** empty the file (keep it as a package marker). **Risk:** low. **Proof:** the app and the test collection import cleanly.
- [x] Approved — shipped in PR #193 (issue #189)

### S-04: `ExperimentalConditionsService` is broken and only legacy calls it · **Verified**
- **Evidence:** `backend/services/experimental_conditions_service.py:46,96` call `conditions.calculate_derived_conditions()`, `:102` calls `additive.calculate_derived_values()` and `:109` calls `scalar_data.calculate_yields()`. None of these methods exists anywhere (`git grep "def calculate_yields\|def calculate_derived"` is empty), so create and update raise `AttributeError`. `calculate_water_to_rock_ratio` (`:56`) has no callers and returns `0.0` where the engine returns `None`.
- **Inbound refs:** LEGACY `legacy/streamlit_frontend/edit_experiment.py:11,249,261`, `legacy/streamlit_frontend/new_experiment.py:8,382`; a docstring mention in `database/event_listeners.py:1221`; prose in `database/data_migrations/README.md`.
- **Last change:** 2026-03-16 · **Locked:** no · **Derived path:** nominally yes, but the code cannot run.
- **Action:** delete the module and drop the docstring mention. **Risk:** none for the app; this breaks a legacy Streamlit import that is already broken at runtime. **Proof:** `git grep ExperimentalConditionsService` shows only `legacy/` and docs.
- [x] Approved — shipped in PR #193 (issue #189)

### S-05: `GET /api/dashboard/reactor-status` and `ReactorStatusResponse` · **Verified**
- **Evidence:** `backend/api/routers/dashboard.py:373-425`; schema `backend/api/schemas/dashboard.py:8-9` ("Legacy response — kept for backwards-compat"). The comment at `dashboard.py:393` cites `/api/dashboard/reactor-cards`, which does not exist.
- **Inbound refs:**
  - TEST: `tests/api/test_dashboard.py:812-848, :1482-1509`; `frontend/src/pages/__tests__/Dashboard.test.tsx:14` (mock key).
  - The wrapper `dashboardApi.reactorStatus` (`frontend/src/api/dashboard.ts:113-115`) has 0 live callers.
  - No `scripts/` caller.
  - Power BI: **not checkable from the repo.** Mat to confirm.
- **Last change:** block 2026-07-30; file 2026-11-10 · **Locked:** no · **Derived path:** no
- **Action:** remove the endpoint, schema, re-export (S-03) and both tests. The wrapper and the `ReactorStatus` TS interface go in the frontend sweep. **Risk:** low. **Proof:** assert absence via the FastAPI route registry, not HTTP 404 (the SPA catch-all serves 200).
- [x] Approved — shipped in PR #193 (issue #189)

### S-06: `GET /api/dashboard/timeline/{experiment_id}` and its two schemas · **Verified** (no live caller)
- **Evidence:** `backend/api/routers/dashboard.py:428-474`; `ExperimentTimelineResponse`, `TimelinePoint` (`backend/api/schemas/dashboard.py:19, :28`).
- **Inbound refs:**
  - The wrapper `dashboardApi.timeline` (`frontend/src/api/dashboard.ts:117-118`) has 0 live callers. It is mis-typed as `TimelineEntry[]`; the endpoint returns one object.
  - TEST: the `Dashboard.test.tsx:14` mock only.
  - **No pytest exercises it.** The "timeline" hits in `test_dashboard.py:290-308` are the `timeline` key of `GET /api/dashboard/`.
  - No `scripts/` caller.
- **Last change:** block 2026-03-16; file 2026-11-10 · **Locked:** no · **Derived path:** no
- **Action:** remove the endpoint and schemas (wrapper goes in the frontend sweep). **Risk:** low. **Proof:** route-registry assertion; Power BI check.
- [x] Approved — shipped in PR #193 (issue #189)

### S-07: `GET`/`POST /api/chemicals/additives/{conditions_id}` · **Verified** (no live caller)
- **Evidence:** `backend/api/routers/chemicals.py:113-146`. The POST calls `recalculate(additive)` but, unlike every other additive write path, writes **no `ModificationsLog` row**. It is a third copy of additive-write logic (D-07).
- **Inbound refs:**
  - The wrappers `chemicalsApi.listAdditives` / `addAdditive` (`frontend/src/api/chemicals.ts:73, :77`) have 0 callers.
  - No pytest uses either path.
  - No `scripts/` caller.
- **Last change:** file 2026-03-24 · **Locked:** no · **Derived path:** **yes** (POST writes the additive calc fields).
- **Action:** remove both endpoints (wrappers go in the frontend sweep). **Risk:** low–med (endpoint removal; Power BI and external scripts must be ruled out). **Proof:** route-registry assertion; grep `chemicals/additives` in `scripts/`, `frontend/src`, `tests/`.
- [x] Approved — shipped in PR #193 (issue #189)

### S-08: `ScalarResultsService.update_scalar_result` and `validate_required_fields` · Reported
- **Evidence:** `backend/services/scalar_results_service.py:471` (`update_scalar_result`, contains a registry call at `:495`) and `:501` (`validate_required_fields`).
- **Inbound refs:** none for either. Related TEST-only methods in the same class are listed for visibility and **not proposed** for removal: `bulk_create_scalar_results` (`:273`, `tests/test_icp_handling.py`) and `get_scalar_results_for_experiment` (`:435`, `tests/…/test_scalar_results_ambiguity.py:60`).
- **Last change:** block 2026-03-19; file 2026-11-09 · **Locked:** no · **Derived path:** dead code only.
- **Action:** delete the two zero-caller methods. **Risk:** low. **Proof:** `git grep` for both names is empty outside the definition.
- [x] Approved — shipped in PR #193 (issue #189)

### S-09: `experiment_validation.format_validation_warning` and the unused re-exports · Reported
- **Evidence:** `backend/services/experiment_validation.py:264` (`format_validation_warning`). The `__all__` entries `EXPERIMENT_TYPE_ABBREVIATIONS`, `ParsedExperimentID` and `get_experiment_type_from_id` (`:33-35`, imported at `:24-30` only to re-export) are never imported from this module; live callers import them from `database.experiment_id_parser`. `validate_experiment_id` is LIVE (the locked `new_experiments.py:32,485`) and stays.
- **Inbound refs:** LEGACY `legacy/streamlit_frontend/new_experiment.py:12,129` for `format_validation_warning`; none for the re-exports from this module.
- **Last change:** file 2026-07-24 · **Locked:** no (but keep `new_experiments.py`'s imports intact) · **Derived path:** no
- **Action:** delete the function, trim `__all__` and the re-export imports. **Risk:** low. **Proof:** grep each name outside `legacy/`.
- [x] Approved — shipped in PR #193 (issue #189)

### S-10: Unused and redundant imports in `routers/samples.py` · Reported
- **Evidence:** `backend/api/routers/samples.py:3` `import os` is unused. Module-level symbols are re-imported inside functions: `ExternalAnalysis as EA` / `selectinload as sl` at `:489-490, :547-548, :568-569`, and `PXRFReading` at `:166, :248`.
- **Inbound refs:** n/a · **Last change:** file 2026-04-24 · **Locked:** no · **Derived path:** no
- **Action:** remove. **Risk:** low. **Proof:** `.venv` flake8 is clean; tests/api samples tests pass.
- [x] Approved — shipped in PR #193 (issue #189)

### S-11: Stale comments and docstrings (no behaviour change) · Reported
- **Evidence:**
  - `backend/services/run_service.py:70` refers to `_conditions_for`, removed in b62b96d. The rule now lives at `result_entry_service.py:133`.
  - `backend/services/replicate_groups.py:6-8` says `/replicate-group` delegates to `resolve_group`; `routers/experiments.py:1003-1010` says it deliberately does not.
  - `backend/services/samples.py:105,112` say "will fail before Task 3 migration"; the column has long existed.
  - `backend/services/calculations/registry.py:28` says "after every DB commit"; callers actually run it after flush and before commit.
  - The trigger-list line refs in `docs/CALCULATIONS.md` are stale (conditions.py 103/125 → 115/142; experiments.py 1329 → 1689; lineage_utils.py 603 → 606). The same stale refs appear in a comment in the locked `new_experiments.py:185-187`, which is listed under L-misc rather than changed here.
- **Last change:** various · **Locked:** no (except the comment noted) · **Derived path:** no
- **Action:** correct the text. **Risk:** nil.
- [x] Approved — shipped in PR #193 (issue #189)

---

## Duplicated (D)

### D-01: "Experiment by string ID, else 404" is written out about 26 times · Reported
- **Evidence:**
  - `select(Experiment).where(Experiment.experiment_id == …).scalar_one_or_none()` plus a 404 appears in `backend/api/routers/experiments.py` at `:816, 985, 1014, 1082, 1138, 1177, 1241, 1296, 1393, 1515, 1748, 1771, 1800, 1871, 1963`, plus `dashboard.py:435` and `results.py:64`.
  - The same exact-match lookup (without the 404) appears in `services/icp_series.py:67-69`, `h2_background.py:78-80`, `experiment_export.py:310-312`, `run_service.py:51-54`, `conditions.py`, `result_entry_service.py`.
  - `base_experiment_id or experiment_id` is open-coded at `experiment_export.py:272,323`, `icp_series.py:72`, `result_merge_utils.py:279` and `routers/experiments.py:324,990,1019`, although `h2_background.group_key` (`:25-26`) exists.
  - These are all exact-match API lookups. None re-implements `_id_match`.
- **Exceptions to preserve:** `list_experiment_additives` (`experiments.py:1141`) returns `[]` instead of a 404; `upsert_experiment_additive` uses the detail text "Experiment conditions not found".
- **Locked:** no · **Derived path:** it sits in front of derived writes without changing them.
- **Action:** `get_experiment_or_404(db, id)` in a router helper module, and `series_key(exp)` in services. **Risk:** low. **Proof:** tests/api experiments, additives, notes, dashboard, results.
- [ ] Approved

### D-02: "Conditions for an experiment, lowest id wins" is done several ways · Reported
- **Evidence:**
  - `routers/experiments.py:82-86` (inside the list loop), `:1149, :1185, :1248, :1400, :1683`; `conditions.py:251` via a join.
  - Services use three idioms for the same lowest-id rule: an ordered loop with a `seen` set (`run_service.load_segments`), a dict filled in descending order (`experiment_export._load_members`), and `.first()` (`experiment_deletion.py:249-253`, `denormalized_ids.py`).
  - `elemental_composition_service.py:50-64` uses `.first()` **without** `order_by` (see E-06).
- **Locked:** no · **Derived path:** **yes**. `experiments.py:1683` feeds `recalculate(cond)`.
- **Action:** one `lowest_conditions(db, exp_fk)` helper (keep `.first()` semantics per #109). **Risk:** low. **Proof:** tests/api plus a derived-column diff, because `:1683` is a write path. Contract entry in `decisions.md`.
- [ ] Approved

### D-03: `next-id` and `next-ids` duplicate the suffix parse and disagree on the Autoclave prefix · **Verified**
- **Evidence:** `routers/experiments.py:386-400` and `:404-428` use the same max-suffix loop. `_TYPE_PREFIX` (`:58-63`) maps `"Autoclave"` to `"AUTOCLAVE"`; `next-ids` (`:414`) uses `"Autoclave"`. `LIKE` is case-sensitive on Postgres, so the two endpoints can disagree. The finding is also a correctness issue (X-09).
- **Inbound refs:** LIVE (`experimentsApi.nextId`, `bulkUploadsApi.getNextIds`).
- **Last change:** file 2026-11-08 · **Locked:** no · **Derived path:** no
- **Action:** one helper, after Mat decides the canonical prefix (H-04). **Risk:** med. **Proof:** dev-DB counts of `LIKE 'AUTOCLAVE\_%'` vs `LIKE 'Autoclave\_%'`.
- [ ] Approved

### D-04: The experiments list re-implements `v_experiment_additives_summary` · Reported
- **Evidence:** the raw `string_agg` at `routers/experiments.py:89-99` matches the view in `database/event_listeners.py:222-232`, which `services/replicate_groups.py:229` already reads.
- **Locked:** no · **Derived path:** no (read only)
- **Action:** read the view, batched per page (pairs with E-01). **Risk:** low. **Proof:** list-endpoint JSON diff on dev.
- [ ] Approved

### D-05: The "scalars for an experiment" two-step query is written three times · Reported
- **Evidence:** `routers/experiments.py:1302-1308`, `:1694-1699`; `services/experiment_deletion.py:171`. Each selects result ids, then `ScalarResults.result_id.in_(…)`.
- **Locked:** no · **Derived path:** **yes**. Both router copies drive `recalculate(scalar)` loops.
- **Action:** one helper (a join saves a round trip). **Risk:** low. **Proof:** derived-column diff.
- [ ] Approved

### D-06: Note-scope rules (mirrors of `ck_note_scope`) are written three times · Reported
- **Evidence:** `add_note` (`routers/experiments.py:1807-1821`), `patch_note` (`:1892-1906`) and `_check_bulk_retype` (`:671-711`). The 422 messages differ slightly between them.
- **Locked:** no · **Derived path:** no
- **Action:** one validator in `services/notes.py`. **Risk:** med (tests may pin exact 422 text). **Proof:** tests/api notes tests.
- [ ] Approved

### D-07: Additive write/delete logic exists three times, and `modified_by` is inconsistent · Reported
- **Evidence:**
  - `PUT`/`DELETE /api/experiments/{id}/additives/{cid}` (`routers/experiments.py:1164-1281`), `PATCH`/`DELETE /api/additives/{pk}` (`routers/additives.py:21-133`) and `POST /api/chemicals/additives/{cid}` (S-07).
  - The two deletes build the same `old_vals` snapshot (`experiments.py:1263-1268`, `additives.py:111-116`).
  - `experiments.py` writes `modified_by=current_user.uid` (`:1221, :1273`, and `update_experiment` `:1535-1706`); `additives.py` writes `.email` (`:82, :125`).
- **Locked:** no · **Derived path:** **yes** (additive calc fields).
- **Action:** one additive service. The `uid` vs `email` choice is H-05. **Risk:** med. **Proof:** derived-column diff; tests/api additives.
- [ ] Approved

### D-08: Hand-built serialization of `ModificationsLog` rows and notes, and three JSON-safe helpers · Reported
- **Evidence:**
  - `routers/experiments.py:1431-1442` and `routers/samples.py:616-626` build the same modification dict.
  - `routers/experiments.py:1417-1430` builds note dicts by hand instead of `NoteResponse`; `ExperimentDetailResponse` types notes and modifications as `list[dict]` (`schemas/experiments.py:121-122`).
  - The JSON-safe value helpers for `ModificationsLog` differ: `_primitive` (`experiment_deletion.py:206-214`: enum, date and datetime, else str), `_jsonable` (`result_entry_service.py:137`: datetime only) and `_serialize` (`scalar_results_service.py:226`: anything with isoformat).
- **Locked:** no · **Derived path:** no
- **Action:** a typed `ModificationResponse`, reuse `NoteResponse`, and one `audit_jsonable()` helper. **Risk:** low–med (`NoteResponse` adds `experiment_id` to the payload). **Proof:** tests/api detail tests; frontend type-check.
- [ ] Approved

### D-09: `_ResultEntryFields` and `_CoreFloodSampleFields` share eight fields and a validator · Reported
- **Evidence:** `schemas/results.py:155-172` and `schemas/core_floods.py:83-100` share the same eight fields (`gc_run_date` … `final_conductivity_mS_cm`) plus `result_note`. The `_omittable_not_nullable` validators are duplicated (`results.py:187-194`, `core_floods.py:115-122`).
- **Locked:** no · **Derived path:** indirectly (these fields feed the scalar H2 and yield calcs).
- **Action:** a common base class; `extra="forbid"` must carry over. **Risk:** low–med. **Proof:** tests/api results and core_floods; OpenAPI schema diff.
- [ ] Approved

### D-10: Three near-identical exception-to-HTTP helpers · Reported
- **Evidence:** `_run_result_entry` (`routers/experiments.py:903-910`), `_translate` (`routers/core_floods.py:20-26`), `_translate` (`routers/hpht.py:23-28`).
- **Locked:** no · **Derived path:** no
- **Action:** optional. **Risk:** low. Low value; listed for completeness.
- [ ] Approved

### D-11: Experiment-type `.value` normalization is copied within `dashboard.py` · Reported
- **Evidence:** `routers/dashboard.py:142-147` and `:314-319`. Related: X-08 (the Serum literal in the same file).
- **Locked:** no · **Derived path:** no
- **Action:** one helper (consider `normalize_experiment_type`). **Risk:** low.
- [ ] Approved

### D-12: Bulk-upload router: 14 copies of the failure-response block · Reported
- **Evidence:** `except Exception: db.rollback(); log.error(…); return UploadResponse(created=0, updated=0, skipped=0, errors=[str(exc)], message="Upload failed")` at `backend/api/routers/bulk_uploads.py:160, 198, 345, 376, 409, 477, 513, 543, 571, 599, 632, 677, 719, 750`, plus a variant at `:822`.
- **Preserve:** the plan-gate, experiment-status validation-failed and ICP parse-failed early returns keep their extra fields. Footnote 3(e) requires ICP to pass `warnings=`.
- **Locked:** no (the router is not a parser) · **Derived path:** no
- **Action:** a `_failed(db, event, exc)` helper. **Risk:** low. **Proof:** `tests/api/test_bulk_uploads*.py`.
- [ ] Approved

### D-13: Bulk-upload router template building · Reported
- **Evidence:** `_simple_template` (`bulk_uploads.py:466`) exists, but its fill/font/width loop is re-coded in the new-experiments (`:924-937`), rock-inventory (`:1101-1114`) and experiment-status (`:1201-1215`) branches. The INSTRUCTIONS-sheet writer is repeated at `:1021-1078, :1119-1162, :1219-1247`. (Locked parser-side copies: L-D9.)
- **Locked:** no (router only) · **Derived path:** no
- **Action:** extend `_simple_template` with `instructions=` and `extra_sheets=`. **Risk:** low. **Proof:** template tests plus a cell-level diff of the generated workbooks (headers, fills, instruction rows).
- [ ] Approved

### D-14: Bulk-upload router installs the `frontend.config.variable_config` stub three times · Reported
- **Evidence:** `bulk_uploads.py:120-151` (scalar, with a 20-key header literal), `:237-246` (pXRF) and `:436-454` (ICP). It exists because the locked `scalar_results.py:12`, `pxrf_data.py:11` and `icp_service.py:11` import a module that no longer exists. The scalar template headers (`:907-916`) are a second hand-kept copy of the stub's strings.
- **Locked:** no for the router helper; replacing the stub with a real backend module is H-09 (locked edits).
- **Action:** one `_ensure_variable_config()` helper. **Risk:** low. **Proof:** tests/api bulk uploads.
- [ ] Approved

### D-15: The `is_variant` rule is written twice in Python · Reported
- **Evidence:** `services/run_service.py:89-90` and `services/experiment_export.py:274-275` (`parent and id.startswith(parent.id + "_")`). The SQL copies (`icp_series.py:21-25` `_IS_VARIANT`, `v_core_flood_samples`, `v_hpht_samples`) are documented and stay.
- **Locked:** no · **Derived path:** no
- **Action:** one `is_variant(exp)` helper. **Risk:** low. **Proof:** tests/api export, core_floods, hpht.
- [ ] Approved

### D-16: Run-member loading and root description, `run_service` vs `experiment_export` · Reported
- **Evidence:** member building in `run_service.load_segments` (`:58-97`) and `experiment_export._load_members` (`:255-282`); root description in `run_service.run_description` (`:111-118`) and `experiment_export._root_description` (`:591-595`). The rule is the same, but the ordering tie-break differs (`_series_order`'s `-t` text key vs `by_date`'s plain id), so the result can differ only for runs with `-t` vials.
- **Locked:** no · **Derived path:** no
- **Action:** a shared loader plus helper. **Risk:** low–med (the export workbook "Description" cell could change on ties). **Proof:** compare both functions across every dev-DB lineage before switching.
- [ ] Approved

### D-17: Core Flood and HPHT `list_runs` / `_resolve` are about 85% identical · Reported
- **Evidence:** `core_flood_service.py:119-152` vs `hpht_service.py:150-181`, and `core_flood_service.py:88-98` vs `hpht_service.py:121-129`. Both re-implement `run_service.latest_sample_by_base` (`:196-210`) as `real[-1]`.
- **Locked:** no · **Derived path:** no (reads `cumulative_h2_grams_per_ton` from views)
- **Action:** a generic `list_run_items` / `resolve_run` in `run_service` with per-series callbacks. Leave the dashboard's deliberate date choice (`dashboard.py:222-229`) alone. **Risk:** med. **Proof:** byte-compare both list endpoints' JSON on dev (as #149 did).
- [ ] Approved

### D-18: Fe molar mass and other engine literals · Reported
- **Evidence:** `55.845` appears in `services/calculations/scalar_calcs.py:8` and `services/elemental_composition_service.py:11` (inside `FE_IN_FEO_FRACTION`). Inline literals sit in `scalar_calcs.py`: background default `0.2` (`:57, :108`; also the model default), NH₄⁺ MW `18.04` (`:110`) and a function-local `H2_MOLAR_MASS = 2.01588` (`:158`). The SQL view copies are documented and test-guarded; leave them.
- **Locked:** no · **Derived path:** **yes** (formula inputs).
- **Action:** import one constant and hoist the literals to module constants. Byte-identical floats preserve values. **Risk:** low. **Proof:** derived-column diff (it must be zero).
- [ ] Approved

### D-19: Two different "characterized" rules (service vs mapper listener) · **Verified**
- **Evidence:**
  - `backend/services/samples.py:45-90` `evaluate_characterized` counts XRD only with a linked `XRDAnalysis`, Elemental or Titration only with joined `ElementalAnalysis`, **or** a resolvable pXRF reading.
  - `database/event_listeners.py:14-66` `update_sample_characterized_status` runs on every flush touching `ExternalAnalysis` or `ElementalAnalysis`. It counts **any** `analysis_type == 'XRD'` row or any `ElementalAnalysis` by `sample_id`, and has **no pXRF criterion**.
  - So a pXRF-only sample marked True by `routers/samples.py:362/525/596` or the pXRF bulk path can be flipped back to False by the next such flush.
  - The "Bulk Elemental Composition" string at `elemental_composition_service.py:112` is not in `AnalysisType`, and `samples.py:66-69` does not count it.
- **Locked:** the listener lives in `database/` (outside `models/`) but is model-layer. **Derived path:** stored `SampleInfo.characterized`.
- **Action:** pick one rule and have the other delegate to it (H-07). This is a product decision before it is a refactor. **Risk:** med–high (changes stored flags). **Proof:** dry-run both rules over every dev-DB sample and diff the results.
- [ ] Approved

---

## Inefficient (E)

### E-01: Experiments list is N+1, and the grouped mode multiplies it · Reported
- **Evidence:** `_build_list_item` (`routers/experiments.py:76-104`) makes three queries per row: conditions (`:82`), the additive `string_agg` (`:89`) and the lazy `exp.description` (the `description_note` relationship, `database/models/experiments.py:58-64`, not eager). Grouped mode adds one bucket query per row (`:341-349`) plus three per collapsed child (`:364-365`). With `limit` up to 500, that is thousands of queries.
- **Locked:** no · **Derived path:** no
- **Action:** batch conditions, additive summaries (via the view, D-04), descriptions and bucket membership with a few `IN` queries. **Risk:** med (the list logic carries #87/#98/#109 subtleties). **Proof:** `tests/api/test_experiments*.py`, the rollup and replicate tests, and a page-JSON diff on dev.
- [ ] Approved

### E-02: Results tab runs two queries per result · Reported
- **Evidence:** `_result_with_flags` (`routers/experiments.py:842-853`) fetches the scalar row and the ICP row separately per result, called in a loop from `GET /{id}/results` (`:839`). `dashboard.py:448-456` already does this in bulk.
- **Locked:** no · **Derived path:** read only
- **Action:** `selectinload(ExperimentalResults.scalar_data, ExperimentalResults.icp_data)`. **Risk:** low. **Proof:** tests/api results-tab tests.
- [ ] Approved

### E-03: `next-id` / `next-ids` load every matching ID into Python · **Verified**
- **Evidence:** `routers/experiments.py:391-399` (one pass) and `:416-426` (four passes) select every matching `experiment_id` and take the max in Python.
- **Locked:** no · **Derived path:** no
- **Action:** compute the max in SQL (regex plus cast), or accept the cost at about 1k rows. Fold into D-03. **Risk:** low.
- [ ] Approved

### E-04: `create_analysis` runs a discarded query · Reported
- **Evidence:** `routers/samples.py:518-522` runs a `selectinload` query whose result is thrown away. `db.commit()` and `db.refresh(ea)` (`:532-533`) then expire the object, so `_to_analysis_response` lazy-loads again.
- **Locked:** no · **Derived path:** no
- **Action:** drop the dead query, or reload after the commit. **Risk:** low.
- [ ] Approved

### E-05: Conditions cascade lazy-loads every result's scalar · **Verified**
- **Evidence:** `services/calculations/conditions_calcs.py:52-57` iterates `experiment.results` and lazily reads `result.scalar_data` per result (default `lazy="select"`). It also does `session.get(Experiment)` (`:38`) and then `instance.experiment` (`:52`), two lookups for the same row.
- **Locked:** no · **Derived path:** **yes**
- **Action:** callers pre-load `experiment → results → scalar_data` with `selectinload`; reuse the one experiment object. The math is unchanged. **Risk:** low. **Proof:** SQL-echo query count before and after, plus the derived-column diff.
- [ ] Approved

### E-06: `recalculate_conditions_for_samples` runs one query per experiment, with no SAVEPOINT · Reported
- **Evidence:** `services/elemental_composition_service.py:50-66` runs a separate conditions query per experiment, using `.first()` with **no `order_by`**, which breaks the lowest-id convention. `get_analyte_wt_pct` (`conditions_calcs.py:42`) re-runs the same FeO query for every experiment on the same sample. There is no `begin_nested()` per row, so a DBAPI error poisons the rest of the loop. That violates the SAVEPOINT-per-row rule.
- **Locked:** no (but it is called by the locked `actlabs_titration_data.py:240, :624`) · **Derived path:** **yes** (`total_ferrous_iron_g` cascades to scalars)
- **Action:** one ordered query for all conditions, an FeO cache per sample within the call, and `begin_nested()` per row. **Risk:** low–med. Adding `order_by` could change which row is recalculated where duplicates exist (#109). **Proof:** derived-column diff; actlabs titration tests.
- [ ] Approved

### E-07: Background-ammonium recalc loop lazy-loads per row · Reported
- **Evidence:** `routers/experiments.py:1302-1312`. `recalculate_scalar` lazily loads `scalar.result_entry` per row; the result ids were selected as ints, so no objects are in the identity map.
- **Locked:** no · **Derived path:** **yes**
- **Action:** `selectinload(ScalarResults.result_entry)`. **Risk:** low. **Proof:** derived-column diff; `test_background_ammonium.py`.
- [ ] Approved

### E-08: `PATCH /api/experiments/{id}` sample change recalculates every scalar twice · **Verified**
- **Evidence:** `routers/experiments.py:1688-1690` runs `recalculate(cond, db)`, which cascades to every linked scalar (`conditions_calcs.py:52-57`). Then `:1693-1701` re-selects and recalculates the same scalars. Only a `db.flush()` runs between them. `recalculate_scalar` is idempotent, so the second pass writes identical values. The in-code comment justifies the loop **only** for the no-conditions case.
- **Locked:** no · **Derived path:** **yes**
- **Action:** run the `:1693-1701` loop only in an `else` branch when `cond is None`. This keeps the no-conditions case intact. **Risk:** low. **Proof:** on a dev-DB copy, PATCH the sample for one experiment with conditions and one without, before and after the change, and diff every scalar derived column. Then the full derived-column diff.
- [ ] Approved

### E-09: `update_cumulative_times_for_chain` re-walks the whole lineage on every uploaded row · Reported
- **Evidence:** `services/result_merge_utils.py:225-302`. The query count per call is 2 + Σ(2·depth + 1) over the chain, because `get_ancestor_time_offset` (`:247-257`) re-queries every ancestor's MAX. It is called once per row from `icp_service.py:769` (inside `bulk_create_icp_results`, `:795`), `scalar_results_service.py:268` (per `create_scalar_result_ex`, used by master, long_format and quick_upload) and `result_entry_service.py:283`.
- **Locked:** the module is not locked; the per-batch alternative would need locked caller edits (H-10). **Derived path:** **yes** (`cumulative_time_post_reaction_days`).
- **Action (local, behaviour-preserving):** load the chain once, get MAX(time) per experiment with one GROUP BY, walk parents in memory, then update. That is about 3 queries per call. **Risk:** med. **Proof:** dry-run `recalculate_cumulative_times_014` on dev before and after (zero changes); `test_time_field_guardrails`; the core-flood view tests.
- [ ] Approved

### E-10: `replicate_groups._compare_conditions` lazy-loads conditions per member · Reported
- **Evidence:** `services/replicate_groups.py:190-196` reads `member.conditions` per member; `_fetch_members` (`:126-143`) loads with no options.
- **Locked:** no · **Derived path:** no
- **Action:** `.options(selectinload(Experiment.conditions))`. **Risk:** low. **Proof:** `tests/api/test_replicate_group_detail.py`.
- [ ] Approved

### E-11: `delete_experiment_cascade` lets the ORM lazy-load each child · Reported
- **Evidence:** `services/experiment_deletion.py:378`. `db.delete(exp)` cascades through `results`, then each result's `files`, `scalar_data` and `icp_data`, with no `passive_deletes`. That is about 3 SELECTs per result. Bulk delete runs it per experiment (`experiment_deletion_bulk.py:146`).
- **Locked:** the service fix is not locked; a model-level `passive_deletes` fix would be (do not do that). **Derived path:** no
- **Action:** `selectinload` the children before `db.delete`. **Risk:** med (delete path). **Proof:** delete and bulk-delete tests; audit-row impact counts unchanged.
- [ ] Approved

### E-12: `run_service.load_segments(base_id=None)` loads every lineage experiment, then filters in Python · Reported
- **Evidence:** `services/run_service.py:65-81` joins every experiment that has a base, then filters with `include()` per row. `list_runs` then fetches view rows for every run (`core_flood_service.py:122-124`, `hpht_service.py:151-153`) before `scope="active"` drops the non-ongoing ones.
- **Locked:** no · **Derived path:** no
- **Action:** push the series filter into SQL (via the normalized experiment-type set from `reactor_slot`) and fetch samples only for runs that pass scope. **Risk:** low–med (normalization must match `series_prefix`). **Proof:** JSON diff of both list endpoints.
- [ ] Approved

### E-13: `evaluate_characterized` calls `db.get(PXRFReading)` per comma-separated reading · Reported
- **Evidence:** `services/samples.py:83-88`. It is called per affected sample from the pXRF upload router (E-14).
- **Locked:** no · **Derived path:** `SampleInfo.characterized`
- **Action:** one `IN` query. **Risk:** low. Sequence it after D-19's decision.
- [ ] Approved

### E-14: pXRF reverse-match in the bulk-upload router queries per sample · Reported
- **Evidence:** `routers/bulk_uploads.py:302-340`. A 4-way `LIKE` OR across every imported reading number runs first, then one `db.query(SampleInfo)` plus `evaluate_characterized` per sample. The router also parses the file a second time (openpyxl, falling back to pandas). Its "mirror" of the parser's reading-number normalization is not a true mirror (X-10).
- **Locked:** no (router) · **Derived path:** `characterized` only
- **Action:** fetch the samples with one `IN`. **Risk:** low. **Proof:** tests/api pXRF tests.
- [ ] Approved

### E-15: actlabs-rock upload resolves each sample ID about three times and discards one result · Reported
- **Evidence:**
  - `routers/bulk_uploads.py:689` computes `auto_log` from `preflight_check`, then never uses it. Preflight runs `fuzzy_find_sample` per unique ID, which is a full `SampleInfo` scan on a miss (`actlabs_titration_data.py:467-499`), and `find_similar_samples` loads all samples again (`:174`).
  - The router then runs `import_excel` (`:716`), which resolves each row again (`:593`).
- **Locked:** the router part is not locked (drop the unused auto-resolve or surface it as warnings); the service-side index is locked (L-E3).
- **Derived path:** yes, downstream (`recalculate_conditions_for_samples`)
- **Action:** remove the discarded `auto_log` work in the router. **Risk:** low. **Proof:** tests/api actlabs tests.
- [ ] Approved

---

## Locked: separate sign-off required

Every item here touches `backend/services/bulk_uploads/` or `backend/services/icp_service.py`. Both are locked per `docs/LOCKED_COMPONENTS.md`. **Ticking a box is not sign-off.** Each item needs Mat's explicit approval for that item, in conversation, before it enters any PR. Footnote contracts 1–6 in LOCKED_COMPONENTS.md constrain every proposal below.

### Locked: stale

| ID | Item | Evidence | Inbound refs | Last change (block / file) | Proposed action · risk | Approve |
|---|---|---|---|---|---|---|
| L-S1 | `ExperimentAdditivesService` has no route (**seed**) | `bulk_uploads/experiment_additives.py:17`; own comment `:125-133` | LEGACY `legacy/streamlit_frontend/bulk_uploads.py:8,982`; TEST `tests/services/bulk_uploads/test_experiment_additives.py` | file 2026-07-29 | Delete with its test once legacy is retired (H-01). Low. Live additive path is the `new_experiments` additives sheet. | [x] PR #193, signed off by Mat 2026-11-13 |
| L-S2 | `quick_upload`, `long_format`, `metric_groups` have no route | `quick_upload_from_excel`, `long_format_upload_from_excel`, `METRIC_GROUPS` | LEGACY `bulk_uploads.py:21-29,1015,1103,1129`; TEST `test_parser_result_notes.py:13-14`, `test_typed_notes_dual_write.py:387` | quick/long file 2026-10-14 (**< 60 days**), metric_groups 2026-03-16 | **Fails the 60-day rule** for two files, so also a human call. Footnote 6 names `_note_source='quick_upload'`. Check prod notes with `created_by='quick_upload'` first. Low–med. | [x] PR #193, signed off by Mat 2026-11-13 |
| L-S3 | `ScalarResultsUploadService.bulk_upsert_from_excel` (non-`_ex` wrapper) | `bulk_uploads/scalar_results.py:46-62` | none (router and legacy call `_ex`) · **Verified** | block 2026-03-16 / file 2026-10-14 | Delete. Low. | [x] PR #193, signed off by Mat 2026-11-13 |
| L-S4 | `AnalyteService` | `bulk_uploads/actlabs_titration_data.py:80-118` | none · **Verified** | file 2026-06-17 | Delete. Low. | [x] PR #193, signed off by Mat 2026-11-13 |
| L-S5 | `ICPService.get_icp_results_for_experiment`, `update_icp_result` | `icp_service.py:846, :866` | none · **Verified** | block 2026-03-16 / file 2026-10-14 | Delete both. Low. | [x] PR #193, signed off by Mat 2026-11-13 |
| L-S6 | Legacy-only diagnostics | `ICPService.diagnose_csv_structure` (`icp_service.py:1009`); `ActlabsRockTitrationService.diagnose` (`actlabs_titration_data.py:357`), which makes `_read_table_with_mode` (`:250`) dead too | LEGACY `bulk_uploads.py:1525, :693` | — | Delete with legacy. **Not** `parse_and_process_icp_file` / `process_icp_dataframe`: footnote 3(d) keeps their 2-tuple arity for `legacy/…:1558,1599`. | [x] PR #193, signed off by Mat 2026-11-13 |
| L-S7 | `PXRFUploadService.ingest_from_source` and the `update_existing=True` branch | `pxrf_data.py:145`, `:110-117` | TEST `tests/api/test_bulk_uploads.py:1477-1494` (asserts only that an import stays lazy) · **Verified**; LEGACY `:554` passes `update_existing` | file 2026-05-05 | Delete `ingest_from_source` and adjust that test. The `update_existing` branch is H-08. Low. | [x] PR #193, signed off by Mat 2026-11-13 |
| L-S8 | rock_inventory image-attach branch | `rock_inventory.py:349-401`; the router passes `image_files=[]` (`routers/bulk_uploads.py:567`) | LEGACY `bulk_uploads.py:647` | file 2026-04-24 | Delete with legacy. Low. | [x] PR #193, signed off by Mat 2026-11-13 |
| L-S9 | `_id_match.fuzzy_find_experiment` | `_id_match.py:133` | TEST `test_id_match_ambiguity.py:19,43,55,64,69` · **Verified** | file 2026-08-05 | Delete, or keep as a tested API. Low. | [x] PR #193, signed off by Mat 2026-11-13 |

### Locked: duplicated

| ID | Item | Evidence | Proposed action · risk | Approve |
|---|---|---|---|---|
| L-D1 | Experiment/sample ID matching uses three semantics in about 13 places | (a) canonical `_id_match.normalize_id`, which refuses ambiguity. (b) strip `-` `_` space plus `lower()` in SQL, with `.first()` that **guesses on collision** (the defect `_id_match.py:19-33` documents): `new_experiments.py:163, 522, 537, 591, 991, 1173, 1271`; `experiment_additives.py:79`; `aeris_xrd.py:41-67`; `xrd_upload.py:62-83` (verbatim copy); `rock_inventory.py:140, 155, 365`. (c) `icp_service._find_experiment` `:909-936` (no space strip). Exact-only: `experiment_status.py:190-194`, `experiment_deletion_bulk.py:234`. | Move aeris_xrd and xrd_upload onto `find_experiment_matches` first (results-only, small blast radius); `new_experiments` last (it decides create, rename or overwrite; footnotes 1 and 4). Before switching, count dev-DB experiments whose (a) and (b) keys disagree. **High** risk. Which semantics wins is H-03. | [ ] |
| L-D2 | Number/blank parsing: about 13 variants (**seed**) | `master_bulk_upload.py:305 _parse_float`, `:316 _parse_measurement_float` and `_ZERO_BLANK_COLUMNS` (footnote 5(g)); inline in `scalar_results.py:160-172`, `quick_upload.py:70-79,131`, `long_format.py:168-246`, `actlabs_titration_data.py:336-354` (`<0.5`→0.5), `chemical_inventory.py:43`, `experiment_additives.py:55-61`, `new_experiments.py:1352`, `pxrf_data.py:58` (LOD→0), `rock_inventory.py:228`, plus the XRD and elemental parsers. No variant handles thousands commas. | **Do not unify values.** The differences are meaningful. At most extract `is_blank(val)` (None, NaN, whitespace, NaT). Low for `is_blank`, **high** for value unification. Proof: the footnote-5 workbook still reports "Merged 72 rows into 36 vial-days" and 4 conflicts. | [ ] |
| L-D3 | Date parsing: five copies | `master._parse_date:328` (NaT-safe), `scalar_results._parse_measurement_date:20`, `quick_upload:115` (docstring: "replicates …"), `rock_inventory._parse_date:31`, `xrd_upload:179-186` (`%Y-%m-%d` only) | Share master's helper. Med: `pd.NaT` handling changes in scalar and quick. | [ ] |
| L-D4 | Bool parsing: five copies | `master._parse_bool:346`, `timepoint_modifications:41`, `rock_inventory:20`, `new_experiments.parse_bool:427`, `scalar_results:285-290` | Share one. Med: whether "y" is accepted differs. | [ ] |
| L-D5 | Sheet selection, header normalization, Excel/CSV readers | "Data sheet, else first non-INSTRUCTION, else 0": `quick_upload:191-202`, `long_format:119-131`, `scalar_results:67-80`. `normalize_column` closure ×3 in `new_experiments.py` (`:456, 957, 1249`). Asterisk stripping ×4. Readers: `pxrf:21`, `xrd_upload:114`, `timepoint_modifications:80`, `experiment_deletion_bulk:59`, actlabs `_read_table`/`_read_table_with_mode` `:250, :266`. | One helper module. Low–med. | [ ] |
| L-D6 | `_clean_mineral_name` copied verbatim | `aeris_xrd.py:70`, `xrd_upload.py:86` | Import from one place. Low. | [ ] |
| L-D7 | Error-feedback dict repeated | `scalar_results.py` ×5 (`:191-291`), `long_format.py` ×4 (`:185-237`) | Local `_err_fb()` helper. Low. | [ ] |
| L-D8 | Replicate plus `-t` token resolution duplicated, with identical error text | `scalar_results.py:178-206`, `master_bulk_upload._resolve_row_identity:488-507` | Move into `replicate_routing.py`. Low–med (footnote 2/5 identity). | [ ] |
| L-D9 | Parser-side template styling loops | `xrd_upload.generate_template_bytes:311`, `timepoint_modifications.generate_template_bytes:235` | Share with the router helper from D-13. Low. | [ ] |

### Locked: inefficient

| ID | Item | Evidence | Proposed action · risk | Approve |
|---|---|---|---|---|
| L-E1 | `_id_match.find_experiment_matches` / `find_sample_matches` load the whole table on each exact-match miss | `_id_match.py:92-111`. Called per row without caching via `ScalarResultsService._find_experiment` (`scalar_results_service.py:389`; master, scalar, long, quick) and `timepoint_modifications:171`. About 500 rows × about 1k experiments gives about 500k normalisations per Master upload with mismatched spellings. | A per-batch normalised index, updated when `auto_create_treatment_experiment` adds a row mid-batch. Med (a stale index would mis-resolve). Proof: `test_id_match*`, master and scalar ambiguity tests, the footnote-5 workbook, and the derived-column diff. | [ ] |
| L-E2 | Non-sargable `lower(replace(…))` lookups, per row | The L-D1(b)/(c) sites; up to about 4 full scans per experiment ID per New Experiments upload, per row in `experiment_additives`, `rock_inventory`, and ICP `_find_experiment` (`:643, :857`). aeris_xrd and xrd_upload already cache. | Prefetch a normalised map per sheet. `new_experiments` must update it on create and rename (footnote 1 flush ordering; prod `autoflush=False`). Med–high there, low for ICP. | [ ] |
| L-E3 | Per-cell existence queries | `actlabs _write_elemental_record` (`:44-77`, one query per sample×analyte; also used by elemental composition); XRDPhase per mineral (`aeris_xrd:222-230`, `xrd_upload:477-485`, `actlabs_xrd_report:558-565`); ExternalAnalysis/XRDAnalysis per row (`actlabs_xrd_report:505-522`); actlabs sample resolution (with E-15) | Prefetch per batch. It must also see rows inserted earlier in the batch. Low–med. | [ ] |
| L-E4 | `chemical_inventory` runs two queries per row | `chemical_inventory.py:68-70` (`ilike` name, then CAS) | Prefetch maps. Care: `ilike` treats `%` and `_` in names as wildcards, so a dict lookup changes matching. Low–med. | [ ] |
| L-misc | Stale line refs in a comment | `new_experiments.py:185-187` cites old router lines | Comment-only fix, but in a locked file. Nil. | [ ] |

---

## Needs human call

These items fail one staleness condition, may be reached dynamically, or need a product decision before any cleanup.

- **H-01: Retire `legacy/streamlit_frontend/`?** It is the sole remaining caller of S-04, S-09, L-S1, L-S2, L-S6 and L-S8, and its `bulk_uploads.py:1558,1599` calls are why footnote 3(d) pins ICP's 2-tuple arity. Retiring it first (scripts/docs sweep) turns most locked-stale items into simple deletions. **Decided 2026-11-13: yes. Deleted in PR #193; root `app.py` and the `streamlit` pin go to #174.**
- **H-02: Endpoints with no live UI caller that tooling or tests may still use.** No `scripts/` file calls any of them; the only endpoint-calling script, `scripts/delete_experiments_via_api.ps1`, uses `GET /api/experiments/{id}`, `/delete-impact` and `DELETE`. **Power BI usage can't be checked from the repo.**

  | Endpoint | Wrapper (live callers) | Tests | Derived write |
  |---|---|---|---|
  | `POST /api/results` (`results.py:77`) | `resultsApi.createResult` (0) | yes | no |
  | `POST /api/results/scalar` (`:117`), `PATCH /api/results/scalar/{id}` (`:142`) | `createScalar`, `patchScalar` (0) | yes | **yes** |
  | `GET /api/results/{experiment_id}` (`:57`) | `resultsApi.list` (0) | yes | no |
  | `GET /api/results/icp/{id}` (`:42`), `POST /api/results/icp` (`:162`) | `getIcp` (0); POST has no wrapper | **none** | no |
  | `POST /api/admin/recalculate/{type}/{id}` (`admin.py:26`; string-keyed `_MODEL_MAP`) | none | yes | **yes** |
  | `GET /api/experiments/{id}/rollup` (`experiments.py:978`) | `getRollup` (mocks only) | yes | no |
  | `PATCH /api/experiments/{id}/background-ammonium` (`:1284`) | `setBackgroundAmmonium` (mocks only) | yes | **yes** |
  | `DELETE /api/experiments/{id}/additives/{cid}` (`:1233`) | `chemicalsApi.deleteAdditive` (0); the UI uses `deleteAdditiveById` | yes | no |
  | `GET /api/chemicals/compounds/{id}` (`chemicals.py:59`) | `getCompound` (0) | yes | no |
  | `GET /api/conditions/{id}` (`conditions.py:216`) | none | yes | no |
  | `GET /api/samples/geo` (`samples.py:34`), `GET /api/samples/{id}/analyses` (`:541`) | `listGeo`, `listAnalyses` (0) | yes | no |
  | `POST /api/bulk-uploads/aeris-xrd` (`bulk_uploads.py:362`; block 2026-07-29) | none (`/xrd-mineralogy` auto-detects Aeris) | yes | no |
  | `GET /health` (`main.py:73`) | none | yes | no (keep for monitors) |

  The `results.py` docstrings say "Kept for Master Results tooling and tests" (`:85-86, :125-127`).
- **H-03: Which ID-matching semantics is canonical** (L-D1).
- **H-04: Canonical Autoclave prefix**, `AUTOCLAVE_` or `Autoclave_` (D-03 / X-09).
- **H-05: `modified_by`: `uid` or `email`?** `routers/experiments.py` writes `uid` (`update_experiment` and the additive upsert/delete); every other path writes `email` (D-07). This affects the audit consumers (the dashboard recent-activity panel).
- **H-06: Keep the `ChemicalAdditive` mapper listener?** `database/event_listeners.py:1199-1209` runs `recalculate(target, None)` on `before_insert`/`before_update`, so every additive write computes three times. **The explicit post-flush `recalculate(additive, db)` calls are load-bearing.** At `before_insert`, the `experiment`/`compound` relationships of a pending instance are reported to resolve to `None` (SQLAlchemy default `load_on_pending=False`; Reported, not checked against the library), so the listener's first pass nulls %/ppm/mM/M/% of Rock-derived fields. Removing an explicit call would store NULLs. Removing the listener is value-preserving only while every write path calls `recalculate` explicitly, which all LIVE insert sites do today.
- **H-07: The correct `characterized` rule** (D-19), including whether "Bulk Elemental Composition" analyses count.
- **H-08: `overwrite` / `update_existing` flags the API never passes.** These are `ElementalCompositionService.bulk_upsert_wide_from_excel(overwrite=)`, `ActlabsRockTitrationService.import_excel(overwrite=)` and pXRF `update_existing` (L-S7). Through the API, "updated" is always 0 for these. Expose the flags or delete the branches?
- **H-09: Replace the `frontend.config.variable_config` stub with a real backend constants module.** That needs locked edits to `scalar_results.py:12`, `pxrf_data.py:11` and `icp_service.py:11` (see D-14, X-13).
- **H-10: Per-batch cumulative-time update** (beyond E-09's local fix) needs locked caller edits.
- **H-11: `core_flood_service.RESULT_FIELDS` / `SCALAR_FIELDS` (`:156-157`) and the `run_description` alias (`:60`).** They have no importers, but the lines were last changed 2026-11-07, so they **fail the 60-day rule**. They became orphans in b62b96d (#146). Delete them in Phase 2 anyway? **Decided 2026-11-13: delete despite the 60-day rule. Shipped in PR #193.**
- **H-12: Two DB engines in one process.** `backend/api/dependencies/db.py:7-9` uses `Settings.database_url`; `database/database.py:13-25` builds a second engine from `os.getenv("DATABASE_URL")` with a different default, imported via `main.py:25` (`reset_postgres_sequences`). Merging touches `database/database.py`, which locked code and scripts import.
- **H-13: `update_cumulative_times_for_chain` filters on `base_experiment_id == base_id`** (`result_merge_utils.py:279-285`). A row with NULL `base_experiment_id` never updates itself. Roots get base = self from `parse_lineage_fields`, so this should affect only legacy or empty IDs. One dev-DB SQL count would settle it.

---

## Defects found during the sweep (not cleanup; file separately)

These are correctness bugs, not S/D/E items. The issue's Phase 2 PRs are cleanup-only and must not change stored values, so each needs its own issue, and the locked ones need sign-off. Verified items were confirmed by re-reading the code; **none has a reproducing test yet**. Write one before fixing.

| ID | Defect | Evidence | Status | Locked |
|---|---|---|---|---|
| X-01 | A blank additive amount stores **NaN**, then recalculates on it | `new_experiments.py:1352` `float(row.get('amount'))` on a blank cell gives `nan`, which passes `amount_val <= 0` (False). Same in `experiment_additives.py:55-61`. Derived additive fields. | **Verified** by reading | yes |
| X-02 | A blank compound cell auto-creates `Compound(name='nan')` | `str(row.get('compound') or '')`: NaN is truthy, so this gives `'nan'` (`new_experiments.py:1345`, create at `:1371-1377`; `chemical_inventory.py:51`). Same idiom, producing not-found errors, in `actlabs_xrd_report:57`, `ElementalCompositionService:204`, `timepoint_modifications:112,135`, `xrd_upload:152`, `aeris_xrd:136`. Related to the fixed `issue-blank-initial-note-parses-to-nan.md` (#118), same root cause in other columns. | **Verified** (new_experiments, chemical_inventory) | yes |
| X-03 | A blank Chemical Inventory cell overwrites an existing compound's MW/density with **NaN** | `chemical_inventory.py:43-47` `num(NaN)` returns NaN, not None; `:75-76` then assigns it because `is not None`. MW and density feed additive derived fields. | **Verified** | yes |
| X-04 | Conditions PATCH never recalculates additives | `routers/conditions.py:141-142` calls `recalculate(cond)`, which cascades to scalars only (`conditions_calcs.py:52-57`). Additive calcs read `water_volume_mL` and `rock_mass_g` (`additive_calcs.py:24-29`), so a volume or rock-mass edit leaves `catalyst_percentage`, `catalyst_ppm`, mass, moles and `final_concentration` stale. The retired `ExperimentalConditionsService.update` did cascade; migration 012 does too. Same gap in `new_experiments` for experiments absent from the additives sheet. Compare `issue-bulk-upload-never-recalculates-conditions.md` (fixed for conditions, not additives). | **Verified** | router no; parser yes |
| X-05 | Compound PATCH never recalculates linked additives | `routers/chemicals.py:105-107` changes `molecular_weight_g_mol` / `elemental_fraction` with no additive recalc. The Chemical Inventory upload is likely the same. | Reported | no / yes |
| X-06 | `auto_create_treatment_experiment` copies conditions with no recalc | `database/lineage_utils.py:528`. `water_to_rock_ratio` is excluded from the copy (`:407`), so it stays NULL, the "recalculate never ran" signature. Reached LIVE from `create_scalar_result_ex:113`. | Reported | no (`database/`) |
| X-07 | Creating or deleting an Elemental analysis never recalculates `total_ferrous_iron_g` | `routers/samples.py:482` (POST) and `:561` (DELETE) do not call `recalculate_conditions_for_samples`; deleting the FeO analysis leaves Fe and both Fe yields stale. | Reported | no |
| X-08 | Dashboard Serum KPI still undercounts | `routers/dashboard.py:276` uses `experiment_type == "Serum"`. `SERUM` is the most-used spelling. **Already documented** in `audit-2026-07-28-results-and-cleanup.md` ("CONFIRMED LIVE BUG … ~72%"), cited there at `:212`; still unfixed on develop. | **Verified** | no |
| X-09 | `next-id` vs `next-ids` Autoclave prefix mismatch | See D-03. | **Verified** | no |
| X-10 | pXRF reading number truncation | `pxrf_data.py:50` `str(int(float(x)))` stores "1.5" as "1" and drops "ABC-01". The router's "mirror" (`routers/bulk_uploads.py:252-283`, via `samples.normalize_pxrf_reading_no`) keeps both, so the reverse-match can miss samples. | Reported | yes |
| X-11 | `analysis.py` lookups filter on the denormalized `experiment_id` string, not `experiment_fk` | `routers/analysis.py:25, :54`. #109 established that those strings can be stale. | Reported | no |
| X-12 | `GET /api/samples/{sample_id}` commits on a read | `routers/samples.py:194-197` writes `characterized` as a side effect of a GET. | Reported | no |
| X-13 | Import-order dependency on a stub module | `database/models/results.py:257` lazily imports `frontend.config.variable_config`, which exists only if a bulk-upload endpoint installed the stub first. `database/ingest_pxrf.py:23-24` imports the nonexistent `frontend.config` and `utils.storage` at module top. | Reported | models: yes |
| X-14 | `ExperimentalConditionsService` and `database/services.py` call removed model methods | See S-04; the `database/services.py` half is out of scope (database sweep). | **Verified** | no |

---

## Out-of-scope observations (logged only; no action taken)

### Frontend sweep (`frontend/src`)
- **Dead API wrappers (0 live callers):**
  - `dashboardApi.reactorStatus`, `timeline` (`dashboard.ts:113-118`; `timeline` is mis-typed as an array)
  - `resultsApi.list`, `createResult`, `createScalar`, `patchScalar`, `getIcp` (`results.ts:104-124`; `results.test.ts:48-49` asserts two of them exist)
  - `chemicalsApi.getCompound`, `listAdditives`, `addAdditive`, `deleteAdditive` (`chemicals.ts:63, 73, 77, 91`)
  - `samplesApi.listGeo`, `listAnalyses` (`samples.ts:171, 196`)
  - `experimentsApi.getRollup`, `setBackgroundAmmonium` (`experiments.ts:513, 467`)
- **A wrapper that calls a nonexistent route:** `resultsApi.listScalar` calls `GET /results/scalar/` (`results.ts:117-118`), which only `/api/results/{experiment_id}` matches, with id `"scalar"`.
- **Duplicated client-side code:** `PSI_TO_MPA` is duplicated in `frontend/src/utils/units.ts:2` (also `master_bulk_upload.py:77`); `Step2Conditions.tsx:70` computes a display-only W:R preview.

### Scripts, docs and root files sweep
- `legacy/streamlit_frontend/` is the gate for H-01.
- `database/data_migrations/README.md:124-126` documents removed model methods.
- `docs/CALCULATIONS.md:15-16` shows `registry.recalculate` (callers import `recalculate`), and its trigger-list line refs are stale (S-11).
- `LOCKED_COMPONENTS.md:9` says all derived calculations live in `calculations/`, but `total_ferrous_iron_g`'s FeO→Fe constant lives in `services/elemental_composition_service.py`.
- Cross-ref: `issue-dead-add-result-modal.md` (shipped #104) removed the modal that used `resultsApi.createResult`. That is why those wrappers and endpoints (H-02) lost their last UI caller.
- Cross-ref: `issue-orphaned-files-on-disk.md` (open) overlaps E-11's delete path. Coordinate with it rather than refactoring the delete cascade twice.

### Database sweep (`database/`)
- `database/services.py` holds a second `ScalarResultsService` with zero importers that calls the removed `calculate_yields()` (`:12, :22`). Last change 2026-03-16.
- Old data migrations 001–005, 011 and `chemical_migration.py` call removed model methods and would raise if run. Mark them retired; migration files are never deleted.
- View/Python divergence: `event_listeners.py:529` `GREATEST(0, gross - bg)` gives 0 for a NULL gross where Python gives `None`, and treats a NULL bg as 0 where Python defaults it to 0.2. The same pattern appears at `:577-580`. Power BI reads these views. Report only.
- Migration 012: the up-front `joinedload` is defeated after chunk 1 by `expire_on_commit=True` (`database/database.py:25`). It matters only if 012 is re-run. Its second scalar pass duplicates the conditions cascade harmlessly.
- Layering: services import API schemas (`hpht_service`, `run_service`, `icp_series`, `core_flood_service` from `backend.api.schemas.*`) and private helpers (`result_entry_service._aware`, `notes._clean`). Not a database item; it belongs to a future architecture pass.
- `experiment_deletion.py:359-374` audit `new_values` omits `impact.h2_background_for`, which the impact dialog shows.
- `ExternalAnalysisResponse` is defined twice with different fields (`schemas/analysis.py:35`, `schemas/samples.py:160`). Both are live; the duplicate name is confusing.

---

## Phase 2 notes for the controller

- **Suggested PR order** (per the issue): `chore/sweep-stale-removal` (approved S plus approved L-S), then `refactor/sweep-dedupe` (D/L-D; helpers that future code must use get `decisions.md` contract entries: D-01, D-02, D-08, any L-D1 matcher), then `refactor/sweep-efficiency` (E/L-E).
- **Derived-column diff required** for the PRs touching D-02, D-05, D-07, D-09, D-18, E-05 to E-09 and any L-D1/L-D2/L-E1/L-E2 item.
- **Route-removal proof:** use the FastAPI route registry, never HTTP 404 (the SPA catch-all).
- **Baseline:** the #152 scoped pytest baseline is 1,752 passes; the scoped run was not executed in Phase 1.
- The X-defects are **not** Phase 2 material. File them as issues; X-01 to X-04 touch stored derived values and need a before/after diff on a prod backup once fixed.
