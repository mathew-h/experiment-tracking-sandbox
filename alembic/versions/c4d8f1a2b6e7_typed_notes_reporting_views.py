"""Reporting views read the typed notes model (issue #118, PR3).

View-only, no table DDL. Recreates v_experiments, v_dim_timepoints and
v_results_scalar and creates v_notes, matching database/event_listeners.py
(which also recreates every view on API startup -- this migration exists so the
lab PC's Power BI dataset is correct after the nightly `alembic upgrade head`
even before the API process restarts, and so downgrade can restore the exact
prior definitions).

* v_experiments.description -- **correctness fix, not a refactor**: was the
  first note by created_at (the transaction timestamp, shared by every note a
  bulk upload wrote in one transaction, so LIMIT 1 was arbitrary); now the note
  typed 'description'. Disagreed with the app on 16 of 1,277 experiments on the
  2026-09-04 production mirror.
* v_dim_timepoints.brine_modification_description -> modification_note, read
  from the result's 'modification' notes ('; '-joined in id order).
* v_results_scalar.sampling_description dropped (the legacy column it exposed
  is retired by #118 and dropped in PR4).
* v_notes -- new: experiment_id, result_id, note_type, note_text, created_at,
  created_by, needs_review (+ note_id).

Requires reclassify_notes_020.py to have been applied for the description
column to be populated; before that every experiment reads NULL.

Revision ID: c4d8f1a2b6e7
Revises: b7e2c9a41d05
Create Date: 2026-09-09
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4d8f1a2b6e7"
down_revision: Union[str, None] = "b7e2c9a41d05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_V_EXPERIMENTS_HEAD = """
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
"""
_V_EXPERIMENTS_TAIL = """
    FROM experiments e
    LEFT JOIN experimental_conditions ec ON ec.experiment_fk = e.id
"""
_V_EXPERIMENTS_NEW = _V_EXPERIMENTS_HEAD + """
        (SELECT n.note_text
         FROM experiment_notes n
         WHERE n.experiment_fk = e.id
           AND n.note_type = 'description') AS description
""" + _V_EXPERIMENTS_TAIL
_V_EXPERIMENTS_OLD = _V_EXPERIMENTS_HEAD + """
        (SELECT n.note_text
         FROM experiment_notes n
         WHERE n.experiment_fk = e.id
         ORDER BY n.created_at ASC
         LIMIT 1) AS description
""" + _V_EXPERIMENTS_TAIL

_V_DIM_HEAD = """
    CREATE VIEW v_dim_timepoints AS
    SELECT
        er.id                                  AS result_id,
        e.experiment_id,
        er.time_post_reaction_days,
        er.time_post_reaction_bucket_days,
        er.cumulative_time_post_reaction_days,
"""
_V_DIM_TAIL = """
    FROM experimental_results er
    JOIN experiments e ON e.id = er.experiment_fk
    WHERE er.is_primary_timepoint_result = TRUE
"""
_V_DIM_NEW = _V_DIM_HEAD + """
        (SELECT string_agg(n.note_text, '; ' ORDER BY n.id)
         FROM experiment_notes n
         WHERE n.result_id = er.id
           AND n.note_type = 'modification') AS modification_note
""" + _V_DIM_TAIL
_V_DIM_OLD = _V_DIM_HEAD + """
        er.brine_modification_description
""" + _V_DIM_TAIL

_V_SCALAR_BODY = """
        er.time_post_reaction_days,
        er.time_post_reaction_bucket_days,
        er.cumulative_time_post_reaction_days,
        sr."gross_ammonium_concentration_mM",
        sr."background_ammonium_concentration_mM",
        sr.grams_per_ton_yield,
        sr.final_ph,
        sr."final_nitrate_concentration_mM",
        sr.ferrous_iron_yield,
        sr.ferrous_iron_yield_h2_pct,
        SUM(COALESCE(sr.ferrous_iron_yield_h2_pct, 0)) OVER (
            PARTITION BY e.experiment_id
            ORDER BY er.cumulative_time_post_reaction_days, er.id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_ferrous_iron_yield_h2_pct,
        sr.ferrous_iron_yield_nh3_pct,
        sr."final_dissolved_oxygen_mg_L",
        sr."final_conductivity_mS_cm",
        sr."final_alkalinity_mg_L",
        sr."co2_partial_pressure_MPa",
        sr."sampling_volume_mL",
        sr.ammonium_quant_method,
        sr.background_experiment_fk,
        sr.measurement_date                      AS scalar_measurement_date,
        sr.nmr_run_date,
        GREATEST(0, sr."gross_ammonium_concentration_mM" - sr."background_ammonium_concentration_mM") AS net_ammonium_concentration
    FROM experimental_results er
    JOIN experiments e        ON e.id  = er.experiment_fk
    LEFT JOIN scalar_results sr ON sr.result_id = er.id
    WHERE er.is_primary_timepoint_result = TRUE
"""
_V_SCALAR_NEW = """
    CREATE VIEW v_results_scalar AS
    SELECT
        er.id                                    AS result_id,
        e.experiment_id,
        er.experiment_fk,
""" + _V_SCALAR_BODY
_V_SCALAR_OLD = """
    CREATE VIEW v_results_scalar AS
    SELECT
        er.id                                    AS result_id,
        e.experiment_id,
        er.experiment_fk,
        er.description                           AS sampling_description,
""" + _V_SCALAR_BODY

_V_NOTES = """
    CREATE VIEW v_notes AS
    SELECT
        n.id                 AS note_id,
        e.experiment_id,
        n.result_id,
        n.note_type::text    AS note_type,
        n.note_text,
        n.created_at,
        n.created_by,
        n.needs_review
    FROM experiment_notes n
    JOIN experiments e ON e.id = n.experiment_fk
"""


def _recreate(name: str, sql: str) -> None:
    op.execute(f"DROP VIEW IF EXISTS {name} CASCADE")
    op.execute(sql)


def upgrade() -> None:
    _recreate("v_experiments", _V_EXPERIMENTS_NEW)
    _recreate("v_dim_timepoints", _V_DIM_NEW)
    _recreate("v_results_scalar", _V_SCALAR_NEW)
    _recreate("v_notes", _V_NOTES)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_notes CASCADE")
    _recreate("v_results_scalar", _V_SCALAR_OLD)
    _recreate("v_dim_timepoints", _V_DIM_OLD)
    _recreate("v_experiments", _V_EXPERIMENTS_OLD)
