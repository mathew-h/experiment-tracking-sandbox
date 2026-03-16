"""gross ammonium conc, background ammonium conc

Revision ID: 0e0dac437037
Revises: ae024eb31357
Create Date: 2025-12-30 12:49:43.620004

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e0dac437037'
down_revision: Union[str, None] = 'ae024eb31357'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent."""
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
    
    # Check what operations are needed
    has_old_column = 'solution_ammonium_concentration' in columns
    has_new_column = 'gross_ammonium_concentration' in columns
    has_background_column = 'background_ammonium_concentration' in columns
    
    # Only perform operations if needed (idempotency)
    if has_old_column or not has_background_column:
        with op.batch_alter_table('scalar_results', schema=None) as batch_op:
            # Rename column if old name exists and new name doesn't
            if has_old_column and not has_new_column:
                batch_op.alter_column('solution_ammonium_concentration',
                                      new_column_name='gross_ammonium_concentration',
                                      existing_type=sa.Float(),
                                      nullable=True)
            # Add background column if it doesn't exist
            if not has_background_column:
                batch_op.add_column(sa.Column('background_ammonium_concentration', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema - SQLite compatible and idempotent."""
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
    
    # Check what operations are needed
    has_new_column = 'gross_ammonium_concentration' in columns
    has_old_column = 'solution_ammonium_concentration' in columns
    has_background_column = 'background_ammonium_concentration' in columns
    
    # Only perform operations if needed (idempotency)
    if has_background_column or has_new_column:
        with op.batch_alter_table('scalar_results', schema=None) as batch_op:
            # Drop background column if it exists
            if has_background_column:
                batch_op.drop_column('background_ammonium_concentration')
            # Rename back if new name exists and old name doesn't
            if has_new_column and not has_old_column:
                batch_op.alter_column('gross_ammonium_concentration',
                                      new_column_name='solution_ammonium_concentration',
                                      existing_type=sa.Float(),
                                      nullable=True)
