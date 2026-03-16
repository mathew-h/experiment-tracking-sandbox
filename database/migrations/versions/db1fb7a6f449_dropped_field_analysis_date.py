"""dropped field analysis date


Revision ID: db1fb7a6f449
Revises: bcecaa35be9c
Create Date: 2026-02-25 11:38:11.691420

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db1fb7a6f449'
down_revision: Union[str, None] = 'bcecaa35be9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()

    er_columns = [col['name'] for col in inspector.get_columns('experimental_results')]
    er_indexes = [idx['name'] for idx in inspector.get_indexes('experimental_results')]
    icp_columns = [col['name'] for col in inspector.get_columns('icp_results')]

    for temp_table in ['_alembic_tmp_experimental_results', '_alembic_tmp_icp_results']:
        if temp_table in all_tables:
            op.drop_table(temp_table)

    op.execute("DROP VIEW IF EXISTS v_primary_experiment_results")
    op.execute("DROP VIEW IF EXISTS v_experiment_additives_summary")

    if 'ix_experimental_results_time_post_reaction' in er_indexes:
        op.drop_index('ix_experimental_results_time_post_reaction', table_name='experimental_results')

    if 'time_post_reaction' in er_columns:
        with op.batch_alter_table('experimental_results', schema=None) as batch_op:
            batch_op.drop_column('time_post_reaction')

    if 'analysis_date' in icp_columns:
        with op.batch_alter_table('icp_results', schema=None) as batch_op:
            batch_op.drop_column('analysis_date')

    # Self-referential FK on experiments is handled by the ORM, not as a DB constraint
    # v_primary_experiment_results is auto-recreated by event_listeners.py on app startup


def downgrade() -> None:
    """Downgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    icp_columns = [col['name'] for col in inspector.get_columns('icp_results')]
    er_columns = [col['name'] for col in inspector.get_columns('experimental_results')]
    er_indexes = [idx['name'] for idx in inspector.get_indexes('experimental_results')]

    if 'analysis_date' not in icp_columns:
        op.add_column('icp_results', sa.Column('analysis_date', sa.DATETIME(), nullable=True))

    if 'time_post_reaction' not in er_columns:
        op.add_column('experimental_results', sa.Column('time_post_reaction', sa.FLOAT(), nullable=True))

    if 'ix_experimental_results_time_post_reaction' not in er_indexes:
        op.create_index('ix_experimental_results_time_post_reaction', 'experimental_results', ['time_post_reaction'], unique=False)
