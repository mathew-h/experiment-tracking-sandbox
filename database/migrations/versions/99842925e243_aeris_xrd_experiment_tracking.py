"""aeris xrd experiment tracking

Revision ID: 99842925e243
Revises: db1fb7a6f449
Create Date: 2026-02-27 07:54:30.748557

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99842925e243'
down_revision: Union[str, None] = 'db1fb7a6f449'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Aeris XRD experiment-tracking columns — SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()
    columns = [col['name'] for col in inspector.get_columns('xrd_phases')]
    indexes = {idx['name'] for idx in inspector.get_indexes('xrd_phases')}

    # Clean up leftover temp tables from failed migrations
    if '_alembic_tmp_xrd_phases' in all_tables:
        op.drop_table('_alembic_tmp_xrd_phases')

    # Add new columns (idempotent, outside batch mode)
    if 'experiment_fk' not in columns:
        op.add_column('xrd_phases', sa.Column('experiment_fk', sa.Integer(), nullable=True))
    if 'experiment_id' not in columns:
        op.add_column('xrd_phases', sa.Column('experiment_id', sa.String(), nullable=True))
    if 'time_post_reaction_days' not in columns:
        op.add_column('xrd_phases', sa.Column('time_post_reaction_days', sa.Integer(), nullable=True))
    if 'measurement_date' not in columns:
        op.add_column('xrd_phases', sa.Column('measurement_date', sa.DateTime(timezone=True), nullable=True))
    if 'rwp' not in columns:
        op.add_column('xrd_phases', sa.Column('rwp', sa.Float(), nullable=True))

    # Batch mode required for nullable change + unique constraint in SQLite
    with op.batch_alter_table('xrd_phases', schema=None) as batch_op:
        batch_op.alter_column('sample_id', existing_type=sa.VARCHAR(), nullable=True)
        batch_op.create_unique_constraint(
            'uq_xrd_phase_experiment_time_mineral',
            ['experiment_id', 'time_post_reaction_days', 'mineral_name'],
        )

    # Create new indexes after batch mode (idempotent)
    inspector = inspect(conn)
    indexes = {idx['name'] for idx in inspector.get_indexes('xrd_phases')}
    if 'ix_xrd_phases_experiment_fk' not in indexes:
        op.create_index(op.f('ix_xrd_phases_experiment_fk'), 'xrd_phases', ['experiment_fk'], unique=False)
    if 'ix_xrd_phases_experiment_id' not in indexes:
        op.create_index(op.f('ix_xrd_phases_experiment_id'), 'xrd_phases', ['experiment_id'], unique=False)

    # FK constraint skipped — relationship handled by SQLAlchemy ORM


def downgrade() -> None:
    """Remove Aeris XRD experiment-tracking columns — SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()
    columns = [col['name'] for col in inspector.get_columns('xrd_phases')]
    indexes = {idx['name'] for idx in inspector.get_indexes('xrd_phases')}

    # Clean up leftover temp tables from failed migrations
    if '_alembic_tmp_xrd_phases' in all_tables:
        op.drop_table('_alembic_tmp_xrd_phases')

    # Drop indexes BEFORE batch mode
    if 'ix_xrd_phases_experiment_id' in indexes:
        op.drop_index(op.f('ix_xrd_phases_experiment_id'), table_name='xrd_phases')
    if 'ix_xrd_phases_experiment_fk' in indexes:
        op.drop_index(op.f('ix_xrd_phases_experiment_fk'), table_name='xrd_phases')

    # Batch mode for constraint drop, nullable revert, and column drops
    cols_to_drop = ['rwp', 'measurement_date', 'time_post_reaction_days', 'experiment_id', 'experiment_fk']
    if any(c in columns for c in cols_to_drop):
        with op.batch_alter_table('xrd_phases', schema=None) as batch_op:
            batch_op.drop_constraint('uq_xrd_phase_experiment_time_mineral', type_='unique')
            batch_op.alter_column('sample_id', existing_type=sa.VARCHAR(), nullable=False)
            for col in cols_to_drop:
                if col in columns:
                    batch_op.drop_column(col)
