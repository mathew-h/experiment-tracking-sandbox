"""Time post reaction optional

Revision ID: 2a832c8d5048
Revises: 54e7b847aa92
Create Date: 2025-10-27 11:46:50.911815

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a832c8d5048'
down_revision: Union[str, None] = '54e7b847aa92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    
    # CRITICAL: Clean up any leftover temporary tables from failed migrations
    # This ensures idempotency and allows re-running after failures
    all_tables = inspector.get_table_names()
    temp_table = '_alembic_tmp_experimental_results'
    if temp_table in all_tables:
        op.drop_table(temp_table)
    
    # Check if experimental_results table exists and get its current structure
    if 'experimental_results' in all_tables:
        columns = [col['name'] for col in inspector.get_columns('experimental_results')]
        indexes = [idx['name'] for idx in inspector.get_indexes('experimental_results')]
        constraints = [con['name'] for con in inspector.get_unique_constraints('experimental_results')]
        
        # IMPORTANT: Drop indexes on columns we're about to drop BEFORE batch mode
        # Batch mode tries to recreate all indexes, which fails if they reference dropped columns
        if 'ix_experimental_results_experiment_id' in indexes:
            op.drop_index('ix_experimental_results_experiment_id', table_name='experimental_results')
        
        # Use batch mode for constraint and column operations (SQLite limitation)
        with op.batch_alter_table('experimental_results', schema=None) as batch_op:
            # Drop the unique constraint if it exists
            if 'uix_experiment_time' in constraints:
                batch_op.drop_constraint('uix_experiment_time', type_='unique')
            
            # Drop experiment_id column if it exists
            if 'experiment_id' in columns:
                batch_op.drop_column('experiment_id')
        
        # Create index on experiment_fk if it doesn't exist (outside batch mode)
        if 'ix_experimental_results_experiment_fk' not in indexes:
            op.create_index('ix_experimental_results_experiment_fk', 'experimental_results', ['experiment_fk'], unique=False)


def downgrade() -> None:
    """Downgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    
    # Check if experimental_results table exists and get its current structure
    if 'experimental_results' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('experimental_results')]
        indexes = [idx['name'] for idx in inspector.get_indexes('experimental_results')]
        constraints = [con['name'] for con in inspector.get_unique_constraints('experimental_results')]
        
        # Drop the experiment_fk index if it exists (outside batch mode)
        if 'ix_experimental_results_experiment_fk' in indexes:
            op.drop_index('ix_experimental_results_experiment_fk', table_name='experimental_results')
        
        # Use batch mode for constraint and column operations (SQLite limitation)
        with op.batch_alter_table('experimental_results', schema=None) as batch_op:
            # Add back experiment_id column if it doesn't exist
            if 'experiment_id' not in columns:
                batch_op.add_column(sa.Column('experiment_id', sa.VARCHAR(), nullable=False))
            
            # Create the unique constraint if it doesn't exist
            if 'uix_experiment_time' not in constraints:
                batch_op.create_unique_constraint('uix_experiment_time', ['experiment_fk', 'time_post_reaction'])
        
        # Create the experiment_id index AFTER batch mode completes (outside batch mode)
        if 'ix_experimental_results_experiment_id' not in indexes:
            op.create_index('ix_experimental_results_experiment_id', 'experimental_results', ['experiment_id'], unique=False)
        
        # Note: time_post_reaction nullable=False change is handled by SQLAlchemy model definition
