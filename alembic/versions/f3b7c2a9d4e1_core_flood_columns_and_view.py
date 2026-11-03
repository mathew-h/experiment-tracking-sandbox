"""Core flood schema: per-sample tube/flow/pressure columns and pore volume (#132).

Additive: five nullable columns on experimental_results (sample_tube_number
Integer; flow_rate_mL_min, nitrogen_flow_rate_mL_min, inlet_pressure_psi,
outlet_pressure_psi Float) and one on experimental_conditions (pore_volume_mL
Float). No backfill: existing rows stay NULL. No CHECK constraints: bulk
parsers must not have a constraint violation abort the transaction mid-sheet;
validation belongs in the API schemas. There is deliberately no separate core
flood table and no pore_pressure_psi column (pore pressure is
experimental_conditions.pore_pressure).

v_dim_timepoints and v_experiment_conditions are recreated in upgrade() so
Power BI sees the new columns right after the nightly `alembic upgrade head`
(update.ps1), before the API restarts. downgrade() restores the OLD views
FIRST and only then drops the columns: once the API has started on the new
code, database/event_listeners.py has recreated the views selecting the
columns, and a bare drop_column fails with "cannot drop column ... because
other objects depend on it". No other view selects from either of these two,
so CASCADE drops nothing else.

Revision ID: f3b7c2a9d4e1
Revises: e9a4c1f7b3d2
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3b7c2a9d4e1"
down_revision: Union[str, None] = "e9a4c1f7b3d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_V_DIM_OLD = """
    CREATE VIEW v_dim_timepoints AS
    SELECT
        er.id                                  AS result_id,
        e.experiment_id,
        er.time_post_reaction_days,
        er.time_post_reaction_bucket_days,
        er.cumulative_time_post_reaction_days,
        (SELECT string_agg(n.note_text, '; ' ORDER BY n.id)
         FROM experiment_notes n
         WHERE n.result_id = er.id
           AND n.note_type = 'modification') AS modification_note
    FROM experimental_results er
    JOIN experiments e ON e.id = er.experiment_fk
    WHERE er.is_primary_timepoint_result = TRUE
"""

_V_DIM_NEW = """
    CREATE VIEW v_dim_timepoints AS
    SELECT
        er.id                                  AS result_id,
        e.experiment_id,
        er.time_post_reaction_days,
        er.time_post_reaction_bucket_days,
        er.cumulative_time_post_reaction_days,
        er.sample_tube_number,
        (SELECT string_agg(n.note_text, '; ' ORDER BY n.id)
         FROM experiment_notes n
         WHERE n.result_id = er.id
           AND n.note_type = 'modification') AS modification_note
    FROM experimental_results er
    JOIN experiments e ON e.id = er.experiment_fk
    WHERE er.is_primary_timepoint_result = TRUE
"""

_V_CONDITIONS_OLD = """
    CREATE VIEW v_experiment_conditions AS
    SELECT
        e.experiment_id,
        ec.experiment_type,
        ec.temperature_c,
        ec.particle_size,
        ec.initial_ph,
        ec.rock_mass_g,
        ec."water_volume_mL",
        ec."serum_vial_size_mL",
        ec.water_to_rock_ratio,
        ec.reactor_number,
        ec.feedstock,
        ec.stir_speed_rpm,
        ec.room_temp_pressure_psi,
        ec.rxn_temp_pressure_psi,
        ec."co2_partial_pressure_MPa",
        ec.confining_pressure,
        ec.pore_pressure,
        ec.flow_rate,
        ec."initial_conductivity_mS_cm",
        ec.initial_nitrate_concentration,
        ec.initial_dissolved_oxygen,
        ec.initial_alkalinity,
        ec.core_height_cm,
        ec.core_width_cm,
        ec.core_volume_cm3,
        ec.total_ferrous_iron_g,
        ec.total_ferrous_iron
    FROM experiments e
    JOIN experimental_conditions ec ON ec.experiment_fk = e.id
"""

_V_CONDITIONS_NEW = """
    CREATE VIEW v_experiment_conditions AS
    SELECT
        e.experiment_id,
        ec.experiment_type,
        ec.temperature_c,
        ec.particle_size,
        ec.initial_ph,
        ec.rock_mass_g,
        ec."water_volume_mL",
        ec."serum_vial_size_mL",
        ec.water_to_rock_ratio,
        ec.reactor_number,
        ec.feedstock,
        ec.stir_speed_rpm,
        ec.room_temp_pressure_psi,
        ec.rxn_temp_pressure_psi,
        ec."co2_partial_pressure_MPa",
        ec.confining_pressure,
        ec.pore_pressure,
        ec.flow_rate,
        ec."initial_conductivity_mS_cm",
        ec.initial_nitrate_concentration,
        ec.initial_dissolved_oxygen,
        ec.initial_alkalinity,
        ec.core_height_cm,
        ec.core_width_cm,
        ec.core_volume_cm3,
        ec."pore_volume_mL",
        ec.total_ferrous_iron_g,
        ec.total_ferrous_iron
    FROM experiments e
    JOIN experimental_conditions ec ON ec.experiment_fk = e.id
"""


def _recreate(name: str, sql: str) -> None:
    op.execute(f"DROP VIEW IF EXISTS {name} CASCADE")
    op.execute(sql)


_RESULT_COLUMNS = (
    ("sample_tube_number", sa.Integer),
    ("flow_rate_mL_min", sa.Float),
    ("nitrogen_flow_rate_mL_min", sa.Float),
    ("inlet_pressure_psi", sa.Float),
    ("outlet_pressure_psi", sa.Float),
)


def upgrade() -> None:
    for name, type_ in _RESULT_COLUMNS:
        op.add_column("experimental_results", sa.Column(name, type_(), nullable=True))
    op.add_column(
        "experimental_conditions",
        sa.Column("pore_volume_mL", sa.Float(), nullable=True),
    )
    _recreate("v_dim_timepoints", _V_DIM_NEW)
    _recreate("v_experiment_conditions", _V_CONDITIONS_NEW)


def downgrade() -> None:
    # Order matters: the views must stop depending on the columns first.
    _recreate("v_experiment_conditions", _V_CONDITIONS_OLD)
    _recreate("v_dim_timepoints", _V_DIM_OLD)
    op.drop_column("experimental_conditions", "pore_volume_mL")
    for name, _ in reversed(_RESULT_COLUMNS):
        op.drop_column("experimental_results", name)
