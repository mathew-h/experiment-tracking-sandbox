# Reference docs still describe a dead view: `v_primary_experiment_results`

**Labels:** `docs`, `database`
**Depends on:** nothing
**Blocks:** nothing

## Problem

`.claude/rules/MODELS.md`, `.claude/MEMORY.md`, and — most visibly — the team-facing
`docs/user_guide/ONBOARDING.md` all document `v_primary_experiment_results` as a live,
queryable reporting view: the recommended "main fact table" / "base table" for Power BI
and direct SQL reporting.

It does not exist. `database/event_listeners.py` (lines 653–671) builds the current set of
reporting views from a `_VIEWS` list of 13 entries — `v_primary_experiment_results` is not
among them. Instead, the same block runs this unconditionally, on every app startup, right
before recreating the real views:

```python
conn.execute(text("DROP VIEW IF EXISTS v_primary_experiment_results CASCADE;"))
```

So on any environment that ever had it, it gets dropped and never recreated. Three Alembic
migrations (`db1fb7a6f449_dropped_field_analysis_date.py`,
`bcecaa35be9c_add_ca_column.py`, `6bd58ee7bf51_normalized_time_buckets.py`) also drop it as
part of their pre-batch-operation cleanup, each with a comment along the lines of
"`v_primary_experiment_results` is recreated by `event_listeners.py` on app startup" — which
was true at some earlier point in the view's history but is not true of the current
`_VIEWS` list. Nobody remembered to update the three docs above when the view was retired
from that list.

**Highest-impact instance:** `docs/user_guide/ONBOARDING.md` lines 105 and 120 tell new
team members connecting Power BI to "start with `v_primary_experiment_results` as your base
table" because "it already resolves the primary result per timepoint." A researcher
following that instruction today will not find the view. This is the exact audience
(non-developer researchers, first contact with the database) most likely to hit this and
have no idea whether they're the one making a mistake or the doc is wrong.

`docs/working/issues/03-expose-h2-ppm-api-and-rollup.md` (an already-merged issue) also
lists "Adding H2 ppm to `v_primary_experiment_results`" as explicitly out of scope, on the
assumption it exists and already exposes `h2_concentration` — showing the stale assumption
has been load-bearing in at least one other completed piece of work, though harmlessly in
that case (the view didn't need touching either way since it doesn't exist).

## Correct replacement pattern

The view's job — one flattened row per primary result timepoint, scalar + H2 + ICP data all
present — is now split across three views, joined on `result_id`:

```sql
SELECT s.experiment_id, s.time_post_reaction_days,
       s."gross_ammonium_concentration_mM", s.net_ammonium_concentration, s.final_ph,
       h.h2_concentration, h.h2_micromoles, h.h2_grams_per_ton_yield,
       i.fe_ppm, i.ni_ppm, i.cu_ppm  -- etc., all icp.*_ppm columns
FROM v_results_scalar s
LEFT JOIN v_results_h2  h ON h.result_id = s.result_id
LEFT JOIN v_results_icp i ON i.result_id = s.result_id
WHERE s.experiment_id = '<experiment_id>'
ORDER BY s.time_post_reaction_days;
```

`LEFT JOIN` (not `JOIN`) matters: `v_results_h2` excludes rows with no H2 measurement, and
`v_results_icp` only includes rows with ICP data — an inner join silently drops timepoints
that have scalar data but not both of the others yet. `v_dim_timepoints` is also available
as the shared time-axis dimension if a report needs to join in from that direction instead
(see `docs/POWERBI_MODEL.md`).

This replacement pattern is already written up, with verified column names and worked
examples, in `docs/PSQL_ACCESS.md` (added in this same PR) — that section can be copied
into MODELS.md largely as-is.

## Docs to fix

- **`.claude/rules/MODELS.md`** — remove or rewrite the `### v_primary_experiment_results`
  section (currently ~lines 205–223 as of this branch); update the `is_outlier` bullet
  (~line 21) which lists `v_primary_experiment_results` alongside
  `v_results_scalar`/`v_results_h2`/`v_results_icp` as a per-row view it stays visible in —
  it should drop from that list, since it no longer exists as a per-row view at all.
- **`.claude/MEMORY.md`** — the "Reporting Views (Power BI Integration)" section
  (~lines 132–141) documents it as a live view with its own column list; needs the same
  correction or removal.
- **`docs/user_guide/ONBOARDING.md`** — lines ~105 and ~120 actively instruct new
  Power-BI/reporting users to use it as their base table. This is the one that should be
  fixed first/most carefully, since it's the doc actual humans read before touching the
  database. Replace with guidance to start from `v_results_scalar` (or the join pattern
  above) instead. Note: `docs/project_context/ONBOARDING.md` is an auto-synced mirror of
  this file (per the `PostToolUse` hook in `.claude/CLAUDE.md` §10) — fixing the source and
  letting the hook re-sync is sufficient; don't hand-edit the mirror.

## Docs intentionally left alone (historical, not living reference)

- `docs/working/issue-log.md` — append-only log of completed work; entries describe what
  was true/assumed at the time and shouldn't be retroactively rewritten.
- `docs/working/issues/03-expose-h2-ppm-api-and-rollup.md` — a completed issue draft; same
  reasoning.
- `docs/superpowers/plans/*.md` — point-in-time implementation plans, excluded from
  `docs/project_context/` sync by design (`.claude/CLAUDE.md` §10), not treated as living
  documentation.
- `alembic/versions/*.py` (the three migrations that drop the view) — this is legitimate
  migration history; the `DROP VIEW IF EXISTS ... CASCADE` calls are correct as written and
  must not be edited (migration files are locked per `docs/LOCKED_COMPONENTS.md`). Only the
  stale in-file *comments* claiming it gets "recreated by event_listeners.py on app
  startup" are inaccurate, and migration files aren't the place to fix that — it's noted
  here for awareness only, no action proposed.

## Acceptance criteria

- [ ] `\dv` (or `SELECT * FROM pg_views WHERE viewname = 'v_primary_experiment_results'`)
      confirms the view does not exist in the current schema — already true, just the
      starting assumption to verify before editing docs
- [ ] `.claude/rules/MODELS.md` no longer describes `v_primary_experiment_results` as an
      existing view
- [ ] `docs/user_guide/ONBOARDING.md` points Power BI / reporting users at the
      `v_results_scalar` + `v_results_h2` + `v_results_icp` join (or equivalent) instead
- [ ] `.claude/MEMORY.md`'s reporting-views section no longer lists it as live
- [ ] No change to `database/event_listeners.py`, `alembic/versions/`, or any other code —
      this is a documentation-only correction

## Tests

- [ ] None (documentation only)

## Out of scope

- Recreating `v_primary_experiment_results` — the split into `v_results_scalar` /
  `v_results_h2` / `v_results_icp` is the intended current design (per `docs/POWERBI_MODEL.md`),
  not a regression to reverse
- Any change to `alembic/versions/` migration files
- Auditing `docs/superpowers/plans/` or `docs/working/issue-log.md` for every other stale
  reference in point-in-time artifacts
