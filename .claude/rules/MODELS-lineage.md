---
paths:
  - "database/lineage_utils.py"
  - "database/experiment_id_parser.py"
  - "backend/services/replicate_groups.py"
  - "backend/services/replicate_collapse.py"
  - "backend/services/experiment_validation.py"
  - "backend/services/bulk_uploads/_id_match.py"
  - "backend/services/bulk_uploads/new_experiments.py"
  - "backend/services/bulk_uploads/replicate_routing.py"
  - "backend/services/icp_service.py"
  - "backend/api/routers/experiments.py"
  - "tests/**/*lineage*"
  - "tests/**/*replicate*"
  - "tests/**/*experiment_id*"
  - "tests/**/*rename*"
  - "tests/**/*timepoint*"
---

# Experiment Lineage, IDs & Replicates

> Part of the schema reference split out of `.claude/rules/MODELS.md` (the index). Field lists live in the model files; this file keeps what the code cannot tell you.

Columns live on `Experiment` in `database/models/experiments.py`.

- **Lineage Tracking**:
  - `base_experiment_id`: Tracks the root of a series (e.g., "HPHT_001" for "HPHT_001-2").
  - **Group addressing (issue #87):** `base_experiment_id` is a parsed string, not guaranteed to reference an existing `Experiment` row — lettered-only replicate sets (e.g. `SERUM_001a/b/c` with no bare `SERUM_001` row) are the common case. The replicate group is therefore addressed by this base-ID string via `GET /api/experiments/groups/{base_id}` and the `/experiments/groups/{baseId}` UI page, not by an experiment row lookup.
  - `parent_experiment_fk`: FK to the immediate parent experiment.
  - `replicate_label`: Single lowercase letter (`"a"`, `"b"`, `"c"`) identifying this row as a replicate member of a base experiment; `NULL` if this experiment is not a replicate. The bare base ID (or its explicit `S-0`/`S-1` spelling) is "replicate 0" — the group parent — and always has `replicate_label = NULL`.
  - **Known gap:** the `-0`/`-1` group-parent reclassification above only applies going forward, via the live `before_flush` event listener, to experiments created or re-saved after this change landed. It does NOT retroactively reclassify pre-existing `-0`/`-1`-suffixed experiments already in the database, and the one-off `establish_experiment_lineage_006.py` migration script was deliberately left with its original (pre-replicate) classification logic. Any historical experiment ID ending in `-0` or `-1` that was used as an ordinary sequential re-run (not a parent alias) will not be automatically reclassified — check case-by-case before building reporting or UI logic that assumes universal `-0`/`-1` = group-parent semantics.
  - **Parent wiring for letter + sequential re-runs (P5):** an ID like `SERUM_001a-2` (a sequential re-run of lettered replicate `a`) sets `parent_experiment_fk` to the lettered sibling `SERUM_001a` when that experiment exists (including when both are created in the same flush); otherwise it falls back to the group parent (bare stem, then `-0`, then `-1`), as before P5. Any `-N` links to the letter itself (`a-3` → `a`, not `a-2`). Letter + sequential + treatment combos (e.g. `SERUM_001a-2_Desorption`) are excluded and keep the group-parent link. Insertion-order caveat: if `a-2` is created while neither `a` nor the stem exists, it is orphaned; a later insert of the **stem** back-links it to the stem (the orphan pass is letter-unaware), and a later insert of `a` alone does not re-link it.
  - **Self-parent guard + rename-path ordering (issue #86):** `parent_experiment_fk` can never equal the experiment's own `id`. `update_experiment_lineage` (`database/lineage_utils.py`) drops a self-resolved parent to `NULL` (logging a warning) in both the replicate and sequential/treatment branches — a self-referential FK is never valid lineage and raises `CircularDependencyError` at flush. The trigger was the bulk-upload rename path: with `autoflush=False` (production `SessionLocal`), recomputing lineage before the rename was flushed made the group-parent `SELECT` match the row against its own stale (old) ID when old and new normalize alike (e.g. `X_cation_001` → `X_Cation_001a-t5`). The rename path in `backend/services/bulk_uploads/new_experiments.py` now flushes the new `experiment_id` **before** calling `update_experiment_lineage`, so the lookup resolves against the new ID.
  - **Canonical ID parser:** the experiment ID grammar lives in `database/experiment_id_parser.py` (`parse_lineage_fields` / `parse_experiment_id_full`); `database/lineage_utils.py::parse_experiment_id` is a delegating wrapper. `backend/services/experiment_validation.py::extract_lineage_info` is a frozen **legacy** shim whose divergent behavior (naive trailing `-N`, e.g. `CF-015` → sequential 15 of `CF`; combined `-N_Treatment` suffixes never extract the sequential number) is deliberately pinned because locked bulk-upload code depends on it.
    Separate from the parser, `backend/services/bulk_uploads/_id_match.py::normalize_id`
    is the canonical **fuzzy match key** used to resolve a workbook's ID spelling
    against a stored one. It is run-delimited (alpha/digit runs, leading zeros
    stripped per digit run, joined with `_`) — deliberately *not* a plain
    strip-and-concatenate, which collapsed `SERUM_JW_010-2` onto `SERUM_JW_102`
    (13 real pairs). The finders return **all** matches; nothing resolves an
    ambiguous key. See `docs/issues/issue-fuzzy-experiment-id-conflation.md`.
  - `id_timepoint_days` (Float, nullable, indexed): day value parsed from a trailing `-t<days>` ID token (e.g. `SERUM_001a-t7` → 7.0; decimals allowed). NULL = not encoded. The ID is canonical for the vial's timepoint: result creation fills a blank time from it and rejects a conflicting one (guards in `create_scalar_result_ex` and `POST /api/results`; string-level checks in the scalar/master bulk parsers). Set by `update_experiment_lineage` via `split_timepoint_token`; the token is stripped before lineage grouping, so `SERUM_001a-t7` groups under base `SERUM_001` with `replicate_label = a` and rolls up per day bucket with no view changes. A letterless `-t` vial (`SERUM_001-t7`) stays a parent-like row (base = stem, parent NULL).
    - **A letterless `-t` vial is one destructively-sampled instance of the stem
      itself — not a replicate (issue #101, decided 2026-08-11).** `SERUM_pH_002-t1/-t3/-t7`
      is ONE experiment sampled three times, so the set forms a group whose
      members are those vials: `member_count = 3`, `replicate_count = 0`,
      `replicates = []`. `replicate_count == 0` therefore does NOT mean "empty
      group" anywhere — read `member_count`. The letter remains the scientific
      unit *when there is one* (issue #98); this only says a set can have vials
      and no letters, and that per-bucket stats over such a set are a **time
      course**, not replicate statistics (one vial per bucket → `n_vials = 1`,
      `sd` NULL). `backend/services/replicate_groups.py::_member_clause` is the
      single definition, keyed on the timepoint-stripped `experiment_id` (via
      `timepoint_stem_expr`) — NOT on `id_timepoint_days IS NOT NULL`, which
      would also adopt `SERUM_001-2-t0` and `SERUM_001_Desorption-t5`, both of
      which carry the stem as their `base_experiment_id`. A bare-stem row has no
      token, so it stays the `parent` and is never also a member.
    - **ICP-OES upload honors the token but REPORTS rather than rejects (2026-08-07).**
      `extract_sample_info_ex` (`backend/services/icp_service.py`) takes the day from
      the ID's `-t` token and emits one file-level warning when the label's `_Day<n>`
      disagrees — matching `master_bulk_upload.py:383` rather than
      `apply_id_timepoint`, because an ICP label is machine-written by the worklist
      and letting it veto the ID would reject a whole run's readings. A label may
      therefore omit `Day` entirely (`SERUM_Cation_005c-t5_21x`); one with neither a
      `-t` token nor a `Day`/`Time` token is skipped, counted in the response's
      `skipped`, and named in a warning. Note the token is **lowercase `-t` only**, so
      `-T5` and `_t5` land in that reported-skip bucket. See footnote ³ in
      `docs/LOCKED_COMPONENTS.md`.
    - **Letter vs vial (issue #98):** a replicate *letter* is the scientific unit; a
      `-t<days>` *vial* is one destructively-sampled instance of it. The two are
      surfaced at different grains, and the collapse key is the timepoint-stripped
      `experiment_id` — never `(base_experiment_id, replicate_label)`, because
      `SERUM_001a-2` (a sequential re-run) shares both base and letter with
      `SERUM_001a` and must stay a separate row.
      - `GET /api/experiments` flat mode: one row per stem. `group_display_id`
        carries the label; `experiment_id` still names the representative row
        (the earliest non-outlier vial), which also supplies the Sample, Reactor,
        Date, Description and Additives columns.
      - `GET /api/experiments` grouped mode: one row per group, labeled by the
        stem, with `replicate_letters` for the badge and `vial_count` for the
        total row count.
      - `GET /api/experiments/groups/{base_id}`: `members`/`member_count` stay
        **per vial**; `replicates`/`replicate_count` are **per letter**.
      - The `-t` token is never rendered on `/experiments`, and a row standing for
        more than one vial shows status read-only, since an inline PATCH would
        reach only the representative.
