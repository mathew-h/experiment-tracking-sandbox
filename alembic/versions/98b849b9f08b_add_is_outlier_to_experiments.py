"""add is_outlier to experiments

Revision ID: 98b849b9f08b
Revises: fe48608cabb7
Create Date: 2026-07-23 18:11:10.483175

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '98b849b9f08b'
down_revision: Union[str, None] = 'fe48608cabb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ROLLUP_COLUMNS_SQL = """
        SELECT
            COALESCE(e.base_experiment_id, e.experiment_id)              AS base_experiment_id,
            er.time_post_reaction_bucket_days,
            COUNT(sr.result_id)                                          AS n_replicates,
            AVG(sr."gross_ammonium_concentration_mM")                   AS "mean_gross_ammonium_mM",
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY sr."gross_ammonium_concentration_mM")          AS "median_gross_ammonium_mM",
            stddev_samp(sr."gross_ammonium_concentration_mM")           AS "sd_gross_ammonium_mM",
            AVG(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS "mean_net_ammonium_mM",
            stddev_samp(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS "sd_net_ammonium_mM",
            AVG(sr.h2_micromoles)                                       AS mean_h2_micromoles,
            stddev_samp(sr.h2_micromoles)                               AS sd_h2_micromoles,
            AVG(sr.h2_grams_per_ton_yield)                              AS mean_h2_grams_per_ton,
            stddev_samp(sr.h2_grams_per_ton_yield)                      AS sd_h2_grams_per_ton,
            AVG(sr.ferrous_iron_yield_h2_pct)                           AS mean_fe_yield_h2_pct,
            stddev_samp(sr.ferrous_iron_yield_h2_pct)                   AS sd_fe_yield_h2_pct,
            AVG(sr.ferrous_iron_yield_nh3_pct)                          AS mean_fe_yield_nh3_pct,
            stddev_samp(sr.ferrous_iron_yield_nh3_pct)                  AS sd_fe_yield_nh3_pct,
            AVG(sr.grams_per_ton_yield)                                 AS mean_grams_per_ton_yield,
            stddev_samp(sr.grams_per_ton_yield)                         AS sd_grams_per_ton_yield,
            AVG(sr.final_ph)                                            AS mean_final_ph
        FROM experimental_results er
        JOIN experiments e         ON e.id  = er.experiment_fk
        LEFT JOIN scalar_results sr ON sr.result_id = er.id
"""

# P4 definition: outlier-flagged experiments excluded from all aggregates.
ROLLUP_VIEW_NEW = f"""
    CREATE VIEW v_results_scalar_rollup AS
    {_ROLLUP_COLUMNS_SQL}
        WHERE er.is_primary_timepoint_result = TRUE
          AND NOT COALESCE(e.is_outlier, false)
        GROUP BY COALESCE(e.base_experiment_id, e.experiment_id),
                 er.time_post_reaction_bucket_days
"""

# Pre-P4 definition (no outlier filter) — restored on downgrade so the view
# keeps working after the column is dropped.
ROLLUP_VIEW_OLD = f"""
    CREATE VIEW v_results_scalar_rollup AS
    {_ROLLUP_COLUMNS_SQL}
        WHERE er.is_primary_timepoint_result = TRUE
        GROUP BY COALESCE(e.base_experiment_id, e.experiment_id),
                 er.time_post_reaction_bucket_days
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'experiments',
        sa.Column('is_outlier', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )
    op.execute("DROP VIEW IF EXISTS v_results_scalar_rollup CASCADE")
    op.execute(ROLLUP_VIEW_NEW)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_results_scalar_rollup CASCADE")
    op.execute(ROLLUP_VIEW_OLD)
    op.drop_column('experiments', 'is_outlier')
