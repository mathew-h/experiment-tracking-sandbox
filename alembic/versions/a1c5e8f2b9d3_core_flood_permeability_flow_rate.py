"""Core flood permeability flow rate column (#140).

Additive: one nullable Float column, experimental_results.permeability_flow_rate_mL_min.
No backfill (no core flood sample carries a pressure yet) and no CHECK constraint.
Its presence marks a sample as an intentional permeability test and is the sole
trigger for any future permeability computation; nothing computes it yet.

v_core_flood_samples is recreated in upgrade() so Power BI sees the column right
after the nightly `alembic upgrade head`, before the API restarts. downgrade()
restores the OLD view FIRST and only then drops the column: once the API has
started on the new code, database/event_listeners.py has recreated the view
selecting the column, and a bare drop_column fails with "cannot drop column ...
because other objects depend on it". No other view selects it.

Revision ID: a1c5e8f2b9d3
Revises: f3b7c2a9d4e1
Create Date: 2026-11-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c5e8f2b9d3"
down_revision: Union[str, None] = "f3b7c2a9d4e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_V_CORE_FLOOD_SAMPLES_OLD = """
    CREATE VIEW v_core_flood_samples AS
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
            er."flow_rate_mL_min",
            er."nitrogen_flow_rate_mL_min",
            er.inlet_pressure_psi,
            er.outlet_pressure_psi,
            sr."sampling_volume_mL",
            sr.h2_concentration,
            sr.gas_sampling_volume_ml,
            sr."gas_sampling_pressure_MPa",
            sr.h2_micromoles,
            sr.h2_mass_ug,
            sr.h2_grams_per_ton_yield,
            sr.final_ph,
            sr."final_conductivity_mS_cm",
            ec."pore_volume_mL"
        FROM experimental_results er
        JOIN experiments e               ON e.id = er.experiment_fk
        LEFT JOIN experiments p          ON p.id = e.parent_experiment_fk
        JOIN experimental_conditions ec  ON ec.experiment_fk = e.id
        LEFT JOIN scalar_results sr      ON sr.result_id = er.id
        WHERE er.is_primary_timepoint_result = TRUE
          -- Same reading of Core Flood as database/reactor_slot.py::_SERIES_BY_TYPE
          -- (lowercase, whitespace collapsed); keep the two in sync.
          AND lower(btrim(regexp_replace(ec.experiment_type, '\\s+', ' ', 'g')))
              IN ('core flood', 'coreflood', 'cf')
    ), w AS (
        SELECT
            s.*,
            s.cumulative_time_post_reaction_days
                - COALESCE(LAG(s.cumulative_time_post_reaction_days) OVER win, 0)
                                                   AS interval_days,
            SUM(COALESCE(s."sampling_volume_mL", 0)) OVER win
                                                   AS "cumulative_liquid_volume_mL",
            SUM(COALESCE(s.h2_grams_per_ton_yield, 0)) OVER win
                                                   AS cumulative_h2_grams_per_ton
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
        "flow_rate_mL_min",
        "nitrogen_flow_rate_mL_min",
        inlet_pressure_psi,
        outlet_pressure_psi,
        "sampling_volume_mL",
        h2_concentration,
        gas_sampling_volume_ml,
        "gas_sampling_pressure_MPa",
        h2_micromoles,
        h2_mass_ug,
        h2_grams_per_ton_yield,
        final_ph,
        "final_conductivity_mS_cm",
        "pore_volume_mL",
        CASE WHEN is_variant THEN NULL ELSE interval_days END
                                                   AS interval_days,
        CASE WHEN is_variant THEN NULL ELSE "cumulative_liquid_volume_mL" END
                                                   AS "cumulative_liquid_volume_mL",
        CASE WHEN is_variant THEN NULL
             ELSE "cumulative_liquid_volume_mL" / NULLIF("pore_volume_mL", 0) END
                                                   AS cumulative_pore_volumes,
        CASE WHEN is_variant THEN NULL ELSE cumulative_h2_grams_per_ton END
                                                   AS cumulative_h2_grams_per_ton,
        CASE WHEN is_variant THEN NULL
             ELSE h2_grams_per_ton_yield / NULLIF(interval_days, 0) END
                                                   AS h2_grams_per_ton_per_day,
        CASE WHEN is_variant THEN NULL ELSE "flow_rate_mL_min" = 0 END
                                                   AS is_hold_interval
    FROM w
"""

_V_CORE_FLOOD_SAMPLES = """
    CREATE VIEW v_core_flood_samples AS
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
            er."flow_rate_mL_min",
            er."nitrogen_flow_rate_mL_min",
            er.inlet_pressure_psi,
            er.outlet_pressure_psi,
            er."permeability_flow_rate_mL_min",
            sr."sampling_volume_mL",
            sr.h2_concentration,
            sr.gas_sampling_volume_ml,
            sr."gas_sampling_pressure_MPa",
            sr.h2_micromoles,
            sr.h2_mass_ug,
            sr.h2_grams_per_ton_yield,
            sr.final_ph,
            sr."final_conductivity_mS_cm",
            ec."pore_volume_mL"
        FROM experimental_results er
        JOIN experiments e               ON e.id = er.experiment_fk
        LEFT JOIN experiments p          ON p.id = e.parent_experiment_fk
        JOIN experimental_conditions ec  ON ec.experiment_fk = e.id
        LEFT JOIN scalar_results sr      ON sr.result_id = er.id
        WHERE er.is_primary_timepoint_result = TRUE
          -- Same reading of Core Flood as database/reactor_slot.py::_SERIES_BY_TYPE
          -- (lowercase, whitespace collapsed); keep the two in sync.
          AND lower(btrim(regexp_replace(ec.experiment_type, '\\s+', ' ', 'g')))
              IN ('core flood', 'coreflood', 'cf')
    ), w AS (
        SELECT
            s.*,
            s.cumulative_time_post_reaction_days
                - COALESCE(LAG(s.cumulative_time_post_reaction_days) OVER win, 0)
                                                   AS interval_days,
            SUM(COALESCE(s."sampling_volume_mL", 0)) OVER win
                                                   AS "cumulative_liquid_volume_mL",
            SUM(COALESCE(s.h2_grams_per_ton_yield, 0)) OVER win
                                                   AS cumulative_h2_grams_per_ton
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
        "flow_rate_mL_min",
        "nitrogen_flow_rate_mL_min",
        inlet_pressure_psi,
        outlet_pressure_psi,
        "permeability_flow_rate_mL_min",
        "sampling_volume_mL",
        h2_concentration,
        gas_sampling_volume_ml,
        "gas_sampling_pressure_MPa",
        h2_micromoles,
        h2_mass_ug,
        h2_grams_per_ton_yield,
        final_ph,
        "final_conductivity_mS_cm",
        "pore_volume_mL",
        CASE WHEN is_variant THEN NULL ELSE interval_days END
                                                   AS interval_days,
        CASE WHEN is_variant THEN NULL ELSE "cumulative_liquid_volume_mL" END
                                                   AS "cumulative_liquid_volume_mL",
        CASE WHEN is_variant THEN NULL
             ELSE "cumulative_liquid_volume_mL" / NULLIF("pore_volume_mL", 0) END
                                                   AS cumulative_pore_volumes,
        CASE WHEN is_variant THEN NULL ELSE cumulative_h2_grams_per_ton END
                                                   AS cumulative_h2_grams_per_ton,
        CASE WHEN is_variant THEN NULL
             ELSE h2_grams_per_ton_yield / NULLIF(interval_days, 0) END
                                                   AS h2_grams_per_ton_per_day,
        CASE WHEN is_variant THEN NULL ELSE "flow_rate_mL_min" = 0 END
                                                   AS is_hold_interval
    FROM w
"""


def _recreate(name: str, sql: str) -> None:
    op.execute(f"DROP VIEW IF EXISTS {name} CASCADE")
    op.execute(sql)


def upgrade() -> None:
    op.add_column(
        "experimental_results",
        sa.Column("permeability_flow_rate_mL_min", sa.Float(), nullable=True),
    )
    _recreate("v_core_flood_samples", _V_CORE_FLOOD_SAMPLES)


def downgrade() -> None:
    # Order matters: the view must stop depending on the column first.
    _recreate("v_core_flood_samples", _V_CORE_FLOOD_SAMPLES_OLD)
    op.drop_column("experimental_results", "permeability_flow_rate_mL_min")
