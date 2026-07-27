"""backfill result timepoint buckets

Revision ID: daae92e908f1
Revises: 6a84a5a15592
Create Date: 2026-07-27 11:20:05.036321

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'daae92e908f1'
down_revision: Union[str, None] = '6a84a5a15592'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Issue #83: POST /api/results (the Add Results modal) never set
# time_post_reaction_bucket_days, so every hand-entered result row has a NULL
# bucket and v_results_scalar_rollup lumps a group's whole history into one
# bucket=NULL row. This migration backfills the bucket from
# time_post_reaction_days, rounded to 4 decimals — the same normalization as
# backend/services/result_merge_utils.normalize_timepoint (Postgres ROUND
# half-up vs Python banker's rounding differs only at the 5th decimal, which
# never occurs in real day values).
#
# Because uq_primary_result_per_experiment_bucket is UNIQUE on
# (experiment_fk, time_post_reaction_bucket_days)
# WHERE is_primary_timepoint_result,
# and NULL buckets never conflicted, some experiments may hold several primary
# rows that land in the same bucket after backfill. Those are demoted first,
# keeping the best-ranked row primary: rows with scalar+icp data beat rows
# with either, which beat dataless rows; ties break to the highest id —
# mirroring result_merge_utils._rank_primary_candidate.

DEMOTE_COLLIDING_PRIMARIES_SQL = """
    WITH eff AS (
        SELECT er.id,
               er.experiment_fk,
               COALESCE(er.time_post_reaction_bucket_days,
                        ROUND(er.time_post_reaction_days::numeric, 4)::float8)
                   AS eff_bucket,
               (sr.id IS NOT NULL)  AS has_scalar,
               (icp.id IS NOT NULL) AS has_icp
        FROM experimental_results er
        LEFT JOIN scalar_results sr  ON sr.result_id  = er.id
        LEFT JOIN icp_results   icp ON icp.result_id = er.id
        WHERE er.is_primary_timepoint_result = TRUE
          AND er.time_post_reaction_days IS NOT NULL
    ),
    ranked AS (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY experiment_fk, eff_bucket
                   ORDER BY CASE
                                WHEN has_scalar AND has_icp THEN 0
                                WHEN has_scalar OR  has_icp THEN 1
                                ELSE 2
                            END,
                            id DESC
               ) AS rn
        FROM eff
    )
    UPDATE experimental_results
    SET is_primary_timepoint_result = FALSE
    WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
"""

BACKFILL_BUCKETS_SQL = """
    UPDATE experimental_results
    SET time_post_reaction_bucket_days =
        ROUND(time_post_reaction_days::numeric, 4)::float8
    WHERE time_post_reaction_bucket_days IS NULL
      AND time_post_reaction_days IS NOT NULL
"""


def upgrade() -> None:
    """Backfill NULL timepoint buckets; demote colliding primaries first."""
    op.execute(DEMOTE_COLLIDING_PRIMARIES_SQL)
    op.execute(BACKFILL_BUCKETS_SQL)


def downgrade() -> None:
    # Which buckets were NULL (and which rows were demoted) is not recoverable
    # after the fact. Downgrade is intentionally a no-op, matching
    # 458f344f73d8_clamp_negative_icp_ppm_to_zero.
    pass
