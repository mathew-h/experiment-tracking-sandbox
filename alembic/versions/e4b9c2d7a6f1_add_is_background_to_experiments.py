"""Add experiments.is_background (issue #152).

Additive: a NOT NULL boolean, server default false, so every existing row is a
non-background (nothing is backfilled here; database/data_migrations/
set_background_flags_023.py sets confirmed backgrounds after #151).

Four views read the column and are recreated with it:
- v_experiments gains is_background (last column).
- v_results_scalar_rollup and v_results_h2_bkg_adjusted_rollup leave
  is_background vials out of a group that also has sample vials; a group whose
  non-outlier members are all backgrounds keeps its rollup. The scalar rollup
  gains is_background_group (last column).
- v_results_h2_bkg_adjusted: a linked background set with any flagged vials
  uses only those for the background mean.

API startup (database/event_listeners.py) recreates the same SQL, so each
_NEW string must equal its _VIEWS entry (tests/models/test_is_background_column.py).
downgrade() restores the _OLD definitions BEFORE dropping the column, which the
new views depend on. v_results_h2_bkg_adjusted_rollup reads
v_results_h2_bkg_adjusted, so it is dropped first and created last.

Revision ID: e4b9c2d7a6f1
Revises: d8a3f5c1e7b2
Create Date: 2026-11-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4b9c2d7a6f1"
down_revision: Union[str, None] = "d8a3f5c1e7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Generated from database/event_listeners.py::_VIEWS before (_OLD) and after
# (_NEW) issue #152. Raw strings: the H2 view carries a regex with backslashes.
_V_EXPERIMENTS_OLD = r"""
        CREATE VIEW v_experiments AS
        SELECT
            e.experiment_id,
            e.experiment_number,
            e.status,
            e.researcher,
            e.date,
            e.sample_id,
            e.base_experiment_id,
            ec.reactor_number,
            ec.rock_mass_g,
            ec."water_volume_mL",
            ec.initial_ph,
            ec.experiment_type,
            ec.feedstock,
            (SELECT n.note_text
             FROM experiment_notes n
             WHERE n.experiment_fk = e.id
               AND n.note_type = 'description') AS description
        FROM experiments e
        LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id
    """
_V_EXPERIMENTS_NEW = r"""
        CREATE VIEW v_experiments AS
        SELECT
            e.experiment_id,
            e.experiment_number,
            e.status,
            e.researcher,
            e.date,
            e.sample_id,
            e.base_experiment_id,
            ec.reactor_number,
            ec.rock_mass_g,
            ec."water_volume_mL",
            ec.initial_ph,
            ec.experiment_type,
            ec.feedstock,
            (SELECT n.note_text
             FROM experiment_notes n
             WHERE n.experiment_fk = e.id
               AND n.note_type = 'description') AS description,
            e.is_background
        FROM experiments e
        LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id
    """
_V_SCALAR_ROLLUP_OLD = r"""
        CREATE VIEW v_results_scalar_rollup AS
        SELECT
            COALESCE(e.base_experiment_id, e.experiment_id)              AS base_experiment_id,
            er.time_post_reaction_bucket_days,
            COUNT(DISTINCT e.id)                                         AS n_vials,
            COUNT(DISTINCT e.replicate_label)                            AS n_replicate_letters,
            COUNT(*)                                                     AS n_values,
            AVG(sr."gross_ammonium_concentration_mM")                   AS "mean_gross_ammonium_mM",
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY sr."gross_ammonium_concentration_mM")          AS "median_gross_ammonium_mM",
            stddev_samp(sr."gross_ammonium_concentration_mM")           AS "sd_gross_ammonium_mM",
            AVG(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS "mean_net_ammonium_mM",
            stddev_samp(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS "sd_net_ammonium_mM",
            -- h2_concentration is invariant ppm (vol/vol) per MODELS.md; AVG is only
            -- meaningful because the unit never varies. If h2_concentration_unit ever
            -- becomes variable, this silently averages mixed units.
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
        JOIN experiments e     ON e.id  = er.experiment_fk
        JOIN scalar_results sr ON sr.result_id = er.id
        WHERE er.is_primary_timepoint_result = TRUE
          AND NOT COALESCE(e.is_outlier, false)
        GROUP BY COALESCE(e.base_experiment_id, e.experiment_id),
                 er.time_post_reaction_bucket_days
    """
_V_SCALAR_ROLLUP_NEW = r"""
        CREATE VIEW v_results_scalar_rollup AS
        SELECT
            COALESCE(e.base_experiment_id, e.experiment_id)              AS base_experiment_id,
            er.time_post_reaction_bucket_days,
            COUNT(DISTINCT e.id)                                         AS n_vials,
            COUNT(DISTINCT e.replicate_label)                            AS n_replicate_letters,
            COUNT(*)                                                     AS n_values,
            AVG(sr."gross_ammonium_concentration_mM")                   AS "mean_gross_ammonium_mM",
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY sr."gross_ammonium_concentration_mM")          AS "median_gross_ammonium_mM",
            stddev_samp(sr."gross_ammonium_concentration_mM")           AS "sd_gross_ammonium_mM",
            AVG(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS "mean_net_ammonium_mM",
            stddev_samp(GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM"))
                                                                        AS "sd_net_ammonium_mM",
            -- h2_concentration is invariant ppm (vol/vol) per MODELS.md; AVG is only
            -- meaningful because the unit never varies. If h2_concentration_unit ever
            -- becomes variable, this silently averages mixed units.
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
            AVG(sr.final_ph)                                            AS mean_final_ph,
            g.all_background                                            AS is_background_group
        FROM experimental_results er
        JOIN experiments e     ON e.id  = er.experiment_fk
        JOIN scalar_results sr ON sr.result_id = er.id
        JOIN (
            SELECT COALESCE(base_experiment_id, experiment_id) AS group_key,
                   bool_and(COALESCE(is_background, false))   AS all_background
            FROM experiments
            WHERE NOT COALESCE(is_outlier, false)
            GROUP BY 1
        ) g ON g.group_key = COALESCE(e.base_experiment_id, e.experiment_id)
        WHERE er.is_primary_timepoint_result = TRUE
          AND NOT COALESCE(e.is_outlier, false)
          AND (NOT COALESCE(e.is_background, false) OR g.all_background)
        GROUP BY COALESCE(e.base_experiment_id, e.experiment_id),
                 er.time_post_reaction_bucket_days,
                 g.all_background
    """
_V_H2_BKG_ADJUSTED_OLD = r"""
        CREATE VIEW v_results_h2_bkg_adjusted AS
        WITH s AS (
            SELECT
                er.id                                AS result_id,
                e.experiment_id,
                er.experiment_fk,
                l.base_experiment_id,
                er.time_post_reaction_bucket_days,
                CASE WHEN l.background_base_id IS NOT NULL
                     THEN 'group' ELSE 'vial' END    AS background_mode,
                COALESCE(l.background_base_id, l.background_stem_id)
                                                     AS background_ref,
                sr.h2_micromoles,
                2.01588 / NULLIF(ec.rock_mass_g, 0)  AS k_gpt,
                3 * 55.845 / 1e6 / NULLIF(ec.total_ferrous_iron_g, 0) * 100
                                                     AS k_fe
            FROM experimental_results er
            JOIN experiments e          ON e.id = er.experiment_fk
            JOIN scalar_results sr      ON sr.result_id = er.id
            JOIN h2_background_links l
                 ON l.base_experiment_id = COALESCE(e.base_experiment_id, e.experiment_id)
            LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id
            WHERE er.is_primary_timepoint_result = TRUE
              AND sr.h2_concentration IS NOT NULL
        ),
        bkg AS (
            SELECT
                l.base_experiment_id                 AS sample_base,
                er.time_post_reaction_bucket_days    AS bucket,
                COUNT(*)                             AS n_values,
                AVG(sr.h2_concentration)             AS mean_ppm,
                AVG(sr.h2_micromoles)                AS mean_umol,
                stddev_samp(sr.h2_micromoles)        AS sd_umol
            FROM h2_background_links l
            JOIN experiments e ON
                 (l.background_base_id IS NOT NULL
                  AND COALESCE(e.base_experiment_id, e.experiment_id) = l.background_base_id)
              OR (l.background_stem_id IS NOT NULL
                  AND regexp_replace(e.experiment_id, '-t[0-9]+(\.[0-9]+)?$', '') = l.background_stem_id)
            JOIN experimental_results er ON er.experiment_fk = e.id
            JOIN scalar_results sr       ON sr.result_id = er.id
            WHERE er.is_primary_timepoint_result = TRUE
              AND sr.h2_micromoles IS NOT NULL
              AND er.time_post_reaction_bucket_days IS NOT NULL
              AND NOT COALESCE(e.is_outlier, false)
            GROUP BY l.base_experiment_id, er.time_post_reaction_bucket_days
        ),
        d AS (
            SELECT
                s.*,
                m.bucket                             AS bkg_time_bucket_days,
                m.bucket - s.time_post_reaction_bucket_days
                                                     AS bkg_time_gap_days,
                m.n_values                           AS bkg_n_values,
                m.mean_ppm                           AS bkg_mean_h2_ppm,
                m.mean_umol                          AS bkg_mean_h2_micromoles,
                m.sd_umol                            AS bkg_sd_h2_micromoles,
                s.h2_micromoles - m.mean_umol        AS d_umol
            FROM s
            LEFT JOIN LATERAL (
                SELECT b.bucket, b.n_values, b.mean_ppm, b.mean_umol, b.sd_umol
                FROM bkg b
                WHERE b.sample_base = s.base_experiment_id
                  AND s.time_post_reaction_bucket_days IS NOT NULL
                ORDER BY abs(b.bucket - s.time_post_reaction_bucket_days), b.bucket
                LIMIT 1
            ) m ON true
        )
        SELECT
            result_id,
            experiment_id,
            experiment_fk,
            base_experiment_id,
            time_post_reaction_bucket_days,
            background_mode,
            background_ref,
            bkg_time_bucket_days,
            bkg_time_gap_days,
            bkg_n_values,
            bkg_mean_h2_ppm,
            bkg_mean_h2_micromoles,
            bkg_sd_h2_micromoles,
            h2_micromoles,
            d_umol                                   AS net_h2_micromoles_unclamped,
            CASE WHEN d_umol IS NOT NULL THEN GREATEST(0, d_umol) END
                                                     AS net_h2_micromoles,
            bkg_sd_h2_micromoles                     AS u_bkg_h2_micromoles,
            CASE WHEN d_umol IS NOT NULL THEN GREATEST(0, d_umol) END * 2.01588
                                                     AS net_h2_mass_ug,
            d_umol * k_gpt                           AS net_h2_grams_per_ton_unclamped,
            CASE WHEN d_umol * k_gpt IS NOT NULL THEN GREATEST(0, d_umol * k_gpt) END
                                                     AS net_h2_grams_per_ton,
            bkg_sd_h2_micromoles * k_gpt             AS u_bkg_h2_grams_per_ton,
            d_umol * k_fe                            AS net_fe_yield_h2_pct_unclamped,
            CASE WHEN d_umol * k_fe IS NOT NULL THEN GREATEST(0, d_umol * k_fe) END
                                                     AS net_fe_yield_h2_pct,
            bkg_sd_h2_micromoles * k_fe              AS u_bkg_fe_yield_h2_pct,
            d_umol < 0                               AS below_background
        FROM d
    """
_V_H2_BKG_ADJUSTED_NEW = r"""
        CREATE VIEW v_results_h2_bkg_adjusted AS
        WITH s AS (
            SELECT
                er.id                                AS result_id,
                e.experiment_id,
                er.experiment_fk,
                l.base_experiment_id,
                er.time_post_reaction_bucket_days,
                CASE WHEN l.background_base_id IS NOT NULL
                     THEN 'group' ELSE 'vial' END    AS background_mode,
                COALESCE(l.background_base_id, l.background_stem_id)
                                                     AS background_ref,
                sr.h2_micromoles,
                2.01588 / NULLIF(ec.rock_mass_g, 0)  AS k_gpt,
                3 * 55.845 / 1e6 / NULLIF(ec.total_ferrous_iron_g, 0) * 100
                                                     AS k_fe
            FROM experimental_results er
            JOIN experiments e          ON e.id = er.experiment_fk
            JOIN scalar_results sr      ON sr.result_id = er.id
            JOIN h2_background_links l
                 ON l.base_experiment_id = COALESCE(e.base_experiment_id, e.experiment_id)
            LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id
            WHERE er.is_primary_timepoint_result = TRUE
              AND sr.h2_concentration IS NOT NULL
        ),
        bm AS (
            SELECT
                l.base_experiment_id                 AS sample_base,
                e.id                                 AS experiment_fk,
                COALESCE(e.is_background, false)     AS is_background
            FROM h2_background_links l
            JOIN experiments e ON
                 (l.background_base_id IS NOT NULL
                  AND COALESCE(e.base_experiment_id, e.experiment_id) = l.background_base_id)
              OR (l.background_stem_id IS NOT NULL
                  AND regexp_replace(e.experiment_id, '-t[0-9]+(\.[0-9]+)?$', '') = l.background_stem_id)
            WHERE NOT COALESCE(e.is_outlier, false)
        ),
        bsel AS (
            SELECT bm.sample_base, bm.experiment_fk
            FROM bm
            WHERE bm.is_background
               OR NOT EXISTS (SELECT 1 FROM bm b2
                              WHERE b2.sample_base = bm.sample_base AND b2.is_background)
        ),
        bkg AS (
            SELECT
                bsel.sample_base,
                er.time_post_reaction_bucket_days    AS bucket,
                COUNT(*)                             AS n_values,
                AVG(sr.h2_concentration)             AS mean_ppm,
                AVG(sr.h2_micromoles)                AS mean_umol,
                stddev_samp(sr.h2_micromoles)        AS sd_umol
            FROM bsel
            JOIN experimental_results er ON er.experiment_fk = bsel.experiment_fk
            JOIN scalar_results sr       ON sr.result_id = er.id
            WHERE er.is_primary_timepoint_result = TRUE
              AND sr.h2_micromoles IS NOT NULL
              AND er.time_post_reaction_bucket_days IS NOT NULL
            GROUP BY bsel.sample_base, er.time_post_reaction_bucket_days
        ),
        d AS (
            SELECT
                s.*,
                m.bucket                             AS bkg_time_bucket_days,
                m.bucket - s.time_post_reaction_bucket_days
                                                     AS bkg_time_gap_days,
                m.n_values                           AS bkg_n_values,
                m.mean_ppm                           AS bkg_mean_h2_ppm,
                m.mean_umol                          AS bkg_mean_h2_micromoles,
                m.sd_umol                            AS bkg_sd_h2_micromoles,
                s.h2_micromoles - m.mean_umol        AS d_umol
            FROM s
            LEFT JOIN LATERAL (
                SELECT b.bucket, b.n_values, b.mean_ppm, b.mean_umol, b.sd_umol
                FROM bkg b
                WHERE b.sample_base = s.base_experiment_id
                  AND s.time_post_reaction_bucket_days IS NOT NULL
                ORDER BY abs(b.bucket - s.time_post_reaction_bucket_days), b.bucket
                LIMIT 1
            ) m ON true
        )
        SELECT
            result_id,
            experiment_id,
            experiment_fk,
            base_experiment_id,
            time_post_reaction_bucket_days,
            background_mode,
            background_ref,
            bkg_time_bucket_days,
            bkg_time_gap_days,
            bkg_n_values,
            bkg_mean_h2_ppm,
            bkg_mean_h2_micromoles,
            bkg_sd_h2_micromoles,
            h2_micromoles,
            d_umol                                   AS net_h2_micromoles_unclamped,
            CASE WHEN d_umol IS NOT NULL THEN GREATEST(0, d_umol) END
                                                     AS net_h2_micromoles,
            bkg_sd_h2_micromoles                     AS u_bkg_h2_micromoles,
            CASE WHEN d_umol IS NOT NULL THEN GREATEST(0, d_umol) END * 2.01588
                                                     AS net_h2_mass_ug,
            d_umol * k_gpt                           AS net_h2_grams_per_ton_unclamped,
            CASE WHEN d_umol * k_gpt IS NOT NULL THEN GREATEST(0, d_umol * k_gpt) END
                                                     AS net_h2_grams_per_ton,
            bkg_sd_h2_micromoles * k_gpt             AS u_bkg_h2_grams_per_ton,
            d_umol * k_fe                            AS net_fe_yield_h2_pct_unclamped,
            CASE WHEN d_umol * k_fe IS NOT NULL THEN GREATEST(0, d_umol * k_fe) END
                                                     AS net_fe_yield_h2_pct,
            bkg_sd_h2_micromoles * k_fe              AS u_bkg_fe_yield_h2_pct,
            d_umol < 0                               AS below_background
        FROM d
    """
_V_H2_BKG_ADJUSTED_ROLLUP_OLD = r"""
        CREATE VIEW v_results_h2_bkg_adjusted_rollup AS
        SELECT
            v.base_experiment_id,
            v.time_post_reaction_bucket_days,
            COUNT(v.net_h2_micromoles_unclamped)                        AS n_values,
            MIN(v.bkg_time_bucket_days)                                 AS bkg_time_bucket_days,
            MIN(v.bkg_time_gap_days)                                    AS bkg_time_gap_days,
            MIN(v.bkg_n_values)                                         AS bkg_n_values,
            MIN(v.bkg_mean_h2_micromoles)                               AS bkg_mean_h2_micromoles,
            MIN(v.bkg_sd_h2_micromoles)                                 AS bkg_sd_h2_micromoles,
            CASE WHEN AVG(v.net_h2_micromoles_unclamped) IS NOT NULL
                 THEN GREATEST(0, AVG(v.net_h2_micromoles_unclamped)) END             AS mean_net_h2_micromoles,
            CASE WHEN stddev_samp(v.net_h2_micromoles_unclamped) IS NULL
                      AND AVG(v.u_bkg_h2_micromoles) IS NULL THEN NULL
                 ELSE sqrt(power(COALESCE(stddev_samp(v.net_h2_micromoles_unclamped), 0), 2)
                           + power(COALESCE(AVG(v.u_bkg_h2_micromoles), 0), 2))
            END                                                         AS sd_net_h2_micromoles,
            CASE WHEN AVG(v.net_h2_grams_per_ton_unclamped) IS NOT NULL
                 THEN GREATEST(0, AVG(v.net_h2_grams_per_ton_unclamped)) END          AS mean_net_h2_grams_per_ton,
            CASE WHEN stddev_samp(v.net_h2_grams_per_ton_unclamped) IS NULL
                      AND AVG(v.u_bkg_h2_grams_per_ton) IS NULL THEN NULL
                 ELSE sqrt(power(COALESCE(stddev_samp(v.net_h2_grams_per_ton_unclamped), 0), 2)
                           + power(COALESCE(AVG(v.u_bkg_h2_grams_per_ton), 0), 2))
            END                                                         AS sd_net_h2_grams_per_ton,
            CASE WHEN AVG(v.net_fe_yield_h2_pct_unclamped) IS NOT NULL
                 THEN GREATEST(0, AVG(v.net_fe_yield_h2_pct_unclamped)) END           AS mean_net_fe_yield_h2_pct,
            CASE WHEN stddev_samp(v.net_fe_yield_h2_pct_unclamped) IS NULL
                      AND AVG(v.u_bkg_fe_yield_h2_pct) IS NULL THEN NULL
                 ELSE sqrt(power(COALESCE(stddev_samp(v.net_fe_yield_h2_pct_unclamped), 0), 2)
                           + power(COALESCE(AVG(v.u_bkg_fe_yield_h2_pct), 0), 2))
            END                                                         AS sd_net_fe_yield_h2_pct,
            AVG(v.net_h2_micromoles_unclamped) < 0                      AS below_background
        FROM v_results_h2_bkg_adjusted v
        JOIN experiments e ON e.id = v.experiment_fk
        WHERE NOT COALESCE(e.is_outlier, false)
          AND v.time_post_reaction_bucket_days IS NOT NULL
        GROUP BY v.base_experiment_id, v.time_post_reaction_bucket_days
    """
_V_H2_BKG_ADJUSTED_ROLLUP_NEW = r"""
        CREATE VIEW v_results_h2_bkg_adjusted_rollup AS
        SELECT
            v.base_experiment_id,
            v.time_post_reaction_bucket_days,
            COUNT(v.net_h2_micromoles_unclamped)                        AS n_values,
            MIN(v.bkg_time_bucket_days)                                 AS bkg_time_bucket_days,
            MIN(v.bkg_time_gap_days)                                    AS bkg_time_gap_days,
            MIN(v.bkg_n_values)                                         AS bkg_n_values,
            MIN(v.bkg_mean_h2_micromoles)                               AS bkg_mean_h2_micromoles,
            MIN(v.bkg_sd_h2_micromoles)                                 AS bkg_sd_h2_micromoles,
            CASE WHEN AVG(v.net_h2_micromoles_unclamped) IS NOT NULL
                 THEN GREATEST(0, AVG(v.net_h2_micromoles_unclamped)) END             AS mean_net_h2_micromoles,
            CASE WHEN stddev_samp(v.net_h2_micromoles_unclamped) IS NULL
                      AND AVG(v.u_bkg_h2_micromoles) IS NULL THEN NULL
                 ELSE sqrt(power(COALESCE(stddev_samp(v.net_h2_micromoles_unclamped), 0), 2)
                           + power(COALESCE(AVG(v.u_bkg_h2_micromoles), 0), 2))
            END                                                         AS sd_net_h2_micromoles,
            CASE WHEN AVG(v.net_h2_grams_per_ton_unclamped) IS NOT NULL
                 THEN GREATEST(0, AVG(v.net_h2_grams_per_ton_unclamped)) END          AS mean_net_h2_grams_per_ton,
            CASE WHEN stddev_samp(v.net_h2_grams_per_ton_unclamped) IS NULL
                      AND AVG(v.u_bkg_h2_grams_per_ton) IS NULL THEN NULL
                 ELSE sqrt(power(COALESCE(stddev_samp(v.net_h2_grams_per_ton_unclamped), 0), 2)
                           + power(COALESCE(AVG(v.u_bkg_h2_grams_per_ton), 0), 2))
            END                                                         AS sd_net_h2_grams_per_ton,
            CASE WHEN AVG(v.net_fe_yield_h2_pct_unclamped) IS NOT NULL
                 THEN GREATEST(0, AVG(v.net_fe_yield_h2_pct_unclamped)) END           AS mean_net_fe_yield_h2_pct,
            CASE WHEN stddev_samp(v.net_fe_yield_h2_pct_unclamped) IS NULL
                      AND AVG(v.u_bkg_fe_yield_h2_pct) IS NULL THEN NULL
                 ELSE sqrt(power(COALESCE(stddev_samp(v.net_fe_yield_h2_pct_unclamped), 0), 2)
                           + power(COALESCE(AVG(v.u_bkg_fe_yield_h2_pct), 0), 2))
            END                                                         AS sd_net_fe_yield_h2_pct,
            AVG(v.net_h2_micromoles_unclamped) < 0                      AS below_background
        FROM v_results_h2_bkg_adjusted v
        JOIN experiments e ON e.id = v.experiment_fk
        JOIN (
            SELECT COALESCE(base_experiment_id, experiment_id) AS group_key,
                   bool_and(COALESCE(is_background, false))   AS all_background
            FROM experiments
            WHERE NOT COALESCE(is_outlier, false)
            GROUP BY 1
        ) g ON g.group_key = v.base_experiment_id
        WHERE NOT COALESCE(e.is_outlier, false)
          AND (NOT COALESCE(e.is_background, false) OR g.all_background)
          AND v.time_post_reaction_bucket_days IS NOT NULL
        GROUP BY v.base_experiment_id, v.time_post_reaction_bucket_days
    """

# Dependants first when dropping; dependencies first when creating.
_DROP_ORDER = (
    "v_results_h2_bkg_adjusted_rollup",
    "v_results_h2_bkg_adjusted",
    "v_results_scalar_rollup",
    "v_experiments",
)


def _recreate(defs: tuple[str, ...]) -> None:
    for name in _DROP_ORDER:
        op.execute(f"DROP VIEW IF EXISTS {name}")
    for sql in defs:
        op.execute(sql)


def upgrade() -> None:
    op.add_column(
        "experiments",
        sa.Column("is_background", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    _recreate((_V_EXPERIMENTS_NEW, _V_SCALAR_ROLLUP_NEW,
               _V_H2_BKG_ADJUSTED_NEW, _V_H2_BKG_ADJUSTED_ROLLUP_NEW))


def downgrade() -> None:
    _recreate((_V_EXPERIMENTS_OLD, _V_SCALAR_ROLLUP_OLD,
               _V_H2_BKG_ADJUSTED_OLD, _V_H2_BKG_ADJUSTED_ROLLUP_OLD))
    op.drop_column("experiments", "is_background")
