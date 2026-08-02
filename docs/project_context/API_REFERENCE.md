# API Reference

Base URL: `http://localhost:8000`
Auth: All endpoints require `Authorization: Bearer <firebase-id-token>` header.

## Experiments

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/experiments` | List experiments. Query: `skip`, `limit`, `status`, `experiment_type`, `sample_id`, `researcher`, `search` (case-insensitive partial match on `experiment_id`), `reactor_number`, `date_from`, `date_to`, `description` (matches the experiment's first note / Description column), `group_replicates` (bool, default false). `experiment_type`, `reactor_number`, and `description` are applied in SQL before `skip`/`limit`, so `total` and the returned page always reflect the fully-filtered set (#64). |
| GET | `/api/experiments/next-id` | Next auto-incremented experiment ID. Query: `type` (Serum/HPHT/Autoclave/Core Flood). Returns `{"next_id": "HPHT_004"}` |
| GET | `/api/experiments/{experiment_id}/exists` | Check if experiment ID string is already in use |
| GET | `/api/experiments/{experiment_id}` | Get single experiment with conditions, notes, and modifications |
| GET | `/api/experiments/{experiment_id}/results` | List result timepoints with scalar/ICP existence flags |
| GET | `/api/experiments/{experiment_id}/rollup` | Cross-replicate mean/median/std per timepoint bucket from `v_results_scalar_rollup` |
| GET | `/api/experiments/{experiment_id}/replicate-group` | The lettered replicate set (parent + members) this experiment belongs to |
| GET | `/api/experiments/groups/{base_id}` | Replicate group detail addressed by base-ID string (not an experiment row) — members, shared/divergent conditions, additives summary |
| GET | `/api/experiments/groups/{base_id}/rollup` | Cross-replicate rollup for the group, addressed by base-ID string; same shape as `/rollup` above |
| POST | `/api/experiments` | Create experiment (auto-assigns `experiment_number` if omitted) |
| POST | `/api/experiments/replicates` | Batch-create lettered replicates copying a base experiment's setup |
| PATCH | `/api/experiments/{experiment_id}` | Update status, researcher, date, sample_id, experiment_id (rename), and is_outlier |
| PATCH | `/api/experiments/{experiment_id}/status` | Inline status update. Body: `{"status": "COMPLETED"}` |
| DELETE | `/api/experiments/{experiment_id}` | Delete experiment (cascades all related data) |
| POST | `/api/experiments/{experiment_id}/notes` | Add a note |
| PATCH | `/api/experiments/{experiment_id}/notes/{note_id}` | Edit note text. Body: `{"note_text": "..."}`. No-op if text unchanged. Writes ModificationsLog. Returns updated note with `updated_at`. |
| GET | `/api/experiments/{experiment_id}/change-requests` | List reactor modification entries linked to this experiment. Returns `[]` if none. |
| GET | `/api/experiments/{experiment_id}/change-requests/recent` | Reactor modification entry for `date` (query param, default today) plus the most recent prior entry — both scoped to this experiment only, never another experiment that previously occupied the same reactor. Returns `{"selected": ..., "previous": ...}`, either nullable. |
| POST | `/api/experiments/{experiment_id}/change-requests` | Create or update a reactor modification for a given reactor + date. Body: `{"reactor_label": "R05", "requested_change": "...", "sync_date": "2026-07-20"}` (`sync_date` optional, defaults to today). Upserts on `(reactor_label, experiment_id, sync_date)`. |

### GET /api/experiments/{experiment_id}/exists

Check whether an experiment ID string is already in use.

**Auth:** Required (Firebase token)

**Path params:**
- `experiment_id` — the string to check

**Response `200`:**
```json
{ "exists": true }
```
or
```json
{ "exists": false }
```

**Usage:** Called by the frontend on a 300 ms debounce while the user types a custom ID, to show real-time availability feedback without submitting the form.

### GET /api/experiments — `group_replicates`

When `group_replicates=true`, pagination runs over **top-level rows** instead of raw experiment rows:

- A row is top-level when `replicate_label IS NULL OR parent_experiment_fk IS NULL`.
- A lettered replicate that matches the active filters is represented by its parent row instead of itself — i.e. filtering that matches only `SERUM_001b` still pulls `SERUM_001` (the parent) into the page, with `b` attached as a child.
- Every list item (flat or grouped mode) now includes `base_experiment_id`, `parent_experiment_fk`, `replicate_label`, `is_outlier`, and `id_timepoint_days`.
- In grouped mode, the representative row of a real lettered group (parent-led or an orphan stem with no parent row) additionally gets a `replicates` array. Membership is resolved by matching every row's bucket key (base stem), **not** by `parent_experiment_fk`, and the array includes the representative's own letter — see *New fields* below for the exact rules and the letter + sequential-rerun caveat. Rows attach in full regardless of whether they individually matched the filters — that's the point of grouping. Non-group items have `replicates: null`.
- `total` counts top-level rows, not raw experiment rows.
- Flat mode (`group_replicates=false`, the default) is **not** a raw pass-through: among the matched rows, any that differ only by a trailing `-t<days>` token are collapsed into one row per stem (issue #98) — e.g. `SERUM_001a-t1` and `SERUM_001a-t3` (one replicate sampled twice) render as a single row. `group_display_id` carries the collapsed label and `vial_count` the number of rows folded into it. Collapsing only ever happens among rows that passed the active filters — see *New fields* below.

**New fields (letter vs vial, issue #98):**
- `group_display_id` (string, nullable) — what the UI should render as this row's
  ID. Grouped mode: the group stem (`SERUM_001`). Flat mode: the
  timepoint-stripped stem (`SERUM_001a`). `experiment_id` continues to name the
  real representative row, which is the earliest non-outlier vial and also
  supplies `sample_id`, `reactor_number`, `date`, `condition_note` and
  `additives_summary`.
- `vial_count` (integer, default 1) — how many experiment rows this row stands
  for. Flat mode counts matched rows sharing the stem; grouped mode counts every
  row in the bucket, parent included. A row with `vial_count > 1` must not offer
  an inline status edit — the PATCH would reach only the representative.
- `replicate_letters` (array of string, nullable) — grouped mode only: the
  group's DISTINCT replicate letters, for the "N replicates: a, b" badge. Null
  in flat mode and for rows that are not groups.
- `replicates` (array, nullable) — grouped mode only: one entry per replicate
  letter-row, collapsed on the timepoint stem, **including the representative's
  own letter**. Because the collapse key is the stem rather than the letter, a
  letter that also has a sequential re-run (`SERUM_001a` plus `SERUM_001a-2`)
  contributes two entries while `replicate_letters` counts one.

Example grouped item (`group_replicates=true`) — letter `a` was sacrificed across two timepoints, letter `b` is a single flagged vial:
```json
{
  "id": 210,
  "experiment_id": "SERUM_001",
  "base_experiment_id": null,
  "parent_experiment_fk": null,
  "replicate_label": null,
  "is_outlier": false,
  "id_timepoint_days": null,
  "group_display_id": "SERUM_001",
  "vial_count": 4,
  "replicate_letters": ["a", "b"],
  "replicates": [
    { "id": 211, "experiment_id": "SERUM_001a-t1", "replicate_label": "a", "parent_experiment_fk": 210, "is_outlier": false, "id_timepoint_days": 1.0, "group_display_id": "SERUM_001a", "vial_count": 2, "replicates": null },
    { "id": 213, "experiment_id": "SERUM_001b", "replicate_label": "b", "parent_experiment_fk": 210, "is_outlier": true, "id_timepoint_days": null, "group_display_id": "SERUM_001b", "vial_count": 1, "replicates": null }
  ]
}
```
`SERUM_001a-t3`, the sibling timepoint collapsed into the `SERUM_001a` child above, is not itself listed — it is folded into `vial_count: 2` on that child. `experiment_id` on the top-level item still names the group's representative row, not a rendering label; the UI renders `group_display_id`.

### GET /api/experiments/{experiment_id}/rollup

Cross-replicate mean/median/std per timepoint bucket, sourced from the `v_results_scalar_rollup` reporting view (see `MODELS.md`).

**Auth:** Required (Firebase token)

**Path params:**
- `experiment_id` — any member of the group (base, parent, or a lettered replicate) — the endpoint resolves the group key itself.

**Grouping key:** `COALESCE(base_experiment_id, experiment_id)` for the given experiment — i.e. its `base_experiment_id` if set, else its own `experiment_id`.

**Response `200`:** array of rows, one per `time_post_reaction_bucket_days`, ordered ascending. 21 fields per row:
`base_experiment_id`, `time_post_reaction_bucket_days`, `n_vials`, `mean_gross_ammonium_mM`, `median_gross_ammonium_mM`, `sd_gross_ammonium_mM`, `mean_net_ammonium_mM`, `sd_net_ammonium_mM`, `mean_h2_ppm`, `sd_h2_ppm`, `mean_h2_micromoles`, `sd_h2_micromoles`, `mean_h2_grams_per_ton`, `sd_h2_grams_per_ton`, `mean_fe_yield_h2_pct`, `sd_fe_yield_h2_pct`, `mean_fe_yield_nh3_pct`, `sd_fe_yield_nh3_pct`, `mean_grams_per_ton_yield`, `sd_grams_per_ton_yield`, `mean_final_ph`. `mean_h2_ppm`/`sd_h2_ppm` (issue #90) aggregate `h2_concentration` (ppm); `sd_h2_ppm` is `null` when `n_vials = 1`.

**Parent inclusion (intended):** the bare group parent's own primary results share the
grouping key with its lettered replicates, so they are averaged into the group stats
like any member. Flag the parent `is_outlier` to exclude it. There is no separate
parent opt-out.

**Errors:**
- `404 Not Found` — no experiment matches `experiment_id`

**Outlier exclusion (P4):** experiments with `is_outlier = true` are excluded from every statistic in this response, including `n_vials` — a flagged replicate never contributes to the mean/median/std or the count, though its own data remains queryable via the per-row endpoints/views.

**Caveat (MODELS.md):** the grouping key does not distinguish a lettered replicate set from an ordinary sequential re-run sharing the same `base_experiment_id` (e.g. `HPHT_001` + `HPHT_001-2`). `n_vials >= 2` on this endpoint does not by itself confirm the group is a lettered replicate set — check case-by-case.

### GET /api/experiments/{experiment_id}/replicate-group

The lettered replicate set (if any) that `experiment_id` belongs to.

**Auth:** Required (Firebase token)

**Response `200`:**
```json
{
  "base_experiment_id": "SERUM_001",
  "parent": { "id": 210, "experiment_id": "SERUM_001", "replicate_label": null, "status": "ONGOING", "is_outlier": false },
  "members": [
    { "id": 211, "experiment_id": "SERUM_001a", "replicate_label": "a", "status": "ONGOING", "is_outlier": false },
    { "id": 212, "experiment_id": "SERUM_001b", "replicate_label": "b", "status": "ONGOING", "is_outlier": true }
  ]
}
```

**Semantics:**
- `members` is `[]` for a non-replicate solo experiment (no lettered children, no parent).
- **Orphan members:** if a lettered member's parent row doesn't exist (or was deleted), `parent` is `null` and `members` still lists the siblings, resolved by matching `base_experiment_id` directly rather than via the parent FK.

**Errors:**
- `404 Not Found` — no experiment matches `experiment_id`

### GET /api/experiments/groups/{base_id}

Replicate group detail addressed by the base-ID **string** — `base_id` need not match any experiment row. Lettered-only replicate sets (the common case) have no parent row.

**Auth:** Required (Firebase token)

**Response `200`** (`ReplicateGroupDetailResponse`) — a 2-letter set where letter `a` was sacrificed across two timepoints:
```json
{
  "base_experiment_id": "SERUM_001",
  "parent": {
    "id": 210, "experiment_id": "SERUM_001", "replicate_label": null, "status": "ONGOING", "is_outlier": false,
    "id_timepoint_days": null, "researcher": "MH", "date": "2026-03-01", "result_count": 1, "conditions": {}
  },
  "members": [
    { "id": 211, "experiment_id": "SERUM_001a-t1", "replicate_label": "a", "status": "ONGOING", "is_outlier": false, "id_timepoint_days": 1.0, "researcher": "MH", "date": "2026-03-01", "result_count": 1, "conditions": { "rock_mass_g": 5.2 } },
    { "id": 212, "experiment_id": "SERUM_001a-t3", "replicate_label": "a", "status": "ONGOING", "is_outlier": false, "id_timepoint_days": 3.0, "researcher": "MH", "date": "2026-03-01", "result_count": 1, "conditions": { "rock_mass_g": 5.2 } },
    { "id": 213, "experiment_id": "SERUM_001b", "replicate_label": "b", "status": "ONGOING", "is_outlier": true, "id_timepoint_days": null, "researcher": "MH", "date": "2026-03-01", "result_count": 4, "conditions": {} }
  ],
  "member_count": 3,
  "replicates": [
    { "replicate_label": "a", "vials": [
      { "id": 211, "experiment_id": "SERUM_001a-t1", "replicate_label": "a", "status": "ONGOING", "is_outlier": false, "id_timepoint_days": 1.0, "researcher": "MH", "date": "2026-03-01", "result_count": 1, "conditions": { "rock_mass_g": 5.2 } },
      { "id": 212, "experiment_id": "SERUM_001a-t3", "replicate_label": "a", "status": "ONGOING", "is_outlier": false, "id_timepoint_days": 3.0, "researcher": "MH", "date": "2026-03-01", "result_count": 1, "conditions": { "rock_mass_g": 5.2 } }
    ] },
    { "replicate_label": "b", "vials": [
      { "id": 213, "experiment_id": "SERUM_001b", "replicate_label": "b", "status": "ONGOING", "is_outlier": true, "id_timepoint_days": null, "researcher": "MH", "date": "2026-03-01", "result_count": 4, "conditions": {} }
    ] }
  ],
  "replicate_count": 2,
  "shared_conditions": { "temperature_c": 200.0 },
  "divergent_fields": ["rock_mass_g"],
  "additives_summary": "Mg(OH)2 5 g" ,
  "additive_names": "Mg(OH)2",
  "additives_diverge": false
}
```

**Fields:**
- `parent` — `null` when no parent row exists (orphan lettered set).
- `members[].conditions` — only the fields whose values diverge from `shared_conditions`, per member.
- `shared_conditions` / `divergent_fields` — condition fields identical vs. differing across all members.
- `additives_summary` / `additive_names` — `null` when `additives_diverge` is `true` (members disagree on additives).

**New fields (letter vs vial, issue #98):**
- `members` / `member_count` — **per vial**, unchanged. `member_count` always
  equals `len(members)`.
- `replicates` (array of `{replicate_label, vials[]}`) — the same members grouped
  by replicate letter. A letter holds several vials when the set is sacrificed
  per timepoint.
- `replicate_count` (integer) — number of LETTERS. This is what the group page
  header reports; a 2-letter × 2-timepoint set gives `replicate_count = 2` and
  `member_count = 4`.
- `parent` — now a full `ReplicateGroupMemberDetail` (was the narrower
  `ReplicateGroupMember`). `id_timepoint_days` and `result_count` reflect the
  parent's own row; `conditions` is always `{}` because the parent is
  deliberately excluded from the group's divergence scan.
- `divergent_fields` — vials with no `conditions` row are excluded from the
  comparison rather than counting as all-null, so conditions shared across the
  vials that do have rows stay in `shared_conditions`.

**Errors:**
- `404 Not Found` — `base_id` matches neither an experiment row nor any `base_experiment_id` value.

### GET /api/experiments/groups/{base_id}/rollup

Cross-replicate rollup for the group, addressed the same way as the detail endpoint above.

**Auth:** Required (Firebase token)

**Response `200`:** `list[RollupTimepointResponse]` — same shape as `GET /api/experiments/{experiment_id}/rollup`.

**Errors:**
- `404 Not Found` — same rule as the detail endpoint above.

**Compatibility note:** `GET /{experiment_id}/replicate-group` and `GET /{experiment_id}/rollup` are unchanged (byte-identical responses) — both are now thin wrappers delegating to the same group resolver used by the two endpoints above.

### POST /api/experiments/replicates

Batch-create lettered replicates copying a base experiment's setup.

**Auth:** Required (Firebase token)

**Request body:**
```json
{ "base_experiment_id": "SERUM_001", "count": 3 }
```
- `base_experiment_id` (string, required) — the stem; either the bare base or an explicit `S-0`/`S-1` group-parent spelling resolves to the same parent.
- `count` (int, 1–25, default 3)

**Response `201`:**
```json
{
  "created": [ /* ExperimentResponse-shaped objects, one per new replicate */ ],
  "skipped": [ "'SERUM_001a' already exists — skipped, not overwritten." ]
}
```

**Copy semantics:** each new replicate copies the base (parent) experiment's `sample_id`, `researcher`, `status`, `date`, its `ExperimentalConditions` row, and all `ChemicalAdditive` rows; the calc engine re-runs on the copied conditions and additives. Per-vial actuals (e.g. measured mass, actual reactor) are left as copies and are expected to be edited per replicate afterwards.

**Letter assignment:** continues after any existing lettered members for the base (e.g. `a`, `b` already present → new replicates get `c`, `d`, ...).

**Conflict handling:** a per-letter ID collision (an experiment already exists at that exact ID) is skipped with a message in `skipped` — it is never fatal; other requested replicates in the same call still get created. If fewer free letters remain than `count`, a message is added to `skipped` and only the available letters are created.

**Errors:**
- `404 Not Found` — no base/parent experiment exists for `base_experiment_id` (create the base experiment first)
- `409 Conflict` — unexpected IntegrityError on creation (distinct from the normal skip path above)

### GET /api/experiments/{experiment_id}/delete-impact

Preview what deleting an experiment would destroy and decouple. Read-only;
powers the delete confirmation dialog. `404` if the experiment does not exist.

```json
{
  "experiment_id": "SERUM_001a",
  "conditions": 1,
  "results": 3,
  "scalar_results": 3,
  "icp_results": 2,
  "result_files": 0,
  "notes": 1,
  "additives": 2,
  "external_analyses": 0,
  "xrd_phases": 4,
  "change_requests": 0,
  "total": 16,
  "background_for": ["SERUM_002a"],
  "replicate_children": []
}
```

`conditions` is the `ExperimentalConditions` setup row (temperature, initial pH,
rock mass, water volume, reactor number, pressures). It is hard-deleted with the
experiment, so it is counted — an experiment with conditions and nothing else
reports `total: 1`, not `0`.

`total` sums the counts only. `background_for` (experiments naming this one as
their ammonium background) and `replicate_children` (experiments whose
`parent_experiment_fk` points here) are **decoupled, not deleted** — those
experiments survive, and `background_ammonium_concentration_mM` on the citing
rows is left intact — so they are excluded from `total`. The UI requires the user
to type the experiment ID whenever anything is destroyed **or** decoupled, i.e.
`total > 0` or either list is non-empty.

### DELETE /api/experiments/{experiment_id}

Hard-deletes the experiment and **purges everything it owns**. Available to any
approved researcher. `404` if the experiment does not exist.

Purged: the conditions row and its chemical additives, all results (scalar, ICP,
result files), notes, external analyses **and their `elemental_analysis` rows**,
XRD phase rows, this experiment's `reactor_change_requests` rows, and its prior
`ModificationsLog` history.

Decoupled but **not** destroyed — a deletion never touches another experiment's
data: other experiments' `scalar_results` that cite this one as their ammonium
background have `background_experiment_id` / `background_experiment_fk` cleared
while the row and its `background_ammonium_concentration_mM` value survive; and
replicate siblings lose only `parent_experiment_fk`, keeping
`base_experiment_id` and `replicate_label` so the group stays addressable by
string (issue #87).

**Returns `200` with a body, not `204`** — the caller needs to know what was
decoupled:

```json
{
  "experiment_id": "SERUM_001a",
  "deleted": true,
  "impact": { "...": "same shape as GET /delete-impact" }
}
```

`impact` is measured immediately before the delete, so it reports what actually
happened rather than the pre-flight estimate.

Every call writes one `ModificationsLog` entry (`modification_type='delete'`,
`experiment_fk = NULL`) whose `old_values` is a **record of what was deleted, not
a restore point**: the experiment header, its conditions, its additives and its
note text. Results/ICP values, XRD phase rows, external-analysis metadata and
files, note timestamps, the purged prior audit history and resolvable lineage are
**not** recoverable from it. That single row is the only surviving trace of the
deletion — see the deletion-path notes in `.claude/rules/MODELS.md` for the
orphan-prevention details and the `experiment_fk = NULL` requirement.

### PATCH /api/experiments/{experiment_id}

Update experiment properties.

**Auth:** Required (Firebase token)

**Path params:**
- `experiment_id` — the experiment string ID

**Request body fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `status` | string (enum) | No | `ONGOING`, `COMPLETED`, `CANCELLED` |
| `researcher` | string | No | Researcher name or initials |
| `date` | string (ISO 8601) | No | Experiment start date |
| `sample_id` | string | No | Reference to `SampleInfo.sample_id` |
| `experiment_id` | string | No | Rename: must be unique; max 100 chars; whitespace stripped before validation |
| `is_outlier` | boolean | No | Flags/unflags a bad vial (see `MODELS.md`). Writing it appends a `ModificationsLog` audit entry. |

**Response `200`:** Updated experiment object with all fields, including `is_outlier`.

**Errors:**
- `409 Conflict` — `experiment_id` is already in use by another experiment; `sample_id` FK constraint fails
- `422 Unprocessable Entity` — validation error (e.g., invalid status enum)

**Side effects:**
- On rename, `ExperimentalConditions.experiment_id` is updated and a `ModificationsLog` entry is written.
- On `is_outlier` change, a `ModificationsLog` entry is written recording the old/new value.

### PATCH /api/experiments/{experiment_id}/status

Inline status update (issue #97). Body: `{"status": "ONGOING"}`.

**Auth:** Required (Firebase token)

**Response `200`:** Updated experiment object.

**Errors:**
- `409 Conflict` — the transition to `ONGOING` was rejected because another experiment is already `ONGOING` in the same physical reactor slot. `detail` names the slot, the occupying `experiment_id` and its start date, e.g. `Reactor R08 is already occupied by ONGOING experiment 'HPHT_222' (started 2026-07-24). Complete or cancel it before starting 'HPHT_230'.` The occupant is **not** demoted — this endpoint cannot distinguish advancing a sequential re-run from a mis-picked reactor. Only the transition *to* `ONGOING` is gated; `COMPLETED` / `CANCELLED` / `QUEUED` are never blocked, and an experiment with no physical slot (Serum, Autoclave, Other, or no `reactor_number`) is never blocked.
- `422 Unprocessable Entity` — invalid status enum value.

**Not yet built:** no frontend confirm-and-supersede dialog. Until one exists, the caller must complete or cancel the occupant first and retry. Tracked in `docs/issues/issue-reactor-occupancy-uniqueness-trigger.md`.

## Conditions

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/conditions/{id}` | Get conditions by PK |
| GET | `/api/conditions/by-experiment/{experiment_id}` | Get conditions by experiment string ID |
| POST | `/api/conditions` | Create conditions (triggers `water_to_rock_ratio` calc) |
| PATCH | `/api/conditions/{id}` | Update conditions (recalculates derived fields) |

`ConditionsResponse` also includes `reactor_slot` (string, nullable, **read-only/derived** — issue #97). It is never accepted on `ConditionsCreate`/`ConditionsUpdate`; the backend derives and overwrites it from `(reactor_number, experiment_type)` on every write via `database/reactor_slot.py::derive_reactor_slot`. See `.claude/rules/MODELS.md` for the full mapping and caveats.

## Additives

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/experiments/{experiment_id}/additives` | List chemical additives for an experiment |
| PUT | `/api/experiments/{experiment_id}/additives/{compound_id}` | Upsert additive by compound PK. Body: `{"amount": float, "unit": string}`. Triggers recalculation. Writes ModificationsLog. |
| DELETE | `/api/experiments/{experiment_id}/additives/{compound_id}` | Remove additive by compound PK. Writes ModificationsLog. |
| PATCH | `/api/additives/{additive_id}` | Partial update by additive PK. Accepts `compound_id`, `amount`, `unit`, `addition_order`, `addition_method`. Triggers recalculation. Writes ModificationsLog. Returns 409 if new compound is already in the experiment. |
| DELETE | `/api/additives/{additive_id}` | Remove additive by additive PK. Writes ModificationsLog. |

## Results

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/results/{experiment_id}` | List all result timepoints for an experiment |
| POST | `/api/results` | Create result entry |
| GET | `/api/results/scalar/{result_id}` | Get scalar result |
| POST | `/api/results/scalar` | Create scalar (triggers H2 + ammonium yield calc) |
| PATCH | `/api/results/scalar/{scalar_id}` | Update scalar (recalculates) |
| GET | `/api/results/icp/{result_id}` | Get ICP result |
| POST | `/api/results/icp` | Create ICP result |

`GET /api/experiments/{experiment_id}/results` and scalar result responses now include `nmr_run_date`, `icp_run_date`, `gc_run_date`, and `xrd_run_date` (all nullable) — instrument run-date provenance.

`GET /api/experiments/{experiment_id}/results` also includes `h2_concentration` (raw measured H2 in ppm, vol/vol; issue #90) on every row, `null` where the result has no scalar record — so the per-result table can show ppm without a second `resultsApi.getScalar` request per row.

### POST /api/results and POST /api/results/scalar — `id_timepoint_days` (issue #81)

If the target experiment's `id_timepoint_days` is set (its ID carries a `-t<days>` token),
the day encoded in the ID is canonical for that vial's timepoint:

- An omitted/blank `time_post_reaction_days` (`POST /api/results`) or `time_post_reaction`
  (`create_scalar_result_ex`, the scalar-result creation path shared by all bulk-upload
  routes — the UI's Add Results modal is guarded separately via `POST /api/results`) is
  filled from `id_timepoint_days`.
- A supplied value that differs from `id_timepoint_days` by more than
  `TIMEPOINT_TOLERANCE_DAYS` (0.0001 days) is rejected with `422 Unprocessable Entity`; the
  error message contains "canonical" and names the conflicting day.
- No change to behavior when `id_timepoint_days` is `NULL` (the common case).

This guard lives in `backend/services/result_merge_utils.py::apply_id_timepoint`, called
from `backend/api/routers/results.py::create_result` and
`backend/services/scalar_results_service.py::create_scalar_result_ex`. The bulk-upload
parsers (Solution Chemistry, Master Results Sync) additionally check this at the
string/row level before results ever reach these functions, so a conflicting row is
reported with a per-row error rather than raising at the API layer — see
`docs/upload_templates/scalar_results.md` and `docs/upload_templates/master_bulk_upload.md`.

**Known bulk-upload limitation:** the New Experiments upload parses and persists
`id_timepoint_days` for each created row but does not copy a parent's conditions/additives
for `-t<days>` IDs — see `docs/user_guide/REPLICATES.md` for the full limitation.

### POST /api/results — timepoint bucketing (issue #83)

- The server sets `time_post_reaction_bucket_days` to the resolved
  `time_post_reaction_days` rounded to 4 decimals (`normalize_timepoint`). Any
  client-supplied `time_post_reaction_bucket_days` is ignored — the field is
  accepted for backward compatibility but always overwritten.
- A `null` resolved time (no `time_post_reaction_days` and no `-t<days>` ID token)
  leaves the bucket `null`; such rows do not appear in `v_results_scalar_rollup`
  buckets.
- **Newest wins:** if the new row is primary (`is_primary_timepoint_result`, default
  `true`) and another primary row already occupies the same bucket for the same
  experiment, the older row is demoted to non-primary. Non-primary inserts leave the
  existing primary untouched.
- Historical rows created before this fix were backfilled by the
  `backfill result timepoint buckets` migration using the same rounding and a
  data-first demotion rule (rows with scalar+ICP outrank rows with either, which
  outrank dataless rows; ties go to the newest row).

## Samples

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/samples` | List samples. Query: `search`, `country`, `rock_classification`, `characterized`, `has_pxrf`, `has_xrd`, `has_elemental`, `skip`, `limit` |
| GET | `/api/samples/geo` | Samples with coordinates only (for map view). Returns `[{sample_id, latitude, longitude, rock_classification, characterized}]` |
| GET | `/api/samples/{sample_id}` | Full sample detail with linked experiments, photos, analyses, elemental results |
| POST | `/api/samples` | Create sample. Auto-evaluates `characterized` on creation. |
| PATCH | `/api/samples/{sample_id}` | Update mutable fields. Auto-evaluates `characterized` unless `characterized` is explicitly set in the payload. |
| DELETE | `/api/samples/{sample_id}` | Delete sample. Returns 409 if experiments are linked. Returns 204. |
| POST | `/api/samples/{sample_id}/photos` | Upload photo (JPEG/PNG, max 20 MB). Returns `201 SamplePhotoResponse`. |
| DELETE | `/api/samples/{sample_id}/photos/{photo_id}` | Delete photo from DB and disk. Returns 204. |
| GET | `/api/samples/{sample_id}/analyses` | List external analyses for the sample |
| POST | `/api/samples/{sample_id}/analyses` | Create external analysis. pXRF: normalizes `pxrf_reading_no`, returns warnings for unmatched reading numbers. Auto-evaluates `characterized`. |
| DELETE | `/api/samples/{sample_id}/analyses/{analysis_id}` | Delete analysis. Auto-evaluates `characterized`. Returns 204. |
| GET | `/api/samples/{sample_id}/activity` | Last 100 modification log entries for the sample |

### GET /api/samples

Query parameters:
- `search` (string) — filter by sample_id or locality (case-insensitive substring)
- `country` (string) — exact match
- `rock_classification` (string) — case-insensitive substring
- `characterized` (bool) — filter by characterized status
- `has_pxrf`, `has_xrd`, `has_elemental` (bool) — filter by analysis type presence
- `skip` / `limit` (int, default limit=50)

Response shape:
```json
{
  "items": [
    {
      "sample_id": "SMP-042",
      "rock_classification": "Peridotite",
      "country": "Oman",
      "locality": "Samail Ophiolite",
      "characterized": true,
      "created_at": "2026-03-01T09:00:00Z"
    }
  ],
  "total": 14,
  "skip": 0,
  "limit": 50
}
```

### POST /api/samples/{sample_id}/analyses — pXRF notes

When `analysis_type` is `"pXRF"` and `pxrf_reading_no` is provided, the server:
1. Normalizes the reading number (strip whitespace, convert `"1.0"` → `"1"`)
2. Looks up `PXRFReading` by the normalized key
3. If not found, returns `ExternalAnalysisWithWarnings` (HTTP 201) with a `warnings` array — creation still succeeds

Response (pXRF with missing reading):
```json
{
  "analysis": { ... },
  "warnings": ["pXRF reading '42' not found in database — analysis created but reading is unlinked"]
}
```

## Chemicals

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chemicals/compounds` | List all compounds |
| GET | `/api/chemicals/compounds/{id}` | Get compound |
| POST | `/api/chemicals/compounds` | Create compound |
| GET | `/api/chemicals/additives/{conditions_id}` | List additives for a conditions record |
| POST | `/api/chemicals/additives/{conditions_id}` | Add additive (triggers full additive calc) |

## Analysis

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/analysis/xrd/{experiment_id}` | XRD phases for an experiment |
| GET | `/api/analysis/pxrf` | List pXRF readings. Query: `skip`, `limit` |
| GET | `/api/analysis/external/{experiment_id}` | External analyses for an experiment |

## Dashboard

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dashboard/` | **M7** Full dashboard payload: summary stats, reactor cards, Gantt timeline, recent activity. Single call. |
| GET | `/api/dashboard/reactor-status` | Legacy — reactors with current ONGOING experiment |
| GET | `/api/dashboard/timeline/{experiment_id}` | All timepoints with scalar/ICP presence flags |

### GET /api/dashboard/

Returns all dashboard data in a single call. Response shape:

```json
{
  "summary": {
    "reactors": { "total": 16, "ongoing": 8, "queued": 4, "empty": 4 },
    "core_floods": { "total": 3, "ongoing": 1, "queued": 0, "empty": 2 },
    "gc_measurements_7wd": 5,
    "gc_experiments_7wd": 3,
    "serum_vials_started_7wd": 4,
    "serum_experiments_7wd": 2,
    "workday_window_start": "2026-07-21",
    "workday_window_end": "2026-07-29"
  },
  "reactors": [
    {
      "reactor_number": 5,
      "reactor_label": "R05",
      "experiment_id": "HPHT_MH_072",
      "experiment_db_id": 142,
      "status": "ONGOING",
      "experiment_type": "HPHT",
      "sample_id": "SMP-042",
      "description": "Baseline run with magnetite catalyst",
      "researcher": "MH",
      "started_at": "2026-03-01T09:00:00Z",
      "days_running": 18,
      "temperature_c": 200.0,
      "todays_modification": "Swapped stir shaft; topped up catalyst"
    }
  ],
  "timeline": [
    {
      "experiment_id": "HPHT_MH_072",
      "experiment_db_id": 142,
      "status": "ONGOING",
      "experiment_type": "HPHT",
      "sample_id": "SMP-042",
      "researcher": "MH",
      "started_at": "2026-03-01T09:00:00Z",
      "ended_at": null,
      "days_running": 18
    }
  ],
  "recent_activity": [
    {
      "id": 501,
      "experiment_id": "HPHT_MH_072",
      "modified_by": "MH",
      "modification_type": "update",
      "modified_table": "scalar_results",
      "created_at": "2026-03-19T14:30:00Z"
    }
  ]
}
```

**Notes:**
- Only occupied reactor slots are returned; the frontend renders all 18 fixed slots
- `description` is the text of the oldest note for the experiment
- Timeline limited to 100 most recent experiments
- Activity limited to last 20 modification log entries
- Core Flood experiments use `CF01`/`CF02` labels; all others use `R01`–`R16`
- `todays_modification` is the `requested_change` of a reactor modification saved for the current UTC day for this card's `(experiment_id, reactor_label)`; `null` if none was saved today. Populated by one batched query — the endpoint remains a single call.

## Admin

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/admin/recalculate/{model_type}/{id}` | Re-run calc engine. model_type: `conditions`, `scalar`, `additive` |

## Bulk Uploads

All endpoints return `UploadResponse`:
```json
{
  "created": 0, "updated": 0, "skipped": 0,
  "errors": [], "warnings": [], "feedbacks": [], "message": "", "dry_run": false,
  "plan": null, "plan_hash": null
}
```

**`dry_run` (issue #100 item 1):** every POST endpoint below accepts a `dry_run` form field (default `false`). When `true`, the parser still runs in full — the response's `created`/`updated`/`skipped`/`errors`/`warnings` reflect what *would* happen — but the transaction is rolled back instead of committed, so nothing is persisted. The `message` is prefixed `[DRY RUN]` and the response's `dry_run` field is `true`. For `actlabs-rock`, `dry_run` applies to both write paths (the no-conflict direct import and the resolutions-supplied Phase 2 import); Phase 1's preflight-only response (`ConflictCheckResponse`) never writes regardless of `dry_run`. For `new-experiments` specifically, `dry_run` is also the preview half of the plan-hash handshake described below.

**`plan` (issue #100 item 2, `new-experiments` only):** `UploadResponse.plan` is a structured summary of what the upload did (or, with `dry_run=true`, would have done):
```json
{
  "creates":    [{ "row": 2, "experiment_id": "HPHT_072", "parent_id": null, "copied_from": null }],
  "renames":    [{ "row": 3, "from_id": "HPHT_071", "to_id": "HPHT_071_Renamed" }],
  "overwrites": [{ "row": 4, "experiment_id": "HPHT_070", "fields_changed": [{ "field": "initial_ph", "old": 4.0, "new": 9.0 }] }],
  "skips":      [{ "row": 5, "experiment_id": null, "reason": "empty experiment_id" }],
  "conflicts":  [{ "row": 6, "kind": "already_exists", "detail": "experiment_id 'HPHT_070' already exists; set overwrite=True to update" }],
  "counts": { "creates": 1, "renames": 1, "overwrites": 1, "skips": 1, "conflicts": 1 }
}
```
`fields_changed` merges diffs discovered across the experiments sheet (`sample_id`, `researcher`, `status`, `date`) and the conditions sheet (any updatable `ExperimentalConditions` column — the `initial_ph` example above is exactly the issue's own "silently changes from 4 to 9" case) into one entry per `experiment_id`; a brand-new conditions row is not diffed (nothing to have silently overwritten). Additives are reported as a single summary line (`{"field": "additives", "old": "N additive(s)", "new": "M additive(s) provided"}`) rather than per-compound diffed. `conflicts[].kind` is one of `chain_rename_conflict`, `rename_without_overwrite`, `overwrite_old_id_not_found`, `overwrite_nonexistent`, `already_exists`. Every other upload type returns `plan: null` — the schema (`creates`/`renames`/`parent_id`/`copied_from`) is written around `new_experiments.py`'s own concepts (rename, parent-copy) and doesn't generalize cleanly to the other 12 parsers.

**Conflicts reject the whole file (issue #100 item 4, `new-experiments` only):** if `plan.conflicts` is non-empty the entire upload is rolled back — including rows that would have succeeded. The response is still `200` with `created`/`updated`/`skipped` all `0`, one `errors` entry per conflict formatted `Row <n>: [<kind>] <detail>`, and a `message` of `Upload rejected: N problem(s) must be resolved; no changes applied` (`would be rejected` under `dry_run`). `plan` is returned **in full**, including the `creates` that were refused, so the researcher can see what the file would have done and fix it. Partial application is what turned the 2026-07-28 rename incident into a 149-row reconciliation; a skip (e.g. a blank `experiment_id`) is *not* a conflict and does not block the commit. Parser-level `errors` are not folded into this gate — that path is unchanged.

**`plan_hash` preview→commit handshake (issue #100 item 5, `new-experiments` only):** every `new-experiments` response carries `plan_hash`, a sha256 over the plan's `creates`/`renames`/`overwrites`/`skips`/`conflicts` (`counts` is excluded as derived; list order is preserved because rename ordering is meaningful). Pass it back as a `plan_hash` form field on the real submit and the freshly computed plan must match, or the upload is rejected and rolled back with an error telling the user to preview again.

`plan_hash` is **verified when supplied, not required** — the issue text asked for it to be mandatory, but that would break every existing caller, so omitting it preserves the pre-existing behavior exactly. The UI path always sends it.

Because `overwrites[].fields_changed` records the *current* database values as `old`, the fingerprint covers **DB state as well as file bytes** — so it also catches another researcher changing the underlying experiments between preview and commit, not just an edited workbook.

```
POST /api/bulk-uploads/new-experiments   file=<xlsx>  dry_run=true
  → 200 { "dry_run": true, "plan": {...}, "plan_hash": "a1b2…" }
POST /api/bulk-uploads/new-experiments   file=<same xlsx>  plan_hash=a1b2…
  → 200 { "created": 12, ... }              # plan unchanged, committed
  → 200 { "created": 0, "errors": ["Plan changed since preview: …"] }   # file or DB changed
```

Note: the legacy Streamlit uploader (`legacy/streamlit_frontend/bulk_uploads.py`) calls the service directly via `bulk_upsert_from_excel` and is not covered by either gate.

### Bulk experiment deletion (issue #109, Phase 1)

`POST /api/bulk-uploads/experiment-deletion` takes a `.xlsx`/`.xls`/`.csv` file with a
single `experiment_id` column and **hard-deletes** each listed experiment via
`experiment_deletion.delete_experiment_cascade` — the same irreversible purge as
`DELETE /api/experiments/{experiment_id}` (see `MODELS.md`). There is **no preview,
no `dry_run` and no `plan_hash` gate**: the deliberate Phase 1 trade-off is speed for
one trusted user cleaning up a known list. Phase 2 adds the preview-first flow.

- **Access:** the handler's first statement compares `current_user.email` (case-insensitively)
  against `BULK_DELETE_ALLOWED_EMAIL` in `backend/api/routers/bulk_uploads.py` and raises
  **403** otherwise. This is a hardcoded single address, not a role check — the frontend row
  is visible to everyone and the 403 is the only gate.
- **Partial success is intended.** `delete_experiment_cascade` commits per row, and each row
  runs inside its own SAVEPOINT, so one unusable row is unwound and reported without
  discarding the deletions that already succeeded.
- **Unknown IDs do not fail the request** — they come back in `missing` so a typo cannot
  block a cleanup batch.
- **Audit:** every deleted experiment still gets its `ModificationsLog` row with
  `experiment_fk = NULL`. That row is the only surviving trace; the snapshot in `old_values`
  is a record of what was deleted, not a restore point.
- **No batch size cap** in Phase 1.

Response is the standard `UploadResponse`, reinterpreted: `updated` = deletions,
`skipped` = IDs not found, `errors` = `"<id>: <reason>"` per failed row. The itemized
lists are in `feedbacks[0]` as `{deleted: [...], missing: [...], failed: [{experiment_id, error}]}`
and repeated in `warnings` for display.

```
POST /api/bulk-uploads/experiment-deletion   file=<xlsx with experiment_id column>
  → 403 { "detail": "Bulk experiment deletion is restricted to the data owner." }
  → 200 { "updated": 12, "skipped": 1, "errors": ["HPHT_099: <reason>"],
          "feedbacks": [{"deleted": [...], "missing": ["HPHT_TYPO"], "failed": [...]}] }
```

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/bulk-uploads/master-results` | Master Results upload. `file` required — the no-file SharePoint sync mode and the GET/PATCH /master-results/config endpoints were removed (issue #74). Runs calc engine on affected `ScalarResults`. Rows may carry either a full replicate ID (`SERUM_001a`) or a base ID plus an optional `Replicate` column (letter `a`–`z`, or `0`/blank for the group parent). Base + letter is resolved to the sibling experiment before upsert; unresolved or conflicting rows produce per-row errors in `errors`/`feedbacks` without aborting the upload. Replicate siblings are never auto-created by result uploads. |
| POST | `/api/bulk-uploads/scalar-results` | Bulk-create/update `ScalarResults` rows from Excel template. Runs calc engine. Rows may carry either a full replicate ID (`SERUM_001a`) or a base ID plus an optional `Replicate` column (letter `a`–`z`, or `0`/blank for the group parent). Base + letter is resolved to the sibling experiment before upsert; unresolved or conflicting rows produce per-row errors in `errors`/`feedbacks` without aborting the upload. Replicate siblings are never auto-created by result uploads. |
| POST | `/api/bulk-uploads/new-experiments` | Create `Experiment` + `ExperimentalConditions` rows in bulk. Returns a structured `plan` + `plan_hash` (see above). Any conflict in the plan rejects the whole file; optional `plan_hash` form field enforces the preview→commit handshake. |
| POST | `/api/bulk-uploads/icp-oes` | Import raw ICP-OES instrument CSV. |
| POST | `/api/bulk-uploads/xrd-mineralogy` | Unified XRD upload — auto-detects Aeris or ActLabs format. |
| POST | `/api/bulk-uploads/timepoint-modifications` | Bulk-set `brine_modification_description` on result rows. Writes audit log. |
| POST | `/api/bulk-uploads/rock-inventory` | Create/update `SampleInfo` records. Normalises sample IDs to uppercase, no underscores. |
| POST | `/api/bulk-uploads/chemical-inventory` | Create/update `Compound` (reagent) records. |
| POST | `/api/bulk-uploads/elemental-composition` | Import wide-format elemental composition into `ElementalAnalysis`. Query param: `default_unit` (auto-creates unknown analytes). |
| POST | `/api/bulk-uploads/actlabs-rock` | Import ActLabs geochemical analysis reports (Excel or CSV). Heuristic header detection. |
| POST | `/api/bulk-uploads/experiment-status` | Per-row status/date/reactor update. HPHT/Core Flood rows set to ONGOING with a reactor_number auto-complete an older occupant in the same reactor (date-gated); no blanket "complete unlisted HPHT" behavior. |
| POST | `/api/bulk-uploads/pxrf` | Import pXRF readings from instrument export. |
| POST | `/api/bulk-uploads/experiment-deletion` | **Hard-deletes** every experiment in the file's `experiment_id` column. **403 for anyone but `mhearl@addisenergy.com`** (see below). |
| GET | `/api/bulk-uploads/templates/{upload_type}` | Download Excel template. `upload_type`: `scalar-results`, `new-experiments`, `xrd-mineralogy`, `timepoint-modifications`, `rock-inventory`, `chemical-inventory`, `elemental-composition`, `experiment-status`, `experiment-deletion`. Returns 404 for types with no template. |
| GET | `/api/experiments/next-ids` | Returns `{"HPHT": N, "Serum": N, "CF": N}` — next experiment number per type. Used by New Experiments card. |

## Interactive Docs

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
