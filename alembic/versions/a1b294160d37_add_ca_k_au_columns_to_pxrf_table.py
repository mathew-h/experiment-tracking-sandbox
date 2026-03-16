"""Add Ca, K, Au columns to pXRF table

Revision ID: a1b294160d37
Revises: ba9098fe51ba
Create Date: 2025-11-04 12:51:42.414811

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b294160d37'
down_revision: Union[str, None] = 'ba9098fe51ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Ca, K, Au columns to pXRF table - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('pxrf_readings')]
    
    # Add columns only if they don't exist (idempotent)
    if 'Ca' not in columns:
        op.add_column('pxrf_readings', sa.Column('Ca', sa.Float(), nullable=True))
    
    if 'K' not in columns:
        op.add_column('pxrf_readings', sa.Column('K', sa.Float(), nullable=True))
    
    if 'Au' not in columns:
        op.add_column('pxrf_readings', sa.Column('Au', sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove Ca, K, Au columns from pXRF table - SQLite compatible and idempotent."""
    from alembic import context
    from sqlalchemy import inspect
    
    conn = context.get_context().bind
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('pxrf_readings')]
    
    # Drop columns only if they exist (idempotent)
    if 'Au' in columns:
        op.drop_column('pxrf_readings', 'Au')
    
    if 'K' in columns:
        op.drop_column('pxrf_readings', 'K')
    
    if 'Ca' in columns:
        op.drop_column('pxrf_readings', 'Ca')
