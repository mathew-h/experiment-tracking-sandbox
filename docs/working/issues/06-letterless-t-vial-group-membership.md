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

Nothing — fixed 2026-08-11 on `fix/issue-101-letterless-t-vial-groups`.

The semantic decision was made by the issue owner: **a letterless `-t` vial is
one destructively-sampled instance of the stem itself, not a replicate.** So the
set forms a group whose members are those vials, with `replicate_count = 0`.

## How it presented

Filed as a members-table/rollup *disagreement*, which undersold it. Because
issue #98's list-page collapsing already merged these vials into one row, and
that row's only link was to its representative vial, a letterless set had **no
reachable group page at all**: `/groups/{base}` and `/groups/{base}/rollup` both
404'd, and `GroupedResultsView` rendered that 404 as "No primary results to
aggregate yet." So the researcher saw one experiment where there were four, and
was told there was no data when there was. Measured in the dev DB: 13 stems
affected, 8 of them with more than one vial.

The mixed case this issue was written around (letterless `-t` vials *plus*
lettered members under one stem) has **zero** instances in the dev DB — the
all-letterless set is what actually bites.

## Acceptance criteria

- [x] Decide and document what a letterless `-t` vial is, in `.claude/rules/MODELS.md`
      (under `id_timepoint_days`, plus the `v_results_scalar_rollup` note that
      previously recorded this as a known gap).
- [x] The group page's member list and `v_results_scalar_rollup` agree on group
      membership for a base ID that has a letterless `-t` vial.
      (`n_replicates` no longer exists — it was replaced by `n_vials` /
      `n_replicate_letters` / `n_values` on 2026-08-01.)
- [x] Relaxing the `_fetch_members` filter does not pull in sequential re-runs
      (`SERUM_001-2`) or treatment variants (`SERUM_001_Desorption`) — nor
      `SERUM_001-2-t0` / `SERUM_001_Desorption-t5`, which carry both the stem as
      their `base_experiment_id` and a `-t` token, and so would have been adopted
      by a filter keyed on `id_timepoint_days IS NOT NULL`. Membership is keyed on
      the timepoint-stripped `experiment_id` instead (`_member_clause`).

## Fixed beyond the filed scope

- `/experiments` routes a letterless multi-vial row to its group page and shows a
  "N vials" chip — the row previously looked identical to a standalone experiment
  while silently disabling its own status dropdown.
- The detail page offers **Grouped (n=N)** and a **Group** link for a letterless
  vial; both were gated on the letter-only `/{id}/replicate-group` wrapper, which
  is pinned and was left untouched.
- `GroupedResultsView` distinguishes a failed fetch from an empty result.
- A NULL `sd` renders as the mean alone instead of "± 0.0" (a fabricated zero
  spread on a single reading), and the error bars and "mean ± sd" legend are
  omitted when no spread exists.

## References

- `docs/superpowers/specs/2026-07-29-issue-98-t-vial-replicate-collapsing-design.md` §6
- `.claude/rules/MODELS.md` — `id_timepoint_days`, `v_results_scalar_rollup` "Known gap"
