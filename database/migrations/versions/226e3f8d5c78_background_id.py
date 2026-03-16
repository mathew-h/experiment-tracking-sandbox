"""background id

Revision ID: 226e3f8d5c78
Revises: 0e0dac437037
Create Date: 2026-01-14 09:28:05.165165

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '226e3f8d5c78'
down_revision: Union[str, None] = '0e0dac437037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add background_experiment_id and background_experiment_fk columns to scalar_results - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    all_tables = inspector.get_table_names()
    columns = [col['name'] for col in inspector.get_columns('scalar_results')]
    
    # CRITICAL: Clean up leftover temp tables from failed migrations
    temp_table = '_alembic_tmp_scalar_results'
    if temp_table in all_tables:
        op.drop_table(temp_table)
    
    # Add background_experiment_id column (String, nullable) - stores the experiment ID as text
    if 'background_experiment_id' not in columns:
        op.add_column('scalar_results', sa.Column('background_experiment_id', sa.String(), nullable=True))
    
    # Add background_experiment_fk column (Integer, nullable) - FK to experiments.id
    # Note: Skipping FK constraint creation (SQLite limitation); relationship is defined in the model
    if 'background_experiment_fk' not in columns:
        op.add_column('scalar_results', sa.Column('background_experiment_fk', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Remove background_experiment_id and background_experiment_fk columns - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('scalar_results')]
    
    # Drop columns only if they exist
    if 'background_experiment_fk' in columns:
        op.drop_column('scalar_results', 'background_experiment_fk')
    
    if 'background_experiment_id' in columns:
        op.drop_column('scalar_results', 'background_experiment_id')
