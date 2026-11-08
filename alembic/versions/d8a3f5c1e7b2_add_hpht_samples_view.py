"""Add the v_hpht_samples reporting view (issue #149).

Additive: one view, no table or column changes. One row per primary timepoint of
an HPHT experiment with per-run values (cumulative H2 g/t, umol and Fe(II) yield
%, H2 g/t per day), the HPHT counterpart of v_core_flood_samples. Per-sample H2
is incremental (decided 2026-11-06), so the running sums are the run's H2 to date.

upgrade() drops the view first (IF EXISTS) because the API recreates every
_VIEWS entry on startup: on a database where the new code has already run, the
view exists before this migration does. downgrade() drops the view only. No
other view selects from it.

Revision ID: d8a3f5c1e7b2
Revises: c6d2f8a4e1b9
Create Date: 2026-11-07
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d8a3f5c1e7b2"
down_revision: Union[str, None] = "c6d2f8a4e1b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exactly database/event_listeners.py's _VIEWS["v_hpht_samples"] (a test checks).
_V_HPHT_SAMPLES = """
    CREATE VIEW v_hpht_samples AS
    WITH s AS (
        SELECT
            er.id                                  AS result_id,
            e.experiment_id,
            er.experiment_fk,
            e.base_experiment_id                   AS run_base_id,
            COALESCE(p.experiment_id IS NOT NULL
                     AND left(e.experiment_id, length(p.experiment_id) + 1)
                         = p.experiment_id || '_',
                     false)                        AS is_variant,
            er.time_post_reaction_days,
            er.cumulative_time_post_reaction_days,
            sr.measurement_date                    AS sample_date,
            sr.gc_run_date,
            er.sample_tube_number,
            sr."sampling_volume_mL",
            sr.h2_concentration,
            sr.gas_sampling_volume_ml,
            sr."gas_sampling_pressure_MPa",
            sr.h2_micromoles,
            sr.h2_mass_ug,
            sr.h2_grams_per_ton_yield,
            sr.ferrous_iron_yield_h2_pct,
            sr.final_ph,
            sr."final_conductivity_mS_cm",
            ec.reactor_slot
        FROM experimental_results er
        JOIN experiments e               ON e.id = er.experiment_fk
        LEFT JOIN experiments p          ON p.id = e.parent_experiment_fk
        JOIN experimental_conditions ec  ON ec.experiment_fk = e.id
        LEFT JOIN scalar_results sr      ON sr.result_id = er.id
        WHERE er.is_primary_timepoint_result = TRUE
          -- Same reading of HPHT as database/reactor_slot.py::_SERIES_BY_TYPE
          -- (lowercase, whitespace collapsed); keep the two in sync.
          AND lower(btrim(regexp_replace(ec.experiment_type, '\\s+', ' ', 'g')))
              = 'hpht'
    ), w AS (
        SELECT
            s.*,
            s.cumulative_time_post_reaction_days
                - COALESCE(LAG(s.cumulative_time_post_reaction_days) OVER win, 0)
                                                   AS interval_days,
            SUM(COALESCE(s.h2_grams_per_ton_yield, 0)) OVER win
                                                   AS cumulative_h2_grams_per_ton,
            SUM(COALESCE(s.h2_micromoles, 0)) OVER win
                                                   AS cumulative_h2_micromoles,
            SUM(COALESCE(s.ferrous_iron_yield_h2_pct, 0)) OVER win
                                                   AS cumulative_ferrous_iron_yield_h2_pct
        FROM s
        WINDOW win AS (PARTITION BY run_base_id, is_variant
                       ORDER BY cumulative_time_post_reaction_days, result_id
                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
    )
    SELECT
        result_id,
        experiment_id,
        experiment_fk,
        run_base_id,
        is_variant,
        time_post_reaction_days,
        cumulative_time_post_reaction_days,
        sample_date,
        gc_run_date,
        sample_tube_number,
        "sampling_volume_mL",
        h2_concentration,
        gas_sampling_volume_ml,
        "gas_sampling_pressure_MPa",
        h2_micromoles,
        h2_mass_ug,
        h2_grams_per_ton_yield,
        ferrous_iron_yield_h2_pct,
        final_ph,
        "final_conductivity_mS_cm",
        reactor_slot,
        CASE WHEN is_variant THEN NULL ELSE interval_days END
                                                   AS interval_days,
        CASE WHEN is_variant THEN NULL ELSE cumulative_h2_grams_per_ton END
                                                   AS cumulative_h2_grams_per_ton,
        CASE WHEN is_variant THEN NULL
             ELSE h2_grams_per_ton_yield / NULLIF(interval_days, 0) END
                                                   AS h2_grams_per_ton_per_day,
        CASE WHEN is_variant THEN NULL ELSE cumulative_h2_micromoles END
                                                   AS cumulative_h2_micromoles,
        CASE WHEN is_variant THEN NULL ELSE cumulative_ferrous_iron_yield_h2_pct END
                                                   AS cumulative_ferrous_iron_yield_h2_pct
    FROM w
"""


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_hpht_samples CASCADE")
    op.execute(_V_HPHT_SAMPLES)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_hpht_samples CASCADE")
