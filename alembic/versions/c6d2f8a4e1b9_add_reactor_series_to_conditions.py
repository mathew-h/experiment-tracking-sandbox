"""Add experimental_conditions.reactor_series for the Parr HPHT vessels (#147).

Additive: one nullable String(4) column. NULL means the experiment type's
default slot series ('R' for HPHT, 'CF' for Core Flood); 'P' marks the Parr
HPHT vessels P01-P06. CHECK ck_conditions_reactor_series allows only NULL or
'P', so a later series is a one-line migration rather than free text. No
backfill: no Parr runs exist yet, and every existing row keeps its derived
reactor_slot (database.reactor_slot.derive_reactor_slot treats NULL as before).

v_experiment_conditions is recreated with reactor_series and reactor_slot after
reactor_number, so Power BI can tell P03 from R03. downgrade() restores the old
view FIRST, then drops the CHECK and the column: once the API has started on
the new code, database/event_listeners.py has recreated the view selecting the
column, and a bare drop_column fails with "cannot drop column ... because other
objects depend on it" (the serum_vial_size_mL precedent, e9a4c1f7b3d2). No other
view selects from v_experiment_conditions, so CASCADE drops nothing else.

Revision ID: c6d2f8a4e1b9
Revises: b7e2d9c4a1f6
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c6d2f8a4e1b9"
down_revision: Union[str, None] = "b7e2d9c4a1f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exactly f3b7c2a9d4e1's _V_CONDITIONS_NEW (the view before this revision).
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
        ec."pore_volume_mL",
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
        ec.reactor_series,
        ec.reactor_slot,
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


def upgrade() -> None:
    op.add_column(
        "experimental_conditions",
        sa.Column("reactor_series", sa.String(length=4), nullable=True),
    )
    op.create_check_constraint(
        "ck_conditions_reactor_series",
        "experimental_conditions",
        "reactor_series IS NULL OR reactor_series IN ('P')",
    )
    _recreate("v_experiment_conditions", _V_CONDITIONS_NEW)


def downgrade() -> None:
    # Order matters: the view must stop depending on the column first.
    _recreate("v_experiment_conditions", _V_CONDITIONS_OLD)
    op.drop_constraint("ck_conditions_reactor_series", "experimental_conditions", type_="check")
    op.drop_column("experimental_conditions", "reactor_series")
