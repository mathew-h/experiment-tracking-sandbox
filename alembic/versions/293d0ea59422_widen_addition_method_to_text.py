"""widen addition method to text

Revision ID: 293d0ea59422
Revises: a1f2c3d4e5b6
Create Date: 2026-07-29 08:23:02.919540

Deviation from plan (found during implementation): a plain ALTER COLUMN fails
on Postgres with "cannot alter type of a column used by a view or rule"
because the reporting view v_chemical_additives (database/event_listeners.py)
selects ca.addition_method directly. Following the established pattern from
a1f2c3d4e5b6 (drop dependent view -> DDL -> recreate view, verbatim SQL from
event_listeners.py), this migration drops and recreates that view around the
column type change in both upgrade() and downgrade().
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '293d0ea59422'
down_revision: Union[str, None] = 'a1f2c3d4e5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Verbatim from database/event_listeners.py (v_chemical_additives) — the SQL text
# itself does not change; only the addition_method column's underlying type does.
V_CHEMICAL_ADDITIVES = """
        CREATE VIEW v_chemical_additives AS
        SELECT
            e.experiment_id,
            c.name        AS compound_name,
            c.formula,
            ca.amount,
            ca.unit,
            ca.addition_order,
            ca.addition_method,
            ca.purity,
            ca.mass_in_grams,
            ca.moles_added,
            ca.final_concentration,
            ca.concentration_units,
            ca.elemental_metal_mass,
            ca.catalyst_percentage,
            ca.catalyst_ppm
        FROM chemical_additives ca
        JOIN experimental_conditions ec ON ec.id = ca.experiment_id
        JOIN experiments e             ON e.id  = ec.experiment_fk
        JOIN compounds c               ON c.id  = ca.compound_id
    """


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_chemical_additives CASCADE")
    op.alter_column(
        'chemical_additives',
        'addition_method',
        existing_type=sa.String(length=50),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.execute(V_CHEMICAL_ADDITIVES)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_chemical_additives CASCADE")
    op.alter_column(
        'chemical_additives',
        'addition_method',
        existing_type=sa.Text(),
        type_=sa.String(length=50),
        existing_nullable=True,
    )
    op.execute(V_CHEMICAL_ADDITIVES)
