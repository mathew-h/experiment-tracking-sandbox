"""Add Ca (Calcium) fixed column to icp_results

Revision ID: bcecaa35be9c
Revises: ff30f56e6033
Create Date: 2026-02-17 11:48:30.157667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcecaa35be9c'
down_revision: Union[str, None] = 'ff30f56e6033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ca column to icp_results - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('icp_results')]

    # Add calcium column only if it doesn't already exist
    if 'ca' not in columns:
        op.add_column('icp_results', sa.Column('ca', sa.Float(), nullable=True))

    # NOTE: Removed auto-generated create_foreign_key for self-referential
    # experiments.parent_experiment_fk -- SQLite does not support adding FK
    # constraints via ALTER TABLE, and self-referential FKs cause
    # CircularDependencyError in batch mode.  The relationship is defined
    # in the ORM model; no DB-level constraint is needed.


def downgrade() -> None:
    """Remove ca column from icp_results - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect

    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()
    columns = [col['name'] for col in inspector.get_columns('icp_results')]

    if 'ca' not in columns:
        return  # Nothing to drop

    # Clean up leftover temp tables from failed migrations
    temp_table = '_alembic_tmp_icp_results'
    if temp_table in all_tables:
        op.drop_table(temp_table)

    # Drop views that reference icp_results before batch mode
    op.execute("DROP VIEW IF EXISTS v_primary_experiment_results")

    with op.batch_alter_table('icp_results', schema=None) as batch_op:
        batch_op.drop_column('ca')

    # v_primary_experiment_results is recreated by event_listeners.py on app startup
