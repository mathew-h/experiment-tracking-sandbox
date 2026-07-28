"""add h2 ppm aggregates to v_results_scalar_rollup

Revision ID: a1f2c3d4e5b6
Revises: daae92e908f1
Create Date: 2026-07-28 00:00:00.000000

Additive, view-only. Drops and recreates v_results_scalar_rollup to add
mean_h2_ppm / sd_h2_ppm (AVG / stddev_samp over scalar_results.h2_concentration).
No table DDL. downgrade() restores the prior view definition verbatim.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1f2c3d4e5b6'
down_revision: Union[str, None] = 'daae92e908f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Column block WITH the new h2 ppm aggregates (mean_h2_ppm / sd_h2_ppm placed
# immediately before mean_h2_micromoles so the H2 block stays contiguous).
# h2_concentration is invariant ppm (vol/vol) per MODELS.md; AVG is only
# meaningful because the unit never varies.
_ROLLUP_COLUMNS_NEW = """
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
            AVG(sr.h2_concentration)                                    AS mean_h2_ppm,
            stddev_samp(sr.h2_concentration)                            AS sd_h2_ppm,
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

# Prior (pre-issue-90) column block — no h2 ppm aggregates. Restored on downgrade.
_ROLLUP_COLUMNS_OLD = """
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

_ROLLUP_FILTER_GROUP = """
        WHERE er.is_primary_timepoint_result = TRUE
          AND NOT COALESCE(e.is_outlier, false)
        GROUP BY COALESCE(e.base_experiment_id, e.experiment_id),
                 er.time_post_reaction_bucket_days
"""

ROLLUP_VIEW_NEW = f"""
    CREATE VIEW v_results_scalar_rollup AS
    {_ROLLUP_COLUMNS_NEW}
    {_ROLLUP_FILTER_GROUP}
"""

ROLLUP_VIEW_OLD = f"""
    CREATE VIEW v_results_scalar_rollup AS
    {_ROLLUP_COLUMNS_OLD}
    {_ROLLUP_FILTER_GROUP}
"""


def upgrade() -> None:
    """Upgrade schema: recreate rollup view with mean_h2_ppm / sd_h2_ppm."""
    op.execute("DROP VIEW IF EXISTS v_results_scalar_rollup CASCADE")
    op.execute(ROLLUP_VIEW_NEW)


def downgrade() -> None:
    """Downgrade schema: restore prior rollup view without h2 ppm aggregates."""
    op.execute("DROP VIEW IF EXISTS v_results_scalar_rollup CASCADE")
    op.execute(ROLLUP_VIEW_OLD)
