"""Add experimental_conditions.serum_vial_size_mL (nominal serum vial size).

Additive: one nullable Integer column holding the NOMINAL vial size in whole
mL (20, 60, 120, 160, ...). Tracking only -- no calculation reads it. No
backfill: existing rows stay NULL. No CHECK (> 0): the new-experiments
conditions-sheet loop has no per-row SAVEPOINT, so a constraint violation
would abort the transaction and break every remaining row of the sheet;
positive-integer validation lives in ConditionsCreate/ConditionsUpdate and
the UI instead. See docs/issues/issue-serum_vial_size.md.txt.

v_experiment_conditions is recreated in upgrade() so Power BI sees the column
right after the nightly `alembic upgrade head` (update.ps1), before the API
restarts. downgrade() restores the OLD view FIRST and only then drops the
column: once the API has started on the new code, database/event_listeners.py
has recreated the view selecting the column, and a bare drop_column fails with
"cannot drop column ... because other objects depend on it". No other view
selects from v_experiment_conditions, so CASCADE drops nothing else.

Revision ID: e9a4c1f7b3d2
Revises: b8c4e2d7f9a1
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e9a4c1f7b3d2"
down_revision: Union[str, None] = "b8c4e2d7f9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
        ec.total_ferrous_iron_g,
        ec.total_ferrous_iron
    FROM experiments e
    JOIN experimental_conditions ec ON ec.experiment_fk = e.id
"""


def _recreate(name: str, sql: str) -> None:
    op.execute(f"DROP VIEW IF EXISTS {name} CASCADE")
    op.execute(sql)


def upgrade() -> None:
    op.add_column(
        "experimental_conditions",
        sa.Column("serum_vial_size_mL", sa.Integer(), nullable=True),
    )
    _recreate("v_experiment_conditions", _V_CONDITIONS_NEW)


def downgrade() -> None:
    # Order matters: the view must stop depending on the column first.
    _recreate("v_experiment_conditions", _V_CONDITIONS_OLD)
    op.drop_column("experimental_conditions", "serum_vial_size_mL")
