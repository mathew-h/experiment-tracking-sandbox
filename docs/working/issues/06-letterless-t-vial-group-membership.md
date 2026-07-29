# Letterless `-t` vials are counted in the rollup but absent from the group page

**Labels:** `bug`, `backend`, `replicates`
**Split out of:** #98
**Filed as:** #101 (2026-07-29)

## Summary

`_fetch_members` (`backend/services/replicate_groups.py:98-109`) requires
`replicate_label IS NOT NULL`, so a letterless timepoint vial such as
`SERUM_001-t7` never appears in the group page's members table. But
`v_results_scalar_rollup` groups on `COALESCE(base_experiment_id, experiment_id)`,
which resolves to `SERUM_001`, so that vial IS counted in `n_replicates`. The
rollup table and the members table therefore disagree about who belongs to the
group.

## What #98 already fixed

Issue #98 fixed the **list-page half**, because its stem-labeling forced it:
`_bucket_key_expr`'s `else_` branch now strips the `-t` token, so a letterless
vial joins its parent's row instead of rendering as a second top-level row
displaying the same label. That change had to be paired with the hand-written
Python `bucket_key` mirror in the item loop — the two diverged during
implementation and the result was worse than the original bug: a letterless `-t`
vial hid its lettered siblings from the list response entirely (fixed in
`a76659e`).

## What remains

The **group-page half**. It needs a semantic decision before any code:
is a letterless `-t` vial a group parent, an unlettered replicate, or something
else? Until that is settled, `_fetch_members`' `replicate_label IS NOT NULL`
filter cannot be safely relaxed — dropping it would pull sequential re-runs and
treatment variants into the members table too.

## Acceptance criteria (draft)

- [ ] Decide and document what a letterless `-t` vial is, in `.claude/rules/MODELS.md`.
- [ ] The group page's member list and `v_results_scalar_rollup`'s `n_replicates`
      agree on group membership for a base ID that has a letterless `-t` vial.
- [ ] Relaxing the `_fetch_members` filter does not pull in sequential re-runs
      (`SERUM_001-2`) or treatment variants (`SERUM_001_Desorption`).

## References

- `docs/superpowers/specs/2026-07-29-issue-98-t-vial-replicate-collapsing-design.md` §6
- `.claude/rules/MODELS.md` — `id_timepoint_days`, `v_results_scalar_rollup` "Known gap"
