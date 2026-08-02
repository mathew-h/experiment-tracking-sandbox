# Replicate group view: dead base-experiment link, split list grouping, rename lineage loss

**Priority:** High
**Type:** bug + feature
**Areas:** `backend/api/routers/experiments.py`, `database/lineage_utils.py`, `database/event_listeners.py`, `frontend/src/pages/ExperimentDetail/`, new `frontend/src/pages/ReplicateGroup/`
**Schema change:** none. No migration, no new dependency.

---

## Problem

On the detail page for a lettered replicate, the header renders `Replicate b of SERUM_Catalyst_020` with the base ID as a link. Clicking it 404s and the page renders `Experiment not found`, because no experiment row named `SERUM_Catalyst_020` exists. Users create replicates almost exclusively as lettered members (`a`, `b`, `c`), so the group parent frequently never exists — making this the common case, not the edge case.

Two further defects share the root cause and should be fixed together.

## Root cause

`base_experiment_id` is a parsed **string** that is not guaranteed to name a row.

`update_experiment_lineage` (`database/lineage_utils.py:269`) unconditionally assigns `experiment.base_experiment_id = base_id` for any derivation. `parent_experiment_fk` is only populated when `find_replicate_group_parent` (`database/lineage_utils.py:84`) actually resolves a row — bare stem, then `-0`, then `-1`. When none exists the member is an "orphan": correct `base_experiment_id`, `parent_experiment_fk = NULL`.

### D1 — dead header link

`frontend/src/pages/ExperimentDetail/index.tsx:~226-236` links to `/experiments/{base_experiment_id}` whenever `replicate_label !== null`, with no check that the target resolves. `GET /api/experiments/{id}` 404s and `index.tsx:151` renders the not-found string.

The sibling data needed to render something useful is **already available**: `GET /{experiment_id}/replicate-group` (`backend/api/routers/experiments.py:~345-354`) already falls back to `base_experiment_id` when the parent row is missing, and the detail page already fetches it into `replicateGroup`. The header simply ignores it.

### D2 — grouped list mode splits orphan sets

`group_replicates` is a `Query(False)` parameter of `list_experiments` (`backend/api/routers/experiments.py:79`, param at 91). Its two blocks — bucketing at 139-163, child attachment at 171-185 — key entirely off `parent_experiment_fk`: the `case` expression at 146-155 picks the bucket, and children are attached by `parent_experiment_fk == exp.id`. An orphan a/b/c set therefore appears as three independent top-level rows rather than one collapsed group — the same "I can't see my replicates together" complaint in a second place.

### D3 — rename does not recompute replicate lineage

`update_experiment_lineage_on_flush` (`database/event_listeners.py:697`) iterates only `session.new`, never `session.dirty`. The PATCH rename branch works around this for exactly one field, and says so in a comment (`backend/api/routers/experiments.py:857-860`): it re-syncs `id_timepoint_days` and nothing else.

Consequence: renaming `SERUM_020` → `SERUM_020b` leaves `replicate_label = NULL` and `parent_experiment_fk = NULL`. The vial is invisible as a replicate — `get_replicate_group` filters on `replicate_label IS NOT NULL`, so it never appears in its own group, and grouped list mode never collapses it with its siblings.

Scope note, verified against the view definition: `v_results_scalar_rollup` groups on `COALESCE(base_experiment_id, experiment_id)` and never references `replicate_label` or `parent_experiment_fk` (`database/event_listeners.py:521-553`). For a rename that keeps the stem (`SERUM_020` → `SERUM_020b`), `base_experiment_id` is already `SERUM_020` and stays correct, so rollup aggregation is **not** affected. Rollup breaks only when a rename changes the stem (`SERUM_020` → `SERUM_030b`), which leaves `base_experiment_id` pointing at the old stem and aggregates the vial into the wrong group. Both failure modes are fixed by the same recompute.

Another rename path already does this correctly and is a working precedent for the fix: `backend/services/bulk_uploads/new_experiments.py:385-392` reassigns `experiment_id` and then calls `update_experiment_lineage(db, experiment)`.

## Locked decisions

1. **No shell/placeholder experiment rows.** The group is addressed by base-ID string, so the link never depends on a row existing. This also fixes every orphan set already in the database with no backfill migration.
2. **The group page is always the link target**, including when the base experiment row does exist. One code path. An existing parent row appears on the group page as replicate 0 with a link to its own detail page.
3. **Read-only.** No group-level editing, no create-replicates action, no outlier toggles. The page carries the notice: *"This is a grouped experiment view — you may only edit individual replicates."*
4. **Divergent conditions are shown as divergent, not averaged or arbitrarily picked.** Conditions should match across replicates but are not enforced to; displaying one member's temperature as "the group's temperature" would be worse than the current bug.
5. **Renaming a group parent that has lettered replicates is blocked** with a `409` naming the affected members. Silently orphaning a whole set is the bug class this issue exists to eliminate.

## Implementation

### Phase 1 — backend group resource

New `backend/services/replicate_groups.py`:

```
resolve_group(db, base_id) -> GroupData
```

- Parent: `find_replicate_group_parent(db, base_id)` so `-0` / `-1` spellings keep working.
- Members: all experiments with `base_experiment_id == base_id` and `replicate_label IS NOT NULL`.
- Ordering: `replicate_label`, then `id_timepoint_days` (NULLs first), then `experiment_number`.
- Shared vs divergent conditions: compare each condition field across members; identical values go to `shared_conditions`, differing field names go to `divergent_fields` and their per-member values ride along on each member.
- Additive summary: read `v_experiment_additives_summary` and `v_experiment_additive_names_summary`. If members disagree, set `additives_diverge = true` and leave the summary fields `NULL`.

New routes in `backend/api/routers/experiments.py`:

- `GET /api/experiments/groups/{base_id}` → `ReplicateGroupDetailResponse`
- `GET /api/experiments/groups/{base_id}/rollup` → `list[RollupTimepointResponse]`

**Declaration order matters.** Both must be registered *before* the `/{experiment_id}` routes; FastAPI matches in declaration order and `/{experiment_id}` would otherwise capture the literal segment `groups`.

Refactor the two existing endpoints into thin wrappers that resolve the base ID and delegate to the shared service:

- `GET /{experiment_id}/replicate-group`
- `GET /{experiment_id}/rollup`

Their response contracts do not change, so existing tests and callers stand.

`ReplicateGroupDetailResponse` (extends the existing `ReplicateGroupMember` shape at `backend/api/schemas/experiments.py:126`):

| Field | Notes |
|---|---|
| `base_experiment_id` | str |
| `parent` | `ReplicateGroupMember \| null` |
| `members` | `list[ReplicateGroupMemberDetail]` |
| `member_count` | int |
| `shared_conditions` | dict of field → value, identical across all members |
| `divergent_fields` | list[str] |
| `additives_summary` | str \| null |
| `additive_names` | str \| null |
| `additives_diverge` | bool |

`ReplicateGroupMemberDetail` adds `id_timepoint_days`, `researcher`, `date`, `result_count`, and a `conditions` sub-object holding only the divergent fields.

Return `404` only when `base_id` matches neither an experiment row nor any `base_experiment_id` value.

**Label uniqueness caveat:** `replicate_label` is **not** unique within a group. A `-t<days>` timepoint vial carries the same letter as its parent vial (`SERUM_001a` and `SERUM_001a-t7` are both label `a`). Nothing — API ordering, React keys, dict keys — may assume one row per letter.

### Phase 2 — group page

New route in `frontend/src/App.tsx`, alongside the existing `/experiments/:id` at line 37:

```
<Route path="/experiments/groups/:baseId" element={<ReplicateGroupPage />} />
```

Three static segments vs two, so no conflict with `/experiments/:id`.

New `frontend/src/pages/ReplicateGroup/index.tsx`:

- **Header** — base ID, member count, experiment type, sample, researcher; the read-only notice from locked decision 3.
- **Members table** — replicate label, experiment ID (links to detail), timepoint if `id_timepoint_days` is set, status, outlier badge, result count, plus one column per divergent field.
- **Shared conditions panel** — `shared_conditions` and the additive summary. Divergent fields render as `varies` and point at the members table. When `additives_diverge`, say so explicitly rather than showing nothing.
- **Rollup** — reuse `GroupedResultsView`.

`GroupedResultsView` refactor (`frontend/src/pages/ExperimentDetail/GroupedResultsView.tsx:45-51`): change the prop from `experimentId` to `baseExperimentId` and point its two queries at the new group endpoints. One component then serves both pages.

At the call site (`ResultsTab.tsx:221`), note that `ResultsTab`'s props are `{ experimentId, experimentFk, idTimepointDays }` (`ResultsTab.tsx:100-108`) — there is no `experiment` object in scope. Use the replicate-group query the tab already issues at `ResultsTab.tsx:116-118` and pass `replicateGroup?.base_experiment_id ?? experimentId`; `ReplicateGroupResponse.base_experiment_id` is non-optional (`backend/api/schemas/experiments.py:136`). Adding a new prop threaded from `index.tsx:391` is the alternative if the query timing proves awkward.

### Phase 3 — detail header group strip

Replace the `Replicate {label} of {link}` block at `frontend/src/pages/ExperimentDetail/index.tsx:~226-236` with:

```
Replicate b · Group SERUM_Catalyst_020 · a [b] c d
```

- Rendered when `experiment.replicate_label !== null || (replicateGroup?.members.length ?? 0) > 0`. Never rendered otherwise, so a standalone experiment offers no group page.
- `Group <base_id>` links to `/experiments/groups/{base_experiment_id ?? experiment_id}`.
- Each chip links to that sibling's detail page; the current experiment's chip is styled inactive and not a link.
- Chips key off `member.id`, never `replicate_label`.
- Chips render whether or not a parent row exists — this is what removes the 404 entirely.

### Phase 4 — rename lineage (D3)

In the rename branch of `update_experiment` (`backend/api/routers/experiments.py:857-860`):

1. Before applying the rename, reject with `409` if the experiment being renamed is a group parent with at least one lettered member, listing the affected experiment IDs (locked decision 5).
2. Replace the `split_timepoint_token` line with a full `update_experiment_lineage(db, exp)` call, which recomputes `replicate_label`, `base_experiment_id`, `parent_experiment_fk`, and `id_timepoint_days` together.
3. If the new ID is a group-parent spelling (no treatment, no letter, sequential in `{None, 0, 1}`), call `update_orphaned_derivations(db, new_stem)` so pre-existing orphans back-link to it.

Do **not** widen the `before_flush` listener to `session.dirty`. That listener runs on every flush for every session and a blanket widening risks reclassifying historical rows — including the documented `-0` / `-1` reclassification gap in `MODELS.md`. Keep the fix scoped to the rename endpoint.

**Accepted limitation:** the `409` parent-rename guard covers only the PATCH endpoint. Bulk upload also renames experiments (`backend/services/bulk_uploads/new_experiments.py:385-392`) and is locked/out of scope, so a lettered set can still be orphaned through that path. Acceptable because that path already calls `update_experiment_lineage`, so the renamed row itself stays correctly classified; only the guard is missing.

### Phase 5 — grouped list mode (D2)

In the two `if group_replicates:` blocks of `list_experiments` (`backend/api/routers/experiments.py:139-163` and `171-185`):

- Bucket lettered members on `COALESCE(base_experiment_id, experiment_id)` instead of `parent_experiment_fk` (replace the `case` expression at 146-155).
- Attach children by `base_experiment_id` match rather than `parent_experiment_fk == exp.id` (171-185).
- When no parent row exists for a bucket, the lowest-ordered member becomes the group's representative row and the remaining members attach as `replicates`.

Separable: phases 1-4 ship without this.

## Acceptance criteria

- [ ] From `SERUM_Catalyst_020b` (or any orphan replicate), clicking the group link renders a group page. No 404, no `Experiment not found`.
- [ ] The group page lists every lettered member, and the parent row as replicate 0 when one exists.
- [ ] Shared conditions and the additive summary display; fields that differ across members show `varies` and appear per-member in the table.
- [ ] The read-only notice is present: "This is a grouped experiment view — you may only edit individual replicates."
- [ ] The rollup chart renders on the group page for a group with no parent row.
- [ ] The detail header shows sibling chips; each navigates to that sibling; the current one is inactive.
- [ ] No group strip appears on a non-replicate experiment.
- [ ] Renaming `SERUM_020` → `SERUM_020b` sets `replicate_label = 'b'` and links `parent_experiment_fk` when a parent exists, and the vial then appears in its replicate group and collapses with its siblings in grouped list mode.
- [ ] Renaming across stems (`SERUM_020` → `SERUM_030b`) rewrites `base_experiment_id` to `SERUM_030`, so the vial aggregates under the correct group in `v_results_scalar_rollup`.
- [ ] Renaming a parent that has lettered replicates returns `409` naming them.
- [ ] With `group_replicates=true`, an orphan a/b/c set collapses to one row (phase 5).
- [ ] Existing `/{experiment_id}/replicate-group` and `/{experiment_id}/rollup` responses are byte-identical to before.

## Test plan

**Backend (pytest)**

- `resolve_group` with: parent present; orphan set with no parent; `-0` / `-1` parent spelling; `-t` vials sharing a letter with their parent vial; members with divergent `temperature_c`; divergent additive sets; unknown base ID → 404.
- Route ordering: `GET /api/experiments/groups/SERUM_001` is not captured by `/{experiment_id}`.
- Rename within the same stem recomputes `replicate_label` and `parent_experiment_fk`; rename across stems also rewrites `base_experiment_id`; rename of a parent with children returns 409; rename to a group-parent spelling back-links existing orphans.
- Wrapper endpoints return unchanged payloads.
- `group_replicates` over an orphan set (phase 5).

**Frontend (vitest)**

- Group page renders an orphan set including the read-only notice.
- Divergent field renders as `varies` and appears as a members-table column.
- Header strip renders correct links; absent for a non-replicate.
- Chips render correctly when two members share a letter (`a`, `a-t7`).
- `GroupedResultsView` queries the group endpoints off a base ID.

**E2E**

- Reproduce the reported failure: open an orphan lettered replicate, click the group link, assert a rendered group page listing the siblings.

## Out of scope

- Group-level editing or condition propagation to members.
- Create-replicates or create-missing-base actions on the group page.
- Retroactive reclassification of historical `-0` / `-1` suffixed experiments (documented gap in `MODELS.md`).
- Any change to `v_results_scalar_rollup` or other reporting views.
- Any change to bulk upload parsers (`backend/services/bulk_uploads/`, locked).

## Docs to update on completion

- `MODELS.md` — note that `base_experiment_id` may not name an existing row, and that the group is addressed by string.
- `docs/api/API_REFERENCE.md` — the two new `groups/` endpoints.
- `docs/user_guide/` — the replicate group view.
