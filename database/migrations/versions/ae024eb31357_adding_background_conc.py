"""Adding background conc.

Revision ID: ae024eb31357
Revises: f081c805d28b
Create Date: 2025-12-26 13:21:23.909140

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae024eb31357'
down_revision: Union[str, None] = 'f081c805d28b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - SQLite compatible and idempotent.
    
    Changes solution_ammonium_concentration to split into:
    - gross_ammonium_concentration: Total measured ammonium
    - background_ammonium_concentration: Background/blank correction
    """
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('scalar_results')]
    
    # Add new columns only if they don't exist
    if 'gross_ammonium_concentration' not in columns:
        op.add_column('scalar_results', sa.Column('gross_ammonium_concentration', sa.Float(), nullable=True))
    
    if 'background_ammonium_concentration' not in columns:
        op.add_column('scalar_results', sa.Column('background_ammonium_concentration', sa.Float(), nullable=True))
    
    # Drop old columns using batch mode (SQLite requirement for column drops)
    with op.batch_alter_table('scalar_results', schema=None) as batch_op:
        if 'solution_ammonium_concentration' in columns:
            batch_op.drop_column('solution_ammonium_concentration')
        if 'ammonium_quant_method' in columns:
            batch_op.drop_column('ammonium_quant_method')


def downgrade() -> None:
    """Downgrade schema - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('scalar_results')]
    
    # Add back old columns only if they don't exist
    if 'ammonium_quant_method' not in columns:
        op.add_column('scalar_results', sa.Column('ammonium_quant_method', sa.VARCHAR(), nullable=True))
    
    if 'solution_ammonium_concentration' not in columns:
        op.add_column('scalar_results', sa.Column('solution_ammonium_concentration', sa.FLOAT(), nullable=True))
    
    # Drop new columns using batch mode
    with op.batch_alter_table('scalar_results', schema=None) as batch_op:
        if 'background_ammonium_concentration' in columns:
            batch_op.drop_column('background_ammonium_concentration')
        if 'gross_ammonium_concentration' in columns:
            batch_op.drop_column('gross_ammonium_concentration')
