"""drop sample mineral from xrd table

Revision ID: 4efd20d110e8
Revises: 99842925e243
Create Date: 2026-03-02 11:29:21.682859

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4efd20d110e8'
down_revision: Union[str, None] = '99842925e243'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the (sample_id, mineral_name) unique constraint from xrd_phases.

    Aeris XRD time-series data is keyed by (experiment_id, time_post_reaction_days, mineral_name).
    The old sample-level constraint prevented multiple time points for the same rock.
    ActLabs data uniqueness is enforced at the application layer.
    """
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()

    temp_table = '_alembic_tmp_xrd_phases'
    if temp_table in all_tables:
        op.drop_table(temp_table)

    constraints = inspector.get_unique_constraints('xrd_phases')
    constraint_names = [c['name'] for c in constraints]

    if 'uq_xrd_phase_sample_mineral' in constraint_names:
        with op.batch_alter_table('xrd_phases', schema=None) as batch_op:
            batch_op.drop_constraint('uq_xrd_phase_sample_mineral', type_='unique')


def downgrade() -> None:
    """Restore the (sample_id, mineral_name) unique constraint on xrd_phases."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()

    temp_table = '_alembic_tmp_xrd_phases'
    if temp_table in all_tables:
        op.drop_table(temp_table)

    constraints = inspector.get_unique_constraints('xrd_phases')
    constraint_names = [c['name'] for c in constraints]

    if 'uq_xrd_phase_sample_mineral' not in constraint_names:
        with op.batch_alter_table('xrd_phases', schema=None) as batch_op:
            batch_op.create_unique_constraint(
                'uq_xrd_phase_sample_mineral', ['sample_id', 'mineral_name']
            )
