"""Add experiment lineage model

Revision ID: 54e7b847aa92
Revises: ad16ea5b7e36
Create Date: 2025-10-27 11:07:17.496115

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '54e7b847aa92'
down_revision: Union[str, None] = 'ad16ea5b7e36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent."""
    # For SQLite: Add columns and index directly without foreign key constraint
    # SQLite doesn't enforce foreign keys by default, and the self-referential FK
    # causes circular dependency issues in batch mode. The relationship is defined
    # in the model and handled by SQLAlchemy at the application level.
    
    from alembic import context
    import sqlalchemy as sa
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('experiments')]
    indexes = [idx['name'] for idx in inspector.get_indexes('experiments')]
    
    # Add lineage tracking columns only if they don't exist
    if 'base_experiment_id' not in columns:
        op.add_column('experiments', sa.Column('base_experiment_id', sa.String(), nullable=True))
    
    if 'parent_experiment_fk' not in columns:
        op.add_column('experiments', sa.Column('parent_experiment_fk', sa.Integer(), nullable=True))
    
    # Create index on base_experiment_id for efficient lineage queries (if not exists)
    if 'ix_experiments_base_experiment_id' not in indexes:
        op.create_index('ix_experiments_base_experiment_id', 'experiments', ['base_experiment_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('experiments')]
    indexes = [idx['name'] for idx in inspector.get_indexes('experiments')]
    
    # Drop index if it exists
    if 'ix_experiments_base_experiment_id' in indexes:
        op.drop_index('ix_experiments_base_experiment_id', table_name='experiments')
    
    # Drop lineage columns if they exist
    if 'parent_experiment_fk' in columns:
        op.drop_column('experiments', 'parent_experiment_fk')
    
    if 'base_experiment_id' in columns:
        op.drop_column('experiments', 'base_experiment_id')
