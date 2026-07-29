# Design — Issue #98: sacrificial-timepoint (`-t<days>`) vials break replicate collapsing

**Date:** 2026-07-29
**Issue:** [#98](https://github.com/mathew-h/experiment-tracking-sandbox/issues/98)
**Branch:** `fix/issue-98-t-vial-replicate-collapsing`
**Related:** #81 (`-t<days>` token), #83 (rollup grouping), #87 (group addressing), #90 (H2 ppm rollup)

---

## 1. Problem

Serum vials are sacrificed per timepoint, so one logical replicate spans several
experiment rows differing only by the `-t<days>` token:

| experiment_id | base_experiment_id | replicate_label | id_timepoint_days |
|---|---|---|---|
| `SERUM_001a-t1` | `SERUM_001` | a | 1.0 |
| `SERUM_001a-t3` | `SERUM_001` | a | 3.0 |
| `SERUM_001b-t1` | `SERUM_001` | b | 1.0 |
| `SERUM_001b-t3` | `SERUM_001` | b | 3.0 |

The ID parser and `v_results_scalar_rollup` handle this correctly. Every UI surface
that presents replicate groups does not: the Experiments list picks a day-1 vial as
the identity of the whole set, the replicate badge prints duplicate letters, and the
group view reports 4 replicates where there are 2.

The `-t` token is an internal encoding of a vial's timepoint. It must never be
rendered on the Experiments list page.

## 2. Scope boundary

**In scope:** the Experiments list endpoint and page, the `/groups/{base_id}`
endpoint and page, the grouped results chart, and the condition-divergence scan.

**Out of scope** (unchanged, and correct as-is): the `-t` parser grammar,
`v_results_scalar_rollup` grouping, and `v_results_scalar`'s per-experiment
cumulative partition. No schema change, no migration, no view change.

---

## 3. Decisions

### D1 — The collapse key is the timepoint-stripped `experiment_id`, not `(base, letter)`

The issue proposes bucketing ungrouped rows by `(base_experiment_id, replicate_label)`.
**That key is wrong.** `parse_lineage_fields("SERUM_001a-2")` returns
`("SERUM_001", 2, None, "a")` (`database/experiment_id_parser.py:157-158`), so a
sequential re-run of a lettered replicate shares both base and letter with
`SERUM_001a`, and there is no persisted derivation-number column to separate them.

| experiment_id | `(base, letter)` — wrong | stripped ID — correct |
|---|---|---|
| `SERUM_001a` | `SERUM_001\|a` | `SERUM_001a` |
| `SERUM_001a-t3` | `SERUM_001\|a` | `SERUM_001a` |
| `SERUM_001a-2` | `SERUM_001\|a` — merged | `SERUM_001a-2` — separate |

The stripped-ID key is a literal reading of the issue's own stated rule ("collapse
only when rows differ solely by timepoint") and additionally handles letterless
`-t` vials (`SERUM_001-t7` collapses with `SERUM_001`) with no special case.

**Computed inline in SQL** as `regexp_replace(experiment_id, '-t[0-9]+(\.[0-9]+)?$', '')`
— no new column, no migration, nothing to backfill or keep in sync. Postgres-specific,
which is acceptable: production is Postgres-only.

The cost is one new copy of the timepoint-token pattern, bringing the total to
**three**: the canonical Python regex (`database/experiment_id_parser.py:69`), the
TypeScript mirror (`frontend/src/utils/experimentId.ts:4`), and this POSIX form for
Postgres. Python-side stripping reuses the canonical
`split_timepoint_token` rather than adding a fourth, and a test asserts the SQL and
Python forms agree across every ID shape the grammar produces.

### D2 — Row identity is a new `group_display_id` field; `experiment_id` stays truthful

`experiment_id` on a list item continues to name the real representative row. A new
nullable `group_display_id` carries what the ID column should render. Rejected
alternative: overwriting `experiment_id` with the stem — the item would stop naming a
real row (`SERUM_001` frequently has no row at all), which breaks anything that
navigates or PATCHes by that field, and breaks
`tests/api/test_experiments.py:1046`.

### D3 — Status is read-only on any row covering more than one vial

`ExperimentRow` renders a live `<select>` that PATCHes `exp.experiment_id`
(`frontend/src/pages/ExperimentList.tsx:335-337`). Once a row is labeled `SERUM_001`
but backed by one representative vial, changing status there would silently write to
one of four vials. Collapsed rows therefore render a read-only `StatusBadge`; the
editable dropdown remains on single-vial rows and on expanded child rows. Writing to
every vial in the row was rejected as needing a bulk endpoint plus per-vial
`ModificationsLog` entries — more scope than #98 describes.

### D4 — `member_count` keeps its per-vial meaning; letter data is added, not substituted

The issue proposes redefining `member_count` to mean letters. That changes the
meaning of a shipped field while `members` still holds vials, so `member_count` would
no longer equal `len(members)`. Instead: `members` and `member_count` are untouched,
and `replicates` + `replicate_count` are added.

### D5 — A vial with no `conditions` row is excluded from the divergence scan

`_compare_conditions` currently treats a missing `conditions` row as `None` for every
field (`backend/services/replicate_groups.py:108-110`), which pushes nearly every
field into `divergent_fields` as soon as one sacrificial vial lacks conditions. Such
vials are now skipped entirely. Within a vial that *does* have a conditions row, a
NULL field still counts as a real value that can differ — field-by-field NULL
skipping was rejected because it would display a value recorded on one vial and never
recorded on another as "shared".

### D6 — The comparison grain stays per-vial

The issue proposes comparing "vials sharing a letter as one unit". Rejected: if
`SERUM_001a-t1` and `SERUM_001a-t3` genuinely differ on `rock_mass_g` (each vial
weighed separately), that is real data a researcher should see in the members table,
and collapsing it because the two vials share a letter hides it. D5 alone satisfies
the acceptance criterion about `shared_conditions`.

### D7 — `is_outlier ASC` leads the representative-ordering clause in the list endpoint

Added at `backend/api/routers/experiments.py:206-210` (grouped rank) and to the new
ungrouped stem window, so a flagged vial is never chosen to represent a collapsed row
while a clean sibling exists. This matters because the representative supplies the
Sample/Additives/Date columns (D9).

**Deliberately not applied to `backend/services/replicate_groups.py:87-89`**, the
other clause the issue's test gap 8 names. That `order_by` feeds the members table's
*display* order, not a representative choice — and under D10 the group page needs no
canonical vial at all (a single-vial letter renders that vial; a multi-vial letter
renders the letter with its vials nested beneath). Adding `is_outlier ASC` as the
leading term there would sort every flagged vial to the end of the list, breaking
letter adjacency; adding it after `replicate_label` would shuffle a letter's vials out
of day order. Neither buys anything, so the display order stays
`replicate_label, id_timepoint_days NULLS FIRST, experiment_number` as today. Test gap
8 is closed by the list-endpoint half, which is where the bug it describes lives.

### D8 — `replicates` on a grouped list item lists all letter-rows, not siblings

Required for the badge to read `2 replicates: a, b`; since the row is now labeled by
stem, the representative's own letter belongs in the expanded list. Behavior changes
only for orphan lettered sets — parent-having groups are already equivalent, because
`members` requires `replicate_label IS NOT NULL` and so never contains the parent.

### D9 — The representative vial supplies the non-identity columns

For a collapsed row, Sample, Reactor, Date, Description, and Additives come from the
representative vial — after D7, the earliest clean vial of the lowest letter. Stated
in a code comment at the point of construction.

### D10 — Single-vial letters and stems render exactly as today

The regression guard is structural rather than incidental: a letter or stem with
exactly one vial renders with a linked ID, `T+N`, result count, and divergent cells,
and gains no expand affordance. Only multi-vial letters and stems enter the new
nesting paths, so data with no `-t` vials cannot regress.

### D11 — Outlier vials contribute no points to a letter's chart series

Matches `v_results_scalar_rollup`'s P4 outlier exclusion, so the individual-replicate
overlay and the mean ± sd line agree on what counts. Outlier vials remain reachable
as struck-through drill-in links. With `-t` vials a letter can be partly flagged, so
marking a whole letter as outlier (today's behavior) would taint an otherwise-good
replicate.

### D12 — The list collapses by stem; the group page nests by letter

A deliberate asymmetry. `SERUM_001a-2` gets its own list row (it is not a timepoint
variant of `SERUM_001a`) but sits under letter `a` on the group page (it is still
replicate `a`). Consequence to document: for a group containing a letter + sequential
re-run, the badge counts letters while the expansion shows one row per stem, so
"2 replicates: a, b" can expand to three rows. Rare and honest.

---

## 4. Design

### 4.1 New module — `backend/services/replicate_collapse.py`

Pure exports, all about the stem key and nothing else:

- `TIMEPOINT_TOKEN_SQL_PATTERN` → the POSIX form of the token pattern.
- `timepoint_stem_expr(col)` → the D1 `regexp_replace` SQLAlchemy expression, usable
  against either the `Experiment` class or a subquery's `.c` collection, matching the
  existing `_bucket_key_expr(col)` convention in `experiments.py`.
- `collapse_by_stem(rows)` → `StemGroup(stem, representative, vial_count)` per stem,
  for the Python-side collapse of a grouped row's letter children.

Letter grouping (`group_vials_by_letter`) lives in `replicate_groups.py` instead,
next to the `GroupMemberData` dataclass it operates on — putting it here would
either invert the dependency or force duck typing.

The module docstring records the three-way pattern duplication from D1 and names the
test that guards it.

### 4.2 List endpoint — `backend/api/routers/experiments.py`

Four additive fields on `ExperimentListItem`:

| Field | Type | Grouped mode | Ungrouped mode |
|---|---|---|---|
| `group_display_id` | `Optional[str]` | bucket stem (`SERUM_001`) | timepoint-stripped stem (`SERUM_001a`) |
| `replicate_letters` | `Optional[list[str]]` | distinct letters in the group | `None` |
| `vial_count` | `int` (default 1) | vials in the bucket | vials collapsed into this row |
| `replicates` | `Optional[list[Item]]` | **all** letter-rows (D8) | `None`, as today |

**Ungrouped branch** gains a window over the D1 stem key with
`row_number() ... ORDER BY is_outlier ASC, id_timepoint_days ASC NULLS FIRST, experiment_number ASC`,
and `total` becomes the distinct-stem count. Rows whose stem is unique are unaffected.

Two behaviors this branch fixes explicitly, because both are ambiguous in the issue:

- **Collapsing happens among matched rows only.** Unlike the grouped branch — which
  deliberately resolves bucket membership from the *unfiltered* table so that
  filtering to `b` still resolves representative `a` (`experiments.py:167-177`) —
  ungrouped mode collapses only rows that passed the filters. Searching `t3` therefore
  yields `SERUM_001a` and `SERUM_001b` with `vial_count = 1` each, not rows claiming
  vials the filter excluded.
- **`vial_count` counts the rows the displayed row stands for**: in ungrouped mode, the
  matched rows sharing its stem; in grouped mode, every row in the bucket, parent
  included. It is `1` for an ordinary standalone experiment.

An ungrouped collapsed row still navigates to `/experiments/{experiment_id}` — the
representative vial's detail page. So a row displaying `SERUM_001a` opens
`SERUM_001a-t1` when no bare `SERUM_001a` row exists. This is intended: there is no
per-letter detail page, and the group page is reachable from grouped mode. The
representative is the earliest clean vial (D7), which is the most useful landing point.

**Grouped branch** keeps its existing `_bucket_key_expr` logic for bucketing and
`total`; only the rank ordering changes (D7). `replicates` is built by collapsing the
bucket's lettered members on the D1 stem key.

Both counts stay in SQL. Collapsing in the frontend is not an option: `total` and
pagination are computed server-side, and the `#64` comment at `experiments.py:122-126`
documents that filtering after `offset/limit` produced wrong totals and empty first
pages.

### 4.3 Group endpoint — `replicate_groups.py` + `schemas/experiments.py`

New schema:

```python
class ReplicateLetterGroup(BaseModel):
    replicate_label: str
    vials: list[ReplicateGroupMemberDetail]
```

`ReplicateGroupDetailResponse` gains `replicates: list[ReplicateLetterGroup]` and
`replicate_count: int`. `members`, `member_count`, `shared_conditions`,
`divergent_fields`, and the additives fields are unchanged (D4). `parent` widens from
`ReplicateGroupMember` to `ReplicateGroupMemberDetail` — additive, and it stops the
parent row hard-coding `—` in its Timepoint / Results / divergent cells
(`ReplicateGroup/index.tsx:81,85,88`).

`_compare_conditions` implements D5. Vials skipped from the scan still receive a
per-member divergent map (all divergent fields → `None`) so their table cells render
`—` rather than crashing the lookup. When *every* vial lacks a conditions row the
function returns empty shared/divergent, as it does today for an empty member list.

`_fetch_members` keeps its per-vial contract and its display ordering unchanged — see
D7 for why `is_outlier` is deliberately not added here.

### 4.4 Frontend

**`ExperimentList.tsx`** — render `exp.group_display_id ?? exp.experiment_id`; delete
the `day N` chip (`:308-312`); build the badge from `replicate_letters` rather than
`replicates.length` (`:232`); navigate group rows to
`/experiments/groups/{group_display_id}` instead of the representative's detail page
(`:300`); render Status as a read-only `StatusBadge` when the row covers more than one
vial (D3). A row is treated as a group when `replicates` is non-empty; it is treated
as multi-vial when `replicates` is non-empty **or** `vial_count > 1`.

**`ReplicateGroup/index.tsx`** — members table renders from `replicates`: one row per
letter, expandable to its vial rows. `T+{N}` and `result_count` move to the vial
sub-rows. Header count reads `replicate_count`. Per D10, a letter with one vial
renders as a plain row identical to today's.

**`GroupedResultsView.tsx`** — `seriesEntities` becomes one entry per letter, its
points concatenated from that letter's non-outlier vials' result rows (D11), sliced to
`chartColors.series.length` by letter so a 2×5 study consumes 2 slots rather than 10.
The drill-in link row continues to list every vial so each vial's data stays reachable.

### 4.5 Docs

`.claude/rules/MODELS.md` — the `id_timepoint_days` and `v_results_scalar_rollup`
sections state the letter-vs-vial distinction and which surface presents which grain.
`docs/api/API_REFERENCE.md` — the new list-item and group-response fields.

---

## 5. Testing

The issue's seven gaps, each as a named test:

1. Grouped list, 2 letters × 2 timepoints, no parent → `total == 1`,
   `group_display_id == "SERUM_001"`, `replicate_letters == ["a","b"]`.
2. Ungrouped list, same set → exactly 2 rows, `group_display_id`
   `SERUM_001a` / `SERUM_001b`.
3. `/groups/{base_id}` → `replicate_count == 2` and `member_count == 4`.
4. `divergent_fields` / `additives_diverge` with a `-t` vial that has no
   `conditions` row → conditions shared across the rest stay in `shared_conditions`.
5. `/{experiment_id}/replicate-group` member order is deterministic for duplicate
   labels.
6. `result_count` per `-t` vial in the group response.
7. Grouped-list pagination with a multi-timepoint set.
8. An `is_outlier` `-t` vial is not chosen as a collapsed row's representative.

Plus, as first-class regression guards: a no-`-t` dataset renders identically in both
list modes (D10), and `SERUM_001a-2` stays a separate row from `SERUM_001a` (D1).

Frontend: no `-t` substring and no `day N` chip anywhere in the rendered list; Status
renders read-only on a collapsed row and editable on a single-vial row; the chart
draws one series per letter.

**Two existing tests change**, both asserting behavior the issue identifies as the bug:

- `tests/api/test_experiments.py::test_orphan_lettered_set_collapses_to_one_row` —
  `replicates` labels `["b","c"]` → `["a","b","c"]` (D8).
- `tests/api/test_experiments.py::test_timepoint_variant_shares_letter_no_dedupe` —
  rewritten from asserting duplicate `["a","a"]` labels to asserting one collapsed
  letter row.

---

## 6. Discovered, deferred to a follow-up issue

`_fetch_members` requires `replicate_label IS NOT NULL`, so a **letterless** `-t` vial
(`SERUM_001-t7`) never appears on the group page — yet `v_results_scalar_rollup`
groups it under `SERUM_001` and counts it in `n_replicates`. The rollup table and the
members table therefore disagree about who is in the group.

**The list half is fixed here, because D1 forces it.** `_bucket_key_expr`'s `else_`
branch buckets non-lettered rows on their raw `experiment_id`, so once rows are
labeled by stem a letterless `-t` vial would render as a *second* top-level row
carrying the same visible label as the real `SERUM_001` row. That branch therefore
strips the token too, and the vial joins its parent's bucket. A no-op for every ID
without a token, so no existing bucket moves.

**The group-page half is deferred**: whether such a vial belongs in `members`
requires deciding what a letterless timepoint vial *is* (group parent? unlettered
replicate?), which is orthogonal to the 2×2 repro. File as its own issue.

---

## 7. Acceptance criteria (from the issue)

- [ ] No `-t<days>` substring and no `day N` chip anywhere on `/experiments`.
- [ ] Grouped: the 2×2 set renders one row labeled `SERUM_001`, badge
      `2 replicates: a, b`, linking to `/experiments/groups/SERUM_001`.
- [ ] Ungrouped: the same set renders exactly two rows, `SERUM_001a` and `SERUM_001b`.
- [ ] Data with no `-t` vials renders identically to today in both modes.
- [ ] `GET /api/experiments/groups/SERUM_001` reports 2 replicates and 4 vials,
      distinguishably.
- [ ] The group view lists `a` and `b`, each expandable to `t1` and `t3` with each
      vial's H2 values.
- [ ] Rollup table and chart still show two buckets with `n_replicates = 2` each;
      the individual-replicate overlay draws 2 series, not 4.
- [ ] Conditions shared across all four vials appear in `shared_conditions`, not
      `divergent_fields`.
